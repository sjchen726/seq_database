# Group B+C Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 2 个显示/交互 Bug（B1 多词搜索表头排序、B2 UPDATE TIME 双行）并补充 2 个缺失功能（C1 裸序列列表导航入口、C2 模块列表搜索）。

**Architecture:** 所有 4 项改动完全独立，按 C1→B2→B1→C2 顺序逐项执行，每项单独提交。Django 5.1 项目，无测试套件，改动后通过 `python manage.py runserver` 手动验证。

**Tech Stack:** Django 5.1, Python 3.10, Django Templates, MySQL

---

## 文件清单

| 文件 | 改动原因 |
|------|---------|
| `templates/base.html` | C1：侧边栏添加裸序列列表链接 |
| `app01/views.py` | B2：`build_duplex_groups()` 添加 `latest_update_time`；C2：`module_list`/`seqmodule_list` 添加 `q` 过滤 |
| `templates/_seq_group_row.html` | B2：UPDATE TIME 改为单行显示 |
| `templates/seq_list.html` | B1：多词模式下表头去掉 `ds-th-sort` class |
| `templates/module_list.html` | C2：topbar 添加搜索框，分页链接保留 `q` 参数 |
| `templates/seqmodule_list.html` | C2：同上 |

---

## Task 1: C1 — 侧边栏添加裸序列列表链接

**Files:**
- Modify: `templates/base.html:41-43`

**背景：** `reg_seq_list` 视图、URL、模板均已存在，只是未加入侧边栏导航。当前"序列数据"节只有一个"序列列表"链接（第 41 行），在其后插入新链接即可。

- [ ] **Step 1: 在 `base.html` 第 43 行后（`</a>` 之后）插入裸序列列表链接**

将文件第 41–44 行从：

```html
    <a href="{% url 'seq_list' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'seq_list' %}active{% endif %}">
      <i class="bi bi-table ds-nav-icon"></i> 序列列表
    </a>

    <div class="ds-nav-divider"></div>
```

改为：

```html
    <a href="{% url 'seq_list' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'seq_list' %}active{% endif %}">
      <i class="bi bi-table ds-nav-icon"></i> 序列列表
    </a>
    <a href="{% url 'reg_seq_list' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'reg_seq_list' %}active{% endif %}">
      <i class="bi bi-list-ul ds-nav-icon"></i> 裸序列列表
    </a>

    <div class="ds-nav-divider"></div>
```

- [ ] **Step 2: 启动开发服务器验证**

```bash
source venv/bin/activate && python manage.py runserver
```

在浏览器中访问任意页面，确认侧边栏"序列数据"节中出现"裸序列列表"链接；点击后跳转到 `/reg_seq_list/`，且该链接高亮为 active 状态。

- [ ] **Step 3: 提交**

```bash
git add templates/base.html
git commit -m "feat: add reg_seq_list to sidebar navigation"
```

---

## Task 2: B2 — UPDATE TIME 只显示最新的一个

**Files:**
- Modify: `app01/views.py:2195-2200`（`build_duplex_groups` 末尾 `sequence_groups.append(...)` 块）
- Modify: `templates/_seq_group_row.html:200-205`

**背景：** `build_duplex_groups()` 目前构造的 group dict 不含 `latest_update_time`；模板第 200–205 行分两行显示 AS 和 SS 的更新时间。修复分两步：view 计算最大值，模板改为单行。

`formatted_update_time` 格式为 `'YYYY-MM-DD HH:MM'`，字典序等价时间序，`max()` 直接可用。

- [ ] **Step 1: 在 `views.py` 的 `sequence_groups.append(...)` 块中添加 `latest_update_time`**

将第 2195–2200 行从：

```python
        sequence_groups.append({
            'project': project,
            'duplex_id': duplex_id,
            'items': sorted_items,
            'aligned_columns': aligned,
        })
```

改为：

```python
        times = [item.get('formatted_update_time') for item in sorted_items
                 if item.get('formatted_update_time')]
        sequence_groups.append({
            'project': project,
            'duplex_id': duplex_id,
            'items': sorted_items,
            'aligned_columns': aligned,
            'latest_update_time': max(times) if times else None,
        })
```

- [ ] **Step 2: 在 `_seq_group_row.html` 将双行更新时间改为单行**

将第 200–205 行从：

```html
          <td>
            {{ group.items.0.formatted_update_time|default_if_none:'' }}
            {% if group.items.1 and group.items.1.formatted_update_time %}
              <br>{{ group.items.1.formatted_update_time }}
            {% endif %}
          </td>
```

改为：

```html
          <td>{{ group.latest_update_time|default_if_none:'' }}</td>
```

- [ ] **Step 3: 验证**

启动服务器，访问序列列表（`/seq_list/`），在含 AS+SS 两条记录的 duplex 行上确认 UPDATE TIME 列只显示一个时间值（较新的那个），不再换行显示两个。

- [ ] **Step 4: 提交**

```bash
git add app01/views.py templates/_seq_group_row.html
git commit -m "fix: show only the latest update_time per duplex group"
```

---

## Task 3: B1 — 多词搜索模式下禁用表头排序样式

**Files:**
- Modify: `templates/seq_list.html:183-201`

**背景：** 多词搜索模式（`is_multi_term=True`）下，`<tbody>` 同时含组标题行（`.search-group-header`）和数据行，DataTables 不初始化（无 `id="example"`），但带 `ds-th-sort` 的表头仍显示 `cursor:pointer` 的可点击样式。将 `ds-th-sort` 改为条件渲染，多词模式下退化为普通静态表头。

共 10 个需要修改的 `<th>`（第 183–201 行）：

| 行号 | 列名 |
|------|------|
| 183 | Strand ID |
| 184 | Project |
| 185 | Target |
| 186 | Sequence ID |
| 196 | Transcript |
| 197 | Position |
| 198 | Strand_MWs |
| 199 | Parents |
| 200 | Remarks |
| 201 | Update Time |

- [ ] **Step 1: 将 `seq_list.html` 第 183–201 行的 10 个 `ds-th-sort` 改为条件渲染**

将这 10 行逐一修改，模式为：

```html
<!-- 修改前 -->
<th class="ds-th-sort">列名</th>

<!-- 修改后 -->
<th {% if not is_multi_term %}class="ds-th-sort"{% endif %}>列名</th>
```

具体 10 处改动（原文→新文）：

第 183 行：
```html
          <th {% if not is_multi_term %}class="ds-th-sort"{% endif %}>Strand ID</th>
```

第 184 行：
```html
          <th {% if not is_multi_term %}class="ds-th-sort"{% endif %}>Project</th>
```

第 185 行：
```html
          <th {% if not is_multi_term %}class="ds-th-sort"{% endif %}>Target</th>
```

第 186 行：
```html
          <th {% if not is_multi_term %}class="ds-th-sort"{% endif %}>Sequence ID</th>
```

第 196 行：
```html
          <th {% if not is_multi_term %}class="ds-th-sort"{% endif %}>Transcript</th>
```

第 197 行：
```html
          <th {% if not is_multi_term %}class="ds-th-sort"{% endif %}>Position</th>
```

第 198 行：
```html
          <th {% if not is_multi_term %}class="ds-th-sort"{% endif %}>Strand_MWs</th>
```

第 199 行：
```html
          <th {% if not is_multi_term %}class="ds-th-sort"{% endif %}>Parents</th>
```

第 200 行：
```html
          <th {% if not is_multi_term %}class="ds-th-sort"{% endif %}>Remarks</th>
```

第 201 行：
```html
          <th {% if not is_multi_term %}class="ds-th-sort"{% endif %}>Update Time</th>
```

- [ ] **Step 2: 验证**

1. 访问单词搜索结果（`/seq_list/?q=xxx`，单个词），确认表头列仍有 hover 高亮/pointer 效果。
2. 访问多词搜索结果（`/seq_list/?q=xxx+yyy`，多个词，触发 `is_multi_term=True`），确认表头不再有 pointer 效果，纯静态文本。

- [ ] **Step 3: 提交**

```bash
git add templates/seq_list.html
git commit -m "fix: disable ds-th-sort on table headers in multi-term search mode"
```

---

## Task 4: C2 — 模块列表搜索功能

**Files:**
- Modify: `app01/views.py:2681-2693`（`module_list` view）
- Modify: `app01/views.py:2823-2835`（`seqmodule_list` view）
- Modify: `templates/module_list.html`（topbar 搜索框 + 分页链接）
- Modify: `templates/seqmodule_list.html`（topbar 搜索框 + 分页链接）

**背景：** 两个视图目前无关键字过滤，分页链接也不携带 `q` 参数。需在 view 端添加 `q` 过滤，在模板 topbar 添加搜索框，并修复分页链接以保留 `q`。

### 4a: 修改 `module_list` view

- [ ] **Step 1: 将 `views.py` 第 2681–2693 行改为支持 `q` 过滤**

将以下代码：

```python
def module_list(request):
    page_size = int(request.GET.get('page_size', 20))
    page = int(request.GET.get('page', 1))

    queryset = DeliveryModule.objects.all().values('id', 'keyword', 'type_code', 'Strand_MWs')
    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(page)

    return render(request, 'module_list.html', {
        'module_list': page_obj.object_list,
        'page_obj': page_obj,
        'page_size': page_size,
    })
```

改为：

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

### 4b: 修改 `seqmodule_list` view

- [ ] **Step 2: 将 `views.py` 第 2823–2835 行改为支持 `q` 过滤**

将以下代码：

```python
def seqmodule_list(request):
    page_size = int(request.GET.get('page_size', 20))
    page = int(request.GET.get('page', 1))

    queryset = SeqModule.objects.all().values('id', 'keyword', 'base_char', 'linker_connector')
    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(page)

    return render(request, 'seqmodule_list.html', {
        'seqmodule_list': page_obj.object_list,
        'page_obj': page_obj,
        'page_size': page_size,
    })
```

改为：

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

### 4c: 修改 `module_list.html` 模板

- [ ] **Step 3: 在 topbar（`{% endblock topbar_content %}` 之前）添加搜索框**

将 `module_list.html` 第 8–10 行从：

```html
  <span class="ds-topbar-spacer"></span>
  <a href="{% url 'upload_modules' %}" class="ds-btn ds-btn-ghost">&#8593; 批量上传</a>
  <a href="{% url 'edit_module' %}" class="ds-btn ds-btn-primary">&#43; 新增模块</a>
```

改为：

```html
  <span class="ds-topbar-spacer"></span>
  <form method="get" action="" style="display:contents;">
    <div class="ds-search-wrap" style="width:180px;">
      <i class="bi bi-search ds-search-icon"></i>
      <input type="text" name="q" class="ds-search-input" placeholder="搜索 Keyword…" value="{{ q }}">
    </div>
    {% if q %}<a href="{% url 'module_list' %}" class="ds-btn ds-btn-ghost" style="height:34px;padding:0 10px;font-size:11.5px;">✕ 清除</a>{% endif %}
  </form>
  <a href="{% url 'upload_modules' %}" class="ds-btn ds-btn-ghost">&#8593; 批量上传</a>
  <a href="{% url 'edit_module' %}" class="ds-btn ds-btn-primary">&#43; 新增模块</a>
```

- [ ] **Step 4: 修复 `module_list.html` 分页链接以保留 `q` 参数**

分页区域共 3 处链接（第 66、72、76 行），将：

```html
      <a href="?page={{ page_obj.previous_page_number }}&page_size={{ page_size }}" class="ds-pg">‹</a>
```
改为：
```html
      <a href="?page={{ page_obj.previous_page_number }}&page_size={{ page_size }}{% if q %}&q={{ q }}{% endif %}" class="ds-pg">‹</a>
```

将：
```html
        <a href="?page={{ num }}&page_size={{ page_size }}" class="ds-pg">{{ num }}</a>
```
改为：
```html
        <a href="?page={{ num }}&page_size={{ page_size }}{% if q %}&q={{ q }}{% endif %}" class="ds-pg">{{ num }}</a>
```

将：
```html
      <a href="?page={{ page_obj.next_page_number }}&page_size={{ page_size }}" class="ds-pg">›</a>
```
改为：
```html
      <a href="?page={{ page_obj.next_page_number }}&page_size={{ page_size }}{% if q %}&q={{ q }}{% endif %}" class="ds-pg">›</a>
```

同时修复 `ds-pagesize-select` 的 `onchange` 跳转（第 56 行），将：
```html
      <select class="ds-pagesize-select" onchange="window.location.href='?page=1&page_size='+this.value">
```
改为：
```html
      <select class="ds-pagesize-select" onchange="window.location.href='?page=1&page_size='+this.value+'{% if q %}&q={{ q }}{% endif %}'">
```

### 4d: 修改 `seqmodule_list.html` 模板

- [ ] **Step 5: 修改 `seqmodule_list.html` topbar，添加搜索框**

将第 8–10 行从：

```html
  <span class="ds-topbar-spacer"></span>
  <a href="{% url 'upload_seqmodules' %}" class="ds-btn ds-btn-ghost">&#8593; 批量上传</a>
  <a href="{% url 'edit_seqmodule' %}" class="ds-btn ds-btn-primary">＋ 新增模块</a>
```

改为：

```html
  <span class="ds-topbar-spacer"></span>
  <form method="get" action="" style="display:contents;">
    <div class="ds-search-wrap" style="width:180px;">
      <i class="bi bi-search ds-search-icon"></i>
      <input type="text" name="q" class="ds-search-input" placeholder="搜索 Keyword…" value="{{ q }}">
    </div>
    {% if q %}<a href="{% url 'seqmodule_list' %}" class="ds-btn ds-btn-ghost" style="height:34px;padding:0 10px;font-size:11.5px;">✕ 清除</a>{% endif %}
  </form>
  <a href="{% url 'upload_seqmodules' %}" class="ds-btn ds-btn-ghost">&#8593; 批量上传</a>
  <a href="{% url 'edit_seqmodule' %}" class="ds-btn ds-btn-primary">＋ 新增模块</a>
```

- [ ] **Step 6: 修复 `seqmodule_list.html` 分页链接以保留 `q` 参数**

与 module_list.html 相同模式，修复 3 处分页链接和 pagesize-select：

上一页链接改为：
```html
      <a href="?page={{ page_obj.previous_page_number }}&page_size={{ page_size }}{% if q %}&q={{ q }}{% endif %}" class="ds-pg">‹</a>
```

页码链接改为：
```html
        <a href="?page={{ num }}&page_size={{ page_size }}{% if q %}&q={{ q }}{% endif %}" class="ds-pg">{{ num }}</a>
```

下一页链接改为：
```html
      <a href="?page={{ page_obj.next_page_number }}&page_size={{ page_size }}{% if q %}&q={{ q }}{% endif %}" class="ds-pg">›</a>
```

pagesize-select 改为：
```html
      <select class="ds-pagesize-select" onchange="window.location.href='?page=1&page_size='+this.value+'{% if q %}&q={{ q }}{% endif %}'">
```

- [ ] **Step 7: 验证两个搜索功能**

启动服务器后：
1. 访问 `/module_list/`，在搜索框输入关键词（如 `moe`），确认列表过滤显示；点击"✕ 清除"，确认恢复全量显示；切换分页，确认 `q` 参数保留。
2. 访问 `/seqmodule_list/`，同上操作验证。

- [ ] **Step 8: 提交**

```bash
git add app01/views.py templates/module_list.html templates/seqmodule_list.html
git commit -m "feat: add keyword search to module_list and seqmodule_list"
```
