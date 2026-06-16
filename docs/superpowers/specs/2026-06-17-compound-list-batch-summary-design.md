# Compound List — Batch Summary Chart & UX Improvements

**Date:** 2026-06-17  
**Scope:** `templates/compound_list.html` only (CSS + JS). No backend changes.

---

## Goal

Five improvements to the compound list page:

1. Auto-render mRNA% chart on row expand (no click required)
2. Default grouping mode = 按批次+类型 (not 按化合物)
3. Batch group header shows a multi-series summary line chart (one line per compound)
4. Batch group header rows visually distinct from column header row
5. Current template backed up as `.bak2` before any edits

---

## Backup

Before any edit: `cp templates/compound_list.html templates/compound_list.html.bak2`

A `.bak` already exists from the previous redesign. `.bak2` preserves the current state.

---

## Change 1 — Auto-Render Chart on Expand

**Current state:** `toggleRow()` uses a polling loop (`tryRender`) that checks `offsetWidth > 0` every 30 ms, up to 20 retries. This is already implemented. Verify it works; no design change needed.

---

## Change 2 — Default Grouping

In the JS initialisation block at the bottom of `{% block extra_scripts %}`:

```javascript
// Before:
var initGroup = urlParams.get('group') || 'compound';

// After:
var initGroup = urlParams.get('group') || 'batch';
```

The `<select id="cl-group-sel">` value is set from `initGroup`, so the dropdown will reflect the default correctly.

---

## Change 3 — Batch Group Header Styling

Replace the existing `.cl-gh` / `.cl-gh-label` / `.cl-gh-count` CSS with type-aware variants.

**CSS additions/replacements:**

```css
/* remove old .cl-gh background — replaced by type-specific classes */
.cl-gh { /* no background here */ }
.cl-gh td {
  padding: 0;                        /* inner divs handle padding */
  border-bottom: 1px solid #e2e8f0;
}

/* vitro batch header: blue left stripe + light blue bg */
.cl-gh-vitro td {
  background: #eff6ff;
  border-top: 2px solid #93c5fd;
  border-left: 4px solid #3b82f6;
}

/* invivo batch header: orange left stripe + light orange bg */
.cl-gh-vivo td {
  background: #fff7ed;
  border-top: 2px solid #fdba74;
  border-left: 4px solid #f97316;
}

/* header label row inside td */
.cl-gh-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 12px 4px;
}
.cl-gh-label {
  font-size: 12px;
  font-weight: 700;
  font-family: monospace;
  color: #1e40af;          /* vitro */
}
.cl-gh-label-vivo {
  font-size: 12px;
  font-weight: 700;
  font-family: monospace;
  color: #9a3412;          /* invivo */
}
.cl-gh-count {
  font-size: 11px;
  color: #64748b;
}
```

Column header `thead` stays `#f1f5f9` — clearly different from both batch header colours.

---

## Change 4 — Batch Summary Chart

### CSS

```css
.cl-bgh-chart-wrap {
  padding: 2px 12px 10px;
}
.cl-bgh-chart {
  height: 160px;
  width: 100%;
}
```

### JS — `applyBatchGrouping()` rewrite

Key changes inside the function:

1. **Add type class to group header row:**
   ```javascript
   gh.className = 'cl-gh ' + (p.type === 'in_vitro' ? 'cl-gh-vitro' : 'cl-gh-vivo');
   ```

2. **Restructure td content — header div + chart div:**
   ```javascript
   // header row
   var headerDiv = document.createElement('div');
   headerDiv.className = 'cl-gh-header';
   var labelSpan = document.createElement('span');
   labelSpan.className = p.type === 'in_vitro' ? 'cl-gh-label' : 'cl-gh-label-vivo';
   labelSpan.textContent = p.batch + ' · ' + typeLabel;
   var countSpan = document.createElement('span');
   countSpan.className = 'cl-gh-count';
   countSpan.textContent = cnt + ' 个化合物';
   headerDiv.appendChild(labelSpan);
   headerDiv.appendChild(countSpan);
   td.appendChild(headerDiv);

   // summary chart
   var chartKey = p.batch.replace(/[^a-zA-Z0-9]/g, '_') + '_' + p.type;
   var chartId = 'cl-bgh-' + chartKey;
   var chartWrap = document.createElement('div');
   chartWrap.className = 'cl-bgh-chart-wrap';
   var chartDiv = document.createElement('div');
   chartDiv.id = chartId;
   chartDiv.className = 'cl-bgh-chart';
   chartWrap.appendChild(chartDiv);
   td.appendChild(chartWrap);
   ```

3. **Collect exp_ids for the group, schedule render:**
   ```javascript
   var groupExpIds = [];
   pairs.filter(function(x) {
     return x.batch === p.batch && x.type === p.type;
   }).forEach(function(gp) {
     var er = gp.er;
     var vtEl = er.querySelector('[id^="cl-vt-"]');
     var ivEl = er.querySelector('[id^="cl-iv-"]');
     if (vtEl) groupExpIds.push({ id: parseInt(vtEl.id.replace('cl-vt-', '')), kind: 'vitro' });
     if (ivEl) groupExpIds.push({ id: parseInt(ivEl.id.replace('cl-iv-', '')), kind: 'invivo' });
   });

   // capture variables for async render
   (function(cid, eids) {
     (function tryBgh(n) {
       var el = document.getElementById(cid);
       if (el && el.offsetWidth > 0) {
         renderBatchSummary(cid, eids);
       } else if (n > 0) {
         setTimeout(function() { tryBgh(n - 1); }, 30);
       }
     })(20);
   })(chartId, groupExpIds);
   ```

### JS — `renderBatchSummary(chartId, expIds)` (new function)

```javascript
var BGH_COLORS = ['#3b82f6','#16a34a','#f97316','#8b5cf6','#ec4899','#0891b2','#dc2626','#d97706'];

function renderBatchSummary(chartId, expIds) {
  var container = document.getElementById(chartId);
  if (!container || container.offsetWidth === 0) return;

  var series = [];
  var kind = expIds.length ? expIds[0].kind : null;

  expIds.forEach(function(e, i) {
    var color = BGH_COLORS[i % BGH_COLORS.length];
    if (e.kind === 'vitro') {
      var d = vtDataMap[e.id];
      if (d && d.mrna_pts && d.mrna_pts.length) {
        series.push({
          data: d.mrna_pts, color: color,
          lines: { show: true, lineWidth: 1.5 },
          points: { show: true, radius: 2 }
        });
      }
    } else {
      var d = ivcCharts.find(function(x) { return x.exp_id === e.id; });
      if (d && d.points && d.points.length) {
        series.push({
          data: d.points, color: color,
          lines: { show: true, lineWidth: 1.5 },
          points: { show: true, radius: 2 }
        });
      }
    }
  });

  if (!series.length) return;

  var isVitro = kind === 'vitro';
  try {
    $.plot(container, series, {
      xaxis: isVitro ? { ticks: LOG_TICKS, tickLength: 3 } : { tickLength: 3 },
      yaxis: { min: 0, max: isVitro ? 120 : undefined, labelWidth: 30 },
      grid: { hoverable: false, borderWidth: 1,
              borderColor: isVitro ? '#bfdbfe' : '#fed7aa' },
      legend: { show: false }
    });
  } catch (e) {}
}
```

### `restoreCompoundOrder()` — no change needed

Removing `.cl-gh` rows (which already happens) automatically removes the chart divs inside them. Flot doesn't leave orphan state that needs cleanup.

---

## Files Changed

| File | Change |
|------|--------|
| `templates/compound_list.html` | CSS + JS only — all 5 changes |
| `templates/compound_list.html.bak2` | Snapshot before edits |

No other files touched.

---

## Success Criteria

1. Expanding any row auto-renders the mRNA% chart without needing to click the toggle button
2. Page loads with "按批次+类型" as the active grouping by default
3. Each batch group header shows a colour-coded multi-line Flot chart with one line per compound
4. Batch headers are visually distinct from the grey column header: blue (体外) or orange (体内)
5. Switching to "按化合物" removes group headers and their charts; rows restore to compound order
6. `.bak2` file exists on disk before any edit
