# 编辑权限申请与审批工作流 — 设计文档（Spec 3）

**日期：** 2026-06-29
**范围：** 化合物列表页行级编辑/删除权限 — 申请、审批、撤销全流程

---

## 1. 背景

Spec 1 添加了行级 ✏️/🗑 按钮，Spec 2 实现了编辑 modal。两者目前仅对拥有全局 `data` 模块权限（`module_permissions` 含 `'data'`）或 superadmin 的用户开放。

Spec 3 在现有 `ProjectAccessRequest` + `AuditLog` 基础上，以最小改动支持：普通用户按项目申请编辑权限 → admin/superadmin 审批 → 权限生效，直到 admin 手动撤销。

---

## 2. 数据模型变更

### 2.1 `ProjectAccessRequest` 加 `request_type`

```python
request_type = models.CharField(
    max_length=8,
    choices=[('view', '查看权限'), ('edit', '编辑权限')],
    default='view',
)
```

现有所有记录默认值 `'view'`，无需数据迁移。

### 2.2 `LmsUser` 加 `edit_projects`

```python
edit_projects = models.TextField(blank=True, default='')
```

与 `permissions_project` 完全对称——逗号分隔的 project_code 列表。admin 批准 edit 类型申请时写入此字段。

### 2.3 `AuditLog.ACTION_CHOICES` 新增三个值

```python
('edit_request',  '申请编辑权限'),
('edit_approved', '编辑权限批准'),
('edit_rejected', '编辑权限拒绝'),
```

### 2.4 迁移

一次迁移文件，加上述三个字段，无数据变更。

---

## 3. 权限检查

### 3.1 helper：`_can_edit_compound(user, compound)`

新增到 `app01/views.py`：

```python
def _can_edit_compound(user, compound):
    if user.is_superuser or user.user_type == 'superadmin' or _has_module(user, 'data'):
        return True
    edit_set = set(p.strip() for p in (user.edit_projects or '').split(',') if p.strip())
    return compound.project in edit_set
```

`api_compound_detail` 和 `api_experiment_detail` 的 PATCH 权限检查均改用此 helper。

### 3.2 `compound_list` 视图

`can_delete` 保留（仅控制批量删除按钮），另计算 `edit_project_set` 传入模板：

```python
can_delete = (
    request.user.is_superuser
    or request.user.user_type == 'superadmin'
    or _has_module(request.user, 'data')
)
edit_project_set = set(
    p.strip() for p in (request.user.edit_projects or '').split(',') if p.strip()
)
```

`context` 中新增 `'edit_project_set': edit_project_set`。

---

## 4. 化合物列表模板（`compound_list.html`）

### 4.1 行级按钮：两分支

体外和体内两张表的 actions 列均改为：

```django
{% if can_delete or vc.compound.project in edit_project_set %}
<td class="cl-row-actions" onclick="event.stopPropagation()">
  <button class="cl-icon-btn cl-icon-edit"
          onclick="clEditRow('{{ vc.compound.compound_id }}', {{ vc.exp_ids.0 }})"
          title="编辑">✏️</button>
  <button class="cl-icon-btn cl-icon-del"
          onclick="clDeleteRow({{ vc.exp_ids|join:',' }})"
          title="删除">🗑</button>
</td>
{% else %}
<td class="cl-row-actions" onclick="event.stopPropagation()">
  <button class="cl-icon-btn cl-icon-edit cl-icon-locked"
          onclick="clRequestEditPerm('{{ vc.compound.project }}')"
          title="申请编辑权限">✏️</button>
  <button class="cl-icon-btn cl-icon-del cl-icon-locked"
          onclick="clRequestEditPerm('{{ vc.compound.project }}')"
          title="申请编辑权限">🗑</button>
</td>
{% endif %}
```

`.cl-icon-locked` CSS：`opacity: 0.35; cursor: not-allowed;`（hover 时变 `opacity: 1` 但保持 `cursor: not-allowed`）。

批量删除按钮保持 `{% if can_delete %}` 不变。

### 4.2 申请 modal HTML（加到 `{% endblock %}` 前）

```html
{# ── 编辑权限申请 modal ── #}
<div id="cl-req-overlay" class="cl-cmp-overlay" onclick="clCloseReqModal()" style="display:none"></div>
<div id="cl-req-modal" class="cl-edit-modal" style="display:none;max-width:360px;">
  <div class="cl-edit-hdr">
    <span class="cl-edit-title">申请编辑权限</span>
    <button class="cl-cmp-close" onclick="clCloseReqModal()">✕</button>
  </div>
  <div class="cl-edit-body" style="padding:20px 18px;">
    <p style="margin:0 0 16px;font-size:13px;color:#475569;">
      您需要项目 <strong id="cl-req-project"></strong> 的编辑权限才能执行此操作。
    </p>
    <form id="cl-req-form" method="POST" action="{% url 'profile_request_edit' %}">
      {% csrf_token %}
      <input type="hidden" name="project_code" id="cl-req-project-input">
      <button type="submit" class="ds-btn ds-btn-primary" style="width:100%;">
        申请编辑权限
      </button>
    </form>
  </div>
</div>
```

---

## 5. JS（`compound_list.js`）

```js
// ── 编辑权限申请 modal ──────────────────────────────────────────
function clRequestEditPerm(projectCode) {
  document.getElementById('cl-req-project').textContent      = projectCode;
  document.getElementById('cl-req-project-input').value      = projectCode;
  document.getElementById('cl-req-overlay').style.display   = 'block';
  document.getElementById('cl-req-modal').style.display     = 'flex';
}

function clCloseReqModal() {
  document.getElementById('cl-req-overlay').style.display = 'none';
  document.getElementById('cl-req-modal').style.display   = 'none';
}
```

---

## 6. 后端：`profile_request_edit` view

新增到 `app01/views.py`：

```python
@login_required
def profile_request_edit(request):
    if request.method != 'POST':
        return redirect('user_profile')
    project_code = request.POST.get('project_code', '').strip()
    if not project_code:
        messages.error(request, '项目代码不能为空')
        return redirect('compound_list')
    user = request.user
    # 已有编辑权限
    edit_set = set(p.strip() for p in (user.edit_projects or '').split(',') if p.strip())
    if project_code in edit_set:
        messages.info(request, f'你已拥有项目 {project_code} 的编辑权限')
        return redirect('compound_list')
    # 已有 pending 申请
    if ProjectAccessRequest.objects.filter(
        user=user, project_code=project_code,
        request_type='edit', status='pending'
    ).exists():
        messages.info(request, f'项目 {project_code} 的编辑权限申请已在审批中')
        return redirect('compound_list')
    ProjectAccessRequest.objects.create(
        user=user, project_code=project_code, request_type='edit'
    )
    AuditLog.objects.create(
        actor=user,
        action='edit_request',
        detail=json.dumps({'project': project_code}),
    )
    messages.success(request, f'已提交项目 {project_code} 的编辑权限申请，等待 admin 审批')
    return redirect('compound_list')
```

URL：`path('profile/request-edit/', views.profile_request_edit, name='profile_request_edit')`

---

## 7. 审批：`project_request_approve` / `project_request_reject` 更新

`project_request_approve` 按 `request_type` 分支：

```python
req = get_object_or_404(ProjectAccessRequest, id=req_id)
user = req.user
if req.request_type == 'edit':
    existing = [p.strip() for p in (user.edit_projects or '').split(',') if p.strip()]
    if req.project_code not in existing:
        existing.append(req.project_code)
    user.edit_projects = ','.join(existing)
    user.save(update_fields=['edit_projects'])
    audit_action = 'edit_approved'
else:
    existing = [p.strip() for p in (user.permissions_project or '').split(',') if p.strip()]
    if req.project_code not in existing:
        existing.append(req.project_code)
    user.permissions_project = ','.join(existing)
    user.save(update_fields=['permissions_project'])
    audit_action = 'project_approved'

req.status = 'approved'
req.reviewed_by = request.user
req.reviewed_at = datetime.datetime.now()
req.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])
AuditLog.objects.create(actor=request.user, action=audit_action,
                         target_user=user,
                         detail=json.dumps({'project': req.project_code}))
```

`project_request_reject` 同理：`audit_action = 'edit_rejected'` 或 `'project_rejected'`。

---

## 8. 用户管理页（`user_management.html`）

待审批区块的表格加"类型"列：

```html
<th style="padding:6px 10px;text-align:left;">权限类型</th>
...
<td style="padding:7px 10px;">
  {% if req.request_type == 'edit' %}
  <span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;background:#fed7aa;color:#c2410c;">编辑权限</span>
  {% else %}
  <span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;background:#dbeafe;color:#1d4ed8;">查看权限</span>
  {% endif %}
</td>
```

`user_management_view` 里 `pending_requests` 查询不变（已经 filter `status='pending'`，自动包含两类）。

---

## 9. 用户资料页（`profile.html`）

现有 `access_requests` 表格加"类型"列，与用户管理页用相同 badge 样式区分 view/edit。不需要修改视图逻辑。

---

## 10. 撤销编辑权限

Admin 进入"编辑用户"页（`user_edit.html`）修改 `edit_projects` 字段，删除对应 project_code。

**`user_edit.html`** 在"可访问项目"字段下方新增：

```html
<div style="margin-bottom:20px;">
  <label style="display:block;font-size:12px;font-weight:600;color:#475569;margin-bottom:5px;">
    可编辑项目（逗号分隔）
  </label>
  <input type="text" name="edit_projects" class="ds-form-control"
         value="{{ target.edit_projects }}" style="width:100%;"
         placeholder="如 BPR350,BPR3M03">
</div>
```

**`user_edit_view`** POST 分支补充读取和保存 `edit_projects`：

```python
old_edit = target.edit_projects
new_edit = request.POST.get('edit_projects', '').strip()
target.edit_projects = new_edit
# save() 和 AuditLog detail 中也包含 edit_projects before/after
```

---

## 11. 文件清单

| 文件 | 变更 |
|------|------|
| `app01/models.py` | `ProjectAccessRequest` 加 `request_type`；`LmsUser` 加 `edit_projects`；`AuditLog.ACTION_CHOICES` 加 3 个值 |
| `app01/views.py` | 新增 `_can_edit_compound`、`profile_request_edit`；更新 `compound_list`（加 `edit_project_set`）；更新 `project_request_approve` / `project_request_reject`（按 `request_type` 分支）；更新 `api_compound_detail` / `api_experiment_detail`（改用 `_can_edit_compound`） |
| `bprdb/urls.py` | 新增 `/profile/request-edit/` |
| `templates/compound_list.html` | 行级 actions 拆两分支；加申请 modal HTML |
| `templates/user_management.html` | 待审批区块加"权限类型"列 |
| `templates/profile.html` | `access_requests` 表格加"类型"列 |
| `templates/user_edit.html` | 新增 `edit_projects` 输入字段 |
| `static/js/compound_list.js` | 新增 `clRequestEditPerm`、`clCloseReqModal` |
| `app01/migrations/xxxx_add_edit_permission_fields.py` | 一次迁移 |

---

## 12. 测试要点

- 普通用户在化合物列表点击 ✏️/🗑 → 弹申请 modal，显示正确的 project_code
- 提交申请 → 跳回列表页，显示成功提示；重复提交 → 提示"已在审批中"
- Admin 用户管理页看到 pending 申请，显示"编辑权限"橙色标签
- Admin 点击"批准"→ `user.edit_projects` 写入对应 project_code
- 被批准的用户刷新页面 → 对应项目的行显示真实 ✏️/🗑（可操作）
- 编辑/保存走 `api_compound_detail` PATCH → 200；无权限用户 PATCH → 403
- Admin 在 user_edit 页清除 `edit_projects` 中的 project_code → 用户失去编辑权限
- `AuditLog` 正确记录 `edit_request`、`edit_approved`、`edit_rejected`
