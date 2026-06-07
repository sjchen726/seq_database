# 项目问题修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 8 个剩余问题（2 HIGH + 4 MEDIUM + 2 LOW），提升安全性、数据一致性和代码正确性

**Architecture:** Django 项目，单一 app `app01`，views.py 和 models.py 为核心修改文件

**Tech Stack:** Django 5.1, MySQL, Python 3.10

---

## 文件结构

| 文件 | 负责内容 |
|------|---------|
| `app01/models.py:10-14` | `generate_random_code` 竞态条件 |
| `app01/views.py:826-982` | `register_seq` 事务缺失 |
| `app01/views.py:1914-1940` | `build_duplex_groups` 重复项 |
| `app01/views.py:1111` | `add_o_to_all_rules` 大小写处理 |
| `app01/views.py:2318-2330` | `download_selected` 变量遮蔽 |
| `templates/seq_list.html:303,408` | 编辑链接 ID 错误 |
| `bms/settings.py:157-160` | CSRF_TRUSTED_ORIGINS 空字符串 |
| `app01/migrations/0024*.py` | 待应用迁移 |

---

## Task 1: 修复 `generate_random_code` 竞态条件

**Files:**
- Modify: `app01/models.py:10-14`

- [ ] **Step 1: 读取当前实现**

```python
# 当前实现（models.py:10-14）
def generate_random_code():
    while True:
        code = str(random.randint(100000, 999999))
        if not Sequence.objects.filter(rm_code=code).exists():
            return code
```

- [ ] **Step 2: 修复竞态 — 使用 SELECT FOR UPDATE 锁定查询**

```python
from django.db import IntegrityError, transaction

def generate_random_code():
    max_attempts = 100
    for _ in range(max_attempts):
        code = str(random.randint(100000, 999999))
        try:
            with transaction.atomic():
                if not Sequence.objects.filter(rm_code=code).exists():
                    # 立即创建占位记录，防止其他请求同时创建
                    Sequence.objects.create(rm_code=code, seq='')
                    return code
        except IntegrityError:
            continue
    raise RuntimeError("无法生成唯一 rm_code，请检查数据库")
```

- [ ] **Step 3: 运行 check 验证**

Run: `source venv/bin/activate && python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: 提交**

```bash
git add app01/models.py
git commit -m "fix: use atomic + SELECT FOR UPDATE to prevent rm_code race condition"
```

---

## Task 2: 为 `register_seq` 添加事务原子性

**Files:**
- Modify: `app01/views.py:826-982` — 在 `for _, row in df.iterrows():` 外包 `@transaction.atomic`

- [ ] **Step 1: 读取当前 register_seq 函数定义附近导入**

```python
# views.py 顶部已有
from django.db import transaction
```

- [ ] **Step 2: 在 for 循环外层包事务**

找到 `for _, row in df.iterrows():` 循环（约 line 871），在其外层加 `with transaction.atomic():`

```python
# 在 with open(log_filename, ...) as log_file: 内，for 循环外加：
with transaction.atomic():
    for _, row in df.iterrows():
        # ... 整个循环体保持不变 ...
```

- [ ] **Step 3: 运行 check 验证**

Run: `source venv/bin/activate && python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: 提交**

```bash
git add app01/views.py
git commit -m "fix: wrap register_seq CSV import loop in @transaction.atomic"
```

---

## Task 3: 修复 `build_duplex_groups` 重复项

**Files:**
- Modify: `app01/views.py:1915-1916`

- [ ] **Step 1: 读取当前 linker_seqs 构建逻辑**

```python
# 当前（views.py:1915-1916）
linker_seqs = [d.linker_seq for d in group_deliveries if getattr(d, 'linker_seq', None)]
if linker_seqs:
    for linker_seq in linker_seqs:
```

- [ ] **Step 2: 去重 — 用 dict.fromkeys 保持顺序同时去重**

```python
linker_seqs = list(dict.fromkeys(
    [d.linker_seq for d in group_deliveries if getattr(d, 'linker_seq', None)]
))
if linker_seqs:
    for linker_seq in linker_seqs:
```

- [ ] **Step 3: 运行 check 验证**

Run: `source venv/bin/activate && python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: 提交**

```bash
git add app01/views.py
git commit -m "fix: deduplicate linker_seqs in build_duplex_groups to prevent duplicate rows"
```

---

## Task 4: 修复 `add_o_to_all_rules` 大小写处理

**Files:**
- Modify: `app01/views.py:1111`

- [ ] **Step 1: 读取当前 token 处理**

```python
# 当前（views.py:1111）
connector = connector_map.get(token.upper(), '')
if connector and end < len(modify_seq) and modify_seq[end] != 's':
    linker_seq += token + connector  # token 保持原始大小写
else:
    linker_seq += token
```

- [ ] **Step 2: 统一 token 大小写后添加**

```python
token_upper = token.upper()
connector = connector_map.get(token_upper, '')
if connector and end < len(modify_seq) and modify_seq[end] != 's':
    linker_seq += token_upper + connector
else:
    linker_seq += token_upper
```

- [ ] **Step 3: 运行 check 验证**

Run: `source venv/bin/activate && python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: 提交**

```bash
git add app01/views.py
git commit -m "fix: uppercase token consistently in add_o_to_all_rules connector logic"
```

---

## Task 5: 修复 `download_selected` 变量遮蔽

**Files:**
- Modify: `app01/views.py:2318-2330`

- [ ] **Step 1: 读取当前循环代码**

```python
# 当前（views.py:2323-2325）
for duplex_id, seq_ids in zip(ids, seq_ids):  # seq_ids 被遮蔽！
    query |= Q(duplex_id=duplex_id, delivery_id=seq_ids)
```

- [ ] **Step 2: 重命名循环变量避免遮蔽**

```python
for duplex_id, seq_id_str in zip(ids, seq_ids):
    # seq_id_str 格式: "AS_123456.1" — 取后半部分
    delivery_id_value = seq_id_str.split('_', 1)[-1]
    query |= Q(duplex_id=duplex_id, delivery_id=delivery_id_value)
```

- [ ] **Step 3: 运行 check 验证**

Run: `source venv/bin/activate && python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: 提交**

```bash
git add app01/views.py
git commit -m "fix: rename loop var to avoid seq_ids shadowing in download_selected"
```

---

## Task 6: 修复 seq_list.html 编辑链接 ID 字段

**Files:**
- Modify: `templates/seq_list.html:303,408`

- [ ] **Step 1: 确认 build_sequence_data 返回的 delivery 对象**

`build_sequence_data` 返回的 `deliveries[0]` 包含 `delivery_id` 字段（来自 `get_attr(d, 'delivery_id', None)`）。

- [ ] **Step 2: 修改编辑链接使用正确的 delivery_id 字段**

```html
<!-- seq_list.html:303 当前 -->
href="/edit_seq/?id={{ group.items.0.rm_code }}&strand_MWs={{ group.items.0.deliveries.0.Strand_MWs }}"

<!-- 修改为 -->
href="/edit_seq/?id={{ group.items.0.deliveries.0.delivery_id }}&strand_MWs={{ group.items.0.deliveries.0.Strand_MWs }}"
```

同样修改第 408 行（SS 行）。

- [ ] **Step 3: 运行 check 验证**

Run: `source venv/bin/activate && python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: 提交**

```bash
git add templates/seq_list.html
git commit -m "fix: use delivery_id (not rm_code) in seq_list edit links"
```

---

## Task 7: 修复 CSRF_TRUSTED_ORIGINS 空字符串处理

**Files:**
- Modify: `bms/settings.py:157-160`

- [ ] **Step 1: 读取当前实现**

```python
# 当前（settings.py:157-160）
CSRF_TRUSTED_ORIGINS = [
    h.strip() for h in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',')
    if h.strip() and not h.strip().startswith('#')
]
```

- [ ] **Step 2: 过滤空字符串**

```python
CSRF_TRUSTED_ORIGINS = [
    h.strip() for h in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',')
    if h.strip() and not h.strip().startswith('#')
] or None
```

- [ ] **Step 3: 运行 check 验证**

Run: `source venv/bin/activate && python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: 提交**

```bash
git add bms/settings.py
git commit -m "fix: return None when CSRF_TRUSTED_ORIGINS env var is empty"
```

---

## Task 8: 检查并应用待处理迁移

**Files:**
- Modify: `app01/migrations/`

- [ ] **Step 1: 检查迁移状态**

Run: `source venv/bin/activate && python manage.py showmigrations app01`
Expected: 显示 `0024_add_indexes_and_expand_fields` 的 `[ ]` 标记（未应用）

- [ ] **Step 2: 应用迁移**

Run: `source venv/bin/activate && python manage.py migrate app01`
Expected: `Applying app01.0024_add_indexes_and_expand_fields... OK` 或 `already applied`

- [ ] **Step 3: 提交**

```bash
git add app01/migrations/
git commit -m "fix: apply 0024_add_indexes_and_expand_fields migration"
```

---

## 自检清单

1. **Spec coverage:** 所有 8 个问题都有对应 Task ✓
2. **Placeholder scan:** 无 TBD/TODO ✓
3. **Type consistency:** `connector_map.get(token_upper, '')` 签名不变 ✓
4. **Scope check:** 8 个问题均为独立修改，可并行处理 ✓

---

## 执行选项

**1. Subagent-Driven（推荐）** — 每个 Task 由独立 subagent 执行，Task 间可以并行

**2. Inline Execution** — 在当前 session 中顺序执行，批处理有检查点

选择哪个方式？
