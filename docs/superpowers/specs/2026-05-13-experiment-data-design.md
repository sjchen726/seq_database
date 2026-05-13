---
name: experiment-data
description: Design spec for siRNA experimental data management — in vitro and in vivo results linked to duplex_id, with two-tier data model, bulk upload, and seq_list summary display
metadata:
  type: project
---

# siRNA 实验数据管理 — 设计规范

## 背景

当前系统只管理序列注册和递送信息，没有存储实验活性数据的地方。研究人员需要将体外（细胞系 knockdown、剂量-效应曲线）和体内（动物实验 knockdown、PK 数据）的实验结果与序列关联起来，方便筛选和比较。

## 目标

- 支持体外（in vitro）和体内（in vivo）实验数据的录入和查看
- 实验记录关联到 `duplex_id`（双链整体，AS+SS 共享同一条实验记录）
- 支持手动填写和批量 CSV 上传两种录入方式
- 支持附件上传（本地文件）和外部链接
- `seq_list` 页面显示实验数据摘要，点击进入详情页

## 数据模型

### `Experiment`（实验记录，元数据层）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | AutoField PK | |
| `duplex_id` | CharField(24) | 关联 `Delivery.duplex_id`（非外键，字符串关联） |
| `exp_type` | CharField choices | `in_vitro` / `in_vivo` |
| `assay_type` | CharField choices | `single_point` / `dose_response` / `in_vivo_efficacy` / `pk` |
| `cell_line` | CharField(100) nullable | 体外：细胞系（如 HepG2、Huh7） |
| `animal_species` | CharField(100) nullable | 体内：动物种属（如 mouse / rat / monkey） |
| `batch` | CharField(64) | 批次号 |
| `exp_date` | DateField nullable | 实验日期 |
| `transfection_reagent` | CharField(100) nullable | 体外转染试剂（如 Lipofectamine） |
| `route` | CharField(20) nullable | 体内给药途径（SC / IV / PO） |
| `notes` | TextField nullable | 备注 |
| `created_by` | CharField(64) | 录入人用户名 |
| `created_at` | DateTimeField auto_now_add | |

### `DataPoint`（数据点，子记录层）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | AutoField PK | |
| `experiment` | FK → Experiment CASCADE | |
| `concentration_or_dose` | FloatField nullable | 浓度/剂量数值 |
| `conc_unit` | CharField(20) choices | `nM` / `mg_kg` / `ug_kg` / `uM` |
| `timepoint` | CharField(32) nullable | 时间点（如 `48h` / `Day7` / `Week4`） |
| `readout_type` | CharField(32) choices | `mRNA_remaining` / `protein_remaining` / `knockdown_pct` / `plasma_conc` / `tissue_conc` |
| `value` | FloatField | 数值 |
| `value_unit` | CharField(20) nullable | 单位（如 `%` / `ng_mL`） |
| `replicate` | CharField(32) nullable | 重复信息（如 `n=3`、`mean±SD`） |

### `ExperimentAttachment`（附件）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | AutoField PK | |
| `experiment` | FK → Experiment CASCADE | |
| `file` | FileField nullable | 上传文件，存 `MEDIA_ROOT/exp_attachments/` |
| `external_url` | URLField nullable | 外部链接（OneDrive、飞书等） |
| `label` | CharField(200) | 文件描述（如"原始 qPCR 数据"） |

约束：`file` 和 `external_url` 至少一个非空（在 `clean()` 方法中校验）。

## 录入入口

### 手动录入

- `seq_list` 页面每个 duplex 行的"操作"列新增"+ 实验"按钮
- 点击跳转到 `/experiment/add/?duplex_id=BP000001`
- 表单分两步：
  1. 填写实验元数据（exp_type、assay_type、cell_line/animal_species、batch、exp_date 等）
  2. 动态添加数据点（JS 动态增删行）+ 附件上传区域

### 批量 CSV 上传

新建 `/upload_experiment/` 页面，支持两种 CSV 格式：

**格式一：直接填 `duplex_id`**

```
duplex_id, exp_type, assay_type, cell_line, animal_species, batch, exp_date, transfection_reagent, route, conc, conc_unit, timepoint, readout_type, value, value_unit, replicate, notes
BP000001, in_vitro, single_point, HepG2, , B2024, 2024-03-01, Lipofectamine, , 10, nM, 48h, mRNA_remaining, 15, %, n=3,
BP000001, in_vitro, single_point, HepG2, , B2024, 2024-03-01, Lipofectamine, , 10, nM, 48h, protein_remaining, 22, %, n=3,
BP000001, in_vivo, in_vivo_efficacy, , mouse, B2024, 2024-04-01, , SC, 3, mg_kg, Day7, mRNA_remaining, 18, %, n=5,
```

**格式二：填修饰序列（AS/SS 上下两行为一组）**

```
modify_seq, exp_type, assay_type, cell_line, animal_species, batch, exp_date, conc, conc_unit, timepoint, readout_type, value, value_unit, replicate, notes
AmsCmsUmsGm..., in_vitro, single_point, HepG2, , B2024, 2024-03-01, 10, nM, 48h, mRNA_remaining, 15, %, n=3,
UmsGmsAmsGm..., in_vitro, single_point, HepG2, , B2024, 2024-03-01, 10, nM, 48h, mRNA_remaining, 15, %, n=3,
```

**序列匹配逻辑（格式二）：**
- 检测到 `modify_seq` 列（而非 `duplex_id` 列）时进入序列匹配模式
- 上下两行为一组（奇数行 + 偶数行），分别匹配数据库中的 AS 和 SS `modify_seq`
- 找到共同 `duplex_id` 的 AS+SS 配对才算匹配成功
- 匹配到多个 `duplex_id` 时报错，提示用户改用格式一手动指定
- 实验数据填在 AS 行或 SS 行均可，两行数据点合并到同一条 `Experiment`

**归并规则：**
同一 `duplex_id + batch + assay_type + cell_line + animal_species + exp_date` 的多行自动归并为一条 `Experiment` + 多条 `DataPoint`。

## 查看方式

### `seq_list` 摘要列

在"操作"列左侧新增独立的"实验数据"列（第 15 列，默认显示，可通过列显示面板隐藏）。显示规则：

- 有体外数据：显示最佳单点（如 `KD 85%@10nM`）或最低 IC₅₀（如 `IC₅₀ 0.3nM`，需 dose_response 数据）
- 有体内数据：显示最佳 knockdown（如 `in vivo 82%@3mpk`）
- 两者都有：体外 + 体内各一行
- 无数据：显示 `—`
- 点击摘要跳转到实验详情页

### 实验详情页 `/experiment/<duplex_id>/`

- 展示该 duplex 所有实验记录，按 `exp_type` 分组（体外/体内）
- 每条 `Experiment` 记录展开显示：元数据 + 数据点表格 + 附件列表
- 提供"编辑"和"删除"操作（`data_admin` 及以上角色）
- 提供"+ 添加实验"按钮

## 权限控制

- 查看：沿用 `permissions_project` 机制，用户能看到哪些项目的序列就能看到对应实验数据
- 录入：有项目权限即可录入
- 编辑/删除：仅限 `data_admin`、`admin`、`superadmin` 角色

## 涉及文件

| 文件 | 改动类型 |
|------|---------|
| `app01/models.py` | 新增 `Experiment`、`DataPoint`、`ExperimentAttachment` 模型 |
| `app01/migrations/0026_experiment.py` | 建表迁移 |
| `app01/views.py` | 新增 `experiment_detail`、`add_experiment`、`upload_experiment` 视图 |
| `bms/urls.py` | 新增 3 条路由 |
| `templates/experiment_detail.html` | 实验详情页（新建） |
| `templates/add_experiment.html` | 手动录入表单（新建） |
| `templates/upload_experiment.html` | 批量上传页面（新建） |
| `templates/seq_list.html` | 新增实验数据摘要列 |
| `static/js/add_experiment.js` | 数据点动态增删行（新建） |
| `bms/settings.py` | 配置 `MEDIA_ROOT` 和 `MEDIA_URL`（如未配置） |

## 非目标

- 本次不实现 IC₅₀ 自动计算（需要剂量-效应曲线拟合，作为后续功能）
- 本次不实现实验数据的跨项目共享（沿用 `DeliveryProject` 机制，实验数据通过 `duplex_id` 间接共享）
- 本次不实现实验数据的导出功能
