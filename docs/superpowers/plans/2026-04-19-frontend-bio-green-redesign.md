# Frontend Bio-Green Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the Bio-Green theme (green brand + blue-purple interactive) to the SeqDB worktree, fix all four known style inconsistencies, and add pagination to `reg_seq_list`.

**Architecture:** CSS-first strategy — `design-system.css` is updated once, then templates are updated to use the design system classes. All work is in `.worktrees/frontend-redesign/`. No new routes or models.

**Tech Stack:** Django 5.1 templates, vanilla CSS/JS, Bootstrap Icons (already loaded), Django `Paginator` (already imported in `views.py`).

---

## File Map

| File | Action |
|---|---|
| `.worktrees/frontend-redesign/static/css/design-system.css` | Modify — brand colors + DataTables overrides + BLAST classes |
| `.worktrees/frontend-redesign/templates/base.html` | Modify — sidebar icons, width |
| `.worktrees/frontend-redesign/templates/module_list.html` | Rewrite — use ds-* classes |
| `.worktrees/frontend-redesign/templates/seqmodule_list.html` | Rewrite — use ds-* classes |
| `.worktrees/frontend-redesign/templates/seq_list.html` | Modify — remove old CSS links, add ds-table class |
| `.worktrees/frontend-redesign/templates/blast_results.html` | Modify — remove inline style block |
| `.worktrees/frontend-redesign/templates/multi_blast_results.html` | Modify — remove inline style block |
| `.worktrees/frontend-redesign/templates/multi_blast.html` | Modify — remove inline style block if present |
| `.worktrees/frontend-redesign/app01/views.py` | Modify — add pagination + search to `reg_seq_list` |
| `.worktrees/frontend-redesign/templates/reg_seq_list.html` | Modify — add search input + pagination footer |

---

## Task 1: Update `design-system.css` — Brand Colors

**Files:**
- Modify: `.worktrees/frontend-redesign/static/css/design-system.css`

- [ ] **Step 1: Replace `.ds-logo-mark` gradient**

Find (line ~51):
```css
.ds-logo-mark {
  ...
  background: linear-gradient(135deg, #38bdf8, #6366f1);
  ...
  box-shadow: 0 3px 10px rgba(99,102,241,0.32);
```
Replace those two properties:
```css
  background: #16a34a;
  box-shadow: 0 3px 10px rgba(22,163,74,0.32);
```

- [ ] **Step 2: Replace sidebar active indicator gradient**

Find (line ~102):
```css
.ds-nav-item.active::before {
  ...
  background: linear-gradient(180deg, #38bdf8, #6366f1);
```
Replace:
```css
  background: linear-gradient(180deg, #16a34a, #22d3ee);
```

- [ ] **Step 3: Update `.ds-sidebar` width**

Find:
```css
.ds-sidebar {
  width: 210px;
```
Replace:
```css
.ds-sidebar {
  width: 220px;
```

- [ ] **Step 4: Replace `.ds-btn-primary` gradient**

Find (line ~188):
```css
.ds-btn-primary {
  background: linear-gradient(135deg, #38bdf8, #6366f1);
  color: #fff;
  box-shadow: 0 2px 8px rgba(99,102,241,0.28);
```
Replace:
```css
.ds-btn-primary {
  background: linear-gradient(135deg, #16a34a, #22d3ee);
  color: #fff;
  box-shadow: 0 2px 8px rgba(22,163,74,0.28);
```

- [ ] **Step 5: Replace `.ds-pg.active` gradient**

Find (line ~373):
```css
.ds-pg.active { background: linear-gradient(135deg, #38bdf8, #6366f1); color: #fff; border-color: transparent; font-weight: 700; box-shadow: 0 2px 6px rgba(99,102,241,0.3); }
```
Replace:
```css
.ds-pg.active { background: linear-gradient(135deg, #16a34a, #22d3ee); color: #fff; border-color: transparent; font-weight: 700; box-shadow: 0 2px 6px rgba(22,163,74,0.3); }
```

- [ ] **Step 6: Replace `.ds-user-avatar` gradient**

Find (line ~133):
```css
.ds-user-avatar {
  ...
  background: linear-gradient(135deg, #38bdf8, #6366f1);
```
Replace:
```css
  background: linear-gradient(135deg, #16a34a, #22d3ee);
```

- [ ] **Step 7: Commit**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2/.worktrees/frontend-redesign
git add static/css/design-system.css
git commit -m "feat: apply green brand colors to design system"
```

---

## Task 2: Update `design-system.css` — DataTables Overrides + BLAST Classes

**Files:**
- Modify: `.worktrees/frontend-redesign/static/css/design-system.css`

- [ ] **Step 1: Append DataTables overrides at end of file**

Add to the very end of `design-system.css`:
```css

/* ── DataTables overrides ── */
.dataTables_wrapper { font-family: inherit; font-size: 11.5px; }
.dataTables_filter { margin-bottom: 0; }
.dataTables_filter label { display: flex; align-items: center; gap: 6px; font-size: 11.5px; color: #64748b; }
.dataTables_filter input {
  height: 32px; border: 1px solid #e2e8f0 !important; border-radius: 8px;
  padding: 0 12px; font-size: 11.5px; font-family: 'DM Sans', sans-serif;
  color: #334155; background: #fff; outline: none; margin-left: 0 !important;
}
.dataTables_filter input:focus { border-color: #a5b4fc !important; box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }
.dataTables_info { font-size: 11px; color: #94a3b8; font-family: 'DM Mono', monospace; padding-top: 6px; }
.dataTables_length label { font-size: 11.5px; color: #64748b; display: flex; align-items: center; gap: 6px; }
.dataTables_length select {
  height: 30px; border: 1px solid #e2e8f0; border-radius: 6px;
  padding: 0 8px; font-size: 11.5px; color: #334155; background: #f8fafc; outline: none;
}
.dataTables_paginate { padding-top: 6px !important; }
.dataTables_paginate .paginate_button {
  min-width: 28px; height: 28px; border-radius: 6px !important;
  border: 1px solid #e2e8f0 !important; background: #fff !important;
  color: #64748b !important; font-size: 11px !important; font-weight: 500;
  padding: 0 6px !important; margin: 0 1px !important;
  transition: all 0.12s; cursor: pointer;
}
.dataTables_paginate .paginate_button:hover {
  border-color: #c4b5fd !important; color: #6366f1 !important;
  background: #f5f3ff !important;
}
.dataTables_paginate .paginate_button.current,
.dataTables_paginate .paginate_button.current:hover {
  background: linear-gradient(135deg, #16a34a, #22d3ee) !important;
  color: #fff !important; border-color: transparent !important;
  font-weight: 700 !important; box-shadow: 0 2px 6px rgba(22,163,74,0.3);
}
.dataTables_paginate .paginate_button.disabled,
.dataTables_paginate .paginate_button.disabled:hover {
  color: #cbd5e1 !important; background: #fff !important;
  border-color: #f1f5f9 !important; cursor: default;
}
```

- [ ] **Step 2: Append BLAST component classes**

Continue adding to end of file:
```css

/* ── BLAST result components ── */
.ds-info-card {
  background: #fff; border: 1px solid #e8edf4; border-radius: 8px;
  padding: 14px 18px; margin-bottom: 16px;
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  box-shadow: 0 1px 4px rgba(15,23,42,0.05);
}
.ds-seq-badge {
  font-family: 'DM Mono', monospace; font-size: 13px;
  background: #eff6ff; padding: 3px 10px; border-radius: 4px;
  letter-spacing: 1px; color: #1d4ed8;
}
.ds-source-badge {
  background: #fbbf24; color: #78350f;
  padding: 1px 8px; border-radius: 10px;
  font-size: 11px; margin-left: 6px; font-weight: 600;
}
/* multi_blast_results local classes */
.ds-result-stat-bar {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 16px; background: #f8fafc;
  border: 1px solid #e8edf4; border-radius: 8px;
  margin-bottom: 16px; font-size: 13px; flex-wrap: wrap;
}
.ds-result-stat-bar h4 { margin: 0; font-size: 14px; font-weight: 700; color: #0f172a; }
.ds-stat-divider { color: #cbd5e1; }
.ds-stat-item { color: #475569; }
.ds-stat-item .cnt { font-weight: 700; color: #0f172a; }
.ds-group-card { border-radius: 8px; overflow: hidden; border: 1px solid #e8edf4; margin-bottom: 20px; }
.ds-group-card-ss { border-color: #bfdbfe; }
.ds-group-card-as { border-color: #bbf7d0; }
```

- [ ] **Step 3: Commit**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2/.worktrees/frontend-redesign
git add static/css/design-system.css
git commit -m "feat: add DataTables overrides and BLAST classes to design system"
```

---

## Task 3: Update `base.html` — Sidebar Icons

**Files:**
- Modify: `.worktrees/frontend-redesign/templates/base.html`

- [ ] **Step 1: Replace all `<span class="ds-nav-dot"></span>` with Bootstrap Icons**

Replace each nav item's dot span with the corresponding icon. The full sidebar nav section (lines 40–75) becomes:

```html
    <div class="ds-nav-section">序列数据</div>
    <a href="{% url 'seq_list' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'seq_list' %}active{% endif %}">
      <i class="bi bi-table" style="font-size:13px;flex-shrink:0;"></i> 序列列表
    </a>

    <div class="ds-nav-divider"></div>
    <div class="ds-nav-section">功能模块</div>
    <a href="{% url 'register_seq' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'register_seq' %}active{% endif %}">
      <i class="bi bi-plus-circle" style="font-size:13px;flex-shrink:0;"></i> 序列注册
    </a>
    <a href="{% url 'seq_delivery' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'seq_delivery' %}active{% endif %}">
      <i class="bi bi-cloud-upload" style="font-size:13px;flex-shrink:0;"></i> 序列上传
    </a>

    <div class="ds-nav-divider"></div>
    <div class="ds-nav-section">BLAST</div>
    <a href="{% url 'multi_blast' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'multi_blast' or request.resolver_match.url_name == 'multi_blast_results' %}active{% endif %}">
      <i class="bi bi-search" style="font-size:13px;flex-shrink:0;"></i> 多序列比对
    </a>

    <div class="ds-nav-divider"></div>
    <div class="ds-nav-section">模块管理</div>
    <a href="{% url 'module_list' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'module_list' or request.resolver_match.url_name == 'edit_module' %}active{% endif %}">
      <i class="bi bi-box-seam" style="font-size:13px;flex-shrink:0;"></i> Delivery 模块
    </a>
    <a href="{% url 'seqmodule_list' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'seqmodule_list' or request.resolver_match.url_name == 'edit_seqmodule' %}active{% endif %}">
      <i class="bi bi-check2-square" style="font-size:13px;flex-shrink:0;"></i> 序列修饰模块
    </a>

    {% if request.user.user_type in 'admin,superadmin' or request.user.is_superuser %}
    <div class="ds-nav-divider"></div>
    <div class="ds-nav-section">系统</div>
    <a href="{% url 'author_list' %}" class="ds-nav-item {% if request.resolver_match.url_name in 'author_list,add_author,edit_author' %}active{% endif %}">
      <i class="bi bi-people" style="font-size:13px;flex-shrink:0;"></i> 用户管理
    </a>
    {% endif %}
```

- [ ] **Step 2: Verify in browser**

Start dev server in worktree:
```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2/.worktrees/frontend-redesign
source venv/bin/activate 2>/dev/null || source ../venv/bin/activate
python manage.py runserver 8001
```
Open `http://localhost:8001/seq_list/`. Confirm: green logo, green sidebar active strip, icons visible in nav.

- [ ] **Step 3: Commit**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2/.worktrees/frontend-redesign
git add templates/base.html
git commit -m "feat: add Bootstrap Icons to sidebar navigation"
```

---

## Task 4: Rewrite `module_list.html`

**Files:**
- Rewrite: `.worktrees/frontend-redesign/templates/module_list.html`

- [ ] **Step 1: Replace entire file**

```html
{% extends 'base.html' %}
{% block page_title %} — Delivery 模块{% endblock %}
{% block topbar_content %}
  <span class="ds-topbar-title">Delivery 模块</span>
  {% if page_obj %}
  <span class="ds-count-badge">{{ page_obj.paginator.count }}</span>
  {% endif %}
  <span class="ds-topbar-spacer"></span>
  <a href="{% url 'upload_modules' %}" class="ds-btn ds-btn-ghost">&#8593; 批量上传</a>
  <a href="{% url 'edit_module' %}" class="ds-btn ds-btn-primary">&#43; 新增模块</a>
{% endblock %}
{% block content %}
<div class="ds-table-card">
  <div style="display:flex;align-items:center;gap:10px;padding:9px 14px;background:#fff;border-bottom:1.5px solid #e8edf4;">
    <span style="font-size:11.5px;color:#64748b;">✅ 共 {{ page_obj.paginator.count }} 条</span>
    <div style="width:1px;height:14px;background:#d1d5db;"></div>
    <span style="font-size:11.5px;color:#64748b;">💡 每个 Type Code 对应特定颜色</span>
  </div>
  <div class="ds-table-scroll">
    <table class="ds-table">
      <thead>
        <tr>
          <th style="min-width:130px;">Keyword</th>
          <th>Type Code</th>
          <th style="min-width:80px;">Strand_MWs</th>
          <th style="cursor:default;">操作</th>
        </tr>
      </thead>
      <tbody>
        {% for module in module_list %}
        <tr>
          <td><code style="background:#f1f5f9;color:#334155;padding:2px 7px;border-radius:4px;font-size:11px;font-family:'DM Mono',monospace;white-space:nowrap;">{{ module.keyword }}</code></td>
          <td><span class="type-code-pill" data-type="{{ module.type_code }}" style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;">{{ module.type_code }}</span></td>
          <td class="cell-mono-dim">{{ module.Strand_MWs|default_if_none:'—' }}</td>
          <td>
            <div class="ds-actions">
              <a href="{% url 'edit_module' %}?id={{ module.id }}" class="ds-act ds-act-edit">编辑</a>
              <form method="POST" action="{% url 'delete_module' %}" style="display:inline;" onsubmit="return confirm('确定删除该模块？');">
                {% csrf_token %}
                <input type="hidden" name="id" value="{{ module.id }}">
                <button type="submit" class="ds-act" style="border-color:#fca5a5;color:#ef4444;background:#fff;">删除</button>
              </form>
            </div>
          </td>
        </tr>
        {% empty %}
        <tr><td colspan="4" style="text-align:center;color:#94a3b8;padding:32px;">暂无模块数据</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% if page_obj.paginator.count > page_size %}
  <div class="ds-table-footer">
    <div class="ds-pagesize-wrap">
      每页显示
      <select class="ds-pagesize-select" onchange="window.location.href='?page=1&page_size='+this.value">
        <option value="10" {% if page_size == 10 %}selected{% endif %}>10</option>
        <option value="20" {% if page_size == 20 %}selected{% endif %}>20</option>
        <option value="50" {% if page_size == 50 %}selected{% endif %}>50</option>
      </select>
      条
    </div>
    <span class="ds-record-info">共 {{ page_obj.paginator.count }} 条</span>
    <div class="ds-pagination">
      {% if page_obj.has_previous %}
      <a href="?page={{ page_obj.previous_page_number }}&page_size={{ page_size }}" class="ds-pg">‹</a>
      {% endif %}
      {% for num in page_obj.paginator.page_range %}
        {% if page_obj.number == num %}
        <span class="ds-pg active">{{ num }}</span>
        {% else %}
        <a href="?page={{ num }}&page_size={{ page_size }}" class="ds-pg">{{ num }}</a>
        {% endif %}
      {% endfor %}
      {% if page_obj.has_next %}
      <a href="?page={{ page_obj.next_page_number }}&page_size={{ page_size }}" class="ds-pg">›</a>
      {% endif %}
    </div>
  </div>
  {% endif %}
</div>
{% endblock %}
{% block extra_scripts %}
<script>
(function() {
  var palette = [
    ['#dbeafe','#1d4ed8'],['#ede9fe','#6d28d9'],['#fef3c7','#92400e'],
    ['#dcfce7','#15803d'],['#fce7f3','#9d174d'],['#e0f2fe','#0369a1'],
    ['#ffedd5','#c2410c'],['#f3f4f6','#374151']
  ];
  var colorMap = {}, idx = 0;
  document.querySelectorAll('.type-code-pill').forEach(function(el) {
    var code = el.getAttribute('data-type');
    if (!colorMap[code]) { colorMap[code] = palette[idx % palette.length]; idx++; }
    el.style.background = colorMap[code][0];
    el.style.color = colorMap[code][1];
  });
})();
</script>
{% endblock %}
```

- [ ] **Step 2: Verify in browser**

Navigate to `http://localhost:8001/module_list/`. Confirm: white toolbar, `ds-table` styling, green active pagination button, no purple gradient header.

- [ ] **Step 3: Commit**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2/.worktrees/frontend-redesign
git add templates/module_list.html
git commit -m "refactor: rewrite module_list using design system classes"
```

---

## Task 5: Rewrite `seqmodule_list.html`

**Files:**
- Rewrite: `.worktrees/frontend-redesign/templates/seqmodule_list.html`

- [ ] **Step 1: Replace entire file**

```html
{% extends 'base.html' %}
{% block page_title %} — 序列修饰模块{% endblock %}
{% block topbar_content %}
  <span class="ds-topbar-title">序列修饰模块</span>
  {% if page_obj %}
  <span class="ds-count-badge">{{ page_obj.paginator.count }}</span>
  {% endif %}
  <span class="ds-topbar-spacer"></span>
  <a href="{% url 'upload_seqmodules' %}" class="ds-btn ds-btn-ghost">&#8593; 批量上传</a>
  <a href="{% url 'edit_seqmodule' %}" class="ds-btn ds-btn-primary">＋ 新增模块</a>
{% endblock %}
{% block content %}
<div class="ds-table-card">
  <div style="display:flex;align-items:center;gap:10px;padding:9px 14px;background:#fff;border-bottom:1.5px solid #e8edf4;">
    <span style="font-size:11.5px;color:#64748b;">✅ 共 {{ page_obj.paginator.count }} 条</span>
  </div>
  <div class="ds-table-scroll">
    <table class="ds-table">
      <thead>
        <tr>
          <th style="min-width:130px;">Keyword</th>
          <th>Base Char</th>
          <th style="min-width:90px;">Linker Connector</th>
          <th style="cursor:default;">操作</th>
        </tr>
      </thead>
      <tbody>
        {% for module in seqmodule_list %}
        <tr>
          <td><code style="background:#f1f5f9;color:#334155;padding:2px 7px;border-radius:4px;font-size:11px;font-family:'DM Mono',monospace;white-space:nowrap;">{{ module.keyword }}</code></td>
          <td>
            {% if module.base_char == 'A' %}
              <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;background:#dbeafe;color:#1d4ed8;">A</span>
            {% elif module.base_char == 'U' %}
              <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;background:#ffedd5;color:#c2410c;">U</span>
            {% elif module.base_char == 'G' %}
              <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;background:#dcfce7;color:#15803d;">G</span>
            {% elif module.base_char == 'C' %}
              <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;background:#fce7f3;color:#9d174d;">C</span>
            {% elif module.base_char %}
              <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;background:#f1f5f9;color:#475569;">{{ module.base_char }}</span>
            {% else %}
              <span class="cell-dim">—</span>
            {% endif %}
          </td>
          <td><code style="background:#f1f5f9;color:#334155;padding:2px 6px;border-radius:3px;font-family:'DM Mono',monospace;font-size:10.5px;white-space:nowrap;">{{ module.linker_connector|default:'—' }}</code></td>
          <td>
            <div class="ds-actions">
              <a href="{% url 'edit_seqmodule' %}?id={{ module.id }}" class="ds-act ds-act-edit">编辑</a>
              <form method="POST" action="{% url 'delete_seqmodule' %}" style="display:inline;" onsubmit="return confirm('确定删除该修饰模块？');">
                {% csrf_token %}
                <input type="hidden" name="id" value="{{ module.id }}">
                <button type="submit" class="ds-act" style="border-color:#fca5a5;color:#ef4444;background:#fff;">删除</button>
              </form>
            </div>
          </td>
        </tr>
        {% empty %}
        <tr><td colspan="4" style="text-align:center;color:#94a3b8;padding:32px;">暂无修饰模块数据</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% if page_obj.paginator.count > page_size %}
  <div class="ds-table-footer">
    <div class="ds-pagesize-wrap">
      每页显示
      <select class="ds-pagesize-select" onchange="window.location.href='?page=1&page_size='+this.value">
        <option value="10" {% if page_size == 10 %}selected{% endif %}>10</option>
        <option value="20" {% if page_size == 20 %}selected{% endif %}>20</option>
        <option value="50" {% if page_size == 50 %}selected{% endif %}>50</option>
      </select>
      条
    </div>
    <span class="ds-record-info">共 {{ page_obj.paginator.count }} 条</span>
    <div class="ds-pagination">
      {% if page_obj.has_previous %}
      <a href="?page={{ page_obj.previous_page_number }}&page_size={{ page_size }}" class="ds-pg">‹</a>
      {% endif %}
      {% for num in page_obj.paginator.page_range %}
        {% if page_obj.number == num %}
        <span class="ds-pg active">{{ num }}</span>
        {% else %}
        <a href="?page={{ num }}&page_size={{ page_size }}" class="ds-pg">{{ num }}</a>
        {% endif %}
      {% endfor %}
      {% if page_obj.has_next %}
      <a href="?page={{ page_obj.next_page_number }}&page_size={{ page_size }}" class="ds-pg">›</a>
      {% endif %}
    </div>
  </div>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 2: Verify in browser**

Navigate to `http://localhost:8001/seqmodule_list/`. Confirm: white toolbar, colored Base Char pills, consistent pagination with module_list.

- [ ] **Step 3: Commit**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2/.worktrees/frontend-redesign
git add templates/seqmodule_list.html
git commit -m "refactor: rewrite seqmodule_list using design system classes"
```

---

## Task 6: Update `seq_list.html` — Remove Old CSS

**Files:**
- Modify: `.worktrees/frontend-redesign/templates/seq_list.html`

- [ ] **Step 1: Remove old CSS link tags**

Find in `{% block extra_head %}` (lines 26–29):
```html
{% block extra_head %}
<link href="/static/vendors/datatables/dataTables.bootstrap.css" rel="stylesheet" media="screen">
<link href="/static/css/styles.css" rel="stylesheet">
{% endblock %}
```
Replace with:
```html
{% block extra_head %}{% endblock %}
```

- [ ] **Step 2: Add `ds-table` class to the DataTables table**

Find (line ~180):
```html
<table id="example" class="table table-container table-bordered" style="width:100%">
```
Replace:
```html
<table id="example" class="ds-table" style="width:100%">
```

- [ ] **Step 3: Verify in browser**

Navigate to `http://localhost:8001/seq_list/`. Confirm:
- Table uses design system font, row hover, and header styles
- DataTables pagination buttons match green active style
- No layout breakage from removed Bootstrap table classes
- Sorting arrows and column toggle still work

- [ ] **Step 4: Commit**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2/.worktrees/frontend-redesign
git add templates/seq_list.html
git commit -m "refactor: remove legacy CSS from seq_list, use ds-table class"
```

---

## Task 7: Extract BLAST Inline Styles

**Files:**
- Modify: `.worktrees/frontend-redesign/templates/blast_results.html`
- Modify: `.worktrees/frontend-redesign/templates/multi_blast_results.html`
- Modify: `.worktrees/frontend-redesign/templates/multi_blast.html`

- [ ] **Step 1: Update `blast_results.html`**

Remove the entire `{% block extra_styles %}<style>...</style>{% endblock %}` block (lines 8–40).

Then replace class names in the template body:
- `class="blast-header-card"` → `class="ds-info-card"`
- `class="naked-seq"` → `class="ds-seq-badge"`
- `class="source-badge"` → `class="ds-source-badge"`

- [ ] **Step 2: Update `multi_blast_results.html`**

Remove the `{% block extra_styles %}<style>...</style>{% endblock %}` block.

Replace class names:
- `class="result-wrapper"` → `class="ds-result-wrapper"` (add `.ds-result-wrapper { padding: 16px 0; }` to design-system.css if this class controls spacing; otherwise keep as inline style `style="padding:16px 0;"`)
- `class="result-stat-bar"` → `class="ds-result-stat-bar"`
- `class="stat-divider"` → `class="ds-stat-divider"`
- `class="stat-item"` → `class="ds-stat-item"`
- `class="not-found-alert"` → `class="ds-alert ds-alert-error"`
- `class="group-card"` → `class="ds-group-card"`
- `class="group-card group-card-ss"` → `class="ds-group-card ds-group-card-ss"`
- `class="group-card group-card-as"` → `class="ds-group-card ds-group-card-as"`

- [ ] **Step 3: Check `multi_blast.html` for any inline style blocks**

If `{% block extra_styles %}<style>` exists in `multi_blast.html`, remove it and replace any local class names with design system equivalents (same pattern as above). If no local style block exists, skip.

- [ ] **Step 4: Verify in browser**

Navigate to `http://localhost:8001/multi_blast/`, run a BLAST search, confirm result page renders correctly with `ds-info-card` styling.

- [ ] **Step 5: Commit**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2/.worktrees/frontend-redesign
git add templates/blast_results.html templates/multi_blast_results.html templates/multi_blast.html
git commit -m "refactor: extract BLAST inline styles to design system classes"
```

---

## Task 8: Add Pagination + Search to `reg_seq_list`

**Files:**
- Modify: `.worktrees/frontend-redesign/app01/views.py` (around line 2123)
- Modify: `.worktrees/frontend-redesign/templates/reg_seq_list.html`

- [ ] **Step 1: Update `reg_seq_list` view in `views.py`**

Find the `reg_seq_list` function (line 2123). Replace the entire function body up to the `return render(...)` line:

```python
def reg_seq_list(request):
    q = request.GET.get('q', '').strip()
    page_size = int(request.GET.get('page_size', 20))

    sequences = Sequence.objects.exclude(seq_type='duplex').prefetch_related('target_info')
    if q:
        sequences = sequences.filter(rm_code__icontains=q)

    sequence_list = []
    for seq in sequences:
        if seq.seq_type == 'SS':
            seq_prefix = 'SS_'
        elif seq.seq_type == 'AS':
            seq_prefix = 'AS_'
        else:
            seq_prefix = ''

        seq_info = seq.target_info.first()
        remark = seq_info.Remark if seq_info else ''
        pos = seq_info.Pos if seq_info else ''
        Transcript = seq_info.Transcript if seq_info else ''
        formatted_date = seq.created_at.strftime('%Y-%m-%d %H:%M') if seq.created_at else ''

        sequence_list.append({
            'rm_code': seq.rm_code,
            'seq_prefix': seq_prefix,
            'seq': seq.seq,
            'pos': pos,
            'transcript': Transcript,
            'remark': remark,
            'reg_date': formatted_date,
        })

    paginator = Paginator(sequence_list, page_size)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'reg_seq_list.html', {
        'sequence_list': page_obj.object_list,
        'page_obj': page_obj,
        'page_size': page_size,
        'q': q,
    })
```

- [ ] **Step 2: Update `reg_seq_list.html` topbar and add pagination footer**

Replace `{% block topbar_content %}` block:
```html
{% block topbar_content %}
  <span class="ds-topbar-title">注册序列列表</span>
  {% if page_obj %}
  <span class="ds-count-badge">{{ page_obj.paginator.count }}</span>
  {% endif %}
  <span class="ds-topbar-spacer"></span>
  <form method="get" action="" style="display:contents;">
    <div class="ds-search-wrap" style="width:180px;">
      <i class="bi bi-search ds-search-icon"></i>
      <input type="text" name="q" class="ds-search-input" placeholder="搜索 Strand ID…" value="{{ q }}">
    </div>
    {% if q %}<button type="submit" class="ds-btn ds-btn-ghost" style="height:34px;padding:0 10px;font-size:11.5px;">搜索</button>{% endif %}
    {% if q %}<a href="{% url 'reg_seq_list' %}" class="ds-btn ds-btn-ghost" style="height:34px;padding:0 10px;font-size:11.5px;">✕ 清除</a>{% endif %}
  </form>
  <a href="{% url 'register_seq' %}" class="ds-btn ds-btn-primary">&#8593; 注册新序列</a>
{% endblock %}
```

Add pagination footer inside `{% block content %}` after the `</div>` closing the `ds-table-card`, just before `{% endblock %}`:
```html
  {% if page_obj.paginator.num_pages > 1 %}
  <div class="ds-table-footer">
    <div class="ds-pagesize-wrap">
      每页显示
      <select class="ds-pagesize-select" onchange="window.location.href='?page=1&page_size='+this.value+'{% if q %}&q={{ q }}{% endif %}'">
        <option value="20" {% if page_size == 20 %}selected{% endif %}>20</option>
        <option value="50" {% if page_size == 50 %}selected{% endif %}>50</option>
        <option value="100" {% if page_size == 100 %}selected{% endif %}>100</option>
      </select>
      条
    </div>
    <span class="ds-record-info">共 {{ page_obj.paginator.count }} 条</span>
    <div class="ds-pagination">
      {% if page_obj.has_previous %}
      <a href="?page={{ page_obj.previous_page_number }}&page_size={{ page_size }}{% if q %}&q={{ q }}{% endif %}" class="ds-pg">‹</a>
      {% endif %}
      {% for num in page_obj.paginator.page_range %}
        {% if page_obj.number == num %}
        <span class="ds-pg active">{{ num }}</span>
        {% elif num == 1 or num == page_obj.paginator.num_pages or num >= page_obj.number|add:"-2" and num <= page_obj.number|add:"2" %}
        <a href="?page={{ num }}&page_size={{ page_size }}{% if q %}&q={{ q }}{% endif %}" class="ds-pg">{{ num }}</a>
        {% elif num == page_obj.number|add:"-3" or num == page_obj.number|add:"3" %}
        <span class="ds-pg" style="border:none;cursor:default;">…</span>
        {% endif %}
      {% endfor %}
      {% if page_obj.has_next %}
      <a href="?page={{ page_obj.next_page_number }}&page_size={{ page_size }}{% if q %}&q={{ q }}{% endif %}" class="ds-pg">›</a>
      {% endif %}
    </div>
  </div>
  {% endif %}
```

- [ ] **Step 3: Verify in browser**

Navigate to `http://localhost:8001/reg_seq_list/`. Confirm:
- Count badge shows total in topbar
- Pagination footer appears when records > 20
- Search input filters by `rm_code` (partial match)
- Page and search state persist across pagination clicks

- [ ] **Step 4: Commit**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2/.worktrees/frontend-redesign
git add app01/views.py templates/reg_seq_list.html
git commit -m "feat: add pagination and search to reg_seq_list"
```

---

## Self-Review

**Spec coverage:**
- [x] Green brand colors (`#16a34a`) — Tasks 1, 2
- [x] Green sidebar active indicator — Task 1
- [x] Green pagination active — Task 1
- [x] Green primary button — Task 1
- [x] Green user avatar — Task 1
- [x] DataTables CSS overrides — Task 2
- [x] BLAST component classes — Task 2
- [x] Sidebar Bootstrap Icons — Task 3
- [x] `module_list.html` uses `ds-*` classes — Task 4
- [x] `seqmodule_list.html` uses `ds-*` classes — Task 5
- [x] `seq_list.html` removes old CSS — Task 6
- [x] `blast_results.html` inline style removal — Task 7
- [x] `multi_blast_results.html` inline style removal — Task 7
- [x] `reg_seq_list` pagination in views.py — Task 8
- [x] `reg_seq_list.html` pagination footer + search — Task 8

**Placeholder scan:** No TBD, all code blocks complete.

**Type consistency:** `page_obj`, `page_size`, `q` context vars used consistently across views.py and reg_seq_list.html. `ds-pg`, `ds-table-footer`, `ds-pagesize-select` class names match design-system.css definitions.
