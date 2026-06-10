# Sub-project D: 化合物详情页 设计文档

## 概述

为 `/compounds/<compound_id>/` 实现完整的只读详情页，展示化合物的链序列、体外剂量-响应数据（mRNA% + KD% 双曲线）和体内时间-响应数据（表格 + 折线图）。

---

## 需求摘要

- **只读**，所有登录用户均可查看，无权限分级
- 体外：按批次展开/折叠，每批次展示 mRNA_remaining 和 knockdown_pct 两张剂量-响应曲线
- 体内：多批次汇总表 + 多批次对比折线图
- 图表可由用户手动切换显示/隐藏（Toggle 按钮）
- 图表使用已有 Flot 库渲染，X 轴带坐标标签

---

## 数据模型关系

```
Compound
  ├── Strand (SS / AS)  — modify_seq
  └── Experiment (exp_type: in_vitro / in_vivo, batch_label)
        ├── ExperimentSummary (OneToOne) — ic50_nm, max_kd_pct
        └── DataPoint — x_value, x_type, replicate, readout_type, value
```

---

## 视图层

### `compound_detail(request, compound_id)`

**文件**：`app01/views.py`（修改已有 stub）

```python
@login_required
def compound_detail(request, compound_id):
    compound = get_object_or_404(Compound, compound_id=compound_id)
    strands = compound.strands.all()
    vitro = (compound.experiments
             .filter(exp_type='in_vitro')
             .prefetch_related('datapoints', 'summary')
             .order_by('batch_label'))
    vivo = (compound.experiments
            .filter(exp_type='in_vivo')
            .prefetch_related('datapoints')
            .order_by('batch_label'))
    invivo_batches = build_invivo_summary(vivo).get(compound_id, [])
    return render(request, 'compound_detail.html', {
        'compound': compound,
        'strands': strands,
        'vitro_batches': vitro,
        'invivo_batches': invivo_batches,
    })
```

- URL 已存在：`path('compounds/<str:compound_id>/', views.compound_detail, name='compound_detail')`
- `build_invivo_summary` 复用 Sub-project C 的现有函数

---

## 模板层

### `templates/compound_detail.html`

继承 `base.html`，结构如下：

```
{% block content %}
  [① 头部信息条]          — compound_id, project, target, 返回链接
  [② 链序列卡片]          — SS / AS modify_seq，monospace 展示
  [③ 体外实验区]
    {% for batch in vitro_batches %}
      [批次手风琴]         — 标题行：batch_label, IC50, MaxKD
        [图表开关按钮]     — 蓝色 Toggle，"隐藏图表" / "显示图表"
        [mRNA% 图容器]     — id="chart-mrna-{{ batch.id }}"，高度 220px
        [KD% 图容器]       — id="chart-kd-{{ batch.id }}"，高度 220px
        [json_script 数据] — id="data-{{ batch.id }}"
    {% endfor %}
  [④ 体内实验区]
    [汇总表]               — 行=批次（batch_label），列=day（动态，从数据中取）
    [图表开关按钮]         — 琥珀色 Toggle，"隐藏折线图" / "显示折线图"
    [折线图容器]           — id="chart-invivo"，高度 200px
    [json_script 数据]     — id="data-invivo"
{% endblock %}
```

**边界情况**：
- 无体外数据 → 显示占位文字"暂无体外实验数据"
- 无体内数据 → 整个体内区域不渲染
- 无 `ExperimentSummary`（ic50_nm 为空）→ 不画 IC50 参考线，仅显示散点

---

## 图表渲染（Flot）

### 体外：剂量-响应曲线

每个批次展开时懒加载（避免隐藏 div 导致尺寸计算错误）。

**mRNA 残余 % 图**：
- X 轴：`x_value`（浓度，nM），对数刻度（`xaxis: { mode: "log", tickDecimals: 0 }`）
- Y 轴：0–100，线性，标签"mRNA %"
- 数据系列：优先取 `replicate='Mean'` 的数据点连实线；若无 Mean，则分别取 A、B 两条虚线（`dashes: { show: true }`）
- IC50 参考线：若 `ic50_nm` 存在，画水平虚线（y=50）+ 垂直虚线（x=ic50_nm）

**Knockdown % 图**：
- 同上，Y 轴标签"KD %"
- 无 IC50 参考线

### 体内：时间-响应折线图

- X 轴：`x_value`（day），线性，刻度取实际 day 值
- Y 轴：0–100，线性，标签"KD %"
- 每个批次一条线，用 Flot 默认颜色循环区分
- 数据来源：`invivo_batches`（视图中 `build_invivo_summary(vivo).get(compound_id, [])` 的结果）

### 数据内联方式

```html
{{ batch_data|json_script:"data-<batch_id>" }}
```

JS 通过 `JSON.parse(document.getElementById('data-<id>').textContent)` 读取。

---

## 交互行为

### 批次手风琴

- 默认：第一个批次展开，其余折叠
- 点击标题行展开/折叠，展开时若图表未初始化则调用 `$.plot()` 初始化

### 图表 Toggle

- 体外：每个批次独立开关，控制该批次的两张图同时显示/隐藏
- 体内：整体开关，控制折线图显示/隐藏
- 按钮样式：开启时蓝色/琥珀色胶囊，关闭时灰色

---

## 测试

新增测试（`app01/tests.py`）：

| 测试类 | 测试用例 |
|--------|---------|
| `CompoundDetailViewTest` | 未登录跳转 login |
| | 不存在 compound_id 返回 404 |
| | 正常返回 200，context 含 compound/strands/vitro_batches/invivo_batches |
| | 无体外数据时 vitro_batches 为空 queryset |
| | 无体内数据时 invivo_batches 为空列表 |

---

## 文件清单

| 操作 | 文件 |
|------|------|
| 修改 | `app01/views.py`（compound_detail stub → 完整实现） |
| 修改 | `templates/compound_detail.html`（stub → 完整模板） |
| 修改 | `app01/tests.py`（新增 CompoundDetailViewTest） |
| 无需改动 | `bprdb/urls.py`（路由已存在） |
| 无需改动 | `templates/base.html`（侧边栏已存在） |
