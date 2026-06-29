# Row Actions Redesign — Design Spec

**Date:** 2026-06-29
**Scope:** Compound list page — row-level action buttons + multi-select batch toolbar

---

## 1. Background

The compound list (`compound_list.html`) currently has:
- A red `ds-btn ds-btn-danger` delete button (🗑) crammed into a 36 px column — visually jarring
- No edit button
- Checkboxes that drive a compare bar (≥2 selected), but no batch delete or download

This spec covers the first of three sequential improvements:
1. **Spec 1 (this):** Row button redesign + batch toolbar
2. **Spec 2:** Edit modal (experiment + compound metadata)
3. **Spec 3:** Edit/delete permission request & approval workflow

---

## 2. Row Action Buttons

### Current state
```html
<td style="width:36px;padding:4px 2px;text-align:center;">
  <button class="ds-btn ds-btn-danger" style="font-size:10px;padding:2px 6px;height:24px;min-width:0;"
          onclick="event.stopPropagation();clDeleteRow({{ vc.exp_ids|join:',' }})"
          title="删除该化合物的实验数据">🗑</button>
</td>
```

### New design

Replace the single-icon column with a 56 px "actions" column containing two icon-only buttons:

```html
<td class="cl-row-actions" onclick="event.stopPropagation()">
  <button class="cl-icon-btn cl-icon-edit"
          onclick="clEditRow('{{ vc.compound.compound_id }}')"
          title="编辑">✏️</button>
  <button class="cl-icon-btn cl-icon-del"
          onclick="clDeleteRow({{ vc.exp_ids|join:',' }})"
          title="删除">🗑</button>
</td>
```

Permission guard (same as current — both buttons only rendered when user has delete/data permission):
```django
{% if request.user.is_superuser or request.user.user_type == 'superadmin' or 'data' in request.user.module_permissions %}
<td class="cl-row-actions" onclick="event.stopPropagation()">...</td>
{% endif %}
```

### CSS (new classes in `design-system.css`)

```css
/* Actions column — fade in on row hover */
.cl-row-actions {
  width: 56px;
  padding: 0 4px;
  text-align: right;
  white-space: nowrap;
}
.cl-icon-btn {
  background: none;
  border: 1px solid transparent;
  border-radius: 4px;
  padding: 3px 5px;
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, background 0.15s, border-color 0.15s;
}
.cmp-row:hover .cl-icon-btn { opacity: 1; }
.cl-icon-edit { color: #3b82f6; }
.cl-icon-edit:hover { background: #eff6ff; border-color: #bfdbfe; }
.cl-icon-del  { color: #94a3b8; }
.cl-icon-del:hover  { background: #fef2f2; border-color: #fecaca; color: #dc2626; }
```

### Edit placeholder (Spec 2 stub)

```js
function clEditRow(compoundId) {
  // Spec 2 will implement the real modal.
  // For now: show a brief toast.
  _clShowToast('编辑功能即将上线');
}
```

`_clShowToast(msg)` — a small helper that appends a 2-second auto-dismiss notification div.

---

## 3. Multi-Select Batch Toolbar

### Current state

- Bar (`cl-cmp-bar`) shows only when `_clCmpSelected.length >= 2`
- Contains: "已选 N 个化合物", "对比曲线" button, "✕ 清除"

### New behaviour

- Bar shows when `_clCmpSelected.length >= 1`
- Layout (left → right): count label · "⬇ 下载 CSV" · "对比曲线" (greyed when < 2) · "🗑 批量删除" (permission-gated) · "✕"

### Template changes (`cl-cmp-bar` block)

```html
<div id="cl-cmp-bar" class="cl-cmp-bar" style="display:none">
  <span id="cl-cmp-count" class="cl-cmp-count-label"></span>
  <button class="ds-btn ds-btn-ghost cl-bar-btn" onclick="clBatchDownload()">⬇ 下载 CSV</button>
  <button id="cl-cmp-btn" class="ds-btn ds-btn-primary cl-bar-btn" onclick="clOpenCmpModal()">对比曲线</button>
  {% if can_delete %}
  <button class="ds-btn cl-bar-btn cl-bar-delete" onclick="clBatchDelete()">🗑 批量删除</button>
  {% endif %}
  <button class="cl-cmp-clear-btn" onclick="clClearCmpSelection()">✕</button>
</div>
```

`can_delete` is passed from the view (see §4).

### JS changes (`compound_list.js`)

**Update `clToggleCmpCheck()`** — change threshold from 2 to 1:
```js
bar.style.display = _clCmpSelected.length >= 1 ? 'flex' : 'none';
```

**Disable compare button when < 2 selected:**
```js
const cmpBtn = document.getElementById('cl-cmp-btn');
if (cmpBtn) cmpBtn.disabled = _clCmpSelected.length < 2;
```

**New `clBatchDownload()`:**
```js
function clBatchDownload() {
  const expIds = _clCmpSelected.flatMap(s => s.expIds);
  if (!expIds.length) return;
  const form = document.createElement('form');
  form.method = 'POST';
  form.action = '/api/experiments/bulk-export/';
  const csrf = document.createElement('input');
  csrf.type = 'hidden'; csrf.name = 'csrfmiddlewaretoken';
  csrf.value = document.cookie.match(/csrftoken=([^;]+)/)[1];
  form.appendChild(csrf);
  expIds.forEach(id => {
    const inp = document.createElement('input');
    inp.type = 'hidden'; inp.name = 'exp_ids'; inp.value = id;
    form.appendChild(inp);
  });
  document.body.appendChild(form);
  form.submit();
  document.body.removeChild(form);
}
```

**New `clBatchDelete()`:**
```js
function clBatchDelete() {
  const expIds = _clCmpSelected.flatMap(s => s.expIds);
  if (!expIds.length) return;
  if (!confirm(`确定删除选中的 ${_clCmpSelected.length} 个化合物的实验数据？此操作不可恢复。`)) return;
  fetch('/api/experiments/bulk-delete/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': document.cookie.match(/csrftoken=([^;]+)/)[1],
    },
    body: JSON.stringify({ exp_ids: expIds }),
  }).then(r => r.json()).then(data => {
    if (data.ok) { clClearCmpSelection(); location.reload(); }
    else alert('删除失败: ' + (data.error || '未知错误'));
  });
}
```

**New `_clShowToast(msg)`:**
```js
function _clShowToast(msg) {
  const t = document.createElement('div');
  t.className = 'cl-toast';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2000);
}
```

Toast CSS (in `design-system.css`):
```css
.cl-toast {
  position: fixed;
  bottom: 80px;
  left: 50%;
  transform: translateX(-50%);
  background: #1e293b;
  color: #f1f5f9;
  padding: 8px 18px;
  border-radius: 6px;
  font-size: 13px;
  z-index: 9999;
  pointer-events: none;
  animation: cl-toast-in 0.2s ease;
}
@keyframes cl-toast-in { from { opacity:0; transform: translateX(-50%) translateY(8px); } }
```

---

## 4. Backend — `can_delete` context + bulk-export endpoint

### `can_delete` in view context (`app01/views.py`, `compound_list` view)

```python
can_delete = (
    request.user.is_superuser
    or request.user.user_type == 'superadmin'
    or 'data' in request.user.module_permissions
)
```

Pass to template: `context['can_delete'] = can_delete`

### New endpoint: `POST /api/experiments/bulk-export/`

Returns a CSV file attachment. Fields exported per experiment:

| Column | Source |
|--------|--------|
| compound_id | `Experiment.compound.compound_id` |
| exp_type | `Experiment.exp_type` |
| assay_name | `Experiment.assay_name` |
| batch_label | `Experiment.batch_label` |
| cell_line | `Experiment.cell_line` |
| timepoint / dose | `DataPoint.timepoint` or `DataPoint.dose_nm` |
| readout_type | `DataPoint.readout_type` |
| value | `DataPoint.value` |
| replicate | `DataPoint.replicate` |

Implementation: query `Experiment.objects.filter(pk__in=exp_ids)`, prefetch `datapoints`, write CSV via `csv.writer` to `HttpResponse` with `Content-Disposition: attachment`.

Permission check: same as bulk-delete (login required + `can_delete` or read-only for own-project users — since this is just a download, all logged-in users with project access may download; no `can_delete` gate needed for export).

URL: `path('api/experiments/bulk-export/', views.bulk_export_experiments, name='bulk_export_experiments')`

---

## 5. File Map

| File | Change |
|------|--------|
| `templates/compound_list.html` | Replace delete `<td>` → `cl-row-actions` in both vitro + vivo tables; update `cl-cmp-bar` HTML; add `can_delete` template var usage |
| `static/css/design-system.css` | Add `.cl-row-actions`, `.cl-icon-btn`, `.cl-icon-edit`, `.cl-icon-del`, `.cl-toast` |
| `static/js/compound_list.js` | Update `clToggleCmpCheck`; add `clBatchDownload`, `clBatchDelete`, `_clShowToast`, `clEditRow` stub |
| `app01/views.py` | Add `can_delete` to `compound_list` context; add `bulk_export_experiments` view |
| `bms/urls.py` | Register `bulk-export` URL |

No migrations required.

---

## 6. Testing

- Delete button: hover over a row → buttons fade in; click 🗑 → existing confirm prompt fires
- Edit button: click ✏️ → "编辑功能即将上线" toast appears for 2s
- Select 1 compound → bar appears with Download + Delete; Compare button disabled
- Select 2+ compounds → Compare button enabled
- Download CSV: select 2 compounds → click "⬇ 下载 CSV" → file download triggers, CSV contains their data
- Batch delete: select 2 compounds → "🗑 批量删除" → confirm → page reloads without those rows
- Non-admin user: edit/delete buttons not rendered; batch delete button not in bar
