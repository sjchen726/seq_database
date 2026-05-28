# 全项目 Bug 修复审计 — 设计规范

## 背景

对 SeqDB 项目进行全面代码审计后，发现 16 处问题，分为 Critical / Important / Minor 三级。本次修复覆盖全部问题，按 5 个波次执行，最先解决正在发生的崩溃，最后处理代码整洁。

触发本次审计的直接原因：新建 SeqModule 时报
`OperationalError (1364, "Field 'type_code' doesn't have a default value")`，根因为数据库表存在 Django 模型已删除的遗留列。

> **注**：审计初稿中 C2（`DeliveryProject.__str__` 引用 `self.delivery_id`）经核查为误报——Django ForeignKey 自动生成 `delivery_id` 属性，现有代码实际可正常运行，已从修复列表移除。

---

## 不在本次范围内

- 任何新功能
- views.py 大规模重构（仅在修复点局部改动）
- `naked_length` 的业务语义变更（仅修正存储类型）
- I6 清重时被删记录的恢复（只删冗余，保留最小 rm_code 的主记录）

---

## Wave 1 — 止血（无 migration，改完立即可测）

### C1：DROP `type_code` 遗留列

**问题**：`app01_seqmodule` 表存在 `type_code` 列（NOT NULL, 无默认值），Django 模型中此字段已删除。每次 INSERT SeqModule 时 MySQL 强制要求该列有值，导致 OperationalError。

**修复**：新建手写 migration `0029_drop_seqmodule_type_code.py`，使用 `RunSQL` 执行：
```sql
ALTER TABLE app01_seqmodule DROP COLUMN type_code;
```
不修改 Django 模型，无需 `makemigrations`。

**验证**：运行 migration 后，在 `/edit_seqmodule/` 页面新建一条 SeqModule，确认不再报 OperationalError。

---

### I1：`linkermodule_list` 缺 `@login_required`

**问题**：`linkermodule_list` 视图没有 `@login_required` 装饰器，未登录用户可直接访问 `/linkermodule_list/`，与同类视图不一致。

**修复**：在 `views.py` 中为 `linkermodule_list` 函数加上 `@login_required` 装饰器。

**验证**：退出登录后访问 `/linkermodule_list/`，应 302 重定向到登录页。

---

## Wave 2 — 代码逻辑修复（无 migration）

### C3：`save_deliveries` N+1 查询

**问题**：`save_deliveries()` 内循环对每一行数据都执行一次 `Sequence.objects.filter(rm_code=...).first()`，上传 100 行就查 100 次数据库，性能极差。

**修复**：
1. 循环前收集所有 rm_code：`rm_codes = df['rm_code'].dropna().unique().tolist()`
2. 一次性查询：`seq_map = {s.rm_code: s for s in Sequence.objects.filter(rm_code__in=rm_codes)}`
3. 循环内改为：`seq = seq_map.get(rm_code)`

**验证**：上传一个 50 行 CSV，通过 Django Debug Toolbar 或日志确认 Sequence 查询只执行 1 次。

---

### C4：`get_or_create` 后的死代码

**问题**：`confirm_upload_preflight` POST 中对 `get_or_create()` 返回的对象做了 `if seq is None:` 判断。`get_or_create` 在成功时永远返回对象实例，不会返回 `None`，该分支是永远不执行的死代码，且掩盖了真正需要处理的错误情况。

**修复**：
1. 删除 `if seq is None:` 分支
2. 在 `get_or_create` 调用外层补上 `try/except IntegrityError` 捕获并发冲突
3. 确认正确的错误路径（如注册失败时应如何回滚或提示用户）

**验证**：code review 确认无死代码；单元测试验证 IntegrityError 被正确捕获。

---

### I2：`confirm_upload_preflight` 吞异常

**问题**：顶层 `except Exception as e:` 捕获所有异常但只返回一个通用错误，完整堆栈被丢弃，无法诊断问题。

**修复**：
1. 在顶层 `except Exception` 前，增加对已知异常的具体处理：
   - `KeyError` / `json.JSONDecodeError`：session 数据损坏，提示用户重新上传
   - `IntegrityError`：数据库约束冲突，提示具体字段
2. 保留兜底 `except Exception`，但改为 `logger.exception("confirm_upload_preflight 未预期错误")` 记录完整堆栈

**验证**：故意传入损坏的 session 数据，确认日志中出现完整 traceback。

---

### I3：`confirm_share_deliveries` 缺事务

**问题**：`confirm_share_deliveries` 视图中多步写操作（更新 Delivery + 创建 DeliveryProject 等）没有 `transaction.atomic`，中途失败会留下部分写入的脏数据。

**修复**：用 `with transaction.atomic():` 包裹整个写入块。

**验证**：在事务中途手动触发 IntegrityError，确认所有写入均被回滚。

---

## Wave 3 — Schema Migration

Migration 依赖链：`0029` → `0030` → `0031` → `0032`（顺序执行）。

### I5：`naked_length` CharField → IntegerField

**问题**：`naked_length` 存储数字但类型为 `CharField`，字符串排序导致 "9" > "10"，排序逻辑错误。

**修复**：
1. Migration `0030`：
   - `RunPython`：将现有字符串值转为整数（空字符串和 None → `NULL`）
   - `AlterField`：`naked_length = models.IntegerField(null=True, blank=True)`
2. `models.py` 同步修改字段定义

**验证**：`Sequence.objects.order_by('naked_length')` 返回结果按数字排序正确。

---

### I6：`(seq, seq_type)` 唯一约束（含清重）

**问题**：`Sequence` 表缺少联合唯一约束，理论上可插入重复 `(seq, seq_type)` 组合，导致数据冗余。

**修复**：Migration `0031` 分两步：

**Step A — 清重（RunPython）**：
```python
from django.db import models as m
# 找出所有重复 (seq, seq_type) 组
dupes = (Sequence.objects
    .values('seq', 'seq_type')
    .annotate(cnt=m.Count('rm_code'))
    .filter(cnt__gt=1))
for d in dupes:
    qs = Sequence.objects.filter(seq=d['seq'], seq_type=d['seq_type']).order_by('rm_code')
    to_delete = list(qs.values_list('rm_code', flat=True))[1:]  # 保留最小 rm_code
    logger.warning(f"清除重复序列: {to_delete}")
    Sequence.objects.filter(rm_code__in=to_delete).delete()  # 级联删除关联记录
```

**Step B — 加约束（AddConstraint）**：
```python
models.UniqueConstraint(fields=['seq', 'seq_type'], name='unique_seq_seqtype')
```

`models.py` 的 `Sequence.Meta.constraints` 同步添加。

**验证**：migration 成功后，尝试手动插入重复 `(seq, seq_type)` 应报 IntegrityError。

---

### M3：`Sequence.seq` max_length 扩展

**问题**：`seq` 字段 max_length=100，但双链序列拼接后可能超出。

**修复**：Migration `0032`：`AlterField`，`max_length=500`。`models.py` 同步修改。

**验证**：插入一条长度 > 100 的序列，不报截断错误。

---

## Wave 4 — 配置安全（I4）

**问题**：`SECRET_KEY`、MySQL 密码、邮件密码明文写在 `bms/settings.py` 中，通过版本控制暴露。

**修复方案**：引入 `python-decouple`。

**改动清单**：

1. `requirements.txt` 添加 `python-decouple`
2. `.gitignore` 添加 `.env`
3. 新建 `.env.example`（提交到版本库，值为占位符）：
   ```
   SECRET_KEY=your-secret-key-here
   DB_PASSWORD=your-db-password
   EMAIL_HOST_PASSWORD=your-email-password
   ```
4. 服务器上手动创建 `.env`（不提交）
5. `settings.py` 中替换：
   ```python
   from decouple import config
   SECRET_KEY = config('SECRET_KEY')
   DATABASES['default']['PASSWORD'] = config('DB_PASSWORD')
   EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
   ```

**部署注意**：在服务器上 `pip install python-decouple` 并创建 `.env` 文件后再重启 Django。

**验证**：删除本地 `.env` 后启动 Django，应报 `UndefinedValueError`（确认 settings 确实在读环境变量）；重建 `.env` 后正常启动。

---

## Wave 5 — 代码整洁（M1 M2）

### M1：清理注释掉的 print 语句

**修复**：全文搜索 `views.py` 中注释掉的 `# print(` 行，统一删除。

**验证**：`grep -n "# print(" app01/views.py` 返回空。

---

### M2：提取 URL query string 拼接 helper

**问题**：`?page=X&q=Y` 拼接逻辑在 `edit_seqmodule`、`delete_seqmodule`、`edit_linkermodule`、`delete_linkermodule` 中各写一遍。

**修复**：在 `views.py` 顶部附近（helper 函数区）添加：
```python
from urllib.parse import quote as _url_quote

def _list_redirect_url(base_url: str, page, q: str) -> str:
    """构建带 page/q 参数的列表页 redirect URL。"""
    return f"{base_url}?page={page}&q={_url_quote(str(q))}"
```

四处调用点替换为 `_list_redirect_url('/seqmodule_list/', page, q)` 等。

**验证**：编辑/删除 SeqModule 后，redirect 目标 URL 正确携带 page 和 q 参数（与现有行为一致）。

---

## 涉及文件汇总

| 文件 | Wave | 改动说明 |
|------|------|---------|
| `app01/migrations/0029_drop_seqmodule_type_code.py` | 1 | RunSQL DROP COLUMN type_code |
| `app01/migrations/0030_naked_length_to_integer.py` | 3 | 数据迁移 + AlterField IntegerField |
| `app01/migrations/0031_sequence_unique_seq_seqtype.py` | 3 | RunPython 清重 + AddConstraint |
| `app01/migrations/0032_sequence_seq_maxlen.py` | 3 | AlterField max_length=500 |
| `app01/models.py` | 3 | I5 字段类型、I6 Meta constraints、M3 max_length |
| `app01/views.py` | 1,2,5 | I1 装饰器、C3 N+1、C4 死代码、I2 异常、I3 事务、M1 print、M2 helper |
| `bms/settings.py` | 4 | config() 替换敏感值 |
| `.env.example` | 4 | 新建，提交到版本库 |
| `.gitignore` | 4 | 添加 .env |
| `requirements.txt` | 4 | 添加 python-decouple |

---

## 执行顺序约束

- Wave 1 必须最先执行（解除崩溃阻塞）
- Wave 3 的三条 migration 按 0030 → 0031 → 0032 顺序执行
- Wave 4 需在服务器同步操作（创建 .env），执行前与运维确认
- Wave 2 和 Wave 5 可并行执行（互不依赖）
