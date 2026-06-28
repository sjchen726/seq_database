# In-Vivo Chart Y-Axis Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the in-vivo multi-batch comparison chart on the compound detail page so the y-axis upper bound is computed from actual data instead of being hardcoded to 105.

**Architecture:** Pure JavaScript change inside a Django HTML template. The function `initInvivoChart()` in `templates/compound_detail.html` reads `INVIVO_DATA` (already available as a parsed JSON constant on the page) to compute the maximum KD% value, then derives a rounded upper bound with 10% headroom. No backend, no migration, no other files touched.

**Tech Stack:** jQuery Flot (charting), inline JavaScript in Django template.

---

## File Map

| File | Change |
|------|--------|
| `templates/compound_detail.html` | Add 6-line ymax computation + replace `max: 105` with `max: ymax` in `initInvivoChart()` |

---

### Task 1: Fix `initInvivoChart()` y-axis upper bound

**Files:**
- Modify: `templates/compound_detail.html:337–355`

**Background:** `initInvivoChart()` draws a Flot line chart comparing KD% over time across all in-vivo batches for a compound. The Flot y-axis option `max: 105` is hardcoded. If any batch has a timepoint with KD% above 105, that part of the curve is invisible. The fix adds a small block before the `$.plot()` call that scans `INVIVO_DATA` for the maximum KD% and computes a dynamic upper bound.

`INVIVO_DATA` is already a JavaScript constant defined at the top of the script block:
```javascript
const INVIVO_DATA = JSON.parse(document.getElementById('invivo-batches-data').textContent);
```
Its structure is:
```javascript
[
  { batch_label: "BATCH01", timepoints: [{day: 7, kd_pct: 92.3}, {day: 14, kd_pct: 108.5}] },
  ...
]
```

- [ ] **Step 1: Apply the code change**

In `templates/compound_detail.html`, find `initInvivoChart()` at line 337. The current function body is:

```javascript
function initInvivoChart() {
  if (!INVIVO_DATA.length) return;
  var colors = ['#f97316','#92400e','#3b82f6','#10b981','#a855f7'];
  var series = INVIVO_DATA.map(function(batch, i) {
    return {
      label: batch.batch_label,
      data:  batch.timepoints.map(function(tp) { return [tp.day, tp.kd_pct]; }),
      color: colors[i % colors.length],
      lines: { show: true, lineWidth: 2 },
      points: { show: true, radius: 4 }
    };
  });
  $.plot('#chart-invivo', series, {
    xaxis: { axisLabel: '时间点 (day)', tickLength: 4 },
    yaxis: { min: 0, max: 105, axisLabel: 'KD %', labelWidth: 30 },
    grid:  { hoverable: false, borderWidth: 1, borderColor: '#fde68a' },
    legend: { show: true, position: 'topright', backgroundOpacity: 0.7 }
  });
}
```

Replace with:

```javascript
function initInvivoChart() {
  if (!INVIVO_DATA.length) return;
  var colors = ['#f97316','#92400e','#3b82f6','#10b981','#a855f7'];
  var series = INVIVO_DATA.map(function(batch, i) {
    return {
      label: batch.batch_label,
      data:  batch.timepoints.map(function(tp) { return [tp.day, tp.kd_pct]; }),
      color: colors[i % colors.length],
      lines: { show: true, lineWidth: 2 },
      points: { show: true, radius: 4 }
    };
  });
  var allKd = [];
  INVIVO_DATA.forEach(function(b) {
    (b.timepoints || []).forEach(function(tp) {
      if (tp.kd_pct != null) allKd.push(tp.kd_pct);
    });
  });
  var kdMax = allKd.length ? Math.max.apply(null, allKd) : 100;
  var ymax  = Math.max(Math.ceil(kdMax * 1.1 / 10) * 10, 110);
  $.plot('#chart-invivo', series, {
    xaxis: { axisLabel: '时间点 (day)', tickLength: 4 },
    yaxis: { min: 0, max: ymax, axisLabel: 'KD %', labelWidth: 30 },
    grid:  { hoverable: false, borderWidth: 1, borderColor: '#fde68a' },
    legend: { show: true, position: 'topright', backgroundOpacity: 0.7 }
  });
}
```

The only structural changes are:
1. The 6-line block computing `allKd`, `kdMax`, and `ymax` is inserted between the `series` declaration and the `$.plot()` call.
2. `max: 105` is replaced with `max: ymax`.

- [ ] **Step 2: Start the dev server and verify visually**

```bash
source venv/bin/activate
python manage.py runserver
```

Open a compound detail page that has in-vivo experiments. Look for the "体内" (in-vivo) section. The multi-batch comparison chart should:
- For compounds where all KD% ≤ 100: y-axis still reads 0–110 (same as before)
- For compounds where any KD% > 105: y-axis extends to cover the full curve (e.g., 0–120 for KD% up to 108)

If no compound with high KD% is readily available, open the browser console on any detail page with in-vivo data and run:
```javascript
var allKd = [];
INVIVO_DATA.forEach(function(b) {
  (b.timepoints || []).forEach(function(tp) {
    if (tp.kd_pct != null) allKd.push(tp.kd_pct);
  });
});
console.log('max KD%:', Math.max.apply(null, allKd));
```
Confirm the logged max matches what the y-axis now shows (with 10% headroom rounded up).

- [ ] **Step 3: Run the Python test suite to confirm no regressions**

```bash
python manage.py test app01 --keepdb -v 1
```

Expected: all 298 tests pass. This change is pure frontend JS so no Python tests should be affected, but run the suite as a baseline check.

- [ ] **Step 4: Commit**

```bash
git add templates/compound_detail.html
git commit -m "fix: compute initInvivoChart y-axis max from data instead of hardcoded 105"
```

---

### Task 2: Lint check

**Files:** None modified — verification only.

- [ ] **Step 1: Run ruff on Python files (unchanged but baseline)**

```bash
source venv/bin/activate
ruff check app01/views.py --select W293,E401
```

Expected: `All checks passed!` (no Python was touched, this just confirms no drift).

- [ ] **Step 2: Commit if needed**

Only if ruff reported errors (unexpected):
```bash
git add app01/views.py
git commit -m "chore: fix ruff lint violations"
```
