# segment_sep 垂直对齐修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复双段序列展示中，SS row 的 segment_sep 单元格（linker token 如 LK1-L96-LK1）与两侧序列 token 底部不对齐的问题。

**Architecture:** 在 `_seq_group_row.html` 的 SS row segment_sep `<td>` 上加 `vertical-align:bottom`，与两侧正常列保持一致；同时移除 inner div 上无效的 `height:100%` 和 `align-items:flex-end`。

**Tech Stack:** Django template (HTML)

---

### Task 1: 修复 SS row segment_sep 垂直对齐

**Files:**
- Modify: `templates/_seq_group_row.html:65-66`

- [ ] **Step 1: 确认当前代码**

打开 `templates/_seq_group_row.html`，定位到第 64–70 行，确认内容如下：

```html
{% if col.col_type == 'segment_sep' %}
  <td class="seq-segment-sep-col">
    <div style="display:flex;flex-direction:row;flex-wrap:nowrap;align-items:flex-end;gap:0;height:100%;">
      {% for lk in col.linker_tokens %}
        <span class="seq-container seq-wide" style="background-color:rgba(112,203,248,1);">{{ lk.char }}</span>
      {% endfor %}
    </div>
  </td>
```

- [ ] **Step 2: 应用修改**

将上述代码替换为：

```html
{% if col.col_type == 'segment_sep' %}
  <td class="seq-segment-sep-col" style="vertical-align:bottom;">
    <div style="display:flex;flex-direction:row;flex-wrap:nowrap;gap:0;">
      {% for lk in col.linker_tokens %}
        <span class="seq-container seq-wide" style="background-color:rgba(112,203,248,1);">{{ lk.char }}</span>
      {% endfor %}
    </div>
  </td>
```

变化：
- `<td>` 加 `style="vertical-align:bottom;"`
- inner div 删除 `align-items:flex-end;` 和 `height:100%;`

- [ ] **Step 3: 启动开发服务器并目视验证**

```bash
source venv/bin/activate
python manage.py runserver
```

在浏览器中打开序列列表页面，找到 BP000016（双段序列）。

预期效果：
- SS row：LK1、L96、LK1 等 linker token 底部与两侧碱基字符（如 Um）的底线对齐，不再悬空于中部
- AS row：空白 spacer 保持顶部对齐，不变

- [ ] **Step 4: Commit**

```bash
git add templates/_seq_group_row.html
git commit -m "fix: bottom-align segment_sep linker tokens in SS row"
```
