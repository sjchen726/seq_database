# AS/SS 双链对齐修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 seq_list 页面中 AS/SS 双链 modify_seq 列的 token 对齐问题，使每个碱基位置在 AS 和 SS 行之间垂直对齐。

**Architecture:** 将 AS 和 SS 行的 modify_seq 列合并为一个 `<td rowspan="2">`，内含嵌套 table，每列对应同一碱基位置。使用已有的 `modify_seq_colored` 数据（views.py:1819 已计算），不改动 views.py。

**Tech Stack:** Django 5.1 模板、HTML table、已有 CSS 类（`.nested-align-table` 等在 styles.css:1198 已定义）

---

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `templates/seq_list.html` | 修改 | 替换 modify_seq 列渲染（AS 行 td + SS 行 td → rowspan=2 嵌套 table） |
| `app01/views.py` | 修改 | 删除 `build_aligned_tokens()` 函数及其调用（line 300-318, 1820） |

---

### Task 1: 删除 views.py 中的 build_aligned_tokens

**Files:**
- Modify: `app01/views.py:300-318`（删除函数定义）
- Modify: `app01/views.py:1820`（删除 aligned_tokens 计算）

- [ ] **Step 1: 删除 build_aligned_tokens 函数定义**

在 `app01/views.py` 中，删除第 300-318 行的整个函数：

```python
# 删除这段（300-318行）：
def build_aligned_tokens(token_list):
    """
    把 get_modify_seq_colored() 的输出转成对齐单元列表。
    每个单元 = 一个碱基 + 该碱基前面紧跟的 linker（s/o/ss）。
    linker 不占独立对齐列，附属在下一个碱基上。
    """
    LINKERS = {'s', 'o', 'ss'}
    units = []
    pending_linkers = []
    for token in token_list:
        if token['char'] in LINKERS:
            pending_linkers.append(token)
        else:
            units.append({'nuc': token, 'pre_linkers': pending_linkers})
            pending_linkers = []
    if pending_linkers and units:
        units[-1]['post_linkers'] = pending_linkers
    return units
```

- [ ] **Step 2: 删除 aligned_tokens 计算行**

在 `app01/views.py:1820`，删除这一行：

```python
# 删除这行（1820行）：
'aligned_tokens': build_aligned_tokens(get_modify_seq_colored(linker_seq, selected_seq_type, seq_type_authoritative, dm_modules=dm_modules, color_map=color_map)) if linker_seq and selected_seq_type else [],
```

- [ ] **Step 3: 启动服务器确认无报错**

```bash
source venv/bin/activate && python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Commit**

```bash
git add app01/views.py
git commit -m "refactor: remove build_aligned_tokens, unused after template rewrite"
```

---

### Task 2: 改造 seq_list.html 的 modify_seq 列

**Files:**
- Modify: `templates/seq_list.html:242-283`（AS 行 modify_seq td）
- Modify: `templates/seq_list.html:361-399`（SS 行 modify_seq td）

目标结构：把两个独立 `<td>` 替换为一个 `<td rowspan="2">` 内含嵌套 table。

**AS 行（items.0）**：seq-count 在 token 上方，1→N
**SS 行（items.1）**：seq-count 在 token 下方，N→1

- [ ] **Step 1: 替换 AS 行的 modify_seq `<td>`**

找到 `seq_list.html` 中 AS 行的 modify_seq td（约第 242-283 行），整段替换为：

```html
<td rowspan="2" style="padding:4px 2px;vertical-align:middle;">
  <table class="nested-align-table">
    <tr>
      <td class="align-dir-cell">{% if selected_seq_type == 'SS' %}AS 5'{% else %}AS 3'{% endif %}</td>
      {% for item in group.items.0.modify_seq_colored %}
        {% if item.char == 's' or item.char == 'o' or item.char == 'ss' %}
          <td style="vertical-align:bottom;padding:0;">
            <div style="display:flex;flex-direction:column;align-items:center;">
              <span class="seq-count" style="width:auto;">&nbsp;</span>
              <span class="seq-delivery-placeholder">&nbsp;</span>
              <span class="seq-container seq-narrow" style="background-color:{% if item.char == 's' %}rgb(253,246,61){% elif item.char == 'o' %}rgb(198,196,198){% else %}rgb(198,196,198){% endif %};">{{ item.char }}</span>
            </div>
          </td>
        {% else %}
          <td style="vertical-align:bottom;padding:0;">
            <div style="display:flex;flex-direction:column;align-items:center;">
              <span class="seq-count" style="width:auto;">{% if item.count %} {{ item.count }} {% else %}&nbsp;{% endif %}</span>
              {% if item.is_combo %}<span class="seq-delivery-label" style="background-color:{{ item.delivery_color }};">{{ item.delivery_label }}</span>{% else %}<span class="seq-delivery-placeholder">&nbsp;</span>{% endif %}
              <span class="seq-container seq-wide" style="background-color:
                {% if item.type == 'normal' %}rgb(189,199,248);
                {% elif item.type == 'f' %}rgb(22,245,22);
                {% elif item.type == 'm' %}rgb(68,68,68);color:white;
                {% elif item.type == 'd' %}rgb(212,93,245);
                {% elif item.type == 's' %}rgb(253,246,61);
                {% elif item.type == 'o' %}rgb(198,196,198);
                {% elif item.type == 'ss' %}rgb(212,93,245);
                {% elif item.type == 'moe' %}rgb(212,93,245);
                {% elif item.type == 'OCF3' %}rgb(212,93,245);
                {% elif item.type == 'GNA' %}rgb(212,93,245);
                {% elif item.type == 'TNA' %}rgb(245,86,86);color:white;
                {% elif item.type == 'I' %}rgb(212,93,245);
                {% elif item.type == 'unknown' %}rgb(163,163,163);
                {% elif item.type == 'others' %}rgba(112,203,248,1);
                {% endif %};">{{ item.char }}</span>
            </div>
          </td>
        {% endif %}
      {% endfor %}
      <td class="align-dir-cell">{% if selected_seq_type == 'SS' %}3'{% else %}5'{% endif %}</td>
    </tr>
    <tr class="ss-align-row">
      <td class="align-dir-cell">{% if selected_seq_type == 'SS' %}SS 3'{% else %}SS 5'{% endif %}</td>
      {% for item in group.items.1.modify_seq_colored %}
        {% if item.char == 's' or item.char == 'o' or item.char == 'ss' %}
          <td style="vertical-align:top;padding:0;">
            <div style="display:flex;flex-direction:column;align-items:center;">
              <span class="seq-container seq-narrow" style="background-color:{% if item.char == 's' %}rgb(253,246,61){% elif item.char == 'o' %}rgb(198,196,198){% else %}rgb(198,196,198){% endif %};">{{ item.char }}</span>
              <span class="seq-delivery-placeholder">&nbsp;</span>
              <span class="seq-count" style="width:auto;">&nbsp;</span>
            </div>
          </td>
        {% else %}
          <td style="vertical-align:top;padding:0;">
            <div style="display:flex;flex-direction:column;align-items:center;">
              {% if item.is_combo %}<span class="seq-delivery-label" style="background-color:{{ item.delivery_color }};">{{ item.delivery_label }}</span>{% else %}<span class="seq-delivery-placeholder">&nbsp;</span>{% endif %}
              <span class="seq-container seq-wide" style="background-color:
                {% if item.type == 'normal' %}rgb(189,199,248);
                {% elif item.type == 'f' %}rgb(22,245,22);
                {% elif item.type == 'm' %}rgb(68,68,68);color:white;
                {% elif item.type == 'd' %}rgb(212,93,245);
                {% elif item.type == 's' %}rgb(253,246,61);
                {% elif item.type == 'o' %}rgb(198,196,198);
                {% elif item.type == 'ss' %}rgb(212,93,245);
                {% elif item.type == 'moe' %}rgb(212,93,245);
                {% elif item.type == 'OCF3' %}rgb(212,93,245);
                {% elif item.type == 'GNA' %}rgb(212,93,245);
                {% elif item.type == 'TNA' %}rgb(245,86,86);color:white;
                {% elif item.type == 'I' %}rgb(212,93,245);
                {% elif item.type == 'unknown' %}rgb(163,163,163);
                {% elif item.type == 'others' %}rgba(112,203,248,1);
                {% endif %};">{{ item.char }}</span>
              <span class="seq-count" style="width:auto;">{% if item.count %} {{ item.count }} {% else %}&nbsp;{% endif %}</span>
            </div>
          </td>
        {% endif %}
      {% endfor %}
      <td class="align-dir-cell">{% if selected_seq_type == 'SS' %}5'{% else %}3'{% endif %}</td>
    </tr>
  </table>
</td>
```

- [ ] **Step 2: 删除 SS 行的 modify_seq `<td>`**

找到 SS 行（`group.items.1`）的 modify_seq td（约第 361-399 行），整段删除（因为已经合并进 rowspan=2 的 td 里了）。

- [ ] **Step 3: 处理单链序列（无 SS 的情况）**

当 `group.items.1` 不存在时（单链序列），rowspan=2 的 td 会导致表格错乱。需要在 AS 行的 td 上加条件判断：

将 Task 2 Step 1 中的 `<td rowspan="2"` 改为：

```html
<td {% if group.items.1 %}rowspan="2"{% endif %} style="padding:4px 2px;vertical-align:middle;">
```

同时，嵌套 table 的 SS 行也要加条件：

```html
{% if group.items.1 %}
<tr class="ss-align-row">
  ...SS 行内容...
</tr>
{% endif %}
```

- [ ] **Step 4: 启动开发服务器手动验证**

```bash
source venv/bin/activate && python manage.py runserver
```

打开浏览器访问 `http://127.0.0.1:8000/seq_list/`，检查：
1. 双链序列（duplex）的 AS/SS token 是否垂直对齐
2. 单链序列是否正常显示（无表格错乱）
3. AS 视图和 SS 视图切换后对齐是否正确
4. 方向标签（AS 5' / 3'，SS 3' / 5'）是否显示正确
5. seq-count 编号：AS 行在 token 上方，SS 行在 token 下方

- [ ] **Step 5: Commit**

```bash
git add templates/seq_list.html
git commit -m "feat: align AS/SS tokens via rowspan=2 nested table in seq_list"
```

---

### Task 3: 清理 CSS 中的废弃类

**Files:**
- Modify: `static/css/styles.css:1231-1247`（删除 seq-align-unit/linker/nuc 类，这些是旧 flex 方案的产物）

- [ ] **Step 1: 确认这些类不再被任何模板使用**

```bash
grep -r "seq-align-unit\|seq-align-linker\|seq-align-nuc" templates/
```

Expected: 无输出（Task 2 完成后这些类应已从模板中消失）

- [ ] **Step 2: 删除废弃 CSS 类**

在 `static/css/styles.css` 中删除以下三个类（约 1231-1247 行）：

```css
/* 删除这段 */
.seq-align-unit {
    display: inline-flex;
    align-items: stretch;
    gap: 0;
}
.seq-align-linker {
    display: flex;
    flex-direction: column;
    align-items: center;
}
.seq-align-nuc {
    display: flex;
    flex-direction: column;
    align-items: center;
    min-width: 26px;
}
```

- [ ] **Step 3: Commit**

```bash
git add static/css/styles.css
git commit -m "chore: remove unused seq-align-unit/linker/nuc CSS classes"
```
