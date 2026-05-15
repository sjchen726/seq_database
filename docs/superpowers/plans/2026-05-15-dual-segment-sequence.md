# Dual-Segment Sequence (sequence-linker-sequence) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support modify_seq strings containing an embedded linker (e.g. `-LK1-L96-LK1-` or `------------`) that divides the sequence into Part1 and Part2, with correct linker_seq generation and column-by-column Part1↔Part1 / Part2↔Part2 alignment in seq_list.

**Architecture:** Add `detect_embedded_linker()` as the central detection helper; gate all dual-segment logic behind it so single-segment sequences are entirely unaffected. `add_o_to_all_rules_safe()` splits the string before converting, `get_modify_seq_colored()` inserts SEP tokens between segments, and `build_duplex_groups()` uses `split_tokens_at_sep()` to align each segment pair independently.

**Tech Stack:** Django 5.1, Python 3.10, MySQL, Django templates (no JS changes).

**Reference spec:** `docs/superpowers/specs/2026-05-15-dual-segment-sequence-design.md`

**No test suite exists** — verification is manual (run dev server, upload CSV, inspect page).

---

## File Structure

| File | What changes |
|---|---|
| `app01/views.py` | Add 4 helpers + modify 3 existing functions |
| `templates/_seq_group_row.html` | Handle `segment_sep` col + SEP/LINKER_DASH tokens in 2 render loops |

---

### Task 1: Add `detect_embedded_linker()` helper

**Files:**
- Modify: `app01/views.py` — insert before the `def _filter_delivery_qs_by_term(` line

- [ ] **Step 1: Find insertion point**

  In `app01/views.py`, search for the line `def _filter_delivery_qs_by_term(`. The new function goes immediately before it.

- [ ] **Step 2: Insert `detect_embedded_linker()`**

  Add this block immediately before `def _filter_delivery_qs_by_term(`:

  ```python
  def detect_embedded_linker(modify_seq: str):
      """
      Returns (part1, linker_section, part2) if modify_seq contains an embedded linker,
      or None for normal single-segment sequences.

      Detects:
      - 2+ consecutive SeqModule tokens with linker_connector='-' (e.g. -LK1-L96-LK1-)
      - 4+ consecutive dashes (AS placeholder, e.g. ------------)
      Both sides of the match must be non-empty.
      """
      linker_keywords = [
          m.keyword for m in SeqModule.objects.filter(linker_connector='-')
          if m.keyword
      ]
      patterns = []
      if linker_keywords:
          kw_pat = '|'.join(re.escape(k) for k in sorted(linker_keywords, key=len, reverse=True))
          # Require ≥2 consecutive linker tokens to avoid matching single Um-LK1 combos
          patterns.append(rf'-(?:{kw_pat})(?:-(?:{kw_pat}))+-')
      patterns.append(r'-{4,}')

      m = re.search('|'.join(patterns), modify_seq)
      if not m:
          return None
      part1 = modify_seq[:m.start()]
      linker_section = m.group(0)
      part2 = modify_seq[m.end():]
      if not part1.strip() or not part2.strip():
          return None
      return part1, linker_section, part2
  ```

- [ ] **Step 3: Verify syntax**

  ```bash
  cd /Users/gutou/Projects/seq_web/seq_database_v2
  source venv/bin/activate
  python -c "from app01.views import detect_embedded_linker; print('OK')"
  ```

  Expected: `OK`

- [ ] **Step 4: Quick manual test in Django shell**

  ```bash
  python manage.py shell
  ```

  ```python
  from app01.views import detect_embedded_linker

  # SS case — should split at -LK1-L96-LK1-
  ss = "GnsGmsCmUmUmUmCfUmGfCfAmUmCmAmGmAmCmAmsUmsUm-LK1-L96-LK1-UmsCmsCmUmCmUmGfAmUfGfGfUmCmAmAmAmGmUmCmsCmsUm"
  result = detect_embedded_linker(ss)
  assert result is not None, "SS should detect embedded linker"
  p1, lk, p2 = result
  assert p1 == "GnsGmsCmUmUmUmCfUmGfCfAmUmCmAmGmAmCmAmsUmsUm", f"part1 wrong: {p1}"
  assert lk == "-LK1-L96-LK1-", f"linker wrong: {lk}"
  assert p2 == "UmsCmsCmUmCmUmGfAmUfGfGfUmCmAmAmAmGmUmCmsCmsUm", f"part2 wrong: {p2}"

  # AS case — should split at dashes
  as_ = "AnsGfsGmAmCmUfUmUfGfAmCmCmAmUfCmAfGmAmGmsGmsAm------------AmsAfsUmGmdUCmdUGmAmUmGmGmCmAfG"
  result2 = detect_embedded_linker(as_)
  assert result2 is not None, "AS should detect embedded linker"
  p1b, lkb, p2b = result2
  assert lkb == "------------", f"dash linker wrong: {lkb}"

  # Normal single-segment — must return None
  normal = "GmsCmUmUmUmCfUmGf"
  assert detect_embedded_linker(normal) is None, "Single-segment should return None"

  # Single combo Um-LK1 — must return None (only 1 linker token)
  combo = "GnsGmUm-LK1"
  assert detect_embedded_linker(combo) is None, "Single combo should return None"

  print("All assertions passed")
  ```

  Expected: `All assertions passed`

- [ ] **Step 5: Commit**

  ```bash
  git add app01/views.py
  git commit -m "feat: add detect_embedded_linker() helper for dual-segment sequences"
  ```

---

### Task 2: Add `add_o_to_all_rules_safe()` wrapper

**Files:**
- Modify: `app01/views.py` — insert immediately after `detect_embedded_linker()` (just added in Task 1)

- [ ] **Step 1: Insert function**

  Add immediately after the `detect_embedded_linker()` function:

  ```python
  def add_o_to_all_rules_safe(modify_seq: str) -> str:
      """
      Dual-segment-aware wrapper for add_o_to_all_rules().
      For sequences with an embedded linker, processes Part1 and Part2 separately
      so the linker section keeps its own '-' connectors and is not corrupted.
      """
      parts = detect_embedded_linker(modify_seq or "")
      if parts is None:
          return add_o_to_all_rules(modify_seq)
      part1, linker_section, part2 = parts
      return add_o_to_all_rules(part1) + linker_section + add_o_to_all_rules(part2)
  ```

- [ ] **Step 2: Verify syntax**

  ```bash
  python -c "from app01.views import add_o_to_all_rules_safe; print('OK')"
  ```

  Expected: `OK`

- [ ] **Step 3: Quick manual test in Django shell**

  ```bash
  python manage.py shell
  ```

  ```python
  from app01.views import add_o_to_all_rules_safe

  # SS case — the junction UmsUm + -LK1-L96-LK1- must not get a spurious 'o'
  ss = "GnsGmsCmUmUmUmCfUmGfCfAmUmCmAmGmAmCmAmsUmsUm-LK1-L96-LK1-UmsCmsCmUm"
  result = add_o_to_all_rules_safe(ss)
  # Must contain the linker section unmodified
  assert "-LK1-L96-LK1-" in result, f"Linker missing in: {result}"
  # Must NOT contain 'LK1o' (the bug we're fixing)
  assert "LK1o" not in result, f"Spurious 'o' found: {result}"
  print("linker_seq:", result)

  # Normal single-segment — must behave identically to add_o_to_all_rules()
  from app01.views import add_o_to_all_rules
  normal = "GmsCmUmUmCfUm"
  assert add_o_to_all_rules_safe(normal) == add_o_to_all_rules(normal), "Single-segment mismatch"

  print("All assertions passed")
  ```

  Expected: `All assertions passed` and the printed linker_seq contains `-LK1-L96-LK1-` without `LK1o`.

- [ ] **Step 4: Commit**

  ```bash
  git add app01/views.py
  git commit -m "feat: add add_o_to_all_rules_safe() for dual-segment linker_seq"
  ```

---

### Task 3: Fix `save_deliveries()` call sites

**Files:**
- Modify: `app01/views.py` — two lines inside `save_deliveries()`

- [ ] **Step 1: Replace first call (dedup key)**

  Find this line in `save_deliveries()`:
  ```python
  current_linker_seq = add_o_to_all_rules(item['modify_seq'])
  ```
  Replace with:
  ```python
  current_linker_seq = add_o_to_all_rules_safe(item['modify_seq'])
  ```

- [ ] **Step 2: Replace second call (`Delivery.objects.create`)**

  Find this line in the `Delivery.objects.create(...)` block:
  ```python
  linker_seq=add_o_to_all_rules(item['modify_seq']),
  ```
  Replace with:
  ```python
  linker_seq=add_o_to_all_rules_safe(item['modify_seq']),
  ```

- [ ] **Step 3: Verify no other callers remain**

  ```bash
  grep -n "add_o_to_all_rules(" app01/views.py
  ```

  Expected: only the `def add_o_to_all_rules(` definition line and the call inside `add_o_to_all_rules_safe()` itself. No bare call sites.

- [ ] **Step 4: Verify server starts**

  ```bash
  python manage.py runserver --noreload &
  sleep 3 && curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/login/
  kill %1
  ```

  Expected: `200`

- [ ] **Step 5: Commit**

  ```bash
  git add app01/views.py
  git commit -m "fix: use add_o_to_all_rules_safe in save_deliveries to fix dual-segment linker_seq"
  ```

---

### Task 4: Add `_SEP_TOKEN` + update `get_modify_seq_colored()`

**Files:**
- Modify: `app01/views.py` — line before `def get_modify_seq_colored(` and inside that function

`get_modify_seq_colored` is defined at approximately line 163. Its first line of body is `seq = seq or ""`.

- [ ] **Step 1: Add `_SEP_TOKEN` constant**

  Find the line `def get_modify_seq_colored(seq, selected_seq_type, seq_type, dm_modules=None, color_map=None):`.
  Insert this block **immediately before** that `def` line:

  ```python
  _SEP_TOKEN = {
      'char': '|', 'type': 'SEP', 'count': '',
      'is_combo': False, 'delivery_label': None, 'delivery_color': None,
  }
  ```

- [ ] **Step 2: Add dual-segment detection at top of `get_modify_seq_colored()`**

  The very first line of the function body is `seq = seq or ""`. Add the dual-segment block **before** that line (as the first thing in the function):

  ```python
  def get_modify_seq_colored(seq, selected_seq_type, seq_type, dm_modules=None, color_map=None):
      # Dual-segment detection: if modify_seq has an embedded linker, render each part
      # separately and insert SEP tokens as structural markers for alignment.
      parts = detect_embedded_linker(seq or "")
      if parts is not None:
          part1, linker_section, part2 = parts
          if dm_modules is None:
              dm_modules = list(DeliveryModule.objects.all())
          if color_map is None:
              color_map = get_color_map(modules=dm_modules)
          tokens1 = get_modify_seq_colored(part1, selected_seq_type, seq_type, dm_modules, color_map)
          tokens2 = get_modify_seq_colored(part2, selected_seq_type, seq_type, dm_modules, color_map)
          if re.fullmatch(r'-+', linker_section):
              # AS placeholder (e.g. "------------"): render as grey ···
              linker_tokens = [{'char': '···', 'type': 'LINKER_DASH', 'count': '',
                                'is_combo': False, 'delivery_label': None, 'delivery_color': None}]
          else:
              # SS: render linker tokens (LK1, L96 …) with their colours
              linker_tokens = get_modify_seq_colored(
                  linker_section.strip('-'), selected_seq_type, seq_type, dm_modules, color_map
              )
          return tokens1 + [_SEP_TOKEN] + linker_tokens + [_SEP_TOKEN] + tokens2

      # --- existing function body follows, unchanged ---
      seq = seq or ""
      ...
  ```

  **Important:** the existing `seq = seq or ""` line and everything below it stays exactly as-is.

- [ ] **Step 3: Verify syntax**

  ```bash
  python -c "from app01.views import get_modify_seq_colored; print('OK')"
  ```

  Expected: `OK`

- [ ] **Step 4: Manual test in Django shell**

  ```bash
  python manage.py shell
  ```

  ```python
  from app01.views import get_modify_seq_colored

  ss = "GnsGmsCmUmUmUmCfUmGfCfAmUmCmAmGmAmCmAmsUmsUm-LK1-L96-LK1-UmsCmsCmUm"
  tokens = get_modify_seq_colored(ss, 'SS', 'SS')

  sep_indices = [i for i, t in enumerate(tokens) if t['type'] == 'SEP']
  assert len(sep_indices) == 2, f"Expected 2 SEP tokens, got {sep_indices}"
  print(f"SEP at positions {sep_indices}")

  # Tokens between the two SEPs should be the linker tokens (LK1, L96, LK1)
  lk_tokens = tokens[sep_indices[0]+1:sep_indices[1]]
  lk_chars = [t['char'] for t in lk_tokens]
  print(f"Linker tokens: {lk_chars}")

  # AS case — linker should be LINKER_DASH type
  as_ = "AnsGfsGmAmCm------------AmsAfsUmGm"
  tokens_as = get_modify_seq_colored(as_, 'SS', 'AS')
  sep_idx = [i for i, t in enumerate(tokens_as) if t['type'] == 'SEP']
  assert len(sep_idx) == 2, "AS should also have 2 SEP tokens"
  dash_token = tokens_as[sep_idx[0]+1]
  assert dash_token['type'] == 'LINKER_DASH', f"Expected LINKER_DASH, got {dash_token['type']}"
  assert dash_token['char'] == '···', f"Expected ···, got {dash_token['char']}"

  # Single-segment — no SEP tokens
  normal = "GmsCmUmUmCfUm"
  tokens_n = get_modify_seq_colored(normal, 'SS', 'SS')
  assert all(t['type'] != 'SEP' for t in tokens_n), "Single-segment must not have SEP"

  print("All assertions passed")
  ```

  Expected: `All assertions passed`, `SEP at positions [N, M]`, and linker token chars printed.

- [ ] **Step 5: Commit**

  ```bash
  git add app01/views.py
  git commit -m "feat: get_modify_seq_colored handles dual-segment with SEP tokens"
  ```

---

### Task 5: Add `split_tokens_at_sep()` + update `build_duplex_groups()` alignment

**Files:**
- Modify: `app01/views.py` — insert `split_tokens_at_sep()` before `align_duplex_tokens()`, and update the alignment block inside `build_duplex_groups()`

- [ ] **Step 1: Add `split_tokens_at_sep()` before `align_duplex_tokens()`**

  Find the line `def align_duplex_tokens(row0_tokens, row1_tokens):`.
  Insert this block **immediately before** that `def` line:

  ```python
  def split_tokens_at_sep(tokens):
      """
      Split a token list at two SEP markers (inserted by get_modify_seq_colored for
      dual-segment sequences).  Returns (part1, linker_tokens, part2) or None if fewer
      than two SEP markers are present.
      """
      indices = [i for i, t in enumerate(tokens) if t.get('type') == 'SEP']
      if len(indices) < 2:
          return None
      i1, i2 = indices[0], indices[1]
      return tokens[:i1], tokens[i1+1:i2], tokens[i2+1:]
  ```

- [ ] **Step 2: Update alignment block in `build_duplex_groups()`**

  In `build_duplex_groups()`, find this existing block:

  ```python
          aligned = None
          if len(sorted_items) >= 2:
              aligned = align_duplex_tokens(
                  sorted_items[0].get('modify_seq_colored') or [],
                  sorted_items[1].get('modify_seq_colored') or [],
              )
  ```

  Replace it with:

  ```python
          aligned = None
          if len(sorted_items) >= 2:
              ss_tokens = sorted_items[0].get('modify_seq_colored') or []
              as_tokens = sorted_items[1].get('modify_seq_colored') or []
              ss_split = split_tokens_at_sep(ss_tokens)
              as_split = split_tokens_at_sep(as_tokens)
              if ss_split and as_split:
                  ss_p1, ss_lk, ss_p2 = ss_split
                  as_p1, as_lk, as_p2 = as_split
                  aligned = (
                      align_duplex_tokens(ss_p1, as_p1)
                      + [{'col_type': 'segment_sep', 'linker_tokens': ss_lk}]
                      + align_duplex_tokens(ss_p2, as_p2)
                  )
              else:
                  aligned = align_duplex_tokens(ss_tokens, as_tokens)
  ```

- [ ] **Step 3: Verify syntax**

  ```bash
  python -c "from app01.views import split_tokens_at_sep, build_duplex_groups; print('OK')"
  ```

  Expected: `OK`

- [ ] **Step 4: Commit**

  ```bash
  git add app01/views.py
  git commit -m "feat: split_tokens_at_sep + build_duplex_groups dual-segment alignment"
  ```

---

### Task 6: Update `_seq_group_row.html` template

**Files:**
- Modify: `templates/_seq_group_row.html`

There are **three** places to update:
1. SS row `{% for col in group.aligned_columns %}` loop — add `segment_sep` branch
2. AS row `{% for col in group.aligned_columns %}` loop — add `segment_sep` skip
3. Flat fallback `{% for item in group.items.0.modify_seq_colored %}` loop — add SEP/LINKER_DASH handling
4. CSS block

- [ ] **Step 1: SS row — add `segment_sep` branch**

  In the **first** `{% for col in group.aligned_columns %}` loop (the SS row, identified by the `align-dir-cell` containing `SS 3'`), find:

  ```html
                {% if col.col_type == 'linker' %}
  ```

  Add a new branch **before** this `{% if %}`:

  ```html
                {% if col.col_type == 'segment_sep' %}
                  <td class="seq-segment-sep-col" rowspan="2" style="vertical-align:middle;padding:0 6px;border-left:2px dashed #cbd5e1;border-right:2px dashed #cbd5e1;background:#f8fafc;">
                    {% for lk in col.linker_tokens %}
                      <span class="seq-container seq-wide" style="background-color:rgba(112,203,248,1);">{{ lk.char }}</span>
                    {% endfor %}
                  </td>
                {% elif col.col_type == 'linker' %}
  ```

  **Change the original `{% if col.col_type == 'linker' %}` to `{% elif col.col_type == 'linker' %}`** so the chain works:
  ```html
                {% if col.col_type == 'segment_sep' %}
                  ...
                {% elif col.col_type == 'linker' %}
                  ... (existing linker rendering, unchanged) ...
                {% else %}
                  ... (existing nuc rendering, unchanged) ...
                {% endif %}
  ```

- [ ] **Step 2: AS row — add `segment_sep` skip**

  In the **second** `{% for col in group.aligned_columns %}` loop (the AS row, identified by `AS 5'`), apply the same pattern but render **nothing** for `segment_sep` (the `<td rowspan="2">` from the SS row already covers this cell):

  ```html
                {% if col.col_type == 'segment_sep' %}
                  {# rowspan=2 td already rendered in SS row — skip here #}
                {% elif col.col_type == 'linker' %}
                  ... (existing linker rendering, unchanged) ...
                {% else %}
                  ... (existing nuc rendering, unchanged) ...
                {% endif %}
  ```

- [ ] **Step 3: Flat fallback — add SEP / LINKER_DASH handling**

  Find the flat fallback block (used when `not group.aligned_columns`):

  ```html
            <div style="display:flex;gap:0;">
              {% for item in group.items.0.modify_seq_colored %}
                <span class="seq-container {% if item.char == 's' or item.char == 'o' or item.char == 'ss' %}seq-narrow{% else %}seq-wide{% endif %}" style="background-color:...">{{ item.char }}</span>
              {% endfor %}
            </div>
  ```

  Replace the inner `<span>` line with a conditional block:

  ```html
            <div style="display:flex;gap:0;align-items:center;">
              {% for item in group.items.0.modify_seq_colored %}
                {% if item.type == 'SEP' %}
                  <span class="seq-seg-divider">&#124;</span>
                {% elif item.type == 'LINKER_DASH' %}
                  <span class="seq-linker-dash">{{ item.char }}</span>
                {% else %}
                  <span class="seq-container {% if item.char == 's' or item.char == 'o' or item.char == 'ss' %}seq-narrow{% else %}seq-wide{% endif %}" style="background-color:{% if item.type == 'normal' %}rgb(189,199,248){% elif item.type == 'f' %}rgb(22,245,22){% elif item.type == 'm' %}rgb(68,68,68);color:white{% elif item.type == 'd' or item.type == 'ss' or item.type == 'moe' or item.type == 'OCF3' or item.type == 'GNA' or item.type == 'I' %}rgb(212,93,245){% elif item.type == 's' %}rgb(253,246,61){% elif item.type == 'o' %}rgb(198,196,198){% elif item.type == 'TNA' %}rgb(245,86,86);color:white{% elif item.type == 'unknown' %}rgb(163,163,163){% elif item.type == 'others' %}rgba(112,203,248,1){% endif %};">{{ item.char }}</span>
                {% endif %}
              {% endfor %}
            </div>
  ```

- [ ] **Step 4: Add CSS**

  Find the existing `<style>` block in `_seq_group_row.html` (or any inline style section). Append:

  ```css
  .seq-seg-divider  { color: #94a3b8; margin: 0 4px; font-weight: bold; font-size: 14px; }
  .seq-linker-dash  { color: #94a3b8; letter-spacing: 1px; font-style: italic; padding: 0 2px; }
  .seq-segment-sep-col { background: #f8fafc; }
  ```

  If there is no `<style>` block in `_seq_group_row.html`, add these as a `<style>` tag at the top of the file.

- [ ] **Step 5: Commit**

  ```bash
  git add templates/_seq_group_row.html
  git commit -m "feat: _seq_group_row.html handles segment_sep columns and SEP/LINKER_DASH tokens"
  ```

---

### Task 7: Smoke test

**Files:** none — manual verification only

- [ ] **Step 1: Start dev server**

  ```bash
  source venv/bin/activate
  python manage.py runserver
  ```

- [ ] **Step 2: Upload CSV via `register_seq`**

  Navigate to the register_seq upload page. Upload a CSV file with these two rows (adjust Project to one you have access to):

  ```
  Project,Target,Seq_type,Modify_seq,Strand_MWs,Parents,Remarks
  BPR-3T05,TTR,SS,GnsGmsCmUmUmUmCfUmGfCfAmUmCmAmGmAmCmAmsUmsUm-LK1-L96-LK1-UmsCmsCmUmCmUmGfAmUfGfGfUmCmAmAmAmGmUmCmsCmsUm,,,t1
  BPR-3T05,TTR,AS,AnsGfsGmAmCmUfUmUfGfAmCmCmAmUfCmAfGmAmGmsGmsAm------------AmsAfsUmGmdUCmdUGmAmUmGmGmCmAfG (moe) AfAmAmGmsCmsCm,,,t1-1
  ```

- [ ] **Step 3: Verify naked sequences registered correctly**

  ```bash
  python manage.py shell
  ```

  ```python
  from app01.models import Sequence
  ss_naked = Sequence.objects.filter(seq__startswith='GGCUUUCUG').first()
  print(ss_naked.seq)   # expected: GGCUUUCUGCAUCAGACAUUUCCUCUGAUGGUCAAAGUCCU (41 bases)
  as_naked = Sequence.objects.filter(seq__startswith='AGGACUUUG').first()
  print(as_naked.seq)   # expected: AGGACUUUGACCAUCAGAGGAAAUGUCUGAUGGCAGAAAGCC (42 bases)
  ```

- [ ] **Step 4: Verify linker_seq has no spurious 'o'**

  ```python
  from app01.models import Delivery
  d = Delivery.objects.filter(seq_type='SS', duplex_id__icontains='BPR').last()
  print(d.linker_seq)
  assert 'LK1o' not in d.linker_seq, "Spurious 'o' found after LK1!"
  assert '-LK1-L96-LK1-' in d.linker_seq, "Linker section missing"
  print("linker_seq OK")
  ```

- [ ] **Step 5: Check seq_list display**

  Navigate to `/seq_list/` and search for the duplex ID. Verify:
  - SS row shows: `Part1 colored tokens | LK1 L96 LK1 | Part2 colored tokens`
  - AS row shows: `Part1 colored tokens | ··· | Part2 colored tokens`
  - In the alignment table: Part1 of SS aligns column-by-column with Part1 of AS; Part2 with Part2
  - The `segment_sep` column (with LK1/L96/LK1 badges) appears between the two aligned segments

- [ ] **Step 6: Verify single-segment sequences are unaffected**

  Pick any existing duplex in seq_list that has a normal (non-dual-segment) modify_seq. Confirm it still renders identically to before.

- [ ] **Step 7: Final commit**

  ```bash
  git add app01/views.py templates/_seq_group_row.html
  git commit -m "feat: dual-segment sequence display and linker_seq — complete implementation"
  ```
