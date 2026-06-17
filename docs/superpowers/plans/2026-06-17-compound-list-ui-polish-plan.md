# Compound List UI Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the `/compounds/` page to 12 columns (with per-character colored Sequence cell), separate batch groups with a spacer row, and split the batch summary chart into chart + legend.

**Architecture:** Frontend-heavy; backend gets two small derived fields. `templates/compound_list.html` (CSS + HTML + JS) drives the layout. `app01/views.py` pre-computes `strand_map[*].colored_items` (via existing `get_modify_seq_colored()`) and `row.ic50_str` so the template can render without business logic. JS functions `applyBatchGrouping` / `restoreCompoundOrder` / `renderBatchSummary` are updated for new column count, gap rows, and chart-with-legend layout.

**Tech Stack:** Django 5.1 template, vanilla JS, jQuery, Flot.js (`/static/vendors/flot/jquery.flot.js`).

**No test suite:** the project has no pytest setup (`app01/tests.py` is empty per CLAUDE.md). Verification is via the dev server in a browser after each task.

---

## File Structure

| File | Change |
|------|--------|
| `templates/compound_list.html` | CSS additions, table thead/tbody rewrite, expand-area sequence upgrade, JS function rewrites |
| `app01/views.py` | `compound_list()` view extends row_data with `strand_map` dicts (`colored_items`) and `ic50_str` |
| `templates/compound_list.html.bak3` | Snapshot before edits (Task 1) |

---

## Pre-flight

Confirm the dev server is running so each task can be verified in the browser:

```bash
source venv/bin/activate
python manage.py runserver  # default http://localhost:8001 per CLAUDE.md hints
```

Visit `http://localhost:8001/compounds/` — should currently render the 10-column table.

---

### Task 1: Backup current template

**Files:**
- Create: `templates/compound_list.html.bak3`

- [ ] **Step 1: Copy current template**

```bash
cp templates/compound_list.html templates/compound_list.html.bak3
```

- [ ] **Step 2: Verify backup exists, same size as live**

```bash
ls -lh templates/compound_list.html templates/compound_list.html.bak3
```

Expected: both files exist, same byte count.

- [ ] **Step 3: Commit**

```bash
git add templates/compound_list.html.bak3
git commit -m "chore: snapshot compound_list.html before UI polish"
```

---

### Task 2: View — extend `row_data` with colored strand items + ic50 string

**Files:**
- Modify: `app01/views.py` — `compound_list()` function (around lines 949–1037)

Currently `strand_map` is a list of tuples and `row_data` has no `ic50_str`:

```python
strand_map = [(s.strand_type, s.modify_seq) for s in compound.strands.all()]
```

The new shape:
- `strand_map` becomes a list of dicts: `{strand_type, modify_seq, colored_items}`
- `row_data` entries get `ic50_str` field (formatted `IC50` from `g.summary.ic50_nm`, or `''`)
- A single `color_map` is computed once per request (outside the loop)

- [ ] **Step 1: Locate the `compound_list` view**

```bash
grep -n "def compound_list" app01/views.py
```

Expected: single match around line 949.

- [ ] **Step 2: Add color_map import-time setup at top of the function**

Find this block in `compound_list()`:

```python
    row_data = []
    cl_invivo_charts = []
    cl_vitro_charts = []
    for compound in page_obj:
```

Replace with:

```python
    row_data = []
    cl_invivo_charts = []
    cl_vitro_charts = []
    color_map = get_color_map()  # one DB hit; reused across all rows
    for compound in page_obj:
```

- [ ] **Step 3: Change `strand_map` construction**

Find this exact line in `compound_list()`:

```python
        strand_map = [(s.strand_type, s.modify_seq) for s in compound.strands.all()]
```

Replace with:

```python
        strand_map = [
            {
                'strand_type': s.strand_type,
                'modify_seq': s.modify_seq,
                'colored_items': get_modify_seq_colored(
                    s.modify_seq, s.strand_type, s.strand_type, color_map=color_map
                ),
            }
            for s in compound.strands.all()
        ]
```

- [ ] **Step 4: Add `ic50_str` to each row_data entry**

Find the existing `row_data.append({...})` call (around line 1015):

```python
            row_data.append({
                'compound': compound,
                'strand_map': strand_map,
                'group': g,
            })
```

Replace with:

```python
            ic50_val = getattr(getattr(exp, 'summary', None), 'ic50_nm', None)
            ic50_str = f'{ic50_val:.2f}' if ic50_val is not None else ''
            row_data.append({
                'compound': compound,
                'strand_map': strand_map,
                'group': g,
                'ic50_str': ic50_str,
            })
```

- [ ] **Step 5: Restart dev server, reload `/compounds/`**

The page should still render exactly the same as before (template hasn't been changed yet to consume new fields, but the old `{% for strand_type, modify_seq in row.strand_map %}` tuple-unpack in the expand area now sees a **dict**, not a tuple). Verify the page still loads.

Expected outcome: **Template will warn or break** because the existing expand-area loop relies on tuple unpacking. We accept this temporarily — Task 5 fixes the expand area. To avoid a fully broken page in between, do a quick patch:

- [ ] **Step 6: Quick patch the existing expand-area loop to dict access**

Find this exact block (around lines 431–434):

```html
            {% for strand_type, modify_seq in row.strand_map %}
            <div class="cl-seq-row">
              <span class="cl-sl">{{ strand_type }}</span>
              <code class="cl-seq {% if strand_type == 'SS' %}cl-seq-ss{% else %}cl-seq-as{% endif %}">{{ modify_seq }}</code>
            </div>
            {% endfor %}
```

Replace with:

```html
            {% for strand in row.strand_map %}
            <div class="cl-seq-row">
              <span class="cl-sl">{{ strand.strand_type }}</span>
              <code class="cl-seq {% if strand.strand_type == 'SS' %}cl-seq-ss{% else %}cl-seq-as{% endif %}">{{ strand.modify_seq }}</code>
            </div>
            {% endfor %}
```

This keeps the existing expand area visually identical while supporting the new dict shape.

- [ ] **Step 7: Reload `/compounds/`**

The page should now render identically to before. Open any row's expand and confirm the AS/SS pills still display the plain modify_seq text.

- [ ] **Step 8: Commit**

```bash
git add app01/views.py templates/compound_list.html
git commit -m "feat: precompute strand colored_items + ic50_str in compound_list view"
```

---

### Task 3: CSS additions

**Files:**
- Modify: `templates/compound_list.html` — add CSS block after existing `.cl-bgh-chart { ... }` definition (around line 284)

We add: `.cl-table-scroll` outer wrapper, `.cl-seq-cell` + `.cl-seq-line`, `.cl-batch-gap` spacer row, `.cl-bgh-row` + chart/legend split styles.

- [ ] **Step 1: Locate the CSS insertion point**

```bash
grep -n "cl-bgh-chart {" templates/compound_list.html
```

Expected: line where the `.cl-bgh-chart { height: 160px; width: 100%; }` definition exists (around line 281).

- [ ] **Step 2: Insert new CSS block**

Use the Edit tool. Find this exact block:

```css
.cl-bgh-chart-wrap {
  padding: 2px 12px 10px;
}
.cl-bgh-chart {
  height: 160px;
  width: 100%;
}
```

Replace with:

```css
.cl-bgh-chart-wrap {
  padding: 2px 12px 10px;
}
.cl-bgh-chart {
  height: 140px;
  width: 100%;
}

/* outer table scroll wrapper (12 columns, min-width 1450px) */
.cl-table-scroll {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow-x: auto;
}
.cl-table { min-width: 1450px; }

/* sequence column cell (AS + SS, per-character colored) */
.cl-seq-cell {
  min-width: 380px;
  max-width: 480px;
}
.cl-seq-line {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 0;
  align-items: center;
  border-radius: 3px;
  padding: 2px 4px;
  margin-bottom: 3px;
  font-family: monospace;
}
.cl-seq-as-bg { background: #fef9c3; }
.cl-seq-ss-bg { background: #f0fdf4; }
.cl-seq-strand-label {
  font-size: 9px;
  font-weight: 700;
  color: #64748b;
  margin-right: 4px;
}

/* gap row between batch groups (only visible in batch grouping mode) */
.cl-batch-gap td {
  padding: 0;
  height: 14px;
  background: #f0f4f8;
  border: none;
}

/* batch summary chart: chart left + legend right */
.cl-bgh-row {
  display: flex;
  gap: 14px;
  align-items: center;
  padding: 2px 12px 10px;
}
.cl-bgh-chart-side {
  flex: 0 0 60%;
  max-width: 520px;
  display: flex;
  flex-direction: column;
}
.cl-bgh-ytitle {
  font-size: 10px;
  color: #1e3a5f;
  font-weight: 600;
  margin-bottom: 3px;
}
.cl-bgh-legend {
  flex: 1;
  min-width: 160px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 11px;
  color: #1e3a5f;
}
.cl-bgh-legend-item { white-space: nowrap; }
.cl-bgh-dot {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  margin-right: 5px;
  vertical-align: middle;
}
.cl-bgh-extra { color: #64748b; margin-left: 6px; }
```

- [ ] **Step 3: Reload `/compounds/`**

Page should look identical to before. No JS errors. The chart in batch grouping mode might be slightly shorter (140px instead of 160px) — that's the only visible change.

- [ ] **Step 4: Commit**

```bash
git add templates/compound_list.html
git commit -m "feat: add CSS for new compound list columns, batch gap, chart+legend layout"
```

---

### Task 4: Template — replace thead, add table-scroll wrapper, define colgroup

**Files:**
- Modify: `templates/compound_list.html` — table thead block (around lines 350–365) and the `<table>` opening tag

The existing thead has 10 columns. We replace it with 12 columns, add a `<colgroup>` for widths, and wrap the `<table>` in `<div class="cl-table-scroll">`.

- [ ] **Step 1: Locate the existing thead and table tag**

```bash
grep -n "<table class=\"cl-table\"" templates/compound_list.html
grep -n "<th>化合物" templates/compound_list.html
```

- [ ] **Step 2: Replace the thead + table opening**

Find this exact block:

```html
<table class="cl-table">
  <thead>
    <tr>
      <th>化合物</th>
      <th>类型</th>
      <th class="r">IC50 (nM)</th>
      <th class="r">MaxKD%</th>
      <th>批次</th>
      <th>Cell Line</th>
      <th>动物模型</th>
      <th>剂量</th>
      <th>靶点 / 项目</th>
      <th></th>
    </tr>
  </thead>
```

Replace with:

```html
<div class="cl-table-scroll">
<table class="cl-table">
  <colgroup>
    <col style="width:130px;"><col style="width:420px;"><col style="width:90px;"><col style="width:90px;">
    <col style="width:80px;"><col style="width:80px;"><col style="width:100px;"><col style="width:130px;">
    <col style="width:90px;"><col style="width:140px;"><col style="width:80px;"><col style="width:30px;">
  </colgroup>
  <thead>
    <tr>
      <th>ID</th>
      <th>序列 (AS / SS)</th>
      <th>项目</th>
      <th>靶点</th>
      <th class="r">IC50 (nM)</th>
      <th class="r">MaxKD%</th>
      <th>Cell line</th>
      <th>动物模型</th>
      <th>剂量</th>
      <th>实验类型</th>
      <th>批次</th>
      <th></th>
    </tr>
  </thead>
```

- [ ] **Step 3: Close the wrapper div after `</table>`**

Find this block (around lines 549–553):

```html
  {% endfor %}
  </tbody>
</table>

{% else %}
```

Replace with:

```html
  {% endfor %}
  </tbody>
</table>
</div>

{% else %}
```

- [ ] **Step 4: Reload `/compounds/`**

Expected: the table header now shows 12 columns. The data rows are still the old 10 cells, so columns will be visibly misaligned with the header — this is fixed in Task 5. The page **will look broken** but should not throw JS errors.

- [ ] **Step 5: Commit**

```bash
git add templates/compound_list.html
git commit -m "feat: rewrite compound list thead to 12 columns + add scroll wrapper"
```

---

### Task 5: Template — rewrite data row (`cl-dr`) with 12 cells and colored Sequence

**Files:**
- Modify: `templates/compound_list.html` — `cl-dr` row block (lines 370–421)

The new row has 12 cells in this order: ID, 序列, 项目, 靶点, IC50, MaxKD%, Cell line, 动物模型, 剂量, 实验类型, 批次, chevron.

- [ ] **Step 1: Locate the data row**

```bash
grep -n "<tr class=\"cl-dr\"" templates/compound_list.html
```

- [ ] **Step 2: Replace the entire `<tr class="cl-dr">...</tr>` block**

Find this exact block (the existing data row from `<tr class="cl-dr"` through `</tr>` just before the comment `{# ── expand row ── #}`):

```html
    <tr class="cl-dr"
        data-compound="{{ row.compound.compound_id }}"
        data-batch="{{ row.group.experiment.batch_label }}"
        data-type="{{ row.group.experiment.exp_type }}"
        data-idx="{{ forloop.counter }}"
        onclick="toggleRow({{ forloop.counter }})">
      <td>
        <a href="{% url 'compound_detail' row.compound.compound_id %}"
           class="cl-cid-link"
           onclick="event.stopPropagation()">{{ row.compound.compound_id }}</a>
      </td>
      <td>
        <span class="cl-tag {% if row.group.experiment.exp_type == 'in_vitro' %}cl-tag-vitro{% else %}cl-tag-vivo{% endif %}">
          {{ row.group.tag_label }}
        </span>
      </td>
      <td class="cl-num">
        {% if row.group.header_ic50 is not None %}
          <span class="cl-ic50-good">{{ row.group.header_ic50|floatformat:2 }}</span>
        {% else %}
          <span class="cl-dim">—</span>
        {% endif %}
      </td>
      <td class="cl-num">
        {% if row.group.header_maxkd is not None %}
          {{ row.group.header_maxkd|floatformat:0 }}%
        {% else %}
          <span class="cl-dim">—</span>
        {% endif %}
      </td>
      <td class="cl-batch-id">{{ row.group.experiment.batch_label }}</td>
      <td class="cl-meta" style="font-size:11px;color:#64748b;">
        {% if row.group.experiment.exp_type == 'in_vitro' %}
          {% if row.group.experiment.cell_line %}{{ row.group.experiment.cell_line }}{% else %}<span class="cl-dim">—</span>{% endif %}
        {% else %}<span class="cl-dim">—</span>{% endif %}
      </td>
      <td class="cl-meta" style="font-size:11px;color:#64748b;">
        {% if row.group.experiment.exp_type == 'in_vivo' %}
          {% if row.group.experiment.animal_species %}{{ row.group.experiment.animal_species }}{% if row.group.experiment.animal_strain %} {{ row.group.experiment.animal_strain }}{% endif %}{% else %}<span class="cl-dim">—</span>{% endif %}
        {% else %}<span class="cl-dim">—</span>{% endif %}
      </td>
      <td class="cl-meta" style="font-size:11px;color:#64748b;">
        {% if row.group.experiment.exp_type == 'in_vivo' %}
          {% if row.group.experiment.dose_info %}{{ row.group.experiment.dose_info }}{% else %}<span class="cl-dim">—</span>{% endif %}
        {% else %}<span class="cl-dim">—</span>{% endif %}
      </td>
      <td class="cl-meta">
        {% if row.compound.target_name %}{{ row.compound.target_name }}{% endif %}
        {% if row.compound.project %}<span class="cl-proj">{{ row.compound.project }}</span>{% endif %}
      </td>
      <td class="cl-chevron">▼</td>
    </tr>
```

Replace with:

```html
    <tr class="cl-dr"
        data-compound="{{ row.compound.compound_id }}"
        data-batch="{{ row.group.experiment.batch_label }}"
        data-type="{{ row.group.experiment.exp_type }}"
        data-idx="{{ forloop.counter }}"
        data-cid="{{ row.compound.compound_id }}"
        data-ic50="{{ row.ic50_str }}"
        onclick="toggleRow({{ forloop.counter }})">
      <td>
        <a href="{% url 'compound_detail' row.compound.compound_id %}"
           class="cl-cid-link"
           onclick="event.stopPropagation()">{{ row.compound.compound_id }}</a>
      </td>
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
      <td class="cl-meta">
        {% if row.compound.project %}<span class="cl-proj">{{ row.compound.project }}</span>{% else %}<span class="cl-dim">—</span>{% endif %}
      </td>
      <td class="cl-meta">
        {% if row.compound.target_name %}{{ row.compound.target_name }}{% else %}<span class="cl-dim">—</span>{% endif %}
      </td>
      <td class="cl-num">
        {% if row.group.experiment.exp_type == 'in_vitro' and row.group.header_ic50 is not None %}
          <span class="cl-ic50-good">{{ row.group.header_ic50|floatformat:2 }}</span>
        {% else %}
          <span class="cl-dim">—</span>
        {% endif %}
      </td>
      <td class="cl-num">
        {% if row.group.experiment.exp_type == 'in_vitro' and row.group.header_maxkd is not None %}
          {{ row.group.header_maxkd|floatformat:0 }}%
        {% else %}
          <span class="cl-dim">—</span>
        {% endif %}
      </td>
      <td class="cl-meta" style="font-size:11px;color:#64748b;">
        {% if row.group.experiment.exp_type == 'in_vitro' and row.group.experiment.cell_line %}
          {{ row.group.experiment.cell_line }}
        {% else %}<span class="cl-dim">—</span>{% endif %}
      </td>
      <td class="cl-meta" style="font-size:11px;color:#64748b;">
        {% if row.group.experiment.exp_type == 'in_vivo' and row.group.experiment.animal_species %}
          {{ row.group.experiment.animal_species }}{% if row.group.experiment.animal_strain %} {{ row.group.experiment.animal_strain }}{% endif %}
        {% else %}<span class="cl-dim">—</span>{% endif %}
      </td>
      <td class="cl-meta" style="font-size:11px;color:#64748b;">
        {% if row.group.experiment.exp_type == 'in_vivo' and row.group.experiment.dose_info %}
          {{ row.group.experiment.dose_info }}
        {% else %}<span class="cl-dim">—</span>{% endif %}
      </td>
      <td class="cl-meta">{{ row.group.experiment.assay_name|default:"—" }}</td>
      <td class="cl-batch-id">{{ row.group.experiment.batch_label }}</td>
      <td class="cl-chevron">▼</td>
    </tr>
```

- [ ] **Step 3: Update expand-row colspan from 10 to 12**

Find this exact line:

```html
    <tr class="cl-er" id="er-{{ forloop.counter }}">
      <td colspan="10">
```

Replace with:

```html
    <tr class="cl-er" id="er-{{ forloop.counter }}">
      <td colspan="12">
```

- [ ] **Step 4: Reload `/compounds/`**

Expected:
- Table renders 12 columns aligned with header
- Sequence cell shows AS (yellow background) + SS (green background) with per-character colored nucleotides
- IC50/MaxKD/Cell line columns are `—` for in_vivo rows; 动物模型/剂量 are `—` for in_vitro rows
- 实验类型 column shows the assay_name
- 批次 column still present (redundant with batch group header by design)
- Horizontal scroll appears if viewport <1450px

- [ ] **Step 5: Commit**

```bash
git add templates/compound_list.html
git commit -m "feat: rewrite compound list data row to 12 cells with colored sequence"
```

---

### Task 6: Template — upgrade expand-area sequences to per-character coloring

**Files:**
- Modify: `templates/compound_list.html` — expand-area seq block (currently lines 429–438)

The expand area still shows plain `{{ strand.modify_seq }}` text. Make it consistent with the new column by reusing the same per-char `seq-container` rendering. This is a small visual polish; it also serves as a fallback in case the user collapses the new column or grouping changes.

- [ ] **Step 1: Locate the expand-area seq block**

```bash
grep -n "cl-seq-area" templates/compound_list.html
```

- [ ] **Step 2: Replace the expand-area seq block**

Find this exact block (around lines 429–438; this is the version after Task 2 Step 6's patch):

```html
          {# sequences #}
          {% if row.strand_map %}
          <div class="cl-seq-area">
            {% for strand in row.strand_map %}
            <div class="cl-seq-row">
              <span class="cl-sl">{{ strand.strand_type }}</span>
              <code class="cl-seq {% if strand.strand_type == 'SS' %}cl-seq-ss{% else %}cl-seq-as{% endif %}">{{ strand.modify_seq }}</code>
            </div>
            {% endfor %}
          </div>
          {% endif %}
```

Replace with:

```html
          {# sequences (per-character colored, same style as main column) #}
          {% if row.strand_map %}
          <div class="cl-seq-area">
            {% for strand in row.strand_map %}
            <div class="cl-seq-line {% if strand.strand_type == 'SS' %}cl-seq-ss-bg{% else %}cl-seq-as-bg{% endif %}" style="margin-bottom:4px;">
              <span class="cl-seq-strand-label">{{ strand.strand_type }}</span>
              {% for item in strand.colored_items %}
                <span class="seq-container {% if item.char == 's' or item.char == 'o' or item.char == 'ss' %}seq-narrow{% else %}seq-wide{% endif %}"
                      style="background-color:{% if item.type == 'normal' %}rgb(189,199,248){% elif item.type == 'f' %}rgb(22,245,22){% elif item.type == 'm' %}rgb(68,68,68);color:white{% elif item.type == 'd' or item.type == 'ss' or item.type == 'moe' or item.type == 'OCF3' or item.type == 'GNA' or item.type == 'I' %}rgb(212,93,245){% elif item.type == 's' %}rgb(253,246,61){% elif item.type == 'o' %}rgb(198,196,198){% elif item.type == 'TNA' %}rgb(245,86,86);color:white{% elif item.type == 'unknown' %}rgb(163,163,163){% elif item.type == 'others' %}rgba(112,203,248,1){% endif %};">{{ item.char }}</span>
              {% endfor %}
            </div>
            {% endfor %}
          </div>
          {% endif %}
```

- [ ] **Step 3: Reload `/compounds/`, expand any row**

Expected: the AS / SS area inside expand now uses per-character coloring identical to the new Sequence column. No JS errors.

- [ ] **Step 4: Commit**

```bash
git add templates/compound_list.html
git commit -m "feat: per-character colored sequences in compound list expand area"
```

---

### Task 7: JS — `applyBatchGrouping` adds gap rows, colspan=12, carries cid+ic50 for legend

**Files:**
- Modify: `templates/compound_list.html` — `applyBatchGrouping()` function (around lines 745–842) and `restoreCompoundOrder()` (around line 843)

Three changes:
1. `colspan` `'10'` → `'12'`
2. Insert a `.cl-batch-gap` row before every group header except the first
3. Each entry in `groupExpIds` carries `compound_id` and `ic50_str` (used by `renderBatchSummary` in Task 8)
4. `restoreCompoundOrder` removes `.cl-batch-gap` rows too

- [ ] **Step 1: Update colspan in `applyBatchGrouping`**

Find this exact line:

```javascript
        td.setAttribute('colspan', '10');
```

Replace with:

```javascript
        td.setAttribute('colspan', '12');
```

- [ ] **Step 2: Expand `pairs` collection to carry compound + ic50 strings**

Find this exact block:

```javascript
    var pairs = [];
    tbody.querySelectorAll('tr.cl-dr').forEach(function (dr) {
      var idx = dr.getAttribute('data-idx');
      pairs.push({
        dr:    dr,
        er:    document.getElementById('er-' + idx),
        batch: dr.getAttribute('data-batch'),
        type:  dr.getAttribute('data-type'),
      });
    });
```

Replace with:

```javascript
    var pairs = [];
    tbody.querySelectorAll('tr.cl-dr').forEach(function (dr) {
      var idx = dr.getAttribute('data-idx');
      pairs.push({
        dr:    dr,
        er:    document.getElementById('er-' + idx),
        batch: dr.getAttribute('data-batch'),
        type:  dr.getAttribute('data-type'),
        cid:   dr.getAttribute('data-cid')  || '',
        ic50:  dr.getAttribute('data-ic50') || '',
      });
    });
```

- [ ] **Step 3: Expand `groupExpIds` push to include compound_id + ic50_str**

Find this exact block:

```javascript
        // collect exp IDs for this batch group
        var groupExpIds = [];
        groupPairs.forEach(function (gp) {
          if (!gp.er) return;
          var vtEl = gp.er.querySelector('.cl-chart-plot[id^="cl-vt-"]');
          var ivEl = gp.er.querySelector('.cl-chart-plot[id^="cl-iv-"]');
          if (vtEl) groupExpIds.push({ id: parseInt(vtEl.id.replace('cl-vt-', '')), kind: 'vitro' });
          if (ivEl) groupExpIds.push({ id: parseInt(ivEl.id.replace('cl-iv-', '')), kind: 'invivo' });
        });
```

Replace with:

```javascript
        // collect exp IDs for this batch group
        var groupExpIds = [];
        groupPairs.forEach(function (gp) {
          if (!gp.er) return;
          var vtEl = gp.er.querySelector('.cl-chart-plot[id^="cl-vt-"]');
          var ivEl = gp.er.querySelector('.cl-chart-plot[id^="cl-iv-"]');
          if (vtEl) groupExpIds.push({
            id:   parseInt(vtEl.id.replace('cl-vt-', '')),
            kind: 'vitro',
            cid:  gp.cid,
            ic50: gp.ic50,
          });
          if (ivEl) groupExpIds.push({
            id:   parseInt(ivEl.id.replace('cl-iv-', '')),
            kind: 'invivo',
            cid:  gp.cid,
            ic50: gp.ic50,
          });
        });
```

- [ ] **Step 4: Insert gap row before every group header except the first**

Find this exact block (just before `// build group header row`):

```javascript
    var lastKey = null;
    pairs.forEach(function (p) {
      var key = p.batch + '|' + p.type;
      if (key !== lastKey) {
        lastKey = key;
```

Replace with:

```javascript
    var lastKey = null;
    var isFirstGroup = true;
    pairs.forEach(function (p) {
      var key = p.batch + '|' + p.type;
      if (key !== lastKey) {
        // insert gap row before every group except the first
        if (!isFirstGroup) {
          var gapTr = document.createElement('tr');
          gapTr.className = 'cl-batch-gap';
          var gapTd = document.createElement('td');
          gapTd.setAttribute('colspan', '12');
          gapTr.appendChild(gapTd);
          tbody.appendChild(gapTr);
        }
        isFirstGroup = false;
        lastKey = key;
```

- [ ] **Step 5: Update `restoreCompoundOrder` to also remove `.cl-batch-gap` rows**

Find this exact block:

```javascript
  function restoreCompoundOrder() {
    var tbody = document.getElementById('cl-tbody');
    tbody.querySelectorAll('.cl-gh').forEach(function (el) { el.remove(); });
```

Replace with:

```javascript
  function restoreCompoundOrder() {
    var tbody = document.getElementById('cl-tbody');
    tbody.querySelectorAll('.cl-gh').forEach(function (el) { el.remove(); });
    tbody.querySelectorAll('.cl-batch-gap').forEach(function (el) { el.remove(); });
```

- [ ] **Step 6: Reload `/compounds/`**

Expected:
- In default "按批次+类型" mode: a 14px light-gray spacer row appears between adjacent batch groups (visible but not jarring)
- In "按化合物" mode (toggle the grouping dropdown): no group headers, no gap rows
- Toggling back to "按批次+类型" re-creates the spacers
- Batch summary chart still renders (no legend yet — Task 8)
- No JS console errors

- [ ] **Step 7: Commit**

```bash
git add templates/compound_list.html
git commit -m "feat: batch grouping inserts spacer rows + carries cid/ic50 for legend"
```

---

### Task 8: JS — `renderBatchSummary` produces chart + legend, chart container becomes flex row

**Files:**
- Modify: `templates/compound_list.html` — `renderBatchSummary()` (lines 675–721) and the chart container construction inside `applyBatchGrouping()` (lines 809–833)

The new behaviour:
- The container div is a 2-column flex (`.cl-bgh-row`): left side has y-axis label + Flot chart; right side has legend list
- For each compound: `● colored-dot compound_id [IC50 X.XX]` (vitro) or `● compound_id` (vivo)
- The y-axis title above the chart: `mRNA 残余 (%)` for vitro, `肿瘤体积` (or whatever `readout_type` value is) for vivo

To get the vivo `readout_type`, we look it up from `ivcCharts` (the existing JSON map keyed by `exp_id`).

- [ ] **Step 1: Replace `renderBatchSummary` body**

Find this exact block:

```javascript
  function renderBatchSummary(chartId, expIds) {
    var container = document.getElementById(chartId);
    if (!container || container.offsetWidth === 0) return;
    var series = [];
    var isVitro = expIds.length > 0 && expIds[0].kind === 'vitro';
    expIds.forEach(function (e, i) {
      var color = BGH_COLORS[i % BGH_COLORS.length];
      if (e.kind === 'vitro') {
        var d = vtDataMap[e.id];
        if (d && d.mrna_pts && d.mrna_pts.length) {
          series.push({ data: d.mrna_pts, color: color,
            lines: { show: true, lineWidth: 1.5 },
            points: { show: true, radius: 2 } });
        }
      } else {
        var d = ivcCharts.find(function (x) { return x.exp_id === e.id; });
        if (d && d.points && d.points.length) {
          series.push({ data: d.points, color: color,
            lines: { show: true, lineWidth: 1.5 },
            points: { show: true, radius: 2 } });
        }
      }
    });
    if (!series.length) return;
    var allY = [];
    series.forEach(function (s) {
      s.data.forEach(function (pt) { allY.push(pt[1]); });
    });
    var ymax = Math.max.apply(null, allY);
    var ymin = Math.min.apply(null, allY);
    var yAxisOpts;
    if (isVitro) {
      yAxisOpts = { min: 0, max: Math.max(ymax * 1.12, 110), labelWidth: 30 };
    } else {
      var ypad = Math.max((ymax - ymin) * 0.12, 2);
      yAxisOpts = { min: ymin - ypad, max: ymax + ypad, labelWidth: 30 };
    }
    try {
      $.plot(container, series, {
        xaxis: isVitro ? { ticks: LOG_TICKS, tickLength: 3 } : { tickLength: 3 },
        yaxis: yAxisOpts,
        grid: { hoverable: false, borderWidth: 1,
                borderColor: isVitro ? '#bfdbfe' : '#fed7aa' },
        legend: { show: false }
      });
    } catch (e) {}
  }
```

Replace with:

```javascript
  function renderBatchSummary(chartId, expIds) {
    var container = document.getElementById(chartId);
    if (!container || container.offsetWidth === 0) return;
    var legendEl = document.getElementById(chartId + '-legend');
    var titleEl  = document.getElementById(chartId + '-ytitle');
    var isVitro = expIds.length > 0 && expIds[0].kind === 'vitro';

    var series = [];
    var legendHtml = [];
    var readoutLabel = isVitro ? 'mRNA 残余 (%)' : '';

    expIds.forEach(function (e, i) {
      var color = BGH_COLORS[i % BGH_COLORS.length];
      var hasData = false;
      if (e.kind === 'vitro') {
        var d = vtDataMap[e.id];
        if (d && d.mrna_pts && d.mrna_pts.length) {
          series.push({ data: d.mrna_pts, color: color,
            lines: { show: true, lineWidth: 1.5 },
            points: { show: true, radius: 2 } });
          hasData = true;
        }
      } else {
        var d = ivcCharts.find(function (x) { return x.exp_id === e.id; });
        if (d && d.points && d.points.length) {
          series.push({ data: d.points, color: color,
            lines: { show: true, lineWidth: 1.5 },
            points: { show: true, radius: 2 } });
          hasData = true;
          if (!readoutLabel) readoutLabel = d.readout_type || '';
        }
      }
      if (hasData) {
        var extra = (e.kind === 'vitro' && e.ic50)
          ? '<span class="cl-bgh-extra">IC50 ' + e.ic50 + '</span>'
          : '';
        legendHtml.push(
          '<div class="cl-bgh-legend-item">' +
          '<span class="cl-bgh-dot" style="background:' + color + '"></span>' +
          (e.cid || '') + extra +
          '</div>'
        );
      }
    });

    if (titleEl) titleEl.textContent = readoutLabel;
    if (legendEl) legendEl.innerHTML = legendHtml.join('');

    if (!series.length) return;
    var allY = [];
    series.forEach(function (s) {
      s.data.forEach(function (pt) { allY.push(pt[1]); });
    });
    var ymax = Math.max.apply(null, allY);
    var ymin = Math.min.apply(null, allY);
    var yAxisOpts;
    if (isVitro) {
      yAxisOpts = { min: 0, max: Math.max(ymax * 1.12, 110), labelWidth: 30 };
    } else {
      var ypad = Math.max((ymax - ymin) * 0.12, 2);
      yAxisOpts = { min: ymin - ypad, max: ymax + ypad, labelWidth: 30 };
    }
    try {
      $.plot(container, series, {
        xaxis: isVitro ? { ticks: LOG_TICKS, tickLength: 3 } : { tickLength: 3 },
        yaxis: yAxisOpts,
        grid: { hoverable: false, borderWidth: 1,
                borderColor: isVitro ? '#bfdbfe' : '#fed7aa' },
        legend: { show: false }
      });
    } catch (e) {}
  }
```

- [ ] **Step 2: Replace the chart container construction inside `applyBatchGrouping`**

Find this exact block (inside `applyBatchGrouping`, after the `td.appendChild(headerDiv);` call):

```javascript
        // summary chart container
        if (groupExpIds.length) {
          var chartKey = p.batch.replace(/[^a-zA-Z0-9]/g, '_') + '_' + p.type;
          var chartId  = 'cl-bgh-' + chartKey;
          var chartWrap = document.createElement('div');
          chartWrap.className = 'cl-bgh-chart-wrap';
          var chartDiv = document.createElement('div');
          chartDiv.id = chartId;
          chartDiv.className = 'cl-bgh-chart';
          chartWrap.appendChild(chartDiv);
          td.appendChild(chartWrap);
          // render after layout settles (100ms head-start for table reflow)
          (function (cid, eids) {
            setTimeout(function () {
              (function tryBgh(n) {
                var el = document.getElementById(cid);
                if (el && el.offsetWidth > 0) {
                  renderBatchSummary(cid, eids);
                } else if (n > 0) {
                  setTimeout(function () { tryBgh(n - 1); }, 30);
                }
              })(20);
            }, 100);
          })(chartId, groupExpIds);
        }
```

Replace with:

```javascript
        // summary chart + legend (flex row: chart left, legend right)
        if (groupExpIds.length) {
          var chartKey = p.batch.replace(/[^a-zA-Z0-9]/g, '_') + '_' + p.type;
          var chartId  = 'cl-bgh-' + chartKey;

          var row = document.createElement('div');
          row.className = 'cl-bgh-row';

          var chartSide = document.createElement('div');
          chartSide.className = 'cl-bgh-chart-side';
          var ytitle = document.createElement('div');
          ytitle.className = 'cl-bgh-ytitle';
          ytitle.id = chartId + '-ytitle';
          ytitle.textContent = '';  // set by renderBatchSummary
          var chartDiv = document.createElement('div');
          chartDiv.id = chartId;
          chartDiv.className = 'cl-bgh-chart';
          chartSide.appendChild(ytitle);
          chartSide.appendChild(chartDiv);

          var legendDiv = document.createElement('div');
          legendDiv.className = 'cl-bgh-legend';
          legendDiv.id = chartId + '-legend';

          row.appendChild(chartSide);
          row.appendChild(legendDiv);
          td.appendChild(row);

          // render after layout settles (100ms head-start for table reflow)
          (function (cid, eids) {
            setTimeout(function () {
              (function tryBgh(n) {
                var el = document.getElementById(cid);
                if (el && el.offsetWidth > 0) {
                  renderBatchSummary(cid, eids);
                } else if (n > 0) {
                  setTimeout(function () { tryBgh(n - 1); }, 30);
                }
              })(20);
            }, 100);
          })(chartId, groupExpIds);
        }
```

- [ ] **Step 3: Reload `/compounds/`**

Expected:
- Each batch group header now shows: chart on the left (~60% width, max 520px), legend column on the right
- Vitro legend rows: `● BPR_xxx  IC50 0.23` (italic gray IC50 suffix)
- Vivo legend rows: `● BPR_xxx` only
- Chart label above the plot: `mRNA 残余 (%)` (vitro) or upload-specified readout name (vivo)
- Chart is shorter (140px) and not full-width
- No JS console errors

- [ ] **Step 4: Verify edge cases manually**

- Toggle grouping to "按化合物": group headers + gap rows disappear; rows return to compound order
- Toggle back to "按批次+类型": group headers + gap rows + chart + legend all re-appear correctly
- Expand a row: individual chart still renders inside the expand area (this was untouched)
- Click mRNA% / KD% toggle in expanded vitro row: individual chart re-renders correctly

- [ ] **Step 5: Commit**

```bash
git add templates/compound_list.html
git commit -m "feat: batch summary chart with right-column legend (cid + IC50 for vitro)"
```

---

### Task 9: Final verification

- [ ] **Step 1: Hard reload (Cmd-Shift-R) and walk through each acceptance criterion**

Verify each item from the spec's success criteria:

1. ✅ 12 columns + chevron; horizontal scroll under 1450px
2. ✅ Sequence cell: AS (yellow) + SS (green) two rows, per-character colored
3. ✅ Non-applicable cells (vitro/vivo specific) show italic gray `—`
4. ✅ Adjacent batch groups separated by 14px gray gap row
5. ✅ Batch summary chart ~60% width (max 520px); legend in right column
6. ✅ Vitro legend rows show `● compound_id  IC50 <value>`; vivo legend rows show `● compound_id` only
7. ✅ Chart label above plot: `mRNA 残余 (%)` (vitro) or upload readout name (vivo)
8. ✅ "按化合物" mode strips group headers + gap rows; chart rendering still works on row expand
9. ✅ `.bak3` file exists

- [ ] **Step 2: Check browser console for any JS errors**

Expected: no errors. If any, capture and fix before declaring done.

- [ ] **Step 3: Test with a wide variety of data**

- Paginate through several pages
- Use the filter bar: filter by project, target, search by compound_id
- Verify the table behavior is consistent across filtered/unfiltered states

- [ ] **Step 4: Final commit only if any fixes were made above**

```bash
git status
# if nothing changed, skip this step
git add templates/compound_list.html app01/views.py
git commit -m "fix: final compound list UI polish adjustments"
```

---

## Self-Review Checklist

- [x] **Spec coverage:**
  - A4 (11 columns + chevron): Tasks 2, 4, 5
  - Sequence rendering (per-char colored AS/SS): Tasks 2, 3, 5; also Task 6 for expand consistency
  - Horizontal scroll wrapper: Task 3 (`.cl-table-scroll`) + Task 4 (HTML)
  - "—" for non-applicable cells: Task 5
  - A2 (batch gap row): Task 3 (CSS) + Task 7 (JS insert + restoreCompoundOrder cleanup)
  - A1 (chart layout 60% + right legend): Task 3 (CSS) + Task 8 (JS)
  - Vitro legend with IC50, vivo with cid only: Task 8
  - Chart y-axis label from readout_type: Task 8
  - Backup `.bak3`: Task 1
  - View pre-compute (`colored_items`, `ic50_str`): Task 2

- [x] **No placeholders:** all code blocks are complete and runnable; no TBD/TODO/"implement later"

- [x] **Type consistency:**
  - `groupExpIds` push shape (`{id, kind, cid, ic50}`) is identical in Tasks 7 and 8
  - `chartId` format (`'cl-bgh-' + chartKey`) is consistent; ids `chartId + '-legend'` and `chartId + '-ytitle'` are created in Task 8 Step 2 and consumed in Task 8 Step 1
  - `strand_map[*]` is a dict with keys `strand_type / modify_seq / colored_items` everywhere (Task 2 view, Task 2 patched expand area, Task 5 column, Task 6 expand upgrade)
  - colspan `12` is used consistently (Tasks 4, 5, 7)
  - `row.ic50_str` written in Task 2 Step 4; read via `data-ic50` in Task 5; consumed via `gp.ic50` in Task 7; rendered via `e.ic50` in Task 8

- [x] **Class name collisions checked:** new wrapper class is `.cl-table-scroll` to avoid clashing with the existing `.cl-tbl-wrap` inside the expand area
