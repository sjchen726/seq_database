# Upload Pipeline Robustness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the upload pipeline into a 5-phase validation system that surfaces ID conflicts, sequence mismatches, and duplicate data to the user before saving, and fixes data corruption bugs.

**Architecture:** Five phases (parse → normalize → diff_strands → dedup → save). Phases 1–4 run in a new `smart_upload_preview_view`; Phase 5 runs in the existing reduced `smart_upload_confirm_view`. Pipeline result (errors, warnings, remap_log, strand_diffs, dedup_report) stored in `request.session['pipeline_result']`.

**Tech Stack:** Django 5.1, Python 3.10, MySQL, existing `upload_pipeline.py` helper functions

---

## File Map

| File | Changes |
|------|---------|
| `app01/models.py` | Add `Experiment.version` field |
| `app01/migrations/0013_experiment_version.py` | New migration |
| `app01/upload_pipeline.py` | Add `StrandDiff`, `warnings` fields to `ParsedCpFile`/`ParsedTransfectionFile`, `normalize_phase()`, `diff_strands()`, `dedup_phase()` |
| `app01/views.py` | Fix `_generate_batch_label()`, add `smart_upload_preview_view`, refactor `smart_upload_confirm_view` |
| `templates/smart_upload.html` | Add 4-panel conflict display + wire confirm button to new URL |
| `bprdb/urls.py` | Add `smart_upload_preview` URL |
| `app01/tests.py` | Tests for new pipeline functions |

---

## Task 1: Add `Experiment.version` field and migration

**Files:**
- Modify: `app01/models.py:179`
- Create: `app01/migrations/0013_experiment_version.py`
- Test: `app01/tests.py`

- [ ] **Step 1: Write the failing test**

Add this class to `app01/tests.py` after the existing `ExperimentSummaryTests` class:

```python
class ExperimentVersionTests(TestCase):
    def setUp(self):
        self.compound = Compound.objects.create(compound_id='BPR3M03-FN01')

    def test_default_version_is_1(self):
        exp = Experiment.objects.create(
            compound=self.compound, exp_type='in_vitro',
            assay_name='test', batch_label='20260627-001',
        )
        self.assertEqual(exp.version, 1)

    def test_version_field_can_be_set(self):
        exp = Experiment.objects.create(
            compound=self.compound, exp_type='in_vitro',
            assay_name='test', batch_label='20260627-001', version=2,
        )
        self.assertEqual(exp.version, 2)
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
source venv/bin/activate && python manage.py test app01.tests.ExperimentVersionTests -v 2
```

Expected: `TypeError: Experiment() got an unexpected keyword argument 'version'`

- [ ] **Step 3: Add field to model**

In `app01/models.py`, add after the `date` field (line 179):

```python
    date = models.DateField(null=True, blank=True)
    version = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
```

- [ ] **Step 4: Generate and apply migration**

```bash
python manage.py makemigrations app01 --name experiment_version
python manage.py migrate
```

Expected: migration file created at `app01/migrations/0013_experiment_version.py`, migration applied.

- [ ] **Step 5: Run test to confirm it passes**

```bash
python manage.py test app01.tests.ExperimentVersionTests -v 2
```

Expected: 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app01/models.py app01/migrations/0013_experiment_version.py app01/tests.py
git commit -m "feat: add Experiment.version field (default=1)"
```

---

## Task 2: Add `warnings` field to `ParsedCpFile` and `ParsedTransfectionFile`

**Files:**
- Modify: `app01/upload_pipeline.py:41-52`

- [ ] **Step 1: Add `warnings` field to both dataclasses**

In `app01/upload_pipeline.py`, replace the `ParsedCpFile` and `ParsedTransfectionFile` dataclasses:

```python
# Replace lines 40-52 (ParsedCpFile and ParsedTransfectionFile)

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
```

- [ ] **Step 2: Update `parse_cp_file` to populate `warnings` when defaults are used**

In `app01/upload_pipeline.py`, in `parse_cp_file()`, the gene detection block sets `reference_gene = 'GAPDH'` and `target_gene = 'FASN'` as defaults before the loop. Add a flag to track whether a match was found:

Replace lines 327–337:
```python
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
```

Then at the return statement of `parse_cp_file` (currently `return ParsedCpFile(...)`), add:

```python
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
```

- [ ] **Step 3: Update `parse_transfection_file` to populate `warnings` on siRNA mapping conflicts**

In `app01/upload_pipeline.py`, in `parse_transfection_file()`, replace lines 660–666:

```python
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
```

And update the return statement:
```python
    return ParsedTransfectionFile(cell_line=cell_line, notes=notes, mapping=mapping, warnings=transfection_warnings)
```

- [ ] **Step 4: Write and run tests**

Add to `app01/tests.py`:

```python
class ParseCpFileWarningTests(TestCase):
    def _make_cp_file(self, header_row):
        """Build a minimal CP CSV with given header row for gene detection."""
        from io import BytesIO
        lines = [
            b'assay\n',
            b'siRNA Knockdown\n',
            header_row,
            b'siRNA-01,10,1.1,1.2,1.3,,,,,\n',
        ]
        return _BytesFile(b''.join(lines))

    def test_no_gene_detection_produces_warning(self):
        f = _BytesFile(b'assay\nsiRNA Knockdown\nA,B,C,D,E,F,G,H,I,J\n')
        result = parse_cp_file(f)
        self.assertIn('GAPDH', result.reference_gene)
        self.assertEqual(len(result.warnings), 1)
        self.assertIn('默认值', result.warnings[0])

    def test_gene_detected_no_warning(self):
        # Row where col[3]=GAPDH, col[6]=FASN → detected
        f = _BytesFile(b'assay\nsiRNA Knockdown\n,,,,GAPDH,,,FASN,,\n' + b'\n' * 5)
        # A valid detection row: need at least 7 cols with col[3] and col[6]
        import csv, io as sio
        row_bytes = ',,,GAPDH,x,x,FASN\n'.encode()
        data = b'assay\n\n' + row_bytes
        result = parse_cp_file(_BytesFile(data))
        self.assertEqual(result.warnings, [])


class ParseTransfectionFileWarningTests(TestCase):
    def _make_tf_file(self, rows_17_18):
        """rows_17_18: list of (sirna, cid) tuples for cols 16,17."""
        lines = ['Transfection in HepG2\n']
        for sirna, cid in rows_17_18:
            # pad to 18 columns
            cols = [''] * 18
            cols[16] = sirna
            cols[17] = cid
            lines.append(','.join(cols) + '\n')
        return _BytesFile(''.join(lines).encode())

    def test_duplicate_sirna_mapping_produces_warning(self):
        f = self._make_tf_file([
            ('siRNA-01', 'BPR_3M03FN01'),
            ('siRNA-01', 'BPR_3M03FN02'),  # conflict
        ])
        result = parse_transfection_file(f)
        self.assertEqual(result.mapping['siRNA-01'], 'BPR_3M03FN01')  # first kept
        self.assertEqual(len(result.warnings), 1)
        self.assertIn('siRNA-01', result.warnings[0])

    def test_no_conflict_no_warning(self):
        f = self._make_tf_file([('siRNA-01', 'BPR_3M03FN01')])
        result = parse_transfection_file(f)
        self.assertEqual(result.warnings, [])
```

Also add to the imports at the top of the test file:
```python
from app01.upload_pipeline import (
    # existing imports...
    parse_cp_file, parse_transfection_file, _BytesFile,
)
```

Run:
```bash
python manage.py test app01.tests.ParseCpFileWarningTests app01.tests.ParseTransfectionFileWarningTests -v 2
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add app01/upload_pipeline.py app01/tests.py
git commit -m "feat: surface CP gene-detection and transfection mapping warnings from parse functions"
```

---

## Task 3: Add `StrandDiff` dataclass and `diff_strands()` to `upload_pipeline.py`

**Files:**
- Modify: `app01/upload_pipeline.py` (after line 82, in the Data structures section)
- Test: `app01/tests.py`

- [ ] **Step 1: Write the failing test**

Add to `app01/tests.py`:

```python
from app01.upload_pipeline import diff_strands, StrandDiff

class DiffStrandsTests(TestCase):
    def setUp(self):
        self.compound = Compound.objects.create(compound_id='BPR3M03-FN01')

    def test_no_existing_strand_returns_empty(self):
        result = diff_strands([{'compound_id': 'BPR3M03-FN01', 'strand_type': 'AS', 'new_seq': 'GAUG'}])
        self.assertEqual(result, [])

    def test_same_sequence_returns_empty(self):
        Strand.objects.create(compound=self.compound, strand_type='AS', modify_seq='GAUG')
        result = diff_strands([{'compound_id': 'BPR3M03-FN01', 'strand_type': 'AS', 'new_seq': 'GAUG'}])
        self.assertEqual(result, [])

    def test_different_sequence_returns_diff(self):
        Strand.objects.create(compound=self.compound, strand_type='AS', modify_seq='GAUG')
        result = diff_strands([{'compound_id': 'BPR3M03-FN01', 'strand_type': 'AS', 'new_seq': 'GCUG'}])
        self.assertEqual(len(result), 1)
        diff = result[0]
        self.assertEqual(diff.compound_id, 'BPR3M03-FN01')
        self.assertEqual(diff.old_seq, 'GAUG')
        self.assertEqual(diff.new_seq, 'GCUG')
        self.assertEqual(diff.diff_positions, [1])  # position 1: A→C
        self.assertIsNone(diff.user_choice)

    def test_length_mismatch_marks_all_positions(self):
        Strand.objects.create(compound=self.compound, strand_type='AS', modify_seq='GAUG')
        result = diff_strands([{'compound_id': 'BPR3M03-FN01', 'strand_type': 'AS', 'new_seq': 'GAUGG'}])
        self.assertEqual(len(result), 1)
        self.assertGreater(len(result[0].diff_positions), 0)
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
python manage.py test app01.tests.DiffStrandsTests -v 2
```

Expected: `ImportError: cannot import name 'StrandDiff' from 'app01.upload_pipeline'`

- [ ] **Step 3: Implement `StrandDiff` and `diff_strands()`**

In `app01/upload_pipeline.py`, add after the `ParsedInVivoFile` dataclass (after line ~82):

```python
@dataclass
class StrandDiff:
    compound_id: str
    strand_type: str
    old_seq: str
    new_seq: str
    diff_positions: list  # 0-indexed positions where bases differ
    user_choice: str = None  # 'keep' | 'overwrite' — set by preview page
```

Add the `diff_strands()` function after `detect_cross_format_match()` (after line ~434):

```python
def diff_strands(upload_strands: list) -> list:
    """Compare upload sequences against existing Strand records.

    upload_strands: [{'compound_id': str, 'strand_type': str, 'new_seq': str}]
    Returns list of StrandDiff for every case where the existing record differs.
    """
    from app01.models import Strand
    diffs = []
    for item in upload_strands:
        existing = Strand.objects.filter(
            compound_id=item['compound_id'],
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
```

- [ ] **Step 4: Run tests**

```bash
python manage.py test app01.tests.DiffStrandsTests -v 2
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app01/upload_pipeline.py app01/tests.py
git commit -m "feat: add StrandDiff dataclass and diff_strands() to upload_pipeline"
```

---

## Task 4: Add `normalize_phase()` to `upload_pipeline.py`

**Files:**
- Modify: `app01/upload_pipeline.py`
- Test: `app01/tests.py`

- [ ] **Step 1: Write the failing test**

Add to `app01/tests.py`:

```python
from app01.upload_pipeline import normalize_phase, NormalizeResult

class NormalizePhaseTests(TestCase):
    def test_already_canonical_no_remap(self):
        result = normalize_phase(['BPR3M03-FN01'], '3M03')
        self.assertEqual(result.errors, [])
        self.assertEqual(result.remap_log, [])

    def test_underscore_format_gets_remapped(self):
        result = normalize_phase(['BPR_3M03FN01'], '3M03')
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.remap_log), 1)
        self.assertEqual(result.remap_log[0]['reason'], 'canonicalize')
        self.assertEqual(result.remap_log[0]['canonical'], 'BPR3M03-FN01')

    def test_numeric_id_gets_prefix_warning(self):
        result = normalize_phase(['123456789'], '3M03')
        self.assertEqual(len(result.warnings), 1)
        self.assertIn('BPR_', result.warnings[0])

    def test_unrecognizable_id_produces_error(self):
        result = normalize_phase(['TOTALLY_INVALID_!!!'], '3M03')
        self.assertEqual(len(result.errors), 1)
        self.assertIn('TOTALLY_INVALID_!!!', result.errors[0])

    def test_empty_list(self):
        result = normalize_phase([], '3M03')
        self.assertEqual(result.errors, [])
        self.assertEqual(result.remap_log, [])
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
python manage.py test app01.tests.NormalizePhaseTests -v 2
```

Expected: `ImportError: cannot import name 'normalize_phase'`

- [ ] **Step 3: Implement `NormalizeResult` dataclass and `normalize_phase()`**

In `app01/upload_pipeline.py`, add `NormalizeResult` in the Data structures section (alongside `StrandDiff`):

```python
@dataclass
class NormalizeResult:
    remap_log: list   # [{'original': str, 'canonical': str, 'reason': str}]
    errors: list      # [str] — IDs that could not be recognized
    warnings: list    # [str] — informational (e.g. numeric prefix auto-added)
    id_map: dict      # {original_id: final_resolved_id}
```

Add `normalize_phase()` after `diff_strands()`:

```python
# Patterns for IDs that are valid to store in DB
_KNOWN_ID_PATTERNS = [
    re.compile(r'^BPR[A-Z0-9]+-[A-Z]{2}\d{2,3}$'),   # canonical BPR3M03-FN01
    re.compile(r'^BPR_[A-Z0-9]+[A-Z]{2}\d{2,3}$'),    # legacy BPR_3M03FN01
    re.compile(r'^[A-Za-z][A-Za-z ]+$'),               # control group names (Saline, PBS...)
]


def normalize_phase(compound_ids: list, project_code: str) -> NormalizeResult:
    """Phase 2: canonicalize all IDs and apply cross-format DB remapping.

    Returns NormalizeResult with remap_log, errors, warnings, and id_map.
    id_map maps each original ID to its final resolved ID for use in Phase 5.
    """
    remap_log = []
    errors = []
    warnings = []
    id_map = {}

    for cid in compound_ids:
        current = cid

        # Numeric IDs get BPR_ prefix automatically — warn the user
        if re.match(r'^\d', cid):
            warnings.append(f'已自动为数字ID补充前缀 BPR_，请确认这是正确的序列号: {cid}')

        # Step 1: canonicalize
        canonical = canonicalize_compound_id(cid, project_code)
        if canonical != cid:
            remap_log.append({'original': cid, 'canonical': canonical, 'reason': 'canonicalize'})
            current = canonical

        # Step 2: cross-format DB match (2-digit ↔ 3-digit)
        cross = detect_cross_format_match([current])
        if cross and current in cross:
            db_id = cross[current]
            remap_log.append({'original': current, 'canonical': db_id, 'reason': 'format_mismatch'})
            current = db_id

        # Step 3: validate final form
        if not any(p.match(current) for p in _KNOWN_ID_PATTERNS):
            errors.append(f'无法识别的ID格式: {cid}')

        id_map[cid] = current

    return NormalizeResult(remap_log=remap_log, errors=errors, warnings=warnings, id_map=id_map)
```

- [ ] **Step 4: Run tests**

```bash
python manage.py test app01.tests.NormalizePhaseTests -v 2
```

Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app01/upload_pipeline.py app01/tests.py
git commit -m "feat: add NormalizeResult and normalize_phase() to upload_pipeline"
```

---

## Task 5: Add `dedup_phase()` to `upload_pipeline.py`

**Files:**
- Modify: `app01/upload_pipeline.py`
- Test: `app01/tests.py`

- [ ] **Step 1: Write the failing test**

Add to `app01/tests.py`:

```python
from app01.upload_pipeline import dedup_phase

class DedupPhaseTests(TestCase):
    def setUp(self):
        self.compound = Compound.objects.create(compound_id='BPR3M03-FN01')
        self.exp = Experiment.objects.create(
            compound=self.compound, exp_type='in_vitro',
            assay_name='siRNA knockdown', batch_label='20260601-001',
        )
        DataPoint.objects.create(
            experiment=self.exp, x_value=10.0, x_type='concentration',
            replicate='A', value=23.4, readout_type='mRNA_remaining', is_control=False,
        )

    def test_no_existing_experiment_returns_empty_report(self):
        upload_records = [{
            'compound_id': 'BPR3M03-FN02',  # different compound
            'batch_label': '20260627-001',
            'assay_name': 'siRNA knockdown',
            'datapoints': [{'x_value': 10.0, 'replicate': 'A', 'value': 23.4,
                            'readout_type': 'mRNA_remaining', 'is_control': False}],
        }]
        report = dedup_phase(upload_records)
        self.assertEqual(report['exp_conflicts'], [])
        self.assertEqual(report['dp_conflicts'], [])

    def test_same_exp_detected_as_conflict(self):
        upload_records = [{
            'compound_id': 'BPR3M03-FN01',
            'batch_label': '20260601-001',  # same batch
            'assay_name': 'siRNA knockdown',  # same assay
            'datapoints': [{'x_value': 10.0, 'replicate': 'A', 'value': 99.0,
                            'readout_type': 'mRNA_remaining', 'is_control': False}],
        }]
        report = dedup_phase(upload_records)
        self.assertEqual(len(report['exp_conflicts']), 1)
        self.assertEqual(report['exp_conflicts'][0]['compound_id'], 'BPR3M03-FN01')
        self.assertEqual(report['exp_conflicts'][0]['action'], 'new_version')

    def test_identical_datapoints_detected(self):
        upload_records = [{
            'compound_id': 'BPR3M03-FN01',
            'batch_label': '20260601-001',
            'assay_name': 'siRNA knockdown',
            'datapoints': [
                # identical to existing DataPoint
                {'x_value': 10.0, 'replicate': 'A', 'value': 23.4,
                 'readout_type': 'mRNA_remaining', 'is_control': False},
            ],
        }]
        report = dedup_phase(upload_records)
        self.assertEqual(len(report['dp_conflicts']), 1)
        self.assertEqual(report['dp_conflicts'][0]['compound_id'], 'BPR3M03-FN01')
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
python manage.py test app01.tests.DedupPhaseTests -v 2
```

Expected: `ImportError: cannot import name 'dedup_phase'`

- [ ] **Step 3: Implement `dedup_phase()`**

Add after `normalize_phase()` in `app01/upload_pipeline.py`:

```python
def dedup_phase(upload_records: list) -> dict:
    """Phase 4: two-level duplicate detection.

    upload_records: list of dicts with keys:
        compound_id, batch_label, assay_name,
        datapoints: [{'x_value', 'replicate', 'value', 'readout_type', 'is_control'}]

    Returns:
        {
          'exp_conflicts': [{'compound_id', 'batch_label', 'assay_name',
                             'existing_exp_id', 'existing_version', 'action'}],
          'dp_conflicts':  [{'compound_id', 'batch_label', 'assay_name',
                             'datapoints': [...]}],
        }
    """
    from app01.models import Experiment, DataPoint
    exp_conflicts = []
    dp_conflicts = []

    for rec in upload_records:
        cid = rec['compound_id']
        batch = rec['batch_label']
        assay = rec['assay_name']

        # Level 1: experiment-level
        existing_exps = list(
            Experiment.objects.filter(
                compound__compound_id=cid,
                batch_label=batch,
                assay_name=assay,
            ).order_by('-version')
        )
        if existing_exps:
            latest = existing_exps[0]
            exp_conflicts.append({
                'compound_id': cid,
                'batch_label': batch,
                'assay_name': assay,
                'existing_exp_id': latest.pk,
                'existing_version': latest.version,
                'action': 'new_version',
            })

            # Level 2: datapoint-level (against the latest version)
            existing_fps = set(
                (round(float(dp.x_value or 0), 4),
                 dp.replicate,
                 round(float(dp.value or 0), 4) if dp.value is not None else None,
                 dp.readout_type,
                 dp.is_control)
                for dp in DataPoint.objects.filter(experiment=latest)
            )
            dup_dps = []
            for dp in rec.get('datapoints', []):
                fp = (
                    round(float(dp.get('x_value') or 0), 4),
                    dp.get('replicate', ''),
                    round(float(dp.get('value') or 0), 4) if dp.get('value') is not None else None,
                    dp.get('readout_type', ''),
                    bool(dp.get('is_control', False)),
                )
                if fp in existing_fps:
                    dup_dps.append(dp)
            if dup_dps:
                dp_conflicts.append({
                    'compound_id': cid,
                    'batch_label': batch,
                    'assay_name': assay,
                    'datapoints': dup_dps,
                    'skip': True,  # default: skip duplicates
                })

    return {'exp_conflicts': exp_conflicts, 'dp_conflicts': dp_conflicts}
```

- [ ] **Step 4: Run tests**

```bash
python manage.py test app01.tests.DedupPhaseTests -v 2
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app01/upload_pipeline.py app01/tests.py
git commit -m "feat: add dedup_phase() with two-level duplicate detection to upload_pipeline"
```

---

## Task 6: Fix `_generate_batch_label()` to use `select_for_update`

**Files:**
- Modify: `app01/views.py:1609-1624`
- Test: `app01/tests.py`

- [ ] **Step 1: Write the failing test**

Add to `app01/tests.py`:

```python
class GenerateBatchLabelTests(TestCase):
    def test_returns_todays_label_format(self):
        from datetime import date
        from app01.views import _generate_batch_label
        label = _generate_batch_label()
        today = date.today().strftime('%Y%m%d')
        self.assertTrue(label.startswith(today + '-'))
        suffix = label[len(today) + 1:]
        self.assertTrue(suffix.isdigit())
        self.assertEqual(len(suffix), 3)

    def test_increments_when_label_exists(self):
        from datetime import date
        from app01.views import _generate_batch_label
        compound = Compound.objects.create(compound_id='BPR3M03-FN01')
        today = date.today().strftime('%Y%m%d')
        Experiment.objects.create(
            compound=compound, exp_type='in_vitro',
            assay_name='test', batch_label=f'{today}-001',
        )
        label = _generate_batch_label()
        self.assertEqual(label, f'{today}-002')
```

- [ ] **Step 2: Run test to confirm it currently passes (regression guard)**

```bash
python manage.py test app01.tests.GenerateBatchLabelTests -v 2
```

Expected: both tests PASS (existing logic is correct, just not atomic — tests still pass)

- [ ] **Step 3: Replace `_generate_batch_label()` with atomic version**

In `app01/views.py`, replace lines 1609–1624:

```python
def _generate_batch_label() -> str:
    """Return today's rolling batch label, e.g. 20260617-001. Atomic under concurrent uploads."""
    from datetime import date
    from django.db import transaction
    prefix = date.today().strftime('%Y%m%d')
    with transaction.atomic():
        existing = list(
            Experiment.objects
            .select_for_update()
            .filter(batch_label__startswith=prefix + '-')
            .values_list('batch_label', flat=True)
        )
        used = set()
        for bl in existing:
            tail = bl[len(prefix) + 1:]
            if tail.isdigit():
                used.add(int(tail))
        n = 1
        while n in used:
            n += 1
        return f'{prefix}-{n:03d}'
```

- [ ] **Step 4: Run tests again to confirm still passes**

```bash
python manage.py test app01.tests.GenerateBatchLabelTests -v 2
```

Expected: 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "fix: make _generate_batch_label() atomic using select_for_update"
```

---

## Task 7: Create `smart_upload_preview_view` (Phases 1–4 orchestration)

**Files:**
- Modify: `app01/views.py` (add new view after `smart_upload_view`)
- Modify: `bprdb/urls.py` (add new URL)

- [ ] **Step 1: Update imports at top of `views.py`**

In `app01/views.py`, find the import block for upload_pipeline (around line 574). Add the new functions:

```python
from app01.upload_pipeline import (
    parse_seq_file, parse_summary_csv, parse_cp_file,
    build_preview, normalize_compound_ids, parse_transfection_file,
    parse_invivo_kd_file, parse_body_weight_file, detect_invivo_file_type,
    _BytesFile, canonicalize_compound_id,
    normalize_phase, diff_strands, dedup_phase,  # NEW
)
```

- [ ] **Step 2: Add `smart_upload_preview_view` after `smart_upload_view`**

Find the `@login_required` decorator before `smart_upload_confirm_view` (line 1957) and insert the new view before it:

```python
@login_required
def smart_upload_preview_view(request):
    """Runs Phases 2-4 on already-parsed smart_preview session data.

    Stores pipeline_result in session['pipeline_result'] and re-renders
    smart_upload.html with conflict panels. If there are blocking errors,
    the confirm button stays disabled.
    """
    if not _has_module(request.user, 'upload'):
        messages.error(request, '权限不足，无法访问上传页面')
        return redirect('compound_list')
    if request.method != 'POST':
        return redirect('smart_upload')

    smart_preview = request.session.get('smart_preview')
    if not smart_preview:
        return redirect('smart_upload')

    project_code = smart_preview.get('project_code', '')
    invitro = smart_preview.get('invitro') or {}
    invivo_groups = smart_preview.get('invivo_groups', [])

    # Preserve form values in session so confirm view can read them without re-POST
    request.session['upload_meta'] = {
        'batch_label':   request.POST.get('batch_label', '').strip(),
        'assay_name':    request.POST.get('assay_name', '').strip(),
        'exp_date':      request.POST.get('exp_date', '').strip() or None,
        'target_name':   request.POST.get('target_name', '').strip(),
        'source_batch':  request.POST.get('source_batch', '').strip(),
        'attach_vitro':  request.POST.get('source_exp_vitro') == '1',
        'attach_vivo':   request.POST.get('source_exp_vivo') == '1',
    }

    pipeline_result = {
        'errors': [],
        'warnings': [],
        'remap_log': [],
        'strand_diffs': [],
        'dedup_report': {'exp_conflicts': [], 'dp_conflicts': []},
    }

    # Phase 1 warnings from parse results (CP gene detection, transfection conflicts)
    for cp_parsed in invitro.get('cp_parsed_list', []):
        pipeline_result['warnings'].extend(cp_parsed.get('warnings', []))
    if invitro.get('transfection_warnings'):
        pipeline_result['warnings'].extend(invitro['transfection_warnings'])

    # Phase 2: normalize all compound IDs
    all_cids = list(set(
        list(invitro.get('strand_map', {}).keys()) +
        [e['compound_id'] for e in invitro.get('experiments', [])] +
        [g['compound_id'] for grp in invivo_groups for g in grp.get('groups', [])]
    ))
    if all_cids:
        norm_result = normalize_phase(all_cids, project_code)
        pipeline_result['errors'].extend(norm_result.errors)
        pipeline_result['warnings'].extend(norm_result.warnings)
        pipeline_result['remap_log'].extend(norm_result.remap_log)
        # Store id_map in session for Phase 5 to use
        request.session['normalize_id_map'] = norm_result.id_map

    # Phase 3: strand conflict detection
    upload_strands = []
    for cid, seq_data in invitro.get('strand_map', {}).items():
        resolved = request.session.get('normalize_id_map', {}).get(cid, cid)
        if seq_data.get('ss_seq'):
            upload_strands.append({'compound_id': resolved, 'strand_type': 'SS', 'new_seq': seq_data['ss_seq']})
        if seq_data.get('as_seq'):
            upload_strands.append({'compound_id': resolved, 'strand_type': 'AS', 'new_seq': seq_data['as_seq']})
    if upload_strands:
        diffs = diff_strands(upload_strands)
        pipeline_result['strand_diffs'] = [
            {'compound_id': d.compound_id, 'strand_type': d.strand_type,
             'old_seq': d.old_seq, 'new_seq': d.new_seq,
             'diff_positions': d.diff_positions, 'user_choice': None}
            for d in diffs
        ]

    # Phase 4: dedup detection
    id_map = request.session.get('normalize_id_map', {})
    upload_records = [
        {
            'compound_id': id_map.get(e['compound_id'], e['compound_id']),
            'batch_label': request.session['upload_meta']['batch_label'],
            'assay_name': request.session['upload_meta']['assay_name'] or e.get('assay_name', ''),
            'datapoints': e.get('datapoints', []),
        }
        for e in invitro.get('experiments', [])
    ]
    if upload_records and request.session['upload_meta']['batch_label']:
        pipeline_result['dedup_report'] = dedup_phase(upload_records)

    request.session['pipeline_result'] = pipeline_result

    import json as _json
    from app01.models import UploadVocabulary
    qs = Experiment.objects.filter(compound__project=project_code) if project_code else Experiment.objects
    return render(request, 'smart_upload.html', {
        'preview': smart_preview,
        'upload_meta': request.session['upload_meta'],
        'pipeline_result': pipeline_result,
        'show_conflict_panels': True,
        'vocab_file_types': list(UploadVocabulary.objects.filter(category='file_type').order_by('-is_builtin', 'label')),
        'vocab_readouts': list(UploadVocabulary.objects.filter(category='invivo_readout').order_by('-is_builtin', 'label')),
        'suggested_batch_label': _generate_batch_label(),
        'available_batches': list(qs.order_by().values_list('batch_label', flat=True).distinct().order_by('-batch_label')),
    })
```

- [ ] **Step 3: Register the new URL**

In `bprdb/urls.py`, add after the `smart_upload_confirm` line:

```python
path('upload/smart/', views.smart_upload_view, name='smart_upload'),
path('upload/smart/preview/', views.smart_upload_preview_view, name='smart_upload_preview'),  # NEW
path('upload/smart/confirm/', views.smart_upload_confirm_view, name='smart_upload_confirm'),
```

- [ ] **Step 4: Store Phase 1 parse warnings in `smart_preview` session dict**

`parse_cp_file` and `parse_transfection_file` now return `warnings` (Task 2). Find all call sites of these functions in `smart_upload_view` (search for `parse_cp_file(` and `parse_transfection_file(` in `views.py`) and collect their warnings. Store them before saving the session:

```python
    # After parsing cp file (wherever parse_cp_file is called in smart_upload_view):
    session_parse_warnings = []
    cp_result = parse_cp_file(_BytesFile(file_bytes))
    session_parse_warnings.extend(cp_result.warnings)

    # After parsing transfection file:
    transfection_result = parse_transfection_file(_BytesFile(file_bytes))
    session_parse_warnings.extend(transfection_result.warnings)

    # Before saving smart_preview to session:
    smart_preview['parse_warnings'] = session_parse_warnings
    request.session['smart_preview'] = smart_preview
```

In `smart_upload_preview_view`, read these in the Phase 1 warnings block:
```python
    pipeline_result['warnings'].extend(smart_preview.get('parse_warnings', []))
```

- [ ] **Step 5: Verify the server starts without import errors**

```bash
python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 6: Commit**

```bash
git add app01/views.py bprdb/urls.py
git commit -m "feat: add smart_upload_preview_view running pipeline phases 2-4"
```

---

## Task 8: Refactor `smart_upload_confirm_view` to Phase 5 only

**Files:**
- Modify: `app01/views.py:1957` (the existing `smart_upload_confirm_view`)

The goal: the confirm view reads `pipeline_result` and `upload_meta` from session instead of rerunning validation. It applies strand choices and version logic.

- [ ] **Step 1: Update the beginning of `smart_upload_confirm_view`**

In `app01/views.py`, find `smart_upload_confirm_view` (line 1957). Replace the section that reads POST params and revalidates with session reads:

```python
@login_required
def smart_upload_confirm_view(request):
    if not _has_module(request.user, 'upload'):
        messages.error(request, '权限不足，无法访问上传页面')
        return redirect('compound_list')
    if request.method != 'POST':
        return redirect('smart_upload')

    smart_preview = request.session.get('smart_preview')
    pipeline_result = request.session.get('pipeline_result', {})
    upload_meta = request.session.get('upload_meta', {})

    if not smart_preview:
        return redirect('smart_upload')

    # Read strand conflict choices submitted from the preview conflict panel
    strand_diffs = pipeline_result.get('strand_diffs', [])
    for diff in strand_diffs:
        choice = request.POST.get(f'strand_choice_{diff["compound_id"]}_{diff["strand_type"]}', 'keep')
        diff['user_choice'] = choice

    # Read dp_conflict skip/keep choice (default: skip)
    dp_conflicts = pipeline_result.get('dedup_report', {}).get('dp_conflicts', [])
    for dpc in dp_conflicts:
        key = f'dp_choice_{dpc["compound_id"]}_{dpc["batch_label"]}'
        dpc['skip'] = request.POST.get(key, 'skip') == 'skip'

    invitro = smart_preview.get('invitro')
    invivo_groups = smart_preview.get('invivo_groups', [])
    source_files = smart_preview.get('source_files', [])
    project_code = smart_preview.get('project_code', '')

    batch_label = upload_meta.get('batch_label', '')
    assay_name = upload_meta.get('assay_name', '')
    exp_date = upload_meta.get('exp_date')
    target_name_input = upload_meta.get('target_name', '')
    source_batch = upload_meta.get('source_batch', '')
    attach_vitro = upload_meta.get('attach_vitro', False)
    attach_vivo = upload_meta.get('attach_vivo', False)
    is_source_only = smart_preview.get('is_source_only', False)

    # Collect invivo_meta from POST (user still fills these on preview page)
    invivo_meta = []
    errors = []
    for i, group in enumerate(invivo_groups):
        if group.get('readout_code') == 'body_weight':
            time_unit = 'day'
        else:
            time_unit = request.POST.get(f'time_unit_{i}', '').strip()
        dose_override = request.POST.get(f'dose_override_{i}', '').strip()
        animal_species = request.POST.get(f'animal_species_{i}', '').strip()
        animal_strain = request.POST.get(f'animal_strain_{i}', '').strip()
        route = request.POST.get(f'route_{i}', '').strip()
        gender = request.POST.get(f'gender_{i}', '').strip()
        if not time_unit:
            errors.append(f'文件 {group["filename"]}: 请填写时间单位')
        if group['needs_dose'] and not dose_override:
            errors.append(f'文件 {group["filename"]}: 请填写剂量信息')
        if not animal_species:
            errors.append(f'文件 {group["filename"]}: 请填写动物物种')
        if not animal_strain:
            errors.append(f'文件 {group["filename"]}: 请填写动物品系')
        if not route:
            errors.append(f'文件 {group["filename"]}: 请填写给药途径')
        if not gender:
            errors.append(f'文件 {group["filename"]}: 请填写动物性别')
        invivo_meta.append({
            'time_unit': time_unit, 'dose_override': dose_override,
            'animal_species': animal_species, 'animal_strain': animal_strain,
            'route': route, 'gender': gender,
        })

    if not target_name_input:
        errors.append('靶点必填，不能为空')
    has_exp_data = bool(invitro and invitro.get('experiments')) or bool(invivo_groups)
    if has_exp_data and not batch_label:
        errors.append('批次名称为必填项')

    if errors:
        # Re-render with errors (same pattern as before)
        import json as _json
        from app01.models import UploadVocabulary
        qs_err = Experiment.objects.filter(compound__project=project_code) if project_code else Experiment.objects
        batch_exp_err = {}
        for exp in qs_err.order_by('-batch_label'):
            bl = exp.batch_label
            if not bl:
                continue
            if bl not in batch_exp_err:
                batch_exp_err[bl] = []
            batch_exp_err[bl].append({'exp_type': exp.exp_type, 'label': exp.assay_name or bl, 'pk': exp.pk})
        return render(request, 'smart_upload.html', {
            'preview': smart_preview,
            'upload_meta': upload_meta,
            'pipeline_result': pipeline_result,
            'show_conflict_panels': True,
            'errors': errors,
            'vocab_file_types': list(UploadVocabulary.objects.filter(category='file_type').order_by('-is_builtin', 'label')),
            'vocab_readouts': list(UploadVocabulary.objects.filter(category='invivo_readout').order_by('-is_builtin', 'label')),
            'suggested_batch_label': _generate_batch_label(),
            'available_batches': list(qs_err.order_by().values_list('batch_label', flat=True).distinct().order_by('-batch_label')),
            'batch_experiments_json': _json.dumps(batch_exp_err),
        })
```

- [ ] **Step 2: Update the vitro strand-writing block to respect strand conflict choices**

Find the strand-writing loop (around line 2133):

```python
                for cid, seq_data in preview_copy.get('strand_map', {}).items():
                    resolved = id_remap.get(cid, cid)
                    resolved = _resolve_cid(resolved)
                    compound, _ = Compound.objects.get_or_create(compound_id=resolved)
                    for strand_type, seq_key in [('SS', 'ss_seq'), ('AS', 'as_seq')]:
                        new_seq = seq_data.get(seq_key, '')
                        if not new_seq:
                            continue
                        # Check if this strand has a conflict choice
                        diff_choice = next(
                            (d['user_choice'] for d in strand_diffs
                             if d['compound_id'] == resolved and d['strand_type'] == strand_type),
                            None,
                        )
                        existing = Strand.objects.filter(compound=compound, strand_type=strand_type).first()
                        if existing:
                            if diff_choice == 'overwrite':
                                existing.modify_seq = new_seq
                                existing.save(update_fields=['modify_seq'])
                                n_strands += 1
                            # else: diff_choice == 'keep' or None (no conflict) → skip
                        else:
                            Strand.objects.create(
                                compound=compound,
                                strand_type=strand_type,
                                sequence_id=f'{resolved}_{strand_type}',
                                modify_seq=new_seq,
                            )
                            n_strands += 1
```

- [ ] **Step 3: Update the experiment creation block to use version logic**

Find the `Experiment.objects.get_or_create` call (around line 2158). Replace the entire experiment creation block:

```python
                for exp_data in preview_copy.get('experiments', []):
                    cid = _resolve_cid(exp_data['compound_id'])
                    compound, _ = Compound.objects.get_or_create(compound_id=cid)
                    if project_code:
                        compound.project = project_code
                        compound.save(update_fields=['project'])

                    # Check dedup report for this experiment
                    is_new_version = any(
                        c['compound_id'] == cid
                        and c['batch_label'] == preview_copy['batch_label']
                        and c['assay_name'] == preview_copy['assay_name']
                        for c in pipeline_result.get('dedup_report', {}).get('exp_conflicts', [])
                    )
                    if is_new_version:
                        latest = Experiment.objects.filter(
                            compound=compound,
                            batch_label=preview_copy['batch_label'],
                            assay_name=preview_copy['assay_name'],
                        ).order_by('-version').first()
                        next_version = (latest.version + 1) if latest else 1
                    else:
                        next_version = 1

                    exp = Experiment.objects.create(
                        compound=compound,
                        exp_type=exp_data.get('exp_type', 'in_vitro'),
                        assay_name=preview_copy['assay_name'],
                        batch_label=preview_copy['batch_label'],
                        cell_line=preview_copy.get('cell_line', ''),
                        notes=preview_copy.get('notes', ''),
                        date=exp_date_obj,
                        version=next_version,
                    )
                    vitro_experiments.append(exp)
                    n_experiments += 1

                    # Collect dp_conflict skip sets for this experiment
                    skip_fps = set()
                    for dpc in pipeline_result.get('dedup_report', {}).get('dp_conflicts', []):
                        if (dpc['compound_id'] == cid
                                and dpc['batch_label'] == preview_copy['batch_label']
                                and dpc['assay_name'] == preview_copy['assay_name']
                                and dpc.get('skip', True)):
                            for dp in dpc['datapoints']:
                                skip_fps.add((
                                    round(float(dp.get('x_value') or 0), 4),
                                    dp.get('replicate', ''),
                                    round(float(dp.get('value') or 0), 4) if dp.get('value') is not None else None,
                                    dp.get('readout_type', ''),
                                    bool(dp.get('is_control', False)),
                                ))

                    dp_objs = []
                    for dp in exp_data.get('datapoints', []):
                        fp = (
                            round(float(dp.get('x_value') or 0), 4),
                            dp.get('replicate', ''),
                            round(float(dp.get('value') or 0), 4) if dp.get('value') is not None else None,
                            dp.get('readout_type', ''),
                            bool(dp.get('is_control', False)),
                        )
                        if fp in skip_fps:
                            continue
                        dp_objs.append(DataPoint(
                            experiment=exp,
                            x_value=dp['x_value'],
                            x_type=dp['x_type'],
                            replicate=dp['replicate'],
                            value=dp['value'],
                            readout_type=dp['readout_type'],
                            is_control=dp.get('is_control', False),
                            raw_cp=dp.get('raw_cp'),
                        ))
                    DataPoint.objects.bulk_create(dp_objs)

                    if exp_data.get('summary'):
                        s = exp_data['summary']
                        ExperimentSummary.objects.create(
                            experiment=exp,
                            max_kd_pct=s.get('max_kd_pct'),
                            ic50_nm=s.get('ic50_nm'),
                            rank=s.get('rank'),
                        )
```

- [ ] **Step 4: Fix invivo compound ID resolution to use normalize_phase id_map**

Find the invivo compound_id resolution (around line 2270):

```python
                    compound, _ = Compound.objects.get_or_create(
                        compound_id=_resolve_cid(g['compound_id'])
                    )
```

Update `_resolve_cid` to also check the normalize_id_map from session:

Find the `_resolve_cid` helper (around line 1986) and update it:

```python
    _normalize_id_map = request.session.get('normalize_id_map', {})

    def _resolve_cid(raw: str) -> str:
        # First check if normalize_phase already mapped this ID
        if raw in _normalize_id_map:
            return _normalize_id_map[raw]
        remapped = user_cid_remap.get(raw, raw)
        return canonicalize_compound_id(remapped, project_code)
```

- [ ] **Step 5: Move temp file cleanup outside the atomic block**

The file cleanup block currently at lines 2344–2359 is already outside the vitro/invivo `transaction.atomic()` blocks. Verify it remains that way and still uses `default_storage.exists()` checks. No code change needed if the existing structure is preserved.

- [ ] **Step 6: Clear pipeline_result and upload_meta from session after successful save**

At the successful-completion path (near `del request.session['smart_preview']`), add:

```python
    del request.session['smart_preview']
    request.session.pop('pipeline_result', None)
    request.session.pop('upload_meta', None)
    request.session.pop('normalize_id_map', None)
```

- [ ] **Step 7: Verify the server starts without errors**

```bash
python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 8: Commit**

```bash
git add app01/views.py
git commit -m "refactor: split smart_upload_confirm_view into preview (phases 1-4) and confirm (phase 5) with version logic"
```

---

## Task 9: Update `smart_upload.html` with conflict panels

**Files:**
- Modify: `templates/smart_upload.html`

- [ ] **Step 1: Find the existing confirm form action in the template**

```bash
grep -n "smart_upload_confirm\|action=" templates/smart_upload.html | head -20
```

Note the line number of the form that POSTs to `smart_upload_confirm`.

- [ ] **Step 2: Change the primary "confirm" form to POST to `smart_upload_preview` first**

In `templates/smart_upload.html`, find the form that submits to `smart_upload_confirm` (the main metadata form). Change its action to:

```html
<form method="post" action="{% url 'smart_upload_preview' %}" id="upload-meta-form">
```

- [ ] **Step 3: Add pipeline result panels before the existing confirm button**

Find the section where the confirm/submit button lives and insert the four panels before it. Add the following block:

```html
{% if show_conflict_panels and pipeline_result %}

  {# Panel 1: Parse summary — always shown #}
  <div class="ds-card" style="margin-bottom:16px;">
    <div class="ds-card-header">
      <span class="ds-card-title">解析摘要</span>
    </div>
    <div class="ds-card-body">
      {% if pipeline_result.errors %}
        <div style="color:#ef4444;font-weight:600;margin-bottom:8px;">
          ⛔ {{ pipeline_result.errors|length }} 个错误需要修正后才能上传
        </div>
        <ul style="margin:0;padding-left:20px;">
          {% for err in pipeline_result.errors %}
            <li style="color:#ef4444;">{{ err }}</li>
          {% endfor %}
        </ul>
      {% endif %}
      {% if pipeline_result.warnings %}
        <div style="color:#f59e0b;margin-top:8px;">
          ⚠ {{ pipeline_result.warnings|length }} 条提示（不影响上传）
        </div>
        <ul style="margin:0;padding-left:20px;margin-top:4px;">
          {% for w in pipeline_result.warnings %}
            <li style="color:#f59e0b;font-size:13px;">{{ w }}</li>
          {% endfor %}
        </ul>
      {% endif %}
      {% if not pipeline_result.errors and not pipeline_result.warnings %}
        <span style="color:#22c55e;">✓ 解析通过，无问题</span>
      {% endif %}
    </div>
  </div>

  {# Panel 2: ID remap log — shown if any remapping occurred #}
  {% if pipeline_result.remap_log %}
  <div class="ds-card" style="margin-bottom:16px;">
    <div class="ds-card-header">
      <span class="ds-card-title">ID 重映射日志</span>
      <span class="ds-card-subtitle" style="font-size:12px;color:#64748b;">以下 ID 已自动映射，仅供确认</span>
    </div>
    <div class="ds-card-body">
      <table style="width:100%;font-size:13px;border-collapse:collapse;">
        <thead>
          <tr style="color:#64748b;">
            <th style="text-align:left;padding:4px 8px;">原始 ID</th>
            <th style="text-align:left;padding:4px 8px;">映射至</th>
            <th style="text-align:left;padding:4px 8px;">原因</th>
          </tr>
        </thead>
        <tbody>
          {% for entry in pipeline_result.remap_log %}
          <tr>
            <td style="padding:4px 8px;font-family:monospace;">{{ entry.original }}</td>
            <td style="padding:4px 8px;font-family:monospace;color:#22c55e;">{{ entry.canonical }}</td>
            <td style="padding:4px 8px;color:#94a3b8;">{{ entry.reason }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
  {% endif %}

  {# Panel 3: Strand conflicts — user must choose keep/overwrite per diff #}
  {% if pipeline_result.strand_diffs %}
  <div class="ds-card" style="margin-bottom:16px;border-color:#7c3aed;">
    <div class="ds-card-header" style="background:rgba(124,58,237,0.08);">
      <span class="ds-card-title" style="color:#7c3aed;">序列冲突 — 需要逐条决策</span>
    </div>
    <div class="ds-card-body">
      {% for diff in pipeline_result.strand_diffs %}
      <div style="margin-bottom:16px;padding:12px;background:#1e293b;border-radius:8px;">
        <div style="font-size:13px;color:#94a3b8;margin-bottom:8px;">
          <strong style="color:#f1f5f9;">{{ diff.compound_id }}</strong> · {{ diff.strand_type }} strand
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:10px;">
          <div>
            <div style="font-size:11px;color:#64748b;margin-bottom:4px;">旧序列</div>
            <div style="font-family:monospace;font-size:12px;word-break:break-all;color:#94a3b8;">{{ diff.old_seq }}</div>
          </div>
          <div>
            <div style="font-size:11px;color:#64748b;margin-bottom:4px;">新序列</div>
            <div style="font-family:monospace;font-size:12px;word-break:break-all;color:#f1f5f9;">{{ diff.new_seq }}</div>
          </div>
        </div>
        <div style="display:flex;gap:12px;">
          <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
            <input type="radio" name="strand_choice_{{ diff.compound_id }}_{{ diff.strand_type }}"
                   value="keep" checked>
            <span style="font-size:13px;">保留旧序列</span>
          </label>
          <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
            <input type="radio" name="strand_choice_{{ diff.compound_id }}_{{ diff.strand_type }}"
                   value="overwrite">
            <span style="font-size:13px;color:#f59e0b;">用新序列覆盖</span>
          </label>
        </div>
      </div>
      {% endfor %}
    </div>
  </div>
  {% endif %}

  {# Panel 4: Duplicate detection report #}
  {% with dedup=pipeline_result.dedup_report %}
  {% if dedup.exp_conflicts or dedup.dp_conflicts %}
  <div class="ds-card" style="margin-bottom:16px;border-color:#0369a1;">
    <div class="ds-card-header" style="background:rgba(3,105,161,0.08);">
      <span class="ds-card-title" style="color:#38bdf8;">重复检测报告</span>
    </div>
    <div class="ds-card-body">
      {% if dedup.exp_conflicts %}
        <div style="margin-bottom:10px;">
          <div style="font-size:12px;color:#64748b;margin-bottom:6px;">实验级重复（将自动创建新版本）</div>
          {% for ec in dedup.exp_conflicts %}
          <div style="font-size:13px;padding:6px 10px;background:#0f172a;border-radius:6px;margin-bottom:4px;">
            ℹ {{ ec.compound_id }} · {{ ec.batch_label }} · {{ ec.assay_name }}
            <span style="color:#64748b;"> → 将创建 v{{ ec.existing_version|add:1 }}</span>
          </div>
          {% endfor %}
        </div>
      {% endif %}
      {% if dedup.dp_conflicts %}
        <div>
          <div style="font-size:12px;color:#f59e0b;margin-bottom:6px;">数据点级重复</div>
          {% for dpc in dedup.dp_conflicts %}
          <div style="font-size:13px;padding:8px 10px;background:#0f172a;border-radius:6px;margin-bottom:6px;">
            <div style="margin-bottom:6px;">{{ dpc.compound_id }} · {{ dpc.batch_label }} — {{ dpc.datapoints|length }} 个重复数据点</div>
            <div style="display:flex;gap:12px;">
              <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
                <input type="radio" name="dp_choice_{{ dpc.compound_id }}_{{ dpc.batch_label }}"
                       value="skip" checked>
                <span style="font-size:12px;">跳过这些数据点</span>
              </label>
              <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
                <input type="radio" name="dp_choice_{{ dpc.compound_id }}_{{ dpc.batch_label }}"
                       value="keep">
                <span style="font-size:12px;color:#f59e0b;">仍然上传</span>
              </label>
            </div>
          </div>
          {% endfor %}
        </div>
      {% endif %}
    </div>
  </div>
  {% endif %}
  {% endwith %}

  {# Final confirm button — no invivo hidden inputs needed; metadata is in session #}
  {% if pipeline_result.errors %}
    <div style="text-align:center;color:#ef4444;padding:12px;">
      ⛔ 请修正上方错误后重新上传文件
    </div>
  {% else %}
    <form method="post" action="{% url 'smart_upload_confirm' %}" style="margin-top:8px;">
      {% csrf_token %}
      {# Only strand conflict choices and dp conflict choices come from this form.
         All other metadata (batch_label, invivo fields, etc.) is read from session in the confirm view. #}
      <div style="text-align:center;">
        <button type="submit" class="btn btn-primary" style="padding:10px 32px;font-size:15px;">
          确认上传
        </button>
      </div>
    </form>
  {% endif %}

{% endif %}
```

- [ ] **Step 2: Pass invivo metadata correctly through the two-step form**

The invivo metadata (time_unit, dose_override, etc.) is entered on the preview page and must survive the redirect to the conflict panel → confirm view. Store ALL invivo fields in session in `smart_upload_preview_view`.

In `smart_upload_preview_view`, extend the `upload_meta` session dict:

```python
    # Capture invivo per-group metadata from POST so confirm view can read from session
    n_groups = len(smart_preview.get('invivo_groups', []))
    for i in range(n_groups):
        for fname in ['time_unit', 'dose_override', 'animal_species', 'animal_strain', 'route', 'gender']:
            key = f'{fname}_{i}'
            request.session['upload_meta'][key] = request.POST.get(key, '').strip()
```

Then in `smart_upload_confirm_view`, replace every `request.POST.get(f'time_unit_{i}', '')` etc. with `upload_meta.get(f'time_unit_{i}', '')` — reading from the session `upload_meta` dict, not from the POST body. The confirm POST form only needs to contain strand conflict choices and dp conflict choices (no hidden invivo fields needed in the template).

- [ ] **Step 3: Smoke-test the full upload flow manually**

```bash
python manage.py runserver
```

1. Navigate to `/upload/smart/`
2. Upload a vitro CSV file
3. Select file type, fill metadata, click "预览"
4. Verify the pipeline result panels appear
5. If no conflicts: click "确认上传" and verify success message
6. Run `python manage.py check` — no errors

- [ ] **Step 4: Commit**

```bash
git add templates/smart_upload.html app01/views.py
git commit -m "feat: add 4-panel pipeline conflict display to smart_upload.html"
```

---

## Task 10: Run full test suite and verify no regressions

- [ ] **Step 1: Run all tests**

```bash
python manage.py test app01 -v 2
```

Expected: all existing tests PASS plus new tests from Tasks 1–6.

- [ ] **Step 2: Run ruff linter**

```bash
ruff check app01/upload_pipeline.py app01/views.py app01/models.py
```

Expected: no errors (fix any reported issues before committing)

- [ ] **Step 3: Final commit if any lint fixes were needed**

```bash
git add -p
git commit -m "fix: ruff lint cleanup after upload pipeline robustness implementation"
```
