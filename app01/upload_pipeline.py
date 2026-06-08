import csv
import io
import re
from dataclasses import dataclass


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


# ── Internal helpers ─────────────────────────────────────────────────────────

def _read_csv_text(file) -> str:
    raw = file.read()
    for enc in ('utf-8-sig', 'utf-8', 'gbk'):
        try:
            text = raw.decode(enc)
            # Strip real BOM (U+FEFF) and mojibake BOM chars (\xef\xbb\xbf decoded as latin-1)
            return text.lstrip('﻿\xef\xbb\xbf')
        except (UnicodeDecodeError, AttributeError):
            continue
    return raw.decode('utf-8', errors='replace').lstrip('﻿\xef\xbb\xbf')


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
        result.append(f'{prefix}{n:02d}' if target_format == '2-digit' else f'{prefix}{n:03d}')
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
    raise NotImplementedError


def parse_cp_file(file) -> 'ParsedCpFile':
    raise NotImplementedError


def enrich_datapoints_with_cp(datapoints: list, cp_data: dict, mapping: dict) -> list:
    raise NotImplementedError


def detect_existing_compounds(compound_ids: list) -> dict:
    raise NotImplementedError


def build_preview(seq_parsed, summary_parsed, cp_parsed_list,
                  batch_label: str, assay_name: str, exp_date: str = None) -> dict:
    raise NotImplementedError
