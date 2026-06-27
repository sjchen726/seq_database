# Upload Confirm View Bug Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four correctness bugs in `smart_upload_confirm_view`: silent target_name failure after ID normalization, orphaned temp files and session data on validation errors, partial in_vivo data commits, and strand conflict choices silently ignored due to ID mismatch.

**Architecture:** All four fixes are targeted edits inside `app01/views.py`. Fix 2 adds one new helper function (`_cleanup_upload_session`) at module level. No model changes, no migrations, no new files.

**Tech Stack:** Django 5.1, Python 3.10, MySQL. Tests use `django.test.TestCase`.

---

## File Map

| File | Change |
|------|--------|
| `app01/views.py` | Fix 1: resolve `touched_cids` via `_resolve_cid`; Fix 2: add `_cleanup_upload_session` helper + call on error return; Fix 3: wrap all in_vivo groups in outer `transaction.atomic()` + remove old `invivo_errors = []` initializer; Fix 4: apply `_resolve_cid` in strand diff lookup |
| `app01/tests.py` | One new test per fix |

---

## Task 1: Fix target_name silent failure after ID normalization

**Files:**
- Modify: `app01/views.py:2529-2537`
- Modify: `app01/tests.py` (add method to `SmartUploadConfirmTargetNameTest`, around line 1777)

**Context:** `touched_cids` is built from raw IDs in `smart_preview['invitro']['strand_map']`. When `normalize_id_map` remaps `'BPR_3M03FN01'` → `'BPR3M03-FN01'`, the compound is saved under the canonical form, but `touched_cids` still contains the raw form. `filter(compound_id__in=touched_cids)` finds nothing; `target_name` silently stays blank.

- [ ] **Step 1: Write the failing test**

Add this method to `SmartUploadConfirmTargetNameTest` (after `test_empty_target_name_rejected`, around line 1777):

```python
def test_target_name_updated_after_id_normalization(self):
    """Compound saved under canonical ID is updated even when preview stored the raw ID."""
    Compound.objects.create(compound_id='BPR3M03-FN01', target_name='')
    session = self.client.session
    session['smart_preview'] = {
        'project_code': '3M03',
        'file_detections': [],
        'invitro': {
            'experiments': [],
            'strand_map': {'BPR_3M03FN01': {}},  # raw form in preview
            'new_compounds': [],
            'assay_name': '',
            'cell_line': '',
            'notes': '',
        },
        'invivo_groups': [],
        'source_files': [],
        'attachment_files': [],
        'errors': [],
        'has_no_seq': True,
    }
    session['upload_meta'] = {
        'batch_label': '',
        'assay_name': '',
        'exp_date': None,
        'target_name': 'FASN',
        'source_batch': '',
        'attach_vitro': False,
        'attach_vivo': False,
    }
    session['pipeline_result'] = {
        'errors': [], 'warnings': [], 'remap_log': [],
        'strand_diffs': [],
        'dedup_report': {'exp_conflicts': [], 'dp_conflicts': []},
    }
    session['normalize_id_map'] = {'BPR_3M03FN01': 'BPR3M03-FN01'}
    session.save()
    self.client.post('/upload/smart/confirm/', {})
    self.assertEqual(Compound.objects.get(compound_id='BPR3M03-FN01').target_name, 'FASN')
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_bprdb
source venv/bin/activate
python manage.py test app01.tests.SmartUploadConfirmTargetNameTest.test_target_name_updated_after_id_normalization -v 2
```

Expected: FAIL — `AssertionError: '' != 'FASN'` (target_name not updated because raw ID not found).

- [ ] **Step 3: Apply the fix**

In `app01/views.py`, find the block starting at line ~2528. Replace:

```python
    # Update target_name for all compounds touched in this upload (required; validated above)
    if not (invitro_errors or invivo_errors):
        touched_cids = set()
        if invitro:
            for cid in invitro.get('strand_map', {}):
                touched_cids.add(cid)
            for exp_data in invitro.get('experiments', []):
                touched_cids.add(exp_data['compound_id'])
        for group in invivo_groups:
            for g in group['groups']:
                touched_cids.add(g['compound_id'])
        if touched_cids:
            Compound.objects.filter(compound_id__in=touched_cids, target_name='').update(
                target_name=target_name_input
            )
```

With:

```python
    # Update target_name for all compounds touched in this upload (required; validated above)
    if not (invitro_errors or invivo_errors):
        touched_cids = set()
        if invitro:
            for cid in invitro.get('strand_map', {}):
                touched_cids.add(_resolve_cid(cid))
            for exp_data in invitro.get('experiments', []):
                touched_cids.add(_resolve_cid(exp_data['compound_id']))
        for group in invivo_groups:
            for g in group['groups']:
                touched_cids.add(_resolve_cid(g['compound_id']))
        if touched_cids:
            Compound.objects.filter(compound_id__in=touched_cids, target_name='').update(
                target_name=target_name_input
            )
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
python manage.py test app01.tests.SmartUploadConfirmTargetNameTest -v 2
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "fix: resolve compound IDs before target_name update after normalization"
```

---

## Task 2: Clean up session and temp files on validation error

**Files:**
- Modify: `app01/views.py` — insert `_cleanup_upload_session()` before `_build_user_cid_remap` (~line 2064); call it at the top of the `if errors:` block (~line 2187)
- Modify: `app01/tests.py` — add `SmartUploadConfirmCleanupTest` class after `SmartUploadConfirmTargetNameTest`

**Context:** When `if errors:` fires (e.g. blank target_name), the view returns without clearing session keys or deleting temp files. Repeated failed submissions cause session bloat and orphaned files in `_tmp_smart/`. After this fix, users must re-upload to retry after a confirm validation error.

- [ ] **Step 1: Write the failing test**

Add this class to `app01/tests.py` after `SmartUploadConfirmTargetNameTest` (around line 1779):

```python
class SmartUploadConfirmCleanupTest(TestCase):
    def setUp(self):
        self.tmp_media = tempfile.mkdtemp()
        self.user = LmsUser.objects.create_user(
            username='cleanup_test', password='pw',
            user_type='sub_admin', module_permissions='upload,data,compound,batch',
        )
        self.client.force_login(self.user)

    def tearDown(self):
        shutil.rmtree(self.tmp_media, ignore_errors=True)

    def _set_session(self, target_name=''):
        session = self.client.session
        session['smart_preview'] = {
            'project_code': 'TEST',
            'file_detections': [],
            'invitro': None,
            'invivo_groups': [],
            'source_files': [],
            'attachment_files': [],
            'errors': [],
        }
        session['upload_meta'] = {
            'batch_label': '',
            'assay_name': '',
            'exp_date': None,
            'target_name': target_name,
            'source_batch': '',
            'attach_vitro': False,
            'attach_vivo': False,
        }
        session['pipeline_result'] = {
            'errors': [], 'warnings': [], 'remap_log': [],
            'strand_diffs': [],
            'dedup_report': {'exp_conflicts': [], 'dp_conflicts': []},
        }
        session['normalize_id_map'] = {}
        session.save()

    def test_session_cleared_after_validation_error(self):
        """All session upload keys are cleared when confirm validation fails."""
        self._set_session(target_name='')  # blank triggers '靶点必填' error
        with override_settings(MEDIA_ROOT=self.tmp_media):
            resp = self.client.post('/upload/smart/confirm/', {})
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('smart_preview', self.client.session)
        self.assertNotIn('pipeline_result', self.client.session)
        self.assertNotIn('upload_meta', self.client.session)
        self.assertNotIn('normalize_id_map', self.client.session)
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
python manage.py test app01.tests.SmartUploadConfirmCleanupTest.test_session_cleared_after_validation_error -v 2
```

Expected: FAIL — session keys still present after error response.

- [ ] **Step 3: Add the `_cleanup_upload_session` helper to `views.py`**

Insert this function BEFORE `_build_user_cid_remap` (around line 2064, in the blank line between `smart_upload_preview_view` and `_build_user_cid_remap`):

```python
def _cleanup_upload_session(request, smart_preview):
    for det in (smart_preview or {}).get('file_detections', []):
        path = det.get('saved_path', '')
        if path:
            try:
                if default_storage.exists(path):
                    default_storage.delete(path)
            except Exception:
                pass
    request.session.pop('smart_preview', None)
    request.session.pop('pipeline_result', None)
    request.session.pop('upload_meta', None)
    request.session.pop('normalize_id_map', None)
```

- [ ] **Step 4: Call the helper at the error return**

Find the `if errors:` block at line ~2187. Add `_cleanup_upload_session(request, smart_preview)` as the first statement inside it:

```python
    if errors:
        _cleanup_upload_session(request, smart_preview)
        import json as _json
        from app01.models import UploadVocabulary
        qs_err = Experiment.objects.filter(compound__project=project_code) if project_code else Experiment.objects
        # ... rest of block unchanged ...
```

- [ ] **Step 5: Run the test to confirm it passes**

```bash
python manage.py test app01.tests.SmartUploadConfirmCleanupTest -v 2
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "fix: clean up session and temp files on confirm view validation error"
```

---

## Task 3: Wrap all in_vivo groups in a single all-or-nothing transaction

**Files:**
- Modify: `app01/views.py` — two changes: (a) remove `invivo_errors = []` at line ~2217; (b) replace the in_vivo loop block at lines ~2422–2487
- Modify: `app01/tests.py` — add test to `SmartUploadConfirmTest`

**Context:** Currently each in_vivo group has its own `transaction.atomic()`. If group 1 succeeds and group 2 fails, group 1 is permanently committed. Fix: wrap ALL groups in one outer `transaction.atomic()`. The inner `transaction.atomic()` per group becomes a savepoint. On any inner failure: append to `invivo_errors`, then `raise` — the outer block rolls back everything.

- [ ] **Step 1: Write the failing test**

Add this method to `SmartUploadConfirmTest` (after `test_session_cleared_after_confirm`, around line 1566):

```python
def test_invivo_partial_failure_rolls_back_all_groups(self):
    """If one in_vivo group fails, no Experiment rows from any group should persist."""
    group_valid = {
        'compound_id': 'BPR3M03-FN01',
        'dose': '10mpk',
        'schedule': '',
        'timepoints': [{'time': 7, 'mean': 50.0, 'sd': 5.0}],
    }
    group_bad = {
        'compound_id': None,   # None compound_id → DB IntegrityError on get_or_create
        'dose': '10mpk',
        'schedule': '',
        'timepoints': [],
    }
    common_meta = {
        'time_unit': 'day', 'dose_override': '', 'animal_species': 'mouse',
        'animal_strain': 'C57BL/6', 'route': 'SC', 'gender': 'male',
    }
    session = self.client.session
    session['smart_preview'] = {
        'project_code': '3M03',
        'file_detections': [],
        'invitro': None,
        'invivo_groups': [
            {
                'filename': 'group1.csv', 'readout_code': 'knockdown_pct',
                'readout_label': 'KD', 'needs_dose': False, 'saved_path': '',
                'groups': [group_valid],
            },
            {
                'filename': 'group2.csv', 'readout_code': 'knockdown_pct',
                'readout_label': 'KD', 'needs_dose': False, 'saved_path': '',
                'groups': [group_bad],   # this group will fail
            },
        ],
        'source_files': [],
        'attachment_files': [],
        'errors': [],
    }
    session['upload_meta'] = {
        'batch_label': 'ROLLBACK_TEST',
        'assay_name': '',
        'exp_date': None,
        'target_name': 'FASN',
        'source_batch': '',
        'attach_vitro': False,
        'attach_vivo': False,
        'time_unit_0': 'day', 'dose_override_0': '', 'animal_species_0': 'mouse',
        'animal_strain_0': 'C57BL/6', 'route_0': 'SC', 'gender_0': 'male',
        'time_unit_1': 'day', 'dose_override_1': '', 'animal_species_1': 'mouse',
        'animal_strain_1': 'C57BL/6', 'route_1': 'SC', 'gender_1': 'male',
    }
    session['pipeline_result'] = {
        'errors': [], 'warnings': [], 'remap_log': [],
        'strand_diffs': [],
        'dedup_report': {'exp_conflicts': [], 'dp_conflicts': []},
    }
    session['normalize_id_map'] = {}
    session.save()

    with override_settings(MEDIA_ROOT=self.tmp_media):
        self.client.post(reverse('smart_upload_confirm'), {})

    # All-or-nothing: group 1 data rolled back because group 2 failed
    self.assertEqual(Experiment.objects.filter(exp_type='in_vivo').count(), 0)
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
python manage.py test app01.tests.SmartUploadConfirmTest.test_invivo_partial_failure_rolls_back_all_groups -v 2
```

Expected: FAIL — `AssertionError: 1 != 0` (group 1 committed independently, persists after group 2 failure).

- [ ] **Step 3: Apply the fix — two-part change**

**Part A:** In `app01/views.py`, find the line `invivo_errors = []` at ~line 2217 (it appears right after `invitro_errors = []`). Delete that line — the new code will declare it inside the outer try block.

**Part B:** Find the comment `# Write each in-vivo group in its own atomic transaction (independent)` at ~line 2422. Replace everything from that comment through the closing `except` at ~line 2487 with:

```python
    # Write all in-vivo groups in a single all-or-nothing transaction
    all_invivo_exps = []
    invivo_errors = []
    try:
        with transaction.atomic():
            for i, group in enumerate(invivo_groups):
                meta = invivo_meta[i]
                batch_label_iv = batch_label
                readout_code = group['readout_code']
                readout_label = group.get('readout_label', readout_code)
                assay_name_iv = f'{readout_label} 时间曲线'
                invivo_exps = []

                try:
                    with transaction.atomic():
                        for g in group['groups']:
                            compound, _ = Compound.objects.get_or_create(
                                compound_id=_resolve_cid(g['compound_id'])
                            )
                            if project_code:
                                compound.project = project_code
                                compound.save(update_fields=['project'])
                            dose_info = g.get('dose') or meta['dose_override']
                            schedule = g.get('schedule', '')

                            exp = Experiment.objects.create(
                                compound=compound,
                                exp_type='in_vivo',
                                assay_name=assay_name_iv,
                                batch_label=batch_label_iv,
                                animal_species=meta['animal_species'],
                                animal_strain=meta['animal_strain'],
                                route=meta['route'],
                                gender=meta['gender'],
                                time_unit=meta['time_unit'],
                                dose_info=dose_info,
                                schedule=schedule,
                            )
                            invivo_exps.append(exp)
                            n_invivo += 1

                            dp_objs = []
                            for tp in g['timepoints']:
                                dp_objs.append(DataPoint(
                                    experiment=exp, x_value=tp['time'], x_type='timepoint',
                                    replicate='Mean', value=tp['mean'], readout_type=readout_code,
                                ))
                                dp_objs.append(DataPoint(
                                    experiment=exp, x_value=tp['time'], x_type='timepoint',
                                    replicate='SD', value=tp['sd'], readout_type=readout_code,
                                ))
                            DataPoint.objects.bulk_create(dp_objs)

                        # Attach source file to the FIRST experiment only (batch-level)
                        saved_path = group.get('saved_path', '')
                        if invivo_exps and saved_path and default_storage.exists(saved_path):
                            from django.core.files.base import ContentFile as CF
                            with default_storage.open(saved_path, 'rb') as fh:
                                content = fh.read()
                            att = ExperimentAttachment(
                                experiment=invivo_exps[0], label=group['filename'])
                            att.file.save(group['filename'], CF(content), save=True)
                            n_attachments += 1
                            default_storage.delete(saved_path)

                        all_invivo_exps.extend(invivo_exps)
                except Exception as e:
                    logger.error(f'smart_upload_confirm invivo error: {e}')
                    invivo_errors.append(f'文件 {group["filename"]}: {e}')
                    raise  # trigger outer rollback
    except Exception:
        pass  # invivo_errors already populated above
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
python manage.py test app01.tests.SmartUploadConfirmTest -v 2
```

Expected: All tests in `SmartUploadConfirmTest` PASS (including the new rollback test).

- [ ] **Step 5: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "fix: wrap all in_vivo groups in single transaction for all-or-nothing commit"
```

---

## Task 4: Fix strand diff compound_id resolution in confirm view

**Files:**
- Modify: `app01/views.py:2254-2258`
- Modify: `app01/tests.py` — add `SmartUploadStrandDiffResolutionTest` class

**Context:** `strand_diffs[i]['compound_id']` is set in `smart_upload_preview_view` using `normalize_id_map.get(raw, raw)` only. In `smart_upload_confirm_view`, `resolved` goes through `id_format_mismatch` → `_resolve_cid()` (normalize + user_remap + canonicalize). When `canonicalize_compound_id` converts the raw form differently than `normalize_id_map`, `d['compound_id'] == resolved` is False, and the user's keep/overwrite choice is silently ignored (defaults to 'keep').

Example: `strand_map` key is `'BPR_3M03FN01'`, `normalize_id_map = {}`. `diff['compound_id'] = 'BPR_3M03FN01'`. `resolved = canonicalize_compound_id('BPR_3M03FN01', '3M03') = 'BPR3M03-FN01'`. Comparison `'BPR_3M03FN01' != 'BPR3M03-FN01'` → diff_choice = None → strand silently kept.

`canonicalize_compound_id('BPR_3M03FN01', '3M03')` returns `'BPR3M03-FN01'` by stripping the `_` and inserting a `-` (defined in `upload_pipeline.py:158`).

- [ ] **Step 1: Write the failing test**

Add this class to `app01/tests.py` after `SmartUploadConfirmCleanupTest`:

```python
class SmartUploadStrandDiffResolutionTest(TestCase):
    def setUp(self):
        self.tmp_media = tempfile.mkdtemp()
        self.user = LmsUser.objects.create_user(
            username='strand_diff_test', password='pw',
            user_type='sub_admin', module_permissions='upload,data,compound,batch',
        )
        self.client.force_login(self.user)

    def tearDown(self):
        shutil.rmtree(self.tmp_media, ignore_errors=True)

    def test_strand_overwrite_choice_honoured_after_id_canonicalization(self):
        """'overwrite' choice is applied even when diff compound_id is the raw (un-canonicalized) form."""
        compound = Compound.objects.create(compound_id='BPR3M03-FN01', project='3M03')
        Strand.objects.create(
            compound=compound, strand_type='SS',
            sequence_id='BPR3M03-FN01_SS', modify_seq='AAAA',
        )
        # Set up session: diff stores raw ID, normalize_id_map is empty
        # So _resolve_cid must canonicalize 'BPR_3M03FN01' → 'BPR3M03-FN01' via canonicalize_compound_id
        session = self.client.session
        session['smart_preview'] = {
            'project_code': '3M03',
            'file_detections': [],
            'invitro': {
                'experiments': [],
                'strand_map': {'BPR_3M03FN01': {'ss_seq': 'CCCC', 'as_seq': ''}},
                'new_compounds': [],
                'assay_name': '',
                'cell_line': '',
                'notes': '',
                'id_format_mismatch': {},
            },
            'invivo_groups': [],
            'source_files': [],
            'attachment_files': [],
            'errors': [],
            'has_no_seq': False,
        }
        session['upload_meta'] = {
            'batch_label': '',
            'assay_name': '',
            'exp_date': None,
            'target_name': 'FASN',
            'source_batch': '',
            'attach_vitro': False,
            'attach_vivo': False,
        }
        session['pipeline_result'] = {
            'errors': [], 'warnings': [], 'remap_log': [],
            'strand_diffs': [
                {
                    'compound_id': 'BPR_3M03FN01',  # raw: mismatch with canonicalized resolved
                    'strand_type': 'SS',
                    'old_seq': 'AAAA',
                    'new_seq': 'CCCC',
                    'user_choice': None,
                }
            ],
            'dedup_report': {'exp_conflicts': [], 'dp_conflicts': []},
        }
        session['normalize_id_map'] = {}  # empty: canonicalize_compound_id handles the remap
        session.save()

        with override_settings(MEDIA_ROOT=self.tmp_media):
            self.client.post('/upload/smart/confirm/', {
                'strand_choice_BPR_3M03FN01_SS': 'overwrite',
            })

        strand = Strand.objects.get(compound__compound_id='BPR3M03-FN01', strand_type='SS')
        self.assertEqual(strand.modify_seq, 'CCCC')  # should be overwritten
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
python manage.py test app01.tests.SmartUploadStrandDiffResolutionTest.test_strand_overwrite_choice_honoured_after_id_canonicalization -v 2
```

Expected: FAIL — `AssertionError: 'AAAA' != 'CCCC'` (overwrite ignored, strand still 'AAAA').

- [ ] **Step 3: Apply the fix**

In `app01/views.py`, find lines 2254–2258:

```python
                        diff_choice = next(
                            (d['user_choice'] for d in strand_diffs
                             if d['compound_id'] == resolved and d['strand_type'] == strand_type),
                            None,
                        )
```

Replace with:

```python
                        diff_choice = next(
                            (d['user_choice'] for d in strand_diffs
                             if _resolve_cid(d['compound_id']) == resolved and d['strand_type'] == strand_type),
                            None,
                        )
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
python manage.py test app01.tests.SmartUploadStrandDiffResolutionTest -v 2
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "fix: apply _resolve_cid to strand diff compound_id for correct keep/overwrite matching"
```

---

## Task 5: Run full test suite and lint check

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_bprdb
source venv/bin/activate
python manage.py test app01 -v 2
```

Expected: All tests PASS. If Task 3 test fails with `AssertionError: 1 != 0` (group 1 still committed), check that both changes were applied: (a) `invivo_errors = []` removed from ~line 2217, and (b) the outer `transaction.atomic()` block was inserted correctly with `raise` inside the inner except.

- [ ] **Step 2: Run ruff on modified files**

```bash
ruff check app01/views.py app01/tests.py
```

Expected: no errors in modified sections. Fix any reported issues with `ruff check --fix` for auto-fixable ones, then fix remaining manually.

- [ ] **Step 3: Commit lint fixes (only if needed)**

```bash
git add app01/views.py app01/tests.py
git commit -m "fix: ruff lint cleanup for upload confirm bugfixes"
```
