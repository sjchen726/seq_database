# Performance, Security & Data Correctness Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a database index to `Experiment.batch_label`, enforce project-level access control on attachment endpoints, and prevent silent column-index corruption in `parse_summary_csv`.

**Architecture:** Three independent fixes: one migration (models.py), one view security patch (views.py), one input validation patch (upload_pipeline.py). No cross-task dependencies — each task can be reviewed and committed independently.

**Tech Stack:** Django 5.1, Python 3.10, MySQL. Tests in `app01/tests.py`. Run: `python manage.py test app01 --keepdb -v 1`.

---

## File Map

| File | Change |
|------|--------|
| `app01/models.py` | Add `db_index=True` to `Experiment.batch_label` |
| `app01/migrations/0014_add_batch_label_index.py` | Auto-generated migration |
| `app01/views.py` | Add `select_related` + project permission check to `attachment_download` and `attachment_preview` |
| `app01/upload_pipeline.py` | Add bounds validation after computing `id_col` and `r_id_col` |
| `app01/tests.py` | Add 3 test classes |

---

### Task 1: Add `db_index` to `Experiment.batch_label`

**Files:**
- Modify: `app01/models.py:170`
- Create: `app01/migrations/0014_add_batch_label_index.py` (auto-generated)
- Test: `app01/tests.py`

**Background:** `Experiment.batch_label` is filtered on every compound list page, dedup detection, and batch delete — but has no index. Adding `db_index=True` creates a MySQL B-tree index on the column.

- [ ] **Step 1: Write the failing test**

Add this class to `app01/tests.py`:

```python
class BatchLabelIndexTest(TestCase):
    def test_batch_label_has_db_index(self):
        from app01.models import Experiment
        field = Experiment._meta.get_field('batch_label')
        self.assertTrue(field.db_index, "Experiment.batch_label must have db_index=True")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source venv/bin/activate
python manage.py test app01.tests.BatchLabelIndexTest --keepdb -v 2
```

Expected: FAIL — `False is not true : Experiment.batch_label must have db_index=True`

- [ ] **Step 3: Add `db_index=True` to the model**

In `app01/models.py`, find line 170:

```python
    batch_label = models.CharField(max_length=64, blank=True)
```

Change to:

```python
    batch_label = models.CharField(max_length=64, blank=True, db_index=True)
```

- [ ] **Step 4: Generate the migration**

```bash
python manage.py makemigrations app01 --name add_batch_label_index
```

Expected output: `Migrations for 'app01': app01/migrations/0014_add_batch_label_index.py`

- [ ] **Step 5: Apply the migration**

```bash
python manage.py migrate app01
```

Expected: `Applying app01.0014_add_batch_label_index... OK`

- [ ] **Step 6: Run test to verify it passes**

```bash
python manage.py test app01.tests.BatchLabelIndexTest --keepdb -v 2
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app01/models.py app01/migrations/0014_add_batch_label_index.py app01/tests.py
git commit -m "perf: add db_index to Experiment.batch_label"
```

---

### Task 2: Add project permission check to attachment endpoints

**Files:**
- Modify: `app01/views.py:2625–2692`
- Test: `app01/tests.py`

**Background:** `attachment_download` and `attachment_preview` only check `@login_required`. Any logged-in user can fetch attachments from experiments in projects they have no access to by guessing the pk. The project permission model is already in place: `_get_permitted_projects(user)` returns `None` for unrestricted users (superadmin/superuser) or a list of allowed project codes for `sub_admin` users.

The permission check adds `select_related('experiment__compound')` to avoid extra queries and checks `att.experiment.compound.project` against the permitted list. Compounds with `project=''` (no project assigned) are always accessible — this preserves backward compatibility for unclassified data.

**Important:** The existing `AttachmentDownloadTest` creates a compound with `project=''` and a user with `user_type='admin'`. The `admin` user_type goes through the same project-list path, but since `compound.project == ''` triggers the "skip check" rule, the existing tests will still pass.

- [ ] **Step 1: Write the failing tests**

Add this class to `app01/tests.py`:

```python
class AttachmentProjectPermissionTest(TestCase):
    def setUp(self):
        from django.core.files.base import ContentFile
        # Compound in project P1
        self.compound = Compound.objects.create(compound_id='BPR_PERMTEST01', project='P1')
        exp = Experiment.objects.create(
            compound=self.compound, exp_type='in_vitro',
            assay_name='perm_test', batch_label='PERM1',
        )
        self.att = ExperimentAttachment(experiment=exp, label='perm_test.csv')
        self.att.file.save('perm_test.csv', ContentFile(b'a,b\n1,2\n'), save=True)

        # User with access to P1
        self.user_p1 = LmsUser.objects.create_user(
            username='perm_p1', password='pass',
            user_type='sub_admin', permissions_project='P1',
            module_permissions='data',
        )
        # User with access to P2 only (not P1)
        self.user_p2 = LmsUser.objects.create_user(
            username='perm_p2', password='pass',
            user_type='sub_admin', permissions_project='P2',
            module_permissions='data',
        )

    def tearDown(self):
        if self.att.file:
            self.att.file.delete(save=False)

    def test_download_forbidden_for_wrong_project(self):
        self.client.login(username='perm_p2', password='pass')
        resp = self.client.get(f'/attachments/{self.att.pk}/download/')
        self.assertEqual(resp.status_code, 404)

    def test_download_allowed_for_correct_project(self):
        self.client.login(username='perm_p1', password='pass')
        resp = self.client.get(f'/attachments/{self.att.pk}/download/')
        self.assertEqual(resp.status_code, 200)

    def test_preview_forbidden_for_wrong_project(self):
        self.client.login(username='perm_p2', password='pass')
        resp = self.client.get(f'/attachments/{self.att.pk}/preview/')
        self.assertEqual(resp.status_code, 403)

    def test_preview_allowed_for_correct_project(self):
        self.client.login(username='perm_p1', password='pass')
        resp = self.client.get(f'/attachments/{self.att.pk}/preview/')
        self.assertEqual(resp.status_code, 200)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python manage.py test app01.tests.AttachmentProjectPermissionTest --keepdb -v 2
```

Expected: All 4 FAIL — permission checks do not exist yet, so both P1 and P2 users get 200.

- [ ] **Step 3: Update `attachment_download` in `views.py`**

Find `attachment_download` (lines 2625–2631). Replace the entire function body:

```python
@login_required
def attachment_download(request, pk):
    att = get_object_or_404(
        ExperimentAttachment.objects.select_related('experiment__compound'), pk=pk
    )
    permitted = _get_permitted_projects(request.user)
    compound_project = att.experiment.compound.project
    if permitted is not None and compound_project and compound_project not in permitted:
        raise Http404
    if not att.file:
        raise Http404
    filename = os.path.basename(att.file.name)
    return FileResponse(att.file.open('rb'), as_attachment=True, filename=filename)
```

- [ ] **Step 4: Update `attachment_preview` in `views.py`**

Find `attachment_preview` (line 2633). The function currently starts with:

```python
@login_required
def attachment_preview(request, pk):
    """Return first 50 rows of a CSV attachment as JSON for inline preview.
    ...
    """
    import itertools
    import csv
    from io import StringIO
    att = get_object_or_404(ExperimentAttachment, pk=pk)
    if not att.file:
        return JsonResponse({'headers': [], 'rows': []}, status=404)
```

Replace those lines with:

```python
@login_required
def attachment_preview(request, pk):
    """Return first 50 rows of a CSV attachment as JSON for inline preview.

    When the CSV has many duplicate column headers (multi-animal body-weight
    format), automatically aggregates same-named columns into their mean so the
    preview is readable without horizontal scrolling.
    """
    import itertools
    import csv
    from io import StringIO
    att = get_object_or_404(
        ExperimentAttachment.objects.select_related('experiment__compound'), pk=pk
    )
    permitted = _get_permitted_projects(request.user)
    compound_project = att.experiment.compound.project
    if permitted is not None and compound_project and compound_project not in permitted:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if not att.file:
        return JsonResponse({'headers': [], 'rows': []}, status=404)
```

Leave all remaining lines of `attachment_preview` (the CSV parsing logic) exactly as-is.

- [ ] **Step 5: Run tests to verify they pass**

```bash
python manage.py test app01.tests.AttachmentProjectPermissionTest --keepdb -v 2
```

Expected: All 4 PASS.

- [ ] **Step 6: Verify existing attachment tests still pass**

```bash
python manage.py test app01.tests.AttachmentDownloadTest --keepdb -v 2
```

Expected: All 3 existing tests PASS (compound project is `''`, so the permission check is skipped).

- [ ] **Step 7: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "fix: enforce project permission check on attachment download and preview endpoints"
```

---

### Task 3: Guard against negative column indices in `parse_summary_csv`

**Files:**
- Modify: `app01/upload_pipeline.py:222–233`
- Test: `app01/tests.py`

**Background:** `parse_summary_csv` locates `Dose (nM)` and `IC50` by name, then computes sibling columns by fixed offsets (`dose_col - 1`, `ic50_col - 3`, etc.). If `dose_col == 0` or `ic50_col < 3`, these become negative indices — valid Python, but silently reading the wrong column. The fix adds two explicit bounds checks immediately after computing the indices.

- [ ] **Step 1: Write the failing tests**

Add this class to `app01/tests.py`:

```python
class ParseSummaryCsvBoundsTest(TestCase):
    def _make_file(self, content: str):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile('summary.csv', content.encode('utf-8'))

    def test_dose_col_first_raises_valueerror(self):
        """Dose (nM) as first column → id_col would be -1 → must raise ValueError."""
        from app01.upload_pipeline import parse_summary_csv
        # Dose (nM) is column 0 — no room for the siRNA ID column to the left
        content = (
            'Dose (nM),A,B,Mean,,siRNA,BPR_ID,MaxKD,IC50 (nM),Rank\n'
            '0.1,50,52,51,,siRNA-1,BPR_X01,0.8,0.5,1\n'
        )
        f = self._make_file(content)
        with self.assertRaises(ValueError) as cm:
            parse_summary_csv(f)
        self.assertIn('Dose (nM)', str(cm.exception))

    def test_ic50_col_too_early_raises_valueerror(self):
        """IC50 in column 1 → r_id_col would be -2 → must raise ValueError."""
        from app01.upload_pipeline import parse_summary_csv
        content = (
            'siRNA,IC50 (nM),Dose (nM),A,B,Mean\n'
            'siRNA-1,0.5,0.1,50,52,51\n'
        )
        f = self._make_file(content)
        with self.assertRaises(ValueError) as cm:
            parse_summary_csv(f)
        self.assertIn('IC50', str(cm.exception))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python manage.py test app01.tests.ParseSummaryCsvBoundsTest --keepdb -v 2
```

Expected: Both FAIL — currently no bounds check, the negative indices are silently used.

- [ ] **Step 3: Add bounds validation to `parse_summary_csv`**

In `app01/upload_pipeline.py`, find lines 222–233:

```python
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
```

Replace with:

```python
    # Detect column positions from header row
    dose_col = next(j for j, c in enumerate(header) if c.strip() == 'Dose (nM)')
    id_col = dose_col - 1
    if id_col < 0:
        raise ValueError(
            "汇总表格式错误：'Dose (nM)' 列前缺少 siRNA 标识列"
        )
    a_col = dose_col + 1
    b_col = dose_col + 2
    mean_col = dose_col + 3

    ic50_col = next(j for j, c in enumerate(header) if 'IC50' in c)
    r_id_col = ic50_col - 3    # siRNA label column in right table
    if r_id_col < 0:
        raise ValueError(
            "汇总表格式错误：'IC50' 列前缺少足够的映射列（需要至少 3 列）"
        )
    r_name_col = ic50_col - 2  # BPR compound ID
    r_maxkd_col = ic50_col - 1
    r_rank_col = ic50_col + 1
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python manage.py test app01.tests.ParseSummaryCsvBoundsTest --keepdb -v 2
```

Expected: Both PASS.

- [ ] **Step 5: Commit**

```bash
git add app01/upload_pipeline.py app01/tests.py
git commit -m "fix: raise ValueError on negative column indices in parse_summary_csv"
```

---

### Task 4: Full test suite and lint check

**Files:** None modified — verification only.

- [ ] **Step 1: Run full test suite**

```bash
source venv/bin/activate
python manage.py test app01 --keepdb -v 1
```

Expected: All tests pass. If any fail, fix them before proceeding.

- [ ] **Step 2: Run ruff lint**

```bash
ruff check app01/views.py app01/tests.py app01/upload_pipeline.py app01/models.py --select W293,E401
```

Expected: `All checks passed!`. If violations found, run:

```bash
ruff check --fix app01/views.py app01/tests.py app01/upload_pipeline.py app01/models.py --select W293,E401
```

Then re-run the test suite to confirm nothing broke.

- [ ] **Step 3: Commit lint fixes if needed**

Only if ruff reported errors:

```bash
git add app01/views.py app01/tests.py app01/upload_pipeline.py app01/models.py
git commit -m "chore: fix ruff lint violations"
```
