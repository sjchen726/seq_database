# segment_sep 垂直对齐修复设计 — 2026-05-22

## 问题描述

双段序列（如 BP000016）展示时，nested alignment table 的 SS row 中，segment_sep 单元格（显示 LK1-L96-LK1 等 linker token）与两侧序列 token 垂直位置不一致：linker token 出现在单元格中部（浏览器默认 `vertical-align:middle`），而两侧序列列的 `<td>` 均设置了 `vertical-align:bottom`，导致 linker token 视觉上"悬空"，高于两侧碱基字符底线。

---

## 根因

`templates/_seq_group_row.html` 第 65 行，SS row 的 segment_sep `<td>`：

```html
<td class="seq-segment-sep-col">
  <div style="display:flex;flex-direction:row;flex-wrap:nowrap;align-items:flex-end;gap:0;height:100%;">
```

- `<td>` 无 `vertical-align` 属性，浏览器默认 `middle`；两侧正常列均为 `vertical-align:bottom`。
- `height:100%` 在 table cell 内无效，导致 `align-items:flex-end` 形同虚设。

---

## 修复方案

**仅改 `templates/_seq_group_row.html` 第 65–66 行：**

```html
<!-- 修改前 -->
<td class="seq-segment-sep-col">
  <div style="display:flex;flex-direction:row;flex-wrap:nowrap;align-items:flex-end;gap:0;height:100%;">

<!-- 修改后 -->
<td class="seq-segment-sep-col" style="vertical-align:bottom;">
  <div style="display:flex;flex-direction:row;flex-wrap:nowrap;gap:0;">
```

两处变化：
1. `<td>` 加 `vertical-align:bottom`，与两侧所有正常列保持一致。
2. inner div 去掉 `height:100%`（table cell 内无效）和 `align-items:flex-end`（由 td 的 vertical-align 接管，不再需要）。

---

## 不改动范围

- AS row segment_sep：已有 `style="vertical-align:top;"`，正确，无需改动。
- Python views、CSS class `.seq-segment-sep-col`、其他 template：均不涉及。

---

## 涉及文件

| 文件 | 改动 |
|------|------|
| `templates/_seq_group_row.html` | SS row segment_sep `<td>` 加 `vertical-align:bottom`，inner div 删除 `height:100%` 和 `align-items:flex-end` |
