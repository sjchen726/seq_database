---
name: as-ss-alignment
description: Design spec for AS/SS double-strand token-level alignment in seq_list view
metadata:
  type: project
---

# AS/SS 双链对齐 — 设计规范

## 背景

当前 `seq_list` 页面中，AS 和 SS 链各自独立渲染 `modify_seq`，每个 token 宽度由其文字内容决定（如 `T(MOE)` 比 `A` 宽得多），导致对应碱基位置在视觉上错位，无法直观判断配对关系。

## 目标

在 AS 视图（5'→3'）和 SS 视图（3'→5'）下，让 AS 与 SS 的每个碱基位置在同一列对齐，同时：
- 不改变其他列（Strand ID、Sequence ID、Project、Target、Ligand 1/2 等）的任何展示形式
- 不改变 `modify_seq` 的数据内容或复制行为
- 支持 s/o 链间 linker（各占独立窄列）
- 支持化学 linker（如 LK1-L96-LK1）：AS 行显示虚线占位，SS 行显示彩色 block

## 编号规则

与当前项目保持一致，随 `selected_seq_type` 变化：

| 视图 | AS 编号 | SS 编号 |
|------|---------|---------|
| AS 视图（默认） | 1→N，显示在 token 上方 | N→1，显示在 token 下方 |
| SS 视图 | N→1，显示在 token 上方 | 1→N，显示在 token 下方 |

## 实现方案

### 核心变更：`modify_seq` 列改为 rowspan=2 + 嵌套 table

**仅修改** `templates/seq_list.html` 中 `modify_seq` 那一列（第 6 列）的渲染方式。

**改动前**（AS 和 SS 各自一个 `<td>`）：
```html
<!-- AS 行 -->
<td><div style="display:flex;">...AS tokens...</div></td>
<!-- SS 行 -->
<td><div style="display:flex;">...SS tokens...</div></td>
```

**改动后**（合并为一个 `rowspan="2"` 的 `<td>`，内含嵌套 table）：
```html
<td rowspan="2" style="padding:4px 2px;vertical-align:middle;">
  <table class="nested-align-table">
    <tr><!-- AS 行：seq-count 在上，token 在下 -->
      <td class="dir-cell">AS 5'</td>
      {% for item in group.items.0.modify_seq_colored %}
        {% if item.type == 'chem_linker' %}
          <td><div class="chem-linker-cell">
            <span class="seq-count">&nbsp;</span>
            <span class="chem-linker-placeholder"></span>
          </div></td>
        {% elif item.char == 's' or item.char == 'o' %}
          <td><div class="linker-cell">
            <span class="seq-count">&nbsp;</span>
            <span class="linker-span ...">{{ item.char }}</span>
          </div></td>
        {% else %}
          <td><div class="token-cell">
            <span class="seq-count">{{ item.count|default:"&nbsp;" }}</span>
            {% if item.is_combo %}<span class="combo-label">{{ item.delivery_label }}</span>{% endif %}
            <span class="seq-container ...">{{ item.char }}</span>
          </div></td>
        {% endif %}
      {% endfor %}
      <td class="dir-cell">3'</td>
    </tr>
    <tr><!-- SS 行：token 在上，seq-count 在下 -->
      <td class="dir-cell">SS 3'</td>
      {% for item in group.items.1.modify_seq_colored %}
        ...（同上，seq-count 在 token 下方）
      {% endfor %}
      <td class="dir-cell">5'</td>
    </tr>
  </table>
</td>
```

### 方向标签与编号

AS 视图（`selected_seq_type == 'SS'` 时为默认视图）：
- AS 行：`AS 5'` … `3'`，seq-count 在 token **上方**，1→N
- SS 行：`SS 3'` … `5'`，seq-count 在 token **下方**，N→1

SS 视图（`selected_seq_type == 'AS'`）：
- SS 行：`SS 5'` … `3'`，seq-count 在 token **上方**，1→N
- AS 行：`AS 3'` … `5'`，seq-count 在 token **下方**，N→1

编号逻辑已由 `get_modify_seq_colored()` 中的 `counter` 处理，模板只需按 `item.count` 渲染即可，无需改动 views.py。

### CSS 新增

在项目现有样式基础上新增以下类（不修改已有类）：

```css
.nested-align-table { border-collapse: collapse; }
.nested-align-table td { padding: 0; text-align: center; vertical-align: bottom; }
.nested-align-table .ss-align-row td { vertical-align: top; }
.align-dir-cell { font-size: 10px; color: #aaa; padding: 0 4px; white-space: nowrap; vertical-align: middle; }
.chem-linker-cell { display: flex; flex-direction: column; align-items: center; min-width: 64px; }
.chem-linker-placeholder { display: block; border-top: 2px dashed #ccc; width: 80%; height: 13px; margin-top: 2px; }
.chem-linker-blocks { display: flex; gap: 1px; }
```

### 不改动的内容

- `views.py`：`get_modify_seq_colored()`、`build_duplex_groups()`、`get_sequence_info()` 均不修改
- `seq_list.html`：除 modify_seq 列（第 6 列）外，其余所有列（Strand ID、Sequence ID、Project、Target、Ligand 1/2、Transcript、Position 等）的 `<td>` 结构和内容完全不变
- `char_block_AS.html`、`char_block_SS.html`：不修改（delivery 列继续使用）
- `data-modify-seq` 属性：保留在原位，复制行为不受影响

## 边界情况

| 情况 | 处理方式 |
|------|---------|
| 单链序列（无配对 SS/AS） | 不适用对齐，保持原有单行渲染 |
| 哑铃型（含化学 linker） | AS 行显示虚线占位格，SS 行显示彩色 block；两侧碱基列正常对齐 |
| s/o 链间 linker | 各占独立窄列，AS/SS 行同列对齐 |
| combo token（碱基 + delivery label） | delivery label 显示在 token 上方（AS 行）或下方（SS 行），不影响列宽对齐 |

## 涉及文件

| 文件 | 改动类型 |
|------|---------|
| `templates/seq_list.html` | 修改 modify_seq 列渲染（约 60 行替换） |
| `static/` 下的 CSS 文件（待确认具体文件名） | 新增 6 个 CSS 类 |
