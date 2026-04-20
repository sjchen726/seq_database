# Frontend Polish Sprint 2 — Design Spec

**Date:** 2026-04-20
**Status:** Approved
**Worktree:** `.worktrees/frontend-redesign`

---

## Overview

Second round of CSS/HTML consistency improvements. 11 items in 2 phases:

- **Phase 1** — append new utility classes to `design-system.css` only
- **Phase 2** — template + JS updates using those new classes

Logic is unchanged throughout. No Python/Django changes.

---

## Phase 1: New CSS Utility Classes

### File: `static/css/design-system.css` — append at end

```css
/* ── Alert / message banner ── */
.ds-alert-list { margin-bottom: 16px; }
.ds-alert {
  padding: 10px 14px; border-radius: 6px; margin-bottom: 8px;
  font-size: 13.5px; border: 1px solid transparent;
}
.ds-alert-success { background: #f0fdf4; border-color: #bbf7d0; color: #166534; }
.ds-alert-error   { background: #fef2f2; border-color: #fecaca; color: #991b1b; }
.ds-alert-info    { background: #f0f9ff; border-color: #bae6fd; color: #0c4a6e; }
.ds-alert-warning { background: #fffbeb; border-color: #fde68a; color: #92400e; }

/* ── Empty state row ── */
.ds-empty-state {
  text-align: center; color: #94a3b8; padding: 32px;
}

/* ── Form hint text ── */
.ds-form-hint { font-size: 12px; color: #64748b; margin: 4px 0 0 0; }

/* ── Action: delete ── */
.ds-act-delete {
  background: #fff; border: 1px solid #fca5a5; color: #ef4444;
  border-radius: 5px; padding: 3px 10px; font-size: 12px;
  cursor: pointer; transition: background .12s, border-color .12s;
}
.ds-act-delete:hover { background: #fef2f2; border-color: #f87171; }

/* ── Sidebar nav icon ── */
.ds-nav-icon { font-size: 13px; flex-shrink: 0; }

/* ── Seq-type selector (inside table header) ── */
.ds-seq-type-selector {
  width: auto; display: inline-block; margin-top: 2px;
  min-width: 140px; font-size: 11px;
  border: 1px solid #e2e8f0; border-radius: 4px; padding: 2px 4px;
}

/* ── Form page top offset ── */
.ds-form-page { padding-top: 20px; }

/* ── Button: disabled state ── */
.ds-btn:disabled,
.ds-btn[disabled] {
  opacity: 0.55; cursor: not-allowed; pointer-events: none;
}

/* ── Button: loading state ── */
@keyframes ds-spin { to { transform: rotate(360deg); } }
.ds-btn-loading {
  opacity: 0.75; cursor: not-allowed; pointer-events: none;
  display: inline-flex; align-items: center; gap: 7px;
}
.ds-btn-loading::before {
  content: '';
  display: inline-block;
  width: 13px; height: 13px;
  border: 2px solid rgba(255,255,255,.35);
  border-top-color: #fff;
  border-radius: 50%;
  animation: ds-spin .6s linear infinite;
  flex-shrink: 0;
}
/* For ghost/secondary buttons (dark spinner) */
.ds-btn-ghost.ds-btn-loading::before {
  border-color: rgba(100,116,139,.3);
  border-top-color: #64748b;
}
```

**Note on `.ds-form-page`:** The existing rule already exists in design-system.css (defines layout/max-width). Add `padding-top: 20px` to that existing rule rather than creating a duplicate. The 11 templates that have `style="padding-top:20px;"` on `.ds-form-page` will then have the inline style removed.

---

## Phase 2: Template + JS Updates

### 2.1 Remove ⌘K shortcut

**File:** `templates/seq_list.html`

- Remove line: `<span class="ds-search-kbd">⌘K</span>`
- No JS change needed — there is no keyboard binding in `search.js` for this shortcut

**File:** `static/css/design-system.css`

- Remove the `.ds-search-kbd { ... }` rule block (dead code after HTML removal)

---

### 2.2 seq_list.html — advanced search panel Bootstrap grid

**File:** `templates/seq_list.html` lines ~38–79

The `advancedSearchForm` div currently uses Bootstrap grid:
```html
<div class="row g-2">
  <div class="col-md-4">...</div>  <!-- × 8 -->
  <div class="col-12" id="modifySeqInputsWrap">...</div>
</div>
```

Replace with:
```html
<div class="ds-form-3col">
  <div>...</div>  <!-- × 8 half-width fields become 1/3 each in 3-col -->
  <div class="ds-form-span-3" id="modifySeqInputsWrap">...</div>
</div>
```

**New CSS class to add in Phase 1:**
```css
.ds-form-3col {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 8px 12px;
}
.ds-form-span-3 { grid-column: 1 / -1; }
```

Add these two classes to the Phase 1 CSS block.

---

### 2.3 clone_modal.html — remove inline style block

**File:** `templates/clone_modal.html`

Current lines 1–13: an inline `<style>` block defining `.form-group`, `.form-row`, `.form-control`, `.clone-row`, `.clone-divider`. These are scoped to `#cloneModal`.

- **Remove** the entire `<style>...</style>` block (lines 1–13)
- The modal body content (`#cloneRowsContainer`) is populated dynamically by `clone_delivery.js` — check that JS file for any Bootstrap form classes being injected. If `.form-group` / `.form-control` appear in JS, replace them with `ds-form-*` equivalents in that file too.
- The `.clone-divider` gradient strip styling: move to `design-system.css` as `.ds-clone-divider`:

```css
/* ── Clone modal divider ── */
.ds-clone-divider {
  position: relative; display: block; height: 16px; width: 100%;
  margin: 0.75rem 0 1rem; clear: both;
  background: linear-gradient(90deg, rgba(74,163,223,.12), rgba(74,163,223,.06));
}
.ds-clone-divider::before {
  content: ''; position: absolute; left: 5%; right: 5%; top: 50%;
  height: 0; border-top: 1px dashed rgba(74,163,223,.6);
  transform: translateY(-50%);
}
```

Add `.ds-clone-divider` to the Phase 1 CSS block.

In `clone_modal.html`, replace any `class="clone-divider"` with `class="ds-clone-divider"`.

---

### 2.4 Alert/message blocks → ds-alert classes

**Files with `{% if messages %}` blocks:**
`edit_module.html`, `edit_seqmodule.html`, `auth_edit.html`, `author_add.html`, `change_password.html`, `register.html`, `login.html`, `reg_seq_edit.html`

**Current pattern (each file):**
```django
{% if messages %}
<div style="margin-bottom:16px;">
  {% for message in messages %}
  <div style="padding:10px 14px;border-radius:6px;margin-bottom:8px;font-size:13.5px;
    {% if 'error' in message.tags %}background:#fef2f2;border:1px solid #fecaca;color:#991b1b;
    {% elif 'success' in message.tags %}background:#f0fdf4;border:1px solid #bbf7d0;color:#166534;
    {% else %}background:#f0f9ff;border:1px solid #bae6fd;color:#0c4a6e;{% endif %}">
    {{ message }}
  </div>
  {% endfor %}
</div>
{% endif %}
```

**Replace with:**
```django
{% if messages %}
<div class="ds-alert-list">
  {% for message in messages %}
  <div class="ds-alert {% if 'error' in message.tags %}ds-alert-error{% elif 'success' in message.tags %}ds-alert-success{% else %}ds-alert-info{% endif %}">
    {{ message }}
  </div>
  {% endfor %}
</div>
{% endif %}
```

**Other alert patterns** (non-`messages` Django alerts — inline style divs used as manual alerts):

- `blast_results.html`, `multi_blast_results.html`, `upload_*.html` may use ad-hoc alert divs with inline styles matching the same color palette. Replace `style="padding:10px 14px;background:#fffbeb;border:1px solid #fde68a;..."` with appropriate `ds-alert ds-alert-warning` class.
- Check each file individually and apply the matching variant.

---

### 2.5 Delete buttons → ds-act-delete

**Files:** `module_list.html`, `seqmodule_list.html`

Current:
```html
<button type="submit" class="ds-act" style="border-color:#fca5a5;color:#ef4444;background:#fff;">删除</button>
```

Replace with:
```html
<button type="submit" class="ds-act-delete">删除</button>
```

---

### 2.6 Empty state rows → ds-empty-state

**Files:** `module_list.html`, `seqmodule_list.html`, `reg_seq_list.html`, `auth_list.html`

Current:
```html
<tr><td colspan="N" style="text-align:center;color:#94a3b8;padding:32px;">暂无...数据</td></tr>
```

Replace with:
```html
<tr><td colspan="N" class="ds-empty-state">暂无...数据</td></tr>
```

---

### 2.7 Remove padding-top:20px from ds-form-page divs

**Files (11):** `auth_edit.html`, `author_add.html`, `edit_module.html`, `edit_seqmodule.html`, `multi_blast.html`, `reg_seq_edit.html`, `register_seq.html`, `seq_edit.html`, `upload_delivery_info.html`, `upload_modules.html`, `upload_seqmodules.html`

In every file, change:
```html
<div class="ds-form-page" style="padding-top:20px;">
```
→
```html
<div class="ds-form-page">
```

The `padding-top: 20px` is now in the CSS rule directly (Phase 1).

---

### 2.8 Form hint text → ds-form-hint

**Files:** `auth_edit.html` line 38, `author_add.html` line 36, `edit_seqmodule.html` line 44

Current:
```html
<p style="font-size:12px;color:#64748b;margin:4px 0 0 0;">...</p>
```

Replace with:
```html
<p class="ds-form-hint">...</p>
```

---

### 2.9 Sidebar nav icons → ds-nav-icon

**File:** `base.html` lines 42, 48, 51, 57, 63, 66, 73

Current:
```html
<i class="bi bi-table" style="font-size:13px;flex-shrink:0;"></i>
```

Replace with:
```html
<i class="bi bi-table ds-nav-icon"></i>
```

(Remove `style=` attribute; add `ds-nav-icon` class to the existing `bi` icon element.)

---

### 2.10 Seq-type selector → ds-seq-type-selector

**File:** `templates/seq_list.html` line ~188

Current:
```html
<select id="seq_type_selector" class="ds-pagesize-select" style="width:auto;margin-top:2px;min-width:140px;font-size:11px;">
```

Replace with:
```html
<select id="seq_type_selector" class="ds-seq-type-selector">
```

(Remove `ds-pagesize-select` — that class is for the footer page-size selector, not appropriate here. `ds-seq-type-selector` is the correct class for this context.)

---

### 2.11 Form submit loading state

**New file:** `static/js/loading.js`

```javascript
(function () {
  document.addEventListener('submit', function (e) {
    var form = e.target;
    // Only POST forms with a submit button
    var btn = form.querySelector('button[type=submit], input[type=submit]');
    if (!btn) return;
    // Skip if already loading (prevent double-submit)
    if (btn.classList.contains('ds-btn-loading')) { e.preventDefault(); return; }
    btn.classList.add('ds-btn-loading');
    btn.disabled = true;
    // Store original text for potential reset (e.g., validation failure)
    btn._originalText = btn.textContent;
    btn.textContent = '处理中…';
  });
})();
```

**File:** `templates/base.html` — add script tag in `{% block extra_scripts %}` default content (or in the base scripts section, before closing `</body>`):

```html
<script src="/static/js/loading.js"></script>
```

This applies globally to all POST forms on every page. No per-template changes needed.

---

## Spec Self-Review

- [x] Phase 1 CSS must be committed before Phase 2 template changes
- [x] `.ds-form-page` edit: update existing rule, do not add duplicate rule
- [x] `ds-form-3col` / `ds-form-span-3` added to Phase 1 CSS block for advanced search
- [x] `ds-clone-divider` added to Phase 1 CSS block
- [x] Loading JS: `btn.textContent = '处理中…'` resets text — acceptable since page navigates away on success; on error Django re-renders the page fresh
- [x] `ds-seq-type-selector` replaces `ds-pagesize-select` (not both) — correct distinction
- [x] `⌘K`: no JS binding exists in search.js, only HTML + dead CSS to remove
- [x] Scope: 2 JS files, 1 new JS file, 1 CSS file, ~20 templates
