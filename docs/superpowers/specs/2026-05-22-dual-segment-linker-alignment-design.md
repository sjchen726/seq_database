# 双段序列 Linker 对齐设计 — 2026-05-22

## 问题描述

BP000016 等双段序列中，SS 链形如：

```
...Um-LK1-L96-LK1-Um...
```

AS 链形如（4个以上连续破折号作为占位）：

```
...Am------------Am...
```

当前 `detect_embedded_linker` 的正则要求 linker 段内所有 token 都来自 `SeqModule.linker_connector='-'`（即 LK1/P91/P93/P96）。`L96` 是 `DeliveryModule` 关键字，不在该集合内，导致 SS 链无法被识别为双段序列，走平铺对齐回退路径，两链完全错位。

AS 链因含 4+ 连续破折号，可正常被识别为双段。

---

## 目标效果

```
SS 3' | 21  20 … 2  1 | LK1 L96 LK1 | 21  20 … 2  1 | 5'
AS 5' |  1   2 … 20 21|    （等宽空白）|  1   2 … 20 21| 3'
```

- SS 行：part1（21→1）| Linker 格（LK1-L96-LK1，蓝色，不标编号）| part2（21→1）
- AS 行：part1（1→21）| 等宽空白格（无内容，列宽由 SS Linker 内容自然撑开）| part2（1→21）
- 两段分别精确对齐：part1-SS ↔ part1-AS，part2-SS ↔ part2-AS

---

## 根因分析

**`detect_embedded_linker`（`app01/views.py` 约第 1200 行）**

当前正则（linker 关键字模式）：

```python
rf'-(?:{kw_pat})(?:-(?:{kw_pat}))+-'
```

该模式要求每一个 token 均为 SeqModule linker 关键字。`-LK1-L96-LK1-` 中 `L96` 不在集合内，整体匹配失败，函数返回 `None`。

**`build_duplex_groups`（`app01/views.py` 约第 2212 行）**

`ss_split` 为 `None` 时进入平铺回退路径，SS linker token 混入碱基序列参与位置配对，造成错位。

**`_seq_group_row.html`（`templates/_seq_group_row.html` 约第 64 行）**

当前 segment_sep 单元格使用 `rowspan=2`，linker 内容居中显示在 SS/AS 两行之间。需改为 SS 行独占、AS 行空白。

---

## 修改方案

### 改动 1 — `detect_embedded_linker` 正则（`app01/views.py`）

**现有模式：**
```python
rf'-(?:{kw_pat})(?:-(?:{kw_pat}))+-'
```

**新模式：**
```python
rf'-(?:{kw_pat})(?:-(?:[A-Za-z0-9()]+))+-'
```

将中间重复段从"只允许 SeqModule linker 关键字"放宽为"任意字母数字 token"，同时保持：
- 第一个 token 仍必须是 SeqModule linker 关键字（防止误识别普通碱基修饰连接符）
- 至少两组 `-token`（`+` 量词），避免将 `Um-LK1` 单 combo 错判为双段

验证：
- `-LK1-L96-LK1-` → 匹配 ✓（LK1 开头，-L96- 中间，-LK1- 结尾）
- `-LK1-LK1-` → 匹配 ✓（两个 SeqModule linker）
- `-LK1-` 单独 → 不匹配 ✓（`+` 要求至少一个额外 `-token`）
- `Um-LK1`（无后续 `-`）→ 不匹配 ✓（无尾 `-`）
- `------------`（≥4 破折号）→ 走现有 `r'-{4,}'` 分支，不受影响 ✓

### 改动 2 — 模板 segment_sep 渲染（`templates/_seq_group_row.html`）

**SS 行（第 64–71 行）：** 去掉 `rowspan="2"`，单元格保持现有 Linker token 渲染逻辑不变。

```html
<!-- 修改前 -->
<td class="seq-segment-sep-col" rowspan="2" style="...">

<!-- 修改后 -->
<td class="seq-segment-sep-col" style="vertical-align:bottom;...">
```

**AS 行（第 101–103 行）：** 从"跳过注释"改为渲染空白单元格，沿用 `seq-segment-sep-col` class 保持边框和背景一致。

```html
<!-- 修改前 -->
{% if col.col_type == 'segment_sep' %}
    {# rowspan=2 td rendered in SS row above — skip #}

<!-- 修改后 -->
{% if col.col_type == 'segment_sep' %}
    <td class="seq-segment-sep-col" style="vertical-align:top;"></td>
```

HTML table 同一列的宽度由该列所有单元格内容共同决定，SS 行的 Linker 内容撑开列宽后，AS 行空白单元格自动继承相同宽度。

---

## 涉及文件

| 文件 | 改动内容 |
|------|---------|
| `app01/views.py` | `detect_embedded_linker`：更新 linker 关键字模式正则（1 行） |
| `templates/_seq_group_row.html` | segment_sep SS 行去掉 `rowspan=2`；AS 行改为渲染空白 `<td>` |

**不涉及：** `build_duplex_groups` 逻辑、`align_duplex_tokens`、数据模型、URL、CSS——均无需改动。

---

## 不改动范围

- 编号逻辑：`get_modify_seq_colored` 每次递归调用独立计数器，part1/part2 各自从 1 开始，SS 经 `_reverse_tokens` 后显示 21→1，AS 不反转显示 1→21，均无需改动。
- AS 检测逻辑：`r'-{4,}'` 分支继续处理 AS 链的 `------------` 占位符，不受影响。
- Linker 格编号：`segment_sep` 单元格模板中不渲染 `seq-count`，Linker token 天然不标号，无需额外处理。
