# In Vivo Data Model & Parser — Design Spec

## Goal

Extend BPRdb to support in vivo experimental data: KD% time-course (Data2 format) and body weight time-course (Data3 format). Adds animal model metadata to the schema, two new parsers, a dedicated upload preview flow, and raw-file attachment storage.

## Scope

Sub-project B of a three-part redesign (B → A smart upload → C display overhaul). Produces a working standalone in vivo upload flow; sub-project A will integrate it into a unified single-endpoint upload later.

---

## Part 1 — Data Model Changes

### 1.1 `Experiment` — six new fields (all `blank=True`, no impact on existing in vitro rows)

| Field | Type | Example |
|-------|------|---------|
| `animal_species` | CharField(32) | `"mouse"` |
| `animal_strain` | CharField(64) | `"C57BL/6"` |
| `route` | CharField(32) | `"SC"`, `"IV"` |
| `gender` | CharField(16) | `"male"`, `"female"`, `"mixed"` |
| `time_unit` | CharField(16) | `"day"`, `"week"` |
| `dose_info` | CharField(64) | `"3mpk Q2W×3"` (parsed from Data3 column header; blank when user supplies dose for Data2) |

### 1.2 `DataPoint.READOUT_CHOICES` — new entry

```python
('body_weight', '体重 g')
```

Existing choices (`mRNA_remaining`, `knockdown_pct`) are unchanged.

### 1.3 New model: `ExperimentAttachment`

`ExperimentAttachment` does not yet exist in `app01/models.py` and must be created:

```python
class ExperimentAttachment(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE,
                                   related_name='attachments')
    file = models.FileField(upload_to='experiment_attachments/%Y/%m/')
    label = models.CharField(max_length=128, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'experiment_attachment'
```

Django `MEDIA_ROOT` must be configured in `settings.py` for file uploads. For in vivo uploads the raw CSV is stored here; each attachment is linked to the first Experiment in the batch (all experiments share one file per upload).

### 1.4 Migration

One migration file: `0025_add_invivo_fields.py`. Covers all new fields on `Experiment`, new `ExperimentAttachment` model, and new `READOUT_CHOICES` entry. All new Experiment fields have `blank=True` so no data backfill is needed.

---

## Part 2 — Parser Design

### 2.1 New dataclasses (in `app01/upload_pipeline.py`)

```python
@dataclass
class ParsedInVivoTimepoint:
    time: float       # e.g. 14.0
    mean: float
    sd: float
    n: int            # number of non-empty replicates used

@dataclass
class ParsedInVivoGroup:
    compound_id: str  # stored as-is from file, e.g. "350025087", "Saline"
    dose_info: str    # "3mpk Q2W*3" from Data3 header; "" for Data2 (user supplies)
    timepoints: list  # List[ParsedInVivoTimepoint]

@dataclass
class ParsedInVivoFile:
    readout_type: str        # 'knockdown_pct' | 'body_weight'
    groups: list             # List[ParsedInVivoGroup]
    inferred_time_unit: str  # 'day' | 'unknown'
    needs_dose: bool         # True → dose absent from file, must prompt user
```

### 2.2 `parse_invivo_kd_file(file) -> ParsedInVivoFile`

Input: **Data2 format** — header row has bare compound IDs (repeated per replicate), first column is time point (days, may be negative), values are KD% (may carry `*` suffix).

Algorithm:
1. Read with `_read_csv_text` + `csv.reader`
2. Header row (row 0): strip trailing spaces from each cell; group consecutive identical non-empty cells → each group is one compound's replicate columns
3. For each subsequent row:
   - First cell = time point; skip row if empty
   - For each compound group: collect non-empty cells, strip `*`, cast to float
   - Compute `mean = statistics.mean(values)`, `sd = statistics.stdev(values) if len(values) > 1 else 0.0` (sample SD, n-1 denominator, appropriate for small biological replicates), `n = len(values)`
   - Skip time point if all values empty
4. Time unit inference: any time point < 0 → `inferred_time_unit = 'day'`; otherwise `'unknown'`
5. `needs_dose = True`

### 2.3 `parse_body_weight_file(file) -> ParsedInVivoFile`

Input: **Data3 format** — header row contains `"compound_id dose schedule"` strings (repeated per replicate), first column is time point, values are body weight in grams (may carry `*` suffix).

Algorithm:
1. Header row: for each non-empty cell, split on first space → `compound_id = parts[0]`, `dose_info = ' '.join(parts[1:])` (stripped of `*`); group consecutive identical full-header strings → replicate groups identified by `(compound_id, dose_info)`
2. For each subsequent row: same mean/SD calculation as above
3. Time unit inference: same rule (negative → day; else unknown)
4. `needs_dose = False` (dose already in header)

### 2.4 Shared logic

- Strip `*` suffix: `val.rstrip('*')` before float conversion
- Skip empty cells silently (treat as missing replicate)
- If `n == 1`: `sd = 0.0`; CV will be shown as N/A in display
- CV is never stored; computed on display: `abs(sd / mean) × 100%` when `mean != 0`

---

## Part 3 — File Type Detection (Rule-Based)

Applied before calling the appropriate parser:

| Signal | Conclusion |
|--------|-----------|
| Column header contains a space + digit pattern (e.g. `"350025087 3mpk"`) | `body_weight` → call `parse_body_weight_file` |
| Column headers are bare identifiers (no spaces with digits), values range -100 ~ 0 | `knockdown_pct` → call `parse_invivo_kd_file` |
| Neither rule matches | Show "无法判断文件类型" + dropdown for user to select manually |

Sub-project A (LLM-assisted upload) will enhance this detection; for now rule-based is sufficient.

---

## Part 4 — Upload Preview Flow

### 4.1 New view: `invivo_upload_view` (GET + POST)

**GET**: render `invivo_upload.html` with an empty upload form.

**POST (step 1 — file submission)**:
1. Read `request.FILES['invivo_file']` and `request.POST['project_code']` (required)
2. Detect file type → call appropriate parser
3. Store `ParsedInVivoFile` result in session as `request.session['invivo_preview']`
4. Determine whether user confirmation is needed for:
   - Time unit: `inferred_time_unit == 'unknown'` → show time point list, ask user
   - Dose: `needs_dose == True` → show dose input field
   - Animal model: always required (species/strain/route/gender)
5. Render `invivo_upload.html` with preview context

**POST (step 2 — confirm)**:
1. Read session preview + user-supplied form fields
2. Validate: project_code, time_unit, dose (if needs_dose), species, strain, route, gender all present
3. Write to DB (see §4.2)
4. Save original file as `ExperimentAttachment`
5. Redirect to success page or batch list

### 4.2 DB Write Logic

For each `ParsedInVivoGroup` in `parsed.groups`:
1. `compound, _ = Compound.objects.get_or_create(compound_id=group.compound_id)` — ID stored as-is
2. `Experiment.objects.create(compound=compound, exp_type='in_vivo', assay_name=<readout_type label>, batch_label=<auto-generated>, cell_line='', animal_species=..., animal_strain=..., route=..., gender=..., time_unit=..., dose_info=group.dose_info or user_supplied_dose)`
3. For each `ParsedInVivoTimepoint`:
   - `DataPoint(experiment=exp, x_value=tp.time, x_type='timepoint', replicate='Mean', value=tp.mean, readout_type=parsed.readout_type)`
   - `DataPoint(experiment=exp, x_value=tp.time, x_type='timepoint', replicate='SD', value=tp.sd, readout_type=parsed.readout_type)`
4. `ExperimentAttachment.objects.create(experiment=first_experiment_in_batch, file=uploaded_file, label='Raw data')`

### 4.3 Batch Label Auto-Generation

```python
batch_label = datetime.now().strftime('B%Y%m%d%H%M%S')
# e.g. "B20260615142315"
```

Same batch_label used for all experiments created in one upload session.

---

## Part 5 — Template: `invivo_upload.html`

Extends `base.html`. Two-phase form:

**Phase 1 (file selection):**
- Project code input (required)
- File upload input (`accept=".csv"`)
- Submit → "解析文件"

**Phase 2 (preview + confirm):**
- Detected compounds table: compound_id | dose_info | time points count
- Time unit selector: if `inferred_time_unit == 'unknown'` show all detected time points + radio "天/周/其他"
- Dose input: shown only if `needs_dose == True`
- Animal model form: 4 dropdowns/inputs (species, strain, route, gender)
- Warning banner if file type was user-selected (not auto-detected)
- Confirm button → POST step 2

---

## Part 6 — Route

Add to `bprdb/urls.py`:
```python
path('upload/invivo/', views.invivo_upload_view, name='invivo_upload'),
```

Add sidebar link in `base.html` under "数据录入":
```html
<a href="{% url 'invivo_upload' %}" class="ds-nav-item ...">
  <i class="bi bi-activity ds-nav-icon"></i> 上传体内数据
</a>
```

---

## Part 7 — Error Handling

| Scenario | Handling |
|----------|---------|
| File type undetectable | Show dropdown; block parse until user selects |
| Animal model fields empty | Form validation; block submission |
| Time unit not confirmed | Required radio; block submission |
| Dose missing + user didn't fill | Required input; block submission |
| All replicates empty for a time point | Skip that time point; no DataPoint written |
| n=1 (single replicate) | SD=0; CV shown as N/A in display |
| Compound ID not in DB | Auto-create `Compound` with as-is ID |
| Project code not provided | Required; block upload |
| File parse exception | Log warning; show error; no DB writes |

---

## Part 8 — Tests

- `ParseInVivoKdFileTest`: cell grouping, mean/SD computation, `*` stripping, negative time → day unit, empty cells skipped
- `ParseBodyWeightFileTest`: dose_info extraction from header, replicate grouping, n=1 edge case
- `InVivoUploadViewTest`: GET, POST step1 (session stored), POST step2 (DB records + attachment), missing fields → 400
- `InVivoPermissionTest`: login required

---

## Data Model — Summary of Changes

| Change | Type |
|--------|------|
| 6 new fields on `Experiment` | CharField, all blank=True |
| New `READOUT_CHOICES` entry `body_weight` | Enum addition |
| New `x_type` usage: `timepoint` already exists | No change |
| New migration `0025_add_invivo_fields.py` | 1 file |
| No new models | — |
