# 长表展示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `/compounds/` 化合物列表页从单行摘要改为长表格式（每浓度/时间点一行），新增附件下载接口，并在化合物详情页补充附件列表。

**Architecture:** 新增两个纯函数（`_build_vitro_rows`、`_build_invivo_rows`）和一个组合函数（`_build_batch_groups`）完成数据整理；`compound_list` 视图完全重写，改用 Prefetch 一次取所有关联数据后在 Python 层分组；模板从表格式重写为化合物卡片 + 批次折叠块结构。

**Tech Stack:** Django 5.1, Python 3.10 (`statistics` 标准库), MySQL, Bootstrap collapse (vanilla JS), 现有 `ds-*` CSS 设计系统

**设计文档：** `docs/superpowers/specs/2026-06-15-long-table-display-design.md`

**激活虚拟环境：** `source ../seq_database_v2/venv/bin/activate`

**运行测试：** `python manage.py test app01 -v 1`

---

## 文件变更一览

| 文件 | 操作 |
|------|------|
| `app01/models.py` | `Compound` 加 `target_name` 字段 |
| `app01/migrations/0025_compound_target_name.py` | 新建 migration |
| `app01/views.py` | 加 `import statistics`、`Prefetch`、`FileResponse`；新增 `_build_vitro_rows`、`_build_invivo_rows`、`_build_batch_groups`；重写 `compound_list`；新增 `attachment_download` |
| `bprdb/urls.py` | 新增 `attachment_download` 路由 |
| `templates/compound_list.html` | 完全重写为卡片 + 折叠长表 |
| `templates/compound_detail.html` | 补充附件列表区块 |
| `app01/tests.py` | 新增 `BuildVitroRowsTest`（3个）、`BuildInvivoRowsTest`（4个）、`AttachmentDownloadTest`（3个）；更新 `CompoundListViewTest`（改为验证新 context 结构）|

---

## Task 1: Compound.target_name 字段 + Migration

**Files:**
- Modify: `app01/models.py` (Compound 类，约第 70–91 行)
- Create: `app01/migrations/0025_compound_target_name.py`

- [ ] **Step 1: 在 Compound 模型里加字段**

在 `app01/models.py` 的 `Compound` 类里，`target` 字段后面加一行：

```python
# 已有：
target = models.CharField(max_length=32, blank=True, db_index=True)
# 新增（加在 target 行下方）：
target_name = models.CharField(max_length=128, blank=True)
```

- [ ] **Step 2: 生成并应用 migration**

```bash
source ../seq_database_v2/venv/bin/activate
python manage.py makemigrations app01 --name add_compound_target_name
python manage.py migrate
```

Expected: `Applying app01.0025_add_compound_target_name... OK`

- [ ] **Step 3: 验证字段存在**

```bash
python manage.py shell -c "from app01.models import Compound; c = Compound(compound_id='TEST', target_name='FASN'); print(c.target_name)"
```

Expected: `FASN`

- [ ] **Step 4: 运行全量测试确认无破坏**

```bash
python manage.py test app01 -v 1
```

Expected: All existing tests pass (数量与之前相同，无新失败)

- [ ] **Step 5: Commit**

```bash
git add app01/models.py app01/migrations/
git commit -m "feat: add Compound.target_name field for full gene name (long-table Task 1)"
```

---

## Task 2: `_build_vitro_rows` 辅助函数 + 测试

**Files:**
- Modify: `app01/views.py` (在 `build_invivo_summary` 函数之前，约第 790 行前插入)
- Modify: `app01/tests.py` (在 `BuildInvivoSummaryTest` 类之前插入新测试类)

- [ ] **Step 1: 写失败测试**

在 `app01/tests.py` 文件末尾（最后一个 `class` 之前找合适位置，或直接加在文件末尾），加入：

```python
# ---- BuildVitroRowsTest ----
class BuildVitroRowsTest(TestCase):
    def _make_exp(self):
        from app01.models import Compound, Experiment
        c = Compound.objects.create(compound_id='BPR_VTTEST01')
        return Experiment.objects.create(
            compound=c, exp_type='in_vitro', assay_name='test', batch_label='BV1'
        )

    def test_sorted_high_to_low(self):
        from app01.views import _build_vitro_rows
        exp = self._make_exp()
        DataPoint.objects.create(experiment=exp, x_value=1.0, x_type='concentration', replicate='Mean', value=0.87, readout_type='mRNA_remaining')
        DataPoint.objects.create(experiment=exp, x_value=100.0, x_type='concentration', replicate='Mean', value=0.25, readout_type='mRNA_remaining')
        DataPoint.objects.create(experiment=exp, x_value=10.0, x_type='concentration', replicate='Mean', value=0.50, readout_type='mRNA_remaining')
        rows = _build_vitro_rows(list(exp.datapoints.all()))
        self.assertEqual([r['dose'] for r in rows], [100.0, 10.0, 1.0])

    def test_only_mean_replicate(self):
        from app01.views import _build_vitro_rows
        exp = self._make_exp()
        DataPoint.objects.create(experiment=exp, x_value=100.0, x_type='concentration', replicate='Mean', value=0.25, readout_type='mRNA_remaining')
        DataPoint.objects.create(experiment=exp, x_value=100.0, x_type='concentration', replicate='A', value=0.20, readout_type='mRNA_remaining')
        DataPoint.objects.create(experiment=exp, x_value=100.0, x_type='concentration', replicate='B', value=0.30, readout_type='mRNA_remaining')
        rows = _build_vitro_rows(list(exp.datapoints.all()))
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]['mean'], 0.25)

    def test_skip_control(self):
        from app01.views import _build_vitro_rows
        exp = self._make_exp()
        DataPoint.objects.create(experiment=exp, x_value=0.0, x_type='concentration', replicate='Mean', value=1.01, readout_type='mRNA_remaining', is_control=True)
        DataPoint.objects.create(experiment=exp, x_value=100.0, x_type='concentration', replicate='Mean', value=0.25, readout_type='mRNA_remaining', is_control=False)
        rows = _build_vitro_rows(list(exp.datapoints.all()))
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]['dose'], 100.0)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python manage.py test app01.tests.BuildVitroRowsTest -v 1
```

Expected: `AttributeError: module 'app01.views' has no attribute '_build_vitro_rows'`

- [ ] **Step 3: 实现函数**

在 `app01/views.py` 里，找到 `def build_invivo_summary` 函数（约第 792 行）之前，插入：

```python
def _build_vitro_rows(datapoints):
    """One row per concentration, only Mean replicate, sorted high to low."""
    mean_points = [
        dp for dp in datapoints
        if dp.replicate == 'Mean' and not dp.is_control
    ]
    mean_points.sort(key=lambda dp: -dp.x_value)
    return [{'dose': dp.x_value, 'mean': dp.value} for dp in mean_points]
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python manage.py test app01.tests.BuildVitroRowsTest -v 1
```

Expected: `OK` (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "feat: add _build_vitro_rows helper + tests (long-table Task 2)"
```

---

## Task 3: `_build_invivo_rows` 辅助函数 + 测试

**Files:**
- Modify: `app01/views.py` (在 `_build_vitro_rows` 函数之后插入)
- Modify: `app01/tests.py` (在 `BuildVitroRowsTest` 之后插入)

- [ ] **Step 1: 在 views.py 顶部加 import**

在 `app01/views.py` 第 1 行附近，找到 `from collections import defaultdict` 这行，在它下方加：

```python
import statistics as _statistics
```

- [ ] **Step 2: 写失败测试**

在 `app01/tests.py` 里，`BuildVitroRowsTest` 类之后加入：

```python
# ---- BuildInvivoRowsTest ----
class BuildInvivoRowsTest(TestCase):
    def _make_exp(self, time_unit='day'):
        from app01.models import Compound, Experiment
        c = Compound.objects.create(compound_id='BPR_IVTEST01')
        return Experiment.objects.create(
            compound=c, exp_type='in_vivo', assay_name='test',
            batch_label='BI1', time_unit=time_unit
        )

    def test_day_unit_filters_multiples_of_7(self):
        from app01.views import _build_invivo_rows
        exp = self._make_exp('day')
        for day, val in [(0.0, 0.0), (3.0, -10.0), (7.0, -30.0), (14.0, -95.0), (10.0, -50.0)]:
            DataPoint.objects.create(experiment=exp, x_value=day, x_type='timepoint', replicate='1', value=val, readout_type='knockdown_pct')
            DataPoint.objects.create(experiment=exp, x_value=day, x_type='timepoint', replicate='2', value=val - 2, readout_type='knockdown_pct')
        rows = _build_invivo_rows(list(exp.datapoints.all()), 'day')
        labels = [r['label'] for r in rows]
        self.assertIn('Day 0', labels)
        self.assertIn('Day 7', labels)
        self.assertIn('Day 14', labels)
        self.assertNotIn('Day 3', labels)
        self.assertNotIn('Day 10', labels)

    def test_week_unit_shows_all(self):
        from app01.views import _build_invivo_rows
        exp = self._make_exp('week')
        for wk in [1.0, 2.0, 3.0]:
            DataPoint.objects.create(experiment=exp, x_value=wk, x_type='timepoint', replicate='1', value=-80.0, readout_type='knockdown_pct')
            DataPoint.objects.create(experiment=exp, x_value=wk, x_type='timepoint', replicate='2', value=-82.0, readout_type='knockdown_pct')
        rows = _build_invivo_rows(list(exp.datapoints.all()), 'week')
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['label'], 'Week 1')

    def test_cv_calculation(self):
        from app01.views import _build_invivo_rows
        exp = self._make_exp('day')
        # 3 replicates at day 7: -90, -92, -88  → mean=-90, sd≈2.0, cv≈2.22%
        for rep, val in [('1', -90.0), ('2', -92.0), ('3', -88.0)]:
            DataPoint.objects.create(experiment=exp, x_value=7.0, x_type='timepoint', replicate=rep, value=val, readout_type='knockdown_pct')
        rows = _build_invivo_rows(list(exp.datapoints.all()), 'day')
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]['mean'], -90.0, places=1)
        self.assertIsNotNone(rows[0]['sd'])
        self.assertIsNotNone(rows[0]['cv'])
        self.assertGreater(rows[0]['cv'], 0)

    def test_mean_zero_cv_is_none(self):
        from app01.views import _build_invivo_rows
        exp = self._make_exp('day')
        for rep in ['1', '2']:
            DataPoint.objects.create(experiment=exp, x_value=0.0, x_type='timepoint', replicate=rep, value=0.0, readout_type='knockdown_pct')
        rows = _build_invivo_rows(list(exp.datapoints.all()), 'day')
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]['cv'])
```

- [ ] **Step 3: 运行测试确认失败**

```bash
python manage.py test app01.tests.BuildInvivoRowsTest -v 1
```

Expected: `AttributeError: module 'app01.views' has no attribute '_build_invivo_rows'`

- [ ] **Step 4: 实现函数**

在 `app01/views.py` 的 `_build_vitro_rows` 函数之后插入：

```python
def _build_invivo_rows(datapoints, time_unit):
    """One row per filtered timepoint with mean/SD/CV from raw replicates."""
    grouped = defaultdict(list)
    for dp in datapoints:
        if not dp.is_control and dp.replicate not in ('Mean', 'SD'):
            grouped[dp.x_value].append(dp.value)

    rows = []
    for timepoint in sorted(grouped):
        if time_unit == 'day' and timepoint % 7 != 0 and timepoint != 0:
            continue

        vals = grouped[timepoint]
        n = len(vals)
        mean = _statistics.mean(vals) if n else None
        sd = _statistics.stdev(vals) if n >= 2 else None
        cv = (sd / abs(mean) * 100) if (sd is not None and mean) else None

        if time_unit == 'day':
            label = f'Day {int(timepoint)}'
        elif time_unit == 'week':
            label = f'Week {int(timepoint)}'
        else:
            label = f'{int(timepoint)} {time_unit}'

        rows.append({
            'label': label,
            'mean': round(mean, 2) if mean is not None else None,
            'sd': round(sd, 2) if sd is not None else None,
            'cv': round(cv, 1) if cv is not None else None,
            'n': n,
        })
    return rows
```

- [ ] **Step 5: 运行测试确认通过**

```bash
python manage.py test app01.tests.BuildInvivoRowsTest -v 1
```

Expected: `OK` (4 tests)

- [ ] **Step 6: 全量测试**

```bash
python manage.py test app01 -v 1
```

Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "feat: add _build_invivo_rows helper + tests (long-table Task 3)"
```

---

## Task 4: `_build_batch_groups` + 重写 `compound_list` 视图

**Files:**
- Modify: `app01/views.py` — 加 `Prefetch` import；插入 `_build_batch_groups`；重写 `compound_list`
- Modify: `app01/tests.py` — 更新 `CompoundListViewTest`

- [ ] **Step 1: 在 views.py 顶部加 Prefetch import**

找到第 8 行：
```python
from django.db.models import Q, Min, Max, Count, F
```
替换为：
```python
from django.db.models import Q, Min, Max, Count, F, Prefetch
```

- [ ] **Step 2: 写失败测试（新 context 结构）**

在 `app01/tests.py` 里找到 `class CompoundListViewTest`（约第 615 行），将整个类替换为：

```python
# ---- CompoundListViewTest ----
class CompoundListViewTest(TestCase):
    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='tester', password='pass', user_type='admin'
        )
        self.client.login(username='tester', password='pass')

        self.c1 = Compound.objects.create(
            compound_id='BPR_3M03FN01', project='3M03', target='FN', target_name='FASN'
        )
        self.c2 = Compound.objects.create(
            compound_id='BPR_3M03FN02', project='3M03', target='FN', target_name='FASN'
        )
        self.c3 = Compound.objects.create(
            compound_id='BPR_5X01TT01', project='5X01', target='TT', target_name='PCSK9'
        )
        self.exp_vitro = Experiment.objects.create(
            compound=self.c1, exp_type='in_vitro', assay_name='test', batch_label='B20260615'
        )
        ExperimentSummary.objects.create(experiment=self.exp_vitro, ic50_nm=2.0, max_kd_pct=85.0)
        DataPoint.objects.create(
            experiment=self.exp_vitro, x_value=100.0, x_type='concentration',
            replicate='Mean', value=0.25, readout_type='mRNA_remaining'
        )
        self.exp_vivo = Experiment.objects.create(
            compound=self.c1, exp_type='in_vivo', assay_name='mouse',
            batch_label='M20260615', time_unit='day'
        )
        DataPoint.objects.create(
            experiment=self.exp_vivo, x_value=7.0, x_type='timepoint',
            replicate='1', value=-75.0, readout_type='knockdown_pct'
        )
        DataPoint.objects.create(
            experiment=self.exp_vivo, x_value=7.0, x_type='timepoint',
            replicate='2', value=-77.0, readout_type='knockdown_pct'
        )

    def test_list_returns_200(self):
        resp = self.client.get('/compounds/')
        self.assertEqual(resp.status_code, 200)

    def test_list_requires_login(self):
        self.client.logout()
        resp = self.client.get('/compounds/')
        self.assertRedirects(resp, '/login/?next=/compounds/', fetch_redirect_response=False)

    def test_compound_data_in_context(self):
        resp = self.client.get('/compounds/')
        self.assertIn('compound_data', resp.context)
        ids = [item['compound'].compound_id for item in resp.context['compound_data']]
        self.assertIn('BPR_3M03FN01', ids)

    def test_filter_by_project(self):
        resp = self.client.get('/compounds/?project=5X01')
        ids = [item['compound'].compound_id for item in resp.context['compound_data']]
        self.assertIn('BPR_5X01TT01', ids)
        self.assertNotIn('BPR_3M03FN01', ids)

    def test_filter_by_tag_invitro(self):
        resp = self.client.get('/compounds/?tag=in_vitro')
        # c3 has no experiments, c1 has vitro → c1 present, c3 absent
        ids = [item['compound'].compound_id for item in resp.context['compound_data']]
        self.assertIn('BPR_3M03FN01', ids)
        self.assertNotIn('BPR_5X01TT01', ids)

    def test_batch_groups_in_compound_data(self):
        resp = self.client.get('/compounds/')
        item = next(
            d for d in resp.context['compound_data']
            if d['compound'].compound_id == 'BPR_3M03FN01'
        )
        self.assertGreaterEqual(len(item['batch_groups']), 1)
        first_group = item['batch_groups'][0]
        self.assertIn('rows', first_group)
        self.assertIn('attachments', first_group)

    def test_pagination_20_per_page(self):
        for i in range(22):
            Compound.objects.create(compound_id=f'BPR_PADN{i:02d}')
        resp = self.client.get('/compounds/')
        self.assertEqual(len(resp.context['compound_data']), 20)
```

- [ ] **Step 3: 运行测试确认失败**

```bash
python manage.py test app01.tests.CompoundListViewTest -v 1
```

Expected: 多个测试失败（`compound_data` not in context 等）

- [ ] **Step 4: 插入 `_build_batch_groups` 函数**

在 `app01/views.py` 里，`_build_invivo_rows` 函数之后插入：

```python
def _build_batch_groups(experiments):
    """Convert a list of Experiment objects into template-ready batch group dicts.

    Experiments should be pre-ordered newest-first (by batch_label desc).
    The first group gets default_open=True; all others default_open=False.
    """
    groups = []
    for idx, exp in enumerate(experiments):
        summary = getattr(exp, 'summary', None)
        all_dps = list(exp.datapoints.all())

        if exp.exp_type == 'in_vitro':
            rows = _build_vitro_rows(all_dps)
            header_ic50 = summary.ic50_nm if summary else None
            header_maxkd = summary.max_kd_pct if summary else None
        else:
            rows = _build_invivo_rows(all_dps, exp.time_unit or 'day')
            header_ic50 = None
            header_maxkd = summary.max_kd_pct if summary else None

        groups.append({
            'experiment': exp,
            'summary': summary,
            'rows': rows,
            'attachments': list(exp.attachments.all()),
            'tag_label': '体外' if exp.exp_type == 'in_vitro' else '体内',
            'tag_css': 'tag-vitro' if exp.exp_type == 'in_vitro' else 'tag-invivo',
            'header_ic50': header_ic50,
            'header_maxkd': header_maxkd,
            'timepoint_labels': [r['label'] for r in rows] if exp.exp_type == 'in_vivo' else [],
            'default_open': idx == 0,
        })
    return groups
```

- [ ] **Step 5: 重写 `compound_list` 视图**

找到 `@login_required` 紧接 `def compound_list` 的整个函数（约 824–900 行），替换为：

```python
@login_required
def compound_list(request):
    q = request.GET.get('q', '').strip()
    project = request.GET.get('project', '').strip()
    target_name_filter = request.GET.get('target_name', '').strip()
    tag = request.GET.get('tag', '').strip()

    qs = Compound.objects.prefetch_related(
        Prefetch('strands', queryset=Strand.objects.order_by('-strand_type')),
        Prefetch(
            'experiments',
            queryset=Experiment.objects.select_related('summary')
                .prefetch_related('datapoints', 'attachments')
                .order_by('-batch_label'),
        ),
    ).order_by('compound_id')

    if q:
        qs = qs.filter(compound_id__icontains=q)
    if project:
        qs = qs.filter(project=project)
    if target_name_filter:
        qs = qs.filter(target_name__icontains=target_name_filter)
    if tag:
        qs = qs.filter(experiments__exp_type=tag).distinct()

    paginator = Paginator(qs, 20)
    try:
        page_obj = paginator.page(int(request.GET.get('page', 1)))
    except (ValueError, InvalidPage):
        page_obj = paginator.page(1)

    compound_data = []
    for compound in page_obj:
        exps = list(compound.experiments.all())
        if tag:
            exps = [e for e in exps if e.exp_type == tag]
        strand_map = [(s.strand_type, s.modify_seq) for s in compound.strands.all()]
        compound_data.append({
            'compound': compound,
            'strand_map': strand_map,
            'batch_groups': _build_batch_groups(exps),
        })

    all_projects = sorted(
        Compound.objects.exclude(project='').values_list('project', flat=True).distinct()
    )
    all_targets = sorted(
        Compound.objects.exclude(target_name='').values_list('target_name', flat=True).distinct()
    )

    return render(request, 'compound_list.html', {
        'compound_data': compound_data,
        'page_obj': page_obj,
        'all_projects': all_projects,
        'all_targets': all_targets,
        'q': q,
        'project': project,
        'target_name': target_name_filter,
        'tag': tag,
    })
```

- [ ] **Step 6: 运行测试确认通过**

```bash
python manage.py test app01.tests.CompoundListViewTest -v 1
```

Expected: `OK` (7 tests)

- [ ] **Step 7: 全量测试**

```bash
python manage.py test app01 -v 1
```

Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "feat: _build_batch_groups + rewrite compound_list view (long-table Task 4)"
```

---

## Task 5: `attachment_download` 视图 + URL + 测试

**Files:**
- Modify: `app01/views.py` — 加 `FileResponse` import；新增 `attachment_download`
- Modify: `bprdb/urls.py` — 新增路由
- Modify: `app01/tests.py` — 新增 `AttachmentDownloadTest`

- [ ] **Step 1: 在 views.py 加 FileResponse import**

找到第 5 行：
```python
from django.http import HttpResponse, Http404, JsonResponse
```
替换为：
```python
from django.http import FileResponse, HttpResponse, Http404, JsonResponse
```

- [ ] **Step 2: 写失败测试**

在 `app01/tests.py` 末尾加入：

```python
# ---- AttachmentDownloadTest ----
class AttachmentDownloadTest(TestCase):
    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='dltest', password='pass', user_type='admin'
        )
        self.client.login(username='dltest', password='pass')
        c = Compound.objects.create(compound_id='BPR_ATTEST01')
        exp = Experiment.objects.create(
            compound=c, exp_type='in_vitro', assay_name='test', batch_label='AT1'
        )
        # Create attachment with an in-memory file
        from django.core.files.base import ContentFile
        self.att = ExperimentAttachment(experiment=exp, label='test_file.csv')
        self.att.file.save('test_file.csv', ContentFile(b'col1,col2\n1,2\n'), save=True)

    def tearDown(self):
        if self.att.file:
            self.att.file.delete(save=False)

    def test_valid_pk_returns_file(self):
        resp = self.client.get(f'/attachments/{self.att.pk}/download/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('attachment', resp.get('Content-Disposition', ''))

    def test_invalid_pk_returns_404(self):
        resp = self.client.get('/attachments/99999/download/')
        self.assertEqual(resp.status_code, 404)

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(f'/attachments/{self.att.pk}/download/')
        self.assertEqual(resp.status_code, 302)
```

- [ ] **Step 3: 运行测试确认失败**

```bash
python manage.py test app01.tests.AttachmentDownloadTest -v 1
```

Expected: `404` on valid pk（路由未注册）

- [ ] **Step 4: 在 views.py 末尾加 attachment_download 视图**

在 `app01/views.py` 末尾加：

```python
@login_required
def attachment_download(request, pk):
    att = get_object_or_404(ExperimentAttachment, pk=pk)
    if not att.file:
        raise Http404
    filename = os.path.basename(att.file.name)
    return FileResponse(att.file.open('rb'), as_attachment=True, filename=filename)
```

- [ ] **Step 5: 在 urls.py 注册路由**

在 `bprdb/urls.py` 末尾的 `urlpatterns` 列表里加：

```python
path('attachments/<int:pk>/download/', views.attachment_download, name='attachment_download'),
```

- [ ] **Step 6: 运行测试确认通过**

```bash
python manage.py test app01.tests.AttachmentDownloadTest -v 1
```

Expected: `OK` (3 tests)

- [ ] **Step 7: 全量测试**

```bash
python manage.py test app01 -v 1
```

Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add app01/views.py bprdb/urls.py app01/tests.py
git commit -m "feat: attachment_download view + route + tests (long-table Task 5)"
```

---

## Task 6: 重写 `compound_list.html` 长表模板

**Files:**
- Modify: `templates/compound_list.html` — 完全重写

- [ ] **Step 1: 完全替换 compound_list.html**

用以下内容完整替换 `templates/compound_list.html`：

```html
{% extends "base.html" %}
{% block page_title %} — 化合物列表{% endblock %}
{% block content %}

<div class="ds-topbar">
  <div class="ds-topbar-left">
    <span class="ds-topbar-title">化合物列表</span>
    <span style="background:#e2e8f0;border-radius:10px;padding:2px 9px;font-size:12px;margin-left:8px;">
      {{ page_obj.paginator.count }}
    </span>
  </div>
</div>

<div class="ds-content">

  <!-- 过滤栏 -->
  <form method="get" action="">
    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:8px 14px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:12px;margin-bottom:16px;">
      <span style="color:#64748b;font-weight:600;">过滤：</span>

      <span style="display:inline-flex;align-items:center;gap:4px;background:white;border:1px solid #cbd5e1;border-radius:5px;padding:3px 8px;">
        🔍 <input name="q" value="{{ q }}" placeholder="化合物 ID"
                  style="border:none;outline:none;width:120px;font-size:12px;">
      </span>

      <select name="project" style="font-size:12px;border:1px solid #cbd5e1;border-radius:5px;padding:3px 8px;background:white;">
        <option value="">全部项目</option>
        {% for p in all_projects %}
        <option value="{{ p }}" {% if p == project %}selected{% endif %}>{{ p }}</option>
        {% endfor %}
      </select>

      <select name="target_name" style="font-size:12px;border:1px solid #cbd5e1;border-radius:5px;padding:3px 8px;background:white;">
        <option value="">全部靶点</option>
        {% for t in all_targets %}
        <option value="{{ t }}" {% if t == target_name %}selected{% endif %}>{{ t }}</option>
        {% endfor %}
      </select>

      <select name="tag" style="font-size:12px;border:1px solid #cbd5e1;border-radius:5px;padding:3px 8px;background:white;">
        <option value="" {% if not tag %}selected{% endif %}>全部类型</option>
        <option value="in_vitro" {% if tag == 'in_vitro' %}selected{% endif %}>体外</option>
        <option value="in_vivo" {% if tag == 'in_vivo' %}selected{% endif %}>体内</option>
      </select>

      <button type="submit" class="ds-btn ds-btn-primary" style="font-size:12px;padding:4px 14px;">搜索</button>
      <a href="{% url 'compound_list' %}" style="font-size:12px;color:#64748b;text-decoration:none;padding:4px 8px;">清除</a>
    </div>
  </form>

  <!-- 化合物卡片 -->
  {% for item in compound_data %}
  <div style="border:1px solid #e2e8f0;border-radius:8px;margin-bottom:16px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.04);">

    <!-- 卡片头：化合物 ID / 靶点 / 项目 -->
    <div style="background:#f8fafc;padding:10px 16px;border-bottom:1px solid #e2e8f0;display:flex;align-items:center;gap:12px;">
      <a href="{% url 'compound_detail' item.compound.compound_id %}"
         style="font-weight:700;font-size:14px;color:#1d4ed8;font-family:monospace;text-decoration:none;">
        {{ item.compound.compound_id }}
      </a>
      {% if item.compound.target_name %}
      <span style="font-size:12px;font-weight:600;color:#475569;">{{ item.compound.target_name }}</span>
      {% endif %}
      {% if item.compound.project %}
      <span style="font-size:11px;color:#94a3b8;background:#f1f5f9;border-radius:4px;padding:2px 7px;">{{ item.compound.project }}</span>
      {% endif %}
    </div>

    <!-- 序列区 -->
    {% if item.strand_map %}
    <div style="padding:6px 16px;background:#fafafa;border-bottom:1px solid #f1f5f9;">
      {% for strand_type, modify_seq in item.strand_map %}
      <div style="display:flex;align-items:baseline;gap:6px;{% if not forloop.last %}margin-bottom:3px;{% endif %}">
        <span style="width:20px;font-size:10px;font-weight:700;color:#94a3b8;flex-shrink:0;">{{ strand_type }}</span>
        <code style="font-size:10px;
          {% if strand_type == 'SS' %}background:#f0fdf4;color:#166534;{% else %}background:#fef9c3;color:#78350f;{% endif %}
          border-radius:4px;padding:2px 6px;word-break:break-all;line-height:1.5;">{{ modify_seq }}</code>
      </div>
      {% endfor %}
    </div>
    {% endif %}

    <!-- 批次折叠块 -->
    {% for group in item.batch_groups %}
    <div style="border-top:1px solid #f1f5f9;">

      <!-- 折叠头（按钮） -->
      <button onclick="toggleGroup(this)"
              style="width:100%;background:{% if group.default_open %}white{% else %}#fafafa{% endif %};border:none;border-bottom:{% if group.default_open %}1px solid #f1f5f9{% else %}none{% endif %};padding:10px 16px;text-align:left;cursor:pointer;display:flex;align-items:center;gap:10px;font-size:12px;">

        <!-- Tag 徽章 -->
        <span style="font-size:11px;font-weight:700;padding:2px 8px;border-radius:4px;flex-shrink:0;
          {% if group.experiment.exp_type == 'in_vitro' %}background:#dbeafe;color:#1e40af;
          {% else %}background:#fef9c3;color:#854d0e;{% endif %}">
          {{ group.tag_label }}
        </span>

        {% if group.experiment.exp_type == 'in_vitro' %}
          {% if group.header_ic50 is not None %}
          <span style="color:#475569;">IC50: <b style="color:#15803d;">{{ group.header_ic50|floatformat:2 }} nM</b></span>
          {% endif %}
          {% if group.header_maxkd is not None %}
          <span style="color:#475569;">MaxKD: <b>{{ group.header_maxkd|floatformat:0 }}%</b></span>
          {% endif %}
        {% else %}
          {% if group.header_maxkd is not None %}
          <span style="color:#475569;">MaxKD: <b>{{ group.header_maxkd|floatformat:0 }}%</b></span>
          {% endif %}
          {% if group.experiment.dose_info %}
          <span style="color:#94a3b8;">{{ group.experiment.dose_info }}</span>
          {% endif %}
          {% if group.experiment.animal_species %}
          <span style="color:#94a3b8;font-size:11px;">{{ group.experiment.animal_species }}{% if group.experiment.animal_strain %} {{ group.experiment.animal_strain }}{% endif %}</span>
          {% endif %}
        {% endif %}

        <span style="margin-left:auto;font-size:11px;color:#94a3b8;font-family:monospace;">{{ group.experiment.batch_label }}</span>
        <span class="toggle-arrow" style="color:#94a3b8;font-size:11px;flex-shrink:0;">{% if group.default_open %}▲{% else %}▼{% endif %}</span>
      </button>

      <!-- 折叠体 -->
      <div class="group-body" style="display:{% if group.default_open %}block{% else %}none{% endif %};">

        {% if group.experiment.exp_type == 'in_vitro' %}
        <!-- 体外数据表 -->
        <table style="width:100%;border-collapse:collapse;font-size:12px;">
          <thead>
            <tr style="background:#f8fafc;color:#64748b;font-size:11px;">
              <th style="padding:5px 16px;text-align:left;font-weight:600;">Dose (nM)</th>
              <th style="padding:5px 16px;text-align:right;font-weight:600;">Mean</th>
            </tr>
          </thead>
          <tbody>
            {% for row in group.rows %}
            <tr style="border-top:1px solid #f1f5f9;">
              <td style="padding:5px 16px;font-weight:600;color:#374151;">{{ row.dose }}</td>
              <td style="padding:5px 16px;text-align:right;color:#374151;">{{ row.mean|floatformat:3 }}</td>
            </tr>
            {% empty %}
            <tr><td colspan="2" style="padding:10px 16px;color:#94a3b8;font-size:11px;">无浓度数据</td></tr>
            {% endfor %}
          </tbody>
        </table>

        {% else %}
        <!-- 体内数据表 -->
        <!-- 动物模型信息 -->
        {% if group.experiment.route or group.experiment.gender %}
        <div style="padding:5px 16px;font-size:11px;color:#64748b;border-bottom:1px solid #f8fafc;">
          给药途径: {{ group.experiment.route|default:"—" }} &nbsp;|&nbsp;
          性别: {{ group.experiment.gender|default:"—" }}
        </div>
        {% endif %}

        <!-- 时间点筛选 -->
        {% if group.timepoint_labels %}
        <div class="tp-filter" style="padding:6px 16px;display:flex;gap:8px;flex-wrap:wrap;font-size:11px;background:#fffbeb;border-bottom:1px solid #fef3c7;">
          <span style="color:#78350f;font-weight:600;flex-shrink:0;">显示时间点：</span>
          {% for label in group.timepoint_labels %}
          <label style="display:inline-flex;align-items:center;gap:3px;cursor:pointer;color:#374151;">
            <input type="checkbox" checked
                   data-tp="{{ label }}"
                   onchange="filterTimepoint(this, '{{ forloop.parentloop.counter }}_{{ forloop.parentloop.parentloop.counter }}')">
            {{ label }}
          </label>
          {% endfor %}
        </div>
        {% endif %}

        <table class="invivo-table" style="width:100%;border-collapse:collapse;font-size:12px;"
               data-tpkey="{{ forloop.parentloop.counter }}_{{ forloop.counter }}">
          <thead>
            <tr style="background:#f8fafc;color:#64748b;font-size:11px;">
              <th style="padding:5px 16px;text-align:left;font-weight:600;">时间点</th>
              <th style="padding:5px 16px;text-align:right;font-weight:600;">Mean</th>
              <th style="padding:5px 16px;text-align:right;font-weight:600;">SD</th>
              <th style="padding:5px 16px;text-align:right;font-weight:600;">CV%</th>
              <th style="padding:5px 8px;text-align:right;font-weight:600;color:#94a3b8;">n</th>
            </tr>
          </thead>
          <tbody>
            {% for row in group.rows %}
            <tr data-tp="{{ row.label }}" style="border-top:1px solid #f1f5f9;">
              <td style="padding:5px 16px;font-weight:600;color:#374151;">{{ row.label }}</td>
              <td style="padding:5px 16px;text-align:right;">{% if row.mean is not None %}{{ row.mean|floatformat:1 }}%{% else %}<span style="color:#94a3b8;">—</span>{% endif %}</td>
              <td style="padding:5px 16px;text-align:right;color:#64748b;">{% if row.sd is not None %}{{ row.sd|floatformat:2 }}{% else %}<span style="color:#94a3b8;">—</span>{% endif %}</td>
              <td style="padding:5px 16px;text-align:right;color:#64748b;">{% if row.cv is not None %}{{ row.cv|floatformat:1 }}%{% else %}<span style="color:#94a3b8;">—</span>{% endif %}</td>
              <td style="padding:5px 8px;text-align:right;color:#94a3b8;">{{ row.n }}</td>
            </tr>
            {% empty %}
            <tr><td colspan="5" style="padding:10px 16px;color:#94a3b8;font-size:11px;">无时间点数据</td></tr>
            {% endfor %}
          </tbody>
        </table>
        {% endif %}

        <!-- 附件 + 详情链接 -->
        <div style="padding:7px 16px;border-top:1px solid #f1f5f9;display:flex;gap:10px;align-items:center;flex-wrap:wrap;background:#fafafa;">
          {% for att in group.attachments %}
          <a href="{% url 'attachment_download' att.pk %}"
             style="font-size:11px;color:#475569;text-decoration:none;display:inline-flex;align-items:center;gap:3px;"
             title="{{ att.label }}">
            📎 {{ att.label|default:"附件" }}
          </a>
          {% endfor %}
          <a href="{% url 'compound_detail' item.compound.compound_id %}"
             style="margin-left:auto;font-size:11px;color:#3b82f6;text-decoration:none;font-weight:500;">
            📊 查看详情 →
          </a>
        </div>

      </div><!-- /group-body -->
    </div>
    {% endfor %}<!-- /batch groups -->

  </div><!-- /compound card -->
  {% empty %}
  <div style="text-align:center;padding:48px;color:#94a3b8;">没有找到符合条件的化合物</div>
  {% endfor %}

  <!-- 分页 -->
  {% if page_obj.paginator.num_pages > 1 %}
  <div style="padding:10px 4px;display:flex;align-items:center;justify-content:space-between;font-size:12px;color:#64748b;margin-top:8px;">
    <span>第 {{ page_obj.number }} / {{ page_obj.paginator.num_pages }} 页，共 {{ page_obj.paginator.count }} 个化合物</span>
    <div style="display:flex;gap:4px;">
      {% if page_obj.has_previous %}
      <a href="?q={{ q }}&project={{ project }}&target_name={{ target_name }}&tag={{ tag }}&page={{ page_obj.previous_page_number }}"
         style="padding:3px 8px;border:1px solid #e2e8f0;border-radius:4px;background:white;text-decoration:none;color:#475569;">◀</a>
      {% endif %}
      {% for num in page_obj.paginator.page_range %}
        {% if num == page_obj.number %}
        <span style="padding:3px 8px;border:1px solid #3b82f6;border-radius:4px;background:#3b82f6;color:white;">{{ num }}</span>
        {% elif num >= page_obj.number|add:"-3" and num <= page_obj.number|add:"3" %}
        <a href="?q={{ q }}&project={{ project }}&target_name={{ target_name }}&tag={{ tag }}&page={{ num }}"
           style="padding:3px 8px;border:1px solid #e2e8f0;border-radius:4px;background:white;text-decoration:none;color:#475569;">{{ num }}</a>
        {% endif %}
      {% endfor %}
      {% if page_obj.has_next %}
      <a href="?q={{ q }}&project={{ project }}&target_name={{ target_name }}&tag={{ tag }}&page={{ page_obj.next_page_number }}"
         style="padding:3px 8px;border:1px solid #e2e8f0;border-radius:4px;background:white;text-decoration:none;color:#475569;">▶</a>
      {% endif %}
    </div>
    <span>每页 20 个</span>
  </div>
  {% endif %}

</div><!-- /ds-content -->

<script>
function toggleGroup(btn) {
    const body = btn.nextElementSibling;
    const arrow = btn.querySelector('.toggle-arrow');
    const isOpen = body.style.display !== 'none';
    body.style.display = isOpen ? 'none' : 'block';
    btn.style.background = isOpen ? '#fafafa' : 'white';
    if (arrow) arrow.textContent = isOpen ? '▼' : '▲';
}

function filterTimepoint(checkbox, tpkey) {
    const tp = checkbox.dataset.tp;
    const table = document.querySelector(`.invivo-table[data-tpkey="${tpkey}"]`);
    if (!table) return;
    table.querySelectorAll(`tr[data-tp="${tp}"]`).forEach(row => {
        row.style.display = checkbox.checked ? '' : 'none';
    });
}
</script>

{% endblock %}
```

- [ ] **Step 2: 启动开发服务器并手动验证**

```bash
source ../seq_database_v2/venv/bin/activate
python manage.py runserver 8001
```

打开浏览器访问 `http://127.0.0.1:8001/compounds/`，确认：
- 化合物卡片正常显示（化合物ID + 靶点 + 项目）
- 序列区显示 SS/AS（如有）
- 批次折叠块可展开/折叠（点击标题行）
- 体外批次显示 Dose 表格
- 体内批次显示 Mean/SD/CV 表格 + 时间点筛选复选框
- 过滤栏筛选项目/靶点/类型有效
- 分页正常

- [ ] **Step 3: 全量测试**

```bash
python manage.py test app01 -v 1
```

Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add templates/compound_list.html
git commit -m "feat: rewrite compound_list.html as long-table card layout (long-table Task 6)"
```

---

## Task 7: 更新 `compound_detail` 视图 + 模板（附件列表）

**Files:**
- Modify: `app01/views.py` — `compound_detail` 函数加附件查询
- Modify: `templates/compound_detail.html` — 补充附件列表区块

- [ ] **Step 1: 更新 compound_detail 视图加载附件**

找到 `app01/views.py` 里的 `compound_detail` 函数（约 955 行），将 `return render(...)` 之前的代码替换，加入附件查询：

找到：
```python
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

替换为：
```python
    vitro_chart_data = [_build_vitro_chart_data(exp) for exp in vitro]
    invivo_batches = build_invivo_summary(vivo).get(compound_id, [])
    all_attachments = list(
        ExperimentAttachment.objects.filter(
            experiment__compound_id=compound_id
        ).select_related('experiment').order_by('-uploaded_at')
    )
    return render(request, 'compound_detail.html', {
        'compound':         compound,
        'strands':          strands,
        'vitro_batches':    vitro,
        'vitro_chart_data': vitro_chart_data,
        'invivo_batches':   invivo_batches,
        'all_attachments':  all_attachments,
    })
```

- [ ] **Step 2: 在 compound_detail.html 末尾（{% endblock %} 之前）加附件区块**

读取 `templates/compound_detail.html` 末尾，找到 `{% endblock %}` 前插入：

```html
{% if all_attachments %}
<div style="margin-top:24px;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
  <div style="background:#f8fafc;padding:10px 16px;border-bottom:1px solid #e2e8f0;font-weight:600;font-size:13px;color:#374151;">
    📎 原始文件附件
  </div>
  <div style="padding:8px 16px;">
    {% for att in all_attachments %}
    <div style="display:flex;align-items:center;gap:10px;padding:6px 0;{% if not forloop.last %}border-bottom:1px solid #f1f5f9;{% endif %}">
      <span style="font-size:11px;color:#94a3b8;font-family:monospace;min-width:100px;">{{ att.experiment.batch_label }}</span>
      <a href="{% url 'attachment_download' att.pk %}"
         style="font-size:12px;color:#3b82f6;text-decoration:none;">
        {{ att.label|default:att.file.name }}
      </a>
      <span style="margin-left:auto;font-size:11px;color:#94a3b8;">{{ att.uploaded_at|date:"Y-m-d H:i" }}</span>
    </div>
    {% endfor %}
  </div>
</div>
{% endif %}
```

- [ ] **Step 3: 手动验证**

访问任意有附件数据的化合物详情页 `http://127.0.0.1:8001/compounds/<compound_id>/`，确认：
- 页面末尾出现"原始文件附件"区块
- 附件链接可点击下载
- 无附件时该区块不显示

- [ ] **Step 4: 全量测试**

```bash
python manage.py test app01 -v 1
```

Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add app01/views.py templates/compound_detail.html
git commit -m "feat: add attachments list to compound_detail view + template (long-table Task 7)"
```

---

## 自我审查

**1. Spec coverage 检查：**
- ✅ Part 1 (target_name 字段) → Task 1
- ✅ Part 2.3 `compound_list` 视图逻辑 → Task 4
- ✅ Part 2.5 `_build_vitro_rows` → Task 2
- ✅ Part 2.6 `_build_invivo_rows` → Task 3
- ✅ Part 2.7 模板结构 → Task 6
- ✅ Part 3 `attachment_download` → Task 5
- ✅ Part 4 详情页附件 → Task 7
- ✅ Part 6 测试用例 → Tasks 2/3/4/5

**2. 无占位符**：所有步骤含完整代码。

**3. 类型一致性**：
- `_build_vitro_rows` 返回 `[{'dose': float, 'mean': float}]`，模板用 `row.dose` / `row.mean` ✅
- `_build_invivo_rows` 返回 `[{'label': str, 'mean', 'sd', 'cv', 'n'}]`，模板字段对应 ✅
- `_build_batch_groups` 返回含 `rows`、`attachments`、`timepoint_labels` 的 dict，模板 for 循环字段对应 ✅
- `compound_data` context 含 `compound`、`strand_map`（list of tuples）、`batch_groups` ✅
