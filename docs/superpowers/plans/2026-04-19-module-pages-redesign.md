# Module Pages Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign `module_list.html`, `edit_module.html`, `seqmodule_list.html`, and `edit_seqmodule.html` in the worktree with colored pills, monospace badges, and full-field edit forms; plus two minimal view fixes required to expose all model fields.

**Architecture:** Template-only redesign in the git worktree at `.worktrees/frontend-redesign/`. Two minimal 1-line view changes are required: (1) `seqmodule_list` view only queries `values('id','keyword','base_char')` — must add `linker_connector` and `description`; (2) `edit_seqmodule` view POST handler doesn't read/save `description` — must add it. These are data-access changes only; no business logic, URLs, or models change.

**Tech Stack:** Django 5.1 templates, inline CSS (no new CSS classes), vanilla JS (type_code color assignment), existing design-system CSS classes (`ds-table-card`, `ds-table`, `ds-btn`, `ds-btn-primary`, `ds-btn-ghost`, `ds-actions`)

---

## File Map

| File | Action | Change |
|---|---|---|
| `.worktrees/frontend-redesign/templates/module_list.html` | Modify | Full redesign |
| `.worktrees/frontend-redesign/templates/edit_module.html` | Modify | Full redesign |
| `.worktrees/frontend-redesign/templates/seqmodule_list.html` | Modify | Full redesign |
| `.worktrees/frontend-redesign/templates/edit_seqmodule.html` | Modify | Full redesign |
| `app01/views.py` | Modify (2 lines) | Add `linker_connector`, `description` to `seqmodule_list` queryset; add `description` to `edit_seqmodule` POST handler |

---

### Task 1: Redesign `module_list.html`

**Files:**
- Modify: `.worktrees/frontend-redesign/templates/module_list.html`

**Spec reference:** Section 1 of `docs/superpowers/specs/2026-04-19-module-pages-redesign.md`

Context variables from `views.py`:
- `module_list` — queryset of `DeliveryModule` with fields `id`, `keyword`, `type_code`, `Strand_MWs`

- [ ] **Step 1: Rewrite `module_list.html`**

Replace the entire file content with:

```html
{% extends 'base.html' %}
{% block page_title %} — Delivery 模块{% endblock %}
{% block topbar_content %}
  <span class="ds-topbar-title">Delivery 模块</span>
  {% if module_list %}
  <span class="ds-count-badge">{{ module_list|length }}</span>
  {% endif %}
  <span class="ds-topbar-spacer"></span>
  <a href="{% url 'upload_modules' %}" class="ds-btn ds-btn-ghost">&#8593; 批量上传</a>
  <a href="{% url 'edit_module' %}" class="ds-btn ds-btn-primary">&#43; 新增模块</a>
{% endblock %}
{% block content %}
<div class="ds-table-card" style="flex:none;max-width:860px;">
  <div style="padding:10px 16px;font-size:12.5px;color:#64748b;background:#f8fafc;border-bottom:1px solid #e8edf4;">
    <i class="bi bi-info-circle"></i>
    每个 Type Code 对应特定显示颜色，相同 Type Code 显示相同颜色。请保持团队内统一，避免随意更改。
  </div>
  <div class="ds-table-scroll">
    <table class="ds-table">
      <thead>
        <tr>
          <th>Keyword</th>
          <th>Type Code</th>
          <th>Strand_MWs</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        {% for module in module_list %}
        <tr>
          <td>
            <code style="background:#1e293b;color:#e2e8f0;padding:2px 8px;border-radius:4px;font-size:11px;font-family:'DM Mono',monospace;">{{ module.keyword }}</code>
          </td>
          <td>
            <span class="type-code-pill" data-type="{{ module.type_code }}" style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:500;">{{ module.type_code }}</span>
          </td>
          <td style="font-family:'DM Mono',monospace;color:#94a3b8;font-size:12px;">
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

Navigate to `/module_list/` on the worktree dev server (port 8001). Confirm:
- Keyword shows as dark monospace badge
- Type Code shows as colored pill (same type_code = same color)
- Strand_MWs shows in muted DM Mono or `—` if null
- 编辑 and 删除 are text buttons (not icon buttons)
- Info banner still present at top

- [ ] **Step 3: Commit**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2/.worktrees/frontend-redesign
git add templates/module_list.html
git commit -m "feat: redesign module_list with colored pills and monospace badges"
```

---

### Task 2: Redesign `edit_module.html`

**Files:**
- Modify: `.worktrees/frontend-redesign/templates/edit_module.html`

**Spec reference:** Section 2 of the spec.

Context variables from `views.py`:
- `module` — a `DeliveryModule` instance when editing, `None` when creating
- `form_data` — dict `{'keyword', 'type_code', 'Strand_MWs'}` only present after a duplicate-keyword validation error

POST fields read by view: `keyword`, `type_code`, `Strand_MWs`  
Hidden field for edit mode: `id`

- [ ] **Step 1: Rewrite `edit_module.html`**

Replace entire file content with:

```html
{% extends 'base.html' %}
{% block page_title %} — {% if module %}编辑模块{% else %}新增模块{% endif %}{% endblock %}
{% block topbar_content %}
  <span class="ds-topbar-title">{% if module %}编辑模块{% else %}新增模块{% endif %}</span>
{% endblock %}
{% block content %}
<div class="ds-form-card" style="max-width:560px;">
  <form method="POST" action="{% url 'edit_module' %}">
    {% csrf_token %}
    {% if module %}
    <input type="hidden" name="id" value="{{ module.id }}">
    {% endif %}

    <div class="ds-form-group">
      <label class="ds-label">Keyword <span style="color:#ef4444;">*</span></label>
      <input type="text" name="keyword" class="ds-input" required
        value="{{ form_data.keyword|default:module.keyword|default:'' }}"
        placeholder="例：C16-NH">
    </div>

    <div class="ds-form-group">
      <label class="ds-label">Type Code <span style="color:#ef4444;">*</span></label>
      <input type="text" name="type_code" class="ds-input" required
        value="{{ form_data.type_code|default:module.type_code|default:'' }}"
        placeholder="例：Lipid">
    </div>

    <div class="ds-form-group">
      <label class="ds-label">Strand_MWs</label>
      <input type="text" name="Strand_MWs" class="ds-input"
        value="{{ form_data.Strand_MWs|default:module.Strand_MWs|default:'' }}"
        placeholder="（选填）分子量">
    </div>

    <div style="display:flex;gap:8px;margin-top:24px;">
      <button type="submit" class="ds-btn ds-btn-primary">保存</button>
      <a href="{% url 'module_list' %}" class="ds-btn ds-btn-ghost">取消</a>
    </div>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 2: Verify in browser**

Navigate to `/edit_module/` (new) and `/edit_module/?id=<some-id>` (edit). Confirm:
- Card form renders with correct max-width
- Edit mode pre-fills all three fields
- Required fields marked with red asterisk
- Submit redirects to module_list on success
- Cancel returns to module_list

- [ ] **Step 3: Commit**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2/.worktrees/frontend-redesign
git add templates/edit_module.html
git commit -m "feat: redesign edit_module as card form with all fields"
```

---

### Task 3: Fix `seqmodule_list` view + redesign `seqmodule_list.html`

**Files:**
- Modify: `app01/views.py` (1 line change)
- Modify: `.worktrees/frontend-redesign/templates/seqmodule_list.html`

**Why view change is needed:** The current view calls `.values('id', 'keyword', 'base_char')` which excludes `linker_connector` and `description`. Without these fields in the queryset dict, the template cannot access them. This is a data-access fix, not a business logic change.

- [ ] **Step 1: Fix `seqmodule_list` view in `app01/views.py`**

Find this line (around line 2475):
```python
seqmodule_list = SeqModule.objects.all().values('id', 'keyword', 'base_char')
```

Replace with:
```python
seqmodule_list = SeqModule.objects.all().values('id', 'keyword', 'base_char', 'linker_connector', 'description')
```

- [ ] **Step 2: Rewrite `seqmodule_list.html`**

Replace entire file content with:

```html
{% extends 'base.html' %}
{% block page_title %} — 序列修饰模块{% endblock %}
{% block topbar_content %}
  <span class="ds-topbar-title">序列修饰模块</span>
  {% if seqmodule_list %}
  <span class="ds-count-badge">{{ seqmodule_list|length }}</span>
  {% endif %}
  <span class="ds-topbar-spacer"></span>
  <a href="{% url 'upload_seqmodules' %}" class="ds-btn ds-btn-ghost">&#8593; 批量上传</a>
  <a href="{% url 'edit_seqmodule' %}" class="ds-btn ds-btn-primary">＋ 新增模块</a>
{% endblock %}
{% block content %}
<div class="ds-table-card" style="flex:none;max-width:860px;">
  <div class="ds-table-scroll">
    <table class="ds-table">
      <thead>
        <tr>
          <th>Keyword</th>
          <th>Base Char</th>
          <th>Linker Connector</th>
          <th>Description</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        {% for module in seqmodule_list %}
        <tr>
          <td>
            <code style="background:#1e293b;color:#e2e8f0;padding:2px 8px;border-radius:4px;font-size:11px;font-family:'DM Mono',monospace;">{{ module.keyword }}</code>
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
            <code style="background:#f1f5f9;color:#334155;padding:1px 6px;border-radius:3px;font-family:'DM Mono',monospace;font-size:10px;">{{ module.linker_connector|default:'—' }}</code>
          </td>
          <td style="color:#64748b;font-size:13px;">
            {{ module.description|default:'—' }}
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
        <tr><td colspan="5" style="text-align:center;color:#94a3b8;padding:32px;">暂无修饰模块数据</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Verify in browser**

Navigate to `/seqmodule_list/`. Confirm:
- Keyword shows as dark monospace badge
- Base Char shows as color-coded pill (A=blue, U=orange, G=green, C=pink, other=gray, empty=dash)
- Linker Connector shows as small monospace code tag
- Description shows as plain text or dash if empty
- 编辑 and 删除 are text buttons

- [ ] **Step 4: Commit**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2
git add app01/views.py
cd .worktrees/frontend-redesign
git add templates/seqmodule_list.html
git commit -m "feat: add linker_connector/description to seqmodule_list view and redesign template"
```

Note: Since the worktree and main repo share the same git index, run `git add` for `app01/views.py` from the main repo root, then `git add` for the template from the worktree. Both go into the same commit on the worktree branch.

---

### Task 4: Fix `edit_seqmodule` view + redesign `edit_seqmodule.html`

**Files:**
- Modify: `app01/views.py` (2 line additions in POST handler)
- Modify: `.worktrees/frontend-redesign/templates/edit_seqmodule.html`

**Why view change is needed:** The `edit_seqmodule` POST handler reads `keyword`, `base_char`, and `linker_connector` but not `description`. Without reading and saving it, the description textarea in the form would be silently ignored.

Context variables from view:
- `module` — a `SeqModule` instance when editing (has `keyword`, `base_char`, `linker_connector`, `description`), `None` when creating
- `form_data` — dict with `keyword`, `base_char`, `linker_connector` (on validation error); after fix will also have `description`

- [ ] **Step 1: Add `description` handling to `edit_seqmodule` view**

In `app01/views.py`, find the `edit_seqmodule` POST handler (around line 2492). The section reads:

```python
    if request.method == 'POST':
        keyword = request.POST.get('keyword', '').strip()
        base_char = request.POST.get('base_char', '').strip()
        linker_connector = request.POST.get('linker_connector', 'o').strip() or 'o'

        if module is None:
            if SeqModule.objects.filter(keyword=keyword).exists():
                messages.warning(request, f'修饰模块"{keyword}"已存在，请勿重复添加。')
                return render(request, 'edit_seqmodule.html', {
                    'module': None,
                    'form_data': {'keyword': keyword, 'base_char': base_char, 'linker_connector': linker_connector},
                })
            SeqModule.objects.create(keyword=keyword, base_char=base_char or None, linker_connector=linker_connector)
            return redirect('/seqmodule_list/')
        else:
            if keyword != module.keyword and SeqModule.objects.filter(keyword=keyword).exists():
                messages.warning(request, f'修饰模块"{keyword}"已存在，请换一个名称。')
                return render(request, 'edit_seqmodule.html', {
                    'module': module,
                    'form_data': {'keyword': keyword, 'base_char': base_char, 'linker_connector': linker_connector},
                })
            module.keyword = keyword
            module.base_char = base_char or None
            module.linker_connector = linker_connector
            module.save()
            return redirect('/seqmodule_list/')
```

Replace with (adds `description` in 5 places):

```python
    if request.method == 'POST':
        keyword = request.POST.get('keyword', '').strip()
        base_char = request.POST.get('base_char', '').strip()
        linker_connector = request.POST.get('linker_connector', 'o').strip() or 'o'
        description = request.POST.get('description', '').strip()

        if module is None:
            if SeqModule.objects.filter(keyword=keyword).exists():
                messages.warning(request, f'修饰模块"{keyword}"已存在，请勿重复添加。')
                return render(request, 'edit_seqmodule.html', {
                    'module': None,
                    'form_data': {'keyword': keyword, 'base_char': base_char, 'linker_connector': linker_connector, 'description': description},
                })
            SeqModule.objects.create(keyword=keyword, base_char=base_char or None, linker_connector=linker_connector, description=description or None)
            return redirect('/seqmodule_list/')
        else:
            if keyword != module.keyword and SeqModule.objects.filter(keyword=keyword).exists():
                messages.warning(request, f'修饰模块"{keyword}"已存在，请换一个名称。')
                return render(request, 'edit_seqmodule.html', {
                    'module': module,
                    'form_data': {'keyword': keyword, 'base_char': base_char, 'linker_connector': linker_connector, 'description': description},
                })
            module.keyword = keyword
            module.base_char = base_char or None
            module.linker_connector = linker_connector
            module.description = description or None
            module.save()
            return redirect('/seqmodule_list/')
```

- [ ] **Step 2: Rewrite `edit_seqmodule.html`**

Replace entire file content with:

```html
{% extends 'base.html' %}
{% block page_title %} — {% if module %}编辑修饰模块{% else %}新增修饰模块{% endif %}{% endblock %}
{% block topbar_content %}
  <span class="ds-topbar-title">{% if module %}编辑修饰模块{% else %}新增修饰模块{% endif %}</span>
{% endblock %}
{% block content %}
<div class="ds-form-card" style="max-width:600px;">
  <form method="POST" action="{% url 'edit_seqmodule' %}">
    {% csrf_token %}
    {% if module %}
    <input type="hidden" name="id" value="{{ module.id }}">
    {% endif %}

    <div class="ds-form-group">
      <label class="ds-label">Keyword <span style="color:#ef4444;">*</span></label>
      <input type="text" name="keyword" class="ds-input" required
        value="{{ form_data.keyword|default:module.keyword|default:'' }}"
        placeholder="例：VP25A">
    </div>

    <div class="ds-form-group">
      <label class="ds-label">Base Char</label>
      <input type="text" name="base_char" class="ds-input"
        value="{{ form_data.base_char|default:module.base_char|default:'' }}"
        placeholder="A / U / G / C / INVAB（留空表示连接符）">
    </div>

    <div class="ds-form-group">
      <label class="ds-label">Linker Connector</label>
      <input type="text" name="linker_connector" class="ds-input"
        value="{{ form_data.linker_connector|default:module.linker_connector|default:'o' }}"
        placeholder="o">
    </div>

    <div class="ds-form-group">
      <label class="ds-label">Description</label>
      <textarea name="description" class="ds-input" rows="3"
        placeholder="（选填）模块说明">{{ form_data.description|default:module.description|default:'' }}</textarea>
    </div>

    <div style="display:flex;gap:8px;margin-top:24px;">
      <button type="submit" class="ds-btn ds-btn-primary">保存</button>
      <a href="{% url 'seqmodule_list' %}" class="ds-btn ds-btn-ghost">取消</a>
    </div>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 3: Verify in browser**

Navigate to `/edit_seqmodule/` (new) and `/edit_seqmodule/?id=<some-id>` (edit). Confirm:
- All four fields render correctly
- Edit mode pre-fills all fields including description
- Saving and returning to list shows updated description in the list
- Cancel returns to seqmodule_list

- [ ] **Step 4: Commit**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2
git add app01/views.py
cd .worktrees/frontend-redesign
git add templates/edit_seqmodule.html
git commit -m "feat: add description field to edit_seqmodule view and redesign template"
```
