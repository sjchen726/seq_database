# Smart Upload Consolidation & UX Enhancement — Design Spec

**Date:** 2026-06-24
**Scope:** Sub-project A of the upload optimization series.

---

## Goal

1. Remove all legacy upload entry points; keep only `smart_upload`.
2. Let users correct compound IDs and confirm/fix batch metadata before saving.

---

## Section 1: URL Consolidation

### Redirects (permanent)

The five legacy routes are replaced with Django `RedirectView` pointing to `/upload/smart/`:

| Old URL | Old view |
|---|---|
| `/upload/` | `upload_view` |
| `/upload/confirm/` | `upload_confirm_view` |
| `/upload/success/` | `upload_success_view` |
| `/upload/invivo/` | `invivo_upload_view` |
| `/upload/invivo/confirm/` | `invivo_upload_confirm_view` |

### Code deleted

- `upload_view`, `upload_confirm_view`, `upload_success_view` (~300 lines in `views.py`)
- `invivo_upload_view`, `invivo_upload_confirm_view` (~170 lines in `views.py`)
- Templates: `upload.html`, `invivo_upload.html`, `upload_success.html`, `confirm_upload_preflight.html`

### Code kept

`parse_cp_file` and `parse_transfection_file` in `upload_pipeline.py` are **not** deleted — `smart_upload_view` still imports them (needed if file type detection routes a file there in a future path).

---

## Section 2: Editable Confirm Page

### 2a. Batch metadata pre-fill

`exp_date` is currently an empty date input. If `preview.invitro.exp_date` is non-null (parsed from the summary file header), pre-fill it as the input's `value`. User can still override it.

No change needed for `assay_name` (already pre-filled from parsed data) or `batch_label` (already a writable input).

### 2b. Compound ID correction table

A collapsible card **"化合物 ID 确认"** appears on the confirm page whenever `preview.invitro.experiments` or `preview.invivo_groups` is non-empty.

**Template rendering:**

Collect all unique compound IDs from:
- `preview.invitro.experiments[*].compound_id`
- `preview.invivo_groups[*].groups[*].compound_id`

Render one row per unique ID:

```html
<!-- for each unique compound_id at index N -->
<input type="hidden" name="cid_orig_N" value="{{ compound_id }}">
<input type="text"   name="cid_new_N"  value="{{ compound_id }}">
```

The card is collapsed by default (JS toggle). A mismatch badge ("已修正 N 个") appears on the card header when any input diverges from its original value.

**Confirm view changes (`smart_upload_confirm_view`):**

1. Read all `cid_orig_N` / `cid_new_N` pairs from POST → build `user_cid_remap: dict[str, str]`. (Named distinctly from the existing `id_remap` variable produced by `detect_cross_format_match`, which handles cross-format DB matches.)
2. Validate: if any `cid_new_N` is empty after strip → append error "化合物 ID 不能为空".
3. Apply remap at every compound resolution point:
   ```python
   def _resolve_cid(raw: str) -> str:
       remapped = user_cid_remap.get(raw, raw)
       return canonicalize_compound_id(remapped, project_code)
   ```
4. Replace the four `get_or_create` call sites:
   - `new_compounds` loop
   - `strand_map` loop (after existing `id_remap` lookup)
   - `experiments` loop
   - invivo `groups` loop

**Merge semantics:** Two originally-different IDs remapped to the same value → both resolve to the same `Compound` object. This is intentional (user is merging two entries).

---

## Section 3: Data Flow

```
Upload files
  └─ Phase 1 POST → save to temp storage, auto-detect types
  └─ Phase 2 POST (reparse) → _build_smart_preview → session
  └─ GET ?preview=1 → render confirm page
        ├─ [metadata inputs: batch_label, assay_name, exp_date]  ← already editable
        └─ [Compound ID correction table]  ← new
  └─ POST to /upload/smart/confirm/
        ├─ 1. read id_remap from cid_orig_N / cid_new_N
        ├─ 2. validate (no empty new IDs)
        ├─ 3. _resolve_cid() at all get_or_create sites
        └─ 4. normal save flow (unchanged)
```

---

## Section 4: Error Handling

| Condition | Behaviour |
|---|---|
| `cid_new_N` is empty | Validation error: "化合物 ID 不能为空" |
| Two IDs remapped to same value | Allowed — merges into one `Compound` |
| Remapped ID already exists in DB | `get_or_create` returns existing object — no error |
| After canonicalize, new == original | No-op, remap silently skipped |

---

## Out of Scope

- Editing individual data point values (wrong values → re-upload the file)
- Persisting the remap for future uploads
- Adding a new URL or page step
