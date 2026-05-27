# 转录本定位工具 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在序列列表和搜索结果页，勾选序列后可一键拉取 NCBI 转录本 + Smith-Waterman 比对，预览位置/得分/对齐图后选择性回填 SeqInfo.Transcript 和 SeqInfo.Pos。

**Architecture:** 三步页面流（seq_list 勾选 → 准备页填 NM 号 → 运行比对存 session → 结果预览页确认写入），遵循项目现有 preflight-confirm 风格。算法封装在独立模块 `app01/transcript_align.py`，不依赖 Django request。

**Tech Stack:** Django 5.1, Python 3.10, MySQL, Biopython (pairwise2 + Entrez), Jinja2 模板

---

## 文件改动地图

| 文件 | 类型 | 说明 |
|------|------|------|
| `app01/transcript_align.py` | 新建 | NCBI 拉取 + SW 比对 + 错配解析，纯函数 |
| `templates/transcript_align_prepare.html` | 新建 | 准备页：显示待比对序列，允许输入/修改 NM 号 |
| `templates/transcript_align_results.html` | 新建 | 预览页：比对结果表 + 对齐图 + 确认写入 |
| `app01/views.py` | 追加 | `transcript_align_prepare`、`transcript_align_results` 两个视图 |
| `bms/urls.py` | 追加 | 两条 URL 路由 |
| `bms/settings.py` | 追加 | `ENTREZ_EMAIL`、`SW_SCORE_THRESHOLD` 配置项 |
| `templates/seq_list.html` | 修改 | 工具栏追加「转录本定位」按钮 |
| `templates/search_results.html` | 修改 | 同上 |
| `static/js/transcript-align-toolbar.js` | 新建 | 按钮点击时收集选中 rm_code 并提交 |
| `templates/base.html` | 修改 | 全局加载 transcript-align-toolbar.js |

---

## Task 1：安装 Biopython + Settings 配置

**Files:**
- Modify: `bms/settings.py`

### 背景
项目 venv 里没有 biopython，需先安装。`ENTREZ_EMAIL` 是 NCBI 要求的必填邮箱（匿名调用也需要）。`SW_SCORE_THRESHOLD=15` 是 Smith-Waterman 最低得分阈值，低于此值的比对显示橙色警告。

- [ ] **Step 1：安装 biopython**

```bash
source venv/bin/activate
pip install biopython
```

期望输出包含：`Successfully installed biopython-x.xx`

- [ ] **Step 2：验证安装**

```bash
source venv/bin/activate
python -c "from Bio import pairwise2, Entrez, SeqIO; print('biopython OK')"
```

期望输出：`biopython OK`

- [ ] **Step 3：在 settings.py 末尾追加配置**

找到 `bms/settings.py` 末尾（`MEDIA_ROOT` 那行后面），追加：

```python

# ── 转录本定位工具 ──────────────────────────────────────────────────
ENTREZ_EMAIL = 'admin@seqdb.local'   # NCBI Entrez 必填邮箱
SW_SCORE_THRESHOLD = 15              # Smith-Waterman 最低得分阈值
```

- [ ] **Step 4：验证 Django 系统检查**

```bash
source venv/bin/activate
python manage.py check
```

期望输出：`System check identified no issues (0 silenced).`

- [ ] **Step 5：Commit**

```bash
git add bms/settings.py
git commit -m "feat: add ENTREZ_EMAIL and SW_SCORE_THRESHOLD to settings"
```

---

## Task 2：算法模块 `app01/transcript_align.py`

**Files:**
- Create: `app01/transcript_align.py`

### 背景
该模块封装三件事：（1）从 NCBI 拉取转录本 FASTA；（2）从 duplex_id 取 SS 链裸序列（无 SS 则取 AS 的反向互补）；（3）运行 Smith-Waterman 并解析错配。对外只暴露 `align_duplex()`。

参数说明（遵循原脚本 `smithwaterman_v3.py`）：
- match=1, mismatch=0, gap_open=-10, gap_extend=-0.5
- `parse_mismatches` 中位置计数：从 query 5' 端（pos=query_len）向 3' 端（pos=1）递减；reversed 后输出为 3'→5' 顺序

- [ ] **Step 1：创建 `app01/transcript_align.py`，写入完整内容**

```python
"""
转录本定位工具 — 算法模块

对外接口：align_duplex(duplex_id, nm_accession, user, score_threshold) -> dict
内部：fetch_transcript_seq, get_ss_naked_dna, parse_mismatches, run_sw_alignment
"""
from __future__ import annotations


class TranscriptFetchError(Exception):
    """NCBI 拉取失败时抛出。"""


_COMP = {'A': 'T', 'T': 'A', 'C': 'G', 'G': 'C'}


def fetch_transcript_seq(accession: str) -> str:
    """调用 NCBI Entrez efetch 拉取 FASTA，返回大写 DNA 字符串（T，不含 U）。
    失败时抛 TranscriptFetchError。"""
    from Bio import Entrez, SeqIO
    from django.conf import settings

    Entrez.email = getattr(settings, 'ENTREZ_EMAIL', 'admin@seqdb.local')
    try:
        handle = Entrez.efetch(
            db='nucleotide', id=accession.strip(),
            rettype='fasta', retmode='text'
        )
        record = SeqIO.read(handle, 'fasta')
        handle.close()
        return str(record.seq).upper()
    except Exception as exc:
        raise TranscriptFetchError(f'NCBI 获取失败（{accession}）: {exc}') from exc


def get_ss_naked_dna(duplex_id: str, user) -> tuple[str | None, str | None]:
    """返回 (naked_dna, sequence_rm_code)。
    优先取 SS 链裸序列（RNA→DNA, U→T）；
    无 SS 则取 AS 链裸序列的反向互补。
    两者都没有时返回 (None, None)。"""
    from app01.views import get_permitted_delivery_qs

    qs = get_permitted_delivery_qs(user).select_related('sequence')

    # 优先 SS
    ss_d = qs.filter(duplex_id=duplex_id, seq_type='SS').first()
    if ss_d and ss_d.sequence and ss_d.sequence.seq:
        dna = ss_d.sequence.seq.upper().replace('U', 'T')
        return dna, ss_d.sequence.rm_code

    # 降级到 AS 反向互补
    as_d = qs.filter(duplex_id=duplex_id, seq_type='AS').first()
    if as_d and as_d.sequence and as_d.sequence.seq:
        dna = as_d.sequence.seq.upper().replace('U', 'T')
        rc = ''.join(_COMP.get(b, 'N') for b in reversed(dna))
        return rc, as_d.sequence.rm_code

    return None, None


def parse_mismatches(seqA: str, seqB: str, query_len: int) -> list[dict]:
    """解析 SW 比对结果中的错配信息。
    seqA：query 对齐串（含 '-' gap）
    seqB：subject 对齐串（含 '-' gap）
    query_len：query 实际长度（不含 gap）
    返回列表，每项 {'pos': int, 'query_base': str, 'ref_base': str}，
    pos 从 query 5' 端（= query_len）向 3' 端（= 1）计数，输出按 3'→5' 排列。
    """
    result = []
    pos = query_len  # 5' 端位置
    for q, s in zip(seqA, seqB):
        if q == '-':
            continue  # query gap，位置不递减
        if q != s:
            result.append({
                'pos': pos,
                'query_base': _COMP.get(q, q),  # 显示 AS 链碱基（互补）
                'ref_base': s,
            })
        pos -= 1
    return list(reversed(result))  # 转为 3'→5' 顺序（pos 升序）


def run_sw_alignment(naked_dna: str, transcript_seq: str, score_threshold: int) -> dict | None:
    """运行 Smith-Waterman 局部比对。
    naked_dna：query，已是 DNA（T），大写
    transcript_seq：subject，已是 DNA（T），大写
    返回 None 表示无匹配（score < threshold 或无 alignment）。
    返回 dict：
        position      : '1234-1254'（1-based，含首尾）
        score         : float
        mismatch_count: int
        mismatches    : list[dict]
        alignment_str : pairwise2.format_alignment 原始字符串
    """
    from Bio import pairwise2

    alignments = pairwise2.align.localms(
        naked_dna, transcript_seq,
        1, 0, -10, -0.5          # match, mismatch, gap_open, gap_extend
    )
    if not alignments:
        return None

    best = max(alignments, key=lambda a: a.score)
    if best.score < score_threshold:
        return None

    mismatches = parse_mismatches(best.seqA, best.seqB, len(naked_dna))
    return {
        'position': f'{best.start + 1}-{best.end}',
        'score': best.score,
        'mismatch_count': len(mismatches),
        'mismatches': mismatches,
        'alignment_str': pairwise2.format_alignment(*best),
    }


def align_duplex(
    duplex_id: str,
    nm_accession: str,
    user,
    score_threshold: int | None = None,
) -> dict:
    """对外接口：给定 duplex_id + NM 登录号，返回完整比对结果 dict。
    字段：duplex_id, nm, sequence_rm_code, position, score,
          mismatch_count, mismatches, alignment_str, used_rc, error
    error 非 None 时表示失败，position 等字段为 None。
    """
    from django.conf import settings

    if score_threshold is None:
        score_threshold = getattr(settings, 'SW_SCORE_THRESHOLD', 15)

    result: dict = {
        'duplex_id': duplex_id,
        'nm': nm_accession.strip(),
        'sequence_rm_code': None,
        'position': None,
        'score': None,
        'mismatch_count': None,
        'mismatches': [],
        'alignment_str': '',
        'used_rc': False,
        'error': None,
    }

    try:
        naked_dna, seq_rm_code = get_ss_naked_dna(duplex_id, user)
        if not naked_dna:
            result['error'] = '无裸序列信息'
            return result
        result['sequence_rm_code'] = seq_rm_code

        transcript_seq = fetch_transcript_seq(nm_accession)
        sw = run_sw_alignment(naked_dna, transcript_seq, score_threshold)

        if sw is None:
            result['error'] = f'未找到匹配（得分 < {score_threshold}）'
            return result

        result.update(sw)

    except TranscriptFetchError as exc:
        result['error'] = str(exc)
    except Exception as exc:
        result['error'] = f'比对出错：{exc}'

    return result
```

- [ ] **Step 2：用 Django shell 验证模块可导入**

```bash
source venv/bin/activate
python manage.py shell -c "
from app01.transcript_align import (
    TranscriptFetchError, fetch_transcript_seq,
    get_ss_naked_dna, parse_mismatches,
    run_sw_alignment, align_duplex,
)
print('import OK')
"
```

期望输出：`import OK`

- [ ] **Step 3：验证 `parse_mismatches` 逻辑**

```bash
source venv/bin/activate
python manage.py shell -c "
from app01.transcript_align import parse_mismatches
# seqA=query, seqB=subject, query_len=5
# 第 2 位不同（A≠C），第 4 位不同（G≠T）
result = parse_mismatches('AAGGT', 'ACGTT', 5)
print(result)
# 期望：[{'pos': 2, 'query_base': 'T', 'ref_base': 'C'},
#        {'pos': 4, 'query_base': 'T', 'ref_base': 'T'}]
# 注意：query_base 是互补碱基，pos 为 3'→5' 升序（即 pos 小=3'端）
assert len(result) == 2
assert result[0]['pos'] < result[1]['pos']
print('parse_mismatches OK')
"
```

期望输出：`parse_mismatches OK`

- [ ] **Step 4：验证 `run_sw_alignment` 精确匹配**

```bash
source venv/bin/activate
python manage.py shell -c "
from app01.transcript_align import run_sw_alignment
query = 'ATGCATGCATGCATGCATGC'   # 20 bp
# transcript 里插在 pos 10 开始
transcript = 'CCCCCCCCCC' + query + 'GGGGGGGGGG'
res = run_sw_alignment(query, transcript, score_threshold=15)
print(res)
assert res is not None
assert res['position'] == '11-30'
assert res['mismatch_count'] == 0
assert res['score'] == 20.0
print('run_sw_alignment OK')
"
```

期望输出：`run_sw_alignment OK`

- [ ] **Step 5：Commit**

```bash
git add app01/transcript_align.py
git commit -m "feat: add transcript_align module (NCBI fetch + Smith-Waterman)"
```

---

## Task 3：URL + 视图骨架

**Files:**
- Modify: `bms/urls.py`
- Modify: `app01/views.py`（末尾追加）

### 背景
先建好路由和视图骨架，确认 URL 注册正确，再在后续 Task 里填充完整逻辑。

- [ ] **Step 1：在 `bms/urls.py` 的 multi_blast 行后追加两条路由**

找到：
```python
    path('multi_blast/', views.multi_blast, name='multi_blast'),
```

替换为：
```python
    path('multi_blast/', views.multi_blast, name='multi_blast'),
    path('transcript_align/', views.transcript_align_prepare, name='transcript_align_prepare'),
    path('transcript_align/results/', views.transcript_align_results, name='transcript_align_results'),
```

- [ ] **Step 2：在 `app01/views.py` 末尾（`multi_blast` 函数之后、Experiment views 注释之前）追加骨架视图**

找到：
```python
# ─────────────────────────────────────────────────────────────────────────────
# Experiment data views
```

在其前面插入：

```python
# ─────────────────────────────────────────────────────────────────────────────
# Transcript alignment views
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def transcript_align_prepare(request):
    """准备页：接收来自 seq_list 的 rm_code 列表（step='init'），
    或接收填好 NM 号的表单（step='run'）触发比对。"""
    return HttpResponse('transcript_align_prepare placeholder')


@login_required
def transcript_align_results(request):
    """结果预览页：GET 从 session 读结果；POST 写 DB。"""
    return HttpResponse('transcript_align_results placeholder')

```

- [ ] **Step 3：验证路由注册正确**

```bash
source venv/bin/activate
python manage.py check
python manage.py shell -c "
from django.urls import reverse
print(reverse('transcript_align_prepare'))
print(reverse('transcript_align_results'))
"
```

期望输出：
```
/transcript_align/
/transcript_align/results/
```

- [ ] **Step 4：Commit**

```bash
git add bms/urls.py app01/views.py
git commit -m "feat: register transcript_align URL routes and view stubs"
```

---

## Task 4：准备页视图 + 模板

**Files:**
- Modify: `app01/views.py`（替换 `transcript_align_prepare` 骨架）
- Create: `templates/transcript_align_prepare.html`

### 背景
准备页视图有两个 POST 分支，通过隐藏字段 `step` 区分：
- `step='init'`：来自 seq_list/search_results，接收 rm_code 列表，渲染填写表格
- `step='run'`：来自准备页表单，接收 duplex_id+NM 列表，运行比对，redirect 到结果页

`_resolve_duplex_id` 和 `get_permitted_delivery_qs` 已在 `app01/views.py` 中定义，可直接调用。

- [ ] **Step 1：替换 `transcript_align_prepare` 视图为完整实现**

找到：
```python
@login_required
def transcript_align_prepare(request):
    """准备页：接收来自 seq_list 的 rm_code 列表（step='init'），
    或接收填好 NM 号的表单（step='run'）触发比对。"""
    return HttpResponse('transcript_align_prepare placeholder')
```

替换为：

```python
@login_required
def transcript_align_prepare(request):
    """准备页：接收来自 seq_list 的 rm_code 列表（step='init'），
    或接收填好 NM 号的表单（step='run'）触发比对。"""
    if request.method != 'POST':
        return redirect('seq_list')

    step = request.POST.get('step', 'init')
    back_url = request.POST.get('back_url') or reverse('seq_list')

    # ── step='init'：收集选中序列，渲染填写表格 ──────────────────────
    if step == 'init':
        rm_codes = request.POST.getlist('rm_code')
        if not rm_codes:
            messages.warning(request, '请先勾选至少一条序列')
            return redirect(back_url)

        rows = []
        seen_duplex = set()
        for rm_code in rm_codes:
            duplex_id = _resolve_duplex_id(rm_code, request.user)
            if not duplex_id or duplex_id in seen_duplex:
                continue
            seen_duplex.add(duplex_id)

            # SS 裸序列预览
            from app01.transcript_align import get_ss_naked_dna
            naked_dna, seq_rm_code = get_ss_naked_dna(duplex_id, request.user)
            if naked_dna:
                preview = naked_dna[:15] + ('…' if len(naked_dna) > 15 else '')
            else:
                preview = '—'

            # 现有 SeqInfo
            existing_transcript = ''
            existing_pos = ''
            if seq_rm_code:
                si = SeqInfo.objects.filter(sequence_id=seq_rm_code).first()
                if si:
                    existing_transcript = si.Transcript or ''
                    existing_pos = si.Pos or ''

            rows.append({
                'duplex_id': duplex_id,
                'naked_preview': preview,
                'existing_transcript': existing_transcript,
                'existing_pos': existing_pos,
            })

        if not rows:
            messages.warning(request, '未找到有效序列，请检查选中项')
            return redirect(back_url)

        return render(request, 'transcript_align_prepare.html', {
            'rows': rows,
            'back_url': back_url,
        })

    # ── step='run'：运行比对，结果写 session，redirect 到结果页 ──────
    if step == 'run':
        duplex_ids = request.POST.getlist('duplex_id')
        nm_values = request.POST.getlist('nm')

        if len(duplex_ids) > 20:
            messages.error(request, '每次最多处理 20 条序列，请分批操作')
            return redirect(back_url)

        from app01.transcript_align import align_duplex
        from django.conf import settings
        threshold = getattr(settings, 'SW_SCORE_THRESHOLD', 15)

        ta_results = []
        for duplex_id, nm in zip(duplex_ids, nm_values):
            nm = nm.strip()
            if not nm:
                ta_results.append({
                    'duplex_id': duplex_id,
                    'nm': nm,
                    'sequence_rm_code': None,
                    'position': None,
                    'score': None,
                    'mismatch_count': None,
                    'mismatches': [],
                    'alignment_str': '',
                    'used_rc': False,
                    'error': 'Transcript 登录号不能为空',
                })
                continue
            ta_results.append(align_duplex(duplex_id, nm, request.user, threshold))

        request.session['ta_results'] = ta_results
        request.session['ta_back_url'] = back_url
        return redirect('transcript_align_results')

    return redirect(back_url)
```

- [ ] **Step 2：创建 `templates/transcript_align_prepare.html`**

```html
{% extends 'base.html' %}
{% block page_title %} — 转录本定位{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">转录本定位 — 准备</span>
  <span class="ds-topbar-spacer"></span>
  <a href="{{ back_url }}" class="ds-btn ds-btn-ghost">&#8592; 返回</a>
{% endblock %}

{% block content %}
<div class="ds-table-card" style="max-width:900px;margin:24px auto;padding:24px;">
  <h2 style="font-size:15px;font-weight:700;margin-bottom:6px;">确认比对序列与转录本</h2>
  <p style="font-size:13px;color:#666;margin-bottom:16px;">
    请为每条序列填写目标转录本的 NCBI 登录号（如 <code>NM_001234</code>）。
    已有值已预填，可直接修改。⚠️ 标注的条目写入后将覆盖现有 Position。
  </p>

  <form method="POST" action="{% url 'transcript_align_prepare' %}">
    {% csrf_token %}
    <input type="hidden" name="step" value="run">
    <input type="hidden" name="back_url" value="{{ back_url }}">

    <table class="ds-table" style="width:100%;margin-bottom:16px;">
      <thead>
        <tr>
          <th style="width:130px;">Duplex ID</th>
          <th style="width:160px;">SS 裸序列预览</th>
          <th>Transcript（NM 登录号）</th>
          <th style="width:140px;">现有 Position</th>
        </tr>
      </thead>
      <tbody>
        {% for row in rows %}
        <tr>
          <td style="font-family:monospace;font-size:12px;">
            {{ row.duplex_id }}
            <input type="hidden" name="duplex_id" value="{{ row.duplex_id }}">
          </td>
          <td style="font-family:monospace;font-size:12px;color:#555;">{{ row.naked_preview }}</td>
          <td>
            <input type="text" name="nm"
                   value="{{ row.existing_transcript }}"
                   placeholder="如 NM_001234"
                   required
                   class="ds-form-control"
                   style="width:100%;max-width:280px;">
          </td>
          <td style="font-size:12px;">
            {% if row.existing_pos %}
              <span style="color:#f59e0b;font-weight:600;">{{ row.existing_pos }} ⚠️ 将覆盖</span>
            {% else %}
              <span style="color:#94a3b8;">—</span>
            {% endif %}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>

    <div style="display:flex;gap:8px;align-items:center;">
      <a href="{{ back_url }}" class="ds-btn ds-btn-ghost" style="height:30px;font-size:12px;">取消</a>
      <button type="submit" class="ds-btn ds-btn-primary" style="height:30px;font-size:12px;">
        🧬 开始比对 →
      </button>
    </div>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 3：用 Django shell 验证 step='init' 路径**

先确保 DB 里有至少一条 duplex 序列（查任意 duplex_id）：

```bash
source venv/bin/activate
python manage.py shell -c "
from app01.models import Delivery
d = Delivery.objects.filter(duplex_id__isnull=False).first()
print('sample duplex_id:', d.duplex_id if d else 'NONE')
print('sample rm_code:', d.id if d else 'NONE')
"
```

记录输出的 `rm_code`（即 Delivery.id）。

- [ ] **Step 4：验证 step='run' 路径（session 正确写入）**

```bash
source venv/bin/activate
python manage.py check
```

期望输出：`System check identified no issues (0 silenced).`

- [ ] **Step 5：Commit**

```bash
git add app01/views.py templates/transcript_align_prepare.html
git commit -m "feat: implement transcript_align_prepare view and template"
```

---

## Task 5：结果页视图 + 模板

**Files:**
- Modify: `app01/views.py`（替换 `transcript_align_results` 骨架）
- Create: `templates/transcript_align_results.html`

### 背景
结果页 GET 从 session 读取 `ta_results`，渲染预览表格（含对齐图折叠）。POST 将选中行的 Transcript + Pos 写入 SeqInfo，redirect 回原列表。

`SeqInfo.sequence` 是 FK 到 `Sequence`，PK 为 `rm_code`（CharField）。因此写入用 `SeqInfo.objects.get_or_create(sequence_id=row['sequence_rm_code'])`。

- [ ] **Step 1：替换 `transcript_align_results` 视图为完整实现**

找到：
```python
@login_required
def transcript_align_results(request):
    """结果预览页：GET 从 session 读结果；POST 写 DB。"""
    return HttpResponse('transcript_align_results placeholder')
```

替换为：

```python
@login_required
def transcript_align_results(request):
    """结果预览页：GET 从 session 读结果；POST 写 DB。"""
    if request.method == 'GET':
        ta_results = request.session.get('ta_results')
        if not ta_results:
            messages.warning(request, '无比对结果，请重新操作')
            return redirect('seq_list')
        return render(request, 'transcript_align_results.html', {
            'ta_results': ta_results,
            'back_url': request.session.get('ta_back_url', '/seq_list/'),
            'score_threshold': getattr(__import__('django.conf', fromlist=['settings']).settings,
                                       'SW_SCORE_THRESHOLD', 15),
        })

    if request.method == 'POST':
        ta_results = request.session.pop('ta_results', [])
        back_url = request.session.pop('ta_back_url', '/seq_list/')
        selected = set(request.POST.getlist('selected'))

        saved_count = 0
        for row in ta_results:
            if row['duplex_id'] not in selected:
                continue
            if row.get('error') or not row.get('position') or not row.get('sequence_rm_code'):
                continue
            seqinfo, _ = SeqInfo.objects.get_or_create(
                sequence_id=row['sequence_rm_code']
            )
            seqinfo.Transcript = row['nm']
            seqinfo.Pos = row['position']
            seqinfo.save()
            saved_count += 1

        messages.success(request, f'已更新 {saved_count} 条序列的转录本位置信息')
        return redirect(back_url)

    return redirect('seq_list')
```

- [ ] **Step 2：创建 `templates/transcript_align_results.html`**

```html
{% extends 'base.html' %}
{% block page_title %} — 转录本定位结果{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">转录本定位 — 比对结果</span>
  <span class="ds-topbar-spacer"></span>
{% endblock %}

{% block content %}
<div class="ds-table-card" style="max-width:1100px;margin:24px auto;padding:24px;">
  <h2 style="font-size:15px;font-weight:700;margin-bottom:6px;">比对结果预览</h2>
  <p style="font-size:13px;color:#666;margin-bottom:4px;">
    勾选要写入的行，点「确认写入」后将更新 Transcript 和 Position 字段。
  </p>
  <p style="font-size:12px;color:#f59e0b;margin-bottom:16px;">
    ⚠️ 得分低于 {{ score_threshold }} 的结果以橙色标注，请核实后再写入。
  </p>

  <form method="POST" action="{% url 'transcript_align_results' %}">
    {% csrf_token %}

    <table class="ds-table" style="width:100%;margin-bottom:16px;table-layout:fixed;">
      <colgroup>
        <col style="width:36px;">
        <col style="width:130px;">
        <col style="width:130px;">
        <col style="width:120px;">
        <col style="width:70px;">
        <col style="width:70px;">
        <col>
      </colgroup>
      <thead>
        <tr>
          <th><input type="checkbox" id="ta-select-all" title="全选/取消"></th>
          <th>Duplex ID</th>
          <th>Transcript</th>
          <th>位置</th>
          <th>得分</th>
          <th>错配数</th>
          <th>对齐图</th>
        </tr>
      </thead>
      <tbody>
        {% for row in ta_results %}
        {% if row.error %}
        <tr style="background:#fff1f2;">
          <td></td>
          <td style="font-family:monospace;font-size:12px;">{{ row.duplex_id }}</td>
          <td style="font-size:12px;">{{ row.nm }}</td>
          <td colspan="4" style="color:#dc2626;font-size:12px;">❌ {{ row.error }}</td>
        </tr>
        {% elif row.score is not None and row.score < score_threshold %}
        <tr style="background:#fffbeb;">
          <td><input type="checkbox" name="selected" value="{{ row.duplex_id }}" checked></td>
          <td style="font-family:monospace;font-size:12px;">{{ row.duplex_id }}</td>
          <td style="font-size:12px;">{{ row.nm }}</td>
          <td style="font-size:12px;color:#f59e0b;font-weight:600;">{{ row.position }} ⚠️</td>
          <td style="font-size:12px;color:#f59e0b;">{{ row.score }}</td>
          <td style="font-size:12px;">{{ row.mismatch_count }}</td>
          <td>
            {% if row.alignment_str %}
            <button type="button" class="ta-toggle ds-btn ds-btn-ghost" style="font-size:11px;height:24px;padding:0 6px;">展开</button>
            <pre class="ta-pre" style="display:none;font-size:11px;background:#f8fafc;padding:8px;border-radius:4px;overflow-x:auto;margin-top:4px;">{{ row.alignment_str }}</pre>
            {% else %}—{% endif %}
          </td>
        </tr>
        {% else %}
        <tr>
          <td><input type="checkbox" name="selected" value="{{ row.duplex_id }}" checked></td>
          <td style="font-family:monospace;font-size:12px;">{{ row.duplex_id }}</td>
          <td style="font-size:12px;">{{ row.nm }}</td>
          <td style="font-size:12px;font-weight:600;">{{ row.position }}</td>
          <td style="font-size:12px;">{{ row.score }}</td>
          <td style="font-size:12px;">{{ row.mismatch_count }}</td>
          <td>
            {% if row.alignment_str %}
            <button type="button" class="ta-toggle ds-btn ds-btn-ghost" style="font-size:11px;height:24px;padding:0 6px;">展开</button>
            <pre class="ta-pre" style="display:none;font-size:11px;background:#f8fafc;padding:8px;border-radius:4px;overflow-x:auto;margin-top:4px;">{{ row.alignment_str }}</pre>
            {% else %}—{% endif %}
          </td>
        </tr>
        {% endif %}
        {% endfor %}
      </tbody>
    </table>

    <div style="display:flex;gap:8px;align-items:center;">
      <a href="{{ back_url }}" class="ds-btn ds-btn-ghost" style="height:30px;font-size:12px;">放弃，返回列表</a>
      <button type="submit" class="ds-btn ds-btn-primary" style="height:30px;font-size:12px;">✅ 确认写入选中</button>
    </div>
  </form>
</div>
{% endblock %}

{% block extra_scripts %}
<script>
// 对齐图折叠展开
document.querySelectorAll('.ta-toggle').forEach(function(btn) {
    btn.addEventListener('click', function() {
        var pre = this.nextElementSibling;
        var hidden = pre.style.display === 'none';
        pre.style.display = hidden ? 'block' : 'none';
        this.textContent = hidden ? '收起' : '展开';
    });
});

// 全选 / 取消全选
var selectAll = document.getElementById('ta-select-all');
if (selectAll) {
    selectAll.addEventListener('change', function() {
        document.querySelectorAll('input[name="selected"]').forEach(function(cb) {
            cb.checked = selectAll.checked;
        });
    });
}
</script>
{% endblock %}
```

- [ ] **Step 3：验证 Django 系统检查**

```bash
source venv/bin/activate
python manage.py check
```

期望输出：`System check identified no issues (0 silenced).`

- [ ] **Step 4：Commit**

```bash
git add app01/views.py templates/transcript_align_results.html
git commit -m "feat: implement transcript_align_results view and template"
```

---

## Task 6：工具栏按钮 + JS

**Files:**
- Modify: `templates/seq_list.html`
- Modify: `templates/search_results.html`
- Create: `static/js/transcript-align-toolbar.js`
- Modify: `templates/base.html`

### 背景
按钮跟随现有 `multiBlastBtn` 风格（`ds-tb-btn` 样式，无勾选时 disabled）。JS 与 `multi-blast-toolbar.js` 逻辑相同：读取 `input.row-checkbox:checked` 行的 `data-rm-code`，动态创建 POST 表单提交到 `/transcript_align/`（step=init）。加载到 `base.html`，覆盖 seq_list 和 search_results 两个页面。

- [ ] **Step 1：在 `seq_list.html` 工具栏追加按钮**

找到（`templates/seq_list.html` 第 133 行附近）：
```html
  <button id="multiBlastBtn" type="button" class="ds-tb-btn ds-tb-green"
          data-url="{% url 'multi_blast' %}" disabled>⌗ 多序列比对</button>
```

替换为：
```html
  <button id="multiBlastBtn" type="button" class="ds-tb-btn ds-tb-green"
          data-url="{% url 'multi_blast' %}" disabled>⌗ 多序列比对</button>
  <button id="transcriptAlignBtn" type="button" class="ds-tb-btn ds-tb-teal"
          data-url="{% url 'transcript_align_prepare' %}" disabled>🧬 转录本定位</button>
```

- [ ] **Step 2：在 `search_results.html` 工具栏追加按钮**

找到（`templates/search_results.html` 第 21 行附近）：
```html
  <button id="download-selected" class="ds-btn ds-btn-ghost" style="font-size:12.5px;">
```

在其前面插入：
```html
  <button id="transcriptAlignBtn" type="button" class="ds-btn ds-btn-ghost"
          data-url="{% url 'transcript_align_prepare' %}" style="font-size:12.5px;" disabled>
    🧬 转录本定位
  </button>
```

- [ ] **Step 3：创建 `static/js/transcript-align-toolbar.js`**

```javascript
/**
 * transcript-align-toolbar.js
 * 为「转录本定位」按钮提供交互：
 * - 有勾选时启用按钮，无勾选时禁用
 * - 点击时收集选中行的 data-rm-code，以 POST 表单提交到 /transcript_align/
 */
(function () {
    var btn = document.getElementById('transcriptAlignBtn');
    if (!btn) return;

    function getCheckedRmCodes() {
        return Array.prototype.map.call(
            document.querySelectorAll('input.row-checkbox:checked'),
            function (cb) { return cb.closest('tr').dataset.rmCode; }
        ).filter(Boolean);
    }

    function updateBtn() {
        btn.disabled = getCheckedRmCodes().length === 0;
    }

    document.addEventListener('change', function (e) {
        if (e.target.matches('input.row-checkbox') || e.target.id === 'select-all') {
            updateBtn();
        }
    });

    btn.addEventListener('click', function () {
        var rmCodes = getCheckedRmCodes();
        if (!rmCodes.length) {
            alert('请先勾选至少一条序列');
            return;
        }

        // 去重
        var seen = {};
        var unique = rmCodes.filter(function (c) {
            if (seen[c]) return false;
            seen[c] = true;
            return true;
        });

        if (unique.length > 20) {
            alert('每次最多选择 20 条序列，请减少勾选数量');
            return;
        }

        // 动态表单 POST
        var form = document.createElement('form');
        form.method = 'POST';
        form.action = btn.dataset.url;
        form.style.display = 'none';

        var csrfMatch = document.cookie.match(/csrftoken=([^;]+)/);
        if (!csrfMatch) { alert('CSRF 错误，请刷新页面'); return; }

        [
            { name: 'csrfmiddlewaretoken', value: csrfMatch[1] },
            { name: 'step',     value: 'init' },
            { name: 'back_url', value: window.location.href },
        ].forEach(function (f) {
            var inp = document.createElement('input');
            inp.type = 'hidden';
            inp.name = f.name;
            inp.value = f.value;
            form.appendChild(inp);
        });

        unique.forEach(function (rmCode) {
            var inp = document.createElement('input');
            inp.type = 'hidden';
            inp.name = 'rm_code';
            inp.value = rmCode;
            form.appendChild(inp);
        });

        document.body.appendChild(form);
        form.submit();
    });
})();
```

- [ ] **Step 4：在 `base.html` 末尾全局加载 JS**

找到（`templates/base.html` 第 135 行）：
```html
<script src="/static/js/multi-blast-toolbar.js"></script>
```

替换为：
```html
<script src="/static/js/multi-blast-toolbar.js"></script>
<script src="/static/js/transcript-align-toolbar.js"></script>
```

- [ ] **Step 5：添加 `ds-tb-teal` 样式**

`seq_list.html` 里 `ds-tb-teal` 颜色暂未在 CSS 中定义。在 `static/css/styles.css` 末尾追加：

```css
/* ── Transcript align toolbar button ──────────────────────────── */
.ds-tb-teal {
  background: #f0fdfa;
  color: #0f766e;
  border: 1px solid #99f6e4;
}
.ds-tb-teal:hover:not(:disabled) {
  background: #ccfbf1;
  border-color: #5eead4;
}
.ds-tb-teal:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
```

- [ ] **Step 6：验证 Django 系统检查**

```bash
source venv/bin/activate
python manage.py check
```

期望输出：`System check identified no issues (0 silenced).`

- [ ] **Step 7：启动开发服务器，手动验证完整流程**

```bash
source venv/bin/activate
python manage.py runserver
```

打开浏览器，执行以下验证：

1. 进入序列列表，**不勾选**任何行 → 「转录本定位」按钮为灰色 disabled 状态
2. 勾选 1~2 条序列 → 按钮变为可点击状态
3. 点击按钮 → 跳转到准备页，表格正确显示 duplex_id / 裸序列预览 / NM 输入框
4. 填写有效 NM 号（如 `NM_000117`，任意真实登录号）→ 点「开始比对」
5. 等待约 5~15 秒（NCBI 网络请求）→ 跳转到结果页，显示位置、得分、对齐图
6. 展开对齐图 → 显示 `<pre>` 等宽字体对齐内容
7. 勾选要写入的行 → 点「确认写入选中」→ 跳回原列表，显示成功 toast
8. 在编辑页验证 Transcript 和 Position 字段已更新

- [ ] **Step 8：Commit**

```bash
git add templates/seq_list.html templates/search_results.html \
        static/js/transcript-align-toolbar.js templates/base.html \
        static/css/styles.css
git commit -m "feat: add transcript alignment toolbar button to seq_list and search_results"
```
