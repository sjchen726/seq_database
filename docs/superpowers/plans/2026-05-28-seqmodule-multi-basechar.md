# SeqModule 多值 base_char + 分页保留 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 支持 SeqModule.base_char 存逗号分隔多值（如 `A,U`），在上传预检时让用户消歧后继续上传；同步修复 SeqModule / LinkerModule 列表分页状态丢失的问题。

**Architecture:** 共 8 个独立可测试任务。Part A（Tasks 1–6）：多值 base_char 的 DB、UI、预检消歧、保存管道；Part B（Tasks 7–8）：分页状态保留（完全独立，可并行做）。所有逻辑集中在 `app01/views.py`（单文件约 4000 行）、模板和一条 migration，不新增模块文件。

**Tech Stack:** Django 5.1、Python 3.10、MySQL。无 pytest；验证方式为手动功能测试。

**关键架构决策（与设计规范的差异）：**
- 多值 token 检测在 `run_preflight_check()` 内完成，**不改动 `group_sequences()`**（它只做行配对，不涉及 base_char）。
- `save_deliveries()` 新增可选参数 `sm_overrides: dict | None = None`，用于在写入时覆盖多值 token 的 base_char。
- 消歧选择以 token 为键（非逐行），同一批上传中同一 token 的选择全局生效（对同一化学修饰，一次上传中选择相同碱基是合理约束）。

---

## 涉及文件速览

| 文件 | 任务 | 改动类型 |
|------|------|---------|
| `app01/models.py` | T1 | `SeqModule.base_char` max_length 10→32；新增 `base_char_list` 属性 |
| `app01/migrations/0028_seqmodule_base_char_maxlen.py` | T1 | 新建 migration |
| `app01/views.py` | T2,T4,T6,T7,T8 | 多处修改（行号注释在各任务中） |
| `templates/edit_seqmodule.html` | T2,T7 | hint 文字；page/q hidden 字段 |
| `templates/seqmodule_list.html` | T3,T7 | 多值显示；删除 form page/q；编辑链接 page/q |
| `templates/confirm_upload_preflight.html` | T5 | 改为整页 `<form>`；加消歧区块 |
| `templates/linkermodule_list.html` | T8 | 删除 form page/q；编辑链接 page/q |
| `templates/edit_linkermodule.html` | T8 | page/q hidden 字段 |

---

## Task 1：Migration — SeqModule.base_char max_length 10→32

**Files:**
- Modify: `app01/models.py`
- Create: `app01/migrations/0028_seqmodule_base_char_maxlen.py`

- [ ] **Step 1：更新 `models.py` 中 `SeqModule.base_char` 字段，并新增 `base_char_list` 属性**

  在 `app01/models.py` 找到 `SeqModule` 类，将 `base_char` 的 `max_length=10` 改为 `max_length=32`，并在类末尾添加属性：

  ```python
  # 修改字段
  base_char = models.CharField(max_length=32, null=True, blank=True)

  # 在类末尾添加（models.py 的 SeqModule 类内）
  @property
  def base_char_list(self):
      """返回 base_char 各值的列表，如 'A,U' → ['A', 'U']；空则返回 []"""
      if not self.base_char:
          return []
      return [c.strip() for c in self.base_char.split(',') if c.strip()]
  ```

- [ ] **Step 2：创建 migration 文件**

  ```python
  # app01/migrations/0028_seqmodule_base_char_maxlen.py
  from django.db import migrations, models

  class Migration(migrations.Migration):
      dependencies = [
          ('app01', '0027_linkermodule'),
      ]
      operations = [
          migrations.AlterField(
              model_name='seqmodule',
              name='base_char',
              field=models.CharField(blank=True, max_length=32, null=True),
          ),
      ]
  ```

- [ ] **Step 3：应用 migration**

  ```bash
  source venv/bin/activate
  python manage.py migrate
  ```

  预期输出：`Applying app01.0028_seqmodule_base_char_maxlen... OK`

- [ ] **Step 4：验证**

  ```bash
  python manage.py shell -c "from app01.models import SeqModule; m = SeqModule(keyword='TEST', base_char='A,U'); m.save(); print(m.base_char_list); m.delete()"
  ```

  预期输出：`['A', 'U']`

- [ ] **Step 5：Commit**

  ```bash
  git add app01/models.py app01/migrations/0028_seqmodule_base_char_maxlen.py
  git commit -m "feat: extend SeqModule.base_char to max_length=32, add base_char_list property"
  ```

---

## Task 2：SeqModule 编辑页 — base_char 校验 + hint

**Files:**
- Modify: `app01/views.py` (line ~3442 `edit_seqmodule` POST 处理)
- Modify: `templates/edit_seqmodule.html`

- [ ] **Step 1：在 `edit_seqmodule` 视图的 POST 分支中加入 base_char 校验**

  在 `app01/views.py` 的 `edit_seqmodule` 函数内，找到：
  ```python
  base_char = request.POST.get('base_char', '').strip()
  ```
  在该行之后（约 line 3445），`linker_connector` 赋值之前，插入校验逻辑：

  ```python
  # base_char 校验：每个值必须是 A/U/G/C/I/INVAB
  VALID_BASE_CHARS = {'A', 'U', 'G', 'C', 'I', 'INVAB'}
  if base_char:
      bad_vals = [v.strip() for v in base_char.split(',')
                  if v.strip() and v.strip() not in VALID_BASE_CHARS]
      if bad_vals:
          messages.error(
              request,
              f'无效碱基值：{", ".join(bad_vals)}。仅允许 A/U/G/C/I/INVAB，多个用逗号分隔（如 A,U）。'
          )
          return render(request, 'edit_seqmodule.html', {
              'module': module,
              'form_data': {
                  'keyword': request.POST.get('keyword', '').strip(),
                  'base_char': base_char,
                  'linker_connector': request.POST.get('linker_connector', 'o').strip() or 'o',
              },
          })
  ```

  > 注意：该代码块需插入在 `if module is None:` 分支判断之前，校验发生在写入 DB 前的同一路径上。完整顺序：`keyword` → `base_char` → 校验 base_char → `linker_connector` → `if module is None:` 分支。

- [ ] **Step 2：更新 `edit_seqmodule.html` — 加 hint 文字**

  在 `templates/edit_seqmodule.html` 找到 `base_char` 的 `<div class="ds-form-row">` 块，在 `<input>` 之后、`</div>` 之前插入：

  ```html
  <p class="ds-form-hint">多个碱基用逗号分隔，如 A,U（仅允许 A / U / G / C / I / INVAB）</p>
  ```

  修改后该 `<div class="ds-form-row">` 块完整结构：
  ```html
  <div class="ds-form-row">
    <label class="ds-form-label" for="base_char">对应碱基</label>
    <input type="text" id="base_char" name="base_char" class="ds-form-control"
      placeholder="A / U / G / C / INVAB（纯连接符可留空）"
      value="{% if form_data %}{{ form_data.base_char }}{% elif module %}{{ module.base_char }}{% endif %}">
    <p class="ds-form-hint">多个碱基用逗号分隔，如 A,U（仅允许 A / U / G / C / I / INVAB）</p>
  </div>
  ```

- [ ] **Step 3：手动验证**

  启动 dev server（`python manage.py runserver`），导航至「新增修饰模块」页：
  - 输入 `base_char = A,Z` → 应显示错误：「无效碱基值：Z」，不保存
  - 输入 `base_char = A,U` → 保存成功
  - 页面 hint 文字可见

- [ ] **Step 4：Commit**

  ```bash
  git add app01/views.py templates/edit_seqmodule.html
  git commit -m "feat: validate multi-value base_char in edit_seqmodule, add hint text"
  ```

---

## Task 3：SeqModule 列表 — 多值 base_char 显示

**Files:**
- Modify: `templates/seqmodule_list.html`

- [ ] **Step 1：替换 `seqmodule_list.html` 中 base_char 单值判断块**

  找到 `{% if module.base_char == 'A' %}...{% endif %}` 整段（约 line 39–51），替换为使用 `base_char_list` 属性的循环：

  ```html
  {% if module.base_char_list %}
    {% for c in module.base_char_list %}
      {% if c == 'A' %}
        <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;background:#dbeafe;color:#1d4ed8;">A</span>
      {% elif c == 'U' %}
        <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;background:#ffedd5;color:#c2410c;">U</span>
      {% elif c == 'G' %}
        <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;background:#dcfce7;color:#15803d;">G</span>
      {% elif c == 'C' %}
        <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;background:#fce7f3;color:#9d174d;">C</span>
      {% else %}
        <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;background:#f1f5f9;color:#475569;">{{ c }}</span>
      {% endif %}
    {% endfor %}
  {% else %}
    <span class="cell-dim">—</span>
  {% endif %}
  ```

- [ ] **Step 2：手动验证**

  在 Django shell 里给一个模块设置多值：
  ```python
  from app01.models import SeqModule
  m = SeqModule.objects.first()
  m.base_char = 'A,U'
  m.save()
  ```
  刷新 `/seqmodule_list/`，该行应显示两个 pill：蓝色 A + 橙色 U，并排显示。

- [ ] **Step 3：Commit**

  ```bash
  git add templates/seqmodule_list.html
  git commit -m "feat: display multi-value base_char as multiple pills in seqmodule_list"
  ```

---

## Task 4：`run_preflight_check` — 检测多值 token → `ambiguous_pairs`

**Files:**
- Modify: `app01/views.py` (`run_preflight_check` 函数，line 1303–1471)

这是核心改动。`group_sequences()` 不动，检测逻辑全部在 `run_preflight_check()` 内完成。

- [ ] **Step 1：在 `run_preflight_check` 内构建 `_ambig_map` / `_ambig_re`，并将 `_sm_norm_re` 限制为单值 token**

  找到 `run_preflight_check` 函数内（约 line 1311–1320）：

  ```python
  # ── 原有代码 ──
  _sm_list = sorted(
      SeqModule.objects.filter(base_char__isnull=False).exclude(base_char=''),
      key=lambda m: len(m.keyword), reverse=True,
  )
  _sm_map = {m.keyword.upper(): m.base_char for m in _sm_list}
  _sm_norm_re = (
      re.compile('|'.join(re.escape(m.keyword) for m in _sm_list), re.IGNORECASE)
      if _sm_list else None
  )
  ```

  替换为：

  ```python
  _sm_list = sorted(
      SeqModule.objects.filter(base_char__isnull=False).exclude(base_char=''),
      key=lambda m: len(m.keyword), reverse=True,
  )
  _sm_map = {m.keyword.upper(): m.base_char for m in _sm_list}

  # 多值 token（base_char 含逗号）→ 消歧映射
  _ambig_map = {kw: bc for kw, bc in _sm_map.items() if ',' in bc}
  _ambig_sorted = sorted(_ambig_map.keys(), key=len, reverse=True)
  _ambig_re = (
      re.compile('|'.join(re.escape(k) for k in _ambig_sorted), re.IGNORECASE)
      if _ambig_sorted else None
  )

  # _sm_norm_re 只包含单值 token（排除多值），避免裸序列推导出错
  _sm_list_single = [m for m in _sm_list if ',' not in (m.base_char or '')]
  _sm_norm_re = (
      re.compile('|'.join(re.escape(m.keyword) for m in _sm_list_single), re.IGNORECASE)
      if _sm_list_single else None
  )
  ```

- [ ] **Step 2：在输出列表初始化处新增 `ambiguous_pairs = []`**

  找到（约 line 1344）：
  ```python
  auto_register_pairs = []
  unknown_module_pairs = []
  unknown_delivery_warnings = []
  skip_group_indices = set()
  ```

  改为：
  ```python
  auto_register_pairs = []
  unknown_module_pairs = []
  unknown_delivery_warnings = []
  ambiguous_pairs = []           # 新增
  skip_group_indices = set()
  ```

- [ ] **Step 3：在 per-pair 内层循环中收集 `pair_ambig_tokens`，并在外层做判断**

  找到 `for group_idx, (_, project, group) in enumerate(ss_groups):` 循环体，在现有变量初始化后（`pair_has_unknown_module = False` 那组）新增：

  ```python
  pair_ambig_tokens = {}   # { 'BU01': ['A', 'U'] }  — 新增
  ```

  然后在内层 `for label, row in [('ss', ss_row), ('as', as_row)]:` 循环内，找到 `tmp = normalize_tmp_seq_with_combo(clean_seq)` 这行，在它**之后**、`if _sm_norm_re:` 替换之**前**，插入：

  ```python
  # ── [新增] 检测多值 token（必须在 sm 替换之前） ──
  if _ambig_re:
      for match in _ambig_re.finditer(tmp):
          token_upper = match.group(0).upper()
          if token_upper not in pair_ambig_tokens:
              pair_ambig_tokens[token_upper] = [
                  c.strip() for c in _ambig_map[token_upper].split(',')
              ]
  ```

  然后在内层循环结束后（`extracted[label] = {...}` 赋值之后），在现有 `if pair_has_unknown_module:` 判断之前，插入消歧对的处理：

  ```python
  # ── [新增] 消歧对：含多值 token → 归入 ambiguous_pairs ──
  if pair_ambig_tokens:
      skip_group_indices.add(group_idx)
      ambiguous_pairs.append({
          'ss_row_id': ss_row_id,
          'as_row_id': as_row_id,
          'project': str(project).strip(),
          'duplex_preview': str(ss_row['Modify_seq'])[:80],
          'ambig_tokens': pair_ambig_tokens,
          'original_lines': pair_original_lines,
      })
      continue
  ```

  > 此 `continue` 跳过下方的 `if pair_has_unknown_module:` 和裸序列注册检查，与 unknown_module 对的处理方式平行。

- [ ] **Step 4：更新 `return` 字典，新增 `ambiguous_pairs` 键**

  找到函数末尾（约 line 1466）：
  ```python
  return {
      'auto_register_pairs': auto_register_pairs,
      'unknown_module_pairs': unknown_module_pairs,
      'unknown_delivery_warnings': unknown_delivery_warnings,
      'clean_groups': clean_groups,
  }
  ```

  改为：
  ```python
  return {
      'auto_register_pairs': auto_register_pairs,
      'unknown_module_pairs': unknown_module_pairs,
      'unknown_delivery_warnings': unknown_delivery_warnings,
      'ambiguous_pairs': ambiguous_pairs,          # 新增
      'clean_groups': clean_groups,
  }
  ```

- [ ] **Step 5：在 Django shell 中验证检测逻辑**

  ```python
  from app01.models import SeqModule
  # 确认有一个多值 token（Task 1/3 中设置的）
  m = SeqModule.objects.filter(base_char__contains=',').first()
  print(m.keyword, m.base_char)  # 期望：'BU01' 'A,U'（或你设置的）
  ```

  如果没有测试数据，先设置：
  ```python
  SeqModule.objects.get_or_create(keyword='BU01TEST', defaults={'base_char': 'A,U', 'linker_connector': 'o'})
  ```

  然后准备一个最小化 CSV（在 Django shell 里直接用 df）：
  ```python
  import pandas as pd
  from io import StringIO
  from app01.views import group_sequences, run_preflight_check

  csv_content = """Seq_type,Modify_seq,Project,Transcript,Position
  SS,BU01TEST-Am-Gm,TEST_PROJECT,,
  AS,Cm-Um-BU01TEST,TEST_PROJECT,,
  """
  df = pd.read_csv(StringIO(csv_content))
  df['__row_id'] = range(len(df))
  df['__original_line'] = range(2, len(df)+2)
  df.index = df['__row_id']

  ss_groups, _ = group_sequences(df)
  result = run_preflight_check(df, ss_groups)
  print('ambiguous_pairs:', result['ambiguous_pairs'])
  print('clean_groups:', result['clean_groups'])
  ```

  预期：`ambiguous_pairs` 有 1 条（含 `BU01TEST`），`clean_groups` 为空（该对被排除）。

- [ ] **Step 6：Commit**

  ```bash
  git add app01/views.py
  git commit -m "feat: detect ambiguous multi-value tokens in run_preflight_check, collect ambiguous_pairs"
  ```

---

## Task 5：上传预检 — session 存储 + GET 渲染 + 消歧模板

**Files:**
- Modify: `app01/views.py` (`upload_delivery_info` POST 约 line 2063–2104；`confirm_upload_preflight` GET 约 line 2241–2248)
- Modify: `templates/confirm_upload_preflight.html`

- [ ] **Step 1：`upload_delivery_info` POST — 将 `ambiguous_pairs` 纳入 `needs_confirm` 判断和 session**

  找到（约 line 2072–2097）：
  ```python
  preflight = run_preflight_check(df, ss_groups)
  needs_confirm = (
      bool(preflight['auto_register_pairs'])
      or bool(preflight['unknown_module_pairs'])
      or bool(preflight['unknown_delivery_warnings'])
  )

  if needs_confirm:
      ...
      preflight_serializable = {
          'auto_register_pairs': preflight['auto_register_pairs'],
          'unknown_module_pairs': preflight['unknown_module_pairs'],
          'unknown_delivery_warnings': preflight['unknown_delivery_warnings'],
      }
  ```

  改为：
  ```python
  preflight = run_preflight_check(df, ss_groups)
  needs_confirm = (
      bool(preflight['auto_register_pairs'])
      or bool(preflight['unknown_module_pairs'])
      or bool(preflight['unknown_delivery_warnings'])
      or bool(preflight.get('ambiguous_pairs'))       # 新增
  )

  if needs_confirm:
      ...
      preflight_serializable = {
          'auto_register_pairs': preflight['auto_register_pairs'],
          'unknown_module_pairs': preflight['unknown_module_pairs'],
          'unknown_delivery_warnings': preflight['unknown_delivery_warnings'],
          'ambiguous_pairs': preflight.get('ambiguous_pairs', []),    # 新增
      }
  ```

- [ ] **Step 2：`confirm_upload_preflight` GET — 将 `ambiguous_pairs` 传入模板上下文**

  找到（约 line 2244–2248）：
  ```python
  return render(request, 'confirm_upload_preflight.html', {
      'auto_register_pairs': preflight.get('auto_register_pairs', []),
      'unknown_module_pairs': preflight.get('unknown_module_pairs', []),
      'unknown_delivery_warnings': preflight.get('unknown_delivery_warnings', []),
  })
  ```

  改为：
  ```python
  return render(request, 'confirm_upload_preflight.html', {
      'auto_register_pairs': preflight.get('auto_register_pairs', []),
      'unknown_module_pairs': preflight.get('unknown_module_pairs', []),
      'unknown_delivery_warnings': preflight.get('unknown_delivery_warnings', []),
      'ambiguous_pairs': preflight.get('ambiguous_pairs', []),        # 新增
  })
  ```

- [ ] **Step 3：重写 `confirm_upload_preflight.html` — 整页用一个 `<form>`，顶部插入消歧区块**

  当前模板的 `<form>` 只包裹「确认并上传」按钮。现在消歧 radio 需要提交，所以把整个内容区包进一个 form，并在顶部加消歧区块。

  完整替换 `templates/confirm_upload_preflight.html`：

  ```html
  {% extends "base.html" %}
  {% block content %}
  <div class="ds-container" style="max-width:800px;margin:32px auto;padding:0 16px;">
    <h2 style="font-size:20px;font-weight:700;margin-bottom:24px;">📋 上传预检报告</h2>

    {% if messages %}
      {% for msg in messages %}
        <div class="ds-alert ds-alert-{{ msg.tags }}" style="margin-bottom:12px;">{{ msg }}</div>
      {% endfor %}
    {% endif %}

    <form method="post">
    {% csrf_token %}

    {# ── 消歧区块（最顶部）── #}
    {% if ambiguous_pairs %}
    <div style="margin-bottom:20px;border:1px solid #f59e0b;border-radius:8px;padding:14px 16px;background:#fffbeb;">
      <div style="font-weight:600;margin-bottom:12px;color:#92400e;">
        ⚠️ 以下序列含可对应多碱基的修饰 token，请为每条选择裸碱基（{{ ambiguous_pairs|length }} 对）
      </div>
      {% for pair in ambiguous_pairs %}
      <div style="background:#fff;border:1px solid #fde68a;border-radius:6px;padding:10px 14px;margin-bottom:10px;">
        <div style="font-size:12px;color:#64748b;margin-bottom:8px;">
          原始行 {{ pair.original_lines.0 }}–{{ pair.original_lines.1 }}：
          <code style="font-size:11px;background:#fefce8;padding:2px 6px;border-radius:3px;">{{ pair.duplex_preview }}</code>
        </div>
        {% for token, options in pair.ambig_tokens.items %}
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:6px;">
          <code style="background:#fef3c7;padding:3px 8px;border-radius:4px;font-size:11px;min-width:60px;text-align:center;">{{ token }}</code>
          {% for opt in options %}
          <label style="font-size:13px;cursor:pointer;display:flex;align-items:center;gap:4px;">
            <input type="radio" name="disambig_{{ pair.ss_row_id }}_{{ token }}" value="{{ opt }}" required>
            <span style="font-weight:600;color:#0f172a;">{{ opt }}</span>
          </label>
          {% endfor %}
        </div>
        {% endfor %}
      </div>
      {% endfor %}
    </div>
    {% endif %}

    {# ── 自动注册区块 ── #}
    {% if auto_register_pairs %}
    <details open style="margin-bottom:20px;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;">
      <summary style="font-weight:600;cursor:pointer;color:#0f172a;">
        ✅ 将自动注册裸序列（{{ auto_register_pairs|length }} 对）
      </summary>
      <div style="margin-top:12px;display:flex;flex-direction:column;gap:8px;">
        {% for pair in auto_register_pairs %}
        <div style="background:#f8fafc;border-radius:6px;padding:10px 14px;font-size:13px;font-family:monospace;">
          <div><span style="color:#475569;width:36px;display:inline-block;">SS:</span>
            <span>{{ pair.naked_ss }}</span>
            {% if pair.ss_exists %}<span style="color:#16a34a;margin-left:8px;">（已存在，复用）</span>
            {% else %}<span style="color:#0284c7;margin-left:8px;">（新建）</span>{% endif %}
          </div>
          <div><span style="color:#475569;width:36px;display:inline-block;">AS:</span>
            <span>{{ pair.naked_as }}</span>
            {% if pair.as_exists %}<span style="color:#16a34a;margin-left:8px;">（已存在，复用）</span>
            {% else %}<span style="color:#0284c7;margin-left:8px;">（新建）</span>{% endif %}
          </div>
          {% if pair.transcript %}<div style="color:#64748b;margin-top:4px;">Transcript: {{ pair.transcript }}{% if pair.position %} &nbsp;|&nbsp; Position: {{ pair.position }}{% endif %}</div>{% endif %}
        </div>
        {% endfor %}
      </div>
    </details>
    {% endif %}

    {# ── Delivery 模块警告区块 ── #}
    {% if unknown_delivery_warnings %}
    <div style="margin-bottom:20px;border:1px solid #fcd34d;border-radius:8px;padding:12px 16px;background:#fffbeb;">
      <div style="font-weight:600;margin-bottom:8px;color:#92400e;">⚠️ Delivery 模块未知（{{ unknown_delivery_warnings|length }} 条，上传继续）</div>
      {% for warn in unknown_delivery_warnings %}
      <div style="font-size:13px;color:#78350f;margin-bottom:4px;">
        行 {{ warn.original_line }}：token
        {% for t in warn.unknown_tokens %}<code style="background:#fef3c7;padding:1px 5px;border-radius:3px;">{{ t }}</code> {% endfor %}
        未在 DeliveryModule 中找到
      </div>
      {% endfor %}
    </div>
    {% endif %}

    {# ── SeqModule 未知（跳过）区块 ── #}
    {% if unknown_module_pairs %}
    <div style="margin-bottom:20px;border:1px solid #fca5a5;border-radius:8px;padding:12px 16px;background:#fff1f2;">
      <div style="font-weight:600;margin-bottom:8px;color:#9f1239;">❌ SeqModule 未知，已跳过（{{ unknown_module_pairs|length }} 对）</div>
      {% for pair in unknown_module_pairs %}
      <div style="font-size:13px;color:#be123c;margin-bottom:4px;">
        行 {{ pair.original_lines|join:"–" }}：未知 token
        {% for t in pair.unknown_tokens %}<code style="background:#ffe4e6;padding:1px 5px;border-radius:3px;">{{ t }}</code> {% endfor %}
      </div>
      {% endfor %}
      <a href="?download=skip_csv" class="ds-btn ds-btn-secondary" style="margin-top:10px;display:inline-block;font-size:13px;">
        ⬇ 下载跳过序列 CSV
      </a>
    </div>
    {% endif %}

    {# ── 操作按钮 ── #}
    <div style="display:flex;gap:12px;justify-content:flex-end;margin-top:24px;">
      <a href="{% url 'seq_delivery' %}" class="ds-btn ds-btn-secondary">取消</a>
      <button type="submit" class="ds-btn ds-btn-primary">确认并上传</button>
    </div>

    </form>
  </div>
  {% endblock %}
  ```

- [ ] **Step 4：手动验证**

  上传含 `BU01TEST` 的 CSV（见 Task 4 Step 5 中的 csv_content），检查预检页：
  - 顶部出现橙色消歧区块，有 radio 选项 A / U
  - 原有 auto_register、unknown_delivery、unknown_module 区块正常显示
  - 不选 radio 直接提交 → 浏览器阻止（`required`）

- [ ] **Step 5：Commit**

  ```bash
  git add app01/views.py templates/confirm_upload_preflight.html
  git commit -m "feat: add ambiguous_pairs to preflight session, add disambiguation UI to confirm page"
  ```

---

## Task 6：`confirm_upload_preflight` POST 消歧 + `save_deliveries` override

**Files:**
- Modify: `app01/views.py` (`confirm_upload_preflight` POST，约 line 2250–2352；`save_deliveries`，约 line 1765)

这是最复杂的任务，分步实现。

- [ ] **Step 1：修改 `save_deliveries` 签名，接受 `sm_overrides` 参数**

  找到（line 1765）：
  ```python
  def save_deliveries(df, duplex_id_map, username):
  ```

  改为：
  ```python
  def save_deliveries(df, duplex_id_map, username, sm_overrides=None):
  ```

  找到函数内（约 line 1779）：
  ```python
  _sm_map = {m.keyword.upper(): m.base_char for m in _sm_list}
  ```

  在该行之后插入：
  ```python
  # 应用外部消歧覆盖（供含多值 token 的序列上传后正确推导裸序列）
  if sm_overrides:
      _sm_map.update({k.upper(): v for k, v in sm_overrides.items()})
  ```

- [ ] **Step 2：在 `confirm_upload_preflight` POST 的最顶部（try 块内首行）读取消歧选择**

  找到 `if request.method == 'POST':` 下的 `try:` 块，在 `preflight = request.session.get('preflight_result', {})` 之前插入：

  ```python
  # ── 0. 读取消歧选择 ──
  disambig_choices = {}  # { ss_row_id (int): { 'BU01': 'A' } }
  for key, val in request.POST.items():
      if key.startswith('disambig_'):
          parts = key.split('_', 2)
          if len(parts) == 3:
              try:
                  row_id = int(parts[1])
              except ValueError:
                  continue
              token = parts[2]
              disambig_choices.setdefault(row_id, {})[token] = val.strip()

  # 构建全局 sm_overrides（token→单值，同一批次内同一 token 的选择相同）
  sm_overrides = {}
  for token_choices in disambig_choices.values():
      for token, char in token_choices.items():
          sm_overrides.setdefault(token.upper(), char)
  ```

- [ ] **Step 3：在 `auto_register_bare_sequences` 调用之后、`df` 恢复之前，插入消歧对处理逻辑**

  找到（约 line 2274）：
  ```python
  # ── 2. 从 session 恢复 df 和 clean_groups ──
  df = pd.read_json(StringIO(df_json))
  ```

  在该行之前、自动注册步骤之后，插入：
  > 注意：插入位置是 `auto_register_bare_sequences` 调用后、df 恢复前。

  实际上，df 和 clean_groups 恢复之后才能处理消歧对（需要读 df.loc[row_id]）。所以插入位置是 clean_groups 恢复之后（约 line 2282 之后）。找到：

  ```python
  raw_groups = json.loads(clean_groups_json)
  clean_groups = [(g[0], g[1], g[2]) for g in raw_groups]
  ```

  在这两行之后插入：

  ```python
  # ── [新增] 消歧对处理：将用户选择的 base_char 用于推导裸序列，并入 clean_groups ──
  ambiguous_pairs_session = preflight.get('ambiguous_pairs', [])
  if ambiguous_pairs_session and disambig_choices:
      # 构建用于裸序列推导的 sm_map（含消歧覆盖）
      from app01.models import SeqModule as _SM
      _sm_for_disambig = sorted(
          _SM.objects.filter(base_char__isnull=False).exclude(base_char=''),
          key=lambda m: len(m.keyword), reverse=True,
      )
      _sm_map_disambig = {m.keyword.upper(): m.base_char for m in _sm_for_disambig}
      _sm_map_disambig.update({k.upper(): v for k, v in sm_overrides.items()})
      _sm_re_disambig = (
          re.compile('|'.join(re.escape(m.keyword) for m in _sm_for_disambig), re.IGNORECASE)
          if _sm_for_disambig else None
      )

      ambig_auto_pairs = []   # 需要自动注册的消歧对
      for pair in ambiguous_pairs_session:
          ss_rid = pair['ss_row_id']
          if ss_rid not in disambig_choices:
              continue  # 用户未提交该对的选择（前端 required 应阻止，但防御性跳过）

          ambig_naked = {}
          for label, row_id in [('ss', ss_rid), ('as', pair['as_row_id'])]:
              row = df.loc[row_id]
              full_seq = str(row['Modify_seq'])
              clean_seq = re.sub(r'^\[.*?\]', '', full_seq)
              clean_seq = re.sub(r'\[.*?\]$', '', clean_seq)
              tmp = normalize_tmp_seq_with_combo(clean_seq)
              if _sm_re_disambig:
                  tmp = _sm_re_disambig.sub(
                      lambda m, mp=_sm_map_disambig: mp[m.group(0).upper()], tmp
                  )
              tmp = re.sub(r'\(.*?\)', '', tmp)
              naked_seq = ''.join(re.findall(r'(INVAB|[AUGCI])', tmp))
              ambig_naked[label] = naked_seq

          # 检查裸序列是否已注册
          ss_exists = Sequence.objects.filter(seq=ambig_naked['ss'], seq_type='SS').exists()
          as_exists = Sequence.objects.filter(seq=ambig_naked['as'], seq_type='AS').exists()
          if not ss_exists or not as_exists:
              ambig_auto_pairs.append({
                  'ss_row_id': ss_rid,
                  'as_row_id': pair['as_row_id'],
                  'naked_ss': ambig_naked['ss'],
                  'naked_as': ambig_naked['as'],
                  'ss_exists': ss_exists,
                  'as_exists': as_exists,
                  'transcript': '',
                  'position': '',
                  'project': pair['project'],
              })

          # 将消歧对并入 clean_groups
          clean_groups.append((None, pair['project'], [ss_rid, pair['as_row_id']]))

      # 自动注册消歧对的裸序列（如有未注册）
      if ambig_auto_pairs and user_type != 'guest':
          reg_log2, skip_log2 = auto_register_bare_sequences(
              ambig_auto_pairs, request.user.username
          )
          if reg_log2:
              messages.success(request, f"消歧后自动注册 {len(reg_log2)} 条序列")
          if skip_log2:
              messages.warning(request, f"{len(skip_log2)} 对消歧序列注册失败，已跳过")
          # 从 clean_groups 移除注册失败的
          if skip_log2:
              failed_ss = {e['naked_ss'] for e in skip_log2 if e.get('naked_ss')}
              failed_rids = set()
              for p in ambig_auto_pairs:
                  if p.get('naked_ss') in failed_ss:
                      failed_rids.update([p['ss_row_id'], p['as_row_id']])
              if failed_rids:
                  clean_groups = [g for g in clean_groups if not any(r in failed_rids for r in g[2])]
  ```

- [ ] **Step 4：在调用 `save_deliveries` 时传入 `sm_overrides`**

  找到（约 line 2323）：
  ```python
  upload_meg, upload_log, unregistered_meg, unregistered_log = save_deliveries(
      df, duplex_id_map, username
  )
  ```

  改为：
  ```python
  upload_meg, upload_log, unregistered_meg, unregistered_log = save_deliveries(
      df, duplex_id_map, username, sm_overrides=sm_overrides if sm_overrides else None
  )
  ```

  同样检查 `confirm_share` 视图（约 line 2200–2214）内也有 `save_deliveries` 调用，它不涉及消歧对（cross_project 流程），无需传 sm_overrides，保持原样即可。

- [ ] **Step 5：手动 end-to-end 验证**

  准备含 `BU01TEST`（base_char='A,U'）的测试 CSV：
  ```
  Seq_type,Modify_seq,Project
  SS,[L96]BU01TEST-Am-Gm-Am-Cm,TEST_PROJECT
  AS,[L96]Gm-Um-Cm-BU01TEST-Cm,TEST_PROJECT
  ```

  操作步骤：
  1. 上传 CSV → 跳转预检页 → 消歧区块出现 BU01TEST，有 A/U 两个 radio
  2. 选择 A → 点「确认并上传」
  3. 观察：
     - 若 naked_seq（去 BU01TEST → A）对应 Sequence 已存在 → 上传成功
     - 若不存在 → 先自动注册，再上传
  4. 在 DB 中验证 Delivery 记录的 `modify_seq` 仍为 `BU01TEST-Am-...`（原始值，未被替换）
  5. 对应 Sequence.seq 包含 A（非 A,U 两个字符）

- [ ] **Step 6：Commit**

  ```bash
  git add app01/views.py
  git commit -m "feat: disambiguate multi-value tokens in confirm_upload_preflight POST, pass sm_overrides to save_deliveries"
  ```

---

## Task 7：SeqModule 列表分页保留

**Files:**
- Modify: `templates/seqmodule_list.html`
- Modify: `templates/edit_seqmodule.html`
- Modify: `app01/views.py` (`delete_seqmodule` 约 line 3474；`edit_seqmodule` 约 line 3431)

- [ ] **Step 1：`seqmodule_list.html` — 删除 form 加 `page`/`q` hidden 字段**

  找到（约 line 57–61）：
  ```html
  <form method="POST" action="{% url 'delete_seqmodule' %}" style="display:inline;" onsubmit="return confirm('确定删除该修饰模块？');">
    {% csrf_token %}
    <input type="hidden" name="id" value="{{ module.id }}">
    <button type="submit" class="ds-act ds-act-delete">删除</button>
  </form>
  ```

  改为：
  ```html
  <form method="POST" action="{% url 'delete_seqmodule' %}" style="display:inline;" onsubmit="return confirm('确定删除该修饰模块？');">
    {% csrf_token %}
    <input type="hidden" name="id" value="{{ module.id }}">
    <input type="hidden" name="page" value="{{ page_obj.number }}">
    <input type="hidden" name="q" value="{{ q }}">
    <button type="submit" class="ds-act ds-act-delete">删除</button>
  </form>
  ```

- [ ] **Step 2：`seqmodule_list.html` — 编辑链接携带 `page`/`q`**

  找到（约 line 56）：
  ```html
  <a href="{% url 'edit_seqmodule' %}?id={{ module.id }}" class="ds-act ds-act-edit">编辑</a>
  ```

  改为：
  ```html
  <a href="{% url 'edit_seqmodule' %}?id={{ module.id }}&page={{ page_obj.number }}&q={{ q|urlencode }}" class="ds-act ds-act-edit">编辑</a>
  ```

- [ ] **Step 3：`delete_seqmodule` 视图 — 读取 `page`/`q`，redirect 时携带**

  找到（约 line 3483）：
  ```python
  module.delete()
  return redirect('/seqmodule_list/')
  ```

  改为：
  ```python
  module.delete()
  page = request.POST.get('page', 1)
  q = request.POST.get('q', '')
  qs = f'?page={page}'
  if q:
      from urllib.parse import quote
      qs += f'&q={quote(q)}'
  return redirect(f'/seqmodule_list/{qs}')
  ```

- [ ] **Step 4：`edit_seqmodule` 视图 — GET 读取 `page`/`q`；保存后 redirect 携带；渲染时传给模板**

  找到（约 line 3436）：
  ```python
  module_id = request.GET.get('id')
  module = None
  ```

  改为：
  ```python
  module_id = request.GET.get('id')
  page = request.GET.get('page', 1)
  q = request.GET.get('q', '')
  module = None
  ```

  找到 POST 分支中的两处 `return redirect('/seqmodule_list/')` （新建成功 & 更新成功），都改为：
  ```python
  page = request.POST.get('page', 1)
  q = request.POST.get('q', '')
  qs = f'?page={page}'
  if q:
      from urllib.parse import quote
      qs += f'&q={quote(q)}'
  return redirect(f'/seqmodule_list/{qs}')
  ```

  找到函数末尾（GET 渲染）：
  ```python
  return render(request, 'edit_seqmodule.html', {'module': module})
  ```

  改为：
  ```python
  return render(request, 'edit_seqmodule.html', {'module': module, 'page': page, 'q': q})
  ```

  以及所有 POST 分支中 `return render(request, 'edit_seqmodule.html', {...})` 的表单校验失败路径，都追加 `'page': request.POST.get('page', 1), 'q': request.POST.get('q', '')` 到 context dict（共 2 处：keyword 重复告警的两个 render 调用）。

- [ ] **Step 5：`edit_seqmodule.html` — 加 `page`/`q` hidden 字段 + 更新「返回」链接**

  在 `<form>` 内（`{% csrf_token %}` 之后）加：
  ```html
  <input type="hidden" name="page" value="{{ page|default:1 }}">
  <input type="hidden" name="q" value="{{ q|default:'' }}">
  ```

  同时更新两处「返回」链接（topbar 和底部），使用动态 URL：
  ```html
  {# topbar #}
  <a href="{% url 'seqmodule_list' %}{% if page %}?page={{ page }}&q={{ q|urlencode }}{% endif %}" class="ds-btn ds-btn-ghost">返回列表</a>
  
  {# 底部按钮 #}
  <a href="{% url 'seqmodule_list' %}{% if page %}?page={{ page }}&q={{ q|urlencode }}{% endif %}" class="ds-btn ds-btn-ghost">返回</a>
  ```

- [ ] **Step 6：手动验证**

  1. 导航至 `/seqmodule_list/?page=2`（或有多页时）
  2. 点击某行「编辑」→ 编辑页 URL 含 `?id=...&page=2&q=`
  3. 保存 → 返回 `/seqmodule_list/?page=2`（不回到第 1 页）
  4. 点击某行「删除」→ 返回 `/seqmodule_list/?page=2`
  5. 删除某页最后一条 → Django Paginator 自动返回最后一页（无需额外处理）

- [ ] **Step 7：Commit**

  ```bash
  git add templates/seqmodule_list.html templates/edit_seqmodule.html app01/views.py
  git commit -m "feat: preserve page/q params after seqmodule delete and edit"
  ```

---

## Task 8：LinkerModule 列表分页保留

**Files:**
- Modify: `templates/linkermodule_list.html`
- Modify: `templates/edit_linkermodule.html`
- Modify: `app01/views.py` (`delete_linkermodule` 约 line 4641；`edit_linkermodule` 约 line 4601)

与 Task 7 完全平行，只替换 `seqmodule` → `linkermodule`。

- [ ] **Step 1：`linkermodule_list.html` — 删除 form 加 `page`/`q` hidden 字段**

  找到删除 form（结构与 seqmodule_list 相同）：
  ```html
  <form method="POST" action="{% url 'delete_linkermodule' %}" ... >
    {% csrf_token %}
    <input type="hidden" name="id" value="{{ module.id }}">
    <button type="submit" ...>删除</button>
  </form>
  ```

  加入：
  ```html
  <input type="hidden" name="page" value="{{ page_obj.number }}">
  <input type="hidden" name="q" value="{{ q }}">
  ```

- [ ] **Step 2：`linkermodule_list.html` — 编辑链接携带 `page`/`q`**

  找到编辑链接（格式：`?id={{ module.id }}`），改为：
  ```html
  <a href="{% url 'edit_linkermodule' %}?id={{ module.id }}&page={{ page_obj.number }}&q={{ q|urlencode }}" ...>编辑</a>
  ```

- [ ] **Step 3：`delete_linkermodule` 视图 — 读取并携带 `page`/`q`**

  找到（约 line 4650）：
  ```python
  module.delete()
  return redirect('/linkermodule_list/')
  ```

  改为：
  ```python
  module.delete()
  page = request.POST.get('page', 1)
  q = request.POST.get('q', '')
  qs = f'?page={page}'
  if q:
      from urllib.parse import quote
      qs += f'&q={quote(q)}'
  return redirect(f'/linkermodule_list/{qs}')
  ```

- [ ] **Step 4：`edit_linkermodule` 视图 — GET 读取；保存 redirect 携带；渲染传给模板**

  找到 `module_id = request.GET.get('id')` 那行，之后追加：
  ```python
  page = request.GET.get('page', 1)
  q = request.GET.get('q', '')
  ```

  所有 `return redirect('/linkermodule_list/')` 改为：
  ```python
  page = request.POST.get('page', 1)
  q = request.POST.get('q', '')
  qs = f'?page={page}'
  if q:
      from urllib.parse import quote
      qs += f'&q={quote(q)}'
  return redirect(f'/linkermodule_list/{qs}')
  ```

  函数末尾 GET 渲染：
  ```python
  return render(request, 'edit_linkermodule.html', {'module': module, 'page': page, 'q': q})
  ```

  同样更新 POST 分支中校验失败的 render 调用（共 2 处），追加 `'page': request.POST.get('page', 1), 'q': request.POST.get('q', '')` 到 context。

- [ ] **Step 5：`edit_linkermodule.html` — 加 hidden 字段 + 更新返回链接**

  在 `<form>` 内 `{% csrf_token %}` 之后加：
  ```html
  <input type="hidden" name="page" value="{{ page|default:1 }}">
  <input type="hidden" name="q" value="{{ q|default:'' }}">
  ```

  更新两处「返回」链接（topbar + 底部）：
  ```html
  <a href="{% url 'linkermodule_list' %}{% if page %}?page={{ page }}&q={{ q|urlencode }}{% endif %}" class="ds-btn ds-btn-ghost">返回列表</a>
  ```

  ```html
  <a href="{% url 'linkermodule_list' %}{% if page %}?page={{ page }}&q={{ q|urlencode }}{% endif %}" class="ds-btn ds-btn-ghost">返回</a>
  ```

- [ ] **Step 6：手动验证**

  同 Task 7 Step 6，对 `/linkermodule_list/?page=2` 进行相同测试。

- [ ] **Step 7：Commit**

  ```bash
  git add templates/linkermodule_list.html templates/edit_linkermodule.html app01/views.py
  git commit -m "feat: preserve page/q params after linkermodule delete and edit"
  ```

---

## 自检：Spec 覆盖确认

| 规范要求 | 对应任务 | 覆盖？ |
|---------|---------|-------|
| `SeqModule.base_char` max_length 10→32 | T1 | ✅ |
| migration | T1 | ✅ |
| `base_char_list` 属性 | T1 | ✅ |
| edit 页 hint 文字 | T2 | ✅ |
| edit 视图 A/U/G/C/I/INVAB 校验 | T2 | ✅ |
| list 页多值显示（多个 pill） | T3 | ✅ |
| 多值 token 在 preflight 中检测 | T4 | ✅ |
| 检测结果加入 session 和 GET 上下文 | T5 | ✅ |
| 消歧区块 UI（radio buttons） | T5 | ✅ |
| 消歧选择为 required（前端阻止漏选） | T5 | ✅ |
| confirm POST 读 disambig_* 字段 | T6 | ✅ |
| 消歧后推导裸序列、自动注册 | T6 | ✅ |
| 消歧对并入 clean_groups | T6 | ✅ |
| save_deliveries 使用 sm_overrides | T6 | ✅ |
| SeqModule 删除/编辑分页保留 | T7 | ✅ |
| LinkerModule 删除/编辑分页保留 | T8 | ✅ |
| 超出页码边界 → get_page 自动修正 | — | ✅（Django Paginator 默认处理） |

**注：** 设计规范中 `group_sequences` 返回三元组的说法已在本计划中更正为：三元组检测不改动 `group_sequences`，全部在 `run_preflight_check` 完成。
