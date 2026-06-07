# BPRdb 子项目 A — Fork 与新数据模型设计

**日期：** 2026-06-07  
**范围：** 新 Django 项目的 fork 方案 + 核心数据模型定义  
**前置上下文：** 从当前 SeqDB（seq_database_v2）fork，保留前端展示和权限体系，替换数据模型。

---

## 一、Fork 方案

### 新项目基本信息

| 项目 | 说明 |
|------|------|
| 目录 | `seq_database_bprdb/`（与 seq_database_v2 并列） |
| Django 项目名 | `bprdb` |
| 应用名 | `app01`（保持一致） |
| 数据库 | 新建 MySQL DB，名称 `bprdb` |
| Python/Django 版本 | 同 seq_database_v2（Python 3.10，Django 5.1） |

### 保留的内容

| 类型 | 内容 |
|------|------|
| 模型 | `LmsUser`（含用户角色体系）、`SeqModule`、`LinkerModule`、`DeliveryModule` |
| 视图函数 | 所有序列着色函数：`get_modify_seq_colored`、`get_delivery_colored`、`detect_embedded_linker`、`build_duplex_groups` 及其依赖 |
| 静态资源 | `static/css/`（全部）、`static/js/`（通用部分：`tables.js`、`forms.js`、`drag.js`）、`static/vendors/` |
| 模板 | 基础布局（侧边栏、顶栏）、`char_block_SS.html`、`char_block_AS.html`、`_seq_group_row.html` |
| 权限逻辑 | `get_permitted_delivery_qs`、`user_can_edit_delivery`（按需适配新模型） |

### 移除的内容

| 模型/视图 | 原因 |
|-----------|------|
| `Sequence`、`DuplexRelationship`、`SeqInfo` | 由 `Compound` + `Strand` 替代 |
| `Delivery`、`DeliveryProject` | 合成/交付追踪不在新系统范围内 |
| `Experiment`、`DataPoint`、`ExperimentAttachment`（旧） | 由新实验模型替代 |
| `upload_delivery_info` 及 CSV pipeline | 由新上传流程（子项目 B）替代 |
| `seq_list` 视图及相关模板 | 由新化合物列表视图（子项目 C）替代 |

---

## 二、新数据模型

### 2.1 Compound（化合物，主实体）

一行 = 一个双链化合物（duplex）。Compound ID 直接使用化合物编号，无自动生成逻辑。

```python
class Compound(models.Model):
    compound_id   = models.CharField(max_length=32, primary_key=True)
    # 自动从 compound_id 提取，如 BPR_3M03FN01 → project="3M03", target="FN"
    project       = models.CharField(max_length=32, blank=True)
    target        = models.CharField(max_length=32, blank=True)
    transcript_ref = models.CharField(max_length=64, blank=True)  # NM_007988.3
    remarks       = models.TextField(blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)
```

**compound_id 解析规则：**

| compound_id | project | target |
|-------------|---------|--------|
| BPR_3M03FN01 | 3M03 | FN |
| BPR_3M03FN10 | 3M03 | FN |
| BPR_4A01CD05 | 4A01 | CD |

格式：`BPR_{project}{target}{2位序号}` 或 `BPR_{project}{target}{3位序号}`，上传时自动解析。

---

### 2.2 Strand（链，序列实体）

每个 Compound 最多两条链（SS + AS）。

```python
class Strand(models.Model):
    compound     = models.ForeignKey(Compound, on_delete=models.CASCADE,
                                     related_name='strands')
    strand_type  = models.CharField(max_length=4)   # 'SS' or 'AS'
    sequence_id  = models.CharField(max_length=64, blank=True)  # BPR_3M03FN01_SS
    modify_seq   = models.TextField(blank=True)     # mAmGfUmA...
```

`sequence_id` 来源：从 `ID_sequence.csv` 直接读取，或上传时自动生成（`{compound_id}_SS` / `{compound_id}_AS`）。

---

### 2.3 Experiment（实验批次）

一次上传对应一个 Experiment 记录，同一化合物可挂多个 Experiment。

```python
class Experiment(models.Model):
    EXP_TYPE_CHOICES = [('in_vitro', '体外'), ('in_vivo', '体内')]

    compound     = models.ForeignKey(Compound, on_delete=models.CASCADE,
                                     related_name='experiments')
    exp_type     = models.CharField(max_length=16, choices=EXP_TYPE_CHOICES)
    assay_name   = models.CharField(max_length=128)   # "FASN knockdown Hepa1-6"
    cell_line    = models.CharField(max_length=64, blank=True)  # 体外专用
    batch_label  = models.CharField(max_length=64, blank=True)  # 用户手填，如"2026-05"
    notes        = models.TextField(blank=True)
    date         = models.DateField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
```

---

### 2.4 DataPoint（测量值）

体内体外统一存储，`x_type` 区分浓度/时间点。

```python
class DataPoint(models.Model):
    X_TYPE_CHOICES = [('concentration', '浓度 nM'), ('timepoint', '时间点 天')]
    READOUT_CHOICES = [
        ('mRNA_remaining', 'mRNA 残余%'),
        ('knockdown_pct',  'KD%'),
    ]

    experiment    = models.ForeignKey(Experiment, on_delete=models.CASCADE,
                                      related_name='datapoints')
    x_value       = models.FloatField()            # nM 或 天
    x_type        = models.CharField(max_length=16, choices=X_TYPE_CHOICES)
    replicate     = models.CharField(max_length=8)  # A/B/1/2/3/Mean
    value         = models.FloatField()
    readout_type  = models.CharField(max_length=32, choices=READOUT_CHOICES)
    is_control    = models.BooleanField(default=False)   # Mock 对照
    is_flagged    = models.BooleanField(default=False)   # 异常标记（*）
    flag_note     = models.CharField(max_length=128, blank=True)
    raw_cp        = models.JSONField(null=True, blank=True)  # 见下方结构
```

**`raw_cp` JSON 结构**（体外 RT-qPCR 专用，其余为 null）：

```json
{
  "reference_gene": "GAPDH",
  "target_gene": "FASN",
  "cp_values": {
    "GAPDH": {"A": 16.06, "B": 16.18, "C": 16.07},
    "FASN":  {"A": 23.85, "B": 23.85, "C": 23.81}
  },
  "computed": {
    "GAPDH_mean": 16.07, "GAPDH_cv": 0.05,
    "FASN_mean": 23.85,  "FASN_cv": 0.02
  }
}
```

---

### 2.5 ExperimentSummary（体外实验汇总，一对一）

存储 Prism 曲线拟合后的汇总统计，每个体外 Experiment 对应一条记录。

```python
class ExperimentSummary(models.Model):
    experiment   = models.OneToOneField(Experiment, on_delete=models.CASCADE,
                                        related_name='summary')
    max_kd_pct   = models.FloatField(null=True, blank=True)   # 74.71
    ic50_nm      = models.FloatField(null=True, blank=True)   # 5.48
    rank         = models.IntegerField(null=True, blank=True) # 批次内排名
```

---

## 三、实体关系图

```
Compound (BPR_3M03FN01)
  ├── Strand × 1-2        (SS, AS 序列)
  └── Experiment × N      (每次上传一批)
        ├── DataPoint × N (原始剂量/时间点数据)
        └── ExperimentSummary × 1  (体外：IC50, Max KD, Rank)
```

---

## 四、ID 格式统一策略

上传时出现格式不一致（如 `BPR_3M03FN01` vs `BPR_3M03FN001`），处理流程：

1. 系统检测上传文件中出现的 ID 格式
2. 上传确认页显示检测到的格式，提示用户：
   > "检测到化合物编号格式为 `BPR_3M03FN001`（3位序号），数据库中已有格式为 `BPR_3M03FN01`（2位），是否统一为 2 位格式？"
3. 用户确认后，系统按选定格式规范化所有 ID 后再入库

数据库中 `compound_id` 统一存储用户最终确认的格式，不做自动推断转换。

---

## 五、迁移策略

1. `python manage.py makemigrations` 生成初始迁移
2. `python manage.py migrate` 建表
3. `SeqModule`、`LinkerModule`、`DeliveryModule` 数据通过 `dumpdata` / `loaddata` 从旧库迁移
4. `LmsUser` 数据同上迁移（用户账号复用）

---

## 六、涉及文件

| 文件 | 变更 |
|------|------|
| `app01/models.py` | 全量替换为上述 5 个模型 |
| `bprdb/settings.py` | 新数据库配置，`INSTALLED_APPS` |
| `app01/migrations/` | 全新初始迁移 |
| `app01/views.py` | 保留着色函数，移除旧视图，新增 stub 视图 |
| `bprdb/urls.py` | 新路由（placeholder） |

---

## 七、边界说明

- 本子项目 **只负责** fork 搭建 + 模型定义 + 初始迁移，不包含任何视图或上传逻辑
- 上传 pipeline 在子项目 B 中实现
- 列表展示在子项目 C 中实现
- 实验数据展示在子项目 D 中实现
