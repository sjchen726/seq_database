# Seq List Polish — Design Spec

**Date:** 2026-04-22
**Status:** Approved

---

## Overview

Three targeted changes to `seq_list.html` and related files. No Python/Django changes.

---

## Item 1: Increase `.seq-delivery-label` Font Size

### Change

`static/css/design-system.css` — `.seq-delivery-label` rule:

```css
/* before */
font-size: 0.62em;

/* after */
font-size: 0.75em;
```

One-line change. Affects all pages that render sequence blocks (seq_list.html).

---

## Item 2: Remove Blast Action Button

### Change

`templates/seq_list.html` — delete both occurrences of:

```html
<a class="ds-act ds-act-blast" href="/blast_seq/?delivery_id={{ group.items.0.rm_code }}&seq_type={{ group.items.0.deliveries.0.Seq_type }}" target="_blank">Blast</a>
```

There are two instances (one in the AS/duplex render block, one in the SS block). Both are removed. No other changes needed — `.ds-act-blast` CSS can remain (harmless dead rule).

---

## Item 3: Multi-Blast Button in Toolbar with Checkbox-Driven Submit

### Button placement

Move the "多序列比对" link out of the topbar and into the toolbar, immediately after the `◧ 列显示` button:

```html
<!-- topbar: remove this -->
<a class="ds-btn ds-btn-green" href="{% url 'multi_blast' %}">⌗ 多序列比对</a>

<!-- toolbar: add after 列显示 button -->
<button id="multiBlastBtn" type="button" class="ds-tb-btn ds-tb-green" disabled>⌗ 多序列比对</button>
```

The button uses `disabled` by default (no rows selected). Style class `ds-tb-green` follows existing `ds-tb-btn` modifier pattern.

### JS behavior (`static/js/multi-blast-toolbar.js`)

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

- `btn.dataset.url` is set via `data-url="{% url 'multi_blast' %}"` on the button element
- CSRF token read from cookie (standard Django pattern, already works site-wide)
- Submits in current tab (navigates away)

### HTML button element

```html
<button id="multiBlastBtn" type="button" class="ds-tb-btn ds-tb-green"
        data-url="{% url 'multi_blast' %}" disabled>⌗ 多序列比对</button>
```

### CSS — add `ds-tb-green` modifier

Append to `design-system.css`:

```css
.ds-tb-btn.ds-tb-green { color: #15803d; }
.ds-tb-btn.ds-tb-green:hover:not(:disabled) { background: #f0fdf4; border-color: #86efac; }
.ds-tb-btn:disabled { opacity: 0.45; cursor: not-allowed; }
```

### `base.html`

Add script tag after `table-sort.js`:

```html
<script src="/static/js/multi-blast-toolbar.js"></script>
```

---

## File Map

| File | Action |
|---|---|
| `static/css/design-system.css` | Modify: increase `.seq-delivery-label` font-size; append `ds-tb-green` + `ds-tb-btn:disabled` |
| `templates/seq_list.html` | Modify: remove 2× Blast links; remove topbar multi-blast link; add toolbar button |
| `static/js/multi-blast-toolbar.js` | **Create** |
| `templates/base.html` | Modify: add `multi-blast-toolbar.js` script tag |

---

## Spec Self-Review

- [x] No Python/Django changes
- [x] CSRF token read from cookie — works with Django's default `CsrfViewMiddleware`
- [x] `data-rm-code` attribute already exists on every `<tr>` in seq_list.html — JS uses `row.dataset.rmCode`
- [x] Button disabled state synced on both individual checkbox change and select-all change
- [x] `ds-tb-green` modifier follows existing `ds-tb-purple`, `ds-tb-blue` pattern in design-system.css
- [x] `ds-tb-btn:disabled` rule needed — no existing disabled style for toolbar buttons
- [x] Blast link removal: 2 occurrences in seq_list.html (AS block + SS block) — both removed
- [x] Topbar multi-blast link fully removed (not just hidden)
