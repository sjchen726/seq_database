# Compound List Sub-project B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add batch select-all checkboxes, delete-selected and download (PNG + CSV) actions to the compound list page.

**Architecture:** Backend adds two JSON API endpoints (`/api/experiments/bulk-delete/` and `/api/experiments/export-csv/`); frontend changes are isolated to `compound_list.html` (template) and `compound_list.js` (JS). Compound entry builder functions are extended to expose `exp_ids` so the template can render `data-exp-id` on every row, enabling the JS to identify which experiments to delete/export.

**Tech Stack:** Django 5.1 (function-based views, `JsonResponse`, `HttpResponse` CSV), Chart.js (canvas PNG via `toDataURL`), vanilla JS `fetch`, Django `TestCase`

---

## File Map

| File | Change |
|---|---|
| `app01/views.py` | Add `experiments_bulk_delete`, `experiments_export_csv`; extend `_build_vitro_compound_entry` and `_build_vivo_compound_entry` with `exp_ids` |
| `app01/tests.py` | Add `ExperimentsBulkDeleteTest`, `ExperimentsExportCsvTest` |
| `bprdb/urls.py` | Add two `/api/experiments/` paths |
| `templates/compound_list.html` | Add `data-exp-id` to rows; add select-all checkboxes in table headers; add delete button to sticky bar; add download buttons to modal header |
| `static/js/compound_list.js` | Update `clToggleCmpCheck`; add `clToggleBatchSelectAll`, `_clSyncBatchSelectAll`, `_clCsrfToken`, `clDeleteSelected`, `clDownloadCmpPng`, `clDownloadCmpCsv` |
| `static/css/design-system.css` | Add `.ds-btn-danger` rule |

---

### Task 1: Backend — bulk delete endpoint

**Files:**
- Modify: `app01/views.py` (after line 1473, after `batch_delete`)
- Modify: `bprdb/urls.py`
- Modify: `app01/tests.py`

**Context:** The project already imports `json`, `csv`, `JsonResponse`, `HttpResponse`, `login_required`, `Experiment`, and `DataPoint` at the top of `views.py`. No new imports needed.

- [ ] **Step 1: Write failing tests**

Add this class to the bottom of `app01/tests.py`:

```python
import json as _json_mod


class ExperimentsBulkDeleteTest(TestCase):
    def _make_data(self):
        compound = Compound.objects.create(compound_id='BPR350-TEST01')
        self.exp = Experiment.objects.create(
            compound=compound,
            exp_type='in_vitro',
            assay_name='bulk delete test',
            batch_label='2099-01',
        )
        DataPoint.objects.create(
            experiment=self.exp,
            x_value=10.0, x_type='concentration',
            replicate='A', value=0.5, readout_type='mRNA_remaining',
        )
        return compound

    def test_guest_forbidden(self):
        self._make_data()
        LmsUser.objects.create_user(username='bdt_g1', password='pass', user_type='guest')
        self.client.login(username='bdt_g1', password='pass')
        r = self.client.post(
            '/api/experiments/bulk-delete/',
            data=_json_mod.dumps({'exp_ids': [self.exp.id]}),
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Experiment.objects.filter(id=self.exp.id).count(), 1)

    def test_data_admin_can_delete(self):
        self._make_data()
        LmsUser.objects.create_user(username='bdt_da1', password='pass', user_type='data_admin')
        self.client.login(username='bdt_da1', password='pass')
        r = self.client.post(
            '/api/experiments/bulk-delete/',
            data=_json_mod.dumps({'exp_ids': [self.exp.id]}),
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['deleted'], 1)
        self.assertFalse(Experiment.objects.filter(id=self.exp.id).exists())

    def test_datapoints_cascade(self):
        self._make_data()
        LmsUser.objects.create_user(username='bdt_da2', password='pass', user_type='data_admin')
        self.client.login(username='bdt_da2', password='pass')
        self.client.post(
            '/api/experiments/bulk-delete/',
            data=_json_mod.dumps({'exp_ids': [self.exp.id]}),
            content_type='application/json',
        )
        self.assertEqual(DataPoint.objects.filter(experiment=self.exp.id).count(), 0)

    def test_get_not_allowed(self):
        LmsUser.objects.create_user(username='bdt_da3', password='pass', user_type='data_admin')
        self.client.login(username='bdt_da3', password='pass')
        r = self.client.get('/api/experiments/bulk-delete/')
        self.assertEqual(r.status_code, 405)
```

- [ ] **Step 2: Run tests — verify they all fail**

```bash
source venv/bin/activate
python manage.py test app01.tests.ExperimentsBulkDeleteTest --noinput
```

Expected: `FAIL` / `ERROR` — URL does not exist (404) or view not defined.

- [ ] **Step 3: Add the `experiments_bulk_delete` view**

In `app01/views.py`, after the closing of `batch_delete` (around line 1473), insert:

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

- [ ] **Step 4: Add URL**

In `bprdb/urls.py`, add this line inside `urlpatterns` (before the closing `]`):

```python
path('api/experiments/bulk-delete/', views.experiments_bulk_delete, name='experiments_bulk_delete'),
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
python manage.py test app01.tests.ExperimentsBulkDeleteTest --noinput
```

Expected: `OK` (4 tests).

- [ ] **Step 6: Commit**

```bash
git add app01/views.py app01/tests.py bprdb/urls.py
git commit -m "feat: add experiments_bulk_delete API endpoint"
```

---

### Task 2: Backend — CSV export endpoint

**Files:**
- Modify: `app01/views.py` (after `experiments_bulk_delete`)
- Modify: `bprdb/urls.py`
- Modify: `app01/tests.py`

- [ ] **Step 1: Write failing tests**

Add this class to the bottom of `app01/tests.py`:

```python
class ExperimentsExportCsvTest(TestCase):
    def _make_data(self):
        compound = Compound.objects.create(compound_id='BPR350-TEST02')
        self.exp = Experiment.objects.create(
            compound=compound,
            exp_type='in_vitro',
            assay_name='export test assay',
            cell_line='Hepa1-6',
            batch_label='2099-02',
        )
        DataPoint.objects.create(
            experiment=self.exp,
            x_value=10.0, x_type='concentration',
            replicate='Mean', value=0.4, readout_type='mRNA_remaining',
        )
        LmsUser.objects.create_user(username='csv_u1', password='pass', user_type='admin')

    def test_returns_csv_content_type(self):
        self._make_data()
        self.client.login(username='csv_u1', password='pass')
        r = self.client.post(
            '/api/experiments/export-csv/',
            data=_json_mod.dumps({'exp_ids': [self.exp.id]}),
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn('text/csv', r.get('Content-Type', ''))

    def test_csv_header_row(self):
        self._make_data()
        self.client.login(username='csv_u1', password='pass')
        r = self.client.post(
            '/api/experiments/export-csv/',
            data=_json_mod.dumps({'exp_ids': [self.exp.id]}),
            content_type='application/json',
        )
        content = r.content.decode('utf-8-sig')
        self.assertIn('compound_id', content)
        self.assertIn('batch_label', content)
        self.assertIn('ic50_nm', content)

    def test_csv_data_row(self):
        self._make_data()
        self.client.login(username='csv_u1', password='pass')
        r = self.client.post(
            '/api/experiments/export-csv/',
            data=_json_mod.dumps({'exp_ids': [self.exp.id]}),
            content_type='application/json',
        )
        content = r.content.decode('utf-8-sig')
        self.assertIn('BPR350-TEST02', content)
        self.assertIn('2099-02', content)

    def test_get_not_allowed(self):
        LmsUser.objects.create_user(username='csv_u2', password='pass', user_type='admin')
        self.client.login(username='csv_u2', password='pass')
        r = self.client.get('/api/experiments/export-csv/')
        self.assertEqual(r.status_code, 405)
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
python manage.py test app01.tests.ExperimentsExportCsvTest --noinput
```

Expected: `FAIL` / `ERROR`.

- [ ] **Step 3: Add the `experiments_export_csv` view**

In `app01/views.py`, right after `experiments_bulk_delete`, insert:

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

- [ ] **Step 4: Add URL**

In `bprdb/urls.py`, add inside `urlpatterns`:

```python
path('api/experiments/export-csv/', views.experiments_export_csv, name='experiments_export_csv'),
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
python manage.py test app01.tests.ExperimentsExportCsvTest --noinput
```

Expected: `OK` (4 tests).

- [ ] **Step 6: Commit**

```bash
git add app01/views.py app01/tests.py bprdb/urls.py
git commit -m "feat: add experiments_export_csv API endpoint"
```

---

### Task 3: Expose `exp_ids` in compound entry builders + template `data-exp-id`

**Files:**
- Modify: `app01/views.py` (lines ~868, ~908)
- Modify: `templates/compound_list.html` (lines ~113, ~217)

**Context:** `_build_vitro_compound_entry` (line 853) returns a dict — currently only `'experiment': exp` is present (no list of all IDs). `_build_vivo_compound_entry` (line 883) doesn't have an `'experiment'` key at all. Both need `'exp_ids'` so the template can write `data-exp-id` for the JS delete/CSV logic.

- [ ] **Step 1: Add `exp_ids` to `_build_vitro_compound_entry`**

In `app01/views.py`, find the `return { ... }` block in `_build_vitro_compound_entry` (around line 868). Add `'exp_ids': [e.id for e in vitro_exps],` as the second key:

```python
    return {
        'compound': compound,
        'experiment': exp,
        'exp_ids': [e.id for e in vitro_exps],
        'ic50_str': f"{summary.ic50_nm:.2f}" if summary and summary.ic50_nm is not None else '',
        'ic50_nm': summary.ic50_nm if summary else None,
        'max_kd_pct': summary.max_kd_pct if summary else None,
        'vitro_rows': rows,
        'mrna_pts': mrna_pts,
        'kd_pts': kd_pts,
        'as_seq': seqs.get('AS', ''),
        'ss_seq': seqs.get('SS', ''),
        'attachments': list(exp.attachments.all()),
    }
```

- [ ] **Step 2: Add `exp_ids` to `_build_vivo_compound_entry`**

In `app01/views.py`, find the `return { ... }` block in `_build_vivo_compound_entry` (around line 908). Add `'exp_ids': [e.id for e in vivo_exps],` after `'compound': compound,`:

```python
    return {
        'compound': compound,
        'exp_ids': [e.id for e in vivo_exps],
        'readout_data': readout_data,
        'readouts': readouts,
        'summary': summary,
        'dose_groups': dose_groups,
        'as_seq': seqs.get('AS', ''),
        'ss_seq': seqs.get('SS', ''),
        'attachments': all_attachments,
    }
```

- [ ] **Step 3: Add `data-exp-id` to the vitro compound row in template**

In `templates/compound_list.html`, find the vitro `<tr class="cmp-row">` (around line 113). Add `data-exp-id="{{ vc.exp_ids|join:',' }}"`:

Old:
```html
    <tr class="cmp-row" id="{{ vrid }}" data-cid="{{ vc.compound.compound_id }}" data-exp-type="vitro" data-panel-id="{{ vpid }}" onclick="clToggleRow('{{ vrid }}','{{ vpid }}')">
```

New:
```html
    <tr class="cmp-row" id="{{ vrid }}" data-cid="{{ vc.compound.compound_id }}" data-exp-type="vitro" data-panel-id="{{ vpid }}" data-exp-id="{{ vc.exp_ids|join:',' }}" onclick="clToggleRow('{{ vrid }}','{{ vpid }}')">
```

- [ ] **Step 4: Add `data-exp-id` to the vivo compound row in template**

In `templates/compound_list.html`, find the vivo `<tr class="cmp-row">` (around line 217). Add `data-exp-id="{{ vc.exp_ids|join:',' }}"`:

Old:
```html
    <tr class="cmp-row" id="{{ irid }}" data-cid="{{ vc.compound.compound_id }}" data-exp-type="vivo" data-panel-id="{{ ipid }}" onclick="clToggleRow('{{ irid }}','{{ ipid }}')">
```

New:
```html
    <tr class="cmp-row" id="{{ irid }}" data-cid="{{ vc.compound.compound_id }}" data-exp-type="vivo" data-panel-id="{{ ipid }}" data-exp-id="{{ vc.exp_ids|join:',' }}" onclick="clToggleRow('{{ irid }}','{{ ipid }}')">
```

- [ ] **Step 5: Update `clToggleCmpCheck` in JS and add `_clSyncBatchSelectAll`**

In `static/js/compound_list.js`, replace the existing `clToggleCmpCheck` function (lines 233–245):

Old:
```js
function clToggleCmpCheck(chk) {
  const row = chk.closest('tr.cmp-row');
  const {cid, expType, panelId} = row.dataset;
  row.classList.toggle('cmp-selected', chk.checked);
  if (chk.checked) {
    if (!_clCmpSelected.find(s => s.panelId === panelId))
      _clCmpSelected.push({cid, expType, panelId});
  } else {
    const idx = _clCmpSelected.findIndex(s => s.panelId === panelId);
    if (idx >= 0) _clCmpSelected.splice(idx, 1);
  }
  _clUpdateCmpBar();
}
```

New:
```js
function clToggleCmpCheck(chk) {
  const row = chk.closest('tr.cmp-row');
  const {cid, expType, panelId, expId} = row.dataset;
  const expIds = expId ? expId.split(',').map(Number).filter(n => n > 0) : [];
  row.classList.toggle('cmp-selected', chk.checked);
  if (chk.checked) {
    if (!_clCmpSelected.find(s => s.panelId === panelId))
      _clCmpSelected.push({cid, expType, panelId, expIds});
  } else {
    const idx = _clCmpSelected.findIndex(s => s.panelId === panelId);
    if (idx >= 0) _clCmpSelected.splice(idx, 1);
  }
  _clUpdateCmpBar();
  _clSyncBatchSelectAll(row);
}
```

Also append `_clSyncBatchSelectAll` at the **end** of `static/js/compound_list.js` (Task 4 will add `clToggleBatchSelectAll` which calls this; defining it here keeps Task 3 self-contained):

```js
function _clSyncBatchSelectAll(row) {
  const table = row.closest('table');
  if (!table) return;
  const selectAll = table.querySelector('.cl-batch-select-all');
  if (!selectAll) return;
  const all = [...table.querySelectorAll('.cl-cmp-chk')];
  const checkedCount = all.filter(c => c.checked).length;
  if (checkedCount === 0) {
    selectAll.checked = false;
    selectAll.indeterminate = false;
  } else if (checkedCount === all.length) {
    selectAll.checked = true;
    selectAll.indeterminate = false;
  } else {
    selectAll.checked = false;
    selectAll.indeterminate = true;
  }
}
```

- [ ] **Step 6: Verify manually**

```bash
python manage.py runserver
```

Open `/compounds/`, inspect a vitro compound row in DevTools — confirm `data-exp-id` attribute is present and contains a number. Confirm vivo rows also have it.

- [ ] **Step 7: Commit**

```bash
git add app01/views.py templates/compound_list.html static/js/compound_list.js
git commit -m "feat: expose exp_ids on compound rows for delete/export"
```

---

### Task 4: Batch select-all checkboxes

**Files:**
- Modify: `templates/compound_list.html` (lines ~101, ~204)
- Modify: `static/js/compound_list.js`

- [ ] **Step 1: Replace empty `<th>` in the vitro table header**

In `templates/compound_list.html`, find the vitro table's first `<th>` (around line 101):

Old:
```html
      <th style="width:28px;padding:4px;"></th>
      <th style="width:110px">ID</th>
      <th style="width:380px">序列 (AS / SS)</th>
```

New:
```html
      <th style="width:28px;padding:4px;"><input type="checkbox" class="cl-batch-select-all" onchange="clToggleBatchSelectAll(this)" title="全选本批"></th>
      <th style="width:110px">ID</th>
      <th style="width:380px">序列 (AS / SS)</th>
```

- [ ] **Step 2: Replace empty `<th>` in the vivo table header**

In `templates/compound_list.html`, find the vivo table's first `<th>` (around line 204):

Old:
```html
      <th style="width:28px;padding:4px;"></th>
      <th style="width:110px">ID</th>
      <th style="width:360px">序列 (AS)</th>
```

New:
```html
      <th style="width:28px;padding:4px;"><input type="checkbox" class="cl-batch-select-all" onchange="clToggleBatchSelectAll(this)" title="全选本批"></th>
      <th style="width:110px">ID</th>
      <th style="width:360px">序列 (AS)</th>
```

- [ ] **Step 3: Add `clToggleBatchSelectAll` to JS**

At the **end** of `static/js/compound_list.js`, append (`_clSyncBatchSelectAll` was already added in Task 3):

```js
// ── Batch select-all header checkbox ─────────────────────────
function clToggleBatchSelectAll(chkEl) {
  const table = chkEl.closest('table');
  if (!table) return;
  table.querySelectorAll('.cl-cmp-chk').forEach(chk => {
    if (chk.checked !== chkEl.checked) {
      chk.checked = chkEl.checked;
      clToggleCmpCheck(chk);
    }
  });
}
```

- [ ] **Step 4: Verify manually**

Open `/compounds/`. A batch with multiple compounds should show a checkbox in the table header. Clicking it should select/deselect all rows in that table. Manually checking one row should set the header checkbox to indeterminate.

- [ ] **Step 5: Commit**

```bash
git add templates/compound_list.html static/js/compound_list.js
git commit -m "feat: add per-batch select-all checkbox to compound list"
```

---

### Task 5: Delete button + CSS + JS

**Files:**
- Modify: `static/css/design-system.css`
- Modify: `templates/compound_list.html` (lines ~349–353)
- Modify: `static/js/compound_list.js`

- [ ] **Step 1: Add `.ds-btn-danger` CSS rule**

In `static/css/design-system.css`, after the `.ds-btn-green:hover` rule (around line 205), insert:

```css
.ds-btn-danger {
  background: #dc2626; color: #fff; font-weight: 600;
  box-shadow: 0 2px 8px rgba(220,38,38,0.28);
}
.ds-btn-danger:hover { background: #b91c1c; color: #fff; text-decoration: none; }
```

- [ ] **Step 2: Add delete button to the sticky floating bar**

In `templates/compound_list.html`, find the `cl-cmp-bar` div (around lines 349–353):

Old:
```html
<div id="cl-cmp-bar" class="cl-cmp-bar" style="display:none">
  <span id="cl-cmp-count" class="cl-cmp-count-label"></span>
  <button class="ds-btn ds-btn-primary" style="font-size:12px;padding:4px 16px;" onclick="clOpenCmpModal()">对比曲线</button>
  <button class="cl-cmp-clear-btn" onclick="clClearCmpSelection()">✕ 清除</button>
</div>
```

New:
```html
<div id="cl-cmp-bar" class="cl-cmp-bar" style="display:none">
  <span id="cl-cmp-count" class="cl-cmp-count-label"></span>
  <button class="ds-btn ds-btn-primary" style="font-size:12px;padding:4px 16px;" onclick="clOpenCmpModal()">对比曲线</button>
  <button class="ds-btn ds-btn-danger" style="font-size:12px;padding:4px 14px;" onclick="clDeleteSelected()">🗑 删除选中</button>
  <button class="cl-cmp-clear-btn" onclick="clClearCmpSelection()">✕ 清除</button>
</div>
```

- [ ] **Step 3: Add `_clCsrfToken` and `clDeleteSelected` to JS**

At the **end** of `static/js/compound_list.js`, append:

```js
// ── CSRF helper ───────────────────────────────────────────────
function _clCsrfToken() {
  const m = document.cookie.match(/csrftoken=([^;]+)/);
  return m ? m[1] : '';
}

// ── Delete selected experiments ───────────────────────────────
function clDeleteSelected() {
  if (!confirm(`确认删除选中的 ${_clCmpSelected.length} 条实验记录？此操作不可撤销。`)) return;
  const expIds = _clCmpSelected.flatMap(s => s.expIds);
  fetch('/api/experiments/bulk-delete/', {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': _clCsrfToken()},
    body: JSON.stringify({exp_ids: expIds}),
  })
    .then(r => r.json().then(data => ({ok: r.ok, data})))
    .then(({ok, data}) => {
      if (!ok) { alert(data.error || '删除失败'); return; }
      alert(`已删除 ${data.deleted} 条实验记录`);
      location.reload();
    })
    .catch(() => alert('删除失败，请重试'));
}
```

- [ ] **Step 4: Verify manually**

Open `/compounds/`. Select 1–2 compounds. Confirm a red "🗑 删除选中" button appears in the floating bar. Click it — confirm the confirm dialog appears. Cancel — nothing should happen. Confirm — experiments should be deleted and page reloads.

To test the 403 path: log in as a `guest` user and try deleting. The alert should say "权限不足".

- [ ] **Step 5: Commit**

```bash
git add static/css/design-system.css templates/compound_list.html static/js/compound_list.js
git commit -m "feat: add delete-selected button to compound list floating bar"
```

---

### Task 6: Download PNG + CSV buttons in comparison modal

**Files:**
- Modify: `templates/compound_list.html` (lines ~358–361)
- Modify: `static/js/compound_list.js`

- [ ] **Step 1: Add download buttons to modal header**

In `templates/compound_list.html`, find the `cl-cmp-hdr` div inside `cl-cmp-modal` (around lines 358–361):

Old:
```html
  <div class="cl-cmp-hdr">
    <span class="cl-cmp-title">化合物曲线对比</span>
    <button class="cl-cmp-close" onclick="clCloseCmpModal()">✕</button>
  </div>
```

New:
```html
  <div class="cl-cmp-hdr">
    <span class="cl-cmp-title">化合物曲线对比</span>
    <button class="ds-btn ds-btn-ghost" style="font-size:11px;padding:3px 10px;" onclick="clDownloadCmpPng()">⬇ 图片</button>
    <button class="ds-btn ds-btn-ghost" style="font-size:11px;padding:3px 10px;" onclick="clDownloadCmpCsv()">⬇ CSV</button>
    <button class="cl-cmp-close" onclick="clCloseCmpModal()">✕</button>
  </div>
```

- [ ] **Step 2: Add `clDownloadCmpPng` and `clDownloadCmpCsv` to JS**

At the **end** of `static/js/compound_list.js`, append:

```js
// ── Download comparison chart as PNG ─────────────────────────
function clDownloadCmpPng() {
  const isVitro = document.getElementById('cl-cmp-tab-vitro').classList.contains('active');
  let canvas;
  if (isVitro) {
    canvas = document.getElementById('cl-cmp-vitro-canvas');
  } else {
    const panes = document.querySelectorAll('#cl-cmp-vivo-charts .cl-cmp-vivo-pane');
    for (const p of panes) {
      if (p.style.display !== 'none') { canvas = p.querySelector('canvas'); break; }
    }
  }
  if (!canvas) return;
  const a = document.createElement('a');
  a.download = isVitro ? 'comparison_vitro.png' : 'comparison_vivo.png';
  a.href = canvas.toDataURL('image/png');
  a.click();
}

// ── Download selected experiments as CSV ─────────────────────
function clDownloadCmpCsv() {
  const expIds = _clCmpSelected.flatMap(s => s.expIds);
  fetch('/api/experiments/export-csv/', {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': _clCsrfToken()},
    body: JSON.stringify({exp_ids: expIds}),
  })
    .then(r => {
      if (!r.ok) throw new Error('export failed');
      return r.blob();
    })
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

- [ ] **Step 3: Verify manually**

Open `/compounds/`. Select 2+ compounds. Open "对比曲线" modal.

- Click "⬇ 图片" — browser should download `comparison_vitro.png` (or `comparison_vivo.png` if on the vivo tab).
- Click "⬇ CSV" — browser should download `compound_export.csv`. Open it — confirm it has a header row and data rows with compound IDs.

- [ ] **Step 4: Run all tests one final time**

```bash
python manage.py test app01 --noinput
```

Expected: existing pre-passing tests still pass, new tests all pass. Note: two pre-existing failures are known (`CompoundListViewTest.test_compound_data_in_context`, `ParseBodyWeightFileTest.test_time_unit_unknown_positive_only`) — these are not regressions.

- [ ] **Step 5: Commit**

```bash
git add templates/compound_list.html static/js/compound_list.js
git commit -m "feat: add PNG and CSV download buttons to comparison modal"
```
