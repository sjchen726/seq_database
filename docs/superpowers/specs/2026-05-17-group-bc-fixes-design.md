# Group B+C 修复设计 — 2026-05-17

## Scope

修复 2 个显示/交互 Bug（B1、B2）+ 补充 2 个缺失功能（C1、C2）。所有改动独立，无依赖关系。

---

## B1 — 多词搜索模式下禁用表头排序

**文件：** `templates/seq_list.html`

**根因：** 多词搜索模式（`is_multi_term=True`）下，`<tbody>` 同时包含组标题行（`.search-group-header`，colspan=16）和正常数据行。若任何排序行为（DataTables 或浏览器）对这些行重排，分组结构立即崩溃，产生严重错位。当前代码在多词模式下不给 table 加 `id="example"`，DataTables 不初始化；但所有列头仍保留 `ds-th-sort` class（`cursor:pointer`），给用户可排序的错误提示，实际点击后可能触发非预期行为。

**修复：** 在 `seq_list.html` 中，对所有带 `ds-th-sort` 的 `<th>` 元素，改为条件渲染——仅在单词模式下（`{% if not is_multi_term %}`）添加该 class；多词模式下表头为普通静态文本，不再显示可点击样式。

涉及列（共 8 个）：Strand ID、Project、Target、Sequence ID、Transcript、Position、Strand_MWs、Parents、Remarks、Update Time（其中 Ligand 1/2、Sequences、实验数据、操作本身就无此 class，无需改动）。

**改动位置：** `templates/seq_list.html` 第 183–201 行，每个 `<th class="ds-th-sort">` 改为：
```html
<th {% if not is_multi_term %}class="ds-th-sort"{% endif %}>列名</th>
```

**不改动：** 单词模式下的 DataTables 排序行为保持不变（仅 column 1 Strand ID 可排序）。

---

## B2 — UPDATE TIME 只显示 AS/SS 中较新的一个

**文件：** `app01/views.py`（`build_duplex_groups`），`templates/_seq_group_row.html`

**根因：** `_seq_group_row.html` 第 201–204 行分两行显示 `group.items.0.formatted_update_time` 和 `group.items.1.formatted_update_time`，用户只需看最新的那个。

**修复：**

1. `app01/views.py` — `build_duplex_groups()` 中，在构造 group dict 时添加 `latest_update_time`：

```python
times = [item.get('formatted_update_time') for item in sorted_items
         if item.get('formatted_update_time')]
# 格式 'YYYY-MM-DD HH:MM'，字典序等价时间序
group_dict['latest_update_time'] = max(times) if times else None
```

2. `templates/_seq_group_row.html` 第 201–204 行替换为：

```html
<td>{{ group.latest_update_time|default_if_none:'' }}</td>
```

---

## C1 — 裸序列展示页面加入侧边栏导航

**文件：** `templates/base.html`

**发现：** v2 已完整实现 `reg_seq_list`（视图 `app01/views.py:2470`、模板 `templates/reg_seq_list.html`、URL `reg_seq_list/`），但未添加到侧边栏，用户不知道入口。

**修复：** 在 `templates/base.html` 侧边栏"序列数据"节（约第 40–44 行），在"序列列表"链接之后添加：

```html
<a href="{% url 'reg_seq_list' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'reg_seq_list' %}active{% endif %}">
  <i class="bi bi-list-ul ds-nav-icon"></i> 裸序列列表
</a>
```

---

## C2 — 模块列表搜索功能

**文件：** `app01/views.py`（2 处），`templates/module_list.html`，`templates/seqmodule_list.html`

**根因：** `module_list` 和 `seqmodule_list` 视图无关键字过滤，数据量大时查找困难。

**修复：**

### View 端（`app01/views.py`）

**`module_list`（约第 2681 行）：**

```python
def module_list(request):
    page_size = int(request.GET.get('page_size', 20))
    page = int(request.GET.get('page', 1))
    q = request.GET.get('q', '').strip()

    queryset = DeliveryModule.objects.all().values('id', 'keyword', 'type_code', 'Strand_MWs')
    if q:
        queryset = queryset.filter(keyword__icontains=q)
    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(page)

    return render(request, 'module_list.html', {
        'module_list': page_obj.object_list,
        'page_obj': page_obj,
        'page_size': page_size,
        'q': q,
    })
```

**`seqmodule_list`（约第 2823 行）：**

```python
def seqmodule_list(request):
    page_size = int(request.GET.get('page_size', 20))
    page = int(request.GET.get('page', 1))
    q = request.GET.get('q', '').strip()

    queryset = SeqModule.objects.all().values('id', 'keyword', 'base_char', 'linker_connector')
    if q:
        queryset = queryset.filter(keyword__icontains=q)
    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(page)

    return render(request, 'seqmodule_list.html', {
        'seqmodule_list': page_obj.object_list,
        'page_obj': page_obj,
        'page_size': page_size,
        'q': q,
    })
```

### 模板端

两个模板的 topbar（紧接计数 span 之后，上传/新增按钮之前）插入搜索框：

```html
<form method="get" action="" style="display:contents;">
  <div class="ds-search-wrap" style="width:180px;">
    <i class="bi bi-search ds-search-icon"></i>
    <input type="text" name="q" class="ds-search-input" placeholder="搜索 Keyword…" value="{{ q }}">
  </div>
  {% if q %}<a href="{% url 'module_list' %}" class="ds-btn ds-btn-ghost" style="height:34px;padding:0 10px;font-size:11.5px;">✕ 清除</a>{% endif %}
</form>
```

（`seqmodule_list.html` 中 `{% url 'module_list' %}` 改为 `{% url 'seqmodule_list' %}`）

分页链接需附带 `q` 参数，防止翻页时搜索词丢失：
```html
<a href="?page={{ num }}&page_size={{ page_size }}{% if q %}&q={{ q }}{% endif %}">{{ num }}</a>
```

---

## 执行顺序建议

| 顺序 | 项目 | 难度 | 文件 |
|------|------|------|------|
| 1 | C1 — 侧边栏导航 | 极低（1行） | `base.html` |
| 2 | B2 — UPDATE TIME | 低（views.py + 模板） | `views.py`, `_seq_group_row.html` |
| 3 | B1 — 表头排序禁用 | 低（模板条件渲染） | `seq_list.html` |
| 4 | C2 — 模块搜索 | 低（2 views + 2 模板） | `views.py`, `module_list.html`, `seqmodule_list.html` |
