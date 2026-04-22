# Seq List Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Increase delivery-label font size, remove Blast buttons, and move multi-blast to the toolbar with checkbox-driven POST submit.

**Architecture:** CSS-only change for font; HTML deletions for Blast removal; new `multi-blast-toolbar.js` handles button state + form construction; button placed in toolbar HTML; one `ds-tb-btn:disabled` CSS rule appended. No Python changes.

**Tech Stack:** Vanilla JS (ES5), CSS, Django templates. Working directory: `/Users/gutou/Projects/seq_web/seq_database_v2`. No worktree needed.

---

## File Map

| File | Action | What changes |
|---|---|---|
| `static/css/design-system.css` | Modify line 700 + append | `font-size: 0.75em`; append `ds-tb-btn:disabled` rule |
| `templates/seq_list.html` | Modify lines 22, 131–132, 304, 410 | Remove topbar link; add toolbar button; delete 2× Blast links |
| `static/js/multi-blast-toolbar.js` | **Create** | Button enabled/disabled state + form POST on click |
| `templates/base.html` | Modify line 128 | Add `multi-blast-toolbar.js` script tag after `table-sort.js` |

---

## Task 1: CSS — font size + disabled state

**Files:**
- Modify: `static/css/design-system.css:700` (font-size line)
- Modify: `static/css/design-system.css` (append at end)

- [ ] **Step 1: Increase `.seq-delivery-label` font-size**

Line 700 currently reads:
```css
  font-size: 0.62em;
```

Change to:
```css
  font-size: 0.75em;
```

- [ ] **Step 2: Append `ds-tb-btn:disabled` rule at end of file**

Current last lines of `design-system.css`:
```css
.ds-th-sort.ds-sort-asc,
.ds-th-sort.ds-sort-desc { color: #1d4ed8; }
.ds-th-sort.ds-sort-asc .ds-sort-icon,
.ds-th-sort.ds-sort-desc .ds-sort-icon { color: #3b82f6; }
```

Append after them:
```css

/* ── Toolbar button disabled state ── */
.ds-tb-btn:disabled { opacity: 0.45; cursor: not-allowed; }
```

- [ ] **Step 3: Commit**

```bash
git add static/css/design-system.css
git commit -m "style: increase seq-delivery-label font; add ds-tb-btn:disabled"
```

---

## Task 2: Remove Blast action buttons from seq_list.html

**Files:**
- Modify: `templates/seq_list.html:304` (AS/duplex block Blast link)
- Modify: `templates/seq_list.html:410` (SS block Blast link)

- [ ] **Step 1: Remove Blast link in AS/duplex block (line 304)**

Find and delete this exact line (currently at line ~304):
```html
              <a class="ds-act ds-act-blast" href="/blast_seq/?delivery_id={{ group.items.0.rm_code }}&seq_type={{ group.items.0.deliveries.0.Seq_type }}" target="_blank">Blast</a>
```

Delete the entire line. Nothing replaces it.

- [ ] **Step 2: Remove Blast link in SS block (line 410)**

Find and delete this exact line (currently at line ~410 after previous deletion shifts lines):
```html
              <a class="ds-act ds-act-blast" href="/blast_seq/?delivery_id={{ group.items.1.rm_code }}&seq_type={{ group.items.1.deliveries.0.Seq_type }}" target="_blank">Blast</a>
```

Delete the entire line. Nothing replaces it.

- [ ] **Step 3: Verify no Blast links remain**

```bash
grep -n "ds-act-blast\|blast_seq" templates/seq_list.html
```

Expected: no output (zero matches).

- [ ] **Step 4: Commit**

```bash
git add templates/seq_list.html
git commit -m "feat: remove Blast action buttons from seq_list 操作 column"
```

---

## Task 3: Create multi-blast-toolbar.js

**Files:**
- Create: `static/js/multi-blast-toolbar.js`

- [ ] **Step 1: Create the file with this exact content**

```javascript
(function () {
  var btn = document.getElementById('multiBlastBtn');
  if (!btn) return;

  function updateBtn() {
    btn.disabled = document.querySelectorAll('input.row-checkbox:checked').length === 0;
  }

  document.addEventListener('change', function (e) {
    if (e.target.matches('input.row-checkbox') || e.target.id === 'select-all') {
      updateBtn();
    }
  });

  btn.addEventListener('click', function () {
    var checked = document.querySelectorAll('input.row-checkbox:checked');
    if (!checked.length) return;

    var form = document.createElement('form');
    form.method = 'POST';
    form.action = btn.dataset.url;

    var csrf = document.createElement('input');
    csrf.type = 'hidden';
    csrf.name = 'csrfmiddlewaretoken';
    csrf.value = document.cookie.match(/csrftoken=([^;]+)/)[1];
    form.appendChild(csrf);

    checked.forEach(function (cb) {
      var row = cb.closest('tr');
      var input = document.createElement('input');
      input.type = 'hidden';
      input.name = 'seq_id';
      input.value = row.dataset.rmCode;
      form.appendChild(input);
    });

    document.body.appendChild(form);
    form.submit();
  });
})();
```

- [ ] **Step 2: Commit**

```bash
git add static/js/multi-blast-toolbar.js
git commit -m "feat: add multi-blast-toolbar.js for checkbox-driven POST submit"
```

---

## Task 4: Update seq_list.html — move button + add to base.html

**Files:**
- Modify: `templates/seq_list.html:22` (topbar — remove old link)
- Modify: `templates/seq_list.html:131` (toolbar — add new button after 列显示)
- Modify: `templates/base.html:128` (add script tag)

- [ ] **Step 1: Remove multi-blast link from topbar (line 22)**

Find and delete this exact line in `templates/seq_list.html`:
```html
  <a class="ds-btn ds-btn-green" href="{% url 'multi_blast' %}">⌗ 多序列比对</a>
```

Delete the entire line. Nothing replaces it in the topbar.

- [ ] **Step 2: Add multi-blast button to toolbar after 列显示 (line 131)**

Current line 131:
```html
  <button id="toggleColumnPanel" type="button" class="ds-tb-btn ds-tb-purple">◧ 列显示</button>
```

Replace with:
```html
  <button id="toggleColumnPanel" type="button" class="ds-tb-btn ds-tb-purple">◧ 列显示</button>
  <button id="multiBlastBtn" type="button" class="ds-tb-btn ds-tb-green"
          data-url="{% url 'multi_blast' %}" disabled>⌗ 多序列比对</button>
```

- [ ] **Step 3: Add script tag to base.html after table-sort.js (line 128)**

Current line 128 in `templates/base.html`:
```html
<script src="/static/js/table-sort.js"></script>
```

Replace with:
```html
<script src="/static/js/table-sort.js"></script>
<script src="/static/js/multi-blast-toolbar.js"></script>
```

- [ ] **Step 4: Verify topbar no longer has multi-blast link**

```bash
grep -n "multi_blast\|多序列比对" templates/seq_list.html
```

Expected: one match only (the toolbar button `data-url`).

- [ ] **Step 5: Commit**

```bash
git add templates/seq_list.html templates/base.html
git commit -m "feat: move 多序列比对 to toolbar; wire checkbox-driven POST via multi-blast-toolbar.js"
```

---

## Self-Review

**Spec coverage:**
- ✅ Item 1 (font): Task 1 Step 1 — `font-size: 0.62em` → `0.75em`
- ✅ Item 2 (Blast removal): Task 2 — both Blast links deleted, verified by grep
- ✅ Item 3 (multi-blast toolbar): Task 3 (JS) + Task 4 (HTML + base.html)

**Placeholder scan:** None found.

**Type consistency:**
- `multiBlastBtn` id used in JS (`getElementById`) matches HTML (`id="multiBlastBtn"`) — consistent
- `btn.dataset.url` in JS matches `data-url="{% url 'multi_blast' %}"` in HTML — consistent
- `row.dataset.rmCode` in JS reads from `data-rm-code` attribute on `<tr>` (camelCase conversion is automatic) — correct
- `input.row-checkbox` selector in JS matches existing `class="row-checkbox"` on checkboxes — consistent
- `ds-tb-btn:disabled` CSS added in Task 1 covers the `disabled` attribute set on the button — consistent
