# edit_seq Permission Fix + HTTP Security Headers — Design Spec

## Goal

Fix a project-permission bypass in the `edit_seq` view (same class of bug as the
`cor_seq` fix shipped in the previous round), and add three HTTP-safe security
headers to harden the application for its internal-network HTTP deployment.

## Architecture

Two independent fixes, one commit each.

| # | Fix | Type | Files |
|---|-----|------|-------|
| 1 | `edit_seq` GET path lacks project-permission filter | Backend security | `app01/views.py`, `app01/tests.py` |
| 2 | Add X-Frame-Options, Content-Type-Options, Referrer-Policy headers | Config security | `bms/settings.py` |

---

## Fix 1: `edit_seq` Permission Bypass

### Root Cause

`app01/views.py:719`:

```python
delivery = get_object_or_404(Delivery, Q(id=seq_id) & Q(Strand_MWs=seq_Strand_MWs))
```

Any authenticated user can supply an arbitrary numeric `id` in the query string
and reach the edit page for a delivery that belongs to a project they have no
permission to access. The POST path is protected by `user_can_edit_delivery()`,
but the GET path already exposes all delivery field values in the rendered form.

### Fix

Replace the unscoped lookup with the user's permitted queryset — identical
pattern to the `cor_seq` fix applied in the previous round:

```python
permitted_qs = get_permitted_delivery_qs(request.user)
delivery = get_object_or_404(permitted_qs, Q(id=seq_id) & Q(Strand_MWs=seq_Strand_MWs))
```

`get_permitted_delivery_qs` is already defined in `views.py` and handles the
superadmin case (returns `Delivery.objects.all()`), so privileged users are
not affected.

**Response on unauthorized access:** HTTP 404 — does not leak whether the
delivery ID exists.

### Tests

Append `EditSeqPermissionTests` to `app01/tests.py`:

```python
class EditSeqPermissionTests(TestCase):
    """edit_seq must not expose deliveries outside the user's permitted projects."""

    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='editseq_noperm', password='p',
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
        url = f'/edit_seq/?id={self.delivery.id}&strand_MWs=1234.5'
        r = self.client.get(url)
        self.assertEqual(r.status_code, 404)

    def test_permitted_user_gets_200(self):
        self.user.permissions_project = 'PRJ-HIDDEN'
        self.user.save()
        url = f'/edit_seq/?id={self.delivery.id}&strand_MWs=1234.5'
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
```

---

## Fix 2: HTTP Security Headers

### Root Cause

`bms/settings.py` has no security header configuration. Django's
`SecurityMiddleware` (already present in `MIDDLEWARE`) will inject these headers
automatically once the settings are present, but they are absent by default.

The deployment is internal-network HTTP only — HTTPS-specific settings
(`SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`,
`SECURE_HSTS_SECONDS`) must NOT be set, as they would break the HTTP deployment.

### Fix

Append to the bottom of `bms/settings.py`:

```python
# ── Security headers (injected by SecurityMiddleware) ──
X_FRAME_OPTIONS = 'DENY'            # Prevent clickjacking via iframe embedding
SECURE_CONTENT_TYPE_NOSNIFF = True  # Prevent MIME-type sniffing
REFERRER_POLICY = 'same-origin'     # Do not send Referer on cross-origin requests
```

These are hardcoded constants — no environment variable needed. Values are
appropriate for an internal HTTP deployment and will not change between
environments.

### Verification

`python manage.py check` must pass with 0 issues.

Add one test to verify `SecurityMiddleware` injects the headers:

```python
class SecurityHeaderTests(TestCase):
    """SecurityMiddleware must inject the configured headers on every response."""

    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='sec_header_user', password='p',
            user_type='sub_admin', permissions_project='',
        )
        self.client.force_login(self.user)

    def test_x_frame_options_deny(self):
        r = self.client.get('/seq_list/')
        self.assertEqual(r.get('X-Frame-Options'), 'DENY')

    def test_content_type_nosniff(self):
        r = self.client.get('/seq_list/')
        self.assertEqual(r.get('X-Content-Type-Options'), 'nosniff')
```

(`Referrer-Policy` is not tested because Django's test client does not always
populate it — the settings value is correct and the header is injected in real
browser responses.)

---

## Files Changed

| File | Change |
|------|--------|
| `app01/views.py` | `edit_seq`: one-line queryset scope fix |
| `app01/tests.py` | Append `EditSeqPermissionTests` + `SecurityHeaderTests` |
| `bms/settings.py` | Append 3 security header constants |

---

## Out of Scope

- HTTPS security headers (`SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`,
  `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`) — deployment is HTTP-only
- `Delivery.objects.filter(id__in=related_ids)` at `cor_seq:3234` — pre-existing,
  separate concern
- `edit_reg_seq` direct `created_at` mutation — separate concern
