# Smart Upload Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the auto-detecting smart upload UI with a user-driven dropdown that supports custom file types and in-vivo readouts (persisted), merge in-vivo KD/BW into one type, require 靶点, and save custom-typed files to a new `ProjectAttachment` table without parsing.

**Architecture:** New `UploadVocabulary` + `ProjectAttachment` Django models hold the extensible dropdown vocabulary and custom-typed file landings. `app01/views.py` smart-upload functions are reworked to drop rule/LLM detection and pass user-selected codes through. `templates/smart_upload.html` Phase 2 is rewritten: dropdowns are vocab-driven with a `+ 自定义...` inline-input mechanism; per-invivo card gains a readout dropdown; target field becomes `required`.

**Tech Stack:** Django 5.1, MySQL (table changes via migrations), function-based views in `app01/views.py`, vanilla JS for the inline custom-input toggle.

**Tests exist:** `app01/tests.py` has ~184 tests including `ExtractTargetNameTest` and `SmartUploadConfirmTargetNameTest`. Tests for deleted helpers are deleted; tests for changed behavior are updated.

**Python interpreter:** `/Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/python` (shared venv).

---

## File Structure

| File | Change |
|------|--------|
| `app01/models.py` | + `UploadVocabulary`, + `ProjectAttachment` |
| `app01/migrations/0005_upload_vocabulary_project_attachment.py` | new — schema for both models |
| `app01/migrations/0006_seed_upload_vocabulary.py` | new — RunPython to insert 11 built-in entries |
| `app01/views.py` | rewrite `smart_upload_view`, `_build_smart_preview`, `smart_upload_confirm_view`; add helpers `_slugify_custom_code`, `_ensure_vocab`; delete `_extract_target_name_rules`, `_extract_target_name_llm`; drop imports of `detect_file_type_rules`/`detect_file_type_llm` from `smart_upload_view` (keep in `upload_pipeline.py`) |
| `app01/tests.py` | delete `ExtractTargetNameTest`; update `SmartUploadConfirmTargetNameTest` for the new required-target behavior |
| `templates/smart_upload.html` | overhaul Phase 2 (vocab-driven dropdowns + inline custom-input JS + required target + attachment notice) |
| `templates/smart_upload.html.bak3` | snapshot before edits (Task 1) |

---

## Pre-flight

```bash
cd /Users/gutou/Projects/seq_web/seq_database_bprdb
/Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/python manage.py showmigrations app01 | tail -5
```
Expected: latest applied is `[X] 0004_add_target_name_index` — new migrations are `0005`, `0006`.

```bash
/Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/python manage.py check
```
Expected: `System check identified no issues (0 silenced).`

---

### Task 1: Backup smart_upload.html

**Files:**
- Create: `templates/smart_upload.html.bak3`

- [ ] **Step 1: Copy template to backup**

```bash
cp templates/smart_upload.html templates/smart_upload.html.bak3
ls -lh templates/smart_upload.html templates/smart_upload.html.bak3
```

Expected: two files, same byte count.

- [ ] **Step 2: Commit**

```bash
git add templates/smart_upload.html.bak3
git commit -m "chore: snapshot smart_upload.html before overhaul"
```

---

### Task 2: Add `UploadVocabulary` and `ProjectAttachment` models + schema migration

**Files:**
- Modify: `app01/models.py` — append two new models
- Create: `app01/migrations/0005_upload_vocabulary_project_attachment.py` (via makemigrations)

- [ ] **Step 1: Append models to `app01/models.py`**

Find the last class in `app01/models.py` (currently `LmsUser` at the bottom). Append the following block at the end of the file:

```python
class UploadVocabulary(models.Model):
    """
    Extensible dropdown vocabulary for the smart upload page.

    Two categories drive two dropdowns: file_type and invivo_readout.
    Built-in entries are seeded by migration; user-added entries have
    is_builtin=False and appear in the dropdown for future uploads.
    """

    CATEGORY_CHOICES = [
        ('file_type', '文件类型'),
        ('invivo_readout', '体内 readout'),
    ]

    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, db_index=True)
    code = models.SlugField(max_length=64, allow_unicode=True)
    label = models.CharField(max_length=128)
    is_builtin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'upload_vocabulary'
        unique_together = [['category', 'code']]
        ordering = ['category', '-is_builtin', 'label']

    def __str__(self):
        return f'{self.category}:{self.label}'


class ProjectAttachment(models.Model):
    """
    Landing pad for files that the user marks as custom / "其他附件" — stored
    on disk and recorded here, no parsing. Not linked to any Experiment.
    """

    project = models.CharField(max_length=32, db_index=True)
    label = models.CharField(max_length=128)
    vocab_code = models.CharField(max_length=64, blank=True, default='')
    file = models.FileField(upload_to='project_attachments/%Y%m%d/')
    original_filename = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(
        'LmsUser', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='project_attachments',
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'project_attachment'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'{self.project} / {self.label} / {self.original_filename}'
```

- [ ] **Step 2: Generate the schema migration**

```bash
/Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/python manage.py makemigrations app01 --name upload_vocabulary_project_attachment
```

Expected output mentions both `UploadVocabulary` and `ProjectAttachment` created. A file like `app01/migrations/0005_upload_vocabulary_project_attachment.py` appears.

- [ ] **Step 3: Apply migration**

```bash
/Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/python manage.py migrate app01
```

Expected: `Applying app01.0005_upload_vocabulary_project_attachment... OK`

- [ ] **Step 4: Sanity check models via shell**

```bash
/Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/python manage.py shell -c "
from app01.models import UploadVocabulary, ProjectAttachment
print('vocab count:', UploadVocabulary.objects.count())
print('attachment count:', ProjectAttachment.objects.count())
"
```

Expected: both print `0` (no seed yet).

- [ ] **Step 5: Commit**

```bash
git add app01/models.py app01/migrations/0005_upload_vocabulary_project_attachment.py
git commit -m "feat: add UploadVocabulary + ProjectAttachment models"
```

---

### Task 3: Seed built-in vocabulary entries

**Files:**
- Create: `app01/migrations/0006_seed_upload_vocabulary.py`

- [ ] **Step 1: Write the seed migration**

Create `app01/migrations/0006_seed_upload_vocabulary.py` with this exact content:

```python
from django.db import migrations


BUILTIN_VOCABULARY = [
    # file types
    ('file_type', 'vitro_summary',       '体外汇总（IC50/MaxKD）'),
    ('file_type', 'vitro_seq',           '体外序列文件'),
    ('file_type', 'vitro_cp',            'Cp 原始文件 (RT-qPCR)'),
    ('file_type', 'vitro_transfection',  '转染方案'),
    ('file_type', 'invivo_summary',      '体内数据汇总'),
    ('file_type', 'custom_attachment',   '其他（附件,不解析）'),
    # invivo readouts
    ('invivo_readout', 'knockdown_pct', 'KD%'),
    ('invivo_readout', 'body_weight',   '体重'),
    ('invivo_readout', 'tumor_volume',  '肿瘤体积'),
    ('invivo_readout', 'alt_value',     'ALT'),
    ('invivo_readout', 'custom',        '其他...'),
]


def seed_vocab(apps, schema_editor):
    UploadVocabulary = apps.get_model('app01', 'UploadVocabulary')
    for category, code, label in BUILTIN_VOCABULARY:
        UploadVocabulary.objects.update_or_create(
            category=category, code=code,
            defaults={'label': label, 'is_builtin': True},
        )


def unseed_vocab(apps, schema_editor):
    UploadVocabulary = apps.get_model('app01', 'UploadVocabulary')
    for category, code, _label in BUILTIN_VOCABULARY:
        UploadVocabulary.objects.filter(category=category, code=code, is_builtin=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('app01', '0005_upload_vocabulary_project_attachment'),
    ]
    operations = [
        migrations.RunPython(seed_vocab, unseed_vocab),
    ]
```

- [ ] **Step 2: Apply the migration**

```bash
/Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/python manage.py migrate app01
```

Expected: `Applying app01.0006_seed_upload_vocabulary... OK`

- [ ] **Step 3: Verify the rows**

```bash
/Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/python manage.py shell -c "
from app01.models import UploadVocabulary
print('file_type:', list(UploadVocabulary.objects.filter(category='file_type').values_list('code', 'label')))
print('invivo_readout:', list(UploadVocabulary.objects.filter(category='invivo_readout').values_list('code', 'label')))
"
```

Expected output (order may differ):
```
file_type: [('custom_attachment', '其他（附件,不解析）'), ('invivo_summary', '体内数据汇总'), ('vitro_cp', 'Cp 原始文件 (RT-qPCR)'), ('vitro_seq', '体外序列文件'), ('vitro_summary', '体外汇总（IC50/MaxKD）'), ('vitro_transfection', '转染方案')]
invivo_readout: [('alt_value', 'ALT'), ('body_weight', '体重'), ('custom', '其他...'), ('knockdown_pct', 'KD%'), ('tumor_volume', '肿瘤体积')]
```

- [ ] **Step 4: Commit**

```bash
git add app01/migrations/0006_seed_upload_vocabulary.py
git commit -m "feat: seed built-in upload vocabulary (file types + invivo readouts)"
```

---

### Task 4: Helpers `_slugify_custom_code` and `_ensure_vocab` in `views.py`

**Files:**
- Modify: `app01/views.py` — add two module-level helpers near the other `_extract_*` helpers (around line 1431, where `_extract_target_name_rules` currently is)

These helpers are used by Tasks 5–7.

- [ ] **Step 1: Add the helpers**

In `app01/views.py`, find this line:

```python
def _extract_target_name_rules(filename: str, file_bytes: bytes) -> str | None:
```

Insert **before** that line:

```python
def _slugify_custom_code(label: str) -> str:
    """Stable slug for user-typed custom labels (handles CJK via allow_unicode=True)."""
    from django.utils.text import slugify
    s = slugify(label, allow_unicode=True)
    return s or f'custom_{abs(hash(label)) % 100000}'


def _ensure_vocab(category: str, label: str):
    """Upsert a UploadVocabulary entry; returns the row. Raises ValueError on empty label."""
    from app01.models import UploadVocabulary
    label = label.strip()
    if not label:
        raise ValueError('label cannot be empty')
    code = _slugify_custom_code(label)
    obj, _created = UploadVocabulary.objects.get_or_create(
        category=category, code=code,
        defaults={'label': label, 'is_builtin': False},
    )
    return obj


```

(Two blank lines before `def _extract_target_name_rules`.)

- [ ] **Step 2: Sanity check via shell**

```bash
/Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/python manage.py shell -c "
from app01.views import _slugify_custom_code, _ensure_vocab
print(_slugify_custom_code('我的新类型'))
print(_slugify_custom_code('My Custom Type 1'))
v = _ensure_vocab('file_type', '我的测试类型')
print(v.code, v.label, v.is_builtin)
v.delete()
"
```

Expected: slug for the Chinese label is non-empty (Unicode slug), the test entry creates with `is_builtin=False`, then deleted.

- [ ] **Step 3: Commit**

```bash
git add app01/views.py
git commit -m "feat: add _slugify_custom_code + _ensure_vocab helpers"
```

---

### Task 5: Rewrite `smart_upload_view` (drop auto-detect; pass user codes)

**Files:**
- Modify: `app01/views.py` — replace the `smart_upload_view` function body (currently around lines 1614–1700)

The new flow:
- Initial POST: just save files, build an empty `file_detections` list (each `{filename, saved_path}` only).
- Reparse POST: each `file_type_{i}` is a vocab code (built-in or user-added). If `file_type_{i} == '__new__'`, read `custom_label_{i}` and upsert via `_ensure_vocab`. Each invivo file also carries `readout_{i}` / `readout_custom_{i}`.

- [ ] **Step 1: Replace the whole function**

Find this block (the entire `smart_upload_view` function):

```python
@login_required
def smart_upload_view(request):
    if request.method == 'POST':
        # Re-parse with user-selected types
        if request.POST.get('reparse'):
            smart_preview = request.session.get('smart_preview', {})
            project_code = smart_preview.get('project_code', '')
            # Build allowlist of paths already in session — prevents path traversal via crafted POST
            allowed_paths = {
                det['saved_path']
                for det in smart_preview.get('file_detections', [])
            }
            try:
                file_count = int(request.POST.get('file_count', 0))
            except ValueError:
                file_count = 0
            file_detections = []
            for i in range(file_count):
                filename = request.POST.get(f'filename_{i}', '')
                saved_path = request.POST.get(f'saved_path_{i}', '')
                file_type = request.POST.get(f'file_type_{i}', 'unknown')
                if filename and saved_path and saved_path in allowed_paths:
                    file_detections.append({
                        'filename': filename,
                        'saved_path': saved_path,
                        'detected_type': file_type,
                        'confidence': 'manual',
                    })
            preview = _build_smart_preview(file_detections, project_code)
            request.session['smart_preview'] = preview
            return redirect('/upload/smart/?preview=1')

        # Initial file upload
        project_code = request.POST.get('project_code', '').strip()
        files = request.FILES.getlist('files')
        if not files:
            return render(request, 'smart_upload.html', {
                'errors': ['请至少上传一个文件'],
                'project_code': project_code,
            })

        from django.conf import settings as djsettings
        from django.core.files.base import ContentFile
        llm_key_configured = bool(getattr(djsettings, 'DEEPSEEK_API_KEY', ''))

        file_detections = []
        llm_unavailable = False

        for f in files:
            filename = f.name
            file_bytes = f.read()

            saved_path_key = f'_tmp_smart/{filename}'
            if default_storage.exists(saved_path_key):
                default_storage.delete(saved_path_key)
            actual_path = default_storage.save(saved_path_key, ContentFile(file_bytes))

            detected_type = detect_file_type_rules(_BytesFile(file_bytes))
            confidence = 'rule'

            if detected_type == 'unknown':
                if llm_key_configured:
                    detected_type = detect_file_type_llm(filename, _BytesFile(file_bytes))
                    confidence = 'llm' if detected_type != 'unknown' else 'none'
                else:
                    llm_unavailable = True
                    confidence = 'none'

            file_detections.append({
                'filename': filename,
                'saved_path': actual_path,
                'detected_type': detected_type,
                'confidence': confidence,
            })

        preview = _build_smart_preview(file_detections, project_code)
        preview['llm_unavailable'] = llm_unavailable
        request.session['smart_preview'] = preview
        return redirect('/upload/smart/?preview=1')

    # GET
    if request.GET.get('preview') and 'smart_preview' in request.session:
        return render(request, 'smart_upload.html', {'preview': request.session['smart_preview']})

    if 'smart_preview' in request.session:
        del request.session['smart_preview']
    return render(request, 'smart_upload.html', {})
```

Replace with:

```python
@login_required
def smart_upload_view(request):
    if request.method == 'POST':
        # ── Phase 2: re-parse with user-selected types ──
        if request.POST.get('reparse'):
            smart_preview = request.session.get('smart_preview', {})
            project_code = smart_preview.get('project_code', '')
            allowed_paths = {
                det['saved_path']
                for det in smart_preview.get('file_detections', [])
            }
            try:
                file_count = int(request.POST.get('file_count', 0))
            except ValueError:
                file_count = 0

            file_detections = []
            for i in range(file_count):
                filename = request.POST.get(f'filename_{i}', '')
                saved_path = request.POST.get(f'saved_path_{i}', '')
                file_type_code = request.POST.get(f'file_type_{i}', '')

                if not (filename and saved_path and saved_path in allowed_paths):
                    continue
                if not file_type_code:
                    continue  # user left "-- 请选择 --"; skip (UI marks select required)

                # Custom type — upsert vocabulary
                if file_type_code == '__new__':
                    label = request.POST.get(f'custom_label_{i}', '').strip()
                    if not label:
                        continue
                    vocab = _ensure_vocab('file_type', label)
                    file_type_code = vocab.code

                # Invivo readout (only meaningful for invivo_summary)
                readout_code = request.POST.get(f'readout_{i}', '').strip()
                if readout_code == '__new__':
                    rlabel = request.POST.get(f'readout_custom_{i}', '').strip()
                    if rlabel:
                        rvocab = _ensure_vocab('invivo_readout', rlabel)
                        readout_code = rvocab.code
                    else:
                        readout_code = ''

                file_detections.append({
                    'filename': filename,
                    'saved_path': saved_path,
                    'file_type_code': file_type_code,
                    'readout_code': readout_code,
                })

            preview = _build_smart_preview(file_detections, project_code)
            request.session['smart_preview'] = preview
            return redirect('/upload/smart/?preview=1')

        # ── Phase 1: initial upload — save files, no detection ──
        project_code = request.POST.get('project_code', '').strip()
        files = request.FILES.getlist('files')
        if not files:
            return render(request, 'smart_upload.html', {
                'errors': ['请至少上传一个文件'],
                'project_code': project_code,
            })

        from django.core.files.base import ContentFile

        file_detections = []
        for f in files:
            filename = f.name
            file_bytes = f.read()

            saved_path_key = f'_tmp_smart/{filename}'
            if default_storage.exists(saved_path_key):
                default_storage.delete(saved_path_key)
            actual_path = default_storage.save(saved_path_key, ContentFile(file_bytes))

            file_detections.append({
                'filename': filename,
                'saved_path': actual_path,
                'file_type_code': '',     # user picks in Phase 2
                'readout_code': '',
            })

        preview = _build_smart_preview(file_detections, project_code)
        request.session['smart_preview'] = preview
        return redirect('/upload/smart/?preview=1')

    # GET
    if request.GET.get('preview') and 'smart_preview' in request.session:
        return render(request, 'smart_upload.html', {'preview': request.session['smart_preview']})

    if 'smart_preview' in request.session:
        del request.session['smart_preview']
    return render(request, 'smart_upload.html', {})
```

- [ ] **Step 2: Drop unused imports**

Find this line near the top of `app01/views.py` (around line 549):

```python
from app01.upload_pipeline import (
    ...
    detect_file_type_rules,
    detect_file_type_llm,
    ...
)
```

If `detect_file_type_rules` and `detect_file_type_llm` are listed in the imports and are no longer referenced from `views.py` (grep to confirm), drop those two names from the import. Run:

```bash
grep -n "detect_file_type_rules\|detect_file_type_llm" app01/views.py
```

Expected after this step: no matches. If the names remain in the import line only, remove them. If they appear elsewhere (they shouldn't), leave the import.

- [ ] **Step 3: Run Django check**

```bash
/Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Commit**

```bash
git add app01/views.py
git commit -m "feat: smart_upload_view no longer auto-detects; reads user-selected codes"
```

---

### Task 6: Rewrite `_build_smart_preview` (drop unknown handling; unify invivo; add attachment_files)

**Files:**
- Modify: `app01/views.py` — replace the entire `_build_smart_preview` function (currently around lines 1490–1611)

The new preview shape:
```python
{
    'project_code': str,
    'file_detections': [...],   # echo of input + label/vocab_code per row
    'invitro': {...} | None,    # only if vitro_* files present
    'invivo_groups': [...],     # one per invivo_summary file (carries readout_code & readout_label)
    'attachment_files': [...],  # one per non-parsed file
    'errors': [...],
    'has_no_seq': bool,
}
```

Note: target extraction is gone — UI requires the user to fill in `target_name`.

- [ ] **Step 1: Replace the function**

Find this exact opening line and locate the matching function end (the next `def` or `@login_required`):

```python
def _build_smart_preview(file_detections: list, project_code: str) -> dict:
```

Replace the entire function body with:

```python
def _build_smart_preview(file_detections: list, project_code: str) -> dict:
    """
    Build the smart upload preview from user-classified files.

    Each `file_detections` entry MUST have:
      filename, saved_path, file_type_code, readout_code

    Known parsing codes: vitro_summary / vitro_seq / vitro_cp / vitro_transfection
    / invivo_summary. Anything else (including custom_attachment + user-added)
    lands in `attachment_files` with no parsing.
    """
    from app01.models import UploadVocabulary

    invitro_type_files = {
        'vitro_seq': [], 'vitro_summary': [],
        'vitro_cp': [], 'vitro_transfection': [],
    }
    invivo_groups = []
    attachment_files = []
    errors = []

    # Build code → label map (one query) for echoing labels back to the UI
    vocab_label_by_code = {
        v.code: v.label
        for v in UploadVocabulary.objects.all()
    }

    KNOWN_CODES = set(invitro_type_files.keys()) | {'invivo_summary'}

    for det in file_detections:
        code = det.get('file_type_code') or ''
        if not code:
            continue  # not yet classified

        file_bytes = _read_from_storage(det['saved_path'])
        if file_bytes is None:
            errors.append(f'{det["filename"]}: 无法读取临时文件')
            continue

        if code in invitro_type_files:
            invitro_type_files[code].append((det['filename'], file_bytes))
            continue

        if code == 'invivo_summary':
            try:
                f = _BytesFile(file_bytes)
                try:
                    parsed = parse_invivo_kd_file(f)
                except Exception:
                    f = _BytesFile(file_bytes)
                    parsed = parse_body_weight_file(f)
                readout_code = det.get('readout_code') or parsed.readout_type
                invivo_groups.append({
                    'filename': det['filename'],
                    'saved_path': det['saved_path'],
                    'readout_code': readout_code,
                    'readout_label': vocab_label_by_code.get(readout_code, readout_code),
                    'inferred_time_unit': parsed.inferred_time_unit,
                    'needs_dose': parsed.needs_dose,
                    'groups': [
                        {
                            'compound_id': g.compound_id,
                            'dose_info': g.dose_info,
                            'timepoints': [
                                {'time': tp.time, 'mean': tp.mean, 'sd': tp.sd, 'n': tp.n}
                                for tp in g.timepoints
                            ],
                        }
                        for g in parsed.groups
                    ],
                })
            except Exception as e:
                errors.append(f'{det["filename"]}: 体内数据解析失败 {e}')
            continue

        # Anything not in KNOWN_CODES → custom / custom_attachment → store as attachment
        attachment_files.append({
            'filename': det['filename'],
            'saved_path': det['saved_path'],
            'vocab_code': code,
            'label': vocab_label_by_code.get(code, code),
        })

    seq_parsed = None
    summary_parsed = None
    cp_parsed_list = []
    transfection_parsed = None

    for filename, file_bytes in invitro_type_files['vitro_seq']:
        try:
            seq_parsed = parse_seq_file(_BytesFile(file_bytes))
        except Exception as e:
            errors.append(f'{filename}: 序列文件解析失败 {e}')

    for filename, file_bytes in invitro_type_files['vitro_summary']:
        try:
            summary_parsed = parse_summary_csv(_BytesFile(file_bytes))
        except Exception as e:
            errors.append(f'{filename}: 汇总表解析失败 {e}')

    for filename, file_bytes in invitro_type_files['vitro_cp']:
        try:
            cp_parsed_list.append(parse_cp_file(_BytesFile(file_bytes)))
        except Exception as e:
            errors.append(f'{filename}: Cp 文件解析失败 {e}')

    for filename, file_bytes in invitro_type_files['vitro_transfection']:
        try:
            transfection_parsed = parse_transfection_file(_BytesFile(file_bytes))
        except Exception as e:
            errors.append(f'{filename}: 转染文件解析失败 {e}')

    invitro = None
    if seq_parsed or summary_parsed or cp_parsed_list:
        try:
            assay_name = (
                (summary_parsed.assay_name if summary_parsed else '')
                or (cp_parsed_list[0].assay_name if cp_parsed_list else '')
            )
            invitro = build_preview(
                seq_parsed, summary_parsed, cp_parsed_list,
                batch_label='', assay_name=assay_name, exp_date=None,
                transfection_parsed=transfection_parsed,
            )
        except Exception as e:
            errors.append(f'体外数据整合失败：{e}')

    has_no_seq = bool(invitro) and not (invitro.get('strand_map') or seq_parsed)

    return {
        'project_code': project_code,
        'file_detections': file_detections,
        'invitro': invitro,
        'invivo_groups': invivo_groups,
        'attachment_files': attachment_files,
        'errors': errors,
        'has_no_seq': has_no_seq,
    }
```

- [ ] **Step 2: Run Django check**

```bash
/Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 3: Commit**

```bash
git add app01/views.py
git commit -m "feat: _build_smart_preview unified invivo + custom attachment files"
```

---

### Task 7: Rewrite `smart_upload_confirm_view` (target required; readout per-file; ProjectAttachment writes)

**Files:**
- Modify: `app01/views.py` — replace the `smart_upload_confirm_view` function (currently around lines 1703–1932)

Changes:
- Validate `target_name` first; reject empty.
- For each `invivo_groups[i]`, take `readout_code` from the group (already set by Task 6). The `assay_name_iv` derives from the readout label; readout_type on DataPoints is the readout_code (may be custom slug).
- After in-vitro / in-vivo writes, iterate `preview['attachment_files']` and create `ProjectAttachment` rows; delete temp file after copy.

- [ ] **Step 1: Replace the function**

Find this opening:

```python
@login_required
def smart_upload_confirm_view(request):
    if request.method != 'POST':
        return redirect('smart_upload')
```

Locate its closing `}` (i.e. up to the line `return redirect('smart_upload')` just before the next `@login_required` / function). Replace the entire function with:

```python
@login_required
def smart_upload_confirm_view(request):
    if request.method != 'POST':
        return redirect('smart_upload')

    smart_preview = request.session.get('smart_preview')
    if not smart_preview:
        return redirect('smart_upload')

    invitro = smart_preview.get('invitro')
    invivo_groups = smart_preview.get('invivo_groups', [])
    attachment_files = smart_preview.get('attachment_files', [])
    project_code = smart_preview.get('project_code', '')

    batch_label = request.POST.get('batch_label', '').strip()
    assay_name = request.POST.get('assay_name', '').strip()
    exp_date = request.POST.get('exp_date', '').strip() or None
    target_name_input = request.POST.get('target_name', '').strip()

    errors = []

    if not target_name_input:
        errors.append('靶点必填,不能为空')

    if invitro and not batch_label:
        errors.append('批次名称为必填项')

    invivo_meta = []
    for i, group in enumerate(invivo_groups):
        time_unit = request.POST.get(f'time_unit_{i}', '').strip()
        dose_override = request.POST.get(f'dose_override_{i}', '').strip()
        animal_species = request.POST.get(f'animal_species_{i}', '').strip()
        animal_strain = request.POST.get(f'animal_strain_{i}', '').strip()
        route = request.POST.get(f'route_{i}', '').strip()
        gender = request.POST.get(f'gender_{i}', '').strip()

        if not time_unit:
            errors.append(f'文件 {group["filename"]}: 请填写时间单位')
        if group['needs_dose'] and not dose_override:
            errors.append(f'文件 {group["filename"]}: 请填写剂量信息')
        if not animal_species:
            errors.append(f'文件 {group["filename"]}: 请填写动物物种')
        if not animal_strain:
            errors.append(f'文件 {group["filename"]}: 请填写动物品系')
        if not route:
            errors.append(f'文件 {group["filename"]}: 请填写给药途径')
        if not gender:
            errors.append(f'文件 {group["filename"]}: 请填写动物性别')
        if not group.get('readout_code'):
            errors.append(f'文件 {group["filename"]}: 请选择 readout 类型')

        invivo_meta.append({
            'time_unit': time_unit,
            'dose_override': dose_override,
            'animal_species': animal_species,
            'animal_strain': animal_strain,
            'route': route,
            'gender': gender,
        })

    if errors:
        return render(request, 'smart_upload.html', {
            'preview': smart_preview,
            'errors': errors,
        })

    n_experiments = 0
    n_invivo = 0
    n_attachments = 0
    invitro_errors = []
    invivo_errors = []
    attachment_errors = []

    # Write in-vitro (one atomic transaction)
    if invitro:
        preview_copy = copy.deepcopy(invitro)
        preview_copy['batch_label'] = batch_label
        preview_copy['assay_name'] = assay_name or preview_copy.get('assay_name', '')
        exp_date_obj = None
        if exp_date:
            try:
                exp_date_obj = date_type.fromisoformat(exp_date)
            except ValueError:
                pass

        try:
            with transaction.atomic():
                for c in preview_copy.get('new_compounds', []):
                    Compound.objects.get_or_create(compound_id=c['compound_id'])

                for cid, seq_data in preview_copy.get('strand_map', {}).items():
                    compound, _ = Compound.objects.get_or_create(compound_id=cid)
                    if seq_data.get('ss_seq'):
                        Strand.objects.get_or_create(
                            compound=compound, strand_type='SS',
                            defaults={'sequence_id': f'{cid}_SS', 'modify_seq': seq_data['ss_seq']},
                        )
                    if seq_data.get('as_seq'):
                        Strand.objects.get_or_create(
                            compound=compound, strand_type='AS',
                            defaults={'sequence_id': f'{cid}_AS', 'modify_seq': seq_data['as_seq']},
                        )

                for exp_data in preview_copy.get('experiments', []):
                    cid = exp_data['compound_id']
                    compound, _ = Compound.objects.get_or_create(compound_id=cid)
                    exp, exp_created = Experiment.objects.get_or_create(
                        compound=compound,
                        batch_label=preview_copy['batch_label'],
                        assay_name=preview_copy['assay_name'],
                        defaults={
                            'exp_type': exp_data.get('exp_type', 'in_vitro'),
                            'cell_line': preview_copy.get('cell_line', ''),
                            'notes': preview_copy.get('notes', ''),
                            'date': exp_date_obj,
                        },
                    )
                    if exp_created:
                        n_experiments += 1
                        dp_objs = [
                            DataPoint(
                                experiment=exp,
                                x_value=dp['x_value'],
                                x_type=dp['x_type'],
                                replicate=dp['replicate'],
                                value=dp['value'],
                                readout_type=dp['readout_type'],
                                is_control=dp.get('is_control', False),
                                raw_cp=dp.get('raw_cp'),
                            )
                            for dp in exp_data.get('datapoints', [])
                        ]
                        DataPoint.objects.bulk_create(dp_objs)

                        if exp_data.get('summary'):
                            s = exp_data['summary']
                            ExperimentSummary.objects.create(
                                experiment=exp,
                                max_kd_pct=s.get('max_kd_pct'),
                                ic50_nm=s.get('ic50_nm'),
                                rank=s.get('rank'),
                            )
        except Exception as e:
            logger.error(f'smart_upload_confirm invitro error: {e}')
            invitro_errors.append(str(e))

    # Write each in-vivo group in its own atomic transaction (independent)
    for i, group in enumerate(invivo_groups):
        meta = invivo_meta[i]
        batch_label_iv = datetime.now().strftime('B%Y%m%d%H%M%S') + f'{i:02d}'
        readout_code = group['readout_code']
        readout_label = group.get('readout_label', readout_code)
        assay_name_iv = f'{readout_label} 时间曲线'
        first_exp = None

        try:
            with transaction.atomic():
                for g in group['groups']:
                    compound, _ = Compound.objects.get_or_create(compound_id=g['compound_id'])
                    dose_info = g['dose_info'] or meta['dose_override']

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
                    )
                    if first_exp is None:
                        first_exp = exp
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

                saved_path = group.get('saved_path', '')
                if first_exp and saved_path and default_storage.exists(saved_path):
                    from django.core.files.base import ContentFile as CF
                    with default_storage.open(saved_path, 'rb') as fh:
                        content = fh.read()
                    att = ExperimentAttachment(experiment=first_exp, label=group['filename'])
                    att.file.save(group['filename'], CF(content), save=True)
                    default_storage.delete(saved_path)
        except Exception as e:
            logger.error(f'smart_upload_confirm invivo error: {e}')
            invivo_errors.append(f'文件 {group["filename"]}: {e}')

    # Write project attachments (custom-typed files)
    if attachment_files:
        from app01.models import ProjectAttachment
        from django.core.files.base import ContentFile as CF
        for af in attachment_files:
            saved_path = af['saved_path']
            try:
                if not default_storage.exists(saved_path):
                    attachment_errors.append(f'文件 {af["filename"]}: 临时文件已丢失')
                    continue
                with default_storage.open(saved_path, 'rb') as fh:
                    content = fh.read()
                pa = ProjectAttachment(
                    project=project_code,
                    label=af['label'],
                    vocab_code=af['vocab_code'],
                    original_filename=af['filename'],
                    uploaded_by=request.user if request.user.is_authenticated else None,
                )
                pa.file.save(af['filename'], CF(content), save=True)
                default_storage.delete(saved_path)
                n_attachments += 1
            except Exception as e:
                logger.error(f'smart_upload_confirm attachment error: {e}')
                attachment_errors.append(f'文件 {af["filename"]}: {e}')

    # Clean up any other lingering temp files
    for det in smart_preview.get('file_detections', []):
        code = det.get('file_type_code', '')
        if code in ('invivo_summary',):
            continue  # already handled in invivo branch
        try:
            if default_storage.exists(det['saved_path']):
                default_storage.delete(det['saved_path'])
        except Exception:
            pass

    # Update target_name for all compounds touched in this upload (required, validated above)
    if not (invitro_errors and invivo_errors):
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

    del request.session['smart_preview']

    parts = []
    if n_experiments:
        parts.append(f'{n_experiments} 条体外实验')
    if n_invivo:
        parts.append(f'{n_invivo} 条体内实验')
    if n_attachments:
        parts.append(f'{n_attachments} 个附件')

    all_err = invitro_errors + invivo_errors + attachment_errors
    if all_err:
        messages.warning(request, f'部分写入失败：{"；".join(all_err)}')
    else:
        messages.success(request, f'数据已上传：{", ".join(parts) or "0 条"}')

    return redirect('smart_upload')
```

- [ ] **Step 2: Run Django check**

```bash
/Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 3: Commit**

```bash
git add app01/views.py
git commit -m "feat: smart_upload_confirm requires target; handles readouts + attachments"
```

---

### Task 8: Delete `_extract_target_name_rules`, `_extract_target_name_llm`, and `ExtractTargetNameTest`

**Files:**
- Modify: `app01/views.py` — delete two functions
- Modify: `app01/tests.py` — delete `ExtractTargetNameTest`

- [ ] **Step 1: Delete the two helpers from `app01/views.py`**

Find this block:

```python
def _extract_target_name_rules(filename: str, file_bytes: bytes) -> str | None:
```

Find the bottom of `_extract_target_name_llm` (the second function). Delete both functions inclusive of their docstrings and bodies. Use grep to locate boundaries:

```bash
grep -n "^def _extract_target_name\|^def _build_smart_preview\|^@login_required" app01/views.py | head -10
```

Expected: `_extract_target_name_rules` and `_extract_target_name_llm` are gone after this step; `_build_smart_preview` remains; the next decorator (`@login_required` for `smart_upload_view`) immediately follows.

- [ ] **Step 2: Delete `ExtractTargetNameTest` from `app01/tests.py`**

Find the class block:

```python
# ---- ExtractTargetNameTest ----
class ExtractTargetNameTest(TestCase):
```

Delete from the `# ---- ExtractTargetNameTest ----` comment line through the end of the class (the last `def test_no_match_returns_none(self): ...` block).

Expected: the next class after deletion is whatever followed it (e.g., `class SmartUploadConfirmTargetNameTest(TestCase):`).

- [ ] **Step 3: Run the test suite to confirm those tests are gone and the rest still work**

```bash
/Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/python manage.py test app01.tests 2>&1 | tail -10
```

Expected: total test count drops by 6 (the number of `test_*` methods in `ExtractTargetNameTest`); `SmartUploadConfirmTargetNameTest` is still present and may have failures — those are addressed in Task 11.

- [ ] **Step 4: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "chore: drop _extract_target_name_rules/llm and their tests"
```

---

### Task 9: Template — Phase 2 file-type table, target required, attachment notice, JS for custom inputs

**Files:**
- Modify: `templates/smart_upload.html` — Phase 2 block (currently lines 58–302)
- The view (`smart_upload_view` GET path) must also pass `vocab_file_types` and `vocab_readouts` to the template — Step 1 adjusts that.

- [ ] **Step 1: Make the view pass vocab into the template**

In `app01/views.py`, find this block in `smart_upload_view` (GET path):

```python
    # GET
    if request.GET.get('preview') and 'smart_preview' in request.session:
        return render(request, 'smart_upload.html', {'preview': request.session['smart_preview']})

    if 'smart_preview' in request.session:
        del request.session['smart_preview']
    return render(request, 'smart_upload.html', {})
```

Replace with:

```python
    # GET — pass vocabularies for the dropdowns
    from app01.models import UploadVocabulary
    vocab_file_types = list(
        UploadVocabulary.objects.filter(category='file_type').order_by('-is_builtin', 'label')
    )
    vocab_readouts = list(
        UploadVocabulary.objects.filter(category='invivo_readout').order_by('-is_builtin', 'label')
    )

    if request.GET.get('preview') and 'smart_preview' in request.session:
        return render(request, 'smart_upload.html', {
            'preview': request.session['smart_preview'],
            'vocab_file_types': vocab_file_types,
            'vocab_readouts': vocab_readouts,
        })

    if 'smart_preview' in request.session:
        del request.session['smart_preview']
    return render(request, 'smart_upload.html', {
        'vocab_file_types': vocab_file_types,
        'vocab_readouts': vocab_readouts,
    })
```

- [ ] **Step 2: Rewrite Phase 2 file-type table in `templates/smart_upload.html`**

Find this exact opening of Phase 2 (around line 58):

```html
  {% else %}
  {# ── Phase 2: Detection results + confirm ── #}
  <div class="ds-form-card-title">确认上传</div>

  {% if preview.llm_unavailable %}
```

And the closing `{% endif %}` of Phase 2 (`{% endif %}` followed by `</div>` of `ds-form-card` near line 302).

Replace the **file-type table form** (from `<form method="POST" action="{% url 'smart_upload' %}">` with `<input type="hidden" name="reparse" value="1">` through its closing `</form>` and the `<div style="display:flex;gap:10px;...` re-parse buttons block) — currently lines 68 through ~126 — with:

```html
  {# File classification table + re-parse form #}
  <form method="POST" action="{% url 'smart_upload' %}">
    {% csrf_token %}
    <input type="hidden" name="reparse" value="1">
    <input type="hidden" name="file_count" value="{{ preview.file_detections|length }}">

    <div style="font-size:12px;font-weight:600;color:#374151;margin-bottom:8px;">
      文件分类(请逐个选择类型)
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:12px;margin-bottom:12px;">
      <thead>
        <tr style="border-bottom:1px solid #e2e8f0;">
          <th style="text-align:left;padding:6px 8px;color:#64748b;font-weight:600;width:40%;">文件名</th>
          <th style="text-align:left;padding:6px 8px;color:#64748b;font-weight:600;">类型 *</th>
        </tr>
      </thead>
      <tbody>
        {% for det in preview.file_detections %}
        <tr style="border-bottom:1px solid #f1f5f9;">
          <td style="padding:6px 8px;">{{ det.filename }}</td>
          <td style="padding:6px 8px;">
            <input type="hidden" name="saved_path_{{ forloop.counter0 }}" value="{{ det.saved_path }}">
            <input type="hidden" name="filename_{{ forloop.counter0 }}" value="{{ det.filename }}">
            <select name="file_type_{{ forloop.counter0 }}" class="ds-form-control" required
                    onchange="onTypeChange(this, {{ forloop.counter0 }})"
                    style="font-size:12px;padding:3px 6px;">
              <option value="">-- 请选择 --</option>
              {% for v in vocab_file_types %}
                <option value="{{ v.code }}" {% if v.code == det.file_type_code %}selected{% endif %}>{{ v.label }}</option>
              {% endfor %}
              <option value="__new__">+ 自定义类型...</option>
            </select>
            <input type="text" name="custom_label_{{ forloop.counter0 }}"
                   id="custom_input_{{ forloop.counter0 }}"
                   class="ds-form-control" placeholder="输入自定义类型名"
                   style="display:none;margin-top:6px;font-size:12px;padding:3px 6px;">
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>

    <div style="display:flex;gap:10px;align-items:center;margin-bottom:24px;">
      <button type="submit" class="ds-btn ds-btn-ghost">↻ 重新解析</button>
      <a href="{% url 'smart_upload' %}" class="ds-btn ds-btn-ghost"
         style="color:#64748b;">✕ 重新选择文件</a>
    </div>
  </form>

  <script>
    function onTypeChange(sel, i) {
      var ci = document.getElementById('custom_input_' + i);
      if (!ci) return;
      ci.style.display = (sel.value === '__new__') ? 'block' : 'none';
      ci.required = (sel.value === '__new__');
    }
  </script>
```

Also **remove the `{% if preview.llm_unavailable %}` warning block** (the orange "AI 识别暂不可用" notice — currently lines 62–66). The Phase 2 title and `{% if errors %}` block above it stay unchanged.

- [ ] **Step 3: Add attachment notice (just above the confirm button)**

In `templates/smart_upload.html`, find the closing of the in-vivo loop and the start of the 靶点 card:

```html
    {% endfor %}

    {% if preview.invitro or preview.invivo_groups %}
    <div style="border:1px solid #e2e8f0;border-radius:8px;padding:14px 16px;margin-bottom:16px;background:#f8fafc;">
      <div style="font-weight:600;font-size:13px;color:#1e293b;margin-bottom:10px;">🏷 靶点信息</div>
```

Replace the surrounding section with:

```html
    {% endfor %}

    {% if preview.attachment_files %}
    <div style="border:1px solid #fde68a;background:#fef9c3;border-radius:8px;padding:10px 14px;margin-bottom:16px;font-size:12px;color:#92400e;">
      ⓘ {{ preview.attachment_files|length }} 个附件文件将作为项目附件保存,不参与数据解析:
      {% for af in preview.attachment_files %}
        <span style="background:white;border:1px solid #fde68a;border-radius:3px;padding:1px 6px;font-size:11px;margin-right:4px;">{{ af.filename }} ({{ af.label }})</span>
      {% endfor %}
    </div>
    {% endif %}

    {% if preview.invitro or preview.invivo_groups or preview.attachment_files %}
    <div style="border:1px solid #e2e8f0;border-radius:8px;padding:14px 16px;margin-bottom:16px;background:#f8fafc;">
      <div style="font-weight:600;font-size:13px;color:#1e293b;margin-bottom:10px;">🏷 靶点信息</div>
```

- [ ] **Step 4: Make 靶点 required + update helper text**

Find this block (the existing 靶点 input):

```html
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
        <label class="ds-form-label" style="margin-bottom:0;flex-shrink:0;">靶点名称</label>
        <input type="text" name="target_name" value="{{ preview.target_name }}"
               class="ds-form-control" style="width:180px;"
               placeholder="如 FASN、PCSK9（留空则不更新）">
        {% if preview.target_name %}
        <span style="font-size:11px;color:#64748b;background:#e0f2fe;border-radius:4px;padding:2px 7px;">自动提取</span>
        {% endif %}
        <span style="font-size:11px;color:#94a3b8;">本批所有空白靶点将更新为此值</span>
      </div>
```

Replace with:

```html
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
        <label class="ds-form-label" style="margin-bottom:0;flex-shrink:0;">靶点名称 *</label>
        <input type="text" name="target_name" value="{{ preview.target_name|default:'' }}"
               class="ds-form-control" style="width:180px;" required
               placeholder="如 FASN、PCSK9(必填)">
        <span style="font-size:11px;color:#94a3b8;">必填,所有空白靶点将更新为此值</span>
      </div>
```

- [ ] **Step 5: Update the "no parsed data" fallback**

Find this near the bottom of Phase 2:

```html
    {% if preview.invitro or preview.invivo_groups %}
    <div style="display:flex;gap:10px;align-items:center;margin-top:8px;">
      <button type="submit" class="ds-btn ds-btn-primary">确认上传 →</button>
    </div>
    {% else %}
    <div style="color:#64748b;font-size:12px;margin-top:8px;">
      未解析到可写入数据。请调整文件类型后点击"重新解析"。
    </div>
    {% endif %}
```

Replace with:

```html
    {% if preview.invitro or preview.invivo_groups or preview.attachment_files %}
    <div style="display:flex;gap:10px;align-items:center;margin-top:8px;">
      <button type="submit" class="ds-btn ds-btn-primary">确认上传 →</button>
    </div>
    {% else %}
    <div style="color:#64748b;font-size:12px;margin-top:8px;">
      未识别到任何文件类型。请在上方为每个文件选择类型后点击"重新解析"。
    </div>
    {% endif %}
```

- [ ] **Step 6: Run Django check + open page**

```bash
/Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

If a dev server is up on `:8001`, refreshing `/upload/smart/` should render the upload form normally. Phase 2 cannot be verified yet without an actual upload, but the GET path must not error.

- [ ] **Step 7: Commit**

```bash
git add app01/views.py templates/smart_upload.html
git commit -m "feat: vocab-driven file-type dropdown + custom-input + required target in smart upload"
```

---

### Task 10: Template — in-line readout select inside reparse table; invivo card shows readout label only

**Files:**
- Modify: `templates/smart_upload.html` — extend each reparse-table row with a conditional readout block (visible only when `file_type == invivo_summary`); change the in-vivo card to display the readout label read-only

**Why in the reparse table:** The readout must be set BEFORE the preview is built — `_build_smart_preview` (Task 6) reads `readout_code` from each `file_detections` entry. The reparse form is where each file's classification (and readout) gets fixed. The confirm form just consumes the preview.

- [ ] **Step 1: Extend each reparse-table row with the readout block**

In `templates/smart_upload.html`, find the `<td>` cell from Task 9 (file-type select + custom_label input). Find this exact block:

```html
          <td style="padding:6px 8px;">
            <input type="hidden" name="saved_path_{{ forloop.counter0 }}" value="{{ det.saved_path }}">
            <input type="hidden" name="filename_{{ forloop.counter0 }}" value="{{ det.filename }}">
            <select name="file_type_{{ forloop.counter0 }}" class="ds-form-control" required
                    onchange="onTypeChange(this, {{ forloop.counter0 }})"
                    style="font-size:12px;padding:3px 6px;">
              <option value="">-- 请选择 --</option>
              {% for v in vocab_file_types %}
                <option value="{{ v.code }}" {% if v.code == det.file_type_code %}selected{% endif %}>{{ v.label }}</option>
              {% endfor %}
              <option value="__new__">+ 自定义类型...</option>
            </select>
            <input type="text" name="custom_label_{{ forloop.counter0 }}"
                   id="custom_input_{{ forloop.counter0 }}"
                   class="ds-form-control" placeholder="输入自定义类型名"
                   style="display:none;margin-top:6px;font-size:12px;padding:3px 6px;">
          </td>
```

Replace with:

```html
          <td style="padding:6px 8px;">
            <input type="hidden" name="saved_path_{{ forloop.counter0 }}" value="{{ det.saved_path }}">
            <input type="hidden" name="filename_{{ forloop.counter0 }}" value="{{ det.filename }}">
            <select name="file_type_{{ forloop.counter0 }}" class="ds-form-control" required
                    onchange="onTypeChange(this, {{ forloop.counter0 }})"
                    style="font-size:12px;padding:3px 6px;">
              <option value="">-- 请选择 --</option>
              {% for v in vocab_file_types %}
                <option value="{{ v.code }}" {% if v.code == det.file_type_code %}selected{% endif %}>{{ v.label }}</option>
              {% endfor %}
              <option value="__new__">+ 自定义类型...</option>
            </select>
            <input type="text" name="custom_label_{{ forloop.counter0 }}"
                   id="custom_input_{{ forloop.counter0 }}"
                   class="ds-form-control" placeholder="输入自定义类型名"
                   style="display:none;margin-top:6px;font-size:12px;padding:3px 6px;">

            {# Readout block — visible only when file type is invivo_summary #}
            <div id="readout_block_{{ forloop.counter0 }}"
                 style="margin-top:6px;{% if det.file_type_code != 'invivo_summary' %}display:none;{% endif %}">
              <label style="font-size:10px;color:#64748b;">体内 readout *</label>
              <select name="readout_{{ forloop.counter0 }}" class="ds-form-control"
                      {% if det.file_type_code == 'invivo_summary' %}required{% endif %}
                      onchange="onReadoutChange(this, {{ forloop.counter0 }})"
                      style="font-size:12px;padding:3px 6px;">
                <option value="">-- 选择 --</option>
                {% for r in vocab_readouts %}
                  <option value="{{ r.code }}" {% if r.code == det.readout_code %}selected{% endif %}>{{ r.label }}</option>
                {% endfor %}
                <option value="__new__">+ 自定义...</option>
              </select>
              <input type="text" name="readout_custom_{{ forloop.counter0 }}"
                     id="readout_custom_input_{{ forloop.counter0 }}"
                     class="ds-form-control" placeholder="输入自定义 readout 名"
                     style="display:none;margin-top:4px;font-size:12px;padding:3px 6px;">
            </div>
          </td>
```

- [ ] **Step 2: Extend the JS handlers**

Replace the `<script>` block added in Task 9 Step 2 (the `onTypeChange` function) with the expanded version:

Find:

```html
  <script>
    function onTypeChange(sel, i) {
      var ci = document.getElementById('custom_input_' + i);
      if (!ci) return;
      ci.style.display = (sel.value === '__new__') ? 'block' : 'none';
      ci.required = (sel.value === '__new__');
    }
  </script>
```

Replace with:

```html
  <script>
    function onTypeChange(sel, i) {
      var ci = document.getElementById('custom_input_' + i);
      if (ci) {
        ci.style.display = (sel.value === '__new__') ? 'block' : 'none';
        ci.required = (sel.value === '__new__');
      }
      var rb = document.getElementById('readout_block_' + i);
      if (rb) {
        var isInvivo = (sel.value === 'invivo_summary');
        rb.style.display = isInvivo ? 'block' : 'none';
        var rs = rb.querySelector('select[name="readout_' + i + '"]');
        if (rs) rs.required = isInvivo;
      }
    }
    function onReadoutChange(sel, i) {
      var ci = document.getElementById('readout_custom_input_' + i);
      if (!ci) return;
      ci.style.display = (sel.value === '__new__') ? 'block' : 'none';
      ci.required = (sel.value === '__new__');
    }
  </script>
```

- [ ] **Step 3: Change the invivo card to show readout label as read-only metadata**

Find this exact opening of the invivo card loop:

```html
    {% for g in preview.invivo_groups %}
    <div style="border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin-bottom:20px;">
      <div style="font-weight:600;font-size:13px;color:#1e293b;margin-bottom:4px;">
        🐭 体内数据：{{ g.filename }}
      </div>
      <div style="font-size:11px;color:#64748b;margin-bottom:12px;">
        类型：{% if g.readout_type == 'knockdown_pct' %}KD% 时间曲线{% else %}体重时间曲线{% endif %}
        &nbsp;·&nbsp; {{ g.groups|length }} 组化合物
      </div>
```

Replace the type/count line with:

```html
    {% for g in preview.invivo_groups %}
    <div style="border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin-bottom:20px;">
      <div style="font-weight:600;font-size:13px;color:#1e293b;margin-bottom:4px;">
        🐭 体内数据：{{ g.filename }}
      </div>
      <div style="font-size:11px;color:#64748b;margin-bottom:12px;">
        readout: <strong>{{ g.readout_label }}</strong>
        &nbsp;·&nbsp; {{ g.groups|length }} 组化合物
      </div>
```

(The existing time_unit/dose/species/etc. fields after this block are unchanged.)

- [ ] **Step 4: Run Django check**

```bash
/Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 5: Commit**

```bash
git add templates/smart_upload.html
git commit -m "feat: in-line readout select in reparse table; invivo card shows readout label"
```

---

### Task 11: Update `SmartUploadConfirmTargetNameTest` for required-target behavior

**Files:**
- Modify: `app01/tests.py` — `SmartUploadConfirmTargetNameTest` class (currently around lines 1773–end-of-class)

The class currently builds a session with `target_name='FASN'` and tests that compounds get the target. With the new required target behavior:
- The session no longer holds an auto-extracted `target_name` (Task 6 dropped it from preview).
- The POST body must supply `target_name` (it always did — that's `target_name_input`). Tests already POST `target_name='X'`.
- A new test should cover: POSTing with empty `target_name` returns the form with an error and does NOT update any compound.

- [ ] **Step 1: Inspect the class to see current test methods**

```bash
grep -n "def test_" app01/tests.py | awk -F: '/SmartUploadConfirmTargetNameTest/{p=1} p' | head -20
sed -n '1773,1900p' app01/tests.py
```

Identify the existing methods and their structure.

- [ ] **Step 2: Update the `_make_session` helper to use the new preview shape**

Find:

```python
    def _make_session(self, compound_ids):
        """Store minimal smart_preview in session with given compound IDs."""
        experiments = [{'compound_id': cid, 'datapoints': [], 'summary': None} for cid in compound_ids]
        preview = {
            'project_code': 'TEST',
            'file_detections': [],
            'invitro': {
                'experiments': experiments,
                'strand_map': {cid: {} for cid in compound_ids},
                'new_compounds': [{'compound_id': cid} for cid in compound_ids],
                'assay_name': 'TestAssay',
                'cell_line': '',
                'notes': '',
            },
            'invivo_groups': [],
            'unknown_files': [],
            'errors': [],
            'llm_unavailable': False,
            'has_no_seq': True,
            'target_name': 'FASN',
        }
        session = self.client.session
        session['smart_preview'] = preview
        session.save()
```

Replace with:

```python
    def _make_session(self, compound_ids):
        """Store minimal smart_preview in session with given compound IDs."""
        experiments = [{'compound_id': cid, 'datapoints': [], 'summary': None} for cid in compound_ids]
        preview = {
            'project_code': 'TEST',
            'file_detections': [],
            'invitro': {
                'experiments': experiments,
                'strand_map': {cid: {} for cid in compound_ids},
                'new_compounds': [{'compound_id': cid} for cid in compound_ids],
                'assay_name': 'TestAssay',
                'cell_line': '',
                'notes': '',
            },
            'invivo_groups': [],
            'attachment_files': [],
            'errors': [],
            'has_no_seq': True,
        }
        session = self.client.session
        session['smart_preview'] = preview
        session.save()
```

- [ ] **Step 3: Add a new test method confirming empty target is rejected**

At the bottom of the `SmartUploadConfirmTargetNameTest` class, before its closing line, add:

```python
    def test_empty_target_name_rejected(self):
        Compound.objects.create(compound_id='BPR_TNTEST10', target_name='')
        self._make_session(['BPR_TNTEST10'])
        resp = self.client.post('/upload/smart/confirm/', {
            'batch_label': 'B20260618',
            'assay_name': 'TestAssay',
            'target_name': '',  # empty — must be rejected
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '靶点必填')
        # Compound stays unchanged
        c = Compound.objects.get(compound_id='BPR_TNTEST10')
        self.assertEqual(c.target_name, '')
```

- [ ] **Step 4: Run the relevant test class**

```bash
/Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/python manage.py test app01.tests.SmartUploadConfirmTargetNameTest -v 2 2>&1 | tail -20
```

Expected: all tests pass (the `test_empty_target_name_rejected` new test included).

- [ ] **Step 5: Run the full app01 test suite**

```bash
/Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/python manage.py test app01.tests 2>&1 | tail -10
```

Expected: the test count is down by 6 (deleted ExtractTargetNameTest) and up by 1 (new empty-target test); the pre-existing 2 failures + 6 errors (per pre-flight) should be unchanged.

- [ ] **Step 6: Commit**

```bash
git add app01/tests.py
git commit -m "test: smart upload confirm rejects empty target"
```

---

### Task 12: Final verification walkthrough

**Files:**
- No edits expected; verification only.

- [ ] **Step 1: Restart dev server, walk through the page**

Start (if not already running):

```bash
/Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/python manage.py runserver 8001
```

Open `http://localhost:8001/upload/smart/`.

- [ ] **Step 2: Verify Phase 1**

- Project code + file picker render normally
- Pick 2–3 sample CSVs from your test corpus, submit
- Expect redirect to `?preview=1`

- [ ] **Step 3: Verify Phase 2 — file-type table**

- Each row shows the filename and a dropdown defaulting to `-- 请选择 --`
- Dropdown contains all 6 built-in file types + `+ 自定义类型...`
- Confidence column is gone; "AI 不可用" banner is gone
- Click `+ 自定义类型...` on a row → inline text input appears below
- Choose `体内数据汇总` on a row → an additional readout block appears with preset readouts + `+ 自定义...`
- Switch off `体内数据汇总` → readout block hides again

- [ ] **Step 4: Verify reparse round-trip**

- Type a custom file type "我的测试附件" on a row
- Click "↻ 重新解析"
- Expect the page to refresh; that row's dropdown now shows "我的测试附件" as a selectable option (selected on this row), plus the original 6 built-ins
- Verify the entry exists in DB:
  ```bash
  /Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/python manage.py shell -c "
  from app01.models import UploadVocabulary
  print(list(UploadVocabulary.objects.filter(is_builtin=False).values_list('category','code','label')))
  "
  ```

- [ ] **Step 5: Verify attachment notice + custom-typed file confirms to ProjectAttachment**

- Pick the custom-typed file in reparse + assign any of the known parsing types to the other files
- After reparse, the "ⓘ N 个附件文件" notice appears with that filename + label
- Submit the confirm form with `target_name = FASN`
- Verify:
  ```bash
  /Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/python manage.py shell -c "
  from app01.models import ProjectAttachment
  for pa in ProjectAttachment.objects.all():
      print(pa.project, pa.label, pa.original_filename)
  "
  ```

- [ ] **Step 6: Verify target_name required**

- Restart from Phase 1, submit confirm with empty target field
- Expect an in-page error: "靶点必填,不能为空"
- No DB writes happen

- [ ] **Step 7: Verify invivo readout flows**

- Upload a known in-vivo CSV (`B20...invivo_kd.csv` or similar)
- Set its type to `体内数据汇总`, select readout `KD%`, fill in time_unit/species/etc., set target = something
- Confirm
- Verify `Experiment.exp_type='in_vivo'` records created with `assay_name='KD% 时间曲线'`
- Verify the `DataPoint.readout_type='knockdown_pct'` on the new datapoints

- [ ] **Step 8: Verify custom readout persists**

- Upload another in-vivo CSV; pick `体内数据汇总` + `+ 自定义...` readout, type `肝重指数`
- Reparse, then confirm with full metadata
- Check vocab:
  ```bash
  /Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/python manage.py shell -c "
  from app01.models import UploadVocabulary
  for v in UploadVocabulary.objects.filter(category='invivo_readout', is_builtin=False):
      print(v.code, v.label)
  "
  ```
  Expect a row matching `('肝重指数', '肝重指数')` (slugified code, original label).

- [ ] **Step 9: No JS console errors**

In DevTools console, confirm zero red errors on any of the above flows.

- [ ] **Step 10: No new commits expected here — only sign off**

If anything misfires, fix it under a `fix: ...` commit and re-verify.

---

## Self-Review Checklist

- [x] **Spec coverage:**
  - Drop rule/LLM detection (#1): Tasks 5, 8 (delete helpers + drop detect_* calls)
  - No "unknown / skip" (#2): Task 5 (dropdown defaults to "-- 请选择 --"; required attribute); Task 6 (no `unknown_files` list)
  - Rename Cp label (#3): Task 3 (seed label is "Cp 原始文件 (RT-qPCR)")
  - Custom types remembered (#4): Tasks 4 (`_ensure_vocab` helper), 5 (handles `__new__` POST), 9 (UI inline-input + JS toggle)
  - Merged in-vivo + readout picker (#5): Task 3 (single `invivo_summary` file_type + readout vocab), 6 (unified invivo parsing + readout_code/label), 7 (uses readout_code from preview), 10 (in-line readout select)
  - Target required (#6): Task 7 (server validation), 9 (HTML `required` + helper text), 11 (test)
  - Custom-type file → ProjectAttachment: Tasks 2, 6, 7

- [x] **No placeholders:** all code blocks contain runnable code; commands use absolute paths to the shared venv; no TBD / "implement later".

- [x] **Type consistency:**
  - `file_detections[*]` shape is `{filename, saved_path, file_type_code, readout_code}` everywhere it appears (Tasks 5, 6, template).
  - `preview['attachment_files'][*]` shape is `{filename, saved_path, vocab_code, label}` consistent across Tasks 6, 7, 9.
  - `preview['invivo_groups'][*]` carries `readout_code` and `readout_label` (Tasks 6, 7, 10).
  - `__new__` sentinel + `_ensure_vocab(category, label)` consistent across Tasks 4, 5, template handlers.
  - Migration ordering: 0005 (schema) → 0006 (seed). Task 3 explicitly depends on `0005`.
