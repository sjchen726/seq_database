# Compound ID Canonicalization Design

## Goal

Normalize all compound IDs to `BPR<project_code>-<serial>` format on upload and retroactively migrate all existing records.

## Problem

IDs for the same compound arrive in multiple formats:
- `350025087` — bare number (no prefix)
- `BPR_350025087` — legacy underscore prefix
- `BPR-350025087` — dash-after-BPR variant
- `BPR350-025087` — target canonical form

All of these refer to the same compound. After this change, all IDs in the database and all new uploads will use the single canonical form `BPR<project_code>-<serial>`.

## Canonical Format

```
BPR<project_code>-<serial>
```

Examples:
| Raw input | project_code | Canonical |
|---|---|---|
| `350025087` | `350` | `BPR350-025087` |
| `BPR_350025087` | `350` | `BPR350-025087` |
| `BPR-350025087` | `350` | `BPR350-025087` |
| `BPR350-025087` | `350` | `BPR350-025087` (unchanged) |
| `BPR_3M03FN01` | `3M03` | `BPR3M03-FN01` |
| `3M03FN01` | `3M03` | `BPR3M03-FN01` |
| `BPR3M03-FN01` | `3M03` | `BPR3M03-FN01` (unchanged) |
| `Alnylam` | `350` | `Alnylam` (project_code not found in ID — control compound, left as-is) |
| `Saline` | `3M03` | `Saline` (same — left as-is) |

## Architecture

### 1. `canonicalize_compound_id(raw_id, project_code)` — `upload_pipeline.py`

Single normalization function. Algorithm:

1. If `raw_id` already starts with `BPR{project_code}-` → return unchanged.
2. Try stripping prefix variations in order: `BPR_{project_code}`, `BPR-{project_code}`, `BPR{project_code}-`, `BPR{project_code}`, `{project_code}`.
3. After stripping, strip any leading `-`.
4. If no prefix matched (serial is empty or project_code not found in ID) → return `raw_id` unchanged.
5. Return `BPR{project_code}-{serial}`.

If `project_code` is empty or `raw_id` is empty → return `raw_id` unchanged.

### 2. Upload flow integration — `app01/views.py`

In `smart_upload_confirm_view`, wrap all three `Compound.objects.get_or_create` call sites with `canonicalize_compound_id(cid, project_code)`:

- `new_compounds` list entries (vitro seq)
- `strand_map` keys
- invivo group `compound_id` values

`project_code` is already available as a local variable in the confirm view.

`parse_body_weight_file` already adds `BPR_` prefix to numeric IDs. The confirm view canonicalization will convert those further (e.g., `BPR_350025087` → `BPR350-025087`). No change to the parser needed.

### 3. `_parse_compound_id` — `app01/models.py`

Updated to handle new format first, with legacy fallback:

```python
def _parse_compound_id(compound_id):
    # New format: BPR3M03-FN01 → project=3M03, target=FN
    m = re.match(r'^BPR([A-Z0-9]+)-([A-Z]{2})(\d+)$', compound_id)
    if m:
        return m.group(1), m.group(2)
    # New format numeric serial: BPR350-025087 → project=350, target=''
    m = re.match(r'^BPR([A-Z0-9]+)-\d', compound_id)
    if m:
        return m.group(1), ''
    # Legacy format: BPR_3M03FN01 (kept for transition period)
    m = re.match(r'^BPR_([A-Z0-9]+)([A-Z]{2})(\d{2,3})$', compound_id)
    if m:
        return m.group(1), m.group(2)
    return '', ''
```

### 4. `detect_id_format` and `normalize_compound_ids` — `upload_pipeline.py`

Regexes updated to match new format `BPR<proj>-<target><digits>` instead of `BPR_<proj><target><digits>`:

- `detect_id_format`: `r'^BPR[A-Z0-9]+-[A-Z]{2}(\d{2,3})$'`
- `normalize_compound_ids`: split on `r'^(BPR[A-Z0-9]+-[A-Z]{2})(\d{2,3})$'`

IDs with purely numeric serials (e.g., `BPR350-025087`) don't participate in 2-digit/3-digit normalization and pass through unchanged (same as before).

### 5. Data migration — `app01/migrations/0010_canonicalize_compound_ids.py`

RunPython using raw SQL with `FOREIGN_KEY_CHECKS=0`.

Tables updated in order:
1. `strand.compound_id` — FK to compound
2. `experiment.compound_id` — FK to compound
3. `compound.compound_id` — PK

`canonicalize_compound_id` logic is inlined into the migration (not imported from `upload_pipeline.py`) to ensure the migration remains self-contained and won't break if the function is later renamed or moved.

Reverse function: no-op (PK renames are not reversible without a full snapshot).

## Files Changed

| File | Change |
|---|---|
| `app01/upload_pipeline.py` | Add `canonicalize_compound_id`; update `detect_id_format` and `normalize_compound_ids` regexes |
| `app01/models.py` | Update `_parse_compound_id` for new format |
| `app01/views.py` | Wrap 3 `get_or_create` call sites in `smart_upload_confirm_view` |
| `app01/migrations/0010_canonicalize_compound_ids.py` | New migration: bulk PK rename via raw SQL |
| `app01/tests.py` | Update existing `normalize_compound_ids`/`detect_id_format` tests; add `canonicalize_compound_id` tests |

## What Is Not Changed

- `Compound`, `Strand`, `Experiment`, `DataPoint` model schemas — no field changes
- All view query logic — `compound_id` lookups work identically with new format
- `id_format_mismatch` cross-format detection — updated indirectly via `normalize_compound_ids`
- `parse_body_weight_file` — existing `BPR_` prefix logic kept; confirm view handles final canonicalization
