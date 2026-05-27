# 跨项目共享修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复混合项目 CSV 的跨项目检测逻辑，并在序列列表里显示"共享自/至"标记。

**Architecture:** 两部分独立改动：（1）`check_duplicates` 改为从每对的 ss_groups 元组读取 `group_project`，替换全局 `target_project` 参数；（2）`build_duplex_groups` 预取 `project_links`，计算 `shared_projects`，模板里在项目名旁渲染共享 pill。

**Tech Stack:** Django 5.1, Python 3.10, MySQL, Jinja2 模板, CSS

---

## 文件改动地图

| 文件 | 改动类型 |
|------|---------|
| `app01/views.py` | 修改 `check_duplicates`（签名 + 内部）、删除两处 `target_project` 读取、修改 `build_duplex_groups`（prefetch + shared_projects） |
| `templates/_seq_group_row.html` | 第 12 行 project td 增加 shared-pill |
| `static/css/styles.css` | 末尾追加 `.shared-pill` 样式 |

---

## Task 1：修复 `check_duplicates` — 改为 per-pair project

**Files:**
- Modify: `app01/views.py:1560-1676`

### 背景
`check_duplicates(df, ss_groups, target_project=None)` 当前用全局 `target_project` 与 DB 比较。`group_sequences` 已将每对的 project 存入 ss_groups 元组第二位，但函数里写的是 `for _, _, group in ss_groups`，把它丢弃了。

- [ ] **Step 1：修改函数签名，读取 group_project**

在 `app01/views.py` 找到第 1560 行，将以下内容：

```python
def check_duplicates(df, ss_groups, target_project=None):
    repeated_ids = set()
    duplicate_meg = []
    cross_project_duplicates = []
```

替换为：

```python
def check_duplicates(df, ss_groups):
    repeated_ids = set()
    duplicate_meg = []
    cross_project_duplicates = []
```

- [ ] **Step 2：修改循环头，解包 group_project**

找到第 1578 行：

```python
    for _, _, group in ss_groups:
```

替换为：

```python
    for _, group_project, group in ss_groups:
```

- [ ] **Step 3：将两处 `target_project` 替换为 `group_project`**

找到第 1657 行：

```python
                        if target_project and target_project in existing_projects:
```

替换为：

```python
                        if group_project and group_project in existing_projects:
```

找到第 1669 行：

```python
                                'target_project': target_project or '',
```

替换为：

```python
                                'target_project': group_project or '',
```

- [ ] **Step 4：用 Django shell 验证函数签名正确**

```bash
source venv/bin/activate
python manage.py shell -c "
from app01.views import check_duplicates
import inspect
sig = inspect.signature(check_duplicates)
print('参数：', list(sig.parameters.keys()))
# 期望输出：参数： ['df', 'ss_groups']
"
```

期望输出：`参数： ['df', 'ss_groups']`

- [ ] **Step 5：Commit**

```bash
git add app01/views.py
git commit -m "fix: check_duplicates uses per-pair group_project instead of global target_project"
```

---

## Task 2：更新两处调用方，删除 `target_project` 读取

**Files:**
- Modify: `app01/views.py:2110-2117`（upload_delivery_info）
- Modify: `app01/views.py:2307-2314`（confirm_upload_preflight）

### 背景
`upload_delivery_info` 和 `confirm_upload_preflight` 两处都在调用 `check_duplicates` 前读取 `target_project = df['Project'].iloc[0]`，现在不再需要。

- [ ] **Step 1：删除 upload_delivery_info 里的 target_project 读取**

找到 `upload_delivery_info` 中以下 5 行（约第 2110 行）：

```python
            # 从 CSV 第一行读取目标项目
            target_project = None
            if 'Project' in df.columns and not df.empty:
                target_project = str(df['Project'].iloc[0]).strip()

            repeated_ids, duplicate_meg, cross_project_duplicates = check_duplicates(
                df, ss_groups, target_project=target_project
            )
```

替换为：

```python
            repeated_ids, duplicate_meg, cross_project_duplicates = check_duplicates(
                df, ss_groups
            )
```

- [ ] **Step 2：删除 confirm_upload_preflight 里的 target_project 读取**

找到 `confirm_upload_preflight` POST 中以下 5 行（约第 2307 行）：

```python
            target_project = None
            if 'Project' in df.columns and not df.empty:
                target_project = str(df['Project'].iloc[0]).strip()

            # ── 3. 继续现有上传管道 ──
            repeated_ids, duplicate_meg, cross_project_duplicates = check_duplicates(
                df, clean_groups, target_project=target_project
            )
```

替换为：

```python
            # ── 3. 继续现有上传管道 ──
            repeated_ids, duplicate_meg, cross_project_duplicates = check_duplicates(
                df, clean_groups
            )
```

- [ ] **Step 3：确认 Django 系统检查通过**

```bash
source venv/bin/activate
python manage.py check
```

期望输出：`System check identified no issues (0 silenced).`

- [ ] **Step 4：用 Django shell 端到端验证检测逻辑**

此步骤需要 DB 里已有 BPR-XXXX 的四对序列（delivery_ids 63-70）。

```bash
source venv/bin/activate
python manage.py shell -c "
import pandas as pd, re
from io import StringIO
from app01.views import check_duplicates, group_sequences, normalize_middle_brackets

csv_content = '''Project,Target,Seq_type,Modify_seq,Strand_MWs,Parents,Remarks,Transcript,Position
BPR-11,GENE,SS,\"[invAb]AmUmGmCmAmUmGmCmAmUm[Vp]\",,,,,
BPR-11,GENE,AS,\"[Vp]AmGmCmAmUmGmAmCmGmUm[invAb]\",,,,,
BPR-XXXX,GENE,SS,\"[invAb]AmUmGmCmAmUmGmCmAmUm[Vp]\",,,,,
BPR-XXXX,GENE,AS,\"[Vp-invAb]AmGmCmAmUmGmAmCmGmUm[invAb]\",,,,,'''

df = pd.read_csv(StringIO(csv_content))
df['__row_id'] = range(len(df))
df['__original_line'] = range(2, len(df)+2)
df['Modify_seq'] = df['Modify_seq'].apply(normalize_middle_brackets)

ss_groups, _ = group_sequences(df)
print('ss_groups projects:', [g[1] for g in ss_groups])
# 期望：['BPR-11', 'BPR-XXXX']

repeated_ids, dup_meg, cross = check_duplicates(df, ss_groups)
print('repeated_ids:', repeated_ids)
print('cross_project count:', len(cross))
for c in cross:
    print('  cross:', c['target_project'], '<-', c['existing_projects'])
# 期望：
#   repeated_ids: {2, 3}  (BPR-XXXX 对已在 DB 里，同项目重复)
#   cross_project count: 1  (BPR-11 对跨项目)
#   cross: BPR-11 <- ['BPR-XXXX']
"
```

- [ ] **Step 5：Commit**

```bash
git add app01/views.py
git commit -m "fix: remove global target_project reads from upload views, use per-pair project"
```

---

## Task 3：`build_duplex_groups` 计算 `shared_projects`

**Files:**
- Modify: `app01/views.py:2659-2779`（build_duplex_groups）

### 背景
`build_duplex_groups` 收到 `delivery_qs` 后，需要：（1）预取 `project_links` 避免 N+1；（2）为每个 item 计算 `shared_projects`（超出 `Delivery.project` 的额外项目）；（3）将其提升到 group 级别的 `sequence_groups` dict。

- [ ] **Step 1：在函数入口处加 prefetch_related**

找到 `build_duplex_groups` 函数（约第 2659 行），在第一行预加载 `_dm_modules` 之前插入：

```python
def build_duplex_groups(delivery_qs, selected_seq_type):
    # 预取 project_links，避免后续访问产生 N+1 查询
    delivery_qs = delivery_qs.prefetch_related('project_links')
```

即将：

```python
def build_duplex_groups(delivery_qs, selected_seq_type):
    # 预加载 DeliveryModule 和 LinkerModule（一次查询，供所有 build_sequence_data 调用复用）
    _dm_modules = list(DeliveryModule.objects.all())
```

替换为：

```python
def build_duplex_groups(delivery_qs, selected_seq_type):
    # 预取 project_links，避免后续访问产生 N+1 查询
    delivery_qs = delivery_qs.prefetch_related('project_links')
    # 预加载 DeliveryModule 和 LinkerModule（一次查询，供所有 build_sequence_data 调用复用）
    _dm_modules = list(DeliveryModule.objects.all())
```

- [ ] **Step 2：在两处 `duplex_group_map[...].append(item)` 前计算 shared_projects**

当前函数内有两处 `duplex_group_map[(project, duplex_id)].append(item)`（linker_seq 分支和无 linker_seq 分支）。

找到 linker_seq 分支（约第 2729 行）：

```python
                    duplex_group_map[(project, duplex_id)].append(item)
```

替换为：

```python
                    # 计算共享项目（超出原始 Delivery.project 的额外项目）
                    first_d = group_deliveries[0]
                    all_projs = list(first_d.project_links.values_list('project_code', flat=True))
                    item['shared_projects'] = [p for p in all_projs if p != first_d.project]
                    duplex_group_map[(project, duplex_id)].append(item)
```

找到无 linker_seq 分支（约第 2742 行）：

```python
                duplex_group_map[(project, duplex_id)].append(item)
```

替换为：

```python
                # 计算共享项目（超出原始 Delivery.project 的额外项目）
                first_d = group_deliveries[0]
                all_projs = list(first_d.project_links.values_list('project_code', flat=True))
                item['shared_projects'] = [p for p in all_projs if p != first_d.project]
                duplex_group_map[(project, duplex_id)].append(item)
```

- [ ] **Step 3：将 shared_projects 提升到 group 级别**

找到 `sequence_groups.append(...)` 块（约第 2771 行）：

```python
        sequence_groups.append({
            'project': project,
            'duplex_id': duplex_id,
            'items': sorted_items,
            'aligned_columns': aligned,
            'latest_update_time': max(times) if times else None,
        })
```

替换为：

```python
        sequence_groups.append({
            'project': project,
            'duplex_id': duplex_id,
            'items': sorted_items,
            'aligned_columns': aligned,
            'latest_update_time': max(times) if times else None,
            'shared_projects': items[0].get('shared_projects', []) if items else [],
        })
```

- [ ] **Step 4：验证 shared_projects 正确填充**

先在 UI 或 shell 里确认 BPR-XXXX 的某条序列被共享至 BPR-11（可用上一 Task 的确认流程做一次共享操作），然后：

```bash
source venv/bin/activate
python manage.py shell -c "
from app01.models import Delivery, DeliveryProject
# 检查 delivery_id=63 是否已被共享到 BPR-11
dp = DeliveryProject.objects.filter(delivery_id=63)
print('project_codes:', list(dp.values_list('project_code', flat=True)))
# 期望：['BPR-XXXX', 'BPR-11']（共享后）

from app01.views import build_duplex_groups
from app01.models import Delivery
qs = Delivery.objects.filter(id=63)
groups = build_duplex_groups(qs, 'SS')
for g in groups:
    print('shared_projects:', g['shared_projects'])
# 期望：shared_projects: ['BPR-11']
"
```

- [ ] **Step 5：Commit**

```bash
git add app01/views.py
git commit -m "feat: compute shared_projects per duplex group in build_duplex_groups"
```

---

## Task 4：模板 + CSS 共享 pill

**Files:**
- Modify: `templates/_seq_group_row.html:12`
- Modify: `static/css/styles.css`（末尾追加）

### 背景
`_seq_group_row.html` 第 12 行显示 `{{ group.items.0.Project }}`，在它后面加共享 pill。`group.shared_projects` 已在 Task 3 中填充。

- [ ] **Step 1：在模板 project td 里追加 shared-pill**

找到 `templates/_seq_group_row.html` 第 12 行：

```html
          <td>{{ group.items.0.Project }}</td>
```

替换为：

```html
          <td>
            {{ group.items.0.Project }}
            {% if group.shared_projects %}
              <span class="shared-pill" title="已共享至：{{ group.shared_projects|join:', ' }}">→ {{ group.shared_projects|join:', ' }}</span>
            {% endif %}
          </td>
```

- [ ] **Step 2：在 styles.css 末尾追加 .shared-pill 样式**

在 `static/css/styles.css` 末尾（`::-webkit-scrollbar-thumb:hover` 规则之后）追加：

```css
/* ── Shared project pill ───────────────────────────────────────── */
.shared-pill {
  display: inline-block;
  margin-left: 5px;
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

- [ ] **Step 3：启动开发服务器，视觉验证**

```bash
source venv/bin/activate
python manage.py runserver
```

打开浏览器，进入序列列表，选择包含 BPR-XXXX 原始序列的视图（或全项目视图）。确认：

1. 未被共享的序列：正常显示项目名，**无** pill
2. 被共享至 BPR-11 的序列：显示 `BPR-XXXX → BPR-11`（蓝色圆角标签）
3. 在 BPR-11 项目过滤视图下：该序列仍可见，项目列显示 `BPR-XXXX → BPR-11`

- [ ] **Step 4：Commit**

```bash
git add templates/_seq_group_row.html static/css/styles.css
git commit -m "feat: show shared-pill in sequence list for cross-project deliveries"
```
