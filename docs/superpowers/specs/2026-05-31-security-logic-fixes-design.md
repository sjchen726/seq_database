# Security & Logic Fixes — Design Spec

## Goal

Fix five verified security and data-integrity bugs in SeqDB:
XSS in the clone modal, a project-permission bypass in `cor_seq`,
hard-coded `DEBUG`/`ALLOWED_HOSTS` settings, a nullable `created_at`
field on `Sequence`, and unvalidated session data in the preflight
upload flow.

## Architecture

Five independent, sequentially-committed fixes. No shared state or
cross-dependencies. Each fix is a single commit that can be reverted
without affecting the others.

| # | Fix | Type | Files |
|---|-----|------|-------|
| 1 | XSS — clone modal HTML injection | Frontend security | `static/js/clone_delivery.js` |
| 2 | Permission bypass — `cor_seq` no project filter | Backend security | `app01/views.py` |
| 3 | `DEBUG`/`ALLOWED_HOSTS` via environment variables | Config security | `bms/settings.py`, `.env.example` |
| 4 | `Sequence.created_at` → `auto_now_add=True` | Data integrity | `app01/models.py`, new migration |
| 5 | Session data validation in `confirm_upload_preflight` | Backend stability | `app01/views.py` |

---

## Fix 1: XSS in `clone_delivery.js`

### Root Cause

Lines 29–46 build the clone modal's HTML via string concatenation.
Fields like `r.Project`, `r.Target`, `r.Modify_seq` are inserted
verbatim without HTML escaping. An attacker who stores a payload
such as `"><script>alert(1)</script>` in any of those database
fields will have it executed in every user's browser that opens
the clone modal.

### Fix

Replace all string-concatenated HTML with DOM API calls:
`document.createElement` to create elements, and
`element.textContent = value` (or `element.value = value` for
inputs) to assign field values. The browser's DOM parser then
handles escaping automatically — no library needed.

**Pattern to apply for each field:**

```javascript
// BEFORE (unsafe):
html += '<input name="Project" value="' + (r.Project || '') + '" readonly />';

// AFTER (safe):
const input = document.createElement('input');
input.name = 'Project';
input.value = r.Project || '';
input.readOnly = true;
container.appendChild(input);
```

The entire modal body must be rebuilt this way — no `innerHTML`
assignment with user-sourced data.

---

## Fix 2: Permission Bypass in `cor_seq`

### Root Cause

`app01/views.py` around line 3208:

```python
delivery = get_object_or_404(Delivery, Q(id=query_id_tmp) & Q(seq_type=seq_type))
```

This fetches any `Delivery` row by ID regardless of whether the
requesting user has permission to access the associated project.
Any authenticated user who knows a delivery's numeric ID can
correct sequences outside their permitted projects.

### Fix

Filter against the user's permitted queryset before the lookup:

```python
permitted_qs = get_permitted_delivery_qs(request.user)
delivery = get_object_or_404(permitted_qs, Q(id=query_id_tmp) & Q(seq_type=seq_type))
```

`get_object_or_404` accepts a queryset as its first argument and
appends the additional Q filters — the permission scope is enforced
at the DB level.

**Response on unauthorized access:** HTTP 404 (not 403). Returning
404 for a resource the user cannot see prevents leaking whether a
given delivery ID exists — a standard security practice.
`cor_seq` is an AJAX endpoint; the frontend already handles
non-200 responses with an error message display.

---

## Fix 3: Environment Variable–Managed Settings

### Root Cause

`bms/settings.py` has `DEBUG = True` and `ALLOWED_HOSTS = ['*']`
hard-coded. If deployed to a production server as-is, Django exposes
full tracebacks to any visitor and accepts requests from any hostname.

### Fix

Read the three sensitive values from environment variables with
safe fallbacks:

```python
import os

DEBUG = os.environ.get('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '127.0.0.1').split(',')
SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    '<existing hardcoded value as dev fallback>'
)
```

A local `.env` file (git-ignored) provides development values:

```dotenv
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost
SECRET_KEY=<dev-secret-key>
```

`.env.example` (committed) is updated to document all three variables
with placeholder values and comments.

**Note:** The project already has `.env.example` in the repo.
No new dependency (python-dotenv) is needed — `os.environ.get` is
sufficient since the dev server is typically started after
`source .env` or via a shell that exports these vars. If the team
prefers auto-loading, adding `python-dotenv` and a
`load_dotenv()` call at the top of `settings.py` is a one-line
change.

---

## Fix 4: `Sequence.created_at` → `auto_now_add`

### Root Cause

```python
created_at = models.DateTimeField('创建时间', blank=True, null=True)
```

No `auto_now_add=True` means new `Sequence` records are created
with `created_at = NULL` unless the caller explicitly sets it.
This breaks chronological sorting and any "recently added" queries.

### Fix

```python
created_at = models.DateTimeField('创建时间', auto_now_add=True, null=True)
```

`null=True` is retained for backward compatibility — existing rows
with `NULL` values remain untouched and won't cause errors. All
newly created sequences automatically receive the current timestamp.

A migration (`0036_sequence_created_at_auto_now_add.py`) is
generated via `makemigrations` and applied. No data backfill is
needed; historical NULLs are acceptable.

---

## Fix 5: Session Data Validation in `confirm_upload_preflight`

### Root Cause

The view reads session keys with direct dictionary access:

```python
pairs = request.session['upload_pairs']
row_ids = request.session['upload_row_ids']
```

If the session expires between the preflight check and the confirm
step, or if a user navigates to the confirm URL directly, a
`KeyError` raises an unhandled 500 error.

### Fix

Use `.get()` with explicit validation, redirect to the upload page
on failure:

```python
pairs = request.session.get('upload_pairs')
row_ids = request.session.get('upload_row_ids')

if not pairs or not isinstance(pairs, list):
    messages.error(request, '会话已过期，请重新上传文件。')
    return redirect('seq_delivery')

if not row_ids or not isinstance(row_ids, list):
    messages.error(request, '会话数据不完整，请重新上传文件。')
    return redirect('seq_delivery')
```

Apply the same guard pattern to any other session keys read by
this view. The user sees a clear Chinese-language error message
and is returned to the upload form rather than a crash page.

---

## Files Changed

| File | Change |
|------|--------|
| `static/js/clone_delivery.js` | Rewrite modal HTML builder with DOM API |
| `app01/views.py` | `cor_seq`: add `get_permitted_delivery_qs` filter; `confirm_upload_preflight`: add session key guards |
| `bms/settings.py` | Read `DEBUG`, `ALLOWED_HOSTS`, `SECRET_KEY` from `os.environ` |
| `.env.example` | Add `DEBUG`, `ALLOWED_HOSTS`, `SECRET_KEY` entries with comments |
| `app01/models.py` | `Sequence.created_at`: add `auto_now_add=True` |
| `app01/migrations/0036_sequence_created_at_auto_now_add.py` | Generated migration |

---

## Out of Scope

- Email or in-app notifications for security events
- Rate limiting / brute-force protection
- Full audit log for `cor_seq` corrections
- UX improvements (clone modal field layout, upload success feedback)
- Backfilling historical `NULL` values in `Sequence.created_at`
