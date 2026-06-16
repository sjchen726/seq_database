# In-Vivo Batch Charts Design

## Goal

Add per-batch Flot charts with SD error bars to the `compound_detail` page for in-vivo experiments (KD% and body_weight readouts), parallel to the existing per-batch vitro charts. Retain the existing aggregated KD% chart.

## Architecture

Server computes mean ± SD per (compound+dose, timepoint) group inside `_build_invivo_chart_data(exp)`. The result is JSON-serialized into the template as `INVIVO_CHART_DATA`. JS reads this array at page load and initializes a Flot chart with the errorbars plugin for each batch. The existing `INVIVO_DATA` / `initInvivoChart()` aggregated chart is untouched.

## Data Flow

```
DataPoint (readout_type ∈ {knockdown_pct, body_weight})
  → group by (compound_id, dose_info, x_value)
  → compute mean, stdev, n per timepoint
  → _build_invivo_chart_data(exp) → dict
  → compound_detail view → json.dumps(list) → INVIVO_CHART_DATA in template
  → initInvivoBatchCharts() → Flot.plot() per batch
```

## `_build_invivo_chart_data(exp)` Output Schema

```python
{
  'exp_id': int,
  'batch_label': str,
  'readout_type': 'knockdown_pct' | 'body_weight',
  'time_unit': str,          # 'day' | 'week' | 'hour'
  'series': [
    {
      'label': str,          # f"{compound_id} {dose_info}"
      'points': [
        {'x': float, 'mean': float, 'sd': float, 'n': int},
        ...                  # sorted ascending by x
      ]
    },
    ...
  ]
}
```

SD: `statistics.stdev(values)` when n ≥ 2; 0.0 when n = 1.
Skip DataPoints where `x_value` is None or `readout_value` is None.

## View Changes (`compound_detail`)

- After building `invivo_exps`, map `_build_invivo_chart_data` over each experiment.
- Add `invivo_chart_data_list` to context (Python list of dicts).
- Template serializes as `const INVIVO_CHART_DATA = {{ invivo_chart_data_list_json|safe }};`.

## Template Changes (`compound_detail.html`)

1. Load `jquery.flot.errorbars.js` in `{% block extra_scripts %}` (already in `static/vendors/flot/`).
2. Inside each in-vivo batch accordion card (identified by `exp.id`), add:
   ```html
   <div id="invivo-chart-{{ exp.id }}"
        style="width:100%;height:240px;margin-top:12px;"></div>
   ```
3. The existing `<div id="chart-invivo">` aggregated chart is unchanged.

## JS Changes

New function `initInvivoBatchCharts()` called in `$(document).ready`:

```javascript
function initInvivoBatchCharts() {
  INVIVO_CHART_DATA.forEach(function(d) {
    var container = document.getElementById('invivo-chart-' + d.exp_id);
    if (!container || !d.series.length) return;

    var series = d.series.map(function(s) {
      return {
        label: s.label,
        data: s.points.map(function(p) {
          return [p.x, p.mean, p.mean - p.sd, p.mean + p.sd];
        }),
        points: { show: true, errorbars: 'y', yerr: { show: true, upperCap: '-', lowerCap: '-' } },
        lines: { show: true }
      };
    });

    var yLabel = d.readout_type === 'knockdown_pct' ? 'KD%' : '体重 (g)';
    $.plot(container, series, {
      xaxis: { axisLabel: d.time_unit },
      yaxis: { axisLabel: yLabel, min: 0 },
      legend: { show: true, position: 'topright' },
      grid: { hoverable: true, borderWidth: 1 }
    });
  });
}
```

Existing `initInvivoChart()` is called as-is after `initInvivoBatchCharts()`.

## Error Handling

- If `INVIVO_CHART_DATA` is empty or `[]`, `forEach` loops zero iterations — no error.
- If a batch container div is not found (e.g., accordion not rendered), skip silently.
- SD = 0 produces zero-length error bars (single point drawn without caps visible) — acceptable.

## Files to Change

| File | Change |
|------|--------|
| `app01/views.py` | Add `_build_invivo_chart_data(exp)` function; update `compound_detail` view to pass `invivo_chart_data_list_json` |
| `templates/compound_detail.html` | Load errorbars plugin; add per-batch chart div; add `INVIVO_CHART_DATA` const; call `initInvivoBatchCharts()` |

No model changes. No migration needed.

## Testing

- Manual: upload an in-vivo CSV with ≥2 replicates per timepoint, open compound_detail, verify chart renders with error bars.
- Edge cases: n=1 (no error bars shown), mixed KD%+body_weight batches, compound with no in-vivo data.
