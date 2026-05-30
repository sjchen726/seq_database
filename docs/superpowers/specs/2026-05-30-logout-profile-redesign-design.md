# Logout + Profile Page Redesign — Design Spec

## Goal

Add a logout button to the sidebar user card; redesign the profile page with a professional
two-column layout; add a module-permission request workflow parallel to the existing
project-permission request workflow.

## Architecture

Three independent but related changes shipped together:

1. **Logout** — a POST form on the sidebar footer → Django `auth_logout()` → redirect to login
2. **ModulePermissionRequest model** — mirrors `ProjectAccessRequest`; superadmin approves
   in the same `auth_list.html` yellow bar (new section)
3. **Profile page** — two-column layout (960 px max), left = status info, right = forms;
   combined request-history table at the bottom

---

## 1. Logout Button

### Implementation

- New view `logout_view` in `app01/views.py`:
  ```python
  @require_POST
  def logout_view(request):
      from django.contrib.auth import logout as auth_logout
      auth_logout(request)
      return redirect('login')
  ```
- New URL: `path('logout/', views.logout_view, name='logout')`

### UI placement — sidebar footer

The existing `.ds-user-card` becomes a flex row with `justify-content: space-between`.
A small logout icon button sits on the far right:

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

---

## 2. ModulePermissionRequest Model

### Model definition (`app01/models.py`)

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

### Migration

`app01/migrations/0035_module_permission_request.py` — `CreateModel` only, noop reverse.

### Admin registration

```python
@admin.register(ModulePermissionRequest)
class ModulePermissionRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'modules_requested', 'status', 'requested_at', 'reviewed_by')
    list_filter = ('status',)
    search_fields = ('user__username', 'modules_requested')
```

---

## 3. New Views

### `request_module_access(request)`

```
POST /request_module/
@login_required, @require_POST
- Reject superadmin (redirect author_list)
- Validate at least one checkbox selected
- Block if existing pending ModulePermissionRequest exists for user
- Create ModulePermissionRequest(user, modules_requested, note)
- Redirect user_profile with success message
```

### `approve_module_request(request, req_id)`

```
POST /approve_module_request/<int:req_id>/
@login_required, @require_POST, _is_superadmin required
- On action='approve':
    existing = set of current module_permissions split by ','
    new_mods  = set of modules_requested split by ','
    merged    = sorted(existing | new_mods)
    user.module_permissions = ','.join(merged)
    user.save(update_fields=['module_permissions'])
    req.status = 'approved'
- On action='reject': req.status = 'rejected', req.review_note = review_note
- Set reviewed_by, reviewed_at on both paths
- Redirect author_list
```

### `user_profile` view update

Add to context:
```python
'module_requests': ModulePermissionRequest.objects.filter(user=user).order_by('-requested_at'),
```

### URLs

```python
path('request_module/', views.request_module_access, name='request_module_access'),
path('approve_module_request/<int:req_id>/', views.approve_module_request, name='approve_module_request'),
```

---

## 4. Context Processor Update

`app01/context_processors.py` — `pending_approval_count` sums both request types:

```python
from app01.models import ProjectAccessRequest, ModulePermissionRequest

def pending_approval_count(request):
    count = 0
    if (request.user.is_authenticated and
            (request.user.is_superuser or
             getattr(request.user, 'user_type', '') == 'superadmin')):
        count = (ProjectAccessRequest.objects.filter(status='pending').count()
               + ModulePermissionRequest.objects.filter(status='pending').count())
    return {'pending_approval_count': count}
```

---

## 5. Profile Page Redesign (`templates/profile.html`)

### Layout

```
max-width: 960px; margin: 0 auto;
display: grid; grid-template-columns: 320px 1fr; gap: 20px;

Left column  (320px): info-card + project-status-card + module-status-card
Right column (1fr):   change-password-card + request-project-card + request-module-card
Full-width bottom:    combined request history table
```

### Left column — info card

- Large avatar circle (48px, gradient, first letter)
- Username bold (16px)
- Role badge (`ds-role-badge`) beneath
- Email if available (gray, small)

### Left column — 我的项目权限 card

Each approved project on its own row:
```
● BPR-350
● BPR-3T03
```
Green dot `●`, project code in `font-weight:600`, gray background row with `border-radius:6px`.
Empty state: "暂无已批准项目" with a subtle icon.

### Left column — 我的模块权限 card

Colored badge chips per module:
- `delivery` → green (`#dcfce7` bg, `#16a34a` text)
- `seq`      → purple (`#ede9fe` bg, `#7c3aed` text)
- `linker`   → orange (`#fff7ed` bg, `#ea580c` text)

Empty state: "暂无模块管理权限"

### Right column — 修改密码 card

Unchanged fields; card layout same as now.

### Right column — 申请项目权限 card

Unchanged form fields; card layout same as now.

### Right column — 申请模块权限 card (NEW)

```html
<div class="ds-form-card">
  <div class="ds-form-card-title">申请模块权限</div>
  <form method="POST" action="{% url 'request_module_access' %}">
    {% csrf_token %}
    <div class="ds-form-row">
      <label class="ds-form-label">申请模块</label>
      <div style="display:flex;gap:16px;margin-top:6px;">
        <label>
          <input type="checkbox" name="modules_requested" value="delivery"> Delivery 模块
        </label>
        <label>
          <input type="checkbox" name="modules_requested" value="seq"> 修饰模块
        </label>
        <label>
          <input type="checkbox" name="modules_requested" value="linker"> Linker 模块
        </label>
      </div>
    </div>
    <div class="ds-form-row">
      <label class="ds-form-label" for="module_note">申请说明</label>
      <input class="ds-form-control" id="module_note" name="note" placeholder="（选填）">
    </div>
    <div style="display:flex;justify-content:flex-end;margin-top:16px;">
      <button type="submit" class="ds-btn ds-btn-primary">提交申请</button>
    </div>
  </form>
</div>
```

### Full-width bottom — 申请记录 table

Combined table with a **「类型」column** (项目 / 模块) so user sees all their requests in
one place, sorted by `requested_at` descending.

| 类型 | 申请内容 | 状态 | 审批备注 | 时间 |
|------|---------|------|---------|------|
| 项目 | BPR-350 | ✅ 已批准 | — | 2026-05-29 |
| 模块 | delivery,seq | ⏳ 待审批 | — | 2026-05-30 |

`user_profile` view must merge and sort both querysets before passing to template.

---

## 6. `auth_list.html` Admin Changes

The yellow pending-request section splits into **two sub-sections**:

```html
{% if pending_project_requests %}
<!-- 项目权限申请 section (existing) -->
{% endif %}

{% if pending_module_requests %}
<!-- 模块权限申请 section (new, same visual pattern) -->
<!-- approve/reject posts to approve_module_request -->
{% endif %}
```

`author_list` view must pass both `pending_project_requests` and `pending_module_requests`
(currently only `pending_requests`). Rename existing `pending_requests` →
`pending_project_requests` throughout.

---

## 7. Files Changed / Created

| File | Change |
|------|--------|
| `app01/models.py` | Add `ModulePermissionRequest` |
| `app01/migrations/0035_module_permission_request.py` | Create table |
| `app01/admin.py` | Register `ModulePermissionRequestAdmin` |
| `app01/context_processors.py` | Sum both pending counts |
| `app01/views.py` | `logout_view`, `request_module_access`, `approve_module_request`; update `author_list`, `user_profile` |
| `bms/urls.py` | Add `/logout/`, `/request_module/`, `/approve_module_request/<id>/` |
| `templates/base.html` | Logout button in sidebar footer |
| `templates/profile.html` | Full rewrite: two-column grid layout |
| `templates/auth_list.html` | Split pending section into project + module sub-sections |

---

## 8. Out of Scope

- Email notifications for approval results
- Superadmin self-service profile page (they use auth_list)
- Revoking permissions from the profile page (superadmin edits user directly)
- Bulk module permission requests
