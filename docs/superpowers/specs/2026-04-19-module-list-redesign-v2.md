# Module List Redesign v2 — Design Spec

**Date:** 2026-04-19
**Status:** Approved

---

## Overview

Redesign `module_list.html` and `seqmodule_list.html` to match Direction A: a card with toolbar, larger fonts, sortable column headers, centered content, and a polished footer with page numbers.

---

## Design Direction

**Direction A — Card + Toolbar**

- Restore `ds-table-card` wrapper around the table
- Toolbar strip inside card top with stats and info text
- Table headers: 13px, bold, black (`#0f172a`), sortable columns show ↑↓ arrows on hover
- Table cells: 13px, centered content, thicker dividers
- Edit button: blue style (`ds-act-edit`: `#eff6ff` bg, `#bfdbfe` border, `#1d4ed8` text)
- Delete button: red border style (not filled)
- Footer: left = pagesize selector (10/20/50), right = page number buttons with large ‹ › arrows

---

## Visual Specs

### Card Container
```css
.ds-table-card {
  background: #fff;
  border-radius: 12px;
  border: 1px solid #d1d5db;
  box-shadow: 0 1px 4px rgba(15,23,42,0.07);
  overflow: hidden;
}
```

### Toolbar
- Background: `#fff`, border-bottom: `2px solid #e8edf4`
- Stats text + separator + info text + upload button
- Font: 12px, color: `#64748b`

### Table Headers
- Font: 13px, bold, black (`#0f172a`), uppercase, letter-spacing: 0.05em
- Padding: 12px 14px
- Border-bottom: `2px solid #d1d5db`
- Sortable columns: show `↑↓` arrow icons, opacity 0.3 → 0.6 on hover
- Hover: background `#eef2ff`, color `#4338ca`
- Operation column: non-sortable, left-aligned

### Table Body
- Font: 13px, centered
- Padding: 10px 14px
- Row border-bottom: `1.5px solid #e8edf4`
- Alternating row: `#fafbfd`
- Hover: `#eef2ff`

### Keyword Cell
```css
.keyword-code {
  background: #f1f5f9;
  color: #334155;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'DM Mono', monospace;
  white-space: nowrap;
}
```

### Type Code Pill
```css
.type-code-pill {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  /* colors assigned by JS palette */
}
```

### Action Buttons
```css
/* Blue edit button */
.ds-act-edit {
  padding: 3px 9px;
  border-radius: 5px;
  font-size: 11px;
  font-weight: 500;
  border: 1px solid #bfdbfe;
  background: #eff6ff;
  color: #1d4ed8;
  cursor: pointer;
  text-decoration: none;
  transition: all 0.1s;
}
.ds-act-edit:hover {
  background: #dbeafe;
  color: #1d4ed8;
  text-decoration: none;
}

/* Red delete button */
.ds-act-delete {
  padding: 3px 9px;
  border-radius: 5px;
  font-size: 11px;
  font-weight: 500;
  border: 1px solid #fca5a5;
  color: #ef4444;
  background: #fff;
  cursor: pointer;
  transition: all 0.1s;
}
.ds-act-delete:hover {
  background: #fef2f2;
}
```

### Footer
- Left side: pagesize selector (10/20/50 dropdown) + "共 N 条"
- Right side: page number buttons (‹ 1 2 3 ›)
- Active page: gradient background (`#38bdf8` → `#6366f1`), white text, shadow
- Arrows: 16px, lighter weight (`letter-spacing: -2px`)
- Border-top: `2px solid #e8edf4`

---

## Pages

### module_list.html
**Columns:** Keyword | Type Code | Strand_MWs | 操作

**Toolbar content:** "✅ 共 N 条" + separator + "💡 每个 Type Code 对应特定颜色" + separator + upload button

**Context vars:** `module_list` (paginated), `page_obj`, `page_size`

### seqmodule_list.html
**Columns:** Keyword | Base Char | Linker Connector | 操作

**Note:** No Description column (removed per previous iteration)

**Toolbar content:** "✅ 共 N 条" + separator + upload button

**Context vars:** `seqmodule_list` (paginated), `page_obj`, `page_size`

---

## Empty State
Show table header + empty row with `colspan="4"` and centered message "暂无模块数据"

---

## Spec Self-Review
- [x] No placeholder/TODO items
- [x] No internal contradictions
- [x] Scope focused (two list pages)
- [x] All visual specs have exact values
