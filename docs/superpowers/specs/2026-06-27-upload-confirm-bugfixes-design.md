# Upload Confirm View Bug Fixes — Design Spec

**Date:** 2026-06-27
**Scope:** Four correctness bugs in `smart_upload_confirm_view` (`app01/views.py`)

---

## 1. Background

The `smart_upload_confirm_view` (lines 2084–2570) was recently refactored as part of the Upload Pipeline Robustness sub-project. Four bugs were identified in the refactored code during a post-implementation audit:

1. **target_name silent failure** — compound metadata not updated after ID normalization
2. **Error path resource leak** — session data and temp files accumulate on validation failure
3. **in_vivo partial commit** — group-level transactions allow partial data persistence
4. **Strand diff ID mismatch** — conflict choices silently ignored when IDs went through format remap

All four bugs are contained within `views.py`. No model changes, no migrations, no new files required.

---

## 2. Fix Specifications

### Fix 1 — `target_name` Silent Failure

**Location:** `views.py:2528–2541`

**Root cause:** `touched_cids` is built from raw compound IDs in `smart_preview` (the original parsed form). The `Compound.objects.filter(compound_id__in=touched_cids)` query finds nothing when the compounds were saved under normalized IDs (via `_resolve_cid()`).

**Example:** Upload contains `BPR_3M03FN01` → normalized to `BPR3M03-FN01` → saved as `BPR3M03-FN01` in DB. `touched_cids = {'BPR_3M03FN01'}`. Filter finds no rows. `target_name` silently stays blank.

**Fix:** Resolve each raw ID through `_resolve_cid()` before building the update set:

```python
touched_cids = set()
if invitro:
    for cid in invitro.get('strand_map', {}):
        touched_cids.add(_resolve_cid(cid))
    for exp_data in invitro.get('experiments', []):
        touched_cids.add(_resolve_cid(exp_data['compound_id']))
for group in invivo_groups:
    for g in group['groups']:
        touched_cids.add(_resolve_cid(g['compound_id']))
if touched_cids:
    Compound.objects.filter(compound_id__in=touched_cids, target_name='').update(
        target_name=target_name_input
    )
```

---

### Fix 2 — Error Path Resource Leak

**Location:** `views.py:2187–2210`

**Root cause:** When validation fails (`if errors:` at line 2187), the view renders the form and returns immediately without cleaning up:
- Session keys: `smart_preview`, `pipeline_result`, `upload_meta`, `normalize_id_map`
- Temp files: all `saved_path` entries in `smart_preview['file_detections']`

On repeated failed submissions, session grows unboundedly and `_tmp_smart/` accumulates orphaned files.

**Fix:** Extract `_cleanup_upload_session(request, smart_preview)` — a private helper function defined at module level (before `smart_upload_confirm_view`):

```python
def _cleanup_upload_session(request, smart_preview):
    """Delete temp files and clear upload session keys."""
    for det in (smart_preview or {}).get('file_detections', []):
        path = det.get('saved_path', '')
        if path:
            try:
                if default_storage.exists(path):
                    default_storage.delete(path)
            except Exception:
                pass
    request.session.pop('smart_preview', None)
    request.session.pop('pipeline_result', None)
    request.session.pop('upload_meta', None)
    request.session.pop('normalize_id_map', None)
```

Call it before the `return render(...)` in the `if errors:` block:

```python
if errors:
    _cleanup_upload_session(request, smart_preview)
    return render(request, 'smart_upload.html', { ... })
```

The existing success-path cleanup at lines 2543–2546 is unchanged (it already clears session correctly; temp files are deleted inside the write loop).

---

### Fix 3 — in_vivo Partial Commit

**Location:** `views.py:2419–2487`

**Root cause:** Each in_vivo group is wrapped in its own `transaction.atomic()`. If group N fails, groups 1..N-1 are already committed. The result is partial data in the database with no rollback.

**Fix:** Wrap all in_vivo groups in a single outer `transaction.atomic()`. The inner `transaction.atomic()` per group becomes a savepoint (Django nested atomics use `SAVEPOINT`). On any group exception: append to `invivo_errors`, then re-raise to trigger the outer rollback.

```python
invivo_errors = []
try:
    with transaction.atomic():                     # outer: all-or-nothing
        for i, group in enumerate(invivo_groups):
            meta = invivo_meta[i]
            invivo_exps = []
            try:
                with transaction.atomic():         # inner: savepoint per group
                    # ... existing write logic for this group ...
                    all_invivo_exps.extend(invivo_exps)
            except Exception as e:
                logger.error(f'smart_upload_confirm invivo error: {e}')
                invivo_errors.append(f'文件 {group["filename"]}: {e}')
                raise                              # trigger outer rollback
except Exception:
    pass                                           # invivo_errors already populated
```

Error message to user (line 2560): unchanged — `invivo_errors` still shows which group failed.

---

### Fix 4 — Strand Diff ID Mismatch

**Location:** `views.py:2254–2258`

**Root cause:** `strand_diffs[i]['compound_id']` was built in `smart_upload_preview_view` using only `normalize_id_map` (line 2007: `id_map.get(cid, cid)`). But in confirm view, `resolved` is built via `id_format_mismatch` remap first, then `_resolve_cid()` (which applies `normalize_id_map` → `user_cid_remap` → `canonicalize_compound_id`). When `id_format_mismatch` remaps an ID differently than `normalize_id_map`, the comparison `d['compound_id'] == resolved` fails, and `diff_choice` is always `None` (defaults to 'keep').

**Fix:** In the `diff_choice` lookup (lines 2254–2258), apply `_resolve_cid()` to `d['compound_id']` so both sides of the comparison go through the same final resolution step:

```python
diff_choice = next(
    (d['user_choice'] for d in strand_diffs
     if _resolve_cid(d['compound_id']) == resolved and d['strand_type'] == strand_type),
    None,
)
```

`_resolve_cid(d['compound_id'])` is safe here: the already-normalized ID is not in `normalize_id_map` (step 1 is a no-op), `user_cid_remap` uses the raw form (step 2 is also typically a no-op on normalized IDs), and `canonicalize_compound_id` is idempotent on canonical IDs.

---

## 3. Files Changed

| File | Change |
|------|--------|
| `app01/views.py` | Fix 1: `touched_cids` resolved before update; Fix 2: `_cleanup_upload_session()` helper added, called on error return; Fix 3: outer `transaction.atomic()` wrapping all in_vivo groups; Fix 4: `_resolve_cid()` in strand diff lookup |

No model changes. No new migrations. No template changes.

---

## 4. Testing

Each fix needs a unit/integration test:

| Fix | Test scenario |
|-----|---------------|
| Fix 1 | Upload compound with legacy ID `BPR_3M03FN01` that normalizes to `BPR3M03-FN01`. After confirm, assert `Compound.objects.get(compound_id='BPR3M03-FN01').target_name != ''` |
| Fix 2 | POST to confirm with missing `target_name`. Assert session keys are absent after response. Assert no files remain in `_tmp_smart/` path. |
| Fix 3 | Upload two in_vivo groups where second group has invalid data. Assert no `Experiment` rows were created for either group. |
| Fix 4 | Upload strand with ID that has `id_format_mismatch` entry. Set `user_choice = 'overwrite'`. Assert `Strand.modify_seq` is updated after confirm. |

---

## 5. Out of Scope

- `get_or_create` inefficiency for project field update (Medium, separate cleanup task)
- User remap ordering vs. dedup detection (Medium, requires preview/confirm flow redesign)
- `readout_type` validation at parse time (Low, no user-facing breakage currently)
