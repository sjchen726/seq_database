# Module List Redesign v2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign `module_list.html` and `seqmodule_list.html` with Direction A style: card + toolbar, sortable headers, centered content, blue edit buttons, page-number footer.

**Architecture:** Two templates rewritten with exact HTML/CSS per spec. Views unchanged (pagination already in place from previous iteration).

**Tech Stack:** Django 5.1 templates, vanilla CSS/JS, existing `ds-*` CSS classes.

---

## File Map

| File | Action |
|---|---|
| `.worktrees/frontend-redesign/templates/module_list.html` | Rewrite |
| `.worktrees/frontend-redesign/templates/seqmodule_list.html` | Rewrite |

---

### Task 1: Rewrite `module_list.html`

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
  <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:#fff;border-bottom:2px solid #e8edf4;">
    <span style="font-size:12px;color:#64748b;">✅ 共 {{ page_obj.paginator.count }} 条</span>
    <div style="width:1px;height:16px;background:#d1d5db;"></div>
    <span style="font-size:12px;color:#64748b;">💡 每个 Type Code 对应特定颜色</span>
  </div>
  <div class="ds-table-scroll">
    <table class="ds-table">
      <thead>
        <tr>
          <th style="min-width:130px;">Keyword <span style="display:inline-flex;flex-direction:column;gap:2px;margin-left:6px;opacity:0.3;vertical-align:middle;"><span style="width:0;height:0;border-left:3px solid transparent;border-right:3px solid transparent;border-bottom:4px solid currentColor;display:block;"></span><span style="width:0;height:0;border-left:3px solid transparent;border-right:3px solid transparent;border-top:4px solid currentColor;display:block;"></span></span></th>
          <th>Type Code <span style="display:inline-flex;flex-direction:column;gap:2px;margin-left:6px;opacity:0.3;vertical-align:middle;"><span style="width:0;height:0;border-left:3px solid transparent;border-right:3px solid transparent;border-bottom:4px solid currentColor;display:block;"></span><span style="width:0;height:0;border-left:3px solid transparent;border-right:3px solid transparent;border-top:4px solid currentColor;display:block;"></span></span></th>
          <th style="min-width:80px;">Strand_MWs <span style="display:inline-flex;flex-direction:column;gap:2px;margin-left:6px;opacity:0.3;vertical-align:middle;"><span style="width:0;height:0;border-left:3px solid transparent;border-right:3px solid transparent;border-bottom:4px solid currentColor;display:block;"></span><span style="width:0;height:0;border-left:3px solid transparent;border-right:3px solid transparent;border-top:4px solid currentColor;display:block;"></span></span></th>
          <th style="text-align:left;">操作</th>
        </tr>
      </thead>
      <tbody>
        {% for module in module_list %}
        <tr>
          <td>
            <code style="background:#f1f5f9;color:#334155;padding:3px 8px;border-radius:4px;font-size:12px;font-family:'DM Mono',monospace;white-space:nowrap;">{{ module.keyword }}</code>
          </td>
          <td>
            <span class="type-code-pill" data-type="{{ module.type_code }}" style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;">{{ module.type_code }}</span>
          </td>
          <td style="color:#94a3b8;font-family:'DM Mono',monospace;font-size:13px;text-align:center;">
            {{ module.Strand_MWs|default_if_none:'—' }}
          </td>
          <td style="text-align:center;">
            <div style="display:flex;gap:4px;justify-content:center;">
              <a href="{% url 'edit_module' %}?id={{ module.id }}" class="ds-act-edit" style="padding:3px 9px;border-radius:5px;font-size:11px;font-weight:500;border:1px solid #bfdbfe;background:#eff6ff;color:#1d4ed8;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;">编辑</a>
              <form method="POST" action="{% url 'delete_module' %}" style="display:inline;" onsubmit="return confirm('确定删除该模块？');">
                {% csrf_token %}
                <input type="hidden" name="id" value="{{ module.id }}">
                <button type="submit" class="ds-act-delete" style="padding:3px 9px;border-radius:5px;font-size:11px;font-weight:500;border:1px solid #fca5a5;color:#ef4444;background:#fff;cursor:pointer;display:inline-flex;align-items:center;">删除</button>
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
  <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:#fff;border-top:2px solid #e8edf4;">
    <div style="display:flex;align-items:center;gap:8px;font-size:12px;color:#475569;">
      每页显示
      <select id="page-size-select" onchange="window.location.href='?page=1&page_size='+this.value" style="appearance:none;background:#f8fafc url(&quot;data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='5'%3E%3Cpath d='M0 0l4 5 4-5z' fill='%2394a3b8'/%3E%3C/svg%3E&quot;) no-repeat right 8px center;border:1px solid #e2e8f0;border-radius:6px;padding:4px 24px 4px 9px;font-size:12px;font-family:'DM Mono',monospace;color:#334155;cursor:pointer;outline:none;">
        <option value="10" {% if page_size == 10 %}selected{% endif %}>10</option>
        <option value="20" {% if page_size == 20 %}selected{% endif %}>20</option>
        <option value="50" {% if page_size == 50 %}selected{% endif %}>50</option>
      </select>
      条，共 {{ page_obj.paginator.count }} 条
    </div>
    <div style="display:flex;align-items:center;gap:4px;">
      {% if page_obj.has_previous %}
      <a href="?page={{ page_obj.previous_page_number }}&page_size={{ page_size }}" style="min-width:30px;height:30px;border-radius:6px;border:1px solid #e2e8f0;background:#fff;color:#334155;font-size:16px;font-weight:300;letter-spacing:-2px;display:flex;align-items:center;justify-content:center;text-decoration:none;">‹</a>
      {% endif %}
      {% for num in page_obj.paginator.page_range %}
        {% if page_obj.number == num %}
        <a style="min-width:30px;height:30px;border-radius:6px;border:1px solid transparent;background:linear-gradient(135deg,#38bdf8,#6366f1);color:#fff;font-size:13px;font-weight:600;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 6px rgba(99,102,241,0.3);">{{ num }}</a>
        {% else %}
        <a href="?page={{ num }}&page_size={{ page_size }}" style="min-width:30px;height:30px;border-radius:6px;border:1px solid #e2e8f0;background:#fff;color:#334155;font-size:13px;font-weight:500;display:flex;align-items:center;justify-content:center;text-decoration:none;">{{ num }}</a>
        {% endif %}
      {% endfor %}
      {% if page_obj.has_next %}
      <a href="?page={{ page_obj.next_page_number }}&page_size={{ page_size }}" style="min-width:30px;height:30px;border-radius:6px;border:1px solid #e2e8f0;background:#fff;color:#334155;font-size:16px;font-weight:300;letter-spacing:-2px;display:flex;align-items:center;justify-content:center;text-decoration:none;">›</a>
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

Navigate to `/module_list/` on worktree dev server. Confirm all elements match spec.

- [ ] **Step 3: Commit**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2/.worktrees/frontend-redesign
git add templates/module_list.html
git commit -m "feat: redesign module_list with card toolbar and centered content"
```

---

### Task 2: Rewrite `seqmodule_list.html`

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
  <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:#fff;border-bottom:2px solid #e8edf4;">
    <span style="font-size:12px;color:#64748b;">✅ 共 {{ page_obj.paginator.count }} 条</span>
    <div style="width:1px;height:16px;background:#d1d5db;"></div>
    <a href="{% url 'upload_seqmodules' %}" class="ds-btn ds-btn-ghost" style="height:28px;padding:0 10px;font-size:11px;">↑ 批量上传</a>
  </div>
  <div class="ds-table-scroll">
    <table class="ds-table">
      <thead>
        <tr>
          <th style="min-width:130px;">Keyword <span style="display:inline-flex;flex-direction:column;gap:2px;margin-left:6px;opacity:0.3;vertical-align:middle;"><span style="width:0;height:0;border-left:3px solid transparent;border-right:3px solid transparent;border-bottom:4px solid currentColor;display:block;"></span><span style="width:0;height:0;border-left:3px solid transparent;border-right:3px solid transparent;border-top:4px solid currentColor;display:block;"></span></span></th>
          <th>Base Char <span style="display:inline-flex;flex-direction:column;gap:2px;margin-left:6px;opacity:0.3;vertical-align:middle;"><span style="width:0;height:0;border-left:3px solid transparent;border-right:3px solid transparent;border-bottom:4px solid currentColor;display:block;"></span><span style="width:0;height:0;border-left:3px solid transparent;border-right:3px solid transparent;border-top:4px solid currentColor;display:block;"></span></span></th>
          <th style="min-width:70px;">Linker Connector <span style="display:inline-flex;flex-direction:column;gap:2px;margin-left:6px;opacity:0.3;vertical-align:middle;"><span style="width:0;height:0;border-left:3px solid transparent;border-right:3px solid transparent;border-bottom:4px solid currentColor;display:block;"></span><span style="width:0;height:0;border-left:3px solid transparent;border-right:3px solid transparent;border-top:4px solid currentColor;display:block;"></span></span></th>
          <th style="text-align:left;">操作</th>
        </tr>
      </thead>
      <tbody>
        {% for module in seqmodule_list %}
        <tr>
          <td>
            <code style="background:#f1f5f9;color:#334155;padding:3px 8px;border-radius:4px;font-size:12px;font-family:'DM Mono',monospace;white-space:nowrap;">{{ module.keyword }}</code>
          </td>
          <td style="text-align:center;">
            {% if module.base_char == 'A' %}
              <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;background:#dbeafe;color:#1d4ed8;">A</span>
            {% elif module.base_char == 'U' %}
              <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;background:#ffedd5;color:#c2410c;">U</span>
            {% elif module.base_char == 'G' %}
              <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;background:#dcfce7;color:#15803d;">G</span>
            {% elif module.base_char == 'C' %}
              <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;background:#fce7f3;color:#9d174d;">C</span>
            {% elif module.base_char %}
              <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;background:#f1f5f9;color:#475569;">{{ module.base_char }}</span>
            {% else %}
              <span style="color:#94a3b8;">—</span>
            {% endif %}
          </td>
          <td>
            <code style="background:#f1f5f9;color:#334155;padding:2px 6px;border-radius:3px;font-family:'DM Mono',monospace;font-size:11px;white-space:nowrap;">{{ module.linker_connector|default:'—' }}</code>
          </td>
          <td style="text-align:center;">
            <div style="display:flex;gap:4px;justify-content:center;">
              <a href="{% url 'edit_seqmodule' %}?id={{ module.id }}" class="ds-act-edit" style="padding:3px 9px;border-radius:5px;font-size:11px;font-weight:500;border:1px solid #bfdbfe;background:#eff6ff;color:#1d4ed8;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;">编辑</a>
              <form method="POST" action="{% url 'delete_seqmodule' %}" style="display:inline;" onsubmit="return confirm('确定删除该修饰模块？');">
                {% csrf_token %}
                <input type="hidden" name="id" value="{{ module.id }}">
                <button type="submit" class="ds-act-delete" style="padding:3px 9px;border-radius:5px;font-size:11px;font-weight:500;border:1px solid #fca5a5;color:#ef4444;background:#fff;cursor:pointer;display:inline-flex;align-items:center;">删除</button>
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
  <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:#fff;border-top:2px solid #e8edf4;">
    <div style="display:flex;align-items:center;gap:8px;font-size:12px;color:#475569;">
      每页显示
      <select id="page-size-select" onchange="window.location.href='?page=1&page_size='+this.value" style="appearance:none;background:#f8fafc url(&quot;data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='5'%3E%3Cpath d='M0 0l4 5 4-5z' fill='%2394a3b8'/%3E%3C/svg%3E&quot;) no-repeat right 8px center;border:1px solid #e2e8f0;border-radius:6px;padding:4px 24px 4px 9px;font-size:12px;font-family:'DM Mono',monospace;color:#334155;cursor:pointer;outline:none;">
        <option value="10" {% if page_size == 10 %}selected{% endif %}>10</option>
        <option value="20" {% if page_size == 20 %}selected{% endif %}>20</option>
        <option value="50" {% if page_size == 50 %}selected{% endif %}>50</option>
      </select>
      条，共 {{ page_obj.paginator.count }} 条
    </div>
    <div style="display:flex;align-items:center;gap:4px;">
      {% if page_obj.has_previous %}
      <a href="?page={{ page_obj.previous_page_number }}&page_size={{ page_size }}" style="min-width:30px;height:30px;border-radius:6px;border:1px solid #e2e8f0;background:#fff;color:#334155;font-size:16px;font-weight:300;letter-spacing:-2px;display:flex;align-items:center;justify-content:center;text-decoration:none;">‹</a>
      {% endif %}
      {% for num in page_obj.paginator.page_range %}
        {% if page_obj.number == num %}
        <a style="min-width:30px;height:30px;border-radius:6px;border:1px solid transparent;background:linear-gradient(135deg,#38bdf8,#6366f1);color:#fff;font-size:13px;font-weight:600;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 6px rgba(99,102,241,0.3);">{{ num }}</a>
        {% else %}
        <a href="?page={{ num }}&page_size={{ page_size }}" style="min-width:30px;height:30px;border-radius:6px;border:1px solid #e2e8f0;background:#fff;color:#334155;font-size:13px;font-weight:500;display:flex;align-items:center;justify-content:center;text-decoration:none;">{{ num }}</a>
        {% endif %}
      {% endfor %}
      {% if page_obj.has_next %}
      <a href="?page={{ page_obj.next_page_number }}&page_size={{ page_size }}" style="min-width:30px;height:30px;border-radius:6px;border:1px solid #e2e8f0;background:#fff;color:#334155;font-size:16px;font-weight:300;letter-spacing:-2px;display:flex;align-items:center;justify-content:center;text-decoration:none;">›</a>
      {% endif %}
    </div>
  </div>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 2: Verify in browser**

Navigate to `/seqmodule_list/` on worktree dev server. Confirm all elements match spec.

- [ ] **Step 3: Commit**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2/.worktrees/frontend-redesign
git add templates/seqmodule_list.html
git commit -m "feat: redesign seqmodule_list with card toolbar and centered content"
```
