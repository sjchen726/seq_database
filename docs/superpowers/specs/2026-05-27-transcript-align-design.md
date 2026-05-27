# 转录本定位工具 — 设计规范

## 背景与问题

当前 `SeqInfo.Transcript` 和 `SeqInfo.Pos` 字段只能通过 CSV 上传或手动编辑填写，没有自动比对能力。用户已有两个成熟脚本：

- `get_nt_from_ncbi2.py`：调用 NCBI Entrez API 按登录号拉取转录本 FASTA
- `smithwaterman_v3.py`：用 Smith-Waterman 局部比对算法，将 siRNA SS 链比对到转录本，输出位置、得分、错配信息

目标：将这两个脚本的功能集成进 SeqDB 的 Web 界面，让用户在序列列表或搜索结果页勾选序列后，一键完成"拉取转录本 → 比对 → 预览结果 → 选择性回填 Pos"的完整流程。

## 不在本次范围内

- 全基因组层面的 off-target 批量扫描
- 转录本本地缓存数据库（NCBI 实时拉取即可）
- 异步/后台任务队列（同步执行，建议每次 ≤20 条）
- AS 链 off-target 预测

---

## 整体流程

```
seq_list / search_results 工具栏
  → 勾选 ≥1 条序列 → 点「转录本定位」按钮
      ↓ POST (selected duplex_ids + back_url)
  /transcript_align/  ── 准备页
      表格：duplex_id | SS裸序列预览 | Transcript输入 | 现有Position
      已有 Position → 橙色提示"将覆盖"
      ↓ 点「开始比对」POST
  服务端：fetch NCBI + 跑 SW → 写 session['ta_results']
      ↓ redirect
  /transcript_align/results/  ── 预览页
      表格：☑ duplex_id | NM号 | 位置 | 得分 | 错配数 | [展开]对齐图
      失败行标红，不可勾选
      ↓ 点「确认写入」POST
  写 SeqInfo.Transcript + SeqInfo.Pos → redirect 回原列表
```

---

## 算法设计

### 链选择逻辑

比对使用 SS 链裸序列（与 mRNA 同向，可直接匹配）：

1. 优先取 `Delivery.seq_type='SS'` 的 `Sequence.seq`
2. 若 duplex 只有 AS 链，取 AS 裸序列的反向互补序列

### Smith-Waterman 参数

沿用原脚本参数：

| 参数 | 值 |
|------|----|
| match_score | 1 |
| mismatch_penalty | 0 |
| open_gap_penalty | -10 |
| extend_gap_penalty | -0.5 |
| score_threshold | 15（默认，可在 settings.py 配置） |

得分 < 阈值：结果仍返回，但标橙色警告；用户仍可勾选写入。  
无任何比对结果（alignments 为空）：显示"未找到匹配"，不可写入。

### 错配解析

改写自 `parse_match`，输出列表：

```python
[
    {'pos': 5,  'query_base': 'A', 'ref_base': 'C'},  # AS链位置计数，1-based
    {'pos': 18, 'query_base': 'G', 'ref_base': 'T'},
]
```

位置计数方式：从 query 序列 3' 端（位置 1）往 5' 端（位置 len）计数，与原脚本一致。

### 对齐图格式

使用 `pairwise2.format_alignment(*best)` 原始输出，HTML 里用 `<pre>` 等宽字体渲染，初始折叠，点击展开。

---

## 新文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `app01/transcript_align.py` | 新建 | NCBI 拉取 + SW 比对 + 错配解析，纯函数，不依赖 Django request |
| `templates/transcript_align_prepare.html` | 新建 | 准备页：选序列、填 NM 号 |
| `templates/transcript_align_results.html` | 新建 | 预览页：结果表 + 对齐图 + 确认写入 |
| `app01/views.py` | 修改 | 追加 `transcript_align_prepare`、`transcript_align_results` 两个视图 |
| `bms/urls.py` | 修改 | 追加两条 URL |
| `bms/settings.py` | 修改 | 追加 `ENTREZ_EMAIL`、`SW_SCORE_THRESHOLD=15` |
| `templates/seq_list.html` | 修改 | 工具栏追加「转录本定位」按钮 + 表单 |
| `templates/search_results.html` | 修改 | 同上 |

---

## 详细模块设计

### `app01/transcript_align.py`

```python
class TranscriptFetchError(Exception): pass
class AlignmentNotFoundError(Exception): pass

def fetch_transcript_seq(accession: str) -> str:
    """调用 NCBI Entrez 拉取 FASTA，返回大写 DNA 序列（T，不含 U）。
    失败抛 TranscriptFetchError。"""

def get_ss_naked_dna(duplex_id: str, user) -> str | None:
    """返回 SS 链裸序列的 DNA 字符串（U→T）。
    无 SS 则取 AS 的反向互补。无任何链则返回 None。"""

def run_sw_alignment(naked_dna: str, transcript_seq: str, score_threshold: int) -> dict:
    """运行 SW 比对，返回结果 dict 或 None（未找到匹配）。
    返回格式：
    {
        'position': '1234-1254',
        'score': 21.0,
        'mismatch_count': 2,
        'mismatches': [{'pos': 5, 'query_base': 'A', 'ref_base': 'C'}, ...],
        'alignment_str': '...',   # pairwise2.format_alignment 原始输出
    }"""

def align_duplex(duplex_id: str, nm_accession: str, user, score_threshold: int) -> dict:
    """对外接口：给定 duplex_id + NM 号，返回完整比对结果 dict（含 error 字段）。"""
```

### 视图：`transcript_align_prepare`

**GET**（从 seq_list 点击按钮跳转，带 duplex_ids 参数）：
- 读取 selected duplex_ids（GET 参数或 session）
- 查询每条 duplex 的 SS 裸序列、现有 Transcript、现有 Pos
- 渲染准备表格

**POST**（用户填好 NM 号后提交）：
- 前端校验：所有行 Transcript 不为空
- 逐条调用 `align_duplex()`，收集结果列表
- 写入 `request.session['ta_results']` 和 `request.session['ta_back_url']`
- `redirect('transcript_align_results')`

### 视图：`transcript_align_results`

**GET**：从 session 读 `ta_results`，渲染预览表格

**POST**（确认写入）：
- 读取勾选的行（by duplex_id）
- 对每行执行：
  ```python
  seqinfo, _ = SeqInfo.objects.get_or_create(sequence_id=row['sequence_id'])
  seqinfo.Transcript = row['nm']
  seqinfo.Pos = row['position']   # 格式："start-end"，如 "1234-1254"
  seqinfo.save()
  ```
- 清除 session 中的 `ta_results`
- `messages.success(...)` + redirect 回 `ta_back_url`

---

## 触发入口（两处模板改动）

`seq_list.html` 和 `search_results.html` 工具栏各追加：

```html
<!-- 隐藏表单，收集选中的 duplex_ids -->
<form id="ta-form" method="POST" action="{% url 'transcript_align_prepare' %}">
  {% csrf_token %}
  <div id="ta-ids-container"></div>  <!-- JS 动态写入 hidden inputs -->
  <input type="hidden" name="back_url" value="{{ request.get_full_path }}">
</form>
<button type="button" id="ta-btn" class="ds-btn ds-btn-ghost">
  <i class="bi bi-search"></i> 转录本定位
</button>
```

JS 逻辑：点击按钮时，读取当前已勾选的 duplex_id，写入隐藏 input，提交表单。若无勾选则 alert 提示。

---

## 错误处理

| 情况 | 处理 |
|------|------|
| NCBI 网络超时 / 无效登录号 | 该行 error = "NCBI 获取失败：{accession}"，标红，不可写入 |
| SW 无匹配（score < 阈值且无 alignment） | error = "未找到匹配（得分不足）"，标红，不可写入 |
| SW 得分 < 阈值但有 alignment | 显示结果，橙色警告"得分偏低，请核实"，仍可勾选写入 |
| duplex 无 SS/AS 裸序列 | error = "无裸序列信息"，标红 |
| 一次提交超过 20 条 | 准备页提交时报错拦截，提示分批操作 |

---

## 边界情况

| 情况 | 处理 |
|------|------|
| 同一 duplex 已有 Position | 准备页橙色提示"已有值 xxx，比对后将覆盖"；用户仍可继续 |
| 多个比对结果（多处匹配） | 取 score 最高的一个；若并列则取 start 最小的 |
| NM 号输入多个（用空格/逗号分隔） | 本次不支持，只取第一个；后续可扩展 |
| seq_list 勾选的是 AS 行（无 SS duplex） | 自动取 AS 反向互补做比对，预览页备注"使用 AS 反向互补" |

---

## 依赖

```
biopython>=1.81
```

`requirements.txt` 追加；`venv` 需手动 `pip install biopython`。

---

## 涉及文件汇总

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `app01/transcript_align.py` | 新建 | 算法模块 |
| `templates/transcript_align_prepare.html` | 新建 | 准备页 |
| `templates/transcript_align_results.html` | 新建 | 预览+确认页 |
| `app01/views.py` | 追加 | 2 个视图函数 |
| `bms/urls.py` | 追加 | 2 条 URL |
| `bms/settings.py` | 追加 | ENTREZ_EMAIL、SW_SCORE_THRESHOLD |
| `templates/seq_list.html` | 修改 | 工具栏按钮 + 触发表单 |
| `templates/search_results.html` | 修改 | 同上 |
