# Chart Y-Axis Min Fix — Design Spec

**Date:** 2026-06-28
**Scope:** Three JS fixes across `templates/compound_detail.html` and `static/js/compound_list.js`

---

## 1. Background

RNA interference experiments can produce KD% values below 0 due to normalization variation. Three chart functions hardcode `min: 0` for their y-axis, causing any negative data point to be silently clipped at the bottom of the plot.

The affected charts are:

| Chart | Location | Readout type | Symptom |
|-------|----------|--------------|---------|
| 体内各批次对比图（per-experiment） | `initInvivoBatchCharts()` | knockdown_pct | 负 KD% 下半截断 |
| 体外剂量-效应图（detail page） | `plotOpts()` | mRNA% / KD% | 负 KD% 下半截断 |
| 列表页体外小图 | `_clInitVitroChart()` + `clToggleVitroReadout()` | mRNA% / KD% | 切换到 KD% 后负值截断 |

---

## 2. Root Cause

### Fix 1 — `initInvivoBatchCharts()` (`compound_detail.html` ~line 394)

The function already computes `ymin` from data (including ±SD), and the `else` branch (body-weight change) already uses it. But the `knockdown_pct` branch hardcodes `min: 0`:

```javascript
if (d.readout_type === 'knockdown_pct') {
  yOpts = { min: 0, max: Math.max(ymax + ypad, 110), labelWidth: 30 };  // ← bug
} else {
  yOpts = { min: ymin - ypad, max: ymax + ypad, labelWidth: 30 };        // ← correct
}
```

### Fix 2 — `plotOpts()` (`compound_detail.html` ~line 282)

`allY` is already computed but the computed minimum is unused; `min: 0` is hardcoded:

```javascript
yaxis: { min: 0, max: ymax, axisLabel: axisLabel, labelWidth: 30 },  // ← bug
```

### Fix 3 — `compound_list.js`

`_clInitVitroChart()` sets `min: 0` in Chart.js scale options. When `clToggleVitroReadout()` switches from mRNA% to KD%, it updates data and title but does not clear `chart.options.scales.y.min`, so the `0` constraint persists.

---

## 3. Fix

### Fix 1: `initInvivoBatchCharts()` knockdown_pct branch

Add one line to compute a dynamic floor, then use it:

```javascript
// before: yOpts = { min: 0, ... }
var yminKd = (ymin - ypad < 0) ? Math.floor((ymin - ypad) / 10) * 10 : 0;
yOpts = { min: yminKd, max: Math.max(ymax + ypad, 110), labelWidth: 30 };
```

**Y-axis lower bound logic (knockdown_pct):**

| Data minimum (incl. SD) | yminKd |
|-------------------------|--------|
| 5 (all ≥ 0)             | 0      |
| −8                      | −20    |
| −25                     | −30    |

### Fix 2: `plotOpts()` — use computed ymin

After the existing `allY` / `ymax` block, add:

```javascript
var ymin_data = allY.length ? Math.min.apply(null, allY) : 0;
var ymin = (ymin_data < 0) ? Math.floor(ymin_data * 1.1 / 10) * 10 : 0;
```

Replace `min: 0` with `min: ymin` in the returned `yaxis` object.

### Fix 3: `compound_list.js`

**`_clInitVitroChart()`** — remove `min: 0` from y-scale options entirely; Chart.js auto-scales from data.

**`clToggleVitroReadout()`** — before `chart.update()`, reset the y-axis minimum:

```javascript
chart.options.scales.y.min = undefined;
chart.update();
```

This lets Chart.js recalculate the lower bound whenever the user switches between mRNA% and KD%.

---

## 4. Scope

| File | Change |
|------|--------|
| `templates/compound_detail.html` | Fix 1 (1 line added + 1 line changed) + Fix 2 (2 lines added + 1 line changed) |
| `static/js/compound_list.js` | Fix 3 (remove `min: 0`; add 1 line in toggle handler) |

No Python, no migrations, no other files touched.

---

## 5. Testing

1. Open compound detail page for a compound with in-vivo experiments where any KD% timepoint is negative → verify the curve bottom is no longer clipped.
2. Open compound detail page for a compound with vitro experiments where KD% data has negative values → verify `plotOpts()` shows full curve.
3. On the compound list page, click a vitro chart card, toggle to KD%, verify the y-axis lower bound reflects negative values if present.
4. For all-positive data, verify y-axis still starts at 0 (no regression).
