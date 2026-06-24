# Compound List Sub-project B — Design Spec

**Date:** 2026-06-25
**Scope:** Select-all per batch, download (PNG + CSV), delete selected experiments on the compound list page.

---

## Goal

1. Add a "全选" checkbox to each batch section header so users can select all compounds in a batch at once.
2. Let users delete selected compounds' experiment records (in their respective batches) from the compound list page.
3. Let users download the comparison chart as a PNG image and the selected compounds' data as a CSV file.

---

## Section 1: Select All per Batch

### Template change

Each batch section has a vitro table and/or a vivo table. Add one "全选" checkbox per table (not one per entire batch, since vitro and vivo are separate scopes):

```html
<!-- in each table's <thead><tr> first cell -->
<th style="width:28px;padding:4px;">
  <input type="checkbox" class="cl-batch-select-all"
         onchange="clToggleBatchSelectAll(this)">
</th>
```

This replaces the existing empty `<th style="width:28px;padding:4px;"></th>` that already exists in both the vitro and vivo table headers.

### JS: `clToggleBatchSelectAll(chkEl)`

- Scope: the `<table>` ancestor of `chkEl`
- If checked → set all `.cl-cmp-chk` in that table to checked, call `clToggleCmpCheck` on each
- If unchecked → set all `.cl-cmp-chk` in that table to unchecked, call `clToggleCmpCheck` on each

### Reverse sync

Modify `clToggleCmpCheck` to update the batch select-all checkbox state after each individual toggle:

- All checked → select-all = checked
- None checked → select-all = unchecked
- Some checked → select-all = indeterminate (`chk.indeterminate = true`)

---

## Section 2: Delete Selected Experiments

### Template change

Add `data-exp-id="{{ vc.experiment.id }}"` to every `<tr class="cmp-row">` for both vitro and vivo compound rows.

### JS: `_clCmpSelected` extended

Add `expId` to each entry:

```js
_clCmpSelected.push({ cid, expType, panelId, expId });
```

### Floating bar change

Add a delete button next to the existing "对比曲线" button:

```html
<button class="ds-btn ds-btn-danger" style="font-size:12px;padding:4px 14px;"
        onclick="clDeleteSelected()">
  🗑 删除选中
</button>
```

### JS: `clDeleteSelected()`

```js
function clDeleteSelected() {
  if (!confirm(`确认删除选中的 ${_clCmpSelected.length} 条实验记录？此操作不可撤销。`)) return;
  const expIds = _clCmpSelected.map(s => s.expId);
  fetch('/api/experiments/bulk-delete/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _clCsrfToken() },
    body: JSON.stringify({ exp_ids: expIds }),
  })
    .then(r => r.json().then(data => ({ ok: r.ok, data })))
    .then(({ ok, data }) => {
      if (!ok) { alert(data.error || '删除失败'); return; }
      alert(`已删除 ${data.deleted} 条实验记录`);
      location.reload();
    })
    .catch(() => alert('删除失败，请重试'));
}
```

`_clCsrfToken()` reads from the `csrftoken` cookie (standard Django pattern).

### Backend: `experiments_bulk_delete` view

```python
@login_required
def experiments_bulk_delete(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    allowed = (
        request.user.is_superuser
        or getattr(request.user, 'user_type', '') in ('data_admin', 'admin', 'superadmin')
    )
    if not allowed:
        return JsonResponse({'error': '权限不足'}, status=403)
    data = json.loads(request.body)
    exp_ids = data.get('exp_ids', [])
    count, _ = Experiment.objects.filter(id__in=exp_ids).delete()
    return JsonResponse({'deleted': count})
```

### New URL

```python
path('api/experiments/bulk-delete/', views.experiments_bulk_delete, name='experiments_bulk_delete'),
```

---

## Section 3: Download PNG

### Comparison modal header

Add two download buttons:

```html
<div class="cl-cmp-hdr">
  <span class="cl-cmp-title">化合物曲线对比</span>
  <button class="ds-btn" style="font-size:11px;padding:3px 10px;" onclick="clDownloadCmpPng()">⬇ 图片</button>
  <button class="ds-btn" style="font-size:11px;padding:3px 10px;" onclick="clDownloadCmpCsv()">⬇ CSV</button>
  <button class="cl-cmp-close" onclick="clCloseCmpModal()">✕</button>
</div>
```

### JS: `clDownloadCmpPng()`

- Determine active tab (`vitro` or `vivo`)
- Vitro: get `#cl-cmp-vitro-canvas`
- Vivo: get the visible `.cl-cmp-vivo-pane canvas` (the one in the displayed pane)
- `canvas.toDataURL('image/png')` → create `<a>` with `download` attribute → click
- Filename: `comparison_vitro.png` or `comparison_vivo.png`

---

## Section 4: Download CSV

### JS: `clDownloadCmpCsv()`

```js
function clDownloadCmpCsv() {
  const expIds = _clCmpSelected.map(s => s.expId);
  fetch('/api/experiments/export-csv/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _clCsrfToken() },
    body: JSON.stringify({ exp_ids: expIds }),
  })
    .then(r => r.blob())
    .then(blob => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'compound_export.csv';
      a.click();
      URL.revokeObjectURL(url);
    })
    .catch(() => alert('导出失败，请重试'));
}
```

### Backend: `experiments_export_csv` view

Columns (one row per DataPoint):

```
compound_id, batch_label, exp_type, assay_name, cell_line, date,
ic50_nm, max_kd_pct, x_type, x_value, readout_type, replicate, value
```

```python
@login_required
def experiments_export_csv(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    data = json.loads(request.body)
    exp_ids = data.get('exp_ids', [])
    exps = (
        Experiment.objects
        .filter(id__in=exp_ids)
        .select_related('compound', 'summary')
        .prefetch_related('datapoints')
    )
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="compound_export.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'compound_id', 'batch_label', 'exp_type', 'assay_name',
        'cell_line', 'date', 'ic50_nm', 'max_kd_pct',
        'x_type', 'x_value', 'readout_type', 'replicate', 'value',
    ])
    for exp in exps:
        try:
            ic50 = exp.summary.ic50_nm
            max_kd = exp.summary.max_kd_pct
        except ExperimentSummary.DoesNotExist:
            ic50 = None
            max_kd = None
        for dp in exp.datapoints.all():
            writer.writerow([
                exp.compound_id, exp.batch_label, exp.exp_type,
                exp.assay_name, exp.cell_line, exp.date,
                ic50, max_kd,
                dp.x_type, dp.x_value, dp.readout_type, dp.replicate, dp.value,
            ])
    return response
```

### New URL

```python
path('api/experiments/export-csv/', views.experiments_export_csv, name='experiments_export_csv'),
```

---

## Data Flow Summary

```
Batch list page load
  └─ each <tr class="cmp-row"> has data-exp-id

User checks individual box OR clicks batch select-all
  └─ _clCmpSelected updated with {cid, expType, panelId, expId}
  └─ floating bar shows count + "对比曲线" + "删除选中"

User clicks "删除选中"
  └─ confirm() → POST /api/experiments/bulk-delete/ → reload

User clicks "对比曲线"
  └─ comparison modal opens
  └─ "⬇ 图片" → canvas.toDataURL PNG download
  └─ "⬇ CSV"  → POST /api/experiments/export-csv/ → CSV blob download
```

---

## Files Changed

| File | Change |
|---|---|
| `templates/compound_list.html` | Add `data-exp-id` to rows; add batch select-all checkboxes; add delete button to sticky bar; add download buttons to modal header |
| `static/js/compound_list.js` | Add `clToggleBatchSelectAll`, update `clToggleCmpCheck`, add `clDeleteSelected`, `clDownloadCmpPng`, `clDownloadCmpCsv`, `_clCsrfToken` |
| `app01/views.py` | Add `experiments_bulk_delete`, `experiments_export_csv` views; add `import csv` and `import json` if not present |
| `bprdb/urls.py` | Add two new API paths before the `compounds/<str:compound_id>/` catch-all |

---

## Error Handling

| Condition | Behaviour |
|---|---|
| Non-admin user clicks delete | 403 JSON → JS shows alert |
| Empty exp_ids list | `Experiment.objects.filter(id__in=[]).delete()` returns 0 — alert "已删除 0 条" |
| Network error on delete | JS catch → alert "删除失败，请重试" |
| Network error on CSV export | JS catch → alert "导出失败，请重试" |
| Canvas not initialized when downloading PNG | Button visible only after modal renders charts — canvas always exists |

---

## Out of Scope

- Undo/restore after deletion
- Exporting charts server-side (PNG generated client-side via canvas)
- Bulk operations on the "按化合物" view tab
