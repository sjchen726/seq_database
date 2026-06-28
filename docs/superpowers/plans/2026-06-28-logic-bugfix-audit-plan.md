# Logic Bug Audit Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 8 logic bugs found in code audit: data loss in upload pipeline, wrong chart data, access control leak, and storage isolation gap.

**Architecture:** All fixes are surgical 1–5 line changes across `app01/views.py` and `app01/upload_pipeline.py`. No migrations, no template changes, no model changes.

**Tech Stack:** Django 5.1, Python 3.10, MySQL.

---

## File Map

| File | Tasks |
|------|-------|
| `app01/views.py` | Tasks 1–4, 6, 7, 8 |
| `app01/upload_pipeline.py` | Task 5 |

---

### Task 1: Remove session cleanup from confirm-page validation error path

**Files:**
- Modify: `app01/views.py:2230–2232`

**Background:** When the confirm form has validation errors (e.g., missing `time_unit`), `_cleanup_upload_session()` is called before re-rendering. This deletes the session and all temp files. If the user fixes the error and resubmits, the session is empty and they are silently redirected back to the upload start, losing all uploaded files.

The current block at lines 2230–2232:

```python
if errors:
    # Clean up session now so repeated validation failures don't accumulate stale state.
    _cleanup_upload_session(request, smart_preview)
    import json as _json
```

- [ ] **Step 1: Remove the cleanup call**

Replace:

```python
    if errors:
        # Clean up session now so repeated validation failures don't accumulate stale state.
        _cleanup_upload_session(request, smart_preview)
        import json as _json
```

With:

```python
    if errors:
        import json as _json
```

Delete the two lines: the comment and the `_cleanup_upload_session(request, smart_preview)` call. The session will now be preserved so the user can fix errors and resubmit without re-uploading files.

- [ ] **Step 2: Run the test suite to confirm no regressions**

```bash
source venv/bin/activate
python manage.py test app01 --keepdb -v 1
```

Expected: all 298 tests pass.

- [ ] **Step 3: Commit**

```bash
git add app01/views.py
git commit -m "fix: preserve upload session on confirm-page validation error"
```

---

### Task 2: Attach source files to all vitro experiments, not just the first

**Files:**
- Modify: `app01/views.py:2413–2431`

**Background:** The source file attachment block uses `vitro_experiments[0]` (hardcoded index) for both the duplicate check and the attachment creation. When a batch uploads data for multiple compounds, the source CSV is only attached to the first compound's experiment. All other compounds' experiments have no source file.

The current block (lines 2413–2431):

```python
    if vitro_experiments and source_files and not invitro_errors:
        from django.core.files.base import ContentFile as CF
        for sf in source_files:
            saved_path = sf.get('saved_path', '')
            if not saved_path or not default_storage.exists(saved_path):
                continue
            if ExperimentAttachment.objects.filter(
                    experiment=vitro_experiments[0], label=sf['filename']).exists():
                dup_warnings.append(sf['filename'])
                continue
            try:
                with default_storage.open(saved_path, 'rb') as fh:
                    content = fh.read()
                att = ExperimentAttachment(
                    experiment=vitro_experiments[0], label=sf['filename'])
                att.file.save(sf['filename'], CF(content), save=True)
                n_attachments += 1
            except Exception as e:
                logger.error(f'smart_upload source vitro attachment error: {e}')
```

- [ ] **Step 1: Rewrite the source-file attachment loop**

Replace the entire block above with:

```python
    if vitro_experiments and source_files and not invitro_errors:
        from django.core.files.base import ContentFile as CF
        for sf in source_files:
            saved_path = sf.get('saved_path', '')
            if not saved_path or not default_storage.exists(saved_path):
                continue
            try:
                with default_storage.open(saved_path, 'rb') as fh:
                    content = fh.read()
                for exp in vitro_experiments:
                    if ExperimentAttachment.objects.filter(
                            experiment=exp, label=sf['filename']).exists():
                        dup_warnings.append(sf['filename'])
                        continue
                    att = ExperimentAttachment(experiment=exp, label=sf['filename'])
                    att.file.save(sf['filename'], CF(content), save=True)
                    n_attachments += 1
            except Exception as e:
                logger.error(f'smart_upload source vitro attachment error: {e}')
```

The key changes:
1. File content is read once outside the experiment loop
2. The dup check and `att` creation both use `exp` (the loop variable) instead of `vitro_experiments[0]`

- [ ] **Step 2: Run the test suite**

```bash
source venv/bin/activate
python manage.py test app01 --keepdb -v 1
```

Expected: 298 tests pass.

- [ ] **Step 3: Commit**

```bash
git add app01/views.py
git commit -m "fix: attach source files to all vitro experiments in batch, not just first"
```

---

### Task 3: Fix body-weight Day 0 = 0.0 normalization skipped

**Files:**
- Modify: `app01/views.py:851`
- Modify: `app01/views.py:935`

**Background:** `if day0:` treats `0.0` as falsy. If a body-weight experiment has Day 0 recorded as exactly `0.0`, the normalization block is skipped and the function returns raw gram values instead of percent-change, mixing scales with other arms on the same chart.

Two locations:

Line 851 (inside `_arm_series()`):
```python
        if day0:
            return [
                round((mean_map[d] - day0) / day0 * 100, 2) if d in mean_map else None
                for d in days
            ]
```

Line 935 (inside `max_bw_drop` summary):
```python
        if day0:
            for val in bw_map.values():
```

- [ ] **Step 1: Fix both `if day0:` guards**

At line 851, change:
```python
        if day0:
```
To:
```python
        if day0 is not None:
```

At line 935, change:
```python
        if day0:
```
To:
```python
        if day0 is not None:
```

Note: if `day0 == 0.0` and normalization runs, the division `(val - day0) / day0` would be division by zero. The guard `if day0 is not None:` still allows `day0 = 0.0` to enter the block. Add a secondary zero-division guard:

At line 851, the full replacement:
```python
        if day0 is not None and day0 != 0:
            return [
                round((mean_map[d] - day0) / day0 * 100, 2) if d in mean_map else None
                for d in days
            ]
```

At line 935:
```python
        if day0 is not None and day0 != 0:
            for val in bw_map.values():
```

This correctly handles three cases:
- `day0 = None` (no Day 0 data): skip, return raw values
- `day0 = 0.0` (data entry error): skip division by zero, return raw values (same safe behavior as before, just now explicit)
- `day0 = 85.3` (normal): normalize

- [ ] **Step 2: Run the test suite**

```bash
source venv/bin/activate
python manage.py test app01 --keepdb -v 1
```

Expected: 298 tests pass.

- [ ] **Step 3: Commit**

```bash
git add app01/views.py
git commit -m "fix: guard body-weight Day 0 normalization against 0.0 falsy and zero-division"
```

---

### Task 4: Add in-vivo experiment dedup to prevent duplicate rows on retry

**Files:**
- Modify: `app01/views.py:2493–2507`

**Background:** The vitro upload path calls `dedup_phase` before writing to avoid duplicates. The in-vivo path has no equivalent: every call to `smart_upload_confirm_view` unconditionally calls `Experiment.objects.create()` for each group. Re-uploading or retrying creates duplicate experiments with identical data.

The current block (lines 2493–2507):

```python
                            exp = Experiment.objects.create(
                                compound=compound,
                                exp_type='in_vivo',
                                assay_name=assay_name_iv,
                                batch_label=batch_label_iv,
                                animal_species=meta['animal_species'],
                                animal_strain=meta['animal_strain'],
                                route=meta['route'],
                                gender=meta['gender'],
                                time_unit=meta['time_unit'],
                                dose_info=dose_info,
                                schedule=schedule,
                            )
                            invivo_exps.append(exp)
                            n_invivo += 1
```

- [ ] **Step 1: Add `n_invivo_skipped` counter at line 2260**

At `app01/views.py:2259–2260`, after `n_invivo = 0`, add:

```python
n_invivo_skipped = 0
```

So the block becomes:

```python
    n_invivo = 0
    n_invivo_skipped = 0
    n_attachments = 0
```

- [ ] **Step 2: Replace `Experiment.objects.create()` with `get_or_create()`**

Replace the block at lines 2493–2507 with:

```python
                            exp, created = Experiment.objects.get_or_create(
                                compound=compound,
                                exp_type='in_vivo',
                                assay_name=assay_name_iv,
                                batch_label=batch_label_iv,
                                dose_info=dose_info,
                                defaults={
                                    'animal_species': meta['animal_species'],
                                    'animal_strain': meta['animal_strain'],
                                    'route': meta['route'],
                                    'gender': meta['gender'],
                                    'time_unit': meta['time_unit'],
                                    'schedule': schedule,
                                }
                            )
                            if not created:
                                n_invivo_skipped += 1
                                continue
                            invivo_exps.append(exp)
                            n_invivo += 1
```

- [ ] **Step 3: Include skipped count in the success message**

Find the success message block (around line 2616):

```python
        messages.success(request, f'数据已上传：{", ".join(parts) or "0 条"}')
```

Add a skipped-invivo note before it:

```python
        if n_invivo_skipped:
            messages.warning(request, f'体内实验：{n_invivo_skipped} 条已存在，已跳过重复写入')
        messages.success(request, f'数据已上传：{", ".join(parts) or "0 条"}')
```

- [ ] **Step 4: Run the test suite**

```bash
source venv/bin/activate
python manage.py test app01 --keepdb -v 1
```

Expected: 298 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app01/views.py
git commit -m "fix: skip duplicate in-vivo experiments on retry using get_or_create"
```

---

### Task 5: Fix summary CSV rejecting new-format compound IDs

**Files:**
- Modify: `app01/upload_pipeline.py:275`

**Background:** The right-table mapping in `parse_summary_csv()` uses `re.match(r'^BPR_', r_name)` which only matches legacy underscore IDs (`BPR_XXXXXX`). Compounds using the canonical hyphen format (`BPRxxxx-NN`) are silently rejected: all their datapoints and IC50 values are dropped with no error or warning.

The current line (line 275):

```python
        if re.match(r'^siRNA-\d+$', r_id) and re.match(r'^BPR_', r_name):
```

- [ ] **Step 1: Broaden the regex**

Change:

```python
        if re.match(r'^siRNA-\d+$', r_id) and re.match(r'^BPR_', r_name):
```

To:

```python
        if re.match(r'^siRNA-\d+$', r_id) and re.match(r'^BPR', r_name):
```

One character removed (`_` after `BPR`). Both `BPR_XXXXXX` and `BPRxxxx-NN` now match.

- [ ] **Step 2: Run the test suite**

```bash
source venv/bin/activate
python manage.py test app01 --keepdb -v 1
```

Expected: 298 tests pass.

- [ ] **Step 3: Commit**

```bash
git add app01/upload_pipeline.py
git commit -m "fix: accept BPRxxxx- canonical compound IDs in summary CSV mapping"
```

---

### Task 6: Filter total_compounds stat by user permission

**Files:**
- Modify: `app01/views.py:1352`

**Background:** `total_compounds = Compound.objects.count()` in `compound_list` counts all compounds regardless of the requesting user's project permissions. A restricted user (with `permissions_project` set) sees the global compound total, leaking information about projects they cannot access.

`_permitted` is already computed at line 1283 and applied to `exp_qs` at line 1293. The `total_compounds` stat does not use it.

The current line (line 1352):

```python
    total_compounds = Compound.objects.count()
```

- [ ] **Step 1: Apply permission filter**

Replace:

```python
    total_compounds = Compound.objects.count()
```

With:

```python
    _cmpd_count_qs = Compound.objects.all()
    if _permitted is not None:
        _cmpd_count_qs = _cmpd_count_qs.filter(project__in=_permitted)
    total_compounds = _cmpd_count_qs.count()
```

- [ ] **Step 2: Run the test suite**

```bash
source venv/bin/activate
python manage.py test app01 --keepdb -v 1
```

Expected: 298 tests pass.

- [ ] **Step 3: Commit**

```bash
git add app01/views.py
git commit -m "fix: filter total_compounds stat by user project permissions"
```

---

### Task 7: Return error field from attachment preview on exception

**Files:**
- Modify: `app01/views.py:2703–2704`

**Background:** `except Exception: return JsonResponse({'headers': [], 'rows': []})` returns an empty 200 response on any error (file not found, malformed CSV, storage failure). The frontend renders an empty table, indistinguishable from a file that genuinely has no data. Users cannot tell if the preview failed or if the file is empty.

The current lines (2703–2704):

```python
    except Exception:
        return JsonResponse({'headers': [], 'rows': []})
```

- [ ] **Step 1: Add error field**

Replace:

```python
    except Exception:
        return JsonResponse({'headers': [], 'rows': []})
```

With:

```python
    except Exception:
        return JsonResponse({'headers': [], 'rows': [], 'error': '预览失败，请直接下载文件'})
```

- [ ] **Step 2: Run the test suite**

```bash
source venv/bin/activate
python manage.py test app01 --keepdb -v 1
```

Expected: 298 tests pass.

- [ ] **Step 3: Commit**

```bash
git add app01/views.py
git commit -m "fix: return error field from attachment preview on exception"
```

---

### Task 8: Isolate temp upload files by user PK

**Files:**
- Modify: `app01/views.py:1906`

**Background:** `saved_path_key = f'_tmp_smart/{filename}'` — two users uploading files with the same filename (e.g., `summary.csv`) share the same storage path. The second upload silently overwrites the first user's file, injecting wrong data into their session.

The current line (line 1906):

```python
            saved_path_key = f'_tmp_smart/{filename}'
```

- [ ] **Step 1: Add user PK to storage path**

Replace:

```python
            saved_path_key = f'_tmp_smart/{filename}'
```

With:

```python
            saved_path_key = f'_tmp_smart/{request.user.pk}/{filename}'
```

- [ ] **Step 2: Run the test suite**

```bash
source venv/bin/activate
python manage.py test app01 --keepdb -v 1
```

Expected: 298 tests pass.

- [ ] **Step 3: Commit**

```bash
git add app01/views.py
git commit -m "fix: isolate temp upload files by user PK to prevent cross-user overwrite"
```

---

### Task 9: Lint check

**Files:** None modified.

- [ ] **Step 1: Run ruff**

```bash
source venv/bin/activate
ruff check app01/views.py app01/upload_pipeline.py --select W293,E401
```

Expected: `All checks passed!`

- [ ] **Step 2: Commit only if violations found**

```bash
git add app01/views.py app01/upload_pipeline.py
git commit -m "chore: fix ruff lint violations"
```
