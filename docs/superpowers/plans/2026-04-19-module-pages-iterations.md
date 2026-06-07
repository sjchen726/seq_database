# Module Pages Iteration 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve module list pages: keyword style, pagination, font size, and full-width layout.

**Architecture:** Template-only changes in worktree `.worktrees/frontend-redesign/` plus two minimal view changes in `app01/views.py` to add pagination. All font size changes applied as inline styles on the two list templates only.

**Tech Stack:** Django 5.1, Paginator, existing design-system.css

---

## File Map

| File | Action | Change |
|---|---|---|
| `.worktrees/frontend-redesign/templates/module_list.html` | Modify | Keyword style, remove max-width, add font bump, add pagination footer |
| `.worktrees/frontend-redesign/templates/seqmodule_list.html` | Modify | Keyword style, remove max-width, add font bump, add pagination footer, description default |
| `app01/views.py` | Modify | Add Paginator to `module_list` and `seqmodule_list` |

---

### Task 1: Add Paginator to views

**Files:**
- Modify: `app01/views.py` (lines 2338–2344 and 2474–2476)

- [ ] **Step 1: Add Paginator import and update module_list view**

Find line 2338–2344:
```python
def module_list(request):

    # 获取所有 DeliveryModule 的 keyword 和 type_code
    module_list = DeliveryModule.objects.all().values('id', 'keyword', 'type_code', 'Strand_MWs')

    # 渲染模板并传递数据
    return render(request, 'module_list.html', {'module_list': module_list})
```

Replace with:
```python
def module_list(request):
    from django.core.paginator import Paginator
    all_modules = DeliveryModule.objects.all().values('id', 'keyword', 'type_code', 'Strand_MWs')
    paginator = Paginator(all_modules, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'module_list.html', {'module_list': page_obj, 'page_obj': page_obj})
```

- [ ] **Step 2: Update seqmodule_list view**

Find line 2474–2476:
```python
def seqmodule_list(request):
    seqmodule_list = SeqModule.objects.all().values('id', 'keyword', 'base_char', 'linker_connector', 'description')
    return render(request, 'seqmodule_list.html', {'seqmodule_list': seqmodule_list})
```

Replace with:
```python
def seqmodule_list(request):
    from django.core.paginator import Paginator
    all_modules = SeqModule.objects.all().values('id', 'keyword', 'base_char', 'linker_connector', 'description')
    paginator = Paginator(all_modules, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'seqmodule_list.html', {'seqmodule_list': page_obj, 'page_obj': page_obj})
```

- [ ] **Step 3: Commit**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2
git add app01/views.py
git commit -m "feat: add pagination to module_list and seqmodule_list views (20 per page)"
```

---

### Task 2: Redesign module_list.html

**Files:**
- Modify: `.worktrees/frontend-redesign/templates/module_list.html`

- [ ] **Step 1: Rewrite module_list.html**

Replace entire file with:

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
  <div style="padding:10px 16px;font-size:13.5px;color:#64748b;background:#f8fafc;border-bottom:1px solid #e8edf4;">
    <i class="bi bi-info-circle"></i>
    每个 Type Code 对应特定显示颜色，相同 Type Code 显示相同颜色。请保持团队内统一，避免随意更改。
  </div>
  <div class="ds-table-scroll">
    <table class="ds-table" style="font-size:13px;">
      <thead>
        <tr>
          <th style="font-size:11px;">Keyword</th>
          <th style="font-size:11px;">Type Code</th>
          <th style="font-size:11px;">Strand_MWs</th>
          <th style="font-size:11px;">操作</th>
        </tr>
      </thead>
      <tbody>
        {% for module in module_list %}
        <tr>
          <td>
            <code style="background:#f1f5f9;color:#334155;padding:3px 10px;border-radius:6px;font-size:13px;font-family:'DM Mono',monospace;">{{ module.keyword }}</code>
          </td>
          <td>
            <span class="type-code-pill" data-type="{{ module.type_code }}" style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:13px;font-weight:500;">{{ module.type_code }}</span>
          </td>
          <td style="font-family:'DM Mono',monospace;color:#94a3b8;font-size:13px;">
            {{ module.Strand_MWs|default_if_none:'' }}
          </td>
          <td>
            <div class="ds-actions">
              <a href="{% url 'edit_module' %}?id={{ module.id }}" class="ds-btn ds-btn-ghost" style="padding:3px 10px;font-size:13px;">编辑</a>
              <form method="POST" action="{% url 'delete_module' %}" style="display:inline;" onsubmit="return confirm('确定删除该模块？');">
                {% csrf_token %}
                <input type="hidden" name="id" value="{{ module.id }}">
                <button type="submit" class="ds-btn" style="padding:3px 10px;font-size:13px;color:#ef4444;border:1px solid #fca5a5;background:none;cursor:pointer;border-radius:6px;">删除</button>
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
  {% if page_obj.paginator.num_pages > 1 %}
  <div class="ds-table-footer">
    <span class="ds-record-info">第 {{ page_obj.start_index }}–{{ page_obj.end_index }} 条，共 {{ page_obj.paginator.count }} 条</span>
    <div class="ds-pagination">
      {% if page_obj.has_previous %}
      <a href="?page={{ page_obj.previous_page_number }}" class="ds-pg">‹</a>
      {% endif %}
      {% for num in page_obj.paginator.page_range %}
        {% if page_obj.number == num %}
        <span class="ds-pg active">{{ num }}</span>
        {% else %}
        <a href="?page={{ num }}" class="ds-pg">{{ num }}</a>
        {% endif %}
      {% endfor %}
      {% if page_obj.has_next %}
      <a href="?page={{ page_obj.next_page_number }}" class="ds-pg">›</a>
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

Navigate to `/module_list/`. Confirm:
- Keyword shows as light gray pill, not dark badge
- Table fills content area width (no max-width constraint)
- Font sizes are visibly larger (13px body, 13px pills)
- Pagination footer appears at bottom if >20 records
- Strand_MWs shows blank instead of dash when null

- [ ] **Step 3: Commit**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2/.worktrees/frontend-redesign
git add templates/module_list.html
git commit -m "feat: redesign module_list with gray keyword pills, larger fonts, full width, pagination"
```

---

### Task 3: Redesign seqmodule_list.html

**Files:**
- Modify: `.worktrees/frontend-redesign/templates/seqmodule_list.html`

- [ ] **Step 1: Rewrite seqmodule_list.html**

Replace entire file with:

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
  <div class="ds-table-scroll">
    <table class="ds-table" style="font-size:13px;">
      <thead>
        <tr>
          <th style="font-size:11px;">Keyword</th>
          <th style="font-size:11px;">Base Char</th>
          <th style="font-size:11px;">Linker Connector</th>
          <th style="font-size:11px;">Description</th>
          <th style="font-size:11px;">操作</th>
        </tr>
      </thead>
      <tbody>
        {% for module in seqmodule_list %}
        <tr>
          <td>
            <code style="background:#f1f5f9;color:#334155;padding:3px 10px;border-radius:6px;font-size:13px;font-family:'DM Mono',monospace;">{{ module.keyword }}</code>
          </td>
          <td>
            {% if module.base_char == 'A' %}
              <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:13px;font-weight:500;background:#dbeafe;color:#1d4ed8;">A</span>
            {% elif module.base_char == 'U' %}
              <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:13px;font-weight:500;background:#ffedd5;color:#c2410c;">U</span>
            {% elif module.base_char == 'G' %}
              <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:13px;font-weight:500;background:#dcfce7;color:#15803d;">G</span>
            {% elif module.base_char == 'C' %}
              <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:13px;font-weight:500;background:#fce7f3;color:#9d174d;">C</span>
            {% elif module.base_char %}
              <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:13px;font-weight:500;background:#f1f5f9;color:#475569;">{{ module.base_char }}</span>
            {% else %}
              <span style="color:#94a3b8;">—</span>
            {% endif %}
          </td>
          <td>
            <code style="background:#f1f5f9;color:#334155;padding:1px 6px;border-radius:3px;font-family:'DM Mono',monospace;font-size:12px;">{{ module.linker_connector|default:'' }}</code>
          </td>
          <td style="color:#64748b;font-size:14px;">
            {{ module.description|default:'' }}
          </td>
          <td>
            <div class="ds-actions">
              <a href="{% url 'edit_seqmodule' %}?id={{ module.id }}" class="ds-btn ds-btn-ghost" style="padding:3px 10px;font-size:13px;">编辑</a>
              <form method="POST" action="{% url 'delete_seqmodule' %}" style="display:inline;" onsubmit="return confirm('确定删除该修饰模块？');">
                {% csrf_token %}
                <input type="hidden" name="id" value="{{ module.id }}">
                <button type="submit" class="ds-btn" style="padding:3px 10px;font-size:13px;color:#ef4444;border:1px solid #fca5a5;background:none;cursor:pointer;border-radius:6px;">删除</button>
              </form>
            </div>
          </td>
        </tr>
        {% empty %}
        <tr><td colspan="5" style="text-align:center;color:#94a3b8;padding:32px;">暂无修饰模块数据</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% if page_obj.paginator.num_pages > 1 %}
  <div class="ds-table-footer">
    <span class="ds-record-info">第 {{ page_obj.start_index }}–{{ page_obj.end_index }} 条，共 {{ page_obj.paginator.count }} 条</span>
    <div class="ds-pagination">
      {% if page_obj.has_previous %}
      <a href="?page={{ page_obj.previous_page_number }}" class="ds-pg">‹</a>
      {% endif %}
      {% for num in page_obj.paginator.page_range %}
        {% if page_obj.number == num %}
        <span class="ds-pg active">{{ num }}</span>
        {% else %}
        <a href="?page={{ num }}" class="ds-pg">{{ num }}</a>
        {% endif %}
      {% endfor %}
      {% if page_obj.has_next %}
      <a href="?page={{ page_obj.next_page_number }}" class="ds-pg">›</a>
      {% endif %}
    </div>
  </div>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 2: Verify in browser**

Navigate to `/seqmodule_list/`. Confirm:
- Keyword shows as light gray pill
- Table fills content area width
- All columns fully visible (no truncation)
- Font sizes are larger
- Description shows blank instead of dash when empty
- Pagination footer appears if >20 records

- [ ] **Step 3: Commit**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2/.worktrees/frontend-redesign
git add templates/seqmodule_list.html
git commit -m "feat: redesign seqmodule_list with gray keyword pills, larger fonts, full width, pagination"
```
