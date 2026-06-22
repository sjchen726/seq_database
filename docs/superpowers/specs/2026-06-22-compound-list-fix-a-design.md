# Compound List Fix Track A — Design Spec

**Date:** 2026-06-22  
**Scope:** Three high-priority bug fixes on the compound list page (`compound_list.html`, `views.py`, `cl_extras.py`, `compound_list.css`). No model or URL changes.

---

## Goal

Fix three correctness/UX issues identified in the compound list page audit:

1. **Search actually searches target and sequence** (currently only searches compound ID despite the placeholder saying otherwise)
2. **In-vivo metrics have threshold coloring** (body weight drop and peak KD% show meaningful color signals instead of uniform orange pills)
3. **Stats bar shows real numbers** (total compounds from the Compound table, vitro/vivo batch counts, filtered hit count when filters are active)

---

## Fix 1 — Search Logic

### Problem
`compound_list` view filters with `compound__compound_id__icontains=q`. The search input placeholder says "化合物 ID / 靶点 / 序列" — a lie that misleads users searching by target name or sequence.

### Solution
Replace single-field filter with OR across three fields using `Q` objects:

```python
from django.db.models import Q

if q:
    exp_qs = exp_qs.filter(
        Q(compound__compound_id__icontains=q) |
        Q(compound__target_name__icontains=q) |
        Q(compound__strands__modify_seq__icontains=q)
    ).distinct()
```

The `.distinct()` is required because joining through `compound__strands` can produce duplicate `Experiment` rows when a compound has multiple strands matching the query.

### Files
- **Modify:** `app01/views.py` — `compound_list` view, the `if q:` block

---

## Fix 2 — In-Vivo Metric Coloring

### Problem
Body weight drop (`max_bw_drop`) and peak knockdown (`peak_kd`) are both displayed as uniform orange pills regardless of value. This gives no safety or efficacy signal at a glance.

### Thresholds (domain-standard, IACUC/FDA rodent study guidelines)

**Body weight drop** (`max_bw_drop` is negative: -20.1 = 20.1% loss from Day 0 baseline):

| Range | Meaning | Color class |
|-------|---------|------------|
| `> -10%` | Acceptable, normal variation | `cl-val-good` (green) |
| `-10%` to `-20%` | Significant toxicity signal | `cl-val-ok` (orange) |
| `< -20%` | IACUC humane endpoint — severe toxicity | `cl-val-danger` (red) |

**Peak KD%** (same thresholds as in-vitro MaxKD%):

| Range | Meaning | Color class |
|-------|---------|------------|
| `≥ 80%` | Excellent, clinical-grade knockdown | `cl-val-good` (green) |
| `50–79%` | Moderate, worth further optimization | `cl-val-ok` (orange) |
| `< 50%` | Insufficient, typically not progressed | `cl-val-weak` (gray) |

### New Template Filters

**`app01/templatetags/cl_extras.py`** — add two filters:

```python
@register.filter
def vivo_kd_class(kd_pct):
    """CSS class for in-vivo peak KD%: ≥80% good, ≥50% ok, else weak."""
    if kd_pct is None:
        return ''
    if kd_pct >= 80:
        return 'cl-val-good'
    if kd_pct >= 50:
        return 'cl-val-ok'
    return 'cl-val-weak'

@register.filter
def bw_drop_class(pct):
    """CSS class for body weight % change from Day 0 baseline.
    pct is negative for weight loss (e.g. -20.1 = 20.1% drop).
    Thresholds: IACUC/FDA rodent study guidelines.
    """
    if pct is None:
        return ''
    if pct > -10:
        return 'cl-val-good'
    if pct > -20:
        return 'cl-val-ok'
    return 'cl-val-danger'
```

### New CSS

**`static/css/compound_list.css`** — add danger class alongside existing threshold classes:

```css
.cl-val-danger { color: #dc2626; font-weight: 700; }
```

### Template Changes

**`templates/compound_list.html`** — body weight column (replace orange pill):

```html
<td>
  {% if vc.summary.max_bw_drop is not None %}
    <span class="{{ vc.summary.max_bw_drop|bw_drop_class }}">
      {{ vc.summary.max_bw_drop|floatformat:1 }}%
    </span>
  {% else %}<span class="cl-dim">—</span>{% endif %}
</td>
```

**`templates/compound_list.html`** — peak KD% column (replace orange pill):

```html
<td>
  {% if vc.summary.peak_kd is not None %}
    <span class="{{ vc.summary.peak_kd|vivo_kd_class }}">
      {{ vc.summary.peak_kd|floatformat:0 }}%
    </span>
  {% else %}<span class="cl-dim">—</span>{% endif %}
</td>
```

### Files
- **Modify:** `app01/templatetags/cl_extras.py` — add `vivo_kd_class`, `bw_drop_class`
- **Modify:** `static/css/compound_list.css` — add `.cl-val-danger`
- **Modify:** `templates/compound_list.html` — body weight column and peak KD% column in the vivo table

---

## Fix 3 — Stats Bar

### Problem
Stats bar shows `{{ page_obj.paginator.count }} 批次`. The number is the total filtered batch count (correct), but:
- "批次数" is not the most useful primary metric — researchers want compound count
- No breakdown of vitro vs vivo batches
- No indication of how many compounds match when filters are active

### Solution

**`app01/views.py`** — compute four additional context variables before `render()`:

```python
# Total compounds in the database (Compound table, unfiltered)
total_compounds = Compound.objects.count()

# Vitro and vivo batch counts within the current filter
total_vitro_batches = (
    exp_qs.filter(exp_type='in_vitro')
    .values('batch_label').distinct().count()
)
total_vivo_batches = (
    exp_qs.filter(exp_type='in_vivo')
    .values('batch_label').distinct().count()
)

# When a filter is active, show how many distinct compounds matched
filtered_compound_count = None
if any([q, project_filter, target_name_filter, tag]):
    filtered_compound_count = exp_qs.values('compound_id').distinct().count()
```

Pass all four to the template:
```python
return render(request, 'compound_list.html', {
    ...
    'total_compounds': total_compounds,
    'total_vitro_batches': total_vitro_batches,
    'total_vivo_batches': total_vivo_batches,
    'filtered_compound_count': filtered_compound_count,
})
```

**`templates/compound_list.html`** — replace the existing stats bar:

```html
<div class="cl-page-header">
  <div class="cl-stats">
    <span><strong>{{ total_compounds }}</strong> 个化合物</span>
    {% if filtered_compound_count is not None %}
      <span>筛选命中 <strong>{{ filtered_compound_count }}</strong> 个</span>
    {% endif %}
    <span>体外批次 <strong>{{ total_vitro_batches }}</strong></span>
    <span>体内批次 <strong>{{ total_vivo_batches }}</strong></span>
  </div>
</div>
```

**Display behavior:**
- No filters active: `142 个化合物 · 体外批次 38 · 体内批次 12`
- Filters active: `142 个化合物 · 筛选命中 8 个 · 体外批次 3 · 体内批次 1`

### Files
- **Modify:** `app01/views.py` — `compound_list` view, before `render()` call
- **Modify:** `templates/compound_list.html` — stats bar section

---

## Summary of All File Changes

| File | Change |
|------|--------|
| `app01/views.py` | Search: Q-object OR filter + `.distinct()`. Stats: 4 new context vars. |
| `app01/templatetags/cl_extras.py` | Add `vivo_kd_class` and `bw_drop_class` filters. |
| `static/css/compound_list.css` | Add `.cl-val-danger { color: #dc2626; font-weight: 700; }` |
| `templates/compound_list.html` | Stats bar replacement. Vivo body-weight and peak-KD columns: pill → colored text. |

No migrations, no model changes, no URL changes.
