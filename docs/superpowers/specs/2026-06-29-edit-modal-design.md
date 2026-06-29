# Edit Modal — Design Spec (Spec 2)

**Date:** 2026-06-29
**Scope:** Compound list page — inline edit modal for compound and experiment metadata

---

## 1. Background

Spec 1 added a ✏️ icon button per row that currently shows a "即将上线" toast. This spec implements the real edit modal behind that button.

The edit covers two levels:
- **Compound** — `target_name`, `transcript_ref`, `remarks`
- **Experiment** — common fields + type-specific fields (vitro vs vivo)

Spec 3 (permission request workflow) will later gate this behind a proper `edit` permission. For now, the same `can_delete` check (superadmin or `data` in module_permissions) controls access.

---

## 2. Button Update

The current stub in `compound_list.html` passes only `compoundId`:

```html
onclick="clEditRow('{{ vc.compound.compound_id }}')"
```

Both vitro and vivo templates must be updated to also pass the first experiment ID:

```html
onclick="clEditRow('{{ vc.compound.compound_id }}', {{ vc.exp_ids.0 }})"
```

`vc.exp_ids.0` is the Django template accessor for the first element of the `exp_ids` list.

---

## 3. Modal HTML

Added to `templates/compound_list.html` before `{% endblock %}`, using the same overlay pattern as the comparison modal:

```html
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
```

---

## 4. CSS (append to `static/css/compound_list.css`)

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

---

## 5. JS (`static/js/compound_list.js`)

Replace the existing `clEditRow` stub and add three new functions.

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

    document.getElementById('cl-edit-target-name').value   = cmp.target_name    || '';
    document.getElementById('cl-edit-transcript-ref').value = cmp.transcript_ref || '';
    document.getElementById('cl-edit-remarks').value        = cmp.remarks        || '';

    document.getElementById('cl-edit-assay-name').value   = exp.assay_name   || '';
    document.getElementById('cl-edit-batch-label').value  = exp.batch_label  || '';
    document.getElementById('cl-edit-notes').value        = exp.notes        || '';
    document.getElementById('cl-edit-date').value         = exp.date         || '';

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
```

---

## 6. Backend API (`app01/views.py`)

Two new view functions. Both require login and `can_delete` permission.

### `api_compound_detail(request, compound_id)`

```python
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
```

### `api_experiment_detail(request, exp_id)`

```python
@login_required
def api_experiment_detail(request, exp_id):
    if not (request.user.is_superuser
            or request.user.user_type == 'superadmin'
            or _has_module(request.user, 'data')):
        return JsonResponse({'error': '权限不足'}, status=403)
    exp = get_object_or_404(Experiment, pk=exp_id)
    if request.method == 'GET':
        return JsonResponse({
            'exp_type':      exp.exp_type,
            'assay_name':    exp.assay_name,
            'batch_label':   exp.batch_label,
            'cell_line':     exp.cell_line,
            'notes':         exp.notes,
            'date':          exp.date.isoformat() if exp.date else '',
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
```

---

## 7. URL Registration (`bprdb/urls.py`)

```python
path('api/compounds/<str:compound_id>/', views.api_compound_detail, name='api_compound_detail'),
path('api/experiments/<int:exp_id>/',    views.api_experiment_detail, name='api_experiment_detail'),
```

---

## 8. File Map

| File | Change |
|------|--------|
| `templates/compound_list.html` | Update `clEditRow(...)` calls to pass `exp_id`; add edit modal HTML before `{% endblock %}` |
| `static/css/compound_list.css` | Append edit modal CSS |
| `static/js/compound_list.js` | Replace `clEditRow` stub; add `clSaveEdit`, `clCloseEditModal`, state vars |
| `app01/views.py` | Add `api_compound_detail` and `api_experiment_detail` views |
| `bprdb/urls.py` | Register two new URL patterns |
| `app01/tests.py` | Tests for both API views (GET + PATCH, permission denied) |

No migrations required.

---

## 9. Testing

- GET `/api/compounds/<id>/` returns correct fields
- PATCH `/api/compounds/<id>/` updates target_name, transcript_ref, remarks
- GET `/api/experiments/<id>/` returns correct fields including exp_type
- PATCH `/api/experiments/<id>/` updates fields for vitro and vivo
- Both endpoints return 403 for users without `data` permission
- Modal opens with pre-filled values after clicking ✏️
- Saving closes modal, shows "保存成功" toast, page reloads after 800ms
- Vivo modal shows vivo fields; vitro shows cell_line only
