# seq_list 展示页面全面美化 — 设计文档 2026-05-24

## 背景与问题

seq_list 展示页面存在多处对齐与样式问题，影响核酸序列数据的可读性。  
问题分三类：结构性（HTML 布局缺陷）、CSS 历史遗留冲突、视觉一致性不足。

---

## 问题清单

### 🔴 结构性问题

**① LIGAND 列与 SEQUENCES 列垂直对齐失效**

当前外层表有 3 个独立 `td`（Ligand 1 / Sequences / Ligand 2）。Ligand td 内是两个堆叠的 `div`（SS div + AS div）；Sequences td 内是一张 2 行嵌套表（SS 行 + AS 行）。三列各自独立，没有共享高度机制，SS/AS 分界线位置无法同步。  
表现：BP000013 的 AS 链 Ligand "Vp" 与 AS 序列行错位。

**② segment_sep（LK1-L96-LK1）linker token 偏高**

`segment_sep` td 内只有 token flex 行，缺少顶部 `seq-count` 占位层。相邻序列列有 `seq-count`（高度锚点）+ `seq-container` 的两层结构；segment_sep 缺少顶层，视觉上 token 显得偏高、悬浮。

**③ `char_block_AS.html` flex 定位逻辑错误**

AS Ligand 块使用 `justify-content: flex-end` + delivery-item 在前、hidden-count 在后，intent 是让 token 微抬，但效果依赖容器高度，实际行为不可预测。

**④ 单链（无 duplex）序列走 fallback div**

当 `group.aligned_columns` 为空时，SEQUENCES 列退回到无计数、无方向标签的简单 `<div>` 布局，与双链显示风格不统一。

### 🟡 CSS / 样式问题

**⑤ `delivery-item` 残留旧 CSS 规则**  
旧规则（line ~1113）：`display: inline-block; vertical-align: middle; min-width: max-content`。新 design-system 规则未显式覆盖 `display`、`vertical-align`、`min-width`，导致层叠混乱。

**⑥ Ligand token 无 `min-width`，宽度与 seq-container 不一致**  
`seq-container` 有 `min-width: 22px`，`delivery-item` 无此约束，单字符 Ligand token 宽度偏小。

**⑦ seq-count 的 `line-height` 两处定义冲突**  
- `.nested-align-table .seq-count`：`line-height: 1.3`（无 `!important`）  
- 全局 `.seq-count`：`line-height: 1.4 !important`（覆盖前者）  
嵌套表内意图使用 1.3（更紧凑），实际得到 1.4。

### 🟢 视觉一致性

**⑧ 列切换（Ligand 1 / Ligand 2）依赖 DataTables column 索引**  
合并三列后，原有 `table.column(5/7).visible()` 方案失效，需改为 CSS class 切换。

**⑨ 空 AS 行占高度**  
单链行的 AS 行（空）仍渲染并占据垂直空间，显示一行多余空白。

**⑩ segment_sep AS 行无高度锚点**  
AS 行的 segment_sep 是空白等宽 td，无下方 seq-count 垫片，AS 两段序列的对齐分界线缺乏视觉引导。

---

## 设计方案

### 核心架构：统一嵌套表（Unified Strand Table）

**废除三独立 td，改用单 td + 统一嵌套表**。

当前结构：
```
外层 <tr>
  <td>Ligand 1</td>   ← 两个堆叠 div（SS div / AS div）
  <td>Sequences</td>  ← nested-align-table（SS 行 / AS 行）
  <td>Ligand 2</td>   ← 两个堆叠 div
```

新结构：
```
外层 <tr>
  <td class="unified-display-td">   ← 单个合并 td
    <table class="unified-strand-table">
      <tr>  ← SS 行，所有 td vertical-align:bottom
        <td class="align-dir-cell">SS 3'/5'</td>
        <td class="ligand-col-l">SS Ligand 1 tokens</td>
        <td class="ligand-seq-sep"></td>
        [seq col 1] ... [seq col N]   ← 现有 aligned_columns 渲染
        <td class="ligand-seq-sep"></td>
        <td class="ligand-col-r">SS Ligand 2 tokens</td>
        <td class="align-dir-cell">5'/3'</td>
      </tr>
      <tr class="ss-align-row">  ← AS 行，所有 td vertical-align:top
        <td class="align-dir-cell">AS 5'/3'</td>
        <td class="ligand-col-l">AS Ligand 1 tokens</td>
        <td class="ligand-seq-sep"></td>
        [seq col 1] ... [seq col N]
        <td class="ligand-seq-sep"></td>
        <td class="ligand-col-r">AS Ligand 2 tokens</td>
        <td class="align-dir-cell">3'/5'</td>
      </tr>
    </table>
  </td>
```

浏览器 table 布局保证同行所有 td 高度相同，Ligand 与 Sequences 的 SS/AS 行高天然同步，无需 JS。

### segment_sep 修复（问题 ②⑩）

SS 行 segment_sep td 内加高度锚点层：
```html
<td class="seq-segment-sep-col" style="vertical-align:bottom;">
  <div style="display:flex;flex-direction:column;align-items:center;">
    <span class="seq-count" style="visibility:hidden;">0</span>  <!-- 顶部高度锚 -->
    <div style="display:flex;flex-direction:row;flex-wrap:nowrap;gap:0;">
      {% for lk in col.linker_tokens %}
        <span class="seq-container seq-wide" style="background-color:rgba(112,203,248,1);">{{ lk.char }}</span>
      {% endfor %}
    </div>
  </div>
</td>
```

AS 行 segment_sep（空白占位 td）内加底部高度锚：
```html
<td class="seq-segment-sep-col" style="vertical-align:top;">
  <div style="display:flex;flex-direction:column;align-items:center;">
    <div style="visibility:hidden;height:1px;"></div>  <!-- 顶部撑开 -->
    <span class="seq-count" style="visibility:hidden;">0</span>  <!-- 底部高度锚 -->
  </div>
</td>
```

### Ligand token 渲染简化（问题 ③）

`char_block_SS.html` 和 `char_block_AS.html` 中去掉所有 `flex-direction:column / justify-content:flex-end` 的垂直定位技巧。  
垂直对齐完全由 unified-strand-table 的行 `vertical-align:bottom/top` 负责。

新版 char_block_SS.html（只做水平排列）：
```html
{% for char_item in delivery_colored %}
  <span class="delivery-item"
        style="background-color:{{ char_item.color }};
               {% if char_item.type == 's' %}color:black;{% endif %}">
    {{ char_item.char }}
  </span>
{% endfor %}
```

`char_block_AS.html` 结构相同（水平排列，不再有方向区别）。

### 单链回退统一（问题 ④⑨）

去掉 `{% else %} <div>...</div>` fallback，改为：
- 若 `group.aligned_columns` 非空 → 使用 unified-strand-table
- 若 `group.aligned_columns` 为空（单链）→ 同样使用 unified-strand-table，AS 行不渲染（`{% if group.items.1 %}`）

单链行只渲染 SS 行，AS 行完全省略，不占高度。

### CSS 修复（问题 ⑤⑥⑦）

在 design-system override 区块补充以下规则（均用 `!important` 以保证优先级）：

```css
/* ⑤⑥ delivery-item 统一化 */
.delivery-item {
  display: inline-flex !important;
  vertical-align: baseline !important;
  min-width: 22px !important;
  align-items: center !important;
  justify-content: center !important;
}

/* ⑦ nested 内 seq-count 行高固定 */
.nested-align-table .seq-count {
  line-height: 1.3 !important;
}

/* ⑧ Ligand 列切换 CSS class */
.hide-ligand-l .ligand-col-l { display: none !important; }
.hide-ligand-r .ligand-col-r { display: none !important; }

/* ligand-seq-sep 视觉分隔 */
.ligand-seq-sep {
  width: 4px;
  border-left: 1px dashed #e2e8f0;
}
```

### 列切换 JS 更新（问题 ⑧）

`seq_list.html` 的 checkbox：
```html
<!-- 原 data-column="5" 改为 data-toggle-class -->
<label>
  <input type="checkbox" class="toggle-vis export-field toggle-ligand-l"
         data-column="5" data-toggle-class="hide-ligand-l" value="delivery5" checked>
  Ligand 1
</label>
<label>
  <input type="checkbox" class="toggle-vis export-field"
         data-column="5" value="modify_seq" checked>
  Sequences
</label>
<label>
  <input type="checkbox" class="toggle-vis export-field toggle-ligand-r"
         data-column="5" data-toggle-class="hide-ligand-r" value="delivery3" checked>
  Ligand 2
</label>
```

注意：合并后 Ligand 1 / Sequences / Ligand 2 共享同一外层列（index 5）。DataTables 控制整列显隐；Ligand 1/2 的单独切换用 CSS class。

`tables.js` 新增处理逻辑：
```js
// 在 .toggle-vis 的 change handler 中补充：
const toggleClass = $(this).data('toggle-class');
if (toggleClass) {
  $('body').toggleClass(toggleClass, !$(this).prop('checked'));
}
```

外层表头同步更新：移除独立 Ligand 1 / Ligand 2 `<th>`，Sequences `<th>` 保留。  
后续列的 `data-column` 全部下移 2（原 8→6, 9→7, ..., 15→13）。

---

## 文件修改清单

| 文件 | 改动内容 | 规模 |
|------|---------|------|
| `templates/seq_list.html` | 移除 2 个独立 `<th>`；更新 data-column（原 8-15 → 6-13）；checkbox handler 补 toggle-class 逻辑 | 小 |
| `templates/_seq_group_row.html` | 移除 Ligand 1/2 独立 `<td>`；重构 Sequences `<td>` 为 unified-strand-table；修复 segment_sep 结构；去掉单链 fallback | **核心，最大** |
| `templates/char_block_SS.html` | 去掉 flex-column 包装，只保留 token span 排列 | 小 |
| `templates/char_block_AS.html` | 同上 | 小 |
| `static/css/styles.css` | 补 delivery-item override；ligand hide class；seq-count line-height；ligand-seq-sep | 小 |
| `static/js/tables.js` | toggle-class 支持；column index 若有硬编码则更新 | 小 |

---

## 不在本次范围内

- Ligand 列的 5'/3' 方向标签（当前 `align-dir-cell` 只在 Sequences 区，可在后续迭代评估是否在 Ligand 区重复显示）
- 移动端响应式适配
- 导出字段逻辑（export-field value 不变，仅 DataTables 列索引更新）
