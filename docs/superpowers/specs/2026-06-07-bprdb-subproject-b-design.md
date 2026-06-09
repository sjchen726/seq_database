# BPRdb 子项目 B — Smart CSV 上传管道设计

**日期：** 2026-06-07  
**范围：** 实验数据 CSV 上传页面、解析逻辑、session 预览流程、写库  
**前置上下文：** 基于子项目 A 已完成的数据模型（Compound / Strand / Experiment / DataPoint / ExperimentSummary）

---

## 一、用户体验流程（UX Flow）

```
用户打开 /upload/
  ↓
填写文件槽 + 批次名称 → 点击 [解析预览]
  ↓  (POST /upload/)
后端解析 CSV → 存入 session → redirect GET /upload/?preview=1
  ↓
页面下方显示预览区（检测到的化合物、mapping 确认、冲突提示）
  ↓
用户确认 → 点击 [确认上传]
  ↓  (POST /upload/confirm/)
后端从 session 读取 → 写入数据库 → redirect /upload/success/
```

两次点击，无 JS 框架，Django 原生 POST + session + redirect。

---

## 二、上传页面字段

### 文件上传槽（同一页面，4 个独立 FileInput）

| 槽位 | 字段名 | 必填 | 格式说明 |
|------|--------|------|----------|
| 序列文件 | `seq_file` | 否 | `siRNAID, SS, AS` 三列 CSV |
| 体外汇总表 | `summary_file` | 否 | Prism 汇总格式（见第四节） |
| 原始 Cp 文件 | `cp_files` | 否 | 可上传多个文件，Prism 两步法格式（见第四节） |
| 体内数据 | `invivo_file` | 否 | 占位槽，本子项目不处理，显示「即将支持」提示 |

### 文本字段

| 字段 | 字段名 | 必填 | 说明 |
|------|--------|------|------|
| 批次名称 | `batch_label` | 是 | 用户手填，如 `2026-05`，存入 `Experiment.batch_label` |
| Assay 名称 | `assay_name` | 否 | 自动从 CSV 标题行提取；提取失败时用户手填 |
| 实验日期 | `exp_date` | 否 | 日期选择器，存入 `Experiment.date` |

---

## 三、URL 设计

| 方法 | URL | 视图函数 | 说明 |
|------|-----|----------|------|
| GET | `/upload/` | `upload_view` | 显示上传表单 |
| POST | `/upload/` | `upload_view` | 解析 CSV → session → redirect |
| POST | `/upload/confirm/` | `upload_confirm_view` | 从 session 写库 |
| GET | `/upload/success/` | `upload_success_view` | 成功页 |

redirect 逻辑：POST `/upload/` 成功后 → `redirect('/upload/?preview=1')`，模板判断 `request.GET.preview` 来显示预览区。

---

## 四、CSV 格式规范

### 4.1 序列文件（ID_sequence.csv）

```
siRNAID,SS,AS
BPR_3M03FN001,GmGmGmGmAmAmAfCmAfCfAfUmUmGmGmCmAmAmAmGmUm,AmCfUmUmdUG...
```

- 第 1 列：化合物 ID（`siRNAID` 列名，实际值为 BPR ID）
- 第 2 列：SS 序列（`modify_seq`）
- 第 3 列：AS 序列（`modify_seq`）
- `sequence_id` 自动生成为 `{compound_id}_SS` / `{compound_id}_AS`

### 4.2 体外汇总表（Prism 1_summary.csv 格式）

结构（行索引从 0 计）：

| 行 | 内容 |
|----|------|
| 0 | 空行 |
| 1 | 目标基因名称（如 `FASN mRNA`） |
| 2 | 列标题：左表 `#, ID, Dose (nM), A, B, Mean` + 右表 `#, ID, Name, Max KD, IC50 (nM), Rank` |
| 3+ | 数据行 |

**左表**（剂量响应数据）：
- `#` 行号，`ID` = siRNA 标签，`Dose (nM)` = 浓度，`A`/`B` = 两个生物重复，`Mean` = 均值
- `Dose == 'Mock'` → `is_control=True`，`x_value=0`，`x_type='concentration'`
- `value` 存储归一化 mRNA 残余比值（如 0.26），`readout_type='mRNA_remaining'`
- 每条 siRNA/剂量产生 3 个 DataPoint：`replicate='A'`、`replicate='B'`、`replicate='Mean'`

**右表**（汇总统计，也含 siRNA→BPR 映射）：
- `ID` = siRNA 标签，`Name` = BPR 化合物 ID → 提取为映射表
- `Max KD`（百分比，如 74.71）→ `ExperimentSummary.max_kd_pct`
- `IC50 (nM)` → `ExperimentSummary.ic50_nm`
- `Rank` → `ExperimentSummary.rank`

**检测方法**：扫描 CSV，找到同一行同时含 `Dose (nM)` 和 `IC50` 的行，确认为汇总表格式。

### 4.3 原始 Cp 文件（Prism 两步法 RT-qPCR 格式）

结构：

| 行 | 内容 |
|----|------|
| 0 | 空行 |
| 1 | 实验标题（如 `Two step RT-qPCR study in Hepa1-6 cells (Day 1)`）→ 提取为 `assay_name` |
| 2–4 | 多级列标题（跳过） |
| 5+ | 数据行 |

数据行列布局（列索引从 0）：

| 列 | 内容 |
|----|------|
| 0 | # |
| 1 | siRNA ID |
| 2 | 剂量 |
| 3–5 | GAPDH Cp 三重复（A, B, C） |
| 6–8 | FASN Cp 三重复（A, B, C） |
| 9 | GAPDH mean |
| 15 | FASN/GAPDH 比值 |
| 17–25 | 右表：`#, ID, Dose, A, B, Mean, CV, Correlation` |

**重复结构**：同一 siRNA/剂量组合在数据中出现两次：
- 第一次出现 → 生物重复 A 的 Cp 值
- 第二次出现 → 生物重复 B 的 Cp 值

**`raw_cp` JSON 结构**（存入对应 DataPoint）：

```json
{
  "reference_gene": "GAPDH",
  "target_gene": "FASN",
  "rep_A": {
    "GAPDH": [16.06, 16.18, 16.07],
    "FASN":  [23.85, 23.85, 23.81]
  },
  "rep_B": {
    "GAPDH": [16.17, 16.12, 16.43],
    "FASN":  [24.00, 24.01, 23.95]
  }
}
```

Cp JSON 挂载到 `replicate='A'` 和 `replicate='B'` 的 DataPoint 上（`replicate='Mean'` 不挂载）。

---

## 五、解析模块设计（`app01/upload_pipeline.py`）

```python
# 数据结构（dataclasses）
@dataclass
class ParsedSeqFile:
    rows: list[dict]  # [{compound_id, ss_seq, as_seq}]
    id_format: str    # '2-digit' | '3-digit' | 'mixed'

@dataclass
class ParsedSummary:
    assay_name: str
    mapping: dict          # {'siRNA-01': 'BPR_3M03FN01', ...}
    datapoints: list[dict] # [{compound_id, x_value, x_type, replicate, value, is_control, readout_type}]
    summaries: list[dict]  # [{compound_id, max_kd_pct, ic50_nm, rank}]

@dataclass
class ParsedCpFile:
    assay_name: str
    cp_data: dict  # {(siRNA_label, dose): {rep_A: {...}, rep_B: {...}}}
```

```python
# 公开函数
def parse_seq_file(file) -> ParsedSeqFile: ...
def parse_summary_csv(file) -> ParsedSummary: ...
def parse_cp_file(file) -> ParsedCpFile: ...
def enrich_datapoints_with_cp(datapoints, cp_data, mapping) -> list[dict]: ...
def detect_id_format(compound_ids: list[str]) -> str: ...
def normalize_compound_ids(ids: list[str], target_format: str) -> list[str]: ...
def detect_existing_compounds(compound_ids: list[str]) -> dict: ...
    # returns {'existing': [...], 'new': [...]}
def build_preview(seq_parsed, summary_parsed, cp_parsed_list, batch_label, assay_name) -> dict: ...
```

---

## 六、Session 数据结构

```python
request.session['upload_preview'] = {
    'batch_label': '2026-05',
    'assay_name': 'FASN knockdown Hepa1-6',
    'exp_date': '2026-05-10',   # ISO 格式字符串或 None

    # 序列文件解析结果
    'new_compounds': [           # 数据库中不存在的化合物
        {'compound_id': 'BPR_3M03FN01', 'ss_seq': '...', 'as_seq': '...'}
    ],
    'existing_compounds': ['BPR_3M03FN06', ...],  # 已存在，追加新批次
    'id_format_conflict': False,  # True = seq file 与 summary 格式不一致
    'chosen_format': None,        # 用户选择的格式：'2-digit' / '3-digit'

    # 体外汇总解析结果
    'mapping': {'siRNA-01': 'BPR_3M03FN01', ...},
    'experiments': [
        {
            'compound_id': 'BPR_3M03FN01',
            'exp_type': 'in_vitro',
            'datapoints': [...],   # 包含已 enrich 的 raw_cp
            'summary': {'max_kd_pct': 74.71, 'ic50_nm': 5.48, 'rank': 9}
        },
        ...
    ],

    'warnings': [                 # 非致命性提示
        'BPR_3M03FN03 已存在，将追加新批次数据',
    ],
    'errors': [],                 # 致命错误（有则不显示确认按钮）
}
```

---

## 七、现有化合物处理逻辑

| 情况 | 处理 |
|------|------|
| 化合物不存在 | 创建 Compound（+ Strand，如有序列文件） |
| 化合物已存在 | 在预览区显示提示；`confirm` 时直接追加新 Experiment，**不更新** Strand |
| 序列文件有数据但化合物已存在 | 序列数据静默忽略（不报错，不更新） |

---

## 八、ID 格式冲突处理

若上传文件中检测到两种 ID 格式（如序列文件 `BPR_3M03FN001` vs 汇总表 `BPR_3M03FN01`）：
1. 预览区显示警告 + 单选框：  
   > "检测到两种编号格式，请选择统一使用哪种："  
   > ○ 2 位序号（BPR_3M03FN01） ● 3 位序号（BPR_3M03FN001）
2. 用户选择后，`confirm` POST 中附带 `chosen_format` 参数
3. 写库前统一规范化所有 compound_id

若与数据库中已有格式冲突（数据库有 2 位，上传文件用 3 位），同样触发此提示。

---

## 九、错误与警告分级

| 级别 | 示例 | 处理 |
|------|------|------|
| `error`（阻断上传） | mapping 中的 siRNA 标签在汇总表数据列中找不到 | 预览区显示红色错误，隐藏「确认上传」按钮 |
| `error`（阻断上传） | 汇总表检测到的 BPR ID 在序列文件和数据库中均不存在 | 同上 |
| `warning`（可继续） | 化合物已存在，将追加批次 | 预览区黄色提示，仍显示「确认上传」 |
| `warning`（可继续） | ID 格式冲突，需用户选择 | 预览区黄色单选框 |
| `info` | Cp 文件未上传，raw_cp 将为 null | 预览区蓝色提示 |

---

## 十、写库流程（`upload_confirm_view`）

原子事务 `atomic()`：
1. 规范化 compound_id（若有格式选择）
2. 对 `new_compounds` 批量 `get_or_create(Compound)`
3. 对有序列的 new_compound 创建 `Strand`（SS + AS）
4. 对每个 experiment：  
   a. `Experiment.objects.create(...)`  
   b. `DataPoint.objects.bulk_create([...])`  
   c. `ExperimentSummary.objects.create(...)` (仅体外)
5. 清空 `request.session['upload_preview']`
6. Redirect → `/upload/success/`

---

## 十一、模板结构

### `templates/upload.html`

```
区域 1：上传表单
  - 4 个文件槽（拖拽 + 点击）
  - 批次名称（必填）
  - Assay 名称（可选）
  - 实验日期（可选）
  - [解析预览] 按钮

区域 2：预览区（仅当 ?preview=1 且 session 有数据时显示）
  - ✅ 检测到 10 个化合物（N 个新增，M 个已存在）
  - ✅ mapping 表格：siRNA-01 → BPR_3M03FN01 ...
  - ⚠️ 格式冲突选择（如有）
  - ⚠️ 已存在化合物提示
  - ❌ 错误列表（如有，则隐藏确认按钮）
  - [确认上传] 按钮（POST /upload/confirm/）
```

### `templates/upload_success.html`

显示：已写入 N 个化合物、M 个实验批次，提供「返回上传」和「查看化合物列表」链接。

---

## 十二、涉及文件

| 文件 | 变更 |
|------|------|
| `app01/upload_pipeline.py` | 新建：所有 CSV 解析函数 |
| `app01/views.py` | 新增：`upload_view`、`upload_confirm_view`、`upload_success_view` |
| `bprdb/urls.py` | 新增：`/upload/`、`/upload/confirm/`、`/upload/success/` |
| `templates/upload.html` | 新建：上传表单 + 预览区 |
| `templates/upload_success.html` | 新建：上传成功页 |
| `app01/tests.py` | 新增：解析函数单元测试 |

---

## 十三、边界说明

- 本子项目只负责上传管道（parse → preview → confirm → DB 写入）
- 体内数据槽为占位，本子项目**不实现**解析逻辑
- 化合物列表展示在子项目 C 中实现
- 实验数据详情展示在子项目 D 中实现
