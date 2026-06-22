# Compound List UX Improvements — Design Spec

**Date:** 2026-06-22  
**Scope:** Fix 14 UX/UI problems in the compound list page (`/compounds/`). No model changes, no new URLs, no migrations. Issues 15–16 (management summary view, new-data badge) are deferred to a separate plan.

**Users:** Lab scientists (体外/体内实验人员) and management (领导).

---

## Issues Addressed

| # | Issue | Priority |
|---|-------|----------|
| 1 | View toggle visually buried inside filter bar | High |
| 2 | Stats bar numbers are ambiguous (total vs filtered) | High |
| 3 | Batch card expansion causes jarring full-width layout shift | High |
| 4 | Compound view expand panel repeats sequences already shown in row | High |
| 5 | No column sorting in compound view | High |
| 6 | Vivo batch card shows minimal info (no animal/route/schedule) | Medium |
| 7 | Column header inconsistency (MaxKD% vs 最高KD%) | Medium |
| 8 | Vivo dose group column is unreadable — control group not highlighted | Medium |
| 9 | Batch type tags (体外/体内 pill) are redundant with border color | Medium |
| 10 | Search Enter-key behavior — verify and fix if broken | Low |
| 11 | Search input too narrow (130px) | High |
| 12 | Type filter (体外/体内) behavior in compound view needs clarification | Low |
| 13 | Pagination shows only page numbers, no "page X of Y" context | Medium |
| 14 | Chart.js loaded from CDN — fails in intranet environments | Medium |

---

## Section 1: Filter Bar & Stats Bar

### 1.1 View Toggle — Move Above Filter Bar (Issue 1)

Remove the toggle buttons from inside the filter `<form>`. Place them as a standalone tab strip directly above the filter bar:

```html
<div class="cl-view-tabs">
  <a href="?...&view=batch"    class="cl-view-tab {% if view_mode == 'batch' %}active{% endif %}">按批次</a>
  <a href="?...&view=compound" class="cl-view-tab {% if view_mode == 'compound' %}active{% endif %}">按化合物</a>
</div>
<form method="get">
  <div class="cl-filter-bar">...</div>
</form>
```

CSS: `.cl-view-tabs` is a flex row with a bottom border that lines up with the tab active state, giving a proper tab-strip appearance. Active tab has a bottom border highlight color matching the current view (blue for compound, orange for batch — or neutral dark for both).

### 1.2 Search Box Width (Issue 11)

Change `.cl-filter-bar input[type="text"]` width from `130px` to `240px`.

### 1.3 Stats Bar Redesign (Issue 2)

Current (confusing):
```
总共 87 个化合物 · 筛选命中 3 个 · 体外批次 12 · 体内批次 5
```

New format — two semantic layers:

```
第 1–20 条，共 87 个化合物  [筛选命中 3 个]    体外实验 12 批 · 体内实验 5 批
```

Rules:
- "第 X–Y 条，共 N 个" always shown — X = `(page-1)*per_page + 1`, Y = `min(page*per_page, total)`
- "筛选命中 M 个" only shown when any filter is active (q, project, target_name, or tag is set)
- "总共 N 个化合物" is the full unfiltered count, shown in the "第 X–Y 条" part
- Batch counts come from the current filtered result set

Backend: view already passes `total_compounds`, `total_vitro_batches`, `total_vivo_batches`. Add `filtered_compound_count` (already exists), `page_start`, `page_end` computed from `page_obj`.

### 1.4 Pagination Inline (Issue 13)

Keep the existing `.cl-pagination` component. Add "第 {{ page_obj.number }} 页 / 共 {{ page_obj.paginator.num_pages }} 页" as text before the page number links.

### 1.5 Type Filter Clarification (Issue 12)

Add a small help tooltip or subtitle under the "全部类型" dropdown:

```
类型▼   (筛选影响列表，展开后显示全部批次)
```

No logic change. Filter already applies only to which compounds appear in the list; expand panel always shows all batches for that compound.

### 1.6 Search Enter Key (Issue 10)

`<input>` is inside a `<form method="get">`, so Enter should already submit. Verify during implementation; add `onkeydown` handler only if broken.

---

## Section 2: Batch View Cleanup

### 2.1 Remove Redundant Type Tags (Issue 9)

In `compound_list.html`, delete the `.cl-batch-tags` div inside `.cl-batch-hdr`:

```django
{# DELETE this block: #}
<div class="cl-batch-tags">
  {% if bg.type == 'in_vitro' or bg.type == 'mixed' %}<span class="cl-btag vitro">体外</span>{% endif %}
  {% if bg.type == 'in_vivo'  or bg.type == 'mixed' %}<span class="cl-btag vivo">体内</span>{% endif %}
</div>
```

The left-border color (`.cl-batch-sec.type-invitro` → blue, `.type-invivo` → orange) already encodes this information clearly.

### 2.2 Column Header Text Consistency (Issue 7)

In the in-vitro table header in batch view (`compound_list.html` line ~101):
- Change `MaxKD%` → `最高 KD%`

This aligns with the compound view which already uses `最高 KD%`.

### 2.3 Vivo Dose Group Column (Issue 8)

**Backend** (`views.py`): When building vivo compound entries for the batch view, detect control group by checking if the dose group label contains any of: `Veh`, `vehicle`, `Vehicle`, `saline`, `Saline`, `PBS`, `对照`, `0 mg/kg`, `0mg/kg`. Add a flag `is_control` to each dose group.

**Template**: Replace the current single `{{ vc.dose_group_label }}` with a structured render:

```django
{% for dg in vc.dose_groups %}
  <span class="cl-dg {% if dg.is_control %}cl-dg-ctrl{% endif %}">{{ dg.label }}</span>
  {% if not forloop.last %} · {% endif %}
{% endfor %}
```

CSS:
```css
.cl-dg      { font-size: 11px; color: #374151; }
.cl-dg-ctrl { color: #94a3b8; }  /* control group greyed out */
```

**Backend data shape change**: `vc.dose_group_label` (string) → `vc.dose_groups` (list of `{label, is_control}`).

---

## Section 3: Compound View — Sortable Column Headers (Issue 5)

### 3.1 URL Parameters

Sort state is carried in URL params:
```
?sort=ic50&order=asc
?sort=kd&order=desc
?sort=compound_id&order=asc
?sort=n_vitro&order=desc
?sort=n_vivo&order=desc
```

When `sort` is absent, default to `batch_label` descending (current behavior, no header highlighted).

### 3.2 Sortable Columns

| Column header | sort value | Natural direction |
|---|---|---|
| 化合物 ID | `compound_id` | asc |
| 最佳 IC50 | `ic50` | asc (lower = better) |
| 最高 KD% | `kd` | desc (higher = better) |
| 体外批次 | `n_vitro` | desc |
| 体内批次 | `n_vivo` | desc |

AS 序列, 靶点, 项目 columns are not sortable.

### 3.3 Column Header Template

Each sortable header becomes a link that toggles direction:

```django
{% with next_order=... %}
<th class="cl-sortable {% if sort == 'ic50' %}cl-sort-active{% endif %}">
  <a href="?...&sort=ic50&order={{ next_order }}">
    最佳 IC50 (nM)
    <span class="cl-sort-arrow">
      {% if sort == 'ic50' %}{% if order == 'asc' %}▲{% else %}▼{% endif %}{% else %}⇅{% endif %}
    </span>
  </a>
</th>
{% endwith %}
```

`next_order`: if currently sorted by this column ascending → `desc`; if descending → `asc`; if not this column → use natural direction for the column.

### 3.4 Backend Sort

In `_build_compound_centric_page(exp_qs, page, sort='', order='')`:

First pass — build a lightweight `{cid: {ic50, kd, n_vitro, n_vivo}}` map from `cid_map` for sorting without full entry construction:

```python
def _cid_sort_key(cid, sort, order, cid_map):
    exps = cid_map[cid]
    if sort == 'compound_id':
        key = cid
    elif sort == 'ic50':
        vals = [e.summary.ic50_nm for e in exps if getattr(e,'summary',None) and e.summary.ic50_nm is not None]
        key = min(vals) if vals else float('inf')
    elif sort == 'kd':
        vals = [e.summary.max_kd_pct for e in exps if getattr(e,'summary',None) and e.summary.max_kd_pct is not None]
        key = max(vals) if vals else -1
    elif sort == 'n_vitro':
        key = sum(1 for e in exps if e.exp_type == 'in_vitro')
    elif sort == 'n_vivo':
        key = sum(1 for e in exps if e.exp_type == 'in_vivo')
    else:
        labels = [e.batch_label for e in exps if e.batch_label]
        key = max(labels) if labels else ''
    return key

reverse = (order == 'desc')
sorted_cids = sorted(cid_map.keys(), key=lambda c: _cid_sort_key(c, sort, order, cid_map), reverse=reverse)
```

Note: `ic50` natural direction is asc (lower = better), so `order='asc'` means `reverse=False`.

The view reads: `sort = request.GET.get('sort', '')` and `order = request.GET.get('order', 'desc')`.

---

## Section 4: Compound View — Expand Panel Redesign (Issues 3, 4, 6)

### 4.1 Remove Redundant Sequence Block (Issue 4)

Delete the `{# Sequences #}` block (lines 47–53 of `_compound_view.html`) from the expand panel. The row already shows a truncated preview; the full sequence is one click away at compound detail.

### 4.2 Batch Card Drawer Pattern (Issue 3)

**Structural change**: Move chart content out of each `.cl-batch-card` and into a shared `.cl-batch-drawer` below the card grid. Cards become purely selectors; the drawer shows the selected card's data.

New template structure per compound expand panel:

```django
{# ── Vitro batch cards ── #}
{% if entry.vitro_batches %}
<div class="cl-cep-section-hdr vitro">🔬 体外实验（{{ entry.n_vitro }}批）</div>
<div class="cl-batch-cards-grid" id="vgrid-{{ cid }}">
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
{# ── Vitro drawer (shared, one per compound) ── #}
<div class="cl-batch-drawer" id="vdrawer-{{ cid }}">
  <div class="cl-drawer-hdr">
    <span class="cl-drawer-title"></span>
    <button class="cl-drawer-close" onclick="clCloseBatchDrawer(event, 'vdrawer-{{ cid }}')">×</button>
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
```

Vivo section follows the identical pattern with `vpid`, `vdrawer-{{ cid }}`.

**JS — `clSelectBatchCard(event, cardEl)`**:
```javascript
function clSelectBatchCard(event, cardEl) {
  event.stopPropagation();
  const drawerId = cardEl.dataset.drawer;
  const panelId  = cardEl.dataset.panel;
  const drawer   = document.getElementById(drawerId);
  const grid     = cardEl.closest('.cl-batch-cards-grid');

  // If clicking the already-selected card, close drawer
  if (cardEl.classList.contains('selected')) {
    cardEl.classList.remove('selected');
    drawer.classList.remove('show');
    return;
  }

  // Deselect all cards in this grid
  grid.querySelectorAll('.cl-batch-card').forEach(c => c.classList.remove('selected'));
  cardEl.classList.add('selected');

  // Hide all panels in drawer, show the target
  drawer.querySelectorAll('.cl-drawer-panel').forEach(p => p.style.display = 'none');
  const panel = document.getElementById(panelId);
  if (panel) panel.style.display = 'block';

  // Update drawer title
  const badge = cardEl.querySelector('.cl-card-badge');
  const title = drawer.querySelector('.cl-drawer-title');
  if (title && badge) title.textContent = badge.textContent;

  // Show drawer and init charts
  drawer.classList.add('show');
  clInitChartsInPanel(panel);
}

function clCloseBatchDrawer(event, drawerId) {
  event.stopPropagation();
  const drawer = document.getElementById(drawerId);
  if (!drawer) return;
  drawer.classList.remove('show');
  // Deselect all cards pointing to this drawer
  document.querySelectorAll(`[data-drawer="${drawerId}"]`).forEach(c => c.classList.remove('selected'));
}
```

**CSS additions**:
```css
.cl-batch-drawer {
  display: none;
  margin-top: 8px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px 16px;
  background: white;
  margin-bottom: 12px;
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
.cl-batch-card.selected { border-color: #3b82f6; background: #eff6ff; box-shadow: 0 0 0 2px #bfdbfe; }
.cl-batch-card.vivo.selected { border-color: #f97316; background: #fff7ed; box-shadow: 0 0 0 2px #fed7aa; }
```

**Remove**: The old `.cl-batch-card.expanded`, `.cl-card-panel`, `.cl-card-expand-hint` styles and `clToggleBatchCard` function — replaced by the drawer pattern.

### 4.3 Vivo Card Info Enrichment (Issue 6)

Current card body:
```
20260620-001
峰值KD 88%  体重 -8%
```

New card body:
```
20260620-001
小鼠 SC · Q2W×3          ← animal + route + schedule line
峰值KD 88%  体重 -8%
```

Template change in vivo card: add `<div class="cl-card-meta">{{ card.animal|default:"" }}{% if card.route %} {{ card.route }}{% endif %}{% if card.schedule %} · {{ card.schedule }}{% endif %}</div>` after the badge.

No backend change needed — `card.animal`, `card.route`, `card.schedule` are already in the vivo batch card dict.

---

## Section 5: Technical (Issues 14)

### 5.1 Chart.js Local Bundle (Issue 14)

Download `chart.umd.min.js` from `https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js` and save to `static/vendors/chartjs/chart.umd.min.js`.

Change in `compound_list.html`:
```html
{# Before: #}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
{# After: #}
<script src="/static/vendors/chartjs/chart.umd.min.js"></script>
```

---

## Files Changed

| File | Change |
|------|--------|
| `app01/views.py` | `_build_compound_centric_page`: add `sort`/`order` params + `_cid_sort_key`; vivo compound entries: `dose_group_label` → `dose_groups` list with `is_control`; add `page_start`/`page_end` to context |
| `templates/compound_list.html` | Move view toggle above filter bar; stats bar redesign; pagination info; remove batch type tags; fix MaxKD% header; vivo dose group template |
| `templates/compound_list/_compound_view.html` | Remove sequence block from expand panel; sortable column headers with sort links; drawer pattern replacing card-panel pattern |
| `static/css/compound_list.css` | Search width 240px; view tab strip styles; drawer styles; card selected state; sort arrow styles; dose group ctrl color; remove `.cl-batch-card.expanded`, `.cl-card-panel`, `.cl-card-expand-hint` |
| `static/js/compound_list.js` | Add `clSelectBatchCard`, `clCloseBatchDrawer`; remove `clToggleBatchCard` |
| `static/vendors/chartjs/chart.umd.min.js` | New — local Chart.js bundle |

No model changes. No migrations. No new URLs.

---

## Implementation Order (by priority)

1. Chart.js local bundle (unblock all other testing)
2. Search width + view toggle position + stats bar (filter bar)
3. Batch view cleanup (tags, header text, dose groups)
4. Compound view sortable headers (backend + template)
5. Compound view drawer pattern (biggest template/JS change)
6. Vivo card info enrichment
7. Pagination info + type filter tooltip
