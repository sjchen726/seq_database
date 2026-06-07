# Group A Bug Fix Design — 2026-05-16

## Scope

修复 5 个数据/逻辑层 bug，不涉及新功能或 UI 重构。

---

## A1 — G(moe) 双重 connector 追加

**文件：** `app01/views.py`  
**函数：** `add_o_to_all_rules()`  
**行号：** 约 1147

**根因：** SeqModule token（如 `Gm`）被匹配后，判断是否追加 connector 时只排除了后一字符为 `'s'` 的情况，未排除后一字符已经是相同 connector（`'o'` 或 `'-'`）的情况。当序列中显式写了 `o`（如 `GmoU`），匹配 `Gm` 后还会追加 `'o'`，生成 `GmooU`。

**修复：**

```python
# 修改前
if connector and end < len(modify_seq) and modify_seq[end] != 's':

# 修改后
if connector and end < len(modify_seq) and modify_seq[end] not in ('s', 'o', '-'):
```

**影响范围：** 仅影响 modify_seq 中已显式写出 linker 字符的序列。不影响不含显式 linker 的正常序列（绝大多数情况）。

---

## A2 — Part2 AS/SS 对齐列宽错位

**文件：** `app01/views.py`  
**函数：** `build_duplex_groups()`  
**行号：** 约 2184–2188

**根因：** `get_modify_seq_colored` 对 SS 链做 group-based token 反转（seq_type == selected_seq_type），所以 `ss_p2` 的位置0 是 Part2 的 terminal 端（远离 linker）。而 `as_p2` 未经反转，位置0 是靠近 linker 的端点。两端起点不同 → 逐列对齐时错位。Part1 能正确对齐是因为 SS Part1 反转后与 AS Part1（从 linker junction 起始存储）恰好方向一致；Part2 方向相反，须对 `as_p2` 补做相同的反转。

**修复：**

1. 将 `get_modify_seq_colored` 中的 group-based 反转逻辑提取为独立函数 `_reverse_tokens(tokens)`（不含 IGNORECASE 逻辑，只做 token 列表的 group 反转）。

2. 在 Part2 对齐调用时对 `as_p2` 用同样的反转：

```python
# 修改前
align_duplex_tokens(ss_p2, as_p2)

# 修改后
align_duplex_tokens(ss_p2, _reverse_tokens(as_p2))
```

**注意：** `_reverse_tokens` 内部逻辑与 `get_modify_seq_colored` 中现有的反转块完全相同（LINKERS = {'s','o','ss'}，group-based reversed 重排），抽取为独立函数避免重复。Part1 对齐保持不变 `align_duplex_tokens(ss_p1, as_p1)`。

---

## A3 — download_selected 下载失效

**文件：** `static/js/tables.js`（约 286、306 行），`app01/views.py`（约 2626–2633 行）

**根因（两处）：**

1. **JS 端 — seqType 解析错误：** `$(row).find('td:nth-child(5)').text().trim()` 当一行包含 SS+AS 两个 delivery_id 时，文本是多行（如 `"SS_RM000001.1\nAS_RM000002.1"`），`split('_', 1)[-1]` 后得到 `"RM000001.1\nAS_RM000002.1"`，delivery_id 字段查询错误。

2. **JS 端 — CSRF token 可能为 null：** `document.querySelector('input[name=csrfmiddlewaretoken]').value` 若页面上没有该元素会抛 TypeError。

3. **View 端 — 逻辑过于复杂：** 每行一个 duplex_id 已足以唯一确定下载范围，不需要额外过滤 delivery_id（一个 duplex 本身就包含 SS+AS 全部记录）。

**修复：**

JS 端：
- CSRF token 改为从 cookie 读取（`getCsrfFromCookie()`），消除对页面元素的依赖。
- 下载逻辑只收集 `duplex_id`，不再读取第5列 seqType 文本。

View 端：
- 移除 `seq_ids` 提取逻辑，改为直接按 `duplex_id__in=ids` 查询：

```python
# 修改后（简化）
ids = json.loads(selected_ids)
deliveries = Delivery.objects.filter(duplex_id__in=ids)\
    .select_related('sequence')\
    .prefetch_related('sequence__target_info')
```

---

## A4 — check_duplicates 与 save_deliveries 去重字段不一致

**文件：** `app01/views.py`  
**函数：** `check_duplicates()`  
**行号：** 约 1270–1273

**根因：** `check_duplicates` 用 `modify_seq` 字段在 DB 中查重，而 `save_deliveries` 用 `linker_seq`（经 `add_o_to_all_rules_safe` 规范化）去重。当上传序列的 `modify_seq` 与 DB 中格式略有不同（如显式 `o` vs 无显式 `o`）时，`check_duplicates` 漏判，但 `save_deliveries` 的 `linker_seq` 比对仍能捕获。两步用不同字段是不一致的隐患。

**修复：** `check_duplicates` 查 DB 时改用 `linker_seq` 字段（对 `clean_seq` 先调用 `add_o_to_all_rules_safe` 再查询），与 `save_deliveries` 保持一致：

```python
# 修改前
ss_deliveries = Delivery.objects.filter(
    modify_seq=ss_clean_seq,
    delivery5=ss_d5,
    delivery3=ss_d3
)

# 修改后
ss_linker_seq = add_o_to_all_rules_safe(ss_clean_seq)
ss_deliveries = Delivery.objects.filter(
    linker_seq=ss_linker_seq,
    delivery5=ss_d5,
    delivery3=ss_d3
)
```

同理对 AS 查询也做相同调整。

---

## A5 — Remark 拼接显示 "None"

**文件：** `app01/views.py`  
**函数：** `build_sequence_data()`  
**行号：** 约 1956–1961

**根因：** 当 `seqinfo.Remark is None` 时，`f"{seqinfo.Remark}\n{...}"` 产生字符串 `"None\n..."` 直接暴露在页面上。即使只有一方有值，另一方为空时也会产生多余的 `\n`。

**修复：** 改为先收集非空 part，再 join：

```python
# 修改后
_remark_parts = [
    seqinfo.Remark if seqinfo and seqinfo.Remark else None,
    get_attr(deliveries[0], 'Remark') if deliveries else None,
]
remark = '\n'.join(p for p in _remark_parts if p) or None
```

---

## 执行顺序建议

| 顺序 | Bug | 难度 | 独立性 |
|------|-----|------|--------|
| 1 | A1 — 双 connector | 低（一行改动） | 完全独立 |
| 2 | A5 — Remark None | 低（3行改动） | 完全独立 |
| 3 | A4 — 去重字段一致 | 低（2处改动） | 完全独立 |
| 4 | A3 — download | 中（JS+view） | 完全独立 |
| 5 | A2 — Part2 对齐 | 中（提取函数+调用） | 完全独立 |

各 bug 之间无依赖关系，可并行修复。
