# edit_seq Permission Fix + HTTP Security Headers — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix a project-permission bypass in `edit_seq`'s GET path, and add three HTTP security headers to the Django settings.

**Architecture:** Two independent one-commit fixes. Fix 1 scopes the `edit_seq` GET lookup to `get_permitted_delivery_qs(request.user)` — identical pattern to the `cor_seq` fix already shipped. Fix 2 appends three header constants to `bms/settings.py`; `SecurityMiddleware` (already in `MIDDLEWARE`) picks them up automatically.

**Tech Stack:** Django 5.1, Python 3.10, Django `unittest.TestCase`

---

## Context

**Test baseline (before this plan):** 129 tests, 5 pre-existing failures:
- 4 `CheckDuplicatesTests` errors (DB fixture issue, unrelated)
- 1 `DropAuthorSecurityTests` failure (unrelated)

New tests added by this plan must pass; the pre-existing 5 failures are expected and acceptable.

**Key helper already in `app01/views.py`:**

```python
def get_permitted_delivery_qs(user):
    """Return a Delivery queryset scoped to the user's permitted projects."""
    if user.is_superuser or getattr(user, 'user_type', None) == 'superadmin':
        return Delivery.objects.all()
    allowed = user.get_allowed_projects()
    if not allowed:
        return Delivery.objects.none()
    return Delivery.objects.filter(deliveryproject__project_code__in=allowed)
```

**Buggy line** (`app01/views.py:719`):

```python
delivery = get_object_or_404(Delivery, Q(id=seq_id) & Q(Strand_MWs=seq_Strand_MWs))
```

**Fixed line:**

```python
delivery = get_object_or_404(get_permitted_delivery_qs(request.user), Q(id=seq_id) & Q(Strand_MWs=seq_Strand_MWs))
```

**Settings insertion point** — end of `bms/settings.py` (currently last line):

```python
SW_SCORE_THRESHOLD = 15              # Smith-Waterman 最低得分阈值
```

---

## Files Changed

| File | Change |
|------|--------|
| `app01/views.py` | `edit_seq` line 719: scope lookup to permitted queryset |
| `app01/tests.py` | Append `EditSeqPermissionTests` + `SecurityHeaderTests` |
| `bms/settings.py` | Append 3 security header constants |

---

## Task 1: edit_seq Permission Fix

**Files:**
- Modify: `app01/views.py:719`
- Test: `app01/tests.py` (append `EditSeqPermissionTests`)

- [ ] **Step 1: Write the failing tests**

Open `app01/tests.py` and append the following class at the very end of the file. Place it after the last test class already in the file.

```python
class EditSeqPermissionTests(TestCase):
    """edit_seq must not expose deliveries outside the user's permitted projects."""

    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='editseq_noperm',
            password='p',
            user_type='sub_admin',
            permissions_project='',
        )
        self.client.force_login(self.user)

        self.seq = Sequence.objects.create(seq='GCGCGCGC', seq_type='AS')
        self.delivery = Delivery.objects.create(
            sequence=self.seq,
            seq_type='AS',
            duplex_id='BP_EDITSEQ_TEST',
            project='PRJ-HIDDEN',
            Strand_MWs='1234.5',
        )
        DeliveryProject.objects.create(
            delivery=self.delivery,
            project_code='PRJ-HIDDEN',
        )

    def test_unpermitted_user_gets_404(self):
        """User with no permitted projects must get 404, not 200."""
        url = f'/edit_seq/?id={self.delivery.id}&strand_MWs=1234.5'
        r = self.client.get(url)
        self.assertEqual(r.status_code, 404)

    def test_permitted_user_gets_200(self):
        """User with matching project permission must reach the edit page."""
        self.user.permissions_project = 'PRJ-HIDDEN'
        self.user.save()
        url = f'/edit_seq/?id={self.delivery.id}&strand_MWs=1234.5'
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
```

Verify the imports at the top of `app01/tests.py` include `DeliveryProject`. If not, add it to the existing import line that imports from `app01.models`.

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2
source venv/bin/activate
python manage.py test app01.tests.EditSeqPermissionTests -v 2
```

Expected: `test_unpermitted_user_gets_404` **FAIL** (gets 200 instead of 404), `test_permitted_user_gets_200` **PASS** or **FAIL** depending on whether delivery setup works. The key signal is that the unpermitted test does NOT return 404 yet.

- [ ] **Step 3: Apply the one-line fix in `app01/views.py`**

Find line 719 in `app01/views.py`. It reads:

```python
    delivery = get_object_or_404(Delivery, Q(id=seq_id) & Q(Strand_MWs=seq_Strand_MWs))
```

Replace it with:

```python
    delivery = get_object_or_404(get_permitted_delivery_qs(request.user), Q(id=seq_id) & Q(Strand_MWs=seq_Strand_MWs))
```

No other changes needed. `get_permitted_delivery_qs` is already defined earlier in `views.py` and imported into scope.

- [ ] **Step 4: Run the new tests again — both must pass**

```bash
python manage.py test app01.tests.EditSeqPermissionTests -v 2
```

Expected output:

```
test_permitted_user_gets_200 (app01.tests.EditSeqPermissionTests) ... ok
test_unpermitted_user_gets_404 (app01.tests.EditSeqPermissionTests) ... ok

Ran 2 tests in X.XXXs

OK
```

- [ ] **Step 5: Run the full test suite — verify no regressions**

```bash
python manage.py test app01 -v 1 2>&1 | tail -20
```

Expected: 131 tests total (129 baseline + 2 new). Failures should remain at 5 (the same pre-existing failures). No new failures.

- [ ] **Step 6: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "fix: scope edit_seq GET lookup to permitted delivery queryset

Any authenticated user could open /edit_seq/?id=X and read delivery
data for a project they have no permission to access. The POST path
was protected by user_can_edit_delivery(), but the GET path exposed
all form field values.

Apply the same get_permitted_delivery_qs() pattern used in cor_seq:
get_object_or_404 now receives the user-scoped queryset, returning
HTTP 404 for unauthorized IDs without leaking resource existence.

Adds EditSeqPermissionTests (2 tests) to verify the fix.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: HTTP Security Headers

**Files:**
- Modify: `bms/settings.py` (append at end)
- Test: `app01/tests.py` (append `SecurityHeaderTests`)

- [ ] **Step 1: Append the three header constants to `bms/settings.py`**

Open `bms/settings.py`. The current last line is:

```python
SW_SCORE_THRESHOLD = 15              # Smith-Waterman 最低得分阈值
```

Append the following block immediately after it (leave one blank line between):

```python

# ── Security headers (injected by SecurityMiddleware) ──────────────────────
# HTTPS-specific settings (SECURE_SSL_REDIRECT, SESSION_COOKIE_SECURE,
# CSRF_COOKIE_SECURE, SECURE_HSTS_SECONDS) are intentionally omitted:
# this application runs on an internal HTTP network only.
X_FRAME_OPTIONS = 'DENY'            # Prevent clickjacking via iframe embedding
SECURE_CONTENT_TYPE_NOSNIFF = True  # Prevent MIME-type sniffing (nosniff header)
REFERRER_POLICY = 'same-origin'     # Do not send Referer on cross-origin requests
```

- [ ] **Step 2: Verify Django's system check passes**

```bash
python manage.py check
```

Expected:

```
System check identified no issues (0 silenced).
```

If any issues are reported, they must be fixed before proceeding.

- [ ] **Step 3: Write the SecurityHeaderTests and append to `app01/tests.py`**

Append this class at the very end of `app01/tests.py` (after `EditSeqPermissionTests` added in Task 1):

```python
class SecurityHeaderTests(TestCase):
    """SecurityMiddleware must inject the configured headers on every response."""

    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='sec_header_user',
            password='p',
            user_type='sub_admin',
            permissions_project='',
        )
        self.client.force_login(self.user)

    def test_x_frame_options_deny(self):
        """X-Frame-Options: DENY must be present on all responses."""
        r = self.client.get('/seq_list/')
        self.assertEqual(r.get('X-Frame-Options'), 'DENY')

    def test_content_type_nosniff(self):
        """X-Content-Type-Options: nosniff must be present on all responses."""
        r = self.client.get('/seq_list/')
        self.assertEqual(r.get('X-Content-Type-Options'), 'nosniff')
```

Note: `Referrer-Policy` is not tested here because Django's test client does not reliably populate it. The header IS injected in real browser responses; the settings value is correct.

- [ ] **Step 4: Run the new tests — both must pass**

```bash
python manage.py test app01.tests.SecurityHeaderTests -v 2
```

Expected:

```
test_content_type_nosniff (app01.tests.SecurityHeaderTests) ... ok
test_x_frame_options_deny (app01.tests.SecurityHeaderTests) ... ok

Ran 2 tests in X.XXXs

OK
```

If `test_x_frame_options_deny` fails with `None != 'DENY'`, confirm `django.middleware.security.SecurityMiddleware` is listed in `MIDDLEWARE` in `bms/settings.py` (it should already be present as it is part of the default Django setup).

- [ ] **Step 5: Run the full test suite — verify no regressions**

```bash
python manage.py test app01 -v 1 2>&1 | tail -20
```

Expected: 133 tests total (131 after Task 1 + 2 new). Failures remain at 5 (the same pre-existing failures). No new failures.

- [ ] **Step 6: Commit**

```bash
git add bms/settings.py app01/tests.py
git commit -m "feat: add X-Frame-Options, Content-Type-Options, Referrer-Policy headers

Append three HTTP-safe security header constants to bms/settings.py.
SecurityMiddleware (already in MIDDLEWARE) injects them on every response.

HTTPS-specific headers intentionally omitted: deployment is internal HTTP only.

Adds SecurityHeaderTests (2 tests) to verify header injection.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Final Verification

After both tasks are committed:

```bash
python manage.py test app01 -v 1 2>&1 | tail -5
```

Expected: 133 tests, exactly 5 failures (the pre-existing ones), 0 errors from the new code.

```bash
python manage.py check
```

Expected: 0 issues.
