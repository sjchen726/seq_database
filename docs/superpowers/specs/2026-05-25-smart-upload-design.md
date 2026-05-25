# 智能上传（Smart Upload）— 设计文档 2026-05-25

## 背景与目标

当前上传流程要求：先完成序列注册（裸序列 → `Sequence`/`SeqInfo`），再上传 Delivery 信息。两步操作繁琐。本功能实现：

1. **自动注册裸序列** — 上传时若 naked_seq 未注册，自动创建 `Sequence` + `SeqInfo` + `DuplexRelationship`
2. **模块预检** — 上传前扫描所有 token，Delivery 模块未知仅警告，SeqModule 未知则跳过该对并输出 CSV

流程采用与现有 `confirm_share` 一致的**预检报告页 → 用户确认 → 执行**模式。

---

## 上传 CSV 模板扩展

**新增两列（可选）：**

| 列名 | 说明 | 映射字段 |
|------|------|---------|
| `Transcript` | 转录本编号，如 `NM_001234` | `SeqInfo.Transcript` |
| `Position` | 靶向位点，如 `123` | `SeqInfo.Pos` |

- 两列均可空，不在 `required_columns` 中
- **取值规则**：从 SS/AS 对中取第一个非空值（SS 行优先，若 SS 行为空则取 AS 行）
- `parse_uploaded_csv` 不变，调用方读取时用 `df.get('Transcript', '')` 方式取值

---

## 预检分析管道

### 插入位置

`upload_delivery_info` 视图 POST 分支：

```
parse_uploaded_csv(request)
→ df['Modify_seq'].apply(normalize_middle_brackets)
→ group_sequences(df)                   ← 现有
→ run_preflight_check(df, ss_groups)    ← 新增
→ 若有 auto_register_pairs 或 unknown_module_pairs
    → 存 session → redirect confirm_upload_preflight
→ 否则（全部 clean）
    → check_duplicates → assign_duplex_ids → save_deliveries（现有流程）
```

### `run_preflight_check(df, ss_groups)` 返回结构

```python
{
  'auto_register_pairs': [
    {
      'ss_row_id': int,
      'as_row_id': int,
      'naked_ss': str,       # 从 SS Modify_seq 提取的裸序列
      'naked_as': str,       # 从 AS Modify_seq 提取的裸序列
      'ss_exists': bool,     # Sequence.objects.filter(seq=naked_ss).exists()
      'as_exists': bool,
      'transcript': str,     # SS 行或 AS 行中第一个非空 Transcript
      'position': str,       # SS 行或 AS 行中第一个非空 Position
      'project': str,
    },
    ...
  ],
  'unknown_module_pairs': [   # SeqModule 未知 → 整对跳过，输出 CSV
    {
      'ss_row_id': int,
      'as_row_id': int,
      'unknown_tokens': ['Zm', 'XYZ'],
      'original_lines': [5, 6],
    },
    ...
  ],
  'unknown_delivery_warnings': [  # DeliveryModule 未知 → 仅警告，不阻止
    {
      'row_id': int,
      'unknown_tokens': ['XYZ'],
      'original_line': int,
    },
    ...
  ],
  'clean_groups': [...],   # ss_groups 中去掉 unknown_module_pairs 后剩余的组
}
```

### SeqModule 未知的判定逻辑

对每条 `Modify_seq`（去除首尾括号后的 `clean_seq`）：
1. 调用 `normalize_tmp_seq_with_combo()` 去掉 combo token
2. 用 `SeqModule.objects.values_list('keyword', flat=True)` 构建替换字典，将已知 token 替换为 `base_char`
3. 去除括号、连字符后，若剩余字符串含非 `[AUGCI]` 字符（正则 `[^AUGCIaugci]`），则判定为含未知 SeqModule token
4. 提取未知字符片段作为 `unknown_tokens`

### DeliveryModule 未知的判定逻辑

对每条 `Modify_seq` 的 `delivery5` 和 `delivery3`（括号内容）：
1. 用 `-` 分割得到各 token
2. 对比 `DeliveryModule.objects.values_list('keyword', flat=True)`
3. 不在列表中的 token 加入 `unknown_delivery_warnings`

---

## 预检报告页

**新 URL：** `path('confirm_upload_preflight/', views.confirm_upload_preflight, name='confirm_upload_preflight')`

**新视图：** `confirm_upload_preflight(request)`

- **GET**：从 session 读取预检结果，渲染报告页
- **POST（"确认并上传"）**：执行自动注册 + 继续上传流程
- **GET `?download=skip_csv`**：下载未知 SeqModule 序列 CSV

**新模板：** `templates/confirm_upload_preflight.html`

报告页三区块：

```
┌──────────────────────────────────────────────────────────┐
│  📋 上传预检报告                                           │
│                                                           │
│  ✅ 将自动注册（N 对）                        [可折叠]     │
│  ┌───────────────────────────────────────────────────┐   │
│  │ SS: AUGCAUGCAUGC...  (新建)                        │   │
│  │ AS: GCAUGCAUGCAU...  (已存在，复用)                │   │
│  └───────────────────────────────────────────────────┘   │
│                                                           │
│  ⚠️  Delivery 模块未知（N 条）               [仅警告]    │
│  行 3: [XYZ] 未在 DeliveryModule 中，上传继续             │
│                                                           │
│  ❌ SeqModule 未知，已跳过（N 对）                         │
│  行 5-6: token [Zm] 未识别                               │
│  [下载跳过序列 CSV]                                        │
│                                                           │
│              [取消]        [确认并上传]                    │
└──────────────────────────────────────────────────────────┘
```

**Session 存储键（POST 执行后清除）：**

| 键 | 内容 |
|----|------|
| `preflight_df_json` | normalize 后的 DataFrame（JSON） |
| `preflight_auto_register` | `auto_register_pairs` 列表（JSON） |
| `preflight_clean_groups` | 可安全上传的 ss_groups（JSON） |
| `preflight_skip_csv_path` | 未知 SeqModule 对的 CSV 文件路径 |

---

## 自动注册逻辑

**新函数 `auto_register_bare_sequences(auto_register_pairs, username)`**

整个函数包在 `transaction.atomic()` 内。

**权限门控**：调用前检查，`user_type == 'guest'` 时跳过，将该对放入 `unregistered_log`。

**四种情形处理：**

| 情形 | 操作 |
|------|------|
| SS 和 AS 都不存在 | 创建 SS + AS + Duplex 三条 `Sequence`；创建两条 `SeqInfo`；创建 `DuplexRelationship` |
| 只有 SS 不存在 | 创建 SS `Sequence` + `SeqInfo`；已有 AS 直接复用；创建新 Duplex `Sequence` + `DuplexRelationship` |
| 只有 AS 不存在 | 对称处理 |
| 两者都存在 | 跳过注册，`clean_groups` 中保留该对，正常上传 |

**`rm_code` 生成：**

```python
with transaction.atomic():
    last = Sequence.objects.select_for_update().order_by('-rm_code').first()
    next_code = f"RM{int(last.rm_code[2:]) + 1:04d}" if last else "RM0001"
```

格式遵循现有 6 字符规则（如 `RM0042`）。

**Duplex `seq` 字段：** `f"{naked_as}, {naked_ss}"`（与 `register_seq` 视图一致）。

**SeqInfo 填充：**

```python
SeqInfo.objects.create(
    sequence=ss_seq,
    Transcript=pair['transcript'],
    Pos=pair['position'],
    project=pair['project'],
    Remark='',
)
```

---

## 确认后的执行流程

`confirm_upload_preflight` POST 分支：

```python
# 1. 权限检查
if user_type != 'guest':
    registered_log = auto_register_bare_sequences(auto_register_pairs, username)

# 2. 从 session 恢复数据
df = pd.read_json(session['preflight_df_json'])
clean_groups = session['preflight_clean_groups']

# 3. 继续现有上传管道（不重复 parse/normalize/group）
repeated_ids, duplicate_meg, cross_project_duplicates = check_duplicates(df, clean_groups, target_project)

# 4. 跨项目重复处理（现有 confirm_share 流程）
if cross_project_duplicates:
    ...

# 5. 正常上传
duplex_id_map = assign_duplex_ids(df, clean_groups, repeated_ids)
upload_meg, upload_log, unregistered_meg, unregistered_log = save_deliveries(df, duplex_id_map, username)

# 6. 清除 session 键
for key in ['preflight_df_json', 'preflight_auto_register', 'preflight_clean_groups', 'preflight_skip_csv_path']:
    session.pop(key, None)
```

---

## 文件修改清单

| 文件 | 改动 | 规模 |
|------|------|------|
| `app01/views.py` | 新增 `run_preflight_check()`、`auto_register_bare_sequences()`、`confirm_upload_preflight()` 视图；`upload_delivery_info` POST 分支插入预检跳转 | **大** |
| `bms/urls.py` | 新增 `confirm_upload_preflight/` 路由 | 小 |
| `templates/confirm_upload_preflight.html` | 新建预检报告页 | 中 |
| `static/templates/upload_seq_template.csv` | 新增 `Transcript`、`Position` 两列 | 小 |

---

## 不在本次范围内

- `register_seq` 视图本身不改动（仍保留独立注册入口）
- 移动端响应式适配
- 批量 SeqModule 注册引导（用户需手动去管理后台补充 SeqModule）
- 自动注册的历史日志 / 审计记录（可在后续迭代添加）
