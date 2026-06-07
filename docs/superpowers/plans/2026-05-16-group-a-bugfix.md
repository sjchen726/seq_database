# Group A Bug Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 5 个数据/逻辑层 Bug（A1–A5），全部独立、无依赖，按建议顺序执行。

**Architecture:** 所有改动均在 `app01/views.py`（后端逻辑）和 `static/js/tables.js`（前端 JS）中完成，无新文件、无 DB migration。A2 额外提取 `_reverse_tokens()` 辅助函数（同文件），A3 同时修改 JS 与 View。

**Tech Stack:** Django 5.1 · Python 3.10 · MySQL · jQuery/DataTables (tables.js)

---

## 文件变动清单

| 文件 | 改动 |
|------|------|
| `app01/views.py:1147` | A1 — connector 判断加排除 `'o'`/`'-'` |
| `app01/views.py:1956-1961` | A5 — Remark None 拼接修复 |
| `app01/views.py:1270-1282` | A4 — check_duplicates 改用 linker_seq |
| `app01/views.py:2615-2638` | A3 — download_selected 简化为 duplex_id 查询 |
| `app01/views.py:168` (新增) | A2 — 提取 `_reverse_tokens()` 辅助函数 |
| `app01/views.py:2187` | A2 — as_p2 反转后再对齐 |
| `static/js/tables.js:278-337` | A3 — 移除 seqType 读取，CSRF 改读 cookie |

---

## Task 1：A1 — G(moe) 双重 connector 修复

**文件：** `app01/views.py:1147`

- [ ] **Step 1: 定位并修改 connector 判断**

  找到 `app01/views.py` 第 1147 行：

  ```python
  # 修改前
  if connector and end < len(modify_seq) and modify_seq[end] != 's':
  ```

  改为：

  ```python
  # 修改后
  if connector and end < len(modify_seq) and modify_seq[end] not in ('s', 'o', '-'):
  ```

- [ ] **Step 2: Django shell 验证**

  ```bash
  source venv/bin/activate
  python manage.py shell
  ```

  ```python
  from app01.views import add_o_to_all_rules_safe
  # 正常序列不受影响
  assert add_o_to_all_rules_safe("GmoU") == "GmoU",  f"got: {add_o_to_all_rules_safe('GmoU')}"
  # 无显式 o 时正常追加
  r = add_o_to_all_rules_safe("GmU")
  assert 'o' in r, f"got: {r}"
  # 已有 s 时不追加
  r2 = add_o_to_all_rules_safe("GmsU")
  assert r2 == "GmsU", f"got: {r2}"
  print("A1 all pass")
  ```

  预期输出：`A1 all pass`

- [ ] **Step 3: Commit**

  ```bash
  git add app01/views.py
  git commit -m "fix: skip connector append when next char is already 'o' or '-'"
  ```

---

## Task 2：A5 — Remark None 拼接修复

**文件：** `app01/views.py:1956-1961`

- [ ] **Step 1: 定位并替换 Remark 拼接逻辑**

  找到 `app01/views.py` 第 1956–1961 行（在 `build_sequence_data()` 函数中）：

  ```python
  # 修改前
  remark = (
      f"{seqinfo.Remark}\n{get_attr(deliveries[0], 'Remark')}"
      if seqinfo and deliveries else
      seqinfo.Remark if seqinfo else
      get_attr(deliveries[0], 'Remark') if deliveries else None
  )
  ```

  改为：

  ```python
  # 修改后
  _remark_parts = [
      seqinfo.Remark if seqinfo and seqinfo.Remark else None,
      get_attr(deliveries[0], 'Remark') if deliveries else None,
  ]
  remark = '\n'.join(p for p in _remark_parts if p) or None
  ```

- [ ] **Step 2: Django shell 验证**

  ```python
  # 模拟 build_sequence_data 中的 remark 逻辑
  def _test_remark(seqinfo_remark, delivery_remark):
      class FakeSeqinfo:
          Remark = seqinfo_remark
      class FakeDelivery:
          Remark = delivery_remark
      seqinfo = FakeSeqinfo() if seqinfo_remark is not None else None
      deliveries = [FakeDelivery()]

      get_attr = lambda obj, attr: getattr(obj, attr, None)

      _remark_parts = [
          seqinfo.Remark if seqinfo and seqinfo.Remark else None,
          get_attr(deliveries[0], 'Remark') if deliveries else None,
      ]
      return '\n'.join(p for p in _remark_parts if p) or None

  assert _test_remark(None, None) is None
  assert _test_remark("Hello", None) == "Hello"
  assert _test_remark(None, "World") == "World"
  assert _test_remark("Hello", "World") == "Hello\nWorld"
  # seqinfo.Remark=None 时不应出现 "None"
  r = _test_remark(None, "OK")
  assert "None" not in str(r), f"got: {r}"
  print("A5 all pass")
  ```

  预期输出：`A5 all pass`

- [ ] **Step 3: Commit**

  ```bash
  git add app01/views.py
  git commit -m "fix: prevent 'None' string in Remark when seqinfo.Remark is None"
  ```

---

## Task 3：A4 — check_duplicates 改用 linker_seq

**文件：** `app01/views.py:1270-1282`

- [ ] **Step 1: 定位 SS 查重块并修改**

  找到 `app01/views.py` 第 1270–1274 行（`check_duplicates()` 函数内）：

  ```python
  # 修改前
  ss_deliveries = Delivery.objects.filter(
      modify_seq=ss_clean_seq,
      delivery5=ss_d5,
      delivery3=ss_d3
  ).prefetch_related('project_links')
  ```

  改为：

  ```python
  # 修改后
  ss_linker_seq = add_o_to_all_rules_safe(ss_clean_seq)
  ss_deliveries = Delivery.objects.filter(
      linker_seq=ss_linker_seq,
      delivery5=ss_d5,
      delivery3=ss_d3
  ).prefetch_related('project_links')
  ```

- [ ] **Step 2: 定位 AS 查重块并修改**

  在同一函数中，找到对应的 AS 查重 `Delivery.objects.filter(modify_seq=as_clean_seq, ...)` 行（紧接在 SS 查重块之后约第 1277–1282 行）：

  ```python
  # 修改前
  exists_as = Delivery.objects.filter(
      modify_seq=as_clean_seq,
      delivery5=as_d5,
      delivery3=as_d3,
      duplex_id=ss_del.duplex_id
  ).exists()
  ```

  改为：

  ```python
  # 修改后
  as_linker_seq = add_o_to_all_rules_safe(as_clean_seq)
  exists_as = Delivery.objects.filter(
      linker_seq=as_linker_seq,
      delivery5=as_d5,
      delivery3=as_d3,
      duplex_id=ss_del.duplex_id
  ).exists()
  ```

- [ ] **Step 3: 验证 `add_o_to_all_rules_safe` 已在函数作用域内可访问**

  ```bash
  grep -n "def add_o_to_all_rules_safe\|def check_duplicates" app01/views.py
  ```

  确认 `add_o_to_all_rules_safe` 定义在 `check_duplicates` 之前（行号较小），否则将 `add_o_to_all_rules_safe` 的定义移到 `check_duplicates` 之前。

- [ ] **Step 4: Commit**

  ```bash
  git add app01/views.py
  git commit -m "fix: check_duplicates now queries by linker_seq to match save_deliveries logic"
  ```

---

## Task 4：A3 — download_selected 修复（JS + View）

**文件：** `static/js/tables.js:278-337`，`app01/views.py:2615-2638`

### 4a — JS 端修复

- [ ] **Step 1: 添加 getCsrfFromCookie 辅助函数**

  在 `static/js/tables.js` 文件顶部（或在 download 按钮事件监听器之前），添加：

  ```javascript
  function getCsrfFromCookie() {
      const match = document.cookie.match(/csrftoken=([^;]+)/);
      return match ? match[1] : '';
  }
  ```

- [ ] **Step 2: 替换 download 按钮事件中的数据收集逻辑**

  找到 `static/js/tables.js` 第 278–293 行：

  ```javascript
  // 修改前
  // ✅ 获取选中行中的 duplex_id 和 seq_type
  const selectedIds = [];
  const selectedSeqTypes = [];

  table.rows().every(function() {
      const row = this.node();
      if ($(row).find('input.row-checkbox').prop('checked')) {
          const duplexId = $(row).find('td:nth-child(2)').text().trim();
          const seqType = $(row).find('td:nth-child(5)').text().trim();

          if (duplexId && seqType) {
              selectedIds.push(duplexId);
              selectedSeqTypes.push(seqType);
          }
      }
  });

  if (selectedIds.length === 0) {
      alert("请先选择至少一条序列");
      return;
  }
  ```

  改为：

  ```javascript
  // 修改后
  const selectedIds = [];

  table.rows().every(function() {
      const row = this.node();
      if ($(row).find('input.row-checkbox').prop('checked')) {
          const duplexId = $(row).find('td:nth-child(2)').text().trim();
          if (duplexId) {
              selectedIds.push(duplexId);
          }
      }
  });

  if (selectedIds.length === 0) {
      alert("请先选择至少一条序列");
      return;
  }
  ```

- [ ] **Step 3: 替换 CSRF token 读取方式**

  找到第 306 行：

  ```javascript
  // 修改前
  const csrfToken = document.querySelector('input[name=csrfmiddlewaretoken]').value;
  ```

  改为：

  ```javascript
  // 修改后
  const csrfToken = getCsrfFromCookie();
  ```

- [ ] **Step 4: 移除 selected_seq_types 表单字段**

  找到第 329–334 行（表单提交代码中）：

  ```javascript
  // 删除整个 seq_type 列表块
  // ✅ seq_type 列表
  form.appendChild(Object.assign(document.createElement('input'), {
      type: 'hidden',
      name: 'selected_seq_types',
      value: JSON.stringify(selectedSeqTypes)
  }));
  ```

  将这 7 行全部删除。

### 4b — View 端修复

- [ ] **Step 5: 修改 download_selected view**

  找到 `app01/views.py` 第 2617–2638 行：

  ```python
  # 修改前
  selected_seq_types = request.POST.get('selected_seq_types')
  selected_columns = request.POST.get('selected_columns')

  if not selected_ids or not selected_columns or not selected_seq_types:
      return HttpResponse("参数缺失", status=400)

  try:
      ids = json.loads(selected_ids)
      types = json.loads(selected_seq_types)
      seq_ids = [t.split('_', 1)[-1] if '_' in t else t for t in types]
      columns = json.loads(selected_columns)
  except json.JSONDecodeError:
      return HttpResponse("参数格式错误", status=400)

  query = Q()
  for duplex_id, seq_ids in zip(ids, seq_ids):
      query |= Q(duplex_id=duplex_id, delivery_id=seq_ids)
   #   print(duplex_id, seq_ids)

  deliveries = Delivery.objects.filter(query)\
      .select_related('sequence')\
      .prefetch_related('sequence__target_info')
  ```

  改为：

  ```python
  # 修改后
  selected_columns = request.POST.get('selected_columns')

  if not selected_ids or not selected_columns:
      return HttpResponse("参数缺失", status=400)

  try:
      ids = json.loads(selected_ids)
      columns = json.loads(selected_columns)
  except json.JSONDecodeError:
      return HttpResponse("参数格式错误", status=400)

  deliveries = Delivery.objects.filter(duplex_id__in=ids)\
      .select_related('sequence')\
      .prefetch_related('sequence__target_info')
  ```

  同时确认第 2615 行的 `selected_ids = request.POST.get('selected_ids')` 保留不动（该行在修改范围之前）。

- [ ] **Step 6: 浏览器手动验证**

  1. 启动开发服务器：`python manage.py runserver`
  2. 登录后进入序列列表页
  3. 勾选 1–3 条序列（包含 duplex 行，即 SS+AS 同一行）
  4. 点击"下载选中"按钮
  5. 预期：弹出 CSV 下载，文件包含所勾选 duplex_id 对应的全部 Delivery 记录（SS + AS 均在内）；不再出现"未找到匹配的序列" 404

- [ ] **Step 7: Commit**

  ```bash
  git add static/js/tables.js app01/views.py
  git commit -m "fix: download_selected queries by duplex_id only; CSRF token read from cookie"
  ```

---

## Task 5：A2 — Part2 AS/SS 对齐列宽修复

**文件：** `app01/views.py:168`（新增），`app01/views.py:286-320`（重构），`app01/views.py:2187`（调用）

### 5a — 提取 `_reverse_tokens()` 辅助函数

- [ ] **Step 1: 在 `get_modify_seq_colored` 定义之前插入 `_reverse_tokens`**

  找到 `app01/views.py` 第 169 行（`def get_modify_seq_colored(...):`），在其**正上方**插入以下函数：

  ```python
  def _reverse_tokens(tokens):
      """Group-based reversal: nucleotides are grouped with their preceding linkers (s/o/ss),
      then the group order is reversed. Used for alignment of AS Part2 with SS Part2."""
      LINKERS = {'ss', 's', 'o'}
      groups = []
      current_group = None
      for item in tokens:
          if item['char'] in LINKERS:
              if current_group is not None:
                  current_group['subs'].append(item)
              else:
                  groups.append({'main': item, 'subs': []})
          else:
              if current_group is not None:
                  groups.append(current_group)
              current_group = {'main': item, 'subs': []}
      if current_group is not None:
          groups.append(current_group)

      new_result = []
      prev_main = None
      for group in reversed(groups):
          if prev_main is not None:
              new_result.append(prev_main)
              new_result.extend(group['subs'])
          else:
              new_result.extend(group['subs'])
          prev_main = group['main']
      if prev_main:
          new_result.append(prev_main)
      return new_result
  ```

### 5b — 重构 `get_modify_seq_colored` 中的内联反转块

- [ ] **Step 2: 将内联反转逻辑改为调用 `_reverse_tokens`**

  找到 `app01/views.py` 第 286–320 行（`get_modify_seq_colored` 末尾的 `# === 7) 保留你原来的 SS 分组反转逻辑 ===` 块）：

  ```python
  # 修改前（286-320 行）
  if seq_type == reversed_seq_type:
      groups = []
      current_group = None

      for item in result:
          if item['char'] in ['ss', 's', 'o']:
              if current_group is not None:
                  current_group['subs'].append(item)
              else:
                  groups.append({'main': item, 'subs': []})
          else:
              if current_group is not None:
                  groups.append(current_group)
              current_group = {'main': item, 'subs': []}

      if current_group is not None:
          groups.append(current_group)

      # 反转组并组合成新结果（subs + 上一组 main）
      new_result = []
      prev_main = None

      for group in reversed(groups):
          if prev_main is not None:
              new_result.append(prev_main)
              new_result.extend(group['subs'])
          else:
              # 第一组只有 subs，先插入
              new_result.extend(group['subs'])
          prev_main = group['main']

      if prev_main:
          new_result.append(prev_main)

      result = new_result

  return result
  ```

  改为：

  ```python
  # 修改后
  if seq_type == reversed_seq_type:
      result = _reverse_tokens(result)

  return result
  ```

### 5c — 在 Part2 对齐时反转 as_p2

- [ ] **Step 3: 修改 `build_duplex_groups` 中 Part2 对齐调用**

  找到 `app01/views.py` 第 2185–2188 行（`build_duplex_groups()` 函数中）：

  ```python
  # 修改前
  aligned = (
      align_duplex_tokens(ss_p1, as_p1)
      + [{'col_type': 'segment_sep', 'linker_tokens': ss_lk}]
      + align_duplex_tokens(ss_p2, as_p2)
  )
  ```

  改为：

  ```python
  # 修改后
  aligned = (
      align_duplex_tokens(ss_p1, as_p1)
      + [{'col_type': 'segment_sep', 'linker_tokens': ss_lk}]
      + align_duplex_tokens(ss_p2, _reverse_tokens(as_p2))
  )
  ```

- [ ] **Step 4: Django shell 验证 `_reverse_tokens` 函数正确性**

  ```python
  from app01.views import _reverse_tokens

  # 构造简单 token 列表：A s C o G
  tokens = [
      {'char': 'A', 'type': 'normal'},
      {'char': 's', 'type': 's'},
      {'char': 'C', 'type': 'normal'},
      {'char': 'o', 'type': 'o'},
      {'char': 'G', 'type': 'normal'},
  ]
  result = _reverse_tokens(tokens)
  chars = [t['char'] for t in result]
  # 反转后：G o C s A
  assert chars == ['G', 'o', 'C', 's', 'A'], f"got: {chars}"
  print("A2 _reverse_tokens pass")
  ```

  预期输出：`A2 _reverse_tokens pass`

- [ ] **Step 5: 浏览器验证 Part2 对齐**

  1. 启动开发服务器：`python manage.py runserver`
  2. 打开含双段序列（Part1-linker-Part2）的 duplex 行
  3. 观察对齐表格：SS 的 Part2 与 AS 的 Part2 应从相同方向（terminal 端）逐列对齐
  4. 预期：Part2 区域列对齐正确（与 Part1 区域对齐方式一致）

- [ ] **Step 6: Commit**

  ```bash
  git add app01/views.py
  git commit -m "fix: extract _reverse_tokens helper; reverse as_p2 before Part2 alignment"
  ```

---

## 执行顺序总结

| 顺序 | Task | 预计时间 |
|------|------|---------|
| 1 | Task 1 — A1 connector | ~5 min |
| 2 | Task 2 — A5 Remark | ~5 min |
| 3 | Task 3 — A4 linker_seq | ~5 min |
| 4 | Task 4 — A3 download | ~15 min |
| 5 | Task 5 — A2 Part2 对齐 | ~15 min |
