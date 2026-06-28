# Logic Bug Audit Fixes — Design Spec

**Date:** 2026-06-28
**Scope:** 8 logic bugs found in code audit — upload pipeline, data display, and access control

---

## 1. Background

A systematic code audit identified 8 correctness bugs across `app01/views.py`, `app01/upload_pipeline.py`, and `app01/models.py`. None require schema migrations. All fixes are surgical (1–5 lines each).

---

## 2. Fixes

### Fix 1 — Session destroyed on confirm-page validation error (`views.py:2232`)

**Root cause:** When the confirm form has validation errors (e.g., missing `time_unit`), `_cleanup_upload_session()` is called before re-rendering — deleting the session and temp files. If the user fixes the error and resubmits, the session is empty and they are silently redirected to the upload start, losing all uploaded files.

**Fix:** Remove `_cleanup_upload_session(request, smart_preview)` from the `if errors:` branch. The session is already cleaned up on successful commit (line 2621). Only clean up on success.

```python
# Before (views.py:2230-2232)
if errors:
    _cleanup_upload_session(request, smart_preview)
    ...

# After
if errors:
    # (no cleanup — session preserved so user can fix errors and resubmit)
    ...
```

---

### Fix 2 — Vitro source file attached only to first experiment (`views.py:2413-2431`)

**Root cause:** `ExperimentAttachment` is created with `experiment=vitro_experiments[0]` (hardcoded index). When a batch uploads data for multiple compounds, the source CSV is only attached to the first compound's experiment record.

**Fix:** Iterate over all `vitro_experiments`, attaching the source file to each. Read file content once, create one attachment per experiment.

```python
# Before
att = ExperimentAttachment(experiment=vitro_experiments[0], label=sf['filename'])

# After — inside a loop over vitro_experiments
for exp in vitro_experiments:
    if ExperimentAttachment.objects.filter(experiment=exp, label=sf['filename']).exists():
        continue
    att = ExperimentAttachment(experiment=exp, label=sf['filename'])
    att.file.save(sf['filename'], CF(content), save=True)
    n_attachments += 1
```

The dup-check moves inside the per-experiment loop; `n_attachments` counts total created across all experiments.

---

### Fix 3 — New-format compound IDs silently dropped from summary CSV (`upload_pipeline.py:275`)

**Root cause:** `re.match(r'^BPR_', r_name)` only matches the legacy underscore format (`BPR_XXXXXX`). Compounds using the canonical hyphen format (`BPRxxxx-NN`) are rejected and all their datapoints and IC50 values are silently discarded.

**Fix:** Broaden the regex to `^BPR` to accept both formats.

```python
# Before
if re.match(r'^siRNA-\d+$', r_id) and re.match(r'^BPR_', r_name):

# After
if re.match(r'^siRNA-\d+$', r_id) and re.match(r'^BPR', r_name):
```

---

### Fix 4 — In-vivo experiments duplicated on retry (`views.py:2493`)

**Root cause:** The vitro upload path has a `dedup_phase` that skips already-existing experiments. The in-vivo path has no equivalent check: each `smart_upload_confirm` call unconditionally calls `Experiment.objects.create()`, so retrying or re-uploading a file creates duplicate rows.

**Fix:** Before creating the in-vivo experiment, check for an existing experiment with the same `(compound, batch_label, exp_type, assay_name, dose_info)`. If found, skip.

```python
# Before
exp = Experiment.objects.create(
    compound=compound,
    exp_type='in_vivo',
    assay_name=assay_name_iv,
    batch_label=batch_label_iv,
    dose_info=dose_info,
    ...
)

# After
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
    continue  # skip datapoint insertion for existing experiment
```

Add `n_invivo_skipped = 0` counter before the loop; include in success message if > 0.

---

### Fix 5 — Body-weight Day 0 = 0.0 skips normalization (`views.py:851`, `views.py:935`)

**Root cause:** `if day0:` treats `0.0` as falsy. If Day 0 body weight is recorded as exactly `0.0` (data entry error or placeholder), the `if` block is skipped: the function returns raw gram values instead of percent-change values, mixing scales with other arms on the same chart.

**Fix:** Replace `if day0:` with `if day0 is not None:` at both call sites.

```python
# views.py:851 — in _arm_series()
if day0 is not None:   # was: if day0:

# views.py:935 — in max_bw_drop summary
if day0 is not None:   # was: if day0:
```

---

### Fix 6 — Total compound count ignores permission filter (`views.py:1352`)

**Root cause:** `total_compounds = Compound.objects.count()` counts all compounds regardless of the requesting user's project permissions. A restricted user sees the global total, leaking information about inaccessible projects.

**Fix:** Apply the same `_permitted` filter used for `exp_qs`.

```python
# Before
total_compounds = Compound.objects.count()

# After
_cmpd_count_qs = Compound.objects.all()
if _permitted is not None:
    _cmpd_count_qs = _cmpd_count_qs.filter(project__in=_permitted)
total_compounds = _cmpd_count_qs.count()
```

---

### Fix 7 — Attachment preview returns empty table on error (`views.py:2703`)

**Root cause:** `except Exception: return JsonResponse({'headers': [], 'rows': []})` — any error (file not found, malformed CSV, storage failure) returns a 200 with an empty data structure. The frontend renders an empty table, indistinguishable from a file that genuinely has no data.

**Fix:** Add an `error` field so the frontend can show a user-facing message.

```python
# Before
except Exception:
    return JsonResponse({'headers': [], 'rows': []})

# After
except Exception:
    return JsonResponse({'headers': [], 'rows': [], 'error': '预览失败，请直接下载文件'})
```

The frontend template already has an error-display path — it just needs the `error` key to be present.

---

### Fix 8 — Temp file storage not user-isolated (`views.py:1906`)

**Root cause:** `saved_path_key = f'_tmp_smart/{filename}'` — two users uploading files with the same filename (e.g., `summary.csv`) share the same storage path. The second upload overwrites the first user's file, injecting wrong data into the first user's upload session.

**Fix:** Prefix the storage key with the user's PK.

```python
# Before
saved_path_key = f'_tmp_smart/{filename}'

# After
saved_path_key = f'_tmp_smart/{request.user.pk}/{filename}'
```

---

## 3. File Map

| File | Fixes |
|------|-------|
| `app01/views.py` | Fix 1, 2, 4, 5, 6, 7, 8 (7 changes) |
| `app01/upload_pipeline.py` | Fix 3 (1 change) |

No migrations. No template changes. No model changes.

---

## 4. Testing

- **Fix 1:** Upload files, trigger a validation error on confirm page, fix the error, resubmit — should succeed without re-uploading.
- **Fix 2:** Upload a batch with 3+ compounds; confirm; open each compound's detail page — all should have the source file attachment.
- **Fix 3:** Upload a summary CSV containing `BPRxxxx-NN` style compound IDs — datapoints should appear.
- **Fix 4:** Upload the same in-vivo file twice — second upload should report "N experiments skipped (already exist)" rather than duplicating.
- **Fix 5:** Cannot easily test in isolation without crafting Day 0 = 0.0 data; verify `if day0 is not None:` pattern in code review.
- **Fix 6:** Log in as a restricted user; the stats bar total should reflect only accessible compounds.
- **Fix 7:** Open attachment preview on a deleted/inaccessible file — should show error message not empty table.
- **Fix 8:** Code review only — storage path should contain user PK segment.
