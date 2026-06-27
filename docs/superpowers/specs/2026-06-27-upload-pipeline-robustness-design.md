# Upload Pipeline Robustness — Design Spec

**Date:** 2026-06-27  
**Sub-project:** A of 5 (Upload Pipeline Robustness)  
**Scope:** Issues A1–A10, C2, C3 from the 2026-06-27 project audit  

---

## 1. Background & Problem Statement

The current upload pipeline (`smart_upload_view` + `smart_upload_confirm_view` in `views.py`, `upload_pipeline.py`) has accumulated several reliability and correctness issues:

- **ID handling:** `normalize_compound_ids()` silently passes malformed IDs through; cross-format remapping (2-digit ↔ 3-digit) is applied to vitro uploads but completely skipped for invivo uploads, causing new compounds to be created with wrong-format IDs.
- **Duplicate detection:** The fingerprint used in `smart_upload_confirm_view` ignores `batch_label`, `control` flag, and floating-point precision, producing false positives and false negatives.
- **Re-upload semantics:** `Experiment.objects.get_or_create(compound, batch_label, assay_name)` over-matches — users cannot upload corrected data for the same compound/batch/assay. `Strand.objects.get_or_create` silently discards updated sequences with no user feedback.
- **Parsing errors:** Exceptions during file parsing expose internal stack traces; partial parse success is indistinguishable from total failure.
- **Other issues:** CP file gene detection silently defaults to GAPDH/FASN; siRNA mapping conflicts are logged but not surfaced to users; invivo metadata validation is too permissive; batch label generation is non-atomic under concurrent uploads.

**Goal:** Restructure the upload flow into a multi-phase validation pipeline that surfaces all issues before saving, gives users actionable choices for conflicts, and prevents data corruption.

---

## 2. Chosen Approach: Multi-Phase Validation Pipeline

The upload flow is restructured into 5 explicit phases. Each phase produces a structured output dict; the preview page renders the combined result before the user confirms.

**Rationale:** The existing code already has a functional two-step flow (upload → preview → confirm) and a partially-functional `upload_pipeline.py` with function-level separation. This approach extends that structure rather than replacing it, keeping risk low while giving each concern a clear home.

**Rejected alternative:** Async background validation (Celery) — current file sizes do not require it; the added infrastructure complexity is not justified.

---

## 3. Pipeline Architecture

### 3.1 Phase Definitions

```
Upload files
  → Phase 1: parse          — file format, column validation, row-level errors
  → Phase 2: normalize      — ID canonicalization + cross-format remap (vitro & invivo unified)
  → Phase 3: diff_strands   — compare upload sequences against DB Strands
  → Phase 4: dedup          — two-level duplicate detection (experiment → datapoint)
  → Phase 5: save           — atomic write, applies user choices from preview
```

### 3.2 Pipeline Result Structure

Each phase appends to a shared `pipeline_result` dict stored in `request.session`:

```python
pipeline_result = {
    "errors":        [],   # blocking; confirm button disabled while non-empty
    "warnings":      [],   # non-blocking; shown in preview, user may proceed
    "remap_log":     [],   # informational; ID mappings applied
    "strand_diffs":  [],   # requires user decision (keep / overwrite per diff)
    "dedup_report": {
        "exp_conflicts": [],   # experiment-level → auto version-append, informational
        "dp_conflicts":  [],   # datapoint-level → warning, user chooses skip/keep
    },
}
```

**Gating rule:** If `errors` is non-empty, the preview page disables the confirm button and shows an error panel. The user must fix the source file and re-upload. `warnings`, `strand_diffs`, and `dedup_report` entries never block submission.

### 3.3 View Split

`smart_upload_confirm_view` (~500 lines) is split into two views:

| View | Responsibility |
|------|----------------|
| `smart_upload_preview_view` (new) | Runs Phases 1–4; stores `pipeline_result` in session; renders preview page |
| `smart_upload_confirm_view` (reduced) | Reads `pipeline_result` from session; applies user choices; runs Phase 5 (atomic save) |

The existing `smart_upload_view` (file upload entry point) is unchanged.

---

## 4. Phase Specifications

### Phase 1 — Parse

**Existing functions preserved:** `parse_vitro_file()`, `parse_invivo_file()`, `parse_body_weight_file()`, `parse_cp_file()`, `parse_transfection_file()` are not rewritten. Changes:

- Wrap each call in a try/except that catches `Exception` and appends a user-friendly error (file name + short description) to `errors`, without exposing stack traces or internal paths.
- For CP file gene detection failure: append `warning` ("未检测到基因名，已使用默认值 GAPDH/FASN，请确认文件格式") instead of silently using the default.
- For siRNA mapping conflicts (`parse_transfection_file`): append `warning` ("检测到 siRNA {key} 对应多个 compound ID，已使用第一条映射，请核查源文件") instead of log-only.
- Partial row failures: collect per-row errors into `warnings` with row numbers; continue parsing remaining rows.

### Phase 2 — ID Normalization

New function `normalize_phase(compound_ids, upload_type) -> NormalizeResult` in `upload_pipeline.py`.

**Logic (applied to both vitro and invivo — unified):**

1. For each ID, call `canonicalize_compound_id(cid)`. If result differs from input, append to `remap_log`.
2. Query DB for cross-format match via existing `detect_cross_format_match()` (already exists for vitro). If a match is found and the DB compound ID differs from the canonical form, remap and append to `remap_log` with `"reason": "format_mismatch"`.
3. If `canonicalize_compound_id()` returns a value that does not match any known format regex, append to `errors` ("无法识别的ID格式: {cid}").
4. Body weight file: if a numeric ID is prefixed with `BPR_` automatically (existing logic), append `warning` ("已自动为数字ID补充前缀 BPR_，请确认这是正确的序列号").

**Key fix:** The invivo confirm path in `views.py` previously ignored `preview_copy['id_format_mismatch']`. Phase 2 is now called from `smart_upload_preview_view` for all upload types before any invivo-specific processing.

### Phase 3 — Strand Conflict Detection

New function `diff_strands(upload_strands) -> list[StrandDiff]` in `upload_pipeline.py`.

```python
@dataclass
class StrandDiff:
    compound_id: str
    strand_type: str        # e.g. "antisense", "sense"
    old_seq: str
    new_seq: str
    diff_positions: list[int]   # 0-indexed positions where bases differ
    user_choice: str | None     # "keep" | "overwrite" — set by preview page
```

- If `Strand` for `(compound_id, strand_type)` does not exist: no diff, normal create.
- If exists and `sequence == new_seq`: no diff (no-op).
- If exists and `sequence != new_seq`: create `StrandDiff`, append to `strand_diffs`.

The preview page renders each diff as a side-by-side old/new sequence with differing positions highlighted. The user selects "保留旧序列" (keep) or "用新序列覆盖" (overwrite) per diff. All diffs must have a `user_choice` set before the confirm button is enabled.

Phase 5 applies choices: `keep` → skip strand update; `overwrite` → call `strand.sequence = new_seq; strand.save()`.

### Phase 4 — Duplicate Detection (Two-Level)

**Level 1 — Experiment-level:**

Query: `Experiment.objects.filter(compound=compound, batch_label=batch_label, assay_name=assay_name)`.

If exists:
- Append to `dedup_report["exp_conflicts"]` as informational (not a warning or error).
- Mark the upload record with `action: "new_version"`.
- Phase 5 will create a new `Experiment` with `version = existing.version + 1` instead of raising an error.

**Level 2 — Datapoint-level (within same experiment):**

Build fingerprint set from existing `DataPoint` records for the matched experiment:
```python
fingerprint = (
    round(dp.x_value, 4),
    dp.replicate,
    round(dp.value, 4),
    dp.readout_type,
    dp.control,
)
```

For each upload datapoint, check against fingerprint set. Duplicates appended to `dedup_report["dp_conflicts"]` as `warnings`. Preview page shows the list with options "跳过这些数据点" (skip) or "仍然上传" (upload anyway). Default is skip.

**Batch label generation fix (D4):**

`_generate_batch_label()` currently queries `Experiment` rows for today's prefix then increments in Python — a race condition under concurrent uploads. Fix:

```python
def _generate_batch_label() -> str:
    from datetime import date
    prefix = date.today().strftime('%Y%m%d')
    with transaction.atomic():
        # Lock all matching rows for the duration of this transaction
        existing_nums = set(
            Experiment.objects
            .select_for_update()
            .filter(batch_label__startswith=prefix + '-')
            .values_list('batch_label', flat=True)
        )
        used = {int(bl[len(prefix)+1:]) for bl in existing_nums if bl[len(prefix)+1:].isdigit()}
        n = 1
        while n in used:
            n += 1
        # Caller must create the Experiment inside this same transaction
        return f'{prefix}-{n:03d}'
```

The caller (`smart_upload_confirm_view`) must create the `Experiment` record inside the same `transaction.atomic()` block so the lock is held until the row is written.

### Phase 5 — Save (Atomic)

Executed in `smart_upload_confirm_view` after user confirms on preview page.

```python
with transaction.atomic():
    # 1. Apply strand choices
    for diff in pipeline_result["strand_diffs"]:
        if diff["user_choice"] == "overwrite":
            strand = Strand.objects.get(compound_id=diff["compound_id"], strand_type=diff["strand_type"])
            strand.sequence = diff["new_seq"]
            strand.save(update_fields=["sequence"])

    # 2. Create/version Experiments
    for exp_data in upload_records:
        if exp_data.get("action") == "new_version":
            existing = Experiment.objects.filter(...).order_by("-version").first()
            experiment = Experiment.objects.create(..., version=existing.version + 1)
        else:
            experiment = Experiment.objects.create(..., version=1)

    # 3. Save DataPoints (skip dp_conflicts if user chose skip)
    ...

    # 4. Temp file cleanup (after successful commit only)
```

Temp file cleanup is moved **outside** the `atomic()` block and runs only after the transaction commits successfully, eliminating the resource leak in the current implementation (A5).

---

## 5. Data Model Changes

### 5.1 `Experiment.version` Field

```python
class Experiment(models.Model):
    # existing fields ...
    version = models.PositiveSmallIntegerField(default=1)
```

Migration: `0025_experiment_version.py` — adds `version` column with `DEFAULT 1`. No data backfill needed (all existing records are version 1 by definition).

The experiment detail page and compound list show the version number. No version-switching UI is required in this sub-project (deferred to sub-project B).

### 5.2 No Other Model Changes

`StrandDiff` is an in-memory dataclass, not persisted. No new models required.

---

## 6. Preview Page Changes

The existing preview template is extended (not replaced) with four panels rendered conditionally:

| Panel | Condition | User Action Required |
|-------|-----------|----------------------|
| 解析摘要 | Always | None |
| ID重映射日志 | `remap_log` non-empty | None (informational) |
| 序列冲突对比 | `strand_diffs` non-empty | Must choose keep/overwrite per diff |
| 重复检测报告 | `dedup_report` non-empty | Must choose dp skip/keep if dp_conflicts |

Confirm button is disabled until: no `errors` remain AND all `strand_diffs` have `user_choice` set AND all `dp_conflicts` groups have a skip/keep decision.

---

## 7. Files to Change

| File | Change |
|------|--------|
| `app01/upload_pipeline.py` | Add `normalize_phase()`, `diff_strands()`, `StrandDiff` dataclass; update `parse_*` functions for better error output |
| `app01/views.py` | Split confirm view; add `smart_upload_preview_view`; fix invivo remap path; fix batch label atomicity |
| `app01/models.py` | Add `Experiment.version` field |
| `app01/migrations/0025_experiment_version.py` | New migration |
| `templates/smart_upload_preview.html` | Add 4-panel conditional sections |
| `bms/urls.py` | Add URL for `smart_upload_preview_view` |

---

## 8. Out of Scope (Deferred)

- Version-switching UI on experiment detail page (sub-project B — page display)
- Numeric range validation on DataPoint values (A9) — low risk, deferred
- Rate limiting on file upload size (D3) — infrastructure concern, deferred
- Soft delete / audit trail (D9) — deferred to sub-project C
- Email notifications (D10) — deferred to sub-project E
