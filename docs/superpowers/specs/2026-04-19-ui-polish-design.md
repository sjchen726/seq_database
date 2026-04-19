# UI Polish — Design Spec

**Date:** 2026-04-19  
**Status:** Approved  
**Worktree:** `.worktrees/frontend-redesign`

---

## Overview

10 targeted polish items to eliminate legacy Bootstrap / inline-style inconsistencies across the worktree. Logic is unchanged throughout. `seq_list.html` changes are purely class substitutions — visual output is identical.

---

## Design Decisions

### New CSS utility classes (added to `design-system.css`)

| Class | Purpose |
|---|---|
| `.ds-form-2col` | 2-column CSS Grid replacing Bootstrap `row g-3` + `col-md-6` |
| `.ds-form-span-2` | Full-width row inside `.ds-form-2col` (replaces `col-md-12`) |
| `.ds-divider-v` | Vertical separator (1 px, 14 px tall, `#d1d5db`) |
| `.ds-close-btn` | Borderless icon-close button (`#94a3b8`, 16 px) |
| `.ds-active-filter-bar` | Active filter tag row above table |
| `.ds-seq-input` | Monospace sequence text input (replaces SFMono in multi_blast) |
| `.ds-btn-remove-row` | Row-remove button in multi_blast (replaces `.btn-remove-row`) |
| `.ds-btn-add-row` | Dashed add-row button in multi_blast (replaces `.btn-add-row`) |
| `.ds-hint-box` / `.ds-hint-title` / `.ds-hint-grid` / `.ds-hint-row` / `.ds-hint-code` / `.ds-hint-note` | Hint panel in multi_blast (replaces `.hint-*`) |
| `.ds-blast-action-bar` | Action bar in multi_blast (replaces `.blast-action-bar`) |

All new classes produce **visually identical output** to what they replace; the only change for `.ds-seq-input` is font: `SFMono-Regular` → `'DM Mono', monospace`.

---

## File Changes

### 1. `static/css/design-system.css` — append new utilities

```css
/* ── Form 2-column grid (replaces Bootstrap row/col) ── */
.ds-form-2col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 0;
}
.ds-form-span-2 { grid-column: 1 / -1; }

/* ── Utility: vertical divider ── */
.ds-divider-v { width: 1px; height: 14px; background: #d1d5db; flex-shrink: 0; }

/* ── Utility: close button ── */
.ds-close-btn {
  background: none; border: none; color: #94a3b8;
  cursor: pointer; font-size: 16px; padding: 0; line-height: 1;
  transition: color 0.12s;
}
.ds-close-btn:hover { color: #475569; }

/* ── Active filter bar ── */
.ds-active-filter-bar {
  font-size: 12px; color: #64748b;
  display: flex; flex-wrap: wrap; gap: 4px;
  margin-bottom: 6px;
}

/* ── multi_blast: sequence input row ── */
.ds-seq-num {
  width: 26px; text-align: right; font-size: 12px;
  color: #a0aab4; flex-shrink: 0; font-variant-numeric: tabular-nums;
}
.ds-seq-row {
  display: flex; align-items: center; gap: 8px; margin-bottom: 6px;
  animation: rowIn .12s ease;
}
@keyframes rowIn {
  from { opacity: 0; transform: translateY(-3px); }
  to   { opacity: 1; transform: none; }
}
.ds-seq-input {
  flex: 1;
  font-family: 'DM Mono', monospace;
  font-size: 13px;
  border: 1px solid #c8d0d8;
  border-radius: 4px;
  padding: 7px 11px;
  color: #2d3748;
  transition: border-color .15s, box-shadow .15s;
  background: #fff;
}
.ds-seq-input:focus {
  outline: none;
  border-color: #a5b4fc;
  box-shadow: 0 0 0 3px rgba(99,102,241,.12);
}
.ds-seq-input::placeholder { color: #bbc4ce; }
.ds-btn-remove-row {
  background: none; border: none; color: #c8d0d8;
  font-size: 17px; line-height: 1; cursor: pointer;
  padding: 4px 7px; border-radius: 4px; flex-shrink: 0;
  transition: color .12s, background .12s;
}
.ds-btn-remove-row:hover { color: #e74c3c; background: #fef0f0; }
.ds-btn-add-row {
  background: none; border: 1px dashed #c0c8d4; color: #6a7a8a;
  font-size: 12.5px; padding: 6px 16px; border-radius: 5px;
  cursor: pointer; margin-top: 8px;
  transition: border-color .15s, color .15s, background .15s;
}
.ds-btn-add-row:hover { border-color: #a5b4fc; color: #6366f1; background: #f0f6ff; }
.ds-hint-box {
  background: #f8fafc; border: 1px solid #e8edf4;
  border-radius: 6px; padding: 14px 18px; margin-top: 20px;
}
.ds-hint-title { font-size: 12.5px; font-weight: 600; color: #0f172a; margin-bottom: 10px; }
.ds-hint-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 5px 24px; }
.ds-hint-row { display: flex; align-items: baseline; gap: 8px; font-size: 12px; color: #5a6a7a; }
.ds-hint-code {
  font-family: 'DM Mono', monospace; background: #e8edf4;
  padding: 1px 7px; border-radius: 3px; color: #0f172a;
  white-space: nowrap; font-size: 12px; flex-shrink: 0;
}
.ds-hint-note {
  margin-top: 10px; color: #9baab4; font-size: 11.5px;
  border-top: 1px solid #edf2f7; padding-top: 8px;
}
.ds-blast-action-bar { display: flex; align-items: center; gap: 10px; }
```

---

### 2. `templates/seq_edit.html` — replace Bootstrap grid

- `<div class="row g-3">` → `<div class="ds-form-2col">`
- `<div class="col-md-6">` → `<div>`
- `<div class="col-md-12">` → `<div class="ds-form-span-2">`
- Button row: remove the `col-md-12` wrapper, keep inline `style="margin-top:8px;display:flex;gap:10px;align-items:center;"` on the div

---

### 3. `templates/multi_blast.html` — remove local `<style>` block, rename classes

Remove entire `{% block extra_styles %}<style>...</style>{% endblock %}` block.

Rename in HTML body:
| Old class | New class |
|---|---|
| `seq-input-area` | `ds-seq-input-area` (keep as-is, no CSS needed) |
| `seq-row` | `ds-seq-row` |
| `seq-num` | `ds-seq-num` |
| `seq-row input[type=text]` → | `<input class="ds-seq-input">` |
| `btn-remove-row` | `ds-btn-remove-row` |
| `btn-add-row` | `ds-btn-add-row` |
| `hint-box` | `ds-hint-box` |
| `hint-title` | `ds-hint-title` |
| `hint-grid` | `ds-hint-grid` |
| `hint-row` | `ds-hint-row` |
| `hint-code` | `ds-hint-code` |
| `hint-note` | `ds-hint-note` |
| `blast-action-bar` | `ds-blast-action-bar` |

---

### 4. `templates/clone_modal.html` — remove Bootstrap button classes

- Line 20: `class="btn btn-light btn-sm"` → `class="ds-close-btn"` (remove `data-bs-dismiss="modal"` is kept)
- Line 30: `class="btn btn-secondary ds-btn ds-btn-ghost"` → `class="ds-btn ds-btn-ghost"`
- Line 31: `class="btn btn-primary ds-btn ds-btn-primary"` → `class="ds-btn ds-btn-primary"`

---

### 5. `templates/module_list.html` + `templates/seqmodule_list.html` — inline divider → class

Replace `<div style="width:1px;height:14px;background:#d1d5db;">` with `<div class="ds-divider-v">` in the toolbar strip.

---

### 6. `templates/search_results.html` — remove leftover `extra_styles` block

The block contains only a hidden CSRF form. Move the hidden form inside `{% block content %}` instead; remove the `{% block extra_styles %}` block entirely.

---

### 7. `templates/seq_list.html` — close button + filter bar (display unchanged)

- `id="closeSearchPanel"` button: replace inline `style="background:none;border:none;color:#94a3b8;cursor:pointer;font-size:16px;"` with `class="ds-close-btn"`
- `id="activeFilterBar"` div: replace inline `style="font-size:12px;color:#64748b;margin-bottom:6px;display:flex;flex-wrap:wrap;gap:4px;"` with `class="ds-active-filter-bar"`

---

## Spec Self-Review

- [x] No TBD items — all class names and file locations are exact
- [x] seq_list.html changes: only class substitutions, no visual delta
- [x] All new CSS classes produce identical output to what they replace
- [x] Font change in `.ds-seq-input` (`SFMono` → `DM Mono`) is intentional — aligns with design system
- [x] No logic changes anywhere
- [x] Scope: 7 file groups, focused
