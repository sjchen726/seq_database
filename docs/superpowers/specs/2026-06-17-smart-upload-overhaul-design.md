# Smart Upload Overhaul

**Date:** 2026-06-17
**Scope:** `/smart_upload/` page + supporting backend. Replace automatic file-type detection with always-user-selected dropdowns, support user-extensible vocabularies (file types + in-vivo readouts), merge the two in-vivo file types into one, make 靶点 required, and route custom-type files to a new attachment table without parsing.

---

## Goal

Six UX fixes to the smart upload entry:

1. **Drop rule/LLM auto-detection.** The detection is unreliable. User always picks the file type from a dropdown; default is `"-- 请选择 --"`.
2. **No "unknown / skip" option.** User must pick a real type to proceed.
3. **Rename "Cp 原始数据" → "Cp 原始文件 (RT-qPCR)"** to make the meaning explicit.
4. **Custom types are remembered.** A `"+ 自定义类型..."` entry at the bottom of the dropdown reveals an inline text input. When the user submits a new label, it's persisted in `UploadVocabulary` and appears in the dropdown next time.
5. **Merge in-vivo types.** Drop separate `invivo_kd` / `invivo_bw` file types. Use a single `invivo_summary` type. The actual readout (KD%、体重、肿瘤体积、ALT、自定义…) is picked per-file in the detail card. The readout dropdown also supports custom additions (same mechanism as file types).
6. **靶点 (target_name) is required.** Both client-side (`required` attribute) and server-side validation. Empty target → upload rejected with an error message.

---

## Data Model

### `UploadVocabulary` — extensible dropdown options

Single table holding all dropdown options across two categories (file_type, invivo_readout). Built-in entries are seeded by migration; user-added entries are stored with `is_builtin=False`.

```python
class UploadVocabulary(models.Model):
    CATEGORY_CHOICES = [
        ('file_type', '文件类型'),
        ('invivo_readout', '体内 readout'),
    ]
    category   = models.CharField(max_length=32, choices=CATEGORY_CHOICES, db_index=True)
    code       = models.SlugField(max_length=64, allow_unicode=True)
    label      = models.CharField(max_length=128)
    is_builtin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'upload_vocabulary'
        unique_together = [['category', 'code']]
        ordering = ['category', '-is_builtin', 'label']
```

**Seed entries (built-in, via migration):**

| category | code | label |
|----------|------|-------|
| file_type | `vitro_summary` | 体外汇总（IC50/MaxKD） |
| file_type | `vitro_seq` | 体外序列文件 |
| file_type | `vitro_cp` | Cp 原始文件 (RT-qPCR) |
| file_type | `vitro_transfection` | 转染方案 |
| file_type | `invivo_summary` | 体内数据汇总 |
| file_type | `custom_attachment` | 其他（附件,不解析） |
| invivo_readout | `knockdown_pct` | KD% |
| invivo_readout | `body_weight` | 体重 |
| invivo_readout | `tumor_volume` | 肿瘤体积 |
| invivo_readout | `alt_value` | ALT |
| invivo_readout | `custom` | 其他... |

Custom user entries: `is_builtin=False`, `code = slugify(label, allow_unicode=True)` (fallback to `f"custom_{hash}"` if slug is empty).

### `ProjectAttachment` — landing pad for custom-typed files

Custom-typed / "其他附件" files are not parsed — they're stored on disk and recorded here so they can be listed later (out of scope for this spec).

```python
class ProjectAttachment(models.Model):
    project           = models.CharField(max_length=32, db_index=True)
    label             = models.CharField(max_length=128)              # display label (custom or built-in)
    vocab_code        = models.CharField(max_length=64, blank=True, default='')
    file              = models.FileField(upload_to='project_attachments/%Y%m%d/')
    original_filename = models.CharField(max_length=255)
    uploaded_by       = models.ForeignKey('LmsUser', null=True, on_delete=models.SET_NULL)
    uploaded_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'project_attachment'
        ordering = ['-uploaded_at']
```

---

## UI (templates/smart_upload.html)

### Phase 1 — upload form

No change.

### Phase 2 — detection table + per-file metadata

**File type table** — drop the "置信度" column entirely. Each row: filename + a single dropdown.

```html
<tr>
  <td>{{ det.filename }}</td>
  <td>
    <select name="file_type_{{ forloop.counter0 }}" class="ds-form-control" required
            onchange="onTypeChange(this, {{ forloop.counter0 }})">
      <option value="">-- 请选择 --</option>
      {% for v in vocab_file_types %}
        <option value="{{ v.code }}">{{ v.label }}</option>
      {% endfor %}
      <option value="__new__">+ 自定义类型...</option>
    </select>
    <input type="text" name="custom_label_{{ forloop.counter0 }}"
           id="custom_input_{{ forloop.counter0 }}"
           class="ds-form-control" placeholder="输入自定义类型名"
           style="display:none;margin-top:6px;">
  </td>
</tr>
```

`onTypeChange(sel, i)` reveals `custom_input_{i}` when value is `__new__`, hides otherwise.

The page-load JS removes the old "AI 不可用" warning bar entirely.

### In-vivo data card (per `invivo_summary` file)

Add a readout-type select at the top of the metadata grid. Use the same `+ 自定义...` mechanism.

```html
<div>
  <label class="ds-form-label">readout 类型 *</label>
  <select name="readout_{{ forloop.counter0 }}" class="ds-form-control" required
          onchange="onReadoutChange(this, {{ forloop.counter0 }})">
    <option value="">-- 选择 --</option>
    {% for r in vocab_readouts %}
      <option value="{{ r.code }}">{{ r.label }}</option>
    {% endfor %}
    <option value="__new__">+ 自定义...</option>
  </select>
  <input type="text" name="readout_custom_{{ forloop.counter0 }}"
         id="readout_custom_input_{{ forloop.counter0 }}"
         class="ds-form-control" placeholder="输入自定义 readout 名"
         style="display:none;margin-top:6px;">
</div>
```

The card otherwise keeps its existing fields (时间单位 / 物种 / 品系 / 给药途径 / 性别 / 剂量 / 时间点折叠预览).

The two existing file types `invivo_kd` and `invivo_bw` are gone — there's only one in-vivo branch in the preview.

### 靶点 information card (bottom)

Replace the optional input with a required one:

```html
<input type="text" name="target_name" required value="{{ preview.target_name }}"
       class="ds-form-control" style="width:180px;"
       placeholder="如 FASN、PCSK9（必填）">
```

Helper text changes from "留空则不更新" → "必填,所有空白靶点将更新为此值"。

### Custom attachment note

If `preview.attachment_files` is non-empty, display a brief notice near the confirm button:

```
ⓘ N 个附件文件将作为项目附件保存,不参与数据解析。
```

No further per-file UI for these.

---

## Backend (app01/views.py)

### Remove

- `_extract_target_name_rules` — delete (target now required from user)
- `_extract_target_name_llm` — delete
- In `_build_smart_preview`: the rule-based / LLM file-type classification, the `unknown_files` list, `llm_unavailable` flag, all related warnings
- File-type detection caching in session payloads (`detected_type`, `confidence` for individual files reduces to nothing meaningful — drop fields)
- The two specialized in-vivo classification paths (KD / BW); the single in-vivo branch carries a user-supplied readout instead

### `smart_upload_view` (POST handling, second-phase reparse)

Inputs change:

- `file_type_{i}` — vocab code; `__new__` means a custom entry was added
- `custom_label_{i}` — only present when `file_type_{i} == '__new__'`; the new label string
- `readout_{i}` — per-invivo-file readout code; `__new__` means a new readout was added
- `readout_custom_{i}` — only present when `readout_{i} == '__new__'`

For each `__new__`:

```python
file_type = _ensure_vocab('file_type', custom_label_i)   # returns the saved row
effective_code = file_type.code
```

`_ensure_vocab(category, label)`:
```python
def _ensure_vocab(category, label):
    from django.utils.text import slugify
    label = label.strip()
    if not label:
        raise ValueError('label cannot be empty')
    code = slugify(label, allow_unicode=True) or f'custom_{abs(hash(label)) % 100000}'
    obj, _ = UploadVocabulary.objects.get_or_create(
        category=category, code=code,
        defaults={'label': label, 'is_builtin': False},
    )
    return obj
```

Built-in codes that drive parsing: `vitro_summary`, `vitro_seq`, `vitro_cp`, `vitro_transfection`, `invivo_summary`. Anything else (including `custom_attachment` and any user-added code) lands in `preview['attachment_files']`.

### `_build_smart_preview` rewrite

Inputs:
- `file_detections`: list of `{filename, saved_path, file_type_code, readout_code, readout_custom_label}` (everything user-selected)
- `project_code`: as before

Output `preview`:
```python
{
    'invitro': {...},                     # if any vitro_* file present
    'invivo_groups': [{...}, {...}],      # one per invivo_summary file
    'attachment_files': [{...}, {...}],   # one per non-parsed file
    'target_name': '',                    # always blank — user fills in
    'file_detections': [...],             # re-rendered as form state
    'has_no_seq': True/False,
}
```

For each in-vivo group, the `readout_type` field is set from `readout_code` (or the upserted code for custom). The group's preview parsing uses the existing `parse_invivo_kd_file` / `parse_body_weight_file` selection — but unified: try `parse_invivo_kd_file` first; if it raises a format error, fall back to `parse_body_weight_file`. (Both expect a similar shape; if both fail, surface the error to the user.)

### `smart_upload_confirm_view`

Validation prelude:

```python
target_name_input = request.POST.get('target_name', '').strip()
if not target_name_input:
    errors.append('靶点必填,不能为空')
    return render(request, 'smart_upload.html',
                  {'preview': preview, 'errors': errors})
```

Process `preview['attachment_files']`:

```python
for af in preview.get('attachment_files', []):
    with open(af['saved_path'], 'rb') as fh:
        ProjectAttachment.objects.create(
            project=project_code,
            label=af['label'],
            vocab_code=af['vocab_code'],
            file=DjangoFile(fh, name=af['original_filename']),
            original_filename=af['original_filename'],
            uploaded_by=request.user if request.user.is_authenticated else None,
        )
```

In-vivo branch: when creating each `DataPoint`, `readout_type` is set to the effective readout code from the preview (the user's selection — `knockdown_pct` / `body_weight` / custom slug). Downstream chart code already reads `readout_type` as a string and labels axes accordingly (`compound_list.html` Task 8 reads `d.readout_type`); arbitrary codes work for new charts, and the chart y-axis label falls back to the label string.

---

## Files Changed

| File | Change |
|------|--------|
| `app01/models.py` | + `UploadVocabulary`, + `ProjectAttachment` |
| `app01/migrations/0026_upload_vocabulary.py` | new model |
| `app01/migrations/0027_project_attachment.py` | new model |
| `app01/migrations/0028_seed_upload_vocabulary.py` | RunPython seed (file_type + invivo_readout built-ins) |
| `app01/views.py` | Rewrite of `smart_upload_view`, `_build_smart_preview`, `smart_upload_confirm_view`; delete `_extract_target_name_rules`, `_extract_target_name_llm`; minor unify of in-vivo file parsing |
| `templates/smart_upload.html` | UI overhaul per Section 3 |
| `templates/smart_upload.html.bak3` | Snapshot before edits (created in implementation Task 1) |

---

## Success Criteria

1. File type dropdown shows 6 built-in + any user-added entries + `+ 自定义类型...` at the end. Default selection is `-- 请选择 --`. No "未知/跳过" option.
2. Picking `+ 自定义类型...` reveals an inline text input; submitting persists the entry and the dropdown shows it next time.
3. No automatic detection happens — `det.detected_type` is always `None` / "请选择". The "AI 不可用" warning bar is gone.
4. The in-vivo data card has a `readout 类型 *` select (preset readouts + `+ 自定义...`); the file-type table no longer has separate KD / BW entries.
5. `target_name` is required; submitting empty produces an in-page error and no DB write occurs.
6. Files with a custom or `custom_attachment` type are stored in `ProjectAttachment` with the right label + project code; they do not appear in `invitro` or `invivo_groups` previews.
7. `UploadVocabulary` table is seeded by migration with the 6 + 5 built-ins on a fresh DB.
8. Existing parsing for the 5 built-in known file types (vitro_summary / vitro_seq / vitro_cp / vitro_transfection / invivo_summary) continues to work; in-vivo summary parsing accepts both old KD-shaped and BW-shaped CSVs and writes `readout_type` per the user's selection.
