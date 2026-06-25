# Permission System Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 7-tier role system with 3-tier + module permissions, add self-registration auto-grant, project access request workflow, superadmin-only user management page, and audit logging.

**Architecture:** Model layer adds `module_permissions` to `LmsUser` and two new models (`ProjectAccessRequest`, `AuditLog`). Two new helper functions (`_has_module`, `_get_permitted_projects`) replace all scattered `user_type in (...)` checks. Five new views handle user management and project requests. Registration is updated to auto-grant sub_admin. A management command clears all non-superadmin users.

**Tech Stack:** Django 5.1, function-based views, Django `TestCase`, Django management commands, vanilla HTML/CSS templates matching the project design system (`design-system.css`).

---

## File Map

| File | Change |
|------|--------|
| `app01/models.py` | Add `module_permissions` to `LmsUser`; change `user_type` choices; add `ProjectAccessRequest`, `AuditLog` |
| `app01/migrations/0011_permission_redesign.py` | New migration |
| `app01/views.py` | Add `_has_module`, `_get_permitted_projects`; update `register_view`, `batch_delete`, `experiments_bulk_delete`, `experiments_export_csv`, `compound_list`, `smart_upload_view`, `smart_upload_confirm_view`, `user_profile`; add `user_management_view`, `user_edit_view`, `user_delete_view`, `project_request_approve`, `project_request_reject`, `profile_request_project` |
| `app01/tests.py` | New test classes for all new/changed views and helpers |
| `app01/management/__init__.py` | New (empty) |
| `app01/management/commands/__init__.py` | New (empty) |
| `app01/management/commands/reset_users.py` | New management command |
| `bprdb/urls.py` | Add 6 new URL patterns |
| `templates/register.html` | Add project_code field, update subtitle |
| `templates/profile.html` | Add permissions display, project request form, request history |
| `templates/user_management.html` | New page (pending requests + user list + audit log) |
| `templates/base.html` | Update superadmin sidebar link from `/admin/` to `/users/` |
| `templates/compound_list.html` | Add per-row delete button (conditional on `data` module) |
| `static/js/compound_list.js` | Add `clDeleteRow` function |

---

### Task 1: Model changes + migration

**Files:**
- Modify: `app01/models.py`
- Create: `app01/migrations/0011_permission_redesign.py`

**Context:** `LmsUser` currently has `user_type` with 7 choices and no `module_permissions`. The `db_table = 'lms_user'`. We only change the `choices` list (no DB column change) and add a new `module_permissions` column. We also create two new tables.

- [ ] **Step 1: Update `LmsUser` in `app01/models.py`**

Find the `LmsUser` class (line 6). Replace the `USER_TYPE_CHOICES` and `user_type` field, and add `module_permissions`:

Old:
```python
class LmsUser(AbstractUser):
    USER_TYPE_CHOICES = [
        ('guest', 'guest'),
        ('delivery', 'delivery'),
        ('modify', 'modify'),
        ('project', 'project'),
        ('data_admin', 'data_admin'),
        ('admin', 'admin'),
        ('superadmin', 'superadmin'),
    ]
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='guest')
    permissions_project = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'lms_user'
```

New:
```python
class LmsUser(AbstractUser):
    USER_TYPE_CHOICES = [
        ('user',       '普通用户'),
        ('sub_admin',  '模块管理员'),
        ('superadmin', '超级管理员'),
    ]
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='user')
    permissions_project = models.TextField(blank=True, default='')
    module_permissions = models.CharField(
        max_length=64, blank=True, default='',
        help_text="逗号分隔，可选值: upload,data,compound,batch",
    )

    class Meta:
        db_table = 'lms_user'
```

- [ ] **Step 2: Add `ProjectAccessRequest` and `AuditLog` models**

After the `LmsUser` class (before `class SeqModule`), insert:

```python
class ProjectAccessRequest(models.Model):
    STATUS_CHOICES = [
        ('pending',  '待审批'),
        ('approved', '已批准'),
        ('rejected', '已拒绝'),
    ]
    user         = models.ForeignKey(LmsUser, on_delete=models.CASCADE,
                                     related_name='project_requests')
    project_code = models.CharField(max_length=64)
    status       = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    note         = models.TextField(blank=True, default='')
    created_at   = models.DateTimeField(auto_now_add=True)
    reviewed_at  = models.DateTimeField(null=True, blank=True)
    reviewed_by  = models.ForeignKey(LmsUser, null=True, blank=True,
                                     on_delete=models.SET_NULL,
                                     related_name='reviewed_requests')

    class Meta:
        ordering = ['-created_at']


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('register',          '注册'),
        ('project_request',   '申请项目'),
        ('project_approved',  '项目批准'),
        ('project_rejected',  '项目拒绝'),
        ('user_role_changed', '角色变更'),
        ('user_deleted',      '用户删除'),
    ]
    actor       = models.ForeignKey(LmsUser, on_delete=models.SET_NULL,
                                    null=True, related_name='audit_actions')
    action      = models.CharField(max_length=32, choices=ACTION_CHOICES)
    target_user = models.ForeignKey(LmsUser, on_delete=models.SET_NULL,
                                    null=True, blank=True,
                                    related_name='audit_events')
    detail      = models.TextField(default='')
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
```

- [ ] **Step 3: Generate and apply migration**

```bash
source venv/bin/activate
python manage.py makemigrations app01 --name permission_redesign
python manage.py migrate
```

Expected: migration `0011_permission_redesign.py` created and applied cleanly.

- [ ] **Step 4: Verify**

```bash
python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 5: Commit**

```bash
git add app01/models.py app01/migrations/0011_permission_redesign.py
git commit -m "feat: add module_permissions to LmsUser and add ProjectAccessRequest, AuditLog models"
```

---

### Task 2: Permission helpers + tests

**Files:**
- Modify: `app01/views.py` (add two helper functions near top, after imports, before `login_view`)
- Modify: `app01/tests.py`

**Context:** These two helpers replace all scattered `user_type in (...)` checks. They live in `views.py` (not `models.py`) to stay consistent with the existing pattern where view-level logic lives in `views.py`.

- [ ] **Step 1: Write failing tests**

Add to the bottom of `app01/tests.py`:

```python
import json as _json


class HasModuleTest(TestCase):
    def _make_user(self, user_type, module_permissions=''):
        return LmsUser(user_type=user_type, module_permissions=module_permissions)

    def test_superadmin_has_all(self):
        from app01.views import _has_module
        u = self._make_user('superadmin')
        self.assertTrue(_has_module(u, 'upload'))
        self.assertTrue(_has_module(u, 'data'))

    def test_sub_admin_with_module(self):
        from app01.views import _has_module
        u = self._make_user('sub_admin', 'upload,data')
        self.assertTrue(_has_module(u, 'upload'))
        self.assertTrue(_has_module(u, 'data'))
        self.assertFalse(_has_module(u, 'compound'))

    def test_user_has_none(self):
        from app01.views import _has_module
        u = self._make_user('user', 'upload,data')
        self.assertFalse(_has_module(u, 'upload'))

    def test_sub_admin_empty_perms(self):
        from app01.views import _has_module
        u = self._make_user('sub_admin', '')
        self.assertFalse(_has_module(u, 'data'))


class GetPermittedProjectsTest(TestCase):
    def test_superadmin_returns_none(self):
        from app01.views import _get_permitted_projects
        u = LmsUser(user_type='superadmin', permissions_project='BPR350')
        self.assertIsNone(_get_permitted_projects(u))

    def test_regular_user_returns_list(self):
        from app01.views import _get_permitted_projects
        u = LmsUser(user_type='sub_admin', permissions_project='BPR350,BPR3M03')
        result = _get_permitted_projects(u)
        self.assertEqual(result, ['BPR350', 'BPR3M03'])

    def test_empty_permissions_returns_empty_list(self):
        from app01.views import _get_permitted_projects
        u = LmsUser(user_type='user', permissions_project='')
        self.assertEqual(_get_permitted_projects(u), [])
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
source venv/bin/activate
python manage.py test app01.tests.HasModuleTest app01.tests.GetPermittedProjectsTest --noinput
```

Expected: `ImportError: cannot import name '_has_module'`

- [ ] **Step 3: Add helpers to `app01/views.py`**

Immediately before `def login_view(request):` (line 26), insert:

```python
def _has_module(user, module: str) -> bool:
    if user.is_superuser or user.user_type == 'superadmin':
        return True
    if user.user_type == 'sub_admin':
        return module in (user.module_permissions or '').split(',')
    return False


def _get_permitted_projects(user):
    if user.is_superuser or user.user_type == 'superadmin':
        return None
    return [p.strip() for p in (user.permissions_project or '').split(',') if p.strip()]
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
python manage.py test app01.tests.HasModuleTest app01.tests.GetPermittedProjectsTest --noinput
```

Expected: `OK (7 tests)`.

- [ ] **Step 5: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "feat: add _has_module and _get_permitted_projects permission helpers"
```

---

### Task 3: Update existing permission checks

**Files:**
- Modify: `app01/views.py` (lines 57, ~1459–1465, ~1484)

**Context:** Three locations check `user_type` directly; replace with helpers. The `batch_delete` view at ~line 1459 uses `in ('data_admin', 'admin', 'superadmin')`.

- [ ] **Step 1: Update `register_view` (line 57)**

Find:
```python
        LmsUser.objects.create_user(username=username, password=password, user_type='guest')
        from django.contrib import messages
        messages.success(request, f'账号 {username} 注册成功，请登录（初始权限为 guest，联系管理员升级）')
```

Replace with:
```python
        LmsUser.objects.create_user(username=username, password=password,
                                     user_type='guest')  # temporary; Task 6 upgrades this
        from django.contrib import messages
        messages.success(request, f'账号 {username} 注册成功，请登录')
```

Note: The actual upgrade to `sub_admin` and project handling happens in Task 6. This step just removes the old message.

- [ ] **Step 2: Update `batch_delete` (find with grep)**

```bash
grep -n "data_admin.*admin.*superadmin\|in.*data_admin" app01/views.py
```

Find the `batch_delete` permission block. It reads:
```python
    allowed = (
        user.is_superuser
        or getattr(user, 'user_type', '') in ('data_admin', 'admin', 'superadmin')
    )
    if not allowed:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('权限不足，需要 data_admin 或以上角色')
```

Replace with:
```python
    if not _has_module(user, 'data'):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('权限不足')
```

- [ ] **Step 3: Update `experiments_bulk_delete`**

Find:
```python
    allowed = (
        request.user.is_superuser
        or getattr(request.user, 'user_type', '') in ('data_admin', 'admin', 'superadmin')
    )
    if not allowed:
        return JsonResponse({'error': '权限不足'}, status=403)
```

Replace with:
```python
    if not _has_module(request.user, 'data'):
        return JsonResponse({'error': '权限不足'}, status=403)
```

- [ ] **Step 4: Update `experiments_export_csv`**

Find (a few lines after `experiments_bulk_delete`):
```python
    allowed = (
        request.user.is_superuser
        or getattr(request.user, 'user_type', '') in ('data_admin', 'admin', 'superadmin')
    )
    if not allowed:
        return JsonResponse({'error': '权限不足'}, status=403)
```

Replace with:
```python
    if not _has_module(request.user, 'data'):
        return JsonResponse({'error': '权限不足'}, status=403)
```

- [ ] **Step 5: Write tests for updated checks**

Add to `app01/tests.py`:

```python
class HasModulePermissionCheckTest(TestCase):
    def _make_experiment(self):
        c = Compound.objects.create(compound_id='BPR350-PERM01')
        exp = Experiment.objects.create(
            compound=c, exp_type='in_vitro', assay_name='perm test', batch_label='2099-PM'
        )
        DataPoint.objects.create(
            experiment=exp, x_value=1.0, x_type='concentration',
            replicate='Mean', value=0.5, readout_type='mRNA_remaining'
        )
        return exp

    def test_user_cannot_bulk_delete(self):
        self._make_experiment()
        exp = Experiment.objects.first()
        LmsUser.objects.create_user(username='u_plain', password='pass', user_type='user')
        self.client.login(username='u_plain', password='pass')
        r = self.client.post(
            '/api/experiments/bulk-delete/',
            data=_json.dumps({'exp_ids': [exp.id]}),
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 403)

    def test_sub_admin_with_data_can_bulk_delete(self):
        self._make_experiment()
        exp = Experiment.objects.first()
        LmsUser.objects.create_user(
            username='u_data', password='pass', user_type='sub_admin',
            module_permissions='data'
        )
        self.client.login(username='u_data', password='pass')
        r = self.client.post(
            '/api/experiments/bulk-delete/',
            data=_json.dumps({'exp_ids': [exp.id]}),
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 200)

    def test_sub_admin_without_data_cannot_bulk_delete(self):
        self._make_experiment()
        exp = Experiment.objects.first()
        LmsUser.objects.create_user(
            username='u_upload', password='pass', user_type='sub_admin',
            module_permissions='upload'
        )
        self.client.login(username='u_upload', password='pass')
        r = self.client.post(
            '/api/experiments/bulk-delete/',
            data=_json.dumps({'exp_ids': [exp.id]}),
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 403)
```

- [ ] **Step 6: Run tests**

```bash
python manage.py test app01.tests.HasModulePermissionCheckTest --noinput
```

Expected: `OK (3 tests)`.

- [ ] **Step 7: Run full suite to confirm no regressions**

```bash
python manage.py test app01 --noinput
```

Expected: known pre-existing failures only (`CompoundListViewTest.test_compound_data_in_context`, `ParseBodyWeightFileTest.test_time_unit_unknown_positive_only`). No new failures.

- [ ] **Step 8: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "feat: replace user_type role checks with _has_module helper in batch_delete, bulk_delete, export_csv"
```

---

### Task 4: Project-level filtering in compound_list

**Files:**
- Modify: `app01/views.py` (`compound_list` view, around line 1194)
- Modify: `app01/tests.py`

**Context:** Currently `compound_list` shows all experiments regardless of `permissions_project`. We add a filter so non-superadmin users only see their permitted projects.

- [ ] **Step 1: Write failing test**

Add to `app01/tests.py`:

```python
class CompoundListProjectFilterTest(TestCase):
    def setUp(self):
        self.c_a = Compound.objects.create(compound_id='BPR350-FILT01', project='BPR350')
        self.c_b = Compound.objects.create(compound_id='BPR3M03-FILT01', project='BPR3M03')
        Experiment.objects.create(
            compound=self.c_a, exp_type='in_vitro', assay_name='test', batch_label='B-FILT-A'
        )
        Experiment.objects.create(
            compound=self.c_b, exp_type='in_vitro', assay_name='test', batch_label='B-FILT-B'
        )

    def test_user_sees_only_permitted_project(self):
        u = LmsUser.objects.create_user(
            username='u_filt', password='pass',
            user_type='sub_admin', permissions_project='BPR350',
            module_permissions='upload,data,compound,batch'
        )
        self.client.login(username='u_filt', password='pass')
        r = self.client.get('/compounds/')
        self.assertEqual(r.status_code, 200)
        projects = r.context['all_projects']
        self.assertIn('BPR350', projects)
        self.assertNotIn('BPR3M03', projects)

    def test_superadmin_sees_all_projects(self):
        u = LmsUser.objects.create_user(
            username='u_super', password='pass', user_type='superadmin'
        )
        u.is_superuser = True
        u.save()
        self.client.login(username='u_super', password='pass')
        r = self.client.get('/compounds/')
        projects = r.context['all_projects']
        self.assertIn('BPR350', projects)
        self.assertIn('BPR3M03', projects)
```

- [ ] **Step 2: Run test — verify it fails**

```bash
python manage.py test app01.tests.CompoundListProjectFilterTest --noinput
```

Expected: `FAIL` (user sees both projects).

- [ ] **Step 3: Add filtering to `compound_list`**

In `app01/views.py`, find the `compound_list` view. After `exp_qs = (...)` (around line 1194), add immediately after the `.order_by(...)` line but **before** the first `if q:` block:

```python
    # Project-level enforcement
    _permitted = _get_permitted_projects(request.user)
    if _permitted is not None:
        exp_qs = exp_qs.filter(compound__project__in=_permitted)
```

Also find where `all_projects` is built (around line 1248):
```python
    all_projects = sorted(
        Compound.objects.exclude(project='').order_by().values_list('project', flat=True).distinct()
    )
```

Replace with:
```python
    _proj_qs = Compound.objects.exclude(project='').order_by()
    if _permitted is not None:
        _proj_qs = _proj_qs.filter(project__in=_permitted)
    all_projects = sorted(_proj_qs.values_list('project', flat=True).distinct())
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
python manage.py test app01.tests.CompoundListProjectFilterTest --noinput
```

Expected: `OK (2 tests)`.

- [ ] **Step 5: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "feat: enforce project-level filtering in compound_list based on permissions_project"
```

---

### Task 5: Upload view protection

**Files:**
- Modify: `app01/views.py` (`smart_upload_view`, `smart_upload_confirm_view`)
- Modify: `app01/tests.py`

- [ ] **Step 1: Write failing tests**

Add to `app01/tests.py`:

```python
class UploadModulePermissionTest(TestCase):
    def test_user_without_upload_module_is_redirected(self):
        LmsUser.objects.create_user(
            username='u_noup', password='pass', user_type='sub_admin',
            module_permissions='data'
        )
        self.client.login(username='u_noup', password='pass')
        r = self.client.get('/upload/smart/')
        self.assertRedirects(r, '/compounds/', fetch_redirect_response=False)

    def test_sub_admin_with_upload_can_access(self):
        LmsUser.objects.create_user(
            username='u_up', password='pass', user_type='sub_admin',
            module_permissions='upload'
        )
        self.client.login(username='u_up', password='pass')
        r = self.client.get('/upload/smart/')
        self.assertEqual(r.status_code, 200)

    def test_superadmin_can_access(self):
        u = LmsUser.objects.create_user(
            username='u_sa', password='pass', user_type='superadmin'
        )
        u.is_superuser = True
        u.save()
        self.client.login(username='u_sa', password='pass')
        r = self.client.get('/upload/smart/')
        self.assertEqual(r.status_code, 200)
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
python manage.py test app01.tests.UploadModulePermissionTest --noinput
```

Expected: `FAIL` (user without upload can access).

- [ ] **Step 3: Add guard to `smart_upload_view`**

In `app01/views.py`, find `def smart_upload_view(request):`. Insert as the first lines of the function body (after any existing docstring):

```python
    if not _has_module(request.user, 'upload'):
        messages.error(request, '权限不足，无法访问上传页面')
        return redirect('compound_list')
```

- [ ] **Step 4: Add guard to `smart_upload_confirm_view`**

Find `def smart_upload_confirm_view(request):`. Insert as the first lines:

```python
    if not _has_module(request.user, 'upload'):
        messages.error(request, '权限不足，无法访问上传页面')
        return redirect('compound_list')
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
python manage.py test app01.tests.UploadModulePermissionTest --noinput
```

Expected: `OK (3 tests)`.

- [ ] **Step 6: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "feat: guard smart_upload_view and smart_upload_confirm_view with upload module check"
```

---

### Task 6: Registration with project code + AuditLog

**Files:**
- Modify: `app01/views.py` (`register_view`)
- Modify: `templates/register.html`
- Modify: `app01/tests.py`

**Context:** Registration should auto-grant `sub_admin` with all four modules for the declared project. Also write an `AuditLog` entry. The `AuditLog` model needs to be imported in `views.py`.

- [ ] **Step 1: Write failing tests**

Add to `app01/tests.py`:

```python
from app01.models import (
    Compound, Strand, Experiment, DataPoint,
    ExperimentSummary, _parse_compound_id, LmsUser,
    ExperimentAttachment, ProjectAccessRequest, AuditLog,
)


class RegisterViewTest(TestCase):
    def test_register_creates_sub_admin(self):
        r = self.client.post('/register/', {
            'username': 'newuser',
            'password': 'pass123',
            'confirm_password': 'pass123',
            'project_code': 'BPR350',
        })
        self.assertRedirects(r, '/login/', fetch_redirect_response=False)
        u = LmsUser.objects.get(username='newuser')
        self.assertEqual(u.user_type, 'sub_admin')
        self.assertEqual(u.module_permissions, 'upload,data,compound,batch')
        self.assertEqual(u.permissions_project, 'BPR350')

    def test_register_without_project(self):
        self.client.post('/register/', {
            'username': 'newuser2',
            'password': 'pass123',
            'confirm_password': 'pass123',
            'project_code': '',
        })
        u = LmsUser.objects.get(username='newuser2')
        self.assertEqual(u.permissions_project, '')

    def test_register_writes_audit_log(self):
        self.client.post('/register/', {
            'username': 'newuser3',
            'password': 'pass123',
            'confirm_password': 'pass123',
            'project_code': 'BPR3M03',
        })
        u = LmsUser.objects.get(username='newuser3')
        log = AuditLog.objects.filter(actor=u, action='register').first()
        self.assertIsNotNone(log)
        self.assertIn('BPR3M03', log.detail)
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
python manage.py test app01.tests.RegisterViewTest --noinput
```

Expected: `FAIL` (user gets `user_type='guest'` currently, `AuditLog` import error).

- [ ] **Step 3: Update imports in `app01/tests.py`**

Find the existing import block at the top of `app01/tests.py`:
```python
from app01.models import (
    Compound, Strand, Experiment, DataPoint,
    ExperimentSummary, _parse_compound_id, LmsUser,
    ExperimentAttachment,
)
```

Replace with:
```python
from app01.models import (
    Compound, Strand, Experiment, DataPoint,
    ExperimentSummary, _parse_compound_id, LmsUser,
    ExperimentAttachment, ProjectAccessRequest, AuditLog,
)
```

- [ ] **Step 4: Update `register_view` in `app01/views.py`**

Find the register_view's success block:
```python
        LmsUser.objects.create_user(username=username, password=password,
                                     user_type='guest')  # temporary; Task 6 upgrades this
        from django.contrib import messages
        messages.success(request, f'账号 {username} 注册成功，请登录')
        return redirect('login')
```

Replace with:
```python
        project_code = request.POST.get('project_code', '').strip()
        new_user = LmsUser.objects.create_user(
            username=username, password=password,
            user_type='sub_admin',
            module_permissions='upload,data,compound,batch',
            permissions_project=project_code,
        )
        from app01.models import AuditLog
        import json as _json_mod
        AuditLog.objects.create(
            actor=new_user,
            action='register',
            detail=_json_mod.dumps({'project': project_code}),
        )
        from django.contrib import messages
        messages.success(request, f'账号 {username} 注册成功，请登录')
        return redirect('login')
```

- [ ] **Step 5: Update `templates/register.html`**

Find the confirm_password field block and add project_code field after it, before the submit button:

Old (the closing `</div>` before the submit button):
```html
    <div style="margin-bottom:20px;">
      <label style="display:block;font-size:13px;font-weight:500;color:#374151;margin-bottom:5px;" for="confirm_password">
        <i class="bi bi-lock-fill"></i> 确认密码
      </label>
      <input type="password" class="ds-form-control" id="confirm_password" name="confirm_password"
             placeholder="再次输入密码" required style="width:100%;box-sizing:border-box;">
    </div>
    <button type="submit" class="ds-btn ds-btn-primary" style="width:100%;justify-content:center;">注册</button>
```

New:
```html
    <div style="margin-bottom:20px;">
      <label style="display:block;font-size:13px;font-weight:500;color:#374151;margin-bottom:5px;" for="confirm_password">
        <i class="bi bi-lock-fill"></i> 确认密码
      </label>
      <input type="password" class="ds-form-control" id="confirm_password" name="confirm_password"
             placeholder="再次输入密码" required style="width:100%;box-sizing:border-box;">
    </div>
    <div style="margin-bottom:20px;">
      <label style="display:block;font-size:13px;font-weight:500;color:#374151;margin-bottom:5px;" for="project_code">
        <i class="bi bi-folder2"></i> 项目代码 <span style="color:#94a3b8;font-weight:400;">（可选）</span>
      </label>
      <input type="text" class="ds-form-control" id="project_code" name="project_code"
             placeholder="如 BPR350、BPR3T05" style="width:100%;box-sizing:border-box;">
      <div style="font-size:11px;color:#94a3b8;margin-top:4px;">填写后自动获得该项目的完整操作权限，无需等待审批</div>
    </div>
    <button type="submit" class="ds-btn ds-btn-primary" style="width:100%;justify-content:center;">注册</button>
```

Also update the subtitle line:
Old:
```html
  <div class="ds-standalone-sub">注册后初始权限为 guest，联系管理员升级</div>
```
New:
```html
  <div class="ds-standalone-sub">注册即可开始使用，填写项目代码自动获得权限</div>
```

- [ ] **Step 6: Run tests — verify they pass**

```bash
python manage.py test app01.tests.RegisterViewTest --noinput
```

Expected: `OK (3 tests)`.

- [ ] **Step 7: Commit**

```bash
git add app01/views.py templates/register.html app01/tests.py
git commit -m "feat: registration auto-grants sub_admin with all modules and writes AuditLog"
```

---

### Task 7: User management view (superadmin only)

**Files:**
- Modify: `app01/views.py` (add `user_management_view`)
- Create: `templates/user_management.html`
- Modify: `app01/tests.py`
- Modify: `bprdb/urls.py`

- [ ] **Step 1: Write failing tests**

Add to `app01/tests.py`:

```python
class UserManagementViewTest(TestCase):
    def setUp(self):
        self.superadmin = LmsUser.objects.create_user(
            username='sadmin', password='pass', user_type='superadmin'
        )
        self.superadmin.is_superuser = True
        self.superadmin.save()
        self.regular = LmsUser.objects.create_user(
            username='regular', password='pass', user_type='sub_admin',
            module_permissions='data'
        )

    def test_superadmin_can_access(self):
        self.client.login(username='sadmin', password='pass')
        r = self.client.get('/users/')
        self.assertEqual(r.status_code, 200)

    def test_regular_user_gets_403(self):
        self.client.login(username='regular', password='pass')
        r = self.client.get('/users/')
        self.assertEqual(r.status_code, 403)

    def test_anonymous_redirected(self):
        r = self.client.get('/users/')
        self.assertIn(r.status_code, [302, 403])

    def test_pending_requests_in_context(self):
        ProjectAccessRequest.objects.create(
            user=self.regular, project_code='BPR350', status='pending'
        )
        self.client.login(username='sadmin', password='pass')
        r = self.client.get('/users/')
        self.assertIn('pending_requests', r.context)
        self.assertEqual(r.context['pending_requests'].count(), 1)
```

- [ ] **Step 2: Add URL**

In `bprdb/urls.py`, add inside `urlpatterns` (before the closing `]`):

```python
path('users/', views.user_management_view, name='user_management'),
```

- [ ] **Step 3: Add view to `app01/views.py`**

At the end of `app01/views.py` (before `attachment_download`), insert:

```python
@login_required
def user_management_view(request):
    if not (request.user.is_superuser or request.user.user_type == 'superadmin'):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('此页面仅 superadmin 可访问')
    from app01.models import ProjectAccessRequest, AuditLog
    pending_requests = ProjectAccessRequest.objects.filter(status='pending').select_related('user')
    all_users = LmsUser.objects.all().order_by('date_joined')
    audit_logs = AuditLog.objects.select_related('actor', 'target_user')[:30]
    return render(request, 'user_management.html', {
        'pending_requests': pending_requests,
        'all_users': all_users,
        'audit_logs': audit_logs,
    })
```

- [ ] **Step 4: Create `templates/user_management.html`**

```html
{% extends "base.html" %}
{% block page_title %} — 用户管理{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">用户管理</span>
  <span class="ds-count-badge">{{ all_users.count }} 用户</span>
  <div class="ds-topbar-spacer"></div>
  <span style="font-size:11px;color:#92400e;background:#fef3c7;padding:3px 10px;border-radius:20px;border:1px solid #fde68a;">superadmin 专属</span>
{% endblock %}

{% block content %}
<div style="display:flex;flex-direction:column;gap:14px;max-width:960px;">

  {# ── Pending requests ── #}
  {% if pending_requests %}
  <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:12px;overflow:hidden;">
    <div style="padding:10px 16px;border-bottom:1px solid #fde68a;display:flex;align-items:center;gap:8px;">
      <span style="font-size:13px;font-weight:600;color:#92400e;">⏳ 待审批的项目申请</span>
      <span style="background:#f59e0b;color:#fff;font-size:11px;border-radius:10px;padding:1px 7px;">{{ pending_requests.count }}</span>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:12px;">
      <thead><tr style="background:#fef9c3;color:#92400e;">
        <th style="padding:6px 12px;text-align:left;font-weight:600;">用户</th>
        <th style="padding:6px 12px;text-align:left;font-weight:600;">申请项目</th>
        <th style="padding:6px 12px;text-align:left;font-weight:600;">申请时间</th>
        <th style="padding:6px 12px;text-align:left;font-weight:600;">操作</th>
      </tr></thead>
      <tbody>
        {% for req in pending_requests %}
        <tr style="border-top:1px solid #fde68a;">
          <td style="padding:8px 12px;font-weight:600;color:#0f172a;">{{ req.user.username }}</td>
          <td style="padding:8px 12px;">
            <span style="background:#ede9fe;color:#6d28d9;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:500;">{{ req.project_code }}</span>
          </td>
          <td style="padding:8px 12px;color:#94a3b8;font-family:monospace;font-size:11px;">{{ req.created_at|date:"Y-m-d H:i" }}</td>
          <td style="padding:8px 12px;display:flex;gap:6px;">
            <form method="post" action="{% url 'project_request_approve' req.id %}" style="display:inline;">
              {% csrf_token %}
              <button type="submit" class="ds-btn ds-btn-green" style="font-size:11px;padding:3px 12px;">批准</button>
            </form>
            <form method="post" action="{% url 'project_request_reject' req.id %}" style="display:inline;">
              {% csrf_token %}
              <button type="submit" class="ds-btn ds-btn-danger" style="font-size:11px;padding:3px 12px;">拒绝</button>
            </form>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% endif %}

  {# ── User list ── #}
  <div style="background:#fff;border:1px solid #eef2f7;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(15,23,42,0.05);">
    <div style="padding:12px 16px;border-bottom:1px solid #f1f5f9;">
      <span style="font-size:13px;font-weight:600;color:#0f172a;">用户列表</span>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:12px;">
      <thead><tr style="background:#f8fafc;color:#94a3b8;">
        <th style="padding:7px 12px;text-align:left;font-size:11px;font-weight:600;text-transform:uppercase;">用户名</th>
        <th style="padding:7px 12px;text-align:left;font-size:11px;font-weight:600;text-transform:uppercase;">角色</th>
        <th style="padding:7px 12px;text-align:left;font-size:11px;font-weight:600;text-transform:uppercase;">模块权限</th>
        <th style="padding:7px 12px;text-align:left;font-size:11px;font-weight:600;text-transform:uppercase;">可访问项目</th>
        <th style="padding:7px 12px;text-align:left;font-size:11px;font-weight:600;text-transform:uppercase;">操作</th>
      </tr></thead>
      <tbody>
        {% for u in all_users %}
        <tr style="border-bottom:1px solid #f4f7fb;">
          <td style="padding:9px 12px;font-weight:600;color:#0f172a;">{{ u.username }}</td>
          <td style="padding:9px 12px;">
            {% if u.user_type == 'superadmin' %}
              <span style="background:#fee2e2;color:#dc2626;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:500;">superadmin</span>
            {% elif u.user_type == 'sub_admin' %}
              <span style="background:#fef3c7;color:#92400e;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:500;">sub_admin</span>
            {% else %}
              <span style="background:#f1f5f9;color:#475569;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:500;">user</span>
            {% endif %}
          </td>
          <td style="padding:9px 12px;">
            {% if u.user_type == 'superadmin' %}
              <span style="color:#94a3b8;font-size:11px;">全部</span>
            {% else %}
              {% for mod in u.module_permissions.split(',') %}{% if mod %}
                <span style="background:#f1f5f9;color:#475569;padding:1px 6px;border-radius:4px;font-size:10.5px;font-weight:500;margin-right:2px;">{{ mod }}</span>
              {% endif %}{% endfor %}
              {% if not u.module_permissions %}<span style="color:#94a3b8;font-size:11px;">—</span>{% endif %}
            {% endif %}
          </td>
          <td style="padding:9px 12px;">
            {% if u.user_type == 'superadmin' %}
              <span style="color:#94a3b8;font-size:11px;font-style:italic;">全部项目</span>
            {% else %}
              {% for proj in u.permissions_project.split(',') %}{% if proj %}
                <span style="background:#ede9fe;color:#6d28d9;padding:1px 6px;border-radius:4px;font-size:11px;font-weight:500;margin-right:2px;">{{ proj|strip }}</span>
              {% endif %}{% endfor %}
              {% if not u.permissions_project %}<span style="color:#94a3b8;font-size:11px;">—</span>{% endif %}
            {% endif %}
          </td>
          <td style="padding:9px 12px;">
            {% if u.user_type != 'superadmin' %}
            <div style="display:flex;gap:6px;">
              <a href="{% url 'user_edit' u.id %}" class="ds-btn ds-btn-ghost" style="font-size:11px;padding:3px 10px;">编辑</a>
              <form method="post" action="{% url 'user_delete' u.id %}" style="display:inline;"
                    onsubmit="return confirm('确认删除用户 {{ u.username }}？')">
                {% csrf_token %}
                <button type="submit" class="ds-btn ds-btn-danger" style="font-size:11px;padding:3px 10px;">删除</button>
              </form>
            </div>
            {% endif %}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  {# ── Audit log ── #}
  <div style="background:#fff;border:1px solid #eef2f7;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(15,23,42,0.05);">
    <div style="padding:12px 16px;border-bottom:1px solid #f1f5f9;display:flex;align-items:center;gap:8px;">
      <span style="font-size:13px;font-weight:600;color:#0f172a;">操作日志</span>
      <span style="font-family:monospace;font-size:11px;font-weight:500;color:#94a3b8;background:#f1f5f9;border:1px solid #e8edf4;padding:2px 8px;border-radius:20px;">近 30 条</span>
    </div>
    {% for log in audit_logs %}
    <div style="display:flex;align-items:flex-start;gap:10px;padding:7px 16px;border-bottom:1px solid #f4f7fb;font-size:12px;">
      <span style="font-family:monospace;font-size:10.5px;color:#94a3b8;white-space:nowrap;margin-top:2px;">{{ log.created_at|date:"Y-m-d H:i" }}</span>
      {% if log.action == 'register' %}
        <span style="background:#dcfce7;color:#166534;padding:1px 6px;border-radius:3px;font-size:10.5px;font-weight:500;flex-shrink:0;">register</span>
      {% elif log.action == 'project_request' %}
        <span style="background:#dbeafe;color:#1e40af;padding:1px 6px;border-radius:3px;font-size:10.5px;font-weight:500;flex-shrink:0;">project_request</span>
      {% elif log.action == 'project_approved' %}
        <span style="background:#dcfce7;color:#166534;padding:1px 6px;border-radius:3px;font-size:10.5px;font-weight:500;flex-shrink:0;">approved</span>
      {% elif log.action == 'project_rejected' %}
        <span style="background:#fee2e2;color:#dc2626;padding:1px 6px;border-radius:3px;font-size:10.5px;font-weight:500;flex-shrink:0;">rejected</span>
      {% elif log.action == 'user_role_changed' %}
        <span style="background:#fef3c7;color:#92400e;padding:1px 6px;border-radius:3px;font-size:10.5px;font-weight:500;flex-shrink:0;">role_changed</span>
      {% else %}
        <span style="background:#f1f5f9;color:#475569;padding:1px 6px;border-radius:3px;font-size:10.5px;font-weight:500;flex-shrink:0;">{{ log.action }}</span>
      {% endif %}
      <span style="color:#475569;line-height:1.4;">
        {% if log.actor %}{{ log.actor.username }}{% endif %}
        {% if log.target_user %} → {{ log.target_user.username }}{% endif %}
        {% if log.detail %}: {{ log.detail }}{% endif %}
      </span>
    </div>
    {% empty %}
    <div style="padding:16px;color:#94a3b8;font-size:12px;text-align:center;">暂无日志</div>
    {% endfor %}
  </div>

</div>
{% endblock %}
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
python manage.py test app01.tests.UserManagementViewTest --noinput
```

Expected: `OK (4 tests)`.

- [ ] **Step 6: Update sidebar in `templates/base.html`**

Find:
```html
    <a href="/admin/" class="ds-nav-item">
      <i class="bi bi-people ds-nav-icon"></i> 用户管理
    </a>
```

Replace with:
```html
    <a href="{% url 'user_management' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'user_management' %}active{% endif %}">
      <i class="bi bi-people ds-nav-icon"></i> 用户管理
    </a>
```

- [ ] **Step 7: Commit**

```bash
git add app01/views.py templates/user_management.html templates/base.html bprdb/urls.py app01/tests.py
git commit -m "feat: add user_management_view and template (superadmin only)"
```

---

### Task 8: User edit and delete views

**Files:**
- Modify: `app01/views.py`
- Create: `templates/user_edit.html`
- Modify: `bprdb/urls.py`
- Modify: `app01/tests.py`

- [ ] **Step 1: Write failing tests**

Add to `app01/tests.py`:

```python
class UserEditDeleteTest(TestCase):
    def setUp(self):
        self.sadmin = LmsUser.objects.create_user(
            username='sa2', password='pass', user_type='superadmin'
        )
        self.sadmin.is_superuser = True
        self.sadmin.save()
        self.target = LmsUser.objects.create_user(
            username='target', password='pass', user_type='sub_admin',
            module_permissions='data', permissions_project='BPR350'
        )

    def test_edit_changes_role_and_modules(self):
        self.client.login(username='sa2', password='pass')
        r = self.client.post(f'/users/{self.target.id}/edit/', {
            'user_type': 'user',
            'module_permissions': '',
            'permissions_project': 'BPR3M03',
        })
        self.assertRedirects(r, '/users/', fetch_redirect_response=False)
        self.target.refresh_from_db()
        self.assertEqual(self.target.user_type, 'user')
        self.assertEqual(self.target.permissions_project, 'BPR3M03')

    def test_edit_writes_audit_log(self):
        self.client.login(username='sa2', password='pass')
        self.client.post(f'/users/{self.target.id}/edit/', {
            'user_type': 'user',
            'module_permissions': '',
            'permissions_project': '',
        })
        log = AuditLog.objects.filter(action='user_role_changed', target_user=self.target).first()
        self.assertIsNotNone(log)

    def test_non_superadmin_cannot_edit(self):
        u = LmsUser.objects.create_user(username='plain', password='pass', user_type='sub_admin')
        self.client.login(username='plain', password='pass')
        r = self.client.post(f'/users/{self.target.id}/edit/', {
            'user_type': 'user', 'module_permissions': '', 'permissions_project': ''
        })
        self.assertEqual(r.status_code, 403)

    def test_delete_removes_user(self):
        self.client.login(username='sa2', password='pass')
        target_id = self.target.id
        r = self.client.post(f'/users/{target_id}/delete/')
        self.assertRedirects(r, '/users/', fetch_redirect_response=False)
        self.assertFalse(LmsUser.objects.filter(id=target_id).exists())

    def test_delete_writes_audit_log(self):
        self.client.login(username='sa2', password='pass')
        username = self.target.username
        self.client.post(f'/users/{self.target.id}/delete/')
        log = AuditLog.objects.filter(action='user_deleted').first()
        self.assertIsNotNone(log)
        self.assertIn(username, log.detail)
```

- [ ] **Step 2: Add URLs**

In `bprdb/urls.py`, add:

```python
path('users/<int:user_id>/edit/', views.user_edit_view, name='user_edit'),
path('users/<int:user_id>/delete/', views.user_delete_view, name='user_delete'),
```

- [ ] **Step 3: Add views to `app01/views.py`**

After `user_management_view`, insert:

```python
@login_required
def user_edit_view(request, user_id):
    if not (request.user.is_superuser or request.user.user_type == 'superadmin'):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('此操作仅 superadmin 可执行')
    from app01.models import AuditLog
    target = get_object_or_404(LmsUser, id=user_id)
    if request.method == 'POST':
        old_type = target.user_type
        old_mods = target.module_permissions
        old_proj = target.permissions_project
        new_type = request.POST.get('user_type', target.user_type)
        new_mods = ','.join(m.strip() for m in request.POST.getlist('module_permissions') if m.strip())
        new_proj = request.POST.get('permissions_project', '').strip()
        target.user_type = new_type
        target.module_permissions = new_mods
        target.permissions_project = new_proj
        target.save()
        import json as _json_mod
        AuditLog.objects.create(
            actor=request.user,
            action='user_role_changed',
            target_user=target,
            detail=_json_mod.dumps({
                'before': {'user_type': old_type, 'module_permissions': old_mods, 'permissions_project': old_proj},
                'after':  {'user_type': new_type, 'module_permissions': new_mods, 'permissions_project': new_proj},
            }),
        )
        messages.success(request, f'用户 {target.username} 已更新')
        return redirect('user_management')
    return render(request, 'user_edit.html', {'target': target})


@login_required
def user_delete_view(request, user_id):
    if not (request.user.is_superuser or request.user.user_type == 'superadmin'):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('此操作仅 superadmin 可执行')
    if request.method != 'POST':
        return redirect('user_management')
    from app01.models import AuditLog
    target = get_object_or_404(LmsUser, id=user_id)
    import json as _json_mod
    username = target.username
    AuditLog.objects.create(
        actor=request.user,
        action='user_deleted',
        detail=_json_mod.dumps({'username': username}),
    )
    target.delete()
    messages.success(request, f'用户 {username} 已删除')
    return redirect('user_management')
```

- [ ] **Step 4: Add `get_object_or_404` import to `app01/views.py`**

Check the top of `app01/views.py` for existing imports. Find the Django imports line and add `get_object_or_404` if not already present:

```bash
grep -n "get_object_or_404\|from django.shortcuts" app01/views.py | head -5
```

If not present, find `from django.shortcuts import render, redirect` and add `get_object_or_404`:
```python
from django.shortcuts import render, redirect, get_object_or_404
```

- [ ] **Step 5: Create `templates/user_edit.html`**

```html
{% extends "base.html" %}
{% block page_title %} — 编辑用户{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">编辑用户：{{ target.username }}</span>
{% endblock %}

{% block content %}
<div style="max-width:480px;">
  <div style="background:#fff;border:1px solid #eef2f7;border-radius:12px;padding:24px;box-shadow:0 1px 4px rgba(15,23,42,0.05);">
    <form method="post">
      {% csrf_token %}

      <div style="margin-bottom:16px;">
        <label style="display:block;font-size:12px;font-weight:600;color:#475569;margin-bottom:5px;">角色</label>
        <select name="user_type" class="ds-form-control" style="width:100%;">
          <option value="user" {% if target.user_type == 'user' %}selected{% endif %}>user — 普通用户</option>
          <option value="sub_admin" {% if target.user_type == 'sub_admin' %}selected{% endif %}>sub_admin — 模块管理员</option>
          <option value="superadmin" {% if target.user_type == 'superadmin' %}selected{% endif %}>superadmin — 超级管理员</option>
        </select>
      </div>

      <div style="margin-bottom:16px;">
        <label style="display:block;font-size:12px;font-weight:600;color:#475569;margin-bottom:6px;">模块权限（sub_admin 时生效）</label>
        {% for mod in 'upload,data,compound,batch'|split:',' %}
        <label style="display:inline-flex;align-items:center;gap:5px;margin-right:14px;font-size:12px;cursor:pointer;">
          <input type="checkbox" name="module_permissions" value="{{ mod }}"
                 {% if mod in target.module_permissions %}checked{% endif %}>
          {{ mod }}
        </label>
        {% endfor %}
      </div>

      <div style="margin-bottom:20px;">
        <label style="display:block;font-size:12px;font-weight:600;color:#475569;margin-bottom:5px;">可访问项目（逗号分隔）</label>
        <input type="text" name="permissions_project" class="ds-form-control"
               value="{{ target.permissions_project }}" style="width:100%;"
               placeholder="如 BPR350,BPR3M03">
      </div>

      <div style="display:flex;gap:8px;">
        <button type="submit" class="ds-btn ds-btn-primary">保存</button>
        <a href="{% url 'user_management' %}" class="ds-btn ds-btn-ghost">取消</a>
      </div>
    </form>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 6: Add `split` template filter**

The template above uses `'upload,data,compound,batch'|split:','`. This requires a custom template filter. Check if one exists:

```bash
grep -rn "def split\|register.filter.*split" app01/ templates/
```

If not found, add a template filter. Create `app01/templatetags/` if needed:

```bash
mkdir -p app01/templatetags
touch app01/templatetags/__init__.py
```

Create `app01/templatetags/custom_filters.py`:

```python
from django import template

register = template.Library()

@register.filter
def split(value, arg):
    return value.split(arg)
```

Then add `{% load custom_filters %}` at the top of `user_edit.html` (after `{% extends "base.html" %}`).

Also add the load tag to `user_management.html` if module_permissions iteration uses it.

- [ ] **Step 7: Run tests**

```bash
python manage.py test app01.tests.UserEditDeleteTest --noinput
```

Expected: `OK (5 tests)`.

- [ ] **Step 8: Commit**

```bash
git add app01/views.py templates/user_edit.html bprdb/urls.py app01/tests.py app01/templatetags/
git commit -m "feat: add user_edit_view and user_delete_view with AuditLog"
```

---

### Task 9: Project request approve/reject views

**Files:**
- Modify: `app01/views.py`
- Modify: `bprdb/urls.py`
- Modify: `app01/tests.py`

- [ ] **Step 1: Write failing tests**

Add to `app01/tests.py`:

```python
class ProjectRequestApproveRejectTest(TestCase):
    def setUp(self):
        self.sadmin = LmsUser.objects.create_user(
            username='sa3', password='pass', user_type='superadmin'
        )
        self.sadmin.is_superuser = True
        self.sadmin.save()
        self.requester = LmsUser.objects.create_user(
            username='req1', password='pass', user_type='sub_admin',
            permissions_project='BPR350', module_permissions='upload,data,compound,batch'
        )
        self.req = ProjectAccessRequest.objects.create(
            user=self.requester, project_code='BPR3M03', status='pending'
        )

    def test_approve_adds_project_to_user(self):
        self.client.login(username='sa3', password='pass')
        self.client.post(f'/users/requests/{self.req.id}/approve/')
        self.requester.refresh_from_db()
        self.assertIn('BPR3M03', self.requester.permissions_project)

    def test_approve_sets_status_approved(self):
        self.client.login(username='sa3', password='pass')
        self.client.post(f'/users/requests/{self.req.id}/approve/')
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, 'approved')

    def test_approve_writes_audit_log(self):
        self.client.login(username='sa3', password='pass')
        self.client.post(f'/users/requests/{self.req.id}/approve/')
        log = AuditLog.objects.filter(action='project_approved').first()
        self.assertIsNotNone(log)

    def test_reject_sets_status_rejected(self):
        self.client.login(username='sa3', password='pass')
        self.client.post(f'/users/requests/{self.req.id}/reject/')
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, 'rejected')

    def test_non_superadmin_cannot_approve(self):
        u = LmsUser.objects.create_user(username='plain2', password='pass', user_type='sub_admin')
        self.client.login(username='plain2', password='pass')
        r = self.client.post(f'/users/requests/{self.req.id}/approve/')
        self.assertEqual(r.status_code, 403)
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, 'pending')
```

- [ ] **Step 2: Add URLs**

In `bprdb/urls.py`, add:

```python
path('users/requests/<int:req_id>/approve/', views.project_request_approve, name='project_request_approve'),
path('users/requests/<int:req_id>/reject/', views.project_request_reject, name='project_request_reject'),
```

- [ ] **Step 3: Add views to `app01/views.py`**

After `user_delete_view`, insert:

```python
@login_required
def project_request_approve(request, req_id):
    if not (request.user.is_superuser or request.user.user_type == 'superadmin'):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('此操作仅 superadmin 可执行')
    if request.method != 'POST':
        return redirect('user_management')
    from app01.models import ProjectAccessRequest, AuditLog
    from django.utils import timezone
    import json as _json_mod
    req = get_object_or_404(ProjectAccessRequest, id=req_id)
    req.status = 'approved'
    req.reviewed_by = request.user
    req.reviewed_at = timezone.now()
    req.save()
    user = req.user
    existing = [p.strip() for p in (user.permissions_project or '').split(',') if p.strip()]
    if req.project_code not in existing:
        existing.append(req.project_code)
    user.permissions_project = ','.join(existing)
    user.save()
    AuditLog.objects.create(
        actor=request.user,
        action='project_approved',
        target_user=user,
        detail=_json_mod.dumps({'project': req.project_code}),
    )
    messages.success(request, f'已批准 {user.username} 访问 {req.project_code}')
    return redirect('user_management')


@login_required
def project_request_reject(request, req_id):
    if not (request.user.is_superuser or request.user.user_type == 'superadmin'):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('此操作仅 superadmin 可执行')
    if request.method != 'POST':
        return redirect('user_management')
    from app01.models import ProjectAccessRequest, AuditLog
    from django.utils import timezone
    import json as _json_mod
    req = get_object_or_404(ProjectAccessRequest, id=req_id)
    req.status = 'rejected'
    req.reviewed_by = request.user
    req.reviewed_at = timezone.now()
    req.save()
    AuditLog.objects.create(
        actor=request.user,
        action='project_rejected',
        target_user=req.user,
        detail=_json_mod.dumps({'project': req.project_code}),
    )
    messages.success(request, f'已拒绝 {req.user.username} 访问 {req.project_code}')
    return redirect('user_management')
```

- [ ] **Step 4: Run tests**

```bash
python manage.py test app01.tests.ProjectRequestApproveRejectTest --noinput
```

Expected: `OK (5 tests)`.

- [ ] **Step 5: Commit**

```bash
git add app01/views.py bprdb/urls.py app01/tests.py
git commit -m "feat: add project_request_approve and project_request_reject views"
```

---

### Task 10: Profile page — request additional projects

**Files:**
- Modify: `app01/views.py` (`user_profile` view + new `profile_request_project` view)
- Modify: `templates/profile.html`
- Modify: `bprdb/urls.py`
- Modify: `app01/tests.py`

- [ ] **Step 1: Write failing tests**

Add to `app01/tests.py`:

```python
class ProfileRequestProjectTest(TestCase):
    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='prof1', password='pass', user_type='sub_admin',
            permissions_project='BPR350', module_permissions='upload,data,compound,batch'
        )
        self.client.login(username='prof1', password='pass')

    def test_submit_creates_request(self):
        r = self.client.post('/profile/request-project/', {'project_code': 'BPR3M03'})
        self.assertRedirects(r, '/profile/', fetch_redirect_response=False)
        self.assertEqual(ProjectAccessRequest.objects.filter(
            user=self.user, project_code='BPR3M03', status='pending'
        ).count(), 1)

    def test_submit_writes_audit_log(self):
        self.client.post('/profile/request-project/', {'project_code': 'BPR3M03'})
        log = AuditLog.objects.filter(actor=self.user, action='project_request').first()
        self.assertIsNotNone(log)

    def test_duplicate_pending_request_rejected(self):
        ProjectAccessRequest.objects.create(
            user=self.user, project_code='BPR3M03', status='pending'
        )
        self.client.post('/profile/request-project/', {'project_code': 'BPR3M03'})
        self.assertEqual(ProjectAccessRequest.objects.filter(
            user=self.user, project_code='BPR3M03', status='pending'
        ).count(), 1)

    def test_already_has_project_rejected(self):
        self.client.post('/profile/request-project/', {'project_code': 'BPR350'})
        self.assertEqual(ProjectAccessRequest.objects.filter(
            user=self.user, project_code='BPR350'
        ).count(), 0)
```

- [ ] **Step 2: Add URL**

In `bprdb/urls.py`, add:

```python
path('profile/request-project/', views.profile_request_project, name='profile_request_project'),
```

- [ ] **Step 3: Add `profile_request_project` to `app01/views.py`**

After `user_profile`, insert:

```python
@login_required
def profile_request_project(request):
    if request.method != 'POST':
        return redirect('user_profile')
    project_code = request.POST.get('project_code', '').strip()
    if not project_code:
        messages.error(request, '项目代码不能为空')
        return redirect('user_profile')
    from app01.models import ProjectAccessRequest, AuditLog
    import json as _json_mod
    user = request.user
    existing = [p.strip() for p in (user.permissions_project or '').split(',') if p.strip()]
    if project_code in existing:
        messages.warning(request, f'你已拥有项目 {project_code} 的访问权限')
        return redirect('user_profile')
    if ProjectAccessRequest.objects.filter(user=user, project_code=project_code, status='pending').exists():
        messages.warning(request, f'项目 {project_code} 的申请已在审批中')
        return redirect('user_profile')
    ProjectAccessRequest.objects.create(user=user, project_code=project_code)
    AuditLog.objects.create(
        actor=user,
        action='project_request',
        detail=_json_mod.dumps({'project': project_code}),
    )
    messages.success(request, f'已提交项目 {project_code} 的访问申请，等待 superadmin 审批')
    return redirect('user_profile')
```

- [ ] **Step 4: Update `user_profile` view to pass request history**

In `app01/views.py`, find `user_profile`. Replace the final `return render(...)` line:

Old:
```python
    projects = [p.strip() for p in user.permissions_project.split(',') if p.strip()]
    return render(request, 'profile.html', {'msg': msg, 'projects': projects})
```

New:
```python
    from app01.models import ProjectAccessRequest
    projects = [p.strip() for p in (user.permissions_project or '').split(',') if p.strip()]
    access_requests = ProjectAccessRequest.objects.filter(user=user)
    return render(request, 'profile.html', {
        'msg': msg,
        'projects': projects,
        'access_requests': access_requests,
    })
```

- [ ] **Step 5: Update `templates/profile.html`**

After the existing "修改密码" card (before `{% endblock %}`), add:

```html
  {# ── 申请新项目 ── #}
  <div style="background:white;border:1px solid #e2e8f0;border-radius:8px;padding:20px 24px;margin-top:16px;">
    <div style="font-size:13px;font-weight:700;color:#374151;margin-bottom:10px;
                border-bottom:1px solid #f1f5f9;padding-bottom:8px;">
      申请访问新项目
    </div>
    <p style="font-size:12px;color:#64748b;margin-bottom:12px;">填写项目代码，提交后等待 superadmin 审批。</p>
    <form method="post" action="{% url 'profile_request_project' %}" style="display:flex;gap:8px;align-items:center;">
      {% csrf_token %}
      <input type="text" name="project_code" class="ds-form-control"
             placeholder="如 BPR350" style="width:180px;">
      <button type="submit" class="ds-btn ds-btn-primary" style="padding:0 16px;height:36px;">提交申请</button>
    </form>
  </div>

  {# ── 申请记录 ── #}
  {% if access_requests %}
  <div style="background:white;border:1px solid #e2e8f0;border-radius:8px;padding:20px 24px;margin-top:16px;">
    <div style="font-size:13px;font-weight:700;color:#374151;margin-bottom:10px;
                border-bottom:1px solid #f1f5f9;padding-bottom:8px;">
      申请记录
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:12px;">
      <tbody>
        {% for req in access_requests %}
        <tr style="border-bottom:1px solid #f4f7fb;">
          <td style="padding:7px 0;color:#94a3b8;font-family:monospace;font-size:11px;width:150px;">{{ req.created_at|date:"Y-m-d H:i" }}</td>
          <td style="padding:7px 8px;">
            <span style="background:#ede9fe;color:#6d28d9;padding:1px 7px;border-radius:10px;font-size:11px;font-weight:500;">{{ req.project_code }}</span>
          </td>
          <td style="padding:7px 0;">
            {% if req.status == 'pending' %}
              <span style="background:#fef3c7;color:#92400e;padding:1px 7px;border-radius:10px;font-size:11px;font-weight:500;">待审批</span>
            {% elif req.status == 'approved' %}
              <span style="background:#dcfce7;color:#166534;padding:1px 7px;border-radius:10px;font-size:11px;font-weight:500;">已批准</span>
            {% else %}
              <span style="background:#fee2e2;color:#dc2626;padding:1px 7px;border-radius:10px;font-size:11px;font-weight:500;">已拒绝</span>
            {% endif %}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% endif %}
```

- [ ] **Step 6: Run tests**

```bash
python manage.py test app01.tests.ProfileRequestProjectTest --noinput
```

Expected: `OK (4 tests)`.

- [ ] **Step 7: Commit**

```bash
git add app01/views.py templates/profile.html bprdb/urls.py app01/tests.py
git commit -m "feat: add profile_request_project view and update profile page with request history"
```

---

### Task 11: Per-row delete button in compound_list

**Files:**
- Modify: `templates/compound_list.html`
- Modify: `static/js/compound_list.js`
- Modify: `app01/tests.py`

**Context:** Each compound row needs a delete button visible only to users with the `data` module. Clicking it calls a new JS function `clDeleteRow(...expIds)` which calls the existing `/api/experiments/bulk-delete/` endpoint. The `exp_ids` are already on the row via `data-exp-id` attribute (added in the compound-list-b plan).

- [ ] **Step 1: Verify `data-exp-id` is present on rows**

```bash
grep -n "data-exp-id" templates/compound_list.html
```

Expected: at least 2 matches (vitro and vivo rows). If not present, check `_build_vitro_compound_entry` and `_build_vivo_compound_entry` in `views.py` for `exp_ids` key; the template needs `data-exp-id="{{ vc.exp_ids|join:',' }}"` on each `<tr class="cmp-row">`.

- [ ] **Step 2: Add delete button to vitro compound row**

In `templates/compound_list.html`, find the vitro `<tr class="cmp-row">` cell that contains the select checkbox (the first `<td>` with the checkbox). Look for the pattern immediately after the `<tr>` tag:

```html
      <td style="width:28px;padding:4px;">
        <input type="checkbox" class="cl-cmp-chk"
```

Add a delete button cell **after** the last `</td>` before `</tr>` in each vitro compound row. Find the closing `</tr>` of the vitro compound row and add before it:

```html
      {% if request.user.user_type == 'superadmin' or request.user.is_superuser or 'data' in request.user.module_permissions %}
      <td style="width:36px;padding:4px 2px;text-align:center;">
        <button class="ds-btn ds-btn-danger" style="font-size:10px;padding:2px 6px;height:24px;min-width:0;"
                onclick="event.stopPropagation();clDeleteRow({{ vc.exp_ids|join:',' }})"
                title="删除该化合物的实验数据">🗑</button>
      </td>
      {% endif %}
```

Also add a matching empty `<th>` to the vitro table header to keep columns aligned:

Find the vitro table header row and add at the end:
```html
      {% if request.user.user_type == 'superadmin' or request.user.is_superuser or 'data' in request.user.module_permissions %}
      <th style="width:36px;"></th>
      {% endif %}
```

Repeat both changes for the vivo compound rows and header.

- [ ] **Step 3: Add `clDeleteRow` to `static/js/compound_list.js`**

At the end of `compound_list.js`, append:

```js
// ── Per-row delete ────────────────────────────────────────────
function clDeleteRow(...expIds) {
  const n = expIds.filter(id => id > 0).length;
  if (!confirm(`确认删除该化合物的 ${n} 条实验记录？此操作不可撤销。`)) return;
  fetch('/api/experiments/bulk-delete/', {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': _clCsrfToken()},
    body: JSON.stringify({exp_ids: expIds.filter(id => id > 0)}),
  })
    .then(r => r.json().then(data => ({ok: r.ok, data})))
    .then(({ok, data}) => {
      if (!ok) { alert(data.error || '删除失败'); return; }
      location.reload();
    })
    .catch(() => alert('删除失败，请重试'));
}
```

- [ ] **Step 4: Manual smoke test**

```bash
python manage.py runserver
```

1. Log in as a user with `module_permissions` containing `data` → each compound row should show a 🗑 button.
2. Log in as a `user` (no module perms) → no 🗑 button.
3. Click 🗑 on a row → confirm dialog → confirm → experiments deleted, page reloads.

- [ ] **Step 5: Commit**

```bash
git add templates/compound_list.html static/js/compound_list.js
git commit -m "feat: add per-row delete button to compound_list (visible to data module holders)"
```

---

### Task 12: Management command `reset_users`

**Files:**
- Create: `app01/management/__init__.py`
- Create: `app01/management/commands/__init__.py`
- Create: `app01/management/commands/reset_users.py`
- Modify: `app01/tests.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p app01/management/commands
touch app01/management/__init__.py
touch app01/management/commands/__init__.py
```

- [ ] **Step 2: Write failing test**

Add to `app01/tests.py`:

```python
from django.core.management import call_command
from io import StringIO


class ResetUsersCommandTest(TestCase):
    def setUp(self):
        self.sa = LmsUser.objects.create_user(
            username='theadmin', password='oldpass', user_type='superadmin'
        )
        self.sa.is_superuser = True
        self.sa.save()
        LmsUser.objects.create_user(username='user1', password='pass', user_type='sub_admin')
        LmsUser.objects.create_user(username='user2', password='pass', user_type='user')

    def test_deletes_non_superadmin_users(self):
        call_command('reset_users', stdout=StringIO())
        self.assertFalse(LmsUser.objects.filter(username='user1').exists())
        self.assertFalse(LmsUser.objects.filter(username='user2').exists())

    def test_keeps_superadmin(self):
        call_command('reset_users', stdout=StringIO())
        self.assertTrue(LmsUser.objects.filter(username='theadmin').exists())

    def test_resets_password_to_123456(self):
        call_command('reset_users', stdout=StringIO())
        sa = LmsUser.objects.get(username='theadmin')
        self.assertTrue(sa.check_password('123456'))

    def test_sets_superadmin_type(self):
        call_command('reset_users', stdout=StringIO())
        sa = LmsUser.objects.get(username='theadmin')
        self.assertEqual(sa.user_type, 'superadmin')
```

- [ ] **Step 3: Run tests — verify they fail**

```bash
python manage.py test app01.tests.ResetUsersCommandTest --noinput
```

Expected: `CommandError` or `ModuleNotFoundError`.

- [ ] **Step 4: Create `app01/management/commands/reset_users.py`**

```python
from django.core.management.base import BaseCommand
from app01.models import LmsUser


class Command(BaseCommand):
    help = 'Reset to single superadmin user (password: 123456). Deletes all other users.'

    def handle(self, *args, **options):
        superadmin = (
            LmsUser.objects.filter(is_superuser=True).first()
            or LmsUser.objects.filter(user_type='superadmin').first()
        )
        if not superadmin:
            self.stderr.write('No superadmin found. Aborting.')
            return

        superadmin.set_password('123456')
        superadmin.user_type = 'superadmin'
        superadmin.module_permissions = ''
        superadmin.is_superuser = True
        superadmin.is_active = True
        superadmin.save()

        deleted_count, _ = LmsUser.objects.exclude(pk=superadmin.pk).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f'Kept: {superadmin.username}. Deleted: {deleted_count} users.'
            )
        )
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
python manage.py test app01.tests.ResetUsersCommandTest --noinput
```

Expected: `OK (4 tests)`.

- [ ] **Step 6: Commit**

```bash
git add app01/management/ app01/tests.py
git commit -m "feat: add reset_users management command"
```

---

### Task 13: Final checks and run all tests

- [ ] **Step 1: Run full test suite**

```bash
source venv/bin/activate
python manage.py test app01 --noinput
```

Expected: all new tests pass. Known pre-existing failures: `CompoundListViewTest.test_compound_data_in_context`, `ParseBodyWeightFileTest.test_time_unit_unknown_positive_only`. No new failures.

- [ ] **Step 2: Manual end-to-end check**

```bash
python manage.py runserver
```

Verify:
1. `/register/` shows project_code field; register creates sub_admin user with correct perms
2. `/users/` — login as superadmin → page loads; login as other user → 403
3. `/users/<id>/edit/` — modal loads, save works, AuditLog written
4. `/profile/` — shows current role + module perms + project request form + history
5. `/compounds/` — sub_admin with `permissions_project='BPR350'` sees only BPR350 data
6. `/upload/smart/` — user with no `upload` module is redirected to `/compounds/`
7. Compound list rows show 🗑 button for users with `data` module, hidden for others

- [ ] **Step 3: Run management command (optional, for actual DB reset)**

Only run this in your target environment when ready to reset users:

```bash
python manage.py reset_users
```

Expected output: `Kept: <username>. Deleted: N users.`

- [ ] **Step 4: Final commit if any fixes were needed**

```bash
git add -p
git commit -m "fix: address issues found in end-to-end testing"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| `user_type` → 3 choices | Task 1 |
| `module_permissions` field | Task 1 |
| `ProjectAccessRequest` model | Task 1 |
| `AuditLog` model | Task 1 |
| `_has_module` helper | Task 2 |
| `_get_permitted_projects` helper | Task 2 |
| `register_view` → sub_admin + all modules + AuditLog | Task 6 |
| `batch_delete` → `_has_module` | Task 3 |
| `experiments_bulk_delete` → `_has_module` | Task 3 |
| `experiments_export_csv` → `_has_module` | Task 3 |
| `compound_list` project filter | Task 4 |
| `smart_upload_view` upload guard | Task 5 |
| `smart_upload_confirm_view` upload guard | Task 5 |
| User management page (`/users/`, superadmin only) | Task 7 |
| User edit modal (role + modules + projects + AuditLog) | Task 8 |
| User delete + AuditLog | Task 8 |
| Pending requests table with approve/reject | Tasks 7, 9 |
| `project_request_approve` → adds project + AuditLog | Task 9 |
| `project_request_reject` → AuditLog | Task 9 |
| Profile page shows permissions + request form + history | Task 10 |
| `profile_request_project` → dedup check + AuditLog | Task 10 |
| Per-row delete button (data module only) | Task 11 |
| `clDeleteRow` JS function | Task 11 |
| `reset_users` management command | Task 12 |
| Sidebar link → `/users/` | Task 7 |
| Register page shows project_code field | Task 6 |
