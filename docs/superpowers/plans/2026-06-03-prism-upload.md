# Prism File Experiment Data Upload — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to upload Prism-exported CSV/TXT files on the existing experiment upload page, automatically parsing the wide-format matrix into Experiment + DataPoint records.

**Architecture:** New `app01/prism_upload.py` holds the pure parsing function; two new views (`upload_prism_preview`, `upload_prism_confirm`) implement the two-step upload flow using Django session for inter-step state; `upload_experiment.html` gains a second Tab. No existing view logic is touched.

**Tech Stack:** Django 5.1, Python `csv` stdlib, existing `Experiment`/`DataPoint` models, Django session (DB-backed).

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `app01/prism_upload.py` | `parse_prism_file()` — format detection, header grouping, value parsing |
| Modify | `app01/tests.py` | `PrismParseTests`, `PrismUploadViewTests` |
| Modify | `app01/views.py` | `upload_prism_preview`, `upload_prism_confirm` (append at end) |
| Modify | `bms/urls.py` | Two new `path()` entries |
| Create | `templates/upload_prism_preview.html` | Preview summary + metadata form |
| Modify | `templates/upload_experiment.html` | Add Prism Tab alongside existing CSV form |

---

### Task 1: `parse_prism_file()` + unit tests

**Files:**
- Create: `app01/prism_upload.py`
- Modify: `app01/tests.py`

- [ ] **Step 1: Write failing tests**

Append to `app01/tests.py` (after the last class):

```python
# ── Prism Upload Tests ────────────────────────────────────────────────────────

from io import BytesIO
from app01.prism_upload import parse_prism_file  # noqa: E402 – placed here intentionally


class PrismParseTests(TestCase):
    """Unit tests for parse_prism_file() in app01/prism_upload.py."""

    def setUp(self):
        self.seq = Sequence.objects.create(rm_code='PP0001', seq='AUGC', seq_type='AS')
        self.delivery = Delivery.objects.create(
            sequence=self.seq,
            seq_type='AS',
            duplex_id='BP000099',
        )

    @staticmethod
    def _f(content, name='test.csv'):
        return BytesIO(content if isinstance(content, bytes) else content.encode())

    def test_csv_basic_parsing(self):
        content = b',BP000099,BP000099,BP000099,NOPE\n-7,0.0,0.0,0.0,1.0\n14,-95.67,-94.49,-95.24,1.5\n'
        r = parse_prism_file(self._f(content), 'test.csv')
        self.assertIn('BP000099', r['matched'])
        self.assertEqual(r['x_values'], [-7.0, 14.0])
        self.assertIn('NOPE', r['skipped_cols'])
        rows = r['matched']['BP000099']['rows']
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['replicates'], [0.0, 0.0, 0.0])

    def test_txt_tab_separated(self):
        content = b'\tBP000099\tBP000099\tBP000099\n14\t-95.67\t-94.49\t-95.24\n'
        r = parse_prism_file(BytesIO(content), 'test.txt')
        self.assertIn('BP000099', r['matched'])
        self.assertEqual(r['x_values'], [14.0])

    def test_asterisk_marks_excluded(self):
        content = b',BP000099,BP000099,BP000099\n14,-95.67,-94.49*,-95.24\n'
        r = parse_prism_file(self._f(content), 'test.csv')
        row = r['matched']['BP000099']['rows'][0]
        self.assertAlmostEqual(row['replicates'][1], -94.49)
        self.assertTrue(row['excluded'][1])
        self.assertFalse(row['excluded'][0])

    def test_empty_cell_is_none(self):
        content = b',BP000099,BP000099,BP000099\n14,-95.67,,-95.24\n'
        r = parse_prism_file(self._f(content), 'test.csv')
        self.assertIsNone(r['matched']['BP000099']['rows'][0]['replicates'][1])

    def test_unsupported_extension_raises(self):
        with self.assertRaises(ValueError):
            parse_prism_file(BytesIO(b'data'), 'test.xls')

    def test_no_matching_duplexes_returns_empty(self):
        content = b',MISSING,MISSING,MISSING\n14,1.0,2.0,3.0\n'
        r = parse_prism_file(self._f(content), 'test.csv')
        self.assertEqual(r['matched'], {})
        self.assertIn('MISSING', r['skipped_cols'])

    def test_invalid_x_value_skipped_with_warning(self):
        content = b',BP000099,BP000099,BP000099\nbadval,-95.67,-94.49,-95.24\n14,-90.0,-91.0,-92.0\n'
        r = parse_prism_file(self._f(content), 'test.csv')
        self.assertEqual(r['x_values'], [14.0])
        self.assertEqual(len(r['warnings']), 1)
        self.assertIn('badval', r['warnings'][0])

    def test_column_name_whitespace_stripped(self):
        content = b',"BP000099 ","BP000099 ","BP000099 "\n14,-95.0,-94.0,-93.0\n'
        r = parse_prism_file(self._f(content), 'test.csv')
        self.assertIn('BP000099', r['matched'])
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
source venv/bin/activate && python manage.py test app01.tests.PrismParseTests -v 2 2>&1 | tail -10
```

Expected output contains: `ModuleNotFoundError` or `ImportError: cannot import name 'parse_prism_file'`

- [ ] **Step 3: Create `app01/prism_upload.py`**

```python
import csv
import io


def parse_prism_file(file_obj, filename):
    """Parse a Prism-exported CSV (.csv) or TXT (.txt) wide-format file.

    Returns dict:
      matched    — {duplex_id: {'rows': [{'x', 'replicates', 'excluded'}]}}
      x_values   — ordered list of x-axis float values (first column)
      skipped_cols — sorted list of unrecognised column header strings
      warnings   — list of human-readable warning strings
    """
    fname = filename.lower()
    if fname.endswith('.csv'):
        sep = ','
    elif fname.endswith('.txt'):
        sep = '\t'
    else:
        raise ValueError(f"不支持的文件格式：{filename}，请使用 .csv 或 .txt")

    raw = file_obj.read()
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8-sig')

    lines = [ln for ln in raw.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("文件为空")

    def split_row(line):
        return next(csv.reader(io.StringIO(line), delimiter=sep))

    # ── Header row ──────────────────────────────────────────────────────────────
    header = split_row(lines[0])
    col_names = [c.strip() for c in header[1:]]  # first cell = x-axis label, skip it

    unique_names = {n for n in col_names if n}
    from .models import Delivery
    existing_ids = set(
        Delivery.objects.filter(duplex_id__in=unique_names)
        .values_list('duplex_id', flat=True)
        .distinct()
    )

    # Build col_mapping: (duplex_id, rep_index, is_matched) per data column
    rep_counter = {}
    col_mapping = []
    for n in col_names:
        rep_idx = rep_counter.get(n, 0)
        rep_counter[n] = rep_idx + 1
        col_mapping.append((n, rep_idx, n in existing_ids))

    skipped_cols = sorted({n for n, _, m in col_mapping if n and not m})

    # ── Data rows ────────────────────────────────────────────────────────────────
    # raw_rows: {duplex_id: {x_float: {'replicates': {rep_idx: val}, 'excluded': {rep_idx: bool}}}}
    raw_rows = {}
    x_values = []
    seen_x = set()
    warnings = []

    for line_no, line in enumerate(lines[1:], start=2):
        row = split_row(line)
        if not row:
            continue
        x_raw = row[0].strip()
        try:
            x = float(x_raw)
        except ValueError:
            warnings.append(f"第 {line_no} 行：X 轴值 {x_raw!r} 无法解析，已跳过")
            continue

        if x not in seen_x:
            seen_x.add(x)
            x_values.append(x)

        data_cols = row[1:]
        for col_idx, (duplex_id, rep_idx, matched) in enumerate(col_mapping):
            if not matched or not duplex_id:
                continue
            raw_rows.setdefault(duplex_id, {}).setdefault(
                x, {'replicates': {}, 'excluded': {}}
            )
            cell = data_cols[col_idx].strip() if col_idx < len(data_cols) else ''
            if not cell:
                continue
            excluded = cell.endswith('*')
            if excluded:
                cell = cell[:-1].strip()
            try:
                val = float(cell)
                raw_rows[duplex_id][x]['replicates'][rep_idx] = val
                raw_rows[duplex_id][x]['excluded'][rep_idx] = excluded
            except ValueError:
                warnings.append(
                    f"第 {line_no} 行，列 {col_idx + 2}：值 {cell!r} 无法解析，已跳过"
                )

    # ── Assemble final structure ─────────────────────────────────────────────────
    rep_counts = {}
    for n, rep_idx, matched in col_mapping:
        if matched and n:
            rep_counts[n] = max(rep_counts.get(n, 0), rep_idx + 1)

    matched = {}
    for duplex_id, x_data in raw_rows.items():
        n_reps = rep_counts.get(duplex_id, 3)
        rows = [
            {
                'x': x,
                'replicates': [x_data[x]['replicates'].get(i) for i in range(n_reps)],
                'excluded': [x_data[x]['excluded'].get(i, False) for i in range(n_reps)],
            }
            for x in x_values
            if x in x_data
        ]
        matched[duplex_id] = {'rows': rows}

    return {
        'matched': matched,
        'x_values': x_values,
        'skipped_cols': skipped_cols,
        'warnings': warnings,
    }
```

- [ ] **Step 4: Run tests — expect all PASS**

```bash
source venv/bin/activate && python manage.py test app01.tests.PrismParseTests -v 2 2>&1 | tail -15
```

Expected: `Ran 8 tests in ...s` → `OK`

- [ ] **Step 5: Commit**

```bash
git add app01/prism_upload.py app01/tests.py
git commit -m "feat: add parse_prism_file utility with tests"
```

---

### Task 2: `upload_prism_preview` view + URL + view tests

**Files:**
- Modify: `app01/views.py` (append)
- Modify: `bms/urls.py`
- Modify: `app01/tests.py`
- Create: `templates/upload_prism_preview.html` (placeholder only — full template in Task 4)

- [ ] **Step 1: Write failing view tests**

Append to `app01/tests.py` (after `PrismParseTests`):

```python
from django.core.files.uploadedfile import SimpleUploadedFile


class PrismUploadViewTests(TestCase):
    """Integration tests for upload_prism_preview and upload_prism_confirm views."""

    CSV_CONTENT = b',BP000077,BP000077,BP000077\n14,-95.67,-94.49,-95.24\n28,-97.16,-96.57,-93.37\n'

    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='prism_tester', password='x', user_type='admin',
            permissions_project='',
        )
        self.client.force_login(self.user)
        seq = Sequence.objects.create(rm_code='PP0002', seq='AUGC', seq_type='AS')
        Delivery.objects.create(sequence=seq, seq_type='AS', duplex_id='BP000077')

    # ── preview tests ────────────────────────────────────────────────────────

    def test_preview_get_redirects(self):
        r = self.client.get('/upload_prism_preview/')
        self.assertRedirects(r, '/upload_experiment/')

    def test_preview_post_no_file_redirects(self):
        r = self.client.post('/upload_prism_preview/')
        self.assertRedirects(r, '/upload_experiment/')

    def test_preview_post_invalid_extension_redirects(self):
        f = SimpleUploadedFile('data.xls', b'data', content_type='application/octet-stream')
        r = self.client.post('/upload_prism_preview/', {'prism_file': f})
        self.assertRedirects(r, '/upload_experiment/')

    def test_preview_post_valid_csv_renders_preview(self):
        f = SimpleUploadedFile('data.csv', self.CSV_CONTENT, content_type='text/csv')
        r = self.client.post('/upload_prism_preview/', {'prism_file': f})
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, 'upload_prism_preview.html')
        self.assertContains(r, 'BP000077')

    def test_preview_post_no_matching_duplexes_redirects(self):
        f = SimpleUploadedFile('data.csv', b',NOPE,NOPE,NOPE\n14,1.0,2.0,3.0\n', content_type='text/csv')
        r = self.client.post('/upload_prism_preview/', {'prism_file': f})
        self.assertRedirects(r, '/upload_experiment/')

    def test_preview_stores_parsed_in_session(self):
        f = SimpleUploadedFile('data.csv', self.CSV_CONTENT, content_type='text/csv')
        self.client.post('/upload_prism_preview/', {'prism_file': f})
        self.assertIn('prism_parsed', self.client.session)
        self.assertIn('BP000077', self.client.session['prism_parsed']['matched'])
```

- [ ] **Step 2: Run tests — expect 404 / NoReverseMatch**

```bash
source venv/bin/activate && python manage.py test app01.tests.PrismUploadViewTests -v 2 2>&1 | tail -15
```

Expected: Tests fail with `NoReverseMatch` or HTTP 404 for `/upload_prism_preview/`

- [ ] **Step 3: Add URL in `bms/urls.py`**

Open `bms/urls.py`. Find the block of experiment-related URLs (around lines 73–77). Insert after line 77:

```python
    path('upload_prism_preview/', views.upload_prism_preview, name='upload_prism_preview'),
```

- [ ] **Step 4: Add view in `app01/views.py`**

Append at the very end of `app01/views.py`:

```python
@login_required
def upload_prism_preview(request):
    """Step 1 of Prism upload: parse file, store in session, render preview."""
    if request.method != 'POST':
        return redirect('upload_experiment')

    file_obj = request.FILES.get('prism_file')
    if not file_obj:
        messages.error(request, "请选择文件")
        return redirect('upload_experiment')

    filename = file_obj.name
    if not (filename.lower().endswith('.csv') or filename.lower().endswith('.txt')):
        messages.error(request, "仅支持 .csv 或 .txt 格式")
        return redirect('upload_experiment')

    try:
        from app01.prism_upload import parse_prism_file
        result = parse_prism_file(file_obj, filename)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect('upload_experiment')

    if not result['matched']:
        messages.error(request, "文件中没有可识别的 duplex ID，请检查列标题")
        return redirect('upload_experiment')

    request.session['prism_parsed'] = result

    total_points = sum(
        len(d['rows']) * (len(d['rows'][0]['replicates']) if d['rows'] else 0)
        for d in result['matched'].values()
    )
    excluded_count = sum(
        sum(1 for ex in row['excluded'] if ex)
        for d in result['matched'].values()
        for row in d['rows']
    )

    return render(request, 'upload_prism_preview.html', {
        'matched_ids': list(result['matched'].keys()),
        'x_values': result['x_values'],
        'skipped_cols': result['skipped_cols'],
        'warnings': result['warnings'],
        'total_points': total_points,
        'excluded_count': excluded_count,
        'exp_type_choices': Experiment.EXP_TYPE_CHOICES,
        'assay_type_choices': Experiment.ASSAY_TYPE_CHOICES,
        'readout_type_choices': DataPoint.READOUT_TYPE_CHOICES,
        'conc_unit_choices': DataPoint.CONC_UNIT_CHOICES,
    })
```

- [ ] **Step 5: Create placeholder template**

Create `templates/upload_prism_preview.html` with minimal content so the view tests can pass (full template in Task 4):

```html
{% extends 'base.html' %}
{% block content %}
<p>{{ matched_ids|join:", " }}</p>
{% endblock %}
```

- [ ] **Step 6: Run tests — expect all PASS**

```bash
source venv/bin/activate && python manage.py test app01.tests.PrismUploadViewTests -v 2 2>&1 | tail -15
```

Expected: `Ran 6 tests in ...s` → `OK`

- [ ] **Step 7: Commit**

```bash
git add app01/views.py bms/urls.py templates/upload_prism_preview.html app01/tests.py
git commit -m "feat: add upload_prism_preview view, URL, and tests"
```

---

### Task 3: `upload_prism_confirm` view + URL + tests

**Files:**
- Modify: `app01/views.py` (append)
- Modify: `bms/urls.py`
- Modify: `app01/tests.py`

- [ ] **Step 1: Write failing confirm tests**

Append these methods inside `PrismUploadViewTests` (they reference `self.user` and `self.client` from setUp):

```python
    # ── confirm tests ────────────────────────────────────────────────────────

    def _set_session(self, rows=None):
        if rows is None:
            rows = [
                {'x': 14.0, 'replicates': [-95.67, -94.49, -95.24], 'excluded': [False, False, False]},
                {'x': 28.0, 'replicates': [-97.16, None, -93.37],   'excluded': [False, False, False]},
            ]
        session = self.client.session
        session['prism_parsed'] = {
            'matched': {'BP000077': {'rows': rows}},
            'x_values': [r['x'] for r in rows],
            'skipped_cols': [],
            'warnings': [],
        }
        session.save()

    def _confirm_post(self, extra=None):
        data = {
            'batch': 'B-Test',
            'exp_type': 'in_vivo',
            'assay_type': 'in_vivo_efficacy',
            'readout_type': 'knockdown_pct',
            'x_axis_type': 'timepoint',
        }
        if extra:
            data.update(extra)
        return self.client.post('/upload_prism_confirm/', data)

    def test_confirm_get_redirects(self):
        r = self.client.get('/upload_prism_confirm/')
        self.assertRedirects(r, '/upload_experiment/')

    def test_confirm_no_session_redirects(self):
        r = self._confirm_post()
        self.assertRedirects(r, '/upload_experiment/')

    def test_confirm_creates_experiment_and_datapoints(self):
        self._set_session()
        r = self._confirm_post({'batch': 'BatchA'})
        self.assertRedirects(r, '/upload_experiment/')
        exp = Experiment.objects.get(duplex_id='BP000077', batch='BatchA')
        # 2 rows × 3 reps = 6 slots; 1 is None → 5 DataPoints
        self.assertEqual(exp.datapoints.count(), 5)

    def test_confirm_timepoint_format(self):
        self._set_session()
        self._confirm_post({'batch': 'BatchTP'})
        exp = Experiment.objects.get(duplex_id='BP000077', batch='BatchTP')
        timepoints = set(exp.datapoints.values_list('timepoint', flat=True))
        self.assertIn('Day 14', timepoints)
        self.assertIn('Day 28', timepoints)

    def test_confirm_concentration_mode(self):
        self._set_session(rows=[
            {'x': 10.0, 'replicates': [-95.0, -94.0, -93.0], 'excluded': [False, False, False]},
        ])
        self._confirm_post({
            'batch': 'BatchConc',
            'exp_type': 'in_vitro',
            'assay_type': 'dose_response',
            'readout_type': 'mRNA_remaining',
            'x_axis_type': 'concentration',
            'conc_unit': 'nM',
        })
        exp = Experiment.objects.get(duplex_id='BP000077', batch='BatchConc')
        dp = exp.datapoints.first()
        self.assertEqual(dp.concentration_or_dose, 10.0)
        self.assertEqual(dp.conc_unit, 'nM')
        self.assertIsNone(dp.timepoint)

    def test_confirm_excluded_replicate_label(self):
        self._set_session(rows=[
            {'x': 14.0, 'replicates': [-95.0, -94.0, -93.0], 'excluded': [False, True, False]},
        ])
        self._confirm_post({'batch': 'BatchExcl'})
        exp = Experiment.objects.get(duplex_id='BP000077', batch='BatchExcl')
        excluded_dp = exp.datapoints.get(value=-94.0)
        self.assertEqual(excluded_dp.replicate, 'excluded')
        normal_dp = exp.datapoints.get(value=-95.0)
        self.assertEqual(normal_dp.replicate, '1')

    def test_confirm_skips_duplicate_experiment(self):
        self._set_session()
        Experiment.objects.create(
            duplex_id='BP000077', exp_type='in_vivo',
            assay_type='in_vivo_efficacy', batch='DupBatch',
            created_by='prism_tester',
        )
        self._confirm_post({'batch': 'DupBatch'})
        self.assertEqual(
            Experiment.objects.filter(duplex_id='BP000077', batch='DupBatch').count(), 1
        )

    def test_confirm_clears_session(self):
        self._set_session()
        self._confirm_post({'batch': 'BatchClr'})
        self.assertNotIn('prism_parsed', self.client.session)
```

- [ ] **Step 2: Run tests — expect failures on confirm routes**

```bash
source venv/bin/activate && python manage.py test app01.tests.PrismUploadViewTests -v 2 2>&1 | tail -20
```

Expected: Preview tests still pass; confirm tests fail with `NoReverseMatch` or 404.

- [ ] **Step 3: Add URL in `bms/urls.py`**

Add immediately after the `upload_prism_preview` line you added in Task 2:

```python
    path('upload_prism_confirm/', views.upload_prism_confirm, name='upload_prism_confirm'),
```

- [ ] **Step 4: Add view in `app01/views.py`**

Append after `upload_prism_preview`:

```python
@login_required
def upload_prism_confirm(request):
    """Step 2 of Prism upload: read session data, apply metadata, write to DB."""
    if request.method != 'POST':
        return redirect('upload_experiment')

    parsed = request.session.get('prism_parsed')
    if not isinstance(parsed, dict) or 'matched' not in parsed:
        messages.error(request, "会话已过期，请重新上传文件")
        return redirect('upload_experiment')

    batch = request.POST.get('batch', '').strip()
    if not batch:
        messages.error(request, "批次不能为空")
        return redirect('upload_experiment')

    exp_type      = request.POST.get('exp_type', 'in_vitro')
    assay_type    = request.POST.get('assay_type', 'single_point')
    readout_type  = request.POST.get('readout_type', 'mRNA_remaining')
    x_axis_type   = request.POST.get('x_axis_type', 'timepoint')
    conc_unit     = request.POST.get('conc_unit', 'nM')
    cell_line     = request.POST.get('cell_line', '').strip() or None
    animal_species = request.POST.get('animal_species', '').strip() or None
    route         = request.POST.get('route', '').strip() or None
    notes         = request.POST.get('notes', '').strip() or None

    from datetime import date as _date
    exp_date = None
    raw_date = request.POST.get('exp_date', '').strip()
    if raw_date:
        try:
            exp_date = _date.fromisoformat(raw_date)
        except ValueError:
            messages.error(request, f"日期格式错误：{raw_date!r}，请使用 YYYY-MM-DD")
            return redirect('upload_experiment')

    created_exp = 0
    created_dp = 0
    skipped_dup = 0

    with transaction.atomic():
        for duplex_id, dp_data in parsed['matched'].items():
            if Experiment.objects.filter(
                duplex_id=duplex_id,
                exp_type=exp_type,
                assay_type=assay_type,
                batch=batch,
            ).exists():
                skipped_dup += 1
                continue

            exp = Experiment.objects.create(
                duplex_id=duplex_id,
                exp_type=exp_type,
                assay_type=assay_type,
                batch=batch,
                exp_date=exp_date,
                cell_line=cell_line,
                animal_species=animal_species,
                route=route,
                notes=notes,
                created_by=request.user.username,
            )
            created_exp += 1

            for row in dp_data['rows']:
                x = row['x']
                for rep_idx, val in enumerate(row['replicates']):
                    if val is None:
                        continue
                    replicate = 'excluded' if row['excluded'][rep_idx] else str(rep_idx + 1)
                    if x_axis_type == 'concentration':
                        DataPoint.objects.create(
                            experiment=exp,
                            concentration_or_dose=x,
                            conc_unit=conc_unit,
                            timepoint=None,
                            readout_type=readout_type,
                            value=val,
                            replicate=replicate,
                        )
                    else:
                        DataPoint.objects.create(
                            experiment=exp,
                            concentration_or_dose=None,
                            conc_unit=None,
                            timepoint=f"Day {x:g}",
                            readout_type=readout_type,
                            value=val,
                            replicate=replicate,
                        )
                    created_dp += 1

    request.session.pop('prism_parsed', None)

    parts = [f"成功导入 {created_exp} 个实验、{created_dp} 个数据点"]
    if skipped_dup:
        parts.append(f"跳过 {skipped_dup} 个重复记录")
    messages.success(request, "；".join(parts))
    return redirect('upload_experiment')
```

- [ ] **Step 5: Run all Prism tests — expect all PASS**

```bash
source venv/bin/activate && python manage.py test app01.tests.PrismParseTests app01.tests.PrismUploadViewTests -v 2 2>&1 | tail -20
```

Expected: `Ran 22 tests in ...s` → `OK`

- [ ] **Step 6: Commit**

```bash
git add app01/views.py bms/urls.py app01/tests.py
git commit -m "feat: add upload_prism_confirm view, URL, and tests"
```

---

### Task 4: Full `upload_prism_preview.html` template

**Files:**
- Modify: `templates/upload_prism_preview.html` (replace placeholder)

- [ ] **Step 1: Write the full template**

Replace the entire content of `templates/upload_prism_preview.html`:

```html
{% extends 'base.html' %}

{% block page_title %} — Prism 数据预览{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">Prism 数据导入预览</span>
  <span class="ds-topbar-spacer"></span>
  <a href="{% url 'upload_experiment' %}" class="ds-btn ds-btn-ghost">← 取消</a>
{% endblock %}

{% block content %}
<div class="ds-form-page">
  <div class="ds-form-card">

    <div class="ds-form-card-title">解析结果</div>
    <div style="font-size:13px;line-height:2;margin-bottom:16px;">
      <div style="color:#15803d;">✓ 识别到 {{ matched_ids|length }} 个 duplex：{{ matched_ids|join:", " }}</div>
      {% if skipped_cols %}
      <div style="color:#b45309;">✗ 跳过 {{ skipped_cols|length }} 列（未匹配）：{{ skipped_cols|join:", " }}</div>
      {% endif %}
      <div style="color:#475569;">X 轴值（{{ x_values|length }} 个）：{{ x_values|join:", " }}</div>
      <div style="color:#475569;">
        预计写入 {{ total_points }} 个数据点{% if excluded_count %}（含 {{ excluded_count }} 个 excluded 标注）{% endif %}
      </div>
    </div>

    {% if warnings %}
    <div style="background:#fef9c3;border-radius:6px;padding:8px 12px;margin-bottom:16px;font-size:12px;color:#854d0e;">
      {% for w in warnings %}<div>⚠ {{ w }}</div>{% endfor %}
    </div>
    {% endif %}

    <div class="ds-form-card-title" style="margin-top:20px;">实验元数据</div>

    <form method="POST" action="{% url 'upload_prism_confirm' %}">
      {% csrf_token %}

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;">

        <div>
          <label class="ds-form-label">实验类型 *</label>
          <select name="exp_type" id="id_exp_type" class="ds-form-control" required onchange="toggleBioFields()">
            {% for val, label in exp_type_choices %}
            <option value="{{ val }}">{{ label }}</option>
            {% endfor %}
          </select>
        </div>

        <div>
          <label class="ds-form-label">Assay 类型 *</label>
          <select name="assay_type" class="ds-form-control" required>
            {% for val, label in assay_type_choices %}
            <option value="{{ val }}">{{ label }}</option>
            {% endfor %}
          </select>
        </div>

        <div>
          <label class="ds-form-label">读数类型 *</label>
          <select name="readout_type" class="ds-form-control" required>
            {% for val, label in readout_type_choices %}
            <option value="{{ val }}">{{ label }}</option>
            {% endfor %}
          </select>
        </div>

        <div>
          <label class="ds-form-label">X 轴含义 *</label>
          <select name="x_axis_type" id="id_x_axis_type" class="ds-form-control" required onchange="toggleConcUnit()">
            <option value="timepoint">时间点（天）</option>
            <option value="concentration">浓度 / 剂量</option>
          </select>
        </div>

        <div id="conc_unit_row" style="display:none;">
          <label class="ds-form-label">浓度单位</label>
          <select name="conc_unit" class="ds-form-control">
            {% for val, label in conc_unit_choices %}
            <option value="{{ val }}">{{ label }}</option>
            {% endfor %}
          </select>
        </div>

        <div>
          <label class="ds-form-label">批次 *</label>
          <input type="text" name="batch" class="ds-form-control" required placeholder="如 Batch-001">
        </div>

        <div>
          <label class="ds-form-label">实验日期</label>
          <input type="date" name="exp_date" class="ds-form-control">
        </div>

        <div id="cell_line_row">
          <label class="ds-form-label">细胞系</label>
          <input type="text" name="cell_line" class="ds-form-control" placeholder="如 HepG2">
        </div>

        <div id="animal_species_row" style="display:none;">
          <label class="ds-form-label">动物种属</label>
          <input type="text" name="animal_species" class="ds-form-control" placeholder="如 mouse">
        </div>

        <div>
          <label class="ds-form-label">给药途径</label>
          <input type="text" name="route" class="ds-form-control" placeholder="如 SC、IV">
        </div>

      </div>

      <div style="margin-bottom:16px;">
        <label class="ds-form-label">备注</label>
        <textarea name="notes" class="ds-form-control" rows="2" style="resize:vertical;"></textarea>
      </div>

      <div style="display:flex;gap:8px;">
        <button type="submit" class="ds-btn ds-btn-primary">确认导入</button>
        <a href="{% url 'upload_experiment' %}" class="ds-btn ds-btn-ghost">取消</a>
      </div>
    </form>

  </div>
</div>

<script>
function toggleBioFields() {
  var t = document.getElementById('id_exp_type').value;
  document.getElementById('cell_line_row').style.display = (t === 'in_vitro') ? '' : 'none';
  document.getElementById('animal_species_row').style.display = (t === 'in_vivo') ? '' : 'none';
}
function toggleConcUnit() {
  var t = document.getElementById('id_x_axis_type').value;
  document.getElementById('conc_unit_row').style.display = (t === 'concentration') ? '' : 'none';
}
</script>
{% endblock %}
```

- [ ] **Step 2: Re-run preview tests to confirm template still passes**

```bash
source venv/bin/activate && python manage.py test app01.tests.PrismUploadViewTests.test_preview_post_valid_csv_renders_preview -v 2 2>&1 | tail -10
```

Expected: `Ran 1 test in ...s` → `OK`

- [ ] **Step 3: Commit**

```bash
git add templates/upload_prism_preview.html
git commit -m "feat: add full upload_prism_preview template with metadata form"
```

---

### Task 5: Add Prism Tab to `upload_experiment.html`

**Files:**
- Modify: `templates/upload_experiment.html`

- [ ] **Step 1: Replace the template**

Replace the full content of `templates/upload_experiment.html`:

```html
{% extends 'base.html' %}

{% block page_title %} — 批量上传实验数据{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">批量上传实验数据</span>
  <span class="ds-topbar-spacer"></span>
  <a href="/seq_list/" class="ds-btn ds-btn-ghost">← 返回</a>
{% endblock %}

{% block content %}
<div class="ds-form-page">
  <div class="ds-form-card">

    {% if messages %}
      {% for m in messages %}
        <div style="padding:8px 12px;margin-bottom:8px;border-radius:6px;font-size:13px;
                    background:{% if m.level_tag == 'success' %}#dcfce7{% elif m.level_tag == 'warning' %}#fef9c3{% else %}#fee2e2{% endif %};
                    color:{% if m.level_tag == 'success' %}#15803d{% elif m.level_tag == 'warning' %}#854d0e{% else %}#b91c1c{% endif %};">
          {{ m }}
        </div>
      {% endfor %}
    {% endif %}

    <!-- Tab buttons -->
    <div style="display:flex;gap:0;margin-bottom:20px;border-bottom:1px solid #e2e8f0;">
      <button id="tab-csv-btn" onclick="switchTab('csv')"
              style="padding:8px 18px;font-size:13px;cursor:pointer;border:none;background:none;
                     border-bottom:2px solid #3b82f6;color:#3b82f6;font-weight:600;">
        CSV 格式
      </button>
      <button id="tab-prism-btn" onclick="switchTab('prism')"
              style="padding:8px 18px;font-size:13px;cursor:pointer;border:none;background:none;
                     border-bottom:2px solid transparent;color:#64748b;">
        Prism 文件导入
      </button>
    </div>

    <!-- Tab 1: existing CSV upload -->
    <div id="tab-csv">
      <div class="ds-form-card-title">CSV 文件上传</div>
      <div style="font-size:12px;color:#475569;margin-bottom:14px;line-height:1.6;">
        <strong>支持两种格式：</strong>
        <br>1. <strong>duplex_id 格式</strong>：CSV 含 <code>duplex_id</code> 列，直接指定。
        <br>2. <strong>modify_seq 格式</strong>：CSV 含 <code>modify_seq</code> 列，AS 和 SS 上下两行为一组，系统自动匹配 <code>duplex_id</code>。
        <br>必填列：<code>exp_type</code>、<code>assay_type</code>、<code>batch</code>、<code>readout_type</code>、<code>value</code>。
      </div>
      <div style="margin-bottom:14px;">
        <a href="{% url 'download_experiment_template' %}" class="ds-btn ds-btn-ghost" style="font-size:12px;">↓ 下载 CSV 模板</a>
      </div>
      <form method="POST" enctype="multipart/form-data">
        {% csrf_token %}
        <div style="margin-bottom:14px;">
          <input type="file" name="csv_file" class="ds-form-control" accept=".csv" required>
        </div>
        <button type="submit" class="ds-btn ds-btn-primary">上传</button>
      </form>
    </div>

    <!-- Tab 2: Prism file upload -->
    <div id="tab-prism" style="display:none;">
      <div class="ds-form-card-title">Prism 文件导入</div>
      <div style="font-size:12px;color:#475569;margin-bottom:14px;line-height:1.6;">
        支持 GraphPad Prism 11 导出的 <strong>.csv</strong> 或 <strong>.txt</strong>（Tab 分隔）格式。
        <br>第一行为 duplex ID 列标题（每个 duplex 连续 3 列对应三个重复），第一列为 X 轴值（天数或浓度）。
        <br>不匹配的列将自动跳过，上传后可在预览页确认并填写实验元数据。
      </div>
      <form method="POST" action="{% url 'upload_prism_preview' %}" enctype="multipart/form-data">
        {% csrf_token %}
        <div style="margin-bottom:14px;">
          <input type="file" name="prism_file" class="ds-form-control" accept=".csv,.txt" required>
        </div>
        <button type="submit" class="ds-btn ds-btn-primary">解析并预览</button>
      </form>
    </div>

  </div>
</div>

<script>
function switchTab(tab) {
  var csvActive = (tab === 'csv');
  document.getElementById('tab-csv').style.display = csvActive ? '' : 'none';
  document.getElementById('tab-prism').style.display = csvActive ? 'none' : '';
  document.getElementById('tab-csv-btn').style.borderBottomColor = csvActive ? '#3b82f6' : 'transparent';
  document.getElementById('tab-csv-btn').style.color = csvActive ? '#3b82f6' : '#64748b';
  document.getElementById('tab-csv-btn').style.fontWeight = csvActive ? '600' : 'normal';
  document.getElementById('tab-prism-btn').style.borderBottomColor = csvActive ? 'transparent' : '#3b82f6';
  document.getElementById('tab-prism-btn').style.color = csvActive ? '#64748b' : '#3b82f6';
  document.getElementById('tab-prism-btn').style.fontWeight = csvActive ? 'normal' : '600';
}
</script>
{% endblock %}
```

- [ ] **Step 2: Run the full test suite**

```bash
source venv/bin/activate && python manage.py test app01 -v 1 2>&1 | tail -10
```

Expected: All existing tests still pass, `OK`

- [ ] **Step 3: Commit**

```bash
git add templates/upload_experiment.html
git commit -m "feat: add Prism Tab to upload_experiment page"
```

---

### Task 6: Manual smoke test

- [ ] **Step 1: Start server**

```bash
source venv/bin/activate && python manage.py runserver
```

- [ ] **Step 2: Verify Tab switching**

Navigate to `http://127.0.0.1:8000/upload_experiment/`. Confirm two tabs render. Click "Prism 文件导入" — tab switches without page reload.

- [ ] **Step 3: Upload sample file**

Upload `/Users/gutou/Desktop/Data_tmp_Prism/Data 2.csv`. Confirm preview page shows:
- Identified duplex IDs (or "没有可识别" if none match DB)
- Skipped columns listed
- Metadata form with all dropdowns populated

- [ ] **Step 4: Complete import**

Fill in batch name, select exp_type/assay_type/readout_type/x_axis_type, click "确认导入". Confirm flash success message and redirect to upload page.

- [ ] **Step 5: Verify in experiment_detail**

Navigate to `http://127.0.0.1:8000/experiment/<one_of_the_duplex_ids>/` — confirm Experiment and DataPoints appear.
