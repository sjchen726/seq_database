# Display & Upload Feedback Fixes — Design Spec

**Date:** 2026-06-27
**Scope:** Three correctness/UX fixes in `app01/views.py`

---

## 1. Background

Post-audit of the project identified three independent issues:

1. **`_SEP_TOKEN` undefined** — `NameError` at runtime when any dual-segment sequence (embedded linker) is rendered
2. **Control group detection too narrow** — exact-keyword matching misses common naming variants ("Control Group", "Saline group", etc.), causing treatment-arm misclassification in charts
3. **Skipped datapoints not reported** — dedup silently discards duplicate data points; user sees "upload successful" with no indication that rows were filtered

All three fixes are contained within `views.py`. No model changes, no migrations, no new files required.

---

## 2. Fix Specifications

### Fix 1 — `_SEP_TOKEN` Undefined

**Location:** `views.py`, near line 259 (before `get_modify_seq_colored`)

**Root cause:** `get_modify_seq_colored()` uses `_SEP_TOKEN.copy()` at line 276 to insert SEP markers between the two parts of a dual-segment sequence (and between the linker section). `_SEP_TOKEN` is never defined anywhere in the codebase.

**Effect:** Any page that renders a `modify_seq` containing an embedded linker (detected by `detect_embedded_linker()`) raises `NameError: name '_SEP_TOKEN' is not defined`.

**Fix:** Define the constant at module level, immediately before `get_modify_seq_colored()`:

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

The template (`_seq_group_row.html:101`) checks only `item.type == 'SEP'` and renders a `|` divider. `split_tokens_at_sep()` checks only `t.get('type') == 'SEP'`. The remaining fields match the structure of other tokens in the list for consistency.

---

### Fix 2 — Control Group Detection Too Narrow

**Location:** `views.py`, near line 770 (`_CONTROL_KEYWORDS` + `_is_control_arm`)

**Root cause:** `_is_control_arm(dose_info)` does a single exact match: `dose_info.lower().strip() in _CONTROL_KEYWORDS`. The keyword set covers only 6 values (`saline, pbs, vehicle, control, nc, neg`). Naming variants like "Control Group", "Saline group", "Negative Control", "PBS ctrl" are not recognized and are classified as treatment arms.

**Fix:** Replace the single-set exact match with a two-pass check:

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

**Pass 1 (exact):** fast set lookup for common single-word values.

**Pass 2 (substring):** catches compound phrases ("Negative Control", "PBS Control group", "Saline vehicle") by checking if any of the longer-form keywords appear anywhere in the string.

The substring set is deliberately smaller than the exact set to avoid false positives. For example, "neg" is exact-only: a dose arm named "1mg/kg BPR-neg123" should not be classified as a control.

---

### Fix 3 — Skipped Datapoints Not Reported

**Location:** `views.py`, inside `smart_upload_confirm_view`, the invitro write loop (~lines 2335–2380)

**Root cause:** When `dp_conflicts` contains entries with `skip=True`, datapoints are silently skipped at line 2360 (`if fp in skip_fps: continue`). The count is never tracked or surfaced to the user.

**Fix:** Add a `n_skipped_dps` counter before the write loop; increment it on each skip; include the count in the success message context.

```python
# Before the write loop
n_skipped_dps = 0

# Inside the loop, replacing the bare continue
if fp in skip_fps:
    n_skipped_dps += 1
    continue
```

In the success message block (near line 2560), append a note when any datapoints were skipped:

```python
if n_skipped_dps:
    parts.append(f'跳过 {n_skipped_dps} 个重复数据点（已存在于数据库）')
```

The `parts` list is already used to build the `success_msg` string that is returned in the template context. No template changes are needed.

---

## 3. Files Changed

| File | Change |
|------|--------|
| `app01/views.py` | Fix 1: define `_SEP_TOKEN` constant; Fix 2: replace `_CONTROL_KEYWORDS` + `_is_control_arm`; Fix 3: add `n_skipped_dps` counter and success message |

No model changes. No new migrations. No template changes.

---

## 4. Testing

| Fix | Test scenario |
|-----|---------------|
| Fix 1 | Call `get_modify_seq_colored(seq, ...)` where `seq` contains an embedded linker (detected by `detect_embedded_linker`). Assert the return value is a list containing at least one token with `type == 'SEP'`. Assert no `NameError` is raised. |
| Fix 2 | Assert `_is_control_arm('Control Group')` → True; `_is_control_arm('Saline group')` → True; `_is_control_arm('PBS ctrl')` → True; `_is_control_arm('pbs')` → True; `_is_control_arm('BPR123')` → False; `_is_control_arm('1mg/kg')` → False. |
| Fix 3 | Set up a confirm POST where `dp_conflicts` contains one skip=True entry matching a datapoint in the upload. Assert `Experiment.datapoints.count()` equals the expected non-skipped count. Assert the response context success message contains `'跳过'` and the correct count. |

---

## 5. Out of Scope

- N+1 query optimization for `exp.datapoints.all()` in display helpers (separate performance task)
- Body weight file ID prefix validation (separate upload pipeline task)
- File read failure detailed logging (minor, deferred)
- Vocabulary upsert transaction wrapping (low-frequency concurrency issue, deferred)
