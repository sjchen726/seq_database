# 全项目 Bug 修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 5 个波次修复全项目代码审计发现的 11 处问题，消除崩溃、逻辑缺陷、安全隐患和代码冗余。

**Architecture:** 所有改动在现有单文件 views.py / models.py / settings.py 上就地修改，无新模块引入（除 python-decouple）。Migration 编号 0029-0032 顺序执行，每个波次独立可测试。

**Tech Stack:** Django 5.1, Python 3.10, MySQL, python-decouple（新增 Wave 4）

---

## 文件结构

| 文件 | 任务 | 改动类型 |
|------|------|---------|
| `app01/migrations/0029_drop_seqmodule_type_code.py` | T1 | 新建 |
| `app01/migrations/0030_naked_length_to_integer.py` | T7 | 新建 |
| `app01/migrations/0031_sequence_unique_seq_seqtype.py` | T8 | 新建 |
| `app01/migrations/0032_sequence_seq_maxlen.py` | T9 | 新建 |
| `app01/models.py` | T7, T8, T9 | 修改 |
| `app01/views.py` | T2, T3, T4, T5, T6, T11, T12 | 修改 |
| `bms/settings.py` | T10 | 修改 |
| `.env.example` | T10 | 新建 |
| `.gitignore` | T10 | 修改 |
| `requirements.txt` | T10 | 修改 |

---

## Wave 1 — 止血

---

### Task 1: C1 — DROP SeqModule 遗留 type_code 列

**背景：** `app01_seqmodule` 表存在一个 `type_code` 列（NOT NULL，无默认值），但 Django 模型中已无此字段。每次新建 SeqModule 时，MySQL 要求该列有值，触发 `OperationalError (1364)`。

**Files:**
- Create: `app01/migrations/0029_drop_seqmodule_type_code.py`

- [ ] **Step 1: 确认列确实存在**

```bash
source venv/bin/activate
python manage.py dbshell
```

在 MySQL shell 中执行：
```sql
SHOW COLUMNS FROM app01_seqmodule;
```

预期输出包含 `type_code` 列。确认后 `\q` 退出。

- [ ] **Step 2: 创建 migration 文件**

创建 `app01/migrations/0029_drop_seqmodule_type_code.py`，内容如下：

```python
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('app01', '0028_seqmodule_base_char_maxlen'),
    ]
    operations = [
        migrations.RunSQL(
            sql='ALTER TABLE app01_seqmodule DROP COLUMN IF EXISTS type_code;',
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
```

- [ ] **Step 3: 运行 migration**

```bash
python manage.py migrate app01 0029
```

预期输出：
```
Applying app01.0029_drop_seqmodule_type_code... OK
```

- [ ] **Step 4: 验证修复**

启动开发服务器：
```bash
python manage.py runserver
```

浏览器打开 `/edit_seqmodule/`，填写 Keyword 和 Linker Connector，点击「创建」。确认不报 OperationalError，页面跳转到列表且新记录可见。

- [ ] **Step 5: Commit**

```bash
git add app01/migrations/0029_drop_seqmodule_type_code.py
git commit -m "fix: drop legacy type_code column from app01_seqmodule via migration

The column existed in DB but was removed from the Django model,
causing OperationalError on every SeqModule INSERT.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 2: I1 — linkermodule_list 加 @login_required

**背景：** `linkermodule_list` 视图（`views.py:4762`）缺少 `@login_required` 装饰器，未登录用户可直接访问 `/linkermodule_list/`。

**Files:**
- Modify: `app01/views.py:4762`

- [ ] **Step 1: 确认缺少装饰器**

```bash
grep -n "def linkermodule_list\|login_required" app01/views.py | grep -A2 "linkermodule_list"
```

预期：显示 `def linkermodule_list(request):` 行，其上方无 `@login_required`。

- [ ] **Step 2: 添加装饰器**

在 `views.py` 中，找到 `def linkermodule_list(request):` 所在行（约 4762 行），在其正上方添加 `@login_required`。

修改前：
```python
def linkermodule_list(request):
    page_size = int(request.GET.get('page_size', 20))
```

修改后：
```python
@login_required
def linkermodule_list(request):
    page_size = int(request.GET.get('page_size', 20))
```

- [ ] **Step 3: 验证修复**

1. 在浏览器中退出登录（或使用隐私模式）
2. 直接访问 `/linkermodule_list/`
3. 预期：302 重定向到登录页（`/login/?next=/linkermodule_list/`）

- [ ] **Step 4: Commit**

```bash
git add app01/views.py
git commit -m "fix: add @login_required to linkermodule_list view

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Wave 2 — 代码逻辑修复

---

### Task 3: C3 — 消除 save_deliveries N+1 查询

**背景：** `save_deliveries()` 的内循环（`views.py:1873` 和 `1899`）对每行数据各执行一次 Sequence DB 查询。上传 50 行 = 100 次额外查询。优化为每个 duplex 组只查一次。

**Files:**
- Modify: `app01/views.py:1863-1899`

- [ ] **Step 1: 理解现有结构**

阅读 `views.py` 约 1828-1900 行，确认以下双查询模式：
- 行 ~1873：`if not Sequence.objects.filter(seq=naked_seq).exists():`（第一个内循环内）
- 行 ~1899：`sequence_obj = Sequence.objects.get(seq=item['naked_seq'])`（第二个内循环内）

- [ ] **Step 2: 将 DB 查询移出内循环**

将 `views.py` 中以下代码段：

```python
            detailed_rows.append({
                'row': row,
                'full_seq': full_seq,
                'delivery5': delivery5,
                'delivery3': delivery3,
                'modify_seq': modify_seq,
                'naked_seq': naked_seq,
                'naked_length': naked_length
            })

            if not Sequence.objects.filter(seq=naked_seq).exists():
                all_registered = False

                # 更稳妥地计算当前组的原始行号列表
                group_lines = ",".join(str(r['__original_line']) for r in rows)

                unregistered_meg.append(f"{row['Project']} ➜ {full_seq} ➜ {naked_seq}")
                unregistered_log.append({
                    'Project': row['Project'],
                    'duplex_id': duplex_id,
                    '行号组': group_lines,
                    'origin_line': row['__original_line'],
                    'Modify_seq': full_seq,
                    'Unregistered': naked_seq,
                    '原因': '组内存在未注册序列，整组未上传'
                })

        if not all_registered:
            # 如果整组未注册，跳过后续处理
            continue

        seen_combinations = {}  # key: (base_id, delivery5, linker_seq, delivery3) → delivery_id

        # 处理每个详细行
        for item in detailed_rows:
            row = item['row']
            sequence_obj = Sequence.objects.get(seq=item['naked_seq'])
```

替换为：

```python
            detailed_rows.append({
                'row': row,
                'full_seq': full_seq,
                'delivery5': delivery5,
                'delivery3': delivery3,
                'modify_seq': modify_seq,
                'naked_seq': naked_seq,
                'naked_length': naked_length
            })

        # ── 批量查询本组所有裸序列（1 次 DB 查询代替 N 次）──
        _naked_seqs = [item['naked_seq'] for item in detailed_rows]
        _seq_cache = {s.seq: s for s in Sequence.objects.filter(seq__in=_naked_seqs)}

        for item in detailed_rows:
            if item['naked_seq'] not in _seq_cache:
                all_registered = False
                group_lines = ",".join(str(r['__original_line']) for r in rows)
                unregistered_meg.append(f"{item['row']['Project']} ➜ {item['full_seq']} ➜ {item['naked_seq']}")
                unregistered_log.append({
                    'Project': item['row']['Project'],
                    'duplex_id': duplex_id,
                    '行号组': group_lines,
                    'origin_line': item['row']['__original_line'],
                    'Modify_seq': item['full_seq'],
                    'Unregistered': item['naked_seq'],
                    '原因': '组内存在未注册序列，整组未上传'
                })

        if not all_registered:
            # 如果整组未注册，跳过后续处理
            continue

        seen_combinations = {}  # key: (base_id, delivery5, linker_seq, delivery3) → delivery_id

        # 处理每个详细行
        for item in detailed_rows:
            row = item['row']
            sequence_obj = _seq_cache[item['naked_seq']]
```

注意：修改后第二个内循环开头的 `row = item['row']` 保留不变，`sequence_obj = Sequence.objects.get(...)` 换成 `sequence_obj = _seq_cache[item['naked_seq']]`。

- [ ] **Step 3: 验证修复**

启动服务器，上传一个包含 5 对序列的 CSV（10 行）。通过 Django shell 确认只触发一次 Sequence 查询：

```python
# 临时在 save_deliveries 函数开头插入计数器（验证后删除）
from django.db import connection, reset_queries
from django.conf import settings
settings.DEBUG = True
reset_queries()
# 运行上传…
print(len([q for q in connection.queries if 'app01_sequence' in q['sql']]))
# 预期：查询次数 = 组数（不是行数）
```

或者：直接检查逻辑正确性——上传后确认所有行均正常创建 Delivery 记录。

- [ ] **Step 4: Commit**

```bash
git add app01/views.py
git commit -m "perf: batch Sequence queries in save_deliveries (eliminate N+1)

Before: 2 DB queries per row in the duplex group loop.
After: 1 bulk query per duplex group.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 4: C4 — 删除 auto_register_bare_sequences 中的死代码

**背景：** `views.py:1541` 和 `1549` 对 `get_or_create()` 的返回值做了 `if ss_obj is None:` 判断。`get_or_create()` 成功时永远返回对象实例，失败时抛异常，永远不返回 `None`。这两个 `if` 是死代码，且掩盖了真实错误路径。

**Files:**
- Modify: `app01/views.py:1541-1550`

- [ ] **Step 1: 定位死代码**

```bash
grep -n "if ss_obj is None\|if as_obj is None" app01/views.py
```

预期输出：
```
1541:                if ss_obj is None:
1542:                    raise ValueError(...)
1549:                if as_obj is None:
1550:                    raise ValueError(...)
```

- [ ] **Step 2: 删除死代码**

将以下代码段（`views.py:1537-1550`）：

```python
                ss_obj, ss_created = Sequence.objects.get_or_create(
                    seq=naked_ss, seq_type='SS',
                    defaults={'created_at': created_at},
                )
                if ss_obj is None:
                    raise ValueError(f"SS sequence not found in DB: seq={naked_ss!r}")

                # ── AS ──
                as_obj, as_created = Sequence.objects.get_or_create(
                    seq=naked_as, seq_type='AS',
                    defaults={'created_at': created_at},
                )
                if as_obj is None:
                    raise ValueError(f"AS sequence not found in DB: seq={naked_as!r}")
```

替换为：

```python
                ss_obj, ss_created = Sequence.objects.get_or_create(
                    seq=naked_ss, seq_type='SS',
                    defaults={'created_at': created_at},
                )

                # ── AS ──
                as_obj, as_created = Sequence.objects.get_or_create(
                    seq=naked_as, seq_type='AS',
                    defaults={'created_at': created_at},
                )
```

注意：`get_or_create` 失败时会抛 `IntegrityError`，已被外层 `try/except` 捕获（`views.py:1530`），无需额外判断。

- [ ] **Step 3: 验证**

```bash
python manage.py shell
```

```python
from app01.views import auto_register_bare_sequences
# 测试正常路径（使用已存在的序列）
result = auto_register_bare_sequences([], 'testuser')
print(result)  # 应返回 ([], [])，无报错
```

- [ ] **Step 4: Commit**

```bash
git add app01/views.py
git commit -m "fix: remove dead None-check after get_or_create in auto_register_bare_sequences

get_or_create() never returns None on success; it raises on failure.
The if-None branches were unreachable and masked real error paths.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 5: I2 — 细化 confirm_upload_preflight 异常捕获

**背景：** `views.py:2484` 的顶层 `except Exception as e:` 吞掉所有异常，只输出 `str(e)` 给用户，完整堆栈丢失，无法诊断问题。

**Files:**
- Modify: `app01/views.py:2484-2488`

- [ ] **Step 1: 定位现有代码**

```bash
grep -n "except Exception" app01/views.py | awk -F: '$1 >= 2480 && $1 <= 2495'
```

预期输出：
```
2484:        except Exception as e:
```

- [ ] **Step 2: 替换为分层异常处理**

将 `views.py` 中（约 2484-2488 行）：

```python
        except Exception as e:
            messages.error(request, f"文件处理失败：{e}")
            for key in ['preflight_result', 'preflight_df_json', 'preflight_clean_groups', 'preflight_skip_csv_path']:
                request.session.pop(key, None)
            return render(request, 'upload_delivery_info.html')
```

替换为：

```python
        except KeyError as e:
            messages.error(request, f"会话数据损坏，请重新上传文件（缺少字段: {e}）")
            for key in ['preflight_result', 'preflight_df_json', 'preflight_clean_groups', 'preflight_skip_csv_path']:
                request.session.pop(key, None)
            return render(request, 'upload_delivery_info.html')
        except (json.JSONDecodeError, ValueError) as e:
            messages.error(request, f"数据解析失败，请重新上传文件：{e}")
            for key in ['preflight_result', 'preflight_df_json', 'preflight_clean_groups', 'preflight_skip_csv_path']:
                request.session.pop(key, None)
            return render(request, 'upload_delivery_info.html')
        except Exception as e:
            _logger = logging.getLogger('edit_book_log')
            _logger.exception("confirm_upload_preflight 未预期错误")
            messages.error(request, f"文件处理失败，请联系管理员：{e}")
            for key in ['preflight_result', 'preflight_df_json', 'preflight_clean_groups', 'preflight_skip_csv_path']:
                request.session.pop(key, None)
            return render(request, 'upload_delivery_info.html')
```

注意：`logging` 已在 `views.py` 顶部 `import logging`（第 26 行）。

- [ ] **Step 3: 验证**

触发一个 KeyError（可在本地临时在处理块开头插入 `raise KeyError('test_field')` 然后提交 preflight 表单），确认页面显示「会话数据损坏，请重新上传文件（缺少字段: 'test_field'）」而不是通用错误。验证后删除测试代码。

- [ ] **Step 4: Commit**

```bash
git add app01/views.py
git commit -m "fix: add specific exception handlers in confirm_upload_preflight

- KeyError: session data corruption message
- JSONDecodeError/ValueError: data parsing message
- Generic Exception: log full traceback via edit_book_log logger

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 6: I3 — confirm_share_deliveries 加事务保护

**背景：** `confirm_share_deliveries`（`views.py:2211`）的 POST 分支执行多步写操作（`DeliveryProject.get_or_create` + `save_deliveries`），无事务保护，中途失败会留脏数据。

**Files:**
- Modify: `app01/views.py:2220-2260`（confirm_share_deliveries POST 分支）

- [ ] **Step 1: 定位写操作块**

读取 `views.py` 约 2220-2265 行，确认写操作在 `if request.method == 'POST':` 分支内，且无 `transaction.atomic()`。

- [ ] **Step 2: 用 transaction.atomic 包裹写操作**

找到 `confirm_share_deliveries` POST 分支中的写操作块，用 `with transaction.atomic():` 包裹。具体地，将：

```python
    if request.method == 'POST':
        from .models import DeliveryProject
        import pandas as pd

        pending = request.session.pop('pending_shares', [])
        pending_df_json = request.session.pop('pending_upload_df', None)
        pending_repeated_ids = request.session.pop('pending_repeated_ids', [])
        request.session.pop('pending_unpaired', None)  # clean up session key

        choices = request.POST.getlist('action')
        shared_count = 0
        for i, item in enumerate(pending):
            action = choices[i] if i < len(choices) else 'skip'
            if action == 'share':
                # Share all deliveries in the duplex (SS + AS), not just the SS strand
                duplex_id = item['existing_duplex_id']
                target_proj = item['target_project']
                for d in Delivery.objects.filter(duplex_id=duplex_id):
                    DeliveryProject.objects.get_or_create(
                        delivery_id=d.id,
                        project_code=target_proj,
                    )
                shared_count += 1

        if pending_df_json:
            df = pd.read_json(pending_df_json)
            if not df.empty:
                ss_groups, _ = group_sequences(df)
                repeated_ids, _, _ = check_duplicates(df, ss_groups)
                repeated_ids.update(pending_repeated_ids)
                duplex_id_map = assign_duplex_ids(df, ss_groups, repeated_ids)
                username = request.user.username
                upload_meg, upload_log, unregistered_meg, unregistered_log = save_deliveries(
                    df, duplex_id_map, username
                )
                write_upload_log(upload_log, username)
                write_unregistered_log(unregistered_log, username)
                if upload_meg:
                    messages.success(request, f"共 {len(upload_meg)} 条序列成功上传！")

        skip_count = len(pending) - shared_count
        messages.success(request, f"成功共享 {shared_count} 条，跳过 {skip_count} 条。")
        return redirect('seq_delivery')
```

替换为：

```python
    if request.method == 'POST':
        from .models import DeliveryProject
        import pandas as pd

        pending = request.session.pop('pending_shares', [])
        pending_df_json = request.session.pop('pending_upload_df', None)
        pending_repeated_ids = request.session.pop('pending_repeated_ids', [])
        request.session.pop('pending_unpaired', None)  # clean up session key

        choices = request.POST.getlist('action')
        shared_count = 0

        with transaction.atomic():
            for i, item in enumerate(pending):
                action = choices[i] if i < len(choices) else 'skip'
                if action == 'share':
                    # Share all deliveries in the duplex (SS + AS), not just the SS strand
                    duplex_id = item['existing_duplex_id']
                    target_proj = item['target_project']
                    for d in Delivery.objects.filter(duplex_id=duplex_id):
                        DeliveryProject.objects.get_or_create(
                            delivery_id=d.id,
                            project_code=target_proj,
                        )
                    shared_count += 1

            if pending_df_json:
                df = pd.read_json(pending_df_json)
                if not df.empty:
                    ss_groups, _ = group_sequences(df)
                    repeated_ids, _, _ = check_duplicates(df, ss_groups)
                    repeated_ids.update(pending_repeated_ids)
                    duplex_id_map = assign_duplex_ids(df, ss_groups, repeated_ids)
                    username = request.user.username
                    upload_meg, upload_log, unregistered_meg, unregistered_log = save_deliveries(
                        df, duplex_id_map, username
                    )
                    write_upload_log(upload_log, username)
                    write_unregistered_log(unregistered_log, username)
                    if upload_meg:
                        messages.success(request, f"共 {len(upload_meg)} 条序列成功上传！")

        skip_count = len(pending) - shared_count
        messages.success(request, f"成功共享 {shared_count} 条，跳过 {skip_count} 条。")
        return redirect('seq_delivery')
```

注意：`transaction` 已在 `views.py` 顶部 `from django.db import IntegrityError, transaction`（第 17 行）。

- [ ] **Step 3: 验证**

正常流程测试：上传一批与已有 duplex 重复的序列，触发 `confirm_share` 页面，选择「共享」并确认。确认 DeliveryProject 记录正确创建，页面跳转正常。

- [ ] **Step 4: Commit**

```bash
git add app01/views.py
git commit -m "fix: wrap confirm_share_deliveries writes in transaction.atomic

Prevents partial writes if DeliveryProject creation or save_deliveries
fails mid-operation.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Wave 3 — Schema Migration

---

### Task 7: I5 — naked_length CharField → IntegerField

**背景：** `Delivery.naked_length`（`models.py:79`）声明为 `CharField`，但存储数字。字符串排序导致 "9" > "10"，排序逻辑错误。

**Files:**
- Create: `app01/migrations/0030_naked_length_to_integer.py`
- Modify: `app01/models.py:79`

- [ ] **Step 1: 查看现有字段定义**

```bash
grep -n "naked_length" app01/models.py
```

预期：
```
79:    naked_length = models.CharField('Naked Length', max_length=100, null=True)
```

- [ ] **Step 2: 创建数据迁移 + 字段类型变更 migration**

创建 `app01/migrations/0030_naked_length_to_integer.py`：

```python
from django.db import migrations, models


def convert_naked_length_to_int(apps, schema_editor):
    """将 naked_length 字符串值转为整数（无法转换的设为 NULL）。"""
    Delivery = apps.get_model('app01', 'Delivery')
    for d in Delivery.objects.filter(naked_length__isnull=False).exclude(naked_length=''):
        try:
            int_val = int(float(d.naked_length))
            # 用 queryset update 避免触发信号
            Delivery.objects.filter(pk=d.pk).update(naked_length=str(int_val))
        except (ValueError, TypeError):
            Delivery.objects.filter(pk=d.pk).update(naked_length=None)


class Migration(migrations.Migration):
    dependencies = [
        ('app01', '0029_drop_seqmodule_type_code'),
    ]
    operations = [
        # Step A: 数据迁移（字符串 → 整数字符串，清除非法值）
        migrations.RunPython(convert_naked_length_to_int, migrations.RunPython.noop),
        # Step B: 字段类型变更
        migrations.AlterField(
            model_name='delivery',
            name='naked_length',
            field=models.IntegerField(verbose_name='Naked Length', null=True, blank=True),
        ),
    ]
```

- [ ] **Step 3: 更新 models.py**

将 `app01/models.py:79`：

```python
    naked_length = models.CharField('Naked Length', max_length=100, null=True)  # Naked Length
```

改为：

```python
    naked_length = models.IntegerField('Naked Length', null=True, blank=True)  # Naked Length
```

- [ ] **Step 4: 运行 migration**

```bash
python manage.py migrate app01 0030
```

预期输出：
```
Applying app01.0030_naked_length_to_integer... OK
```

- [ ] **Step 5: 验证**

```bash
python manage.py shell
```

```python
from app01.models import Delivery
# 确认字段类型正确
d = Delivery.objects.filter(naked_length__isnull=False).first()
print(type(d.naked_length))  # 应为 <class 'int'>

# 确认排序正确（9 < 10）
lengths = list(Delivery.objects.order_by('naked_length').values_list('naked_length', flat=True)[:10])
print(lengths)  # 应为升序整数列表
```

- [ ] **Step 6: Commit**

```bash
git add app01/migrations/0030_naked_length_to_integer.py app01/models.py
git commit -m "fix: convert Delivery.naked_length from CharField to IntegerField

Data migration converts existing string values to integers.
Fixes incorrect string-based sorting ('9' > '10').

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 8: I6 — Sequence (seq, seq_type) 唯一约束（含清重）

**背景：** `Sequence` 表缺少 `(seq, seq_type)` 联合唯一约束，理论上可插入重复组合。需先清理现有重复记录（保留最小 rm_code），再加约束。

**Files:**
- Create: `app01/migrations/0031_sequence_unique_seq_seqtype.py`
- Modify: `app01/models.py`（Sequence.Meta）

- [ ] **Step 1: 检查是否存在重复记录**

```bash
python manage.py shell
```

```python
from django.db.models import Count
from app01.models import Sequence

dupes = (Sequence.objects
    .values('seq', 'seq_type')
    .annotate(cnt=Count('rm_code'))
    .filter(cnt__gt=1))
print(f"重复组数：{dupes.count()}")
for d in dupes[:5]:
    print(d)
```

如无重复（count=0），Step 2 的 RunPython 仍会安全执行（无操作）。

- [ ] **Step 2: 创建 migration**

创建 `app01/migrations/0031_sequence_unique_seq_seqtype.py`：

```python
from django.db import migrations, models
from django.db.models import Count


def remove_duplicate_sequences(apps, schema_editor):
    """保留每组 (seq, seq_type) 中 rm_code 最小的记录，删除其余。级联删除关联数据。"""
    Sequence = apps.get_model('app01', 'Sequence')

    dupes = (Sequence.objects
        .values('seq', 'seq_type')
        .annotate(cnt=Count('rm_code'))
        .filter(cnt__gt=1))

    total_deleted = 0
    for d in dupes:
        qs = list(
            Sequence.objects
            .filter(seq=d['seq'], seq_type=d['seq_type'])
            .order_by('rm_code')
        )
        to_delete = qs[1:]  # 保留第一条（rm_code 最小），删其余
        for obj in to_delete:
            print(f"[migration] 删除重复 Sequence: rm_code={obj.rm_code}, seq_type={obj.seq_type}")
            obj.delete()  # 级联删除 Delivery、DuplexRelationship、SeqInfo
            total_deleted += 1

    print(f"[migration] 共删除 {total_deleted} 条重复 Sequence 记录")


class Migration(migrations.Migration):
    dependencies = [
        ('app01', '0030_naked_length_to_integer'),
    ]
    operations = [
        # Step A: 清重
        migrations.RunPython(remove_duplicate_sequences, migrations.RunPython.noop),
        # Step B: 加唯一约束
        migrations.AddConstraint(
            model_name='sequence',
            constraint=models.UniqueConstraint(
                fields=['seq', 'seq_type'],
                name='unique_sequence_seq_seqtype',
            ),
        ),
    ]
```

- [ ] **Step 3: 更新 models.py 的 Sequence.Meta**

找到 `Sequence` 的 `Meta` 类（约 29-34 行），添加 `constraints`：

修改前：
```python
    class Meta:
        indexes = [
            models.Index(fields=['seq']),  # 加快查询速度
            models.Index(fields=['seq_type']),
            models.Index(fields=['seq', 'seq_type'], name='idx_sequence_seq_seqtype'),
        ]
```

修改后：
```python
    class Meta:
        indexes = [
            models.Index(fields=['seq']),  # 加快查询速度
            models.Index(fields=['seq_type']),
            models.Index(fields=['seq', 'seq_type'], name='idx_sequence_seq_seqtype'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['seq', 'seq_type'],
                name='unique_sequence_seq_seqtype',
            ),
        ]
```

- [ ] **Step 4: 运行 migration**

```bash
python manage.py migrate app01 0031
```

预期输出（无重复时）：
```
[migration] 共删除 0 条重复 Sequence 记录
Applying app01.0031_sequence_unique_seq_seqtype... OK
```

如有重复，会打印每条被删除的记录。

- [ ] **Step 5: 验证**

```bash
python manage.py shell
```

```python
from django.db import IntegrityError
from app01.models import Sequence

# 尝试插入重复记录（应抛 IntegrityError）
try:
    existing = Sequence.objects.first()
    Sequence.objects.create(seq=existing.seq, seq_type=existing.seq_type)
    print("ERROR: 未抛出 IntegrityError！")
except IntegrityError as e:
    print(f"OK: IntegrityError 正确触发: {e}")
```

- [ ] **Step 6: Commit**

```bash
git add app01/migrations/0031_sequence_unique_seq_seqtype.py app01/models.py
git commit -m "fix: add unique constraint on Sequence(seq, seq_type) with dedup migration

Migration first removes duplicate records (keeping smallest rm_code),
then adds UniqueConstraint to prevent future duplicates.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 9: M3 — Sequence.seq max_length 扩展

**背景：** `Sequence.seq` 当前 `max_length=100`。双链序列（如 duplex 类型）拼接后可能超出，导致 DataError。

**Files:**
- Create: `app01/migrations/0032_sequence_seq_maxlen.py`
- Modify: `app01/models.py:25`

- [ ] **Step 1: 创建 migration**

创建 `app01/migrations/0032_sequence_seq_maxlen.py`：

```python
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('app01', '0031_sequence_unique_seq_seqtype'),
    ]
    operations = [
        migrations.AlterField(
            model_name='sequence',
            name='seq',
            field=models.CharField('Sequence', max_length=500, null=True),
        ),
    ]
```

- [ ] **Step 2: 更新 models.py**

将 `app01/models.py:25`：

```python
    seq = models.CharField('Sequence', max_length=100, null=True)  # 存储序列（如 AUGC）
```

改为：

```python
    seq = models.CharField('Sequence', max_length=500, null=True)  # 存储序列（如 AUGC）
```

- [ ] **Step 3: 运行 migration**

```bash
python manage.py migrate app01 0032
```

预期输出：
```
Applying app01.0032_sequence_seq_maxlen... OK
```

- [ ] **Step 4: 验证**

```bash
python manage.py shell
```

```python
from app01.models import Sequence
# 插入一条长度 > 100 的序列（测试用，之后删除）
long_seq = 'A' * 150
s = Sequence(seq=long_seq, seq_type='SS')
s.save()
print(f"OK: 插入 {len(long_seq)} 字符序列成功")
s.delete()
```

- [ ] **Step 5: Commit**

```bash
git add app01/migrations/0032_sequence_seq_maxlen.py app01/models.py
git commit -m "fix: expand Sequence.seq max_length from 100 to 500

Duplex sequences (formatted as 'AS_seq, SS_seq') can exceed 100 chars.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Wave 4 — 配置安全

---

### Task 10: I4 — 敏感配置移入 .env

**背景：** `bms/settings.py:22` 和 `81` 明文存储 `SECRET_KEY` 和 MySQL 密码，已通过版本控制暴露。引入 `python-decouple` 将敏感值移至 `.env` 文件。

**Files:**
- Modify: `bms/settings.py`
- Modify: `requirements.txt`
- Modify: `.gitignore`
- Create: `.env.example`
- Create: `.env`（本地，不提交）

- [ ] **Step 1: 安装 python-decouple**

```bash
pip install python-decouple
```

- [ ] **Step 2: 更新 requirements.txt**

在 `requirements.txt` 末尾添加一行：
```
python-decouple==3.8
```

- [ ] **Step 3: 确认 .gitignore 包含 .env**

```bash
grep "^\.env" .gitignore
```

如无输出，在 `.gitignore` 末尾添加：
```
.env
```

- [ ] **Step 4: 创建 .env.example**

创建项目根目录下的 `.env.example`（提交到版本库，值为占位符）：

```ini
# SeqDB 环境配置示例 — 复制为 .env 并填入真实值
SECRET_KEY=your-django-secret-key-here
DB_PASSWORD=your-mysql-password-here
```

- [ ] **Step 5: 创建本地 .env（不提交）**

创建项目根目录下的 `.env`（仅本地，`.gitignore` 已排除）：

```ini
SECRET_KEY=django-insecure-92c13l2f(48bjnt0bo&dqp89g_og&8x7bugq0=(4l2@#5%cdta
DB_PASSWORD=Bt123456
```

注意：将上述值替换为当前 `settings.py` 中的实际值（`SECRET_KEY` 第 22 行，`DB_PASSWORD` 第 81 行）。

- [ ] **Step 6: 更新 settings.py**

在 `bms/settings.py` 顶部，将：

```python
import os
from pathlib import Path
```

替换为：

```python
import os
from pathlib import Path
from decouple import config
```

然后，将：

```python
SECRET_KEY = 'django-insecure-92c13l2f(48bjnt0bo&dqp89g_og&8x7bugq0=(4l2@#5%cdta'
```

替换为：

```python
SECRET_KEY = config('SECRET_KEY')
```

再将 DATABASES 中：

```python
        'PASSWORD': 'Bt123456',  # 数据库密码
        #'PASSWORD': 'BTYY.com@db',  # 数据库密码
```

替换为：

```python
        'PASSWORD': config('DB_PASSWORD'),  # 数据库密码
```

- [ ] **Step 7: 验证**

```bash
python manage.py check
```

预期：`System check identified no issues (0 silenced).`

再验证 .env 读取有效：

```bash
python manage.py shell -c "from django.conf import settings; print(settings.SECRET_KEY[:10])"
```

预期：打印 `SECRET_KEY` 前 10 字符（非空）。

- [ ] **Step 8: Commit**

```bash
git add requirements.txt .gitignore .env.example bms/settings.py
git commit -m "security: move SECRET_KEY and DB_PASSWORD to .env via python-decouple

Adds .env.example as template. .env is gitignored.
Servers need to create .env before restarting Django.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Wave 5 — 代码整洁

---

### Task 11: M1 — 删除注释掉的 print 语句

**背景：** `views.py` 中有 7 处注释掉的调试 `print` 语句（行 422, 425, 1843, 1846, 1851, 1908, 1909），降低可读性。

**Files:**
- Modify: `app01/views.py:422,425,1843,1846,1851,1908,1909`

- [ ] **Step 1: 定位所有注释 print**

```bash
grep -n "# print(" app01/views.py
```

预期输出（7 行）：
```
422:    # print(raw_premissions_projects)
425:    # print(new_author_permissions_project)
1843:      #      print(d5)
1846:       #     print(d3)
1851:         #   print(f"Processing row: ...")
1908:            # print(f"Key for this item: {key}")  # 调试输出
1909:            # print(f"Seen combinations so far: {seen_combinations}")  # 调试输出
```

- [ ] **Step 2: 逐行删除**

打开 `app01/views.py`，删除以上 7 行（整行删除，不留空行残留）。每行删除时确认上下文逻辑不受影响（这些都是独立注释行，无相邻依赖）。

- [ ] **Step 3: 验证无遗漏**

```bash
grep -n "# print(" app01/views.py
```

预期：无输出。

- [ ] **Step 4: Commit**

```bash
git add app01/views.py
git commit -m "chore: remove commented-out debug print statements from views.py

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 12: M2 — 提取 URL query string 拼接 helper

**背景：** `edit_seqmodule`、`delete_seqmodule`、`edit_linkermodule`、`delete_linkermodule` 四个视图中各重复一次相同的 `?page=X&q=Y` 拼接逻辑，应提取为 helper 函数。

**Files:**
- Modify: `app01/views.py`（helper 函数 + 4 处调用点）

- [ ] **Step 1: 确认 4 处重复代码**

```bash
grep -n "qs = f'?page=" app01/views.py
```

预期：找到 4 处（edit_seqmodule, delete_seqmodule, edit_linkermodule, delete_linkermodule）。

- [ ] **Step 2: 在 views.py 顶部 helper 区添加函数**

在 `views.py` 中，找到靠近顶部的 helper 函数区域（如第一个 `def` 之前，或在 `import` 块之后的适当位置），添加：

```python
def _module_list_url(base: str, page, q: str) -> str:
    """构建带 page/q 参数的模块列表页 redirect URL。"""
    qs = f'?page={page}'
    if q:
        qs += f'&q={urllib.parse.quote(str(q))}'
    return f'{base}{qs}'
```

注意：`urllib.parse` 已在 `views.py:25` 导入（`import urllib.parse`）。

- [ ] **Step 3: 替换 edit_seqmodule 中的重复代码**

找到 `edit_seqmodule` 视图（约 3632-3641 行）中：

```python
            page = request.POST.get('page', 1)
            q = request.POST.get('q', '')
            qs = f'?page={page}'
            if q:
                from urllib.parse import quote
                qs += f'&q={quote(q)}'
            return redirect(f'/seqmodule_list/{qs}')
```

替换为：

```python
            page = request.POST.get('page', 1)
            q = request.POST.get('q', '')
            return redirect(_module_list_url('/seqmodule_list/', page, q))
```

（此处出现两次——新建和编辑成功各一次。两处都要替换。）

- [ ] **Step 4: 替换 delete_seqmodule 中的重复代码**

找到 `delete_seqmodule`（约 3658-3664 行）中相同模式，替换为：

```python
        page = request.POST.get('page', 1)
        q = request.POST.get('q', '')
        return redirect(_module_list_url('/seqmodule_list/', page, q))
```

- [ ] **Step 5: 替换 edit_linkermodule 中的重复代码**

找到 `edit_linkermodule`（约 4824-4833 行）中相同模式，替换为：

```python
            page = request.POST.get('page', 1)
            q = request.POST.get('q', '')
            return redirect(_module_list_url('/linkermodule_list/', page, q))
```

- [ ] **Step 6: 替换 delete_linkermodule 中的重复代码**

找到 `delete_linkermodule`（约 4851-4857 行）中相同模式，替换为：

```python
        page = request.POST.get('page', 1)
        q = request.POST.get('q', '')
        return redirect(_module_list_url('/linkermodule_list/', page, q))
```

- [ ] **Step 7: 验证**

1. 确认已无内联 `from urllib.parse import quote` 残留：
   ```bash
   grep -n "from urllib.parse import quote" app01/views.py
   ```
   预期：无输出（已全部通过 `urllib.parse.quote` 间接使用）。

2. 功能验证：在列表页第 3 页搜索 "Am"，点击编辑，保存，确认 redirect 回到第 3 页且搜索词保留。

- [ ] **Step 8: Commit**

```bash
git add app01/views.py
git commit -m "refactor: extract _module_list_url helper to deduplicate page/q URL building

Replaces 4 identical inline blocks in edit/delete views for
seqmodule and linkermodule.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## 自审检查清单

**Spec coverage:**
- C1 ✅ Task 1
- I1 ✅ Task 2
- C3 ✅ Task 3
- C4 ✅ Task 4
- I2 ✅ Task 5
- I3 ✅ Task 6
- I5 ✅ Task 7
- I6 ✅ Task 8
- M3 ✅ Task 9
- I4 ✅ Task 10
- M1 ✅ Task 11
- M2 ✅ Task 12

**Migration 依赖链:** 0029 → 0030 → 0031 → 0032 ✅

**Wave 顺序约束:**
- Wave 1（T1, T2）必须先于其他 Wave ✅
- Wave 3 的 3 条 migration 按 0030→0031→0032 顺序 ✅
- Wave 4（T10）需服务器同步创建 .env ✅
- Wave 2（T3-T6）和 Wave 5（T11-T12）可并行执行 ✅
