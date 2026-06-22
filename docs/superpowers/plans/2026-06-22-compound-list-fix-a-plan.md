# Compound List Fix Track A — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three high-priority bugs on the compound list page: search actually searching target/sequence fields, in-vivo metrics showing threshold-colored values, and the stats bar showing real compound counts.

**Architecture:** Three independent changes to four files. No new models, no migrations, no URL changes. Each task is self-contained and can be verified manually via `python manage.py check` and visual browser inspection (no test suite exists — `app01/tests.py` is empty).

**Tech Stack:** Django 5.1, Python 3.10, MySQL. venv at `../seq_database_v2/venv/bin/activate`. Run server with `python manage.py runserver` from project root `/Users/gutou/Projects/seq_web/seq_database_bprdb`.

---

## File Map

| File | Change |
|------|--------|
| `app01/views.py` | Search: replace single-field filter with Q OR across 3 fields + `.distinct()`. Stats: compute 4 new context vars before `render()`. |
| `app01/templatetags/cl_extras.py` | Add `vivo_kd_class` and `bw_drop_class` filters. |
| `static/css/compound_list.css` | Add `.cl-val-danger` rule. |
| `templates/compound_list.html` | Replace stats bar. Replace vivo body-weight and peak-KD pill cells with colored-text cells. |

---

## Task 1: Fix search logic in `views.py`

**Files:**
- Modify: `app01/views.py` lines ~1265–1266

The current `if q:` block only filters by `compound__compound_id`. Replace it to search compound ID, target name, and strand sequences with OR logic.

`Q` is already imported at line 9: `from django.db.models import Q, Min, Max, Count, F, Prefetch`.

- [ ] **Step 1: Open `app01/views.py` and find the `if q:` block**

It is inside the `compound_list` view, currently reads:
```python
    if q:
        exp_qs = exp_qs.filter(compound__compound_id__icontains=q)
```

- [ ] **Step 2: Replace that block with the multi-field OR filter**

```python
    if q:
        exp_qs = exp_qs.filter(
            Q(compound__compound_id__icontains=q) |
            Q(compound__target_name__icontains=q) |
            Q(compound__strands__modify_seq__icontains=q)
        ).distinct()
```

The `.distinct()` is required because joining through `compound__strands` can produce duplicate `Experiment` rows when a compound has more than one strand matching the query.

- [ ] **Step 3: Verify Django system check passes**

```bash
source ../seq_database_v2/venv/bin/activate
python manage.py check
```
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Commit**

```bash
git add app01/views.py
git commit -m "fix: search compound list by target_name and strand sequence in addition to compound_id"
```

---

## Task 2: Add `vivo_kd_class` and `bw_drop_class` template filters

**Files:**
- Modify: `app01/templatetags/cl_extras.py`

The existing file already has `kd_class` (for in-vitro MaxKD%) and `ic50_class`. Add two new filters following the same pattern.

- [ ] **Step 1: Open `app01/templatetags/cl_extras.py` and append the two new filters at the end of the file**

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
    """CSS class for body weight % change from Day 0 baseline (negative = loss).
    Thresholds per IACUC/FDA rodent study guidelines:
      > -10%  : acceptable        -> cl-val-good  (green)
      > -20%  : significant loss  -> cl-val-ok    (orange)
      <= -20% : humane endpoint   -> cl-val-danger (red)
    """
    if pct is None:
        return ''
    if pct > -10:
        return 'cl-val-good'
    if pct > -20:
        return 'cl-val-ok'
    return 'cl-val-danger'
```

- [ ] **Step 2: Verify Django system check passes**

```bash
python manage.py check
```
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 3: Commit**

```bash
git add app01/templatetags/cl_extras.py
git commit -m "feat: add vivo_kd_class and bw_drop_class template filters with IACUC thresholds"
```

---

## Task 3: Add `.cl-val-danger` CSS class

**Files:**
- Modify: `static/css/compound_list.css`

The existing threshold classes are at the bottom of the file:
```css
.cl-val-good { color: #15803d; font-weight: 700; }
.cl-val-ok   { color: #b45309; font-weight: 700; }
.cl-val-weak { color: #94a3b8; }
```

- [ ] **Step 1: Add `.cl-val-danger` immediately after `.cl-val-weak`**

```css
.cl-val-danger { color: #dc2626; font-weight: 700; }
```

The full block should now read:
```css
/* ── Data-quality threshold coloring ── */
.cl-val-good   { color: #15803d; font-weight: 700; }
.cl-val-ok     { color: #b45309; font-weight: 700; }
.cl-val-weak   { color: #94a3b8; }
.cl-val-danger { color: #dc2626; font-weight: 700; }
```

- [ ] **Step 2: Commit**

```bash
git add static/css/compound_list.css
git commit -m "feat: add cl-val-danger CSS class (red) for severe body weight drop"
```

---

## Task 4: Update template — vivo table body-weight and peak-KD columns

**Files:**
- Modify: `templates/compound_list.html`

The in-vivo compound rows are rendered in the `{% for vc in bg.vivo_compounds %}` loop (around line 197). There are two cells to change:

**Current body-weight cell (find it by the `max_bw_drop` reference):**
```html
<td>{% if vc.summary.max_bw_drop is not None %}<span class="cl-pill i">{{ vc.summary.max_bw_drop|floatformat:1 }}%</span>{% else %}<span class="cl-dim">—</span>{% endif %}</td>
```

**Current peak-KD cell (find it by the `peak_kd` reference):**
```html
<td>{% if vc.summary.peak_kd is not None %}<span class="cl-pill i">{{ vc.summary.peak_kd|floatformat:0 }}%</span>{% else %}<span class="cl-dim">—</span>{% endif %}</td>
```

- [ ] **Step 1: Replace the body-weight cell**

Find the line containing `vc.summary.max_bw_drop` in the `<tr class="cmp-row">` section (not the expand panel) and replace the entire `<td>…</td>` with:

```html
      <td>{% if vc.summary.max_bw_drop is not None %}<span class="{{ vc.summary.max_bw_drop|bw_drop_class }}">{{ vc.summary.max_bw_drop|floatformat:1 }}%</span>{% else %}<span class="cl-dim">—</span>{% endif %}</td>
```

- [ ] **Step 2: Replace the peak-KD cell**

Find the line containing `vc.summary.peak_kd` in the same `<tr class="cmp-row">` section and replace the entire `<td>…</td>` with:

```html
      <td>{% if vc.summary.peak_kd is not None %}<span class="{{ vc.summary.peak_kd|vivo_kd_class }}">{{ vc.summary.peak_kd|floatformat:0 }}%</span>{% else %}<span class="cl-dim">—</span>{% endif %}</td>
```

- [ ] **Step 3: Verify Django system check passes**

```bash
python manage.py check
```
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Commit**

```bash
git add templates/compound_list.html
git commit -m "feat: color vivo peak-KD and body-weight drop by threshold instead of uniform orange pill"
```

---

## Task 5: Add stats context variables to `views.py`

**Files:**
- Modify: `app01/views.py` — `compound_list` view, before the `return render(...)` call

- [ ] **Step 1: Add four stats variables before the `return render(...)` line**

Find the `return render(request, 'compound_list.html', {` line (around line 1314) and insert immediately before it:

```python
    # ── Stats bar data ──
    total_compounds = Compound.objects.count()
    total_vitro_batches = (
        exp_qs.filter(exp_type='in_vitro')
        .values('batch_label').distinct().count()
    )
    total_vivo_batches = (
        exp_qs.filter(exp_type='in_vivo')
        .values('batch_label').distinct().count()
    )
    filtered_compound_count = None
    if any([q, project_filter, target_name_filter, tag]):
        filtered_compound_count = exp_qs.values('compound_id').distinct().count()
```

- [ ] **Step 2: Add the four new variables to the `render()` context dict**

The `return render(...)` call should include:

```python
    return render(request, 'compound_list.html', {
        'batch_groups': batch_groups,
        'page_obj': page_obj,
        'all_projects': all_projects,
        'all_targets': all_targets,
        'q': q,
        'project': project_filter,
        'target_name': target_name_filter,
        'tag': tag,
        'total_compounds': total_compounds,
        'total_vitro_batches': total_vitro_batches,
        'total_vivo_batches': total_vivo_batches,
        'filtered_compound_count': filtered_compound_count,
    })
```

- [ ] **Step 3: Verify Django system check passes**

```bash
python manage.py check
```
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Commit**

```bash
git add app01/views.py
git commit -m "feat: compute total_compounds, vitro/vivo batch counts, and filtered_compound_count for stats bar"
```

---

## Task 6: Update template — stats bar

**Files:**
- Modify: `templates/compound_list.html`

The current stats bar block (around line 41) reads:
```html
<div class="cl-page-header">
  <div class="cl-stats">
    <span><strong>{{ page_obj.paginator.count }}</strong> 批次</span>
  </div>
</div>
```

- [ ] **Step 1: Replace the entire stats bar block with the new version**

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

- [ ] **Step 2: Verify Django system check passes**

```bash
python manage.py check
```
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 3: Start the dev server and visually verify**

```bash
python manage.py runserver
```

Open `http://127.0.0.1:8000/compound-list/` (or whatever the compound list URL is) and check:

1. **Stats bar** — without filters: shows `N 个化合物 · 体外批次 X · 体内批次 Y`. With a filter active (e.g., type something in the search box): shows an additional `筛选命中 Z 个` item.
2. **Vivo body-weight column** — values > -10% appear green, -10% to -20% appear orange, < -20% appear red. No orange pills remain.
3. **Vivo peak-KD column** — ≥80% green, 50-79% orange, <50% gray. No orange pills remain.
4. **Search** — type a target name (e.g., "PCSK9") in the search box and submit. Compounds with that target should appear. Type a partial sequence string; matching compounds should appear.

- [ ] **Step 4: Commit**

```bash
git add templates/compound_list.html
git commit -m "feat: replace stats bar with total compound count, vitro/vivo batch breakdown, and filtered hit count"
```
