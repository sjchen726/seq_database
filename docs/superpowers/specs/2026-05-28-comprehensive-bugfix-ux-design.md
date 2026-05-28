# 全项目综合修复（安全 / Bug / 性能 / UX）— 设计规范

## 背景

对 SeqDB 项目进行第二轮全面代码审计，发现 63 处问题，分为安全（6）、逻辑 Bug（13）、代码质量（13）、性能（5）、UX/前端（16）、Model（6）、URL（4）七类。

本次修复分两批执行：
- **Batch 1**（优先）：安全漏洞 + Critical/Important Bug + Bug 类 UX，共 9 个修复项（SEC-02、SEC-03、BUG-01、BUG-05、BUG-04、UX-01/02、UX-05/06、BUG-07）
- **Batch 2**（后续）：功能性 Bug + 性能 + 代码质量 + Model/URL 规范，共 10+ 个修复点

> **注**：SEC-01（注册页可 POST 任意 user_type）经用户确认暂不处理，留待后续单独规划。  
> **注**：MODEL-03（permissions_project 逗号字符串改多对多）涉及大规模迁移，本次仅加注释 TODO，不实际执行。

---

## 不在本次范围内

- SEC-01：公开注册 user_type 验证
- MODEL-03：permissions_project 迁移为关联表
- 任何新功能
- views.py 大规模重构（仅在修复点局部改动）
- 纯展示性 UX 优化（空状态设计、排序反馈动画等）

---

## Batch 1 — 安全 + Critical Bug + Bug 类 UX

### SEC-02：`drop_author` 删除用户改为 POST

**问题**：`drop_author` view（`views.py:501`）通过 `request.GET.get('id')` 接收用户 ID，实为 GET 请求删除操作。`templates/auth_list.html:49` 使用 `<a href="...">` 触发，任何含该 URL 的 `<img src>` 或外部链接均可 CSRF 触发删除。

**修复**：
1. `views.py` 中 `drop_author` 改为读取 `request.POST.get('id')`，并在函数顶部加 `if request.method != 'POST': return HttpResponseBadRequest()` 校验
2. `templates/auth_list.html` 将 `<a href="...">` 替换为：
   ```html
   <form method="POST" action="{% url 'drop_author' %}" style="display:inline;"
         onsubmit="return confirm('确定删除该用户？');">
     {% csrf_token %}
     <input type="hidden" name="id" value="{{ user.id }}">
     <button type="submit" class="ds-act" style="color:#ef4444;">删除</button>
   </form>
   ```

**验证**：向 `/drop_author/?id=X` 发 GET 请求，应返回 400；通过表单 POST 删除正常工作。

---

### SEC-03：`download_selected` 绕过项目权限

**问题**：`download_selected` view（`views.py:3359`）直接 `Delivery.objects.filter(duplex_id__in=ids)`，不经过项目级权限过滤。任何登录用户可下载无权限数据。

**修复**：将基础 queryset 改为：
```python
base_qs = get_permitted_delivery_qs(request.user)
deliveries = base_qs.filter(duplex_id__in=ids)\
    .select_related('sequence')\
    .prefetch_related('sequence__target_info')
```
无权限的记录被静默过滤（不报错，不暴露存在）。

**验证**：用 guest 账号（无项目权限）POST 一批受限 duplex_id，返回空 CSV（只有表头）。

---

### BUG-01：`edit_reg_seq` 中 `edit_project` 字段数据静默丢失

**问题**：`views.py:3263` 中：
```python
edit_seq = request.POST.get('edit_project')  # BUG：变量名写成了 edit_seq
```
读取了表单的 `edit_project` 值但存入 `edit_seq`，后续完全没有使用该值，`seqinfo.project` 永远不会被更新。

**修复**（`views.py:3263` 附近）：
```python
# 修复前
edit_seq = request.POST.get('edit_project')

# 修复后
edit_project = request.POST.get('edit_project')
```
并在 `changes` 检查块中补充 project 更新逻辑：
```python
if seqinfo.project != edit_project:
    changes.append(f"Project: {seqinfo.project} → {edit_project}")
    seqinfo.project = edit_project
```

**验证**：在编辑注册序列页面修改 project 字段并提交，刷新页面后 project 显示更新后的值。

---

### BUG-05：`seq_type == reversed_seq_type` 自比较（AS 反转逻辑恒执行或恒跳过）

**问题**：两个着色函数中均存在相同 bug：

`get_delivery_colored`（`views.py:82,127`）：
```python
reversed_seq_type = selected_seq_type  # 赋值为同一参数
...
if seq_type == reversed_seq_type:      # 等价于 if seq_type == selected_seq_type
```

`get_modify_seq_colored`（`views.py:263,342`）：同样模式。

按文档注释，意图是"若 seq_type == 'AS' 则反转 token 顺序"，但实现比较的是 `seq_type` 与 `selected_seq_type`（用户当前筛选值）而非 `'AS'`。在混合显示模式（`selected_seq_type=None` 或 `'SS'`）下，AS 链不会被反转，导致显示方向错误。

**修复**：两个函数中，删除 `reversed_seq_type = selected_seq_type` 赋值行，将判断改为：
```python
# 修复前
reversed_seq_type = selected_seq_type
...
if seq_type == reversed_seq_type:
    result = _reverse_tokens(result)

# 修复后
if seq_type == 'AS':
    result = _reverse_tokens(result)
```

`get_modify_seq_colored` 中的 `_reverse_tokens(result)` 调用目前为 `result = _reverse_tokens(result)` 形式，修复逻辑同上。

**验证**：在 duplex 视图中同时显示 AS + SS 链，AS 链 token 应从 3' → 5' 方向显示（反转），SS 链从 5' → 3'（正常）；切换 selected_seq_type 不影响各自的反转结果。

---

### BUG-04：BP ID 生成存在竞态条件

**问题**：`assign_duplex_ids`（`views.py:1712`）的逻辑：
```python
existing_ids = Delivery.objects.filter(duplex_id__startswith="BP").values_list(...)
next_number = max(existing_numbers, default=0) + 1
```
没有数据库锁，两个并发上传可读到相同的 MAX，生成相同 BP ID，导致 `IntegrityError` 或数据混乱。

**修复**：将取最大值 + 递增的步骤包在 `transaction.atomic()` 加 `select_for_update()` 中：
```python
def assign_duplex_ids(df, ss_groups, repeated_ids):
    duplex_id_map = {}
    valid_groups = [group for _, _, group in ss_groups if not repeated_ids.intersection(group)]
    pattern = re.compile(r"^BP(\d{6})$")

    with transaction.atomic():
        existing_ids = (
            Delivery.objects
            .select_for_update()
            .filter(duplex_id__startswith="BP")
            .values_list('duplex_id', flat=True)
        )
        existing_numbers = [
            int(m.group(1)) for d in existing_ids if (m := pattern.match(d))
        ]
        next_number = max(existing_numbers, default=0) + 1

        for group in valid_groups:
            serial = f"{next_number:06d}"
            duplex_id = f"BP{serial}"
            for row_id in group:
                duplex_id_map[row_id] = duplex_id
            next_number += 1

    return duplex_id_map
```

**验证**：同时发起两个上传请求，确认两者生成的 BP ID 不重复。

---

### UX-01/02：`base.html` 导航高亮使用字符串 `in` 运算符

**问题**：`templates/base.html:78`：
```html
{% if request.resolver_match.url_name in 'author_list,add_author,edit_author' %}
```
Django 模板中 `in` 作用于字符串时检查的是**子串**，不是列表成员。例如 `'list' in 'author_list,add_author,edit_author'` 为 True，导致任何包含 `list`、`author`、`edit` 等字符的 url_name 都会错误激活该导航项。

**修复**：改为显式 `or` 条件：
```html
{% if request.resolver_match.url_name == 'author_list' or request.resolver_match.url_name == 'add_author' or request.resolver_match.url_name == 'edit_author' %}
```

**验证**：访问 `/seqmodule_list/`、`/reg_seq_list/`、`/module_list/` 等含 `list` 的路径，"用户管理"导航项不应高亮；访问 `/author_list/`、`/add_author/`、`/edit_author/` 时正确高亮。

---

### UX-05/06：DeliveryModule 编辑/删除不保留 page/q 参数

**问题**：`edit_module`（`views.py:3431`）和 `delete_module`（`views.py:3540`）在操作成功后均 `redirect('/module_list/')` 不带任何参数，用户每次操作后被跳回第一页、搜索清空。SeqModule 和 LinkerModule 在上一轮修复中已处理，此处为遗漏。

**修复**：
1. `edit_module` POST 中从 `request.POST` 读取 `page` 和 `q`（需要模板先传入）：
   ```python
   page = request.POST.get('page', 1)
   q = request.POST.get('q', '')
   # _module_list_url 已在 views.py 顶部定义（Batch 1 上一轮修复添加），如不存在则直接拼接：
   # return redirect(f'/module_list/?page={page}&q={urllib.parse.quote(str(q))}')
   return redirect(_module_list_url('/module_list/', page, q))
   ```
2. `delete_module` 同理
3. `templates/edit_module.html` 表单中补充两个 hidden field：
   ```html
   <input type="hidden" name="page" value="{{ page|default:1 }}">
   <input type="hidden" name="q" value="{{ q|default:'' }}">
   ```
4. `edit_module` GET 请求时从 `request.GET` 读取并传入 context：
   ```python
   page = request.GET.get('page', 1)
   q = request.GET.get('q', '')
   ```
5. `templates/module_list.html` 中编辑链接添加 `&page={{ page_obj.number }}&q={{ q|urlencode }}`，删除表单添加对应 hidden fields

**验证**：在第 2 页搜索 `"LP"` 后编辑/删除一条 DeliveryModule，完成后应跳回第 2 页且搜索框仍显示 `LP`。

---

### BUG-07：`auto_register_bare_sequences` 仅为 SS 链创建 SeqInfo，AS 链编辑 404

**问题**：`auto_register_bare_sequences`（`views.py:1572`）：
```python
# ── SeqInfo (SS only，如不存在则创建) ──
if not SeqInfo.objects.filter(sequence=ss_obj).exists():
    SeqInfo.objects.create(sequence=ss_obj, ...)
```
AS 链（`as_obj`）没有对应的 SeqInfo 创建。点击"编辑 AS 序列"时，`edit_reg_seq` 中 `get_object_or_404(SeqInfo, sequence_id=rm_code)` 抛出 404。

**修复**：在 SS 的 SeqInfo 创建块后面，补充 AS 的对称逻辑：
```python
# ── SeqInfo (AS，如不存在则创建) ──
if not SeqInfo.objects.filter(sequence=as_obj).exists():
    SeqInfo.objects.create(
        sequence=as_obj,
        Transcript=transcript,
        Pos=position,
        project=project,
        Remark='',
        created_at=created_at,
    )
```

**验证**：上传一个包含新 AS+SS 对的 CSV（两者均未注册），上传完成后检查数据库确认 AS 链和 SS 链各有一条 SeqInfo 记录；分别点击 AS 链和 SS 链的"编辑"，均应成功打开编辑页，不报 404。

---

## Batch 2 — 功能 Bug + 性能 + 代码质量 + Model/URL

### BUG-02 + BUG-03：`save_deliveries` 两处独立问题（同一函数，相邻逻辑）

> 以下两个修复均位于 `save_deliveries` 函数内，属于独立问题，建议在同一 commit 中一并修复。

### BUG-02：`add_o_to_all_rules_safe` 被调用两次

**问题**：`views.py:1897,1928`：
```python
current_linker_seq = add_o_to_all_rules_safe(item['modify_seq'])  # 第一次：用于去重 key
...
Delivery.objects.create(
    ...
    linker_seq=add_o_to_all_rules_safe(item['modify_seq']),  # 第二次：重复调用
    ...
)
```
`add_o_to_all_rules_safe` 对同一输入被调用两次，函数内部执行正则替换，双重调用可能导致连接符被重复添加（如 `o` 追加两遍）。

**修复**：`Delivery.objects.create` 中改为复用已计算的变量：
```python
linker_seq=current_linker_seq,
```

**验证**：上传含修饰序列的 CSV，检查数据库中 `linker_seq` 字段值，确认 `o` 连接符未被重复添加。

---

### BUG-03：`save_deliveries` 去重逻辑缺少 naked_sequence 条件

**问题**：`views.py:1903`：
```python
duplicate = Delivery.objects.filter(
    delivery5=current_delivery5,
    delivery3=current_delivery3,
    linker_seq=current_linker_seq
).first()
```
不包含 `sequence`（naked sequence FK）过滤，导致不同裸序列但具有相同 delivery5/3/linker_seq 的记录被误判为重复（静默跳过，不插入）。

**修复**：加入 `sequence=sequence_obj` 条件：
```python
duplicate = Delivery.objects.filter(
    sequence=sequence_obj,
    delivery5=current_delivery5,
    delivery3=current_delivery3,
    linker_seq=current_linker_seq
).first()
```

**验证**：上传两条 naked_seq 不同但 delivery5/3/linker_seq 相同的行，确认两条均被正常插入数据库。

---

### BUG-06：`group_sequences` AS/SS 配对依赖 SS 先行顺序

**问题**：`group_sequences`（`views.py:1263`）逐行扫描，遇 SS 则向后看一行是否为 AS，配对成功则合并。若 CSV 中 AS 出现在 SS 之前，该 AS 行直接被标记为 `invalid_ss_as`（`原始行 N, 无效AS：没有配对的 SS`），整对被丢弃。

**修复**：改为两轮扫描：
1. **第一轮**：收集所有行，按 `__row_id` 排序
2. **第二轮**：识别相邻 SS+AS 或 AS+SS 对，任一顺序均可配对

```python
def group_sequences(df):
    ss_groups = []
    invalid_ss_as = []
    group_sorted = df.sort_values(by='__row_id').reset_index(drop=True)
    rows = [group_sorted.iloc[i] for i in range(len(group_sorted))]

    i = 0
    while i < len(rows):
        row = rows[i]
        seq_type = row['Seq_type'].strip().upper()
        
        # 检查是否可以与下一行配对（SS+AS 或 AS+SS）
        if i + 1 < len(rows):
            next_row = rows[i + 1]
            next_seq_type = next_row['Seq_type'].strip().upper()
            
            if (seq_type == 'SS' and next_seq_type == 'AS') or \
               (seq_type == 'AS' and next_seq_type == 'SS'):
                # 统一：group 中 SS 在前，AS 在后
                if seq_type == 'SS':
                    temp_group = [row['__row_id'], next_row['__row_id']]
                else:
                    temp_group = [next_row['__row_id'], row['__row_id']]
                project = row['Project']
                ss_groups.append((None, project, temp_group))
                i += 2
                continue
        
        # 未能配对
        invalid_ss_as.append(
            f"原始行 {row['__original_line']}, {row['Modify_seq']}, 无法配对（{seq_type}）"
        )
        i += 1

    return ss_groups, invalid_ss_as
```

> **配对规则说明**：每次循环消耗当前行 + 下一行（相邻配对），每行最多参与一次配对。如 CSV 含 4 行 SS/AS/SS/AS，则第 1+2 行配对，第 3+4 行配对；若顺序是 SS/SS/AS/AS，则第 1 行（SS）找第 2 行（SS），无法配对，第 1 行 SS 标记为无效，第 2+3 行（SS+AS）配对，第 4 行（AS）标记为无效。

**验证**：上传一个 AS 行在 SS 行之前的 CSV，确认双方均正常配对并成功上传，不再出现"无效AS"报错。

---

### PERF-04：`reg_seq_list` 全表载入 Python 后再分页

**问题**：`views.py:3211`：
```python
sequence_list = []
for seq in sequences:  # sequences 是完整 QuerySet，此处触发全表加载
    ...
    sequence_list.append({...})

paginator = Paginator(sequence_list, page_size)  # 对 Python list 分页
```
当 Sequence 表记录数达到数千条时，每次请求将所有记录拼装为 dict list 再分页，内存消耗高。

**修复**：改用数据库级分页，用模板直接读字段值（或保持 dict 结构但改为分页后再拼装）：

```python
sequences = Sequence.objects.exclude(seq_type='duplex').prefetch_related('target_info')
if q:
    sequences = sequences.filter(rm_code__icontains=q)
sequences = sequences.order_by('rm_code')

paginator = Paginator(sequences, page_size)
page_obj = paginator.get_page(request.GET.get('page', 1))

# 仅对当前页的记录做拼装
sequence_list = []
for seq in page_obj.object_list:
    seq_info = seq.target_info.first()
    ...
    sequence_list.append({...})
```

**验证**：访问 `/reg_seq_list/`，通过 Django Debug Toolbar 或日志确认数据库查询只拉取当前页的记录数（+ prefetch），而非全表。

---

### CQ-06：`get_user_default_seq_type` 硬编码用户名 `Y2325`

> **注**：本修复涉及模型字段添加、数据库迁移、历史数据回填、代码改动四个子步骤，复杂度高于普通 CQ 修复，建议单独分配一个任务。

**问题**：`views.py:2652`：
```python
user_default_seq_map = {
    'Y2325': 'AS',
}
```
用户的默认序列方向通过硬编码 dict 维护，函数注释中也提到"优先读取数据库中 LmsUser 的 default_seq_type 字段（如有）"，但该字段从未被创建。

**修复**：
1. `models.py` 中在 `LmsUser` 添加字段：
   ```python
   default_seq_type = models.CharField(
       '默认序列方向', max_length=10, default='SS',
       choices=[('SS', 'SS'), ('AS', 'AS')],
   )
   ```
2. 新建 migration `0033_lmsuser_default_seq_type.py`
3. `views.py` 中 `get_user_default_seq_type` 改为：
   ```python
   def get_user_default_seq_type(user):
       if not user.is_authenticated:
           return 'SS'
       return getattr(user, 'default_seq_type', 'SS') or 'SS'
   ```
4. 在管理后台（Django admin）将 Y2325 用户的 `default_seq_type` 改为 `'AS'`，同时在 migration 中可通过 `RunPython` 完成数据迁移：
   ```python
   def set_y2325_default(apps, schema_editor):
       LmsUser = apps.get_model('app01', 'LmsUser')
       LmsUser.objects.filter(username='Y2325').update(default_seq_type='AS')
   ```

**验证**：Y2325 账号登录后默认显示 AS 方向；其他账号默认 SS；无硬编码用户名残留。

---

### CQ-07/08：`build_combo_re` / `normalize_tmp_seq_with_combo` 每次调用重查数据库

**问题**：
- `build_combo_re`（`views.py:1735`）每次调用都执行 `DeliveryModule.objects.all()` + `SeqModule.objects.all()`
- `normalize_tmp_seq_with_combo`（`views.py:1761`）内部调用 `build_combo_re()`，每行数据处理都触发两次全表查询

在 `run_preflight_check` 中循环调用 `normalize_tmp_seq_with_combo` 时，100 行数据 = 200 次额外查询。

**修复**：为 `build_combo_re` 添加可选参数接收预加载数据：
```python
def build_combo_re(dm_modules=None, sm_modules=None):
    if dm_modules is None:
        dm_modules = list(DeliveryModule.objects.all())
    if sm_modules is None:
        sm_modules = list(SeqModule.objects.all())
    ...
```
调用方（`run_preflight_check` 等）在进入循环前预加载：
```python
dm_modules = list(DeliveryModule.objects.all())
sm_modules = list(SeqModule.objects.all())
combo_re = build_combo_re(dm_modules=dm_modules, sm_modules=sm_modules)
```
`normalize_tmp_seq_with_combo` 同样增加可选参数并传入：
```python
from typing import Optional
import re

def normalize_tmp_seq_with_combo(modify_seq: str, combo_re: Optional[re.Pattern] = None) -> str:
    if combo_re is None:
        combo_re = build_combo_re()
    ...
```

**验证**：上传 50 行 CSV，通过日志确认 `SeqModule` 和 `DeliveryModule` 各只被查询一次（而非 50 次）。

---

### URL-01/02：根路径无 name + 重复注册路由

**问题**：
- `bms/urls.py:25`：`path('', views.login_view)` 无 `name=`，模板无法通过 `{% url %}` 引用
- `bms/urls.py:27,28`：`signup/` 和 `register/` 都指向同一 view，重复且命名不一致

**修复**：
```python
# 修复前
path('', views.login_view),
path('signup/', views.register_view, name='signup'),
path('register/', views.register_view, name='register'),

# 修复后
path('', views.login_view, name='root'),
path('register/', views.register_view, name='register'),  # 保留 register，移除 signup
```
全局搜索 `{% url 'signup' %}` 并替换为 `{% url 'register' %}`（当前无此引用则无需额外操作）。

**验证**：`python manage.py check` 无警告；`{% url 'root' %}` 和 `{% url 'register' %}` 均能正确解析。

---

### MODEL-03：permissions_project 逗号字符串 — TODO 标注

> *本次仅保留 TODO 注释，完整迁移留待后续规划。*

**问题**：`LmsUser.permissions_project` 存为 `max_length=256` 逗号字符串，无法建索引，扩展困难。

**本次处理**：仅在 `models.py` 中添加注释：
```python
# TODO: permissions_project 应迁移为 ManyToManyField(ProjectCode) 以支持索引查询
# 当前实现：逗号分隔字符串，解析逻辑见 get_allowed_projects()
permissions_project = models.CharField(...)
```

---

## 涉及文件汇总

| 文件 | Batch | 改动说明 |
|------|-------|---------|
| `app01/views.py` | 1 | SEC-02 drop_author POST、SEC-03 下载权限、BUG-01 edit_project、BUG-05 reversed_seq_type、BUG-04 atomic、UX-05/06 module redirect、BUG-07 AS SeqInfo |
| `templates/auth_list.html` | 1 | SEC-02 删除链接改 POST 表单 |
| `templates/base.html` | 1 | UX-01/02 导航 in 运算符修复 |
| `templates/edit_module.html` | 1 | UX-05/06 hidden page/q fields |
| `templates/module_list.html` | 1 | UX-05/06 编辑链接和删除表单加 page/q |
| `app01/views.py` | 2 | BUG-02 双调用、BUG-03 去重加 sequence、BUG-06 两轮扫描、PERF-04 DB分页、CQ-06 remove hardcode、CQ-07/08 预加载参数 |
| `app01/models.py` | 2 | CQ-06 添加 default_seq_type 字段、MODEL-03 TODO注释 |
| `app01/migrations/0033_lmsuser_default_seq_type.py` | 2 | AddField + RunPython 设置 Y2325 初始值 |
| `bms/urls.py` | 2 | URL-01 root name、URL-02 移除 signup 重复路由 |

---

## 执行顺序约束

- Batch 1 不涉及 migration，全部改完可立即测试 + 上线
- Batch 2 migration（0033）须在 `models.py` 修改后 `makemigrations`，或手写
- Batch 2 BUG-06 改动 `group_sequences` 逻辑，须保证 `run_preflight_check` 和 `check_duplicates` 的调用方式与新返回格式兼容（返回结构不变：`(ss_groups, invalid_ss_as)`，group 内 SS 仍在前）
- Batch 2 CQ-07/08 改动 `build_combo_re` 签名，须同步更新所有调用点
