# Module Pages Redesign — Design Specification

**Date:** 2026-04-19  
**Scope:** Redesign `module_list.html`, `edit_module.html`, `seqmodule_list.html`, `edit_seqmodule.html` — template-only, no views/models changes.

---

## 1. Delivery 模块列表 (`module_list.html`)

### Table Columns

| Column | Field | Visual |
|---|---|---|
| Keyword | `module.keyword` | `<code>` monospace badge: `background:#1e293b; color:#e2e8f0; padding:2px 8px; border-radius:4px; font-size:11px` |
| Type Code | `module.type_code` | Colored pill — JS auto-assigns one color per unique type_code from a fixed palette |
| Strand_MWs | `module.Strand_MWs` | DM Mono, muted (`color:#94a3b8`); show `—` if null |
| 操作 | — | Text buttons: "编辑" (blue ghost) + "删除" (red ghost, inline POST form with confirm) |

### Type Code Color Assignment (JavaScript)

On page load, JS collects all unique type_code values from the rendered table. It assigns colors sequentially from this palette (background / text pairs):

```
['#dbeafe/#1d4ed8', '#ede9fe/#6d28d9', '#fef3c7/#92400e',
 '#dcfce7/#15803d', '#fce7f3/#9d174d', '#e0f2fe/#0369a1',
 '#ffedd5/#c2410c', '#f3f4f6/#374151']
```

Color assignment is deterministic per page load — same type_code always gets same color within the page. Implemented as a `<script>` block in `{% block extra_scripts %}`.

### Table Header

- `<th>` uses existing `ds-table` styles (10px uppercase)
- Column order: Keyword | Type Code | Strand_MWs | 操作
- No checkbox column (no bulk selection needed)
- Table card: `style="flex:none; max-width:860px;"` (already applied)

### Info Banner

Keep the existing info banner at top of card:  
> "每个 Type Code 对应特定显示颜色，相同 Type Code 显示相同颜色。请保持团队内统一，避免随意更改。"

---

## 2. Delivery 模块编辑/新增 (`edit_module.html`)

Card form, `max-width: 560px`. Fields:

| Field | Input | Note |
|---|---|---|
| keyword | `<input type="text" name="keyword">` | Required |
| type_code | `<input type="text" name="type_code">` | Required |
| Strand_MWs | `<input type="text" name="Strand_MWs">` | Optional |

Submit: `ds-btn ds-btn-primary` "保存"  
Cancel: `ds-btn ds-btn-ghost` → `{% url 'module_list' %}`  
If editing: include `<input type="hidden" name="id" value="{{ module.id }}">` and pre-fill all fields.

---

## 3. 序列修饰模块列表 (`seqmodule_list.html`)

### Table Columns (adds missing fields)

| Column | Field | Visual |
|---|---|---|
| Keyword | `module.keyword` | Same monospace badge as Delivery module |
| Base Char | `module.base_char` | Colored pill by base: A=`#dbeafe/#1d4ed8`, U=`#ffedd5/#c2410c`, G=`#dcfce7/#15803d`, C=`#fce7f3/#9d174d`, blank/other=`#f1f5f9/#475569` |
| Linker Connector | `module.linker_connector` | Small monospace tag: `background:#f1f5f9; color:#334155; padding:1px 6px; border-radius:3px; font-family:'DM Mono'; font-size:10px` |
| Description | `module.description` | Plain text, `color:#64748b`, show `—` if null |
| 操作 | — | "编辑" + "删除" (same pattern as Delivery module) |

### Base Char Colors

Fixed mapping — no JS needed, handled via template `{% if %}` chain:
- `A` → blue pill (`#dbeafe / #1d4ed8`)
- `U` → orange pill (`#ffedd5 / #c2410c`)
- `G` → green pill (`#dcfce7 / #15803d`)
- `C` → pink pill (`#fce7f3 / #9d174d`)
- empty / other → gray pill (`#f1f5f9 / #475569`)

---

## 4. 序列修饰模块编辑/新增 (`edit_seqmodule.html`)

Card form, `max-width: 600px`. Fields:

| Field | Input | Note |
|---|---|---|
| keyword | `<input type="text" name="keyword">` | Required |
| base_char | `<input type="text" name="base_char">` | Optional; placeholder "A / U / G / C / INVAB" |
| linker_connector | `<input type="text" name="linker_connector">` | Default `o`; placeholder "o" |
| description | `<textarea name="description">` | Optional |

Submit + Cancel same pattern as Delivery module edit.  
If editing: `<input type="hidden" name="id">` and pre-fill all fields.

---

## 5. Constraints

- No changes to `views.py`, `models.py`, `urls.py`
- All Django template tags, URL names, and form field `name` attributes preserved exactly as views expect
- Verify form field names against `edit_module` and `edit_seqmodule` views before writing
- Delete action uses `<form method="POST">` with `{% csrf_token %}` and `onsubmit="return confirm(...)"` — no JS redirect
- Files live in worktree: `/Users/gutou/Projects/seq_web/seq_database_v2/.worktrees/frontend-redesign/templates/`
