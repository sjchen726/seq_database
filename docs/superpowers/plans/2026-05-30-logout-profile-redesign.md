# Logout + Profile Redesign + Module Permission Request — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a sidebar logout button, redesign the profile page as a professional two-column layout, and introduce a module-permission request workflow (user submits → superadmin approves → `module_permissions` field updated).

**Architecture:** Three independent but related changes: (1) logout view + POST form in sidebar footer; (2) `ModulePermissionRequest` model mirroring `ProjectAccessRequest` with approval in the same `auth_list` yellow bar; (3) `profile.html` full rewrite using CSS grid (320px + 1fr) with combined request-history table at the bottom.

**Tech Stack:** Django 5.1 / Python 3.10, MySQL, function-based views in `app01/views.py`, Django templates, Bootstrap Icons, design-system CSS.

---

## File Map

| File | Change |
|------|--------|
| `app01/models.py` | Add `ModulePermissionRequest` |
| `app01/migrations/0035_module_permission_request.py` | CreateModel migration |
| `app01/admin.py` | Add `ModulePermissionRequestAdmin` |
| `app01/views.py` | Add `logout_view`, `request_module_access`, `approve_module_request`; update `author_list`, `user_profile` |
| `app01/context_processors.py` | Sum both pending counts |
| `bms/urls.py` | Add `/logout/`, `/request_module/`, `/approve_module_request/<id>/` |
| `templates/base.html` | Logout button in sidebar footer |
| `templates/auth_list.html` | Rename `pending_requests` → `pending_project_requests`; add module-request section |
| `templates/profile.html` | Full rewrite: two-column grid layout + module request form + combined history |

---

## Task 1: ModulePermissionRequest model + migration + admin

**Files:**
- Modify: `app01/models.py`
- Create: `app01/migrations/0035_module_permission_request.py`
- Modify: `app01/admin.py`
- Modify: `app01/tests.py`

- [ ] **Step 1: Write failing tests for the new model**

Append to `app01/tests.py`:

```python
class ModulePermissionRequestModelTests(TestCase):
    """ModulePermissionRequest basic model behaviour."""

    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='requester2', password='pass', user_type='user'
        )
        self.admin = LmsUser.objects.create_user(
            username='sa2', password='pass', user_type='superadmin'
        )

    def test_create_pending_request(self):
        from app01.models import ModulePermissionRequest
        req = ModulePermissionRequest.objects.create(
            user=self.user,
            modules_requested='delivery,seq',
        )
        self.assertEqual(req.status, 'pending')
        self.assertIsNone(req.reviewed_by)
        self.assertIsNone(req.reviewed_at)

    def test_str_includes_username_and_modules(self):
        from app01.models import ModulePermissionRequest
        req = ModulePermissionRequest.objects.create(
            user=self.user, modules_requested='linker'
        )
        s = str(req)
        self.assertIn('requester2', s)
        self.assertIn('linker', s)

    def test_default_ordering_newest_first(self):
        from app01.models import ModulePermissionRequest
        r1 = ModulePermissionRequest.objects.create(
            user=self.user, modules_requested='delivery'
        )
        r2 = ModulePermissionRequest.objects.create(
            user=self.user, modules_requested='seq'
        )
        qs = list(ModulePermissionRequest.objects.all())
        self.assertEqual(qs[0], r2)
        self.assertEqual(qs[1], r1)

    def test_reviewed_fields_update(self):
        from app01.models import ModulePermissionRequest
        from django.utils import timezone
        req = ModulePermissionRequest.objects.create(
            user=self.user, modules_requested='delivery'
        )
        req.status = 'approved'
        req.reviewed_by = self.admin
        req.reviewed_at = timezone.now()
        req.save()
        req.refresh_from_db()
        self.assertEqual(req.status, 'approved')
        self.assertEqual(req.reviewed_by, self.admin)
        self.assertIsNotNone(req.reviewed_at)
```

- [ ] **Step 2: Run tests — expect failure (model doesn't exist yet)**

```bash
source venv/bin/activate
python manage.py test app01.tests.ModulePermissionRequestModelTests -v 2 2>&1 | tail -20
```

Expected: `ImportError` or `django.core.exceptions.ImproperlyConfigured` — `ModulePermissionRequest` doesn't exist.

- [ ] **Step 3: Add `ModulePermissionRequest` to `app01/models.py`**

After the `ProjectAccessRequest` class (near end of file), add:

```python
class ModulePermissionRequest(models.Model):
    STATUS_CHOICES = [
        ('pending',  '待审批'),
        ('approved', '已批准'),
        ('rejected', '已拒绝'),
    ]

    user = models.ForeignKey(
        LmsUser, on_delete=models.CASCADE, related_name='module_requests',
        verbose_name='申请人',
    )
    modules_requested = models.CharField('申请模块', max_length=64)
    # Comma-separated values from: 'delivery', 'seq', 'linker'
    note = models.CharField('申请说明', max_length=256, blank=True)
    requested_at = models.DateTimeField('申请时间', auto_now_add=True)
    status = models.CharField(
        '状态', max_length=16, choices=STATUS_CHOICES, default='pending'
    )
    reviewed_by = models.ForeignKey(
        LmsUser, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='reviewed_module_requests', verbose_name='审批人',
    )
    reviewed_at = models.DateTimeField('审批时间', null=True, blank=True)
    review_note = models.CharField('审批备注', max_length=256, blank=True)

    class Meta:
        verbose_name = '模块权限申请'
        verbose_name_plural = '模块权限申请'
        ordering = ['-requested_at']

    def __str__(self):
        return f"{self.user.username} → {self.modules_requested} [{self.status}]"
```

- [ ] **Step 4: Create migration 0035**

```bash
python manage.py makemigrations app01 --name module_permission_request
```

Expected output: `Migrations for 'app01': app01/migrations/0035_module_permission_request.py`

- [ ] **Step 5: Apply migration**

```bash
python manage.py migrate app01
```

Expected: `Applying app01.0035_module_permission_request... OK`

- [ ] **Step 6: Register admin class in `app01/admin.py`**

Change the import line at top:
```python
from .models import (
    Sequence, Delivery, SeqInfo, DuplexRelationship,
    DeliveryModule, SeqModule, LinkerModule, LmsUser,
    ProjectAccessRequest, ModulePermissionRequest,
)
```

Append after `ProjectAccessRequestAdmin`:
```python

@admin.register(ModulePermissionRequest)
class ModulePermissionRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'modules_requested', 'status', 'requested_at', 'reviewed_by')
    list_filter = ('status',)
    search_fields = ('user__username', 'modules_requested')
```

- [ ] **Step 7: Run tests — expect pass**

```bash
python manage.py test app01.tests.ModulePermissionRequestModelTests -v 2
```

Expected: `Ran 4 tests in ...s OK`

- [ ] **Step 8: Run full test suite to check for regressions**

```bash
python manage.py test app01 -v 1 2>&1 | tail -10
```

Expected: all tests pass (same count as before + 4 new).

- [ ] **Step 9: Commit**

```bash
git add app01/models.py app01/migrations/0035_module_permission_request.py app01/admin.py app01/tests.py
git commit -m "feat: add ModulePermissionRequest model, migration 0035, admin"
```

---

## Task 2: Logout view + URL + sidebar button

**Files:**
- Modify: `app01/views.py`
- Modify: `bms/urls.py`
- Modify: `templates/base.html`
- Modify: `app01/tests.py`

- [ ] **Step 1: Write failing tests for logout view**

Append to `app01/tests.py`:

```python
class LogoutViewTests(TestCase):
    """Logout view: POST-only, clears session, redirects to login."""

    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='logout_test_user', password='pass', user_type='user'
        )

    def test_get_returns_405(self):
        self.client.login(username='logout_test_user', password='pass')
        r = self.client.get('/logout/')
        self.assertEqual(r.status_code, 405)

    def test_post_redirects_to_login(self):
        self.client.login(username='logout_test_user', password='pass')
        r = self.client.post('/logout/')
        self.assertRedirects(r, '/login/', fetch_redirect_response=False)

    def test_post_clears_authentication(self):
        self.client.login(username='logout_test_user', password='pass')
        self.client.post('/logout/')
        # Subsequent request to a login-required page should redirect
        r = self.client.get('/profile/')
        self.assertNotEqual(r.status_code, 200)  # no longer authenticated
```

- [ ] **Step 2: Run tests — expect failure (URL doesn't exist)**

```bash
python manage.py test app01.tests.LogoutViewTests -v 2 2>&1 | tail -15
```

Expected: `NoReverseMatch` or `404` — `/logout/` not mapped.

- [ ] **Step 3: Add `logout_view` to `app01/views.py`**

Find the `change_password` view (line ~562). Add the new view just before it (or at the end of the user/auth section):

```python
@require_POST
def logout_view(request):
    """POST-only logout — clears session and redirects to login."""
    from django.contrib.auth import logout as auth_logout
    auth_logout(request)
    return redirect('login')
```

Note: `@require_POST` is already imported at top of views.py. `redirect` is also imported. No additional imports needed.

- [ ] **Step 4: Add URL to `bms/urls.py`**

In the urlpatterns list, just before the `profile/` entry at the bottom, add:

```python
path('logout/', views.logout_view, name='logout'),
```

- [ ] **Step 5: Update sidebar footer in `templates/base.html`**

Replace the existing sidebar footer block:

```html
    <div class="ds-sidebar-footer">
      <div class="ds-user-card">
        <div class="ds-user-avatar">{{ request.user.username|first|upper }}</div>
        <div>
          <div class="ds-user-name">{{ request.user.username }}</div>
          <div class="ds-user-role">
            <span class="ds-online-dot"></span>
            {{ request.user.user_type|default:"user" }}
          </div>
        </div>
      </div>
    </div>
```

With:

```html
    <div class="ds-sidebar-footer">
      <div class="ds-user-card" style="justify-content:space-between;">
        <div style="display:flex;align-items:center;gap:10px;">
          <div class="ds-user-avatar">{{ request.user.username|first|upper }}</div>
          <div>
            <div class="ds-user-name">{{ request.user.username }}</div>
            <div class="ds-user-role">
              <span class="ds-online-dot"></span>
              {{ request.user.user_type|default:"user" }}
            </div>
          </div>
        </div>
        {% if request.user.is_authenticated %}
        <form method="POST" action="{% url 'logout' %}" style="margin:0;">
          {% csrf_token %}
          <button type="submit" title="退出登录"
                  style="background:none;border:none;cursor:pointer;padding:4px 6px;
                         border-radius:6px;color:#94a3b8;display:flex;align-items:center;"
                  onmouseover="this.style.color='#ef4444';this.style.background='#fef2f2'"
                  onmouseout="this.style.color='#94a3b8';this.style.background='none'">
            <i class="bi bi-box-arrow-right" style="font-size:16px;"></i>
          </button>
        </form>
        {% endif %}
      </div>
    </div>
```

- [ ] **Step 6: Run tests — expect pass**

```bash
python manage.py test app01.tests.LogoutViewTests -v 2
```

Expected: `Ran 3 tests in ...s OK`

- [ ] **Step 7: Run full test suite**

```bash
python manage.py test app01 -v 1 2>&1 | tail -5
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add app01/views.py bms/urls.py templates/base.html app01/tests.py
git commit -m "feat: add logout view, URL, sidebar logout button"
```

---

## Task 3: request_module_access + approve_module_request views + context processor + user_profile + URLs

**Files:**
- Modify: `app01/views.py`
- Modify: `app01/context_processors.py`
- Modify: `bms/urls.py`
- Modify: `app01/tests.py`

- [ ] **Step 1: Write failing tests**

Append to `app01/tests.py`:

```python
class ModuleRequestWorkflowTests(TestCase):
    """request_module_access and approve_module_request views."""

    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='mod_requester', password='pass', user_type='user',
            module_permissions='',
        )
        self.admin = LmsUser.objects.create_user(
            username='mod_sa', password='pass', user_type='superadmin',
        )
        self.client_u = self.client_class()
        self.client_u.login(username='mod_requester', password='pass')
        self.client_sa = self.client_class()
        self.client_sa.login(username='mod_sa', password='pass')

    def test_user_can_submit_module_request(self):
        from app01.models import ModulePermissionRequest
        r = self.client_u.post('/request_module/', {
            'modules_requested': ['delivery', 'seq'],
            'note': 'need access',
        })
        self.assertIn(r.status_code, [302, 200])
        req = ModulePermissionRequest.objects.filter(user=self.user).first()
        self.assertIsNotNone(req)
        self.assertEqual(req.status, 'pending')
        self.assertIn('delivery', req.modules_requested)

    def test_duplicate_pending_blocked(self):
        from app01.models import ModulePermissionRequest
        ModulePermissionRequest.objects.create(
            user=self.user, modules_requested='delivery'
        )
        r = self.client_u.post('/request_module/', {
            'modules_requested': ['seq'],
        })
        self.assertIn(r.status_code, [302, 200])
        # Still only one pending request
        self.assertEqual(
            ModulePermissionRequest.objects.filter(user=self.user, status='pending').count(),
            1,
        )

    def test_empty_modules_rejected(self):
        from app01.models import ModulePermissionRequest
        r = self.client_u.post('/request_module/', {'modules_requested': []})
        self.assertIn(r.status_code, [302, 200])
        self.assertEqual(ModulePermissionRequest.objects.filter(user=self.user).count(), 0)

    def test_superadmin_cannot_submit_module_request(self):
        from app01.models import ModulePermissionRequest
        r = self.client_sa.post('/request_module/', {
            'modules_requested': ['delivery'],
        })
        self.assertIn(r.status_code, [302, 200])
        self.assertEqual(ModulePermissionRequest.objects.filter(user=self.admin).count(), 0)

    def test_approve_module_request_grants_permissions(self):
        from app01.models import ModulePermissionRequest
        req = ModulePermissionRequest.objects.create(
            user=self.user, modules_requested='delivery,linker'
        )
        r = self.client_sa.post(f'/approve_module_request/{req.id}/', {
            'action': 'approve',
            'review_note': '',
        })
        self.assertIn(r.status_code, [302, 200])
        req.refresh_from_db()
        self.assertEqual(req.status, 'approved')
        self.user.refresh_from_db()
        self.assertIn('delivery', self.user.module_permissions)
        self.assertIn('linker', self.user.module_permissions)

    def test_approve_merges_with_existing_permissions(self):
        from app01.models import ModulePermissionRequest
        self.user.module_permissions = 'seq'
        self.user.save()
        req = ModulePermissionRequest.objects.create(
            user=self.user, modules_requested='delivery'
        )
        self.client_sa.post(f'/approve_module_request/{req.id}/', {
            'action': 'approve',
            'review_note': '',
        })
        self.user.refresh_from_db()
        mods = {m for m in self.user.module_permissions.split(',') if m}
        self.assertIn('seq', mods)
        self.assertIn('delivery', mods)

    def test_double_approve_no_duplicate_modules(self):
        from app01.models import ModulePermissionRequest
        req = ModulePermissionRequest.objects.create(
            user=self.user, modules_requested='delivery'
        )
        self.client_sa.post(f'/approve_module_request/{req.id}/', {'action': 'approve', 'review_note': ''})
        self.client_sa.post(f'/approve_module_request/{req.id}/', {'action': 'approve', 'review_note': ''})
        self.user.refresh_from_db()
        mods = [m for m in self.user.module_permissions.split(',') if m]
        self.assertEqual(mods.count('delivery'), 1)

    def test_reject_does_not_grant_permissions(self):
        from app01.models import ModulePermissionRequest
        req = ModulePermissionRequest.objects.create(
            user=self.user, modules_requested='seq'
        )
        self.client_sa.post(f'/approve_module_request/{req.id}/', {
            'action': 'reject',
            'review_note': 'not approved',
        })
        req.refresh_from_db()
        self.assertEqual(req.status, 'rejected')
        self.user.refresh_from_db()
        self.assertNotIn('seq', self.user.module_permissions or '')

    def test_non_superadmin_cannot_approve(self):
        from app01.models import ModulePermissionRequest
        req = ModulePermissionRequest.objects.create(
            user=self.user, modules_requested='delivery'
        )
        r = self.client_u.post(f'/approve_module_request/{req.id}/', {
            'action': 'approve',
        })
        self.assertIn(r.status_code, [302, 403])
        req.refresh_from_db()
        self.assertEqual(req.status, 'pending')
```

- [ ] **Step 2: Run tests — expect failure**

```bash
python manage.py test app01.tests.ModuleRequestWorkflowTests -v 2 2>&1 | tail -20
```

Expected: `NoReverseMatch` — `/request_module/` and `/approve_module_request/` not yet mapped.

- [ ] **Step 3: Add `request_module_access` view to `app01/views.py`**

Add after `request_project_access` view (around line 4971):

```python

@login_required
@require_POST
def request_module_access(request):
    """Submit a new module permission request."""
    if _is_superadmin(request.user):
        messages.error(request, '超级管理员无需申请模块权限。')
        return redirect('author_list')

    modules = request.POST.getlist('modules_requested')
    note = request.POST.get('note', '').strip()

    # Only accept known valid values
    valid = {'delivery', 'seq', 'linker'}
    modules = [m for m in modules if m in valid]

    if not modules:
        messages.error(request, '请至少选择一个模块。')
        return redirect('user_profile')

    if ModulePermissionRequest.objects.filter(user=request.user, status='pending').exists():
        messages.warning(request, '您有一个待审批的模块权限申请，请等待处理后再提交新申请。')
        return redirect('user_profile')

    ModulePermissionRequest.objects.create(
        user=request.user,
        modules_requested=','.join(sorted(modules)),
        note=note,
    )
    messages.success(request, '模块权限申请已提交，等待超级管理员审批。')
    return redirect('user_profile')
```

- [ ] **Step 4: Add `approve_module_request` view to `app01/views.py`**

Add after `approve_project_request` view (around line 5012):

```python

@login_required
@require_POST
def approve_module_request(request, req_id):
    """Approve or reject a module permission request. Superadmin only."""
    if not _is_superadmin(request.user):
        messages.error(request, '您没有权限执行此操作。')
        return redirect('seq_list')

    try:
        req = ModulePermissionRequest.objects.select_related('user').get(pk=req_id)
    except ModulePermissionRequest.DoesNotExist:
        messages.error(request, '申请记录不存在。')
        return redirect('author_list')

    action = request.POST.get('action')
    review_note = request.POST.get('review_note', '').strip()

    req.reviewed_by = request.user
    req.reviewed_at = timezone.now()
    req.review_note = review_note

    if action == 'approve':
        req.status = 'approved'
        user = req.user
        existing = {m for m in (user.module_permissions or '').split(',') if m}
        new_mods = {m for m in req.modules_requested.split(',') if m}
        merged = sorted(existing | new_mods)
        user.module_permissions = ','.join(merged)
        user.save(update_fields=['module_permissions'])
        messages.success(request, f'已批准 {user.username} 的模块权限申请。')
    elif action == 'reject':
        req.status = 'rejected'
        messages.success(request, f'已拒绝申请，备注：{review_note or "无"}。')
    else:
        messages.error(request, '无效操作。')
        return redirect('author_list')

    req.save()
    return redirect('author_list')
```

Note: `ModulePermissionRequest` must be imported at the top of `views.py`. Find the models import line and add it:

```python
from .models import (
    ...
    ProjectAccessRequest, ModulePermissionRequest,
)
```

(or wherever `ProjectAccessRequest` is imported — add `ModulePermissionRequest` alongside it).

- [ ] **Step 5: Update `user_profile` view to include module_requests in context**

The `user_profile` view currently returns (lines 4933–4946):
```python
def user_profile(request):
    """Personal profile page for non-superadmin users."""
    if _is_superadmin(request.user):
        return redirect('author_list')

    user = request.user
    requests_qs = ProjectAccessRequest.objects.filter(user=user).order_by('-requested_at')

    return render(request, 'profile.html', {
        'profile_user': user,
        'access_requests': requests_qs,
        'approved_projects': user.get_allowed_projects(),
        'module_perms': [m for m in (user.module_permissions or '').split(',') if m],
    })
```

Replace with:

```python
@login_required
def user_profile(request):
    """Personal profile page for non-superadmin users."""
    if _is_superadmin(request.user):
        return redirect('author_list')

    user = request.user
    project_reqs = ProjectAccessRequest.objects.filter(user=user).order_by('-requested_at')
    module_reqs = ModulePermissionRequest.objects.filter(user=user).order_by('-requested_at')

    # Merge both request types into a single sorted list for combined history table
    combined = []
    for r in project_reqs:
        combined.append({
            'req_type': '项目',
            'content': r.project_codes,
            'status': r.status,
            'review_note': r.review_note,
            'requested_at': r.requested_at,
        })
    for r in module_reqs:
        combined.append({
            'req_type': '模块',
            'content': r.modules_requested,
            'status': r.status,
            'review_note': r.review_note,
            'requested_at': r.requested_at,
        })
    combined.sort(key=lambda x: x['requested_at'], reverse=True)

    return render(request, 'profile.html', {
        'profile_user': user,
        'combined_requests': combined,
        'approved_projects': user.get_allowed_projects(),
        'module_perms': [m for m in (user.module_permissions or '').split(',') if m],
    })
```

Note: removed the old `access_requests` context key — profile.html (Task 5) will use `combined_requests`.

- [ ] **Step 6: Update `app01/context_processors.py`**

Replace the entire file:

```python
from app01.models import ProjectAccessRequest, ModulePermissionRequest


def pending_approval_count(request):
    """Inject total pending request count (project + module) for superadmin sidebar badge."""
    count = 0
    if (request.user.is_authenticated and
            (request.user.is_superuser or
             getattr(request.user, 'user_type', '') == 'superadmin')):
        count = (ProjectAccessRequest.objects.filter(status='pending').count()
               + ModulePermissionRequest.objects.filter(status='pending').count())
    return {'pending_approval_count': count}
```

- [ ] **Step 7: Add URLs to `bms/urls.py`**

Add these three lines just before the `path('profile/', ...)` line:

```python
path('logout/', views.logout_view, name='logout'),  # already added in Task 2
path('request_module/', views.request_module_access, name='request_module_access'),
path('approve_module_request/<int:req_id>/', views.approve_module_request, name='approve_module_request'),
```

(Only add the module lines if logout was already added in Task 2.)

- [ ] **Step 8: Run tests — expect pass**

```bash
python manage.py test app01.tests.ModuleRequestWorkflowTests -v 2
```

Expected: `Ran 9 tests in ...s OK`

- [ ] **Step 9: Run full test suite**

```bash
python manage.py test app01 -v 1 2>&1 | tail -5
```

Expected: all tests pass.

- [ ] **Step 10: Commit**

```bash
git add app01/views.py app01/context_processors.py bms/urls.py app01/tests.py
git commit -m "feat: add request_module_access and approve_module_request views, update context_processor and user_profile"
```

---

## Task 4: auth_list.html split + author_list view update

**Files:**
- Modify: `app01/views.py` (author_list function, lines 446–459)
- Modify: `templates/auth_list.html`
- Modify: `app01/tests.py`

- [ ] **Step 1: Write failing tests for author_list context keys**

Append to `app01/tests.py`:

```python
class AuthorListContextTests(TestCase):
    """author_list view passes correct context keys after refactor."""

    def setUp(self):
        self.admin = LmsUser.objects.create_user(
            username='ctx_sa', password='pass', user_type='superadmin'
        )
        self.client.login(username='ctx_sa', password='pass')

    def test_context_has_pending_project_requests_key(self):
        r = self.client.get('/author_list/')
        self.assertIn('pending_project_requests', r.context)

    def test_context_has_pending_module_requests_key(self):
        r = self.client.get('/author_list/')
        self.assertIn('pending_module_requests', r.context)

    def test_context_does_not_have_old_pending_requests_key(self):
        r = self.client.get('/author_list/')
        self.assertNotIn('pending_requests', r.context)

    def test_module_request_appears_in_pending_module_requests(self):
        from app01.models import ModulePermissionRequest
        requester = LmsUser.objects.create_user(
            username='ctx_req', password='pass', user_type='user'
        )
        ModulePermissionRequest.objects.create(
            user=requester, modules_requested='delivery'
        )
        r = self.client.get('/author_list/')
        self.assertEqual(len(r.context['pending_module_requests']), 1)
```

- [ ] **Step 2: Run tests — expect failure**

```bash
python manage.py test app01.tests.AuthorListContextTests -v 2 2>&1 | tail -15
```

Expected: `AssertionError: 'pending_project_requests' not found in response.context` (view still uses old key).

- [ ] **Step 3: Update `author_list` view in `app01/views.py`**

Replace lines 446–459 (the entire `author_list` function body):

```python
def author_list(request):
    if not _is_superadmin(request.user):
        messages.error(request, '您没有权限访问用户管理页面。')
        return redirect('seq_list')

    users = LmsUser.objects.all().order_by('username')
    pending_project_requests = ProjectAccessRequest.objects.filter(
        status='pending'
    ).select_related('user')
    pending_module_requests = ModulePermissionRequest.objects.filter(
        status='pending'
    ).select_related('user')

    return render(request, 'auth_list.html', {
        'user_list': users,
        'pending_project_requests': pending_project_requests,
        'pending_module_requests': pending_module_requests,
    })
```

- [ ] **Step 4: Update `templates/auth_list.html` — rename project section and add module section**

Replace the existing pending-requests block (lines 13–58):

```html
{% if pending_project_requests %}
<div class="ds-table-card" style="margin-bottom:16px;">
  <div style="padding:10px 16px;background:#fef9c3;border-bottom:1.5px solid #fde047;font-size:13px;font-weight:600;color:#854d0e;">
    ⏳ 待审批的项目权限申请（{{ pending_project_requests|length }} 条）
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
        {% for req in pending_project_requests %}
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

{% if pending_module_requests %}
<div class="ds-table-card" style="margin-bottom:16px;">
  <div style="padding:10px 16px;background:#fef9c3;border-bottom:1.5px solid #fde047;font-size:13px;font-weight:600;color:#854d0e;">
    ⏳ 待审批的模块权限申请（{{ pending_module_requests|length }} 条）
  </div>
  <div class="ds-table-scroll">
    <table class="ds-table">
      <thead>
        <tr>
          <th>申请人</th>
          <th>申请模块</th>
          <th>说明</th>
          <th>申请时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        {% for req in pending_module_requests %}
        <tr>
          <td><strong>{{ req.user.username }}</strong></td>
          <td><code style="font-size:11px;">{{ req.modules_requested }}</code></td>
          <td class="cell-dim">{{ req.note|default:'—' }}</td>
          <td class="cell-dim">{{ req.requested_at|date:"Y-m-d H:i" }}</td>
          <td>
            <div style="display:flex;gap:6px;align-items:center;">
              <form method="POST" action="{% url 'approve_module_request' req.id %}" style="display:inline;">
                {% csrf_token %}
                <input type="hidden" name="action" value="approve">
                <button type="submit" class="ds-btn ds-btn-primary" style="height:28px;padding:0 10px;font-size:11.5px;">批准</button>
              </form>
              <form method="POST" action="{% url 'approve_module_request' req.id %}" style="display:inline;">
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
```

- [ ] **Step 5: Run tests — expect pass**

```bash
python manage.py test app01.tests.AuthorListContextTests -v 2
```

Expected: `Ran 4 tests in ...s OK`

- [ ] **Step 6: Run full test suite**

```bash
python manage.py test app01 -v 1 2>&1 | tail -5
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add app01/views.py templates/auth_list.html app01/tests.py
git commit -m "feat: split auth_list pending section into project and module sub-sections"
```

---

## Task 5: profile.html full rewrite + user_profile view update

**Files:**
- Modify: `templates/profile.html` (full rewrite)
- Modify: `app01/tests.py`

Note: `user_profile` view was already updated in Task 3 to pass `combined_requests`. This task only rewrites the template and adds template-rendering tests.

- [ ] **Step 1: Write failing test for profile page rendering**

Append to `app01/tests.py`:

```python
class ProfilePageTests(TestCase):
    """Profile page renders two-column layout and combined history."""

    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='profile_user', password='pass', user_type='user',
            permissions_project='BPR-350',
            module_permissions='delivery',
        )
        self.client.login(username='profile_user', password='pass')

    def test_profile_page_loads(self):
        r = self.client.get('/profile/')
        self.assertEqual(r.status_code, 200)

    def test_profile_shows_approved_projects(self):
        r = self.client.get('/profile/')
        self.assertContains(r, 'BPR-350')

    def test_profile_shows_module_perms(self):
        r = self.client.get('/profile/')
        self.assertContains(r, 'delivery')

    def test_profile_combined_history_shows_both_types(self):
        from app01.models import ProjectAccessRequest, ModulePermissionRequest
        ProjectAccessRequest.objects.create(
            user=self.user, project_codes='BPR-999'
        )
        ModulePermissionRequest.objects.create(
            user=self.user, modules_requested='seq'
        )
        r = self.client.get('/profile/')
        self.assertContains(r, '项目')
        self.assertContains(r, '模块')

    def test_superadmin_redirected_from_profile(self):
        admin = LmsUser.objects.create_user(
            username='profile_sa', password='pass', user_type='superadmin'
        )
        c = self.client_class()
        c.login(username='profile_sa', password='pass')
        r = c.get('/profile/')
        self.assertEqual(r.status_code, 302)

    def test_module_request_form_present(self):
        r = self.client.get('/profile/')
        self.assertContains(r, 'request_module_access')
        self.assertContains(r, '申请模块权限')
```

- [ ] **Step 2: Run tests — some may already pass (profile page loads) but module form test fails**

```bash
python manage.py test app01.tests.ProfilePageTests -v 2 2>&1 | tail -20
```

Expected: `test_module_request_form_present` fails — current profile.html doesn't have the module request form or combined history.

- [ ] **Step 3: Rewrite `templates/profile.html`**

Replace the entire file with:

```html
{% extends 'base.html' %}
{% block page_title %} — 我的资料{% endblock %}
{% block topbar_content %}
  <span class="ds-topbar-title">我的资料</span>
{% endblock %}
{% block content %}
<div style="max-width:960px;margin:0 auto;">

  {# ── Two-column grid ── #}
  <div style="display:grid;grid-template-columns:320px 1fr;gap:20px;align-items:start;">

    {# ── LEFT COLUMN ── #}
    <div>

      {# Info card #}
      <div class="ds-form-card" style="margin-bottom:16px;text-align:center;">
        <div style="width:60px;height:60px;border-radius:50%;
                    background:linear-gradient(135deg,#6366f1,#8b5cf6);
                    color:#fff;font-size:24px;font-weight:700;
                    display:flex;align-items:center;justify-content:center;
                    margin:0 auto 12px;">
          {{ profile_user.username|first|upper }}
        </div>
        <div style="font-size:16px;font-weight:700;color:#1e293b;margin-bottom:6px;">
          {{ profile_user.username }}
        </div>
        <span class="ds-role-badge ds-role-{{ profile_user.user_type }}">
          {% if profile_user.user_type == 'sub_admin' %}次级管理员{% else %}普通用户{% endif %}
        </span>
        {% if profile_user.email %}
        <div style="font-size:12px;color:#94a3b8;margin-top:8px;">{{ profile_user.email }}</div>
        {% endif %}
      </div>

      {# Project permissions card #}
      <div class="ds-form-card" style="margin-bottom:16px;">
        <div class="ds-form-card-title">我的项目权限</div>
        {% if approved_projects %}
          {% for p in approved_projects %}
          <div style="display:flex;align-items:center;gap:8px;padding:6px 10px;
                      background:#f8fafc;border-radius:6px;margin-bottom:4px;">
            <span style="color:#16a34a;font-size:12px;">●</span>
            <span style="font-weight:600;font-size:13px;color:#1e293b;">{{ p }}</span>
          </div>
          {% endfor %}
        {% else %}
          <div style="color:#94a3b8;font-size:13px;text-align:center;padding:12px 0;">
            <i class="bi bi-folder-x" style="font-size:18px;display:block;margin-bottom:4px;"></i>
            暂无已批准项目
          </div>
        {% endif %}
      </div>

      {# Module permissions card #}
      <div class="ds-form-card">
        <div class="ds-form-card-title">我的模块权限</div>
        {% if module_perms %}
          <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:4px;">
            {% if 'delivery' in module_perms %}
            <span style="background:#dcfce7;color:#16a34a;padding:4px 12px;
                         border-radius:12px;font-size:12px;font-weight:600;">Delivery</span>
            {% endif %}
            {% if 'seq' in module_perms %}
            <span style="background:#ede9fe;color:#7c3aed;padding:4px 12px;
                         border-radius:12px;font-size:12px;font-weight:600;">修饰</span>
            {% endif %}
            {% if 'linker' in module_perms %}
            <span style="background:#fff7ed;color:#ea580c;padding:4px 12px;
                         border-radius:12px;font-size:12px;font-weight:600;">Linker</span>
            {% endif %}
          </div>
        {% else %}
          <div style="color:#94a3b8;font-size:13px;text-align:center;padding:12px 0;">
            <i class="bi bi-shield-x" style="font-size:18px;display:block;margin-bottom:4px;"></i>
            暂无模块管理权限
          </div>
        {% endif %}
      </div>

    </div>{# /left column #}

    {# ── RIGHT COLUMN ── #}
    <div>

      {# Change password card #}
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

      {# Request project access card #}
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

      {# Request module access card #}
      <div class="ds-form-card">
        <div class="ds-form-card-title">申请模块权限</div>
        <form method="POST" action="{% url 'request_module_access' %}">
          {% csrf_token %}
          <div class="ds-form-row">
            <label class="ds-form-label">申请模块</label>
            <div style="display:flex;gap:16px;margin-top:6px;flex-wrap:wrap;">
              <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;">
                <input type="checkbox" name="modules_requested" value="delivery"> Delivery 模块
              </label>
              <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;">
                <input type="checkbox" name="modules_requested" value="seq"> 修饰模块
              </label>
              <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;">
                <input type="checkbox" name="modules_requested" value="linker"> Linker 模块
              </label>
            </div>
          </div>
          <div class="ds-form-row">
            <label class="ds-form-label" for="module_note">申请说明</label>
            <input class="ds-form-control" id="module_note" name="note" placeholder="（选填）说明申请原因">
          </div>
          <div style="display:flex;justify-content:flex-end;margin-top:16px;">
            <button type="submit" class="ds-btn ds-btn-primary">提交申请</button>
          </div>
        </form>
      </div>

    </div>{# /right column #}

  </div>{# /two-column grid #}

  {# ── Full-width bottom: combined request history ── #}
  {% if combined_requests %}
  <div class="ds-table-card" style="margin-top:20px;">
    <div style="padding:9px 14px;font-size:12px;font-weight:600;color:#64748b;border-bottom:1.5px solid #e8edf4;">
      申请记录
    </div>
    <div class="ds-table-scroll">
      <table class="ds-table">
        <thead>
          <tr>
            <th>类型</th>
            <th>申请内容</th>
            <th>状态</th>
            <th>审批备注</th>
            <th>时间</th>
          </tr>
        </thead>
        <tbody>
          {% for item in combined_requests %}
          <tr>
            <td>
              {% if item.req_type == '项目' %}
              <span style="background:#dbeafe;color:#1d4ed8;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;">项目</span>
              {% else %}
              <span style="background:#f3e8ff;color:#7c3aed;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;">模块</span>
              {% endif %}
            </td>
            <td><code style="font-size:11px;">{{ item.content }}</code></td>
            <td>
              {% if item.status == 'pending' %}
                <span style="color:#d97706;font-size:12px;font-weight:600;">⏳ 待审批</span>
              {% elif item.status == 'approved' %}
                <span style="color:#16a34a;font-size:12px;font-weight:600;">✅ 已批准</span>
              {% else %}
                <span style="color:#dc2626;font-size:12px;font-weight:600;">❌ 已拒绝</span>
              {% endif %}
            </td>
            <td class="cell-dim">{{ item.review_note|default:'—' }}</td>
            <td class="cell-dim" style="font-size:11.5px;">{{ item.requested_at|date:"Y-m-d H:i" }}</td>
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

- [ ] **Step 4: Run tests — expect pass**

```bash
python manage.py test app01.tests.ProfilePageTests -v 2
```

Expected: `Ran 6 tests in ...s OK`

- [ ] **Step 5: Run full test suite**

```bash
python manage.py test app01 -v 1 2>&1 | tail -5
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add templates/profile.html app01/tests.py
git commit -m "feat: rewrite profile.html as two-column grid layout with combined request history"
```

---

## Self-Review Checklist

### Spec coverage

| Spec section | Covered in |
|---|---|
| Logout view `@require_POST` → `auth_logout` → redirect `login` | Task 2 |
| Logout button in sidebar footer (POST form, icon, hover red) | Task 2 Step 5 |
| `ModulePermissionRequest` model with all fields | Task 1 |
| Migration 0035 `CreateModel` | Task 1 |
| Admin registration | Task 1 |
| `request_module_access` view (block superadmin, block duplicate pending, checkbox validation) | Task 3 |
| `approve_module_request` view (set-union merge, reject path, superadmin gate) | Task 3 |
| Context processor sums both pending counts | Task 3 |
| `user_profile` passes merged combined_requests | Task 3 |
| New URLs `/logout/`, `/request_module/`, `/approve_module_request/<id>/` | Tasks 2+3 |
| `auth_list.html` rename `pending_requests` → `pending_project_requests` | Task 4 |
| `auth_list.html` new module-requests section | Task 4 |
| `author_list` view passes both pending context keys | Task 4 |
| Profile left column: info card (avatar, role badge, email) | Task 5 |
| Profile left column: 我的项目权限 (green dot rows, empty state) | Task 5 |
| Profile left column: 我的模块权限 (colored chips, empty state) | Task 5 |
| Profile right column: change-password card | Task 5 |
| Profile right column: request-project card | Task 5 |
| Profile right column: request-module card (checkboxes) | Task 5 |
| Profile full-width: combined history table with 类型 column | Task 5 |
| Two-column CSS grid (320px + 1fr, 960px max) | Task 5 |

### Placeholder scan

No TBD, TODO, or vague "add validation" items — every step has full code.

### Type consistency

- `ModulePermissionRequest` model name consistent across models.py, admin.py, views.py imports, tests.
- Context key `combined_requests` used in both `user_profile` view (Task 3) and `profile.html` template (Task 5).
- Context key `pending_project_requests` / `pending_module_requests` consistent between `author_list` view (Task 4) and `auth_list.html` template (Task 4).
- URL name `request_module_access` consistent between views.py, urls.py, and profile.html `{% url %}` tag.
- URL name `approve_module_request` consistent between views.py, urls.py, and auth_list.html `{% url %}` tag.
