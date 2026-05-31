# Security & Logic Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix five verified security and data-integrity bugs: XSS in the clone modal, a project-permission bypass in `cor_seq`, hard-coded `DEBUG`/`ALLOWED_HOSTS`, a nullable `created_at` on `Sequence`, and unvalidated session data in the preflight upload flow.

**Architecture:** Five independent commits, each touching one concern. No cross-task dependencies — any task can be skipped or reverted without affecting the others. All backend fixes tested with Django `TestCase`; the JS fix is verified manually in the browser.

**Tech Stack:** Django 5.1 / Python 3.10 / MySQL / jQuery / python-decouple 3.8

---

## File Map

| File | Task(s) | Change |
|------|---------|--------|
| `static/js/clone_delivery.js` | 1 | Rewrite modal builder with DOM API |
| `app01/tests.py` | 2, 4, 5 | New test classes at end of file |
| `app01/views.py` | 2, 5 | One-line fix in `cor_seq`; session guard in `confirm_upload_preflight` |
| `bms/settings.py` | 3 | Read `DEBUG` + `ALLOWED_HOSTS` via `config()` |
| `.env.example` | 3 | Document new env vars |
| `app01/models.py` | 4 | `auto_now_add=True` on `Sequence.created_at` |
| `app01/migrations/0036_sequence_created_at_auto_now_add.py` | 4 | Generated migration |

---

## Baseline

Before starting, note the pre-existing test failures (do NOT fix these — they are out of scope):

```
ERROR: test_cross_project_duplicate_triggers_share_list (CheckDuplicatesTests)
ERROR: test_linker_seq_format_difference_still_detected (CheckDuplicatesTests)
ERROR: test_new_sequence_not_in_db_no_duplicate (CheckDuplicatesTests)
ERROR: test_same_project_duplicate_goes_to_repeated_ids (CheckDuplicatesTests)
FAIL:  test_post_request_deletes_user (DropAuthorSecurityTests)
```

Your changes must not introduce any new failures beyond these five.

---

## Task 1: Fix XSS in Clone Modal (`clone_delivery.js`)

**Files:**
- Modify: `static/js/clone_delivery.js:18-55`

> **Note:** This is a pure JavaScript fix. There is no Django test framework for frontend rendering. The "failing test" step here is a manual browser check. The implementation replaces all `innerHTML`-via-string-concat with safe DOM API calls.

- [ ] **Step 1: Verify the vulnerability manually (pre-fix)**

  In the Django shell, create a delivery with an XSS payload in the `project` field:

  ```bash
  source venv/bin/activate
  python manage.py shell
  ```

  ```python
  from app01.models import Sequence, Delivery, DeliveryProject
  s = Sequence.objects.create(seq='TESTXSS', seq_type='AS')
  d = Delivery.objects.create(
      sequence=s, seq_type='AS', duplex_id='BP_XSS_TEST',
      project='"><img src=x onerror=alert(1)>'
  )
  DeliveryProject.objects.create(delivery=d, project_code='"><img src=x onerror=alert(1)>')
  print(d.id, d.duplex_id)
  ```

  Log in as a `sub_admin` user and open the clone modal for `BP_XSS_TEST`. The `<img>` tag should fire — confirming the bug. Press F12 and check the Console for the alert.

  After verifying, clean up:
  ```python
  d.delete(); s.delete()
  ```

- [ ] **Step 2: Rewrite `clone_delivery.js` lines 18–55 using DOM API**

  Replace the entire `rows.forEach` loop body (lines 18–55 in the original file) with:

  ```javascript
  rows.forEach(function(r, idx) {
      var rowDiv = document.createElement('div');
      rowDiv.className = 'ds-clone-row';

      // Heading
      var h6 = document.createElement('h6');
      var seqType = (r.Seq_type || '').toString().toUpperCase();
      if (seqType === 'AS' || seqType === 'SS') {
          h6.style.fontSize = '1.25rem';
          h6.style.fontWeight = '600';
      }
      h6.textContent = 'Record ' + (idx + 1) + ' - ' + (r.Seq_type || '');
      rowDiv.appendChild(h6);

      // Helper: create a labeled input cell
      function makeField(labelText, name, value, readOnly) {
          var wrapper = document.createElement('div');
          var lbl = document.createElement('label');
          lbl.className = 'ds-form-label';
          lbl.textContent = labelText;
          var inp = document.createElement('input');
          inp.name = name;
          inp.className = 'ds-form-control';
          inp.value = value || '';
          if (readOnly) inp.readOnly = true;
          wrapper.appendChild(lbl);
          wrapper.appendChild(inp);
          return wrapper;
      }

      // Row 1: Project, Target, Seq_type (readonly)
      var row1 = document.createElement('div');
      row1.className = 'ds-form-3col';
      row1.appendChild(makeField('Project',  'Project',  r.Project,  true));
      row1.appendChild(makeField('Target',   'Target',   r.Target,   true));
      row1.appendChild(makeField('Seq_type', 'Seq_type', r.Seq_type, true));
      rowDiv.appendChild(row1);

      // Row 2: Modify_seq (full width, editable)
      var row2 = document.createElement('div');
      row2.appendChild(makeField('Modify_seq', 'Modify_seq', r.Modify_seq, false));
      rowDiv.appendChild(row2);

      // Row 3: delivery5, delivery3 (editable)
      var row3 = document.createElement('div');
      row3.className = 'ds-form-2col';
      row3.appendChild(makeField('delivery5', 'delivery5', r.delivery5, false));
      row3.appendChild(makeField('delivery3', 'delivery3', r.delivery3, false));
      rowDiv.appendChild(row3);

      // Row 4: Strand_MWs, Parents, Remark (editable)
      var row4 = document.createElement('div');
      row4.className = 'ds-form-3col';
      row4.appendChild(makeField('Strand_MWs', 'Strand_MWs', r.Strand_MWs, false));
      row4.appendChild(makeField('Parents',    'Parents',    r.Parents,    false));
      row4.appendChild(makeField('Remark',     'Remark',     r.Remark,     false));
      rowDiv.appendChild(row4);

      $('#cloneRowsContainer').append(rowDiv);
  });
  ```

  The complete updated file should look like this (replace the entire file):

  ```javascript
  // clone_delivery.js - delegated handler for Clone Sequence modal
  $(document).ready(function() {
      function getCsrf() {
          return $("input[name=csrfmiddlewaretoken]").first().val();
      }

      // open modal and load deliveries (works for any page where .clone-seq-btn exists)
      $('body').on('click', '.clone-seq-btn', function(e) {
          e.preventDefault();
          var strand = $(this).data('strand-id');
          if (!strand) { alert('Strand ID not available'); return; }
          $('#cloneStrandId').text(strand);
          $('#modal_strand_id').val(strand);
          $('#cloneRowsContainer').empty();
          $.get('/clone_delivery/', { strand_id: strand }, function(resp) {
              if (resp.error) { alert(resp.error); return; }
              var rows = resp.deliveries;
              rows.forEach(function(r, idx) {
                  var rowDiv = document.createElement('div');
                  rowDiv.className = 'ds-clone-row';

                  // Heading
                  var h6 = document.createElement('h6');
                  var seqType = (r.Seq_type || '').toString().toUpperCase();
                  if (seqType === 'AS' || seqType === 'SS') {
                      h6.style.fontSize = '1.25rem';
                      h6.style.fontWeight = '600';
                  }
                  h6.textContent = 'Record ' + (idx + 1) + ' - ' + (r.Seq_type || '');
                  rowDiv.appendChild(h6);

                  // Helper: create a labeled input cell
                  function makeField(labelText, name, value, readOnly) {
                      var wrapper = document.createElement('div');
                      var lbl = document.createElement('label');
                      lbl.className = 'ds-form-label';
                      lbl.textContent = labelText;
                      var inp = document.createElement('input');
                      inp.name = name;
                      inp.className = 'ds-form-control';
                      inp.value = value || '';
                      if (readOnly) inp.readOnly = true;
                      wrapper.appendChild(lbl);
                      wrapper.appendChild(inp);
                      return wrapper;
                  }

                  // Row 1: Project, Target, Seq_type (readonly)
                  var row1 = document.createElement('div');
                  row1.className = 'ds-form-3col';
                  row1.appendChild(makeField('Project',  'Project',  r.Project,  true));
                  row1.appendChild(makeField('Target',   'Target',   r.Target,   true));
                  row1.appendChild(makeField('Seq_type', 'Seq_type', r.Seq_type, true));
                  rowDiv.appendChild(row1);

                  // Row 2: Modify_seq (full width, editable)
                  var row2 = document.createElement('div');
                  row2.appendChild(makeField('Modify_seq', 'Modify_seq', r.Modify_seq, false));
                  rowDiv.appendChild(row2);

                  // Row 3: delivery5, delivery3 (editable)
                  var row3 = document.createElement('div');
                  row3.className = 'ds-form-2col';
                  row3.appendChild(makeField('delivery5', 'delivery5', r.delivery5, false));
                  row3.appendChild(makeField('delivery3', 'delivery3', r.delivery3, false));
                  rowDiv.appendChild(row3);

                  // Row 4: Strand_MWs, Parents, Remark (editable)
                  var row4 = document.createElement('div');
                  row4.className = 'ds-form-3col';
                  row4.appendChild(makeField('Strand_MWs', 'Strand_MWs', r.Strand_MWs, false));
                  row4.appendChild(makeField('Parents',    'Parents',    r.Parents,    false));
                  row4.appendChild(makeField('Remark',     'Remark',     r.Remark,     false));
                  rowDiv.appendChild(row4);

                  $('#cloneRowsContainer').append(rowDiv);
              });
              // ensure divider sits between Record 1 and Record 2 (insert after first record)
              if (rows.length > 1) {
                  $('#cloneRowsContainer .ds-clone-row').first().after('<div class="ds-clone-divider" aria-hidden="true"></div>');
              }
              $('#cloneModal').modal('show');
          }).fail(function(xhr) {
              alert('加载失败: ' + xhr.responseText);
          });
      });

      // submit cloned data
      $('body').on('click', '#confirmCloneBtn', function() {
          var deliveries = [];
          $('#cloneRowsContainer .ds-clone-row').each(function() {
              var $row = $(this);
              var obj = {};
              $row.find('input').each(function() {
                  var name = $(this).attr('name');
                  obj[name] = $(this).val();
              });
              deliveries.push(obj);
          });

          if (deliveries.length === 0) { alert('无可克隆的记录'); return; }

          var payload = { deliveries: deliveries };

          $.ajax({
              url: '/clone_delivery/',
              method: 'POST',
              headers: { 'X-CSRFToken': getCsrf() },
              contentType: 'application/json',
              data: JSON.stringify(payload),
              success: function(resp) {
                  if (resp.success) {
                      alert('克隆成功: ' + resp.duplex_id);
                      location.reload();
                  } else if (resp.error) {
                      var msg = resp.error || '发生错误';
                      if (resp.detail && Array.isArray(resp.detail)) {
                          msg += '\n\n详情:';
                          resp.detail.forEach(function(d) { msg += '\n - ' + d; });
                      } else if (resp.detail) {
                          msg += '\n' + resp.detail;
                      }
                      alert(msg);
                  }
              },
              error: function(xhr) {
                  var txt = xhr.responseJSON && xhr.responseJSON.error ? xhr.responseJSON.error : xhr.responseText;
                  alert('提交失败: ' + txt);
              }
          });
      });
  });
  ```

- [ ] **Step 3: Verify the fix manually**

  Repeat the browser test from Step 1 (create the XSS delivery, open the clone modal). The `<img>` tag must NOT fire. The field value should appear as literal text inside the input, not interpreted as HTML. Check the DOM inspector — `<input value="">` should show the raw payload string, not parsed HTML.

- [ ] **Step 4: Commit**

  ```bash
  git add static/js/clone_delivery.js
  git commit -m "fix: replace innerHTML string-concat with DOM API in clone modal (XSS)"
  ```

---

## Task 2: Fix Permission Bypass in `cor_seq`

**Files:**
- Modify: `app01/views.py:3208`
- Modify: `app01/tests.py` (append new class at end)

- [ ] **Step 1: Write the failing test**

  Open `app01/tests.py` and append this class at the very end of the file:

  ```python
  class CorSeqPermissionTests(TestCase):
      """cor_seq must not return deliveries outside the user's permitted projects."""

      def setUp(self):
          # A user with NO project permissions
          self.user = LmsUser.objects.create_user(
              username='noperm_user', password='p',
              user_type='sub_admin',
              permissions_project='',
          )
          self.client.force_login(self.user)

          # A sequence + delivery in project 'PRJ-SECRET'
          self.seq = Sequence.objects.create(seq='AACCGGUU', seq_type='AS')
          self.delivery = Delivery.objects.create(
              sequence=self.seq,
              seq_type='AS',
              duplex_id='BP_PERM_TEST',
              project='PRJ-SECRET',
          )
          DeliveryProject.objects.create(
              delivery=self.delivery,
              project_code='PRJ-SECRET',
          )

      def test_unpermitted_user_gets_404(self):
          """A user with no project permissions must receive 404, not the delivery page."""
          url = f'/cor_seq/?id={self.delivery.id}&seq_type=AS'
          r = self.client.get(url)
          self.assertEqual(r.status_code, 404)

      def test_permitted_user_gets_200(self):
          """A user with the correct project permission must reach the page."""
          self.user.permissions_project = 'PRJ-SECRET'
          self.user.save()
          url = f'/cor_seq/?id={self.delivery.id}&seq_type=AS'
          r = self.client.get(url)
          self.assertEqual(r.status_code, 200)
  ```

  You also need to add `DeliveryProject` to the import at the top of `app01/tests.py`. The current import line is:

  ```python
  from app01.models import Sequence, SeqModule, DeliveryModule, Delivery, DeliveryProject, LmsUser
  ```

  `DeliveryProject` is already imported — no change needed.

- [ ] **Step 2: Run the new tests to confirm they fail**

  ```bash
  source venv/bin/activate
  python manage.py test app01.tests.CorSeqPermissionTests -v 2
  ```

  Expected: `test_unpermitted_user_gets_404` FAILS (status 200 instead of 404).
  `test_permitted_user_gets_200` may pass or fail depending on how the view renders — either is acceptable at this stage.

- [ ] **Step 3: Apply the one-line fix in `app01/views.py`**

  Find line 3208 (inside `cor_seq`):

  ```python
  delivery = get_object_or_404(Delivery, Q(id=query_id_tmp)&Q(seq_type=seq_type))  # 根据 query_id 获取 Delivery 对象
  ```

  Replace with:

  ```python
  delivery = get_object_or_404(base_delivery_qs, Q(id=query_id_tmp)&Q(seq_type=seq_type))  # 根据 query_id 获取 Delivery 对象
  ```

  `base_delivery_qs` is already computed two lines above (line 3204):
  ```python
  base_delivery_qs = get_permitted_delivery_qs(request.user)
  ```
  No other change is needed.

- [ ] **Step 4: Run the tests again to confirm they pass**

  ```bash
  python manage.py test app01.tests.CorSeqPermissionTests -v 2
  ```

  Expected: both tests PASS.

- [ ] **Step 5: Run full test suite to confirm no regressions**

  ```bash
  python manage.py test app01
  ```

  Expected: same 4 errors + 1 failure as the baseline. No new failures.

- [ ] **Step 6: Commit**

  ```bash
  git add app01/views.py app01/tests.py
  git commit -m "fix: apply project permission filter in cor_seq to prevent cross-project access"
  ```

---

## Task 3: Env-Var–Managed DEBUG and ALLOWED_HOSTS

**Files:**
- Modify: `bms/settings.py:26-28`
- Modify: `.env.example`

> **Note:** Django settings are loaded once at startup — there is no useful automated test for this change. Verification is manual (start the dev server and confirm behavior). `python-decouple` is already installed (v3.8) and already used for `SECRET_KEY` in this file.

- [ ] **Step 1: Update `bms/settings.py`**

  Find lines 26–28:

  ```python
  # SECURITY WARNING: don't run with debug turned on in production!
  DEBUG = True

  ALLOWED_HOSTS = ['*']  # 允许所有主机访问，实际使用中请修改为具体的域名或 IP 地址
  ```

  Replace with:

  ```python
  # SECURITY WARNING: don't run with debug turned on in production!
  DEBUG = config('DEBUG', default=False, cast=bool)

  ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='127.0.0.1,localhost', cast=Csv())
  ```

  At the top of `settings.py`, `config` is already imported on line 14:
  ```python
  from decouple import config
  ```

  Change that import to also bring in `Csv`:
  ```python
  from decouple import config, Csv
  ```

- [ ] **Step 2: Update `.env.example`**

  Current content of `.env.example`:
  ```
  # SeqDB 环境配置示例 — 复制为 .env 并填入真实值
  SECRET_KEY=your-django-secret-key-here
  DB_PASSWORD=your-mysql-password-here
  ```

  Replace with:
  ```
  # SeqDB 环境配置示例 — 复制为 .env 并填入真实值

  # Django secret key (required)
  SECRET_KEY=your-django-secret-key-here

  # Database password (required)
  DB_PASSWORD=your-mysql-password-here

  # Set DEBUG=True for local development; leave False (or omit) in production
  DEBUG=True

  # Comma-separated list of allowed hostnames; use * only for local dev
  ALLOWED_HOSTS=127.0.0.1,localhost
  ```

- [ ] **Step 3: Verify your local `.env` file has the two new variables**

  Check whether a `.env` file exists in the project root:
  ```bash
  ls -la .env
  ```

  If it exists, add `DEBUG=True` and `ALLOWED_HOSTS=127.0.0.1,localhost` to it.
  If it does not exist, create it:
  ```bash
  cp .env.example .env
  ```
  Then edit `.env` to set your real `SECRET_KEY` and `DB_PASSWORD`.

- [ ] **Step 4: Verify the server starts**

  ```bash
  source venv/bin/activate
  python manage.py check
  ```

  Expected: `System check identified no issues (0 silenced).`

  Then start the dev server briefly:
  ```bash
  python manage.py runserver 8000
  ```

  Visit `http://127.0.0.1:8000/` — the page must load normally. Ctrl+C to stop.

- [ ] **Step 5: Commit**

  ```bash
  git add bms/settings.py .env.example
  git commit -m "fix: read DEBUG and ALLOWED_HOSTS from environment via python-decouple"
  ```

---

## Task 4: Fix `Sequence.created_at` — `auto_now_add`

**Files:**
- Modify: `app01/models.py:27`
- Create: `app01/migrations/0036_sequence_created_at_auto_now_add.py` (generated)
- Modify: `app01/tests.py` (append new class at end)

- [ ] **Step 1: Write the failing test**

  Append this class at the very end of `app01/tests.py`:

  ```python
  class SequenceCreatedAtTests(TestCase):
      """Sequence.created_at must auto-populate on creation."""

      def test_created_at_auto_populated(self):
          """New Sequence must have a non-null created_at after save."""
          seq = Sequence.objects.create(seq='AUGUAGU', seq_type='SS')
          seq.refresh_from_db()
          self.assertIsNotNone(seq.created_at,
                               "created_at should be set automatically on creation")

      def test_created_at_not_changed_on_update(self):
          """created_at must not change when the row is updated (auto_now_add, not auto_now)."""
          seq = Sequence.objects.create(seq='CCUUAAGG', seq_type='AS')
          seq.refresh_from_db()
          original_ts = seq.created_at
          seq.seq = 'CCUUAAGG'  # no-op update
          seq.save(update_fields=['seq'])
          seq.refresh_from_db()
          self.assertEqual(seq.created_at, original_ts,
                           "created_at must not change on update")
  ```

- [ ] **Step 2: Run the new tests to confirm they fail**

  ```bash
  source venv/bin/activate
  python manage.py test app01.tests.SequenceCreatedAtTests -v 2
  ```

  Expected: `test_created_at_auto_populated` FAILS (`created_at` is `None`).

- [ ] **Step 3: Update `app01/models.py` line 27**

  Find:
  ```python
  created_at = models.DateTimeField('Created At',  blank=True, null=True)  # 创建时间
  ```

  Replace with:
  ```python
  created_at = models.DateTimeField('Created At', auto_now_add=True, null=True)  # 创建时间
  ```

  `null=True` is kept so existing rows with `NULL` values are not rejected by the DB constraint.

- [ ] **Step 4: Generate and apply the migration**

  ```bash
  python manage.py makemigrations app01 --name sequence_created_at_auto_now_add
  ```

  Expected output: `Migrations for 'app01': app01/migrations/0036_sequence_created_at_auto_now_add.py`

  Then apply it:
  ```bash
  python manage.py migrate
  ```

  Expected: `Applying app01.0036_sequence_created_at_auto_now_add... OK`

- [ ] **Step 5: Run the tests to confirm they pass**

  ```bash
  python manage.py test app01.tests.SequenceCreatedAtTests -v 2
  ```

  Expected: both tests PASS.

- [ ] **Step 6: Run full test suite**

  ```bash
  python manage.py test app01
  ```

  Expected: same 4 errors + 1 failure as baseline. No new failures.

- [ ] **Step 7: Commit**

  ```bash
  git add app01/models.py app01/migrations/0036_sequence_created_at_auto_now_add.py app01/tests.py
  git commit -m "fix: Sequence.created_at auto_now_add=True to prevent NULL timestamps"
  ```

---

## Task 5: Session Data Validation in `confirm_upload_preflight`

**Files:**
- Modify: `app01/views.py` (`confirm_upload_preflight`, POST branch)
- Modify: `app01/tests.py` (append new class at end)

- [ ] **Step 1: Write the failing tests**

  Append this class at the very end of `app01/tests.py`:

  ```python
  class PreflightSessionGuardTests(TestCase):
      """confirm_upload_preflight must redirect gracefully when session data is missing."""

      def setUp(self):
          self.user = LmsUser.objects.create_user(
              username='preflight_user', password='p',
              user_type='sub_admin',
              permissions_project='PRJ-X',
          )
          self.client.force_login(self.user)

      def test_get_with_empty_session_redirects(self):
          """GET with no preflight_result in session → redirect to seq_delivery."""
          r = self.client.get('/confirm_upload_preflight/')
          self.assertRedirects(r, '/seq_delivery/', fetch_redirect_response=False)

      def test_post_with_empty_session_redirects_with_error(self):
          """POST with no session data → redirect to seq_delivery, not a 500."""
          r = self.client.post('/confirm_upload_preflight/', {})
          # Must not crash — expect redirect
          self.assertIn(r.status_code, [302, 200],
                        "Empty session POST must not return 500")
          if r.status_code == 302:
              self.assertIn('/seq_delivery/', r['Location'])

      def test_post_with_corrupted_preflight_redirects(self):
          """POST with preflight_result set to a non-dict → redirect with error, not 500."""
          session = self.client.session
          session['preflight_result'] = 'corrupted_string'
          session['preflight_df_json'] = 'not valid json'
          session['preflight_clean_groups'] = None
          session.save()

          r = self.client.post('/confirm_upload_preflight/', {})
          self.assertIn(r.status_code, [302, 200],
                        "Corrupted session must not return 500")
  ```

- [ ] **Step 2: Run the new tests to confirm their current state**

  ```bash
  source venv/bin/activate
  python manage.py test app01.tests.PreflightSessionGuardTests -v 2
  ```

  `test_get_with_empty_session_redirects` should already pass (the GET guard exists).
  `test_post_with_empty_session_redirects_with_error` should pass (caught by `if not df_json`).
  `test_post_with_corrupted_preflight_redirects` may fail with a 500 because `preflight_result` is a string and `json.JSONDecodeError` or similar is thrown by `pd.read_json('not valid json')`.

  Run the tests and note which ones fail before the fix.

- [ ] **Step 3: Add type guard for `preflight_result` in the POST branch**

  Find `confirm_upload_preflight` in `app01/views.py`. In the POST `try:` block, locate lines 2375–2381:

  ```python
  preflight = request.session.get('preflight_result', {})
  df_json = request.session.get('preflight_df_json', None)
  clean_groups_json = request.session.get('preflight_clean_groups', None)

  if not df_json or clean_groups_json is None:
      messages.error(request, "会话已过期，请重新上传文件")
      return redirect('seq_delivery')
  ```

  Replace with:

  ```python
  preflight = request.session.get('preflight_result', {})
  df_json = request.session.get('preflight_df_json', None)
  clean_groups_json = request.session.get('preflight_clean_groups', None)

  if not isinstance(preflight, dict):
      messages.error(request, "会话数据已损坏，请重新上传文件")
      return redirect('seq_delivery')

  if not df_json or not clean_groups_json:
      messages.error(request, "会话已过期，请重新上传文件")
      return redirect('seq_delivery')
  ```

  Two changes:
  1. Added `isinstance(preflight, dict)` guard — catches session-corruption where `preflight_result` is not the expected dict.
  2. Changed `clean_groups_json is None` → `not clean_groups_json` — also catches empty string `''`.

- [ ] **Step 4: Run the tests to confirm they pass**

  ```bash
  python manage.py test app01.tests.PreflightSessionGuardTests -v 2
  ```

  Expected: all 3 tests PASS.

- [ ] **Step 5: Run full test suite**

  ```bash
  python manage.py test app01
  ```

  Expected: same 4 errors + 1 failure as baseline. No new failures.

- [ ] **Step 6: Commit**

  ```bash
  git add app01/views.py app01/tests.py
  git commit -m "fix: add session type guard in confirm_upload_preflight POST to prevent 500 on corruption"
  ```

---

## Completion Checklist

After all 5 tasks:

- [ ] `python manage.py test app01` shows exactly the same pre-existing failures (4 errors + 1 failure), nothing new
- [ ] `python manage.py check` shows 0 issues
- [ ] Clone modal tested manually in browser — no XSS fires
- [ ] Dev server starts with `.env` providing `DEBUG=True`
- [ ] All 5 commits present in `git log --oneline -5`
