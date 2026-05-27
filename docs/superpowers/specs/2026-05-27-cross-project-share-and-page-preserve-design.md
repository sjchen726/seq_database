# Design Spec: 跨项目共享修复 + 编辑后返页保留

**日期：** 2026-05-27  
**计划：** 计划一（Bug修复）  
**对应功能：** 功能4（跨项目样品可见）+ 功能2（编辑后保留当前页）

---

## 背景

### 功能4：跨项目样品共享（Bug）

用户将已属于项目350的序列上传至项目3T03时，系统未弹出跨项目共享确认页，直接显示"重复，已跳过"，序列无法写入3T03。

**根本原因：** `check_duplicates()` 使用 `linker_seq` 字段做数据库匹配。`linker_seq` 由 `add_o_to_all_rules_safe()` 对 `modify_seq` 处理生成，历史数据与新上传数据的规范化结果可能存在细微差异，导致查询返回空结果——序列既未被识别为跨项目重复（不触发共享确认页），也可能因其他约束无法写入，最终静默失败。

### 功能2：搜索后编辑返页（Bug）

用户在搜索结果页面进行编辑操作，保存后跳回第一页，丢失搜索上下文和页码位置。

**当前机制存在的问题：**
1. 编辑链接在模板渲染时不含 `dt_page`，依赖 JS 在 DataTables draw 事件后动态追加——若用户在 JS 追加完成前点击，`dt_page` 丢失
2. Seq Type 下拉（切换 SS/AS 显示方向）触发 GET 请求时未保留当前页码，DataTables 重置为第0页

---

## 设计

### 功能4 修复

#### 匹配键变更

将 `check_duplicates()` 中的数据库查询键从 `linker_seq` 改为 `naked_seq`：

**修改前：**
```python
ss_deliveries = Delivery.objects.filter(
    linker_seq=ss_linker_seq,
    delivery5=ss_d5,
    delivery3=ss_d3
)
```

**修改后：**
```python
ss_deliveries = Delivery.objects.filter(
    sequence__seq=ss_naked_seq,   # 裸序列，稳定且无格式差异
    delivery5=ss_d5,
    delivery3=ss_d3
).prefetch_related('project_links')
```

`naked_seq` 提取逻辑复用 `run_preflight_check` 中已有的规范化流程（normalize_tmp_seq_with_combo → _sm_norm_re.sub → strip parens → findall AUGCI），确保与 `save_deliveries` 存库时使用的裸序列格式一致。

#### 跨项目共享流程（保持现有设计，确认正常工作）

```
上传 CSV（Project=BPR-3T03）
  ↓
check_duplicates() 检测到相同 (naked_seq, delivery5, delivery3) 已在 BPR-350
  ↓ existing_projects=['BPR-350'], target_project='BPR-3T03' → 识别为跨项目
  ↓
跳转 confirm_share 确认页
  ↓ 用户选择「共享」
  ↓
DeliveryProject.objects.get_or_create(delivery_id=..., project_code='BPR-3T03')
  ↓
BPR-350 和 BPR-3T03 用户均可通过 get_permitted_delivery_qs() 查询该序列
```

#### 需要同步修改的地方

- `check_duplicates()` 函数签名不变，内部查询键更换
- `confirm_share.html` 和 `confirm_share_deliveries` view 无需改动
- `run_preflight_check()` 中已有 naked_seq 计算逻辑，可抽取为共用函数供 `check_duplicates` 调用

#### 错误处理

- 若 `naked_seq` 为空（序列全为未知 token），跳过该对，记录 warning
- 跨项目确认页「跳过」选项保留现有行为（不创建 DeliveryProject）

---

### 功能2 修复

#### 问题1：编辑链接 dt_page 依赖 JS 追加

**修改文件：** `templates/_seq_group_row.html`、`templates/search_results.html`

**修改方案：** 在模板渲染时直接将 `dt_page` 写入编辑链接的 `next` URL，使其在 JS 未执行时也能正确携带页码。

JS 仍保留动态更新逻辑作为兜底（处理页面内翻页后用户点击编辑的场景）。

**模板层修改思路（_seq_group_row.html）：**

编辑链接中的 `next` 参数由 `request.get_full_path|urlencode` 生成，已包含当前 URL 的所有查询参数（含 `dt_page`，若 URL 中有的话）。JS 负责在 DataTables 翻页后更新编辑链接中的 `dt_page`——只要 JS 的 draw 事件在用户点击前完成，dt_page 就会正确。

实际断链场景：初次渲染时 URL 中可能没有 `dt_page`（第一次加载），此时 JS 在 draw 后才写入，窗口很短。

**补强方案：** 在 `seq_edit.html` 的取消/返回按钮也使用 `next` URL，确保不走 JS 路径时也能回到正确页面。同时，JS 在页面初始化时立即更新所有编辑链接（不等 draw 事件）。

#### 问题2：Seq Type 切换重置页码

**修改文件：** `templates/seq_list.html`（Seq Type 切换的 JS 逻辑）

**修改方案：** Seq Type 切换触发新 GET 请求时，读取当前 DataTables 页码并附加到 URL：

```javascript
seqTypeSelector.addEventListener('change', function() {
    const currentPage = window.table ? window.table.page() : 0;
    const url = new URL(window.location.href);
    url.searchParams.set('seq_type', this.value);
    url.searchParams.set('dt_page', currentPage);
    window.location.href = url.toString();
});
```

#### 数据流（修复后）

```
用户在第3页搜索结果中点击「编辑」
  ↓ 编辑链接：/edit_seq/?id=123&next=/seq_list/?q=BP0104&dt_page=2
  ↓
编辑页面：next=/seq_list/?q=BP0104, dt_page hidden input = 2
  ↓ 用户保存
  ↓
edit_seq view: redirect → /seq_list/?q=BP0104&dt_page=2
  ↓
seq_list 页面加载，JS initDrawWithDtPage 读取 dt_page=2
  ↓ table.page(2).draw(false)
  ↓
用户回到第3页（0-indexed page 2）的搜索结果 ✓
```

---

## 涉及文件

| 文件 | 修改内容 |
|------|---------|
| `app01/views.py` | `check_duplicates()` 匹配键从 linker_seq 改为 naked_seq；提取 naked_seq 计算为辅助函数 |
| `templates/_seq_group_row.html` | 编辑链接确保含 dt_page（或由 JS 即时更新）|
| `templates/search_results.html` | 同上 |
| `templates/seq_list.html` | Seq Type 切换保留 dt_page |
| `static/js/tables.js` | 初始化时立即更新所有编辑链接中的 dt_page（不等 draw 事件）|

---

## 不在此计划内

- 功能1（多搜索叠放）→ 计划二
- 功能3（转录本比对）→ 计划二
- 共享确认页 UI 优化
- 用户权限级别对共享操作的限制（保持现有逻辑）
