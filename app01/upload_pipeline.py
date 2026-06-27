import csv
import io
import json  # used by detect_file_type_llm
import logging
import re
import statistics
import urllib.request  # used by detect_file_type_llm
from collections import defaultdict
from dataclasses import dataclass, replace as dc_replace

_logger = logging.getLogger(__name__)


class _BytesFile:
    """Wraps bytes as a file-like object with a read() method. Avoids closure bugs in loops."""
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data


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
    warnings: list = None  # populated post-init

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


@dataclass
class ParsedTransfectionFile:
    cell_line: str
    notes: str
    mapping: dict  # {'siRNA-01': 'BPR_3M03FN01', ...}
    warnings: list = None  # populated post-init

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


@dataclass
class ParsedInVivoTimepoint:
    time: float
    mean: float
    sd: float
    n: int


@dataclass
class ParsedInVivoGroup:
    compound_id: str
    dose: str       # e.g. "3mpk"; empty for KD files or control groups
    schedule: str   # e.g. "Q2W*3"; from body-weight header 3rd token
    timepoints: list  # List[ParsedInVivoTimepoint]

    @property
    def dose_info(self):
        return ' '.join(p for p in [self.dose, self.schedule] if p)


@dataclass
class ParsedInVivoFile:
    readout_type: str        # 'knockdown_pct' | 'body_weight'
    groups: list             # List[ParsedInVivoGroup]
    inferred_time_unit: str  # 'day' | 'unknown'
    needs_dose: bool


@dataclass
class StrandDiff:
    compound_id: str
    strand_type: str
    old_seq: str
    new_seq: str
    diff_positions: list  # 0-indexed positions where bases differ
    user_choice: str = None  # 'keep' | 'overwrite' — set by preview page


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
        m = re.match(r'^BPR[A-Z0-9]+-[A-Z]{2}(\d{2,3})$', cid)
        if not m:
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
        m = re.match(r'^(BPR[A-Z0-9]+-[A-Z]{2})(\d{2,3})$', cid)
        if not m:
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


def canonicalize_compound_id(raw_id: str, project_code: str) -> str:
    """Normalize raw_id to BPR<project_code>-<serial> form.

    Returns raw_id unchanged if project_code is absent from the ID (control compounds).
    """
    if not raw_id or not project_code:
        return raw_id
    if raw_id.startswith(f'BPR{project_code}-'):
        return raw_id
    serial = None
    for prefix in (
        f'BPR_{project_code}',
        f'BPR-{project_code}',
        f'BPR{project_code}-',
        f'BPR{project_code}',
        project_code,
    ):
        if raw_id.startswith(prefix):
            serial = raw_id[len(prefix):]
            break
    if serial is None:
        return raw_id
    serial = serial.lstrip('-')
    if not serial:
        return raw_id
    return f'BPR{project_code}-{serial}'


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
    gene_detected = False
    for row in rows:
        if len(row) > 6:
            c3 = row[3].strip()
            c6 = row[6].strip()
            if (c3 and re.match(r'^[A-Z][A-Z0-9]*$', c3) and
                    c6 and re.match(r'^[A-Z][A-Z0-9]*$', c6) and c3 != c6):
                reference_gene = c3
                target_gene = c6
                gene_detected = True
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

    cp_warnings = []
    if not gene_detected:
        cp_warnings.append('未检测到基因名，已使用默认值 GAPDH/FASN，请确认文件格式')
    return ParsedCpFile(
        assay_name=assay_name,
        reference_gene=reference_gene,
        target_gene=target_gene,
        cp_data=dict(cp_data),
        warnings=cp_warnings,
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


def detect_cross_format_match(new_ids: list) -> dict:
    """
    For IDs not found in DB exactly, check whether their zero-padding
    counterpart (2-digit ↔ 3-digit) already exists.
    Returns {file_id: db_id} for each cross-format match found.
    Handles mixed-format lists by checking each group independently.
    e.g. {'BPR_3M03FN001': 'BPR_3M03FN01'}
    """
    from app01.models import Compound
    if not new_ids:
        return {}
    result = {}
    three_digit = [cid for cid in new_ids if re.match(r'^BPR_[A-Z0-9]+[A-Z]{2}\d{3}$', cid)]
    two_digit   = [cid for cid in new_ids if re.match(r'^BPR_[A-Z0-9]+[A-Z]{2}\d{2}$', cid)]
    if three_digit:
        norm2 = normalize_compound_ids(three_digit, '2-digit')
        existing2 = set(Compound.objects.filter(compound_id__in=norm2).values_list('compound_id', flat=True))
        result.update({o: n for o, n in zip(three_digit, norm2) if n in existing2})
    if two_digit:
        norm3 = normalize_compound_ids(two_digit, '3-digit')
        existing3 = set(Compound.objects.filter(compound_id__in=norm3).values_list('compound_id', flat=True))
        result.update({o: n for o, n in zip(two_digit, norm3) if n in existing3})
    return result


def diff_strands(upload_strands: list) -> list:
    """Compare upload sequences against existing Strand records.

    upload_strands: [{'compound_id': str, 'strand_type': str, 'new_seq': str}]
    Returns list of StrandDiff for every case where the existing record differs.
    """
    from app01.models import Strand
    diffs = []
    for item in upload_strands:
        existing = Strand.objects.filter(
            compound__compound_id=item['compound_id'],
            strand_type=item['strand_type'],
        ).first()
        if existing is None:
            continue
        old_seq = existing.modify_seq or ''
        new_seq = item['new_seq'] or ''
        if old_seq == new_seq:
            continue
        if len(old_seq) == len(new_seq):
            positions = [i for i, (a, b) in enumerate(zip(old_seq, new_seq)) if a != b]
        else:
            positions = list(range(min(len(old_seq), len(new_seq))))
        diffs.append(StrandDiff(
            compound_id=item['compound_id'],
            strand_type=item['strand_type'],
            old_seq=old_seq,
            new_seq=new_seq,
            diff_positions=positions,
        ))
    return diffs


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

    # When uploading seq + summary together with conflicting formats, normalize
    # seq IDs to match the summary's format to avoid creating duplicate compounds.
    if id_format_conflict and seq_by_cid and sum_fmt:
        seq_by_cid = {
            normalize_compound_ids([cid], sum_fmt)[0]: data
            for cid, data in seq_by_cid.items()
        }
        all_compound_ids = set(seq_by_cid.keys()) | {v for v in mapping.values() if v}

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
    # Initialise all mapped compounds to False, then update from actual datapoints
    cp_coverage = {cid: False for cid in mapping.values()}
    for cid, dps in dp_by_cid.items():
        ab_dps = [dp for dp in dps
                  if dp.get('replicate') in ('A', 'B') and not dp.get('is_control')]
        if ab_dps:
            cp_coverage[cid] = all(dp.get('raw_cp') is not None for dp in ab_dps)

    # Group summaries by compound_id
    summary_by_cid = {}
    if summary_parsed:
        for s in summary_parsed.summaries:
            summary_by_cid[s['compound_id']] = s

    # Detect existing vs new
    existing_info = detect_existing_compounds(list(all_compound_ids))

    # Check cross-format matches for ALL seq IDs (both new and existing in DB), so
    # that strands are always directed to the correct-format compound even when a
    # wrong-format compound was previously created in DB.
    seq_ids_for_remap = existing_info['new'] + [
        cid for cid in existing_info['existing'] if cid in seq_by_cid
    ]
    cross_format_remap = detect_cross_format_match(seq_ids_for_remap)
    # IDs that are cross-format matches should not be treated as truly new
    truly_new = [cid for cid in existing_info['new'] if cid not in cross_format_remap]

    # Build new_compounds list (include strand data if available)
    new_compounds = []
    for cid in truly_new:
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

    if cross_format_remap:
        example_file = next(iter(cross_format_remap))
        example_db = cross_format_remap[example_file]
        warnings.append(
            f'序列文件 ID 与数据库格式不同（如 {example_file} → 数据库 {example_db}），'
            f'共 {len(cross_format_remap)} 个，确认后将自动对齐'
        )

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
        'id_format_mismatch': cross_format_remap,
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
    transfection_warnings = []
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
                transfection_warnings.append(
                    f'检测到 siRNA {sirna} 对应多个 compound ID（{mapping[sirna]} 和 {cid}），已使用第一条映射，请核查源文件'
                )
            else:
                mapping[sirna] = cid

    return ParsedTransfectionFile(cell_line=cell_line, notes=notes, mapping=mapping, warnings=transfection_warnings)


# ── In vivo file parsers ─────────────────────────────────────────────────────

def _strip_star(val: str) -> str:
    return val.strip().rstrip('*')


def _parse_header_cell(cell: str) -> tuple:
    """Return (compound_id, dose, schedule) from a single header cell.

    Control groups (purely alphabetic names like Saline, Vehicle) have no dose,
    so the second token is treated as schedule rather than dose.
    """
    parts = cell.split(None, 2)
    if not parts:
        return '', '', ''
    cid = parts[0]
    if not re.search(r'\d', cid):   # alphabetic-only → control group, no dose
        dose = ''
        schedule = parts[1] if len(parts) > 1 else ''
        if len(parts) > 2:
            schedule = (schedule + ' ' + parts[2]).strip()
    else:
        dose = parts[1] if len(parts) > 1 else ''
        schedule = parts[2] if len(parts) > 2 else ''
    return cid, dose, schedule


def _group_header_columns(header_row: list) -> list:
    """Group consecutive identical non-empty header cells; split into compound_id, dose, schedule."""
    groups = []
    current_key = None
    current_indices = []
    for i, cell in enumerate(header_row):
        cell = cell.strip()
        if not cell:
            continue
        if cell != current_key:
            if current_key is not None:
                cid, dose, schedule = _parse_header_cell(current_key)
                groups.append({
                    'compound_id': cid,
                    'dose': dose,
                    'schedule': schedule,
                    'indices': current_indices,
                })
            current_key = cell
            current_indices = [i]
        else:
            current_indices.append(i)
    if current_key is not None:
        cid, dose, schedule = _parse_header_cell(current_key)
        groups.append({
            'compound_id': cid,
            'dose': dose,
            'schedule': schedule,
            'indices': current_indices,
        })
    return groups


def _parse_invivo_rows(rows: list, groups_meta: list, readout_type: str, needs_dose: bool,
                       force_time_unit: str = None) -> ParsedInVivoFile:
    """Shared parsing logic for KD% and body weight files."""
    has_negative_time = False
    group_data = {i: [] for i in range(len(groups_meta))}

    for row in rows[1:]:  # skip header
        if not row or not row[0].strip():
            continue
        try:
            time_val = float(_strip_star(row[0]))
        except ValueError:
            continue
        if time_val < 0:
            has_negative_time = True

        for gi, gm in enumerate(groups_meta):
            values = []
            for col_idx in gm['indices']:
                if col_idx < len(row):
                    raw = _strip_star(row[col_idx])
                    if raw:
                        try:
                            values.append(float(raw))
                        except ValueError:
                            pass
            if values:
                group_data[gi].append((time_val, values))

    result_groups = []
    for gi, gm in enumerate(groups_meta):
        tps = []
        for time_val, values in group_data[gi]:
            n = len(values)
            mean = statistics.mean(values)
            sd = statistics.stdev(values) if n > 1 else 0.0
            tps.append(ParsedInVivoTimepoint(time=time_val, mean=mean, sd=sd, n=n))
        tps.sort(key=lambda tp: tp.time)
        if tps:
            result_groups.append(ParsedInVivoGroup(
                compound_id=gm['compound_id'],
                dose=gm['dose'],
                schedule=gm['schedule'],
                timepoints=tps,
            ))

    if force_time_unit:
        inferred_time_unit = force_time_unit
    else:
        inferred_time_unit = 'day' if has_negative_time else 'unknown'

    return ParsedInVivoFile(
        readout_type=readout_type,
        groups=result_groups,
        inferred_time_unit=inferred_time_unit,
        needs_dose=needs_dose,
    )


def parse_invivo_kd_file(file) -> ParsedInVivoFile:
    """Parse Data2-format in vivo KD% file (bare compound IDs in header, no dose info)."""
    try:
        text = _read_csv_text(file)
        rows = list(csv.reader(io.StringIO(text)))
        if len(rows) < 2:
            return ParsedInVivoFile(readout_type='knockdown_pct', groups=[], inferred_time_unit='unknown', needs_dose=True)
        groups_meta = _group_header_columns(rows[0])
        for gm in groups_meta:
            gm['dose'] = ''
            gm['schedule'] = ''
        return _parse_invivo_rows(rows, groups_meta, 'knockdown_pct', needs_dose=True)
    except Exception:
        _logger.exception('parse_invivo_kd_file failed')
        return ParsedInVivoFile(readout_type='knockdown_pct', groups=[], inferred_time_unit='unknown', needs_dose=True)


def parse_body_weight_file(file) -> ParsedInVivoFile:
    """Parse Data3-format body weight file (compound + dose + schedule in header).

    Applies BPR_ prefix to numeric compound IDs (e.g. 350025087 → BPR_350025087).
    Named controls (Saline, Vehicle, …) are stored as-is.
    Time unit is always 'day' for body weight studies.
    """
    try:
        text = _read_csv_text(file)
        rows = list(csv.reader(io.StringIO(text)))
        if len(rows) < 2:
            return ParsedInVivoFile(readout_type='body_weight', groups=[], inferred_time_unit='day', needs_dose=False)
        groups_meta = _group_header_columns(rows[0])
        result = _parse_invivo_rows(rows, groups_meta, 'body_weight', needs_dose=False, force_time_unit='day')
        # Apply BPR_ prefix to numeric compound IDs
        fixed_groups = []
        for g in result.groups:
            cid = g.compound_id
            if re.match(r'^\d', cid):
                cid = 'BPR_' + cid
            fixed_groups.append(ParsedInVivoGroup(
                compound_id=cid, dose=g.dose, schedule=g.schedule, timepoints=g.timepoints
            ))
        return dc_replace(result, groups=fixed_groups)
    except Exception:
        _logger.exception('parse_body_weight_file failed')
        return ParsedInVivoFile(readout_type='body_weight', groups=[], inferred_time_unit='day', needs_dose=False)


def detect_invivo_file_type(file) -> str:
    """Return 'knockdown_pct', 'body_weight', or 'unknown'."""
    try:
        text = _read_csv_text(file)
        rows = list(csv.reader(io.StringIO(text)))
        if not rows:
            return 'unknown'
        header = [h.strip() for h in rows[0] if h.strip()]

        # Body weight: any header cell has 2+ words (compound + dose info)
        if any(len(h.split()) >= 2 for h in header):
            return 'body_weight'

        # KD%: single-word headers + values are all <= 10 (knockdown range -100 to ~0)
        all_values = []
        for row in rows[1:]:
            for cell in row[1:]:
                raw = _strip_star(cell)
                if raw:
                    try:
                        all_values.append(float(raw))
                    except ValueError:
                        pass

        if all_values and max(all_values) <= 10:
            return 'knockdown_pct'

        # Body weight values are typically > 10
        if all_values and min(all_values) > 10:
            return 'body_weight'

        return 'unknown'
    except Exception:
        _logger.exception('detect_invivo_file_type failed')
        return 'unknown'


def detect_file_type_rules(file) -> str:
    """Rule-based file type detection. Returns one of the 7 labels or 'unknown'."""
    try:
        file_bytes = file.read()

        # Check vitro file types first (header-keyword rules take priority)
        text = _read_csv_text(_BytesFile(file_bytes))
        rows = list(csv.reader(io.StringIO(text)))
        if not rows:
            return 'unknown'

        header = ' '.join(c.strip() for c in rows[0]).lower()
        if re.search(r'ic50|max.?kd', header):
            return 'vitro_summary'
        if re.search(r'modify.?seq|sequence.?id|sirnaid', header):
            return 'vitro_seq'
        if re.search(r'sirna|transfection', header):
            return 'vitro_transfection'

        header_cells = [c.strip().lower() for c in rows[0] if c.strip()]
        if any(re.match(r'^cp[\s_]?\d*$', cell) for cell in header_cells):
            body_values = []
            for row in rows[1:6]:
                for cell in row[1:]:
                    s = cell.strip()
                    if s:
                        try:
                            body_values.append(float(s))
                        except ValueError:
                            pass
            if body_values and all(10 <= v <= 45 for v in body_values):
                return 'vitro_cp'

        # Fall back to in-vivo detection
        invivo_result = detect_invivo_file_type(_BytesFile(file_bytes))
        if invivo_result == 'knockdown_pct':
            return 'invivo_kd'
        if invivo_result == 'body_weight':
            return 'invivo_bw'

        return 'unknown'
    except Exception:
        _logger.exception('detect_file_type_rules failed')
        return 'unknown'


def detect_file_type_llm(filename: str, file) -> str:
    """Call DeepSeek to classify a CSV file. Returns one of the 7 labels or 'unknown' on failure."""
    from django.conf import settings
    api_key = getattr(settings, 'DEEPSEEK_API_KEY', '')
    api_url = getattr(settings, 'DEEPSEEK_API_URL', 'https://api.deepseek.com/chat/completions')
    model = getattr(settings, 'DEEPSEEK_MODEL', 'deepseek-chat')

    if not api_key:
        _logger.warning('detect_file_type_llm: DEEPSEEK_API_KEY not configured')
        return 'unknown'

    valid_labels = {
        'vitro_seq', 'vitro_summary', 'vitro_cp',
        'vitro_transfection', 'invivo_kd', 'invivo_bw', 'unknown',
    }

    try:
        file_bytes = file.read()
        text = _read_csv_text(_BytesFile(file_bytes))
        rows = list(csv.reader(io.StringIO(text)))[:20]
        csv_preview = '\n'.join(','.join(row) for row in rows)
    except Exception:
        _logger.warning('detect_file_type_llm: failed to read CSV preview')
        return 'unknown'

    prompt = (
        f'You are classifying pharmaceutical research CSV files. The file is named "{filename}".\n'
        f'Here are the first rows:\n\n{csv_preview}\n\n'
        'Respond with EXACTLY one label from this list:\n'
        'vitro_seq, vitro_summary, vitro_cp, vitro_transfection, invivo_kd, invivo_bw, unknown\n\n'
        'Definitions:\n'
        '- vitro_seq: sequence file with compound IDs and modification sequences\n'
        '- vitro_summary: in vitro summary with IC50/MaxKD values per compound\n'
        '- vitro_cp: raw RT-qPCR Cp values (LightCycler or similar format)\n'
        '- vitro_transfection: siRNA-to-compound mapping with cell line and transfection notes\n'
        '- invivo_kd: in vivo knockdown % time-course; headers are bare compound IDs repeated per replicate\n'
        '- invivo_bw: in vivo body weight time-course; headers are "compound dose schedule" per replicate\n'
        '- unknown: none of the above\n\n'
        'Respond with only the label, nothing else.'
    )

    payload = json.dumps({
        'model': model,
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 20,
        'temperature': 0,
    }).encode('utf-8')

    req = urllib.request.Request(
        api_url,
        data=payload,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
        label = result['choices'][0]['message']['content'].strip().lower()
        return label if label in valid_labels else 'unknown'
    except Exception:
        _logger.warning('detect_file_type_llm: API call failed')
        return 'unknown'
