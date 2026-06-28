# Chart Y-Axis Min Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove three hardcoded `min: 0` constraints from chart y-axes so that negative KD% values are no longer clipped at the bottom of the plot.

**Architecture:** Pure JavaScript changes in two files. `compound_detail.html` uses jQuery Flot; `compound_list.js` uses Chart.js. Each fix is independent — the same root cause (hardcoded `min: 0`) has three separate instances.

**Tech Stack:** jQuery Flot (detail page charts), Chart.js (list page charts), Django HTML template.

---

## File Map

| File | Change |
|------|--------|
| `templates/compound_detail.html` | Task 1: add 2 lines in `plotOpts()` + replace `min: 0` with `min: ymin`; Task 2: add 1 line in `initInvivoBatchCharts()` + replace `min: 0` with `min: yminKd` |
| `static/js/compound_list.js` | Task 3: remove `min: 0` line in `_clInitVitroChart()`; add 1 line in `clToggleVitroReadout()` |

---

### Task 1: Fix `plotOpts()` y-axis min — `compound_detail.html:269–282`

**Files:**
- Modify: `templates/compound_detail.html:269–282`

**Background:** `plotOpts()` builds Flot chart options for vitro dose-response charts. It already computes `allY` and derives `ymax` dynamically. But the returned `yaxis` object hardcodes `min: 0`. If any data point has a negative KD% value, the bottom of the curve is invisible.

The current function body (lines 265–286):

```javascript
function plotOpts(seriesArr, ic50, axisLabel) {
  var xr = seriesXRange(seriesArr);
  var ticks = LOG_TICKS.filter(function(t) { return t[0] >= xr.min && t[0] <= xr.max; });

  var allY = [];
  seriesArr.forEach(function(s) {
    (s.data || []).forEach(function(p) { allY.push(p[1]); });
  });
  var ymax = allY.length ? Math.ceil(Math.max.apply(null, allY) * 1.08 / 10) * 10 : 110;
  if (ymax < 110) ymax = 110;

  var markings = [];
  if (ic50 != null) {
    markings = [
      { yaxis: { from: 50, to: 50 }, color: '#fbbf24', lineWidth: 1 },
      { xaxis: { from: Math.log10(ic50), to: Math.log10(ic50) }, color: '#fbbf24', lineWidth: 1 }
    ];
  }
  return {
    series: { lines: { show: true }, points: { show: true, radius: 3 } },
    xaxis:  { ticks: ticks, min: xr.min, max: xr.max, axisLabel: '浓度 (nM)', tickLength: 4 },
    yaxis:  { min: 0, max: ymax, axisLabel: axisLabel, labelWidth: 30 },
    grid:   { hoverable: false, borderWidth: 1, borderColor: '#e2e8f0', markings: markings },
    legend: { show: false }
  };
}
```

- [ ] **Step 1: Apply the code change**

Replace the function body with:

```javascript
function plotOpts(seriesArr, ic50, axisLabel) {
  var xr = seriesXRange(seriesArr);
  var ticks = LOG_TICKS.filter(function(t) { return t[0] >= xr.min && t[0] <= xr.max; });

  var allY = [];
  seriesArr.forEach(function(s) {
    (s.data || []).forEach(function(p) { allY.push(p[1]); });
  });
  var ymax = allY.length ? Math.ceil(Math.max.apply(null, allY) * 1.08 / 10) * 10 : 110;
  if (ymax < 110) ymax = 110;
  var ymin_data = allY.length ? Math.min.apply(null, allY) : 0;
  var ymin = (ymin_data < 0) ? Math.floor(ymin_data * 1.1 / 10) * 10 : 0;

  var markings = [];
  if (ic50 != null) {
    markings = [
      { yaxis: { from: 50, to: 50 }, color: '#fbbf24', lineWidth: 1 },
      { xaxis: { from: Math.log10(ic50), to: Math.log10(ic50) }, color: '#fbbf24', lineWidth: 1 }
    ];
  }
  return {
    series: { lines: { show: true }, points: { show: true, radius: 3 } },
    xaxis:  { ticks: ticks, min: xr.min, max: xr.max, axisLabel: '浓度 (nM)', tickLength: 4 },
    yaxis:  { min: ymin, max: ymax, axisLabel: axisLabel, labelWidth: 30 },
    grid:   { hoverable: false, borderWidth: 1, borderColor: '#e2e8f0', markings: markings },
    legend: { show: false }
  };
}
```

The two new lines are:
```javascript
var ymin_data = allY.length ? Math.min.apply(null, allY) : 0;
var ymin = (ymin_data < 0) ? Math.floor(ymin_data * 1.1 / 10) * 10 : 0;
```
And `min: 0` in the `yaxis` return value becomes `min: ymin`.

- [ ] **Step 2: Commit**

```bash
git add templates/compound_detail.html
git commit -m "fix: compute plotOpts() y-axis min from data instead of hardcoded 0"
```

---

### Task 2: Fix `initInvivoBatchCharts()` y-axis min — `compound_detail.html:394–395`

**Files:**
- Modify: `templates/compound_detail.html:394–395`

**Background:** `initInvivoBatchCharts()` draws per-experiment in-vivo time-series charts (KD% or body-weight change over days). It already computes `ymin` from all data points including ±SD. For body-weight change (the `else` branch) it uses `ymin` correctly. But for `knockdown_pct` (the `if` branch) it hardcodes `min: 0`.

The comment on line 382 says "避免负值数据被截掉" (avoid negative value data being clipped) — the intent was always to support negative values, but the `knockdown_pct` branch was missed.

The current block (lines 393–398):

```javascript
var yOpts;
if (d.readout_type === 'knockdown_pct') {
  yOpts = { min: 0, max: Math.max(ymax + ypad, 110), labelWidth: 30 };
} else {
  yOpts = { min: ymin - ypad, max: ymax + ypad, labelWidth: 30 };
}
```

- [ ] **Step 1: Apply the code change**

Replace just the `if (d.readout_type === 'knockdown_pct')` branch:

```javascript
var yOpts;
if (d.readout_type === 'knockdown_pct') {
  var yminKd = (ymin - ypad < 0) ? Math.floor((ymin - ypad) / 10) * 10 : 0;
  yOpts = { min: yminKd, max: Math.max(ymax + ypad, 110), labelWidth: 30 };
} else {
  yOpts = { min: ymin - ypad, max: ymax + ypad, labelWidth: 30 };
}
```

One line is added (`var yminKd = ...`) and `min: 0` becomes `min: yminKd`.

**Formula:** `Math.floor((ymin - ypad) / 10) * 10` floors to the nearest multiple of 10 below the data minimum (with padding). Examples:
- ymin = 5 (all ≥ 0): yminKd = 0
- ymin = −8, ypad = 2: `(−10)/10 = −1` → floor → `−1 × 10 = −10` → yminKd = −10
- ymin = −25, ypad = 3: `(−28)/10 = −2.8` → floor → `−3 × 10 = −30` → yminKd = −30

- [ ] **Step 2: Commit**

```bash
git add templates/compound_detail.html
git commit -m "fix: compute initInvivoBatchCharts() knockdown_pct y-axis min from data"
```

---

### Task 3: Fix list-page vitro chart y-axis — `compound_list.js`

**Files:**
- Modify: `static/js/compound_list.js:96` (`_clInitVitroChart`)
- Modify: `static/js/compound_list.js:465` (`clToggleVitroReadout`)

**Background:** `_clInitVitroChart()` (line 71) initializes a Chart.js line chart with `min: 0` hardcoded in the y-scale options. `clToggleVitroReadout()` (line 453) switches the dataset between mRNA% and KD% but never clears that stored `min: 0`, so Chart.js keeps the constraint on all subsequent data.

Fix: remove the `min: 0` line so Chart.js auto-scales from data on every render and update.

Current `_clInitVitroChart()` y-scale block (lines 95–99):

```javascript
y: {
  min: 0,
  title: { display: true, text: 'mRNA%', font: { size: 9 } },
  ticks: { font: { size: 9 } },
},
```

Current `clToggleVitroReadout()` tail (lines 462–466):

```javascript
chart.data.datasets[0].data  = pts.map(([x, y]) => ({ x, y }));
chart.data.datasets[0].label = readout === 'kd' ? 'KD%' : 'mRNA残余%';
chart.options.scales.y.title.text = readout === 'kd' ? 'KD%' : 'mRNA%';
chart.update();
```

- [ ] **Step 1: Remove `min: 0` from `_clInitVitroChart()`**

Replace the y-scale block with:

```javascript
y: {
  title: { display: true, text: 'mRNA%', font: { size: 9 } },
  ticks: { font: { size: 9 } },
},
```

- [ ] **Step 2: Reset y-axis min in `clToggleVitroReadout()` before `chart.update()`**

Replace the tail of `clToggleVitroReadout()` with:

```javascript
chart.data.datasets[0].data  = pts.map(([x, y]) => ({ x, y }));
chart.data.datasets[0].label = readout === 'kd' ? 'KD%' : 'mRNA残余%';
chart.options.scales.y.title.text = readout === 'kd' ? 'KD%' : 'mRNA%';
chart.options.scales.y.min = undefined;
chart.update();
```

The added line `chart.options.scales.y.min = undefined` tells Chart.js to auto-scale the lower bound from current data on every `update()`.

- [ ] **Step 3: Commit**

```bash
git add static/js/compound_list.js
git commit -m "fix: remove hardcoded min:0 from list-page vitro chart y-axis"
```

---

### Task 4: Start the dev server and verify visually

**Files:** None modified — verification only.

- [ ] **Step 1: Start the dev server**

```bash
source venv/bin/activate
python manage.py runserver
```

- [ ] **Step 2: Verify Fix 1 (plotOpts — vitro detail charts)**

Open the detail page for any compound with in-vitro experiment data. Expand the vitro accordion for a batch. If KD% values go below 0, the curve bottom should now be visible below the x-axis.

If no compound with negative KD% is readily available, verify that the y-axis still starts at 0 for all-positive data (no regression).

- [ ] **Step 3: Verify Fix 2 (initInvivoBatchCharts — in-vivo batch charts)**

Open the detail page for compound `20260623-001`. Locate the in-vivo section and find the chart containing the "alnylam" series. The lower half of the curve should now be visible (y-axis starts below 0 if the data requires it).

- [ ] **Step 4: Verify Fix 3 (list-page vitro charts)**

On the compound list page, locate a compound with a vitro card. Click to open the chart drawer. Toggle between mRNA% and KD% using the toggle buttons. Verify the y-axis lower bound adjusts correctly for each readout type.

- [ ] **Step 5: Run the Python test suite to confirm no regressions**

These are pure JS changes; the Python test suite should be unaffected. Run it as a baseline check:

```bash
source venv/bin/activate
python manage.py test app01 --keepdb -v 1
```

Expected: all 298 tests pass.

---

### Task 5: Lint check

**Files:** None modified — verification only.

- [ ] **Step 1: Run ruff on the Python codebase**

```bash
source venv/bin/activate
ruff check app01/views.py --select W293,E401
```

Expected: `All checks passed!` (no Python was touched).

- [ ] **Step 2: Commit only if ruff reported unexpected errors**

```bash
git add app01/views.py
git commit -m "chore: fix ruff lint violations"
```
