# Permission System Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 7-level `user_type` system with 3 roles (superadmin / sub_admin / user), add per-module management permissions, and add a project-access approval workflow with a personal profile page.

**Architecture:** All permission state lives in three `LmsUser` fields: `user_type` (role), `permissions_project` (approved project codes), and `module_permissions` (which module tables a user may edit). A new `ProjectAccessRequest` model handles the approval workflow. A Django context processor injects the pending-request count into every template so the sidebar badge stays current without per-view plumbing.

**Tech Stack:** Django 5.1, Python 3.10, MySQL, existing design-system CSS (`/static/css/design-system.css`)

**Spec:** `docs/superpowers/specs/2026-05-29-permission-redesign-design.md`

---

## File Map

| File | Change |
|------|--------|
| `app01/models.py` | New `user_type` choices; new `module_permissions` field; new helper methods; new `ProjectAccessRequest` model; deprecate `is_admin` |
| `app01/migrations/0034_permission_redesign.py` | Add fields, create table, RunPython role remap + backfill |
| `app01/context_processors.py` | **New** — inject `pending_approval_count` into every template |
| `bms/settings.py` | Register the context processor |
| `bms/urls.py` | Add `/profile/`, `/request_project/`, `/approve_request/<id>/` |
| `app01/views.py` | Update helpers + all permission guards; add 3 new views |
| `app01/admin.py` | Register `ProjectAccessRequest`; update `LmsUserAdmin` |
| `app01/tests.py` | New test classes for models, helpers, view gates, profile/approval flow |
| `templates/base.html` | Sidebar visibility rules; pending badge; add 我的资料 link |
| `templates/auth_list.html` | Role pills; module-permission column; approval section |
| `templates/auth_edit.html` | New 3-value role dropdown; module-permission checkboxes |
| `templates/author_add.html` | Fix field-name bugs; new 3-value dropdown; module checkboxes |
| `templates/register.html` | Remove user_type dropdown; add optional project-request hint |
| `templates/profile.html` | **New** — personal profile page |

---

## Task 1: Model changes + migration

**Files:**
- Modify: `app01/models.py`
- Create: `app01/migrations/0034_permission_redesign.py`
- Modify: `app01/tests.py`

### Background

`LmsUser` currently has `user_type` with 7 choices stored as class-level constants, an `is_admin` boolean that duplicates role logic, and no `module_permissions` field. We replace the choices, add the new field, add helper methods, and create `ProjectAccessRequest`. The migration remaps old values and backfills `module_permissions` for former `data_admin` users.

- [ ] **Step 1: Write failing tests**

Add to the bottom of `app01/tests.py`:

```python
# ── Permission Redesign: Model Tests ──────────────────────────────────────────

class LmsUserRoleTests(TestCase):
    """LmsUser new role fields and helper methods."""

    def _make_user(self, username, user_type, module_permissions=''):
        return LmsUser.objects.create_user(
            username=username, password='pass',
            user_type=user_type,
            module_permissions=module_permissions,
        )

    def test_superadmin_can_manage_all_modules(self):
        u = self._make_user('sa', 'superadmin')
        for m in ('delivery', 'seq', 'linker'):
            self.assertTrue(u.can_manage_module(m))

    def test_user_without_module_perms_cannot_manage(self):
        u = self._make_user('u', 'user')
        for m in ('delivery', 'seq', 'linker'):
            self.assertFalse(u.can_manage_module(m))

    def test_user_with_delivery_perm_only(self):
        u = self._make_user('u2', 'user', module_permissions='delivery')
        self.assertTrue(u.can_manage_module('delivery'))
        self.assertFalse(u.can_manage_module('seq'))
        self.assertFalse(u.can_manage_module('linker'))

    def test_sub_admin_with_no_explicit_module_perms(self):
        u = self._make_user('pi', 'sub_admin')
        for m in ('delivery', 'seq', 'linker'):
            self.assertFalse(u.can_manage_module(m))

    def test_is_superuser_flag_overrides_module_check(self):
        u = self._make_user('django_su', 'user')
        u.is_superuser = True
        u.save()
        self.assertTrue(u.can_manage_module('delivery'))

    def test_user_type_choices_are_three_values(self):
        choices = dict(LmsUser._meta.get_field('user_type').choices)
        self.assertEqual(set(choices.keys()), {'superadmin', 'sub_admin', 'user'})


class ProjectAccessRequestModelTests(TestCase):
    """ProjectAccessRequest basic model behaviour."""

    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='requester', password='pass', user_type='user'
        )
        self.admin = LmsUser.objects.create_user(
            username='sa', password='pass', user_type='superadmin'
        )

    def test_create_pending_request(self):
        from app01.models import ProjectAccessRequest
        req = ProjectAccessRequest.objects.create(
            user=self.user,
            project_codes='BPR-350,BPR-3T03',
            note='need access',
        )
        self.assertEqual(req.status, 'pending')
        self.assertIsNone(req.reviewed_by)

    def test_approve_request_updates_fields(self):
        from app01.models import ProjectAccessRequest
        from django.utils import timezone
        req = ProjectAccessRequest.objects.create(
            user=self.user, project_codes='BPR-350'
        )
        req.status = 'approved'
        req.reviewed_by = self.admin
        req.reviewed_at = timezone.now()
        req.save()
        req.refresh_from_db()
        self.assertEqual(req.status, 'approved')
        self.assertEqual(req.reviewed_by, self.admin)

    def test_default_ordering_newest_first(self):
        from app01.models import ProjectAccessRequest
        r1 = ProjectAccessRequest.objects.create(user=self.user, project_codes='A')
        r2 = ProjectAccessRequest.objects.create(user=self.user, project_codes='B')
        qs = list(ProjectAccessRequest.objects.all())
        self.assertEqual(qs[0], r2)
        self.assertEqual(qs[1], r1)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
source venv/bin/activate
python manage.py test app01.tests.LmsUserRoleTests app01.tests.ProjectAccessRequestModelTests -v 2 2>&1 | tail -20
```

Expected: errors about missing `can_manage_module`, missing choices, missing model.

- [ ] **Step 3: Update `app01/models.py`**

Replace the `USER_TYPE_CHOICES` block and the class-level constants, add `module_permissions`, add helper methods, and add `ProjectAccessRequest`. Find the section starting with `PROJECT_MANAGEMENT = 'project'` (around line 136) and replace through the end of `LmsUser`:

```python
class LmsUser(AbstractUser):
    USER_TYPE_CHOICES = [
        ('superadmin', '超级管理员'),
        ('sub_admin',  '次级管理员'),
        ('user',       '普通用户'),
    ]

    user_type = models.CharField(
        '用户类型',
        max_length=16,
        choices=USER_TYPE_CHOICES,
        default='user',
    )

    # Deprecated — no longer written or read in code; kept for DB compatibility.
    # Remove in a follow-up migration once confirmed safe.
    is_admin = models.BooleanField('是否为管理员 (deprecated)', default=False)

    # TODO: migrate to ManyToManyField(Project) once a Project model exists;
    #       current comma-separated CharField is a stopgap.
    permissions_project = models.CharField(
        '可查看的项目号',
        max_length=256,
        null=True,
        blank=True,
    )

    default_seq_type = models.CharField(
        '默认序列方向',
        max_length=10,
        default='SS',
        choices=[('SS', 'SS'), ('AS', 'AS')],
    )

    # Comma-separated: 'delivery', 'seq', 'linker'
    # e.g. "delivery,seq"  or ""  (empty = no module management rights)
    module_permissions = models.CharField(
        '模块管理权限',
        max_length=64,
        blank=True,
        default='',
    )

    class Meta:
        verbose_name = '用户'
        verbose_name_plural = '用户'

    # ── helpers ──────────────────────────────────────────────────────────────

    def get_allowed_projects(self):
        """Return list of approved project codes for this user."""
        if not self.permissions_project:
            return []
        return [p.strip() for p in self.permissions_project.split(',') if p.strip()]

    def can_manage_module(self, module: str) -> bool:
        """Return True if user may edit entries in the given module table.

        Args:
            module: one of 'delivery', 'seq', 'linker'
        """
        if self.is_superuser or self.user_type == 'superadmin':
            return True
        return module in (self.module_permissions or '').split(',')

    def can_manage_modules(self) -> bool:
        """Legacy helper — True if user can manage ANY module.
        Kept so old call sites compile; prefer can_manage_module(name)."""
        if self.is_superuser or self.user_type == 'superadmin':
            return True
        return bool(self.module_permissions)

    def __str__(self):
        return f"{self.username} ({self.user_type})"


class ProjectAccessRequest(models.Model):
    STATUS_CHOICES = [
        ('pending',  '待审批'),
        ('approved', '已批准'),
        ('rejected', '已拒绝'),
    ]

    user = models.ForeignKey(
        LmsUser, on_delete=models.CASCADE, related_name='access_requests',
        verbose_name='申请人',
    )
    project_codes = models.CharField('申请项目号', max_length=512)
    note = models.CharField('申请说明', max_length=256, blank=True)
    requested_at = models.DateTimeField('申请时间', auto_now_add=True)
    status = models.CharField(
        '状态', max_length=16, choices=STATUS_CHOICES, default='pending'
    )
    reviewed_by = models.ForeignKey(
        LmsUser, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='reviewed_requests', verbose_name='审批人',
    )
    reviewed_at = models.DateTimeField('审批时间', null=True, blank=True)
    review_note = models.CharField('审批备注', max_length=256, blank=True)

    class Meta:
        verbose_name = '项目权限申请'
        verbose_name_plural = '项目权限申请'
        ordering = ['-requested_at']

    def __str__(self):
        return f"{self.user.username} → {self.project_codes} [{self.status}]"
```

- [ ] **Step 4: Create migration**

```bash
source venv/bin/activate
python manage.py makemigrations app01 --name permission_redesign
```

This creates `app01/migrations/0034_permission_redesign.py`. Open it and add two `RunPython` operations after the `AddField` / `CreateModel` operations:

```python
# Add this import at the top of the migration file:
from django.utils import timezone


def migrate_roles_and_module_perms(apps, schema_editor):
    """Remap old 7-level user_type to new 3-level; backfill module_permissions
    for users who were data_admin (they had full module access before)."""
    LmsUser = apps.get_model('app01', 'LmsUser')

    # Step 1: grant full module permissions to former data_admins BEFORE we
    # overwrite their user_type (so we can still identify them).
    LmsUser.objects.filter(user_type='data_admin').update(
        module_permissions='delivery,seq,linker'
    )

    # Step 2: remap all user_type values
    role_map = {
        'superadmin': 'superadmin',
        'admin':      'superadmin',
        'data_admin': 'sub_admin',
        'project':    'user',
        'modify':     'user',
        'delivery':   'user',
        'guest':      'user',
    }
    for old, new in role_map.items():
        LmsUser.objects.filter(user_type=old).update(user_type=new)


# Inside class Migration, operations list — append after the last auto-generated op:
# migrations.RunPython(migrate_roles_and_module_perms, migrations.RunPython.noop),
```

The final `operations` list should end with:

```python
    operations = [
        # ... auto-generated AddField / CreateModel ops ...
        migrations.RunPython(
            migrate_roles_and_module_perms,
            migrations.RunPython.noop,
        ),
    ]
```

- [ ] **Step 5: Apply migration**

```bash
source venv/bin/activate
python manage.py migrate
```

Expected output ends with: `Applying app01.0034_permission_redesign... OK`

- [ ] **Step 6: Run tests**

```bash
python manage.py test app01.tests.LmsUserRoleTests app01.tests.ProjectAccessRequestModelTests -v 2 2>&1 | tail -15
```

Expected: `Ran 9 tests … OK`

- [ ] **Step 7: Update `app01/admin.py`**

Add `ProjectAccessRequest` to imports and register it:

```python
from .models import (
    Sequence, Delivery, SeqInfo, DuplexRelationship,
    DeliveryModule, SeqModule, LinkerModule, LmsUser,
    ProjectAccessRequest,
)

@admin.register(ProjectAccessRequest)
class ProjectAccessRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'project_codes', 'status', 'requested_at', 'reviewed_by')
    list_filter = ('status',)
    search_fields = ('user__username', 'project_codes')

# Update LmsUserAdmin:
@admin.register(LmsUser)
class LmsUserAdmin(admin.ModelAdmin):
    list_display = ('username', 'user_type', 'module_permissions', 'is_superuser', 'permissions_project')
    list_filter = ('user_type', 'is_superuser')
    search_fields = ('username', 'email', 'permissions_project')
```

- [ ] **Step 8: Commit**

```bash
git add app01/models.py app01/migrations/0034_permission_redesign.py app01/admin.py app01/tests.py
git commit -m "feat: 3-role model, module_permissions, ProjectAccessRequest, migration 0034"
```

---

## Task 2: Permission helper functions in views.py

**Files:**
- Modify: `app01/views.py` (helper functions only — ~lines 2688–2724)
- Modify: `app01/tests.py`

### Background

Two existing helpers need updates: `user_can_edit_delivery` (regular users lose edit right; sub_admins gain it within their projects) and `_user_can_access_duplex` (remove stale role list). One new module-check helper replaces the per-view `can_manage_modules()` pattern.

- [ ] **Step 1: Write failing tests**

Add to `app01/tests.py`:

```python
class PermissionHelperTests(TestCase):
    """user_can_edit_delivery and _is_superadmin helper behaviour."""

    def setUp(self):
        self.seq = Sequence.objects.create(
            rm_code='RM0001', seq='AUGC', seq_type='SS'
        )
        self.delivery = Delivery.objects.create(
            sequence=self.seq,
            seq_type='SS',
            modify_seq='AmUmGmCm',
            linker_seq='AmUmGmCm',
            project='BPR-350',
            duplex_id='BP000001',
        )
        DeliveryProject.objects.create(delivery=self.delivery, project_code='BPR-350')

        self.superadmin = LmsUser.objects.create_user(
            username='sa', password='p', user_type='superadmin'
        )
        self.sub_admin = LmsUser.objects.create_user(
            username='pi', password='p', user_type='sub_admin',
            permissions_project='BPR-350',
        )
        self.regular = LmsUser.objects.create_user(
            username='u', password='p', user_type='user',
            permissions_project='BPR-350',
        )
        self.no_project = LmsUser.objects.create_user(
            username='nop', password='p', user_type='sub_admin',
            permissions_project='OTHER',
        )

    def test_superadmin_can_edit_any_delivery(self):
        from app01.views import user_can_edit_delivery
        self.assertTrue(user_can_edit_delivery(self.superadmin, self.delivery))

    def test_sub_admin_can_edit_own_project(self):
        from app01.views import user_can_edit_delivery
        self.assertTrue(user_can_edit_delivery(self.sub_admin, self.delivery))

    def test_sub_admin_cannot_edit_other_project(self):
        from app01.views import user_can_edit_delivery
        self.assertFalse(user_can_edit_delivery(self.no_project, self.delivery))

    def test_regular_user_cannot_edit(self):
        from app01.views import user_can_edit_delivery
        self.assertFalse(user_can_edit_delivery(self.regular, self.delivery))
```

- [ ] **Step 2: Run to confirm failures**

```bash
python manage.py test app01.tests.PermissionHelperTests -v 2 2>&1 | tail -15
```

Expected: `test_regular_user_cannot_edit` passes (already true), `test_sub_admin_can_edit_own_project` fails (sub_admin not yet in check).

- [ ] **Step 3: Update helpers in `app01/views.py`**

Find `def get_permitted_delivery_qs` (~line 2688) and replace the three functions:

```python
def _is_superadmin(user) -> bool:
    """Return True for Django superusers and SeqDB superadmin role."""
    return user.is_superuser or getattr(user, 'user_type', '') == 'superadmin'


def get_permitted_delivery_qs(user):
    """
    Return the Delivery queryset visible to this user:
    - superadmin: all records
    - sub_admin / user: only records in their approved projects
    - no approved projects: empty queryset
    """
    if _is_superadmin(user):
        return Delivery.objects.all()
    allowed = user.get_allowed_projects()
    if allowed:
        return Delivery.objects.filter(
            project_links__project_code__in=allowed
        ).distinct()
    return Delivery.objects.none()


def user_can_edit_delivery(user, delivery):
    """
    Return True if user may edit/delete/clone this Delivery record.

    Rules:
    - superadmin: always True
    - sub_admin: True only when user holds ALL projects the delivery belongs to
    - user: always False
    """
    if _is_superadmin(user):
        return True
    if getattr(user, 'user_type', '') != 'sub_admin':
        return False
    delivery_projects = set(
        delivery.project_links.values_list('project_code', flat=True)
    )
    user_projects = set(user.get_allowed_projects())
    return delivery_projects.issubset(user_projects)


def _user_can_access_duplex(user, duplex_id):
    """Return True if user can view/edit experiments for this duplex."""
    if _is_superadmin(user):
        return True
    return get_permitted_delivery_qs(user).filter(duplex_id=duplex_id).exists()
```

- [ ] **Step 4: Run tests**

```bash
python manage.py test app01.tests.PermissionHelperTests -v 2 2>&1 | tail -10
```

Expected: `Ran 4 tests … OK`

- [ ] **Step 5: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "refactor: update permission helpers for 3-role model"
```

---

## Task 3: Update existing view permission guards

**Files:**
- Modify: `app01/views.py`
- Modify: `app01/tests.py`

### Background

Every view that previously checked `user_type in ('admin', 'data_admin', 'superadmin')` or `is_superuser or is_admin` needs to be updated to use `_is_superadmin()` or `user_type == 'sub_admin'`. Module management views switch from `can_manage_modules()` to `can_manage_module('delivery'|'seq'|'linker')`. `register_view` must stop accepting a user-supplied role.

- [ ] **Step 1: Write failing tests**

Add to `app01/tests.py`:

```python
class ViewPermissionGateTests(TestCase):
    """Ensure view guards enforce the new 3-role model."""

    def setUp(self):
        self.client_sa = self.client_class()
        self.client_pi = self.client_class()
        self.client_u  = self.client_class()

        self.sa = LmsUser.objects.create_user(
            username='sa', password='p', user_type='superadmin'
        )
        self.pi = LmsUser.objects.create_user(
            username='pi', password='p', user_type='sub_admin'
        )
        self.u = LmsUser.objects.create_user(
            username='u', password='p', user_type='user'
        )
        self.client_sa.force_login(self.sa)
        self.client_pi.force_login(self.pi)
        self.client_u.force_login(self.u)

    # author_list — superadmin only
    def test_author_list_superadmin_200(self):
        r = self.client_sa.get('/author_list/')
        self.assertEqual(r.status_code, 200)

    def test_author_list_sub_admin_403(self):
        r = self.client_pi.get('/author_list/')
        self.assertIn(r.status_code, [302, 403])

    def test_author_list_user_403(self):
        r = self.client_u.get('/author_list/')
        self.assertIn(r.status_code, [302, 403])

    # delete_experiment — sub_admin+
    def test_delete_experiment_user_redirects(self):
        r = self.client_u.post('/experiment/delete/9999/')
        # Must not 200 — either 403 or redirect with error message
        self.assertNotEqual(r.status_code, 200)

    # register sets role to 'user' regardless of POST data
    def test_register_always_creates_user_role(self):
        r = self.client_class().post('/register/', {
            'username': 'newbie',
            'email': 'newbie@test.com',
            'password': 'pass123',
            'user_type': 'superadmin',   # should be ignored
            'permissions_project': '',
        })
        u = LmsUser.objects.filter(username='newbie').first()
        self.assertIsNotNone(u)
        self.assertEqual(u.user_type, 'user')
```

- [ ] **Step 2: Run to confirm failures**

```bash
python manage.py test app01.tests.ViewPermissionGateTests -v 2 2>&1 | tail -15
```

Expected: `test_author_list_sub_admin_403` and `test_author_list_user_403` fail (no guard yet on `author_list`); `test_register_always_creates_user_role` fails (currently accepts user_type from POST).

- [ ] **Step 3: Fix `author_list`, `add_author`, `drop_author`, `edit_author`**

In `app01/views.py`, find `def author_list` (~line 452):

```python
@login_required
def author_list(request):
    if not _is_superadmin(request.user):
        messages.error(request, '您没有权限访问用户管理页面。')
        return redirect('seq_list')
    pending_count = ProjectAccessRequest.objects.filter(status='pending').count()
    users = LmsUser.objects.all().order_by('username')
    pending_requests = ProjectAccessRequest.objects.filter(
        status='pending'
    ).select_related('user')
    return render(request, 'auth_list.html', {
        'user_list': users,
        'pending_requests': pending_requests,
        'pending_count': pending_count,
    })
```

Find `def drop_author` (~line 499), replace the guard:

```python
    if not _is_superadmin(request.user):
        messages.error(request, '您没有权限删除用户信息！')
        return redirect('author_list')
    # Replace the is_admin / is_superuser check for the target user:
    if drop_obj.user_type == 'superadmin' or drop_obj.is_superuser:
        messages.error(request, '不能删除超级管理员账号！')
        return redirect('author_list')
```

Find `def edit_author` (~line 584), replace the top guard:

```python
    if not _is_superadmin(request.user):
        messages.error(request, '您没有权限编辑用户信息！')
        return redirect('author_list')
```

Also in `edit_author` POST block, add saving `module_permissions`:

```python
        # After edit_obj.user_type = new_author_user_type:
        raw_module_perms = request.POST.getlist('module_permissions')
        edit_obj.module_permissions = ','.join(raw_module_perms)
        edit_obj.save()
```

Find `def add_author` (~line 458), replace the entire function:

```python
@login_required
def add_author(request):
    if not _is_superadmin(request.user):
        messages.error(request, '您没有权限添加用户。')
        return redirect('author_list')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        user_type = request.POST.get('user_type', 'user')
        raw_projects = request.POST.get('permissions_project', '')
        permissions_project = ','.join(
            p.strip() for p in raw_projects.split(',') if p.strip()
        )
        raw_module_perms = request.POST.getlist('module_permissions')
        module_permissions = ','.join(raw_module_perms)

        if LmsUser.objects.filter(username=username).exists():
            messages.error(request, '用户名已存在！')
            return redirect('add_author')

        default_password = 'Bt123456'
        LmsUser.objects.create(
            username=username,
            email=email,
            user_type=user_type,
            permissions_project=permissions_project,
            module_permissions=module_permissions,
            password=setPassword(default_password),
        )
        messages.success(request, f'用户 {username} 已创建，默认密码 Bt123456')
        return redirect('author_list')

    project_list = list(
        DeliveryProject.objects
        .exclude(project_code__isnull=True).exclude(project_code='')
        .values_list('project_code', flat=True)
        .distinct().order_by('project_code')
    )
    return render(request, 'author_add.html', {'project_choices': project_list})
```

- [ ] **Step 4: Fix `register_view` — hardcode role to 'user'**

Find `def register_view` (~line 415), replace the `LmsUser.objects.create(...)` call:

```python
        LmsUser.objects.create(
            username=username,
            email=email,
            user_type='user',           # always 'user' on self-registration
            permissions_project='',     # starts with no projects
            password=setPassword(password),
        )
```

Also remove the `user_type = data.get("user_type")` line and the `raw_premissions_projects` / `new_author_permissions_project` lines above it (registration no longer accepts projects — user submits a request after login).

- [ ] **Step 5: Update module management view guards**

Find and replace these six guards (search for `can_manage_modules`):

| View | Old guard | New guard |
|------|-----------|-----------|
| `edit_module` | `not request.user.can_manage_modules()` | `not request.user.can_manage_module('delivery')` |
| `delete_module` | `not request.user.can_manage_modules()` | `not request.user.can_manage_module('delivery')` |
| `upload_modules` | `not request.user.can_manage_modules()` | `not request.user.can_manage_module('delivery')` |
| `edit_seqmodule` | `not request.user.can_manage_modules()` | `not request.user.can_manage_module('seq')` |
| `delete_seqmodule` | `not request.user.can_manage_modules()` | `not request.user.can_manage_module('seq')` |
| `upload_seqmodules` | `not request.user.can_manage_modules()` | `not request.user.can_manage_module('seq')` |
| `edit_linkermodule` | `not request.user.can_manage_modules()` | `not request.user.can_manage_module('linker')` |
| `delete_linkermodule` | `not request.user.can_manage_modules()` | `not request.user.can_manage_module('linker')` |

- [ ] **Step 6: Update `delete_experiment`, `clone_delivery`, `confirm_share_deliveries`**

Find `def delete_experiment` (~line 4591), replace the role guard:

```python
    if not (_is_superadmin(request.user) or
            getattr(request.user, 'user_type', '') == 'sub_admin'):
        messages.error(request, '您没有权限删除实验记录。')
        return redirect('seq_list')
```

Find `def clone_delivery` (~line 2544), replace both permission blocks (GET and POST). They currently check `perms` but not role. Add role check before the project check:

```python
    # In both GET and POST sections, replace the permission block with:
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'login required'}, status=401)
    if not _is_superadmin(request.user):
        if getattr(request.user, 'user_type', '') != 'sub_admin':
            return JsonResponse({'error': 'no permission'}, status=403)
        # sub_admin: check project scope (existing logic below this)
```

Find `def confirm_share_deliveries` (~line 2232). It currently has no role guard. Add one at the top of the POST handler:

```python
    if request.method == 'POST':
        if not (request.user.is_authenticated and
                (_is_superadmin(request.user) or
                 getattr(request.user, 'user_type', '') == 'sub_admin')):
            messages.error(request, '您没有权限执行此操作。')
            return redirect('seq_list')
        # ... rest of existing POST handler
```

- [ ] **Step 7: Add `ProjectAccessRequest` to views.py imports**

Near the top of `views.py`, find the `from .models import` line and add `ProjectAccessRequest`:

```python
from .models import (
    Sequence, Delivery, SeqInfo, DuplexRelationship,
    DeliveryModule, SeqModule, LinkerModule, LmsUser,
    DeliveryProject, Experiment, DataPoint, ExperimentAttachment,
    ProjectAccessRequest,
)
```

- [ ] **Step 8: Run tests**

```bash
python manage.py test app01.tests.ViewPermissionGateTests app01.tests.PermissionHelperTests -v 2 2>&1 | tail -15
```

Expected: `Ran 8 tests … OK`

- [ ] **Step 9: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "feat: enforce 3-role permission guards across all views"
```

---

## Task 4: New views — profile page, project request, approval

**Files:**
- Modify: `app01/views.py` (add 3 views at the end)
- Modify: `bms/urls.py`
- Create: `app01/context_processors.py`
- Modify: `bms/settings.py`
- Modify: `app01/tests.py`

- [ ] **Step 1: Write failing tests**

Add to `app01/tests.py`:

```python
class ProfileAndApprovalViewTests(TestCase):
    """Profile page, project access request, and approval workflow."""

    def setUp(self):
        self.sa = LmsUser.objects.create_user(
            username='sa', password='p', user_type='superadmin'
        )
        self.user = LmsUser.objects.create_user(
            username='u', password='p', user_type='user',
            permissions_project='',
        )
        self.client_sa = self.client_class()
        self.client_u  = self.client_class()
        self.client_sa.force_login(self.sa)
        self.client_u.force_login(self.user)

    def test_profile_page_loads_for_regular_user(self):
        r = self.client_u.get('/profile/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'u')   # username visible

    def test_superadmin_redirected_from_profile(self):
        r = self.client_sa.get('/profile/')
        self.assertIn(r.status_code, [302, 200])
        # superadmin has no profile page; should redirect to author_list
        if r.status_code == 302:
            self.assertIn('author_list', r['Location'])

    def test_submit_project_request_creates_pending(self):
        from app01.models import ProjectAccessRequest
        r = self.client_u.post('/request_project/', {
            'project_codes': 'BPR-350,BPR-3T03',
            'note': 'I need access',
        })
        self.assertIn(r.status_code, [302, 200])
        req = ProjectAccessRequest.objects.filter(user=self.user).first()
        self.assertIsNotNone(req)
        self.assertEqual(req.status, 'pending')
        self.assertEqual(req.project_codes, 'BPR-350,BPR-3T03')

    def test_approve_request_updates_permissions_project(self):
        from app01.models import ProjectAccessRequest
        req = ProjectAccessRequest.objects.create(
            user=self.user, project_codes='BPR-350'
        )
        r = self.client_sa.post(f'/approve_request/{req.id}/', {
            'action': 'approve',
            'review_note': '',
        })
        self.assertIn(r.status_code, [302, 200])
        req.refresh_from_db()
        self.assertEqual(req.status, 'approved')
        self.user.refresh_from_db()
        self.assertIn('BPR-350', self.user.permissions_project)

    def test_reject_request_does_not_grant_permissions(self):
        from app01.models import ProjectAccessRequest
        req = ProjectAccessRequest.objects.create(
            user=self.user, project_codes='BPR-999'
        )
        self.client_sa.post(f'/approve_request/{req.id}/', {
            'action': 'reject',
            'review_note': 'not authorised',
        })
        req.refresh_from_db()
        self.assertEqual(req.status, 'rejected')
        self.user.refresh_from_db()
        self.assertNotIn('BPR-999', self.user.permissions_project or '')

    def test_only_superadmin_can_approve(self):
        from app01.models import ProjectAccessRequest
        req = ProjectAccessRequest.objects.create(
            user=self.user, project_codes='BPR-350'
        )
        r = self.client_u.post(f'/approve_request/{req.id}/', {
            'action': 'approve',
        })
        self.assertIn(r.status_code, [302, 403])
        req.refresh_from_db()
        self.assertEqual(req.status, 'pending')  # unchanged
```

- [ ] **Step 2: Run to confirm failures**

```bash
python manage.py test app01.tests.ProfileAndApprovalViewTests -v 2 2>&1 | tail -15
```

Expected: all fail with 404 (URLs not yet defined).

- [ ] **Step 3: Create `app01/context_processors.py`**

```python
from app01.models import ProjectAccessRequest


def pending_approval_count(request):
    """Inject pending project-request count for superadmin sidebar badge."""
    count = 0
    if (request.user.is_authenticated and
            (request.user.is_superuser or
             getattr(request.user, 'user_type', '') == 'superadmin')):
        count = ProjectAccessRequest.objects.filter(status='pending').count()
    return {'pending_approval_count': count}
```

- [ ] **Step 4: Register context processor in `bms/settings.py`**

In the `context_processors` list inside `TEMPLATES`, add one entry:

```python
'context_processors': [
    'django.template.context_processors.debug',
    'django.template.context_processors.request',
    'django.contrib.auth.context_processors.auth',
    'django.contrib.messages.context_processors.messages',
    'app01.context_processors.pending_approval_count',   # ← add this line
],
```

- [ ] **Step 5: Add three new views to `app01/views.py`**

Append at the end of the file (before any trailing newlines):

```python
# ── Profile & Project Access Request ─────────────────────────────────────────

@login_required
def user_profile(request):
    """Personal profile page for non-superadmin users."""
    if _is_superadmin(request.user):
        return redirect('author_list')

    from .models import ProjectAccessRequest as PAR
    user = request.user
    requests_qs = PAR.objects.filter(user=user).order_by('-requested_at')

    return render(request, 'profile.html', {
        'profile_user': user,
        'access_requests': requests_qs,
        'approved_projects': user.get_allowed_projects(),
        'module_perms': [m for m in (user.module_permissions or '').split(',') if m],
    })


@login_required
@require_POST
def request_project_access(request):
    """Submit a new project access request."""
    if _is_superadmin(request.user):
        messages.error(request, '超级管理员无需申请项目权限。')
        return redirect('author_list')

    from .models import ProjectAccessRequest as PAR
    raw = request.POST.get('project_codes', '').strip()
    note = request.POST.get('note', '').strip()

    if not raw:
        messages.error(request, '请填写至少一个项目号。')
        return redirect('user_profile')

    project_codes = ','.join(p.strip() for p in raw.split(',') if p.strip())
    PAR.objects.create(user=request.user, project_codes=project_codes, note=note)
    messages.success(request, '申请已提交，等待超级管理员审批。')
    return redirect('user_profile')


@login_required
@require_POST
def approve_project_request(request, req_id):
    """Approve or reject a project access request. Superadmin only."""
    if not _is_superadmin(request.user):
        messages.error(request, '您没有权限执行此操作。')
        return redirect('seq_list')

    from .models import ProjectAccessRequest as PAR
    from django.utils import timezone as tz

    try:
        req = PAR.objects.select_related('user').get(pk=req_id)
    except PAR.DoesNotExist:
        messages.error(request, '申请记录不存在。')
        return redirect('author_list')

    action = request.POST.get('action')
    review_note = request.POST.get('review_note', '').strip()

    req.reviewed_by = request.user
    req.reviewed_at = tz.now()
    req.review_note = review_note

    if action == 'approve':
        req.status = 'approved'
        # Merge new project codes into user's permissions_project
        user = req.user
        existing = set(user.get_allowed_projects())
        new_codes = {p.strip() for p in req.project_codes.split(',') if p.strip()}
        merged = sorted(existing | new_codes)
        user.permissions_project = ','.join(merged)
        user.save(update_fields=['permissions_project'])
        messages.success(request, f'已批准 {user.username} 的项目权限申请。')
    elif action == 'reject':
        req.status = 'rejected'
        messages.success(request, f'已拒绝申请，备注：{review_note or "无"}。')
    else:
        messages.error(request, '无效操作。')
        return redirect('author_list')

    req.save()
    return redirect('author_list')
```

- [ ] **Step 6: Add URLs in `bms/urls.py`**

```python
path('profile/', views.user_profile, name='user_profile'),
path('request_project/', views.request_project_access, name='request_project_access'),
path('approve_request/<int:req_id>/', views.approve_project_request, name='approve_project_request'),
```

- [ ] **Step 7: Run tests**

```bash
python manage.py test app01.tests.ProfileAndApprovalViewTests -v 2 2>&1 | tail -15
```

Expected: `Ran 6 tests … OK`

- [ ] **Step 8: Commit**

```bash
git add app01/views.py bms/urls.py app01/context_processors.py bms/settings.py app01/tests.py
git commit -m "feat: profile page, project access request, superadmin approval workflow"
```

---

## Task 5: User management templates

**Files:**
- Modify: `templates/auth_list.html`
- Modify: `templates/auth_edit.html`
- Modify: `templates/author_add.html`

- [ ] **Step 1: Rewrite `templates/auth_list.html`**

Replace the entire file:

```html
{% extends 'base.html' %}
{% block page_title %} — 用户管理{% endblock %}
{% block topbar_content %}
  <span class="ds-topbar-title">用户管理</span>
  <span class="ds-count-badge">{{ user_list|length }}</span>
  <span class="ds-topbar-spacer"></span>
  <a href="{% url 'add_author' %}" class="ds-btn ds-btn-primary">
    <i class="bi bi-person-plus"></i> 新增用户
  </a>
{% endblock %}
{% block content %}

{% if pending_requests %}
<div class="ds-table-card" style="margin-bottom:16px;">
  <div style="padding:10px 16px;background:#fef9c3;border-bottom:1.5px solid #fde047;font-size:13px;font-weight:600;color:#854d0e;">
    ⏳ 待审批的项目权限申请（{{ pending_count }} 条）
  </div>
  <div class="ds-table-scroll">
    <table class="ds-table">
      <thead>
        <tr>
          <th>申请人</th>
          <th>申请项目</th>
          <th>说明</th>
          <th>申请时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        {% for req in pending_requests %}
        <tr>
          <td><strong>{{ req.user.username }}</strong></td>
          <td><code style="font-size:11px;">{{ req.project_codes }}</code></td>
          <td class="cell-dim">{{ req.note|default:'—' }}</td>
          <td class="cell-dim">{{ req.requested_at|date:"Y-m-d H:i" }}</td>
          <td>
            <div style="display:flex;gap:6px;align-items:center;">
              <form method="POST" action="{% url 'approve_project_request' req.id %}" style="display:inline;">
                {% csrf_token %}
                <input type="hidden" name="action" value="approve">
                <button type="submit" class="ds-btn ds-btn-primary" style="height:28px;padding:0 10px;font-size:11.5px;">批准</button>
              </form>
              <form method="POST" action="{% url 'approve_project_request' req.id %}" style="display:inline;">
                {% csrf_token %}
                <input type="hidden" name="action" value="reject">
                <input type="text" name="review_note" placeholder="拒绝理由（可选）"
                       style="height:28px;padding:0 8px;font-size:11.5px;border:1px solid #cbd5e1;border-radius:4px;width:140px;">
                <button type="submit" class="ds-btn ds-btn-ghost" style="height:28px;padding:0 10px;font-size:11.5px;color:#ef4444;">拒绝</button>
              </form>
            </div>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endif %}

<div class="ds-table-card">
  <div class="ds-table-scroll">
    <table class="ds-table">
      <thead>
        <tr>
          <th class="ds-th-sort cell-id">#</th>
          <th class="ds-th-sort">用户名</th>
          <th class="ds-th-sort">邮箱</th>
          <th class="ds-th-sort">角色</th>
          <th class="ds-th-sort">项目权限</th>
          <th class="ds-th-sort">模块权限</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        {% for user in user_list %}
        <tr>
          <td class="cell-dim">{{ forloop.counter }}</td>
          <td class="cell-text"><strong>{{ user.username }}</strong></td>
          <td class="cell-dim">{{ user.email|default:'—' }}</td>
          <td>
            <span class="ds-role-badge ds-role-{{ user.user_type }}">
              {% if user.user_type == 'superadmin' %}超级管理员
              {% elif user.user_type == 'sub_admin' %}次级管理员
              {% else %}普通用户{% endif %}
            </span>
          </td>
          <td class="cell-dim" style="max-width:180px;word-break:break-word;">
            {{ user.permissions_project|default:'—' }}
          </td>
          <td class="cell-dim" style="font-size:11px;">
            {% if user.module_permissions %}{{ user.module_permissions }}{% else %}—{% endif %}
          </td>
          <td>
            <div class="ds-actions">
              <a class="ds-act ds-act-edit" href="{% url 'edit_author' %}?id={{ user.id }}">编辑</a>
              <form method="POST" action="{% url 'drop_author' %}" style="display:inline;"
                    onsubmit="return confirm('确定删除用户 {{ user.username|escapejs }}？');">
                {% csrf_token %}
                <input type="hidden" name="id" value="{{ user.id }}">
                <button type="submit" class="ds-act ds-act-delete">删除</button>
              </form>
            </div>
          </td>
        </tr>
        {% empty %}
        <tr><td colspan="7" class="ds-empty-state">暂无用户数据</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Rewrite `templates/auth_edit.html`**

Replace the entire file:

```html
{% extends 'base.html' %}
{% block page_title %} — 编辑用户{% endblock %}
{% block topbar_content %}
  <span class="ds-topbar-title">编辑用户 — {{ user.username }}</span>
  <span class="ds-topbar-spacer"></span>
  <a href="{% url 'author_list' %}" class="ds-btn ds-btn-ghost">返回列表</a>
{% endblock %}
{% block content %}
<div class="ds-form-page">
  <div class="ds-form-card">
    <div class="ds-form-card-title">编辑 — {{ user.username }}</div>
    <form method="POST" action="{% url 'edit_author' %}?id={{ user.id }}">
      {% csrf_token %}
      <div class="ds-form-row">
        <label class="ds-form-label" for="edit_username">用户名</label>
        <input class="ds-form-control" id="edit_username" name="edit_username" value="{{ user.username }}">
      </div>
      <div class="ds-form-row">
        <label class="ds-form-label" for="edit_email">邮箱</label>
        <input class="ds-form-control" id="edit_email" name="edit_email" type="email" value="{{ user.email }}">
      </div>
      <div class="ds-form-row">
        <label class="ds-form-label" for="edit_user_type">角色</label>
        <select class="ds-form-control" id="edit_user_type" name="edit_user_type">
          <option value="superadmin" {% if user.user_type == 'superadmin' %}selected{% endif %}>超级管理员</option>
          <option value="sub_admin"  {% if user.user_type == 'sub_admin'  %}selected{% endif %}>次级管理员</option>
          <option value="user"       {% if user.user_type == 'user'       %}selected{% endif %}>普通用户</option>
        </select>
      </div>
      <div class="ds-form-row">
        <label class="ds-form-label" for="edit_permissions_project">项目权限</label>
        <input class="ds-form-control" id="edit_permissions_project" name="edit_permissions_project"
               type="text" placeholder="BPR-3M01,BPR-3M02" value="{{ user.permissions_project|default:'' }}">
        <p class="ds-form-hint">多个项目用逗号分隔。</p>
      </div>
      <div class="ds-form-row">
        <label class="ds-form-label">模块管理权限</label>
        <div style="display:flex;gap:16px;margin-top:6px;">
          {% with mp=user.module_permissions|default:'' %}
          <label style="font-size:13px;display:flex;align-items:center;gap:6px;">
            <input type="checkbox" name="module_permissions" value="delivery"
                   {% if 'delivery' in mp %}checked{% endif %}> Delivery 模块
          </label>
          <label style="font-size:13px;display:flex;align-items:center;gap:6px;">
            <input type="checkbox" name="module_permissions" value="seq"
                   {% if 'seq' in mp %}checked{% endif %}> 修饰模块
          </label>
          <label style="font-size:13px;display:flex;align-items:center;gap:6px;">
            <input type="checkbox" name="module_permissions" value="linker"
                   {% if 'linker' in mp %}checked{% endif %}> Linker 模块
          </label>
          {% endwith %}
        </div>
      </div>
      <div style="margin-top:24px;display:flex;justify-content:flex-end;gap:10px;">
        <a href="{% url 'author_list' %}" class="ds-btn ds-btn-ghost">返回</a>
        <button type="submit" class="ds-btn ds-btn-primary">保存</button>
      </div>
    </form>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Rewrite `templates/author_add.html`**

Replace the entire file:

```html
{% extends 'base.html' %}
{% block page_title %} — 新增用户{% endblock %}
{% block topbar_content %}
  <span class="ds-topbar-title">新增用户</span>
  <span class="ds-topbar-spacer"></span>
  <a href="{% url 'author_list' %}" class="ds-btn ds-btn-ghost">返回列表</a>
{% endblock %}
{% block content %}
<div class="ds-form-page">
  <div class="ds-form-card">
    <div class="ds-form-card-title">新增用户</div>
    {% if messages %}
    <div class="ds-alert-list">
      {% for message in messages %}
      <div class="ds-alert {% if 'error' in message.tags %}ds-alert-error{% else %}ds-alert-success{% endif %}">{{ message }}</div>
      {% endfor %}
    </div>
    {% endif %}
    <form method="POST" action="{% url 'add_author' %}">
      {% csrf_token %}
      <div class="ds-form-row">
        <label class="ds-form-label" for="username">用户名 <span style="color:#ef4444;">*</span></label>
        <input class="ds-form-control" id="username" name="username" required placeholder="用户名">
      </div>
      <div class="ds-form-row">
        <label class="ds-form-label" for="email">邮箱</label>
        <input class="ds-form-control" id="email" name="email" type="email" placeholder="邮箱地址">
      </div>
      <div class="ds-form-row">
        <label class="ds-form-label" for="user_type">角色</label>
        <select class="ds-form-control" id="user_type" name="user_type">
          <option value="user" selected>普通用户</option>
          <option value="sub_admin">次级管理员</option>
          <option value="superadmin">超级管理员</option>
        </select>
      </div>
      <div class="ds-form-row">
        <label class="ds-form-label" for="permissions_project">项目权限</label>
        <input class="ds-form-control" id="permissions_project" name="permissions_project"
               type="text" placeholder="BPR-3M01,BPR-3M02">
        <p class="ds-form-hint">多个项目用逗号分隔。留空则注册后由用户自行申请。</p>
      </div>
      <div class="ds-form-row">
        <label class="ds-form-label">模块管理权限</label>
        <div style="display:flex;gap:16px;margin-top:6px;">
          <label style="font-size:13px;display:flex;align-items:center;gap:6px;">
            <input type="checkbox" name="module_permissions" value="delivery"> Delivery 模块
          </label>
          <label style="font-size:13px;display:flex;align-items:center;gap:6px;">
            <input type="checkbox" name="module_permissions" value="seq"> 修饰模块
          </label>
          <label style="font-size:13px;display:flex;align-items:center;gap:6px;">
            <input type="checkbox" name="module_permissions" value="linker"> Linker 模块
          </label>
        </div>
      </div>
      <p class="ds-form-hint" style="margin-top:8px;">默认密码：<code>Bt123456</code>（用户首次登录后请修改）</p>
      <div style="margin-top:24px;display:flex;justify-content:flex-end;gap:10px;">
        <a href="{% url 'author_list' %}" class="ds-btn ds-btn-ghost">返回</a>
        <button type="submit" class="ds-btn ds-btn-primary">创建用户</button>
      </div>
    </form>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 4: Smoke-test manually**

```bash
source venv/bin/activate && python manage.py runserver
```

Log in as a superadmin, navigate to `/author_list/` and verify:
- Pending-request section appears (may be empty)
- Module-permissions column shows in user table
- Edit user shows 3-value role dropdown and module checkboxes
- Add user form shows correctly

- [ ] **Step 5: Commit**

```bash
git add templates/auth_list.html templates/auth_edit.html templates/author_add.html
git commit -m "feat: update user management templates for 3-role model and module permissions"
```

---

## Task 6: Sidebar visibility + profile template + register cleanup

**Files:**
- Modify: `templates/base.html`
- Create: `templates/profile.html`
- Modify: `templates/register.html`

- [ ] **Step 1: Update `templates/base.html` sidebar**

Find the `模块管理` section (lines ~64–73). Replace it and the `系统` section with:

```html
    <div class="ds-nav-divider"></div>
    <div class="ds-nav-section">模块管理</div>
    {% if request.user.can_manage_module('delivery') or request.user.user_type == 'superadmin' or request.user.is_superuser %}
    <a href="{% url 'module_list' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'module_list' or request.resolver_match.url_name == 'edit_module' %}active{% endif %}">
      <i class="bi bi-box-seam ds-nav-icon"></i> Delivery 模块
    </a>
    {% endif %}
    {% if request.user.can_manage_module('seq') or request.user.user_type == 'superadmin' or request.user.is_superuser %}
    <a href="{% url 'seqmodule_list' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'seqmodule_list' or request.resolver_match.url_name == 'edit_seqmodule' %}active{% endif %}">
      <i class="bi bi-check2-square ds-nav-icon"></i> 序列修饰模块
    </a>
    {% endif %}
    {% if request.user.can_manage_module('linker') or request.user.user_type == 'superadmin' or request.user.is_superuser %}
    <a href="{% url 'linkermodule_list' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'linkermodule_list' or request.resolver_match.url_name == 'edit_linkermodule' %}active{% endif %}">
      <i class="bi bi-link-45deg ds-nav-icon"></i> Linker 模块
    </a>
    {% endif %}
```

Replace the `系统` section (currently guarded by `user_type in 'admin,superadmin'`):

```html
    {% if request.user.user_type == 'superadmin' or request.user.is_superuser %}
    <div class="ds-nav-divider"></div>
    <div class="ds-nav-section">系统</div>
    <a href="{% url 'author_list' %}" class="ds-nav-item {% if request.resolver_match.url_name in 'author_list,add_author,edit_author' %}active{% endif %}">
      <i class="bi bi-people ds-nav-icon"></i> 用户管理
      {% if pending_approval_count > 0 %}
      <span style="background:#ef4444;color:#fff;border-radius:10px;font-size:10px;padding:1px 6px;margin-left:auto;">{{ pending_approval_count }}</span>
      {% endif %}
    </a>
    {% endif %}
```

Add a `我的资料` link for non-superadmin users, just before `</nav>`:

```html
    {% if not request.user.is_superuser and request.user.user_type != 'superadmin' %}
    <div class="ds-nav-divider"></div>
    <a href="{% url 'user_profile' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'user_profile' %}active{% endif %}">
      <i class="bi bi-person-circle ds-nav-icon"></i> 我的资料
    </a>
    {% endif %}
```

Note: Django templates cannot call methods with arguments like `can_manage_module('delivery')`. Instead, the sidebar checks are best handled via the `user_type` and `module_permissions` field directly. Replace the condition above with:

```html
    {% if 'delivery' in request.user.module_permissions or request.user.user_type == 'superadmin' or request.user.is_superuser %}
```

Do this for each of the three module nav items.

- [ ] **Step 2: Create `templates/profile.html`**

```html
{% extends 'base.html' %}
{% block page_title %} — 我的资料{% endblock %}
{% block topbar_content %}
  <span class="ds-topbar-title">我的资料</span>
{% endblock %}
{% block content %}
<div class="ds-form-page" style="max-width:640px;">

  {# ── Basic info ── #}
  <div class="ds-form-card" style="margin-bottom:16px;">
    <div class="ds-form-card-title">基本信息</div>
    <div class="ds-form-row">
      <label class="ds-form-label">用户名</label>
      <span style="font-size:14px;color:#1e293b;font-weight:600;">{{ profile_user.username }}</span>
    </div>
    <div class="ds-form-row">
      <label class="ds-form-label">角色</label>
      <span class="ds-role-badge ds-role-{{ profile_user.user_type }}">
        {% if profile_user.user_type == 'sub_admin' %}次级管理员{% else %}普通用户{% endif %}
      </span>
    </div>
    <div class="ds-form-row">
      <label class="ds-form-label">已批准项目</label>
      {% if approved_projects %}
        {% for p in approved_projects %}<code style="background:#f1f5f9;padding:2px 7px;border-radius:4px;font-size:11px;margin-right:4px;">{{ p }}</code>{% endfor %}
      {% else %}
        <span style="color:#94a3b8;font-size:13px;">暂无</span>
      {% endif %}
    </div>
    {% if module_perms %}
    <div class="ds-form-row">
      <label class="ds-form-label">模块管理权</label>
      {% for m in module_perms %}<code style="background:#dbeafe;color:#1d4ed8;padding:2px 7px;border-radius:4px;font-size:11px;margin-right:4px;">{{ m }}</code>{% endfor %}
    </div>
    {% endif %}
  </div>

  {# ── Change password ── #}
  <div class="ds-form-card" style="margin-bottom:16px;">
    <div class="ds-form-card-title">修改密码</div>
    <form method="POST" action="{% url 'change_password' %}">
      {% csrf_token %}
      <div class="ds-form-row">
        <label class="ds-form-label" for="old_password">当前密码</label>
        <input class="ds-form-control" id="old_password" name="old_password" type="password" required>
      </div>
      <div class="ds-form-row">
        <label class="ds-form-label" for="new_password1">新密码</label>
        <input class="ds-form-control" id="new_password1" name="new_password1" type="password" required>
      </div>
      <div class="ds-form-row">
        <label class="ds-form-label" for="new_password2">确认新密码</label>
        <input class="ds-form-control" id="new_password2" name="new_password2" type="password" required>
      </div>
      <div style="display:flex;justify-content:flex-end;margin-top:16px;">
        <button type="submit" class="ds-btn ds-btn-primary">修改密码</button>
      </div>
    </form>
  </div>

  {# ── Project access requests ── #}
  <div class="ds-form-card" style="margin-bottom:16px;">
    <div class="ds-form-card-title">申请项目权限</div>
    <form method="POST" action="{% url 'request_project_access' %}">
      {% csrf_token %}
      <div class="ds-form-row">
        <label class="ds-form-label" for="project_codes">项目号</label>
        <input class="ds-form-control" id="project_codes" name="project_codes"
               placeholder="BPR-350,BPR-3T03" required>
        <p class="ds-form-hint">多个项目用逗号分隔</p>
      </div>
      <div class="ds-form-row">
        <label class="ds-form-label" for="note">申请说明</label>
        <input class="ds-form-control" id="note" name="note" placeholder="（选填）说明申请原因">
      </div>
      <div style="display:flex;justify-content:flex-end;margin-top:16px;">
        <button type="submit" class="ds-btn ds-btn-primary">提交申请</button>
      </div>
    </form>
  </div>

  {# ── Request history ── #}
  {% if access_requests %}
  <div class="ds-table-card">
    <div style="padding:9px 14px;font-size:12px;font-weight:600;color:#64748b;border-bottom:1.5px solid #e8edf4;">申请记录</div>
    <div class="ds-table-scroll">
      <table class="ds-table">
        <thead>
          <tr>
            <th>项目号</th>
            <th>状态</th>
            <th>备注</th>
            <th>时间</th>
          </tr>
        </thead>
        <tbody>
          {% for req in access_requests %}
          <tr>
            <td><code style="font-size:11px;">{{ req.project_codes }}</code></td>
            <td>
              {% if req.status == 'pending' %}
                <span style="color:#d97706;font-size:12px;font-weight:600;">⏳ 待审批</span>
              {% elif req.status == 'approved' %}
                <span style="color:#16a34a;font-size:12px;font-weight:600;">✅ 已批准</span>
              {% else %}
                <span style="color:#dc2626;font-size:12px;font-weight:600;">❌ 已拒绝</span>
              {% endif %}
            </td>
            <td class="cell-dim">{{ req.review_note|default:'—' }}</td>
            <td class="cell-dim" style="font-size:11.5px;">{{ req.requested_at|date:"Y-m-d H:i" }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
  {% endif %}

</div>
{% endblock %}
```

- [ ] **Step 3: Clean up `templates/register.html`**

Remove the `<div>` block containing the `user_type` select (lines 44–52). Also remove the `permissions_project` input (lines 53–58) — users request projects after login. The form should only collect `username`, `email`, `password`:

```html
  <form method="post" action="/register/">
    {% csrf_token %}
    <div style="margin-bottom:14px;">
      <label style="display:block;font-size:13px;font-weight:500;color:#374151;margin-bottom:5px;" for="reg_username">用户名</label>
      <input type="text" class="ds-form-control" id="reg_username" name="username" placeholder="用户名" required style="width:100%;box-sizing:border-box;">
    </div>
    <div style="margin-bottom:14px;">
      <label style="display:block;font-size:13px;font-weight:500;color:#374151;margin-bottom:5px;" for="reg_email">邮箱</label>
      <input type="email" class="ds-form-control" id="reg_email" name="email" placeholder="邮箱地址" style="width:100%;box-sizing:border-box;">
    </div>
    <div style="margin-bottom:20px;">
      <label style="display:block;font-size:13px;font-weight:500;color:#374151;margin-bottom:5px;" for="reg_password">密码</label>
      <input type="password" class="ds-form-control" id="reg_password" name="password" placeholder="密码" required style="width:100%;box-sizing:border-box;">
    </div>
    <p style="font-size:12px;color:#94a3b8;margin:0 0 16px 0;">注册后可在「我的资料」页申请项目权限。</p>
    <button type="submit" class="ds-btn ds-btn-primary" style="width:100%;justify-content:center;">注册</button>
  </form>
```

Also update `register_view` in `views.py` to handle missing `permissions_project` gracefully (already done in Task 3 Step 4 where we hardcoded `permissions_project=''`).

- [ ] **Step 4: Run full test suite**

```bash
python manage.py test app01 -v 2 2>&1 | tail -20
```

Expected: all new tests pass; the 4 pre-existing `CheckDuplicatesTests` failures remain (pre-existing bug unrelated to this work).

- [ ] **Step 5: Smoke-test in browser**

```bash
python manage.py runserver
```

Check:
1. Register a new user → lands with `user_type='user'`, no project permissions
2. Log in as new user → see "我的资料" in sidebar; submit project request
3. Log in as superadmin → see yellow pending-request bar in user management; approve request
4. Log back in as new user → approved project now visible in their profile
5. Module-nav items hidden until superadmin grants module_permissions via edit user

- [ ] **Step 6: Commit**

```bash
git add templates/base.html templates/profile.html templates/register.html
git commit -m "feat: sidebar visibility rules, profile page, register cleanup"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|-----------------|------|
| 3-role model (superadmin/sub_admin/user) | Task 1 |
| module_permissions field | Task 1 |
| ProjectAccessRequest model | Task 1 |
| Migration + role remap + data_admin backfill | Task 1 |
| _is_superadmin helper | Task 2 |
| user_can_edit_delivery updated | Task 2 |
| author_list/add/edit/drop → superadmin only | Task 3 |
| Module views → can_manage_module(name) | Task 3 |
| delete_experiment/clone/share → sub_admin+ | Task 3 |
| register_view hardcodes user_type='user' | Task 3 |
| user_profile view | Task 4 |
| request_project_access view | Task 4 |
| approve_project_request view | Task 4 |
| Context processor for pending badge count | Task 4 |
| auth_list.html with approval section | Task 5 |
| auth_edit.html with 3-role dropdown + module checkboxes | Task 5 |
| author_add.html fixed field names + module checkboxes | Task 5 |
| base.html sidebar visibility + badge | Task 6 |
| profile.html | Task 6 |
| register.html cleanup | Task 6 |

All spec requirements covered. ✅
