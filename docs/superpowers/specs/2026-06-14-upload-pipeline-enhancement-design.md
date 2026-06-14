# Upload Pipeline Enhancement — Design Spec

## Goal

Extend the BPRdb upload pipeline to: (1) parse transfection protocol files and store all experimental metadata, (2) show Cp coverage per compound in the upload preview, (3) add a batch management page for listing and deleting uploaded batches.

## Scope

Three independent but co-located features in `app01/upload_pipeline.py`, `app01/views.py`, and templates.

---

## Part 1 — Transfection File Parser

### Input format (`5_Transfection in Hepa1-6.csv`)

- Row 1: `"Transfection in <CellLine>"` → cell line
- Bottom section contains an Items/Parameters table with rows: Cells, Seeding, Plate, Duration, Analysis, Primer
- Right-side columns contain siRNA → compound_id mapping (same format as summary file)

### New dataclass

```python
@dataclass
class ParsedTransfectionFile:
    cell_line: str   # e.g. "Hepa1-6"
    notes: str       # e.g. "Seeding: 20k/well; Duration: 24h; Analysis: RT-qPCR; Primer: FASN/GAPDH"
    mapping: dict    # {'siRNA-01': 'BPR_3M03FN01', ...} for cross-validation
```

### Parse logic (`parse_transfection_file(file) -> ParsedTransfectionFile`)

1. Read all rows with `_read_csv_text` + `csv.reader`
2. **Cell line**: scan rows for one whose first non-empty cell matches `r'^Transfection in (.+)$'`; capture group 1
3. **Parameters table**: find the row containing `"Items"` and `"Parameters"` as headers; then iterate following rows matching known keys:
   - `"Cells"` → cell_line (overrides title if present and non-empty)
   - `"Seeding"` → include in notes as `"Seeding: <value>"`
   - `"Duration"` → include in notes as `"Duration: <value>"`
   - `"Analysis"` → include in notes as `"Analysis: <value>"`
   - `"Primer"` → include in notes as `"Primer: <value>"`
4. **Mapping**: scan for a column header row containing `"ID"` and a column matching `r'^BPR_'` in following rows; build `{'siRNA-XX': 'BPR_...'}` dict
5. Assemble `notes` by joining non-empty key-value pairs with `"; "`

### Integration into upload pipeline

- `build_preview` accepts new parameter `transfection_parsed: ParsedTransfectionFile | None`
- If provided: add `cell_line` and `notes` keys to preview dict; merge mapping with summary mapping (summary takes precedence on conflict)
- `upload_confirm_view`: write `cell_line` and `notes` into `Experiment` defaults

### Upload form changes (`upload.html`)

- Add new file input: `<input type="file" name="transfection_file" accept=".csv">` labelled "转染方案文件（可选）"
- In preview section: show extracted parameters (cell line, seeding, duration, primer) in a metadata card for user confirmation

### Upload view changes (`upload_view`)

- Read `request.FILES.get('transfection_file')`; if present call `parse_transfection_file()`; pass result to `build_preview`

---

## Part 2 — Cp Coverage Visibility

### Problem

Files 2 and 3 cover Plate 1 (siRNA-01–05) and Plate 2 (siRNA-06–10) respectively. Users must upload both simultaneously via the multi-select Cp file input. Without both files, half the compounds have no raw_cp. The parser is correct; the gap is user awareness.

### Changes to `build_preview`

After calling `enrich_datapoints_with_cp`, compute per-compound Cp coverage:

```python
cp_coverage = {}   # {compound_id: True/False}
for cid, dps in dp_by_cid.items():
    has_cp = any(dp.get('raw_cp') for dp in dps if dp.get('replicate') in ('A', 'B'))
    cp_coverage[cid] = has_cp
```

Add `cp_coverage` to the preview dict.

### Upload preview display

In `upload.html` preview section: show a compact per-compound Cp status table:
- Green tick: compound has raw_cp on both A and B replicates
- Orange warning: compound has no Cp data

Add a summary line: `"X / Y 个化合物有完整 Cp 数据"`. If X < Y, show a warning banner: `"请检查是否遗漏 Cp 文件（每块板一个文件需同时上传）"`.

No changes to parser or DB schema — this is display-only.

---

## Part 3 — Batch Management Page

### New routes

```python
path('batches/', views.batch_list, name='batch_list'),
path('batches/<str:batch_label>/delete/', views.batch_delete, name='batch_delete'),
```

### `batch_list` view (GET, login_required)

Query all distinct `(batch_label, assay_name)` pairs from `Experiment`, annotate with:
- `compound_count = Count('compound_id', distinct=True)`
- `exp_count = Count('id')`
- `dp_count = Count('datapoints')`
- `cp_count = Count('datapoints', filter=Q(datapoints__raw_cp__isnull=False))`

Render `batch_manage.html` with this list sorted by batch_label descending.

### `batch_delete` view (POST, login_required, data_admin+ required)

- Receive `batch_label` from URL
- Delete all `Experiment.objects.filter(batch_label=batch_label)` — cascades to DataPoint and ExperimentSummary automatically
- Compounds are NOT deleted
- Redirect to `batch_list` with a success message

Permission check: `user.user_type not in ('data_admin', 'admin', 'superadmin') and not user.is_superuser` → return 403.

### `batch_manage.html` template

Extends `base.html`. Table columns:

| 批次名称 | Assay | 化合物数 | DataPoint 数 | raw_cp 覆盖率 | 创建时间 | 操作 |
|---------|-------|---------|-------------|--------------|---------|------|

- Delete button: `<form method="post" onsubmit="return confirm('确定删除批次 X 的所有实验数据？化合物记录保留。')">` 
- Only show delete button if user has `data_admin`+ role

### Sidebar entry

In `base.html`, under "数据录入" nav section, add:
```html
<a href="{% url 'batch_list' %}" class="ds-nav-item ...">
  <i class="bi bi-layers ds-nav-icon"></i> 批次管理
</a>
```

---

## Data Model — No Changes

All three features use existing fields:
- `Experiment.cell_line` (CharField, blank=True)
- `Experiment.notes` (TextField, blank=True)
- `DataPoint.raw_cp` (JSONField, nullable)

No migrations needed.

---

## Error Handling

- Transfection file parse failure: log warning, skip gracefully (cell_line and notes remain empty)
- Batch delete on non-existent batch_label: 404
- Batch delete by insufficient-role user: 403

## Testing

- `ParseTransfectionFileTest`: test cell_line extraction, notes assembly, mapping parse, graceful failure on malformed file
- `CpCoverageTest`: test `build_preview` returns correct `cp_coverage` dict with one/two/zero Cp files
- `BatchListViewTest`: test list renders correct counts
- `BatchDeleteViewTest`: test guest/data_admin roles, cascade delete, compound preservation
