# BPRdb 子项目 C — 化合物列表页设计

**日期：** 2026-06-09
**范围：** 化合物列表浏览、排名、过滤、体外体内转换数据对比
**前置上下文：** 基于子项目 A（数据模型）和子项目 B（上传管道）已完成

---

## 一、用户目标

1. **按 IC50 排名浏览**化合物，快速定位效果最优的候选分子
2. **查看体外体内转换效果**：对有体内数据的化合物，展开查看各批次各时间点 KD%，与体外 IC50 对比
3. **快速过滤**：按 Project、Target、IC50 范围、是否有体内数据缩小范围
4. **进入详情**：点击化合物 ID 跳转子项目 D 详情页

---

## 二、URL 设计

| 方法 | URL | 视图函数 | 说明 |
|------|-----|----------|------|
| GET | `/compounds/` | `compound_list` | 化合物列表，支持过滤 + 分页 |
| GET | `/compounds/<compound_id>/` | `compound_detail` | 化合物详情（子项目 D stub） |

---

## 三、视图设计

### `compound_list(request)` — `app01/views.py`

**GET 参数：**

| 参数 | 说明 | 示例 |
|------|------|------|
| `project` | Project 前缀过滤（icontains） | `3M03` |
| `target` | Target 过滤（icontains） | `FN` |
| `ic50_max` | IC50 ≤ N nM | `10` |
| `has_invivo` | `1` = 仅显示有体内实验的化合物 | `1` |
| `sort` | `ic50`（默认）或 `maxkd` 或 `compound_id` | `ic50` |
| `page` | 页码，默认 1 | `2` |

**查询逻辑：**

```python
from django.db.models import Min, Max, Count, Q, FloatField
from django.db.models.functions import Coalesce

qs = Compound.objects.annotate(
    best_ic50=Min('experiments__summary__ic50_nm'),
    best_maxkd=Max('experiments__summary__max_kd_pct'),
    invivo_count=Count(
        'experiments',
        filter=Q(experiments__exp_type='in_vivo'),
        distinct=True
    ),
    peak_invivo_kd=Max(
        'experiments__datapoints__value',
        filter=Q(
            experiments__exp_type='in_vivo',
            experiments__datapoints__readout_type='knockdown_pct',
            experiments__datapoints__replicate='Mean',
        )
    ),
)
```

**过滤：**
```python
if project:
    qs = qs.filter(project__icontains=project)
if target:
    qs = qs.filter(target__icontains=target)
if ic50_max:
    qs = qs.filter(best_ic50__lte=float(ic50_max))
if has_invivo == '1':
    qs = qs.filter(invivo_count__gt=0)
```

**排序：**
```python
sort_map = {
    'ic50': 'best_ic50',       # NULL 排到末尾
    'maxkd': '-best_maxkd',
    'compound_id': 'compound_id',
}
qs = qs.order_by(
    Coalesce('best_ic50', 9999) if sort == 'ic50' else sort_map.get(sort, 'best_ic50')
)
```

**体内展开数据（服务端预渲染）：**

每页 50 条，只为当前页化合物查体内数据：
```python
page_compound_ids = [c.compound_id for c in page_obj]
invivo_experiments = (
    Experiment.objects
    .filter(compound_id__in=page_compound_ids, exp_type='in_vivo')
    .prefetch_related('datapoints')
    .order_by('compound_id', 'batch_label')
)
# 组装 dict: compound_id → [{batch_label, timepoints: [{day, kd_pct}]}]
invivo_data = build_invivo_summary(invivo_experiments)
```

`build_invivo_summary` 为纯函数，提取 `replicate='Mean'` 的时间点数据；若无 Mean，取 A/B 均值。

**分页：** `Paginator(qs, 50)`

**Context：**
```python
{
    'page_obj': page_obj,
    'invivo_data': invivo_data,     # dict: compound_id → batch list
    'filter_params': {...},          # 用于表单回填和分页链接
    'total_count': qs.count(),
    'sort': sort,
}
```

### `compound_detail(request, compound_id)` — stub

```python
@login_required
def compound_detail(request, compound_id):
    compound = get_object_or_404(Compound, pk=compound_id)
    return render(request, 'compound_detail.html', {'compound': compound})
```

子项目 D 实现完整详情页，本子项目只创建 stub。

---

## 四、模板设计

### `templates/compound_list.html`

继承 `base.html`，结构：

```
topbar:
  标题"化合物列表" + 总数 badge
  [无搜索框，过滤在表格上方]

content:
  过滤条（紧贴表格顶部）
    Project 输入 | Target 输入 | IC50 ≤ 输入 | 有体内数据 toggle | 排序 select | [过滤] [清除]
  
  表格
    列：# | 化合物 ID | Project | Target | 体外 IC50 (nM) | MaxKD% | 体内实验 | 体内 Peak KD% | ▼
    行：每个化合物一行
    展开行（隐藏，JS 切换 display）：
      体内批次卡片（batch_label + D7/D14/D21 KD%）
  
  分页条（左：计数，中：页码，右：每页50）
```

**行展开逻辑（纯 JS，无 AJAX）：**

```html
<!-- 主行 -->
<tr class="compound-row" data-id="{{ c.compound_id }}"
    onclick="toggleInvivo(event, '{{ c.compound_id }}')">
  ...
  <td><a href="{% url 'compound_detail' c.compound_id %}"
         onclick="event.stopPropagation()">{{ c.compound_id }}</a></td>
  ...
  <td class="expand-arrow {% if not invivo_data[c.compound_id] %}no-invivo{% endif %}">▼</td>
</tr>

<!-- 展开行（默认隐藏） -->
{% if invivo_data[c.compound_id] %}
<tr class="invivo-row" id="invivo-{{ c.compound_id }}" style="display:none;">
  <td></td>
  <td colspan="8">
    {% for batch in invivo_data[c.compound_id] %}
    <div class="invivo-batch-card">
      <div class="batch-label">批次：{{ batch.batch_label }}</div>
      {% for tp in batch.timepoints %}
        D{{ tp.day }}：<b>{{ tp.kd_pct|floatformat:1 }}%</b>
      {% endfor %}
    </div>
    {% endfor %}
  </td>
</tr>
{% endif %}
```

```javascript
function toggleInvivo(event, compoundId) {
    const row = document.getElementById('invivo-' + compoundId);
    if (!row) return;
    row.style.display = row.style.display === 'none' ? 'table-row' : 'none';
    // toggle ▼/▲ on arrow cell
}
```

### `templates/compound_detail.html`

仅作 stub，显示化合物 ID + "详情功能即将上线"。

---

## 五、辅助函数

### `build_invivo_summary(experiments)` — `app01/views.py`

```python
def build_invivo_summary(experiments):
    """
    返回 dict: compound_id → list of {
        'batch_label': str,
        'timepoints': [{'day': float, 'kd_pct': float}]  # sorted by day
    }
    """
    result = defaultdict(list)
    for exp in experiments:
        dps = {
            dp.x_value: dp.value
            for dp in exp.datapoints.all()
            if dp.replicate == 'Mean' and dp.readout_type == 'knockdown_pct'
        }
        if not dps:
            # fallback: average A and B replicates
            ab = defaultdict(list)
            for dp in exp.datapoints.all():
                if dp.replicate in ('A', 'B') and dp.readout_type == 'knockdown_pct':
                    ab[dp.x_value].append(dp.value)
            dps = {day: sum(vals)/len(vals) for day, vals in ab.items()}
        timepoints = [{'day': day, 'kd_pct': round(kd, 1)}
                      for day, kd in sorted(dps.items())]
        if timepoints:
            result[exp.compound_id].append({
                'batch_label': exp.batch_label,
                'timepoints': timepoints,
            })
    return dict(result)
```

---

## 六、URL 路由

`bprdb/urls.py` 新增：

```python
path('compounds/', views.compound_list, name='compound_list'),
path('compounds/<str:compound_id>/', views.compound_detail, name='compound_detail'),
```

---

## 七、侧边栏

`templates/base.html` 在"数据录入"节之后添加：

```html
<div class="ds-nav-divider"></div>
<div class="ds-nav-section">化合物数据</div>
<a href="{% url 'compound_list' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'compound_list' or request.resolver_match.url_name == 'compound_detail' %}active{% endif %}">
  <i class="bi bi-table ds-nav-icon"></i> 化合物列表
</a>
```

---

## 八、测试设计

### `CompoundListViewTest`（追加到 `app01/tests.py`）

| 测试 | 验证内容 |
|------|----------|
| `test_list_returns_200` | 登录后访问 `/compounds/` 返回 200 |
| `test_list_requires_login` | 未登录跳转登录页 |
| `test_filter_by_project` | `?project=3M03` 只返回该 Project 的化合物 |
| `test_filter_by_ic50_max` | `?ic50_max=5` 只返回 IC50 ≤ 5 的行 |
| `test_filter_has_invivo` | `?has_invivo=1` 只返回有体内实验的化合物 |
| `test_sort_by_ic50` | 默认排序：IC50 最小的排第一 |
| `test_invivo_data_in_context` | 有体内数据的化合物在 invivo_data 中有对应条目 |
| `test_pagination` | 51 条数据时第 1 页显示 50 条，第 2 页显示 1 条 |

### `BuildInvivoSummaryTest`

| 测试 | 验证内容 |
|------|----------|
| `test_mean_replicate_used` | 有 Mean 时使用 Mean 值 |
| `test_ab_fallback` | 无 Mean 时取 A/B 均值 |
| `test_sorted_by_day` | timepoints 按 day 升序排列 |
| `test_no_knockdown_datapoints` | 无 knockdown_pct 数据时返回空 |

---

## 九、文件变更清单

| 文件 | 操作 |
|------|------|
| `app01/views.py` | 追加 `build_invivo_summary`、`compound_list`、`compound_detail` |
| `bprdb/urls.py` | 追加 `/compounds/` 和 `/compounds/<id>/` 路由 |
| `templates/compound_list.html` | 新建完整模板 |
| `templates/compound_detail.html` | 新建 stub 模板 |
| `templates/base.html` | 追加"化合物数据"侧边栏节 |
| `app01/tests.py` | 追加 `CompoundListViewTest`（8 个）+ `BuildInvivoSummaryTest`（4 个） |

---

## 十、范围边界

- 本子项目只实现**化合物列表**，`compound_detail` 为 stub
- 体内展开数据为**服务端预渲染**（per-page），无 AJAX endpoint
- `knockdown_pct` 为体内数据的唯一 readout_type；`mRNA_remaining` 不在体内展开中显示
- IC50 排序时，无 IC50 的化合物排到最后（Coalesce 9999）
- 化合物编辑/删除不在本子项目范围内
