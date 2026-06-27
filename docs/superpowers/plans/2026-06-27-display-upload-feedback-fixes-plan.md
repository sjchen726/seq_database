# Display & Upload Feedback Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix a runtime crash on dual-segment sequence display, improve control group detection, and surface skipped-datapoint counts to the user on upload.

**Architecture:** All three fixes are isolated changes within `app01/views.py`. Fix 1 adds a module-level constant. Fix 2 replaces a constant + function. Fix 3 adds a counter variable and one line to the success message. Tests go in `app01/tests.py`.

**Tech Stack:** Django 5.1, Python 3.10, MySQL. Test runner: `python manage.py test app01`.

---

## File Map

| File | What changes |
|------|-------------|
| `app01/views.py` | Define `_SEP_TOKEN` (line ~258); replace `_CONTROL_KEYWORDS` + `_is_control_arm` (lines 770–774); add `n_skipped_dps` counter and message (lines ~2351, ~2576) |
| `app01/tests.py` | Add 3 test classes: `SepTokenTest`, `IsControlArmTest`, `SkippedDpCountTest` |

---

### Task 1: Fix `_SEP_TOKEN` undefined crash

**Files:**
- Modify: `app01/views.py:258` (add constant before `get_modify_seq_colored`)
- Test: `app01/tests.py` (add `SepTokenTest` class)

**Background:** `get_modify_seq_colored()` at line 276 calls `_SEP_TOKEN.copy()` to insert separator tokens between the two parts of a dual-segment sequence (one that contains an embedded linker like `----`). `_SEP_TOKEN` is never defined, causing `NameError` at runtime whenever a dual-segment sequence is displayed. The token just needs `type='SEP'`; other fields mirror the structure of other tokens in the list.

- [ ] **Step 1: Write the failing test**

In `app01/tests.py`, add this class after the existing imports:

```python
class SepTokenTest(TestCase):
    def test_get_modify_seq_colored_dual_segment_no_crash(self):
        """Sequences with embedded 4+ dash linkers must not raise NameError."""
        from app01.views import get_modify_seq_colored
        # '----' triggers the embedded-linker path (4+ consecutive dashes)
        tokens = get_modify_seq_colored('mAmG----mUmA', 'AS', 'AS')
        types = [t['type'] for t in tokens]
        self.assertIn('SEP', types)
        self.assertEqual(types.count('SEP'), 2)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source venv/bin/activate
python manage.py test app01.tests.SepTokenTest -v 2
```

Expected: FAIL with `NameError: name '_SEP_TOKEN' is not defined`

- [ ] **Step 3: Define `_SEP_TOKEN` in `views.py`**

In `app01/views.py`, insert these lines immediately before the `def get_modify_seq_colored(...)` function at line 259 (after the blank line following `build_duplex_groups` or whichever function precedes it):

```python
_SEP_TOKEN = {
    'type': 'SEP',
    'char': '',
    'count': '',
    'is_combo': False,
    'delivery_label': None,
    'delivery_color': None,
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python manage.py test app01.tests.SepTokenTest -v 2
```

Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "fix: define _SEP_TOKEN constant to prevent NameError on dual-segment sequence display"
```

---

### Task 2: Fix control group detection too narrow

**Files:**
- Modify: `app01/views.py:770–774` (replace `_CONTROL_KEYWORDS` + `_is_control_arm`)
- Test: `app01/tests.py` (add `IsControlArmTest` class)

**Background:** `_is_control_arm(dose_info)` does a single exact lowercase match against a 6-word set. It misses "Control Group", "Saline group", "Negative Control" etc. The fix uses a two-pass check: exact match for single-word terms, then substring check for common multi-word phrases.

- [ ] **Step 1: Write the failing tests**

Add this class in `app01/tests.py`:

```python
class IsControlArmTest(TestCase):
    def _check(self, s):
        from app01.views import _is_control_arm
        return _is_control_arm(s)

    # These should all be True
    def test_exact_saline(self):
        self.assertTrue(self._check('saline'))

    def test_exact_pbs(self):
        self.assertTrue(self._check('PBS'))

    def test_exact_control(self):
        self.assertTrue(self._check('control'))

    def test_exact_sal(self):
        self.assertTrue(self._check('sal'))

    def test_exact_ctrl(self):
        self.assertTrue(self._check('ctrl'))

    def test_substring_control_group(self):
        self.assertTrue(self._check('Control Group'))

    def test_substring_saline_group(self):
        self.assertTrue(self._check('Saline group'))

    def test_substring_negative_control(self):
        self.assertTrue(self._check('Negative Control'))

    def test_substring_pbs_vehicle(self):
        self.assertTrue(self._check('PBS vehicle'))

    # These should all be False
    def test_treatment_arm(self):
        self.assertFalse(self._check('BPR123'))

    def test_dose_string(self):
        self.assertFalse(self._check('1mg/kg'))

    def test_neg_substring_not_match(self):
        # 'neg' is exact-only; 'BPR-neg123' should NOT match
        self.assertFalse(self._check('BPR-neg123'))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python manage.py test app01.tests.IsControlArmTest -v 2
```

Expected: Several FAILs — the substring tests (`test_substring_control_group`, etc.) will fail because the current code uses exact matching only. `test_exact_sal` and `test_exact_ctrl` will also fail (not in the current keyword set).

- [ ] **Step 3: Replace `_CONTROL_KEYWORDS` and `_is_control_arm` in `views.py`**

Find lines 770–774 in `app01/views.py`. They currently read:

```python
_CONTROL_KEYWORDS = {'saline', 'pbs', 'vehicle', 'control', 'nc', 'neg'}


def _is_control_arm(dose_info: str) -> bool:
    return dose_info.lower().strip() in _CONTROL_KEYWORDS
```

Replace with:

```python
_CONTROL_KEYWORDS_EXACT = {
    'saline', 'pbs', 'vehicle', 'control', 'nc', 'neg',
    'sal', 'blank', 'mock', 'ctrl', 'placebo',
}
_CONTROL_KEYWORDS_SUBSTR = {'control', 'saline', 'vehicle', 'negative', 'placebo'}


def _is_control_arm(dose_info: str) -> bool:
    s = dose_info.lower().strip()
    if s in _CONTROL_KEYWORDS_EXACT:
        return True
    return any(kw in s for kw in _CONTROL_KEYWORDS_SUBSTR)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python manage.py test app01.tests.IsControlArmTest -v 2
```

Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "fix: expand control group detection to match common multi-word naming variants"
```

---

### Task 3: Surface skipped datapoint count in upload success message

**Files:**
- Modify: `app01/views.py` — two locations inside `smart_upload_confirm_view`:
  - Near line 2351: add `n_skipped_dps` counter and increment on skip
  - Near line 2574: append skip count to `parts` list before building message
- Test: `app01/tests.py` (add `SkippedDpCountTest` class)

**Background:** When `dp_conflicts` contains skip=True entries, matching datapoints are silently discarded at line 2360 (`if fp in skip_fps: continue`). The user sees "数据已上传" with no indication that data was filtered. The fix adds a counter and appends it to the success message parts.

**How the confirm view works (needed for test setup):**
- Session key `smart_preview` holds `{'invitro': {'batch_label': ..., 'assay_name': ..., 'experiments': [{'compound_id': ..., 'datapoints': [...]}], ...}, ...}`
- Session key `pipeline_result` holds `{'dedup_report': {'dp_conflicts': [...], 'exp_conflicts': []}, 'strand_diffs': [], 'errors': [], ...}`
- Session key `upload_meta` holds `{'batch_label': ..., 'assay_name': ..., 'target_name': ..., ...}`
- POST to `/upload/smart/confirm/` with `{}` (no form fields needed when target_name is in upload_meta)
- On success: redirects to `smart_upload` with a Django messages.success entry
- On error: renders `smart_upload.html` with status 200

A `dp_conflict` entry matches a datapoint when `compound_id`, `batch_label`, `assay_name` all match AND `skip=True`. The fingerprint tuple used for matching is `(round(x_value,4), replicate, round(value,4), readout_type, is_control)`.

- [ ] **Step 1: Write the failing test**

Add this class in `app01/tests.py`:

```python
class SkippedDpCountTest(TestCase):
    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='skip_test', password='pass',
            user_type='sub_admin',
            module_permissions='upload,data,compound,batch',
        )
        self.client.login(username='skip_test', password='pass')
        Compound.objects.create(compound_id='BPR_SKIP01', target_name='')

    def _make_session(self):
        """Session with 2 datapoints where 1 has a matching skip=True dp_conflict."""
        dp_skip = {'x_value': 1.0, 'x_type': 'concentration', 'replicate': '1',
                   'value': 50.0, 'readout_type': 'IC50', 'is_control': False}
        dp_keep = {'x_value': 10.0, 'x_type': 'concentration', 'replicate': '1',
                   'value': 80.0, 'readout_type': 'IC50', 'is_control': False}
        preview = {
            'project_code': 'SKIP',
            'file_detections': [],
            'invitro': {
                'batch_label': 'SKIP_BATCH',
                'assay_name': 'IC50_Assay',
                'cell_line': '',
                'notes': '',
                'experiments': [
                    {
                        'compound_id': 'BPR_SKIP01',
                        'exp_type': 'in_vitro',
                        'datapoints': [dp_skip, dp_keep],
                        'summary': None,
                    }
                ],
                'strand_map': {},
                'new_compounds': [],
            },
            'invivo_groups': [],
            'source_files': [],
            'attachment_files': [],
            'errors': [],
            'has_no_seq': True,
        }
        pipeline_result = {
            'errors': [], 'warnings': [], 'remap_log': [],
            'strand_diffs': [],
            'dedup_report': {
                'exp_conflicts': [],
                'dp_conflicts': [
                    {
                        'compound_id': 'BPR_SKIP01',
                        'batch_label': 'SKIP_BATCH',
                        'assay_name': 'IC50_Assay',
                        'skip': True,
                        'datapoints': [
                            # Same fingerprint as dp_skip
                            {'x_value': 1.0, 'replicate': '1', 'value': 50.0,
                             'readout_type': 'IC50', 'is_control': False},
                        ],
                    }
                ],
            },
        }
        session = self.client.session
        session['smart_preview'] = preview
        session['pipeline_result'] = pipeline_result
        session['upload_meta'] = {
            'batch_label': 'SKIP_BATCH',
            'assay_name': 'IC50_Assay',
            'exp_date': None,
            'target_name': 'FASN',
            'source_batch': '',
            'attach_vitro': False,
            'attach_vivo': False,
        }
        session.save()

    def test_skipped_dp_count_in_success_message(self):
        """One of two datapoints is skipped; message must say '跳过 1 个重复数据点'."""
        self._make_session()
        resp = self.client.post('/upload/smart/confirm/', {}, follow=True)
        self.assertEqual(resp.status_code, 200)
        # Only the non-skipped datapoint should be written
        from app01.models import DataPoint
        self.assertEqual(
            DataPoint.objects.filter(experiment__batch_label='SKIP_BATCH').count(), 1
        )
        # Success message must mention the skip count
        self.assertContains(resp, '跳过 1 个重复数据点')
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test app01.tests.SkippedDpCountTest -v 2
```

Expected: FAIL — `assertContains(resp, '跳过 1 个重复数据点')` fails because the message is not currently generated. (The DataPoint count assertion should pass since the skip mechanism already works.)

- [ ] **Step 3: Add `n_skipped_dps` counter in `views.py`**

**Change A** — Find the block near line 2351 that starts the datapoint loop. It currently looks like:

```python
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
```

Add `n_skipped_dps = 0` before the invitro loop (search for the `invitro_errors = []` declaration near line 2217 and add the new variable right below it):

```python
invitro_errors = []
n_skipped_dps = 0
```

Then change the `if fp in skip_fps: continue` line to:

```python
                        if fp in skip_fps:
                            n_skipped_dps += 1
                            continue
```

**Change B** — Find the `parts = []` block near line 2574. It currently ends with:

```python
    if n_attachments:
        parts.append(f'{n_attachments} 个附件')
```

Add the skip-count line immediately after:

```python
    if n_attachments:
        parts.append(f'{n_attachments} 个附件')
    if n_skipped_dps:
        parts.append(f'跳过 {n_skipped_dps} 个重复数据点（已存在于数据库）')
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python manage.py test app01.tests.SkippedDpCountTest -v 2
```

Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "feat: report skipped duplicate datapoint count in upload success message"
```

---

### Task 4: Full test suite and lint check

**Files:** None modified — verification only.

- [ ] **Step 1: Run full test suite**

```bash
source venv/bin/activate
python manage.py test app01 -v 1
```

Expected: All tests pass. If any test fails, fix it before proceeding.

- [ ] **Step 2: Run ruff lint**

```bash
ruff check app01/views.py app01/tests.py --select W293,E401
```

Expected: `Found 0 errors.` If any are found, run `ruff check --fix app01/views.py app01/tests.py --select W293,E401` and re-run the test suite.

- [ ] **Step 3: Commit lint fixes if needed**

Only if ruff reported errors:

```bash
git add app01/views.py app01/tests.py
git commit -m "chore: fix ruff lint violations"
```
