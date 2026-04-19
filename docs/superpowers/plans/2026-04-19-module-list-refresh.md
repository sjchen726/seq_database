# Module List Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refresh `module_list.html` and `seqmodule_list.html` with three fixes: no-card layout, keyword column width, and per-page size selector (10/20/50, default 20). Also remove description column from seqmodule_list and add pagination to both views.

**Architecture:** Two Django views get pagination logic added; two templates get card wrappers removed, column widths set, and footers replaced with pagesize selectors. URL params: `page_size` and `page`.

**Tech Stack:** Django 5.1 templates, vanilla JS, existing `ds-*` CSS classes, `Paginator` from Django core.

---

## File Map

| File | Action | Change |
|---|---|---|
| `.worktrees/frontend-redesign/app01/views.py` | Modify | Add pagination to `module_list` and `seqmodule_list` views; remove `description` from seqmodule_list queryset |
| `.worktrees/frontend-redesign/templates/module_list.html` | Modify | Remove card, add pagesize footer, set column min-widths |
| `.worktrees/frontend-redesign/templates/seqmodule_list.html` | Modify | Remove card, remove description column, add pagesize footer, set column min-widths |

---

### Task 1: Add pagination to `module_list` view

**Files:**
- Modify: `.worktrees/frontend-redesign/app01/views.py:2338-2344`

- [ ] **Step 1: Rewrite `module_list` view**

Replace lines 2338–2344 with:

```python
from django.core.paginator import Paginator

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

- [ ] **Step 2: Verify import exists**

Confirm `from django.core.paginator import Paginator` is already present in the file. If not, add it.

- [ ] **Step 3: Commit**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2
git add .worktrees/frontend-redesign/app01/views.py
git commit -m "feat: add pagination to module_list view with page_size param"
```

---

### Task 2: Add pagination to `seqmodule_list` view + remove description

**Files:**
- Modify: `.worktrees/frontend-redesign/app01/views.py:2474-2476`

- [ ] **Step 1: Rewrite `seqmodule_list` view**

Replace lines 2474–2476 with:

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

- [ ] **Step 2: Commit**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2
git add .worktrees/frontend-redesign/app01/views.py
git commit -m "feat: add pagination to seqmodule_list view, remove description field"
```

---

### Task 3: Rewrite `module_list.html`

**Files:**
- Modify: `.worktrees/frontend-redesign/templates/module_list.html`

**Changes:**
1. Remove `ds-table-card` wrapper — table and info bar stand alone
2. Keyword cell: `min-width: 120px; white-space: nowrap`
3. Linker Connector cell: `min-width: 60px` (narrower)
4. Strand_MWs cell: `min-width: 80px`
5. Remove `min-width: 1080px` from `ds-table`
6. Replace pagination footer with pagesize selector (show only when total > page_size)
7. Footer left: "每页显示 [10|20|50 ▼] 条" + total count; Footer right: prev/next arrows

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
<div style="padding:10px 16px;font-size:12.5px;color:#64748b;background:#fff;border:1px solid #e8edf4;border-radius:10px;margin-bottom:2px;">
  <i class="bi bi-info-circle"></i>
  每个 Type Code 对应特定显示颜色，相同 Type Code 显示相同颜色。请保持团队内统一，避免随意更改。
</div>
<div class="ds-table-scroll">
  <table class="ds-table">
    <thead>
      <tr>
        <th style="min-width:120px;">Keyword</th>
        <th>Type Code</th>
        <th style="min-width:80px;">Strand_MWs</th>
        <th>操作</th>
      </tr>
    </thead>
    <tbody>
      {% for module in module_list %}
      <tr>
        <td>
          <code style="background:#f1f5f9;color:#334155;padding:2px 8px;border-radius:4px;font-size:11px;font-family:'DM Mono',monospace;white-space:nowrap;">{{ module.keyword }}</code>
        </td>
        <td>
          <span class="type-code-pill" data-type="{{ module.type_code }}" style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:500;">{{ module.type_code }}</span>
        </td>
        <td style="font-family:'DM Mono',monospace;color:#94a3b8;font-size:12px;white-space:nowrap;">
          {{ module.Strand_MWs|default_if_none:'—' }}
        </td>
        <td>
          <div class="ds-actions">
            <a href="{% url 'edit_module' %}?id={{ module.id }}" class="ds-btn ds-btn-ghost" style="padding:3px 10px;font-size:12px;">编辑</a>
            <form method="POST" action="{% url 'delete_module' %}" style="display:inline;" onsubmit="return confirm('确定删除该模块？');">
              {% csrf_token %}
              <input type="hidden" name="id" value="{{ module.id }}">
              <button type="submit" class="ds-btn" style="padding:3px 10px;font-size:12px;color:#ef4444;border:1px solid #fca5a5;background:none;cursor:pointer;border-radius:6px;">删除</button>
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
<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:#fff;border:1px solid #e8edf4;border-top:none;border-radius:0 0 10px 10px;">
  <div style="display:flex;align-items:center;gap:8px;font-size:12px;color:#64748b;">
    每页显示
    <select id="page-size-select" onchange="window.location.href='?page=1&page_size='+this.value" style="appearance:none;background:#f8fafc url(&quot;data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='5'%3E%3Cpath d='M0 0l4 5 4-5z' fill='%2394a3b8'/%3E%3C/svg%3E&quot;) no-repeat right 8px center;border:1px solid #e2e8f0;border-radius:6px;padding:4px 24px 4px 9px;font-size:12px;font-family:'DM Mono',monospace;color:#334155;cursor:pointer;outline:none;">
      <option value="10" {% if page_size == 10 %}selected{% endif %}>10</option>
      <option value="20" {% if page_size == 20 %}selected{% endif %}>20</option>
      <option value="50" {% if page_size == 50 %}selected{% endif %}>50</option>
    </select>
    条，共 {{ page_obj.paginator.count }} 条
  </div>
  <div style="display:flex;gap:4px;">
    {% if page_obj.has_previous %}
    <a href="?page={{ page_obj.previous_page_number }}&page_size={{ page_size }}" class="ds-btn ds-btn-ghost" style="padding:4px 10px;font-size:12px;">‹ 上一页</a>
    {% endif %}
    {% if page_obj.has_next %}
    <a href="?page={{ page_obj.next_page_number }}&page_size={{ page_size }}" class="ds-btn ds-btn-ghost" style="padding:4px 10px;font-size:12px;">下一页 ›</a>
    {% endif %}
  </div>
</div>
{% endif %}
{% endblock %}
{% block extra_scripts %}
<script>
(function() {
  var palette = [
    ['#dbeafe', '#1d4ed8'],
    ['#ede9fe', '#6d28d9'],
    ['#fef3c7', '#92400e'],
    ['#dcfce7', '#15803d'],
    ['#fce7f3', '#9d174d'],
    ['#e0f2fe', '#0369a1'],
    ['#ffedd5', '#c2410c'],
    ['#f3f4f6', '#374151']
  ];
  var colorMap = {};
  var idx = 0;
  document.querySelectorAll('.type-code-pill').forEach(function(el) {
    var code = el.getAttribute('data-type');
    if (!colorMap[code]) {
      colorMap[code] = palette[idx % palette.length];
      idx++;
    }
    el.style.background = colorMap[code][0];
    el.style.color = colorMap[code][1];
  });
})();
</script>
{% endblock %}
```

- [ ] **Step 2: Verify in browser**

Navigate to `/module_list/` on worktree dev server. Confirm:
- No card wrapper — table info bar and table are direct in content area
- Keyword never wraps (long keywords stay on one line with horizontal scroll if needed)
- Strand_MWs column is narrow
- Footer shows only when total > page_size
- Pagesize selector works (change to 10, 50, back to 20)
- Prev/next navigation works

- [ ] **Step 3: Commit**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2/.worktrees/frontend-redesign
git add templates/module_list.html
git commit -m "feat: refresh module_list - no card, column widths, pagesize footer"
```

---

### Task 4: Rewrite `seqmodule_list.html`

**Files:**
- Modify: `.worktrees/frontend-redesign/templates/seqmodule_list.html`

**Changes:**
1. Remove `ds-table-card` wrapper
2. Remove Description column entirely (header + data + empty colspan)
3. Keyword: `min-width: 120px; white-space: nowrap`
4. Base Char: colored pill
5. Linker Connector: `min-width: 60px`
6. Remove `min-width: 1080px` from `ds-table`
7. Pagesize footer (same pattern as module_list)
8. Empty state: `colspan="4"`, no Description

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
<div class="ds-table-scroll">
  <table class="ds-table">
    <thead>
      <tr>
        <th style="min-width:120px;">Keyword</th>
        <th>Base Char</th>
        <th style="min-width:60px;">Linker Connector</th>
        <th>操作</th>
      </tr>
    </thead>
    <tbody>
      {% for module in seqmodule_list %}
      <tr>
        <td>
          <code style="background:#f1f5f9;color:#334155;padding:2px 8px;border-radius:4px;font-size:11px;font-family:'DM Mono',monospace;white-space:nowrap;">{{ module.keyword }}</code>
        </td>
        <td>
          {% if module.base_char == 'A' %}
            <span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:500;background:#dbeafe;color:#1d4ed8;">A</span>
          {% elif module.base_char == 'U' %}
            <span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:500;background:#ffedd5;color:#c2410c;">U</span>
          {% elif module.base_char == 'G' %}
            <span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:500;background:#dcfce7;color:#15803d;">G</span>
          {% elif module.base_char == 'C' %}
            <span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:500;background:#fce7f3;color:#9d174d;">C</span>
          {% elif module.base_char %}
            <span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:500;background:#f1f5f9;color:#475569;">{{ module.base_char }}</span>
          {% else %}
            <span style="color:#94a3b8;">—</span>
          {% endif %}
        </td>
        <td>
          <code style="background:#f1f5f9;color:#334155;padding:1px 6px;border-radius:3px;font-family:'DM Mono',monospace;font-size:10px;white-space:nowrap;">{{ module.linker_connector|default:'—' }}</code>
        </td>
        <td>
          <div class="ds-actions">
            <a href="{% url 'edit_seqmodule' %}?id={{ module.id }}" class="ds-btn ds-btn-ghost" style="padding:3px 10px;font-size:12px;">编辑</a>
            <form method="POST" action="{% url 'delete_seqmodule' %}" style="display:inline;" onsubmit="return confirm('确定删除该修饰模块？');">
              {% csrf_token %}
              <input type="hidden" name="id" value="{{ module.id }}">
              <button type="submit" class="ds-btn" style="padding:3px 10px;font-size:12px;color:#ef4444;border:1px solid #fca5a5;background:none;cursor:pointer;border-radius:6px;">删除</button>
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
<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:#fff;border:1px solid #e8edf4;border-top:none;border-radius:0 0 10px 10px;">
  <div style="display:flex;align-items:center;gap:8px;font-size:12px;color:#64748b;">
    每页显示
    <select id="page-size-select" onchange="window.location.href='?page=1&page_size='+this.value" style="appearance:none;background:#f8fafc url(&quot;data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='5'%3E%3Cpath d='M0 0l4 5 4-5z' fill='%2394a3b8'/%3E%3C/svg%3E&quot;) no-repeat right 8px center;border:1px solid #e2e8f0;border-radius:6px;padding:4px 24px 4px 9px;font-size:12px;font-family:'DM Mono',monospace;color:#334155;cursor:pointer;outline:none;">
      <option value="10" {% if page_size == 10 %}selected{% endif %}>10</option>
      <option value="20" {% if page_size == 20 %}selected{% endif %}>20</option>
      <option value="50" {% if page_size == 50 %}selected{% endif %}>50</option>
    </select>
    条，共 {{ page_obj.paginator.count }} 条
  </div>
  <div style="display:flex;gap:4px;">
    {% if page_obj.has_previous %}
    <a href="?page={{ page_obj.previous_page_number }}&page_size={{ page_size }}" class="ds-btn ds-btn-ghost" style="padding:4px 10px;font-size:12px;">‹ 上一页</a>
    {% endif %}
    {% if page_obj.has_next %}
    <a href="?page={{ page_obj.next_page_number }}&page_size={{ page_size }}" class="ds-btn ds-btn-ghost" style="padding:4px 10px;font-size:12px;">下一页 ›</a>
    {% endif %}
  </div>
</div>
{% endif %}
{% endblock %}
```

- [ ] **Step 2: Verify in browser**

Navigate to `/seqmodule_list/` on worktree dev server. Confirm:
- No card wrapper
- No Description column
- Keyword never wraps
- Linker Connector column is narrow
- Footer shows only when total > page_size
- Pagesize selector works
- Prev/next navigation works

- [ ] **Step 3: Commit**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2/.worktrees/frontend-redesign
git add templates/seqmodule_list.html
git commit -m "feat: refresh seqmodule_list - no card, remove description, pagesize footer"
```
