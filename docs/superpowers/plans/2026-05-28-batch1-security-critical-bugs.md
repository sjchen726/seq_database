# Batch 1 — Security + Critical Bugs + Bug-type UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 9 high-priority issues — 2 security vulnerabilities, 4 critical logic bugs, and 3 UX bugs — so the application reaches a stable, safe baseline before tackling deeper refactors in Batch 2.

**Architecture:** All fixes are local edits to existing views/templates — no new migrations, no new models, no new URL patterns. Each task is self-contained: fix one view function or one template file, add a test, commit. No dependencies between tasks.

**Tech Stack:** Django 5.1 · Python 3.10 · MySQL · `django.test.TestCase` · Django test client

---

## Project Context

- All views live in `app01/views.py` (~4900 lines, function-based)
- Templates in top-level `templates/`
- Custom user model: `app01.models.LmsUser` (extends `AbstractUser`); `user_type` field distinguishes roles
- Helpers already in views.py:
  - `_module_list_url(base, page, q)` at ~line 32 — builds redirect URL with page/q params
  - `get_permitted_delivery_qs(user)` at ~line 2659 — returns project-filtered Delivery queryset
  - `get_delivery_colored(seq, selected_seq_type, seq_type, ...)` at line 74
  - `get_modify_seq_colored(seq, selected_seq_type, seq_type, ...)` at line 209
  - `auto_register_bare_sequences(pairs, username)` at line 1511
- Run tests with: `python manage.py test app01 -v 2`
- Run server: `source venv/bin/activate && python manage.py runserver`

---

## File Structure

| File | Role |
|------|------|
| `app01/views.py` | Primary file — 6 of 9 fixes live here |
| `app01/tests.py` | Tests for all 9 tasks (add to existing file) |
| `templates/auth_list.html` | SEC-02: delete link → POST form |
| `templates/base.html` | UX-01/02: navigation highlight fix |
| `templates/edit_module.html` | UX-05/06: add hidden page/q fields |
| `templates/module_list.html` | UX-05/06: add page/q to edit link and delete form |

---

## Task 1: SEC-02 — User Deletion via GET (CSRF Vulnerability)

**Files:**
- Modify: `app01/views.py` — `drop_author` function (~line 501)
- Modify: `templates/auth_list.html` — delete link at line 49
- Modify: `app01/tests.py` — add `DropAuthorSecurityTests` class

**Background:** `drop_author` reads the user ID from `request.GET`, so any `<img src="/drop_author/?id=X">` can silently delete a user. Fix: require POST + CSRF token.

- [ ] **Step 1: Add a failing test**

Add this class to `app01/tests.py`:

```python
class DropAuthorSecurityTests(TestCase):
    def setUp(self):
        self.admin = LmsUser.objects.create_user(
            username='admin_test', password='pass', user_type='admin', is_admin=True
        )
        self.victim = LmsUser.objects.create_user(
            username='victim_user', password='pass', user_type='guest'
        )
        self.client.login(username='admin_test', password='pass')

    def test_get_request_returns_400(self):
        """GET to drop_author must be rejected (CSRF protection)."""
        response = self.client.get(f'/drop_author/?id={self.victim.id}')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(LmsUser.objects.filter(id=self.victim.id).exists())

    def test_post_request_deletes_user(self):
        """POST to drop_author with valid id deletes the user."""
        response = self.client.post('/drop_author/', {'id': self.victim.id})
        self.assertIn(response.status_code, [200, 302])
        self.assertFalse(LmsUser.objects.filter(id=self.victim.id).exists())
```

- [ ] **Step 2: Run test to confirm failure**

```bash
python manage.py test app01.tests.DropAuthorSecurityTests -v 2
```

Expected: `test_get_request_returns_400` FAILS (currently returns 200/302, not 400).

- [ ] **Step 3: Fix `drop_author` view in `app01/views.py`**

Find `def drop_author(request):` (~line 501). Replace the opening block:

```python
# BEFORE (line 501-506):
def drop_author(request):
    if not request.user.is_authenticated or (not request.user.is_superuser and not request.user.is_admin):
        messages.error(request, '您没有权限删除用户信息！')
        return redirect('/author_list/')

    drop_id = request.GET.get('id')

# AFTER:
def drop_author(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('仅支持 POST 请求')
    if not request.user.is_authenticated or (not request.user.is_superuser and not request.user.is_admin):
        messages.error(request, '您没有权限删除用户信息！')
        return redirect('/author_list/')

    drop_id = request.POST.get('id')
```

Make sure `HttpResponseBadRequest` is imported — check the top of `views.py` for the existing import line:

```python
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
```

If `HttpResponseBadRequest` is missing from the import, add it.

- [ ] **Step 4: Fix the delete link in `templates/auth_list.html`**

Find line 49 (the `<a>` delete link):

```html
<!-- BEFORE (lines 49-50): -->
<a class="ds-act" style="color:#ef4444;" href="{% url 'drop_author' %}?id={{ user.id }}"
   title="删除" onclick="return confirm('确定删除用户 {{ user.username }}？');">&#128465;</a>

<!-- AFTER: -->
<form method="POST" action="{% url 'drop_author' %}" style="display:inline;"
      onsubmit="return confirm('确定删除用户 {{ user.username }}？');">
  {% csrf_token %}
  <input type="hidden" name="id" value="{{ user.id }}">
  <button type="submit" class="ds-act" style="color:#ef4444;background:none;border:none;cursor:pointer;" title="删除">&#128465;</button>
</form>
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
python manage.py test app01.tests.DropAuthorSecurityTests -v 2
```

Expected: both tests PASS.

- [ ] **Step 6: Manual smoke test**

Start the server, log in as admin, go to `/author_list/`, click the delete icon for any user — confirm the confirmation dialog appears and deletion works. Then try `curl -X GET http://localhost:8000/drop_author/?id=1` — confirm 400 response.

- [ ] **Step 7: Commit**

```bash
git add app01/views.py app01/tests.py templates/auth_list.html
git commit -m "fix(sec): drop_author require POST to prevent CSRF deletion via GET

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: SEC-03 — `download_selected` Bypasses Project Permissions

**Files:**
- Modify: `app01/views.py` — `download_selected` function (~line 3345)
- Modify: `app01/tests.py` — add `DownloadSelectedPermissionTests` class

**Background:** `download_selected` queries `Delivery.objects.filter(duplex_id__in=ids)` without checking the user's `permissions_project`. A guest-level user could download restricted data. Fix: use `get_permitted_delivery_qs(user)` as the base queryset.

- [ ] **Step 1: Add a failing test**

```python
from django.test import TestCase, Client
import json

class DownloadSelectedPermissionTests(TestCase):
    def setUp(self):
        # Create two sequences in different projects
        self.seq_a = Sequence.objects.create(seq='AUGCAU', seq_type='SS')
        self.seq_b = Sequence.objects.create(seq='UGCAUG', seq_type='SS')

        # Delivery in project "PROJ-A" (user has access)
        self.del_a = Delivery.objects.create(
            sequence=self.seq_a, duplex_id='BP000001',
            project='PROJ-A', seq_type='SS',
            delivery5='', delivery3='', modify_seq='AmUm', linker_seq='AoU',
        )
        # Delivery in project "PROJ-B" (user has NO access)
        self.del_b = Delivery.objects.create(
            sequence=self.seq_b, duplex_id='BP000002',
            project='PROJ-B', seq_type='SS',
            delivery5='', delivery3='', modify_seq='GmCm', linker_seq='GoC',
        )

        # User with access only to PROJ-A
        self.user = LmsUser.objects.create_user(
            username='proj_user', password='pass',
            user_type='delivery',
            permissions_project='PROJ-A',
        )
        self.client.login(username='proj_user', password='pass')

    def test_restricted_delivery_filtered_out(self):
        """User requesting BP000002 (PROJ-B) should receive empty CSV body (header only)."""
        response = self.client.post(
            '/download_selected/',
            {
                'selected_ids': json.dumps(['BP000002']),
                'selected_columns': json.dumps(['duplex_id', 'project']),
            }
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8-sig')
        lines = [l for l in content.strip().split('\n') if l.strip()]
        # Only the header row — no data rows
        self.assertEqual(len(lines), 1, f"Expected header only, got: {lines}")

    def test_permitted_delivery_included(self):
        """User requesting BP000001 (PROJ-A) should receive the data row."""
        response = self.client.post(
            '/download_selected/',
            {
                'selected_ids': json.dumps(['BP000001']),
                'selected_columns': json.dumps(['duplex_id', 'project']),
            }
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8-sig')
        self.assertIn('BP000001', content)
```

- [ ] **Step 2: Run test to confirm failure**

```bash
python manage.py test app01.tests.DownloadSelectedPermissionTests -v 2
```

Expected: `test_restricted_delivery_filtered_out` FAILS (currently returns PROJ-B data).

- [ ] **Step 3: Fix `download_selected` in `app01/views.py`**

Find `def download_selected(request):` (~line 3345). Replace lines 3359–3361:

```python
# BEFORE:
    deliveries = Delivery.objects.filter(duplex_id__in=ids)\
        .select_related('sequence')\
        .prefetch_related('sequence__target_info')

# AFTER:
    base_qs = get_permitted_delivery_qs(request.user)
    deliveries = base_qs.filter(duplex_id__in=ids)\
        .select_related('sequence')\
        .prefetch_related('sequence__target_info')
```

`get_permitted_delivery_qs` is already defined in the same file (~line 2659). No new imports needed.

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python manage.py test app01.tests.DownloadSelectedPermissionTests -v 2
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "fix(sec): download_selected now respects project-level permissions

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: BUG-01 — `edit_reg_seq` Silently Drops `edit_project`

**Files:**
- Modify: `app01/views.py` — `edit_reg_seq` function (~line 3248)
- Modify: `app01/tests.py` — add `EditRegSeqProjectTests` class

**Background:** Line 3263: `edit_seq = request.POST.get('edit_project')`. The form value is read but stored in the wrong variable `edit_seq`, which is never used. `seqinfo.project` is therefore never updated. Fix: use the correct variable name and add project change-tracking.

- [ ] **Step 1: Add a failing test**

```python
class EditRegSeqProjectTests(TestCase):
    def setUp(self):
        self.admin = LmsUser.objects.create_user(
            username='admin2', password='pass', user_type='admin', is_admin=True
        )
        self.client.login(username='admin2', password='pass')
        self.seq = Sequence.objects.create(seq='AUGCAU', seq_type='SS')
        self.seqinfo = SeqInfo.objects.create(
            sequence=self.seq,
            project='OLD-PROJECT',
            Pos='1',
            Transcript='NM_001',
            Remark='',
        )

    def test_edit_project_is_saved(self):
        """Submitting a new project value must persist to SeqInfo.project."""
        response = self.client.post(
            f'/edit_reg_seq/?id={self.seq.rm_code}',
            {
                'edit_project': 'NEW-PROJECT',
                'edit_position': '1',
                'edit_Transcript': 'NM_001',
                'edit_Remark': '',
                'edit_date': '',
            }
        )
        self.seqinfo.refresh_from_db()
        self.assertEqual(
            self.seqinfo.project, 'NEW-PROJECT',
            f"Expected 'NEW-PROJECT', got '{self.seqinfo.project}'"
        )
```

- [ ] **Step 2: Run test to confirm failure**

```bash
python manage.py test app01.tests.EditRegSeqProjectTests -v 2
```

Expected: FAIL — `seqinfo.project` stays `'OLD-PROJECT'`.

- [ ] **Step 3: Fix `edit_reg_seq` in `app01/views.py`**

Find line 3263. Make two changes:

**Change A** — fix the variable name (line ~3263):

```python
# BEFORE:
        edit_seq = request.POST.get('edit_project')

# AFTER:
        edit_project = request.POST.get('edit_project')
```

**Change B** — add project change-tracking inside the `changes = []` block (~lines 3278–3287). Insert after `edit_remark` check:

```python
        # existing checks (Pos, Transcript, Remark) remain unchanged
        if seqinfo and seqinfo.project != edit_project:
            changes.append(f"Project: {seqinfo.project} → {edit_project}")
            seqinfo.project = edit_project
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
python manage.py test app01.tests.EditRegSeqProjectTests -v 2
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "fix: edit_reg_seq now saves edit_project field (was assigned to wrong variable)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: BUG-05 — AS Strand Reversal Uses Self-Comparison

**Files:**
- Modify: `app01/views.py` — `get_delivery_colored` (~line 82,127) and `get_modify_seq_colored` (~line 263,342)
- Modify: `app01/tests.py` — add `ASReversalTests` class

**Background:** Both coloring functions set `reversed_seq_type = selected_seq_type` then check `if seq_type == reversed_seq_type:`. This makes the reversal conditional on whether the sequence's type matches the *selected filter*, not whether it is actually an AS strand. When `selected_seq_type` is `None` or `'SS'`, AS strands aren't reversed even though they should be. Fix: replace the check with `if seq_type == 'AS':`.

- [ ] **Step 1: Add a failing test**

```python
from app01.views import get_delivery_colored, get_modify_seq_colored

class ASReversalTests(TestCase):
    def setUp(self):
        # Minimal DeliveryModule entries for the coloring function to work
        DeliveryModule.objects.get_or_create(keyword='Am', defaults={'type_code': 'mod'})
        DeliveryModule.objects.get_or_create(keyword='Um', defaults={'type_code': 'mod'})

    def test_as_strand_reversed_when_selected_is_ss(self):
        """AS strand must be reversed even when selected_seq_type='SS'."""
        tokens_as = get_delivery_colored('AmUm', selected_seq_type='SS', seq_type='AS')
        tokens_ss = get_delivery_colored('AmUm', selected_seq_type='SS', seq_type='SS')
        chars_as = [t['char'] for t in tokens_as if t['char'] not in ('s', 'o', '-')]
        chars_ss = [t['char'] for t in tokens_ss if t['char'] not in ('s', 'o', '-')]
        # AS should be reversed: Um then Am; SS should be forward: Am then Um
        self.assertEqual(chars_as, ['Um', 'Am'],
                         f"AS tokens not reversed: {chars_as}")
        self.assertEqual(chars_ss, ['Am', 'Um'],
                         f"SS tokens wrong order: {chars_ss}")

    def test_as_strand_reversed_when_selected_is_none(self):
        """AS strand must be reversed even when selected_seq_type is None."""
        tokens_as = get_delivery_colored('AmUm', selected_seq_type=None, seq_type='AS')
        chars_as = [t['char'] for t in tokens_as if t['char'] not in ('s', 'o', '-')]
        self.assertEqual(chars_as, ['Um', 'Am'],
                         f"AS tokens not reversed when selected=None: {chars_as}")

    def test_ss_strand_not_reversed(self):
        """SS strand must never be reversed regardless of selected_seq_type."""
        tokens = get_delivery_colored('AmUm', selected_seq_type='AS', seq_type='SS')
        chars = [t['char'] for t in tokens if t['char'] not in ('s', 'o', '-')]
        self.assertEqual(chars, ['Am', 'Um'],
                         f"SS tokens were incorrectly reversed: {chars}")
```

- [ ] **Step 2: Run test to confirm failure**

```bash
python manage.py test app01.tests.ASReversalTests -v 2
```

Expected: `test_as_strand_reversed_when_selected_is_ss` and `test_as_strand_reversed_when_selected_is_none` FAIL.

- [ ] **Step 3: Fix `get_delivery_colored` in `app01/views.py`**

Locate the two lines at ~82 and ~127:

```python
# BEFORE (line ~82):
    reversed_seq_type = selected_seq_type

# DELETE this line entirely.
```

```python
# BEFORE (line ~127):
    if seq_type == reversed_seq_type:

# AFTER:
    if seq_type == 'AS':
```

- [ ] **Step 4: Fix `get_modify_seq_colored` in `app01/views.py`**

Locate the two lines at ~263 and ~342:

```python
# BEFORE (line ~263):
    reversed_seq_type = selected_seq_type

# DELETE this line entirely.
```

```python
# BEFORE (line ~342):
    if seq_type == reversed_seq_type:

# AFTER:
    if seq_type == 'AS':
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
python manage.py test app01.tests.ASReversalTests -v 2
```

Expected: all three tests PASS.

- [ ] **Step 6: Run full test suite to catch regressions**

```bash
python manage.py test app01 -v 2
```

Expected: all tests PASS. If any existing test breaks, investigate before committing.

- [ ] **Step 7: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "fix: AS strand reversal now always triggers for seq_type='AS', not based on selected filter

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: BUG-04 — BP ID Generation Race Condition

**Files:**
- Modify: `app01/views.py` — `assign_duplex_ids` function (~line 1712)
- Modify: `app01/tests.py` — add `AssignDuplexIdTests` class

**Background:** `assign_duplex_ids` reads `MAX(duplex_id)` then computes the next number, all without a database lock. Concurrent uploads can read the same MAX and generate duplicate IDs. Fix: wrap the read+compute in `transaction.atomic()` with `select_for_update()`.

- [ ] **Step 1: Add a failing test**

```python
from app01.views import assign_duplex_ids
import pandas as pd

class AssignDuplexIdTests(TestCase):
    def _make_groups(self, n_groups):
        """Build n_groups of [(ss_row_id, as_row_id)] pairs."""
        groups = []
        for i in range(n_groups):
            groups.append((None, f'P{i}', [i * 2, i * 2 + 1]))
        return groups

    def _make_df(self, n_groups):
        rows = []
        for i in range(n_groups * 2):
            rows.append({'__row_id': i, 'Seq_type': 'SS' if i % 2 == 0 else 'AS'})
        df = pd.DataFrame(rows)
        df.index = df['__row_id'].astype(int)
        return df

    def test_sequential_calls_generate_unique_ids(self):
        """Two back-to-back calls must not generate overlapping duplex IDs."""
        Delivery.objects.create(
            sequence=Sequence.objects.create(seq='AAAA', seq_type='SS'),
            duplex_id='BP000001', project='P', seq_type='SS',
            delivery5='', delivery3='', modify_seq='Am', linker_seq='A',
        )
        df = self._make_df(2)
        groups = self._make_groups(2)
        map1 = assign_duplex_ids(df, groups, set())
        map2 = assign_duplex_ids(df, groups, set())
        ids1 = set(map1.values())
        ids2 = set(map2.values())
        self.assertTrue(ids1.isdisjoint(ids2),
                        f"Overlapping duplex IDs generated: {ids1 & ids2}")

    def test_id_format_is_bp_six_digits(self):
        """Generated IDs must match BP######."""
        import re
        df = self._make_df(1)
        groups = self._make_groups(1)
        id_map = assign_duplex_ids(df, groups, set())
        for v in id_map.values():
            self.assertRegex(v, r'^BP\d{6}$')
```

- [ ] **Step 2: Run test to confirm first test passes (it already does) and serves as regression guard**

```bash
python manage.py test app01.tests.AssignDuplexIdTests -v 2
```

Expected: may already PASS (since it's sequential). That's fine — these are regression guards.

- [ ] **Step 3: Fix `assign_duplex_ids` in `app01/views.py`**

Find `def assign_duplex_ids` (~line 1712). Replace the entire function:

```python
def assign_duplex_ids(df, ss_groups, repeated_ids):
    duplex_id_map = {}
    valid_groups = [group for _, _, group in ss_groups if not repeated_ids.intersection(group)]

    pattern = re.compile(r"^BP(\d{6})$")

    with transaction.atomic():
        existing_ids = (
            Delivery.objects
            .select_for_update()
            .filter(duplex_id__startswith="BP")
            .values_list('duplex_id', flat=True)
        )
        existing_numbers = [
            int(m.group(1)) for d in existing_ids if (m := pattern.match(d))
        ]
        next_number = max(existing_numbers, default=0) + 1

        for group in valid_groups:
            serial = f"{next_number:06d}"
            duplex_id = f"BP{serial}"
            for row_id in group:
                duplex_id_map[row_id] = duplex_id
            next_number += 1

    return duplex_id_map
```

`transaction` is already imported at the top of `views.py` (`from django.db import transaction`). Verify this import exists — if not, add it.

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python manage.py test app01.tests.AssignDuplexIdTests -v 2
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "fix: wrap assign_duplex_ids in transaction.atomic + select_for_update to prevent race

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6: UX-01/02 — Navigation Highlight Uses Substring `in` Check

**Files:**
- Modify: `templates/base.html` — line 78

**Background:** `{% if request.resolver_match.url_name in 'author_list,add_author,edit_author' %}` uses Django's template `in` operator on a string, which checks for *substring* presence — not list membership. So any url_name containing `'list'`, `'edit'`, or `'author'` incorrectly activates the Users nav item. Fix: use explicit `==` comparisons joined with `or`.

- [ ] **Step 1: Locate the broken line**

Open `templates/base.html`. Find line 78 (the Users nav item):

```html
<a href="{% url 'author_list' %}" class="ds-nav-item {% if request.resolver_match.url_name in 'author_list,add_author,edit_author' %}active{% endif %}">
```

- [ ] **Step 2: Fix the condition**

Replace the entire line with:

```html
    <a href="{% url 'author_list' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'author_list' or request.resolver_match.url_name == 'add_author' or request.resolver_match.url_name == 'edit_author' %}active{% endif %}">
```

- [ ] **Step 3: Manual verification**

Start the dev server and visit these URLs. Confirm only the correct nav item is highlighted:

| URL | Expected active item |
|-----|---------------------|
| `/reg_seq_list/` | 注册序列 (NOT 用户管理) |
| `/module_list/` | Delivery 模块 (NOT 用户管理) |
| `/seqmodule_list/` | 序列修饰模块 (NOT 用户管理) |
| `/edit_seq/` | 无高亮 (NOT 用户管理) |
| `/author_list/` | 用户管理 ✓ |
| `/add_author/` | 用户管理 ✓ |
| `/edit_author/` | 用户管理 ✓ |

- [ ] **Step 4: Commit**

```bash
git add templates/base.html
git commit -m "fix: base.html navigation highlight uses == instead of string 'in' substring check

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 7: UX-05/06 — DeliveryModule Edit/Delete Lose page/q Params

**Files:**
- Modify: `app01/views.py` — `edit_module` (~line 3431) and `delete_module` (~line 3540)
- Modify: `templates/edit_module.html` — add hidden page/q fields + update return links
- Modify: `templates/module_list.html` — add page/q to edit link and delete form
- Modify: `app01/tests.py` — add `ModuleListPageParamTests` class

**Background:** After editing or deleting a DeliveryModule, the redirect always goes to `/module_list/` without `?page=N&q=X`. The `_module_list_url(base, page, q)` helper already exists in views.py. SeqModule and LinkerModule were fixed in a previous round; this is the leftover.

- [ ] **Step 1: Add a failing test**

```python
class ModuleListPageParamTests(TestCase):
    def setUp(self):
        self.admin = LmsUser.objects.create_user(
            username='mod_admin', password='pass', user_type='admin',
            is_admin=True, is_superuser=True,
        )
        self.client.login(username='mod_admin', password='pass')
        self.module = DeliveryModule.objects.create(keyword='TestKW', type_code='test')

    def test_edit_module_redirect_preserves_page_and_q(self):
        """POST to edit_module should redirect to module_list with page and q params."""
        response = self.client.post(
            f'/edit_module/?id={self.module.id}',
            {
                'keyword': 'TestKW',
                'type_code': 'test',
                'Strand_MWs': '',
                'page': '3',
                'q': 'LP',
            }
        )
        self.assertRedirects(
            response, '/module_list/?page=3&q=LP',
            fetch_redirect_response=False,
        )

    def test_delete_module_redirect_preserves_page_and_q(self):
        """POST to delete_module should redirect to module_list with page and q params."""
        response = self.client.post(
            '/delete_module/',
            {'id': self.module.id, 'page': '2', 'q': 'C16'}
        )
        self.assertRedirects(
            response, '/module_list/?page=2&q=C16',
            fetch_redirect_response=False,
        )
```

- [ ] **Step 2: Run test to confirm failure**

```bash
python manage.py test app01.tests.ModuleListPageParamTests -v 2
```

Expected: both tests FAIL (redirect to `/module_list/` without params).

- [ ] **Step 3: Fix `edit_module` in `app01/views.py`**

Find `def edit_module(request):` (~line 3431). Make these changes:

**3a.** In the GET branch (where the form is rendered), read page and q from `request.GET` and pass to context. Find the final `return render(...)` at the end of the function (~line 3477):

```python
# BEFORE:
    return render(request, 'edit_module.html', {'module': module})

# AFTER:
    page = request.GET.get('page', 1)
    q = request.GET.get('q', '')
    return render(request, 'edit_module.html', {'module': module, 'page': page, 'q': q})
```

**3b.** Also pass page/q for the POST error renders (validation failures). Find all `return render(request, 'edit_module.html', {...})` calls in the POST block (~lines 3454, 3467) and add `'page': request.POST.get('page', 1), 'q': request.POST.get('q', ''),` to each dict.

**3c.** Fix the two successful-POST redirects. Replace both `return redirect('/module_list/')` in the POST block:

```python
# BEFORE (appears twice, ~line 3462 and ~line 3475):
            return redirect('/module_list/')

# AFTER (both occurrences):
            page = request.POST.get('page', 1)
            q = request.POST.get('q', '')
            return redirect(_module_list_url('/module_list/', page, q))
```

- [ ] **Step 4: Fix `delete_module` in `app01/views.py`**

Find `def delete_module(request):` (~line 3540). Replace `return redirect('/module_list/')` inside the try block:

```python
# BEFORE (~line 3550):
        return redirect('/module_list/')

# AFTER:
        page = request.POST.get('page', 1)
        q = request.POST.get('q', '')
        return redirect(_module_list_url('/module_list/', page, q))
```

- [ ] **Step 5: Update `templates/edit_module.html`**

Add two hidden inputs inside the `<form>` tag, after `{% csrf_token %}`:

```html
<!-- Add after {% csrf_token %} (around line 18): -->
      <input type="hidden" name="page" value="{{ page|default:1 }}">
      <input type="hidden" name="q" value="{{ q|default:'' }}">
```

Also update the two "返回" links to carry page/q:

```html
<!-- BEFORE (topbar): -->
  <a href="{% url 'module_list' %}" class="ds-btn ds-btn-ghost">返回列表</a>

<!-- AFTER: -->
  <a href="{% url 'module_list' %}{% if page %}?page={{ page }}&q={{ q|urlencode }}{% endif %}" class="ds-btn ds-btn-ghost">返回列表</a>
```

```html
<!-- BEFORE (form footer): -->
        <a href="{% url 'module_list' %}" class="ds-btn ds-btn-ghost">返回</a>

<!-- AFTER: -->
        <a href="{% url 'module_list' %}{% if page %}?page={{ page }}&q={{ q|urlencode }}{% endif %}" class="ds-btn ds-btn-ghost">返回</a>
```

- [ ] **Step 6: Update `templates/module_list.html`**

**6a.** Update the edit link to carry page and q:

```html
<!-- BEFORE (~line 47): -->
              <a href="{% url 'edit_module' %}?id={{ module.id }}" class="ds-act ds-act-edit">编辑</a>

<!-- AFTER: -->
              <a href="{% url 'edit_module' %}?id={{ module.id }}&page={{ page_obj.number }}&q={{ q|urlencode }}" class="ds-act ds-act-edit">编辑</a>
```

**6b.** Add page/q hidden fields to the delete form:

```html
<!-- BEFORE: -->
              <form method="POST" action="{% url 'delete_module' %}" style="display:inline;" onsubmit="return confirm('确定删除该模块？');">
                {% csrf_token %}
                <input type="hidden" name="id" value="{{ module.id }}">
                <button type="submit" class="ds-act ds-act-delete">删除</button>
              </form>

<!-- AFTER: -->
              <form method="POST" action="{% url 'delete_module' %}" style="display:inline;" onsubmit="return confirm('确定删除该模块？');">
                {% csrf_token %}
                <input type="hidden" name="id" value="{{ module.id }}">
                <input type="hidden" name="page" value="{{ page_obj.number }}">
                <input type="hidden" name="q" value="{{ q }}">
                <button type="submit" class="ds-act ds-act-delete">删除</button>
              </form>
```

- [ ] **Step 7: Run tests to confirm they pass**

```bash
python manage.py test app01.tests.ModuleListPageParamTests -v 2
```

Expected: both tests PASS.

- [ ] **Step 8: Commit**

```bash
git add app01/views.py templates/edit_module.html templates/module_list.html app01/tests.py
git commit -m "fix: DeliveryModule edit/delete now preserve page and q params on redirect

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 8: BUG-07 — AS Chain Has No SeqInfo After Auto-Registration

**Files:**
- Modify: `app01/views.py` — `auto_register_bare_sequences` function (~line 1572)
- Modify: `app01/tests.py` — add test to existing `AutoRegisterTests` class

**Background:** `auto_register_bare_sequences` creates `SeqInfo` for the SS strand but not for the AS strand. When a user clicks "编辑" on a newly registered AS chain, `edit_reg_seq` calls `get_object_or_404(SeqInfo, sequence_id=rm_code)` which raises 404. Fix: mirror the SS SeqInfo creation for AS.

- [ ] **Step 1: Add a failing test**

Add this test method inside the existing `AutoRegisterTests` class in `app01/tests.py`:

```python
    def test_as_chain_seqinfo_created(self):
        """auto_register_bare_sequences must create SeqInfo for AS chain too."""
        pairs = [self._make_pair('AUGCAU', 'UGCAUG', transcript='NM_001', position='42')]
        auto_register_bare_sequences(pairs, self.username)
        as_obj = Sequence.objects.get(seq='UGCAUG', seq_type='AS')
        self.assertTrue(
            SeqInfo.objects.filter(sequence=as_obj).exists(),
            "SeqInfo must be created for AS chain"
        )

    def test_as_chain_seqinfo_has_correct_fields(self):
        """SeqInfo for AS chain should carry the same transcript/position as SS."""
        pairs = [self._make_pair('AUGCAU', 'UGCAUG', transcript='NM_999', position='77')]
        auto_register_bare_sequences(pairs, self.username)
        as_obj = Sequence.objects.get(seq='UGCAUG', seq_type='AS')
        info = SeqInfo.objects.get(sequence=as_obj)
        self.assertEqual(info.Transcript, 'NM_999')
        self.assertEqual(info.Pos, '77')
```

- [ ] **Step 2: Run test to confirm failure**

```bash
python manage.py test app01.tests.AutoRegisterTests.test_as_chain_seqinfo_created app01.tests.AutoRegisterTests.test_as_chain_seqinfo_has_correct_fields -v 2
```

Expected: both FAIL — `SeqInfo.DoesNotExist`.

- [ ] **Step 3: Fix `auto_register_bare_sequences` in `app01/views.py`**

Find the SeqInfo creation block (~lines 1572–1581):

```python
                # ── SeqInfo (SS only，如不存在则创建) ──
                if not SeqInfo.objects.filter(sequence=ss_obj).exists():
                    SeqInfo.objects.create(
                        sequence=ss_obj,
                        Transcript=transcript,
                        Pos=position,
                        project=project,
                        Remark='',
                        created_at=created_at,
                    )
```

Change the comment and add an AS block immediately after:

```python
                # ── SeqInfo SS（如不存在则创建）──
                if not SeqInfo.objects.filter(sequence=ss_obj).exists():
                    SeqInfo.objects.create(
                        sequence=ss_obj,
                        Transcript=transcript,
                        Pos=position,
                        project=project,
                        Remark='',
                        created_at=created_at,
                    )

                # ── SeqInfo AS（如不存在则创建）──
                if not SeqInfo.objects.filter(sequence=as_obj).exists():
                    SeqInfo.objects.create(
                        sequence=as_obj,
                        Transcript=transcript,
                        Pos=position,
                        project=project,
                        Remark='',
                        created_at=created_at,
                    )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python manage.py test app01.tests.AutoRegisterTests -v 2
```

Expected: all tests in `AutoRegisterTests` PASS (including the two new ones).

- [ ] **Step 5: Run full test suite**

```bash
python manage.py test app01 -v 2
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "fix: auto_register_bare_sequences creates SeqInfo for AS chain (was SS-only)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Final Smoke Test

After all 8 commits, perform a manual walkthrough:

1. **SEC-02**: Log in as admin → `/author_list/` → delete a user via the icon button. Also try `curl -X GET /drop_author/?id=1` → 400.
2. **SEC-03**: Log in as limited-permission user → select some deliveries from a restricted project → download → CSV has only the header.
3. **BUG-01**: Edit a registered sequence, change its Project field → save → refresh: project shows updated value.
4. **BUG-05**: Open the delivery list in duplex view. AS chains should display 3'→5' direction (reversed token order vs SS).
5. **BUG-04**: No observable change from the UI, but server logs should show no "Duplicate entry for duplex_id" errors under concurrent load.
6. **UX-01/02**: Navigate to `/reg_seq_list/`, `/module_list/`, `/seqmodule_list/` — "用户管理" nav item must NOT be highlighted.
7. **UX-05/06**: In `/module_list/` on page 2 with search `q=LP`, click 编辑 → edit page shows correct data → save → redirect back to page 2 with `q=LP`.
8. **BUG-07**: Upload a CSV with a new AS+SS pair → after registration, click 编辑 on the AS chain → form opens successfully (no 404).
