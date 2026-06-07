# 双段序列 Linker 对齐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 SS 链双段序列无法被识别的 bug，并将 Linker 格调整为仅在 SS 行显示、AS 行等宽留空，使 part1↔part1、part2↔part2 精确对齐。

**Architecture:** 两处独立改动。① `detect_embedded_linker` 放宽正则，允许 `-LK1-L96-LK1-` 中的非 SeqModule token（如 L96）；② `_seq_group_row.html` 去掉 `rowspan=2`，AS 行改为渲染等宽空白单元格。无数据模型、URL、视图逻辑变更。

**Tech Stack:** Django 5.1, Python 3.10, Django Templates

---

## 文件清单

| 文件 | 改动内容 |
|------|---------|
| `app01/views.py:1208` | `detect_embedded_linker`：更新 linker 段正则（1 行） |
| `templates/_seq_group_row.html:65` | SS 行 segment_sep：去掉 `rowspan="2"`，`vertical-align` 改为 `bottom` |
| `templates/_seq_group_row.html:101-102` | AS 行 segment_sep：从"跳过"改为渲染空白 `<td>` |

---

## Task 1：修复 `detect_embedded_linker` 正则

**Files:**
- Modify: `app01/views.py:1208`

- [ ] **Step 1：定位并修改正则**

打开 `app01/views.py`，找到第 1208 行：

```python
# 现有代码（第 1208 行）
        patterns.append(rf'-(?:{kw_pat})(?:-(?:{kw_pat}))+-')
```

改为：

```python
        patterns.append(rf'-(?:{kw_pat})(?:-(?:[A-Za-z0-9()]+))+-')
```

只改变了重复段的匹配范围：从"必须是 SeqModule linker 关键字"放宽为"任意字母数字 token"，首个 token 仍然必须是 SeqModule linker 关键字。

- [ ] **Step 2：Django shell 验证**

```bash
source venv/bin/activate
python manage.py shell -c "
from app01.views import detect_embedded_linker

ss = 'GnsGmsCmUmUmUmCfUmGfCfAmUmCmAmGmAmCmAmsUmsUm-LK1-L96-LK1-UmsCmsCmUmCmUmGfAmUfGfGfUmCmAmAmAmGmUmCmsCmsUm'
as_ = 'AnsGfsGmAmCmUfUmUfGfAmCmCmAmUfCmAfGmAmGmsGmsAm------------AmsAfsUmGmdUCmdUGmAmUmGmCmAfG(moe)AfAmAmGmsCmsCm'

r_ss = detect_embedded_linker(ss)
r_as = detect_embedded_linker(as_)

print('SS detected:', r_ss is not None)
print('SS linker section:', r_ss[1] if r_ss else None)
print('AS detected:', r_as is not None)
print('AS linker section:', r_as[1] if r_as else None)
"
```

预期输出：
```
SS detected: True
SS linker section: -LK1-L96-LK1-
AS detected: True
AS linker section: ------------
```

- [ ] **Step 3：验证 split_tokens_at_sep 现在可以拆分 SS**

```bash
python manage.py shell -c "
from app01.views import get_modify_seq_colored, split_tokens_at_sep
from app01.models import DeliveryModule

dm = list(DeliveryModule.objects.all())
ss = 'GnsGmsCmUmUmUmCfUmGfCfAmUmCmAmGmAmCmAmsUmsUm-LK1-L96-LK1-UmsCmsCmUmCmUmGfAmUfGfGfUmCmAmAmAmGmUmCmsCmsUm'
tokens = get_modify_seq_colored(ss, 'SS', 'SS', dm_modules=dm)
parts = split_tokens_at_sep(tokens)
print('split result is None:', parts is None)
if parts:
    p1_nucs = [t for t in parts[0] if t['char'] not in ('s','o','ss')]
    p2_nucs = [t for t in parts[2] if t['char'] not in ('s','o','ss')]
    lk = [t['char'] for t in parts[1]]
    print('part1 nuc count:', len(p1_nucs))
    print('linker tokens:', lk)
    print('part2 nuc count:', len(p2_nucs))
"
```

预期输出：
```
split result is None: False
part1 nuc count: 21
linker tokens: ['LK1', '-', 'L96', 'LK1', '-']
part2 nuc count: 21
```

- [ ] **Step 4：提交**

```bash
git add app01/views.py
git commit -m "fix: detect_embedded_linker accepts non-SeqModule tokens in linker section (e.g. -LK1-L96-LK1-)"
```

---

## Task 2：模板调整 — Linker 格仅在 SS 行，AS 行等宽留空

**Files:**
- Modify: `templates/_seq_group_row.html:65,101-102`

- [ ] **Step 1：修改 SS 行 segment_sep 单元格（第 65 行）**

找到第 65 行，去掉 `rowspan="2"`，并将 `vertical-align:middle` 改为 `vertical-align:bottom`：

```html
<!-- 修改前（第 65 行） -->
                    <td class="seq-segment-sep-col" rowspan="2" style="vertical-align:middle;padding:0 6px;border-left:2px dashed #cbd5e1;border-right:2px dashed #cbd5e1;background:#f8fafc;">

<!-- 修改后（第 65 行） -->
                    <td class="seq-segment-sep-col" style="vertical-align:bottom;padding:0 6px;border-left:2px dashed #cbd5e1;border-right:2px dashed #cbd5e1;background:#f8fafc;">
```

- [ ] **Step 2：修改 AS 行 segment_sep 处理（第 101-102 行）**

找到第 101-102 行，从跳过注释改为渲染空白单元格：

```html
<!-- 修改前（第 101-102 行） -->
                  {% if col.col_type == 'segment_sep' %}
                    {# rowspan=2 td rendered in SS row above — skip #}

<!-- 修改后（第 101-102 行） -->
                  {% if col.col_type == 'segment_sep' %}
                    <td class="seq-segment-sep-col" style="vertical-align:top;padding:0 6px;border-left:2px dashed #cbd5e1;border-right:2px dashed #cbd5e1;background:#f8fafc;"></td>
```

HTML table 同列宽度由所有行中该列最宽内容决定，SS 行 Linker 内容（LK1-L96-LK1）撑开列宽后，AS 行空白 `<td>` 自动继承相同宽度。

- [ ] **Step 3：启动开发服务器手动验证**

```bash
source venv/bin/activate && python manage.py runserver
```

在浏览器中打开序列列表，找到 BP000016，确认：
1. SS 行：part1 显示编号 21→1，中间出现蓝色 Linker 格（显示 LK1、L96、LK1，无编号），part2 显示编号 21→1
2. AS 行：part1 显示编号 1→21，中间出现等宽空白格（与 SS Linker 格同宽），part2 显示编号 1→21
3. SS part1 第 1 位与 AS part1 第 1 位纵向对齐；SS part2 第 21 位与 AS part2 第 21 位纵向对齐
4. 不含双段 linker 的普通序列（无 `-LK1-...-` 或 `--------`）渲染不受影响

- [ ] **Step 4：提交**

```bash
git add templates/_seq_group_row.html
git commit -m "fix: segment_sep renders in SS row only; AS row gets equal-width empty spacer"
```
