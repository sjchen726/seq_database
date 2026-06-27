# Performance, Security & Data Correctness Fixes — Design Spec

**Date:** 2026-06-27
**Scope:** Three independent fixes in `app01/models.py`, `app01/views.py`, and `app01/upload_pipeline.py`

---

## 1. Background

Post-audit of the project identified three remaining issues not addressed in prior fix rounds:

1. **Missing `batch_label` index** — `Experiment.batch_label` is heavily filtered but lacks a database index, causing slow queries on compound list, dedup detection, and batch operations.
2. **Attachment endpoints missing project permission** — `attachment_download` and `attachment_preview` only check `@login_required`; any logged-in user can access attachments from projects they have no access to.
3. **`parse_summary_csv` negative index silent corruption** — When `Dose (nM)` or `IC50` columns appear near the left edge of the header, computed relative column indices become negative, causing Python to silently read the wrong column instead of raising an error.

All three fixes are independent. Fix 1 requires a migration. Fixes 2 and 3 are pure code changes with no schema changes.

---

## 2. Fix Specifications

### Fix 1 — Add `db_index` to `Experiment.batch_label`

**Location:** `app01/models.py`, line 170

**Root cause:** `batch_label = models.CharField(max_length=64, blank=True)` has no `db_index=True`. The field is used as a filter in:
- Compound list pagination (`batch_label` grouping)
- Dedup detection (`Experiment.objects.filter(batch_label=...)`)
- Batch delete operations

**Fix:**

```python
batch_label = models.CharField(max_length=64, blank=True, db_index=True)
```

**Migration:** Generate with `python manage.py makemigrations app01 --name add_batch_label_index`. MySQL will use `ALTER TABLE ... ADD INDEX` which is online DDL and safe on production.

---

### Fix 2 — Add Project Permission Check to Attachment Endpoints

**Location:** `app01/views.py`, lines 2625–2631 (`attachment_download`) and 2633–2692 (`attachment_preview`)

**Root cause:** Both views use `get_object_or_404(ExperimentAttachment, pk=pk)` without any project-level access check. The permission model (`_get_permitted_projects`) returns `None` for superadmin/superuser (unrestricted) or a list of allowed project codes for `sub_admin` users. The attachment's project can be derived via `att.experiment.compound.project`.

**Fix for `attachment_download`:**

```python
@login_required
def attachment_download(request, pk):
    att = get_object_or_404(
        ExperimentAttachment.objects.select_related('experiment__compound'), pk=pk
    )
    permitted = _get_permitted_projects(request.user)
    if permitted is not None and att.experiment.compound.project not in permitted:
        raise Http404
    if not att.file:
        raise Http404
    filename = os.path.basename(att.file.name)
    return FileResponse(att.file.open('rb'), as_attachment=True, filename=filename)
```

**Fix for `attachment_preview`:** Apply the same permission check at the top of the view, immediately after fetching `att`:

```python
@login_required
def attachment_preview(request, pk):
    att = get_object_or_404(
        ExperimentAttachment.objects.select_related('experiment__compound'), pk=pk
    )
    permitted = _get_permitted_projects(request.user)
    if permitted is not None and att.experiment.compound.project not in permitted:
        return JsonResponse({'error': 'forbidden'}, status=403)
    # ... rest of existing logic unchanged ...
```

Note: `attachment_download` raises `Http404` (disguises the attachment's existence). `attachment_preview` returns 403 JSON (client-side preview UI can display an access error). Both use `select_related('experiment__compound')` to avoid an extra query.

---

### Fix 3 — Guard Against Negative Column Indices in `parse_summary_csv`

**Location:** `app01/upload_pipeline.py`, lines 222–233

**Root cause:** After locating `dose_col` by name, the code computes `id_col = dose_col - 1`. If `dose_col == 0`, `id_col = -1`, which is a valid Python list index (last element) and silently reads the wrong column. Similarly, `r_id_col = ic50_col - 3` becomes negative if `ic50_col < 3`.

**Fix:** Add bounds validation immediately after computing the derived indices:

```python
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
r_id_col = ic50_col - 3
if r_id_col < 0:
    raise ValueError(
        "汇总表格式错误：'IC50' 列前缺少足够的映射列（需要至少 3 列）"
    )
r_name_col = ic50_col - 2
r_maxkd_col = ic50_col - 1
r_rank_col = ic50_col + 1
```

Normal files are unaffected. Malformed files now fail fast with a message the user can act on instead of silently producing wrong data.

---

## 3. Files Changed

| File | Change |
|------|--------|
| `app01/models.py` | Fix 1: add `db_index=True` to `Experiment.batch_label` |
| `app01/migrations/0014_experiment_batchlabel_index.py` | Fix 1: generated migration |
| `app01/views.py` | Fix 2: add `select_related` + permission check to both attachment endpoints |
| `app01/upload_pipeline.py` | Fix 3: add negative-index guards after computing `id_col` and `r_id_col` |

---

## 4. Testing

| Fix | Test scenario |
|-----|---------------|
| Fix 1 | Run `python manage.py migrate --run-syncdb` and assert no errors. Assert `Experiment._meta.get_field('batch_label').db_index is True`. |
| Fix 2 (download) | Create attachment in project `'P1'`. Login as user with `permissions_project='P2'`. GET `/attachments/<pk>/download/`. Assert 404. Login as user with `permissions_project='P1'`. Assert 200. |
| Fix 2 (preview) | Same setup. GET `/attachments/<pk>/preview/`. Assert 403 for wrong project, 200 for correct. |
| Fix 3 | Pass a CSV where `Dose (nM)` is the first column (`id_col` would be `-1`). Assert `ValueError` is raised with message containing `'Dose (nM)'`. |

---

## 5. Out of Scope

- Module query caching (`DeliveryModule`/`SeqModule` per render) — separate performance task
- `detect_invivo_file_type` heuristic improvement — requires domain knowledge of edge cases
- Body weight file auto-prefix confirmation — UX flow change, deferred
