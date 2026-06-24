# Smart Upload Consolidation & UX Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove five legacy upload views (keeping only `smart_upload`), and add an inline compound-ID correction table to the confirm page.

**Architecture:** Three cleanup tasks remove dead code and routes, then two feature tasks add `unique_compound_ids` to the preview dict and render the correction table, and a final task wires the user remaps into the confirm view at all four `Compound.get_or_create` call sites.

**Tech Stack:** Django 5.1, function-based views (`app01/views.py`), Django templates (`templates/smart_upload.html`), `app01/tests.py` (Django `TestCase`).

---

### Task 1: Replace legacy upload URLs with permanent redirects

**Files:**
- Modify: `bprdb/urls.py`

- [ ] **Step 1: Update `bprdb/urls.py`**

Replace the five legacy route lines (lines 11–13, 19–20) and their import dependencies. The full file becomes:

```python
from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView
from app01 import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('upload/', RedirectView.as_view(url='/upload/smart/', permanent=True), name='upload'),
    path('upload/confirm/', RedirectView.as_view(url='/upload/smart/', permanent=True), name='upload_confirm'),
    path('upload/success/', RedirectView.as_view(url='/upload/smart/', permanent=True), name='upload_success'),
    path('compounds/', views.compound_list, name='compound_list'),
    path('compounds/<str:compound_id>/', views.compound_detail, name='compound_detail'),
    path('profile/', views.user_profile, name='user_profile'),
    path('batches/', views.batch_list, name='batch_list'),
    path('batches/<str:batch_label>/delete/', views.batch_delete, name='batch_delete'),
    path('upload/invivo/', RedirectView.as_view(url='/upload/smart/', permanent=True), name='invivo_upload'),
    path('upload/invivo/confirm/', RedirectView.as_view(url='/upload/smart/', permanent=True), name='invivo_upload_confirm'),
    path('upload/smart/', views.smart_upload_view, name='smart_upload'),
    path('upload/smart/confirm/', views.smart_upload_confirm_view, name='smart_upload_confirm'),
    path('attachments/<int:pk>/download/', views.attachment_download, name='attachment_download'),
    path('attachments/<int:pk>/preview/', views.attachment_preview, name='attachment_preview'),
]
```

- [ ] **Step 2: Verify server starts and redirects work**

```bash
source venv/bin/activate && python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 3: Commit**

```bash
git add bprdb/urls.py
git commit -m "feat: redirect legacy upload URLs to /upload/smart/"
```

---

### Task 2: Delete legacy upload view functions from `views.py`

**Files:**
- Modify: `app01/views.py`

The five functions to delete and their approximate line ranges (verify with `grep -n "^def "` before editing):

| Function | Starts at |
|---|---|
| `upload_view` | 555 |
| `upload_confirm_view` | 629 |
| `upload_success_view` | 765 |
| `invivo_upload_view` | 1692 |
| `invivo_upload_confirm_view` | 1773 |

The next kept function after the second group is `_build_smart_preview` at line 1929.

- [ ] **Step 1: Find exact boundaries**

```bash
grep -n "^def " app01/views.py | head -40
```

Note the line number where each function starts and where the next function starts — that is the end of the previous function.

- [ ] **Step 2: Delete `upload_view`, `upload_confirm_view`, `upload_success_view`**

Delete from line 555 (start of `upload_view`) up to but not including the line where the next non-upload function begins. Check what is between `upload_success_view` and `invivo_upload_view` (lines 765–1691) — if there are helper functions that are only referenced by the deleted views, delete those too. If a helper is referenced by other views, keep it.

To check references:
```bash
# Example for a helper found in that range named e.g. _old_helper:
grep -n "_old_helper" app01/views.py
```

- [ ] **Step 3: Delete `invivo_upload_view` and `invivo_upload_confirm_view`**

Delete from the start of `invivo_upload_view` up to but not including line 1929 (`_build_smart_preview`).

- [ ] **Step 4: Verify no broken references**

```bash
source venv/bin/activate && python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 5: Run existing tests to confirm no regressions**

```bash
source venv/bin/activate && python manage.py test app01 -v 2
```

Expected: all existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add app01/views.py
git commit -m "feat: delete legacy upload_view, upload_confirm_view, upload_success_view, invivo_upload_view, invivo_upload_confirm_view"
```

---

### Task 3: Delete legacy upload templates

**Files:**
- Delete: `templates/upload.html`
- Delete: `templates/invivo_upload.html`
- Delete: `templates/upload_success.html`
- Delete: `templates/confirm_upload_preflight.html`

- [ ] **Step 1: Check no remaining references to deleted templates**

```bash
grep -rn "upload\.html\|invivo_upload\.html\|upload_success\.html\|confirm_upload_preflight\.html" app01/ bprdb/ templates/
```

Expected: zero results (after Task 2, no view renders these).

- [ ] **Step 2: Delete the files**

```bash
rm templates/upload.html templates/invivo_upload.html templates/upload_success.html templates/confirm_upload_preflight.html
```

- [ ] **Step 3: Verify server still starts**

```bash
source venv/bin/activate && python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: delete legacy upload templates (upload, invivo_upload, upload_success, confirm_upload_preflight)"
```

---

### Task 4: Add `unique_compound_ids` to the smart preview dict

**Files:**
- Modify: `app01/views.py` (`_build_smart_preview`, around line 1929 — renumbered after Task 2 deletes)
- Test: `app01/tests.py`

The preview dict needs a deduplicated list of all compound IDs so the template can render the correction table without template-side logic.

- [ ] **Step 1: Write the failing test**

Add to `app01/tests.py` after the existing test classes:

```python
class SmartPreviewUniqueCompoundIdsTest(TestCase):
    def _make_preview(self, vitro_cids=None, invivo_cids=None):
        """Build a minimal _build_smart_preview return dict for testing."""
        invitro = None
        if vitro_cids is not None:
            invitro = {
                'experiments': [{'compound_id': c} for c in vitro_cids],
                'strand_map': {},
                'new_compounds': [],
                'id_format_mismatch': {},
                'assay_name': '',
                'exp_date': None,
            }
        invivo_groups = []
        if invivo_cids is not None:
            invivo_groups = [{'groups': [{'compound_id': c} for c in invivo_cids]}]
        return invitro, invivo_groups

    def test_vitro_only_deduplication(self):
        invitro, invivo_groups = self._make_preview(
            vitro_cids=['BPR3M03-FN01', 'BPR3M03-FN02', 'BPR3M03-FN01', 'Saline']
        )
        from app01.views import _collect_unique_compound_ids
        result = _collect_unique_compound_ids(invitro, invivo_groups)
        self.assertEqual(result, ['BPR3M03-FN01', 'BPR3M03-FN02', 'Saline'])

    def test_invivo_only(self):
        invitro, invivo_groups = self._make_preview(
            invivo_cids=['BPR350-025087', 'Saline']
        )
        from app01.views import _collect_unique_compound_ids
        result = _collect_unique_compound_ids(invitro, invivo_groups)
        self.assertEqual(result, ['BPR350-025087', 'Saline'])

    def test_both_vitro_and_invivo_no_overlap(self):
        invitro, invivo_groups = self._make_preview(
            vitro_cids=['BPR3M03-FN01'],
            invivo_cids=['BPR350-025087'],
        )
        from app01.views import _collect_unique_compound_ids
        result = _collect_unique_compound_ids(invitro, invivo_groups)
        self.assertEqual(result, ['BPR3M03-FN01', 'BPR350-025087'])

    def test_overlap_between_vitro_and_invivo(self):
        invitro, invivo_groups = self._make_preview(
            vitro_cids=['BPR3M03-FN01', 'Saline'],
            invivo_cids=['Saline', 'BPR350-025087'],
        )
        from app01.views import _collect_unique_compound_ids
        result = _collect_unique_compound_ids(invitro, invivo_groups)
        self.assertEqual(result, ['BPR3M03-FN01', 'Saline', 'BPR350-025087'])

    def test_no_experiments(self):
        from app01.views import _collect_unique_compound_ids
        result = _collect_unique_compound_ids(None, [])
        self.assertEqual(result, [])
```

- [ ] **Step 2: Run to verify it fails**

```bash
source venv/bin/activate && python manage.py test app01.tests.SmartPreviewUniqueCompoundIdsTest -v 2
```

Expected: `ImportError: cannot import name '_collect_unique_compound_ids'`

- [ ] **Step 3: Add `_collect_unique_compound_ids` to `app01/views.py`**

Add this function immediately before `_build_smart_preview`:

```python
def _collect_unique_compound_ids(invitro, invivo_groups):
    """Return ordered list of unique compound IDs across invitro experiments and invivo groups."""
    seen = set()
    result = []
    for exp in (invitro.get('experiments', []) if invitro else []):
        cid = exp['compound_id']
        if cid not in seen:
            seen.add(cid)
            result.append(cid)
    for group in invivo_groups:
        for g in group.get('groups', []):
            cid = g['compound_id']
            if cid not in seen:
                seen.add(cid)
                result.append(cid)
    return result
```

- [ ] **Step 4: Add `unique_compound_ids` to `_build_smart_preview` return dict**

In `_build_smart_preview`, find the `return {` statement at the end of the function and add the new key:

```python
    return {
        'project_code': project_code,
        'file_detections': file_detections,
        'invitro': invitro,
        'invivo_groups': invivo_groups,
        'source_files': source_files,
        'errors': errors,
        'has_no_seq': has_no_seq,
        'is_source_only': is_source_only,
        'unique_compound_ids': _collect_unique_compound_ids(invitro, invivo_groups),
    }
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
source venv/bin/activate && python manage.py test app01.tests.SmartPreviewUniqueCompoundIdsTest -v 2
```

Expected: `5 tests, 0 failures`

- [ ] **Step 6: Run full test suite**

```bash
source venv/bin/activate && python manage.py test app01 -v 2
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "feat: add _collect_unique_compound_ids and unique_compound_ids to smart preview dict"
```

---

### Task 5: Add compound ID correction table to the confirm template

**Files:**
- Modify: `templates/smart_upload.html`

The correction table appears between the batch metadata block and the invitro/invivo data sections, but only when there are compound IDs to correct (`preview.unique_compound_ids` is non-empty).

- [ ] **Step 1: Add the correction table HTML and JS**

In `templates/smart_upload.html`, find the existing batch metadata block:

```html
    {% if preview.invitro.experiments or preview.invivo_groups %}
    <div style="border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;margin-bottom:16px;background:#f8fafc;">
```

Insert the following block **after** that entire `{% if preview.invitro.experiments or preview.invivo_groups %}...{% endif %}` block (i.e., after the closing `</div>` at line 195, before `{% elif preview.invitro.strand_map %}`):

```html
    {% if preview.unique_compound_ids %}
    <div id="cid-correction-card" style="border:1px solid #e2e8f0;border-radius:8px;margin-bottom:16px;overflow:hidden;">
      <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 16px;background:#f8fafc;cursor:pointer;"
           onclick="toggleCidCard()">
        <span style="font-size:13px;font-weight:600;color:#1e293b;">化合物 ID 确认</span>
        <span id="cid-badge" style="display:none;font-size:11px;background:#f59e0b;color:#fff;border-radius:10px;padding:2px 8px;"></span>
        <span id="cid-chevron" style="font-size:11px;color:#94a3b8;">▼ 展开</span>
      </div>
      <div id="cid-correction-body" style="display:none;padding:12px 16px;">
        <div style="font-size:11px;color:#64748b;margin-bottom:10px;">如识别有误，可在此修正化合物 ID，仅影响本次上传。</div>
        <table style="width:100%;border-collapse:collapse;font-size:12px;">
          <thead>
            <tr style="color:#94a3b8;">
              <th style="text-align:left;padding:4px 8px;font-weight:500;">解析到的 ID</th>
              <th style="text-align:left;padding:4px 8px;font-weight:500;width:16px;">→</th>
              <th style="text-align:left;padding:4px 8px;font-weight:500;">确认/修正为</th>
            </tr>
          </thead>
          <tbody>
            {% for cid in preview.unique_compound_ids %}
            <tr>
              <td style="padding:4px 8px;color:#475569;">{{ cid }}</td>
              <td style="padding:4px 8px;color:#94a3b8;">→</td>
              <td style="padding:4px 8px;">
                <input type="hidden" name="cid_orig_{{ forloop.counter0 }}" value="{{ cid }}">
                <input type="text" name="cid_new_{{ forloop.counter0 }}"
                       value="{{ cid }}"
                       class="ds-form-control cid-new-input"
                       data-orig="{{ cid }}"
                       style="width:200px;font-size:12px;">
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
    {% endif %}
```

- [ ] **Step 2: Add the JS for the badge and toggle**

In the `<script>` block of `smart_upload.html` (before the closing `</script>`), add:

```javascript
    function toggleCidCard() {
      var body = document.getElementById('cid-correction-body');
      var chevron = document.getElementById('cid-chevron');
      if (body.style.display === 'none') {
        body.style.display = 'block';
        chevron.textContent = '▲ 收起';
      } else {
        body.style.display = 'none';
        chevron.textContent = '▼ 展开';
      }
    }

    function updateCidBadge() {
      var inputs = document.querySelectorAll('.cid-new-input');
      var changed = 0;
      inputs.forEach(function(inp) {
        if (inp.value.trim() !== inp.dataset.orig) changed++;
      });
      var badge = document.getElementById('cid-badge');
      if (!badge) return;
      if (changed > 0) {
        badge.textContent = '已修正 ' + changed + ' 个';
        badge.style.display = 'inline';
      } else {
        badge.style.display = 'none';
      }
    }

    document.addEventListener('DOMContentLoaded', function() {
      document.querySelectorAll('.cid-new-input').forEach(function(inp) {
        inp.addEventListener('input', updateCidBadge);
      });
    });
```

- [ ] **Step 3: Manual smoke test**

```bash
source venv/bin/activate && python manage.py runserver
```

Navigate to `/upload/smart/`, upload a vitro summary CSV, select file type, click "重新解析". Verify:
1. The "化合物 ID 确认" card appears below the batch metadata block
2. Clicking the header expands/collapses the table
3. Editing an ID in the table shows the "已修正 N 个" badge

- [ ] **Step 4: Commit**

```bash
git add templates/smart_upload.html
git commit -m "feat: add compound ID correction table to smart upload confirm page"
```

---

### Task 6: Apply user compound ID remaps in the confirm view

**Files:**
- Modify: `app01/views.py` (`smart_upload_confirm_view` and a new helper `_build_user_cid_remap`)
- Test: `app01/tests.py`

- [ ] **Step 1: Write the failing test**

Add to `app01/tests.py`:

```python
class BuildUserCidRemapTest(TestCase):
    def test_basic_remap(self):
        from app01.views import _build_user_cid_remap
        post = {
            'cid_orig_0': 'BPR_3M03FN01',
            'cid_new_0': 'BPR3M03-FN01',
            'cid_orig_1': 'Saline',
            'cid_new_1': 'Saline',
        }
        remap, errors = _build_user_cid_remap(post)
        self.assertEqual(remap, {'BPR_3M03FN01': 'BPR3M03-FN01'})
        self.assertEqual(errors, [])

    def test_unchanged_ids_excluded(self):
        from app01.views import _build_user_cid_remap
        post = {
            'cid_orig_0': 'BPR3M03-FN01',
            'cid_new_0': 'BPR3M03-FN01',
        }
        remap, errors = _build_user_cid_remap(post)
        self.assertEqual(remap, {})
        self.assertEqual(errors, [])

    def test_empty_new_id_returns_error(self):
        from app01.views import _build_user_cid_remap
        post = {
            'cid_orig_0': 'BPR3M03-FN01',
            'cid_new_0': '   ',
        }
        remap, errors = _build_user_cid_remap(post)
        self.assertEqual(remap, {})
        self.assertIn('化合物 ID 不能为空', errors[0])

    def test_no_remap_keys_returns_empty(self):
        from app01.views import _build_user_cid_remap
        post = {'batch_label': '2026-001', 'assay_name': 'KD'}
        remap, errors = _build_user_cid_remap(post)
        self.assertEqual(remap, {})
        self.assertEqual(errors, [])

    def test_multiple_remaps(self):
        from app01.views import _build_user_cid_remap
        post = {
            'cid_orig_0': 'old-A',
            'cid_new_0': 'new-A',
            'cid_orig_1': 'old-B',
            'cid_new_1': 'new-B',
        }
        remap, errors = _build_user_cid_remap(post)
        self.assertEqual(remap, {'old-A': 'new-A', 'old-B': 'new-B'})
        self.assertEqual(errors, [])
```

- [ ] **Step 2: Run to verify it fails**

```bash
source venv/bin/activate && python manage.py test app01.tests.BuildUserCidRemapTest -v 2
```

Expected: `ImportError: cannot import name '_build_user_cid_remap'`

- [ ] **Step 3: Add `_build_user_cid_remap` to `app01/views.py`**

Add immediately before `smart_upload_confirm_view`:

```python
def _build_user_cid_remap(post_data: dict):
    """Parse cid_orig_N / cid_new_N POST pairs into a remap dict.

    Returns (remap, errors).  remap only contains pairs where new != orig.
    """
    errors = []
    remap = {}
    i = 0
    while f'cid_orig_{i}' in post_data:
        orig = post_data[f'cid_orig_{i}']
        new = post_data.get(f'cid_new_{i}', '').strip()
        if not new:
            errors.append(f'化合物 ID 不能为空（原值：{orig}）')
        elif new != orig:
            remap[orig] = new
        i += 1
    return remap, errors
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source venv/bin/activate && python manage.py test app01.tests.BuildUserCidRemapTest -v 2
```

Expected: `5 tests, 0 failures`

- [ ] **Step 5: Integrate remap into `smart_upload_confirm_view`**

In `smart_upload_confirm_view`, find the POST-reading block (around line 2210 in the original, renumbered after Task 2):

```python
    attach_vitro = request.POST.get('source_exp_vitro') == '1'
    attach_vivo  = request.POST.get('source_exp_vivo')  == '1'

    is_source_only = smart_preview.get('is_source_only', False)

    errors = []
```

Replace with:

```python
    attach_vitro = request.POST.get('source_exp_vitro') == '1'
    attach_vivo  = request.POST.get('source_exp_vivo')  == '1'

    is_source_only = smart_preview.get('is_source_only', False)

    user_cid_remap, remap_errors = _build_user_cid_remap(request.POST)
    errors = list(remap_errors)

    def _resolve_cid(raw: str) -> str:
        remapped = user_cid_remap.get(raw, raw)
        return canonicalize_compound_id(remapped, project_code)
```

- [ ] **Step 6: Replace the four `get_or_create` call sites to use `_resolve_cid`**

**Site 1 — `new_compounds` loop.** Find:
```python
                for c in preview_copy.get('new_compounds', []):
                    compound, _ = Compound.objects.get_or_create(
                        compound_id=canonicalize_compound_id(c['compound_id'], project_code)
                    )
```
Replace with:
```python
                for c in preview_copy.get('new_compounds', []):
                    compound, _ = Compound.objects.get_or_create(
                        compound_id=_resolve_cid(c['compound_id'])
                    )
```

**Site 2 — `strand_map` loop.** Find:
```python
                for cid, seq_data in preview_copy.get('strand_map', {}).items():
                    resolved = id_remap.get(cid, cid)
                    resolved = canonicalize_compound_id(resolved, project_code)
                    compound, _ = Compound.objects.get_or_create(compound_id=resolved)
```
Replace with:
```python
                for cid, seq_data in preview_copy.get('strand_map', {}).items():
                    resolved = id_remap.get(cid, cid)   # cross-format DB remap (unchanged)
                    resolved = _resolve_cid(resolved)
                    compound, _ = Compound.objects.get_or_create(compound_id=resolved)
```

**Site 3 — `experiments` loop.** Find:
```python
                for exp_data in preview_copy.get('experiments', []):
                    cid = canonicalize_compound_id(exp_data['compound_id'], project_code)
                    compound, _ = Compound.objects.get_or_create(compound_id=cid)
```
Replace with:
```python
                for exp_data in preview_copy.get('experiments', []):
                    cid = _resolve_cid(exp_data['compound_id'])
                    compound, _ = Compound.objects.get_or_create(compound_id=cid)
```

**Site 4 — invivo `groups` loop.** Find:
```python
                for g in group['groups']:
                    compound, _ = Compound.objects.get_or_create(
                        compound_id=canonicalize_compound_id(g['compound_id'], project_code)
                    )
```
Replace with:
```python
                for g in group['groups']:
                    compound, _ = Compound.objects.get_or_create(
                        compound_id=_resolve_cid(g['compound_id'])
                    )
```

- [ ] **Step 7: Run full test suite**

```bash
source venv/bin/activate && python manage.py test app01 -v 2
```

Expected: all tests pass.

- [ ] **Step 8: Manual end-to-end test**

```bash
source venv/bin/activate && python manage.py runserver
```

1. Upload a vitro summary CSV, parse it.
2. On the confirm page, expand "化合物 ID 确认", change one ID.
3. Submit. Verify the DB `Compound` record uses the corrected ID.
4. Submit with an empty ID field. Verify the error message "化合物 ID 不能为空" appears.

- [ ] **Step 9: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "feat: apply user compound ID remaps in smart upload confirm view"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| Legacy URLs redirect to `/upload/smart/` | Task 1 |
| `upload_view`, `upload_confirm_view`, `upload_success_view` deleted | Task 2 |
| `invivo_upload_view`, `invivo_upload_confirm_view` deleted | Task 2 |
| Legacy templates deleted | Task 3 |
| `unique_compound_ids` in preview dict | Task 4 |
| Compound ID correction table on confirm page | Task 5 |
| Badge shows count of changed IDs | Task 5 |
| `user_cid_remap` built from POST params | Task 6 |
| Validate no empty new IDs | Task 6 |
| `_resolve_cid` applied at all 4 `get_or_create` sites | Task 6 |
| Cross-format `id_remap` from `detect_cross_format_match` preserved | Task 6 step 6 (Site 2 comment) |
| Two IDs merged to same value → allowed | Implicit in `get_or_create` semantics |
| `exp_date` pre-fill from parsed file | **Not implemented** — `ParsedSummary` has no `exp_date` field; the summary CSV format does not include a date. This spec requirement is vacuous and safely skipped. |

**Placeholder scan:** None found.

**Type consistency:** `_build_user_cid_remap(post_data: dict) -> tuple[dict, list]` used consistently in tests (Task 6 Step 1) and confirm view (Task 6 Step 5). `_resolve_cid` is a closure defined in the confirm view and used in Step 6 — not imported elsewhere.
