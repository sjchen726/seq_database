# Experiment Data Redesign — Design Spec

**Date:** 2026-06-04  
**Scope:** Sub-projects A (readout_type free text) and B (experiment list/detail page redesign). Sub-project C (interactive charts) is out of scope for this spec.

---

## Goals

1. Allow free-text `readout_type` entry (e.g., "体重") instead of fixed choices.
2. Replace the current card-per-experiment layout with a compact list view (accordion + detail navigation).
3. Show replicate data as columns (Rep1 / Rep2 / Rep3 / Mean / SD), not as separate rows.
4. Provide a dedicated per-experiment detail page with a shareable URL.

---

## Sub-project A: readout_type Free Text

### Data Model

`DataPoint.readout_type` is currently a `CharField` with `choices=READOUT_TYPE_CHOICES`. Remove the `choices=...` parameter.

- **No DB migration required** — Django choices are application-layer validation only; the column type and existing data are unchanged.
- Existing stored values (e.g., `'KD'`, `'IC50'`) remain valid.

### UI Pattern (two locations)

Both `add_experiment.html` (data point table row) and `upload_prism_preview.html` (metadata form) use the same "select + custom" widget:

```html
<select name="readout_type" class="readout-type-select ds-form-control" required>
  <option value="KD%">KD%</option>
  <option value="IC50">IC50</option>
  <option value="体重">体重</option>
  <!-- …other presets… -->
  <option value="__custom__">自定义…</option>
</select>
<input type="text" name="readout_type_custom" class="readout-type-custom ds-form-control"
       list="readout_suggestions" placeholder="输入读数类型" style="display:none;">
<datalist id="readout_suggestions">
  <!-- populated by view from DataPoint.objects.values_list('readout_type', flat=True).distinct() -->
</datalist>
```

JS behaviour (in `add_experiment.js` and inline in `upload_prism_preview.html`):
- When `select` changes to `__custom__`: hide the `<select>`, show the `<input>`.
- On form submit: a `submit` event listener iterates all `.readout-type-select` elements; for any with value `__custom__`, it copies the adjacent `.readout-type-custom` input's value into the select's value before submission (so the server always receives `readout_type = the actual string`).
- In `add_experiment.html` the data-point table has multiple rows (each dynamically added). The `addDataPointBtn` handler sets up this toggle on each new row. The submit handler iterates all rows.
- `upload_prism_preview.html` has a single readout_type field; same JS pattern applies inline.

### View changes

- `add_experiment` view: pass `readout_type_suggestions` context = distinct existing values from DB.
- `upload_prism_preview` view: same.
- `upload_prism_confirm` view: drop the allowlist validation on `readout_type` (currently validates against `READOUT_TYPE_CHOICES`). Accept any non-empty string.
- `add_experiment` POST handler: read `readout_type` after resolving custom value server-side (if posted value is `__custom__`, use the `readout_type_custom` field).

---

## Sub-project B: Experiment List & Detail Page Redesign

### URL Structure

```
/experiment/<duplex_id>/           → experiment_list view  (existing URL, view rewritten)
/experiment/<duplex_id>/<exp_id>/  → experiment_detail_single view  (new)
```

### experiment_list view

Replaces the existing `experiment_detail` view at the same URL.

**Context passed to template:**
```python
{
    'duplex_id': duplex_id,
    'vitro_exps': [ExperimentRow, ...],  # in_vitro, ordered by exp_date desc
    'vivo_exps':  [ExperimentRow, ...],  # in_vivo, ordered by exp_date desc
    'can_edit': bool,
}
```

Each `ExperimentRow` is a dict:
```python
{
    'exp': Experiment instance,
    'summary': {
        'label': '体外 · HepG2',   # exp_type + cell_line or animal_species
        'readout_type': 'KD%',
        'batch': '20240315',
        'date_range': 'Day1 ~ Day28',   # min/max of timepoint/concentration values
        'point_count': 9,               # non-excluded DataPoints
        'exp_date': date,
    },
    'pivot': PivotTable,  # see Pivot Computation below
}
```

### experiment_detail_single view (new)

URL: `/experiment/<duplex_id>/<exp_id>/`

Context:
```python
{
    'duplex_id': duplex_id,
    'exp': Experiment instance,
    'pivot': PivotTable,
    'attachments': [ExperimentAttachment, ...],
    'can_edit': bool,
}
```

### Pivot Computation

Extracted into a pure helper function `build_pivot_table(experiment)` in `app01/views.py`:

```python
def build_pivot_table(experiment):
    """
    Always returns a list of pivot dicts (one per distinct readout_type).
    Each pivot dict:
        {
            'readout_type': str,
            'x_label': 'Day' | 'Dose',
            'rows': [
                {
                    'x': str,                              # e.g. 'Day 7' or '10 nM'
                    'reps': [val_or_None, val_or_None, val_or_None],
                    'mean': float | None,
                    'sd': float | None,
                },
                ...
            ]
        }
    """
```

Logic:
1. Fetch all `DataPoint` for the experiment, ordered by `timepoint` / `concentration_or_dose`.
2. Determine x-axis: use `timepoint` if non-null, else `f"{concentration_or_dose} {conc_unit}"`.
3. Group by `(readout_type, x_value)`. For each readout type, build a list of row dicts.
4. For each row, slot into `reps[0/1/2]` by `replicate` field (`'1'`→0, `'2'`→1, `'3'`→2). `replicate='excluded'` is ignored (rep slot stays None).
5. Compute `mean` = `statistics.mean(valid)` where valid = [r for r in reps if r is not None]. If `len(valid) < 1`, mean = None.
6. Compute `sd` = `statistics.stdev(valid)` if `len(valid) >= 2`, else None.
7. Return list of pivot dicts (length ≥ 1); single readout type returns a list of one dict.

### Template: experiment_detail.html (rewritten as list page)

Structure:
```html
<!-- 体外实验 section -->
<h3>体外实验</h3>
{% for row in vitro_exps %}
  <div class="exp-list-row" data-exp-id="{{ row.exp.id }}">
    <div class="exp-list-summary">
      <span class="exp-type-badge">{{ row.summary.label }}</span>
      <span>{{ row.summary.readout_type }}</span>
      <span>Batch: {{ row.summary.batch }}</span>
      <span>{{ row.summary.date_range }}</span>
      <span>{{ row.summary.point_count }} 点</span>
      <span>{{ row.summary.exp_date }}</span>
      <button class="exp-accordion-btn">展开 ▼</button>
      <a href="/experiment/{{ duplex_id }}/{{ row.exp.id }}/" class="ds-act">详情 →</a>
      {% if can_edit %}
        <a href="..." class="ds-act ds-act-edit">编辑</a>
        <button class="ds-act ds-act-delete exp-delete-btn" data-id="{{ row.exp.id }}">删除</button>
      {% endif %}
    </div>
    <div class="exp-accordion-body" style="display:none;">
      {% include 'experiment_pivot_table.html' with pivot=row.pivot %}
    </div>
  </div>
{% endfor %}
```

Accordion JS in `static/js/experiment.js` (new file):
- Toggle `display:none` on `.exp-accordion-body` when `.exp-accordion-btn` clicked.
- Rotate chevron icon.

### Template: experiment_detail_single.html (new)

Sections:
1. **Topbar**: "实验详情  `<duplex_id>`  ← 返回列表  [编辑]  [删除]"
2. **Metadata card**: exp_type, cell_line/animal_species, assay_type, readout_type, batch, exp_date, notes.
3. **Data table**: `{% include 'experiment_pivot_table.html' with pivot=pivot %}`
4. **Attachments**: list of files and URLs.

### Template: experiment_pivot_table.html (new partial)

Shared between list accordion and detail page:
```html
{% for pt in pivot %}   {# loop over readout types if multiple #}
  {% if pivot|length > 1 %}<h4>{{ pt.readout_type }}</h4>{% endif %}
  <table class="ds-table exp-pivot-table">
    <thead>
      <tr>
        <th>{{ pt.x_label }}</th>
        <th>Rep1</th><th>Rep2</th><th>Rep3</th>
        <th>Mean</th><th>SD</th>
      </tr>
    </thead>
    <tbody>
      {% for row in pt.rows %}
      <tr>
        <td>{{ row.x }}</td>
        {% for v in row.reps %}<td>{{ v|default:"—" }}</td>{% endfor %}
        <td>{{ row.mean|default:"—" }}</td>
        <td>{{ row.sd|default:"—" }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
{% endfor %}
```

### experiment_card.html

No longer needed as a standalone include. Can be deleted once the list page is live.

---

## Files Touched

| File | Action |
|------|--------|
| `app01/models.py` | Remove `choices=` from `DataPoint.readout_type` |
| `app01/views.py` | Rewrite `experiment_detail`; add `experiment_detail_single`; add `build_pivot_table`; update `add_experiment` and `upload_prism_confirm` to drop choice validation |
| `bms/urls.py` | Add `experiment/<duplex_id>/<int:exp_id>/` route |
| `templates/experiment_detail.html` | Full rewrite → list page |
| `templates/experiment_detail_single.html` | New |
| `templates/experiment_pivot_table.html` | New partial |
| `templates/experiment_card.html` | Delete |
| `templates/add_experiment.html` | readout_type select+custom widget |
| `templates/upload_prism_preview.html` | readout_type select+custom widget |
| `static/js/experiment.js` | New — accordion toggle JS |
| `static/js/add_experiment.js` | Add select+custom logic for readout_type |

---

## Edge Cases

- **Single replicate**: SD = `—`, Mean = that value.
- **All replicates excluded**: row shows `— — — — —`.
- **Mixed readout types in one experiment**: `build_pivot_table` returns a list of per-readout pivot dicts; template loops over them with sub-headers.
- **No experiments for duplex**: list page shows empty state "暂无实验数据" with "+ 添加实验" CTA.
- **Existing `readout_type` values**: already stored as strings; removing choices doesn't affect them.
- **`experiment_card.html` still referenced**: `_seq_group_row.html` links to `experiment_detail` by duplex_id — URL unchanged, still works.
