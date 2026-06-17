# Compound List — UI Polish (Columns + Batch Separation + Summary Chart Legend)

**Date:** 2026-06-17
**Scope:** Mostly `templates/compound_list.html` (CSS + HTML + JS). Minimal `app01/views.py` additions: pre-compute two derived fields on `row_data` (colored token list per strand, IC50 formatted string).

---

## Goal

Three improvements to `/compounds/`:

1. **Expand column set** from 6 to 11 columns so all key compound + experiment metadata is visible without expanding rows
2. **Visually separate batch groups** with a thin spacer row so adjacent groups don't blend together
3. **Rework batch summary chart** with constrained proportions and a legend identifying each compound by colour

---

## Backup

Before any edit:
```bash
cp templates/compound_list.html templates/compound_list.html.bak3
```

---

## Change 1 — Full 11-Column Table (A4)

### Column order (left to right)

| # | Header | Source | Vitro row | Vivo row |
|---|--------|--------|-----------|----------|
| 1 | ID | `compound.compound_id` | value | value |
| 2 | 序列 (AS/SS) | `strand_map` modify_seq (colored tokens) | value | value |
| 3 | 项目 | `compound.project` | value | value |
| 4 | 靶点 | `compound.target_name` | value | value |
| 5 | IC50 | `g.summary.ic50_nm` | value | `—` |
| 6 | MaxKD% | `g.summary.max_kd_pct` | value | `—` |
| 7 | Cell line | `experiment.cell_line` | value | `—` |
| 8 | 动物模型 | `animal_species` + `animal_strain` | `—` | value |
| 9 | 剂量 | `experiment.dose_info` | `—` | value |
| 10 | 实验类型 | `experiment.assay_name` | value | value |
| 11 | 批次 | `experiment.batch_label` | value | value |
| 12 | (chevron ▼) | — | value | value |

Note: kept 批次 and 项目/靶点 even though they may repeat across rows of the same group — explicit per-row redundancy is desired.

### Column removed

The current **"类型"** column (体外/体内 tag) is removed. Reasons:
- Batch group header (`T1 · 体外`) already states the type
- Row left-border stripe (blue for vitro, orange for vivo) signals the type visually
- In "按化合物" grouping mode, the row left-border continues to indicate type

### Column widths

```html
<colgroup>
  <col style="width:130px;">  <!-- ID -->
  <col style="width:420px;">  <!-- 序列 -->
  <col style="width:90px;">   <!-- 项目 -->
  <col style="width:90px;">   <!-- 靶点 -->
  <col style="width:70px;">   <!-- IC50 -->
  <col style="width:80px;">   <!-- MaxKD% -->
  <col style="width:100px;">  <!-- Cell line -->
  <col style="width:130px;">  <!-- 动物模型 -->
  <col style="width:90px;">   <!-- 剂量 -->
  <col style="width:140px;">  <!-- 实验类型 -->
  <col style="width:80px;">   <!-- 批次 -->
  <col style="width:30px;">   <!-- chevron -->
</colgroup>
```

Total min-width: **1450px** → wrap table in `<div class="cl-tbl-wrap">` with `overflow-x: auto`.

### Sequence cell rendering

**Important:** the existing compound_list expand area currently shows the sequence as plain `{{ modify_seq }}` text inside a single colored pill. We need to upgrade it to per-character colored nucleotides — the same rendering style used in `_seq_group_row.html` line 100–106 (`seq-container` + per-`item.type` background color).

**View change** — `compound_list` view computes one extra field per strand using existing `get_modify_seq_colored()`:

```python
from .views import get_modify_seq_colored, get_color_map

# At top of compound_list, build color_map once:
color_map = get_color_map()

# When constructing strand_map for each row:
strand_map = []
for s in compound.strands.all():
    strand_map.append({
        'strand_type': s.strand_type,
        'modify_seq': s.modify_seq,
        'colored_items': get_modify_seq_colored(
            s.modify_seq, selected_seq_type=s.strand_type, seq_type=s.strand_type,
            color_map=color_map,
        ),
    })
```

Each `colored_items` entry is a dict with `char` and `type` fields (per-nucleotide).

**Template rendering** (per strand) — exactly the pattern from `_seq_group_row.html`:

```html
<td class="cl-seq-cell">
  {% for strand in row.strand_map %}
  <div class="cl-seq-line {% if strand.strand_type == 'SS' %}cl-seq-ss-bg{% else %}cl-seq-as-bg{% endif %}">
    <span class="cl-seq-strand-label">{{ strand.strand_type }}</span>
    {% for item in strand.colored_items %}
      <span class="seq-container {% if item.char == 's' or item.char == 'o' or item.char == 'ss' %}seq-narrow{% else %}seq-wide{% endif %}"
            style="background-color:{% if item.type == 'normal' %}rgb(189,199,248){% elif item.type == 'f' %}rgb(22,245,22){% elif item.type == 'm' %}rgb(68,68,68);color:white{% elif item.type == 'd' or item.type == 'ss' or item.type == 'moe' or item.type == 'OCF3' or item.type == 'GNA' or item.type == 'I' %}rgb(212,93,245){% elif item.type == 's' %}rgb(253,246,61){% elif item.type == 'o' %}rgb(198,196,198){% elif item.type == 'TNA' %}rgb(245,86,86);color:white{% elif item.type == 'unknown' %}rgb(163,163,163){% elif item.type == 'others' %}rgba(112,203,248,1){% endif %};">{{ item.char }}</span>
    {% endfor %}
  </div>
  {% endfor %}
</td>
```

`seq-container`, `seq-narrow`, `seq-wide` styles already exist in `static/css/styles.css` (used by `_seq_group_row.html`). No new chemistry parsing logic.

**Replace** the existing plain-text expand-area rendering (compound_list.html lines 430–435: `<code class="cl-seq cl-seq-as">{{ modify_seq }}</code>`) with the same colored-item pattern so both the new column and the expand area stay consistent.

CSS additions:
```css
.cl-seq-cell { min-width: 380px; max-width: 480px; }
.cl-seq-line {
  display: inline-flex; flex-wrap: wrap; gap: 0; align-items: center;
  border-radius: 3px; padding: 2px 4px; margin-bottom: 3px;
  font-family: monospace;
}
.cl-seq-as-bg { background: #fef9c3; }   /* AS strand row = yellow */
.cl-seq-ss-bg { background: #f0fdf4; }   /* SS strand row = green */
.cl-seq-strand-label { font-size: 9px; font-weight: 700; color: #64748b; margin-right: 4px; }
```

### Non-applicable cells

Cells that don't apply to the row's exp_type show:
```html
<td><span class="cl-dim">—</span></td>
```
CSS: `.cl-dim { color: #cbd5e1; font-style: italic; }`

### Wrapper for horizontal scroll

Note: `.cl-tbl-wrap` is already used inside the expand area for a different purpose. The new outer wrapper uses a fresh class name `.cl-table-scroll`:

```html
<div class="cl-table-scroll">
  <table class="cl-table">...</table>
</div>
```
```css
.cl-table-scroll {
  background: #fff; border: 1px solid #e2e8f0; border-radius: 8px;
  overflow-x: auto;
}
.cl-table { min-width: 1450px; }
```

---

## Change 2 — Batch Group Spacer (A2)

Insert a thin gap row between adjacent batch groups in `applyBatchGrouping()`:

```javascript
// after appending each group's data rows, if a *next* group follows:
if (hasNextGroup) {
  var gapTr = document.createElement('tr');
  gapTr.className = 'cl-batch-gap';
  var gapTd = document.createElement('td');
  gapTd.setAttribute('colspan', '12');  // matches new column count
  gapTr.appendChild(gapTd);
  tbody.appendChild(gapTr);
}
```

CSS:
```css
.cl-batch-gap td {
  padding: 0; height: 14px;
  background: #f0f4f8; border: none;
}
```

Existing batch group header styling (blue/orange left stripe + tinted background) is unchanged.

`restoreCompoundOrder()` already removes `.cl-gh` rows — also remove `.cl-batch-gap` rows in that function.

---

## Change 3 — Summary Chart Layout + Legend (A1)

### Current state

Inside the group header `<td>`, the chart sits in:
```html
<div class="cl-bgh-chart-wrap">
  <div class="cl-bgh-chart"></div>  <!-- height:160px, width:100% -->
</div>
```

### New layout

Split the chart area into a horizontal flex: chart left (~60%), legend right column:

```html
<div class="cl-bgh-row">
  <div class="cl-bgh-chart-side">
    <div class="cl-bgh-ytitle">mRNA 残余 (%)</div>   <!-- vitro -->
    <!-- OR: <div class="cl-bgh-ytitle">{{ readout_type }}</div> for vivo -->
    <div id="cl-bgh-{key}" class="cl-bgh-chart"></div>
  </div>
  <div class="cl-bgh-legend">
    <div class="cl-bgh-legend-item">
      <span class="cl-bgh-dot" style="background:#3b82f6"></span>
      BPR_3M03FN01 <span class="cl-bgh-extra">IC50 0.23</span>
    </div>
    ...
  </div>
</div>
```

CSS:
```css
.cl-bgh-row {
  display: flex; gap: 14px; align-items: center;
  padding: 2px 12px 10px;
}
.cl-bgh-chart-side {
  flex: 0 0 60%; max-width: 520px;
  display: flex; flex-direction: column;
}
.cl-bgh-ytitle {
  font-size: 10px; color: #1e3a5f; margin-bottom: 3px;
  font-weight: 600;
}
.cl-bgh-chart {
  height: 140px;     /* was 160 */
  width: 100%;
}
.cl-bgh-legend {
  flex: 1; min-width: 160px;
  display: flex; flex-direction: column; gap: 5px;
  font-size: 11px; color: #1e3a5f;
}
.cl-bgh-legend-item { white-space: nowrap; }
.cl-bgh-dot {
  display: inline-block; width: 9px; height: 9px; border-radius: 50%;
  margin-right: 5px; vertical-align: middle;
}
.cl-bgh-extra { color: #64748b; margin-left: 6px; }
```

### Legend content rules

- Each line: `● <color dot> <compound_id> <optional extra>`
- **Vitro:** append `IC50 <value>` from `g.summary.ic50` (nM, rounded to 2 decimals; show `—` if null)
- **Vivo:** compound ID only (no per-line numeric — time-series has no single summary)

### Chart label above the plot

- **Vitro:** `mRNA 残余 (%)` (matches existing per-row chart title default)
- **Vivo:** `readout_type` from the first experiment in the group (e.g., `肿瘤体积`)

### `renderBatchSummary()` JS changes

Function signature becomes:
```javascript
function renderBatchSummary(chartId, expIds, kind, readoutLabel)
```

- `chartId`: container id (unchanged)
- `expIds`: array of `{id, kind, compound_id, ic50_str}` — now carries compound_id and pre-formatted IC50 for legend rendering
- `kind`: `'vitro'` or `'vivo'` (used for axes + extra column)
- `readoutLabel`: string for the y-axis title

After plotting Flot, inject the legend column from `expIds` into the sibling `.cl-bgh-legend` div (located by id-suffix lookup).

### `applyBatchGrouping()` changes for legend data

When collecting `groupExpIds`, also collect `compound_id` and `ic50_str`:
```javascript
groupExpIds.push({
  id: parseInt(vtEl.id.replace('cl-vt-', '')),
  kind: 'vitro',
  compound_id: gp.dr.getAttribute('data-cid'),       // new data attribute on cl-dr
  ic50_str: gp.dr.getAttribute('data-ic50') || ''     // new data attribute
});
```

So the data row `<tr class="cl-dr">` must carry:
```html
<tr class="cl-dr"
    data-idx="..."
    data-batch="..."
    data-type="..."
    data-cid="{{ row.compound.compound_id }}"
    data-ic50="{{ row.group.summary.ic50_str|default:'' }}">
```

The Django template already has compound_id; `ic50_str` is a small derived field added in `compound_list` view (`f"{summary.ic50_nm:.2f}"` if `summary.ic50_nm is not None` else `''`).

---

## Files Changed

| File | Change |
|------|--------|
| `templates/compound_list.html` | CSS + HTML (table structure) + JS (`applyBatchGrouping`, `renderBatchSummary`) |
| `app01/views.py` | Pre-compute `colored_html` per strand + `ic50_str` in `compound_list` view (minimal: add 2 fields to row_data; no new helpers) |
| `templates/compound_list.html.bak3` | Snapshot before edits |

No other files touched.

---

## Success Criteria

1. Page renders 11 columns + chevron; horizontal scroll appears when viewport <1450px
2. Sequence cell shows AS (yellow) + SS (green) two rows with colored chemistry tokens, wrapping within ~420px cell
3. Non-applicable cells (vitro/vivo specific) show italic gray `—`
4. Adjacent batch groups separated by a 14px gray gap row
5. Batch summary chart now occupies ~60% width (max 520px); legend appears in right column
6. Vitro legend rows show `● compound_id  IC50 <value>`; vivo legend rows show `● compound_id` only
7. Chart label above plot reads `mRNA 残余 (%)` (vitro) or the upload-specified readout name (vivo)
8. Switching grouping to "按化合物" still works; group header rows + gap rows are removed; chart rendering still works on row expand
9. `.bak3` file exists before any edit
