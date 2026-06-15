# Smart Unified Upload — Design Spec

## Goal

Replace the two separate upload flows (`/upload/` and `/upload/invivo/`) with a single intelligent entry point at `/upload/smart/`. Users drag any mix of CSV files; the system auto-detects each file's type (rules → DeepSeek → manual), groups them into in-vitro and in-vivo sections, and writes all records in one confirm step.

## Scope

Sub-project A of a three-part redesign (B → A → C). Produces a working standalone smart upload flow. Existing `/upload/` and `/upload/invivo/` are kept as fallback specialist flows.

---

## Part 1 — File Type Detection

### 1.1 Detection labels

Seven file-type labels used throughout the system:

| Label | Meaning |
|-------|---------|
| `vitro_seq` | In vitro sequence file (ID + modify_seq + strand columns) |
| `vitro_summary` | In vitro summary table (IC50, Max KD, compound list) |
| `vitro_cp` | In vitro raw Cp values (RT-qPCR, LightCycler format) |
| `vitro_transfection` | Transfection layout (siRNA mapping, cell line, notes) |
| `invivo_kd` | In vivo KD% time-course (Data2 format, bare compound ID headers) |
| `invivo_bw` | In vivo body weight time-course (Data3 format, compound+dose headers) |
| `unknown` | Cannot be determined; user must select manually |

### 1.2 Three-layer detection pipeline

Applied to each uploaded file independently:

**Layer 1 — Rule-based (instant, no cost)**

In-vivo rules reuse existing `detect_invivo_file_type()`. In-vitro rules inspect the header row for known column names:

| Signal | Label |
|--------|-------|
| Header contains columns matching `IC50` or `Max KD` pattern | `vitro_summary` |
| Header contains `Cp` + gene name columns (numeric Cp values) | `vitro_cp` |
| Header contains `modify_seq` or `sequence_id` pattern | `vitro_seq` |
| Header contains `siRNA` or `transfection` keywords | `vitro_transfection` |
| `detect_invivo_file_type()` returns `knockdown_pct` | `invivo_kd` |
| `detect_invivo_file_type()` returns `body_weight` | `invivo_bw` |
| No rule matches | `unknown` → proceed to Layer 2 |

**Layer 2 — DeepSeek API (async, cost-per-call)**

Called only when Layer 1 returns `unknown`. Sends file name + first 20 rows of CSV text. Returns one of the seven labels.

Function signature in `upload_pipeline.py`:
```python
def detect_file_type_llm(filename: str, csv_preview: str) -> str:
    """Call DeepSeek to classify a CSV file. Returns one of the 7 labels or 'unknown' on failure."""
```

Prompt template (sent as user message):
```
You are classifying pharmaceutical research CSV files. The file is named "{filename}".
Here are the first rows:

{csv_preview}

Respond with EXACTLY one label from this list:
vitro_seq, vitro_summary, vitro_cp, vitro_transfection, invivo_kd, invivo_bw, unknown

Definitions:
- vitro_seq: sequence file with compound IDs and modification sequences
- vitro_summary: in vitro summary with IC50/MaxKD values per compound
- vitro_cp: raw RT-qPCR Cp values (LightCycler or similar format)
- vitro_transfection: siRNA-to-compound mapping with cell line and transfection notes
- invivo_kd: in vivo knockdown % time-course; headers are bare compound IDs repeated per replicate
- invivo_bw: in vivo body weight time-course; headers are "compound dose schedule" per replicate
- unknown: none of the above

Respond with only the label, nothing else.
```

API configuration:
```python
# bprdb/settings.py
DEEPSEEK_API_KEY = 'sk-...'
DEEPSEEK_API_URL = 'https://api.deepseek.com/chat/completions'
DEEPSEEK_MODEL = 'deepseek-chat'
```

On any exception (network error, timeout, unexpected response) → return `'unknown'` silently; log a warning.

**Layer 3 — Manual selection**

Files still `unknown` after Layer 2 are shown with an empty required dropdown. User must select before proceeding.

### 1.3 Confidence display

Each file is shown with its detection source:

| Source | Badge |
|--------|-------|
| Rule matched | ✓ 规则匹配 (green) |
| DeepSeek suggested | ~ AI 建议，请确认 (amber) |
| Unknown | ✗ 请手动选择 (red, required) |

All files — regardless of confidence — display a dropdown pre-filled with the detected label. Users can always override.

---

## Part 2 — View Design

### 2.1 `smart_upload_view` (GET + POST)

**Route:** `path('upload/smart/', views.smart_upload_view, name='smart_upload')`

**GET:** Render `smart_upload.html` with empty form. If `?preview=1` and `'smart_preview'` in session → render Phase 2 (detection results + confirm).

**POST step 1 — file upload:**
1. Read `request.FILES.getlist('files')` (required; error if empty)
2. For each file: save bytes to `default_storage` under `_tmp_smart/{filename}` → record `saved_path`
3. For each file: run three-layer detection → build `{filename, saved_path, detected_type, confidence}` dict
4. Group by detected type: in-vitro files → call parsers → `build_preview()`; in-vivo files → call `parse_invivo_kd_file` or `parse_body_weight_file`
5. Store in `request.session['smart_preview']` (JSON-serializable)
6. Redirect to `/upload/smart/?preview=1`

**POST step 2 — type override re-parse:**  
If user changed file types in Phase 2 and clicked "重新解析": re-POST with `file_types[filename]` values; read file bytes from `saved_path` in `default_storage`; re-run parsers with user-specified types; update session; redirect to preview. Original `_tmp_smart/` files are not deleted until confirm completes.

### 2.2 `smart_upload_confirm_view` (POST only)

**Route:** `path('upload/smart/confirm/', views.smart_upload_confirm_view, name='smart_upload_confirm')`

1. Read session `'smart_preview'`
2. Validate in-vitro metadata (`batch_label` required if in-vitro block exists)
3. Validate each in-vivo block's metadata (`time_unit`, `dose_override` if `needs_dose`, `animal_species`, `animal_strain`, `route`, `gender`)
4. Write in-vitro with its own `transaction.atomic()` (reuse logic from `upload_confirm_view`)
5. Write each in-vivo group with its own `transaction.atomic()` (reuse logic from `invivo_upload_confirm_view`)
6. In-vitro and in-vivo failures are independent — one can succeed while the other fails
7. Save raw files as `ExperimentAttachment` (in-vivo only; in-vitro raw Cp already stored in `DataPoint.raw_cp`)
8. Delete session key; show success message with counts; redirect to `smart_upload`

### 2.3 Session structure `'smart_preview'`

```python
{
    'invitro': {                      # None if no in-vitro files
        'batch_label': '',            # pre-filled from summary if available
        'assay_name': '',
        'compounds': [...],           # from build_preview()
        'cp_coverage': {...},
        'cell_line': '',
        'notes': '',
    },
    'invivo_groups': [                # one entry per in-vivo file
        {
            'filename': 'data2.csv',
            'saved_path': '_tmp_invivo/data2.csv',
            'readout_type': 'knockdown_pct',
            'inferred_time_unit': 'day',
            'needs_dose': True,
            'groups': [
                {
                    'compound_id': 'CompA',
                    'dose_info': '',
                    'timepoints': [{'time': -7.0, 'mean': 0.0, 'sd': 0.0, 'n': 3}, ...],
                }
            ],
        }
    ],
    'file_detections': [              # one entry per uploaded file
        {'filename': 'summary.csv', 'saved_path': '_tmp_smart/summary.csv', 'detected_type': 'vitro_summary', 'confidence': 'rule'},
        {'filename': 'data2.csv',   'saved_path': '_tmp_smart/data2.csv',   'detected_type': 'invivo_kd',     'confidence': 'llm'},
        {'filename': 'mystery.csv', 'saved_path': '_tmp_smart/mystery.csv', 'detected_type': 'unknown',       'confidence': 'none'},
    ],
    'project_code': '3M03',           # user-supplied at upload
}
```

---

## Part 3 — Template `smart_upload.html`

Extends `base.html`. Two phases controlled by `{{ preview }}` context variable.

### Phase 1 — Upload form

- `project_code` text input (required)
- Multi-file input: `<input type="file" name="files" multiple accept=".csv">`
- Submit button: "解析文件 →"

### Phase 2 — Detection results + confirm

**File detection table** (one row per file):

| Column | Content |
|--------|---------|
| 文件名 | filename |
| 类型 | `<select name="file_type_X">` pre-filled with detected_type |
| 置信度 | ✓ / ~ / ✗ badge based on `confidence` |

All rows editable. "重新解析" button re-POSTs with updated types if user changes any.

**In-vitro block** (shown if `preview.invitro`):

- 批次名称 *, Assay, 实验日期 inputs
- Collapsed compound preview table (N 个化合物 accordion)

**In-vivo block per file** (shown for each item in `preview.invivo_groups`):

- Header: filename + detected readout type
- time_unit select (pre-selects 'day' if `inferred_time_unit == 'day'`)
- dose_override input (only if `needs_dose`)
- animal_species, animal_strain, route, gender inputs
- Collapsed compound/timepoint preview table

**Confirm button:** `POST /upload/smart/confirm/`

**"重新选择文件" link:** clears session, back to Phase 1.

---

## Part 4 — `detect_file_type_rules` function

New function in `upload_pipeline.py`:

```python
def detect_file_type_rules(file) -> str:
    """
    Rule-based file type detection for in-vitro formats.
    Returns one of the 7 labels or 'unknown'.
    Calls detect_invivo_file_type() for in-vivo detection.
    """
```

Algorithm:
1. Read first 5 rows with `_read_csv_text` + `csv.reader`
2. Call `detect_invivo_file_type()` on the file bytes → map result: `'knockdown_pct'` → `'invivo_kd'`; `'body_weight'` → `'invivo_bw'`; `'unknown'` → continue
3. Check header row for in-vitro signals (case-insensitive):
   - Any cell matches `r'ic50|max.?kd'` → `vitro_summary`
   - Any cell matches `r'^cp[_\s]?\d*$'` AND data values fall in range 10–40 (Cp value range) → `vitro_cp`
   - Any cell matches `r'modify.?seq|sequence.?id'` → `vitro_seq`
   - Any cell matches `r'sirna|transfection'` → `vitro_transfection`
4. Return `'unknown'` if no rule matches

---

## Part 5 — Error Handling

| Scenario | Handling |
|----------|---------|
| No files uploaded | Required field error |
| File with `unknown` type after DeepSeek | Required dropdown in Phase 2; block confirm until selected |
| DeepSeek API unreachable | Log warning; return 'unknown'; show "AI 识别暂不可用" notice |
| In-vitro parse error | Show per-file error; exclude from in-vitro block |
| In-vivo parse empty groups | Mark file with error; exclude from in-vivo groups |
| Missing compound-sequence mapping | Warning in preview: "未找到序列信息，可补传序列文件" (non-blocking) |
| In-vitro confirm fails | Rollback in-vitro; in-vivo writes unaffected |
| In-vivo confirm fails | Rollback that group; other in-vivo groups and in-vitro unaffected |
| DeepSeek returns unexpected label | Treat as 'unknown' |

---

## Part 6 — Route & Sidebar

**`bprdb/urls.py`:**
```python
path('upload/smart/', views.smart_upload_view, name='smart_upload'),
path('upload/smart/confirm/', views.smart_upload_confirm_view, name='smart_upload_confirm'),
```

**`templates/base.html`** — add under "数据录入" before existing upload links:
```html
<a href="{% url 'smart_upload' %}" class="ds-nav-item ...">
  <i class="bi bi-lightning-charge ds-nav-icon"></i> 智能上传
</a>
```

---

## Part 7 — Tests

- `DetectFileTypeRulesTest` (5 tests): vitro_summary detected, vitro_cp detected, invivo_kd routed from detect_invivo_file_type, unknown on garbage, case-insensitive header match
- `DetectFileLLMTest` (3 tests): LLM called when rules return unknown; LLM failure returns 'unknown'; rules take priority over LLM
- `SmartUploadViewTest` (6 tests): GET 200, login required, no files → error, single in-vitro file → session invitro block, single in-vivo file → session invivo_groups block, mixed files → both blocks present
- `SmartUploadConfirmTest` (4 tests): missing batch_label → 400, missing invivo time_unit → 400, successful mixed confirm → Experiment+DataPoint counts correct, in-vitro success + in-vivo failure → in-vitro records exist

---

## File Changes Summary

| File | Change |
|------|--------|
| `bprdb/settings.py` | Add `DEEPSEEK_API_KEY`, `DEEPSEEK_API_URL`, `DEEPSEEK_MODEL` |
| `app01/upload_pipeline.py` | Add `detect_file_type_rules()`, `detect_file_type_llm()` |
| `app01/views.py` | Add `smart_upload_view`, `smart_upload_confirm_view` |
| `bprdb/urls.py` | Add 2 routes |
| `templates/smart_upload.html` | New two-phase template |
| `templates/base.html` | Add "智能上传" sidebar link |
| `app01/tests.py` | Add 4 test classes (18 tests) |
