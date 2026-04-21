# Frontend Polish Sprint 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate remaining inline styles, Bootstrap remnants, and inconsistent patterns across the worktree's templates and static files in 12 focused tasks.

**Architecture:** Phase 1 (Task 1) adds all new CSS utility classes to `design-system.css` first. Phase 2 (Tasks 2–12) does template and JS substitutions that depend on those classes. All changes are in `.worktrees/frontend-redesign/`. No Python/model logic changes.

**Tech Stack:** Django 5.1 templates, CSS appended to `static/css/design-system.css`, vanilla JS in `static/js/`

---

## File Map

| File | Change |
|---|---|
| `static/css/design-system.css` | Append new classes; update `.ds-form-page`; remove dead `.ds-search-kbd` rule |
| `static/js/loading.js` | **NEW** — auto-loading state on form submit |
| `static/js/clone_delivery.js` | Replace Bootstrap `form-row`/`form-group`/`form-control` with `ds-*` |
| `templates/base.html` | Nav icon inline styles → `ds-nav-icon`; add `loading.js` script tag |
| `templates/seq_list.html` | Remove ⌘K span; advanced search grid Bootstrap → `ds-form-3col` |
| `templates/clone_modal.html` | Remove inline `<style>` block; replace `clone-divider` → `ds-clone-divider` |
| `templates/edit_module.html` | Alert → `ds-alert-*` |
| `templates/edit_seqmodule.html` | Alert → `ds-alert-*`; form hint → `ds-form-hint` |
| `templates/auth_edit.html` | Alert → `ds-alert-*`; form hint → `ds-form-hint`; remove padding-top |
| `templates/author_add.html` | Alert → `ds-alert-*`; form hint → `ds-form-hint`; remove padding-top |
| `templates/change_password.html` | Alert → `ds-alert-*`; remove padding-top |
| `templates/register.html` | Alert → `ds-alert-*` |
| `templates/login.html` | Alert → `ds-alert-*` |
| `templates/reg_seq_edit.html` | Alert → `ds-alert-*`; remove padding-top |
| `templates/module_list.html` | Delete btn → `ds-act-delete`; empty state → `ds-empty-state` |
| `templates/seqmodule_list.html` | Delete btn → `ds-act-delete`; empty state → `ds-empty-state` |
| `templates/reg_seq_list.html` | Empty state → `ds-empty-state` |
| `templates/auth_list.html` | Empty state → `ds-empty-state` |
| 11 `ds-form-page` templates | Remove `style="padding-top:20px;"` |
| `templates/multi_blast.html` | Remove `style="padding-top:20px;"` |

---

### Task 1: Add all new CSS utility classes to design-system.css

**Files:**
- Modify: `.worktrees/frontend-redesign/static/css/design-system.css`

- [ ] **Step 1: Update the existing `.ds-form-page` rule (line 376)**

Current line 376:
```css
.ds-form-page { padding: 24px 20px; display: flex; justify-content: center; }
```

Change to:
```css
.ds-form-page { padding: 20px; display: flex; justify-content: center; }
```

(Changes top padding from 24px to 20px, matching what 11 templates' inline `style="padding-top:20px;"` was overriding to.)

- [ ] **Step 2: Append all new utility classes at end of file**

Append this entire block to the end of `design-system.css`:

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
.ds-empty-state { text-align: center; color: #94a3b8; padding: 32px; }

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

/* ── 3-column form grid (advanced search) ── */
.ds-form-3col {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 8px 12px;
}
.ds-form-span-3 { grid-column: 1 / -1; }

/* ── Clone modal row and divider ── */
.ds-clone-row {
  padding: 8px; border: 1px solid #e8edf4;
  border-radius: 6px; margin-bottom: 8px;
}
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

/* ── Button: disabled state ── */
.ds-btn:disabled,
.ds-btn[disabled] {
  opacity: 0.55; cursor: not-allowed; pointer-events: none;
}

/* ── Button: loading state ── */
@keyframes ds-spin { to { transform: rotate(360deg); } }
.ds-btn-loading {
  opacity: 0.75; cursor: not-allowed; pointer-events: none;
  display: inline-flex !important; align-items: center; gap: 7px;
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
.ds-btn-ghost.ds-btn-loading::before {
  border-color: rgba(100,116,139,.3);
  border-top-color: #64748b;
}
```

- [ ] **Step 3: Verify new classes exist**

```bash
grep -c "ds-alert-success\|ds-empty-state\|ds-form-hint\|ds-act-delete\|ds-nav-icon\|ds-seq-type-selector\|ds-form-3col\|ds-clone-divider\|ds-btn-loading" .worktrees/frontend-redesign/static/css/design-system.css
```

Expected: `9` (one match per class)

- [ ] **Step 4: Verify ds-form-page padding updated**

```bash
grep -n "ds-form-page" .worktrees/frontend-redesign/static/css/design-system.css
```

Expected output contains `padding: 20px` (not `24px 20px`).

- [ ] **Step 5: Commit**

```bash
cd .worktrees/frontend-redesign
git add static/css/design-system.css
git commit -m "style: add ds-alert, ds-empty-state, ds-form-hint, ds-act-delete, ds-clone-*, ds-btn-loading utilities; fix ds-form-page padding"
```

---

### Task 2: Remove ⌘K shortcut + dead CSS

**Files:**
- Modify: `.worktrees/frontend-redesign/templates/seq_list.html` (line 17)
- Modify: `.worktrees/frontend-redesign/static/css/design-system.css` (lines 224–230)

- [ ] **Step 1: Remove the ⌘K span from seq_list.html**

Find and remove this line (line ~17):
```html
    <span class="ds-search-kbd">⌘K</span>
```

The surrounding context:
```html
    <input type="text" id="searchInput" class="ds-search-input"
           placeholder="快速搜索 Strand ID / Target / Sequence…" value="{{ search_q }}">
    <span class="ds-search-kbd">⌘K</span>   ← DELETE THIS LINE
  </div>
```

After deletion the `ds-search-wrap` div ends with the `<input>` followed by `</div>`.

- [ ] **Step 2: Remove the dead .ds-search-kbd CSS rule**

In `design-system.css`, find and delete this block (lines ~224–230):
```css
.ds-search-kbd {
  background: #e8edf4; color: #64748b;
  font-size: 9px; font-weight: 700;
  padding: 1px 5px; border-radius: 4px;
  font-family: 'DM Mono', monospace;
}
```

- [ ] **Step 3: Verify**

```bash
grep -rn "ds-search-kbd\|⌘K" .worktrees/frontend-redesign/templates/ .worktrees/frontend-redesign/static/
```

Expected: no output.

- [ ] **Step 4: Commit**

```bash
cd .worktrees/frontend-redesign
git add templates/seq_list.html static/css/design-system.css
git commit -m "style: remove ⌘K shortcut hint and dead ds-search-kbd CSS"
```

---

### Task 3: seq_list.html — advanced search panel Bootstrap grid → ds-form-3col

**Files:**
- Modify: `.worktrees/frontend-redesign/templates/seq_list.html` (lines ~38–95)

The advanced search panel currently uses `<div class="row g-2">` with `<div class="col-md-4">` (8 fields) and `<div class="col-12" id="modifySeqInputsWrap">`.

- [ ] **Step 1: Replace grid wrapper**

```html
<!-- old -->
    <div class="row g-2">
<!-- new -->
    <div class="ds-form-3col">
```

- [ ] **Step 2: Replace all col-md-4 divs**

Change every `<div class="col-md-4">` to `<div>`. There are 8 occurrences (Strand ID, Naked Sequence, Target, Project, Seq Type, 5' Ligand, 3' Ligand, Transcript fields — not all are col-md-4, check the actual file).

Run: `grep -n "col-md-4\|col-md-6\|col-12\|col-md-" .worktrees/frontend-redesign/templates/seq_list.html`

For each `col-md-4` → `<div>`, for each `col-md-6` → `<div>`, for `col-12` with id `modifySeqInputsWrap` → `<div class="ds-form-span-3" id="modifySeqInputsWrap">`, for `col-12` without id → `<div class="ds-form-span-3">`.

- [ ] **Step 3: Verify Bootstrap grid classes gone from advancedSearchForm**

```bash
grep -n "row g-2\|col-md-\|col-12\|col-sm-" .worktrees/frontend-redesign/templates/seq_list.html
```

Expected: no output.

- [ ] **Step 4: Commit**

```bash
cd .worktrees/frontend-redesign
git add templates/seq_list.html
git commit -m "style: seq_list advanced search — Bootstrap grid → ds-form-3col"
```

---

### Task 4: clone_modal.html + clone_delivery.js — remove Bootstrap form classes

**Files:**
- Modify: `.worktrees/frontend-redesign/templates/clone_modal.html`
- Modify: `.worktrees/frontend-redesign/static/js/clone_delivery.js`

#### clone_modal.html

- [ ] **Step 1: Remove the inline `<style>` block from clone_modal.html**

Delete lines 1–13 (the entire `<style>...</style>` block at the top of the file):
```html
<!-- Reusable clone modal include -->
<style>
  /* Normalize labels and heading spacing inside clone modal for consistent alignment */
  #cloneModal .form-group label { ... }
  ...
</style>
```

After deletion the file starts with `<div class="modal fade" id="cloneModal" ...>`.

- [ ] **Step 2: Verify style block gone**

```bash
grep -n "<style>\|form-group\|form-row\|clone-divider" .worktrees/frontend-redesign/templates/clone_modal.html
```

Expected: no output.

#### clone_delivery.js

The JS at lines 20–53 generates HTML using Bootstrap classes. Replace the entire `html +=` block (lines 20–54) as follows:

- [ ] **Step 3: Replace Bootstrap HTML generation in clone_delivery.js**

Find the block starting at `html += '<div class="clone-row p-2 border mb-2">';` and ending before `$('#cloneRowsContainer').append(html);`.

Replace with:

```javascript
                html += '<div class="ds-clone-row">';
                var seqType = (r.Seq_type || '').toString().toUpperCase();
                var headingStyle = '';
                if (seqType === 'AS' || seqType === 'SS') {
                    headingStyle = 'style="font-size:1.1rem; font-weight:600;"';
                }
                html += '<h6 ' + headingStyle + '>Record ' + (idx + 1) + ' - ' + (r.Seq_type || '') + '</h6>';
                // row 1: Project, Target, Seq_type (3 columns)
                html += '<div class="ds-form-3col">';
                html += '<div><label class="ds-form-label">Project</label><input name="Project" class="ds-form-control" value="' + (r.Project || '') + '" readonly /></div>';
                html += '<div><label class="ds-form-label">Target</label><input name="Target" class="ds-form-control" value="' + (r.Target || '') + '" readonly /></div>';
                html += '<div><label class="ds-form-label">Seq_type</label><input name="Seq_type" class="ds-form-control" value="' + (r.Seq_type || '') + '" readonly /></div>';
                html += '</div>';
                // row 2: Modify_seq (full width)
                html += '<div style="margin-top:8px;">';
                html += '<label class="ds-form-label">Modify_seq</label><input name="Modify_seq" class="ds-form-control" value="' + (r.Modify_seq || '') + '" />';
                html += '</div>';
                // row 3: delivery5, delivery3 (2 columns)
                html += '<div class="ds-form-2col" style="margin-top:8px;">';
                html += '<div><label class="ds-form-label">delivery5</label><input name="delivery5" class="ds-form-control" value="' + (r.delivery5 || '') + '" /></div>';
                html += '<div><label class="ds-form-label">delivery3</label><input name="delivery3" class="ds-form-control" value="' + (r.delivery3 || '') + '" /></div>';
                html += '</div>';
                // row 4: Strand_MWs, Parents, Remark (3 columns)
                html += '<div class="ds-form-3col" style="margin-top:8px;">';
                html += '<div><label class="ds-form-label">Strand_MWs</label><input name="Strand_MWs" class="ds-form-control" value="' + (r.Strand_MWs || '') + '" /></div>';
                html += '<div><label class="ds-form-label">Parents</label><input name="Parents" class="ds-form-control" value="' + (r.Parents || '') + '" /></div>';
                html += '<div><label class="ds-form-label">Remark</label><input name="Remark" class="ds-form-control" value="' + (r.Remark || '') + '" /></div>';
                html += '</div>';
                html += '</div>';
```

- [ ] **Step 4: Replace `clone-divider` with `ds-clone-divider` in JS (line ~53)**

```javascript
// old
$('#cloneRowsContainer .clone-row').first().after('<div class="clone-divider" aria-hidden="true"></div>');
// new
$('#cloneRowsContainer .ds-clone-row').first().after('<div class="ds-clone-divider" aria-hidden="true"></div>');
```

Also update the `each` selector on line ~64:
```javascript
// old
$('#cloneRowsContainer .clone-row').each(function() {
// new
$('#cloneRowsContainer .ds-clone-row').each(function() {
```

- [ ] **Step 5: Verify no Bootstrap form classes remain in JS**

```bash
grep -n "form-row\|form-group\|form-control\|col-md-\|col-12\|text-left\|clone-row\|clone-divider" .worktrees/frontend-redesign/static/js/clone_delivery.js | grep -v "ds-"
```

Expected: no output.

- [ ] **Step 6: Commit**

```bash
cd .worktrees/frontend-redesign
git add templates/clone_modal.html static/js/clone_delivery.js
git commit -m "style: clone_modal — remove inline style block; clone_delivery.js — replace Bootstrap form classes with ds-*"
```

---

### Task 5: Alert blocks → ds-alert in all form templates

**Files:** `templates/edit_module.html`, `templates/edit_seqmodule.html`, `templates/auth_edit.html`, `templates/author_add.html`, `templates/change_password.html`, `templates/register.html`, `templates/login.html`, `templates/reg_seq_edit.html`

All 8 files contain the same `{% if messages %}` block pattern. Replace in each file.

- [ ] **Step 1: Identify the alert block in each file**

```bash
grep -n "if messages\|for message in messages\|message.tags" .worktrees/frontend-redesign/templates/edit_module.html .worktrees/frontend-redesign/templates/edit_seqmodule.html .worktrees/frontend-redesign/templates/auth_edit.html .worktrees/frontend-redesign/templates/author_add.html .worktrees/frontend-redesign/templates/change_password.html .worktrees/frontend-redesign/templates/register.html .worktrees/frontend-redesign/templates/login.html .worktrees/frontend-redesign/templates/reg_seq_edit.html
```

- [ ] **Step 2: Replace the alert block in all 8 files**

In each file, find:
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

Replace with:
```django
{% if messages %}
<div class="ds-alert-list">
  {% for message in messages %}
  <div class="ds-alert {% if 'error' in message.tags %}ds-alert-error{% elif 'success' in message.tags %}ds-alert-success{% else %}ds-alert-info{% endif %}">{{ message }}</div>
  {% endfor %}
</div>
{% endif %}
```

Note: the exact whitespace and indentation may differ slightly per file — match the surrounding context's indentation style.

- [ ] **Step 3: Verify no inline alert styles remain**

```bash
grep -rn "background:#fef2f2\|background:#f0fdf4\|background:#f0f9ff\|message.tags.*background" .worktrees/frontend-redesign/templates/edit_module.html .worktrees/frontend-redesign/templates/edit_seqmodule.html .worktrees/frontend-redesign/templates/auth_edit.html .worktrees/frontend-redesign/templates/author_add.html .worktrees/frontend-redesign/templates/change_password.html .worktrees/frontend-redesign/templates/register.html .worktrees/frontend-redesign/templates/login.html .worktrees/frontend-redesign/templates/reg_seq_edit.html
```

Expected: no output.

- [ ] **Step 4: Commit**

```bash
cd .worktrees/frontend-redesign
git add templates/edit_module.html templates/edit_seqmodule.html templates/auth_edit.html templates/author_add.html templates/change_password.html templates/register.html templates/login.html templates/reg_seq_edit.html
git commit -m "style: replace inline alert blocks with ds-alert-* classes across 8 templates"
```

---

### Task 6: Delete buttons + empty states

**Files:** `templates/module_list.html`, `templates/seqmodule_list.html`, `templates/reg_seq_list.html`, `templates/auth_list.html`

- [ ] **Step 1: Fix delete buttons in module_list.html**

Find:
```html
<button type="submit" class="ds-act" style="border-color:#fca5a5;color:#ef4444;background:#fff;">删除</button>
```

Replace with:
```html
<button type="submit" class="ds-act-delete">删除</button>
```

- [ ] **Step 2: Fix delete button in seqmodule_list.html**

Find:
```html
<button type="submit" class="ds-act" style="border-color:#fca5a5;color:#ef4444;background:#fff;">删除</button>
```

Replace with:
```html
<button type="submit" class="ds-act-delete">删除</button>
```

- [ ] **Step 3: Fix empty state in module_list.html**

Find:
```html
<tr><td colspan="4" style="text-align:center;color:#94a3b8;padding:32px;">暂无模块数据</td></tr>
```

Replace with:
```html
<tr><td colspan="4" class="ds-empty-state">暂无模块数据</td></tr>
```

- [ ] **Step 4: Fix empty state in seqmodule_list.html**

Find:
```html
<tr><td colspan="4" style="text-align:center;color:#94a3b8;padding:32px;">暂无修饰模块数据</td></tr>
```

Replace with:
```html
<tr><td colspan="4" class="ds-empty-state">暂无修饰模块数据</td></tr>
```

- [ ] **Step 5: Fix empty state in reg_seq_list.html**

Find:
```html
<tr><td colspan="7" style="text-align:center;color:#94a3b8;padding:32px;">暂无注册序列数据</td></tr>
```

Replace with:
```html
<tr><td colspan="7" class="ds-empty-state">暂无注册序列数据</td></tr>
```

- [ ] **Step 6: Fix empty state in auth_list.html**

Find:
```html
<tr><td colspan="6" style="text-align:center;color:#94a3b8;padding:32px;">暂无用户数据</td></tr>
```

Replace with:
```html
<tr><td colspan="6" class="ds-empty-state">暂无用户数据</td></tr>
```

- [ ] **Step 7: Verify**

```bash
grep -rn "border-color:#fca5a5\|text-align:center;color:#94a3b8;padding:32px" .worktrees/frontend-redesign/templates/module_list.html .worktrees/frontend-redesign/templates/seqmodule_list.html .worktrees/frontend-redesign/templates/reg_seq_list.html .worktrees/frontend-redesign/templates/auth_list.html
```

Expected: no output.

- [ ] **Step 8: Commit**

```bash
cd .worktrees/frontend-redesign
git add templates/module_list.html templates/seqmodule_list.html templates/reg_seq_list.html templates/auth_list.html
git commit -m "style: delete buttons → ds-act-delete; empty states → ds-empty-state"
```

---

### Task 7: Remove padding-top:20px from ds-form-page divs (11 templates)

**Files:** `templates/auth_edit.html`, `templates/author_add.html`, `templates/edit_module.html`, `templates/edit_seqmodule.html`, `templates/multi_blast.html`, `templates/reg_seq_edit.html`, `templates/register_seq.html`, `templates/seq_edit.html`, `templates/upload_delivery_info.html`, `templates/upload_modules.html`, `templates/upload_seqmodules.html`

- [ ] **Step 1: Remove inline padding-top from all 11 files**

In each file, find:
```html
<div class="ds-form-page" style="padding-top:20px;">
```

Replace with:
```html
<div class="ds-form-page">
```

This substitution is identical in all 11 files.

- [ ] **Step 2: Verify**

```bash
grep -rn "ds-form-page.*padding-top\|padding-top.*ds-form-page" .worktrees/frontend-redesign/templates/
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
cd .worktrees/frontend-redesign
git add templates/auth_edit.html templates/author_add.html templates/edit_module.html templates/edit_seqmodule.html templates/multi_blast.html templates/reg_seq_edit.html templates/register_seq.html templates/seq_edit.html templates/upload_delivery_info.html templates/upload_modules.html templates/upload_seqmodules.html
git commit -m "style: remove redundant padding-top:20px from ds-form-page divs — now in CSS"
```

---

### Task 8: Form hints, nav icons, seq-type selector

**Files:** `templates/auth_edit.html`, `templates/author_add.html`, `templates/edit_seqmodule.html`, `templates/base.html`, `templates/seq_list.html`

- [ ] **Step 1: Form hints → ds-form-hint (3 files)**

In `templates/auth_edit.html` (line ~38):
```html
<!-- old -->
<p style="font-size:12px;color:#64748b;margin:4px 0 0 0;">多个项目用逗号分隔。</p>
<!-- new -->
<p class="ds-form-hint">多个项目用逗号分隔。</p>
```

In `templates/author_add.html` (line ~36):
```html
<!-- old -->
<p style="font-size:12px;color:#64748b;margin:4px 0 0 0;">多个项目用逗号分隔。</p>
<!-- new -->
<p class="ds-form-hint">多个项目用逗号分隔。</p>
```

In `templates/edit_seqmodule.html` (line ~44):
```html
<!-- old -->
<p style="font-size:12px;color:#64748b;margin:4px 0 0 0;">linker_seq 中该 token 后追加的连接符，默认为 o</p>
<!-- new -->
<p class="ds-form-hint">linker_seq 中该 token 后追加的连接符，默认为 o</p>
```

- [ ] **Step 2: Nav icons → ds-nav-icon (base.html)**

In `templates/base.html`, replace all 7 instances of:
```html
<i class="bi bi-ICONNAME" style="font-size:13px;flex-shrink:0;"></i>
```
with:
```html
<i class="bi bi-ICONNAME ds-nav-icon"></i>
```

The 7 icons are: `bi-table`, `bi-plus-circle`, `bi-cloud-upload`, `bi-search`, `bi-box-seam`, `bi-check2-square`, `bi-people`.

- [ ] **Step 3: Seq-type selector → ds-seq-type-selector (seq_list.html, line ~188)**

Find:
```html
<select id="seq_type_selector" class="ds-pagesize-select" style="width:auto;margin-top:2px;min-width:140px;font-size:11px;">
```

Replace with:
```html
<select id="seq_type_selector" class="ds-seq-type-selector">
```

- [ ] **Step 4: Verify**

```bash
grep -rn "font-size:12px;color:#64748b;margin:4px" .worktrees/frontend-redesign/templates/
grep -n "font-size:13px;flex-shrink:0" .worktrees/frontend-redesign/templates/base.html
grep -n "ds-pagesize-select.*seq_type_selector\|seq_type_selector.*ds-pagesize-select" .worktrees/frontend-redesign/templates/seq_list.html
```

Expected: all three commands return no output.

- [ ] **Step 5: Commit**

```bash
cd .worktrees/frontend-redesign
git add templates/auth_edit.html templates/author_add.html templates/edit_seqmodule.html templates/base.html templates/seq_list.html
git commit -m "style: form hints → ds-form-hint; nav icons → ds-nav-icon; seq-type selector → ds-seq-type-selector"
```

---

### Task 9: Form submit loading state

**Files:**
- Create: `.worktrees/frontend-redesign/static/js/loading.js`
- Modify: `.worktrees/frontend-redesign/templates/base.html`

- [ ] **Step 1: Create loading.js**

Create `.worktrees/frontend-redesign/static/js/loading.js` with this exact content:

```javascript
(function () {
  document.addEventListener('submit', function (e) {
    var form = e.target;
    var btn = form.querySelector('button[type=submit]');
    if (!btn) return;
    if (btn.classList.contains('ds-btn-loading')) {
      e.preventDefault();
      return;
    }
    btn.classList.add('ds-btn-loading');
    btn.disabled = true;
    btn.textContent = '处理中…';
  });
})();
```

- [ ] **Step 2: Add loading.js to base.html**

Find the closing `</body>` tag in `templates/base.html`. Add the script tag immediately before it:

```html
<script src="/static/js/loading.js"></script>
</body>
```

- [ ] **Step 3: Verify**

```bash
ls .worktrees/frontend-redesign/static/js/loading.js
grep -n "loading.js" .worktrees/frontend-redesign/templates/base.html
```

Expected: file exists; base.html contains the script tag.

- [ ] **Step 4: Commit**

```bash
cd .worktrees/frontend-redesign
git add static/js/loading.js templates/base.html
git commit -m "feat: add form submit loading state — auto-disable button with ds-btn-loading on POST submit"
```

---

## Done

After all 9 tasks, run a final verification:

```bash
# No Bootstrap grid classes in templates (except clone_modal Bootstrap Modal structure which is intentional)
grep -rn "row g-2\|col-md-\|form-group\|form-control\|form-row" .worktrees/frontend-redesign/templates/ | grep -v "modal\|modal-"

# No inline alert color styles
grep -rn "background:#fef2f2\|background:#f0fdf4\|message.tags.*background" .worktrees/frontend-redesign/templates/

# No ds-form-page with padding-top inline
grep -rn "ds-form-page.*padding-top" .worktrees/frontend-redesign/templates/

# No ⌘K
grep -rn "⌘K\|ds-search-kbd" .worktrees/frontend-redesign/templates/ .worktrees/frontend-redesign/static/
```

All expected to return no output.
