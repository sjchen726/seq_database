# Frontend Bio-Green Redesign — Design Spec

**Date:** 2026-04-19
**Status:** Approved
**Worktree:** `.worktrees/frontend-redesign`

---

## Overview

A comprehensive frontend optimization of the SeqDB worktree addressing four known issues while introducing a "Bio Lab Green" visual theme. The existing design system (`design-system.css`) is updated first; all template changes follow.

---

## Design Decisions

### Color Strategy: Green Brand + Blue-Purple Interactive

- **Brand / logo mark:** `#16a34a` (green)
- **Sidebar active indicator strip:** `linear-gradient(180deg, #16a34a, #22d3ee)`
- **Pagination active page:** `linear-gradient(135deg, #16a34a, #22d3ee)`
- **Primary action buttons (topbar):** `linear-gradient(135deg, #16a34a, #22d3ee)`
- **User avatar gradient:** `linear-gradient(135deg, #16a34a, #22d3ee)`
- **Interactive elements (edit buttons, links, focus rings):** retain existing blue-purple (`#6366f1`, `#1d4ed8`)
- **Sidebar active item background:** retain `#eef2ff` (blue-tinted, consistent with interactive blue)

### Sidebar: Icons + Text

Bootstrap Icons already loaded in `base.html`. Each nav item gets an icon at 13×13px. Sidebar width increases from `210px` to `220px`.

Icon mapping:
| Nav item | Icon class |
|---|---|
| 序列列表 | `bi-table` |
| 序列注册 | `bi-plus-circle` |
| 序列上传 | `bi-cloud-upload` |
| 多序列比对 | `bi-search` |
| Delivery 模块 | `bi-box-seam` |
| 序列修饰模块 | `bi-check2-square` |
| 用户管理 | `bi-people` |

### seq_list: Flat Rows (DataTables JS retained, CSS replaced)

Each sequence is an independent row. AS rows show `color:#4338ca`, SS rows show `color:#7c3aed`. DataTables JS sorting and column-visibility are kept; its CSS is replaced by design system overrides.

---

## File Changes

### 1. `static/css/design-system.css`

**A. Brand color updates** (search-replace existing values):
- `.ds-logo-mark` background: `#16a34a`, box-shadow: `rgba(22,163,74,0.32)`
- `.ds-nav-item.active::before` background: `linear-gradient(180deg, #16a34a, #22d3ee)`
- `.ds-user-avatar` background: `linear-gradient(135deg, #16a34a, #22d3ee)`
- `.ds-pg.active` background: `linear-gradient(135deg, #16a34a, #22d3ee)`, box-shadow: `0 2px 6px rgba(22,163,74,0.3)`
- `.ds-btn-primary` background: `linear-gradient(135deg, #16a34a, #22d3ee)`, box-shadow: `0 2px 8px rgba(22,163,74,0.28)`
- `.ds-btn-green` — repurpose as secondary green or remove (primary now handles green)
- `.ds-sidebar` width: `220px`

**B. DataTables overrides** (append new section at end of file):
```css
/* ── DataTables overrides ── */
.dataTables_wrapper { font-family: inherit; font-size: 11.5px; }
.dataTables_filter label { display: flex; align-items: center; gap: 6px; }
.dataTables_filter input {
  height: 32px; border: 1px solid #e2e8f0; border-radius: 8px;
  padding: 0 12px; font-size: 11.5px; font-family: 'DM Sans', sans-serif;
  color: #334155; background: #fff; outline: none;
}
.dataTables_filter input:focus { border-color: #a5b4fc; box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }
.dataTables_paginate { display: flex; gap: 3px; }
.dataTables_paginate .paginate_button {
  min-width: 28px; height: 28px; border-radius: 6px;
  border: 1px solid #e2e8f0 !important; background: #fff !important;
  color: #64748b !important; font-size: 11px; font-weight: 500;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; padding: 0 6px; transition: all 0.12s;
}
.dataTables_paginate .paginate_button:hover {
  border-color: #c4b5fd !important; color: #6366f1 !important;
  background: #f5f3ff !important;
}
.dataTables_paginate .paginate_button.current,
.dataTables_paginate .paginate_button.current:hover {
  background: linear-gradient(135deg, #16a34a, #22d3ee) !important;
  color: #fff !important; border-color: transparent !important;
  font-weight: 700; box-shadow: 0 2px 6px rgba(22,163,74,0.3);
}
.dataTables_info { font-size: 11px; color: #94a3b8; font-family: 'DM Mono', monospace; }
```

**C. BLAST component classes** (append after DataTables section):
```css
/* ── BLAST result components ── */
.ds-info-card {
  background: #fff; border: 1px solid #e8edf4; border-radius: 8px;
  padding: 14px 18px; margin-bottom: 16px;
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  box-shadow: 0 1px 4px rgba(15,23,42,0.05);
}
.ds-seq-badge {
  font-family: 'DM Mono', monospace; font-size: 13px;
  background: #eff6ff; padding: 3px 10px; border-radius: 4px;
  letter-spacing: 1px; color: #1d4ed8;
}
.ds-source-badge {
  background: #fbbf24; color: #78350f;
  padding: 1px 8px; border-radius: 10px;
  font-size: 11px; margin-left: 6px; font-weight: 600;
}
```

---

### 2. `templates/base.html`

- Sidebar width: `220px` (matches CSS)
- Each `<a class="ds-nav-item">` gets `<i class="bi bi-{icon}"></i>` as first child before the text span
- Remove `.ds-nav-dot` spans (replaced by icons)

---

### 3. `templates/module_list.html`

Full rewrite removing all inline styles. Structure:
- `<div class="ds-table-card">` wrapper
- Toolbar strip: `<div style="display:flex;...padding:9px 14px;border-bottom:1.5px solid #e8edf4;">` — white background, "✅ 共 N 条" + separator + "💡 每个 Type Code 对应特定颜色"
- `<table class="ds-table">` with `ds-table-scroll` wrapper
- Keyword cell: `<code>` with `background:#f1f5f9` pill
- Type Code: `<span class="type-code-pill" data-type="...">` (JS assigns palette colors)
- Action buttons: `<a class="ds-act ds-act-edit">` and delete button with `border:1px solid #fca5a5;color:#ef4444`
- Footer: `<div class="ds-table-footer">` with `<select class="ds-pagesize-select">` and `<div class="ds-pagination">` using `<a class="ds-pg">` / `<a class="ds-pg active">`

---

### 4. `templates/seqmodule_list.html`

Same structural pattern as `module_list.html`. Columns: Keyword | Base Char | Linker Connector | 操作. Base Char uses color-coded pills (A=blue, U=orange, G=green, C=pink). No Description column.

---

### 5. `templates/seq_list.html`

- Remove `<link href="/static/vendors/datatables/dataTables.bootstrap.css">` and `<link href="/static/css/styles.css">` from `{% block extra_head %}`
- Add `class="ds-table"` to the `<table id="example">` element
- DataTables JS initialization: add `"pagingType": "simple_numbers"` option
- No changes to JS logic, column definitions, or view

---

### 6. `templates/blast_results.html` + `multi_blast_results.html` + `multi_blast.html`

- Remove `{% block extra_styles %}<style>...</style>{% endblock %}` blocks
- Replace class names in HTML:
  - `.blast-header-card` → `ds-info-card`
  - `.naked-seq` → `ds-seq-badge`
  - `.source-badge` → `ds-source-badge`
- Any remaining one-off inline styles (margins, flex layout) kept as inline

---

### 7. `app01/views.py` + `templates/reg_seq_list.html`

**views.py — `reg_seq_list` view:**
- Add `from django.core.paginator import Paginator` (already imported elsewhere)
- Accept `q` GET param for Strand ID search: `sequence_list = Sequence.objects.filter(rm_code__icontains=q)` if `q` provided, else all
- Wrap with `Paginator(sequence_list, per_page=20)`
- Pass `page_obj`, `page_size=20`, `q` to template context

**reg_seq_list.html:**
- Topbar: add search input `<input name="q">` and count badge from `page_obj.paginator.count`
- Table: unchanged columns
- Footer: `<div class="ds-table-footer">` with pagesize selector and `ds-pagination` page buttons (with ellipsis for large ranges: show first, last, current±1, ellipsis)

---

## Pagination Ellipsis Logic

For large page ranges in `reg_seq_list`, use Django template logic:
- Always show pages 1, 2
- Ellipsis if gap > 1
- Current page ± 1
- Ellipsis if gap > 1
- Always show last 2 pages

This is implemented via a custom template tag or by passing a `page_range_display` list from the view.

---

## Spec Self-Review

- [x] No TBD or placeholder items
- [x] All color values are exact hex codes
- [x] No internal contradictions (brand green vs interactive blue clearly separated)
- [x] DataTables strategy is explicit: JS kept, CSS replaced
- [x] Scope is focused: 7 file groups, no unrelated changes
- [x] Pagination ellipsis logic specified
