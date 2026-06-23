# Smart Upload — Source File Association Redesign

## Goal

Unify the source-file attachment flow in smart upload so that every non-summary file is linked to a specific batch **and** specific experiments (vitro and/or vivo), replacing the fragmented `is_source_only` + `attachment_files` + `ProjectAttachment` split that currently routes files to different places depending on their type code.

## Architecture

Two and only two file types produce experiment records. Everything else is a source file that attaches to existing experiments.

| File type code | Action |
|---|---|
| `vitro_summary` | Parse → create `Experiment` + `DataPoint` records (in-vitro) |
| `invivo_summary` | Parse → create `Experiment` + `DataPoint` records (in-vivo) |
| All other types | Source file → user selects batch + experiment types → `ExperimentAttachment` created |

`vitro_cp`, `vitro_transfection`, `vitro_seq`, `custom_attachment`, and any user-added vocabulary all become source files. `vitro_cp` is no longer parsed to produce DataPoints — IC50/KD% values come from `vitro_summary`; the Cp file is kept as a raw-data reference attachment.

`ExperimentAttachment` model is unchanged (FK to `Experiment`). `ProjectAttachment` is no longer written by smart upload (the table is kept but unused by this flow).

## Feature Details

### 1. Source file collection

In `_build_smart_preview`, the current `attachment_files` list is renamed and expanded to `source_files`. Any file whose `file_type_code` is not `vitro_summary` or `invivo_summary` goes into `source_files` — including `vitro_cp`, `vitro_transfection`, `vitro_seq`, and every custom type. No parsing is attempted on source files.

The `invitro_type_files` dict (`vitro_cp`, `vitro_transfection`, `vitro_seq`) is removed. `vitro_cp` parsing code is removed. `vitro_transfection` parsing (`parse_transfection_file`) is removed. `vitro_seq` parsing (`parse_seq_file`) remains only when the file is tagged `vitro_seq` and uploaded together with `vitro_summary` (i.e. strand data is still extracted when creating new experiments — see §3).

The new `is_source_only` flag:
```python
is_source_only = bool(source_files) and not has_exp_data
# where has_exp_data = bool(invitro experiments) or bool(invivo_groups)
```

### 2. Source-file association UI (confirm page)

When `source_files` is non-empty and `is_source_only` is True, the confirm page shows:

```
📎 源文件（N 个）
  └ filename1   [type label]
  └ filename2   [type label]

批次：[下拉 — 仅列当前 project_code 下的批次]

关联实验：
  [✓] 体外 — assay_name · cell_line    (only shown if batch has in_vitro experiments)
  [✓] 体内 — readout_label · animal    (only shown if batch has in_vivo experiments)
```

**Batch dropdown** is populated server-side, filtered by `project_code`:
```python
available_batches = list(
    Experiment.objects
    .filter(compound__project=project_code)
    .values_list('batch_label', flat=True)
    .order_by()
    .distinct()
    .order_by('-batch_label')
)
```

**Experiment checkboxes** are populated client-side via JavaScript. The template pre-loads a JSON mapping of `{batch_label: [{exp_type, label, pk}]}` for all available batches. When the user changes the batch dropdown, JS renders the appropriate checkboxes — no AJAX required.

The experiment label for vitro: `assay_name` (or batch_label if blank). For vivo: `assay_name` or readout type + animal/route.

Form fields posted:
- `source_batch` — selected batch label
- `source_exp_vitro` — `"1"` if vitro checkbox checked
- `source_exp_vivo` — `"1"` if vivo checkbox checked

### 3. Auto-attach when creating experiments

When the same upload contains `vitro_summary` or `invivo_summary` alongside source files, source files are auto-attached — no extra UI needed.

- New vitro experiments created → all source files → `ExperimentAttachment(experiment=vitro_experiments[0])`
- New vivo experiments created → all source files → `ExperimentAttachment(experiment=invivo_exps[0])`
- Both created → two `ExperimentAttachment` records per source file (one vitro, one vivo)

This replaces the old `VITRO_SOURCE_CODES` allowlist. All source files get attached, not just the four previously hard-coded types.

`vitro_seq` parsing for strand updates is retained: when a `vitro_seq` file is uploaded together with `vitro_summary`, strand records are still created/updated as before. The `vitro_seq` file is additionally attached as a source file.

### 4. Confirm view changes (`smart_upload_confirm_view`)

```python
# Source-only path (new)
if is_source_only and source_files:
    source_batch = request.POST.get('source_batch', '').strip()
    attach_vitro = request.POST.get('source_exp_vitro') == '1'
    attach_vivo  = request.POST.get('source_exp_vivo')  == '1'

    target_exps = []
    if attach_vitro:
        exp = Experiment.objects.filter(batch_label=source_batch, exp_type='in_vitro').first()
        if exp: target_exps.append(exp)
    if attach_vivo:
        exp = Experiment.objects.filter(batch_label=source_batch, exp_type='in_vivo').first()
        if exp: target_exps.append(exp)

    for exp in target_exps:
        for sf in source_files:
            ExperimentAttachment(experiment=exp, label=sf['filename']).file.save(...)
```

Validation:
- `source_batch` required when `is_source_only`
- At least one of `source_exp_vitro` / `source_exp_vivo` must be checked

### 5. Vocabulary cleanup

- Delete the user-added `转染` UploadVocabulary entry (non-builtin duplicate of `vitro_transfection`). Applied as a data migration (`RunPython`).
- Rename `vitro_transfection` label from `"转染方案"` to `"转染"`.

### 6. Removed code paths

- `invitro_type_files` dict and parsing loops for `vitro_cp`, `vitro_transfection`
- `parse_transfection_file` call in `_build_smart_preview`
- `parse_cp_file` call in `_build_smart_preview`
- `VITRO_SOURCE_CODES` allowlist in confirm view
- `attachment_files` / `ProjectAttachment` write path in confirm view
- Old `is_source_only` logic (replaced by §1)

## Files Changed

| File | What changes |
|---|---|
| `app01/views.py` | `_build_smart_preview`: remove invitro_type_files parsing, add source_files; rewrite is_source_only; `smart_upload_confirm_view`: replace source-only and attachment paths |
| `templates/smart_upload.html` | Replace attachment_files section with source-file section (batch dropdown + experiment checkboxes + JS population) |
| `app01/migrations/NNNN_cleanup_upload_vocab.py` | Delete "转染" duplicate vocab; update "vitro_transfection" label |

## What Is Not Changed

- `ExperimentAttachment` model — unchanged
- `ProjectAttachment` model — table kept, just not written by smart upload
- `vitro_summary` parsing pipeline — unchanged
- `invivo_summary` parsing pipeline — unchanged  
- `vitro_seq` strand extraction when paired with `vitro_summary` — unchanged
- `parse_seq_file` import — kept (still used with vitro_seq + vitro_summary combo)
- Experiment display in compound list / compound detail — unchanged (attachments still render via existing ExperimentAttachment FK)
