# Edit Modal — Implementation Plan (Spec 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `clEditRow` "即将上线" stub with a real edit modal that lets authorised users update compound metadata and experiment metadata via two new PATCH API endpoints.

**Architecture:** Two thin Django view functions (`api_compound_detail`, `api_experiment_detail`) wired to `/api/compounds/<id>/` and `/api/experiments/<id>/`; the modal is pure HTML/CSS/JS inside `compound_list.html`/`compound_list.css`/`compound_list.js` — no new files needed. Both endpoints share the same `can_delete` permission check already used by the row delete button.

**Tech Stack:** Django 5.1 (function-based views, `JsonResponse`, `get_object_or_404`), vanilla JS (`async/await`, `fetch`), CSS custom properties.

---

## File Map

| File | Change |
|------|--------|
| `app01/tests.py` | Add `import json`; add `CompoundApiTest` class (7 tests) after line 763 |
| `app01/views.py` | Add `api_compound_detail` + `api_experiment_detail` after line 1634 (after `experiments_export_csv`) |
| `bprdb/urls.py` | Add 2 URL patterns after line 29 |
| `static/css/compound_list.css` | Append edit modal CSS |
| `templates/compound_list.html` | Update `clEditRow(...)` calls on lines 130 + 250; add modal HTML before `{% endblock %}` at line 409 |
| `static/js/compound_list.js` | Replace stub `clEditRow` (lines 631–633) with state vars + full implementation; add `clSaveEdit` + `clCloseEditModal` |

No migrations required (all model fields already exist).

---

### Task 1: Backend — both API views + URL registration + tests

**Files:**
- Modify: `app01/tests.py` (line 1 for import; after line 763 for new class)
- Modify: `app01/views.py` (after line 1634)
- Modify: `bprdb/urls.py` (after line 29)

- [ ] **Step 1: Add `import json` to tests.py**

Open `app01/tests.py`. The first line is `from django.test import TestCase`. Add `import json` as the second import line so the file begins:

```python
from django.test import TestCase
import json
from django.core.management import call_command
```

- [ ] **Step 2: Write the 7 failing tests**

In `app01/tests.py`, find the closing line of `CompoundListViewTest` (around line 763):

```python
    def test_can_delete_false_for_regular_user(self):
        self.user.user_type = 'user'
        self.user.module_permissions = ''
        self.user.is_superuser = False
        self.user.save()
        resp = self.client.get('/compounds/')
        self.assertFalse(resp.context['can_delete'])
```

After that closing block (before the `# ---- CompoundDetailViewTest ----` comment) add:

```python

# ---- CompoundApiTest ----
class CompoundApiTest(TestCase):
    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='apitest', password='pass', user_type='superadmin',
        )
        self.client.login(username='apitest', password='pass')
        self.compound = Compound.objects.create(
            compound_id='BPR_APITEST01', project='API', target='TS',
            target_name='FASN', transcript_ref='NM_004104', remarks='initial remark',
        )
        self.exp_vitro = Experiment.objects.create(
            compound=self.compound,
            exp_type='in_vitro',
            assay_name='lipid_assay',
            batch_label='B20260629',
            cell_line='HepG2',
            notes='vitro notes',
        )
        self.exp_vivo = Experiment.objects.create(
            compound=self.compound,
            exp_type='in_vivo',
            assay_name='mouse_assay',
            batch_label='M20260629',
            animal_species='mouse',
            animal_strain='C57BL/6',
            route='IV',
            gender='M',
            time_unit='day',
            dose_info='3 mg/kg',
            schedule='QW',
        )

    # ── Compound endpoint ──────────────────────────────────────
    def test_get_compound_returns_fields(self):
        resp = self.client.get('/api/compounds/BPR_APITEST01/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['target_name'], 'FASN')
        self.assertEqual(data['transcript_ref'], 'NM_004104')
        self.assertEqual(data['remarks'], 'initial remark')

    def test_patch_compound_updates_fields(self):
        resp = self.client.patch(
            '/api/compounds/BPR_APITEST01/',
            data=json.dumps({'target_name': 'NEW_TARGET', 'remarks': 'updated'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['ok'])
        self.compound.refresh_from_db()
        self.assertEqual(self.compound.target_name, 'NEW_TARGET')
        self.assertEqual(self.compound.remarks, 'updated')

    def test_compound_api_requires_data_permission(self):
        other = LmsUser.objects.create_user(
            username='noperm', password='pass', user_type='user',
        )
        self.client.logout()
        self.client.login(username='noperm', password='pass')
        resp = self.client.get('/api/compounds/BPR_APITEST01/')
        self.assertEqual(resp.status_code, 403)

    # ── Experiment endpoint ────────────────────────────────────
    def test_get_experiment_returns_fields(self):
        resp = self.client.get(f'/api/experiments/{self.exp_vitro.pk}/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['exp_type'], 'in_vitro')
        self.assertEqual(data['assay_name'], 'lipid_assay')
        self.assertEqual(data['cell_line'], 'HepG2')

    def test_patch_experiment_vitro_updates_cell_line(self):
        resp = self.client.patch(
            f'/api/experiments/{self.exp_vitro.pk}/',
            data=json.dumps({'assay_name': 'updated_assay', 'cell_line': 'Hela'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['ok'])
        self.exp_vitro.refresh_from_db()
        self.assertEqual(self.exp_vitro.assay_name, 'updated_assay')
        self.assertEqual(self.exp_vitro.cell_line, 'Hela')

    def test_patch_experiment_vivo_updates_animal_fields(self):
        resp = self.client.patch(
            f'/api/experiments/{self.exp_vivo.pk}/',
            data=json.dumps({'animal_species': 'rat', 'route': 'SC'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.exp_vivo.refresh_from_db()
        self.assertEqual(self.exp_vivo.animal_species, 'rat')
        self.assertEqual(self.exp_vivo.route, 'SC')

    def test_experiment_api_requires_data_permission(self):
        other = LmsUser.objects.create_user(
            username='noperm2', password='pass', user_type='user',
        )
        self.client.logout()
        self.client.login(username='noperm2', password='pass')
        resp = self.client.get(f'/api/experiments/{self.exp_vitro.pk}/')
        self.assertEqual(resp.status_code, 403)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
source venv/bin/activate
python manage.py test app01.tests.CompoundApiTest --keepdb -v 1
```

Expected: all 7 FAIL with 404 (URL not yet registered).

- [ ] **Step 4: Add `api_compound_detail` to `app01/views.py`**

In `app01/views.py`, find this line (around line 1634):

```python
    return response


def _read_from_storage(path: str):
```

Insert the two new views between `return response` and `def _read_from_storage`:

```python
    return response


@login_required
def api_compound_detail(request, compound_id):
    if not (request.user.is_superuser
            or request.user.user_type == 'superadmin'
            or _has_module(request.user, 'data')):
        return JsonResponse({'error': '权限不足'}, status=403)
    compound = get_object_or_404(Compound, pk=compound_id)
    if request.method == 'GET':
        return JsonResponse({
            'target_name':    compound.target_name,
            'transcript_ref': compound.transcript_ref,
            'remarks':        compound.remarks,
        })
    if request.method == 'PATCH':
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({'error': 'invalid JSON'}, status=400)
        allowed = {'target_name', 'transcript_ref', 'remarks'}
        fields = list(set(data.keys()) & allowed)
        for f in fields:
            setattr(compound, f, data[f])
        if fields:
            compound.save(update_fields=fields)
        return JsonResponse({'ok': True})
    return JsonResponse({'error': 'method not allowed'}, status=405)


@login_required
def api_experiment_detail(request, exp_id):
    if not (request.user.is_superuser
            or request.user.user_type == 'superadmin'
            or _has_module(request.user, 'data')):
        return JsonResponse({'error': '权限不足'}, status=403)
    exp = get_object_or_404(Experiment, pk=exp_id)
    if request.method == 'GET':
        return JsonResponse({
            'exp_type':       exp.exp_type,
            'assay_name':     exp.assay_name,
            'batch_label':    exp.batch_label,
            'cell_line':      exp.cell_line,
            'notes':          exp.notes,
            'date':           exp.date.isoformat() if exp.date else '',
            'animal_species': exp.animal_species,
            'animal_strain':  exp.animal_strain,
            'route':          exp.route,
            'gender':         exp.gender,
            'time_unit':      exp.time_unit,
            'dose_info':      exp.dose_info,
            'schedule':       exp.schedule,
        })
    if request.method == 'PATCH':
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({'error': 'invalid JSON'}, status=400)
        allowed = {
            'assay_name', 'batch_label', 'cell_line', 'notes',
            'animal_species', 'animal_strain', 'route', 'gender',
            'time_unit', 'dose_info', 'schedule',
        }
        fields = list(set(data.keys()) & allowed)
        for f in fields:
            setattr(exp, f, data[f])
        if 'date' in data:
            exp.date = data['date'] if data['date'] else None
            fields.append('date')
        if fields:
            exp.save(update_fields=fields)
        return JsonResponse({'ok': True})
    return JsonResponse({'error': 'method not allowed'}, status=405)


def _read_from_storage(path: str):
```

- [ ] **Step 5: Register URLs in `bprdb/urls.py`**

In `bprdb/urls.py`, find line 29:

```python
    path('api/experiments/export-csv/', views.experiments_export_csv, name='experiments_export_csv'),
```

Add two lines immediately after:

```python
    path('api/experiments/export-csv/', views.experiments_export_csv, name='experiments_export_csv'),
    path('api/compounds/<str:compound_id>/', views.api_compound_detail, name='api_compound_detail'),
    path('api/experiments/<int:exp_id>/', views.api_experiment_detail, name='api_experiment_detail'),
```

- [ ] **Step 6: Run the 7 new tests to verify they pass**

```bash
source venv/bin/activate
python manage.py test app01.tests.CompoundApiTest --keepdb -v 1
```

Expected: all 7 PASS.

- [ ] **Step 7: Run full test suite**

```bash
python manage.py test app01 --keepdb -v 1
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add app01/tests.py app01/views.py bprdb/urls.py
git commit -m "feat: add api_compound_detail and api_experiment_detail views with tests"
```

---

### Task 2: CSS — edit modal styles

**Files:**
- Modify: `static/css/compound_list.css` (append at end)

- [ ] **Step 1: Append edit modal CSS**

Open `static/css/compound_list.css` and append at the very end:

```css
/* ── Edit modal ── */
.cl-edit-modal {
  position: fixed;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  z-index: 1010;
  background: white;
  border-radius: 10px;
  box-shadow: 0 8px 32px rgba(0,0,0,.18);
  width: 480px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.cl-edit-hdr {
  display: flex;
  align-items: center;
  padding: 14px 18px;
  border-bottom: 1px solid #e2e8f0;
  flex-shrink: 0;
}
.cl-edit-title {
  font-weight: 600;
  font-size: 14px;
  color: #1e293b;
  flex: 1;
}
.cl-edit-body {
  overflow-y: auto;
  padding: 16px 18px;
  flex: 1;
}
.cl-edit-section { margin-bottom: 20px; }
.cl-edit-section-hd {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .05em;
  color: #94a3b8;
  margin-bottom: 10px;
  padding-bottom: 4px;
  border-bottom: 1px solid #f1f5f9;
}
.cl-edit-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 8px;
}
.cl-edit-lbl {
  width: 90px;
  flex-shrink: 0;
  font-size: 12px;
  color: #475569;
  padding-top: 6px;
  text-align: right;
}
.cl-edit-inp {
  flex: 1;
  border: 1px solid #e2e8f0;
  border-radius: 5px;
  padding: 5px 8px;
  font-size: 13px;
  color: #1e293b;
  background: white;
  outline: none;
  transition: border-color 0.15s;
}
.cl-edit-inp:focus { border-color: #3b82f6; }
textarea.cl-edit-inp { resize: vertical; min-height: 52px; }
.cl-edit-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 18px;
  border-top: 1px solid #e2e8f0;
  flex-shrink: 0;
}
```

- [ ] **Step 2: Commit**

```bash
git add static/css/compound_list.css
git commit -m "feat: add edit modal CSS to compound_list.css"
```

---

### Task 3: Template — update edit button `onclick` + add modal HTML

**Files:**
- Modify: `templates/compound_list.html` (lines 130, 250, and before line 409)

- [ ] **Step 1: Update vitro edit button (line 130)**

Find this exact line (around line 130):

```html
                onclick="clEditRow('{{ vc.compound.compound_id }}')"
```

That appears inside the vitro table row (between `<button class="cl-icon-btn cl-icon-edit"` and `title="编辑">`). Replace with:

```html
                onclick="clEditRow('{{ vc.compound.compound_id }}', {{ vc.exp_ids.0 }})"
```

- [ ] **Step 2: Update vivo edit button (line 250)**

Find the identical line in the vivo table section (around line 250):

```html
                onclick="clEditRow('{{ vc.compound.compound_id }}')"
```

Replace with:

```html
                onclick="clEditRow('{{ vc.compound.compound_id }}', {{ vc.exp_ids.0 }})"
```

- [ ] **Step 3: Add modal HTML before `{% endblock %}`**

Find the block ending (around line 407–409):

```html
</div>

{% endblock %}
```

That `</div>` closes the comparison modal (`cl-cmp-modal`). Insert the edit modal HTML between the `</div>` and `{% endblock %}`:

```html
</div>

{# ── Edit modal ── #}
<div id="cl-edit-overlay" class="cl-cmp-overlay" onclick="clCloseEditModal()" style="display:none"></div>
<div id="cl-edit-modal" class="cl-edit-modal" style="display:none">
  <div class="cl-edit-hdr">
    <span class="cl-edit-title" id="cl-edit-title">编辑</span>
    <button class="cl-cmp-close" onclick="clCloseEditModal()">✕</button>
  </div>
  <div class="cl-edit-body">

    <div class="cl-edit-section">
      <div class="cl-edit-section-hd">化合物信息</div>
      <div class="cl-edit-row">
        <label class="cl-edit-lbl">靶点名称</label>
        <input class="cl-edit-inp" type="text" id="cl-edit-target-name">
      </div>
      <div class="cl-edit-row">
        <label class="cl-edit-lbl">转录本参考</label>
        <input class="cl-edit-inp" type="text" id="cl-edit-transcript-ref">
      </div>
      <div class="cl-edit-row">
        <label class="cl-edit-lbl">备注</label>
        <textarea class="cl-edit-inp" id="cl-edit-remarks" rows="2"></textarea>
      </div>
    </div>

    <div class="cl-edit-section">
      <div class="cl-edit-section-hd">实验信息</div>
      <div class="cl-edit-row">
        <label class="cl-edit-lbl">测定方法</label>
        <input class="cl-edit-inp" type="text" id="cl-edit-assay-name">
      </div>
      <div class="cl-edit-row">
        <label class="cl-edit-lbl">批次号</label>
        <input class="cl-edit-inp" type="text" id="cl-edit-batch-label">
      </div>

      <div id="cl-edit-vitro-fields">
        <div class="cl-edit-row">
          <label class="cl-edit-lbl">细胞系</label>
          <input class="cl-edit-inp" type="text" id="cl-edit-cell-line">
        </div>
      </div>

      <div id="cl-edit-vivo-fields" style="display:none">
        <div class="cl-edit-row">
          <label class="cl-edit-lbl">动物种类</label>
          <input class="cl-edit-inp" type="text" id="cl-edit-animal-species">
        </div>
        <div class="cl-edit-row">
          <label class="cl-edit-lbl">动物品系</label>
          <input class="cl-edit-inp" type="text" id="cl-edit-animal-strain">
        </div>
        <div class="cl-edit-row">
          <label class="cl-edit-lbl">给药途径</label>
          <input class="cl-edit-inp" type="text" id="cl-edit-route">
        </div>
        <div class="cl-edit-row">
          <label class="cl-edit-lbl">性别</label>
          <input class="cl-edit-inp" type="text" id="cl-edit-gender">
        </div>
        <div class="cl-edit-row">
          <label class="cl-edit-lbl">时间单位</label>
          <input class="cl-edit-inp" type="text" id="cl-edit-time-unit">
        </div>
        <div class="cl-edit-row">
          <label class="cl-edit-lbl">剂量信息</label>
          <input class="cl-edit-inp" type="text" id="cl-edit-dose-info">
        </div>
        <div class="cl-edit-row">
          <label class="cl-edit-lbl">给药方案</label>
          <input class="cl-edit-inp" type="text" id="cl-edit-schedule">
        </div>
      </div>

      <div class="cl-edit-row">
        <label class="cl-edit-lbl">实验备注</label>
        <textarea class="cl-edit-inp" id="cl-edit-notes" rows="2"></textarea>
      </div>
      <div class="cl-edit-row">
        <label class="cl-edit-lbl">日期</label>
        <input class="cl-edit-inp" type="date" id="cl-edit-date">
      </div>
    </div>

  </div>
  <div class="cl-edit-footer">
    <button class="ds-btn ds-btn-ghost" onclick="clCloseEditModal()">取消</button>
    <button class="ds-btn ds-btn-primary" id="cl-edit-save-btn" onclick="clSaveEdit()">保存</button>
  </div>
</div>

{% endblock %}
```

- [ ] **Step 4: Run full test suite**

```bash
source venv/bin/activate
python manage.py test app01 --keepdb -v 1
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add templates/compound_list.html
git commit -m "feat: update edit button onclick; add edit modal HTML to compound_list template"
```

---

### Task 4: JS — replace `clEditRow` stub + add `clSaveEdit` + `clCloseEditModal`

**Files:**
- Modify: `static/js/compound_list.js` (lines 631–633 replaced; functions appended after `_clShowToast`)

The file currently ends with (lines 631–642):

```js
// ── Edit row (stub — full modal in Spec 2) ────────────────────
function clEditRow(compoundId) {
  _clShowToast('编辑功能即将上线');
}

// ── Toast helper ──────────────────────────────────────────────
function _clShowToast(msg) {
  const t = document.createElement('div');
  t.className = 'cl-toast';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2000);
}
```

- [ ] **Step 1: Replace the stub block + add all three new functions**

Replace the entire block from `// ── Edit row` through the end of the file with:

```js
// ── Edit modal state ──────────────────────────────────────────
let _clEditCompoundId = null;
let _clEditExpId = null;

// ── Open edit modal ───────────────────────────────────────────
async function clEditRow(compoundId, expId) {
  _clEditCompoundId = compoundId;
  _clEditExpId = expId;

  document.getElementById('cl-edit-title').textContent = `编辑 — ${compoundId}`;
  const saveBtn = document.getElementById('cl-edit-save-btn');
  saveBtn.disabled = true;
  document.getElementById('cl-edit-overlay').style.display = 'block';
  document.getElementById('cl-edit-modal').style.display = 'flex';

  try {
    const [cmpRes, expRes] = await Promise.all([
      fetch(`/api/compounds/${compoundId}/`),
      fetch(`/api/experiments/${expId}/`),
    ]);
    if (!cmpRes.ok || !expRes.ok) throw new Error('fetch failed');
    const cmp = await cmpRes.json();
    const exp = await expRes.json();

    document.getElementById('cl-edit-target-name').value    = cmp.target_name    || '';
    document.getElementById('cl-edit-transcript-ref').value = cmp.transcript_ref || '';
    document.getElementById('cl-edit-remarks').value        = cmp.remarks        || '';

    document.getElementById('cl-edit-assay-name').value  = exp.assay_name  || '';
    document.getElementById('cl-edit-batch-label').value = exp.batch_label || '';
    document.getElementById('cl-edit-notes').value       = exp.notes       || '';
    document.getElementById('cl-edit-date').value        = exp.date        || '';

    const isVivo = exp.exp_type === 'in_vivo';
    document.getElementById('cl-edit-vitro-fields').style.display = isVivo ? 'none' : 'block';
    document.getElementById('cl-edit-vivo-fields').style.display  = isVivo ? 'block' : 'none';

    if (isVivo) {
      document.getElementById('cl-edit-animal-species').value = exp.animal_species || '';
      document.getElementById('cl-edit-animal-strain').value  = exp.animal_strain  || '';
      document.getElementById('cl-edit-route').value          = exp.route          || '';
      document.getElementById('cl-edit-gender').value         = exp.gender         || '';
      document.getElementById('cl-edit-time-unit').value      = exp.time_unit      || '';
      document.getElementById('cl-edit-dose-info').value      = exp.dose_info      || '';
      document.getElementById('cl-edit-schedule').value       = exp.schedule       || '';
    } else {
      document.getElementById('cl-edit-cell-line').value = exp.cell_line || '';
    }

    saveBtn.disabled = false;
  } catch (e) {
    clCloseEditModal();
    alert('加载数据失败，请重试');
  }
}

// ── Save edit ─────────────────────────────────────────────────
async function clSaveEdit() {
  const saveBtn = document.getElementById('cl-edit-save-btn');
  saveBtn.disabled = true;

  const cmpData = {
    target_name:    document.getElementById('cl-edit-target-name').value,
    transcript_ref: document.getElementById('cl-edit-transcript-ref').value,
    remarks:        document.getElementById('cl-edit-remarks').value,
  };

  const isVivo = document.getElementById('cl-edit-vivo-fields').style.display !== 'none';
  const expData = {
    assay_name:  document.getElementById('cl-edit-assay-name').value,
    batch_label: document.getElementById('cl-edit-batch-label').value,
    notes:       document.getElementById('cl-edit-notes').value,
    date:        document.getElementById('cl-edit-date').value || null,
  };
  if (isVivo) {
    Object.assign(expData, {
      animal_species: document.getElementById('cl-edit-animal-species').value,
      animal_strain:  document.getElementById('cl-edit-animal-strain').value,
      route:          document.getElementById('cl-edit-route').value,
      gender:         document.getElementById('cl-edit-gender').value,
      time_unit:      document.getElementById('cl-edit-time-unit').value,
      dose_info:      document.getElementById('cl-edit-dose-info').value,
      schedule:       document.getElementById('cl-edit-schedule').value,
    });
  } else {
    expData.cell_line = document.getElementById('cl-edit-cell-line').value;
  }

  try {
    const [cmpRes, expRes] = await Promise.all([
      fetch(`/api/compounds/${_clEditCompoundId}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _clCsrfToken() },
        body: JSON.stringify(cmpData),
      }),
      fetch(`/api/experiments/${_clEditExpId}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _clCsrfToken() },
        body: JSON.stringify(expData),
      }),
    ]);
    if (cmpRes.ok && expRes.ok) {
      clCloseEditModal();
      _clShowToast('保存成功');
      setTimeout(() => location.reload(), 800);
    } else {
      const errRes = cmpRes.ok ? expRes : cmpRes;
      const err = await errRes.json();
      alert(err.error || '保存失败，请重试');
      saveBtn.disabled = false;
    }
  } catch (e) {
    alert('网络错误，请重试');
    saveBtn.disabled = false;
  }
}

// ── Close edit modal ──────────────────────────────────────────
function clCloseEditModal() {
  document.getElementById('cl-edit-overlay').style.display = 'none';
  document.getElementById('cl-edit-modal').style.display   = 'none';
  _clEditCompoundId = null;
  _clEditExpId      = null;
}

// ── Toast helper ──────────────────────────────────────────────
function _clShowToast(msg) {
  const t = document.createElement('div');
  t.className = 'cl-toast';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2000);
}
```

- [ ] **Step 2: Run full test suite**

```bash
source venv/bin/activate
python manage.py test app01 --keepdb -v 1
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add static/js/compound_list.js
git commit -m "feat: implement clEditRow modal, clSaveEdit, clCloseEditModal in compound_list.js"
```

---

### Task 5: Lint check

**Files:**
- Check: `app01/views.py`, `app01/tests.py`

- [ ] **Step 1: Run ruff**

```bash
source venv/bin/activate
ruff check app01/views.py app01/tests.py --select W293,E401
```

Expected: `All checks passed!`

- [ ] **Step 2: Commit only if violations found**

```bash
git add app01/views.py app01/tests.py
git commit -m "chore: fix ruff lint violations"
```
