# Module Pages Iteration 2 — Design Specification

**Date:** 2026-04-19
**Scope:** Iterative improvements to `module_list.html`, `seqmodule_list.html` in the worktree. No changes to `edit_module.html` or `edit_seqmodule.html`.

---

## 1. Keyword 去掉黑底

Replace the current dark badge:
```html
<!-- Before -->
<code style="background:#1e293b;color:#e2e8f0;padding:2px 8px;border-radius:4px;font-size:11px;font-family:'DM Mono',monospace;">C16-NH</code>

<!-- After: light gray pill -->
<code style="background:#f1f5f9;color:#334155;padding:2px 8px;border-radius:6px;font-size:11px;font-family:'DM Mono',monospace;">C16-NH</code>
```

Applied to both `module_list.html` and `seqmodule_list.html`.

---

## 2. 默认每页 20 行 + 分页

Both `module_list` and `seqmodule_list` views currently return all records with no pagination. Add Django `Paginator` with `per_page=20`.

### View changes (`app01/views.py`)

**`module_list`** (around line 2338):
```python
from django.core.paginator import Paginator

def module_list(request):
    all_modules = DeliveryModule.objects.all().values('id', 'keyword', 'type_code', 'Strand_MWs')
    paginator = Paginator(all_modules, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'module_list.html', {
        'module_list': page_obj,
        'page_obj': page_obj,
    })
```

**`seqmodule_list`** (around line 2474):
```python
def seqmodule_list(request):
    all_modules = SeqModule.objects.all().values('id', 'keyword', 'base_char', 'linker_connector', 'description')
    paginator = Paginator(all_modules, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'seqmodule_list.html', {
        'seqmodule_list': page_obj,
        'page_obj': page_obj,
    })
```

### Template: pagination footer

Both list templates get a footer block after `</table>` using existing `ds-table-footer` / `ds-pagination` CSS classes:

```html
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
```

### Template: topbar count badge

Change from displaying total `|length` to paginator count:
```html
<!-- Before -->
<span class="ds-count-badge">{{ module_list|length }}</span>

<!-- After -->
<span class="ds-count-badge">{{ page_obj.paginator.count }}</span>
```

---

## 3. 序列修饰模块内容显示不全

Root cause: `max-width:860px` on the table card compressed column widths. Removing max-width (change #4) resolves this automatically.

Additionally, empty Description fields currently show `—` dash which adds visual noise. Change to leave blank:
```html
<!-- Before -->
{{ module.description|default:'—' }}

<!-- After -->
{{ module.description|default:'' }}
```

---

## 4. 去掉 max-width，表格撑满内容区

Remove `style="flex:none;max-width:860px;"` from both `module_list.html` and `seqmodule_list.html` table cards.

```html
<!-- Before -->
<div class="ds-table-card" style="flex:none;max-width:860px;">

<!-- After -->
<div class="ds-table-card">
```

The existing `ds-table-card` CSS (`flex:1; display:flex; flex-direction:column; min-height:0;`) naturally expands to fill the `.ds-content` area.

Edit form pages (`edit_module.html`, `edit_seqmodule.html`) keep their `max-width` on `ds-form-card` — centered form layout is correct.

---

## 5. 整体字号放大

Current design-system.css table defaults are compact (11.5px body, 10px headers). Bump up for these two module pages:

| Element | Before | After |
|---|---|---|
| Table body font | 11.5px | 13px |
| Table header (`<th>`) | 10px | 11px |
| Keyword pill | 11px | 13px |
| Type code pill | 11px | 13px |
| Linker connector tag | 10px | 12px |
| Strand_MWs | 12px | 13px |
| Description | 13px | 14px |
| Action buttons | 12px | 13px |
| Info banner | 12.5px | 13.5px |

Applied as inline styles on both `module_list.html` and `seqmodule_list.html` — no global CSS changes to avoid affecting other pages like `seq_list`.

---

## 6. Constraints

- Only `module_list.html` and `seqmodule_list.html` template changes (worktree)
- `app01/views.py`: add Paginator import and paginated queries for both views
- All Django template tags, URL names, and form field names preserved
- No model, URL, or other view changes
