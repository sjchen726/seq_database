# Permission System Redesign — Design Spec

**Date:** 2026-06-25
**Scope:** Replace the 7-tier role system with a 3-tier + module-permission system aligned with seq_database_v2. Add self-registration with auto-grant, project access request workflow, user management page (superadmin only), and audit logging.

---

## Goal

1. Simplify roles to `user / sub_admin / superadmin`.
2. Let new users self-register and immediately get full permissions on their declared project (no approval needed).
3. Add a formal `ProjectAccessRequest` flow for requesting additional projects after registration.
4. Restrict the user management page (`/users/`) to superadmin only.
5. Log all permission-related events to an `AuditLog` model.
6. Migrate: keep only the superadmin account (password reset to `123456`), delete all other users.

---

## Section 1: Data Model

### 1a. `LmsUser` changes

| Field | Change |
|-------|--------|
| `user_type` | Replace 7-choice field with 3 choices: `user`, `sub_admin`, `superadmin` |
| `module_permissions` | **New field** — `CharField(max_length=64, blank=True, default='')`. Comma-separated subset of: `upload`, `data`, `compound`, `batch`. Meaningful only when `user_type='sub_admin'`; superadmin implicitly has all. |
| `permissions_project` | Unchanged — comma-separated project codes. |

Fields removed from choices (not from DB column yet — Django migration just changes `choices`): `guest`, `delivery`, `modify`, `project`, `data_admin`, `admin`.

### 1b. New model: `ProjectAccessRequest`

```python
class ProjectAccessRequest(models.Model):
    STATUS_CHOICES = [
        ('pending',  '待审批'),
        ('approved', '已批准'),
        ('rejected', '已拒绝'),
    ]
    user         = models.ForeignKey(LmsUser, on_delete=models.CASCADE, related_name='project_requests')
    project_code = models.CharField(max_length=64)
    status       = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    note         = models.TextField(blank=True, default='')  # rejection reason
    created_at   = models.DateTimeField(auto_now_add=True)
    reviewed_at  = models.DateTimeField(null=True, blank=True)
    reviewed_by  = models.ForeignKey(LmsUser, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='reviewed_requests')
    class Meta:
        ordering = ['-created_at']
```

### 1c. New model: `AuditLog`

```python
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
                                    null=True, blank=True, related_name='audit_events')
    detail      = models.TextField(default='')  # JSON string with before/after values
    created_at  = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at']
```

### 1d. Permission helpers (new, in `app01/views.py`)

```python
def _has_module(user, module: str) -> bool:
    """True if user may perform operations in the given module."""
    if user.is_superuser or user.user_type == 'superadmin':
        return True
    if user.user_type == 'sub_admin':
        return module in (user.module_permissions or '').split(',')
    return False

def _get_permitted_projects(user):
    """Return None (= all projects) for superadmin, else list of permitted project codes."""
    if user.is_superuser or user.user_type == 'superadmin':
        return None
    return [p.strip() for p in (user.permissions_project or '').split(',') if p.strip()]
```

---

## Section 2: Self-Registration

**URL:** `/register/` (existing view `register_view`)

**Form fields:** username, password, project_code (optional).

**On success:**
1. Create user with:
   - `user_type = 'sub_admin'`
   - `module_permissions = 'upload,data,compound,batch'`
   - `permissions_project = project_code.strip()` (empty string if not provided)
2. Write `AuditLog(actor=new_user, action='register', detail=json.dumps({'project': project_code}))`.
3. Redirect to login with success message.

**Note:** No admin approval required for the initial registration project. This is by design — the system trusts self-declared project membership at registration time. Subsequent project requests require approval.

---

## Section 3: User Management Page

**URL:** `/users/` (new view `user_management_view`)

**Access:** superadmin only. Any non-superadmin user hitting this URL gets a 403.

**Page layout (three sections):**

### 3a. Pending project requests

Table showing all `ProjectAccessRequest` objects with `status='pending'`:
- Columns: username, project_code, created_at, approve/reject buttons
- **Approve action:** sets `status='approved'`, appends project to `user.permissions_project`, writes `AuditLog(action='project_approved')`.
- **Reject action:** sets `status='rejected'`, writes `AuditLog(action='project_rejected')`.
- Both actions set `reviewed_at=now()`, `reviewed_by=request.user`.

### 3b. User list

Table of all `LmsUser` objects:
- Columns: username, user_type badge, module_permissions tags, permissions_project badges, edit/delete buttons
- superadmin row: delete button disabled.
- **Edit:** modal dialog to change `user_type` (dropdown), `module_permissions` (checkboxes for upload/data/compound/batch), `permissions_project` (text input, comma-separated). On save writes `AuditLog(action='user_role_changed', detail=JSON with before/after values)`.
- **Delete:** confirmation dialog → delete user → `AuditLog(action='user_deleted')`.

### 3c. Audit log

Last 30 `AuditLog` entries: timestamp, action badge, description text.

---

## Section 4: Profile Page — Request Additional Projects

**URL:** `/profile/` (existing view, extended)

**New section added:** "申请访问新项目"
- Input: project_code text field + submit button.
- On submit: create `ProjectAccessRequest(user=request.user, project_code=...)` with `status='pending'`. Write `AuditLog(action='project_request')`.
- Validation: reject if user already has this project in `permissions_project`, or if a pending request for the same project already exists.

**Existing section enhanced:** show current `user_type`, `module_permissions`, `permissions_project`.

**New section:** "申请记录" — list user's `ProjectAccessRequest` history with status badges.

---

## Section 5: views.py Permission Updates

### 5a. Three direct replacements

| View | Line (approx.) | Old check | New check |
|------|----------------|-----------|-----------|
| `register_view` | 57 | `user_type='guest'` | `user_type='sub_admin'`, `module_permissions='upload,data,compound,batch'` |
| `experiments_bulk_delete` | 1465 | `user_type in ('data_admin','admin','superadmin')` | `_has_module(request.user, 'data')` |
| `experiments_export_csv` | 1484 | `user_type in ('data_admin','admin','superadmin')` | `_has_module(request.user, 'data')` |

### 5b. Project-level filtering in `compound_list`

After building `exp_qs`, add:

```python
permitted = _get_permitted_projects(request.user)
if permitted is not None:
    exp_qs = exp_qs.filter(compound__project__in=permitted)
    all_projects = [p for p in all_projects if p in permitted]
```

### 5c. Upload protection in `smart_upload_view`

At the top of the view (after `@login_required`):

```python
if not _has_module(request.user, 'upload'):
    messages.error(request, '权限不足，无法访问上传页面')
    return redirect('compound_list')
```

Apply the same guard to `smart_upload_confirm_view`.

### 5d. Per-row delete button visibility in `compound_list.html`

The delete button (each compound row) renders only when the user has the `data` module:

```html
{% if request.user.user_type == 'superadmin' or 'data' in request.user.module_permissions %}
  <button ... onclick="clDeleteRow({{ vc.exp_ids|join:',' }})">删除</button>
{% endif %}
```

`clDeleteRow(...expIds)` is a new JS function that calls `/api/experiments/bulk-delete/` with `{exp_ids: [...expIds]}` and reloads the page on success. It shows a confirmation dialog first: `确认删除该化合物的 N 条实验记录？`

---

## Section 6: Data Migration

### 6a. Management command: `reset_users`

New file: `app01/management/commands/reset_users.py`

Logic:
1. Find the superadmin user (the one with `is_superuser=True` or `user_type='superadmin'`). If multiple, keep the first by `pk`.
2. Set that user's password to `123456`, `user_type='superadmin'`, `module_permissions=''`, `is_active=True`.
3. Delete all other `LmsUser` records.
4. Print summary: `Kept: <username>. Deleted: N users.`

Run once after migration:
```bash
python manage.py reset_users
```

### 6b. Django migration

One new migration (`0025_permission_redesign.py`):
- Alter `LmsUser.user_type` choices
- Add `LmsUser.module_permissions` field
- Create `ProjectAccessRequest` table
- Create `AuditLog` table

---

## Section 7: URL additions

```python
path('users/', views.user_management_view, name='user_management'),
path('users/<int:user_id>/edit/', views.user_edit_view, name='user_edit'),
path('users/<int:user_id>/delete/', views.user_delete_view, name='user_delete'),
path('users/requests/<int:req_id>/approve/', views.project_request_approve, name='project_request_approve'),
path('users/requests/<int:req_id>/reject/', views.project_request_reject, name='project_request_reject'),
path('profile/request-project/', views.profile_request_project, name='profile_request_project'),
```

---

## Out of Scope

- Module access requests (users cannot self-request module permission changes — only superadmin assigns modules).
- Email notifications for approval/rejection.
- Pagination on the user list or audit log (first version shows all, capped at 30 for the log).
