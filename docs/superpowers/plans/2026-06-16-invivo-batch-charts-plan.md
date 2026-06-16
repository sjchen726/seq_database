# In-Vivo Batch Charts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-batch Flot charts with SD error bars to the `compound_detail` page for in-vivo experiments (both KD% and body_weight readouts), alongside the existing aggregated KD% chart.

**Architecture:** A new `_build_invivo_chart_data(exp)` function (parallel to `_build_vitro_chart_data`) computes mean ± SD per timepoint from DataPoints and returns a JSON-safe dict. The `compound_detail` view maps it over all in-vivo experiments and passes the list to the template. The template serializes it inline with `json_script`, renders one `<div>` container per batch inside the existing in-vivo section, and the `jquery.flot.errorbars.js` plugin (already present) draws error-bar line charts.

**Tech Stack:** Django 5.1, Python 3.10, jQuery, Flot (`jquery.flot.js` + `jquery.flot.errorbars.js`), MySQL

---

## File Map

| File | Change |
|------|--------|
| `app01/views.py` | Add `_build_invivo_chart_data(exp)` after line 1049; add `invivo_chart_data` to `compound_detail` context (lines 1068–1082) |
| `app01/tests.py` | Add `BuildInvivoChartDataTest` class after `BuildInvivoRowsTest` (currently ends ~line 1707); add `CompoundDetailInvivoChartContextTest` after that |
| `templates/compound_detail.html` | Load errorbars plugin (line 201); add `json_script` tag (line 196); add per-batch chart divs (after line 167); add `INVIVO_CHART_DATA` constant + `initInvivoBatchCharts()` in extra_scripts block |

---

## Task 1: `_build_invivo_chart_data` function + unit tests

**Files:**
- Modify: `app01/views.py` (insert after line 1049)
- Modify: `app01/tests.py` (append new test class)

- [ ] **Step 1: Write the failing tests**

Append this class to `app01/tests.py` (after line 1833, the last line):

```python
# ---- BuildInvivoChartDataTest ----
class BuildInvivoChartDataTest(TestCase):
    def _make_exp(self, batch='B1', time_unit='day', dose_info='10mpk SC'):
        user = LmsUser.objects.create_user(
            username=f'u_{batch}', password='pass', user_type='admin'
        )
        cmp = Compound.objects.create(compound_id=f'BPR_TEST_{batch}', project='T')
        return Experiment.objects.create(
            compound=cmp, exp_type='in_vivo',
            batch_label=batch, time_unit=time_unit, dose_info=dose_info
        )

    def test_individual_replicates_mean_and_sd(self):
        from app01.views import _build_invivo_chart_data
        exp = self._make_exp('T1')
        for x, rep, val in [
            (7.0, 'A', 80.0), (7.0, 'B', 60.0),
            (14.0, 'A', 50.0), (14.0, 'B', 50.0),
        ]:
            DataPoint.objects.create(
                experiment=exp, x_type='timepoint', x_value=x,
                replicate=rep, readout_type='knockdown_pct', value=val, is_control=False
            )
        result = _build_invivo_chart_data(exp)
        self.assertEqual(result['readout_type'], 'knockdown_pct')
        pts = result['series'][0]['points']
        self.assertEqual(len(pts), 2)
        self.assertAlmostEqual(pts[0]['mean'], 70.0)   # mean(80, 60)
        self.assertAlmostEqual(pts[0]['sd'], 14.14, places=1)  # stdev(80, 60)
        self.assertAlmostEqual(pts[1]['sd'], 0.0)

    def test_n1_replicate_sd_is_zero(self):
        from app01.views import _build_invivo_chart_data
        exp = self._make_exp('T2')
        DataPoint.objects.create(
            experiment=exp, x_type='timepoint', x_value=7.0,
            replicate='A', readout_type='knockdown_pct', value=75.0, is_control=False
        )
        result = _build_invivo_chart_data(exp)
        self.assertEqual(result['series'][0]['points'][0]['sd'], 0.0)
        self.assertEqual(result['series'][0]['points'][0]['n'], 1)

    def test_mean_sd_fallback_when_no_individual_replicates(self):
        from app01.views import _build_invivo_chart_data
        exp = self._make_exp('T3')
        DataPoint.objects.create(
            experiment=exp, x_type='timepoint', x_value=7.0,
            replicate='Mean', readout_type='knockdown_pct', value=70.0, is_control=False
        )
        DataPoint.objects.create(
            experiment=exp, x_type='timepoint', x_value=7.0,
            replicate='SD', readout_type='knockdown_pct', value=8.5, is_control=False
        )
        result = _build_invivo_chart_data(exp)
        pts = result['series'][0]['points']
        self.assertAlmostEqual(pts[0]['mean'], 70.0)
        self.assertAlmostEqual(pts[0]['sd'], 8.5)
        self.assertEqual(pts[0]['n'], 1)

    def test_body_weight_readout_type(self):
        from app01.views import _build_invivo_chart_data
        exp = self._make_exp('T4')
        DataPoint.objects.create(
            experiment=exp, x_type='timepoint', x_value=0.0,
            replicate='Mean', readout_type='body_weight', value=22.0, is_control=False
        )
        result = _build_invivo_chart_data(exp)
        self.assertEqual(result['readout_type'], 'body_weight')

    def test_controls_excluded(self):
        from app01.views import _build_invivo_chart_data
        exp = self._make_exp('T5')
        DataPoint.objects.create(
            experiment=exp, x_type='timepoint', x_value=7.0,
            replicate='A', readout_type='knockdown_pct', value=5.0, is_control=True
        )
        DataPoint.objects.create(
            experiment=exp, x_type='timepoint', x_value=7.0,
            replicate='A', readout_type='knockdown_pct', value=80.0, is_control=False
        )
        result = _build_invivo_chart_data(exp)
        pts = result['series'][0]['points']
        self.assertEqual(len(pts), 1)
        self.assertAlmostEqual(pts[0]['mean'], 80.0)

    def test_empty_datapoints_returns_empty_series(self):
        from app01.views import _build_invivo_chart_data
        exp = self._make_exp('T6')
        result = _build_invivo_chart_data(exp)
        self.assertEqual(result['series'], [])
        self.assertEqual(result['exp_id'], exp.id)
        self.assertEqual(result['batch_label'], 'T6')

    def test_time_unit_and_batch_label_in_result(self):
        from app01.views import _build_invivo_chart_data
        exp = self._make_exp('T7', time_unit='week')
        DataPoint.objects.create(
            experiment=exp, x_type='timepoint', x_value=1.0,
            replicate='Mean', readout_type='knockdown_pct', value=60.0, is_control=False
        )
        result = _build_invivo_chart_data(exp)
        self.assertEqual(result['time_unit'], 'week')
        self.assertEqual(result['batch_label'], 'T7')
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_bprdb && source ../seq_database_v2/venv/bin/activate && python manage.py test app01.tests.BuildInvivoChartDataTest -v 2 2>&1 | tail -20
```

Expected: `AttributeError: module 'app01.views' has no attribute '_build_invivo_chart_data'`

- [ ] **Step 3: Implement `_build_invivo_chart_data` in `views.py`**

Insert the following block **between** line 1049 (the blank line after `_build_vitro_chart_data`) and line 1051 (`@login_required`). The exact old string to match is the two blank lines before `@login_required`:

In `app01/views.py`, find the section ending with:
```python
        'kd_mean':     kd_mean,
        'kd_a':        kd_a,
        'kd_b':        kd_b,
    }


@login_required
def compound_detail(request, compound_id):
```

Replace with:
```python
        'kd_mean':     kd_mean,
        'kd_a':        kd_a,
        'kd_b':        kd_b,
    }


def _build_invivo_chart_data(exp):
    all_dps = list(exp.datapoints.all())
    timepoint_dps = [
        dp for dp in all_dps
        if dp.x_type == 'timepoint' and not dp.is_control
        and dp.x_value is not None and dp.value is not None
    ]
    if not timepoint_dps:
        return {
            'exp_id':       exp.id,
            'batch_label':  exp.batch_label,
            'readout_type': 'knockdown_pct',
            'time_unit':    exp.time_unit or 'day',
            'series':       [],
        }

    readout_types = {dp.readout_type for dp in timepoint_dps}
    if 'knockdown_pct' in readout_types:
        readout_type = 'knockdown_pct'
    elif 'body_weight' in readout_types:
        readout_type = 'body_weight'
    else:
        readout_type = next(iter(readout_types))

    dps = [dp for dp in timepoint_dps if dp.readout_type == readout_type]
    individual = [dp for dp in dps if dp.replicate not in ('Mean', 'SD')]

    if individual:
        grouped = defaultdict(list)
        for dp in individual:
            grouped[dp.x_value].append(dp.value)
        points = []
        for x in sorted(grouped):
            vals = grouped[x]
            n = len(vals)
            mean = _statistics.mean(vals)
            sd = _statistics.stdev(vals) if n >= 2 else 0.0
            points.append({'x': x, 'mean': round(mean, 2), 'sd': round(sd, 2), 'n': n})
    else:
        mean_map = {dp.x_value: dp.value for dp in dps if dp.replicate == 'Mean'}
        sd_map   = {dp.x_value: dp.value for dp in dps if dp.replicate == 'SD'}
        points = []
        for x in sorted(mean_map):
            mean = mean_map[x]
            sd   = sd_map.get(x, 0.0) or 0.0
            points.append({'x': x, 'mean': round(mean, 2), 'sd': round(sd, 2), 'n': 1})

    label = (exp.dose_info or '').strip() or exp.batch_label

    return {
        'exp_id':       exp.id,
        'batch_label':  exp.batch_label,
        'readout_type': readout_type,
        'time_unit':    exp.time_unit or 'day',
        'series': [{'label': label, 'points': points}] if points else [],
    }


@login_required
def compound_detail(request, compound_id):
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python manage.py test app01.tests.BuildInvivoChartDataTest -v 2 2>&1 | tail -15
```

Expected: `OK (tests=7)`

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
python manage.py test app01 2>&1 | tail -5
```

Expected: `OK` with 182 tests (175 + 7 new)

- [ ] **Step 6: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "feat: add _build_invivo_chart_data with SD error bar support"
```

---

## Task 2: Update `compound_detail` view context

**Files:**
- Modify: `app01/views.py` (lines 1051–1082 after Task 1 insert)

- [ ] **Step 1: Write the failing test**

Append to `app01/tests.py` (after the `BuildInvivoChartDataTest` class):

```python
# ---- CompoundDetailInvivoChartContextTest ----
class CompoundDetailInvivoChartContextTest(TestCase):
    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='ctx_tester', password='pass', user_type='admin'
        )
        self.client.login(username='ctx_tester', password='pass')
        self.cmp = Compound.objects.create(compound_id='BPR_CTX01', project='CTX')
        self.exp = Experiment.objects.create(
            compound=self.cmp, exp_type='in_vivo',
            batch_label='B2026', time_unit='day', dose_info='5mpk SC'
        )
        DataPoint.objects.create(
            experiment=self.exp, x_type='timepoint', x_value=7.0,
            replicate='Mean', readout_type='knockdown_pct', value=70.0, is_control=False
        )

    def test_invivo_chart_data_in_context(self):
        resp = self.client.get(f'/compounds/BPR_CTX01/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('invivo_chart_data', resp.context)

    def test_invivo_chart_data_has_correct_structure(self):
        resp = self.client.get(f'/compounds/BPR_CTX01/')
        data = resp.context['invivo_chart_data']
        self.assertEqual(len(data), 1)
        item = data[0]
        self.assertEqual(item['exp_id'], self.exp.id)
        self.assertEqual(item['batch_label'], 'B2026')
        self.assertEqual(item['readout_type'], 'knockdown_pct')
        self.assertEqual(len(item['series']), 1)
        self.assertEqual(item['series'][0]['points'][0]['x'], 7.0)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test app01.tests.CompoundDetailInvivoChartContextTest -v 2 2>&1 | tail -10
```

Expected: `AssertionError: 'invivo_chart_data' not found in context`

- [ ] **Step 3: Update `compound_detail` view**

In `app01/views.py`, find the `compound_detail` function. The current render call is:

```python
    vitro_chart_data = [_build_vitro_chart_data(exp) for exp in vitro]
    invivo_batches = build_invivo_summary(vivo).get(compound_id, [])
    all_attachments = list(
        ExperimentAttachment.objects.filter(
            experiment__compound_id=compound_id
        ).select_related('experiment').order_by('-uploaded_at')
    )
    return render(request, 'compound_detail.html', {
        'compound':         compound,
        'strands':          strands,
        'vitro_batches':    vitro,
        'vitro_chart_data': vitro_chart_data,
        'invivo_batches':   invivo_batches,
        'all_attachments':  all_attachments,
    })
```

Replace with:

```python
    vitro_chart_data = [_build_vitro_chart_data(exp) for exp in vitro]
    invivo_batches = build_invivo_summary(vivo).get(compound_id, [])
    invivo_chart_data = [_build_invivo_chart_data(exp) for exp in vivo]
    all_attachments = list(
        ExperimentAttachment.objects.filter(
            experiment__compound_id=compound_id
        ).select_related('experiment').order_by('-uploaded_at')
    )
    return render(request, 'compound_detail.html', {
        'compound':          compound,
        'strands':           strands,
        'vitro_batches':     vitro,
        'vitro_chart_data':  vitro_chart_data,
        'invivo_batches':    invivo_batches,
        'invivo_chart_data': invivo_chart_data,
        'all_attachments':   all_attachments,
    })
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python manage.py test app01.tests.CompoundDetailInvivoChartContextTest -v 2 2>&1 | tail -10
```

Expected: `OK (tests=2)`

- [ ] **Step 5: Run full test suite**

```bash
python manage.py test app01 2>&1 | tail -5
```

Expected: `OK` with 184 tests

- [ ] **Step 6: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "feat: pass invivo_chart_data to compound_detail context"
```

---

## Task 3: Template — per-batch chart divs, errorbars plugin, JS

**Files:**
- Modify: `templates/compound_detail.html`

No new test class needed for this task — template rendering is covered by the existing `CompoundDetailViewTest` (which checks status 200 and content). Manual browser verification is required after this task.

- [ ] **Step 1: Load `jquery.flot.errorbars.js` in extra_scripts**

In `templates/compound_detail.html`, find:

```html
<script src="/static/vendors/flot/jquery.flot.js"></script>
```

Replace with:

```html
<script src="/static/vendors/flot/jquery.flot.js"></script>
<script src="/static/vendors/flot/jquery.flot.errorbars.js"></script>
```

- [ ] **Step 2: Add `invivo_chart_data` JSON inline data**

In `templates/compound_detail.html`, find:

```html
{# JSON 数据内联 #}
{{ vitro_chart_data|json_script:"vitro-chart-data" }}
{{ invivo_batches|json_script:"invivo-batches-data" }}
```

Replace with:

```html
{# JSON 数据内联 #}
{{ vitro_chart_data|json_script:"vitro-chart-data" }}
{{ invivo_batches|json_script:"invivo-batches-data" }}
{{ invivo_chart_data|json_script:"invivo-chart-data" }}
```

- [ ] **Step 3: Add per-batch chart containers in the in-vivo section**

In `templates/compound_detail.html`, find:

```html
  {% endwith %}

  {# 体内折线图 #}
```

Replace with:

```html
  {% endwith %}

  {# 体内各批次图表 #}
  {% for item in invivo_chart_data %}
  {% if item.series %}
  <div style="padding:4px 14px 8px;">
    <div style="font-size:11px;font-weight:600;color:#92400e;margin-bottom:4px;">
      {{ item.batch_label }}
      · {% if item.readout_type == 'knockdown_pct' %}KD%{% else %}体重 (g){% endif %}
      时间曲线
    </div>
    <div id="invivo-chart-{{ item.exp_id }}" style="height:200px;"></div>
  </div>
  {% endif %}
  {% endfor %}

  {# 体内折线图 #}
```

- [ ] **Step 4: Add `INVIVO_CHART_DATA` constant and `initInvivoBatchCharts` function in JS**

In `templates/compound_detail.html`, find (in the `{% block extra_scripts %}` block):

```javascript
const LOG_TICKS = [[-3,'0.001'],[-2,'0.01'],[-1,'0.1'],[0,'1'],[1,'10'],[2,'100'],[3,'1000']];
const VITRO_DATA  = JSON.parse(document.getElementById('vitro-chart-data').textContent);
const INVIVO_DATA = JSON.parse(document.getElementById('invivo-batches-data').textContent);
const chartInited = {};   // {expId: true} 记录已初始化的图表
```

Replace with:

```javascript
const LOG_TICKS = [[-3,'0.001'],[-2,'0.01'],[-1,'0.1'],[0,'1'],[1,'10'],[2,'100'],[3,'1000']];
const VITRO_DATA       = JSON.parse(document.getElementById('vitro-chart-data').textContent);
const INVIVO_DATA      = JSON.parse(document.getElementById('invivo-batches-data').textContent);
const INVIVO_CHART_DATA = JSON.parse(document.getElementById('invivo-chart-data').textContent);
const chartInited = {};   // {expId: true} 记录已初始化的图表
```

- [ ] **Step 5: Add `initInvivoBatchCharts` function after `initInvivoChart`**

In `templates/compound_detail.html`, find:

```javascript
// ── 批次手风琴 ────────────────────────────────────────────────────────────
$(document).on('click', '.detail-batch-hdr', function() {
```

Insert **before** that line:

```javascript
// ── 体内各批次图表 ────────────────────────────────────────────────────────
function initInvivoBatchCharts() {
  var colors = ['#f97316','#3b82f6','#10b981','#a855f7','#ec4899'];
  INVIVO_CHART_DATA.forEach(function(d) {
    var container = document.getElementById('invivo-chart-' + d.exp_id);
    if (!container || !d.series.length) return;

    var series = d.series.map(function(s, i) {
      return {
        label: s.label,
        color: colors[i % colors.length],
        data: s.points.map(function(p) {
          var lo = p.mean - p.sd;
          var hi = p.mean + p.sd;
          return [p.x, p.mean, lo, hi];
        }),
        points: {
          show: true,
          errorbars: 'y',
          yerr: { show: true, upperCap: '-', lowerCap: '-', radius: 3, lineWidth: 1.5 }
        },
        lines: { show: true, lineWidth: 2 }
      };
    });

    var yLabel = d.readout_type === 'knockdown_pct' ? 'KD %' : '体重 (g)';
    $.plot(container, series, {
      xaxis: { axisLabel: d.time_unit, tickLength: 4 },
      yaxis: { min: 0, axisLabel: yLabel, labelWidth: 30 },
      grid:  { hoverable: false, borderWidth: 1, borderColor: '#fde68a' },
      legend: { show: d.series.length > 1, position: 'topright', backgroundOpacity: 0.7 }
    });
  });
}

// ── 批次手风琴 ────────────────────────────────────────────────────────────
$(document).on('click', '.detail-batch-hdr', function() {
```

- [ ] **Step 6: Call `initInvivoBatchCharts()` in the page-ready block**

In `templates/compound_detail.html`, find:

```javascript
  // 初始化体内折线图
  initInvivoChart();
```

Replace with:

```javascript
  // 初始化体内各批次图表
  initInvivoBatchCharts();
  // 初始化体内折线图
  initInvivoChart();
```

- [ ] **Step 7: Run full test suite to confirm no regressions**

```bash
python manage.py test app01 2>&1 | tail -5
```

Expected: `OK` with 184 tests

- [ ] **Step 8: Manual browser verification**

Start dev server:
```bash
python manage.py runserver 8001
```

Open a compound with in-vivo data (e.g., `http://localhost:8001/compounds/<compound_id>/`).

Verify:
1. Per-batch chart divs appear in the in-vivo section (between summary table and aggregated chart)
2. KD% charts show line + error bars (where SD > 0)
3. Body_weight charts (if present) show correct y-axis label "体重 (g)"
4. Chart with n=1 replicates renders without error bars (zero-height bars)
5. Aggregated KD% chart (`#chart-invivo`) still renders correctly
6. Vitro batch charts unaffected
7. No JS console errors

- [ ] **Step 9: Commit**

```bash
git add templates/compound_detail.html
git commit -m "feat: add per-batch invivo charts with SD error bars to compound_detail"
```
