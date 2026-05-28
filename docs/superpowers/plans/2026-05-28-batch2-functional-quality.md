# Batch 2 — Functional Bugs + Performance + Code Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix upload-pipeline logic bugs, eliminate full-table memory loads, remove a hardcoded username, add a user-level default_seq_type field, cache repeated DB lookups in coloring functions, and clean up URL naming. Batch 1 must be deployed first (no hard code dependency, but Batch 1 fixes are assumed applied).

**Architecture:** One migration (0033) for the `LmsUser.default_seq_type` field. All other changes are local edits to `views.py`, `models.py`, and `urls.py`. Tasks can be done in any order except Task 4 (CQ-06) which requires the migration to exist before the view code change.

**Tech Stack:** Django 5.1 · Python 3.10 · MySQL · `django.test.TestCase` · pandas

---

## Project Context

- `group_sequences(df)` at ~line 1263 — pairs SS+AS rows; currently order-dependent
- `save_deliveries(df, duplex_id_map, username, sm_overrides=None)` at ~line 1798 — bulk insert deliveries; has double-`add_o` call and weak dedup key
- `check_duplicates(df, ss_groups)` at ~line 1594 — cross-batch dedup; the in-upload `seen_combinations` key doesn't include `naked_seq`
- `reg_seq_list(request)` at ~line 3200 — fetches all sequences into Python before paginating
- `get_user_default_seq_type(user)` at ~line 2646 — hardcodes `'Y2325': 'AS'`
- `build_combo_re()` at ~line 1735 — queries full DeliveryModule + SeqModule tables on every call
- `normalize_tmp_seq_with_combo(modify_seq)` at ~line 1761 — calls `build_combo_re()` internally on every call
- `bms/urls.py` — root path has no `name=`; `signup/` and `register/` both point to `register_view`
- Run tests: `python manage.py test app01 -v 2`
- Apply migrations: `python manage.py migrate`

---

## File Structure

| File | Tasks |
|------|-------|
| `app01/views.py` | All tasks except Task 4 migration and Task 6 |
| `app01/models.py` | Task 4 (add `default_seq_type` field + MODEL-03 TODO) |
| `app01/migrations/0033_lmsuser_default_seq_type.py` | Task 4 |
| `bms/urls.py` | Task 6 (URL cleanup) |
| `app01/tests.py` | Tests for all tasks |

---

## Task 1: BUG-02 + BUG-03 — `save_deliveries` Double `add_o` Call + Weak Dedup Key

**Files:**
- Modify: `app01/views.py` — `save_deliveries` function (~lines 1897–1928)
- Modify: `app01/tests.py` — add `SaveDeliveriesTests` class

**Background:**
- **BUG-02**: `add_o_to_all_rules_safe(item['modify_seq'])` is called at line ~1897 to compute `current_linker_seq`, then called *again* at line ~1928 inside `Delivery.objects.create(linker_seq=...)`. The second call re-processes the already-processed string, potentially double-adding `o` connectors.
- **BUG-03**: The dedup filter at ~line 1903 does `Delivery.objects.filter(delivery5=..., delivery3=..., linker_seq=...)` — it does NOT filter by `sequence`. Two different naked sequences with identical delivery5/3/linker_seq would be treated as duplicates of each other, causing the second one to be silently skipped.

Both fixes are in the same function, same commit.

- [ ] **Step 1: Add failing tests**

```python
from app01.views import save_deliveries, group_sequences, assign_duplex_ids
import pandas as pd

class SaveDeliveriesTests(TestCase):
    def setUp(self):
        # SeqModule entries so add_o_to_all_rules_safe works
        SeqModule.objects.get_or_create(keyword='Am', defaults={'base_char': 'A', 'linker_connector': 'o'})
        SeqModule.objects.get_or_create(keyword='Um', defaults={'base_char': 'U', 'linker_connector': 'o'})
        SeqModule.objects.get_or_create(keyword='Gm', defaults={'base_char': 'G', 'linker_connector': 'o'})
        SeqModule.objects.get_or_create(keyword='Cm', defaults={'base_char': 'C', 'linker_connector': 'o'})

        self.ss_seq = Sequence.objects.create(seq='AUGCAU', seq_type='SS')
        self.as_seq = Sequence.objects.create(seq='UGCAUG', seq_type='AS')

    def _make_df(self, rows):
        df = pd.DataFrame(rows)
        df = df.fillna('')
        df['__row_id'] = df.index
        df['__original_line'] = df.index + 2
        df.index = df['__row_id'].astype(int)
        return df

    def test_linker_seq_not_double_processed(self):
        """linker_seq in DB must equal add_o applied once, not twice."""
        from app01.views import add_o_to_all_rules_safe
        modify_seq = 'AmUmGmCmAmUm'
        expected_linker = add_o_to_all_rules_safe(modify_seq)
        double_processed = add_o_to_all_rules_safe(expected_linker)
        # If double-processing changes anything, the bug matters
        if expected_linker == double_processed:
            self.skipTest("add_o is idempotent for this input — choose a different test case")

        rows = [
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'SS', 'Modify_seq': modify_seq,
             'Strand_MWs': '', 'Parents': '', 'Remarks': '', 'Transcript': '', 'Position': ''},
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'AS', 'Modify_seq': modify_seq,
             'Strand_MWs': '', 'Parents': '', 'Remarks': '', 'Transcript': '', 'Position': ''},
        ]
        df = self._make_df(rows)
        ss_groups, _ = group_sequences(df)
        duplex_id_map = assign_duplex_ids(df, ss_groups, set())
        save_deliveries(df, duplex_id_map, 'testuser')
        delivery = Delivery.objects.filter(sequence=self.ss_seq).first()
        self.assertIsNotNone(delivery)
        self.assertEqual(delivery.linker_seq, expected_linker,
                         f"Expected single-processed: {expected_linker!r}, got: {delivery.linker_seq!r}")

    def test_different_naked_seqs_same_delivery_keys_both_saved(self):
        """Two rows with different naked_seqs but same delivery5/3/linker_seq must BOTH be saved."""
        # Create a second sequence with different naked_seq
        ss_seq2 = Sequence.objects.create(seq='CCCCCC', seq_type='SS')
        as_seq2 = Sequence.objects.create(seq='GGGGGG', seq_type='AS')

        # Pre-populate: seq1 already has a delivery with these delivery5/3
        Delivery.objects.create(
            sequence=self.ss_seq, duplex_id='BP000001', seq_type='SS',
            delivery5='invAb', delivery3='Vp',
            modify_seq='AmUmGmCmAmUm', linker_seq='AoUoGoCoAoU',
            project='P1',
        )

        # Now upload seq2 with identical delivery5/3/linker_seq
        rows = [
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'SS',
             'Modify_seq': '[invAb]CmCmCmCmCmCm[Vp]',
             'Strand_MWs': '', 'Parents': '', 'Remarks': '', 'Transcript': '', 'Position': ''},
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'AS',
             'Modify_seq': '[invAb]GmGmGmGmGmGm[Vp]',
             'Strand_MWs': '', 'Parents': '', 'Remarks': '', 'Transcript': '', 'Position': ''},
        ]
        df = self._make_df(rows)
        ss_groups, _ = group_sequences(df)
        duplex_id_map = assign_duplex_ids(df, ss_groups, set())
        save_deliveries(df, duplex_id_map, 'testuser')

        # Both seq2 SS and seq2 AS must have a delivery row
        self.assertTrue(Delivery.objects.filter(sequence=ss_seq2).exists(),
                        "SS delivery for seq2 was not saved (false duplicate detection)")
        self.assertTrue(Delivery.objects.filter(sequence=as_seq2).exists(),
                        "AS delivery for seq2 was not saved (false duplicate detection)")
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
python manage.py test app01.tests.SaveDeliveriesTests -v 2
```

Expected: `test_different_naked_seqs_same_delivery_keys_both_saved` FAIL (delivery for seq2 skipped).

- [ ] **Step 3: Fix BUG-02 — replace second `add_o` call**

Find `save_deliveries` (~line 1924). Inside `Delivery.objects.create(...)`, find:

```python
                linker_seq=add_o_to_all_rules_safe(item['modify_seq']),
```

Replace with:

```python
                linker_seq=current_linker_seq,
```

(`current_linker_seq` is already set on ~line 1897.)

- [ ] **Step 4: Fix BUG-03 — add `sequence=sequence_obj` to dedup filter**

Find the dedup check (~line 1903):

```python
            duplicate = Delivery.objects.filter(
         #       id__startswith=base_id,
                delivery5=current_delivery5,
                delivery3=current_delivery3,
                linker_seq=current_linker_seq
            ).first()
```

Replace with:

```python
            duplicate = Delivery.objects.filter(
                sequence=sequence_obj,
                delivery5=current_delivery5,
                delivery3=current_delivery3,
                linker_seq=current_linker_seq
            ).first()
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
python manage.py test app01.tests.SaveDeliveriesTests -v 2
```

Expected: both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "fix: save_deliveries — remove double add_o call; add sequence to dedup filter

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: BUG-06 — `group_sequences` Requires SS Before AS

**Files:**
- Modify: `app01/views.py` — `group_sequences` function (~line 1263)
- Modify: `app01/tests.py` — add `GroupSequencesOrderTests` class

**Background:** The current implementation is a single-pass scan: when it sees SS, it looks ahead for AS. If AS appears first, it's immediately added to `invalid_ss_as`. Fix: two-pass approach — scan all rows first, then pair consecutive SS+AS *or* AS+SS pairs in either order.

Pairing rule: scan left to right, consume two adjacent rows if their types are (SS,AS) or (AS,SS). Each row participates in at most one pair. Within a group, SS row id comes first (index 0) and AS row id comes second (index 1).

- [ ] **Step 1: Add failing tests**

```python
class GroupSequencesOrderTests(TestCase):
    def _make_df(self, rows):
        df = pd.DataFrame(rows)
        df = df.fillna('')
        df['__row_id'] = df.index
        df['__original_line'] = df.index + 2
        return df

    def _row(self, seq_type, modify_seq='AmUm', project='P1'):
        return {'Seq_type': seq_type, 'Modify_seq': modify_seq, 'Project': project,
                'Target': 'T', 'Strand_MWs': '', 'Parents': '', 'Remarks': ''}

    def test_ss_then_as_pairs_correctly(self):
        """Classic order: SS row 0, AS row 1 → one group."""
        df = self._make_df([self._row('SS'), self._row('AS')])
        ss_groups, invalid = group_sequences(df)
        self.assertEqual(len(ss_groups), 1)
        self.assertEqual(invalid, [])

    def test_as_then_ss_pairs_correctly(self):
        """Reversed order: AS row 0, SS row 1 → one group, SS id first in group."""
        df = self._make_df([self._row('AS'), self._row('SS')])
        ss_groups, invalid = group_sequences(df)
        self.assertEqual(len(ss_groups), 1, f"Expected 1 group, got {len(ss_groups)}: {invalid}")
        self.assertEqual(invalid, [])
        _, _, group = ss_groups[0]
        # SS row_id should be first in group
        ss_row_id = df[df['Seq_type'] == 'SS']['__row_id'].iloc[0]
        self.assertEqual(group[0], ss_row_id)

    def test_two_pairs_as_ss_ss_as(self):
        """AS,SS,SS,AS → two valid groups."""
        df = self._make_df([
            self._row('AS'), self._row('SS'),   # pair 1
            self._row('SS'), self._row('AS'),   # pair 2
        ])
        ss_groups, invalid = group_sequences(df)
        self.assertEqual(len(ss_groups), 2)
        self.assertEqual(invalid, [])

    def test_unpaired_lone_ss_is_invalid(self):
        """SS with no adjacent AS → invalid."""
        df = self._make_df([self._row('SS')])
        ss_groups, invalid = group_sequences(df)
        self.assertEqual(len(ss_groups), 0)
        self.assertEqual(len(invalid), 1)
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
python manage.py test app01.tests.GroupSequencesOrderTests -v 2
```

Expected: `test_as_then_ss_pairs_correctly` and `test_two_pairs_as_ss_ss_as` FAIL.

- [ ] **Step 3: Replace `group_sequences` in `app01/views.py`**

Find `def group_sequences(df):` (~line 1263). Replace the entire function:

```python
def group_sequences(df):
    """
    Pair consecutive SS+AS or AS+SS rows.
    Pairing rule: scan left to right; consume two adjacent rows if their Seq_type
    is (SS,AS) or (AS,SS). Unpaired rows are reported in invalid_ss_as.
    Within each group, SS __row_id is always first, AS __row_id second.
    """
    ss_groups = []
    invalid_ss_as = []

    group_sorted = df.sort_values(by='__row_id').reset_index(drop=True)
    rows = [group_sorted.iloc[i] for i in range(len(group_sorted))]

    i = 0
    while i < len(rows):
        row = rows[i]
        seq_type = row['Seq_type'].strip().upper()

        if i + 1 < len(rows):
            next_row = rows[i + 1]
            next_seq_type = next_row['Seq_type'].strip().upper()

            if seq_type == 'SS' and next_seq_type == 'AS':
                temp_group = [row['__row_id'], next_row['__row_id']]
                ss_groups.append((None, row['Project'], temp_group))
                i += 2
                continue

            if seq_type == 'AS' and next_seq_type == 'SS':
                # SS first in group regardless of CSV order
                temp_group = [next_row['__row_id'], row['__row_id']]
                ss_groups.append((None, next_row['Project'], temp_group))
                i += 2
                continue

        # Could not pair with next row
        invalid_ss_as.append(
            f"原始行 {row['__original_line']}, {row['Modify_seq']}, 无法配对（{seq_type}）"
        )
        i += 1

    return ss_groups, invalid_ss_as
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python manage.py test app01.tests.GroupSequencesOrderTests -v 2
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Run existing preflight tests to check for regressions**

```bash
python manage.py test app01.tests.RunPreflightCheckTests -v 2
python manage.py test app01.tests.CheckDuplicatesTests -v 2
```

Expected: all PASS. The return structure of `group_sequences` is unchanged (`(ss_groups, invalid_ss_as)`), so callers are unaffected.

- [ ] **Step 6: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "fix: group_sequences now pairs SS+AS in either order (AS-first was silently dropped)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: PERF-04 — `reg_seq_list` Loads Entire Table Into Python Before Paging

**Files:**
- Modify: `app01/views.py` — `reg_seq_list` function (~line 3200)
- Modify: `app01/tests.py` — add `RegSeqListPaginationTests` class

**Background:** Current code iterates `Sequence.objects.exclude(seq_type='duplex')` (full table) into a Python list, then wraps it in `Paginator`. Fix: apply `Paginator` to the Django queryset directly, then build the dict list from only the current page's records.

- [ ] **Step 1: Add a failing test**

The bug is observable only at scale, so the test instead checks correctness (correct page size, correct content):

```python
class RegSeqListPaginationTests(TestCase):
    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='pager', password='pass', user_type='guest'
        )
        self.client.login(username='pager', password='pass')
        # Create 25 sequences so we can test page 2
        for i in range(25):
            seq = Sequence.objects.create(seq=f'AUGCAU{i:02d}', seq_type='SS')
            SeqInfo.objects.create(sequence=seq, project='P1', Pos='1', Remark='', Transcript='')

    def test_page_1_returns_correct_count(self):
        response = self.client.get('/reg_seq_list/?page=1&page_size=10')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['sequence_list']), 10)

    def test_page_2_returns_remaining(self):
        response = self.client.get('/reg_seq_list/?page=2&page_size=20')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['sequence_list']), 5)

    def test_page_obj_has_correct_count(self):
        response = self.client.get('/reg_seq_list/')
        self.assertEqual(response.context['page_obj'].paginator.count, 25)
```

- [ ] **Step 2: Run tests to confirm they pass (regression baseline)**

```bash
python manage.py test app01.tests.RegSeqListPaginationTests -v 2
```

These tests check correctness, which the current implementation handles correctly. They should all PASS (confirming the refactor doesn't break functionality).

- [ ] **Step 3: Refactor `reg_seq_list` in `app01/views.py`**

Find `def reg_seq_list(request):` (~line 3200). Replace the entire function:

```python
@login_required
def reg_seq_list(request):
    q = request.GET.get('q', '').strip()
    try:
        page_size = int(request.GET.get('page_size', 20))
    except (ValueError, TypeError):
        page_size = 20

    sequences = (
        Sequence.objects
        .exclude(seq_type='duplex')
        .prefetch_related('target_info')
        .order_by('rm_code')
    )
    if q:
        sequences = sequences.filter(rm_code__icontains=q)

    # DB-level pagination — only fetch the current page's rows
    paginator = Paginator(sequences, page_size)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    sequence_list = []
    for seq in page_obj.object_list:
        if seq.seq_type == 'SS':
            seq_prefix = 'SS_'
        elif seq.seq_type == 'AS':
            seq_prefix = 'AS_'
        else:
            seq_prefix = ''

        seq_info = seq.target_info.first()
        sequence_list.append({
            'rm_code': seq.rm_code,
            'seq_prefix': seq_prefix,
            'seq': seq.seq,
            'pos': seq_info.Pos if seq_info else '',
            'transcript': seq_info.Transcript if seq_info else '',
            'remark': seq_info.Remark if seq_info else '',
            'reg_date': seq.created_at.strftime('%Y-%m-%d %H:%M') if seq.created_at else '',
        })

    return render(request, 'reg_seq_list.html', {
        'sequence_list': sequence_list,
        'page_obj': page_obj,
        'page_size': page_size,
        'q': q,
    })
```

Note: the `@login_required` decorator may already be present above the function — verify and keep it if so.

- [ ] **Step 4: Run tests again to confirm correctness preserved**

```bash
python manage.py test app01.tests.RegSeqListPaginationTests -v 2
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "perf: reg_seq_list uses DB-level pagination instead of full-table Python list

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: CQ-06 — Remove Hardcoded Username `Y2325`, Add `default_seq_type` Field

**Files:**
- Modify: `app01/models.py` — add `default_seq_type` field to `LmsUser`
- Create: `app01/migrations/0033_lmsuser_default_seq_type.py`
- Modify: `app01/views.py` — rewrite `get_user_default_seq_type`
- Modify: `app01/tests.py` — add `DefaultSeqTypeTests` class

**Background:** `get_user_default_seq_type` hardcodes `{'Y2325': 'AS'}`. A `default_seq_type` field was planned (the comment in the function says "优先读取数据库中 LmsUser 的 default_seq_type 字段（如有）") but never created. Fix: add the field and remove the hardcoded map.

- [ ] **Step 1: Add a failing test**

```python
class DefaultSeqTypeTests(TestCase):
    def test_default_is_ss_for_new_user(self):
        """New users default to 'SS' seq type."""
        from app01.views import get_user_default_seq_type
        user = LmsUser.objects.create_user(username='newuser', password='pass')
        self.assertEqual(get_user_default_seq_type(user), 'SS')

    def test_user_with_as_default_returns_as(self):
        """User with default_seq_type='AS' returns 'AS'."""
        from app01.views import get_user_default_seq_type
        user = LmsUser.objects.create_user(
            username='asuser', password='pass', default_seq_type='AS'
        )
        self.assertEqual(get_user_default_seq_type(user), 'AS')

    def test_unauthenticated_returns_ss(self):
        """Anonymous/unauthenticated user returns 'SS'."""
        from app01.views import get_user_default_seq_type
        from django.contrib.auth.models import AnonymousUser
        self.assertEqual(get_user_default_seq_type(AnonymousUser()), 'SS')
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
python manage.py test app01.tests.DefaultSeqTypeTests -v 2
```

Expected: FAIL — `LmsUser` has no `default_seq_type` field.

- [ ] **Step 3: Add field to `app01/models.py`**

Find the `LmsUser` class. After the `permissions_project` field (~line 172), add:

```python
    default_seq_type = models.CharField(
        '默认序列方向',
        max_length=10,
        default='SS',
        choices=[('SS', 'SS'), ('AS', 'AS')],
    )
```

- [ ] **Step 4: Create migration**

```bash
python manage.py makemigrations app01 --name lmsuser_default_seq_type
```

Expected output:
```
Migrations for 'app01':
  app01/migrations/0033_lmsuser_default_seq_type.py
    - Add field default_seq_type to lmsuser
```

- [ ] **Step 5: Edit the migration to include data backfill for Y2325**

Open the generated `app01/migrations/0033_lmsuser_default_seq_type.py`. Add a `RunPython` operation after the `AddField`:

```python
from django.db import migrations, models


def set_y2325_default(apps, schema_editor):
    LmsUser = apps.get_model('app01', 'LmsUser')
    LmsUser.objects.filter(username='Y2325').update(default_seq_type='AS')


def reverse_y2325_default(apps, schema_editor):
    pass  # no need to undo


class Migration(migrations.Migration):

    dependencies = [
        ('app01', '0032_sequence_seq_maxlen'),
    ]

    operations = [
        migrations.AddField(
            model_name='lmsuser',
            name='default_seq_type',
            field=models.CharField(
                choices=[('SS', 'SS'), ('AS', 'AS')],
                default='SS',
                max_length=10,
                verbose_name='默认序列方向',
            ),
        ),
        migrations.RunPython(set_y2325_default, reverse_y2325_default),
    ]
```

- [ ] **Step 6: Apply migration**

```bash
python manage.py migrate
```

Expected: "Applying app01.0033_lmsuser_default_seq_type... OK"

- [ ] **Step 7: Fix `get_user_default_seq_type` in `app01/views.py`**

Find `def get_user_default_seq_type(user):` (~line 2646). Replace the entire function:

```python
def get_user_default_seq_type(user):
    """
    返回指定用户的默认序列方向（SS / AS）。
    从数据库中 LmsUser.default_seq_type 字段读取。
    未登录用户默认 'SS'。
    """
    if not user.is_authenticated:
        return 'SS'
    return getattr(user, 'default_seq_type', 'SS') or 'SS'
```

- [ ] **Step 8: Run tests to confirm they pass**

```bash
python manage.py test app01.tests.DefaultSeqTypeTests -v 2
```

Expected: all 3 tests PASS.

- [ ] **Step 9: Verify Y2325 user has correct default (if present in your dev DB)**

```bash
python manage.py shell -c "from app01.models import LmsUser; u = LmsUser.objects.filter(username='Y2325').first(); print(u.default_seq_type if u else 'user not found')"
```

Expected: `AS` (if the user exists), or `user not found`.

- [ ] **Step 10: Commit**

```bash
git add app01/models.py app01/migrations/0033_lmsuser_default_seq_type.py app01/views.py app01/tests.py
git commit -m "feat: add LmsUser.default_seq_type field, remove hardcoded Y2325 username

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: CQ-07/08 — `build_combo_re` / `normalize_tmp_seq_with_combo` Query DB on Every Call

**Files:**
- Modify: `app01/views.py` — `build_combo_re` (~line 1735), `normalize_tmp_seq_with_combo` (~line 1761), and their call sites in `run_preflight_check` (~line 1303)
- Modify: `app01/tests.py` — add `BuildComboReTests` class

**Background:** `build_combo_re()` queries `DeliveryModule.objects.all()` + `SeqModule.objects.all()` every time it's called. `normalize_tmp_seq_with_combo()` calls `build_combo_re()` internally. In `run_preflight_check`, both are called in a loop over every row, producing N × 2 full-table queries. Fix: add optional `dm_modules` / `sm_modules` parameters so callers can pre-load and share.

- [ ] **Step 1: Add tests**

```python
from unittest.mock import patch

class BuildComboReTests(TestCase):
    def setUp(self):
        DeliveryModule.objects.get_or_create(keyword='invAb', defaults={'type_code': 'ligand'})
        SeqModule.objects.get_or_create(keyword='Am', defaults={'base_char': 'A', 'linker_connector': 'o'})

    def test_build_combo_re_accepts_preloaded_modules(self):
        """build_combo_re should accept dm_modules and sm_modules without querying DB."""
        from app01.views import build_combo_re
        dm = list(DeliveryModule.objects.all())
        sm = list(SeqModule.objects.all())
        with patch.object(DeliveryModule.objects.__class__, 'all') as mock_dm, \
             patch.object(SeqModule.objects.__class__, 'all') as mock_sm:
            result = build_combo_re(dm_modules=dm, sm_modules=sm)
            mock_dm.assert_not_called()
            mock_sm.assert_not_called()
        import re
        self.assertIsInstance(result, re.Pattern)

    def test_normalize_accepts_prebuilt_combo_re(self):
        """normalize_tmp_seq_with_combo should not query DB when combo_re is provided."""
        from app01.views import build_combo_re, normalize_tmp_seq_with_combo
        combo_re = build_combo_re()
        with patch('app01.views.build_combo_re') as mock_build:
            result = normalize_tmp_seq_with_combo('AmUmGmCm', combo_re=combo_re)
            mock_build.assert_not_called()
        self.assertIsInstance(result, str)
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
python manage.py test app01.tests.BuildComboReTests -v 2
```

Expected: FAIL — `build_combo_re` doesn't accept keyword args yet.

- [ ] **Step 3: Update `build_combo_re` signature in `app01/views.py`**

Find `def build_combo_re():` (~line 1735). Replace with:

```python
def build_combo_re(dm_modules=None, sm_modules=None):
    """
    构造 combo_re，用于匹配形如:
      <LEFT>-<module.keyword>
    LEFT 侧从 SeqModule 动态读取，RIGHT 侧从 DeliveryModule 动态读取。
    dm_modules / sm_modules 可由调用方预加载传入，避免重复查询 DB。
    """
    if dm_modules is None:
        dm_modules = list(DeliveryModule.objects.all())
    if sm_modules is None:
        sm_modules = list(SeqModule.objects.all())

    dm_keywords = sorted(
        [m.keyword.strip() for m in dm_modules if m.keyword and m.keyword.strip()],
        key=len, reverse=True,
    )
    dm_pattern = "|".join(re.escape(k) for k in dm_keywords) if dm_keywords else r"(?!x)x"

    sm_keywords = sorted(
        [m.keyword.strip() for m in sm_modules if m.keyword and m.keyword.strip()],
        key=len, reverse=True,
    )
    sm_pattern = "|".join(re.escape(k) for k in sm_keywords) if sm_keywords else r"(?!x)x"

    left_extras = r'INVAB|I|ss|s|o|[ACGUT]'
    left_token_pat = rf"(?:{sm_pattern}|{left_extras})"

    combo_re = re.compile(rf'({left_token_pat})-({dm_pattern})', re.IGNORECASE)
    return combo_re
```

- [ ] **Step 4: Update `normalize_tmp_seq_with_combo` signature in `app01/views.py`**

Find `def normalize_tmp_seq_with_combo(modify_seq: str) -> str:` (~line 1761). Replace signature and first line:

```python
def normalize_tmp_seq_with_combo(modify_seq: str, combo_re=None) -> str:
    """
    先把 modify_seq upper，然后把 combo（LEFT-keyword）展开成 LEFT（保留原样，不做碱基映射）
    combo_re 可由调用方预加载（build_combo_re() 的返回值）以避免重复查询 DB。
    """
    tmp_seq = (modify_seq or "").upper()
    if combo_re is None:
        combo_re = build_combo_re()
```

- [ ] **Step 5: Update `run_preflight_check` to pre-load and share**

Find `def run_preflight_check(df, ss_groups):` (~line 1303). The function already pre-loads `_sm_list`. Add module pre-loading near the top of the function (after the existing `_sm_list` loading) and pass to the `normalize_tmp_seq_with_combo` calls:

Find within `run_preflight_check` the places where `normalize_tmp_seq_with_combo` is called. Add at the top of the function, after `_sm_list`:

```python
    # Pre-load for build_combo_re (avoid per-row DB queries)
    _dm_modules = list(DeliveryModule.objects.all())
    _sm_modules_all = list(SeqModule.objects.all())
    _combo_re = build_combo_re(dm_modules=_dm_modules, sm_modules=_sm_modules_all)
```

Then find each call to `normalize_tmp_seq_with_combo(...)` inside the function and pass `combo_re=_combo_re`:

```python
# BEFORE (two occurrences in run_preflight_check):
            tmp = normalize_tmp_seq_with_combo(clean_seq)

# AFTER:
            tmp = normalize_tmp_seq_with_combo(clean_seq, combo_re=_combo_re)
```

- [ ] **Step 6: Run tests to confirm they pass**

```bash
python manage.py test app01.tests.BuildComboReTests -v 2
```

Expected: both tests PASS.

- [ ] **Step 7: Run full test suite**

```bash
python manage.py test app01 -v 2
```

Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "perf: build_combo_re and normalize_tmp_seq_with_combo accept pre-loaded modules to avoid N+1 DB queries

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6: URL-01/02 — Unnamed Root URL + Duplicate Register Route

**Files:**
- Modify: `bms/urls.py`

**Background:**
- `path('', views.login_view)` has no `name=` — can't be referenced by `{% url %}` in templates
- `path('signup/', ...)` and `path('register/', ...)` both point to `register_view` — redundant; `signup/` is not used anywhere in templates

- [ ] **Step 1: Check that `signup` is not referenced anywhere**

```bash
grep -r "signup" templates/ app01/ bms/ --include="*.html" --include="*.py" | grep -v ".pyc"
```

Expected: no results (or only the url pattern itself). If any template uses `{% url 'signup' %}`, update those references to `{% url 'register' %}` first.

- [ ] **Step 2: Edit `bms/urls.py`**

Find lines 25–28:

```python
# BEFORE:
    path('', views.login_view),                          # 根路径 → 登录页面
    path('login/', views.login_view, name='login'),      # 登录动作
    path('signup/', views.register_view, name='signup'),     # 用户注册页面
    path('register/', views.register_view, name='register'),     # 用户注册页面

# AFTER:
    path('', views.login_view, name='root'),             # 根路径 → 登录页面
    path('login/', views.login_view, name='login'),      # 登录动作
    path('register/', views.register_view, name='register'),     # 用户注册页面
```

(Remove the `signup/` line entirely.)

- [ ] **Step 3: Verify the app still starts**

```bash
python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Run full test suite**

```bash
python manage.py test app01 -v 2
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add bms/urls.py
git commit -m "fix: add name='root' to root URL; remove duplicate signup/ route

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 7: MODEL-03 — Add TODO Comment to `permissions_project`

**Files:**
- Modify: `app01/models.py` — add comment above `permissions_project` field

**Background:** `LmsUser.permissions_project` stores comma-separated project codes in a `CharField`. This is known technical debt. A full migration to `ManyToManyField` is out of scope now; this task records the intent.

- [ ] **Step 1: Add TODO comment in `app01/models.py`**

Find the `permissions_project` field (~line 167):

```python
    permissions_project = models.CharField(
        '可查看的项目号',
        max_length=256,
        null=True,
        blank=True
    )
```

Add a comment above it:

```python
    # TODO: permissions_project 应迁移为 ManyToManyField(ProjectCode) 以支持索引查询。
    # 当前实现：逗号分隔字符串，解析逻辑见 get_allowed_projects()。
    # 迁移时须同步更新 get_permitted_delivery_qs()、edit_author view 和 auth_list.html。
    permissions_project = models.CharField(
        '可查看的项目号',
        max_length=256,
        null=True,
        blank=True
    )
```

- [ ] **Step 2: Verify no migration is generated**

```bash
python manage.py makemigrations --check
```

Expected: `No changes detected` (comments don't trigger migrations).

- [ ] **Step 3: Commit**

```bash
git add app01/models.py
git commit -m "docs: add TODO comment for permissions_project ManyToMany migration

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Final Steps

- [ ] **Run the full test suite one last time**

```bash
python manage.py test app01 -v 2
```

Expected: all tests PASS.

- [ ] **Run system check**

```bash
python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Manual smoke test**

1. Upload a CSV where AS rows appear before SS rows — confirm both are correctly paired and uploaded
2. Upload two different sequences that share the same delivery5/3 — confirm both are saved (BUG-03)
3. Go to `/reg_seq_list/` — navigate to page 2 — confirm only page-2 records appear
4. Log in as Y2325 — confirm the default strand direction is AS (not SS)
5. Navigate to `/module_list/` page 2 with `q=LP` — edit a module — confirm redirect preserves page=2 and q=LP (from Batch 1, regression check)
