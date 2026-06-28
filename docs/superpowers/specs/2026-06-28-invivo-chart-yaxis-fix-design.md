# In-Vivo Chart Y-Axis Fix — Design Spec

**Date:** 2026-06-28
**Scope:** One JS change in `templates/compound_detail.html`

---

## 1. Background

On the compound detail page, the in-vivo multi-batch comparison chart (`initInvivoChart()`) has its y-axis maximum hardcoded to `105`. RNA interference experiments routinely produce KD% values above 105 due to normalization variation. Any batch with a timepoint KD% exceeding 105 is silently clipped at the top, making the curve appear truncated.

The per-experiment batch charts (`initInvivoBatchCharts()`) already compute their y-axis dynamically from data including SD — this fix brings `initInvivoChart()` into line with that approach.

---

## 2. Root Cause

In `templates/compound_detail.html`, function `initInvivoChart()` (~line 349):

```javascript
yaxis: { min: 0, max: 105, axisLabel: 'KD %', labelWidth: 30 },
```

`max: 105` is a hardcoded constant. Any KD% value above 105 at any timepoint in any batch is rendered outside the visible plot area.

---

## 3. Fix

**Location:** `templates/compound_detail.html`, inside `initInvivoChart()`, immediately before the `$.plot(...)` call.

Add a 6-line block that computes `ymax` from `INVIVO_DATA` (already available as a parsed JSON constant on the page):

```javascript
var allKd = [];
INVIVO_DATA.forEach(function(b) {
  (b.timepoints || []).forEach(function(tp) {
    if (tp.kd_pct != null) allKd.push(tp.kd_pct);
  });
});
var kdMax = allKd.length ? Math.max.apply(null, allKd) : 100;
var ymax  = Math.max(Math.ceil(kdMax * 1.1 / 10) * 10, 110);
```

Then replace the hardcoded `max: 105` with the computed `max: ymax`:

```javascript
yaxis: { min: 0, max: ymax, axisLabel: 'KD %', labelWidth: 30 },
```

**Y-axis upper bound logic:**

| Data max | Computed ymax |
|----------|---------------|
| 95       | 110 (floor)   |
| 108      | 120           |
| 130      | 150           |
| empty    | 110 (fallback)|

The formula: `ceil(max × 1.1 / 10) × 10`, minimum 110. This gives 10% headroom rounded to the nearest 10, matching the style used in `initInvivoBatchCharts()`.

---

## 4. Scope

| File | Change |
|------|--------|
| `templates/compound_detail.html` | Add 6-line ymax computation + replace `max: 105` with `max: ymax` |

No Python, no migrations, no other JS files touched.

---

## 5. Testing

Open the detail page for any compound with multiple in-vivo batches where at least one batch has a timepoint KD% above 105. Verify the multi-batch comparison chart shows the full curve with the peak visible.

For compounds where all KD% values are ≤ 100, the chart y-axis should remain at 110 (unchanged from previous behaviour for normal data).
