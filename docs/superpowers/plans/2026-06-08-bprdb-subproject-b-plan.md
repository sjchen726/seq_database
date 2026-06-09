# BPRdb 子项目 B — Smart CSV 上传管道实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现单页 CSV 上传管道：用户上传序列文件和体外汇总表，系统解析、展示预览（含 siRNA→BPR 映射确认），用户点击确认后写入数据库。

**Architecture:** 单页两步式 POST（parse → session → confirm → DB）；解析逻辑全部封装在 `app01/upload_pipeline.py`；三个视图函数（upload_view / upload_confirm_view / upload_success_view）通过 session 传递预览数据。

**Tech Stack:** Django 5.1、Python 3.10、MySQL（通过 Django ORM）、标准库 csv / io / re / dataclasses

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `app01/upload_pipeline.py` | 新建 | 所有 CSV 解析函数 + 数据结构定义 |
| `app01/views.py` | 修改（追加） | `upload_view`、`upload_confirm_view`、`upload_success_view` |
| `bprdb/urls.py` | 修改 | 新增 `/upload/`、`/upload/confirm/`、`/upload/success/` |
| `templates/upload.html` | 新建 | 上传表单 + 预览区 |
| `templates/upload_success.html` | 新建 | 上传成功页 |
| `templates/base.html` | 修改 | 侧边栏添加上传链接 |
| `app01/tests.py` | 修改（追加） | 解析函数单元测试 + 视图集成测试 |

---

### Task 1: upload_pipeline.py 骨架 + parse_seq_file + detect_id_format + normalize_compound_ids

**Files:**
- Create: `app01/upload_pipeline.py`
- Modify: `app01/tests.py`

- [ ] **Step 1: 在 `app01/tests.py` 末尾追加失败测试**

```python
# 在 app01/tests.py 末尾追加以下内容

from io import BytesIO
from app01.upload_pipeline import (
    detect_id_format, normalize_compound_ids, parse_seq_file,
)


class DetectIdFormatTest(TestCase):
    def test_all_2digit(self):
        self.assertEqual(detect_id_format(['BPR_3M03FN01', 'BPR_3M03FN02']), '2-digit')

    def test_all_3digit(self):
        self.assertEqual(detect_id_format(['BPR_3M03FN001', 'BPR_3M03FN002']), '3-digit')

    def test_mixed(self):
        self.assertEqual(detect_id_format(['BPR_3M03FN01', 'BPR_3M03FN002']), 'mixed')

    def test_empty_returns_2digit(self):
        self.assertEqual(detect_id_format([]), '2-digit')


class NormalizeCompoundIdsTest(TestCase):
    def test_3digit_to_2digit(self):
        self.assertEqual(normalize_compound_ids(['BPR_3M03FN001'], '2-digit'), ['BPR_3M03FN01'])

    def test_2digit_to_3digit(self):
        self.assertEqual(normalize_compound_ids(['BPR_3M03FN01'], '3-digit'), ['BPR_3M03FN001'])

    def test_non_bpr_ids_unchanged(self):
        self.assertEqual(normalize_compound_ids(['OTHER_ID'], '2-digit'), ['OTHER_ID'])

    def test_multiple_ids(self):
        result = normalize_compound_ids(['BPR_3M03FN001', 'BPR_3M03FN002'], '2-digit')
        self.assertEqual(result, ['BPR_3M03FN01', 'BPR_3M03FN02'])


class ParseSeqFileTest(TestCase):
    SEQ_CSV = (
        'siRNAID,SS,AS\n'
        'BPR_3M03FN001,GmGmGmGmAmAmAfC,AmCfUmUmdUGmdCC\n'
        'BPR_3M03FN002,UmUmGmUmGmGmCfC,UmUfAmCmdAGmdAG\n'
    )

    def test_parse_rows(self):
        result = parse_seq_file(BytesIO(self.SEQ_CSV.encode()))
        self.assertEqual(len(result.rows), 2)
        self.assertEqual(result.rows[0]['compound_id'], 'BPR_3M03FN001')
        self.assertEqual(result.rows[0]['ss_seq'], 'GmGmGmGmAmAmAfC')
        self.assertEqual(result.rows[0]['as_seq'], 'AmCfUmUmdUGmdCC')

    def test_id_format_detected_as_3digit(self):
        result = parse_seq_file(BytesIO(self.SEQ_CSV.encode()))
        self.assertEqual(result.id_format, '3-digit')

    def test_skips_empty_rows(self):
        csv_content = 'siRNAID,SS,AS\nBPR_3M03FN001,Gm,Am\n,,\n'
        result = parse_seq_file(BytesIO(csv_content.encode()))
        self.assertEqual(len(result.rows), 1)

    def test_bom_handled(self):
        content = '\xef\xbb\xbfsiRNAID,SS,AS\nBPR_3M03FN001,Gm,Am\n'
        result = parse_seq_file(BytesIO(content.encode('utf-8')))
        self.assertEqual(len(result.rows), 1)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_bprdb
source /Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/activate
python manage.py test app01.tests.DetectIdFormatTest app01.tests.NormalizeCompoundIdsTest app01.tests.ParseSeqFileTest -v2 2>&1 | head -20
```

预期输出：`ImportError: cannot import name 'detect_id_format' from 'app01.upload_pipeline'`

- [ ] **Step 3: 创建 `app01/upload_pipeline.py`**

```python
import csv
import io
import re
from collections import defaultdict
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
            return raw.decode(enc)
        except (UnicodeDecodeError, AttributeError):
            continue
    return raw.decode('utf-8', errors='replace')


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


def parse_summary_csv(file) -> ParsedSummary:
    raise NotImplementedError


def parse_cp_file(file) -> ParsedCpFile:
    raise NotImplementedError


def enrich_datapoints_with_cp(datapoints: list, cp_data: dict, mapping: dict) -> list:
    raise NotImplementedError


def detect_existing_compounds(compound_ids: list) -> dict:
    raise NotImplementedError


def build_preview(seq_parsed, summary_parsed, cp_parsed_list,
                  batch_label: str, assay_name: str, exp_date: str = None) -> dict:
    raise NotImplementedError
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python manage.py test app01.tests.DetectIdFormatTest app01.tests.NormalizeCompoundIdsTest app01.tests.ParseSeqFileTest -v2 2>&1 | tail -10
```

预期：`Ran 11 tests in ...s OK`

- [ ] **Step 5: Commit**

```bash
git add app01/upload_pipeline.py app01/tests.py
git commit -m "feat: add upload_pipeline scaffold + parse_seq_file + id format utilities"
```

---

### Task 2: parse_summary_csv

**Files:**
- Modify: `app01/upload_pipeline.py` (实现 `parse_summary_csv`)
- Modify: `app01/tests.py` (追加测试类)

- [ ] **Step 1: 在 `app01/tests.py` 末尾追加测试**

```python
from app01.upload_pipeline import parse_summary_csv


class ParseSummaryCsvTest(TestCase):
    SUMMARY_CSV = (
        '\n'
        ',,,FASN mRNA\n'
        '#,ID,Dose (nM),A,B,Mean,,#,ID,Name,Max KD,IC50 (nM),Rank\n'
        '1,Mock,Mock,1.07,0.94,1.01,,,,,,,\n'
        '2,siRNA-01,100,0.26,0.25,0.25,,1,siRNA-01,BPR_3M03FN01,74.71,5.48,9\n'
        '3,siRNA-01,10,0.47,0.53,0.50,,2,siRNA-02,BPR_3M03FN02,72.39,8.22,10\n'
        '4,siRNA-02,100,0.25,0.30,0.28,,,,,,,\n'
    )

    def setUp(self):
        self.result = parse_summary_csv(BytesIO(self.SUMMARY_CSV.encode()))

    def test_assay_name_extracted(self):
        self.assertEqual(self.result.assay_name, 'FASN mRNA')

    def test_mapping_extracted(self):
        self.assertEqual(self.result.mapping['siRNA-01'], 'BPR_3M03FN01')
        self.assertEqual(self.result.mapping['siRNA-02'], 'BPR_3M03FN02')

    def test_summaries_extracted(self):
        s = next(x for x in self.result.summaries if x['compound_id'] == 'BPR_3M03FN01')
        self.assertAlmostEqual(s['max_kd_pct'], 74.71)
        self.assertAlmostEqual(s['ic50_nm'], 5.48)
        self.assertEqual(s['rank'], 9)

    def test_datapoints_compound_id_resolved(self):
        dp = next(d for d in self.result.datapoints
                  if d['x_value'] == 100.0 and d['replicate'] == 'A')
        self.assertEqual(dp['compound_id'], 'BPR_3M03FN01')
        self.assertAlmostEqual(dp['value'], 0.26)
        self.assertFalse(dp['is_control'])
        self.assertEqual(dp['readout_type'], 'mRNA_remaining')

    def test_datapoints_per_siRNA_dose(self):
        # siRNA-01 at 100nM → 3 DataPoints (A, B, Mean)
        dps = [d for d in self.result.datapoints
               if d['compound_id'] == 'BPR_3M03FN01' and d['x_value'] == 100.0]
        reps = {d['replicate'] for d in dps}
        self.assertEqual(reps, {'A', 'B', 'Mean'})

    def test_mock_values_captured(self):
        self.assertAlmostEqual(self.result.mock_values.get('A'), 1.07)
        self.assertAlmostEqual(self.result.mock_values.get('B'), 0.94)
        self.assertAlmostEqual(self.result.mock_values.get('Mean'), 1.01)

    def test_invalid_format_raises_valueerror(self):
        with self.assertRaises(ValueError):
            parse_summary_csv(BytesIO(b'not,a,summary,file\n1,2,3\n'))
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python manage.py test app01.tests.ParseSummaryCsvTest -v2 2>&1 | head -10
```

预期：`NotImplementedError`

- [ ] **Step 3: 在 `app01/upload_pipeline.py` 中实现 `parse_summary_csv`，替换占位符**

```python
def parse_summary_csv(file) -> ParsedSummary:
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

    for row in rows[header_idx + 1:]:
        needed = max(mean_col, r_rank_col) + 1
        row = row + [''] * max(0, needed - len(row))

        # Right table: extract mapping and summaries
        r_id = row[r_id_col].strip()
        r_name = row[r_name_col].strip()
        if (re.match(r'^siRNA-\d+$', r_id) and re.match(r'^BPR_', r_name)):
            mapping[r_id] = r_name
            try:
                summaries.append({
                    'compound_id': r_name,
                    'max_kd_pct': float(row[r_maxkd_col]) if row[r_maxkd_col].strip() else None,
                    'ic50_nm': float(row[ic50_col]) if row[ic50_col].strip() else None,
                    'rank': int(float(row[r_rank_col])) if row[r_rank_col].strip() else None,
                })
            except ValueError:
                pass

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

    # Resolve siRNA labels → compound IDs
    for dp in datapoints:
        dp['compound_id'] = mapping.get(dp.pop('siRNA_label'), '')

    return ParsedSummary(
        assay_name=assay_name,
        mapping=mapping,
        datapoints=datapoints,
        summaries=summaries,
        mock_values=mock_values,
    )
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python manage.py test app01.tests.ParseSummaryCsvTest -v2 2>&1 | tail -8
```

预期：`Ran 8 tests in ...s OK`

- [ ] **Step 5: Commit**

```bash
git add app01/upload_pipeline.py app01/tests.py
git commit -m "feat: implement parse_summary_csv with mapping, datapoints, IC50 extraction"
```

---

### Task 3: parse_cp_file + enrich_datapoints_with_cp

**Files:**
- Modify: `app01/upload_pipeline.py`
- Modify: `app01/tests.py`

- [ ] **Step 1: 追加测试**

```python
from app01.upload_pipeline import parse_cp_file, enrich_datapoints_with_cp


class ParseCpFileTest(TestCase):
    # Simplified version of the real Prism two-step RT-qPCR format
    CP_CSV = (
        '\n'
        'Two step RT-qPCR study in Hepa1-6 cells (Day 1)\n'
        ',,,Cp value,,,,,,GAPDH,,,FASN\n'
        ',ID,Dose,GAPDH,,,FASN\n'
        '#,,,A,B,C,A,B,C\n'
        '1,siRNA-01,100,16.06,16.18,16.07,23.85,23.85,23.81\n'
        '2,siRNA-01,10,15.95,16.07,15.95,23.16,22.91,22.85\n'
        '9,siRNA-01,100,16.17,16.12,16.43,24.00,24.01,23.95\n'
        '10,siRNA-01,10,16.20,16.21,16.44,23.18,22.95,22.97\n'
    )

    def setUp(self):
        self.result = parse_cp_file(BytesIO(self.CP_CSV.encode()))

    def test_assay_name_extracted(self):
        self.assertIn('Hepa1-6', self.result.assay_name)

    def test_genes_detected(self):
        self.assertEqual(self.result.reference_gene, 'GAPDH')
        self.assertEqual(self.result.target_gene, 'FASN')

    def test_rep_a_cp_values(self):
        key = ('siRNA-01', 100.0)
        self.assertIn(key, self.result.cp_data)
        rep_a = self.result.cp_data[key]['rep_A']
        self.assertEqual(rep_a['GAPDH']['A'], 16.06)
        self.assertEqual(rep_a['FASN']['C'], 23.81)

    def test_rep_b_cp_values(self):
        key = ('siRNA-01', 100.0)
        rep_b = self.result.cp_data[key]['rep_B']
        self.assertEqual(rep_b['GAPDH']['A'], 16.17)
        self.assertEqual(rep_b['FASN']['A'], 24.00)

    def test_second_dose_also_parsed(self):
        self.assertIn(('siRNA-01', 10.0), self.result.cp_data)


class EnrichDatapointsWithCpTest(TestCase):
    def test_enriches_rep_a_and_b(self):
        datapoints = [
            {'compound_id': 'BPR_3M03FN01', 'x_value': 100.0, 'replicate': 'A',
             'x_type': 'concentration', 'value': 0.26, 'is_control': False,
             'readout_type': 'mRNA_remaining', 'raw_cp': None},
            {'compound_id': 'BPR_3M03FN01', 'x_value': 100.0, 'replicate': 'B',
             'x_type': 'concentration', 'value': 0.25, 'is_control': False,
             'readout_type': 'mRNA_remaining', 'raw_cp': None},
            {'compound_id': 'BPR_3M03FN01', 'x_value': 100.0, 'replicate': 'Mean',
             'x_type': 'concentration', 'value': 0.255, 'is_control': False,
             'readout_type': 'mRNA_remaining', 'raw_cp': None},
        ]
        cp_data = {
            ('siRNA-01', 100.0): {
                'rep_A': {'GAPDH': {'A': 16.06, 'B': 16.18, 'C': 16.07},
                          'FASN': {'A': 23.85, 'B': 23.85, 'C': 23.81}},
                'rep_B': {'GAPDH': {'A': 16.17, 'B': 16.12, 'C': 16.43},
                          'FASN': {'A': 24.00, 'B': 24.01, 'C': 23.95}},
            }
        }
        mapping = {'siRNA-01': 'BPR_3M03FN01'}
        result = enrich_datapoints_with_cp(datapoints, cp_data, mapping)
        rep_a = next(d for d in result if d['replicate'] == 'A')
        rep_b = next(d for d in result if d['replicate'] == 'B')
        rep_m = next(d for d in result if d['replicate'] == 'Mean')
        self.assertIsNotNone(rep_a['raw_cp'])
        self.assertIsNotNone(rep_b['raw_cp'])
        self.assertIsNone(rep_m['raw_cp'])
        self.assertEqual(rep_a['raw_cp']['GAPDH']['A'], 16.06)
        self.assertEqual(rep_b['raw_cp']['GAPDH']['A'], 16.17)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python manage.py test app01.tests.ParseCpFileTest app01.tests.EnrichDatapointsWithCpTest -v2 2>&1 | head -10
```

预期：`NotImplementedError`

- [ ] **Step 3: 实现 `parse_cp_file` 和 `enrich_datapoints_with_cp`，替换 `upload_pipeline.py` 中的占位符**

```python
def parse_cp_file(file) -> ParsedCpFile:
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
            if (c3 and re.match(r'^[A-Z][A-Z0-9]+$', c3) and
                    c6 and re.match(r'^[A-Z][A-Z0-9]+$', c6) and c3 != c6):
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
        rep_key = 'rep_A' if occurrence_count[key] == 1 else 'rep_B'

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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python manage.py test app01.tests.ParseCpFileTest app01.tests.EnrichDatapointsWithCpTest -v2 2>&1 | tail -8
```

预期：`Ran 8 tests in ...s OK`

- [ ] **Step 5: Commit**

```bash
git add app01/upload_pipeline.py app01/tests.py
git commit -m "feat: implement parse_cp_file and enrich_datapoints_with_cp"
```

---

### Task 4: detect_existing_compounds + build_preview

**Files:**
- Modify: `app01/upload_pipeline.py`
- Modify: `app01/tests.py`

- [ ] **Step 1: 追加测试**

```python
from app01.upload_pipeline import detect_existing_compounds, build_preview


class DetectExistingCompoundsTest(TestCase):
    def setUp(self):
        Compound.objects.create(compound_id='BPR_3M03FN01')
        Compound.objects.create(compound_id='BPR_3M03FN02')

    def test_separates_existing_and_new(self):
        result = detect_existing_compounds(['BPR_3M03FN01', 'BPR_3M03FN03'])
        self.assertIn('BPR_3M03FN01', result['existing'])
        self.assertIn('BPR_3M03FN03', result['new'])
        self.assertNotIn('BPR_3M03FN03', result['existing'])

    def test_all_new(self):
        result = detect_existing_compounds(['BPR_3M03FN99'])
        self.assertEqual(result['existing'], [])
        self.assertEqual(result['new'], ['BPR_3M03FN99'])

    def test_empty_input(self):
        result = detect_existing_compounds([])
        self.assertEqual(result['existing'], [])
        self.assertEqual(result['new'], [])


class BuildPreviewTest(TestCase):
    SUMMARY_CSV = (
        '\n'
        ',,,FASN mRNA\n'
        '#,ID,Dose (nM),A,B,Mean,,#,ID,Name,Max KD,IC50 (nM),Rank\n'
        '1,Mock,Mock,1.07,0.94,1.01,,,,,,,\n'
        '2,siRNA-01,100,0.26,0.25,0.25,,1,siRNA-01,BPR_3M03FN01,74.71,5.48,9\n'
    )

    def setUp(self):
        self.summary_parsed = parse_summary_csv(BytesIO(self.SUMMARY_CSV.encode()))

    def test_new_compound_detected(self):
        preview = build_preview(None, self.summary_parsed, [], '2026-05', '')
        cids = [c['compound_id'] for c in preview['new_compounds']]
        self.assertIn('BPR_3M03FN01', cids)

    def test_existing_compound_detected(self):
        Compound.objects.create(compound_id='BPR_3M03FN01')
        preview = build_preview(None, self.summary_parsed, [], '2026-05', '')
        self.assertIn('BPR_3M03FN01', preview['existing_compounds'])

    def test_experiments_built(self):
        preview = build_preview(None, self.summary_parsed, [], '2026-05', 'FASN test')
        self.assertEqual(len(preview['experiments']), 1)
        exp = preview['experiments'][0]
        self.assertEqual(exp['compound_id'], 'BPR_3M03FN01')
        self.assertEqual(exp['exp_type'], 'in_vitro')
        self.assertIn('summary', exp)

    def test_warning_for_existing_compound(self):
        Compound.objects.create(compound_id='BPR_3M03FN01')
        preview = build_preview(None, self.summary_parsed, [], '2026-05', '')
        self.assertTrue(any('BPR_3M03FN01' in w for w in preview['warnings']))

    def test_id_format_conflict_detected(self):
        seq_csv = 'siRNAID,SS,AS\nBPR_3M03FN001,Gm,Am\n'
        seq_parsed = parse_seq_file(BytesIO(seq_csv.encode()))  # 3-digit
        # summary has BPR_3M03FN01 (2-digit)
        preview = build_preview(seq_parsed, self.summary_parsed, [], '2026-05', '')
        self.assertTrue(preview['id_format_conflict'])

    def test_no_files_yields_error(self):
        preview = build_preview(None, None, [], '2026-05', '')
        self.assertTrue(len(preview['errors']) > 0)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python manage.py test app01.tests.DetectExistingCompoundsTest app01.tests.BuildPreviewTest -v2 2>&1 | head -10
```

预期：`NotImplementedError`

- [ ] **Step 3: 实现 `detect_existing_compounds` 和 `build_preview`，替换占位符**

```python
def detect_existing_compounds(compound_ids: list) -> dict:
    """Query DB to split compound_ids into existing and new."""
    from app01.models import Compound
    if not compound_ids:
        return {'existing': [], 'new': []}
    existing = list(
        Compound.objects.filter(compound_id__in=compound_ids)
        .values_list('compound_id', flat=True)
    )
    new = [cid for cid in compound_ids if cid not in existing]
    return {'existing': existing, 'new': new}


def build_preview(seq_parsed, summary_parsed, cp_parsed_list,
                  batch_label: str, assay_name: str, exp_date: str = None) -> dict:
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
        mapping = summary_parsed.mapping
        for cid in mapping.values():
            all_compound_ids.add(cid)
        if not assay_name and summary_parsed.assay_name:
            assay_name = summary_parsed.assay_name

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

    # Build experiments (one per mapped compound)
    experiments = []
    for cid in [v for v in mapping.values() if v]:
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
        'new_compounds': new_compounds,
        'existing_compounds': existing_info['existing'],
        'id_format_conflict': id_format_conflict,
        'chosen_format': None,
        'mapping': mapping,
        'experiments': experiments,
        'warnings': warnings,
        'errors': errors,
    }
```

- [ ] **Step 4: 运行全部 pipeline 测试**

```bash
python manage.py test app01.tests.DetectExistingCompoundsTest app01.tests.BuildPreviewTest -v2 2>&1 | tail -8
```

预期：`Ran 9 tests in ...s OK`

- [ ] **Step 5: Commit**

```bash
git add app01/upload_pipeline.py app01/tests.py
git commit -m "feat: implement detect_existing_compounds and build_preview"
```

---

### Task 5: URL 路由 + upload_view (GET + POST)

**Files:**
- Modify: `bprdb/urls.py`
- Modify: `app01/views.py`
- Modify: `app01/tests.py`

- [ ] **Step 1: 追加视图集成测试**

```python
from django.test import Client
from app01.models import LmsUser


class UploadViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        LmsUser.objects.create_user(
            username='uploader', password='pass123', user_type='data_admin'
        )
        self.client.login(username='uploader', password='pass123')

    def test_get_upload_page_returns_200(self):
        response = self.client.get('/upload/')
        self.assertEqual(response.status_code, 200)

    def test_get_requires_login(self):
        self.client.logout()
        response = self.client.get('/upload/')
        self.assertIn(response.status_code, [302, 200])
        if response.status_code == 302:
            self.assertIn('/login/', response['Location'])

    def test_post_without_files_shows_error(self):
        response = self.client.post('/upload/', {'batch_label': '2026-05'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '请至少上传')

    def test_post_seq_file_stores_session_and_redirects(self):
        csv_content = b'siRNAID,SS,AS\nBPR_3M03FN01,GmGm,AmCf\n'
        response = self.client.post('/upload/', {
            'seq_file': BytesIO(csv_content),
            'batch_label': '2026-05',
        }, follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('upload_preview', self.client.session)

    def test_post_missing_batch_label_shows_error(self):
        csv_content = b'siRNAID,SS,AS\nBPR_3M03FN01,GmGm,AmCf\n'
        response = self.client.post('/upload/', {
            'seq_file': BytesIO(csv_content),
            'batch_label': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '批次名称')
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python manage.py test app01.tests.UploadViewTest -v2 2>&1 | head -15
```

预期：`NoReverseMatch` 或 `404`（URL 尚未注册）

- [ ] **Step 3: 在 `bprdb/urls.py` 追加三条路由**

```python
# bprdb/urls.py — 完整文件
from django.contrib import admin
from django.urls import path
from app01 import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('upload/', views.upload_view, name='upload'),
    path('upload/confirm/', views.upload_confirm_view, name='upload_confirm'),
    path('upload/success/', views.upload_success_view, name='upload_success'),
]
```

- [ ] **Step 4: 在 `app01/views.py` 末尾追加 upload_view**

```python
from app01.upload_pipeline import (
    parse_seq_file, parse_summary_csv, parse_cp_file,
    build_preview,
)


@login_required
def upload_view(request):
    if request.method == 'POST':
        batch_label = request.POST.get('batch_label', '').strip()
        assay_name = request.POST.get('assay_name', '').strip()
        exp_date = request.POST.get('exp_date', '').strip() or None

        errors = []
        seq_parsed = None
        summary_parsed = None
        cp_parsed_list = []

        if not batch_label:
            errors.append('批次名称为必填项')

        if 'seq_file' in request.FILES and request.FILES['seq_file'].name:
            try:
                seq_parsed = parse_seq_file(request.FILES['seq_file'])
            except Exception as e:
                errors.append(f'序列文件解析失败：{e}')

        if 'summary_file' in request.FILES and request.FILES['summary_file'].name:
            try:
                summary_parsed = parse_summary_csv(request.FILES['summary_file'])
                if not assay_name and summary_parsed.assay_name:
                    assay_name = summary_parsed.assay_name
            except Exception as e:
                errors.append(f'体外汇总表解析失败：{e}')

        for cp_file in request.FILES.getlist('cp_files'):
            if not cp_file.name:
                continue
            try:
                parsed = parse_cp_file(cp_file)
                cp_parsed_list.append(parsed)
                if not assay_name and parsed.assay_name:
                    assay_name = parsed.assay_name
            except Exception as e:
                errors.append(f'Cp 文件 {cp_file.name} 解析失败：{e}')

        if not seq_parsed and not summary_parsed and not errors:
            errors.append('请至少上传序列文件或体外汇总表')

        if errors:
            return render(request, 'upload.html', {'errors': errors})

        try:
            preview = build_preview(
                seq_parsed, summary_parsed, cp_parsed_list,
                batch_label, assay_name, exp_date,
            )
        except Exception as e:
            return render(request, 'upload.html', {'errors': [f'解析错误：{e}']})

        request.session['upload_preview'] = preview
        return redirect('/upload/?preview=1')

    # GET
    preview = None
    if request.GET.get('preview') and 'upload_preview' in request.session:
        preview = request.session['upload_preview']
    return render(request, 'upload.html', {'preview': preview})
```

- [ ] **Step 5: 创建占位模板 `templates/upload.html`（仅用于通过测试，Task 7 再完善）**

```html
{% extends 'base.html' %}
{% block page_title %} — 上传实验数据{% endblock %}
{% block topbar_content %}<span class="ds-topbar-title">上传实验数据</span>{% endblock %}
{% block content %}
<div class="ds-form-page"><div class="ds-form-card">
{% if errors %}
  {% for e in errors %}<div style="color:red;">{{ e }}</div>{% endfor %}
{% endif %}
<form method="POST" action="/upload/" enctype="multipart/form-data">
  {% csrf_token %}
  <input type="file" name="seq_file">
  <input type="file" name="summary_file">
  <input type="file" name="cp_files" multiple>
  <input type="text" name="batch_label" placeholder="批次名称">
  <input type="text" name="assay_name" placeholder="Assay 名称">
  <button type="submit">解析预览</button>
</form>
{% if preview %}
  <div id="preview-section">preview: {{ preview.batch_label }}</div>
{% endif %}
</div></div>
{% endblock %}
```

- [ ] **Step 6: 运行视图测试**

```bash
python manage.py test app01.tests.UploadViewTest -v2 2>&1 | tail -10
```

预期：`Ran 5 tests in ...s OK`

- [ ] **Step 7: Commit**

```bash
git add bprdb/urls.py app01/views.py templates/upload.html app01/tests.py
git commit -m "feat: add upload_view with GET/POST parse logic and URL routing"
```

---

### Task 6: upload_confirm_view + upload_success_view

**Files:**
- Modify: `app01/views.py`
- Modify: `app01/tests.py`

- [ ] **Step 1: 追加集成测试**

```python
from app01.upload_pipeline import parse_seq_file, parse_summary_csv, build_preview


class UploadConfirmViewTest(TestCase):
    SUMMARY_CSV = (
        '\n'
        ',,,FASN mRNA\n'
        '#,ID,Dose (nM),A,B,Mean,,#,ID,Name,Max KD,IC50 (nM),Rank\n'
        '1,Mock,Mock,1.07,0.94,1.01,,,,,,,\n'
        '2,siRNA-01,100,0.26,0.25,0.25,,1,siRNA-01,BPR_3M03FN01,74.71,5.48,9\n'
    )

    def setUp(self):
        self.client = Client()
        LmsUser.objects.create_user(
            username='confirmer', password='pass123', user_type='data_admin'
        )
        self.client.login(username='confirmer', password='pass123')
        # Pre-populate session with parsed preview
        summary_parsed = parse_summary_csv(BytesIO(self.SUMMARY_CSV.encode()))
        preview = build_preview(None, summary_parsed, [], '2026-05', 'FASN test')
        session = self.client.session
        session['upload_preview'] = preview
        session.save()

    def test_confirm_creates_compound_and_experiment(self):
        response = self.client.post('/upload/confirm/', follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Compound.objects.filter(compound_id='BPR_3M03FN01').exists())
        self.assertTrue(Experiment.objects.filter(batch_label='2026-05').exists())

    def test_confirm_creates_datapoints(self):
        self.client.post('/upload/confirm/', follow=True)
        exp = Experiment.objects.get(batch_label='2026-05')
        self.assertTrue(exp.datapoints.filter(x_value=100.0, replicate='A').exists())

    def test_confirm_creates_experiment_summary(self):
        self.client.post('/upload/confirm/', follow=True)
        exp = Experiment.objects.get(batch_label='2026-05')
        self.assertAlmostEqual(exp.summary.ic50_nm, 5.48)
        self.assertEqual(exp.summary.rank, 9)

    def test_confirm_clears_session(self):
        self.client.post('/upload/confirm/', follow=True)
        self.assertNotIn('upload_preview', self.client.session)

    def test_confirm_without_session_redirects(self):
        session = self.client.session
        del session['upload_preview']
        session.save()
        response = self.client.post('/upload/confirm/')
        self.assertEqual(response.status_code, 302)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python manage.py test app01.tests.UploadConfirmViewTest -v2 2>&1 | head -10
```

预期：`AttributeError: 'function' object` 或 `404`（视图未实现）

- [ ] **Step 3: 在 `app01/views.py` 末尾追加两个视图**

```python
from django.db import transaction
from datetime import date as date_type
from app01.upload_pipeline import normalize_compound_ids


@login_required
def upload_confirm_view(request):
    if request.method != 'POST':
        return redirect('upload')

    preview = request.session.get('upload_preview')
    if not preview:
        return redirect('upload')

    # Handle optional ID format unification
    chosen_format = request.POST.get('chosen_format')
    if chosen_format and preview.get('id_format_conflict'):
        def _norm(cid):
            return normalize_compound_ids([cid], chosen_format)[0]

        for exp in preview.get('experiments', []):
            exp['compound_id'] = _norm(exp['compound_id'])
            for dp in exp.get('datapoints', []):
                if dp.get('compound_id'):
                    dp['compound_id'] = _norm(dp['compound_id'])
        preview['new_compounds'] = [
            {**c, 'compound_id': _norm(c['compound_id'])}
            for c in preview.get('new_compounds', [])
        ]

    batch_label = preview['batch_label']
    assay_name = preview['assay_name']
    exp_date_str = preview.get('exp_date')
    exp_date_obj = None
    if exp_date_str:
        try:
            exp_date_obj = date_type.fromisoformat(exp_date_str)
        except ValueError:
            pass

    n_compounds = 0
    n_experiments = 0

    try:
        with transaction.atomic():
            # Create new compounds and strands
            for c in preview.get('new_compounds', []):
                compound, created = Compound.objects.get_or_create(
                    compound_id=c['compound_id']
                )
                if created:
                    n_compounds += 1
                    if c.get('ss_seq'):
                        Strand.objects.create(
                            compound=compound,
                            strand_type='SS',
                            sequence_id=f"{c['compound_id']}_SS",
                            modify_seq=c['ss_seq'],
                        )
                    if c.get('as_seq'):
                        Strand.objects.create(
                            compound=compound,
                            strand_type='AS',
                            sequence_id=f"{c['compound_id']}_AS",
                            modify_seq=c['as_seq'],
                        )

            # Create experiments
            for exp_data in preview.get('experiments', []):
                cid = exp_data['compound_id']
                compound, _ = Compound.objects.get_or_create(compound_id=cid)

                exp = Experiment.objects.create(
                    compound=compound,
                    exp_type=exp_data.get('exp_type', 'in_vitro'),
                    assay_name=assay_name,
                    cell_line='',
                    batch_label=batch_label,
                    date=exp_date_obj,
                )
                n_experiments += 1

                dp_objs = [
                    DataPoint(
                        experiment=exp,
                        x_value=dp['x_value'],
                        x_type=dp['x_type'],
                        replicate=dp['replicate'],
                        value=dp['value'],
                        readout_type=dp['readout_type'],
                        is_control=dp.get('is_control', False),
                        raw_cp=dp.get('raw_cp'),
                    )
                    for dp in exp_data.get('datapoints', [])
                ]
                DataPoint.objects.bulk_create(dp_objs)

                if exp_data.get('summary'):
                    s = exp_data['summary']
                    ExperimentSummary.objects.create(
                        experiment=exp,
                        max_kd_pct=s.get('max_kd_pct'),
                        ic50_nm=s.get('ic50_nm'),
                        rank=s.get('rank'),
                    )
    except Exception as e:
        logger.error(f'upload_confirm error: {e}')
        return render(request, 'upload.html', {
            'errors': [f'写库失败：{e}'],
            'preview': preview,
        })

    request.session['upload_stats'] = {
        'n_compounds': n_compounds,
        'n_experiments': n_experiments,
        'batch_label': batch_label,
    }
    del request.session['upload_preview']
    return redirect('upload_success')


@login_required
def upload_success_view(request):
    stats = request.session.pop('upload_stats', {})
    return render(request, 'upload_success.html', {'stats': stats})
```

- [ ] **Step 4: 创建占位 `templates/upload_success.html`（仅用于通过测试）**

```html
{% extends 'base.html' %}
{% block page_title %} — 上传成功{% endblock %}
{% block topbar_content %}<span class="ds-topbar-title">上传成功</span>{% endblock %}
{% block content %}
<div class="ds-form-page"><div class="ds-form-card">
  <p>上传成功：{{ stats.n_experiments }} 个实验批次，{{ stats.n_compounds }} 个新化合物。</p>
  <a href="/upload/">继续上传</a>
</div></div>
{% endblock %}
```

- [ ] **Step 5: 运行确认测试**

```bash
python manage.py test app01.tests.UploadConfirmViewTest -v2 2>&1 | tail -10
```

预期：`Ran 5 tests in ...s OK`

- [ ] **Step 6: Commit**

```bash
git add app01/views.py templates/upload_success.html
git commit -m "feat: implement upload_confirm_view and upload_success_view"
```

---

### Task 7: templates/upload.html 完整实现

**Files:**
- Modify: `templates/upload.html` (完整替换)

- [ ] **Step 1: 用完整模板替换 Task 5 创建的占位文件**

内容为下面完整的 `templates/upload.html`：

```html
{% extends 'base.html' %}

{% block page_title %} — 上传实验数据{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">上传实验数据</span>
  <span class="ds-topbar-spacer"></span>
  <a href="{% url 'index' %}" class="ds-btn ds-btn-ghost">← 首页</a>
{% endblock %}

{% block content %}
<div class="ds-form-page">
<div class="ds-form-card">

  {% if errors %}
  <div style="background:#fee2e2;border-radius:6px;padding:10px 14px;margin-bottom:16px;font-size:13px;color:#b91c1c;">
    {% for e in errors %}<div>✗ {{ e }}</div>{% endfor %}
  </div>
  {% endif %}

  <div class="ds-form-card-title">上传实验数据</div>
  <div style="font-size:12px;color:#64748b;margin-bottom:18px;line-height:1.7;">
    上传序列文件和体外汇总表，系统自动解析 siRNA→化合物编号映射，确认后写入数据库。
  </div>

  <form method="POST" action="{% url 'upload' %}" enctype="multipart/form-data">
    {% csrf_token %}

    <div style="display:grid;gap:14px;margin-bottom:18px;">

      <div>
        <label class="ds-form-label">序列文件（可选）</label>
        <div style="font-size:11px;color:#94a3b8;margin-bottom:4px;">ID_sequence.csv 格式：siRNAID, SS, AS 三列</div>
        <input type="file" name="seq_file" accept=".csv" class="ds-form-control">
      </div>

      <div>
        <label class="ds-form-label">体外汇总表（含 mapping + IC50）</label>
        <div style="font-size:11px;color:#94a3b8;margin-bottom:4px;">Prism 汇总格式：左表剂量响应 + 右表 siRNA→BPR 映射、IC50、Rank</div>
        <input type="file" name="summary_file" accept=".csv" class="ds-form-control">
      </div>

      <div>
        <label class="ds-form-label">原始 Cp 文件（可选，可多选）</label>
        <div style="font-size:11px;color:#94a3b8;margin-bottom:4px;">Prism 两步法 RT-qPCR 格式，用于存储原始 Cp 值</div>
        <input type="file" name="cp_files" accept=".csv" multiple class="ds-form-control">
      </div>

      <div style="opacity:0.5;pointer-events:none;">
        <label class="ds-form-label">体内数据（即将支持）</label>
        <input type="file" name="invivo_file" accept=".csv" class="ds-form-control" disabled>
      </div>

    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:18px;">
      <div>
        <label class="ds-form-label">批次名称 *</label>
        <input type="text" name="batch_label" class="ds-form-control"
               placeholder="如 2026-05" required
               value="{{ preview.batch_label|default:'' }}">
      </div>
      <div>
        <label class="ds-form-label">Assay 名称</label>
        <input type="text" name="assay_name" class="ds-form-control"
               placeholder="自动从 CSV 提取"
               value="{{ preview.assay_name|default:'' }}">
      </div>
      <div>
        <label class="ds-form-label">实验日期</label>
        <input type="date" name="exp_date" class="ds-form-control"
               value="{{ preview.exp_date|default:'' }}">
      </div>
    </div>

    <button type="submit" class="ds-btn ds-btn-primary">解析预览</button>
  </form>

  {% if preview %}
  <hr style="margin:24px 0;border-color:#e2e8f0;">

  <div class="ds-form-card-title">解析结果预览</div>

  {% if preview.errors %}
  <div style="background:#fee2e2;border-radius:6px;padding:10px 14px;margin-bottom:12px;font-size:13px;color:#b91c1c;">
    {% for e in preview.errors %}<div>✗ {{ e }}</div>{% endfor %}
  </div>
  {% endif %}

  {% if preview.warnings %}
  <div style="background:#fef9c3;border-radius:6px;padding:10px 14px;margin-bottom:12px;font-size:13px;color:#854d0e;">
    {% for w in preview.warnings %}<div>⚠ {{ w }}</div>{% endfor %}
  </div>
  {% endif %}

  <div style="font-size:13px;line-height:2;margin-bottom:12px;">
    <div style="color:#15803d;">✓ 检测到 {{ preview.experiments|length }} 个化合物
      （{{ preview.new_compounds|length }} 个新增，{{ preview.existing_compounds|length }} 个已存在）</div>
    <div style="color:#475569;">批次名称：{{ preview.batch_label }}</div>
    {% if preview.assay_name %}<div style="color:#475569;">Assay 名称：{{ preview.assay_name }}</div>{% endif %}
  </div>

  {% if preview.mapping %}
  <div style="margin-bottom:16px;">
    <div style="font-size:12px;font-weight:600;color:#374151;margin-bottom:6px;">siRNA → 化合物编号映射确认</div>
    <div style="display:flex;flex-wrap:wrap;gap:6px;">
      {% for sirna, bpr in preview.mapping.items %}
      <span style="font-size:11px;background:#f1f5f9;border-radius:4px;padding:3px 8px;color:#475569;">
        {{ sirna }} → <strong>{{ bpr }}</strong>
      </span>
      {% endfor %}
    </div>
  </div>
  {% endif %}

  {% if preview.id_format_conflict %}
  <div style="background:#fef9c3;border-radius:6px;padding:12px 14px;margin-bottom:16px;font-size:13px;">
    <div style="font-weight:600;color:#854d0e;margin-bottom:8px;">⚠ 检测到 ID 格式冲突，请选择统一格式：</div>
    <label style="margin-right:16px;">
      <input type="radio" name="_format_choice" value="2-digit" checked> 2 位序号（BPR_3M03FN01）
    </label>
    <label>
      <input type="radio" name="_format_choice" value="3-digit"> 3 位序号（BPR_3M03FN001）
    </label>
  </div>
  {% endif %}

  {% if not preview.errors %}
  <form method="POST" action="{% url 'upload_confirm' %}">
    {% csrf_token %}
    {% if preview.id_format_conflict %}
    <input type="hidden" name="chosen_format" id="chosen_format_input" value="2-digit">
    <script>
      document.querySelectorAll('input[name="_format_choice"]').forEach(function(r) {
        r.addEventListener('change', function() {
          document.getElementById('chosen_format_input').value = this.value;
        });
      });
    </script>
    {% endif %}
    <button type="submit" class="ds-btn ds-btn-primary">
      确认上传（{{ preview.experiments|length }} 个实验批次，{{ preview.new_compounds|length }} 个新化合物）
    </button>
  </form>
  {% endif %}

  {% endif %}

</div>
</div>
{% endblock %}
```

- [ ] **Step 2: 启动服务器，手工验证页面渲染正常**

```bash
python manage.py runserver 8001
```

在浏览器打开 `http://127.0.0.1:8001/upload/`，检查：
- 页面加载正常，无 Django 错误
- 4 个文件槽正常显示
- 体内数据槽显示灰色不可用状态
- 批次名称 / Assay 名称 / 实验日期输入框显示正常

- [ ] **Step 3: 用 `/Users/gutou/Desktop/Data_tmp_Prism/1_summary.csv` 进行端到端测试**

上传 `1_summary.csv` 到体外汇总表槽，批次名称填 `test-2026-05`，点击「解析预览」，验证：
- 页面显示 10 个化合物
- mapping 表格显示 siRNA-01 → BPR_3M03FN01 等
- ExperimentSummary 数据显示（IC50、MaxKD、Rank）
- 无报错

- [ ] **Step 4: Commit**

```bash
git add templates/upload.html
git commit -m "feat: complete upload.html with form slots and preview section"
```

---

### Task 8: templates/upload_success.html 完整实现 + base.html 侧边栏

**Files:**
- Modify: `templates/upload_success.html` (完整替换)
- Modify: `templates/base.html`

- [ ] **Step 1: 用完整版本替换占位 `templates/upload_success.html`**

```html
{% extends 'base.html' %}

{% block page_title %} — 上传成功{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">上传成功</span>
  <span class="ds-topbar-spacer"></span>
{% endblock %}

{% block content %}
<div class="ds-form-page">
<div class="ds-form-card" style="text-align:center;padding:40px 32px;">

  <div style="font-size:48px;margin-bottom:16px;">✅</div>
  <div style="font-size:18px;font-weight:600;color:#15803d;margin-bottom:8px;">数据已成功写入数据库</div>

  {% if stats %}
  <div style="font-size:13px;color:#475569;margin-bottom:24px;line-height:1.8;">
    {% if stats.n_compounds %}<div>新建化合物：{{ stats.n_compounds }} 个</div>{% endif %}
    <div>写入实验批次：{{ stats.n_experiments }} 个</div>
    <div>批次名称：{{ stats.batch_label }}</div>
  </div>
  {% endif %}

  <div style="display:flex;gap:12px;justify-content:center;">
    <a href="{% url 'upload' %}" class="ds-btn ds-btn-primary">继续上传</a>
    <a href="{% url 'index' %}" class="ds-btn ds-btn-ghost">返回首页</a>
  </div>

</div>
</div>
{% endblock %}
```

- [ ] **Step 2: 在 `templates/base.html` 侧边栏中添加上传链接**

找到侧边栏中合适位置（`ds-nav-section` 标题附近），在现有导航项后追加：

```html
    <div class="ds-nav-divider"></div>
    <div class="ds-nav-section">数据录入</div>
    <a href="{% url 'upload' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'upload' or request.resolver_match.url_name == 'upload_confirm' or request.resolver_match.url_name == 'upload_success' %}active{% endif %}">
      <i class="bi bi-cloud-upload ds-nav-icon"></i> 上传实验数据
    </a>
```

具体插入位置：在 base.html 中找到最后一个 `ds-nav-divider` 之后，或在 `</nav>` 关闭前。

- [ ] **Step 3: 运行全部测试确认无回归**

```bash
python manage.py test app01 -v2 2>&1 | tail -15
```

预期：所有测试通过，无 FAIL。

- [ ] **Step 4: 端到端验证完整流程**

用实际文件验证完整上传流程：
1. 上传 `/Users/gutou/Desktop/Data_tmp_Prism/ID_sequence.csv`（序列文件）
2. 上传 `/Users/gutou/Desktop/Data_tmp_Prism/1_summary.csv`（体外汇总表）
3. 上传 `/Users/gutou/Desktop/Data_tmp_Prism/2_Two step RT-qPCR study in Hepa1-6 cells (Day 1).csv`（Cp 文件）
4. 批次名称：`2026-05-test`
5. 点击「解析预览」→ 确认 mapping 和数据正确
6. 点击「确认上传」→ 进入成功页
7. 在 Django shell 验证数据写入：

```bash
python manage.py shell -c "
from app01.models import Compound, Experiment, DataPoint, ExperimentSummary
print('Compounds:', Compound.objects.count())
print('Experiments:', Experiment.objects.count())
print('DataPoints:', DataPoint.objects.count())
print('Summaries:', ExperimentSummary.objects.count())
exp = Experiment.objects.filter(batch_label='2026-05-test').first()
if exp:
    print('IC50:', exp.summary.ic50_nm)
    print('DataPoints with raw_cp:', exp.datapoints.exclude(raw_cp=None).count())
"
```

- [ ] **Step 5: Commit**

```bash
git add templates/upload_success.html templates/base.html
git commit -m "feat: complete upload_success page and add sidebar nav link"
```

---

## 全量回归测试

```bash
python manage.py test app01 -v2 2>&1 | tail -20
```

预期：所有测试通过，无警告。
