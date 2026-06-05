# SeqList Display Bugfixes — Design Spec

**Date:** 2026-06-05
**Scope:** Three display/logic bugs in seq_list and sequence coloring.

---

## Bug 1: LK1 Not Detected as Dual-Segment Linker Keyword

### Root Cause

`detect_embedded_linker` builds its detection regex only from `SeqModule.objects.filter(linker_connector='-')`. LK1 exists in `LinkerModule` but not in `SeqModule`, so the pattern `-LK1-L96-LK1-` is never matched. The full sequence is treated as a single flat segment, causing `LK1-L96` to be tokenized as a combo token (char=`LK1`, delivery_label=`L96`). In the normal nucleotide column rendering, `L96` appears as a floating `seq-delivery-label` above `LK1`.

### Fix

**`detect_embedded_linker`:** Merge `LinkerModule` keywords into the linker keyword set alongside `SeqModule(linker_connector='-')` keywords.

```python
sm_kws = [m.keyword for m in SeqModule.objects.filter(linker_connector='-') if m.keyword]
lk_kws = [m.keyword for m in LinkerModule.objects.all() if m.keyword]
linker_keywords = list({*sm_kws, *lk_kws})
```

**`get_modify_seq_colored`:** When `lk_modules` is provided, append LinkerModule keywords to `sm_keywords` so they are matched as whole tokens by the regex (not character-by-character). This ensures `LK1-L96` is tokenized as a combo with `char='LK1'`.

```python
sm_keywords = sorted([m.keyword.strip() for m in SeqModule.objects.all() ...], ...)
if lk_modules is not None:
    lk_kws = [m.keyword.strip() for m in lk_modules if m.keyword and m.keyword.strip()]
    sm_keywords = sorted(set(sm_keywords) | set(lk_kws), key=len, reverse=True)
```

The existing step-7 expansion (`lk_modules` combo expansion) already handles `LK1-L96` → `[LK1, L96]`. The `segment_sep` column template renders only `lk.char` with no `delivery_label`, so no floating label appears in the middle section.

### Affected code paths

- `detect_embedded_linker` (called from `get_modify_seq_colored` and `add_o_to_all_rules_safe`)
- `get_modify_seq_colored` (called from `build_sequence_data`)

---

## Bug 2: Experiment Data Link Not Shown for Non-KD Readout Types

### Root Cause

`get_experiment_summary` only computes a summary string when `readout_type` is `knockdown_pct`, `mRNA_remaining`, `plasma_conc`, or `tissue_conc`. If all experiments for a duplex use other readout types (e.g., `体重`, `IC50`), the summary string is empty. The template at `_seq_group_row.html` only renders a link when `group.exp_summary` is non-empty, so no link appears even though experiment data exists.

### Fix

In `get_experiment_summary`, after computing `parts`, if `parts` is empty but experiments exist, produce a fallback string:

```python
parts = [s for s in [vitro_summary, vivo_summary] if s]
if parts:
    result[duplex_id] = ' / '.join(parts)
else:
    result[duplex_id] = f"{len(exps)} 条实验"
```

The template is unchanged. Any non-empty `exp_summary` renders a link to `experiment_detail`.

---

## Bug 3: Clone Button Appears at Bottom of Tall Rows

### Root Cause

`.ds-table td { vertical-align: middle }` centers all cell content. For duplex rows (SS + AS), the sequence display column is tall (nested 2-row table). The operations `<td>` has no explicit `vertical-align` override, so its content (edit buttons + clone button) is vertically centered in a tall cell, appearing visually low.

### Fix

Add `style="vertical-align:top;"` to the operations `<td>` in `_seq_group_row.html`:

```html
<td style="vertical-align:top;">
  <div class="ds-actions">
```

---

## Files Touched

| File | Change |
|------|--------|
| `app01/views.py` | `detect_embedded_linker`: add LinkerModule keywords to detection set |
| `app01/views.py` | `get_modify_seq_colored`: merge lk_modules keywords into sm_keywords |
| `app01/views.py` | `get_experiment_summary`: fallback to `"N 条实验"` when summary is empty but experiments exist |
| `templates/_seq_group_row.html` | Operations `<td>`: add `vertical-align:top` |

---

## Edge Cases

- **LinkerModule is empty:** `lk_kws` is `[]`; set union adds nothing; behavior unchanged.
- **LK1 appears in both SeqModule and LinkerModule:** Set union deduplicates; no double-matching.
- **Experiment with 0 datapoints:** `len(exps)` counts experiment records, not datapoints; `"1 条实验"` still appears even if no datapoints yet.
- **All experiments have KD summary:** `parts` is non-empty, fallback branch not taken; existing behavior unchanged.
- **Single-segment sequences:** `detect_embedded_linker` returns `None` unchanged when no linker pattern matches; nothing changes for normal sequences.
