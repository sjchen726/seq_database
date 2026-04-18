# SeqDB Frontend Redesign — Design Specification

**Date:** 2026-04-18  
**Scope:** Full HTML/CSS redesign of all frontend templates. No changes to views, models, or business logic.

---

## 1. Design Goals

- Replace the current dark-header, Bootstrap-default styling with a clean, professional data-application aesthetic
- Establish a unified design system (colors, typography, spacing) applied consistently across all ~25 templates
- Preserve every existing function: sorting, filtering, pagination, BLAST, sequence coloring, CRUD operations, file upload, user management
- Desktop-first layout; mobile graceful degradation is acceptable but not a primary concern

---

## 2. Layout Architecture

### Shell Structure
Every page inherits a new `base.html` with a fixed two-column shell:

```
┌──────────────────────────────────────────────────────┐
│  Sidebar (210px, fixed)  │  Main area (flex: 1)       │
│  ┌────────────────────┐  │  ┌──────────────────────┐  │
│  │  Logo + tagline    │  │  │  Topbar (56px)       │  │
│  │  Nav sections      │  │  ├──────────────────────┤  │
│  │  ...               │  │  │  Content area        │  │
│  │  User card (footer)│  │  │  (scrollable)        │  │
│  └────────────────────┘  │  └──────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

**Sidebar separation:** `box-shadow: 2px 0 16px rgba(15,23,42,0.06)` with `z-index: 20` — no `border-right`. This creates a floating-layer effect without a harsh dividing line.

**Height alignment:** Both `.sidebar-logo` and `.topbar` are exactly `height: 56px`, ensuring the horizontal line of the topbar border aligns with the logo area bottom edge across both columns.

---

## 3. Design System

### Typography
| Usage | Font | Weight | Size |
|---|---|---|---|
| UI text, labels, buttons | DM Sans | 400–700 | 12–15px |
| Sequence data, IDs, codes | DM Mono | 400–500 | 10–12px |
| Section headings | DM Sans | 700 | 15px |
| Small labels, uppercase tags | DM Sans | 700 | 9–10px |

### Color Palette
```
Background (app shell): #dde3ed  (light blue-gray)
Sidebar / Topbar:       #ffffff
Content area:           #f8fafc
Table rows:             #ffffff / #fafbfd (alternating)
Table hover:            #eef2ff

Primary gradient:       linear-gradient(135deg, #38bdf8, #6366f1)  (sky → indigo)
Active nav bg:          #eef2ff
Active nav text:        #4338ca
Active nav indicator:   gradient bar, left edge, 3px wide

Text primary:           #0f172a
Text secondary:         #334155
Text muted:             #64748b
Text disabled:          #94a3b8

Border light:           #e8edf4
Border subtle:          #f1f5f9 / #f0f4f8

Success / BLAST green:  #16a34a (btn) / #15803d (hover)
```

### Accent Indicator (active nav item)
```css
.nav-item.active::before {
  content: '';
  position: absolute; left: -8px; top: 20%; bottom: 20%;
  width: 3px;
  background: linear-gradient(180deg, #38bdf8, #6366f1);
  border-radius: 0 3px 3px 0;
}
```

---

## 4. Navigation Structure

### Sidebar Sections

```
SeqDB  [logo mark]
  tagline: Sequence Database

── 序列数据
   • 序列列表  (active)  [badge: 2413]

── 功能模块
   • 序列注册
   • 序列上传

── BLAST
   • 多序列比对

── 模块管理
   • Delivery 模块
   • 序列修饰模块

── 系统
   • 用户管理

──────────────
[User card: avatar | name | role • online]
```

---

## 5. Page-by-Page Specifications

### 5.1 序列列表 (`seq_list.html`)

**Topbar (left → right):**
1. Page title "序列列表" + count badge (DM Mono, pill shape)
2. `flex: 1` spacer
3. Search box (width: 190px, height: 34px) — `⌕` icon + placeholder + `⌘K` kbd hint
4. Ghost button: `⚙ 高级搜索`
5. Green button: `⌗ 多序列比对` (`background: #16a34a`, `box-shadow: 0 2px 8px rgba(22,163,74,0.28)`)

**Content toolbar (below topbar, inside content area):**
Toolbar row with ghost buttons: `▤ 组合/展开`, `☑ 显示选中`, `↓ 下载选中`, `▼ 项目筛选` (orange badge for active filter), `◧ 列显示`

**Table columns (in order):**
`☐` | Strand ID | Project | Target | Sequence ID | Ligand 1 | Sequences | Ligand 2 | Transcript | Position | Strand_MWs | Parents | Remarks | Update Time | 操作

- **Strand ID**: DM Mono, indigo color (`#4338ca`), underline on hover
- **Sequences**: inline colored blocks per nucleotide modification type; AS/SS tabs where applicable
- **Ligand 1 / 2**: colored pills matching `DeliveryModule.type_code` color groups
- **Update Time**: DM Mono, muted color (`#94a3b8`)
- **操作**: `编辑` (blue), `克隆序列` (violet), `Blast` (amber) — small pill buttons with light background

**Sorting:** Clicking any non-checkbox, non-action column header sorts the column. Sorted column shows `color: #4338ca; background: #eef2ff` on `<th>`. Sort direction arrows (up/down triangles) appear in each sortable header; active direction highlighted.

**Table footer:**
```
[每页显示 [50▾] 条]   [第 1–50 条，共 2,413 条]   [‹ 1 2 3 … 49 ›]
```
- Page size options: 10, 25, 50 (default), 100, 200
- Pagination buttons: 28×28px, border radius 6px; active page uses primary gradient

---

### 5.2 序列编辑 (`seq_edit.html`)

Card-based form layout inside a centered max-width container (≤ 900px).

**Fields:**
| Field | Editable | Note |
|---|---|---|
| Project | Read-only | shown as text |
| 5' Ligand | Editable | text input |
| Sequence | Read-only | DM Mono, colored blocks |
| 3' Ligand | Editable | text input |
| Transcript | Read-only | |
| Target | Read-only | |
| Position | Read-only | |
| Strand_MWs | Editable | |
| Parents | Editable | |
| Remarks | Editable | textarea |
| 更新时间 | Editable | datetime-local, auto-filled |

Read-only fields: rendered as styled `<span>` or disabled input with `background: #f8fafc`.  
Submit button: primary gradient, full-width or right-aligned.

---

### 5.3 序列注册 (`register_seq.html`)

CSV upload form. Centered card layout.

- File input with drag-and-drop zone styling
- Field mapping preview table (if applicable)
- Submit button: primary gradient

---

### 5.4 多序列比对 / BLAST 页面

- Query input: large monospace textarea (DM Mono)
- Parameters panel: collapsible card
- Results table: same table component as seq_list, with alignment visualization
- Submit button: green (`#16a34a`)

---

### 5.5 Delivery 模块 / 序列修饰模块管理

Standard list + inline edit tables.  
Add/Edit forms: modal or inline row expansion.

---

### 5.6 用户管理

User list table with role badges (colored pill per `user_type` level).  
Role colors: guest=gray, delivery=blue, modify=indigo, project=violet, data_admin=amber, admin=orange, superadmin=red.  
Add user / edit user: form card.

---

### 5.7 登录 / 注册页

Centered card on `#dde3ed` background (matches app shell).  
Logo mark + "SeqDB" heading.  
Input fields: border `#e2e8f0`, focus `border-color: #a5b4fc; box-shadow: 0 0 0 3px rgba(99,102,241,0.1)`.  
Submit: primary gradient button, full-width.

---

## 6. Component Library (reusable patterns)

| Component | CSS class | Description |
|---|---|---|
| Primary button | `.btn-primary` | gradient background |
| Ghost button | `.btn-ghost` | white bg, border, hover violet |
| Green button | `.btn-green` | `#16a34a` bg |
| Table card | `.table-card` | white bg, rounded 12px, subtle shadow |
| Nav item | `.nav-item` / `.nav-item.active` | with gradient left indicator |
| Badge / count pill | `.nav-badge` | DM Mono, violet tint |
| Role badge | `.role-badge-{type}` | colored pill per user_type |
| Sort header | `th.sorted` | indigo text + bg |
| Action button set | `.act-edit / .act-clone / .act-blast` | per-row table actions |
| Page size selector | `.pagesize-select` | custom `<select>` with arrow SVG |

---

## 7. Bootstrap 5 Integration

Bootstrap 5 is retained as the CSS framework. The new design layer overrides Bootstrap defaults via more-specific selectors or `!important` sparingly.

Key Bootstrap classes still in use:
- Grid system for form layouts
- Modal component (for inline editing dialogs)
- Toast / alert for success/error messages
- Form validation states

Custom styles live in a new `static/css/design-system.css` (replaces current `styles.css`). Google Fonts import for DM Sans + DM Mono added in `base.html` `<head>`.

---

## 8. Implementation Approach

### Phase 1 — Base shell
1. Create new `base.html` with sidebar + topbar shell
2. Create `static/css/design-system.css` with full design system tokens
3. Verify sidebar/topbar alignment, navigation, user card

### Phase 2 — Core pages
4. Redesign `seq_list.html` (most complex; establishes table patterns)
5. Redesign `seq_edit.html`
6. Redesign `register_seq.html`

### Phase 3 — Functional pages
7. Redesign BLAST / 多序列比对 pages
8. Redesign Delivery module management
9. Redesign 序列修饰模块 management

### Phase 4 — System pages
10. Redesign 用户管理
11. Redesign login / register pages
12. Redesign upload pages

### Constraints
- **No changes to `views.py`, `models.py`, `urls.py`** — template-only work
- All existing Django template tags (`{% for %}`, `{% url %}`, `{% csrf_token %}`, filters) preserved
- Existing JavaScript behavior preserved; new CSS must not break existing `id=` / `class=` hooks used by JS
- Sequence coloring output from `get_delivery_colored()` and `get_modify_seq_colored()` rendered inside new styled wrappers without altering the colored span structure
