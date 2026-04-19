# Module List Refresh Design

**Date:** 2026-04-19
**Status:** Draft
**Based on:** 2026-04-19-module-pages-redesign

---

## Overview

Refresh `module_list.html` and `seqmodule_list.html` with three targeted fixes: no-card layout, keyword column width fix, and per-page size selector in the footer. No business logic changes.

---

## 1. Card Layout — Option D (No Card)

Remove `ds-table-card` wrapper from both list pages. The table and info bar stand alone in the content area, giving a lighter, more integrated feel.

**Before:**
```html
<div class="ds-table-card">
  <div class="ds-table-scroll">
    <table class="ds-table">...</table>
  </div>
</div>
```

**After (module_list.html):**
```html
<!-- Info bar, no card -->
<div style="padding:10px 16px;font-size:12.5px;color:#64748b;background:#fff;border:1px solid #e8edf4;border-radius:10px;margin-bottom:2px;">
  <i class="bi bi-info-circle"></i> ...
</div>
<!-- Table directly -->
<div class="ds-table-scroll">
  <table class="ds-table">...</table>
</div>
```

**After (seqmodule_list.html):**
```html
<!-- Table directly -->
<div class="ds-table-scroll">
  <table class="ds-table">...</table>
</div>
```

Also remove `flex:1` from `.ds-table-scroll` where applicable so it doesn't stretch.

---

## 2. Keyword Column Width — Auto-fit with Minimum

Keyword content must not wrap. Each column (Keyword, Linker Connector, Strand_MWs) auto-fits its content with a sensible `min-width` default.

**Keyword:** `min-width: 120px`
**Linker Connector:** `min-width: 60px`
**Strand_MWs:** `min-width: 80px`

Remove `min-width: 1080px` from `.ds-table` to allow natural column shrink.

Use `white-space: nowrap` on Keyword cells.

---

## 3. Per-Page Size Selector (Footer)

Replace the existing pagination UI with a pagesize selector. Default to 20 rows. Options: 10, 20, 50.

**Logic:**
- If total rows ≤ selected page size, hide footer entirely
- If total rows > selected page size, show footer with pagesize select + prev/next navigation

**URL parameter:** `?page_size=20&page=1`

**Footer layout (module_list):**
```
左侧: 每页显示 [10 ▼] 条
右侧: ‹ ›  (只有一页时不显示)
```

**Footer layout (seqmodule_list):** Same pattern.

---

## 4. SeqModule List — Remove Description Column

`seqmodule_list.html` table columns change from:
`Keyword | Base Char | Linker Connector | Description | 操作`

To:
`Keyword | Base Char | Linker Connector | 操作`

Remove all `description` references from the view's `seqmodule_list` queryset.

---

## 5. Empty State

When list is empty, show table header + single empty-row message (no Description column in empty row).

**module_list empty row:** `colspan="4"`
**seqmodule_list empty row:** `colspan="4"`

---

## File Map

| File | Action |
|---|---|
| `.worktrees/frontend-redesign/templates/module_list.html` | Modify — card removal, footer redesign, column widths |
| `.worktrees/frontend-redesign/templates/seqmodule_list.html` | Modify — card removal, remove description col, footer redesign, column widths |
| `.worktrees/frontend-redesign/app01/views.py` | Modify — remove `description` from seqmodule_list queryset; add pagination with page_size param |

---

## View Changes

### `module_list` view
- Add `page_size` param (default 20, from GET `page_size`)
- Add `page` param (default 1, from GET `page`)
- Paginate `DeliveryModule.objects.all()` with `Paginator(queryset, page_size)`
- Pass `module_list`, `page_obj`, `page_size` to template

### `seqmodule_list` view
- Remove `'description'` from `.values()`
- Add `page_size` param (default 20, from GET `page_size`)
- Add `page` param (default 1, from GET `page`)
- Paginate `SeqModule.objects.all()` with `Paginator(queryset, page_size)`
- Pass `seqmodule_list`, `page_obj`, `page_size` to template

---

## Spec Self-Review

- [x] No placeholder/TODO items
- [x] No internal contradictions
- [x] Scope is focused (two list pages + two view changes)
- [x] Ambiguous requirements resolved (page_size always visible, keyword width C) with defaults specified
