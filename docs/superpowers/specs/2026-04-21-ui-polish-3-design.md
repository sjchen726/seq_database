# UI Polish Sprint 3 — Design Spec

**Date:** 2026-04-21
**Status:** Approved
**Worktree:** `.worktrees/frontend-redesign`

---

## Overview

Three targeted UI polish items. No Python/Django changes.

---

## Item 1: Frontend Table Sort

### Scope

Add click-to-sort to all 5 list-page tables:

| Template | Sortable columns | Not sortable |
|---|---|---|
| `seq_list.html` | Strand ID, Project, Target, Sequence ID, Transcript, Position, Strand_MWs, Parents, Remarks, Update Time | checkbox, Ligand 1, Sequences, Ligand 2, 操作 |
| `module_list.html` | Keyword, Type Code, Strand_MWs | 操作 |
| `seqmodule_list.html` | Keyword, Base Char, Linker Connector | 操作 |
| `reg_seq_list.html` | Strand ID, Position, Transcript, Remarks, Registration Time | Sequences, 操作 |
| `auth_list.html` | #, 姓名, 邮箱, 角色, 项目权限 | 操作 |

### CSS — append to `design-system.css`

```css
/* ── Sortable table header ── */
.ds-th-sort {
  cursor: pointer; user-select: none; white-space: nowrap;
}
.ds-th-sort:hover { background: #f1f5f9; }
.ds-th-sort .ds-sort-icon {
  font-size: 11px; color: #94a3b8; margin-left: 3px;
}
.ds-th-sort.ds-sort-asc,
.ds-th-sort.ds-sort-desc { color: #1d4ed8; }
.ds-th-sort.ds-sort-asc .ds-sort-icon,
.ds-th-sort.ds-sort-desc .ds-sort-icon { color: #3b82f6; }
```

### JS — new file `static/js/table-sort.js`

```javascript
(function () {
  document.querySelectorAll('table').forEach(function (table) {
    var headers = table.querySelectorAll('th.ds-th-sort');
    if (!headers.length) return;
    var state = { col: -1, dir: 'asc' };

    headers.forEach(function (th) {
      var icon = document.createElement('span');
      icon.className = 'ds-sort-icon';
      icon.textContent = '↕';
      th.appendChild(icon);

      th.addEventListener('click', function () {
        var colIdx = Array.from(th.parentNode.children).indexOf(th);
        var newDir = (state.col === colIdx && state.dir === 'asc') ? 'desc' : 'asc';

        headers.forEach(function (h) {
          h.classList.remove('ds-sort-asc', 'ds-sort-desc');
          h.querySelector('.ds-sort-icon').textContent = '↕';
        });

        th.classList.add(newDir === 'asc' ? 'ds-sort-asc' : 'ds-sort-desc');
        th.querySelector('.ds-sort-icon').textContent = newDir === 'asc' ? '↑' : '↓';
        state = { col: colIdx, dir: newDir };

        var tbody = table.querySelector('tbody');
        var rows = Array.from(tbody.querySelectorAll('tr'));
        rows.sort(function (a, b) {
          var av = (a.cells[colIdx] ? a.cells[colIdx].textContent : '').trim();
          var bv = (b.cells[colIdx] ? b.cells[colIdx].textContent : '').trim();
          var an = parseFloat(av), bn = parseFloat(bv);
          if (!isNaN(an) && !isNaN(bn)) return newDir === 'asc' ? an - bn : bn - an;
          return newDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
        });
        rows.forEach(function (r) { tbody.appendChild(r); });
      });
    });
  });
})();
```

- Numeric columns (Strand_MWs, Position, #) sort numerically; text columns sort with `localeCompare`.
- Sorts only the current page's visible rows (no server request).

### HTML changes — per template

Add `class="ds-th-sort"` to each sortable `<th>`. No other attributes needed.

**`seq_list.html`** — sortable: Strand ID, Project, Target, Sequence ID, Transcript, Position, Strand_MWs, Parents, Remarks, Update Time

**`module_list.html`** — sortable: Keyword, Type Code, Strand_MWs

**`seqmodule_list.html`** — sortable: Keyword, Base Char, Linker Connector

**`reg_seq_list.html`** — sortable: Strand ID, Position, Transcript, Remarks, Registration Time

**`auth_list.html`** — sortable: #, 姓名, 邮箱, 角色, 项目权限

### `base.html`

Add `<script src="/static/js/table-sort.js"></script>` alongside the other global scripts (near `loading.js`).

---

## Item 2: Delete Button Style

### Problem

`<button class="ds-act-delete">` does not inherit the `.ds-act` base, so its size, font-weight, and border-radius differ from `.ds-act-edit`.

### CSS change — `design-system.css`

Replace the existing `.ds-act-delete` block with a leaner version that relies on `.ds-act` for structure:

```css
.ds-act-delete { background: #fef2f2; border-color: #fca5a5; color: #ef4444; }
.ds-act-delete:hover { background: #fee2e2; border-color: #f87171; }
```

(Remove the duplicate `border-radius`, `padding`, `font-size`, `cursor`, `transition` — those come from `.ds-act`.)

### HTML change — 2 files

`templates/module_list.html` and `templates/seqmodule_list.html`:

```html
<!-- before -->
<button type="submit" class="ds-act-delete">删除</button>

<!-- after -->
<button type="submit" class="ds-act ds-act-delete">删除</button>
```

---

## Item 3: "Sequences" Column Header Centered

### Change

`templates/seq_list.html` — the `<th>` containing "Sequences" and the seq_type_selector:

```html
<!-- before -->
<th>
  Sequences<br>
  <select id="seq_type_selector" class="ds-seq-type-selector">...</select>
</th>

<!-- after -->
<th style="text-align:center;">
  Sequences<br>
  <select id="seq_type_selector" class="ds-seq-type-selector">...</select>
</th>
```

Only the header cell is centered. The sequence color-block content in the `<td>` below is unchanged.

---

## Spec Self-Review

- [x] No Python/Django changes
- [x] `table-sort.js` guards against missing `cells[colIdx]` (sparse rows)
- [x] Numeric sort applied when `parseFloat` succeeds — covers Strand_MWs, Position, `#`
- [x] `.ds-act-delete` CSS is now color-only — relies on `.ds-act` for structure; HTML updated to add both classes
- [x] Sequences `<td>` content untouched — only `<th>` gets `text-align:center`
- [x] `table-sort.js` added to `base.html` globally — no per-template script tags needed
- [x] Scope: 1 new JS file, 1 CSS file, 6 templates
