# Sub-project D: 化合物详情页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `/compounds/<compound_id>/` 详情页，展示链序列、体外剂量-响应曲线（mRNA% + KD%）和体内时间-响应表格+折线图。

**Architecture:** 视图层新增 `_build_vitro_chart_data` 辅助函数（逐批次整理图表数据），`compound_detail` 视图将数据以 `json_script` 方式内联到模板，前端用 Flot 懒加载渲染图表，X 轴取 log10 变换后的值配合自定义 ticks 实现对数刻度。

**Tech Stack:** Django 5.1, Python 3.10, jQuery + Flot (`/static/vendors/flot/jquery.flot.js`), Bootstrap 5

---

## 文件清单

| 操作 | 文件 |
|------|------|
| 修改 | `app01/views.py`（`_build_vitro_chart_data` + `compound_detail`） |
| 修改 | `app01/tests.py`（新增 `CompoundDetailViewTest`） |
| 修改 | `templates/compound_detail.html`（stub → 完整实现） |

---

## Task 1: 视图 + helper + 测试（TDD）

**Files:**
- Modify: `app01/views.py` — 在 `build_invivo_summary` 下方添加 `_build_vitro_chart_data`；将 `compound_detail` stub 替换为完整实现
- Modify: `app01/tests.py` — 在文件末尾追加 `CompoundDetailViewTest`

### 环境确认

- [ ] **Step 1: 激活虚拟环境并确认测试可运行**

```bash
source /Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/activate
cd /Users/gutou/Projects/seq_web/seq_database_bprdb
python manage.py test app01.tests.CompoundListViewTest --verbosity=0
```

期望：`OK`（8 tests）

### 写测试

- [ ] **Step 2: 在 `app01/tests.py` 末尾追加 `CompoundDetailViewTest`**

在文件最后添加：

```python
# ---- CompoundDetailViewTest ----
class CompoundDetailViewTest(TestCase):
    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='tester2', password='pass', user_type='admin'
        )
        self.client.login(username='tester2', password='pass')

        self.cmp = Compound.objects.create(
            compound_id='BPR_TEST01', project='TEST', target='FN'
        )
        Strand.objects.create(
            compound=self.cmp, strand_type='SS', modify_seq='mA·fU·mC'
        )
        Strand.objects.create(
            compound=self.cmp, strand_type='AS', modify_seq='fG·mA·fU'
        )
        # 体外实验 + summary + datapoints
        self.vitro_exp = Experiment.objects.create(
            compound=self.cmp, exp_type='in_vitro',
            assay_name='HeLa', batch_label='2026-03'
        )
        ExperimentSummary.objects.create(
            experiment=self.vitro_exp, ic50_nm=1.26, max_kd_pct=82.0
        )
        for x, rep, rtype, val in [
            (0.01, 'Mean', 'mRNA_remaining', 95.0),
            (0.1,  'Mean', 'mRNA_remaining', 70.0),
            (1.0,  'Mean', 'mRNA_remaining', 30.0),
            (10.0, 'Mean', 'mRNA_remaining', 8.0),
            (0.01, 'Mean', 'knockdown_pct',   5.0),
            (0.1,  'Mean', 'knockdown_pct',  30.0),
            (1.0,  'Mean', 'knockdown_pct',  70.0),
            (10.0, 'Mean', 'knockdown_pct',  92.0),
        ]:
            DataPoint.objects.create(
                experiment=self.vitro_exp,
                x_value=x, x_type='concentration',
                replicate=rep, readout_type=rtype, value=val
            )
        # 体内实验 + datapoints
        self.vivo_exp = Experiment.objects.create(
            compound=self.cmp, exp_type='in_vivo',
            assay_name='mouse', batch_label='2026-05'
        )
        for day, val in [(7.0, 76.0), (14.0, 68.0), (21.0, 52.0)]:
            DataPoint.objects.create(
                experiment=self.vivo_exp,
                x_value=day, x_type='timepoint',
                replicate='Mean', readout_type='knockdown_pct', value=val
            )

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get('/compounds/BPR_TEST01/')
        self.assertRedirects(resp, '/login/?next=/compounds/BPR_TEST01/',
                             fetch_redirect_response=False)

    def test_404_for_unknown_compound(self):
        resp = self.client.get('/compounds/NOTEXIST/')
        self.assertEqual(resp.status_code, 404)

    def test_returns_200_with_context(self):
        resp = self.client.get('/compounds/BPR_TEST01/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['compound'].compound_id, 'BPR_TEST01')
        self.assertEqual(len(resp.context['strands']), 2)
        self.assertEqual(len(resp.context['vitro_batches']), 1)
        self.assertEqual(len(resp.context['vitro_chart_data']), 1)
        self.assertEqual(len(resp.context['invivo_batches']), 1)

    def test_vitro_chart_data_structure(self):
        resp = self.client.get('/compounds/BPR_TEST01/')
        chart = resp.context['vitro_chart_data'][0]
        self.assertEqual(chart['batch_label'], '2026-03')
        self.assertAlmostEqual(chart['ic50_nm'], 1.26)
        self.assertEqual(len(chart['mrna_mean']), 4)
        self.assertEqual(len(chart['kd_mean']), 4)
        self.assertEqual(chart['mrna_a'], [])

    def test_no_vitro_data(self):
        cmp2 = Compound.objects.create(compound_id='BPR_EMPTY01')
        resp = self.client.get('/compounds/BPR_EMPTY01/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(list(resp.context['vitro_batches']), [])
        self.assertEqual(resp.context['invivo_batches'], [])
```

- [ ] **Step 3: 运行测试，确认失败**

```bash
python manage.py test app01.tests.CompoundDetailViewTest --verbosity=1
```

期望：`ERRORS` 或 `FAIL`（视图还是 stub，context keys 不存在）

### 实现视图

- [ ] **Step 4: 在 `app01/views.py` 的 `build_invivo_summary` 函数之后，`compound_detail` 之前，插入 `_build_vitro_chart_data`**

在 `app01/views.py` 中找到 `def compound_detail` 前插入：

```python
def _build_vitro_chart_data(exp):
    """整理单个体外 Experiment 的图表数据，供前端 Flot 使用。"""
    all_dps = list(exp.datapoints.all())
    conc_dps = [dp for dp in all_dps if dp.x_type == 'concentration']

    def series(readout, rep):
        return sorted(
            [(dp.x_value, dp.value)
             for dp in conc_dps
             if dp.readout_type == readout and dp.replicate == rep],
            key=lambda p: p[0]
        )

    try:
        ic50 = exp.summary.ic50_nm
        max_kd = exp.summary.max_kd_pct
    except Exception:
        ic50 = None
        max_kd = None

    mrna_mean = series('mRNA_remaining', 'Mean')
    kd_mean   = series('knockdown_pct',  'Mean')
    return {
        'exp_id':     exp.id,
        'batch_label': exp.batch_label,
        'ic50_nm':    ic50,
        'max_kd_pct': max_kd,
        'mrna_mean':  mrna_mean,
        'mrna_a':     series('mRNA_remaining', 'A') if not mrna_mean else [],
        'mrna_b':     series('mRNA_remaining', 'B') if not mrna_mean else [],
        'kd_mean':    kd_mean,
        'kd_a':       series('knockdown_pct', 'A') if not kd_mean else [],
        'kd_b':       series('knockdown_pct', 'B') if not kd_mean else [],
    }
```

- [ ] **Step 5: 将 `compound_detail` stub 替换为完整实现**

把现有的 stub：

```python
@login_required
def compound_detail(request, compound_id):
    compound = get_object_or_404(Compound, pk=compound_id)
    return render(request, 'compound_detail.html', {'compound': compound})
```

替换为：

```python
@login_required
def compound_detail(request, compound_id):
    compound = get_object_or_404(Compound, pk=compound_id)
    strands = compound.strands.all()
    vitro = list(
        compound.experiments
        .filter(exp_type='in_vitro')
        .select_related('summary')
        .prefetch_related('datapoints')
        .order_by('batch_label')
    )
    vivo = (
        compound.experiments
        .filter(exp_type='in_vivo')
        .prefetch_related('datapoints')
        .order_by('batch_label')
    )
    vitro_chart_data = [_build_vitro_chart_data(exp) for exp in vitro]
    invivo_batches = build_invivo_summary(vivo).get(compound_id, [])
    return render(request, 'compound_detail.html', {
        'compound':         compound,
        'strands':          strands,
        'vitro_batches':    vitro,
        'vitro_chart_data': vitro_chart_data,
        'invivo_batches':   invivo_batches,
    })
```

- [ ] **Step 6: 运行测试，确认全部通过**

```bash
python manage.py test app01.tests.CompoundDetailViewTest --verbosity=1
```

期望：`OK (5 tests)`

- [ ] **Step 7: 运行完整测试套件，确认无回归**

```bash
python manage.py test app01 --verbosity=0
```

期望：`OK`（之前 74 tests + 5 = 79 tests）

- [ ] **Step 8: 提交**

```bash
git add app01/views.py app01/tests.py
git commit -m "feat: compound_detail view with vitro chart data + 5 tests"
```

---

## Task 2: compound_detail.html — HTML 骨架 + JSON 数据内联

**Files:**
- Modify: `templates/compound_detail.html`（替换 stub，先不含 JS）

### 实现模板 HTML 骨架

- [ ] **Step 1: 将 `templates/compound_detail.html` 替换为完整 HTML（暂无图表 JS）**

完整内容如下（`{% block extra_scripts %}` 暂时为空，Task 3 填入）：

```html
{% extends "base.html" %}
{% load compound_filters %}
{% block page_title %} — {{ compound.compound_id }}{% endblock %}

{% block content %}

{# ① 头部信息条 #}
<div style="background:#1e40af;color:white;border-radius:8px;padding:12px 18px;
            margin-bottom:14px;display:flex;justify-content:space-between;align-items:center;">
  <div>
    <span style="font-size:17px;font-weight:700;">{{ compound.compound_id }}</span>
    {% if compound.project %}
    <span style="margin-left:14px;font-size:12px;opacity:.75;">
      Project: {{ compound.project }}
      {% if compound.target %}&nbsp;·&nbsp; Target: {{ compound.target }}{% endif %}
    </span>
    {% endif %}
  </div>
  <a href="{% url 'compound_list' %}"
     style="color:rgba(255,255,255,.65);font-size:12px;text-decoration:none;">← 返回化合物列表</a>
</div>

{# ② 链序列卡片 #}
{% if strands %}
<div style="background:white;border:1px solid #e2e8f0;border-radius:8px;
            padding:12px 16px;margin-bottom:12px;">
  <div style="font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;
              letter-spacing:.04em;margin-bottom:8px;">链序列</div>
  {% for strand in strands %}
  <div style="display:flex;align-items:baseline;gap:8px;margin-bottom:4px;">
    <span style="width:22px;font-size:11px;font-weight:700;color:#94a3b8;flex-shrink:0;">
      {{ strand.strand_type }}
    </span>
    <code style="font-size:11px;
      {% if strand.strand_type == 'SS' %}background:#f0fdf4;color:#166534;
      {% else %}background:#fef9c3;color:#78350f;{% endif %}
      border-radius:4px;padding:3px 8px;word-break:break-all;line-height:1.6;">
      {{ strand.modify_seq }}
    </code>
  </div>
  {% endfor %}
</div>
{% endif %}

{# ③ 体外实验 #}
<div style="font-size:13px;font-weight:700;color:#1e40af;
            border-bottom:2px solid #bfdbfe;padding-bottom:5px;margin-bottom:10px;">
  ■ 体外实验
</div>

{% if vitro_batches %}
{% for batch in vitro_batches %}
{% with chart=vitro_chart_data|index:forloop.counter0 %}
<div class="detail-batch-card"
     style="border:1px solid #e2e8f0;border-radius:8px;margin-bottom:8px;overflow:hidden;">

  {# 批次标题行 #}
  <div class="detail-batch-hdr"
       data-batch-id="{{ batch.id }}"
       style="padding:8px 14px;display:flex;justify-content:space-between;align-items:center;
              cursor:pointer;user-select:none;
              {% if forloop.first %}background:#eff6ff;{% else %}background:#f8fafc;{% endif %}">
    <div style="font-size:12px;display:flex;align-items:center;gap:10px;">
      <span style="font-weight:700;">{{ batch.batch_label }}</span>
      <span style="color:#475569;">
        {{ batch.assay_name }}
        {% if chart.ic50_nm %}&nbsp;·&nbsp; IC50 <b style="color:#15803d;">{{ chart.ic50_nm|floatformat:2 }} nM</b>{% endif %}
        {% if chart.max_kd_pct %}&nbsp;·&nbsp; MaxKD <b style="color:#15803d;">{{ chart.max_kd_pct|floatformat:0 }}%</b>{% endif %}
      </span>
    </div>
    <div style="display:flex;align-items:center;gap:8px;">
      <button class="detail-chart-tgl detail-chart-tgl-on"
              data-batch-id="{{ batch.id }}"
              style="display:inline-flex;align-items:center;gap:5px;
                     border-radius:14px;padding:3px 10px;font-size:11px;font-weight:600;
                     cursor:pointer;border:1.5px solid #3b82f6;color:#1d4ed8;background:white;">
        <span class="tgl-track"
              style="width:24px;height:13px;background:#3b82f6;border-radius:7px;
                     display:inline-flex;align-items:center;padding:1px 2px;flex-shrink:0;">
          <span class="tgl-knob"
                style="width:9px;height:9px;background:white;border-radius:50%;margin-left:auto;"></span>
        </span>
        <span class="tgl-label">隐藏图表</span>
      </button>
      <span class="detail-batch-arr"
            style="font-size:11px;{% if forloop.first %}color:#3b82f6;{% else %}color:#94a3b8;{% endif %}">
        {% if forloop.first %}▼{% else %}▶{% endif %}
      </span>
    </div>
  </div>

  {# 批次展开内容 #}
  <div class="detail-batch-body"
       data-batch-id="{{ batch.id }}"
       {% if not forloop.first %}style="display:none;"{% endif %}>
    <div class="detail-charts-wrap"
         data-batch-id="{{ batch.id }}"
         style="display:flex;gap:12px;padding:12px 16px 4px;">
      <div style="flex:1;min-width:0;">
        <div style="font-size:11px;font-weight:600;color:#3b82f6;text-align:center;margin-bottom:4px;">
          mRNA 残余 %
        </div>
        <div id="chart-mrna-{{ batch.id }}" style="height:220px;"></div>
      </div>
      <div style="flex:1;min-width:0;">
        <div style="font-size:11px;font-weight:600;color:#10b981;text-align:center;margin-bottom:4px;">
          Knockdown %
        </div>
        <div id="chart-kd-{{ batch.id }}" style="height:220px;"></div>
      </div>
    </div>
    <div style="font-size:10px;color:#94a3b8;text-align:center;padding:2px 16px 10px;">
      实线 = Mean replicate；若无 Mean 则分别显示 A（实线）/ B（虚线）
    </div>
  </div>

</div>
{% endwith %}
{% endfor %}
{% else %}
<p style="color:#94a3b8;font-size:13px;padding:8px 0;">暂无体外实验数据</p>
{% endif %}

{# ④ 体内实验 #}
{% if invivo_batches %}
<div style="font-size:13px;font-weight:700;color:#92400e;
            border-bottom:2px solid #fde68a;padding-bottom:5px;margin:14px 0 10px;">
  ■ 体内实验
</div>

<div style="background:white;border:1px solid #fde68a;border-radius:8px;
            padding:0;margin-bottom:0;overflow:hidden;">

  {# 汇总表 — 动态 day 列 #}
  {% with all_days=invivo_batches|all_days %}
  <div style="overflow-x:auto;padding:10px 14px 0;">
    <table style="width:100%;border-collapse:collapse;font-size:12px;">
      <thead>
        <tr style="border-bottom:1px solid #fde68a;">
          <th style="color:#92400e;font-weight:700;padding:5px 10px;text-align:left;background:#fffbeb;">批次</th>
          {% for day in all_days %}
          <th style="color:#92400e;font-weight:700;padding:5px 10px;text-align:left;background:#fffbeb;white-space:nowrap;">
            D{{ day|floatformat:0 }}
          </th>
          {% endfor %}
        </tr>
      </thead>
      <tbody>
        {% for batch in invivo_batches %}
        {% with tp_map=batch.timepoints|as_day_map %}
        <tr style="border-bottom:1px solid #fef9c3;">
          <td style="padding:5px 10px;font-weight:700;">{{ batch.batch_label }}</td>
          {% for day in all_days %}
          {% with val=tp_map|get_item:day %}
          <td style="padding:5px 10px;{% if val is not None %}color:#92400e;font-weight:600;{% else %}color:#cbd5e1;{% endif %}">
            {% if val is not None %}{{ val }}%{% else %}—{% endif %}
          </td>
          {% endwith %}
          {% endfor %}
        </tr>
        {% endwith %}
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% endwith %}

  {# 体内折线图 #}
  <div style="padding:8px 14px 14px;">
    <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:10px 14px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <span style="font-size:11px;font-weight:600;color:#92400e;">KD% 随时间变化（多批次对比）</span>
        <button id="vivo-chart-tgl"
                style="display:inline-flex;align-items:center;gap:5px;
                       border-radius:14px;padding:3px 10px;font-size:11px;font-weight:600;
                       cursor:pointer;border:1.5px solid #f59e0b;color:#92400e;background:#fffbeb;">
          <span id="vivo-tgl-track"
                style="width:24px;height:13px;background:#f59e0b;border-radius:7px;
                       display:inline-flex;align-items:center;padding:1px 2px;flex-shrink:0;">
            <span id="vivo-tgl-knob"
                  style="width:9px;height:9px;background:white;border-radius:50%;margin-left:auto;"></span>
          </span>
          <span id="vivo-tgl-label">隐藏折线图</span>
        </button>
      </div>
      <div id="chart-invivo" style="height:200px;"></div>
    </div>
  </div>

</div>
{% endif %}

{# JSON 数据内联 #}
{{ vitro_chart_data|json_script:"vitro-chart-data" }}
{{ invivo_batches|json_script:"invivo-batches-data" }}

{% endblock %}

{% block extra_scripts %}
{# Task 3 填入图表 JS #}
{% endblock %}
```

> **注意**：上面模板用了三个新模板过滤器：`index`（按下标取列表元素）、`all_days`（从 invivo_batches 提取所有 day 排序去重）、`as_day_map`（把 timepoints 转为 {day: kd_pct} 字典）。需要在 Task 2 Step 2 中添加这三个过滤器。

- [ ] **Step 2: 在 `app01/templatetags/compound_filters.py` 添加三个新过滤器**

```python
@register.filter
def index(lst, i):
    """{{ lst|index:0 }} — 按下标取列表元素"""
    try:
        return lst[i]
    except (IndexError, TypeError):
        return None


@register.filter
def all_days(invivo_batches):
    """从 invivo_batches 提取所有 day 值，排序去重。"""
    days = set()
    for batch in invivo_batches:
        for tp in batch.get('timepoints', []):
            days.add(tp['day'])
    return sorted(days)


@register.filter
def as_day_map(timepoints):
    """把 [{day, kd_pct}, ...] 转为 {day: kd_pct} 字典，供模板查表。"""
    return {tp['day']: tp['kd_pct'] for tp in timepoints}
```

- [ ] **Step 3: 启动开发服务器，在浏览器验证页面结构**

```bash
python manage.py runserver
```

打开 `http://127.0.0.1:8000/compounds/` 点击任意化合物 ID，或直接访问 `http://127.0.0.1:8000/compounds/<任意compound_id>/`

检查：
- 页面加载 200，不报 500
- 蓝色头部信息条、链序列（SS/AS）显示正常
- 体外批次手风琴标题行可见
- 体内汇总表 day 列正确（有数据时）
- 图表容器（`<div id="chart-mrna-...">` 等）存在但为空白——正常，JS 尚未加入

- [ ] **Step 4: 运行全部测试，确认无回归**

```bash
python manage.py test app01 --verbosity=0
```

期望：`OK (79 tests)`

- [ ] **Step 5: 提交**

```bash
git add templates/compound_detail.html app01/templatetags/compound_filters.py
git commit -m "feat: compound_detail HTML skeleton with JSON data inline"
```

---

## Task 3: 图表 JS（Flot 剂量-响应曲线 + 体内折线图 + 交互）

**Files:**
- Modify: `templates/compound_detail.html` — 填入 `{% block extra_scripts %}` 中的所有 JS

### 原理说明（写给实现者）

Flot 不支持对数 X 轴，需手动 log10 变换：
- 数据点：`[x, y]` → `[Math.log10(x), y]`
- IC50 参考线：`x = Math.log10(ic50_nm)`
- X 轴 ticks：用固定映射 `[[-2,'0.01'], [-1,'0.1'], [0,'1'], [1,'10'], [2,'100']]`

体外图表懒加载：只在批次展开时初始化，防止 Flot 在 `display:none` 容器中计算宽度为 0。

- [ ] **Step 1: 将 `{% block extra_scripts %}` 填入完整 JS**

用以下内容替换模板中的 `{% block extra_scripts %}...{% endblock %}`：

```html
{% block extra_scripts %}
<script src="/static/vendors/flot/jquery.flot.js"></script>
<script>
(function() {

// ── 常量 ──────────────────────────────────────────────────────────────────
const LOG_TICKS = [[-3,'0.001'],[-2,'0.01'],[-1,'0.1'],[0,'1'],[1,'10'],[2,'100'],[3,'1000']];
const VITRO_DATA  = JSON.parse(document.getElementById('vitro-chart-data').textContent);
const INVIVO_DATA = JSON.parse(document.getElementById('invivo-batches-data').textContent);
const chartInited = {};   // {expId: true} 记录已初始化的图表

// ── 工具 ──────────────────────────────────────────────────────────────────
function toLog(pairs) {
  return pairs.map(function(p) { return [Math.log10(p[0]), p[1]]; });
}

function plotOpts(ic50, axisLabel) {
  var markings = [];
  if (ic50 != null) {
    markings = [
      { yaxis: { from: 50, to: 50 }, color: '#fbbf24', lineWidth: 1 },
      { xaxis: { from: Math.log10(ic50), to: Math.log10(ic50) }, color: '#fbbf24', lineWidth: 1 }
    ];
  }
  return {
    series: { lines: { show: true }, points: { show: true, radius: 3 } },
    xaxis:  { ticks: LOG_TICKS, axisLabel: '浓度 (nM)', tickLength: 4 },
    yaxis:  { min: 0, max: 105, axisLabel: axisLabel, labelWidth: 30 },
    grid:   { hoverable: false, borderWidth: 1, borderColor: '#e2e8f0', markings: markings },
    legend: { show: false }
  };
}

// ── 体外图表初始化 ────────────────────────────────────────────────────────
function initVitroChart(expId) {
  if (chartInited[expId]) return;
  var data = null;
  for (var i = 0; i < VITRO_DATA.length; i++) {
    if (VITRO_DATA[i].exp_id === expId) { data = VITRO_DATA[i]; break; }
  }
  if (!data) return;

  // mRNA 残余 %
  var mrnaSeries = [];
  if (data.mrna_mean.length) {
    mrnaSeries.push({
      data: toLog(data.mrna_mean), color: '#3b82f6',
      lines: { show: true, lineWidth: 2 }, points: { show: true, radius: 3 }
    });
  } else {
    if (data.mrna_a.length)
      mrnaSeries.push({ label: 'A', data: toLog(data.mrna_a), color: '#3b82f6',
                         lines: { show: true, lineWidth: 1.5 }, points: { show: true, radius: 3 } });
    if (data.mrna_b.length)
      mrnaSeries.push({ label: 'B', data: toLog(data.mrna_b), color: '#93c5fd',
                         lines: { show: true, lineWidth: 1.5, dashes: [4, 3] }, points: { show: true, radius: 3 } });
  }
  if (mrnaSeries.length)
    $.plot('#chart-mrna-' + expId, mrnaSeries, plotOpts(data.ic50_nm, 'mRNA %'));

  // KD%
  var kdSeries = [];
  if (data.kd_mean.length) {
    kdSeries.push({
      data: toLog(data.kd_mean), color: '#10b981',
      lines: { show: true, lineWidth: 2 }, points: { show: true, radius: 3 }
    });
  } else {
    if (data.kd_a.length)
      kdSeries.push({ label: 'A', data: toLog(data.kd_a), color: '#10b981',
                       lines: { show: true, lineWidth: 1.5 }, points: { show: true, radius: 3 } });
    if (data.kd_b.length)
      kdSeries.push({ label: 'B', data: toLog(data.kd_b), color: '#6ee7b7',
                       lines: { show: true, lineWidth: 1.5, dashes: [4, 3] }, points: { show: true, radius: 3 } });
  }
  if (kdSeries.length) {
    var opts = plotOpts(null, 'KD %');
    $.plot('#chart-kd-' + expId, kdSeries, opts);
  }

  chartInited[expId] = true;
}

// ── 体内折线图初始化 ──────────────────────────────────────────────────────
function initInvivoChart() {
  if (!INVIVO_DATA.length) return;
  var colors = ['#f97316','#92400e','#3b82f6','#10b981','#a855f7'];
  var series = INVIVO_DATA.map(function(batch, i) {
    return {
      label: batch.batch_label,
      data:  batch.timepoints.map(function(tp) { return [tp.day, tp.kd_pct]; }),
      color: colors[i % colors.length],
      lines: { show: true, lineWidth: 2 },
      points: { show: true, radius: 4 }
    };
  });
  $.plot('#chart-invivo', series, {
    xaxis: { axisLabel: '时间点 (day)', tickLength: 4 },
    yaxis: { min: 0, max: 105, axisLabel: 'KD %', labelWidth: 30 },
    grid:  { hoverable: false, borderWidth: 1, borderColor: '#fde68a' },
    legend: { show: true, position: 'topright', backgroundOpacity: 0.7 }
  });
}

// ── 批次手风琴 ────────────────────────────────────────────────────────────
$(document).on('click', '.detail-batch-hdr', function() {
  var batchId = $(this).data('batch-id');
  var $body = $('.detail-batch-body[data-batch-id="' + batchId + '"]');
  var $arr  = $(this).find('.detail-batch-arr');
  var isOpen = $body.is(':visible');

  if (isOpen) {
    $body.hide();
    $arr.text('▶').css('color', '#94a3b8');
    $(this).css('background', '#f8fafc');
  } else {
    $body.show();
    $arr.text('▼').css('color', '#3b82f6');
    $(this).css('background', '#eff6ff');
    initVitroChart(batchId);
  }
});

// 阻止开关按钮事件冒泡到手风琴
$(document).on('click', '.detail-chart-tgl', function(e) {
  e.stopPropagation();
  var batchId = $(this).data('batch-id');
  var $wrap = $('.detail-charts-wrap[data-batch-id="' + batchId + '"]');
  var $label = $(this).find('.tgl-label');
  var $track = $(this).find('.tgl-track');
  var $knob  = $(this).find('.tgl-knob');
  var isOn = $wrap.is(':visible');

  if (isOn) {
    $wrap.hide();
    $label.text('显示图表');
    $track.css('background', '#94a3b8');
    $knob.css('margin-left', '0');
    $(this).css({'border-color':'#cbd5e1','color':'#94a3b8','background':'#f8fafc'});
  } else {
    $wrap.show();
    $label.text('隐藏图表');
    $track.css('background', '#3b82f6');
    $knob.css('margin-left', 'auto');
    $(this).css({'border-color':'#3b82f6','color':'#1d4ed8','background':'white'});
  }
});

// ── 体内折线图开关 ────────────────────────────────────────────────────────
$('#vivo-chart-tgl').on('click', function() {
  var $chart = $('#chart-invivo');
  var $label = $('#vivo-tgl-label');
  var $track = $('#vivo-tgl-track');
  var $knob  = $('#vivo-tgl-knob');
  var isOn = $chart.is(':visible');

  if (isOn) {
    $chart.hide();
    $label.text('显示折线图');
    $track.css('background', '#94a3b8');
    $knob.css('margin-left', '0');
    $(this).css({'border-color':'#cbd5e1','color':'#64748b','background':'#f8fafc'});
  } else {
    $chart.show();
    $label.text('隐藏折线图');
    $track.css('background', '#f59e0b');
    $knob.css('margin-left', 'auto');
    $(this).css({'border-color':'#f59e0b','color':'#92400e','background':'#fffbeb'});
  }
});

// ── 页面初始化 ────────────────────────────────────────────────────────────
$(function() {
  // 初始化第一个体外批次图表（默认展开）
  var $firstBody = $('.detail-batch-body').first();
  if ($firstBody.length) {
    var firstId = $firstBody.data('batch-id');
    initVitroChart(firstId);
  }
  // 初始化体内折线图
  initInvivoChart();
});

})();
</script>
{% endblock %}
```

- [ ] **Step 2: 启动开发服务器，在浏览器验证完整功能**

```bash
python manage.py runserver
```

验证清单：
1. 访问一个有体外数据的化合物详情页
2. 第一个批次展开，mRNA% 和 KD% 图表已渲染（有 S 形曲线，有坐标轴标签）
3. IC50 参考虚线可见（若该批次有 ExperimentSummary）
4. 点击折叠批次，手风琴正常展开，图表延迟初始化
5. 点击「隐藏图表」按钮，图表消失，按钮变灰；再点「显示图表」恢复
6. 体内汇总表 day 列正确；体内折线图有多条线（各批次不同颜色）
7. 「隐藏折线图」按钮正常切换
8. 检查 browser console，无 JS 错误

- [ ] **Step 3: 运行全部测试**

```bash
python manage.py test app01 --verbosity=0
```

期望：`OK (79 tests)`

- [ ] **Step 4: 提交**

```bash
git add templates/compound_detail.html
git commit -m "feat: compound_detail Flot charts, accordion, chart toggle JS"
```
