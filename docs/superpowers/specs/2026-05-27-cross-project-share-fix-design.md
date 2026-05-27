# 跨项目共享修复 — 设计规范

## 背景与问题

当前跨项目共享存在两个核心缺陷：

**缺陷 1：`check_duplicates` 用全局 `target_project` 检测重复**

`upload_delivery_info` 只读 CSV 第一行的 `Project` 作为全局 `target_project`，再传给 `check_duplicates`。当上传混合项目的 CSV（如第 1 对属于 `BPR-11`、第 2~4 对属于 `BPR-XXXX`）时，所有对都用 `BPR-11` 做比较：第 2~4 对在 DB 里已存在于 `BPR-XXXX`，理应被检测为"同项目重复"，却因 `target_project='BPR-11'` ≠ `'BPR-XXXX'` 而被误判为跨项目。

**缺陷 2：共享后序列列表看不出来源**

序列被共享到新项目后，列表里仍只显示原始项目名，用户无法区分"本项目原生序列"和"从其他项目共享来的序列"。

## 目标

1. 每对序列用自己 CSV 行的 `Project` 字段做重复检测（per-pair project）
2. 共享后的序列在列表里显示 `BPR-XXXX → BPR-11` 风格的标记，让用户知道来源

## 不在本次范围内

- 取消共享（从某项目移除）
- 编辑权限因共享而变化（已由 `user_can_edit_delivery` 处理，不改）
- 确认页 UI 重构

---

## 方案设计

### Part 1：`check_duplicates` 改为 per-pair project

`group_sequences` 已将每对的 `Project` 存入 ss_groups 元组第二位：

```python
ss_groups.append((None, project, temp_group))
```

`check_duplicates` 目前忽略这一位（`for _, _, group in ss_groups`），改为读取它：

**函数签名变更：**

```python
# 前
def check_duplicates(df, ss_groups, target_project=None):
    for _, _, group in ss_groups:
        ...
        if target_project and target_project in existing_projects:
            # 同项目重复

# 后
def check_duplicates(df, ss_groups):
    for _, group_project, group in ss_groups:
        ...
        if group_project and group_project in existing_projects:
            # 同项目重复
```

**调用方更新（共 2 处）：**

| 位置 | 变更 |
|------|------|
| `upload_delivery_info` POST (`views.py` ~2116) | 删除 `target_project=target_project`，删除读取 `target_project` 的 3 行 |
| `confirm_upload_preflight` POST (`views.py` ~2308) | 同上 |

另外两处调用（`confirm_share_deliveries`、`clone_delivery`）本来就没传 `target_project`，无需改动。

**修复效果：**

上传 `template-1.csv`（第 1 对 BPR-11，第 2~4 对 BPR-XXXX）、DB 里已有 BPR-XXXX 四对时：

| CSV 行 | CSV Project | DB 存在于 | 判断结果 |
|--------|-------------|-----------|---------|
| 第 1 对 | BPR-11 | BPR-XXXX | 跨项目 → 进确认页 ✅ |
| 第 2 对 | BPR-XXXX | BPR-XXXX | 同项目重复 → 跳过 ✅ |
| 第 3 对 | BPR-XXXX | BPR-XXXX | 同项目重复 → 跳过 ✅ |
| 第 4 对 | BPR-XXXX | BPR-XXXX | 同项目重复 → 跳过 ✅ |

---

### Part 2：序列列表共享来源标记

#### 数据层：`build_duplex_groups`

**2a. 预取 `project_links`，避免 N+1 查询：**

```python
def build_duplex_groups(delivery_qs, selected_seq_type):
    delivery_qs = delivery_qs.prefetch_related('project_links')
    ...
```

**2b. 计算 `shared_projects`，追加到每个 item：**

在 `build_sequence_data` 调用之后（`duplex_group_map[(project, duplex_id)].append(item)` 之前）：

```python
# 计算额外项目（超出 Delivery.project 的部分）
shared_projects = []
if group_deliveries:
    first_d = group_deliveries[0]
    all_projs = list(first_d.project_links.values_list('project_code', flat=True))
    shared_projects = [p for p in all_projs if p != first_d.project]
item['shared_projects'] = shared_projects
```

**2c. 将 `shared_projects` 提升到 group 级别：**

在 `sequence_groups.append(...)` 处（`build_duplex_groups` 末段），从 `items[0]` 读取并存入 group：

```python
sequence_groups.append({
    'project': project,
    'duplex_id': duplex_id,
    'items': sorted_items,
    'shared_projects': items[0].get('shared_projects', []) if items else [],
    # ...其余不变
})
```

#### 模板层：`_seq_group_row.html`

在项目名旁边追加共享 pill（仅当 `shared_projects` 非空时渲染）：

```html
{{ group.project }}
{% if group.shared_projects %}
  <span class="shared-pill" title="已共享至：{{ group.shared_projects|join:', ' }}">
    → {{ group.shared_projects|join:', ' }}
  </span>
{% endif %}
```

#### 样式层：`static/css/styles.css`

```css
.shared-pill {
    display: inline-block;
    margin-left: 6px;
    padding: 1px 7px;
    border-radius: 10px;
    background: #e8f0fe;
    color: #1a73e8;
    font-size: 11px;
    font-weight: 500;
    white-space: nowrap;
    vertical-align: middle;
}
```

---

## 涉及文件

| 文件 | 改动 |
|------|------|
| `app01/views.py` | `check_duplicates` 签名 + 内部逻辑（10 行）；`upload_delivery_info` 删 `target_project` 读取（3 行）；`confirm_upload_preflight` 同（3 行）；`build_duplex_groups` 加 prefetch + shared_projects 计算（~12 行） |
| `templates/_seq_group_row.html` | 项目名旁加 shared-pill（~5 行） |
| `static/css/styles.css` | 新增 `.shared-pill` 样式（~10 行） |

## 边界情况

| 情况 | 处理方式 |
|------|---------|
| 一条序列共享至多个项目（BPR-11, BPR-22） | `shared_projects = ['BPR-11', 'BPR-22']`，pill 显示 `→ BPR-11, BPR-22` |
| 序列只属于一个项目 | `shared_projects = []`，不渲染 pill |
| 从原始项目（BPR-XXXX）视角查看 | pill 显示 `→ BPR-11`，说明已被共享出去 |
| 从目标项目（BPR-11）视角查看 | `Delivery.project = 'BPR-XXXX'`，group 显示 `BPR-XXXX → BPR-11`，清晰表达"共享自哪里" |
| `project_links` 未预取时访问 | 已在 `build_duplex_groups` 入口处统一 `prefetch_related`，不会产生 N+1 |
