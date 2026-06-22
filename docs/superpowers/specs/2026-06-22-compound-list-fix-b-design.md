# Compound List Fix Track B — Compound-Centric View Design Spec

**Date:** 2026-06-22  
**Scope:** Add a "按化合物" view mode to the compound list page, alongside the existing "按批次" view. Toggle is a URL parameter; both modes share the same filter bar and URL structure. No model or URL changes.

---

## Goal

Let users switch between two views of the same data:
- **按批次（现有）** — batch cards grouping compounds by experiment batch (existing behavior, unchanged)
- **按化合物（新增）** — one row per compound, showing aggregated best metrics; expand row reveals per-batch history as clickable cards

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| View mode toggle | URL param `?view=compound` / `?view=batch` | Shareable, refresh-safe; default is `compound` |
| Multi-batch aggregation | Best values (lowest IC50, highest KD%) | Shows compound's maximum potential |
| Expand panel layout | Batch cards横排, vitro above vivo | Fast scan, lazy chart load per card |
| Pagination unit | Per compound, 20 per page | Consistent with new primary entity |

---

## URL & Toggle

The toggle is a button group in the filter bar (right side). The current GET form submits `view` as a hidden field or the button appends it via JS.

```
GET /compound-list/?view=compound   → 按化合物模式（default）
GET /compound-list/?view=batch      → 按批次模式（existing layout, unchanged）
```

The `view` param is read in the `compound_list` view and passed to the template as `view_mode`. Default is `'compound'` when absent.

---

## 「按化合物」Table

### Columns

| # | Header | Width | Source |
|---|--------|-------|--------|
| 1 | ☐ (compare checkbox) | 28px | — |
| 2 | 化合物 ID | 120px | `compound.compound_id` |
| 3 | AS 序列 | 300px | `strand.modify_seq` (AS), truncated 50 chars |
| 4 | 靶点 | 80px | `compound.target_name` |
| 5 | 项目 | 70px | `compound.project` |
| 6 | 最佳 IC50 (nM) | 100px | min of all `ExperimentSummary.ic50_nm` (vitro) |
| 7 | 最高 KD% | 80px | max of all `ExperimentSummary.max_kd_pct` (vitro) |
| 8 | 体外批次 | 60px | count of distinct vitro batch_labels |
| 9 | 体内批次 | 60px | count of distinct vivo batch_labels |
| 10 | ▶ chevron | 32px | expand toggle |

Threshold coloring: IC50 uses existing `ic50_class` filter; KD% uses existing `kd_class` filter.

### Sorting & Pagination

- Default sort: `compound_id` ascending (server-side, consistent with current batch view)
- Paginated at 20 compounds per page
- Existing filter params (`q`, `project`, `target_name`, `tag`) apply identically

---

## Expand Panel

Triggered by clicking a compound row. Structure:

```
┌────────────────────────────────────────────────────────┐
│  AS: AUGCCUGAAGUCUACGAUUCG...                          │
│  SS: CGAUCGUAGACUUCAGGCAU...  (opacity 0.75)           │
│                                                        │
│  🔬 体外实验（N批）                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ 20260619-001 │  │ 20260515-003 │  │ 20260410-001 │  │
│  │ HepG2        │  │ HeLa         │  │ HepG2        │  │
│  │ 2024-06-19   │  │ 2024-05-15   │  │ 2024-04-10   │  │
│  │ IC50 0.23nM★ │  │ IC50 0.38nM  │  │ IC50 0.51nM  │  │
│  │ KD 94%       │  │ KD 91%       │  │ KD 89%       │  │
│  │ [▼ 展开图表]  │  │ [▼ 展开图表]  │  │ [▼ 展开图表]  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                        │
│  🐭 体内实验（N批）                                      │
│  ┌──────────────────────────────────────┐              │
│  │ 20260620-001 · 小鼠 · SC · Q2W×3    │              │
│  │ 峰值KD 88%  ·  体重 -8%             │              │
│  │ [▼ 展开图表]                          │              │
│  └──────────────────────────────────────┘              │
└────────────────────────────────────────────────────────┘
```

**Batch card click behavior:** clicking a batch card inline-expands a sub-panel below that card showing the dose-response chart (vitro) or time-course chart (vivo), using the same `clInitChartsInPanel` lazy-render logic as the current expand rows. The canvas `data-*` attributes carry pre-serialized JSON from the server (identical format to current implementation).

**★ marker:** The batch card with the best IC50 gets a small ★ badge in the top-right corner.

---

## Backend: New Data Path

### `compound_list` view changes

```python
view_mode = request.GET.get('view', 'compound')

if view_mode == 'compound':
    compound_entries, page_obj = _build_compound_centric_page(
        exp_qs, page=request.GET.get('page', 1)
    )
else:
    # existing batch path — unchanged
    ...

return render(request, 'compound_list.html', {
    ...
    'view_mode': view_mode,
    'compound_entries': compound_entries if view_mode == 'compound' else [],
})
```

### New function: `_build_compound_centric_page(exp_qs, page)`

Groups `exp_qs` by `compound_id`, paginates at 20 compounds, then builds one entry per compound:

```python
def _build_compound_centric_page(exp_qs, page):
    # Group by compound_id
    cid_map = defaultdict(list)
    for exp in exp_qs:
        cid_map[exp.compound_id].append(exp)

    sorted_cids = sorted(cid_map.keys())
    paginator = Paginator(sorted_cids, 20)
    page_obj = paginator.page(int(page))

    page_cids = list(page_obj.object_list)
    compound_map = {
        c.compound_id: c
        for c in Compound.objects.filter(compound_id__in=page_cids)
                          .prefetch_related('strands')
    }

    entries = [
        _build_compound_entry(compound_map[cid], cid_map[cid])
        for cid in page_cids
        if cid in compound_map
    ]
    return entries, page_obj
```

### New function: `_build_compound_entry(compound, experiments)`

```python
def _build_compound_entry(compound, experiments):
    vitro_exps = [e for e in experiments if e.exp_type == 'in_vitro']
    vivo_exps  = [e for e in experiments if e.exp_type == 'in_vivo']
    seqs = _get_strand_seqs(compound)

    # Aggregate best metrics
    vitro_ic50s  = [e.summary.ic50_nm  for e in vitro_exps if getattr(e, 'summary', None) and e.summary.ic50_nm  is not None]
    vitro_kds    = [e.summary.max_kd_pct for e in vitro_exps if getattr(e, 'summary', None) and e.summary.max_kd_pct is not None]
    best_ic50    = min(vitro_ic50s) if vitro_ic50s else None
    best_kd_pct  = max(vitro_kds)  if vitro_kds  else None

    # Per-batch vitro entries (sorted newest first)
    vitro_batches = sorted([
        _build_vitro_batch_card(e, best_ic50)
        for e in vitro_exps
    ], key=lambda x: x['date'] or '', reverse=True)

    # Per-batch vivo entries (sorted newest first)
    vivo_batches = sorted([
        _build_vivo_batch_card(e)
        for e in vivo_exps
    ], key=lambda x: x['date'] or '', reverse=True)

    return {
        'compound': compound,
        'as_seq': seqs.get('AS', ''),
        'ss_seq': seqs.get('SS', ''),
        'best_ic50': best_ic50,
        'best_kd_pct': best_kd_pct,
        'n_vitro': len(vitro_exps),
        'n_vivo': len(vivo_exps),
        'vitro_batches': vitro_batches,
        'vivo_batches': vivo_batches,
    }
```

### New function: `_build_vitro_batch_card(exp, best_ic50)`

```python
def _build_vitro_batch_card(exp, best_ic50):
    summary = getattr(exp, 'summary', None)
    all_dps = list(exp.datapoints.all())
    rows = _build_vitro_rows(all_dps)
    mrna_pts = [
        [round(math.log10(r['dose']), 4), round(r['mean'], 2)]
        for r in rows if r.get('dose') and r['dose'] > 0 and r.get('mean') is not None
    ]
    kd_pts = [[x, round(max(0.0, 100 - y), 2)] for x, y in mrna_pts]
    ic50_nm = summary.ic50_nm if summary else None
    return {
        'batch_label': exp.batch_label,
        'date': exp.date,
        'cell_line': exp.cell_line or '',
        'ic50_nm': ic50_nm,
        'max_kd_pct': summary.max_kd_pct if summary else None,
        'is_best': ic50_nm is not None and best_ic50 is not None and ic50_nm == best_ic50,
        'vitro_rows': rows,
        'mrna_pts': mrna_pts,
        'kd_pts': kd_pts,
        'attachments': list(exp.attachments.all()),
    }
```

### New function: `_build_vivo_batch_card(exp)`

Uses existing `_build_vivo_schedule_data([exp])`:

```python
def _build_vivo_batch_card(exp):
    readout_data, summary = _build_vivo_schedule_data([exp])
    return {
        'batch_label': exp.batch_label,
        'date': exp.date,
        'animal': f"{exp.gender} {exp.animal_strain}".strip(),
        'route': exp.route or '',
        'peak_kd': summary.get('peak_kd'),
        'max_bw_drop': summary.get('max_bw_drop'),
        'readout_data': readout_data,
        'attachments': list(exp.attachments.all()),
    }
```

---

## Template Structure

`compound_list.html` uses a conditional branch at the top of `{% block content %}`:

```django
{% if view_mode == 'compound' %}
  {% include "compound_list/_compound_view.html" %}
{% else %}
  {# existing batch view markup — unchanged #}
  ...
{% endif %}
```

The new partial `templates/compound_list/_compound_view.html` contains:
- The compound table with the 10 columns above
- The expand row with vitro batch cards + vivo batch cards
- Per-card inline sub-panel with chart canvas

### Toggle button in filter bar

Added after the existing filter controls:

```html
<div style="margin-left:auto;display:flex;gap:0;">
  <a href="?{% if q %}q={{ q }}&{% endif %}{% if project %}project={{ project }}&{% endif %}{% if target_name %}target_name={{ target_name }}&{% endif %}{% if tag %}tag={{ tag }}&{% endif %}view=compound"
     class="cl-view-btn {% if view_mode == 'compound' %}active{% endif %}">按化合物</a>
  <a href="?{% if q %}q={{ q }}&{% endif %}{% if project %}project={{ project }}&{% endif %}{% if target_name %}target_name={{ target_name }}&{% endif %}{% if tag %}tag={{ tag }}&{% endif %}view=batch"
     class="cl-view-btn {% if view_mode == 'batch' %}active{% endif %}">按批次</a>
</div>
```

New CSS classes: `.cl-view-btn`, `.cl-view-btn.active`.

---

## New CSS Classes Needed

```css
/* View mode toggle buttons */
.cl-view-btn { font-size:11px; font-weight:600; padding:4px 12px; border:1px solid #e2e8f0; color:#64748b; text-decoration:none; background:white; }
.cl-view-btn:first-child { border-radius:5px 0 0 5px; }
.cl-view-btn:last-child  { border-radius:0 5px 5px 0; border-left:none; }
.cl-view-btn.active { background:#1e293b; color:white; border-color:#1e293b; }

/* Compound view batch cards */
.cl-batch-card { border:1px solid #e2e8f0; border-radius:6px; padding:8px 10px; background:white; cursor:pointer; }
.cl-batch-card:hover { border-color:#bfdbfe; background:#fafcff; }
.cl-batch-card.vitro { border-left:3px solid #3b82f6; }
.cl-batch-card.vivo  { border-left:3px solid #f97316; }
.cl-batch-card.best::after { content:'★'; color:#f59e0b; font-size:11px; float:right; }
.cl-batch-cards-grid { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:10px; }

/* Batch card inline sub-panel */
.cl-card-panel { display:none; margin-top:8px; padding-top:8px; border-top:1px solid #e2e8f0; }
.cl-card-panel.show { display:block; }
```

---

## Files Changed

| File | Change |
|------|--------|
| `app01/views.py` | Add `view_mode` param; add `_build_compound_centric_page`, `_build_compound_entry`, `_build_vitro_batch_card`, `_build_vivo_batch_card` |
| `templates/compound_list.html` | Add view-mode conditional branch; add toggle button in filter bar |
| `templates/compound_list/_compound_view.html` | **New file** — compound table + expand panel template |
| `static/css/compound_list.css` | New CSS classes for toggle and batch cards |
| `static/js/compound_list.js` | New JS for batch card click expand/collapse |

No model changes. No new URLs. No migrations.
