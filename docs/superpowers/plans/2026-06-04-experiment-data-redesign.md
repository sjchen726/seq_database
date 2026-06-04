# Experiment Data Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace fixed readout_type choices with free-text + presets, and redesign experiment display from flat cards to an accordion list view with dedicated detail pages and pivot tables showing replicates as columns.

**Architecture:** Sub-project A removes the `choices=` constraint from `DataPoint.readout_type` (no migration) and adds a select+custom widget in two form templates. Sub-project B adds a `build_pivot_table()` helper, rewrites `experiment_detail` into a list view returning `ExperimentRow` dicts, adds a new `experiment_detail_single` view at `/experiment/<duplex_id>/<exp_id>/`, and replaces `experiment_card.html` with three new/rewritten templates plus an accordion JS file.

**Tech Stack:** Django 5.1, Python 3.10, MySQL, vanilla JS (no extra libraries), Django templates.

---

## File Map

| File | Action |
|------|--------|
| `app01/models.py` | Remove `choices=READOUT_TYPE_CHOICES` from `DataPoint.readout_type` |
| `app01/views.py` | Add `READOUT_TYPE_PRESETS` constant; add `build_pivot_table()`; rewrite `experiment_detail`; add `experiment_detail_single`; update `add_experiment` and `upload_prism_confirm` context/validation |
| `bms/urls.py` | Add `experiment/<str:duplex_id>/<int:exp_id>/` |
| `templates/experiment_detail.html` | Full rewrite → accordion list page |
| `templates/experiment_detail_single.html` | New — dedicated detail page |
| `templates/experiment_pivot_table.html` | New — shared pivot table partial |
| `templates/experiment_card.html` | Delete |
| `templates/add_experiment.html` | readout_type → select+custom widget; add datalist |
| `templates/upload_prism_preview.html` | readout_type → select+custom widget |
| `static/js/experiment.js` | New — accordion toggle JS |
| `static/js/add_experiment.js` | Replace readout_type select builder; add submit handler |
| `app01/tests.py` | Add `BuildPivotTableTests`, `ExperimentListViewTests`, `ExperimentDetailSingleTests`, `ReadoutTypeModelTests` |

---

### Task 1: Remove choices= from DataPoint.readout_type

**Files:**
- Modify: `app01/models.py:373`
- Test: `app01/tests.py`

- [ ] **Step 1: Write the failing test**

Add to `app01/tests.py` at the end of the file (after all existing test classes):

```python
class ReadoutTypeModelTests(TestCase):
    def setUp(self):
        from app01.models import Experiment
        self.exp = Experiment.objects.create(
            duplex_id='BP000001',
            exp_type='in_vitro',
            assay_type='single_point',
            batch='B001',
            created_by='test',
        )

    def test_arbitrary_readout_type_saves_without_error(self):
        dp = DataPoint.objects.create(
            experiment=self.exp,
            readout_type='体重',
            value=22.5,
        )
        dp.refresh_from_db()
        self.assertEqual(dp.readout_type, '体重')

    def test_long_custom_readout_type_up_to_32_chars(self):
        long_val = 'A' * 32
        dp = DataPoint.objects.create(
            experiment=self.exp,
            readout_type=long_val,
            value=1.0,
        )
        dp.refresh_from_db()
        self.assertEqual(dp.readout_type, long_val)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source venv/bin/activate
python manage.py test app01.tests.ReadoutTypeModelTests -v 2
```

Expected: FAIL — `ValidationError: Value 'body_weight' is not a valid choice.` (or similar when `full_clean()` is triggered by certain validators).

Actually Django doesn't enforce choices at the DB level, so these tests may already pass. If they pass, skip to Step 3 anyway — we still need to remove the choices for the UI to send arbitrary strings without form validation errors.

- [ ] **Step 3: Remove choices= parameter from DataPoint.readout_type**

In `app01/models.py`, find line ~373:
```python
readout_type = models.CharField('终点类型', max_length=32, choices=READOUT_TYPE_CHOICES)
```
Change to:
```python
readout_type = models.CharField('终点类型', max_length=32)
```

Keep the `READOUT_TYPE_CHOICES` class attribute — it may still be referenced elsewhere. Do NOT delete it.

- [ ] **Step 4: Verify no migration is needed**

```bash
python manage.py makemigrations --check
```

Expected output: `No changes detected` (choices are not stored in DB schema).

If it says a migration is needed, run `python manage.py makemigrations` and commit it. This would be unexpected but harmless.

- [ ] **Step 5: Run tests**

```bash
python manage.py test app01.tests.ReadoutTypeModelTests -v 2
```

Expected: both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app01/models.py app01/tests.py
git commit -m "feat: remove choices constraint from DataPoint.readout_type for free-text support"
```

---

### Task 2: Add build_pivot_table helper function

**Files:**
- Modify: `app01/views.py` (add function near line 4398, before `experiment_detail`)
- Test: `app01/tests.py`

- [ ] **Step 1: Write the failing tests**

Add to `app01/tests.py`:

```python
class BuildPivotTableTests(TestCase):
    def setUp(self):
        from app01.models import Experiment
        from app01.views import build_pivot_table
        self.build_pivot_table = build_pivot_table
        self.exp = Experiment.objects.create(
            duplex_id='BP000002',
            exp_type='in_vitro',
            assay_type='single_point',
            batch='B002',
            created_by='test',
        )

    def _dp(self, timepoint=None, conc=None, conc_unit=None, readout_type='KD%',
            value=50.0, replicate='1'):
        return DataPoint.objects.create(
            experiment=self.exp,
            timepoint=timepoint,
            concentration_or_dose=conc,
            conc_unit=conc_unit,
            readout_type=readout_type,
            value=value,
            replicate=replicate,
        )

    def test_empty_experiment_returns_empty_list(self):
        result = self.build_pivot_table(self.exp)
        self.assertEqual(result, [])

    def test_three_replicates_one_timepoint(self):
        self._dp(timepoint='Day 7', value=80.0, replicate='1')
        self._dp(timepoint='Day 7', value=82.0, replicate='2')
        self._dp(timepoint='Day 7', value=78.0, replicate='3')
        result = self.build_pivot_table(self.exp)
        self.assertEqual(len(result), 1)
        pt = result[0]
        self.assertEqual(pt['readout_type'], 'KD%')
        self.assertEqual(pt['x_label'], '时间点')
        self.assertEqual(len(pt['rows']), 1)
        row = pt['rows'][0]
        self.assertEqual(row['x'], 'Day 7')
        self.assertEqual(row['reps'], [80.0, 82.0, 78.0])
        self.assertAlmostEqual(row['mean'], 80.0, places=1)
        self.assertIsNotNone(row['sd'])

    def test_excluded_replicate_not_counted_in_mean(self):
        self._dp(timepoint='Day 7', value=80.0, replicate='1')
        self._dp(timepoint='Day 7', value=82.0, replicate='2')
        self._dp(timepoint='Day 7', value=999.0, replicate='excluded')
        result = self.build_pivot_table(self.exp)
        row = result[0]['rows'][0]
        self.assertEqual(row['reps'], [80.0, 82.0, None])
        self.assertAlmostEqual(row['mean'], 81.0, places=1)

    def test_single_replicate_no_sd(self):
        self._dp(timepoint='Day 7', value=80.0, replicate='1')
        result = self.build_pivot_table(self.exp)
        row = result[0]['rows'][0]
        self.assertEqual(row['mean'], 80.0)
        self.assertIsNone(row['sd'])

    def test_timepoints_sorted_numerically(self):
        self._dp(timepoint='Day 14', value=60.0, replicate='1')
        self._dp(timepoint='Day 7', value=80.0, replicate='1')
        self._dp(timepoint='Day 28', value=40.0, replicate='1')
        result = self.build_pivot_table(self.exp)
        xs = [row['x'] for row in result[0]['rows']]
        self.assertEqual(xs, ['Day 7', 'Day 14', 'Day 28'])

    def test_multiple_readout_types_separate_pivot_dicts(self):
        self._dp(timepoint='Day 7', value=80.0, replicate='1', readout_type='KD%')
        self._dp(timepoint='Day 7', value=22.0, replicate='1', readout_type='体重')
        result = self.build_pivot_table(self.exp)
        self.assertEqual(len(result), 2)
        readout_types = {pt['readout_type'] for pt in result}
        self.assertIn('KD%', readout_types)
        self.assertIn('体重', readout_types)

    def test_concentration_x_axis(self):
        self._dp(conc=10.0, conc_unit='nM', value=90.0, replicate='1')
        self._dp(conc=100.0, conc_unit='nM', value=50.0, replicate='1')
        result = self.build_pivot_table(self.exp)
        self.assertEqual(result[0]['x_label'], '浓度/剂量')
        xs = [row['x'] for row in result[0]['rows']]
        self.assertIn('10 nM', xs)
        self.assertIn('100 nM', xs)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python manage.py test app01.tests.BuildPivotTableTests -v 2
```

Expected: ImportError or AttributeError — `build_pivot_table` does not exist yet.

- [ ] **Step 3: Implement build_pivot_table**

Add the following function in `app01/views.py` immediately before the `def experiment_detail(request, duplex_id):` line (around line 4398). Add it as a module-level function:

```python
def build_pivot_table(experiment):
    """Return list of pivot dicts (one per distinct readout_type).

    Each dict: {'readout_type': str, 'x_label': str, 'rows': [{'x', 'reps', 'mean', 'sd'}]}
    reps is always a list of 3 elements (None where missing).
    Excluded replicates are omitted from reps slots and not counted in mean/sd.
    """
    import statistics as _stats
    import re
    from collections import OrderedDict

    datapoints = list(experiment.datapoints.all())
    if not datapoints:
        return []

    use_timepoint = any(dp.timepoint for dp in datapoints)
    x_label = '时间点' if use_timepoint else '浓度/剂量'

    pivot_by_readout = OrderedDict()  # readout_type → OrderedDict[x_str → [None, None, None]]

    for dp in datapoints:
        if dp.replicate == 'excluded':
            continue
        if use_timepoint:
            x = dp.timepoint or '—'
        else:
            x = (f"{dp.concentration_or_dose:g} {dp.conc_unit}"
                 if dp.concentration_or_dose is not None else '—')

        rt = dp.readout_type or ''
        if rt not in pivot_by_readout:
            pivot_by_readout[rt] = OrderedDict()
        if x not in pivot_by_readout[rt]:
            pivot_by_readout[rt][x] = [None, None, None]

        if dp.replicate in ('1', '2', '3'):
            pivot_by_readout[rt][x][int(dp.replicate) - 1] = dp.value

    def _x_sort_key(x_val):
        m = re.search(r'[\d.]+', x_val)
        return float(m.group()) if m else float('inf')

    result = []
    for rt, x_map in pivot_by_readout.items():
        if use_timepoint:
            ordered_items = sorted(x_map.items(), key=lambda kv: _x_sort_key(kv[0]))
        else:
            # For concentrations, sort by the numeric value parsed from x string
            ordered_items = sorted(x_map.items(), key=lambda kv: _x_sort_key(kv[0]))

        rows = []
        for x, reps in ordered_items:
            valid = [v for v in reps if v is not None]
            mean_val = round(_stats.mean(valid), 2) if valid else None
            sd_val = round(_stats.stdev(valid), 2) if len(valid) >= 2 else None
            rows.append({'x': x, 'reps': reps, 'mean': mean_val, 'sd': sd_val})

        result.append({'readout_type': rt, 'x_label': x_label, 'rows': rows})

    return result
```

Also add to `app01/views.py` imports at the top of the test imports block in `tests.py` — add `build_pivot_table` to the imports:

In `app01/tests.py` line 6–10, add `build_pivot_table` to the import:
```python
from app01.views import (
    normalize_middle_brackets, run_preflight_check, group_sequences,
    auto_register_bare_sequences, check_duplicates,
    build_combo_re, normalize_tmp_seq_with_combo,
    build_pivot_table,
)
```

- [ ] **Step 4: Run tests**

```bash
python manage.py test app01.tests.BuildPivotTableTests -v 2
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "feat: add build_pivot_table helper for experiment data pivot display"
```

---

### Task 3: Rewrite experiment_detail view and templates (list page)

**Files:**
- Modify: `app01/views.py` (rewrite `experiment_detail` at line 4398)
- Rewrite: `templates/experiment_detail.html`
- Create: `templates/experiment_pivot_table.html`
- Test: `app01/tests.py`

- [ ] **Step 1: Write the failing tests**

Add to `app01/tests.py`:

```python
class ExperimentListViewTests(TestCase):
    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='testadmin', password='pass',
            user_type='superadmin',
        )
        self.client.force_login(self.user)
        from app01.models import Experiment
        self.exp = Experiment.objects.create(
            duplex_id='BP000003',
            exp_type='in_vitro',
            assay_type='single_point',
            cell_line='HepG2',
            batch='B003',
            created_by='testadmin',
        )
        DataPoint.objects.create(
            experiment=self.exp,
            timepoint='Day 7',
            readout_type='KD%',
            value=80.0,
            replicate='1',
        )

    def test_list_page_returns_200(self):
        resp = self.client.get(f'/experiment/BP000003/')
        self.assertEqual(resp.status_code, 200)

    def test_list_page_contains_summary_fields(self):
        resp = self.client.get(f'/experiment/BP000003/')
        self.assertContains(resp, 'HepG2')
        self.assertContains(resp, 'B003')
        self.assertContains(resp, 'KD%')

    def test_list_page_contains_detail_link(self):
        resp = self.client.get(f'/experiment/BP000003/')
        self.assertContains(resp, f'/experiment/BP000003/{self.exp.id}/')

    def test_list_page_no_experiments_shows_empty_state(self):
        # Superadmin bypasses access check; a duplex with no experiments shows empty state
        resp = self.client.get('/experiment/BP000099/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '暂无实验数据')

    def test_vitro_vivo_split(self):
        from app01.models import Experiment
        Experiment.objects.create(
            duplex_id='BP000003',
            exp_type='in_vivo',
            assay_type='in_vivo_efficacy',
            animal_species='mouse',
            batch='B004',
            created_by='testadmin',
        )
        resp = self.client.get(f'/experiment/BP000003/')
        self.assertContains(resp, '体外实验')
        self.assertContains(resp, '体内实验')
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python manage.py test app01.tests.ExperimentListViewTests -v 2
```

Expected: FAIL — `experiment_list_page_contains_detail_link` fails because the detail link doesn't exist in current template.

- [ ] **Step 3: Rewrite experiment_detail view**

Replace the entire `experiment_detail` function in `app01/views.py` (starting at line 4398):

```python
def experiment_detail(request, duplex_id):
    """Experiment list page for a duplex_id — accordion rows with pivot tables."""
    from .models import Experiment
    from django.http import Http404

    if not _user_can_access_duplex(request.user, duplex_id):
        raise Http404

    experiments = (
        Experiment.objects
        .filter(duplex_id=duplex_id)
        .prefetch_related('datapoints', 'attachments')
        .order_by('exp_type', '-exp_date', '-created_at')
    )

    def _build_exp_row(exp):
        datapoints = list(exp.datapoints.all())
        non_excl = [dp for dp in datapoints if dp.replicate != 'excluded']

        label_parts = ['体外' if exp.exp_type == 'in_vitro' else '体内']
        if exp.exp_type == 'in_vitro' and exp.cell_line:
            label_parts.append(exp.cell_line)
        elif exp.exp_type == 'in_vivo' and exp.animal_species:
            label_parts.append(exp.animal_species)

        readout_types = list(dict.fromkeys(
            dp.readout_type for dp in non_excl if dp.readout_type
        ))
        readout_display = ' / '.join(readout_types) if readout_types else '—'

        import re
        timepoints = [dp.timepoint for dp in non_excl if dp.timepoint]
        if timepoints:
            def _tp_num(tp):
                m = re.search(r'[\d.]+', tp)
                return float(m.group()) if m else float('inf')
            tp_sorted = sorted(set(timepoints), key=_tp_num)
            date_range = (f"{tp_sorted[0]} ~ {tp_sorted[-1]}"
                          if len(tp_sorted) > 1 else tp_sorted[0])
        else:
            concs = sorted(
                set((dp.concentration_or_dose, dp.conc_unit)
                    for dp in non_excl if dp.concentration_or_dose is not None),
                key=lambda c: c[0],
            )
            if concs:
                def _fmt(c, u): return f"{c:g} {u}" if u else f"{c:g}"
                date_range = (f"{_fmt(*concs[0])} ~ {_fmt(*concs[-1])}"
                              if len(concs) > 1 else _fmt(*concs[0]))
            else:
                date_range = '—'

        return {
            'exp': exp,
            'summary': {
                'label': ' · '.join(label_parts),
                'readout_type': readout_display,
                'batch': exp.batch,
                'date_range': date_range,
                'point_count': len(non_excl),
                'exp_date': exp.exp_date,
            },
            'pivot': build_pivot_table(exp),
        }

    all_rows = [_build_exp_row(e) for e in experiments]
    vitro_rows = [r for r in all_rows if r['exp'].exp_type == 'in_vitro']
    vivo_rows  = [r for r in all_rows if r['exp'].exp_type == 'in_vivo']

    can_edit = (
        request.user.is_superuser or
        getattr(request.user, 'user_type', '') in ('data_admin', 'admin', 'superadmin')
    )

    return render(request, 'experiment_detail.html', {
        'duplex_id':   duplex_id,
        'vitro_exps':  vitro_rows,
        'vivo_exps':   vivo_rows,
        'can_edit':    can_edit,
    })
```

- [ ] **Step 4: Create templates/experiment_pivot_table.html**

Create new file `templates/experiment_pivot_table.html`:

```html
{# Shared pivot table partial. Requires: pivot (list of pivot dicts) #}
{% for pt in pivot %}
  {% if pivot|length > 1 %}
    <div style="font-size:11px;font-weight:600;color:#475569;margin:10px 0 4px;">{{ pt.readout_type }}</div>
  {% endif %}
  <div style="overflow-x:auto;">
    <table class="ds-table exp-pivot-table" style="font-size:11px;min-width:360px;">
      <thead>
        <tr>
          <th style="white-space:nowrap;">{{ pt.x_label }}</th>
          <th>Rep1</th>
          <th>Rep2</th>
          <th>Rep3</th>
          <th style="font-weight:700;">Mean</th>
          <th>SD</th>
        </tr>
      </thead>
      <tbody>
        {% for row in pt.rows %}
        <tr>
          <td style="white-space:nowrap;">{{ row.x }}</td>
          {% for v in row.reps %}
            <td>{{ v|default_if_none:"—" }}</td>
          {% endfor %}
          <td style="font-weight:600;">{{ row.mean|default_if_none:"—" }}</td>
          <td style="color:#64748b;">{{ row.sd|default_if_none:"—" }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
{% endfor %}
```

- [ ] **Step 5: Rewrite templates/experiment_detail.html**

Overwrite the entire file with:

```html
{% extends 'base.html' %}

{% block page_title %} — 实验数据 {{ duplex_id }}{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">实验数据</span>
  <span style="font-family:'DM Mono',monospace;font-size:12px;color:#94a3b8;margin-left:6px;">{{ duplex_id }}</span>
  <span class="ds-topbar-spacer"></span>
  <a href="/seq_list/" class="ds-btn ds-btn-ghost">← 返回列表</a>
  {% if can_edit %}<a href="{% url 'upload_experiment' %}" class="ds-btn ds-btn-ghost" style="font-size:12px;">↑ Prism 批量导入</a>{% endif %}
  {% if can_edit %}<a href="{% url 'add_experiment' %}?duplex_id={{ duplex_id }}" class="ds-btn ds-btn-primary">+ 添加实验</a>{% endif %}
{% endblock %}

{% block content %}
<div style="max-width:1200px;margin:24px auto;padding:0 16px;">

  {% if not vitro_exps and not vivo_exps %}
    <div class="ds-table-card" style="padding:32px;text-align:center;color:#94a3b8;">
      暂无实验数据。{% if can_edit %}点击右上角"+ 添加实验"开始录入。{% endif %}
    </div>
  {% endif %}

  {% if vitro_exps %}
    <h3 style="font-size:13px;font-weight:700;margin:16px 0 8px;color:#374151;">体外实验</h3>
    {% for row in vitro_exps %}{% include '_experiment_list_row.html' with row=row duplex_id=duplex_id can_edit=can_edit %}{% endfor %}
  {% endif %}

  {% if vivo_exps %}
    <h3 style="font-size:13px;font-weight:700;margin:24px 0 8px;color:#374151;">体内实验</h3>
    {% for row in vivo_exps %}{% include '_experiment_list_row.html' with row=row duplex_id=duplex_id can_edit=can_edit %}{% endfor %}
  {% endif %}

</div>
{% endblock %}

{% block extra_scripts %}
<script src="/static/js/experiment.js"></script>
{% endblock %}
```

- [ ] **Step 6: Create templates/_experiment_list_row.html**

Create new file `templates/_experiment_list_row.html`:

```html
{# One accordion row in the experiment list. Requires: row, duplex_id, can_edit #}
<div class="exp-list-row ds-table-card" data-exp-id="{{ row.exp.id }}"
     style="margin-bottom:8px;padding:0;overflow:hidden;">

  <div class="exp-list-summary" style="display:flex;align-items:center;gap:12px;padding:10px 14px;cursor:default;flex-wrap:wrap;">
    <span class="exp-type-badge"
          style="background:#e0f2fe;color:#0369a1;font-size:11px;font-weight:600;padding:2px 8px;border-radius:10px;white-space:nowrap;">
      {{ row.summary.label }}
    </span>
    <span style="font-size:12px;font-weight:600;color:#1e293b;">{{ row.summary.readout_type }}</span>
    <span style="font-size:11px;color:#64748b;">Batch: {{ row.summary.batch }}</span>
    <span style="font-size:11px;color:#64748b;">{{ row.summary.date_range }}</span>
    <span style="font-size:11px;color:#64748b;">{{ row.summary.point_count }} 点</span>
    {% if row.summary.exp_date %}<span style="font-size:11px;color:#64748b;">{{ row.summary.exp_date }}</span>{% endif %}
    <span style="margin-left:auto;display:flex;gap:6px;align-items:center;">
      <button class="exp-accordion-btn ds-btn ds-btn-ghost"
              style="height:24px;font-size:11px;padding:0 8px;">展开 ▼</button>
      <a href="/experiment/{{ duplex_id }}/{{ row.exp.id }}/"
         class="ds-act" style="font-size:11px;">详情 →</a>
      {% if can_edit %}
        <a href="{% url 'add_experiment' %}?duplex_id={{ duplex_id }}&edit={{ row.exp.id }}"
           class="ds-act ds-act-edit" style="font-size:11px;">编辑</a>
        <form method="POST" action="{% url 'delete_experiment' row.exp.id %}"
              style="display:inline;"
              onsubmit="return confirm('确认删除此实验记录？')">
          {% csrf_token %}
          <button type="submit" class="ds-act ds-act-delete" style="font-size:11px;">删除</button>
        </form>
      {% endif %}
    </span>
  </div>

  <div class="exp-accordion-body" style="display:none;padding:0 14px 14px;">
    {% if row.pivot %}
      {% include 'experiment_pivot_table.html' with pivot=row.pivot %}
    {% else %}
      <p style="font-size:11px;color:#94a3b8;padding:8px 0;">暂无数据点。</p>
    {% endif %}
  </div>
</div>
```

- [ ] **Step 7: Run tests**

```bash
python manage.py test app01.tests.ExperimentListViewTests -v 2
```

Expected: all 5 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add app01/views.py app01/tests.py templates/experiment_detail.html templates/experiment_pivot_table.html templates/_experiment_list_row.html
git commit -m "feat: rewrite experiment_detail as accordion list view with pivot tables"
```

---

### Task 4: Add experiment_detail_single view and template

**Files:**
- Modify: `app01/views.py` (add new view after `experiment_detail`)
- Modify: `bms/urls.py`
- Create: `templates/experiment_detail_single.html`
- Test: `app01/tests.py`

- [ ] **Step 1: Write the failing tests**

Add to `app01/tests.py`:

```python
class ExperimentDetailSingleTests(TestCase):
    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='testadmin2', password='pass',
            user_type='superadmin',
        )
        self.client.force_login(self.user)
        from app01.models import Experiment
        self.exp = Experiment.objects.create(
            duplex_id='BP000004',
            exp_type='in_vitro',
            assay_type='single_point',
            cell_line='HeLa',
            batch='B004',
            created_by='testadmin2',
        )
        DataPoint.objects.create(
            experiment=self.exp,
            timepoint='Day 7',
            readout_type='KD%',
            value=75.0,
            replicate='1',
        )

    def test_detail_page_returns_200(self):
        resp = self.client.get(f'/experiment/BP000004/{self.exp.id}/')
        self.assertEqual(resp.status_code, 200)

    def test_detail_page_shows_metadata(self):
        resp = self.client.get(f'/experiment/BP000004/{self.exp.id}/')
        self.assertContains(resp, 'HeLa')
        self.assertContains(resp, 'B004')

    def test_detail_page_shows_pivot_table(self):
        resp = self.client.get(f'/experiment/BP000004/{self.exp.id}/')
        self.assertContains(resp, 'Day 7')
        self.assertContains(resp, '75.0')

    def test_detail_page_wrong_exp_id_returns_404(self):
        resp = self.client.get(f'/experiment/BP000004/99999/')
        self.assertEqual(resp.status_code, 404)

    def test_detail_page_wrong_duplex_returns_404(self):
        resp = self.client.get(f'/experiment/BPWRONG/{self.exp.id}/')
        self.assertEqual(resp.status_code, 404)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python manage.py test app01.tests.ExperimentDetailSingleTests -v 2
```

Expected: FAIL — 404 from URL not found (URL not yet registered).

- [ ] **Step 3: Add URL**

In `bms/urls.py`, add after the existing `experiment/<str:duplex_id>/` line:

```python
path('experiment/<str:duplex_id>/<int:exp_id>/', views.experiment_detail_single, name='experiment_detail_single'),
```

The final experiment URL block should look like:
```python
# Experiment data
path('experiment/add/', views.add_experiment, name='add_experiment'),
path('experiment/delete/<int:exp_id>/', views.delete_experiment, name='delete_experiment'),
path('upload_experiment/', views.upload_experiment, name='upload_experiment'),
path('download_experiment_template/', views.download_experiment_template, name='download_experiment_template'),
path('experiment/<str:duplex_id>/', views.experiment_detail, name='experiment_detail'),
path('experiment/<str:duplex_id>/<int:exp_id>/', views.experiment_detail_single, name='experiment_detail_single'),
path('upload_prism_preview/', views.upload_prism_preview, name='upload_prism_preview'),
path('upload_prism_confirm/', views.upload_prism_confirm, name='upload_prism_confirm'),
```

- [ ] **Step 4: Add experiment_detail_single view**

Add the following function in `app01/views.py` immediately after the `experiment_detail` function:

```python
def experiment_detail_single(request, duplex_id, exp_id):
    """Dedicated detail page for a single experiment record."""
    from .models import Experiment, ExperimentAttachment
    from django.http import Http404

    if not _user_can_access_duplex(request.user, duplex_id):
        raise Http404

    try:
        exp = (Experiment.objects
               .prefetch_related('datapoints', 'attachments')
               .get(pk=exp_id, duplex_id=duplex_id))
    except Experiment.DoesNotExist:
        raise Http404

    can_edit = (
        request.user.is_superuser or
        getattr(request.user, 'user_type', '') in ('data_admin', 'admin', 'superadmin')
    )

    return render(request, 'experiment_detail_single.html', {
        'duplex_id':   duplex_id,
        'exp':         exp,
        'pivot':       build_pivot_table(exp),
        'attachments': list(exp.attachments.all()),
        'can_edit':    can_edit,
    })
```

- [ ] **Step 5: Create templates/experiment_detail_single.html**

Create new file `templates/experiment_detail_single.html`:

```html
{% extends 'base.html' %}

{% block page_title %} — 实验详情 {{ duplex_id }}{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">实验详情</span>
  <span style="font-family:'DM Mono',monospace;font-size:12px;color:#94a3b8;margin-left:6px;">{{ duplex_id }}</span>
  <span class="ds-topbar-spacer"></span>
  <a href="/experiment/{{ duplex_id }}/" class="ds-btn ds-btn-ghost">← 返回列表</a>
  {% if can_edit %}
    <a href="{% url 'add_experiment' %}?duplex_id={{ duplex_id }}&edit={{ exp.id }}"
       class="ds-btn ds-btn-ghost" style="font-size:12px;">编辑</a>
    <form method="POST" action="{% url 'delete_experiment' exp.id %}"
          style="display:inline;margin-left:4px;"
          onsubmit="return confirm('确认删除此实验记录？')">
      {% csrf_token %}
      <button type="submit" class="ds-btn"
              style="height:32px;font-size:12px;padding:0 10px;background:#fee2e2;color:#b91c1c;border:none;border-radius:6px;cursor:pointer;">
        删除
      </button>
    </form>
  {% endif %}
{% endblock %}

{% block content %}
<div style="max-width:900px;margin:24px auto;padding:0 16px;">

  <div class="ds-table-card" style="padding:16px;margin-bottom:16px;">
    <div class="ds-form-card-title" style="margin-bottom:12px;">实验信息</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px 24px;font-size:12px;">
      <div><strong>类型：</strong>{{ exp.get_exp_type_display }}</div>
      <div><strong>Assay：</strong>{{ exp.get_assay_type_display }}</div>
      {% if exp.cell_line %}<div><strong>细胞系：</strong>{{ exp.cell_line }}</div>{% endif %}
      {% if exp.animal_species %}<div><strong>动物种属：</strong>{{ exp.animal_species }}</div>{% endif %}
      {% if exp.transfection_reagent %}<div><strong>转染试剂：</strong>{{ exp.transfection_reagent }}</div>{% endif %}
      {% if exp.route %}<div><strong>给药途径：</strong>{{ exp.route }}</div>{% endif %}
      <div><strong>批次：</strong>{{ exp.batch }}</div>
      <div><strong>实验日期：</strong>{{ exp.exp_date|default:"—" }}</div>
      <div><strong>录入人：</strong>{{ exp.created_by }}</div>
      <div><strong>录入时间：</strong>{{ exp.created_at|date:"Y-m-d H:i" }}</div>
    </div>
    {% if exp.notes %}
      <div style="margin-top:10px;font-size:12px;"><strong>备注：</strong>{{ exp.notes|linebreaksbr }}</div>
    {% endif %}
  </div>

  <div class="ds-table-card" style="padding:16px;margin-bottom:16px;">
    <div class="ds-form-card-title" style="margin-bottom:12px;">数据</div>
    {% if pivot %}
      {% include 'experiment_pivot_table.html' with pivot=pivot %}
    {% else %}
      <p style="font-size:12px;color:#94a3b8;">暂无数据点。</p>
    {% endif %}
  </div>

  {% if attachments %}
  <div class="ds-table-card" style="padding:16px;">
    <div class="ds-form-card-title" style="margin-bottom:10px;">附件</div>
    <div style="font-size:12px;display:flex;flex-wrap:wrap;gap:8px;">
      {% for att in attachments %}
        {% if att.file %}
          <a href="{{ att.file.url }}" target="_blank"
             style="color:#0369a1;text-decoration:none;">📎 {{ att.label }}</a>
        {% elif att.external_url %}
          <a href="{{ att.external_url }}" target="_blank"
             style="color:#0369a1;text-decoration:none;">🔗 {{ att.label }}</a>
        {% endif %}
      {% endfor %}
    </div>
  </div>
  {% endif %}

</div>
{% endblock %}
```

- [ ] **Step 6: Run tests**

```bash
python manage.py test app01.tests.ExperimentDetailSingleTests -v 2
```

Expected: all 5 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add app01/views.py bms/urls.py app01/tests.py templates/experiment_detail_single.html
git commit -m "feat: add experiment_detail_single view at /experiment/<duplex_id>/<exp_id>/"
```

---

### Task 5: Add accordion JS and delete experiment_card.html

**Files:**
- Create: `static/js/experiment.js`
- Delete: `templates/experiment_card.html`

- [ ] **Step 1: Create static/js/experiment.js**

```javascript
(function () {
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.exp-accordion-btn');
    if (!btn) return;
    var row = btn.closest('.exp-list-row');
    if (!row) return;
    var body = row.querySelector('.exp-accordion-body');
    if (!body) return;

    var isOpen = body.style.display !== 'none';
    body.style.display = isOpen ? 'none' : 'block';
    btn.textContent = isOpen ? '展开 ▼' : '收起 ▲';
  });
})();
```

- [ ] **Step 2: Verify experiment_card.html is not referenced anywhere else**

```bash
grep -r "experiment_card" /Users/gutou/Projects/seq_web/seq_database_v2/templates/ /Users/gutou/Projects/seq_web/seq_database_v2/app01/
```

Expected output: no matches (since `experiment_detail.html` was already rewritten in Task 3 and no longer includes it).

If there are matches, update those files to remove the include before deleting.

- [ ] **Step 3: Delete experiment_card.html**

```bash
git rm templates/experiment_card.html
```

- [ ] **Step 4: Commit**

```bash
git add static/js/experiment.js
git commit -m "feat: add accordion JS for experiment list; delete experiment_card.html"
```

- [ ] **Step 5: Manual smoke test**

Start the dev server and visit `http://127.0.0.1:8000/experiment/BP000001/` (or any duplex with experiment data).

Verify:
- Experiment rows appear as compact summary lines
- Click "展开 ▼" → pivot table appears below the row
- Click "收起 ▲" → pivot table hides
- Click "详情 →" → navigates to `/experiment/BP000001/<id>/`
- Detail page shows metadata card + pivot table
- "← 返回列表" navigates back

---

### Task 6: readout_type select+custom in add_experiment

**Files:**
- Modify: `app01/views.py` (add `READOUT_TYPE_PRESETS`; update `add_experiment` GET context and POST handler)
- Modify: `static/js/add_experiment.js`
- Modify: `templates/add_experiment.html`
- Test: `app01/tests.py`

- [ ] **Step 1: Add READOUT_TYPE_PRESETS constant to views.py**

Near the top of `app01/views.py`, after the imports, add:

```python
READOUT_TYPE_PRESETS = [
    'mRNA 残余 %',
    '蛋白残余 %',
    'Knockdown %',
    '血浆浓度',
    '组织浓度',
    '体重',
]
```

- [ ] **Step 2: Write the failing test**

Add to `app01/tests.py`:

```python
class AddExperimentReadoutTests(TestCase):
    def setUp(self):
        from app01.models import Sequence, Delivery
        self.user = LmsUser.objects.create_user(
            username='testadmin3', password='pass',
            user_type='superadmin',
        )
        self.client.force_login(self.user)
        seq = Sequence.objects.create(seq='AAAA', seq_type='SS')
        Delivery.objects.create(
            sequence=seq,
            duplex_id='BP000005',
            project='P001',
        )

    def test_custom_readout_type_saved(self):
        resp = self.client.post('/experiment/add/', {
            'duplex_id': 'BP000005',
            'exp_type': 'in_vitro',
            'assay_type': 'single_point',
            'batch': 'B005',
            'dp_conc': [''],
            'dp_conc_unit': ['nM'],
            'dp_timepoint': ['Day 7'],
            'dp_readout_type': ['细胞活力'],   # custom, not in old choices
            'dp_value': ['85.0'],
            'dp_value_unit': ['%'],
            'dp_replicate': ['1'],
        })
        # Should redirect (success), not re-render form
        self.assertIn(resp.status_code, [302, 200])
        dp = DataPoint.objects.filter(experiment__duplex_id='BP000005').first()
        self.assertIsNotNone(dp)
        self.assertEqual(dp.readout_type, '细胞活力')

    def test_custom_via_hidden_field_resolved_server_side(self):
        """If JS didn't run, __custom__ + dp_readout_type_custom fallback works."""
        resp = self.client.post('/experiment/add/', {
            'duplex_id': 'BP000005',
            'exp_type': 'in_vitro',
            'assay_type': 'single_point',
            'batch': 'B006',
            'dp_conc': [''],
            'dp_conc_unit': ['nM'],
            'dp_timepoint': ['Day 7'],
            'dp_readout_type': ['__custom__'],
            'dp_readout_type_custom': ['自定义类型'],
            'dp_value': ['90.0'],
            'dp_value_unit': ['%'],
            'dp_replicate': ['1'],
        })
        dp = DataPoint.objects.filter(experiment__duplex_id='BP000005', batch='B006').first()
        # via the experiment FK
        dp2 = DataPoint.objects.filter(
            experiment__duplex_id='BP000005', experiment__batch='B006'
        ).first()
        self.assertIsNotNone(dp2)
        self.assertEqual(dp2.readout_type, '自定义类型')
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
python manage.py test app01.tests.AddExperimentReadoutTests -v 2
```

Expected: `test_custom_readout_type_saved` may pass already (since model choices are removed). `test_custom_via_hidden_field_resolved_server_side` should FAIL — `__custom__` gets stored as the readout_type.

- [ ] **Step 4: Update add_experiment view GET context**

In `app01/views.py`, find the `add_experiment` view's GET handler (around line 4477). Change the context dict from:
```python
'readout_type_choices': DataPoint.READOUT_TYPE_CHOICES,
```
to:
```python
'readout_type_presets': READOUT_TYPE_PRESETS,
'readout_type_suggestions': list(
    DataPoint.objects.values_list('readout_type', flat=True).distinct()[:50]
),
```

Do the same change in the `_render_form()` inner function (around line 4530):
```python
'readout_type_presets': READOUT_TYPE_PRESETS,
'readout_type_suggestions': list(
    DataPoint.objects.values_list('readout_type', flat=True).distinct()[:50]
),
```

- [ ] **Step 5: Update add_experiment view POST handler to resolve __custom__**

In `app01/views.py`, after line `readout_types = request.POST.getlist('dp_readout_type')` (around line 4511), add:

```python
readout_types_custom = request.POST.getlist('dp_readout_type_custom')
# Resolve server-side fallback: if JS didn't run and __custom__ slipped through
readout_types = [
    (readout_types_custom[i].strip() if i < len(readout_types_custom) and readout_types_custom[i].strip() else rt)
    if rt == '__custom__' else rt
    for i, rt in enumerate(readout_types)
]
```

- [ ] **Step 6: Update static/js/add_experiment.js**

Replace the entire file content with:

```javascript
(function () {
  var concUnits = JSON.parse(document.getElementById('conc_unit_choices').textContent);
  var readoutPresets = JSON.parse(document.getElementById('readout_type_presets').textContent);

  function buildSelect(name, choices, required) {
    var s = '<select name="' + name + '" class="ds-form-control"' + (required ? ' required' : '') + '>';
    if (!required) s += '<option value="">--</option>';
    for (var i = 0; i < choices.length; i++) {
      s += '<option value="' + choices[i].v + '">' + choices[i].l + '</option>';
    }
    s += '</select>';
    return s;
  }

  function buildReadoutTypeWidget() {
    var html = '<div class="readout-widget" style="position:relative;">';
    html += '<select name="dp_readout_type" class="readout-type-select ds-form-control" required>';
    for (var i = 0; i < readoutPresets.length; i++) {
      var p = readoutPresets[i];
      html += '<option value="' + p + '">' + p + '</option>';
    }
    html += '<option value="__custom__">自定义…</option>';
    html += '</select>';
    html += '<input type="text" name="dp_readout_type_custom" class="readout-type-custom ds-form-control"';
    html += ' list="readout_suggestions" placeholder="输入读数类型" maxlength="32" style="display:none;">';
    html += '</div>';
    return html;
  }

  function setupReadoutToggle(widget) {
    var sel = widget.querySelector('.readout-type-select');
    var inp = widget.querySelector('.readout-type-custom');
    sel.addEventListener('change', function () {
      if (sel.value === '__custom__') {
        sel.style.display = 'none';
        inp.style.display = '';
        inp.focus();
      }
    });
    inp.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        inp.style.display = 'none';
        sel.style.display = '';
        sel.value = readoutPresets[0];
      }
    });
  }

  function dpRow() {
    var tr = document.createElement('tr');
    tr.innerHTML = ''
      + '<td><input type="number" step="any" name="dp_conc" class="ds-form-control"></td>'
      + '<td>' + buildSelect('dp_conc_unit', concUnits, false) + '</td>'
      + '<td><input type="text" name="dp_timepoint" class="ds-form-control" placeholder="48h / Day7"></td>'
      + '<td>' + buildReadoutTypeWidget() + '</td>'
      + '<td><input type="number" step="any" name="dp_value" class="ds-form-control" required></td>'
      + '<td><input type="text" name="dp_value_unit" class="ds-form-control" placeholder="% / ng/mL"></td>'
      + '<td><input type="text" name="dp_replicate" class="ds-form-control" placeholder="n=3"></td>'
      + '<td><button type="button" class="ds-btn ds-btn-ghost remove-dp" style="height:24px;padding:0 6px;">×</button></td>';
    setupReadoutToggle(tr.querySelector('.readout-widget'));
    return tr;
  }

  function attachRow() {
    var div = document.createElement('div');
    div.className = 'attach-row';
    div.style.cssText = 'display:flex;gap:8px;margin-bottom:6px;align-items:center;';
    div.innerHTML = ''
      + '<input type="file" name="att_file" class="ds-form-control" style="flex:1;min-width:0;">'
      + '<input type="text" name="att_url" class="ds-form-control" placeholder="或填外部链接" style="flex:1;min-width:0;">'
      + '<input type="text" name="att_label" class="ds-form-control" placeholder="描述" style="flex:2;min-width:0;">'
      + '<button type="button" class="ds-btn ds-btn-ghost remove-attach" style="height:24px;padding:0 6px;flex-shrink:0;">×</button>';
    return div;
  }

  var savedRows = JSON.parse(document.getElementById('dp_rows_json').textContent || '[]');
  if (savedRows.length > 0) {
    savedRows.forEach(function (row) {
      var tr = dpRow();
      tr.querySelector('[name="dp_conc"]').value = row.conc || '';
      tr.querySelector('[name="dp_conc_unit"]').value = row.conc_unit || '';
      tr.querySelector('[name="dp_timepoint"]').value = row.timepoint || '';
      var sel = tr.querySelector('.readout-type-select');
      var inp = tr.querySelector('.readout-type-custom');
      var rt = row.readout_type || '';
      var optionExists = Array.prototype.some.call(sel.options, function (o) {
        return o.value === rt;
      });
      if (!optionExists && rt) {
        sel.style.display = 'none';
        inp.style.display = '';
        inp.value = rt;
      } else {
        sel.value = rt;
      }
      tr.querySelector('[name="dp_value"]').value = row.value || '';
      tr.querySelector('[name="dp_value_unit"]').value = row.value_unit || '';
      tr.querySelector('[name="dp_replicate"]').value = row.replicate || '';
      document.getElementById('datapoints_body').appendChild(tr);
    });
  } else {
    document.getElementById('datapoints_body').appendChild(dpRow());
  }

  document.getElementById('addDataPointBtn').addEventListener('click', function () {
    document.getElementById('datapoints_body').appendChild(dpRow());
  });
  document.getElementById('datapoints_body').addEventListener('click', function (e) {
    if (e.target.classList.contains('remove-dp')) {
      var tbody = document.getElementById('datapoints_body');
      if (tbody.children.length > 1) e.target.closest('tr').remove();
    }
  });

  document.getElementById('addAttachBtn').addEventListener('click', function () {
    document.getElementById('attachments_wrap').appendChild(attachRow());
  });
  document.getElementById('attachments_wrap').addEventListener('click', function (e) {
    if (e.target.classList.contains('remove-attach')) {
      e.target.closest('.attach-row').remove();
    }
  });

  // Resolve __custom__ selects before submit
  document.querySelector('form').addEventListener('submit', function () {
    document.querySelectorAll('.readout-type-select').forEach(function (sel) {
      if (sel.value === '__custom__') {
        var inp = sel.parentElement.querySelector('.readout-type-custom');
        sel.value = (inp && inp.value.trim()) ? inp.value.trim() : '';
      }
    });
  });

  // assay_type filter per exp_type
  var ASSAY_BY_TYPE = {
    in_vitro: ['single_point', 'dose_response'],
    in_vivo:  ['in_vivo_efficacy', 'pk'],
  };

  function toggleExpType() {
    var t = document.getElementById('exp_type_select').value;
    document.getElementById('cell_line_wrap').style.display = (t === 'in_vitro') ? '' : 'none';
    document.getElementById('reagent_wrap').style.display   = (t === 'in_vitro') ? '' : 'none';
    document.getElementById('animal_wrap').style.display    = (t === 'in_vivo')  ? '' : 'none';
    document.getElementById('route_wrap').style.display     = (t === 'in_vivo')  ? '' : 'none';

    var allowed = ASSAY_BY_TYPE[t] || [];
    var sel = document.querySelector('[name="assay_type"]');
    Array.prototype.forEach.call(sel.options, function (opt) {
      opt.style.display = (allowed.length === 0 || allowed.indexOf(opt.value) !== -1) ? '' : 'none';
    });
    if (allowed.length > 0 && allowed.indexOf(sel.value) === -1) {
      sel.value = allowed[0];
    }
  }
  document.getElementById('exp_type_select').addEventListener('change', toggleExpType);
  toggleExpType();
})();
```

- [ ] **Step 7: Update templates/add_experiment.html**

Replace the `<script type="application/json" id="readout_type_choices">` block and add a datalist. Find the existing lines (around line 107–111) that render `readout_type_choices` JSON:

```html
<script type="application/json" id="readout_type_choices">
  [{% for v, label in readout_type_choices %}{"v":"{{ v }}","l":"{{ label }}"}{% if not forloop.last %},{% endif %}{% endfor %}]
</script>
```

Replace with:

```html
<script type="application/json" id="readout_type_presets">
  [{% for p in readout_type_presets %}"{{ p }}"{% if not forloop.last %},{% endif %}{% endfor %}]
</script>
<datalist id="readout_suggestions">
  {% for s in readout_type_suggestions %}<option value="{{ s }}">{% endfor %}
</datalist>
```

- [ ] **Step 8: Run tests**

```bash
python manage.py test app01.tests.AddExperimentReadoutTests -v 2
```

Expected: both tests PASS.

- [ ] **Step 9: Commit**

```bash
git add app01/views.py static/js/add_experiment.js templates/add_experiment.html app01/tests.py
git commit -m "feat: readout_type select+custom widget in add_experiment form"
```

---

### Task 7: readout_type select+custom in upload_prism_preview

**Files:**
- Modify: `app01/views.py` (update `upload_prism_preview` context; drop readout_type allowlist in `upload_prism_confirm`)
- Modify: `templates/upload_prism_preview.html`
- Test: `app01/tests.py`

- [ ] **Step 1: Write the failing test**

Add to `app01/tests.py`:

```python
class PrismConfirmCustomReadoutTests(TestCase):
    def setUp(self):
        from app01.models import Sequence, Delivery
        self.user = LmsUser.objects.create_user(
            username='testadmin4', password='pass',
            user_type='superadmin',
        )
        self.client.force_login(self.user)
        seq = Sequence.objects.create(seq='CCCC', seq_type='SS')
        Delivery.objects.create(
            sequence=seq,
            duplex_id='BP000006',
            project='P001',
        )
        # Set up session with parsed prism data
        session = self.client.session
        session['prism_parsed'] = {
            'matched': {
                'BP000006': {
                    'rows': [{'x': 7, 'replicates': [80.0, 82.0, 78.0], 'excluded': [False, False, False]}]
                }
            },
            'x_values': [7],
            'skipped_cols': [],
            'warnings': [],
        }
        session.save()

    def test_custom_readout_type_accepted_by_confirm(self):
        resp = self.client.post('/upload_prism_confirm/', {
            'batch': 'B007',
            'exp_type': 'in_vitro',
            'assay_type': 'single_point',
            'readout_type': '细胞活力',   # not in old READOUT_TYPE_CHOICES
            'x_axis_type': 'timepoint',
            'conc_unit': 'nM',
        })
        # Should redirect, not error
        self.assertEqual(resp.status_code, 302)
        dp = DataPoint.objects.filter(experiment__duplex_id='BP000006').first()
        self.assertIsNotNone(dp)
        self.assertEqual(dp.readout_type, '细胞活力')
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test app01.tests.PrismConfirmCustomReadoutTests -v 2
```

Expected: FAIL — the view rejects `细胞活力` because of the allowlist check.

- [ ] **Step 3: Update upload_prism_preview view context**

In `app01/views.py`, find `upload_prism_preview` view (around line 5137). Change the context to replace `readout_type_choices` with `readout_type_presets` and `readout_type_suggestions`:

Find:
```python
'readout_type_choices': DataPoint.READOUT_TYPE_CHOICES,
```
Replace with:
```python
'readout_type_presets': READOUT_TYPE_PRESETS,
'readout_type_suggestions': list(
    DataPoint.objects.values_list('readout_type', flat=True).distinct()[:50]
),
```

- [ ] **Step 4: Drop readout_type allowlist validation in upload_prism_confirm**

In `app01/views.py`, in `upload_prism_confirm` (around line 5228–5238), find:

```python
valid_readout_types = {c[0] for c in DataPoint.READOUT_TYPE_CHOICES}
...
if readout_type not in valid_readout_types:
    messages.error(request, f"无效的读数类型：{readout_type}")
    return redirect('upload_experiment')
```

Replace those three lines with:

```python
if not readout_type:
    messages.error(request, "读数类型不能为空")
    return redirect('upload_experiment')
```

Also truncate to max_length for safety (add after the empty check):
```python
readout_type = readout_type[:32]
```

- [ ] **Step 5: Update templates/upload_prism_preview.html**

Find the readout_type field block (lines 58–65):

```html
<div>
  <label class="ds-form-label">读数类型 *</label>
  <select name="readout_type" class="ds-form-control" required>
    {% for val, label in readout_type_choices %}
    <option value="{{ val }}">{{ label }}</option>
    {% endfor %}
  </select>
</div>
```

Replace with:

```html
<div>
  <label class="ds-form-label">读数类型 *</label>
  <select name="readout_type" id="prism_readout_select" class="readout-type-select ds-form-control" required>
    {% for p in readout_type_presets %}
    <option value="{{ p }}">{{ p }}</option>
    {% endfor %}
    <option value="__custom__">自定义…</option>
  </select>
  <input type="text" id="prism_readout_custom" name="readout_type_custom"
         class="readout-type-custom ds-form-control"
         list="readout_suggestions_prism" placeholder="输入读数类型"
         maxlength="32" style="display:none;margin-top:4px;">
  <datalist id="readout_suggestions_prism">
    {% for s in readout_type_suggestions %}<option value="{{ s }}">{% endfor %}
  </datalist>
</div>
```

At the bottom of the file, in the `<script>` block, add the toggle and submit logic:

```html
<script>
function toggleBioFields() {
  var t = document.getElementById('id_exp_type').value;
  document.getElementById('cell_line_row').style.display = (t === 'in_vitro') ? '' : 'none';
  document.getElementById('animal_species_row').style.display = (t === 'in_vivo') ? '' : 'none';
}
function toggleConcUnit() {
  var t = document.getElementById('id_x_axis_type').value;
  document.getElementById('conc_unit_row').style.display = (t === 'concentration') ? '' : 'none';
}

// Readout type select+custom
(function () {
  var sel = document.getElementById('prism_readout_select');
  var inp = document.getElementById('prism_readout_custom');
  sel.addEventListener('change', function () {
    if (sel.value === '__custom__') {
      sel.style.display = 'none';
      inp.style.display = '';
      inp.focus();
    }
  });
  inp.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      inp.style.display = 'none';
      sel.style.display = '';
      sel.value = sel.options[0].value;
    }
  });
  // Resolve on submit
  document.querySelector('form').addEventListener('submit', function () {
    if (sel.value === '__custom__') {
      sel.value = inp.value.trim() || '';
    }
  });
})();
</script>
```

- [ ] **Step 6: Run tests**

```bash
python manage.py test app01.tests.PrismConfirmCustomReadoutTests -v 2
```

Expected: PASS.

- [ ] **Step 7: Run full test suite to check for regressions**

```bash
python manage.py test app01 -v 1 2>&1 | tail -20
```

Note: pre-existing failures in `CheckDuplicatesTests` (4 errors) and `DropAuthorSecurityTests` (1 failure) are known and unrelated to this work. All other tests should pass.

- [ ] **Step 8: Commit**

```bash
git add app01/views.py templates/upload_prism_preview.html app01/tests.py
git commit -m "feat: readout_type select+custom widget in Prism upload; drop allowlist validation"
```

---

## Done

All tasks complete. The experiment data section now:
1. Accepts free-text readout types (model + both form UIs)
2. Shows experiments as a compact accordion list with pivot tables (Rep1/Rep2/Rep3/Mean/SD)
3. Provides dedicated detail pages at `/experiment/<duplex_id>/<exp_id>/`
