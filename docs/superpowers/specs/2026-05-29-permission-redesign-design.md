# Permission System Redesign — Design Spec

## Goal

Replace the existing 7-level `user_type` hierarchy with a clean 3-role model
(superadmin / sub_admin / user), add a project-permission approval workflow,
introduce per-module management rights, and restrict user management to
superadmins only (everyone else sees only their own profile page).

## Architecture

Three orthogonal permission dimensions are combined at runtime:

| Dimension | Field | Controls |
|-----------|-------|---------|
| Role | `user_type` | Edit/delete sequences; user management |
| Project access | `permissions_project` | Which project's Delivery data is visible |
| Module management | `module_permissions` | Which module tables (Delivery/Seq/Linker) a user can edit |

---

## 1. Role Model

### New `user_type` choices

| Value | Display | Who |
|-------|---------|-----|
| `superadmin` | 超级管理员 | Global admin; manages users, approves requests |
| `sub_admin` | 次级管理员 | Project PI / group lead; can edit & delete in permitted projects |
| `user` | 普通用户 | Default role after registration |

All three roles require project permissions to access project-specific data.
Role alone does not grant data visibility — project access is always explicit.

### Migration mapping from old roles

| Old `user_type` | New `user_type` |
|-----------------|-----------------|
| `superadmin` | `superadmin` |
| `admin` | `superadmin` |
| `data_admin` | `sub_admin` |
| `project` | `user` |
| `modify` | `user` |
| `delivery` | `user` |
| `guest` | `user` |

Old `data_admin` users are also auto-granted all three module permissions
(`delivery,seq,linker`) during migration, preserving their previous access.

---

## 2. New & Modified Model Fields

### `LmsUser` changes

```python
# Replace existing 7-value choices with:
USER_TYPE_CHOICES = [
    ('superadmin', '超级管理员'),
    ('sub_admin',  '次级管理员'),
    ('user',       '普通用户'),
]

# New field — comma-separated, values: 'delivery', 'seq', 'linker'
module_permissions = models.CharField(
    '模块管理权限',
    max_length=64,
    blank=True,
    default='',
)

# Existing field — retained unchanged
permissions_project = models.CharField(
    '可查看的项目号',
    max_length=256,
    null=True,
    blank=True,
)

# is_admin — deprecated; no longer written or read.
# Replaced by: user_type == 'superadmin' checks everywhere.
# Column kept in DB for now; removed in a follow-up migration.
```

### New helper methods on `LmsUser`

```python
def can_manage_module(self, module: str) -> bool:
    """module: 'delivery' | 'seq' | 'linker'"""
    if self.is_superuser or self.user_type == 'superadmin':
        return True
    return module in (self.module_permissions or '').split(',')

def is_superadmin(self) -> bool:
    return self.is_superuser or self.user_type == 'superadmin'

def is_sub_admin(self) -> bool:
    return self.user_type == 'sub_admin'
```

### New model: `ProjectAccessRequest`

```python
class ProjectAccessRequest(models.Model):
    STATUS_CHOICES = [
        ('pending',  '待审批'),
        ('approved', '已批准'),
        ('rejected', '已拒绝'),
    ]

    user          = models.ForeignKey(LmsUser, on_delete=models.CASCADE,
                                      related_name='access_requests')
    project_codes = models.CharField('申请项目号', max_length=512)
    # Comma-separated, e.g. "BPR-350,BPR-3T03"
    note          = models.CharField('申请说明', max_length=256, blank=True)
    requested_at  = models.DateTimeField(auto_now_add=True)
    status        = models.CharField(max_length=16, choices=STATUS_CHOICES,
                                     default='pending')
    reviewed_by   = models.ForeignKey(LmsUser, null=True, blank=True,
                                      on_delete=models.SET_NULL,
                                      related_name='reviewed_requests')
    reviewed_at   = models.DateTimeField(null=True, blank=True)
    review_note   = models.CharField('审批备注', max_length=256, blank=True)

    class Meta:
        ordering = ['-requested_at']
```

---

## 3. Permission Matrix

### Role × Feature

| Feature | user | sub_admin | superadmin |
|---------|:----:|:---------:|:----------:|
| View sequence list (project-filtered) | ✅ approved projects | ✅ approved projects | ✅ all |
| View bare sequence list | ✅ | ✅ | ✅ |
| Upload delivery CSV | ✅ | ✅ | ✅ |
| Register bare sequence | ✅ | ✅ | ✅ |
| **Edit** Delivery record | ❌ | ✅ approved projects | ✅ all |
| **Delete** Delivery record | ❌ | ✅ approved projects | ✅ all |
| Clone Delivery record | ❌ | ✅ approved projects | ✅ all |
| Cross-project share (`confirm_share`) | ❌ | ✅ approved projects | ✅ all |
| Verify sequence (`cor_seq`) | ✅ | ✅ | ✅ |
| Add experiment data | ✅ approved projects | ✅ approved projects | ✅ all |
| Delete experiment data | ❌ | ✅ approved projects | ✅ all |
| BLAST / multi-sequence align | ✅ | ✅ | ✅ |
| Download CSV | ✅ approved projects | ✅ approved projects | ✅ all |
| **Delivery module** management (CRUD entries) | `module_permissions` | `module_permissions` | ✅ always |
| **SeqModule** management (CRUD entries) | `module_permissions` | `module_permissions` | ✅ always |
| **Linker module** management (CRUD entries) | `module_permissions` | `module_permissions` | ✅ always |
| Module CSV bulk upload | same as above | same as above | ✅ always |
| **User management page** (list, add, edit, delete users) | ❌ | ❌ | ✅ |
| Grant / revoke module permissions | ❌ | ❌ | ✅ |
| Approve / reject project access requests | ❌ | ❌ | ✅ |
| Submit project access request | ✅ | ✅ | — |
| View own profile page | ✅ | ✅ | — |
| Change own password | ✅ | ✅ | ✅ |

### Notes

- "approved projects" = project codes in `permissions_project`.
- `sub_admin` edit/delete rights are project-scoped: the user must hold all
  projects a Delivery belongs to (existing `user_can_edit_delivery` logic).
- `sub_admin` does **not** automatically receive module management rights;
  superadmin must explicitly grant them via `module_permissions`.
- Superadmin has no "my profile" nav entry — user management covers their
  own account editing.

---

## 4. Approval Workflow

### Project permission request lifecycle

```
Registration
  → user_type = 'user', permissions_project = '', can log in immediately

User submits request
  → ProjectAccessRequest created (status=pending)
  → Sidebar badge on "用户管理" increments for superadmin

Superadmin reviews (in user management page, approval tab)
  → Approve: append project_codes to user.permissions_project,
             set status=approved, reviewed_by, reviewed_at
  → Reject:  set status=rejected + review_note

User sees result on profile page
  → Approved: green badge, project now visible in sequence list
  → Rejected: red badge + review_note
  → User may submit a new request after rejection (old record kept)
```

### Superadmin notification

- Sidebar "用户管理" nav item shows a red badge with the count of
  `pending` requests whenever count > 0.
- No email notifications (out of scope).

---

## 5. Profile Page (`/profile/`)

Accessible to all authenticated non-superadmin users. Superadmin manages
their account via the user management page.

| Section | Content |
|---------|---------|
| 基本信息 | Username, role display name (read-only) |
| 修改密码 | Current password + new password form |
| 我的项目权限 | Comma-separated list of approved project codes (read-only) |
| 申请记录 | Table of all requests: project codes / status / review note / date |
| 提交新申请 | Project codes input + note textarea + submit button |
| 我的模块权限 | Which modules have been granted (read-only chips) |

---

## 6. Sidebar Visibility Rules

| Nav item | superadmin | sub_admin | user |
|----------|:----------:|:---------:|:----:|
| 序列数据 (seq_list, reg_seq_list) | ✅ | ✅ | ✅ |
| 功能模块 (register_seq, seq_delivery) | ✅ | ✅ | ✅ |
| BLAST | ✅ | ✅ | ✅ |
| 模块管理 — Delivery 模块 | ✅ | `can_manage_module('delivery')` | `can_manage_module('delivery')` |
| 模块管理 — 修饰模块 | ✅ | `can_manage_module('seq')` | `can_manage_module('seq')` |
| 模块管理 — Linker 模块 | ✅ | `can_manage_module('linker')` | `can_manage_module('linker')` |
| 系统 — 用户管理 | ✅ + badge | ❌ | ❌ |
| 我的资料 | ❌ | ✅ | ✅ |

---

## 7. New Views & URLs

| URL | View | Access |
|-----|------|--------|
| `/profile/` | `user_profile` GET+POST | Authenticated, non-superadmin |
| `/request_project/` | `request_project_access` POST | Authenticated, non-superadmin |
| `/approve_request/<int:req_id>/` | `approve_project_request` POST | Superadmin only |

Existing user management views (`author_list`, `add_author`, `edit_author`,
`drop_author`) are restricted to `superadmin` only (replacing the current
`is_superuser or is_admin` check).

---

## 8. Migration Plan

Single migration file (`0034_permission_redesign`):

1. Add `module_permissions` CharField to `LmsUser`
2. Add `ProjectAccessRequest` model
3. RunPython: remap `user_type` values (old → new per table above)
4. RunPython: set `module_permissions = 'delivery,seq,linker'` for all users
   whose old `user_type` was `data_admin`
5. `is_admin` field: leave column in DB, stop reading/writing it in code
   (removed in a later cleanup migration)

Key view changes:

- All `user_type in ('admin', 'data_admin', 'superadmin')` → `user_type in ('superadmin', 'sub_admin')` or role-specific checks
- All `is_superuser or is_admin` guards → `user.is_superadmin()`
- `can_manage_modules()` → `can_manage_module(module_name)`
- `user_can_edit_delivery` → check `user_type in ('superadmin', 'sub_admin')`
  OR (is `user` with full project coverage)
- `delete_experiment` guard → same as edit/delete delivery
- `clone_delivery` guard → same as edit/delete delivery (`sub_admin`+ for permitted projects)
- `confirm_share_deliveries` guard → same as edit/delete delivery
- Module management views: replace `can_manage_modules()` with
  `can_manage_module('delivery' | 'seq' | 'linker')` per view

---

## 9. Out of Scope

- Email notifications for approval results
- Sub-admin delegating module permissions to others
- Project model (Project as a first-class DB entity, not just a string code)
- Two-factor authentication
