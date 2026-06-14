import csv
import io
import logging
import re
from collections import defaultdict
from dataclasses import dataclass

_logger = logging.getLogger(__name__)


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class ParsedSeqFile:
    rows: list      # [{'compound_id': str, 'ss_seq': str, 'as_seq': str}]
    id_format: str  # '2-digit' | '3-digit' | 'mixed'


@dataclass
class ParsedSummary:
    assay_name: str
    mapping: dict      # {'siRNA-01': 'BPR_3M03FN01', ...}
    datapoints: list   # [{'compound_id', 'x_value', 'x_type', 'replicate', 'value', 'is_control', 'readout_type', 'raw_cp'}]
    summaries: list    # [{'compound_id', 'max_kd_pct', 'ic50_nm', 'rank'}]
    mock_values: dict  # {'A': 1.07, 'B': 0.94, 'Mean': 1.01}


@dataclass
class ParsedCpFile:
    assay_name: str
    reference_gene: str
    target_gene: str
    cp_data: dict  # {(siRNA_label, dose_float): {'rep_A': {gene: {A,B,C}}, 'rep_B': {...}}}


@dataclass
class ParsedTransfectionFile:
    cell_line: str
    notes: str
    mapping: dict  # {'siRNA-01': 'BPR_3M03FN01', ...}


# ── Internal helpers ─────────────────────────────────────────────────────────

def _read_csv_text(file) -> str:
    raw = file.read()
    for enc in ('utf-8-sig', 'utf-8', 'gbk'):
        try:
            return raw.decode(enc).removeprefix('﻿')
        except (UnicodeDecodeError, AttributeError):
            continue
    return raw.decode('utf-8', errors='replace').removeprefix('﻿')


# ── Public functions ─────────────────────────────────────────────────────────

def detect_id_format(compound_ids: list) -> str:
    """Return '2-digit', '3-digit', or 'mixed' based on serial number length."""
    formats = set()
    for cid in compound_ids:
        m = re.match(r'^BPR_[A-Z0-9]+[A-Z]{2}(\d{2,3})$', cid)
        if m:
            formats.add('2-digit' if len(m.group(1)) == 2 else '3-digit')
    if not formats:
        return '2-digit'
    return formats.pop() if len(formats) == 1 else 'mixed'


def normalize_compound_ids(ids: list, target_format: str) -> list:
    """Normalize BPR compound IDs to 2-digit or 3-digit serial number."""
    result = []
    for cid in ids:
        m = re.match(r'^(BPR_[A-Z0-9]+[A-Z]{2})(\d{2,3})$', cid)
        if not m:
            result.append(cid)
            continue
        prefix, num_str = m.group(1), m.group(2)
        n = int(num_str)
        if target_format == '2-digit':
            result.append(f'{prefix}{n:02d}' if n <= 99 else cid)
        else:
            result.append(f'{prefix}{n:03d}')
    return result


def parse_seq_file(file) -> ParsedSeqFile:
    """Parse ID_sequence.csv (columns: siRNAID, SS, AS)."""
    text = _read_csv_text(file)
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        cid = (row.get('siRNAID') or '').strip()
        if not cid:
            continue
        rows.append({
            'compound_id': cid,
            'ss_seq': (row.get('SS') or '').strip(),
            'as_seq': (row.get('AS') or '').strip(),
        })
    return ParsedSeqFile(
        rows=rows,
        id_format=detect_id_format([r['compound_id'] for r in rows]),
    )


def parse_summary_csv(file) -> 'ParsedSummary':
    """Parse Prism 1_summary.csv format (dose-response left table + mapping/IC50 right table)."""
    text = _read_csv_text(file)
    rows = list(csv.reader(io.StringIO(text)))

    # Find header row containing 'Dose (nM)' and 'IC50'
    header_idx = None
    for i, row in enumerate(rows):
        if any(c.strip() == 'Dose (nM)' for c in row) and any('IC50' in c for c in row):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("无法识别为体外汇总表格式（未找到含 'Dose (nM)' 和 'IC50' 的行）")

    header = rows[header_idx]

    # Detect column positions from header row
    dose_col = next(j for j, c in enumerate(header) if c.strip() == 'Dose (nM)')
    id_col = dose_col - 1
    a_col = dose_col + 1
    b_col = dose_col + 2
    mean_col = dose_col + 3

    ic50_col = next(j for j, c in enumerate(header) if 'IC50' in c)
    r_id_col = ic50_col - 3    # siRNA label column in right table
    r_name_col = ic50_col - 2  # BPR compound ID
    r_maxkd_col = ic50_col - 1
    r_rank_col = ic50_col + 1

    # Extract assay_name from first non-empty row before the header
    assay_name = ''
    for i in range(header_idx - 1, -1, -1):
        non_empty = [c.strip() for c in rows[i] if c.strip()]
        if non_empty:
            assay_name = non_empty[0]
            break

    mapping = {}
    summaries = []
    datapoints = []
    mock_values = {}

    def _safe_float(s):
        try:
            return float(s.strip()) if s.strip() else None
        except ValueError:
            return None

    def _safe_int(s):
        try:
            return int(float(s.strip())) if s.strip() else None
        except ValueError:
            return None

    needed = max(mean_col, r_rank_col) + 1
    for row in rows[header_idx + 1:]:
        row = row + [''] * max(0, needed - len(row))

        # Right table: extract mapping and summaries
        r_id = row[r_id_col].strip()
        r_name = row[r_name_col].strip()
        if re.match(r'^siRNA-\d+$', r_id) and re.match(r'^BPR_', r_name):
            mapping[r_id] = r_name
            summaries.append({
                'compound_id': r_name,
                'max_kd_pct': _safe_float(row[r_maxkd_col]),
                'ic50_nm': _safe_float(row[ic50_col]),
                'rank': _safe_int(row[r_rank_col]),
            })

        # Left table: extract dose-response data
        siRNA = row[id_col].strip()
        dose_str = row[dose_col].strip()
        if not siRNA or not dose_str:
            continue

        is_mock = dose_str.upper() == 'MOCK' or siRNA.upper() == 'MOCK'
        if is_mock:
            try:
                if not mock_values:
                    mock_values = {
                        'A': float(row[a_col]) if row[a_col].strip() else None,
                        'B': float(row[b_col]) if row[b_col].strip() else None,
                        'Mean': float(row[mean_col]) if row[mean_col].strip() else None,
                    }
            except ValueError:
                pass
            continue

        try:
            x_value = float(dose_str)
        except ValueError:
            continue

        for rep, col_idx in [('A', a_col), ('B', b_col), ('Mean', mean_col)]:
            val_str = row[col_idx].strip()
            if not val_str:
                continue
            try:
                datapoints.append({
                    'siRNA_label': siRNA,
                    'x_value': x_value,
                    'x_type': 'concentration',
                    'replicate': rep,
                    'value': float(val_str),
                    'is_control': False,
                    'readout_type': 'mRNA_remaining',
                    'raw_cp': None,
                })
            except ValueError:
                pass

    # Resolve siRNA labels → compound IDs; drop datapoints with no mapping
    resolved = []
    for dp in datapoints:
        cid = mapping.get(dp.pop('siRNA_label'), '')
        if cid:
            dp['compound_id'] = cid
            resolved.append(dp)
    datapoints = resolved

    return ParsedSummary(
        assay_name=assay_name,
        mapping=mapping,
        datapoints=datapoints,
        summaries=summaries,
        mock_values=mock_values,
    )


def parse_cp_file(file) -> 'ParsedCpFile':
    """Parse Prism two-step RT-qPCR raw Cp CSV.

    Detects reference/target genes from header rows.
    Each (siRNA, dose) pair appears twice: first occurrence = rep_A, second = rep_B.
    """
    text = _read_csv_text(file)
    rows = list(csv.reader(io.StringIO(text)))

    # Extract assay_name from the first non-empty row after row 0
    assay_name = ''
    for row in rows[1:]:
        candidates = [c.strip() for c in row if c.strip()]
        if candidates:
            assay_name = candidates[0]
            break

    # Detect reference/target genes: find a header row where col[3] and col[6]
    # are uppercase alphabetic gene names (e.g. GAPDH, FASN)
    reference_gene = 'GAPDH'
    target_gene = 'FASN'
    for row in rows:
        if len(row) > 6:
            c3 = row[3].strip()
            c6 = row[6].strip()
            if (c3 and re.match(r'^[A-Z][A-Z0-9]*$', c3) and
                    c6 and re.match(r'^[A-Z][A-Z0-9]*$', c6) and c3 != c6):
                reference_gene = c3
                target_gene = c6
                break

    # Parse data rows: col[1] = siRNA label, col[2] = dose, col[3:6] = ref Cp, col[6:9] = tgt Cp
    cp_data = {}
    occurrence_count = defaultdict(int)

    for row in rows:
        if len(row) < 9:
            continue
        siRNA = row[1].strip()
        dose_str = row[2].strip()
        if not re.match(r'^siRNA-\d+$', siRNA):
            continue
        try:
            dose = float(dose_str)
            ref_cp = {'A': float(row[3]), 'B': float(row[4]), 'C': float(row[5])}
            tgt_cp = {'A': float(row[6]), 'B': float(row[7]), 'C': float(row[8])}
        except (ValueError, IndexError):
            continue

        key = (siRNA, dose)
        occurrence_count[key] += 1
        count = occurrence_count[key]
        if count > 2:
            continue
        rep_key = 'rep_A' if count == 1 else 'rep_B'

        if key not in cp_data:
            cp_data[key] = {}
        cp_data[key][rep_key] = {
            reference_gene: ref_cp,
            target_gene: tgt_cp,
        }

    return ParsedCpFile(
        assay_name=assay_name,
        reference_gene=reference_gene,
        target_gene=target_gene,
        cp_data=cp_data,
    )


def enrich_datapoints_with_cp(datapoints: list, cp_data: dict, mapping: dict) -> list:
    """Attach raw_cp dict to replicate A and B DataPoints; Mean DataPoints stay None."""
    reverse_mapping = {v: k for k, v in mapping.items()}
    result = []
    for dp in datapoints:
        dp = dict(dp)
        cid = dp.get('compound_id', '')
        siRNA_label = reverse_mapping.get(cid, '')
        dose = dp.get('x_value', 0.0)
        rep = dp.get('replicate', '')
        key = (siRNA_label, dose)
        if key in cp_data and rep in ('A', 'B'):
            rep_key = f'rep_{rep}'
            if rep_key in cp_data[key]:
                dp['raw_cp'] = cp_data[key][rep_key]
        result.append(dp)
    return result


def detect_existing_compounds(compound_ids: list) -> dict:
    """Query DB to split compound_ids into existing and new."""
    from app01.models import Compound
    if not compound_ids:
        return {'existing': [], 'new': []}
    existing_set = set(
        Compound.objects.filter(compound_id__in=compound_ids)
        .values_list('compound_id', flat=True)
    )
    existing = [cid for cid in compound_ids if cid in existing_set]
    new = [cid for cid in compound_ids if cid not in existing_set]
    return {'existing': existing, 'new': new}


def build_preview(seq_parsed, summary_parsed, cp_parsed_list,
                  batch_label: str, assay_name: str, exp_date: str = None,
                  transfection_parsed=None) -> dict:
    """Assemble session preview dict from parsed file data."""
    all_compound_ids = set()
    seq_by_cid = {}

    if seq_parsed:
        for row in seq_parsed.rows:
            cid = row['compound_id']
            all_compound_ids.add(cid)
            seq_by_cid[cid] = row

    mapping = {}
    if summary_parsed:
        mapping = dict(summary_parsed.mapping)
        for cid in mapping.values():
            all_compound_ids.add(cid)
        if not assay_name and summary_parsed.assay_name:
            assay_name = summary_parsed.assay_name

    # Merge transfection mapping (summary takes precedence on conflict)
    cell_line = ''
    notes = ''
    if transfection_parsed:
        cell_line = transfection_parsed.cell_line
        notes = transfection_parsed.notes
        for sirna, cid in transfection_parsed.mapping.items():
            if sirna not in mapping:
                mapping[sirna] = cid
                all_compound_ids.add(cid)

    # Detect ID format conflict between seq file and summary
    seq_fmt = seq_parsed.id_format if seq_parsed else None
    sum_fmt = detect_id_format(list(mapping.values())) if mapping else None
    id_format_conflict = bool(
        seq_fmt and sum_fmt
        and seq_fmt != 'mixed' and sum_fmt != 'mixed'
        and seq_fmt != sum_fmt
    )

    # Enrich datapoints with Cp data
    datapoints = list(summary_parsed.datapoints) if summary_parsed else []
    for cp_parsed in (cp_parsed_list or []):
        datapoints = enrich_datapoints_with_cp(datapoints, cp_parsed.cp_data, mapping)

    # Group datapoints by compound_id
    dp_by_cid = defaultdict(list)
    for dp in datapoints:
        cid = dp.get('compound_id', '')
        if cid:
            dp_by_cid[cid].append(dp)

    # Cp coverage: True if all non-control A/B DataPoints for a compound have raw_cp
    cp_coverage = {}
    for cid, dps in dp_by_cid.items():
        ab_dps = [dp for dp in dps
                  if dp.get('replicate') in ('A', 'B') and not dp.get('is_control')]
        if ab_dps:
            cp_coverage[cid] = all(dp.get('raw_cp') is not None for dp in ab_dps)
        else:
            cp_coverage[cid] = False

    # Group summaries by compound_id
    summary_by_cid = {}
    if summary_parsed:
        for s in summary_parsed.summaries:
            summary_by_cid[s['compound_id']] = s

    # Detect existing vs new
    existing_info = detect_existing_compounds(list(all_compound_ids))

    # Build new_compounds list (include strand data if available)
    new_compounds = []
    for cid in existing_info['new']:
        entry = {'compound_id': cid}
        if cid in seq_by_cid:
            entry['ss_seq'] = seq_by_cid[cid]['ss_seq']
            entry['as_seq'] = seq_by_cid[cid]['as_seq']
        new_compounds.append(entry)

    # strand_map: all compound IDs (new + existing) that have sequence data.
    # Keys use the seq file's original IDs; upload_confirm_view resolves them
    # after any ID-format normalisation.
    strand_map = {
        cid: {'ss_seq': row['ss_seq'], 'as_seq': row['as_seq']}
        for cid, row in seq_by_cid.items()
    }

    # Mock DataPoints template (added to each experiment)
    mock_dps_template = []
    if summary_parsed and summary_parsed.mock_values:
        for rep, val in summary_parsed.mock_values.items():
            if val is not None:
                mock_dps_template.append({
                    'x_value': 0.0, 'x_type': 'concentration',
                    'replicate': rep, 'value': val,
                    'is_control': True, 'readout_type': 'mRNA_remaining', 'raw_cp': None,
                })

    # Build experiments (one per unique mapped compound, preserving first-seen order)
    experiments = []
    for cid in dict.fromkeys(v for v in mapping.values() if v):
        mock_dps = [{**dp, 'compound_id': cid} for dp in mock_dps_template]
        exp = {
            'compound_id': cid,
            'exp_type': 'in_vitro',
            'datapoints': dp_by_cid.get(cid, []) + mock_dps,
        }
        if cid in summary_by_cid:
            s = summary_by_cid[cid]
            exp['summary'] = {k: v for k, v in s.items() if k != 'compound_id'}
        experiments.append(exp)

    warnings, errors = [], []

    for cid in existing_info['existing']:
        warnings.append(f'{cid} 已存在，将追加新批次数据')

    if summary_parsed and not cp_parsed_list:
        warnings.append('未上传原始 Cp 文件，raw_cp 将为空')

    if id_format_conflict:
        warnings.append(f'ID 格式冲突：序列文件使用 {seq_fmt}，汇总表使用 {sum_fmt}')

    if not summary_parsed and not seq_parsed:
        errors.append('请至少上传序列文件或体外汇总表')

    return {
        'batch_label': batch_label,
        'assay_name': assay_name,
        'exp_date': exp_date,
        'cell_line': cell_line,
        'notes': notes,
        'new_compounds': new_compounds,
        'existing_compounds': existing_info['existing'],
        'id_format_conflict': id_format_conflict,
        'chosen_format': None,
        'mapping': mapping,
        'strand_map': strand_map,
        'experiments': experiments,
        'warnings': warnings,
        'cp_coverage': cp_coverage,
        'errors': errors,
    }


def parse_transfection_file(file) -> ParsedTransfectionFile:
    """Parse transfection protocol CSV (e.g. 5_Transfection in Hepa1-6.csv)."""
    text = _read_csv_text(file)
    rows = list(csv.reader(io.StringIO(text)))

    cell_line = ''
    params = {}
    mapping = {}

    # Cell line from title row "Transfection in <CellLine>"
    if rows and rows[0]:
        m = re.match(r'^Transfection in (.+)$', rows[0][0].strip(), re.IGNORECASE)
        if m:
            cell_line = m.group(1).strip()

    # Parameters table: find header row where col 12 == "Items", col 13 == "Parameters"
    param_header_idx = None
    for i, row in enumerate(rows):
        if len(row) > 13 and row[12].strip() == 'Items' and row[13].strip() == 'Parameters':
            param_header_idx = i
            break

    if param_header_idx is not None:
        note_keys = {'Seeding', 'Plate', 'Duration', 'Analysis', 'Primer'}
        for row in rows[param_header_idx + 1:]:
            if len(row) <= 13:
                continue
            key = row[12].strip()
            val = row[13].strip()
            if not key or not val:
                continue
            if key == 'Cells':
                cell_line = val  # Parameters table overrides title row
            elif key in note_keys:
                params[key] = val

    notes = '; '.join(
        f'{k}: {params[k]}'
        for k in ('Seeding', 'Plate', 'Duration', 'Analysis', 'Primer')
        if k in params
    )

    # siRNA → compound mapping from scattered rows (col 16 = siRNA-XX, col 17 = BPR_...)
    for row in rows:
        if len(row) <= 17:
            continue
        sirna = row[16].strip()
        cid = row[17].strip()
        if re.match(r'^siRNA-\d+$', sirna) and re.match(r'^BPR_', cid):
            if sirna in mapping and mapping[sirna] != cid:
                _logger.warning(
                    'parse_transfection_file: duplicate siRNA key %s maps to %s and %s; keeping first',
                    sirna, mapping[sirna], cid,
                )
            else:
                mapping[sirna] = cid

    return ParsedTransfectionFile(cell_line=cell_line, notes=notes, mapping=mapping)
