# 长表展示 — 设计文档（Sub-project X）

## 目标

将 `/compounds/` 化合物列表页从"每化合物一行摘要"改为"每浓度/时间点一行"的长表格式，同时完善化合物详情页图表和附件下载入口。

## 范围

仅覆盖展示层。上传流程（Sub-project Y）独立处理。

---

## Part 1 — 数据模型变更

### 1.1 唯一新增字段

```python
# app01/models.py — Compound 模型
target_name = models.CharField(max_length=128, blank=True)
# 含义：完整靶点名，如 "FASN"、"PCSK9"
# 区别于现有 target 字段（存 ID 里解析出的两字母缩写，如 "FN"）
# 来源：上传时从文件/DeepSeek 提取，或用户手动填写
```

### 1.2 现有字段复用（无需改动）

| 字段 | 位置 | 用途 |
|------|------|------|
| `Compound.project` | Compound | 从 compound_id 自动解析的项目号 |
| `Compound.target` | Compound | 两字母缩写（FN/PS 等） |
| `Compound.target_name` | Compound | **新增**：完整靶点名 |
| `Strand.modify_seq` + `strand_type` | Strand | SS/AS 序列展示 |
| `Experiment.exp_type` | Experiment | 'in_vitro' / 'in_vivo' |
| `Experiment.batch_label` | Experiment | 批次号（如 B202606151430） |
| `Experiment.dose_info` | Experiment | 体内给药方案（如 3mpk Q2W*3） |
| `Experiment.time_unit` | Experiment | 'day' / 'week' / 'month' |
| `Experiment.animal_species` + `animal_strain` | Experiment | 动物模型 |
| `ExperimentSummary.ic50_nm` | ExperimentSummary | IC50（体外） |
| `ExperimentSummary.max_kd_pct` | ExperimentSummary | MaxKD%（体外/体内） |
| `DataPoint.x_value` + `x_type` | DataPoint | 浓度(nM) 或 时间点 |
| `DataPoint.replicate` + `value` | DataPoint | A/B/Mean 等重复值 |
| `ExperimentAttachment.file` + `label` | ExperimentAttachment | 原始文件附件 |

### 1.3 迁移

```bash
python manage.py makemigrations app01 --name add_compound_target_name
python manage.py migrate
```

---

## Part 2 — 长表主页 `/compounds/`

### 2.1 URL

路由不变：`path('compounds/', views.compound_list, name='compound_list')`

新增附件下载路由：
```python
path('attachments/<int:pk>/download/', views.attachment_download, name='attachment_download')
```

### 2.2 筛选参数（GET）

| 参数 | 类型 | 作用 |
|------|------|------|
| `q` | 文本 | 模糊匹配 compound_id（ILIKE） |
| `project` | 选项 | 精确匹配 Compound.project |
| `target_name` | 选项 | 精确匹配 Compound.target_name |
| `tag` | 选项 | 'in_vitro' / 'in_vivo' / '' |
| `page` | 整数 | 分页页码，默认 1 |

筛选状态通过 GET 参数保留，刷新不丢失。

### 2.3 视图逻辑 `compound_list(request)`

```python
def compound_list(request):
    # 1. 读取筛选参数
    q = request.GET.get('q', '').strip()
    project = request.GET.get('project', '')
    target_name = request.GET.get('target_name', '')
    tag = request.GET.get('tag', '')

    # 2. 查询 Compound，prefetch 关联数据
    qs = Compound.objects.prefetch_related(
        'strands',
        Prefetch('experiments', queryset=Experiment.objects.select_related('summary')
                 .prefetch_related('datapoints', 'attachments')
                 .order_by('-batch_label'))
    )
    if q:
        qs = qs.filter(compound_id__icontains=q)
    if project:
        qs = qs.filter(project=project)
    if target_name:
        qs = qs.filter(target_name=target_name)
    if tag:
        qs = qs.filter(experiments__exp_type=tag).distinct()

    # 3. 分页（每页 20 个化合物）
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    # 4. 构建每个化合物的展示数据
    compound_data = []
    for compound in page_obj:
        strand_map = {s.strand_type: s.modify_seq for s in compound.strands.all()}
        batch_groups = _build_batch_groups(compound.experiments.all())
        compound_data.append({
            'compound': compound,
            'strand_map': strand_map,
            'batch_groups': batch_groups,
        })

    # 5. 筛选器选项
    all_projects = Compound.objects.exclude(project='').values_list('project', flat=True).distinct()
    all_targets = Compound.objects.exclude(target_name='').values_list('target_name', flat=True).distinct()

    return render(request, 'compound_list.html', {
        'compound_data': compound_data,
        'page_obj': page_obj,
        'all_projects': sorted(all_projects),
        'all_targets': sorted(all_targets),
        'q': q, 'project': project, 'target_name': target_name, 'tag': tag,
    })
```

### 2.4 `_build_batch_groups(experiments)` 辅助函数

```python
def _build_batch_groups(experiments):
    """
    将 Experiment queryset 转换为模板可用的分组列表。
    每个 Experiment 对应一个折叠块。
    """
    groups = []
    for exp in experiments:
        summary = getattr(exp, 'summary', None)
        datapoints = list(exp.datapoints.all())

        if exp.exp_type == 'in_vitro':
            rows = _build_vitro_rows(datapoints)
        else:
            rows = _build_invivo_rows(datapoints, exp.time_unit)

        groups.append({
            'experiment': exp,
            'summary': summary,
            'rows': rows,
            'attachments': list(exp.attachments.all()),
            'tag_label': '体外' if exp.exp_type == 'in_vitro' else '体内',
            'tag_css': 'tag-vitro' if exp.exp_type == 'in_vitro' else 'tag-invivo',
        })
    return groups
```

### 2.5 `_build_vitro_rows(datapoints)` — 体外行构建

每个浓度一行，只取 `replicate='Mean'` 的值：

```python
def _build_vitro_rows(datapoints):
    mean_points = [dp for dp in datapoints if dp.replicate == 'Mean' and not dp.is_control]
    mean_points.sort(key=lambda dp: -dp.x_value)  # 浓度从高到低
    return [{'dose': dp.x_value, 'mean': dp.value} for dp in mean_points]
```

### 2.6 `_build_invivo_rows(datapoints, time_unit)` — 体内行构建

按时间点分组，计算 mean/SD/CV；按 time_unit 过滤展示哪些时间点：

```python
import statistics

def _build_invivo_rows(datapoints, time_unit):
    # 按时间点分组，收集所有重复值（排除 is_control）
    from collections import defaultdict
    grouped = defaultdict(list)
    for dp in datapoints:
        if not dp.is_control and dp.replicate not in ('Mean', 'SD'):
            grouped[dp.x_value].append(dp.value)

    rows = []
    for timepoint in sorted(grouped):
        # 时间点过滤
        if time_unit == 'day' and timepoint % 7 != 0 and timepoint != 0:
            continue  # 只展示 0 和 7 的倍数

        vals = grouped[timepoint]
        n = len(vals)
        mean = statistics.mean(vals) if n else None
        sd = statistics.stdev(vals) if n >= 2 else None
        cv = (sd / abs(mean) * 100) if (sd is not None and mean and mean != 0) else None

        # 时间点标签
        if time_unit == 'day':
            label = f'Day {int(timepoint)}' if timepoint != timepoint % 1 == 0 else f'Day {timepoint:.0f}'
        elif time_unit == 'week':
            label = f'Week {int(timepoint)}'
        else:
            label = f'{timepoint} {time_unit}'

        rows.append({
            'label': label,
            'mean': round(mean, 2) if mean is not None else None,
            'sd': round(sd, 2) if sd is not None else None,
            'cv': round(cv, 1) if cv is not None else None,
            'n': n,
        })
    return rows
```

### 2.7 页面结构（`compound_list.html`）

```
顶部筛选栏
  [搜索框] [项目下拉] [靶点下拉] [体内/体外下拉] [搜索按钮]

化合物卡片（每个 compound）
  卡片头部：compound_id | target_name | project
  
  折叠块（每个 batch_group）
    折叠头（可点击）：
      体外：[体外徽章] IC50: X nM  MaxKD: X%  批次: B...
      体内：[体内徽章] MaxKD: X%  给药: dose_info  批次: B...
    
    展开内容（体外）：
      表格：Dose(nM) | Mean | [Sequence（首行显示 SS/AS）]
    
    展开内容（体内）：
      动物模型标注（species + strain + route + gender）
      表格：时间点 | Mean | SD | CV
      时间点筛选复选框（view-time 过滤，JS 控制）
    
    底部：[📎 原始文件列表] [📊 查看详情 →]

分页
```

### 2.8 折叠行为

- 每个化合物最新批次默认展开，旧批次折叠
- 折叠/展开由 vanilla JS 实现（Bootstrap collapse 组件）
- 时间点多选复选框：JS 监听 change 事件，显示/隐藏对应 `<tr>`

---

## Part 3 — 附件下载

### 3.1 `attachment_download(request, pk)` 视图

```python
@login_required
def attachment_download(request, pk):
    att = get_object_or_404(ExperimentAttachment, pk=pk)
    # 权限检查：确认用户有权访问该实验的化合物
    file_path = att.file.path
    filename = os.path.basename(file_path)
    response = FileResponse(open(file_path, 'rb'), as_attachment=True, filename=filename)
    return response
```

---

## Part 4 — 化合物详情页图表 `/compounds/<id>/`

### 4.1 视图更新 `compound_detail(request, compound_id)`

在现有基础上补充：
- 构建体外 IC50 曲线数据（按批次）
- 构建体内 KD% 时间曲线数据（按批次 + 剂量组）
- 构建体内体重时间曲线数据
- 附件列表

### 4.2 图表数据格式（内联 JSON）

**体外 IC50 曲线：**
```json
{
  "vitro_series": [
    {
      "batch": "B202606151430",
      "label": "体外 B202606",
      "data": [[0.00001, 0.89], [0.0001, 1.08], [0.001, 0.83], [0.01, 1.15], [0.1, 1.06], [1, 0.87], [10, 0.50], [100, 0.25]],
      "ic50": 5.48,
      "max_kd": 74.71
    }
  ]
}
```

**体内 KD% 时间曲线：**
```json
{
  "invivo_kd_series": [
    {
      "batch": "B202606151430",
      "dose": "3mpk Q2W*3",
      "label": "3mpk Q2W*3",
      "data": [[7, -30.5], [14, -95.7], [28, -97.2], [56, -95.9]],
      "error": [[7, 0.5], [14, 0.8], [28, 0.6], [56, 0.7]]
    }
  ]
}
```

### 4.3 图表（Flot.js）

| 图表 | X 轴 | Y 轴 | 类型 |
|------|------|------|------|
| IC50 浓度-效应曲线 | log10(Dose nM) | mRNA 残余% | 散点 + 折线 |
| MaxKD 柱状图 | 批次 | MaxKD% | 柱状 |
| KD% 时间曲线 | 时间点 | KD% | 折线 + 误差棒 |
| 体重时间曲线 | 时间点 | 体重(g) | 折线 + 误差棒 |

多批次用标签页切换（Bootstrap tabs），每张图按剂量组用不同颜色区分。

---

## Part 5 — 文件变更一览

| 文件 | 变更 |
|------|------|
| `app01/models.py` | `Compound` 加 `target_name` 字段 |
| `app01/migrations/` | 新增 migration |
| `app01/views.py` | 重写 `compound_list`；更新 `compound_detail`；新增 `attachment_download`；新增 `_build_batch_groups`、`_build_vitro_rows`、`_build_invivo_rows` |
| `bprdb/urls.py` | 新增 `attachment_download` 路由 |
| `templates/compound_list.html` | 完全重写为长表格式 |
| `templates/compound_detail.html` | 更新图表数据 + 附件列表 |
| `app01/tests.py` | 新增 `BuildVitroRowsTest`、`BuildInvivoRowsTest`、`CompoundListLongTableTest`、`AttachmentDownloadTest` |

---

## Part 6 — 测试用例

### `BuildVitroRowsTest`（3 个测试）
- 浓度从高到低排序
- 只取 replicate='Mean' 的行
- 跳过 is_control=True 的行

### `BuildInvivoRowsTest`（4 个测试）
- time_unit='day' 时只展示 0 和 7 的倍数
- time_unit='week' 时展示全部
- CV 计算正确（SD/|Mean| × 100）
- mean=0 时 CV 显示 None

### `CompoundListLongTableTest`（5 个测试）
- GET 200，需要登录
- q 参数过滤化合物 ID
- tag=in_vitro 只返回体外实验数据
- 多批次时最新批次标记为默认展开
- 分页正确（第 2 页返回第 21 个化合物）

### `AttachmentDownloadTest`（2 个测试）
- 有效 pk → 返回文件
- 无效 pk → 404
