# Prism 文件实验数据导入 — 设计规格

## 背景

实验数据主要来源于 GraphPad Prism 11，导出为 CSV 或 TXT（Tab 分隔）。现有 `upload_experiment` 视图要求"行格式"CSV（每行一个 DataPoint），与 Prism 的"宽格式"（每列一个 duplex，每行一个时间点）不兼容。本功能在现有上传页面增加 Prism 文件导入 Tab，用两步流程（上传→预览→确认）完成导入。

## Prism 文件格式约定

```
（空）    BP000001  BP000001  BP000001  BP000002  BP000002  BP000002  ...
-7       0.0000    0.0000    0.0000    0.0000    0.0000    0.0000
14       -95.67    -94.49    -95.24    -90.25    -83.26    -87.44
28       -97.16    -96.57    -93.37    -93.31    -85.17    -77.98
...
```

- **第 1 行**：第一列为空；后续列为 duplex ID，同一 ID 连续重复 3 次表示三个重复
- **第 1 列（第 2 行起）**：X 轴值（天数或浓度）
- **数据值**：浮点数；带 `*` 表示 Prism 标记为排除的点
- **格式**：`.csv` = 逗号分隔；`.txt` = Tab 分隔

## 架构

### 新增 URL / 视图

```
GET  /upload_experiment/         → 现有视图（加 Prism Tab，不动原逻辑）
POST /upload_prism_preview/      → 新视图：解析文件 → session → 渲染预览页
POST /upload_prism_confirm/      → 新视图：session 读取 → 写入 DB → 结果提示
```

### 模板变更

- `upload_experiment.html`：增加第二个 Tab "Prism 文件导入"（文件选择器 + 提交按钮）
- `upload_prism_preview.html`：新建，展示解析摘要 + 元数据表单 + 确认按钮

现有 `upload_experiment` POST 路径**完全不变**。

## 文件解析逻辑

函数 `parse_prism_file(file_obj, filename) → dict`

### 步骤

1. **格式检测**：扩展名 `.csv` → 逗号分隔；`.txt` → Tab 分隔；其他 → 报错
2. **Header 行解析**：
   - 跳过第一列
   - 按列名分组，连续相同列名 = 同一 duplex 的 3 个 replicate
   - 批量查询 `Delivery.objects.values('duplex_id').distinct()` 校验匹配
3. **数据行解析**：
   - 第一列转 float 为 x 轴值；解析失败则跳过该行并记录警告
   - 每个单元格：去首尾空格；带 `*` → 剥离 `*` 并标记 `excluded=True`；空字符串 → 跳过
4. **返回结构**：

```python
{
    "matched": {
        "BP000001": {
            "rows": [
                {"x": -7.0,  "replicates": [0.0, 0.0, 0.0], "excluded": [False, False, False]},
                {"x": 14.0,  "replicates": [-95.67, -94.49, -95.24], "excluded": [False, False, False]},
                ...
            ]
        },
        ...
    },
    "x_values": [-7.0, 14.0, 28.0, ...],
    "skipped_cols": ["PC (35013101)", "Alnylam", "SA030"],
    "warnings": [],
}
```

## 预览页

显示解析摘要：
```
✓ 识别到 N 个 duplex：BP000001, BP000002, ...
✗ 跳过 M 列（未匹配）：PC (35013101), Alnylam, ...
X 轴值：-7, 0, 14, 28, ... （K 个）
总数据点：N × K × 3 = P 个（含 Q 个 excluded 标注）
```

解析结果以 JSON 存入 Django session（key: `prism_parsed`），session 过期时间沿用默认值。项目使用 DB-backed session（`django.contrib.sessions.backends.db`），无大小限制；若为 cookie-based session，则在解析步骤加 50 KB 原始文件大小上限，超出时提示用户拆分文件。

## 元数据表单

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `exp_type` | 下拉 | ✓ | 体内 / 体外 |
| `assay_type` | 下拉 | ✓ | 体内药效 / 剂量效应 / 单点活性 / PK |
| `readout_type` | 下拉 | ✓ | knockdown_pct / mRNA_remaining / protein_remaining / plasma_conc / tissue_conc |
| `x_axis_type` | 下拉 | ✓ | `timepoint`（天）/ `concentration`（浓度/剂量） |
| `conc_unit` | 下拉 | 仅浓度 | nM / µM / mg/kg / µg/kg；JS 按 x_axis_type 显示/隐藏 |
| `batch` | 文本 | ✓ | |
| `exp_date` | 日期 | | YYYY-MM-DD |
| `cell_line` | 文本 | | exp_type=in_vitro 时显示 |
| `animal_species` | 文本 | | exp_type=in_vivo 时显示 |
| `route` | 文本 | | |
| `notes` | 文本 | | |

## 数据写入逻辑（`upload_prism_confirm`）

在 `transaction.atomic()` 内：

```
for each matched duplex_id:
    1. 重复检测：(duplex_id, exp_type, assay_type, batch) 已存在 → 跳过，记录警告
    2. 创建 Experiment 记录
    3. for each x_value, replicate_index (0/1/2):
         - value 为 None → 跳过
         - if x_axis_type == 'timepoint':
             timepoint = f"Day {x_value:g}"
             concentration_or_dose = None, conc_unit = None
         - if x_axis_type == 'concentration':
             concentration_or_dose = x_value
             conc_unit = user_input
             timepoint = None
         - replicate = "excluded" if excluded else str(replicate_index + 1)
         - 创建 DataPoint
```

结果跳转回 `upload_experiment` 并显示 flash message：
`成功导入 N 个实验、M 个数据点；跳过 K 个重复`

## 错误处理

| 情形 | 处理方式 |
|------|---------|
| 文件格式不支持 | 解析步骤报错，返回 upload 页并显示错误 |
| Header 行无任何匹配 | 报错：无可导入的 duplex |
| X 轴值解析失败 | 跳过该行，warnings 列表记录 |
| session 过期后访问确认 | 返回 upload 页，提示重新上传 |
| 全部 duplex 均重复 | 提示跳过原因，不创建任何记录 |

## 不涉及范围

- 不修改现有 `upload_experiment` 视图逻辑
- 不支持 `.prism` 原生格式（需在 Prism 中先导出）
- 不支持自动推断 readout_type（用户手动选择）
- 不支持导入后编辑单个 DataPoint
