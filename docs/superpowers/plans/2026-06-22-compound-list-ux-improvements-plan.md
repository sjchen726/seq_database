# Compound List UX Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 14 UX/UI problems in the compound list page — search, stats bar, view toggle, batch view cleanup, sortable columns, and a new drawer-based chart expansion pattern.

**Architecture:** All changes are contained in the existing single-app Django project. Backend changes are in `app01/views.py` (function-based views, ~3900 lines). Frontend changes span `templates/compound_list.html`, `templates/compound_list/_compound_view.html`, `static/css/compound_list.css`, and `static/js/compound_list.js`. No model changes, no migrations, no new URLs.

**Tech Stack:** Django 5.1, vanilla JS, Chart.js 4.4.0, CSS flexbox/grid.

**Reference:** `docs/superpowers/specs/2026-06-22-compound-list-ux-improvements-design.md`

**Dev setup:**
```bash
source ../seq_database_v2/venv/bin/activate
python manage.py runserver
# Visit http://localhost:8001/compounds/
```

---

## File Map

| File | What changes |
|------|-------------|
| `static/vendors/chartjs/chart.umd.min.js` | **New** — local Chart.js bundle |
| `templates/compound_list.html` | View toggle tab strip; stats bar redesign; remove batch type tags; fix MaxKD% header; vivo dose group template; pagination text |
| `templates/compound_list/_compound_view.html` | Remove sequence block; sortable column headers; drawer pattern replaces card-panel pattern |
| `static/css/compound_list.css` | Search width; tab strip; stats bar; drawer; card selected state; sort arrows; dose group control color; remove obsolete styles |
| `static/js/compound_list.js` | Replace `clToggleBatchCard` with `clSelectBatchCard` + `clCloseBatchDrawer` |
| `app01/views.py` | `_build_compound_centric_page`: add `sort`/`order` params; `_build_vivo_compound_entry`: `dose_group_label` → `dose_groups`; `compound_list`: add `sort`, `order`, `page_start`, `page_end`, `page_total` to context |

---

## Task 1: Chart.js Local Bundle

**Files:**
- Create: `static/vendors/chartjs/chart.umd.min.js`
- Modify: `templates/compound_list.html` (line 373)

- [ ] **Step 1: Download Chart.js**

```bash
mkdir -p static/vendors/chartjs
curl -L "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js" \
     -o static/vendors/chartjs/chart.umd.min.js
```

Verify: `ls -lh static/vendors/chartjs/chart.umd.min.js` — should be ~200KB.

- [ ] **Step 2: Update template to use local file**

In `templates/compound_list.html`, replace line 373:
```django
{# Before: #}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
{# After: #}
<script src="/static/vendors/chartjs/chart.umd.min.js"></script>
```

- [ ] **Step 3: Manual verification**

Run server, visit `http://localhost:8001/compounds/?view=batch`, expand a compound row — the chart should still render. Check browser console for errors (no 404 for chartjs).

- [ ] **Step 4: Commit**

```bash
git add static/vendors/chartjs/chart.umd.min.js templates/compound_list.html
git commit -m "feat: serve Chart.js from local bundle instead of CDN"
```

---

## Task 2: Filter Bar, Stats Bar, Pagination

**Files:**
- Modify: `templates/compound_list.html` (lines 1–56, 326–334)
- Modify: `static/css/compound_list.css`
- Modify: `app01/views.py` (lines 1455–1470, the render() call)

### 2A — Add page_start/page_end/page_total to view context

- [ ] **Step 1: Update `compound_list` view context** (`app01/views.py`, just before the `return render(...)` at line ~1455)

Find the line `return render(request, 'compound_list.html', {` and add these three lines above it:

```python
    per_page = page_obj.paginator.per_page
    page_start = (page_obj.number - 1) * per_page + 1
    page_end   = min(page_obj.number * per_page, page_obj.paginator.count)
    page_total = page_obj.paginator.count

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
        'view_mode': view_mode,
        'compound_entries': compound_entries,
        'sort': request.GET.get('sort', ''),
        'order': request.GET.get('order', 'desc'),
        'page_start': page_start,
        'page_end': page_end,
        'page_total': page_total,
    })
```

### 2B — Redesign filter bar: move view toggle above filter, widen search

- [ ] **Step 2: Replace the filter bar section in `templates/compound_list.html`**

The current template lines 16–44 look like this (the `<form>` with `cl-filter-bar` containing the view toggle at the end). Replace the entire section from `{# ── Filter toolbar ── #}` through `</form>` with:

```django
{# ── View mode tab strip ── #}
<div class="cl-view-tabs">
  <a href="?{% if q %}q={{ q }}&{% endif %}{% if project %}project={{ project }}&{% endif %}{% if target_name %}target_name={{ target_name }}&{% endif %}{% if tag %}tag={{ tag }}&{% endif %}view=batch"
     class="cl-view-tab {% if view_mode == 'batch' %}active{% endif %}">按批次</a>
  <a href="?{% if q %}q={{ q }}&{% endif %}{% if project %}project={{ project }}&{% endif %}{% if target_name %}target_name={{ target_name }}&{% endif %}{% if tag %}tag={{ tag }}&{% endif %}view=compound"
     class="cl-view-tab {% if view_mode == 'compound' %}active{% endif %}">按化合物</a>
</div>

{# ── Filter toolbar ── #}
<form method="get" action="">
  <div class="cl-filter-bar">
    <span style="color:#64748b;font-weight:600;">过滤：</span>
    <span class="cl-search-input-wrap">
      🔍 <input type="text" name="q" value="{{ q }}" placeholder="化合物 ID / 靶点 / 序列">
    </span>
    <select name="project">
      <option value="">全部项目</option>
      {% for p in all_projects %}<option value="{{ p }}" {% if p == project %}selected{% endif %}>{{ p }}</option>{% endfor %}
    </select>
    <select name="target_name">
      <option value="">全部靶点</option>
      {% for t in all_targets %}<option value="{{ t }}" {% if t == target_name %}selected{% endif %}>{{ t }}</option>{% endfor %}
    </select>
    <select name="tag" title="筛选影响列表，展开后始终显示该化合物全部批次">
      <option value="" {% if not tag %}selected{% endif %}>全部类型</option>
      <option value="in_vitro" {% if tag == 'in_vitro' %}selected{% endif %}>体外</option>
      <option value="in_vivo"  {% if tag == 'in_vivo'  %}selected{% endif %}>体内</option>
    </select>
    <input type="hidden" name="view" value="{{ view_mode }}">
    <button type="submit" class="ds-btn ds-btn-primary" style="font-size:12px;padding:4px 14px;">搜索</button>
    <a href="{% url 'compound_list' %}?view={{ view_mode }}" style="font-size:12px;color:#64748b;text-decoration:none;padding:4px 8px;">清除</a>
  </div>
</form>
```

Note the `<input type="hidden" name="view" value="{{ view_mode }}">` — this preserves the current view mode when the filter form is submitted.

### 2C — Redesign stats bar

- [ ] **Step 3: Replace the stats bar section** (lines 46–56, the `cl-page-header` div):

```django
{# ── Page header stats ── #}
<div class="cl-page-header">
  <div class="cl-stats">
    <span>
      {% if view_mode == 'compound' %}
        第 <strong>{{ page_start }}–{{ page_end }}</strong> 个，共 <strong>{{ page_total }}</strong> 个化合物
        {% if filtered_compound_count is not None %}
          <span class="cl-stats-filter">（筛选，全库 {{ total_compounds }} 个）</span>
        {% endif %}
      {% else %}
        第 <strong>{{ page_start }}–{{ page_end }}</strong> 批，共 <strong>{{ page_total }}</strong> 批
      {% endif %}
    </span>
    <span>体外 <strong>{{ total_vitro_batches }}</strong> 批 · 体内 <strong>{{ total_vivo_batches }}</strong> 批</span>
  </div>
</div>
```

### 2D — Add pagination text

- [ ] **Step 4: Update pagination** (lines 326–335). Replace the existing `{# ── Pagination ── #}` block with:

```django
{# ── Pagination ── #}
{% if page_obj.has_other_pages %}
<div class="cl-pagination">
  <span class="cl-pg-info">第 {{ page_obj.number }} 页 / 共 {{ page_obj.paginator.num_pages }} 页</span>
  {% if page_obj.has_previous %}<a href="?{% if q %}q={{ q }}&{% endif %}{% if project %}project={{ project }}&{% endif %}{% if target_name %}target_name={{ target_name }}&{% endif %}{% if tag %}tag={{ tag }}&{% endif %}view={{ view_mode }}&{% if sort %}sort={{ sort }}&order={{ order }}&{% endif %}page={{ page_obj.previous_page_number }}">‹ 上页</a>{% endif %}
  {% for num in page_obj.paginator.page_range %}
    {% if num == page_obj.number %}<span class="current">{{ num }}</span>
    {% else %}<a href="?{% if q %}q={{ q }}&{% endif %}{% if project %}project={{ project }}&{% endif %}{% if target_name %}target_name={{ target_name }}&{% endif %}{% if tag %}tag={{ tag }}&{% endif %}view={{ view_mode }}&{% if sort %}sort={{ sort }}&order={{ order }}&{% endif %}page={{ num }}">{{ num }}</a>{% endif %}
  {% endfor %}
  {% if page_obj.has_next %}<a href="?{% if q %}q={{ q }}&{% endif %}{% if project %}project={{ project }}&{% endif %}{% if target_name %}target_name={{ target_name }}&{% endif %}{% if tag %}tag={{ tag }}&{% endif %}view={{ view_mode }}&{% if sort %}sort={{ sort }}&order={{ order }}&{% endif %}page={{ page_obj.next_page_number }}">下页 ›</a>{% endif %}
</div>
{% endif %}
```

### 2E — Add CSS for tab strip, search width, stats

- [ ] **Step 5: Add new CSS** to the top of `static/css/compound_list.css` (after the opening comment block, before `.cl-page-header`):

```css
/* ── View mode tab strip (above filter bar) ── */
.cl-view-tabs {
  display: flex; gap: 0; border-bottom: 2px solid #e2e8f0;
  margin-bottom: 0;
}
.cl-view-tab {
  font-size: 12px; font-weight: 600; padding: 8px 20px;
  text-decoration: none; color: #64748b;
  border-bottom: 2px solid transparent; margin-bottom: -2px;
  background: none;
}
.cl-view-tab:hover { color: #1e293b; }
.cl-view-tab.active { color: #1e293b; border-bottom-color: #1e293b; }

/* ── Filter bar: widen search input ── */
.cl-filter-bar input[type="text"] { width: 240px; }

/* ── Stats bar ── */
.cl-stats-filter { color: #94a3b8; font-size: 11px; }

/* ── Pagination info text ── */
.cl-pg-info { font-size: 11px; color: #94a3b8; padding: 5px 8px; }
```

Also **remove** the old view toggle button styles (search for `.cl-view-btn` in the CSS and delete the block — lines 321–330 approximately):
```css
/* DELETE these: */
.cl-view-btn { ... }
.cl-view-btn:first-child { ... }
.cl-view-btn:last-child  { ... }
.cl-view-btn.active { ... }
```

- [ ] **Step 6: Manual verification**

- Reload the page. View toggle should appear as tabs above the filter bar, not inside it.
- Search input should be visibly wider.
- Stats bar shows "第 1–10 批，共 N 批" in batch mode, "第 1–20 个，共 N 个化合物" in compound mode.
- Pagination shows "第 1 页 / 共 X 页" text.
- Submitting the filter form stays on the same view mode.
- "清除" link keeps current view mode.

- [ ] **Step 7: Commit**

```bash
git add templates/compound_list.html static/css/compound_list.css app01/views.py
git commit -m "feat: redesign filter bar tabs, stats bar, pagination (issues 1,2,11,13)"
```

---

## Task 3: Batch View Cleanup

**Files:**
- Modify: `templates/compound_list.html` (lines 79–82, 102, 200–201, 221)
- Modify: `static/css/compound_list.css`
- Modify: `app01/views.py` (`_build_vivo_compound_entry` at line 1098)

### 3A — Remove redundant batch type tags (Issue 9)

- [ ] **Step 1: Delete the `.cl-batch-tags` block** from `templates/compound_list.html`

Find and delete lines 79–82:
```django
{# DELETE this entire block: #}
    <div class="cl-batch-tags">
      {% if bg.type == 'in_vitro' or bg.type == 'mixed' %}<span class="cl-btag vitro">体外</span>{% endif %}
      {% if bg.type == 'in_vivo'  or bg.type == 'mixed' %}<span class="cl-btag vivo">体内</span>{% endif %}
    </div>
```

### 3B — Fix column header text (Issue 7)

- [ ] **Step 2: Fix the in-vitro table header** in `templates/compound_list.html` line ~102:

```django
{# Before: #}
<th style="width:80px" class="cl-r">MaxKD%</th>
{# After: #}
<th style="width:80px" class="cl-r">最高 KD%</th>
```

### 3C — Dose group backend (Issue 8)

- [ ] **Step 3: Rewrite `_build_vivo_compound_entry`** in `app01/views.py` at line 1098

Replace the entire function with:

```python
def _build_vivo_compound_entry(compound, vivo_exps):
    """One entry per compound for the vivo sub-table."""
    readout_data, summary = _build_vivo_schedule_data(vivo_exps)
    readouts = [rd['readout'] for rd in readout_data]
    seqs = _get_strand_seqs(compound)

    # Build dose_groups from summary_rows (already has is_control flag)
    dose_groups = []
    if readout_data:
        first_sched = next(iter(readout_data[0]['schedules'].values()), None)
        if first_sched:
            seen = set()
            for row in first_sched['summary_rows']:
                if row['label'] not in seen:
                    seen.add(row['label'])
                    dose_groups.append({'label': row['label'], 'is_control': row['is_control']})

    all_attachments = []
    seen_att = set()
    for exp in vivo_exps:
        for att in exp.attachments.all():
            if att.pk not in seen_att:
                seen_att.add(att.pk)
                all_attachments.append(att)

    return {
        'compound': compound,
        'readout_data': readout_data,
        'readouts': readouts,
        'summary': summary,
        'dose_groups': dose_groups,
        'as_seq': seqs.get('AS', ''),
        'ss_seq': seqs.get('SS', ''),
        'attachments': all_attachments,
    }
```

### 3D — Dose group template (Issue 8)

- [ ] **Step 4: Replace `vc.dose_group_label`** in `templates/compound_list.html` at line ~221:

```django
{# Before: #}
<td><span class="cl-dim" style="font-size:11px;">{{ vc.dose_group_label|default:"—" }}</span></td>

{# After: #}
<td>
  {% if vc.dose_groups %}
    {% for dg in vc.dose_groups %}
      <span class="cl-dg{% if dg.is_control %} cl-dg-ctrl{% endif %}">{{ dg.label }}</span>{% if not forloop.last %} · {% endif %}
    {% endfor %}
  {% else %}<span class="cl-dim">—</span>{% endif %}
</td>
```

- [ ] **Step 5: Add dose group CSS** to `static/css/compound_list.css`:

```css
/* ── Vivo dose group labels ── */
.cl-dg      { font-size: 11px; color: #374151; white-space: nowrap; }
.cl-dg-ctrl { color: #94a3b8; }
```

- [ ] **Step 6: Manual verification**

- Batch view: the 体外/体内 pill tags should be gone from batch headers.
- Vitro table header: "最高 KD%" instead of "MaxKD%".
- Vivo table "剂量组" column: control arm (Veh / Saline / PBS / 0 mg/kg) appears greyed out; treatment arms in dark text.
- If no dose group data, shows "—".

- [ ] **Step 7: Commit**

```bash
git add templates/compound_list.html static/css/compound_list.css app01/views.py
git commit -m "feat: batch view cleanup — remove redundant tags, fix header, style dose groups (issues 7,8,9)"
```

---

## Task 4: Compound View — Sortable Column Headers

**Files:**
- Modify: `app01/views.py` (`_build_compound_centric_page` at line 1340, `compound_list` at line 1371)
- Modify: `templates/compound_list/_compound_view.html`
- Modify: `static/css/compound_list.css`

### 4A — Backend sort

- [ ] **Step 1: Add `_cid_sort_key` and update `_build_compound_centric_page`** in `app01/views.py`

Replace the entire `_build_compound_centric_page` function (lines 1340–1367):

```python
def _build_compound_centric_page(exp_qs, page, sort='', order='desc'):
    cid_map = defaultdict(list)
    for exp in exp_qs:
        cid_map[exp.compound_id].append(exp)

    def _cid_sort_key(cid):
        exps = cid_map[cid]
        if sort == 'compound_id':
            return cid
        elif sort == 'ic50':
            vals = [e.summary.ic50_nm for e in exps if getattr(e, 'summary', None) and e.summary.ic50_nm is not None]
            return min(vals) if vals else float('inf')
        elif sort == 'kd':
            vals = [e.summary.max_kd_pct for e in exps if getattr(e, 'summary', None) and e.summary.max_kd_pct is not None]
            return max(vals) if vals else -1
        elif sort == 'n_vitro':
            return sum(1 for e in exps if e.exp_type == 'in_vitro')
        elif sort == 'n_vivo':
            return sum(1 for e in exps if e.exp_type == 'in_vivo')
        else:
            labels = [e.batch_label for e in exps if e.batch_label]
            return max(labels) if labels else ''

    reverse = (order == 'desc')
    # For compound_id, asc=A→Z is natural; flip default
    if sort == 'compound_id' and order == 'desc':
        reverse = True
    elif sort == 'compound_id':
        reverse = False

    sorted_cids = sorted(cid_map.keys(), key=_cid_sort_key, reverse=reverse)
    paginator = Paginator(sorted_cids, 20)
    try:
        page_obj = paginator.page(int(page))
    except (ValueError, InvalidPage):
        page_obj = paginator.page(1)

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

- [ ] **Step 2: Pass `sort`/`order` from `compound_list` view to `_build_compound_centric_page`**

In `compound_list` view (line ~1376), after `view_mode = request.GET.get('view', 'batch')`, add:

```python
    sort  = request.GET.get('sort', '').strip()
    order = request.GET.get('order', 'desc').strip()
    if order not in ('asc', 'desc'):
        order = 'desc'
```

Then update the call at line ~1400:

```python
    if view_mode == 'compound':
        compound_entries, page_obj = _build_compound_centric_page(
            exp_qs, request.GET.get('page', 1), sort=sort, order=order
        )
```

The `sort` and `order` variables are already added to the render context in Task 2 (Step 1 added them).

### 4B — Template sortable headers

- [ ] **Step 3: Replace the `<thead>` in `templates/compound_list/_compound_view.html`** (lines 5–16)

The URL helper macro: each sortable header needs the full query string with the new sort/order. Define a reusable snippet. Since Django templates don't have macros, we build the base URL once using a `{% with %}` block.

Replace the entire `<thead>` block:

```django
  <thead>
  {% with base="?"|add:"" %}
  {% with qs="{% if q %}q="|add:q|add:"&{% endif %}{% if project %}project="|add:project|add:"&{% endif %}{% if target_name %}target_name="|add:target_name|add:"&{% endif %}{% if tag %}tag="|add:tag|add:"&{% endif %}view=compound&" %}
    <tr>
      <th style="width:120px">
        <a class="cl-sort-link{% if sort == 'compound_id' %} cl-sort-active{% endif %}"
           href="?{% if q %}q={{ q }}&{% endif %}{% if project %}project={{ project }}&{% endif %}{% if target_name %}target_name={{ target_name }}&{% endif %}{% if tag %}tag={{ tag }}&{% endif %}view=compound&sort=compound_id&order={% if sort == 'compound_id' and order == 'asc' %}desc{% else %}asc{% endif %}">
          化合物 ID <span class="cl-sort-arrow">{% if sort == 'compound_id' %}{% if order == 'asc' %}▲{% else %}▼{% endif %}{% else %}⇅{% endif %}</span>
        </a>
      </th>
      <th style="width:300px">AS 序列</th>
      <th style="width:80px">靶点</th>
      <th style="width:70px">项目</th>
      <th style="width:100px;text-align:right;">
        <a class="cl-sort-link{% if sort == 'ic50' %} cl-sort-active{% endif %}"
           href="?{% if q %}q={{ q }}&{% endif %}{% if project %}project={{ project }}&{% endif %}{% if target_name %}target_name={{ target_name }}&{% endif %}{% if tag %}tag={{ tag }}&{% endif %}view=compound&sort=ic50&order={% if sort == 'ic50' and order == 'asc' %}desc{% else %}asc{% endif %}">
          最佳 IC50 (nM) <span class="cl-sort-arrow">{% if sort == 'ic50' %}{% if order == 'asc' %}▲{% else %}▼{% endif %}{% else %}⇅{% endif %}</span>
        </a>
      </th>
      <th style="width:80px;text-align:right;">
        <a class="cl-sort-link{% if sort == 'kd' %} cl-sort-active{% endif %}"
           href="?{% if q %}q={{ q }}&{% endif %}{% if project %}project={{ project }}&{% endif %}{% if target_name %}target_name={{ target_name }}&{% endif %}{% if tag %}tag={{ tag }}&{% endif %}view=compound&sort=kd&order={% if sort == 'kd' and order == 'desc' %}asc{% else %}desc{% endif %}">
          最高 KD% <span class="cl-sort-arrow">{% if sort == 'kd' %}{% if order == 'desc' %}▼{% else %}▲{% endif %}{% else %}⇅{% endif %}</span>
        </a>
      </th>
      <th style="width:60px;text-align:right;">
        <a class="cl-sort-link{% if sort == 'n_vitro' %} cl-sort-active{% endif %}"
           href="?{% if q %}q={{ q }}&{% endif %}{% if project %}project={{ project }}&{% endif %}{% if target_name %}target_name={{ target_name }}&{% endif %}{% if tag %}tag={{ tag }}&{% endif %}view=compound&sort=n_vitro&order={% if sort == 'n_vitro' and order == 'desc' %}asc{% else %}desc{% endif %}">
          体外批次 <span class="cl-sort-arrow">{% if sort == 'n_vitro' %}{% if order == 'desc' %}▼{% else %}▲{% endif %}{% else %}⇅{% endif %}</span>
        </a>
      </th>
      <th style="width:60px;text-align:right;">
        <a class="cl-sort-link{% if sort == 'n_vivo' %} cl-sort-active{% endif %}"
           href="?{% if q %}q={{ q }}&{% endif %}{% if project %}project={{ project }}&{% endif %}{% if target_name %}target_name={{ target_name }}&{% endif %}{% if tag %}tag={{ tag }}&{% endif %}view=compound&sort=n_vivo&order={% if sort == 'n_vivo' and order == 'desc' %}asc{% else %}desc{% endif %}">
          体内批次 <span class="cl-sort-arrow">{% if sort == 'n_vivo' %}{% if order == 'desc' %}▼{% else %}▲{% endif %}{% else %}⇅{% endif %}</span>
        </a>
      </th>
      <th style="width:32px;"></th>
    </tr>
  {% endwith %}{% endwith %}
  </thead>
```

- [ ] **Step 4: Add sort CSS** to `static/css/compound_list.css`:

```css
/* ── Compound view sortable column headers ── */
.cl-sort-link {
  text-decoration: none; color: inherit; display: flex;
  align-items: center; justify-content: flex-end; gap: 4px; white-space: nowrap;
}
.cl-sort-link:hover { color: #1e293b; }
.cl-sort-active { color: #1e293b; font-weight: 700; }
.cl-sort-arrow { font-size: 9px; color: #cbd5e1; }
.cl-sort-active .cl-sort-arrow { color: #1e293b; }
th:first-child .cl-sort-link { justify-content: flex-start; }
```

- [ ] **Step 5: Manual verification**

- Visit `http://localhost:8001/compounds/?view=compound`
- Click "最佳 IC50 (nM)" header — URL should update to `?view=compound&sort=ic50&order=asc`, rows reorder
- Click again — `order=desc`
- Click "化合物 ID" — sorts alphabetically
- Active column shows ▲ or ▼; inactive columns show ⇅
- Sorting persists across filter form submissions

- [ ] **Step 6: Commit**

```bash
git add app01/views.py templates/compound_list/_compound_view.html static/css/compound_list.css
git commit -m "feat: sortable column headers in compound-centric view (issue 5)"
```

---

## Task 5: Compound View — Drawer Expansion Pattern

**Files:**
- Modify: `templates/compound_list/_compound_view.html`
- Modify: `static/css/compound_list.css`
- Modify: `static/js/compound_list.js`

This task replaces the card-panel-inside-card pattern with a shared drawer below the card grid. The drawer renders all batch panels (hidden); clicking a card shows the matching panel inside the drawer without layout shift.

### 5A — Rewrite expand panel in template

- [ ] **Step 1: Replace the entire expand panel content** in `templates/compound_list/_compound_view.html`

The expand panel starts at line ~44 (`<div class="cl-mini-expand">`) and ends at line ~196 (`</div>` closing `cl-mini-expand`). Replace everything inside `<div class="cl-mini-expand">` with:

```django
          {# ── Vitro batch cards + drawer ── #}
          {% if entry.vitro_batches %}
          <div class="cl-cep-section-hdr vitro">🔬 体外实验（{{ entry.n_vitro }}批）</div>
          <div class="cl-batch-cards-grid">
            {% for card in entry.vitro_batches %}
            {% with cpid="cbv-"|add:cid|add:"-"|add:card.batch_label %}
            <div class="cl-batch-card vitro{% if card.is_best %} best{% endif %}"
                 data-drawer="vdrawer-{{ cid }}"
                 data-panel="{{ cpid }}"
                 onclick="clSelectBatchCard(event, this)">
              <div class="cl-card-badge" style="color:#1e40af;">{{ card.batch_label }}</div>
              <div class="cl-card-meta">{{ card.cell_line|default:"—" }}{% if card.date %} · {{ card.date }}{% endif %}</div>
              <div class="cl-card-metrics">
                {% if card.ic50_nm is not None %}<span class="{{ card.ic50_nm|ic50_class }}">IC50 {{ card.ic50_nm|floatformat:2 }}nM</span>{% endif %}
                {% if card.max_kd_pct is not None %}<span style="margin-left:4px;" class="{{ card.max_kd_pct|kd_class }}">KD {{ card.max_kd_pct|floatformat:0 }}%</span>{% endif %}
              </div>
            </div>
            {% endwith %}
            {% endfor %}
          </div>
          <div class="cl-batch-drawer" id="vdrawer-{{ cid }}">
            <div class="cl-drawer-hdr">
              <span class="cl-drawer-title"></span>
              <button class="cl-drawer-close" onclick="clCloseBatchDrawer(event,'vdrawer-{{ cid }}')">×</button>
            </div>
            {% for card in entry.vitro_batches %}
            {% with cpid="cbv-"|add:cid|add:"-"|add:card.batch_label %}
            <div class="cl-drawer-panel" id="{{ cpid }}">
              {% if card.vitro_rows %}
              <div style="display:flex;gap:12px;align-items:flex-start;margin-top:6px;">
                <div style="flex-shrink:0;min-width:160px;">
                  <table class="cl-summary-tbl">
                    <thead><tr><th style="text-align:left;">nM</th><th>mRNA%</th><th>KD%</th></tr></thead>
                    <tbody>
                    {% for row in card.vitro_rows %}
                    <tr>
                      <td style="text-align:left;font-family:monospace;">{{ row.dose }}</td>
                      <td>{{ row.mean|floatformat:1 }}</td>
                      <td>{{ row.kd_pct|floatformat:1 }}</td>
                    </tr>
                    {% endfor %}
                    </tbody>
                  </table>
                </div>
                <div style="flex:1;min-width:0;">
                  <div class="cl-vitro-toggle">
                    <button class="cl-vtoggle-btn active" onclick="event.stopPropagation();clToggleVitroReadout(this,'chart-{{ cpid }}','mrna')">mRNA%</button>
                    <button class="cl-vtoggle-btn" onclick="event.stopPropagation();clToggleVitroReadout(this,'chart-{{ cpid }}','kd')">KD%</button>
                  </div>
                  <div class="cl-vitro-chart-wrap" style="height:180px;">
                    <canvas id="chart-{{ cpid }}" data-chart="vitro"
                      data-mrna="{{ card.mrna_pts|safe }}"
                      data-kd="{{ card.kd_pts|safe }}"></canvas>
                  </div>
                </div>
              </div>
              {% endif %}
              {% if card.attachments %}
              <div class="cl-src-section">
                <div class="cl-src-label">源文件</div>
                {% for att in card.attachments %}
                <div class="cl-src-item">
                  <span class="cl-src-name">📊 {{ att.label|default:att.file.name }}</span>
                  <button class="cl-src-btn" onclick="event.stopPropagation();clTogglePreview(this,'prev-{{ cid }}-{{ att.pk }}',{{ att.pk }})">👁 预览</button>
                  <a class="cl-src-btn" href="{% url 'attachment_download' att.pk %}">⬇ 下载</a>
                </div>
                <div class="cl-src-preview-wrap" id="prev-{{ cid }}-{{ att.pk }}"></div>
                {% endfor %}
              </div>
              {% endif %}
            </div>
            {% endwith %}
            {% endfor %}
          </div>
          {% endif %}

          {# ── Vivo batch cards + drawer ── #}
          {% if entry.vivo_batches %}
          <div class="cl-cep-section-hdr vivo">🐭 体内实验（{{ entry.n_vivo }}批）</div>
          <div class="cl-batch-cards-grid">
            {% for card in entry.vivo_batches %}
            {% with vpid="cbi-"|add:cid|add:"-"|add:card.batch_label %}
            <div class="cl-batch-card vivo"
                 data-drawer="idrawer-{{ cid }}"
                 data-panel="{{ vpid }}"
                 onclick="clSelectBatchCard(event, this)">
              <div class="cl-card-badge" style="color:#c2410c;">{{ card.batch_label }}</div>
              <div class="cl-card-meta">
                {{ card.animal|default:"" }}{% if card.route %} {{ card.route }}{% endif %}{% if card.schedule %} · {{ card.schedule }}{% endif %}
              </div>
              <div class="cl-card-metrics">
                {% if card.peak_kd is not None %}<span class="{{ card.peak_kd|vivo_kd_class }}">峰值KD {{ card.peak_kd|floatformat:0 }}%</span>{% endif %}
                {% if card.max_bw_drop is not None %}<span style="margin-left:4px;" class="{{ card.max_bw_drop|bw_drop_class }}">体重 {{ card.max_bw_drop|floatformat:1 }}%</span>{% endif %}
              </div>
            </div>
            {% endwith %}
            {% endfor %}
          </div>
          <div class="cl-batch-drawer" id="idrawer-{{ cid }}">
            <div class="cl-drawer-hdr">
              <span class="cl-drawer-title"></span>
              <button class="cl-drawer-close" onclick="clCloseBatchDrawer(event,'idrawer-{{ cid }}')">×</button>
            </div>
            {% for card in entry.vivo_batches %}
            {% with vpid="cbi-"|add:cid|add:"-"|add:card.batch_label %}
            <div class="cl-drawer-panel" id="{{ vpid }}">
              {% for rd_item in card.readout_data %}
              {% for sched, sd in rd_item.schedules.items %}
              <div class="cl-sched-panel" style="margin-top:8px;">
                <div class="cl-sched-hdr">
                  <span style="font-size:9px;font-weight:700;color:#64748b;">
                    {% if rd_item.readout == 'body_weight' %}体重变化%{% elif rd_item.readout == 'knockdown_pct' %}KD%{% else %}{{ rd_item.readout }}{% endif %}
                    {% if sched %} · {{ sched }}{% endif %}
                  </span>
                  {% if sd.day_range %}<span style="font-size:9px;color:#94a3b8;margin-left:6px;">{{ sd.day_range }}</span>{% endif %}
                </div>
                <div class="cl-chart-wrap" style="height:160px;">
                  <canvas id="chart-{{ vpid }}-{{ rd_item.readout }}-{{ forloop.parentloop.counter }}-{{ forloop.counter }}"
                    data-chart="vivo"
                    data-readout="{{ rd_item.readout }}"
                    data-days="{{ sd.days_json }}"
                    data-groups="{{ sd.groups_json }}"
                    data-control="{{ sd.control_json }}"></canvas>
                </div>
                {% if sd.summary_rows %}
                <table class="cl-summary-tbl" style="font-size:9px;">
                  <thead><tr>
                    <th>组别</th>
                    {% for d in sd.key_days %}<th class="cl-r">D{{ d|floatformat:0 }}</th>{% endfor %}
                  </tr></thead>
                  <tbody>
                  {% for srow in sd.summary_rows %}
                  <tr {% if srow.is_control %}class="ctrl-row"{% endif %}>
                    <td>{{ srow.label }}</td>
                    {% for v in srow.values %}<td>{{ v|fmt_or_dash:1 }}</td>{% endfor %}
                  </tr>
                  {% endfor %}
                  </tbody>
                </table>
                {% endif %}
              </div>
              {% endfor %}
              {% endfor %}
              {% if card.attachments %}
              <div class="cl-src-section">
                <div class="cl-src-label">源文件</div>
                {% for att in card.attachments %}
                <div class="cl-src-item">
                  <span class="cl-src-name">📊 {{ att.label|default:att.file.name }}</span>
                  <button class="cl-src-btn" onclick="event.stopPropagation();clTogglePreview(this,'prev-{{ cid }}-vivo-{{ att.pk }}',{{ att.pk }})">👁 预览</button>
                  <a class="cl-src-btn" href="{% url 'attachment_download' att.pk %}">⬇ 下载</a>
                </div>
                <div class="cl-src-preview-wrap" id="prev-{{ cid }}-vivo-{{ att.pk }}"></div>
                {% endfor %}
              </div>
              {% endif %}
            </div>
            {% endwith %}
            {% endfor %}
          </div>
          {% endif %}

          <a href="{% url 'compound_detail' cid %}" class="cl-detail-link">📊 查看化合物详情 →</a>
```

### 5B — Update JS

- [ ] **Step 2: Replace `clToggleBatchCard`** in `static/js/compound_list.js` (lines 451–460)

```javascript
// ── Compound-view batch card drawer ──────────────────────────
function clSelectBatchCard(event, cardEl) {
  event.stopPropagation();
  const drawerId = cardEl.dataset.drawer;
  const panelId  = cardEl.dataset.panel;
  const drawer   = document.getElementById(drawerId);
  const grid     = cardEl.closest('.cl-batch-cards-grid');
  if (!drawer || !grid) return;

  // Clicking the already-selected card closes the drawer
  if (cardEl.classList.contains('selected')) {
    cardEl.classList.remove('selected');
    drawer.classList.remove('show');
    return;
  }

  // Deselect all cards in this grid
  grid.querySelectorAll('.cl-batch-card').forEach(c => c.classList.remove('selected'));
  cardEl.classList.add('selected');

  // Hide all panels in drawer, show the target panel
  drawer.querySelectorAll('.cl-drawer-panel').forEach(p => { p.style.display = 'none'; });
  const panel = document.getElementById(panelId);
  if (panel) panel.style.display = 'block';

  // Update drawer title from card badge
  const badge = cardEl.querySelector('.cl-card-badge');
  const title = drawer.querySelector('.cl-drawer-title');
  if (title && badge) title.textContent = badge.textContent.trim();

  // Show drawer and init charts lazily
  drawer.classList.add('show');
  if (panel) clInitChartsInPanel(panel);
}

function clCloseBatchDrawer(event, drawerId) {
  event.stopPropagation();
  const drawer = document.getElementById(drawerId);
  if (!drawer) return;
  drawer.classList.remove('show');
  document.querySelectorAll(`[data-drawer="${drawerId}"]`).forEach(c => c.classList.remove('selected'));
}
```

### 5C — Update CSS

- [ ] **Step 3: Replace old card-panel styles and add drawer styles** in `static/css/compound_list.css`

**Delete** these obsolete rules:
```css
/* DELETE: */
.cl-batch-card.expanded { flex: 0 0 100%; max-width: 100%; cursor: default; }
.cl-card-panel { display: none; margin-top: 8px; padding-top: 8px; border-top: 1px solid #e2e8f0; }
.cl-card-panel.show { display: block; }
.cl-card-expand-hint { font-size: 8px; color: #93c5fd; margin-top: 4px; }
```

**Add** these new rules (after `.cl-batch-card.best::after`):

```css
/* ── Card selected state ── */
.cl-batch-card.selected { border-color: #3b82f6; background: #eff6ff; box-shadow: 0 0 0 2px #bfdbfe; }
.cl-batch-card.vivo.selected { border-color: #f97316; background: #fff7ed; box-shadow: 0 0 0 2px #fed7aa; }

/* ── Batch card drawer ── */
.cl-batch-drawer {
  display: none; margin-top: 8px; margin-bottom: 12px;
  border: 1px solid #e2e8f0; border-radius: 8px;
  padding: 12px 16px; background: white;
}
.cl-batch-drawer.show { display: block; }
.cl-drawer-hdr {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid #f1f5f9;
}
.cl-drawer-title { font-size: 11px; font-weight: 700; color: #374151; font-family: monospace; }
.cl-drawer-close {
  font-size: 14px; line-height: 1; border: none; background: none;
  color: #94a3b8; cursor: pointer; padding: 2px 6px; border-radius: 4px;
}
.cl-drawer-close:hover { background: #f1f5f9; color: #374151; }
.cl-drawer-panel { display: none; }
```

- [ ] **Step 4: Manual verification**

- Visit `http://localhost:8001/compounds/?view=compound`, expand a compound row
- Click a vitro batch card — drawer should appear below the card grid with the correct batch label as the title, showing the dose table and chart
- Chart should render after a moment (lazy init)
- Click the same card again — drawer should close
- Click a different card — drawer content should switch
- `×` button closes the drawer
- Vivo batch cards: clicking shows the time-course chart drawer
- Vivo card preview text shows animal/route/schedule

- [ ] **Step 5: Commit**

```bash
git add templates/compound_list/_compound_view.html static/css/compound_list.css static/js/compound_list.js
git commit -m "feat: replace card-panel with drawer expansion in compound view (issues 3,4,6)"
```

---

## Self-Review Checklist (run before declaring done)

After all tasks are committed, verify each original issue is fixed:

| # | Issue | Verification |
|---|-------|-------------|
| 1 | View toggle buried in filter | Toggle appears as tabs above filter bar |
| 2 | Stats bar ambiguous | "第 X–Y 个，共 N 个化合物" — clear context |
| 3 | Card expansion layout shift | Drawer opens below grid, cards don't move |
| 4 | Sequence repeated in expand panel | Expand panel starts directly with batch cards |
| 5 | No column sorting | Click headers, URL updates, rows reorder |
| 6 | Vivo card missing animal/route/schedule | Card meta line shows "小鼠 SC · Q2W×3" |
| 7 | MaxKD% inconsistency | Batch view shows "最高 KD%" |
| 8 | Vivo dose group unreadable | Control arm greyed, treatment arms dark |
| 9 | Redundant 体外/体内 tags | Tags removed from batch headers |
| 10 | Search Enter key | Press Enter in search box — form submits |
| 11 | Search box too narrow | Input visibly accommodates long compound IDs |
| 12 | Type filter behavior unclear | title tooltip on select |
| 13 | Pagination missing context | "第 X 页 / 共 Y 页" shown |
| 14 | CDN Chart.js | Charts render with no internet access |
