# SeqModule 多值 base_char + 分页状态保留 — 设计规范

## 背景

### 问题一：SeqModule 单值 base_char 限制

`SeqModule.base_char` 当前只能存一个碱基字符（A/U/G/C 或特殊值）。部分修饰 building block（如 BU01）在不同序列中可对应不同裸碱基（A 或 U），现有模型无法表达这种一对多关系，导致上传含该 token 的序列时无法自动推导裸序列。

### 问题二：模块列表分页状态丢失

SeqModule、DeliveryModule、LinkerModule 三个列表页，在执行删除或编辑保存后，均硬 redirect 回列表第 1 页，丢失当前页码和搜索词，体验差。

---

## 不在本次范围内

- 手动编辑单条修饰序列时的 base_char 重新绑定（裸序列与 Delivery 已绑定，不可改）
- 多值 base_char 的反向推导（即从裸序列反推修饰序列）
- 搜索结果页的滚动位置保留（独立需求，另行规划）

---

## Part 1：SeqModule 多值 base_char

### 数据模型

**`SeqModule.base_char`** 字段保持 `CharField`，允许存逗号分隔多值：

| keyword | base_char | 说明 |
|---------|-----------|------|
| Am | A | 单值，现有逻辑不变 |
| BU01 | A,U | 多值：该 token 可对应 A 或 U |

字段 `max_length` 从 10 升至 32，需要一条 migration。

**判断是否多值**：`',' in (base_char or '')`

现有所有单值记录不受影响。

### SeqModule 编辑页

- `edit_seqmodule.html`：base_char 输入框下方加 hint：「多个碱基用逗号分隔，如 A,U」
- `edit_seqmodule` 视图：保存前校验每个值只能是 `A/U/G/C/I` 或已知特殊值（`INVAB`）；非法值提示错误，不保存
- `seqmodule_list.html`：base_char 列原样展示字符串，多值显示为 `A, U`（加空格）

---

## Part 2：上传预检消歧流程

### 总体流程

```
upload_delivery_info POST
  → parse_uploaded_csv()
  → group_sequences()          ← 检测 ambiguous_pairs
      正常对 → ss_groups
      含多值 token 的对 → ambiguous_pairs
  → run_preflight_check()      ← 将 ambiguous_pairs 纳入 preflight 结果
  → session 存储
  → redirect confirm_upload_preflight
      顶部：消歧区块（若 ambiguous_pairs 非空）
      下方：原有 auto_register / unknown_module 区块
  → confirm POST
      读 disambig_* → 构建覆盖 map
      重新推导 ambiguous_pairs 裸序列
      合并进 clean_groups
      继续原有 duplicate check → save_deliveries
```

### group_sequences 改动

遍历每对序列的 `modify_seq` token 时，检测 `base_char` 是否包含逗号：

- **单值 token**：照旧推导裸序列，进入 `ss_groups`
- **多值 token**：
  - 该对归入 `ambiguous_pairs`，不进入 `ss_groups`
  - 记录：`{ row_ids: [ss_row_id, as_row_id], duplex_preview: '...', ambig_tokens: {'BU01': ['A', 'U']} }`
  - 同一 token 在同一序列内多次出现 → 只记录一个选项（同一化学单体，一次选择即可）

`group_sequences` 返回值扩展为三元组：`(ss_groups, unpaired_ss_as, ambiguous_pairs)`

**注意**：`group_sequences` 当前有 3 个调用点（`upload_delivery_info`、`run_preflight_check` 内部、`confirm_upload_preflight`），均需同步更新为三元组解包。

### confirm_upload_preflight 模板改动

若 `ambiguous_pairs` 非空，在页面最顶部插入消歧区块：

```
┌──────────────────────────────────────────────────────────┐
│ ⚠️  以下序列含可对应多碱基的修饰 token，请为每条选择裸碱基  │
├──────────────┬──────────┬──────────────────────────────┤
│ 序列预览      │ Token   │ 选择                         │
├──────────────┼──────────┼──────────────────────────────┤
│ Am-BU01-Gm… │ BU01    │ ○ A  ● U                     │
└──────────────┴──────────┴──────────────────────────────┘
```

表单字段命名：`disambig_<ss_row_id>_<token>`，值为用户选择的单个碱基（如 `A` 或 `U`）。
所有消歧选项加 `required`，前端阻止漏选提交。

### confirm_upload_preflight POST 改动

```python
# 1. 读取消歧选择
disambig_choices = {}  # { ss_row_id: { 'BU01': 'A' } }
for key, val in request.POST.items():
    if key.startswith('disambig_'):
        _, row_id, token = key.split('_', 2)
        disambig_choices.setdefault(int(row_id), {})[token] = val

# 2. 重新推导 ambiguous_pairs 的裸序列（用覆盖 map）
# 对每对：临时覆盖 _sm_map 中对应 token 的 base_char，调用裸序列推导函数

# 3. 将已消歧的对追加进 clean_groups，继续原有流程
```

### 边界情况

| 情况 | 处理 |
|------|------|
| 消歧后裸序列与 DB 已有序列重复 | 走原有 repeated_ids 流程 |
| 消歧后裸序列与同批其他新序列重复 | 同上 |
| ambiguous_pairs 为空 | 跳过消歧区块，页面无变化 |
| 用户漏选 | 前端 required 阻止提交 |

---

## Part 3：模块列表分页状态保留

### 覆盖范围

- `seqmodule_list` / `delete_seqmodule` / `edit_seqmodule`
- `linkermodule_list` / `delete_linkermodule` / `edit_linkermodule`
- `deliverymodule_list`（若有对应删除/编辑视图）

### 删除操作

列表模板删除按钮的 form 里增加两个 hidden 字段：

```html
<input type="hidden" name="page" value="{{ page_obj.number }}">
<input type="hidden" name="q" value="{{ q }}">
```

对应 `delete_*` 视图读取后拼回 redirect：

```python
page = request.POST.get('page', 1)
q = request.POST.get('q', '')
return redirect(f'/seqmodule_list/?page={page}&q={q}')
```

### 编辑操作

编辑页 URL 携带来源页信息（GET 参数）：

```
/edit_seqmodule/?id=123&page=5&q=Am
```

编辑页模板的「取消」按钮链接和 form 里的 hidden 字段都带上 `page` 和 `q`。

保存成功后 redirect：

```python
page = request.POST.get('page', 1)
q = request.POST.get('q', '')
return redirect(f'/seqmodule_list/?page={page}&q={q}')
```

### 边界

删除某页最后一条记录导致页码超出范围 → Django `Paginator.get_page()` 自动返回最后一页，无需额外处理。

---

## 涉及文件汇总

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `app01/models.py` | 修改 | `SeqModule.base_char` max_length 10→32 |
| `app01/migrations/xxxx_seqmodule_base_char_maxlen.py` | 新建 | migration |
| `app01/views.py` | 修改 | `group_sequences`（检测多值 token）、`run_preflight_check`（纳入 ambiguous_pairs）、`confirm_upload_preflight` POST（消歧逻辑）、`edit_seqmodule` / `delete_seqmodule` / 同类视图（分页保留） |
| `templates/confirm_upload_preflight.html` | 修改 | 顶部新增消歧区块 |
| `templates/edit_seqmodule.html` | 修改 | base_char hint + page/q hidden 字段 |
| `templates/seqmodule_list.html` | 修改 | 删除 form 加 page/q hidden，编辑链接加 page/q 参数 |
| `templates/edit_linkermodule.html` | 修改 | 同 edit_seqmodule |
| `templates/linkermodule_list.html` | 修改 | 同 seqmodule_list |
