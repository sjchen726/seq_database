# 智能上传（Smart Upload）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 上传 Delivery CSV 时，自动检查序列是否已注册、模块 token 是否已知，并通过预检报告页让用户确认后自动完成裸序列注册，减少手动操作步骤。

**Architecture:** 在现有 `upload_delivery_info` POST 分支中插入 `run_preflight_check()` 分析函数；若有待注册序列或模块警告，将数据暂存至 session，跳转 `confirm_upload_preflight` 页；用户确认后执行 `auto_register_bare_sequences()` 并继续原有上传管道。沿用 `confirm_share_deliveries` 的"预检→确认→执行"模式。

**Tech Stack:** Django 5.1, Python 3.10, pandas, MySQL, Django messages framework, Django session

---

## 文件改动总览

| 文件 | 操作 | 改动规模 |
|------|------|---------|
| `app01/views.py` | 新增 `run_preflight_check()`、`auto_register_bare_sequences()`、`write_skip_csv()`、`confirm_upload_preflight()` 视图；修改 `upload_delivery_info` POST 分支 | 大 |
| `bms/urls.py` | 新增 `confirm_upload_preflight/` 路由 | 小 |
| `templates/confirm_upload_preflight.html` | 新建预检报告模板 | 中 |
| `static/templates/upload_seq_template.csv` | 新增 `Transcript`、`Position` 两列 | 小 |
| `app01/tests.py` | 新增 `RunPreflightCheckTests`、`AutoRegisterTests` 测试类 | 中 |

---

### Task 1: 扩展 CSV 上传模板（新增 Transcript/Position 列）

**Files:**
- Modify: `static/templates/upload_seq_template.csv`

背景：`parse_uploaded_csv` 不改动，用 `df.get('Transcript', '')` 方式读取可选列；模板只需在表头加列。

- [ ] **Step 1: 更新模板文件**

将 `static/templates/upload_seq_template.csv` 全部替换为以下内容（UTF-8 BOM，用于 Excel 兼容）：

```
Project,Target,Seq_type,Modify_seq,Strand_MWs,Parents,Remarks,Transcript,Position
BPR-XXXX,GENE,SS,[invAb]AmUmGmCmAmUmGmCmAmUm[Vp],,,,,
BPR-XXXX,GENE,AS,[Vp]AmGmCmAmUmGmAmCmGmUm[invAb],,,,,
BPR-XXXX,GENE,SS,[invAb]AmUmGmCmAmUmGmCmAmUm[Vp],,,NM_001234,123
BPR-XXXX,GENE,AS,[Vp-invAb]AmGmCmAmUmGmAmCmGmUm[invAb],,,,,
BPR-XXXX,GENE,SS,[invAb]AmUmGm[LK1-L96-LK1]CmAmUm[Vp],,,NM_005678,456
BPR-XXXX,GENE,AS,[Vp]GmAmUmGmCmAmUm[LK1-L96-LK1]CmGmAmUmGmCmAm[invAb],,,,,
BPR-XXXX,GENE,SS,AmUmGmCmAmUmGmCmAmUm,,,,,
BPR-XXXX,GENE,AS,AmGmCmAmUmGmAmCmGmUm,,,,,
```

注意：文件需以 UTF-8 BOM（`\xef\xbb\xbf`）保存，行尾 CRLF 可选。使用 Python 写入时指定 `encoding='utf-8-sig'`。

- [ ] **Step 2: 验证下载功能**

启动开发服务器，访问 `/seq_delivery/?download=template`，下载文件后用 Excel 打开，确认有 9 列（含 Transcript、Position），8 行数据无乱码。

- [ ] **Step 3: Commit**

```bash
git add static/templates/upload_seq_template.csv
git commit -m "feat: add Transcript and Position columns to upload CSV template"
```

---

### Task 2: `run_preflight_check()` — 预检分析函数

**Files:**
- Modify: `app01/views.py`（在 `group_sequences` 之后，约 line 1302，插入新函数）
- Modify: `app01/tests.py`（新增 `RunPreflightCheckTests`）

该函数不写 DB，只做分析，可被单元测试。

- [ ] **Step 1: 在 `app01/tests.py` 中写失败测试**

在文件末尾追加：

```python
import pandas as pd
from django.test import TestCase
from app01.models import Sequence, SeqModule, DeliveryModule
from app01.views import run_preflight_check, group_sequences


def _make_df(rows):
    """Helper: rows is list of dicts with Modify_seq, Seq_type, Project, Target, etc."""
    df = pd.DataFrame(rows)
    df = df.fillna('')
    df['__row_id'] = df.index
    df['__original_line'] = df.index + 2
    return df


class RunPreflightCheckTests(TestCase):

    def setUp(self):
        # Create a SeqModule: 'm' modification (Am → A)
        SeqModule.objects.create(keyword='Am', base_char='A')
        SeqModule.objects.create(keyword='Um', base_char='U')
        SeqModule.objects.create(keyword='Gm', base_char='G')
        SeqModule.objects.create(keyword='Cm', base_char='C')
        # Create a DeliveryModule
        DeliveryModule.objects.create(keyword='invAb', type_code='ligand')
        DeliveryModule.objects.create(keyword='Vp', type_code='ligand')

    def test_clean_pair_both_registered(self):
        """Both naked_seqs exist → auto_register_pairs is empty, clean_groups has the pair."""
        Sequence.objects.create(seq='AUGCAUGCAU', seq_type='SS')
        Sequence.objects.create(seq='AUGCAUGCAU', seq_type='AS')
        rows = [
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'SS',
             'Modify_seq': 'AmUmGmCmAmUmGmCmAmUm', 'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'AS',
             'Modify_seq': 'AmUmGmCmAmUmGmCmAmUm', 'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
        ]
        df = _make_df(rows)
        ss_groups, _ = group_sequences(df)
        result = run_preflight_check(df, ss_groups)
        self.assertEqual(result['auto_register_pairs'], [])
        self.assertEqual(result['unknown_module_pairs'], [])
        self.assertEqual(len(result['clean_groups']), 1)

    def test_unregistered_ss_added_to_auto_register(self):
        """SS naked_seq not in DB → pair added to auto_register_pairs."""
        # Only AS exists
        Sequence.objects.create(seq='AUGCAUGCAU', seq_type='AS')
        rows = [
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'SS',
             'Modify_seq': 'AmUmGmCmAmUmGmCmAmUm', 'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'AS',
             'Modify_seq': 'AmUmGmCmAmUmGmCmAmUm', 'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
        ]
        df = _make_df(rows)
        ss_groups, _ = group_sequences(df)
        result = run_preflight_check(df, ss_groups)
        self.assertEqual(len(result['auto_register_pairs']), 1)
        pair = result['auto_register_pairs'][0]
        self.assertFalse(pair['ss_exists'])
        self.assertTrue(pair['as_exists'])
        self.assertEqual(pair['naked_ss'], 'AUGCAUGCAU')

    def test_transcript_position_from_ss_row(self):
        """Transcript/Position taken from SS row when present."""
        rows = [
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'SS',
             'Modify_seq': 'AmUmGmCm', 'Transcript': 'NM_001234', 'Position': '99',
             'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'AS',
             'Modify_seq': 'AmUmGmCm', 'Transcript': '', 'Position': '',
             'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
        ]
        df = _make_df(rows)
        ss_groups, _ = group_sequences(df)
        result = run_preflight_check(df, ss_groups)
        if result['auto_register_pairs']:
            pair = result['auto_register_pairs'][0]
            self.assertEqual(pair['transcript'], 'NM_001234')
            self.assertEqual(pair['position'], '99')

    def test_transcript_falls_back_to_as_row(self):
        """Transcript taken from AS row when SS row is empty."""
        rows = [
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'SS',
             'Modify_seq': 'AmUmGmCm', 'Transcript': '', 'Position': '',
             'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'AS',
             'Modify_seq': 'AmUmGmCm', 'Transcript': 'NM_999', 'Position': '42',
             'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
        ]
        df = _make_df(rows)
        ss_groups, _ = group_sequences(df)
        result = run_preflight_check(df, ss_groups)
        if result['auto_register_pairs']:
            pair = result['auto_register_pairs'][0]
            self.assertEqual(pair['transcript'], 'NM_999')
            self.assertEqual(pair['position'], '42')

    def test_unknown_seqmodule_token_skips_pair(self):
        """Unknown SeqModule token → pair moves to unknown_module_pairs, not clean_groups."""
        rows = [
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'SS',
             'Modify_seq': 'AmUmZmCm', 'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'AS',
             'Modify_seq': 'AmUmGmCm', 'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
        ]
        df = _make_df(rows)
        ss_groups, _ = group_sequences(df)
        result = run_preflight_check(df, ss_groups)
        self.assertEqual(len(result['unknown_module_pairs']), 1)
        self.assertEqual(len(result['clean_groups']), 0)
        self.assertIn('Z', result['unknown_module_pairs'][0]['unknown_tokens'])

    def test_unknown_delivery_token_warns_only(self):
        """Unknown DeliveryModule token → warning only, pair still in clean_groups."""
        Sequence.objects.create(seq='AUGCAUGC', seq_type='SS')
        Sequence.objects.create(seq='AUGCAUGC', seq_type='AS')
        rows = [
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'SS',
             'Modify_seq': '[UNKNOWN]AmUmGmCmAmUmGmCm', 'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'AS',
             'Modify_seq': 'AmUmGmCmAmUmGmCm', 'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
        ]
        df = _make_df(rows)
        ss_groups, _ = group_sequences(df)
        result = run_preflight_check(df, ss_groups)
        self.assertEqual(len(result['unknown_module_pairs']), 0)
        self.assertEqual(len(result['unknown_delivery_warnings']), 1)
        self.assertIn('UNKNOWN', result['unknown_delivery_warnings'][0]['unknown_tokens'])
```

- [ ] **Step 2: 运行测试，确认全部失败（`run_preflight_check` 未定义）**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2
source venv/bin/activate
python manage.py test app01.tests.RunPreflightCheckTests -v2 2>&1 | tail -20
```

Expected: `ImportError: cannot import name 'run_preflight_check'`

- [ ] **Step 3: 在 `app01/views.py` 插入 `run_preflight_check()` 函数**

在 `check_duplicates` 之前（约 line 1302，`group_sequences` 函数结束后）插入以下代码：

```python
def run_preflight_check(df, ss_groups):
    """
    预检分析：扫描所有 SS/AS 对，返回：
      auto_register_pairs   — naked_seq 未注册，需自动注册
      unknown_module_pairs  — 含未知 SeqModule token，整对跳过
      unknown_delivery_warnings — 含未知 DeliveryModule token，仅警告
      clean_groups          — ss_groups 去掉 unknown_module_pairs 后的剩余组
    """
    # 预加载 SeqModule（只查一次 DB）
    _sm_list = sorted(
        SeqModule.objects.filter(base_char__isnull=False).exclude(base_char=''),
        key=lambda m: len(m.keyword), reverse=True,
    )
    _sm_map = {m.keyword.upper(): m.base_char for m in _sm_list}
    _sm_norm_re = (
        re.compile('|'.join(re.escape(m.keyword) for m in _sm_list), re.IGNORECASE)
        if _sm_list else None
    )

    # 预加载 DeliveryModule 关键词集合
    dm_keywords = set(DeliveryModule.objects.values_list('keyword', flat=True))

    has_transcript_col = 'Transcript' in df.columns
    has_position_col = 'Position' in df.columns

    auto_register_pairs = []
    unknown_module_pairs = []
    unknown_delivery_warnings = []
    skip_group_indices = set()

    for group_idx, (_, project, group) in enumerate(ss_groups):
        if len(group) < 2:
            continue
        ss_row_id, as_row_id = group[0], group[1]
        ss_row = df.loc[ss_row_id]
        as_row = df.loc[as_row_id]

        pair_has_unknown_module = False
        pair_unknown_tokens = []
        pair_original_lines = [int(ss_row['__original_line']), int(as_row['__original_line'])]

        extracted = {}  # 'ss' → {naked_seq, delivery5, delivery3, row_id, original_line}

        for label, row in [('ss', ss_row), ('as', as_row)]:
            full_seq = str(row['Modify_seq'])

            # 提取 delivery5 / delivery3
            d5_m = re.search(r'^\[([^\[\]]*)\]', full_seq)
            d3_m = re.search(r'\[([^\[\]]*)\]$', full_seq)
            delivery5 = d5_m.group(1) if d5_m else ''
            delivery3 = d3_m.group(1) if d3_m else ''

            # 去掉首尾括号 → clean_seq
            clean_seq = re.sub(r'^\[.*?\]', '', full_seq)
            clean_seq = re.sub(r'\[.*?\]$', '', clean_seq)

            # 提取 naked_seq（与 save_deliveries 完全一致）
            tmp = normalize_tmp_seq_with_combo(clean_seq)
            if _sm_norm_re:
                tmp = _sm_norm_re.sub(lambda m: _sm_map[m.group(0).upper()], tmp)
            tmp = re.sub(r'\(.*?\)', '', tmp)
            naked_seq = ''.join(re.findall(r'(INVAB|[AUGCI])', tmp))

            extracted[label] = {
                'naked_seq': naked_seq,
                'delivery5': delivery5,
                'delivery3': delivery3,
                'row_id': int(row['__row_id']),
                'original_line': int(row['__original_line']),
            }

            # ── 检测未知 SeqModule token ──
            tmp_check = normalize_tmp_seq_with_combo(clean_seq)
            if _sm_norm_re:
                tmp_check = _sm_norm_re.sub(lambda m: _sm_map[m.group(0).upper()], tmp_check)
            tmp_check = re.sub(r'[\(\)\[\]\-]', '', tmp_check)
            unknowns = re.findall(r'[^AUGCIaugci\s]', tmp_check)
            if unknowns:
                pair_has_unknown_module = True
                pair_unknown_tokens.extend(unknowns)

            # ── 检测未知 DeliveryModule token（仅警告）──
            row_dm_unknowns = []
            for dm_str in [delivery5, delivery3]:
                if not dm_str:
                    continue
                for token in dm_str.split('-'):
                    token = token.strip()
                    if token and token not in dm_keywords:
                        row_dm_unknowns.append(token)
            if row_dm_unknowns:
                unknown_delivery_warnings.append({
                    'row_id': extracted[label]['row_id'],
                    'unknown_tokens': row_dm_unknowns,
                    'original_line': extracted[label]['original_line'],
                })

        if pair_has_unknown_module:
            skip_group_indices.add(group_idx)
            unknown_module_pairs.append({
                'ss_row_id': extracted['ss']['row_id'],
                'as_row_id': extracted['as']['row_id'],
                'unknown_tokens': list(set(pair_unknown_tokens)),
                'original_lines': pair_original_lines,
            })
            continue

        # ── 检查裸序列是否已注册 ──
        ss_exists = Sequence.objects.filter(seq=extracted['ss']['naked_seq']).exists()
        as_exists = Sequence.objects.filter(seq=extracted['as']['naked_seq']).exists()

        if not ss_exists or not as_exists:
            # 取 Transcript / Position：SS 行优先，AS 行兜底
            transcript = ''
            position = ''
            for r in [ss_row, as_row]:
                if not transcript and has_transcript_col:
                    v = str(r['Transcript']).strip()
                    if v:
                        transcript = v
                if not position and has_position_col:
                    v = str(r['Position']).strip()
                    if v:
                        position = v

            auto_register_pairs.append({
                'ss_row_id': extracted['ss']['row_id'],
                'as_row_id': extracted['as']['row_id'],
                'naked_ss': extracted['ss']['naked_seq'],
                'naked_as': extracted['as']['naked_seq'],
                'ss_exists': ss_exists,
                'as_exists': as_exists,
                'transcript': transcript,
                'position': position,
                'project': str(project).strip(),
            })

    clean_groups = [g for i, g in enumerate(ss_groups) if i not in skip_group_indices]

    return {
        'auto_register_pairs': auto_register_pairs,
        'unknown_module_pairs': unknown_module_pairs,
        'unknown_delivery_warnings': unknown_delivery_warnings,
        'clean_groups': clean_groups,
    }
```

- [ ] **Step 4: 运行测试，确认全部通过**

```bash
python manage.py test app01.tests.RunPreflightCheckTests -v2 2>&1 | tail -20
```

Expected: `OK (6 tests)`

- [ ] **Step 5: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "feat: add run_preflight_check() with tests"
```

---

### Task 3: `auto_register_bare_sequences()` — 自动注册函数

**Files:**
- Modify: `app01/views.py`（紧接 `run_preflight_check` 之后插入）
- Modify: `app01/tests.py`（新增 `AutoRegisterTests` 类）

- [ ] **Step 1: 在 `app01/tests.py` 末尾追加失败测试**

```python
from app01.views import auto_register_bare_sequences


class AutoRegisterTests(TestCase):

    def setUp(self):
        self.username = 'testuser'

    def _make_pair(self, naked_ss, naked_as, ss_exists=False, as_exists=False,
                   transcript='', position='', project='P1'):
        return {
            'ss_row_id': 0,
            'as_row_id': 1,
            'naked_ss': naked_ss,
            'naked_as': naked_as,
            'ss_exists': ss_exists,
            'as_exists': as_exists,
            'transcript': transcript,
            'position': position,
            'project': project,
        }

    def test_both_missing_creates_all(self):
        """Both SS and AS missing → creates SS, AS, duplex, DuplexRelationship, SeqInfo."""
        pairs = [self._make_pair('AUGCAU', 'UGCAUG')]
        registered_log, skipped_log = auto_register_bare_sequences(pairs, self.username)
        self.assertEqual(skipped_log, [])
        self.assertTrue(Sequence.objects.filter(seq='AUGCAU', seq_type='SS').exists())
        self.assertTrue(Sequence.objects.filter(seq='UGCAUG', seq_type='AS').exists())
        self.assertTrue(Sequence.objects.filter(seq='UGCAUG, AUGCAU', seq_type='duplex').exists())
        from app01.models import DuplexRelationship, SeqInfo
        ss_obj = Sequence.objects.get(seq='AUGCAU', seq_type='SS')
        as_obj = Sequence.objects.get(seq='UGCAUG', seq_type='AS')
        self.assertTrue(DuplexRelationship.objects.filter(ss_seq=ss_obj, as_seq=as_obj).exists())
        self.assertTrue(SeqInfo.objects.filter(sequence=ss_obj).exists())

    def test_ss_missing_as_exists(self):
        """SS missing, AS exists → creates SS + new duplex + DuplexRelationship."""
        as_obj = Sequence.objects.create(seq='UGCAUG', seq_type='AS')
        pairs = [self._make_pair('AUGCAU', 'UGCAUG', ss_exists=False, as_exists=True)]
        registered_log, skipped_log = auto_register_bare_sequences(pairs, self.username)
        self.assertEqual(skipped_log, [])
        self.assertTrue(Sequence.objects.filter(seq='AUGCAU', seq_type='SS').exists())
        from app01.models import DuplexRelationship
        ss_obj = Sequence.objects.get(seq='AUGCAU', seq_type='SS')
        self.assertTrue(DuplexRelationship.objects.filter(ss_seq=ss_obj, as_seq=as_obj).exists())

    def test_both_exist_skips_registration(self):
        """Both SS and AS already exist → no new Sequence created, DuplexRelationship still ensured."""
        Sequence.objects.create(seq='AUGCAU', seq_type='SS')
        Sequence.objects.create(seq='UGCAUG', seq_type='AS')
        seq_count_before = Sequence.objects.count()
        pairs = [self._make_pair('AUGCAU', 'UGCAUG', ss_exists=True, as_exists=True)]
        registered_log, skipped_log = auto_register_bare_sequences(pairs, self.username)
        self.assertEqual(skipped_log, [])
        # No new Sequence rows (duplex get_or_create may add 1)
        # but SS and AS counts unchanged
        self.assertEqual(Sequence.objects.filter(seq_type='SS').count(), 1)
        self.assertEqual(Sequence.objects.filter(seq_type='AS').count(), 1)

    def test_transcript_and_position_saved_in_seqinfo(self):
        """Transcript and Position stored in SeqInfo for SS."""
        pairs = [self._make_pair('AAAA', 'UUUU', transcript='NM_001', position='42')]
        auto_register_bare_sequences(pairs, self.username)
        from app01.models import SeqInfo
        ss_obj = Sequence.objects.get(seq='AAAA', seq_type='SS')
        info = SeqInfo.objects.get(sequence=ss_obj)
        self.assertEqual(info.Transcript, 'NM_001')
        self.assertEqual(info.Pos, '42')

    def test_one_pair_failure_does_not_rollback_others(self):
        """Failure in one pair (bad naked_seq) does not prevent other pairs from registering."""
        good_pair = self._make_pair('CCCCCC', 'GGGGGG')
        # Force failure: naked_ss is None (will cause IntegrityError on create)
        bad_pair = {**self._make_pair('', 'TTTTTT'), 'naked_ss': None}
        registered_log, skipped_log = auto_register_bare_sequences(
            [bad_pair, good_pair], self.username
        )
        self.assertTrue(Sequence.objects.filter(seq='CCCCCC', seq_type='SS').exists())
        self.assertEqual(len(skipped_log), 1)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python manage.py test app01.tests.AutoRegisterTests -v2 2>&1 | tail -20
```

Expected: `ImportError: cannot import name 'auto_register_bare_sequences'`

- [ ] **Step 3: 在 `app01/views.py` 的 `run_preflight_check` 之后插入 `auto_register_bare_sequences()`**

```python
def auto_register_bare_sequences(auto_register_pairs, username):
    """
    为未注册的裸序列自动创建 Sequence + SeqInfo + DuplexRelationship。
    每对用独立 savepoint，单对失败不影响其余对。
    返回 (registered_log, skipped_log)。
    """
    registered_log = []
    skipped_log = []
    created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for pair in auto_register_pairs:
        naked_ss = pair['naked_ss']
        naked_as = pair['naked_as']
        ss_exists = pair['ss_exists']
        as_exists = pair['as_exists']
        transcript = pair.get('transcript', '')
        position = pair.get('position', '')
        project = pair.get('project', '')

        try:
            with transaction.atomic():
                # ── SS ──
                if not ss_exists:
                    ss_obj = Sequence.objects.create(
                        seq=naked_ss, seq_type='SS', created_at=created_at
                    )
                    registered_log.append(f"SS created: {naked_ss} ({ss_obj.rm_code})")
                else:
                    ss_obj = Sequence.objects.filter(seq=naked_ss).first()

                # ── AS ──
                if not as_exists:
                    as_obj = Sequence.objects.create(
                        seq=naked_as, seq_type='AS', created_at=created_at
                    )
                    registered_log.append(f"AS created: {naked_as} ({as_obj.rm_code})")
                else:
                    as_obj = Sequence.objects.filter(seq=naked_as).first()

                # ── Duplex ──
                duplex_seq_str = f"{naked_as}, {naked_ss}"
                duplex_obj, duplex_created = Sequence.objects.get_or_create(
                    seq=duplex_seq_str, seq_type='duplex',
                    defaults={'created_at': created_at},
                )
                if duplex_created:
                    registered_log.append(f"Duplex created: {duplex_seq_str[:60]}")

                # ── DuplexRelationship ──
                DuplexRelationship.objects.get_or_create(
                    as_seq=as_obj, ss_seq=ss_obj,
                    defaults={'duplex_seq': duplex_obj},
                )

                # ── SeqInfo (SS only，如不存在则创建) ──
                if not SeqInfo.objects.filter(sequence=ss_obj).exists():
                    SeqInfo.objects.create(
                        sequence=ss_obj,
                        Transcript=transcript,
                        Pos=position,
                        project=project,
                        Remark='',
                        created_at=created_at,
                    )

        except Exception as e:
            skipped_log.append({
                'naked_ss': naked_ss,
                'naked_as': naked_as,
                'error': str(e),
            })

    return registered_log, skipped_log
```

- [ ] **Step 4: 运行测试，确认全部通过**

```bash
python manage.py test app01.tests.AutoRegisterTests -v2 2>&1 | tail -20
```

Expected: `OK (5 tests)`

- [ ] **Step 5: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "feat: add auto_register_bare_sequences() with tests"
```

---

### Task 4: `write_skip_csv()` 帮助函数 + URL + `confirm_upload_preflight` 视图

**Files:**
- Modify: `app01/views.py`
- Modify: `bms/urls.py`

- [ ] **Step 1: 在 `write_unregistered_log` 附近（约 line 1649）插入 `write_skip_csv()`**

在 `write_unpaired_ss_as_log` 之后插入：

```python
def write_skip_csv(df, unknown_module_pairs, username):
    """将 SeqModule 未知的跳过对写入 CSV，供用户下载修正。"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    user_dir = os.path.join('logs', username)
    os.makedirs(user_dir, exist_ok=True)
    filename = f'{username}_skip_unknown_module_{timestamp}.csv'
    filepath = os.path.join(user_dir, filename)

    rows_to_write = []
    for pair in unknown_module_pairs:
        for row_id in [pair['ss_row_id'], pair['as_row_id']]:
            matching = df.loc[df['__row_id'] == row_id]
            if not matching.empty:
                row = matching.iloc[0]
                rows_to_write.append({
                    'Project': row.get('Project', ''),
                    'Target': row.get('Target', ''),
                    'Seq_type': row.get('Seq_type', ''),
                    'Modify_seq': row.get('Modify_seq', ''),
                    'Strand_MWs': row.get('Strand_MWs', ''),
                    'Parents': row.get('Parents', ''),
                    'Remarks': row.get('Remarks', ''),
                    'Unknown_tokens': ', '.join(pair['unknown_tokens']),
                    'Original_lines': ', '.join(str(l) for l in pair['original_lines']),
                })

    with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
        fieldnames = ['Project', 'Target', 'Seq_type', 'Modify_seq',
                      'Strand_MWs', 'Parents', 'Remarks', 'Unknown_tokens', 'Original_lines']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_to_write)

    return filepath
```

- [ ] **Step 2: 在 `bms/urls.py` 中新增路由**

在 `confirm_share/` 路由之后插入：

```python
path('confirm_upload_preflight/', views.confirm_upload_preflight, name='confirm_upload_preflight'),
```

验证：
```bash
python manage.py check 2>&1 | tail -5
```
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 3: 在 `confirm_share_deliveries` 之后（约 line 1837）插入 `confirm_upload_preflight` 视图**

```python
@login_required
def confirm_upload_preflight(request):
    """
    GET  — 渲染预检报告页（从 session 读取数据）
    GET  ?download=skip_csv — 下载跳过序列 CSV
    POST — 执行自动注册并继续上传管道
    """
    if request.method == 'GET':
        if request.GET.get('download') == 'skip_csv':
            skip_path = request.session.get('preflight_skip_csv_path')
            if skip_path and os.path.exists(skip_path):
                with open(skip_path, 'rb') as f:
                    response = HttpResponse(f.read(), content_type='text/csv')
                    response['Content-Disposition'] = (
                        f'attachment; filename="{os.path.basename(skip_path)}"'
                    )
                    return response
            messages.warning(request, "跳过序列 CSV 文件不存在")
            return redirect('confirm_upload_preflight')

        preflight = request.session.get('preflight_result')
        if not preflight:
            return redirect('seq_delivery')
        return render(request, 'confirm_upload_preflight.html', {
            'auto_register_pairs': preflight.get('auto_register_pairs', []),
            'unknown_module_pairs': preflight.get('unknown_module_pairs', []),
            'unknown_delivery_warnings': preflight.get('unknown_delivery_warnings', []),
        })

    if request.method == 'POST':
        preflight = request.session.pop('preflight_result', {})
        df_json = request.session.pop('preflight_df_json', None)
        clean_groups_json = request.session.pop('preflight_clean_groups', None)

        if not df_json or clean_groups_json is None:
            messages.error(request, "会话已过期，请重新上传文件")
            return redirect('seq_delivery')

        auto_register_pairs = preflight.get('auto_register_pairs', [])

        # ── 1. 自动注册（guest 跳过）──
        user_type = getattr(request.user, 'user_type', 'guest')
        if user_type != 'guest' and auto_register_pairs:
            registered_log, skipped_log = auto_register_bare_sequences(
                auto_register_pairs, request.user.username
            )
            if registered_log:
                messages.success(request, f"已自动注册 {len(registered_log)} 条序列")
            if skipped_log:
                messages.warning(request, f"{len(skipped_log)} 对注册失败，已跳过")

        # ── 2. 从 session 恢复 df 和 clean_groups ──
        import pandas as pd
        df = pd.read_json(StringIO(df_json))
        df = df.fillna('')
        # 恢复 index 以支持 df.loc[row_id]
        if '__row_id' in df.columns:
            df.index = df['__row_id'].astype(int)

        raw_groups = json.loads(clean_groups_json)
        clean_groups = [(g[0], g[1], g[2]) for g in raw_groups]

        target_project = None
        if 'Project' in df.columns and not df.empty:
            target_project = str(df['Project'].iloc[0]).strip()

        # ── 3. 继续现有上传管道 ──
        repeated_ids, duplicate_meg, cross_project_duplicates = check_duplicates(
            df, clean_groups, target_project=target_project
        )

        if cross_project_duplicates:
            cross_row_ids = set()
            for item in cross_project_duplicates:
                cross_row_ids.update(item['row_ids'])
            df_normal = df[~df.index.isin(cross_row_ids)].copy()
            request.session['pending_shares'] = cross_project_duplicates
            request.session['pending_upload_df'] = df_normal.to_json()
            request.session['pending_repeated_ids'] = list(repeated_ids)
            request.session['pending_unpaired'] = []
            request.session.pop('preflight_skip_csv_path', None)
            return redirect('confirm_share')

        duplex_id_map = assign_duplex_ids(df, clean_groups, repeated_ids)
        username = request.user.username
        upload_meg, upload_log, unregistered_meg, unregistered_log = save_deliveries(
            df, duplex_id_map, username
        )
        write_upload_log(upload_log, username)
        write_unregistered_log(unregistered_log, username)
        save_repeated_to_session(request, df, repeated_ids, unregistered_log, username)
        request.session.pop('preflight_skip_csv_path', None)

        if upload_meg:
            messages.success(request, f"共 {len(upload_meg)} 条序列成功上传！")
        if repeated_ids:
            messages.warning(request, f"有 {len(duplicate_meg)} 条重复序列！")
        if unregistered_meg:
            messages.warning(request, f"有 {len(unregistered_meg)} 条序列未注册！")
        if not upload_meg:
            messages.error(request, "无新的序列信息上传")

        return render(request, 'upload_delivery_info.html', {
            'success': True,
            'repeated_count': len(repeated_ids),
        })
```

- [ ] **Step 4: 验证语法无误**

```bash
python manage.py check 2>&1 | tail -5
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 5: Commit**

```bash
git add app01/views.py bms/urls.py
git commit -m "feat: add confirm_upload_preflight view, write_skip_csv helper, URL route"
```

---

### Task 5: `confirm_upload_preflight.html` — 预检报告页模板

**Files:**
- Create: `templates/confirm_upload_preflight.html`

沿用项目现有 `base.html` + `design-system.css` 的 ds-* 样式体系。

- [ ] **Step 1: 创建 `templates/confirm_upload_preflight.html`**

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

  {# ── 无任何问题 ── #}
  {% if not auto_register_pairs and not unknown_delivery_warnings and not unknown_module_pairs %}
  <div style="padding:16px;background:#f0fdf4;border:1px solid #86efac;border-radius:8px;color:#166534;margin-bottom:20px;">
    ✅ 所有序列均已注册且模块均已识别，可直接上传。
  </div>
  {% endif %}

  {# ── 操作按钮 ── #}
  <div style="display:flex;gap:12px;justify-content:flex-end;margin-top:24px;">
    <a href="{% url 'seq_delivery' %}" class="ds-btn ds-btn-secondary">取消</a>
    <form method="post" style="display:inline;">
      {% csrf_token %}
      <button type="submit" class="ds-btn ds-btn-primary">确认并上传</button>
    </form>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: 验证模板渲染不报错**

```bash
python manage.py check --deploy 2>&1 | grep -i template || python manage.py check 2>&1 | tail -5
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 3: Commit**

```bash
git add templates/confirm_upload_preflight.html
git commit -m "feat: add confirm_upload_preflight.html preflight report template"
```

---

### Task 6: 在 `upload_delivery_info` POST 分支中接入预检

**Files:**
- Modify: `app01/views.py`（`upload_delivery_info` 视图，约 line 1724–1749）

当 `run_preflight_check` 发现 `auto_register_pairs` 或 `unknown_module_pairs` 时，暂存数据至 session 并跳转预检页。全部 clean 时走原有流程（保持向后兼容）。

- [ ] **Step 1: 替换 `upload_delivery_info` POST 分支中 `group_sequences` 之后到 `check_duplicates` 之前的段落**

找到现有代码（约 line 1721–1748）：

```python
        df = parse_uploaded_csv(request)
        # 标准化 Modify_seq 中的中间 linker 括号：[LK1-L96-LK1] → -LK1-L96-LK1-
        df['Modify_seq'] = df['Modify_seq'].apply(normalize_middle_brackets)
        ss_groups, unpaired_ss_as = group_sequences(df)

        # 从 CSV 第一行读取目标项目
        target_project = None
        if 'Project' in df.columns and not df.empty:
            target_project = str(df['Project'].iloc[0]).strip()

        repeated_ids, duplicate_meg, cross_project_duplicates = check_duplicates(
```

替换为：

```python
        df = parse_uploaded_csv(request)
        # 标准化 Modify_seq 中的中间 linker 括号：[LK1-L96-LK1] → -LK1-L96-LK1-
        df['Modify_seq'] = df['Modify_seq'].apply(normalize_middle_brackets)
        ss_groups, unpaired_ss_as = group_sequences(df)

        # ── 预检分析 ──
        preflight = run_preflight_check(df, ss_groups)
        needs_confirm = (
            bool(preflight['auto_register_pairs'])
            or bool(preflight['unknown_module_pairs'])
        )

        if needs_confirm:
            # 写跳过序列 CSV（如有），路径存 session 供下载
            username = request.user.username
            skip_csv_path = ''
            if preflight['unknown_module_pairs']:
                skip_csv_path = write_skip_csv(df, preflight['unknown_module_pairs'], username)

            # 序列化 preflight 中的不可 JSON 序列化部分
            preflight_serializable = {
                'auto_register_pairs': preflight['auto_register_pairs'],
                'unknown_module_pairs': preflight['unknown_module_pairs'],
                'unknown_delivery_warnings': preflight['unknown_delivery_warnings'],
            }
            clean_groups_serializable = [
                [g[0], g[1], list(g[2])] for g in preflight['clean_groups']
            ]

            request.session['preflight_result'] = preflight_serializable
            request.session['preflight_df_json'] = df.to_json()
            request.session['preflight_clean_groups'] = json.dumps(clean_groups_serializable)
            if skip_csv_path:
                request.session['preflight_skip_csv_path'] = skip_csv_path

            # 未配对的 SS/AS 警告仍然显示
            if unpaired_ss_as:
                messages.warning(request, f"有未成对的 SS 或 AS 序列，请注意检查。")

            return redirect('confirm_upload_preflight')

        # ── 全部 clean：走原有流程 ──
        # 用 preflight['clean_groups'] 替代原 ss_groups，已去掉未知模块对
        ss_groups = preflight['clean_groups']

        # 从 CSV 第一行读取目标项目
        target_project = None
        if 'Project' in df.columns and not df.empty:
            target_project = str(df['Project'].iloc[0]).strip()

        repeated_ids, duplicate_meg, cross_project_duplicates = check_duplicates(
```

- [ ] **Step 2: 验证改动后语法正确**

```bash
python manage.py check 2>&1 | tail -5
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 3: 运行全部测试**

```bash
python manage.py test app01 -v2 2>&1 | tail -30
```

Expected: 所有测试通过（`OK`），失败数为 0。

- [ ] **Step 4: Commit**

```bash
git add app01/views.py
git commit -m "feat: wire upload_delivery_info to run_preflight_check, redirect to preflight confirm page"
```

---

## 功能验收清单（手动测试）

完成所有任务后，按以下步骤人工验证：

1. **全 clean 路径**：上传一个所有序列已注册、所有 token 已知的 CSV → 应直接跳原有上传结果页，不经过预检报告页。
2. **有未注册序列**：上传含未注册裸序列的 CSV → 应跳转预检报告页，显示"将自动注册 N 对"；点"确认并上传"→ 序列被注册，Delivery 成功上传。
3. **SeqModule 未知**：上传含未知 token（如 `Zm`）的 CSV → 报告页显示"已跳过 N 对"；可下载跳过 CSV；其余对正常上传。
4. **DeliveryModule 未知**：上传 `[UNKNOWN_LIG]` 开头的序列 → 报告页显示警告，但点确认后照常上传。
5. **Transcript/Position 填充**：SS 行填 Transcript/Position → SeqInfo 中有对应值。AS 行填 Transcript/Position 而 SS 行为空 → 也能正确填充。
6. **guest 用户**：以 guest 账号上传含未注册序列的 CSV → 预检报告页正常显示，但点确认后序列不被注册（仍提示未注册）。
