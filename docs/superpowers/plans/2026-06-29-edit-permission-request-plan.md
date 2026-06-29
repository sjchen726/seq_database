# 编辑权限申请与审批工作流 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 允许普通用户在化合物列表页按项目申请编辑权限，admin 在用户管理页审批，权限持续到手动撤销。

**Architecture:** 在现有 `ProjectAccessRequest` + `AuditLog` 模型上最小扩展——加 `request_type` 字段区分查看/编辑申请，加 `LmsUser.edit_projects` 存已批准的编辑权限，化合物列表行级检查 `edit_project_set`，无权限时点击按钮弹申请 modal 而非直接操作。

**Tech Stack:** Django 5.1，MySQL，原生 JS，Django 模板。测试用 `python manage.py test app01.tests.ClassName -v 2`。

---

## 文件清单

| 文件 | 变更类型 |
|------|---------|
| `app01/models.py` | 修改：3 个字段/常量 |
| `app01/views.py` | 修改：加 helper、新 view、更新 5 个现有 view |
| `bprdb/urls.py` | 修改：加 1 条 URL |
| `templates/compound_list.html` | 修改：行级分支 + 申请 modal HTML |
| `templates/user_management.html` | 修改：待审批区块加"类型"列 |
| `templates/profile.html` | 修改：申请记录加"类型"列 |
| `templates/user_edit.html` | 修改：加 `edit_projects` 输入框 |
| `static/css/design-system.css` | 修改：加 `.cl-icon-locked` |
| `static/js/compound_list.js` | 修改：加 2 个函数 |
| `app01/migrations/xxxx_add_edit_permission_fields.py` | 新建：一次迁移 |

---

## Task 1：模型变更 + 迁移

**Files:**
- Modify: `app01/models.py`
- Create: `app01/migrations/` (auto-generated)
- Modify: `app01/tests.py`

- [ ] **Step 1：写失败测试**

在 `app01/tests.py` 末尾加：

```python
class EditPermissionModelTest(TestCase):
    def test_project_access_request_has_request_type(self):
        user = LmsUser.objects.create_user(username='rt_user', password='pass')
        req = ProjectAccessRequest.objects.create(
            user=user, project_code='BPR350', request_type='edit'
        )
        req.refresh_from_db()
        self.assertEqual(req.request_type, 'edit')

    def test_project_access_request_default_request_type_is_view(self):
        user = LmsUser.objects.create_user(username='rt_user2', password='pass')
        req = ProjectAccessRequest.objects.create(user=user, project_code='BPR350')
        req.refresh_from_db()
        self.assertEqual(req.request_type, 'view')

    def test_lms_user_has_edit_projects(self):
        user = LmsUser.objects.create_user(
            username='ep_user', password='pass', edit_projects='BPR350,BPR3M03'
        )
        user.refresh_from_db()
        self.assertEqual(user.edit_projects, 'BPR350,BPR3M03')

    def test_lms_user_edit_projects_default_empty(self):
        user = LmsUser.objects.create_user(username='ep_user2', password='pass')
        self.assertEqual(user.edit_projects, '')

    def test_audit_log_has_edit_action_choices(self):
        choices = dict(AuditLog.ACTION_CHOICES)
        self.assertIn('edit_request', choices)
        self.assertIn('edit_approved', choices)
        self.assertIn('edit_rejected', choices)
```

- [ ] **Step 2：运行确认失败**

```bash
python manage.py test app01.tests.EditPermissionModelTest -v 2
```

期望：`OperationalError` 或 `TypeError`（字段不存在）

- [ ] **Step 3：修改 `app01/models.py`**

在 `ProjectAccessRequest` 模型的 `STATUS_CHOICES` 下方、`user` 字段之前加：

```python
    REQUEST_TYPE_CHOICES = [
        ('view', '查看权限'),
        ('edit', '编辑权限'),
    ]
```

在 `user` 字段之前（或 `note` 字段之后）加 `request_type`，最终模型字段顺序为：

```python
    user         = models.ForeignKey(LmsUser, on_delete=models.CASCADE,
                                     related_name='project_requests')
    project_code = models.CharField(max_length=64)
    request_type = models.CharField(max_length=8, choices=REQUEST_TYPE_CHOICES, default='view')
    status       = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    note         = models.TextField(blank=True, default='')
    created_at   = models.DateTimeField(auto_now_add=True)
    reviewed_at  = models.DateTimeField(null=True, blank=True)
    reviewed_by  = models.ForeignKey(LmsUser, null=True, blank=True,
                                     on_delete=models.SET_NULL,
                                     related_name='reviewed_requests')
```

在 `LmsUser` 的 `module_permissions` 字段之后加：

```python
    edit_projects = models.TextField(blank=True, default='',
                                     help_text='逗号分隔的可编辑 project_code')
```

在 `AuditLog.ACTION_CHOICES` 列表末尾加三项（保持现有缩进格式）：

```python
        ('edit_request',  '申请编辑权限'),
        ('edit_approved', '编辑权限批准'),
        ('edit_rejected', '编辑权限拒绝'),
```

- [ ] **Step 4：生成并执行迁移**

```bash
python manage.py makemigrations app01 --name add_edit_permission_fields
python manage.py migrate
```

期望：迁移无报错，`OK` 结束。

- [ ] **Step 5：运行测试确认通过**

```bash
python manage.py test app01.tests.EditPermissionModelTest -v 2
```

期望：5 个测试全部 `PASS`。

- [ ] **Step 6：提交**

```bash
git add app01/models.py app01/migrations/ app01/tests.py
git commit -m "feat: add request_type to ProjectAccessRequest, edit_projects to LmsUser, audit log choices"
```

---

## Task 2：`_can_edit_compound` helper + 更新 API 端点权限检查

**Files:**
- Modify: `app01/views.py` (helper + 2 个 view 的权限检查)
- Modify: `app01/tests.py`

- [ ] **Step 1：写失败测试**

在 `app01/tests.py` 末尾加：

```python
class CanEditCompoundTest(TestCase):
    def setUp(self):
        self.compound = Compound.objects.create(
            compound_id='BPR_CE01', project='PROJ_A', target='TS',
        )
        self.exp = Experiment.objects.create(
            compound=self.compound, exp_type='in_vitro',
            assay_name='assay', batch_label='B001',
        )

    def _make_user(self, username, user_type='user', module_permissions='',
                   edit_projects='', is_superuser=False):
        u = LmsUser.objects.create_user(
            username=username, password='pass',
            user_type=user_type, module_permissions=module_permissions,
            edit_projects=edit_projects,
        )
        if is_superuser:
            u.is_superuser = True
            u.save()
        return u

    # ── _can_edit_compound helper ──────────────────────────────
    def test_superuser_can_edit(self):
        from app01.views import _can_edit_compound
        u = self._make_user('su', is_superuser=True)
        self.assertTrue(_can_edit_compound(u, self.compound))

    def test_superadmin_can_edit(self):
        from app01.views import _can_edit_compound
        u = self._make_user('sa', user_type='superadmin')
        self.assertTrue(_can_edit_compound(u, self.compound))

    def test_data_module_user_can_edit(self):
        from app01.views import _can_edit_compound
        u = self._make_user('dm', module_permissions='data')
        self.assertTrue(_can_edit_compound(u, self.compound))

    def test_edit_project_matching_compound_project_can_edit(self):
        from app01.views import _can_edit_compound
        u = self._make_user('ep', edit_projects='PROJ_A,PROJ_B')
        self.assertTrue(_can_edit_compound(u, self.compound))

    def test_edit_project_not_matching_cannot_edit(self):
        from app01.views import _can_edit_compound
        u = self._make_user('ep2', edit_projects='PROJ_B')
        self.assertFalse(_can_edit_compound(u, self.compound))

    def test_no_permissions_cannot_edit(self):
        from app01.views import _can_edit_compound
        u = self._make_user('plain')
        self.assertFalse(_can_edit_compound(u, self.compound))

    # ── API endpoint integration ───────────────────────────────
    def test_edit_project_user_can_get_compound(self):
        u = self._make_user('ep3', edit_projects='PROJ_A')
        self.client.login(username='ep3', password='pass')
        resp = self.client.get('/api/compounds/BPR_CE01/')
        self.assertEqual(resp.status_code, 200)

    def test_edit_project_user_can_patch_compound(self):
        u = self._make_user('ep4', edit_projects='PROJ_A')
        self.client.login(username='ep4', password='pass')
        resp = self.client.patch(
            '/api/compounds/BPR_CE01/',
            data=json.dumps({'target_name': 'NEW'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)

    def test_wrong_edit_project_user_gets_403_on_compound(self):
        u = self._make_user('ep5', edit_projects='PROJ_B')
        self.client.login(username='ep5', password='pass')
        resp = self.client.get('/api/compounds/BPR_CE01/')
        self.assertEqual(resp.status_code, 403)

    def test_edit_project_user_can_get_experiment(self):
        u = self._make_user('ep6', edit_projects='PROJ_A')
        self.client.login(username='ep6', password='pass')
        resp = self.client.get(f'/api/experiments/{self.exp.pk}/')
        self.assertEqual(resp.status_code, 200)

    def test_edit_project_user_can_patch_experiment(self):
        u = self._make_user('ep7', edit_projects='PROJ_A')
        self.client.login(username='ep7', password='pass')
        resp = self.client.patch(
            f'/api/experiments/{self.exp.pk}/',
            data=json.dumps({'assay_name': 'new_assay'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)

    def test_wrong_edit_project_user_gets_403_on_experiment(self):
        u = self._make_user('ep8', edit_projects='PROJ_B')
        self.client.login(username='ep8', password='pass')
        resp = self.client.get(f'/api/experiments/{self.exp.pk}/')
        self.assertEqual(resp.status_code, 403)
```

- [ ] **Step 2：运行确认失败**

```bash
python manage.py test app01.tests.CanEditCompoundTest -v 2
```

期望：helper 相关测试 `ImportError` 或 `AttributeError`；API 测试 `403`（旧逻辑无 edit_projects 检查）。

- [ ] **Step 3：在 `app01/views.py` 加 helper**

在 `_has_module` helper（约第 34 行）之后加：

```python
def _can_edit_compound(user, compound):
    if user.is_superuser or user.user_type == 'superadmin' or _has_module(user, 'data'):
        return True
    edit_set = set(p.strip() for p in (user.edit_projects or '').split(',') if p.strip())
    return compound.project in edit_set
```

- [ ] **Step 4：更新 `api_compound_detail` 权限检查**

将 `api_compound_detail` view 的前四行改为先取 compound 再检查：

```python
@login_required
def api_compound_detail(request, compound_id):
    compound = get_object_or_404(Compound, pk=compound_id)
    if not _can_edit_compound(request.user, compound):
        return JsonResponse({'error': '权限不足'}, status=403)
    if request.method == 'GET':
        ...（其余不变）
```

注意：原来没有 `@login_required`，现在要加上。

- [ ] **Step 5：更新 `api_experiment_detail` 权限检查**

将权限检查改为取 exp 后用 helper：

```python
@login_required
def api_experiment_detail(request, exp_id):
    exp = get_object_or_404(Experiment.objects.select_related('compound'), pk=exp_id)
    if not _can_edit_compound(request.user, exp.compound):
        return JsonResponse({'error': '权限不足'}, status=403)
    if request.method == 'GET':
        ...（其余不变）
```

- [ ] **Step 6：运行所有测试**

```bash
python manage.py test app01.tests.CanEditCompoundTest app01.tests.CompoundApiTest -v 2
```

期望：全部 `PASS`（包括 `CompoundApiTest` 的现有测试——验证没有回归）。

- [ ] **Step 7：提交**

```bash
git add app01/views.py app01/tests.py
git commit -m "feat: add _can_edit_compound helper; update api_compound_detail and api_experiment_detail to support edit_projects"
```

---

## Task 3：`profile_request_edit` view + URL

**Files:**
- Modify: `app01/views.py`
- Modify: `bprdb/urls.py`
- Modify: `app01/tests.py`

- [ ] **Step 1：写失败测试**

在 `app01/tests.py` 末尾加：

```python
class ProfileRequestEditTest(TestCase):
    def setUp(self):
        self.admin = LmsUser.objects.create_user(
            username='adm', password='pass', user_type='superadmin',
        )
        self.user = LmsUser.objects.create_user(
            username='req_user', password='pass', user_type='user',
        )
        self.client.login(username='req_user', password='pass')

    def test_post_creates_edit_request(self):
        resp = self.client.post('/profile/request-edit/', {'project_code': 'BPR350'})
        self.assertEqual(ProjectAccessRequest.objects.filter(
            user=self.user, project_code='BPR350', request_type='edit', status='pending'
        ).count(), 1)

    def test_post_creates_audit_log(self):
        self.client.post('/profile/request-edit/', {'project_code': 'BPR350'})
        self.assertEqual(AuditLog.objects.filter(
            actor=self.user, action='edit_request'
        ).count(), 1)

    def test_post_redirects_to_compound_list(self):
        resp = self.client.post('/profile/request-edit/', {'project_code': 'BPR350'})
        self.assertRedirects(resp, '/compound-list/', fetch_redirect_response=False)

    def test_duplicate_pending_request_not_created(self):
        self.client.post('/profile/request-edit/', {'project_code': 'BPR350'})
        self.client.post('/profile/request-edit/', {'project_code': 'BPR350'})
        self.assertEqual(ProjectAccessRequest.objects.filter(
            user=self.user, project_code='BPR350', request_type='edit'
        ).count(), 1)

    def test_already_has_edit_permission_no_request_created(self):
        self.user.edit_projects = 'BPR350'
        self.user.save()
        self.client.post('/profile/request-edit/', {'project_code': 'BPR350'})
        self.assertEqual(ProjectAccessRequest.objects.filter(
            user=self.user, project_code='BPR350', request_type='edit'
        ).count(), 0)

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.post('/profile/request-edit/', {'project_code': 'BPR350'})
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp['Location'])
```

先确认 compound_list 的 URL：

```bash
python manage.py shell -c "from django.urls import reverse; print(reverse('compound_list'))"
```

记录输出路径（后续 `assertRedirects` 用到）。

- [ ] **Step 2：运行确认失败**

```bash
python manage.py test app01.tests.ProfileRequestEditTest -v 2
```

期望：`404`（URL 未注册）或 `NoReverseMatch`。

- [ ] **Step 3：在 `bprdb/urls.py` 加 URL**

在 `profile/request-project/` 那行之后加：

```python
path('profile/request-edit/', views.profile_request_edit, name='profile_request_edit'),
```

- [ ] **Step 4：在 `app01/views.py` 加 view**

在 `profile_request_project` view 之后加：

```python
@login_required
def profile_request_edit(request):
    if request.method != 'POST':
        return redirect('compound_list')
    project_code = request.POST.get('project_code', '').strip()
    if not project_code:
        messages.error(request, '项目代码不能为空')
        return redirect('compound_list')
    user = request.user
    edit_set = set(p.strip() for p in (user.edit_projects or '').split(',') if p.strip())
    if project_code in edit_set:
        messages.info(request, f'你已拥有项目 {project_code} 的编辑权限')
        return redirect('compound_list')
    if ProjectAccessRequest.objects.filter(
        user=user, project_code=project_code, request_type='edit', status='pending'
    ).exists():
        messages.info(request, f'项目 {project_code} 的编辑权限申请已在审批中')
        return redirect('compound_list')
    ProjectAccessRequest.objects.create(
        user=user, project_code=project_code, request_type='edit',
    )
    AuditLog.objects.create(
        actor=user,
        action='edit_request',
        detail=json.dumps({'project': project_code}),
    )
    messages.success(request, f'已提交项目 {project_code} 的编辑权限申请，等待 admin 审批')
    return redirect('compound_list')
```

- [ ] **Step 5：运行测试**

```bash
python manage.py test app01.tests.ProfileRequestEditTest -v 2
```

期望：全部 `PASS`。如有 `assertRedirects` 路径不匹配，用 Step 1 确认的路径修正测试。

- [ ] **Step 6：提交**

```bash
git add app01/views.py bprdb/urls.py app01/tests.py
git commit -m "feat: add profile_request_edit view and URL for per-project edit permission requests"
```

---

## Task 4：更新 `project_request_approve` / `project_request_reject`

**Files:**
- Modify: `app01/views.py`
- Modify: `app01/tests.py`

- [ ] **Step 1：写失败测试**

在 `app01/tests.py` 末尾加：

```python
class EditRequestApprovalTest(TestCase):
    def setUp(self):
        self.admin = LmsUser.objects.create_user(
            username='appr_admin', password='pass', user_type='superadmin',
        )
        self.regular_user = LmsUser.objects.create_user(
            username='appr_user', password='pass', user_type='user',
        )
        self.edit_req = ProjectAccessRequest.objects.create(
            user=self.regular_user, project_code='BPR350', request_type='edit',
        )
        self.view_req = ProjectAccessRequest.objects.create(
            user=self.regular_user, project_code='BPR3M03', request_type='view',
        )
        self.client.login(username='appr_admin', password='pass')

    def test_approve_edit_request_writes_edit_projects(self):
        self.client.post(f'/users/requests/{self.edit_req.pk}/approve/')
        self.regular_user.refresh_from_db()
        self.assertIn('BPR350', self.regular_user.edit_projects.split(','))

    def test_approve_edit_request_does_not_write_permissions_project(self):
        self.client.post(f'/users/requests/{self.edit_req.pk}/approve/')
        self.regular_user.refresh_from_db()
        self.assertNotIn('BPR350', (self.regular_user.permissions_project or '').split(','))

    def test_approve_view_request_writes_permissions_project(self):
        self.client.post(f'/users/requests/{self.view_req.pk}/approve/')
        self.regular_user.refresh_from_db()
        self.assertIn('BPR3M03', self.regular_user.permissions_project.split(','))

    def test_approve_edit_request_logs_edit_approved(self):
        self.client.post(f'/users/requests/{self.edit_req.pk}/approve/')
        self.assertEqual(AuditLog.objects.filter(action='edit_approved').count(), 1)

    def test_approve_edit_request_sets_status_approved(self):
        self.client.post(f'/users/requests/{self.edit_req.pk}/approve/')
        self.edit_req.refresh_from_db()
        self.assertEqual(self.edit_req.status, 'approved')

    def test_reject_edit_request_logs_edit_rejected(self):
        self.client.post(f'/users/requests/{self.edit_req.pk}/reject/')
        self.assertEqual(AuditLog.objects.filter(action='edit_rejected').count(), 1)

    def test_reject_edit_request_does_not_write_edit_projects(self):
        self.client.post(f'/users/requests/{self.edit_req.pk}/reject/')
        self.regular_user.refresh_from_db()
        self.assertEqual(self.regular_user.edit_projects, '')
```

- [ ] **Step 2：运行确认失败**

```bash
python manage.py test app01.tests.EditRequestApprovalTest -v 2
```

期望：approve edit 的测试失败（当前 approve 只写 `permissions_project`）。

- [ ] **Step 3：更新 `project_request_approve`**

将 `app01/views.py` 的 `project_request_approve` view 中，`req.save()` 之后的逻辑替换为：

```python
    req.status = 'approved'
    req.reviewed_by = request.user
    req.reviewed_at = datetime.datetime.now()
    req.save()
    user = req.user
    if req.request_type == 'edit':
        existing = [p.strip() for p in (user.edit_projects or '').split(',') if p.strip()]
        if req.project_code not in existing:
            existing.append(req.project_code)
        user.edit_projects = ','.join(existing)
        user.save(update_fields=['edit_projects'])
        audit_action = 'edit_approved'
        msg = f'已批准 {user.username} 编辑 {req.project_code}'
    else:
        existing = [p.strip() for p in (user.permissions_project or '').split(',') if p.strip()]
        if req.project_code not in existing:
            existing.append(req.project_code)
        user.permissions_project = ','.join(existing)
        user.save(update_fields=['permissions_project'])
        audit_action = 'project_approved'
        msg = f'已批准 {user.username} 访问 {req.project_code}'
    AuditLog.objects.create(
        actor=request.user,
        action=audit_action,
        target_user=user,
        detail=_json_mod.dumps({'project': req.project_code}),
    )
    messages.success(request, msg)
    return redirect('user_management')
```

- [ ] **Step 4：更新 `project_request_reject`**

将 `project_request_reject` view 中 `AuditLog.objects.create(...)` 的 `action=` 替换为：

```python
        action='edit_rejected' if req.request_type == 'edit' else 'project_rejected',
```

- [ ] **Step 5：运行测试**

```bash
python manage.py test app01.tests.EditRequestApprovalTest -v 2
```

期望：全部 `PASS`。

- [ ] **Step 6：提交**

```bash
git add app01/views.py app01/tests.py
git commit -m "feat: update project_request_approve/reject to handle edit request_type"
```

---

## Task 5：更新 `compound_list` view + `user_edit_view`

**Files:**
- Modify: `app01/views.py`
- Modify: `templates/user_edit.html`
- Modify: `app01/tests.py`

- [ ] **Step 1：写失败测试**

在 `app01/tests.py` 末尾加：

```python
class CompoundListEditProjectSetTest(TestCase):
    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='cl_ep_user', password='pass',
            user_type='sub_admin', permissions_project='PROJ_A',
            edit_projects='PROJ_A',
        )
        self.client.login(username='cl_ep_user', password='pass')

    def test_context_has_edit_project_set(self):
        resp = self.client.get('/compound-list/')
        self.assertIn('edit_project_set', resp.context)

    def test_edit_project_set_contains_user_edit_projects(self):
        resp = self.client.get('/compound-list/')
        self.assertIn('PROJ_A', resp.context['edit_project_set'])

    def test_edit_project_set_empty_for_user_with_no_edit_projects(self):
        u2 = LmsUser.objects.create_user(
            username='cl_ep_user2', password='pass',
            user_type='sub_admin', permissions_project='PROJ_A',
        )
        self.client.login(username='cl_ep_user2', password='pass')
        resp = self.client.get('/compound-list/')
        self.assertEqual(resp.context['edit_project_set'], set())


class UserEditViewEditProjectsTest(TestCase):
    def setUp(self):
        self.admin = LmsUser.objects.create_user(
            username='ue_admin', password='pass', user_type='superadmin',
        )
        self.target_user = LmsUser.objects.create_user(
            username='ue_target', password='pass', user_type='user',
        )
        self.client.login(username='ue_admin', password='pass')

    def test_post_saves_edit_projects(self):
        self.client.post(f'/users/{self.target_user.pk}/edit/', {
            'user_type': 'user',
            'module_permissions': [],
            'permissions_project': '',
            'edit_projects': 'BPR350,BPR3M03',
        })
        self.target_user.refresh_from_db()
        self.assertEqual(self.target_user.edit_projects, 'BPR350,BPR3M03')

    def test_post_clears_edit_projects(self):
        self.target_user.edit_projects = 'BPR350'
        self.target_user.save()
        self.client.post(f'/users/{self.target_user.pk}/edit/', {
            'user_type': 'user',
            'module_permissions': [],
            'permissions_project': '',
            'edit_projects': '',
        })
        self.target_user.refresh_from_db()
        self.assertEqual(self.target_user.edit_projects, '')
```

确认 user_edit URL（可能是 `/users/<id>/edit/`）：

```bash
python manage.py shell -c "from django.urls import reverse; print(reverse('user_edit', args=[1]))"
```

如路径不同，调整测试中的 URL。

- [ ] **Step 2：运行确认失败**

```bash
python manage.py test app01.tests.CompoundListEditProjectSetTest app01.tests.UserEditViewEditProjectsTest -v 2
```

期望：`edit_project_set` not in context，`edit_projects` 不保存。

- [ ] **Step 3：更新 `compound_list` view**

在 `app01/views.py` 的 `compound_list` view 里，`can_delete = ...` 之后加：

```python
    edit_project_set = set(
        p.strip() for p in (request.user.edit_projects or '').split(',') if p.strip()
    )
```

在 `return render(...)` 的 context dict 加：

```python
        'edit_project_set': edit_project_set,
```

- [ ] **Step 4：更新 `user_edit_view`**

在 `app01/views.py` 的 `user_edit_view` POST 分支里，`new_proj = request.POST.get(...)` 之后加：

```python
        old_edit = target.edit_projects
        new_edit = request.POST.get('edit_projects', '').strip()
        target.edit_projects = new_edit
```

在 `target.save()` 调用前，`target.user_type = new_type` 等赋值之后，确认 `target.edit_projects = new_edit` 已赋值（见上一步）。

将 AuditLog `detail` 的 before/after 加入 `edit_projects`：

```python
            detail=_json_mod.dumps({
                'before': {
                    'user_type': old_type,
                    'module_permissions': old_mods,
                    'permissions_project': old_proj,
                    'edit_projects': old_edit,
                },
                'after': {
                    'user_type': new_type,
                    'module_permissions': new_mods,
                    'permissions_project': new_proj,
                    'edit_projects': new_edit,
                },
            }),
```

- [ ] **Step 5：更新 `templates/user_edit.html`**

在"可访问项目"输入框的 `</div>` 之后、`<div style="display:flex;...">` 之前加：

```html
      <div style="margin-bottom:20px;">
        <label style="display:block;font-size:12px;font-weight:600;color:#475569;margin-bottom:5px;">可编辑项目（逗号分隔）</label>
        <input type="text" name="edit_projects" class="ds-form-control"
               value="{{ target.edit_projects }}" style="width:100%;"
               placeholder="如 BPR350,BPR3M03">
      </div>
```

- [ ] **Step 6：运行测试**

```bash
python manage.py test app01.tests.CompoundListEditProjectSetTest app01.tests.UserEditViewEditProjectsTest -v 2
```

期望：全部 `PASS`。

- [ ] **Step 7：提交**

```bash
git add app01/views.py templates/user_edit.html app01/tests.py
git commit -m "feat: add edit_project_set to compound_list context; user_edit handles edit_projects"
```

---

## Task 6：`compound_list.html` 模板 + CSS + JS

**Files:**
- Modify: `templates/compound_list.html`
- Modify: `static/css/design-system.css`
- Modify: `static/js/compound_list.js`

本 task 为纯 UI 变更，无单元测试，步骤末尾有手动测试清单。

- [ ] **Step 1：更新 `compound_list.html` — 体外表格表头**

按设计"按钮对所有人可见"，actions 列始终渲染，去掉 `{% if can_delete %}` 条件。

将体外表格的 `<th>`（约第 109 行）：

```django
{% if can_delete %}<th style="width:56px"></th>{% endif %}
```

改为：

```django
<th style="width:56px"></th>
```

- [ ] **Step 2：更新体外表格行级 actions**

将体外表格的 actions 列（约第 127-136 行）：

```django
      {% if can_delete %}
      <td class="cl-row-actions" onclick="event.stopPropagation()">
        <button class="cl-icon-btn cl-icon-edit"
                onclick="clEditRow('{{ vc.compound.compound_id }}', {{ vc.exp_ids.0 }})"
                title="编辑">✏️</button>
        <button class="cl-icon-btn cl-icon-del"
                onclick="clDeleteRow({{ vc.exp_ids|join:',' }})"
                title="删除">🗑</button>
      </td>
      {% endif %}
```

替换为：

```django
      <td class="cl-row-actions" onclick="event.stopPropagation()">
        {% if can_delete or vc.compound.project in edit_project_set %}
        <button class="cl-icon-btn cl-icon-edit"
                onclick="clEditRow('{{ vc.compound.compound_id }}', {{ vc.exp_ids.0 }})"
                title="编辑">✏️</button>
        <button class="cl-icon-btn cl-icon-del"
                onclick="clDeleteRow({{ vc.exp_ids|join:',' }})"
                title="删除">🗑</button>
        {% else %}
        <button class="cl-icon-btn cl-icon-edit cl-icon-locked"
                onclick="clRequestEditPerm('{{ vc.compound.project }}')"
                title="申请编辑权限">✏️</button>
        <button class="cl-icon-btn cl-icon-del cl-icon-locked"
                onclick="clRequestEditPerm('{{ vc.compound.project }}')"
                title="申请编辑权限">🗑</button>
        {% endif %}
      </td>
```

- [ ] **Step 3：更新体外 expand-row colspan**

columns 现在固定为 10（actions 列始终存在）。将体外 expand-row（约第 138 行）：

```django
<tr class="expand-row"><td colspan="{% if can_delete %}10{% else %}9{% endif %}">
```

改为：

```django
<tr class="expand-row"><td colspan="10">
```

- [ ] **Step 4：对体内（vivo）表格做同样三处修改**

体内表格的 `<th>`（约第 224 行）：

```django
{% if can_delete %}<th style="width:56px"></th>{% endif %}
```
→
```django
<th style="width:56px"></th>
```

体内 actions 列（约第 247-256 行），同 Step 2 结构：

```django
      <td class="cl-row-actions" onclick="event.stopPropagation()">
        {% if can_delete or vc.compound.project in edit_project_set %}
        <button class="cl-icon-btn cl-icon-edit"
                onclick="clEditRow('{{ vc.compound.compound_id }}', {{ vc.exp_ids.0 }})"
                title="编辑">✏️</button>
        <button class="cl-icon-btn cl-icon-del"
                onclick="clDeleteRow({{ vc.exp_ids|join:',' }})"
                title="删除">🗑</button>
        {% else %}
        <button class="cl-icon-btn cl-icon-edit cl-icon-locked"
                onclick="clRequestEditPerm('{{ vc.compound.project }}')"
                title="申请编辑权限">✏️</button>
        <button class="cl-icon-btn cl-icon-del cl-icon-locked"
                onclick="clRequestEditPerm('{{ vc.compound.project }}')"
                title="申请编辑权限">🗑</button>
        {% endif %}
      </td>
```

体内 expand-row colspan（约第 258 行）：
```django
<tr class="expand-row"><td colspan="10">
```

- [ ] **Step 5：加申请 modal HTML**

在 `compound_list.html` 的 `{% endblock %}` 之前（可在已有的 edit modal 下方）加：

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

- [ ] **Step 6：加 `.cl-icon-locked` CSS**

在 `static/css/design-system.css` 里，找到 `.cl-icon-del:hover` 规则之后加：

```css
.cl-icon-locked {
  opacity: 0.35;
  cursor: not-allowed;
}
.cmp-row:hover .cl-icon-locked {
  opacity: 0.6;
  cursor: not-allowed;
}
```

- [ ] **Step 7：加 JS 函数**

在 `static/js/compound_list.js` 末尾加：

```js
// ── 编辑权限申请 modal ──────────────────────────────────────────
function clRequestEditPerm(projectCode) {
  document.getElementById('cl-req-project').textContent    = projectCode;
  document.getElementById('cl-req-project-input').value   = projectCode;
  document.getElementById('cl-req-overlay').style.display = 'block';
  document.getElementById('cl-req-modal').style.display   = 'flex';
}

function clCloseReqModal() {
  document.getElementById('cl-req-overlay').style.display = 'none';
  document.getElementById('cl-req-modal').style.display   = 'none';
}
```

- [ ] **Step 8：手动测试**

启动服务器 `python manage.py runserver`，用两个账号验证：

**有权限用户（can_delete=True 或 edit_projects 含该项目）：**
- 鼠标悬停行 → ✏️/🗑 淡入显示
- 点击 ✏️ → 编辑 modal 弹出，表单有数据
- 点击 🗑 → 确认弹框

**无权限普通用户：**
- 鼠标悬停行 → ✏️/🗑 以半透明（opacity 0.35→0.6）显示，cursor not-allowed
- 点击 ✏️ 或 🗑 → 申请 modal 弹出，显示正确的 project_code
- 点击"申请编辑权限" → 跳转回化合物列表，出现成功提示
- 再次点击申请 → 提示"已在审批中"

- [ ] **Step 9：提交**

```bash
git add templates/compound_list.html static/css/design-system.css static/js/compound_list.js
git commit -m "feat: compound_list row-level edit permission branching, request modal, locked icon style"
```

---

## Task 7：更新 `user_management.html`、`profile.html`

**Files:**
- Modify: `templates/user_management.html`
- Modify: `templates/profile.html`

- [ ] **Step 1：更新 `user_management.html` — 加"权限类型"列**

在 `<thead>` 的 `<th>申请项目</th>` 之后（约第 29 行）加：

```html
<th style="padding:6px 10px;text-align:left;">类型</th>
```

在 `{% for req in pending_requests %}` 的行里，`<td>` 申请项目列之后加：

```html
        <td style="padding:7px 10px;">
          {% if req.request_type == 'edit' %}
          <span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;background:#fed7aa;color:#c2410c;">编辑权限</span>
          {% else %}
          <span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;background:#dbeafe;color:#1d4ed8;">查看权限</span>
          {% endif %}
        </td>
```

- [ ] **Step 2：更新 `profile.html` — 申请记录加"类型"列**

在 `{% for req in access_requests %}` 的每行里，在项目 badge `<td>` 之后、状态 `<td>` 之前加：

```html
          <td style="padding:7px 8px;">
            {% if req.request_type == 'edit' %}
            <span style="background:#fed7aa;color:#c2410c;padding:1px 7px;border-radius:10px;font-size:11px;font-weight:500;">编辑</span>
            {% else %}
            <span style="background:#dbeafe;color:#1d4ed8;padding:1px 7px;border-radius:10px;font-size:11px;font-weight:500;">查看</span>
            {% endif %}
          </td>
```

- [ ] **Step 3：手动验证**

以普通用户提交编辑权限申请后：
- 进入 `/profile/` → 申请记录显示"编辑"橙色标签
- 以 superadmin 进入 `/users/` → 待审批区块显示"编辑权限"橙色标签
- 点击"批准" → 用户 `edit_projects` 更新，`permissions_project` 不变

- [ ] **Step 4：提交**

```bash
git add templates/user_management.html templates/profile.html
git commit -m "feat: show request_type badge in user_management and profile access request lists"
```

---

## 回归测试

- [ ] **运行全量测试确认无回归**

```bash
python manage.py test app01 -v 2
```

期望：所有测试 `PASS`，无 `ERROR`。

- [ ] **提交（如有临时修改）**

如回归测试中有因本次改动导致的失败，修复后提交：

```bash
git add -p
git commit -m "fix: regression fixes for edit permission workflow"
```
