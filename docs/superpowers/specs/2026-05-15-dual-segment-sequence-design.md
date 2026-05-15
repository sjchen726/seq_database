# Design Spec: Dual-Segment Sequence (sequence-linker-sequence)

**Date:** 2026-05-15
**Feature:** Support for modify_seq containing an embedded linker between two RNA segments

## Overview

Some siRNA conjugates have a single strand (SS or AS) composed of two RNA segments joined by a chemical linker, expressed in modify_seq as:

```
Part1_tokens - LinkerSection - Part2_tokens
```

Examples:
- SS: `GnsGmsCmUmUmUmCfUmGfCfAmUmCmAmGmAmCmAmsUmsUm-LK1-L96-LK1-UmsCmsCmUmCmUmGfAmUfGfGfUmCmAmAmAmGmUmCmsCmsUm`
- AS: `AnsGfsGmAmCmUfUmUfGfAmCmCmAmUfCmAfGmAmGmsGmsAm------------AmsAfsUmGmdUCmdUGmAmUmGmGmCmAfG (moe) AfAmAmGmsCmsCm`

The AS `------------` is a position placeholder (not a real chemical linker) indicating alignment with the SS linker position.

## Scope

- Files modified: `app01/views.py`, `templates/_seq_group_row.html`
- No new models, no migrations
- Upload: existing `register_seq` (step A) then `upload_delivery_info` (step B)

## Data Model (No Changes)

| Field | Behavior |
|---|---|
| `Delivery.modify_seq` | Stores full string including embedded linker — unchanged |
| `Delivery.linker_seq` | Full converted string (processed per-segment, then rejoined) |
| `Sequence.seq` | Naked bases: Part1_bases + Part2_bases concatenated |
| `Delivery.naked_length` | Total length: Part1 + Part2 |

**Naked sequence extraction already works**: the existing `findall(r'(INVAB|[AUGCI])')` step ignores linker token characters (L, K, 1, 6, 9, `-`) and naturally concatenates Part1+Part2 bases. No changes needed to `save_deliveries()` extraction logic.

## Section 1: `detect_embedded_linker()`

New helper function. Placed immediately before `_filter_delivery_qs_by_term` in `views.py`.

```python
def detect_embedded_linker(modify_seq: str) -> tuple[str, str, str] | None:
    """
    Returns (part1, linker_section, part2) if an embedded linker is detected,
    or None for normal single-segment sequences.

    Detects two patterns:
    - 2+ consecutive known linker tokens (SeqModule entries with linker_connector='-')
      e.g.  -LK1-L96-LK1-
    - 4+ consecutive dashes (AS placeholder)
      e.g.  ------------
    Both sides of the match must be non-empty.
    """
    linker_keywords = [
        m.keyword for m in SeqModule.objects.filter(linker_connector='-')
        if m.keyword
    ]
    patterns = []
    if linker_keywords:
        kw_pat = '|'.join(re.escape(k) for k in sorted(linker_keywords, key=len, reverse=True))
        # Require ≥2 consecutive DM linker tokens (avoids matching single Um-LK1 combos)
        patterns.append(rf'-(?:{kw_pat})(?:-(?:{kw_pat}))+-')
    patterns.append(r'-{4,}')

    m = re.search('|'.join(patterns), modify_seq)
    if not m:
        return None
    part1 = modify_seq[:m.start()]
    linker_section = m.group(0)
    part2 = modify_seq[m.end():]
    if not part1.strip() or not part2.strip():
        return None
    return part1, linker_section, part2
```

**Edge cases:**
- Single combo `Um-LK1` (1 DM token): does NOT match (requires ≥2).
- `------------` AS placeholder: matches dash pattern.
- Linker at string start/end: rejected by the `not part1.strip()` guard.

## Section 2: `add_o_to_all_rules_safe()`

New wrapper for dual-segment linker_seq generation. Replaces direct calls to `add_o_to_all_rules()` in `save_deliveries()`.

**Problem:** `add_o_to_all_rules()` on `...UmsUm-LK1-L96-LK1-Um...` detects `Um-LK1` as a combo and appends `'o'` after it, producing `Um-LK1o` (wrong connector).

**Fix:**

```python
def add_o_to_all_rules_safe(modify_seq: str) -> str:
    parts = detect_embedded_linker(modify_seq)
    if parts is None:
        return add_o_to_all_rules(modify_seq)
    part1, linker_section, part2 = parts
    # linker_section already contains its own '-' delimiters
    return add_o_to_all_rules(part1) + linker_section + add_o_to_all_rules(part2)
```

Why this works:
- `add_o_to_all_rules(part1)` ends with `...UmsUm` (no trailing connector — end of string)
- `linker_section` = `-LK1-L96-LK1-` provides its own leading `-`
- Junction: `UmsUm` + `-LK1-L96-LK1-` = `UmsUm-LK1-L96-LK1-` ✓

**Caller change:** In `save_deliveries()`, replace:
```python
current_linker_seq = add_o_to_all_rules(item['modify_seq'])
```
with:
```python
current_linker_seq = add_o_to_all_rules_safe(item['modify_seq'])
```

## Section 3: `get_modify_seq_colored()` — Dual-Segment Display

**SEP token constant** (added at module level):

```python
_SEP_TOKEN = {
    'char': '|', 'type': 'SEP', 'count': '',
    'is_combo': False, 'delivery_label': None, 'delivery_color': None,
}
```

**Function change** — add at the top of `get_modify_seq_colored()`, before existing logic:

```python
def get_modify_seq_colored(seq, selected_seq_type, seq_type, dm_modules=None, color_map=None):
    parts = detect_embedded_linker(seq or "")
    if parts is not None:
        part1, linker_section, part2 = parts
        if dm_modules is None:
            dm_modules = list(DeliveryModule.objects.all())
        if color_map is None:
            color_map = get_color_map(modules=dm_modules)
        tokens1 = get_modify_seq_colored(part1, selected_seq_type, seq_type, dm_modules, color_map)
        tokens2 = get_modify_seq_colored(part2, selected_seq_type, seq_type, dm_modules, color_map)
        if re.fullmatch(r'-+', linker_section):
            # AS placeholder: show ··· in gray
            linker_tokens = [{'char': '···', 'type': 'LINKER_DASH', 'count': '',
                               'is_combo': False, 'delivery_label': None, 'delivery_color': None}]
        else:
            # SS: render linker tokens (LK1, L96 etc.) with colors
            linker_tokens = get_modify_seq_colored(
                linker_section.strip('-'), selected_seq_type, seq_type, dm_modules, color_map
            )
        return tokens1 + [_SEP_TOKEN] + linker_tokens + [_SEP_TOKEN] + tokens2

    # ... existing logic unchanged ...
```

## Section 4: Alignment — `split_tokens_at_sep()` + `build_duplex_groups()`

### New helper

```python
def split_tokens_at_sep(tokens):
    """Split token list at two SEP markers. Returns (part1, linker_tokens, part2) or None."""
    indices = [i for i, t in enumerate(tokens) if t.get('type') == 'SEP']
    if len(indices) < 2:
        return None
    i1, i2 = indices[0], indices[1]
    return tokens[:i1], tokens[i1+1:i2], tokens[i2+1:]
```

### `build_duplex_groups()` change

Replace the existing `align_duplex_tokens()` call:

```python
ss_tokens = sorted_items[0].get('modify_seq_colored') or []
as_tokens = sorted_items[1].get('modify_seq_colored') or []

ss_split = split_tokens_at_sep(ss_tokens)
as_split = split_tokens_at_sep(as_tokens)

if ss_split and as_split:
    ss_p1, ss_lk, ss_p2 = ss_split
    as_p1, as_lk, as_p2 = as_split
    aligned = (
        align_duplex_tokens(ss_p1, as_p1)
        + [{'col_type': 'segment_sep', 'linker_tokens': ss_lk}]
        + align_duplex_tokens(ss_p2, as_p2)
    )
else:
    aligned = align_duplex_tokens(ss_tokens, as_tokens)
```

**Visual result:**
```
SS 3' │ G  G  C  U  U … │ LK1 L96 LK1 │ U  C  C  U … │ 5'
AS 5' │ A  G  G  A  C … │             │ A  A  U  G … │ 3'
```
Part1 aligns column-by-column with Part1; Part2 aligns with Part2.

## Section 5: Template `_seq_group_row.html`

### Alignment table: handle `segment_sep` column

```html
{% if col.col_type == 'segment_sep' %}
  <td class="seq-segment-sep-col" rowspan="2" style="vertical-align:middle;padding:0 4px;border-left:2px dashed #cbd5e1;border-right:2px dashed #cbd5e1;">
    {% for lk in col.linker_tokens %}
      <span class="seq-container seq-wide" style="background-color:rgba(112,203,248,1);">{{ lk.char }}</span>
    {% endfor %}
  </td>
```

### Any flat token rendering loops: handle SEP and LINKER_DASH

```html
{% if token.type == 'SEP' %}
  <span class="seq-seg-divider">&#124;</span>
{% elif token.type == 'LINKER_DASH' %}
  <span class="seq-linker-dash">{{ token.char }}</span>
{% else %}
  ... existing rendering ...
{% endif %}
```

### CSS additions

```css
.seq-seg-divider   { color: #94a3b8; margin: 0 4px; font-weight: bold; }
.seq-linker-dash   { color: #94a3b8; letter-spacing: 1px; font-style: italic; }
.seq-segment-sep-col { background: #f8fafc; }
```

## Upload Flow

1. **`register_seq` (Step A):** Upload CSV with columns `Project, Target, Seq_type, Modify_seq, Strand_MWs, Parents, Remarks`. Naked sequence extraction already correct (no code change). `add_o_to_all_rules_safe()` used for linker_seq.
2. **`upload_delivery_info` (Step B):** Same `add_o_to_all_rules_safe()` fix applies.

## What Does Not Change

- Model fields and migrations — none
- `align_duplex_tokens()` — unchanged
- `add_o_to_all_rules()` — unchanged (only the call site changes)
- Naked sequence extraction in `save_deliveries()` — already works
- Single-segment sequences — all existing paths unchanged; `detect_embedded_linker()` returns `None`
