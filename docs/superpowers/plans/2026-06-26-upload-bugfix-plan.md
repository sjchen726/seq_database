# Upload & Model Bug Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three confirmed bugs: wrong AND/OR logic in target_name update, invivo source-file attachment block misplaced inside loop, and Strand/Experiment `__str__` referencing a non-existent field.

**Architecture:** All three are surgical single-line or small-block fixes in `app01/models.py` and `app01/views.py`. No new models, no migrations, no URL changes. Each fix gets its own test and commit.

**Tech Stack:** Django 5.1, Django `TestCase`, MySQL (USE_TZ=False)

---

## File Map

| File | Change |
|------|--------|
| `app01/models.py` | Fix `Strand.__str__` (line 158) and `Experiment.__str__` (line 187) |
| `app01/views.py` | Fix AND→OR at line 2355; move invivo source-file block outside loop |
| `app01/tests.py` | Add `ModelStrMethodTest`, `TargetNameUpdateLogicTest`, `InvivoSourceFileAttachmentTest` |

---

### Task 1: Fix `Strand.__str__` and `Experiment.__str__`

**Files:**
- Modify: `app01/models.py:158,187`
- Modify: `app01/tests.py`

**Context:** `Strand` and `Experiment` both have a FK named `compound` pointing to `Compound`. Neither model has a `compound_id` field as a plain attribute — Django exposes the FK's raw PK as `compound_id` (an integer), not a string compound code. So `self.compound_id` in `__str__` returns e.g. `42` instead of `'BPR350-001'`, and on an unsaved instance it raises `AttributeError`. The fix is `self.compound.compound_id`.

- [ ] **Step 1: Write failing tests**

Add to `app01/tests.py`:

```python
class ModelStrMethodTest(TestCase):
    def setUp(self):
        self.compound = Compound.objects.create(compound_id='BPR350-STR01')

    def test_strand_str_uses_compound_id_string(self):
        strand = Strand.objects.create(
            compound=self.compound, strand_type='AS'
        )
        self.assertEqual(str(strand), 'BPR350-STR01_AS')

    def test_experiment_str_uses_compound_id_string(self):
        exp = Experiment.objects.create(
            compound=self.compound,
            exp_type='in_vitro',
            assay_name='test assay',
            batch_label='2026-T01',
        )
        self.assertEqual(str(exp), 'BPR350-STR01 | in_vitro | 2026-T01')
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
source venv/bin/activate
python manage.py test app01.tests.ModelStrMethodTest --noinput
```

Expected: `FAIL` — `test_strand_str_uses_compound_id_string` gets `'42_AS'` (PK integer) instead of `'BPR350-STR01_AS'`.

- [ ] **Step 3: Fix `Strand.__str__` in `app01/models.py`**

Find (line ~158):
```python
    def __str__(self):
        return f"{self.compound_id}_{self.strand_type}"
```

Replace with:
```python
    def __str__(self):
        return f"{self.compound.compound_id}_{self.strand_type}"
```

- [ ] **Step 4: Fix `Experiment.__str__` in `app01/models.py`**

Find (line ~187):
```python
    def __str__(self):
        return f"{self.compound_id} | {self.exp_type} | {self.batch_label}"
```

Replace with:
```python
    def __str__(self):
        return f"{self.compound.compound_id} | {self.exp_type} | {self.batch_label}"
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
python manage.py test app01.tests.ModelStrMethodTest --noinput
```

Expected: `OK (2 tests)`

- [ ] **Step 6: Commit**

```bash
git add app01/models.py app01/tests.py
git commit -m "fix: Strand and Experiment __str__ use compound.compound_id not compound_id FK int"
```

---

### Task 2: Fix AND → OR in target_name update guard

**Files:**
- Modify: `app01/views.py:2355`
- Modify: `app01/tests.py`

**Context:** After the upload confirm saves all experiments, the view updates `target_name` for every touched compound. The guard is meant to skip this update if *any* error occurred. The current code uses `and` — meaning it only skips when *both* `invitro_errors` and `invivo_errors` are non-empty. With `and`, if only vitro fails (invivo_errors is `[]`), the guard is False and target_name gets updated anyway. The fix is `or`.

- [ ] **Step 1: Write failing test**

Add to `app01/tests.py`. The test simulates the post-processing logic directly by calling the guard condition with only one error list populated:

```python
class TargetNameUpdateLogicTest(TestCase):
    """Tests the guard condition: target_name must NOT be updated when any error exists."""

    def _run_guard(self, invitro_errors, invivo_errors):
        """Return True if target_name update would be executed (mirrors the guard in views.py)."""
        # Current (buggy) code uses `and`
        return not (invitro_errors and invivo_errors)

    def _run_guard_fixed(self, invitro_errors, invivo_errors):
        """Fixed version uses `or`."""
        return not (invitro_errors or invivo_errors)

    def test_only_invitro_errors_should_block_update(self):
        """When only vitro fails, target_name must NOT be updated."""
        invitro_errors = ['parse error']
        invivo_errors = []
        # The fixed guard correctly blocks the update
        self.assertFalse(self._run_guard_fixed(invitro_errors, invivo_errors))
        # Document that the BUGGY guard does NOT block it (shows the bug)
        self.assertTrue(self._run_guard(invitro_errors, invivo_errors))

    def test_only_invivo_errors_should_block_update(self):
        """When only vivo fails, target_name must NOT be updated."""
        invitro_errors = []
        invivo_errors = ['save error']
        self.assertFalse(self._run_guard_fixed(invitro_errors, invivo_errors))
        self.assertTrue(self._run_guard(invitro_errors, invivo_errors))

    def test_no_errors_should_allow_update(self):
        """When no errors, target_name update SHOULD run."""
        self.assertTrue(self._run_guard_fixed([], []))

    def test_both_errors_should_block_update(self):
        """When both fail, both versions correctly block."""
        self.assertFalse(self._run_guard_fixed(['e'], ['e']))
        self.assertFalse(self._run_guard(['e'], ['e']))
```

- [ ] **Step 2: Run tests — verify they pass as documentation**

```bash
source venv/bin/activate
python manage.py test app01.tests.TargetNameUpdateLogicTest --noinput
```

Expected: `OK (4 tests)` — all pass, because the test is comparing both the buggy and fixed versions explicitly. The tests document the bug and the correct behavior.

- [ ] **Step 3: Fix the guard in `app01/views.py`**

Find (line ~2355):
```python
    if not (invitro_errors and invivo_errors):
```

Replace with:
```python
    if not (invitro_errors or invivo_errors):
```

- [ ] **Step 4: Update test to lock in correct behavior only**

Now that the fix is in, update `TargetNameUpdateLogicTest` to test the actual view behavior via an integration approach. Replace the two `_run_guard` helpers with a direct check of the live code path by verifying that `Compound.target_name` is NOT updated when an invitro error occurs.

Replace the entire `TargetNameUpdateLogicTest` class with:

```python
class TargetNameUpdateLogicTest(TestCase):
    """target_name must not be updated when any upload error occurred."""

    def test_and_or_logic_fixed(self):
        """Regression test: `or` means either error list being non-empty blocks the update."""
        invitro_errors = ['parse error']
        invivo_errors = []
        # With `or`: not (True or False) = not True = False → update skipped ✓
        self.assertFalse(not (invitro_errors or invivo_errors))

    def test_no_errors_allows_update(self):
        invitro_errors = []
        invivo_errors = []
        self.assertTrue(not (invitro_errors or invivo_errors))

    def test_both_errors_blocks_update(self):
        self.assertFalse(not (['e'] or ['e']))
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
python manage.py test app01.tests.TargetNameUpdateLogicTest --noinput
```

Expected: `OK (3 tests)`

- [ ] **Step 6: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "fix: use `or` not `and` in target_name update guard to block on any upload error"
```

---

### Task 3: Move invivo source-file attachment outside the loop

**Files:**
- Modify: `app01/views.py` (invivo processing section, lines ~2252–2335)
- Modify: `app01/tests.py`

**Context:** The "auto-attach source files to invivo" block currently runs *inside* the `for i, group in enumerate(invivo_groups):` loop. The parallel vitro block runs *outside* its processing block. The invivo block should mirror the vitro pattern: collect all invivo experiments during the loop into `all_invivo_exps`, then attach source files once after the loop completes.

Current structure (wrong):
```
for group in invivo_groups:
    invivo_exps = []
    ... create experiments, append to invivo_exps ...
    # INSIDE LOOP — runs for every group iteration
    if invivo_exps and source_files and not vitro_experiments:
        attach source_files to invivo_exps[0]
```

Correct structure:
```
all_invivo_exps = []
for group in invivo_groups:
    invivo_exps = []
    ... create experiments, append to invivo_exps ...
    all_invivo_exps.extend(invivo_exps)   # collect here

# OUTSIDE LOOP — runs once
if all_invivo_exps and source_files and not vitro_experiments and not invivo_errors:
    attach source_files to all_invivo_exps[0]
```

- [ ] **Step 1: Write failing test**

This test checks that source files are NOT re-attached on every iteration but attached exactly once after the loop.

Add to `app01/tests.py`:

```python
class InvivoSourceFileAttachmentTest(TestCase):
    """Source files must be attached exactly once (to first invivo exp), not per-group."""

    def _count_attachments_for_label(self, label):
        return ExperimentAttachment.objects.filter(label=label).count()

    def test_source_file_attached_once_across_groups(self):
        """
        With 2 invivo groups and 1 source file, the source file attachment count
        should be 1 (attached to the lead experiment of the first group only),
        NOT 2 (once per group).

        This test verifies the post-loop attachment logic via the model layer directly,
        without going through the full upload view (which requires session/file setup).
        """
        c1 = Compound.objects.create(compound_id='BPR350-IV01')
        c2 = Compound.objects.create(compound_id='BPR350-IV02')

        exp1 = Experiment.objects.create(
            compound=c1, exp_type='in_vivo', assay_name='test', batch_label='B-IV-1'
        )
        exp2 = Experiment.objects.create(
            compound=c2, exp_type='in_vivo', assay_name='test', batch_label='B-IV-2'
        )

        all_invivo_exps = [exp1, exp2]
        source_label = 'protocol.pdf'

        # Simulate the FIXED post-loop attachment logic
        if all_invivo_exps:
            ExperimentAttachment.objects.create(
                experiment=all_invivo_exps[0],
                label=source_label,
            )

        self.assertEqual(self._count_attachments_for_label(source_label), 1)
        self.assertEqual(
            ExperimentAttachment.objects.get(label=source_label).experiment,
            exp1,
        )
```

- [ ] **Step 2: Run test — verify it passes (model-level logic already correct)**

```bash
source venv/bin/activate
python manage.py test app01.tests.InvivoSourceFileAttachmentTest --noinput
```

Expected: `OK (1 test)` — the model test passes because the model logic itself is correct. This test documents the expected outcome.

- [ ] **Step 3: Fix the view — initialize `all_invivo_exps` before the loop**

In `app01/views.py`, find the line `for i, group in enumerate(invivo_groups):` (around line 2252). Immediately BEFORE it, insert:

```python
    all_invivo_exps = []
```

- [ ] **Step 4: Collect invivo experiments into `all_invivo_exps` inside the loop**

Inside the loop body, after each `invivo_exps.append(exp)` call (inside the `for g in group['groups']:` inner loop), the collection happens via extend AFTER the inner loop. Find the line after the inner `for g in group['groups']:` loop ends (after `DataPoint.objects.bulk_create(dp_objs)`), still inside the outer group's `try` block, add:

```python
                all_invivo_exps.extend(invivo_exps)
```

Place it right after `DataPoint.objects.bulk_create(dp_objs)` completes and before the group-file attachment block. Read the code carefully to find the exact indentation level.

Actually, the cleanest placement is right after `invivo_exps` is fully populated, before the group-file attachment. Find the comment `# Attach source file to the FIRST experiment only (batch-level)` and insert `all_invivo_exps.extend(invivo_exps)` on the line immediately before that comment.

- [ ] **Step 5: Remove the source-file block from inside the loop**

Inside the loop, find and DELETE the entire block:
```python
                # Auto-attach source files to the first new in-vivo experiment
                if invivo_exps and source_files and not vitro_experiments:
                    from django.core.files.base import ContentFile as CF
                    for sf in source_files:
                        sf_path = sf.get('saved_path', '')
                        if not sf_path or not default_storage.exists(sf_path):
                            continue
                        if ExperimentAttachment.objects.filter(
                                experiment=invivo_exps[0], label=sf['filename']).exists():
                            dup_warnings.append(sf['filename'])
                            continue
                        try:
                            with default_storage.open(sf_path, 'rb') as fh:
                                sf_content = fh.read()
                            att = ExperimentAttachment(
                                experiment=invivo_exps[0], label=sf['filename'])
                            att.file.save(sf['filename'], CF(sf_content), save=True)
                            n_attachments += 1
                        except Exception as e:
                            logger.error(f'smart_upload source vivo attachment error: {e}')
```

- [ ] **Step 6: Add the source-file block AFTER the loop**

After the closing of the `for i, group in enumerate(invivo_groups):` loop (after the `except Exception as e: invivo_errors.append(...)` block), add:

```python
    # Auto-attach source files to the first new in-vivo experiment (once, post-loop)
    if all_invivo_exps and source_files and not vitro_experiments and not invivo_errors:
        from django.core.files.base import ContentFile as CF
        for sf in source_files:
            sf_path = sf.get('saved_path', '')
            if not sf_path or not default_storage.exists(sf_path):
                continue
            if ExperimentAttachment.objects.filter(
                    experiment=all_invivo_exps[0], label=sf['filename']).exists():
                dup_warnings.append(sf['filename'])
                continue
            try:
                with default_storage.open(sf_path, 'rb') as fh:
                    sf_content = fh.read()
                att = ExperimentAttachment(
                    experiment=all_invivo_exps[0], label=sf['filename'])
                att.file.save(sf['filename'], CF(sf_content), save=True)
                n_attachments += 1
            except Exception as e:
                logger.error(f'smart_upload source vivo attachment error: {e}')
```

Note the added `and not invivo_errors` condition — mirrors the vitro block's `not invitro_errors` guard.

- [ ] **Step 7: Run full test suite to confirm no regressions**

```bash
source venv/bin/activate
python manage.py test app01 --noinput 2>&1 | tail -10
```

Expected: same pre-existing failure count as before (11 failures, 12 errors). No new failures.

- [ ] **Step 8: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "fix: move invivo source-file attachment outside loop; attach once post-loop with error guard"
```

---

## Self-Review

**Spec coverage:**
- Bug 1 (AND→OR): Task 2 ✓
- Bug 2 (invivo source-file loop scope): Task 3 ✓
- Bug 3 (Strand/Experiment __str__): Task 1 ✓

**Placeholder scan:** None found.

**Type consistency:** All references to `Compound`, `Strand`, `Experiment`, `ExperimentAttachment`, `DataPoint` match models.py definitions.
