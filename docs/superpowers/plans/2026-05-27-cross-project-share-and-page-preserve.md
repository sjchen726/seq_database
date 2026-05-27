# Cross-Project Share Fix + Page Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two bugs: (1) sequences already in project 350 are silently skipped instead of triggering a cross-project share confirmation when uploaded to project 3T03; (2) after editing a sequence from search results, the user is dropped to page 1 instead of the page where the sequence appeared.

**Architecture:** Bug 1 — swap the duplicate-detection DB query key in `check_duplicates()` from `linker_seq` (format-sensitive) to `sequence__seq` (stable naked nucleotide string), after extracting a shared `extract_naked_seq()` helper. Bug 2 — make the seq_type selector preserve `dt_page` in its GET request, and ensure `tables.js` updates edit-link `dt_page` immediately on init rather than waiting for the first draw event.

**Tech Stack:** Django 5.1, Python 3.10, jQuery DataTables, existing `app01/tests.py` (Django TestCase).

---

## File Map

| File | What changes |
|------|-------------|
| `app01/views.py` | Add `extract_naked_seq()` helper; rewrite DB query in `check_duplicates()` |
| `app01/tests.py` | Add `CheckDuplicatesTests` class |
| `templates/seq_list.html` | Seq-type selector JS preserves `dt_page` |
| `static/js/tables.js` | Run `updateEditLinkDtPage()` on DOM-ready, not only on draw |

---

## Task 1: Extract `extract_naked_seq()` helper in `views.py`

The naked-seq computation is currently duplicated inline inside `run_preflight_check` and `save_deliveries`. Extract it to a module-level function so `check_duplicates` can use it without duplicating SeqModule DB calls.

**Files:**
- Modify: `app01/views.py` (add function near line 1699, alongside `normalize_tmp_seq_with_combo`)

- [ ] **Step 1: Locate insertion point**

Open `app01/views.py`. Find the function `normalize_tmp_seq_with_combo` (around line 1699). The new helper goes immediately after it.

- [ ] **Step 2: Add `extract_naked_seq()` helper**

Insert after `normalize_tmp_seq_with_combo` (after its closing line):

```python
def extract_naked_seq(clean_seq: str, sm_map: dict, sm_norm_re) -> str:
    """
    Derive the bare nucleotide sequence (AUGCI only) from a clean modify_seq
    (brackets already stripped). Uses the caller-preloaded SeqModule map/regex
    to avoid repeated DB hits.

    Args:
        clean_seq:   modify_seq with leading/trailing [...] already removed.
        sm_map:      {keyword.upper(): base_char} from SeqModule.
        sm_norm_re:  compiled regex of SeqModule keywords (or None if empty).

    Returns:
        Bare nucleotide string, e.g. "AUGCAUGC".
    """
    tmp = normalize_tmp_seq_with_combo(clean_seq)
    if sm_norm_re:
        tmp = sm_norm_re.sub(lambda m: sm_map[m.group(0).upper()], tmp)
    tmp = re.sub(r'\(.*?\)', '', tmp)
    return ''.join(re.findall(r'(INVAB|[AUGCI])', tmp))
```

- [ ] **Step 3: Run existing tests to confirm nothing broke**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2
source venv/bin/activate
python manage.py test app01 --verbosity=2 2>&1 | tail -20
```

Expected: all existing tests still pass (no failures).

- [ ] **Step 4: Commit**

```bash
git add app01/views.py
git commit -m "refactor: extract extract_naked_seq() helper from inline duplication"
```

---

## Task 2: Fix `check_duplicates()` — use naked_seq for DB matching

Replace the `linker_seq`-based filter with `sequence__seq` (naked nucleotides), which is immune to normalisation format differences between old and new uploads.

**Files:**
- Modify: `app01/views.py` — `check_duplicates()` function (lines ~1560–1648)

- [ ] **Step 1: Preload SeqModule at the top of `check_duplicates()`**

Find `def check_duplicates(df, ss_groups, target_project=None):` and replace the opening block up to (but not including) `seen_combinations = set()`:

```python
def check_duplicates(df, ss_groups, target_project=None):
    repeated_ids = set()
    duplicate_meg = []
    cross_project_duplicates = []

    # Preload SeqModule once for naked_seq computation
    _sm_list = sorted(
        SeqModule.objects.filter(base_char__isnull=False).exclude(base_char=''),
        key=lambda m: len(m.keyword), reverse=True,
    )
    _sm_map = {m.keyword.upper(): m.base_char for m in _sm_list}
    _sm_norm_re = (
        re.compile('|'.join(re.escape(m.keyword) for m in _sm_list), re.IGNORECASE)
        if _sm_list else None
    )

    seen_combinations = set()
```

- [ ] **Step 2: Replace the DB query block inside `check_duplicates()`**

Find this block (around line 1607–1646):

```python
                # 2️⃣ 与数据库查重
                ss_linker_seq = add_o_to_all_rules_safe(ss_clean_seq)
                ss_deliveries = Delivery.objects.filter(
                    linker_seq=ss_linker_seq,
                    delivery5=ss_d5,
                    delivery3=ss_d3
                ).prefetch_related('project_links')
                as_linker_seq = add_o_to_all_rules_safe(as_clean_seq)

                for ss_del in ss_deliveries:
                    exists_as = Delivery.objects.filter(
                        linker_seq=as_linker_seq,
                        delivery5=as_d5,
                        delivery3=as_d3,
                        duplex_id=ss_del.duplex_id
                    ).exists()
```

Replace with:

```python
                # 2️⃣ 与数据库查重 — 用裸序列匹配，避免 linker_seq 格式化差异导致漏检
                ss_naked = extract_naked_seq(ss_clean_seq, _sm_map, _sm_norm_re)
                as_naked = extract_naked_seq(as_clean_seq, _sm_map, _sm_norm_re)

                if not ss_naked or not as_naked:
                    # Empty naked seq means all-unknown tokens — skip silently
                    continue

                ss_deliveries = Delivery.objects.filter(
                    sequence__seq=ss_naked,
                    delivery5=ss_d5,
                    delivery3=ss_d3,
                ).prefetch_related('project_links')

                for ss_del in ss_deliveries:
                    exists_as = Delivery.objects.filter(
                        sequence__seq=as_naked,
                        delivery5=as_d5,
                        delivery3=as_d3,
                        duplex_id=ss_del.duplex_id,
                    ).exists()
```

- [ ] **Step 3: Run existing tests**

```bash
python manage.py test app01 --verbosity=2 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add app01/views.py
git commit -m "fix: check_duplicates uses naked_seq instead of linker_seq for robust cross-project detection"
```

---

## Task 3: Write tests for `check_duplicates()` cross-project logic

Add a `CheckDuplicatesTests` class to `app01/tests.py` that covers the three paths: same-project duplicate, cross-project duplicate, and new sequence.

**Files:**
- Modify: `app01/tests.py`

- [ ] **Step 1: Add imports at the top of `app01/tests.py`**

Find the existing imports at the top of `app01/tests.py`:

```python
from app01.models import Sequence, SeqModule, DeliveryModule
from app01.views import normalize_middle_brackets, run_preflight_check, group_sequences, auto_register_bare_sequences
from app01.models import DuplexRelationship, SeqInfo
```

Replace with:

```python
from app01.models import Sequence, SeqModule, DeliveryModule, Delivery, DeliveryProject
from app01.views import (
    normalize_middle_brackets, run_preflight_check, group_sequences,
    auto_register_bare_sequences, check_duplicates,
)
from app01.models import DuplexRelationship, SeqInfo
```

- [ ] **Step 2: Add `CheckDuplicatesTests` class at the end of `app01/tests.py`**

```python
class CheckDuplicatesTests(TestCase):
    """Tests for check_duplicates() cross-project and same-project detection."""

    def setUp(self):
        # Minimal SeqModule entries so extract_naked_seq works (Am→A, Um→U, Gm→G, Cm→C)
        for kw, base in [('Am', 'A'), ('Um', 'U'), ('Gm', 'G'), ('Cm', 'C')]:
            SeqModule.objects.create(keyword=kw, base_char=base, linker_connector='o')

        # Register SS and AS bare sequences
        self.ss_seq = Sequence.objects.create(seq='AUGCAU', seq_type='SS')
        self.as_seq = Sequence.objects.create(seq='AUGCAU', seq_type='AS')

        # Create a Delivery in project BPR-350
        self.delivery_ss = Delivery.objects.create(
            sequence=self.ss_seq,
            duplex_id='BP000001',
            seq_type='SS',
            delivery5='invAb',
            delivery3='Vp',
            modify_seq='AmUmGmCmAmUm',
            linker_seq='AoUoGoCoAoU',
            project='BPR-350',
        )
        self.delivery_as = Delivery.objects.create(
            sequence=self.as_seq,
            duplex_id='BP000001',
            seq_type='AS',
            delivery5='Vp',
            delivery3='invAb',
            modify_seq='AmUmGmCmAmUm',
            linker_seq='AoUoGoCoAoU',
            project='BPR-350',
        )
        # Wire up DeliveryProject so 350 is visible
        DeliveryProject.objects.create(delivery=self.delivery_ss, project_code='BPR-350')
        DeliveryProject.objects.create(delivery=self.delivery_as, project_code='BPR-350')

    def _make_df(self, project, ss_seq, as_seq):
        """Build a minimal upload DataFrame for one SS+AS pair."""
        import pandas as pd
        rows = [
            {
                'Project': project,
                'Seq_type': 'SS',
                'Modify_seq': f'[invAb]{ss_seq}[Vp]',
                '__row_id': 0,
                '__original_line': 2,
            },
            {
                'Project': project,
                'Seq_type': 'AS',
                'Modify_seq': f'[Vp]{as_seq}[invAb]',
                '__row_id': 1,
                '__original_line': 3,
            },
        ]
        df = pd.DataFrame(rows)
        df.index = df['__row_id'].astype(int)
        return df

    def _make_ss_groups(self, df):
        """Pair rows 0+1 as one SS+AS group."""
        return [(None, df.iloc[0]['Project'], [0, 1])]

    def test_same_project_duplicate_goes_to_repeated_ids(self):
        """Uploading same (naked_seq, d5, d3) to same project → repeated_ids, not cross."""
        df = self._make_df('BPR-350', 'AmUmGmCmAmUm', 'AmUmGmCmAmUm')
        ss_groups = self._make_ss_groups(df)
        repeated_ids, duplicate_meg, cross = check_duplicates(df, ss_groups, target_project='BPR-350')
        self.assertIn(0, repeated_ids)
        self.assertIn(1, repeated_ids)
        self.assertEqual(cross, [])
        self.assertTrue(len(duplicate_meg) > 0)

    def test_cross_project_duplicate_triggers_share_list(self):
        """Uploading same (naked_seq, d5, d3) to different project → cross_project_duplicates."""
        df = self._make_df('BPR-3T03', 'AmUmGmCmAmUm', 'AmUmGmCmAmUm')
        ss_groups = self._make_ss_groups(df)
        repeated_ids, duplicate_meg, cross = check_duplicates(df, ss_groups, target_project='BPR-3T03')
        self.assertEqual(repeated_ids, set())
        self.assertEqual(duplicate_meg, [])
        self.assertEqual(len(cross), 1)
        self.assertEqual(cross[0]['existing_duplex_id'], 'BP000001')
        self.assertEqual(cross[0]['target_project'], 'BPR-3T03')

    def test_new_sequence_not_in_db_no_duplicate(self):
        """A truly new (naked_seq, d5, d3) not in DB → nothing flagged."""
        df = self._make_df('BPR-3T03', 'AmGmCmUmAmUm', 'AmGmCmUmAmUm')
        ss_groups = self._make_ss_groups(df)
        repeated_ids, duplicate_meg, cross = check_duplicates(df, ss_groups, target_project='BPR-3T03')
        self.assertEqual(repeated_ids, set())
        self.assertEqual(duplicate_meg, [])
        self.assertEqual(cross, [])

    def test_linker_seq_format_difference_still_detected(self):
        """Even if stored linker_seq differs from computed, naked_seq match catches it."""
        # Modify the stored linker_seq to a deliberately different format
        self.delivery_ss.linker_seq = 'DIFFERENT_FORMAT'
        self.delivery_ss.save()
        self.delivery_as.linker_seq = 'DIFFERENT_FORMAT'
        self.delivery_as.save()
        # Should still detect cross-project via naked_seq
        df = self._make_df('BPR-3T03', 'AmUmGmCmAmUm', 'AmUmGmCmAmUm')
        ss_groups = self._make_ss_groups(df)
        repeated_ids, duplicate_meg, cross = check_duplicates(df, ss_groups, target_project='BPR-3T03')
        self.assertEqual(len(cross), 1, "Should detect cross-project even with mismatched linker_seq")
```

- [ ] **Step 3: Run the new tests — they should fail (before fix) or pass (after fix)**

```bash
python manage.py test app01.tests.CheckDuplicatesTests --verbosity=2 2>&1 | tail -30
```

Expected: All 4 tests pass (the fix from Task 2 is already in place).

If `test_linker_seq_format_difference_still_detected` **fails**, the fix is not complete — go back to Task 2 and verify the query uses `sequence__seq`, not `linker_seq`.

- [ ] **Step 4: Run full test suite**

```bash
python manage.py test app01 --verbosity=2 2>&1 | tail -20
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add app01/tests.py
git commit -m "test: add CheckDuplicatesTests for cross-project and same-project duplicate paths"
```

---

## Task 4: Fix seq-type selector — preserve `dt_page` on switch

When the user toggles the SS/AS display direction, the GET request must carry the current DataTables page index so the table resumes on the same page.

**Files:**
- Modify: `templates/seq_list.html` — the `seq_type_selector` change handler (around line 275)

- [ ] **Step 1: Replace the change handler**

Find this block in `seq_list.html`:

```javascript
document.getElementById('seq_type_selector').addEventListener('change', function () {
    const selectedType = this.value;
    const url = new URL(window.location.href);
    url.searchParams.set('seq_type', selectedType);
    window.location.href = url.toString();
});
```

Replace with:

```javascript
document.getElementById('seq_type_selector').addEventListener('change', function () {
    const selectedType = this.value;
    const url = new URL(window.location.href);
    url.searchParams.set('seq_type', selectedType);
    // Preserve current DataTables page so user returns to same position after switch
    try {
        if (window.table) {
            url.searchParams.set('dt_page', window.table.page());
        }
    } catch (e) { /* table not ready, ignore */ }
    window.location.href = url.toString();
});
```

- [ ] **Step 2: Manual verification**

1. Start server: `python manage.py runserver`
2. Go to the sequence list, navigate to page 2 of results
3. Toggle the SS/AS selector — the page should reload but remain on page 2
4. Confirm URL contains `dt_page=1` (0-indexed)

- [ ] **Step 3: Commit**

```bash
git add templates/seq_list.html
git commit -m "fix: seq_type selector preserves dt_page on direction switch"
```

---

## Task 5: Fix edit-link `dt_page` — update immediately on init, not only on draw

`tables.js` currently injects `dt_page` into edit links only inside the `draw` event. If the user clicks an edit link before the first draw event fires (which happens on `table.page(N).draw(false)` call), the link may still carry the server-rendered value (no `dt_page`).

**Files:**
- Modify: `static/js/tables.js` — add an immediate link update after table init

- [ ] **Step 1: Add a named helper function and call it immediately**

In `tables.js`, find the `table.on('draw', ...)` block that updates edit/cor links (around line 140). It currently looks like:

```javascript
    // 每次重绘后，确保编辑/关联链接包含当前页码参数 dt_page
    table.on('draw', function() {
        try {
            const currentPage = table.page(); // 0-based
            // 编辑链接
            $('#example a[href*="/edit_seq/"]').each(function() {
```

Extract the link-update logic into a named function, and call it both on draw and immediately after init:

Replace the entire `table.on('draw', ...)` block (for link updating only — keep the second `table.on('draw', ...)` block for highlights) with:

```javascript
    // ── Edit/cor link dt_page updater ──────────────────────────────────────
    function updateEditLinkDtPage() {
        try {
            const currentPage = table.page(); // 0-based
            $('#example a[href*="/edit_seq/"]').each(function() {
                const $a = $(this);
                const url = new URL($a.prop('href'), window.location.origin);
                url.searchParams.set('dt_page', currentPage);
                $a.prop('href', url.toString());
            });
            $('#example a[href*="/cor_seq/"]').each(function() {
                const $a = $(this);
                const url = new URL($a.prop('href'), window.location.origin);
                url.searchParams.set('dt_page', currentPage);
                $a.prop('href', url.toString());
            });
            // Mirror current page into browser URL bar
            try {
                const curUrl = new URL(window.location.href);
                curUrl.searchParams.set('dt_page', currentPage);
                window.history.replaceState({}, document.title, curUrl.toString());
            } catch (e) {
                console.warn('update URL dt_page failed', e);
            }
        } catch (e) {
            console.warn('append dt_page failed', e);
        }
    }

    // Run on every redraw
    table.on('draw', updateEditLinkDtPage);
```

Then, inside `initDrawWithDtPage()` (around line 244), after `table.page(pageIndex).draw(false)` and after the default `table.draw()`, add a call to `updateEditLinkDtPage()`:

Find:

```javascript
    (function initDrawWithDtPage() {
        try {
            const params = new URLSearchParams(window.location.search);
            const dtPage = params.get('dt_page');
            if (dtPage !== null) {
                const pageIndex = parseInt(dtPage, 10);
                if (!isNaN(pageIndex)) {
                    table.page(pageIndex).draw(false);
                    return;
                }
            }
        } catch (e) {
            console.warn('读取 dt_page 失败', e);
        }

        // 默认绘制第一页
        table.draw();
    })();
```

Replace with:

```javascript
    (function initDrawWithDtPage() {
        try {
            const params = new URLSearchParams(window.location.search);
            const dtPage = params.get('dt_page');
            if (dtPage !== null) {
                const pageIndex = parseInt(dtPage, 10);
                if (!isNaN(pageIndex)) {
                    table.page(pageIndex).draw(false);
                    updateEditLinkDtPage(); // inject dt_page into links immediately
                    return;
                }
            }
        } catch (e) {
            console.warn('读取 dt_page 失败', e);
        }

        // 默认绘制第一页
        table.draw();
        updateEditLinkDtPage(); // inject dt_page=0 into links immediately
    })();
```

- [ ] **Step 2: Manual verification**

1. Go to sequence list, search for something, navigate to page 2 of results
2. Hover over an edit link — verify `dt_page=1` is in the URL (browser status bar)
3. Click edit, make any change (or just save)
4. Confirm return lands on page 2 of the same search results

- [ ] **Step 3: Commit**

```bash
git add static/js/tables.js
git commit -m "fix: update edit link dt_page immediately on init, not only on draw event"
```

---

## Self-Review

**Spec coverage:**
- ✅ Feature 4 root cause (linker_seq mismatch) → Tasks 1 + 2
- ✅ Feature 4 test coverage → Task 3 (4 test cases including the regression test for linker_seq format difference)
- ✅ Feature 4 confirm_share flow unchanged (spec says keep existing behaviour) → no tasks needed
- ✅ Feature 2 seq_type switch → Task 4
- ✅ Feature 2 edit link dt_page timing → Task 5
- ✅ Feature 2 cancel/return in seq_edit.html — already uses `next` URL correctly (verified in codebase exploration); no task needed

**Placeholder scan:** No TBD, TODO, or vague steps found. All code blocks are complete.

**Type consistency:**
- `extract_naked_seq(clean_seq, sm_map, sm_norm_re)` — defined in Task 1, called identically in Task 2 ✅
- `updateEditLinkDtPage()` — defined and called in Task 5 only ✅
- `check_duplicates` import added to tests in Task 3 Step 1 before use in Step 2 ✅
- `Delivery`, `DeliveryProject` model imports added in Task 3 Step 1 before use in setUp ✅
