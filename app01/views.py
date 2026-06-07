from collections import defaultdict
import re, json, os, csv
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, Http404, JsonResponse
from django.contrib.auth import authenticate, login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q
import logging

from app01.models import (
    LmsUser, SeqModule, LinkerModule, DeliveryModule,
    Compound, Strand, Experiment, DataPoint, ExperimentSummary,
)

logger = logging.getLogger("edit_book_log")


# ── Stub views ──────────────────────────────────────────────────────────────

def login_view(request):
    if request.method == "POST":
        user = authenticate(request,
                            username=request.POST.get("username", ""),
                            password=request.POST.get("password", ""))
        if user:
            login(request, user)
            return redirect("index")
        return render(request, "login.html", {"error": "用户名或密码错误"})
    return render(request, "login.html")


def logout_view(request):
    auth_logout(request)
    return redirect("login")


@login_required
def index(request):
    return render(request, "index.html")


# ── Coloring utilities (verbatim from seq_database_v2/app01/views.py) ───────
def _module_list_url(base: str, page, q: str) -> str:
    """构建带 page/q 参数的模块列表页 redirect URL。"""
    qs = f'?page={page}'
    if q:
        qs += f'&q={urllib.parse.quote(str(q))}'
    return f'{base}{qs}'


def get_color_map(modules=None):
    color_palette = [
        "#e06666", "#f6b26b", "#a0d8ef", "#93c47d", "#76a5af",
        "#6fa8dc", "#8e7cc3", "#c27ba0", "#f4cccc", "#1aac6d",
        "#f7c6c7", "#c6e860", "#ffd966", "#ffd966", "#f9cb9c",
        "#d9ead3", "#cfe2f3", "#e6b8af", "#f4cccc", "#b6d7a8",
        "#d5a6bd", "#b4a7d6", "#a2c4c9", "#ffe599", "#b6d7a8",
        "#d9d2e9", "#d0e0e3", "#c9daf8", "#ead1dc", "#fce5cd"
    ]
    special_colors = {
        'ss': "#fff30b",
        's':  "#fff30b",
        '-':  "#c9c9c9",
        'o':  '#c9c9c9',
    }

    if modules is None:
        modules = DeliveryModule.objects.all().order_by('type_code')
    unique_types = sorted(set(m.type_code for m in modules))
    color_map = {}

    for type_code in ['ss', 's', '-', 'o']:
        color_map[type_code] = special_colors.get(type_code, '#cccccc')

    i = 0
    for type_code in unique_types:
        if type_code not in color_map:
            color_map[type_code] = color_palette[i % len(color_palette)]
            i += 1

    return color_map


def get_delivery_colored(seq: str, selected_seq_type: str, seq_type: str,
                         modules=None, color_map=None) -> list:
    """
    给任意 delivery 序列添加颜色标记（不区分 5'/3'）。
    如果 seq_type == 'AS'，将匹配组反向排列。

    modules / color_map 可由调用方预加载传入，避免循环内重复查询 DB。
    """
    if modules is None:
        modules = DeliveryModule.objects.all()

    component_type_map = {
        module.keyword.strip(): module.type_code.strip()
        for module in modules
    }
    component_type_map.update({'ss': 'ss', 's': 's', '-': '-', 'o': 'o'})

    sorted_keywords = sorted(component_type_map.keys(), key=lambda x: -len(x))
    pattern = re.compile(r"|".join(re.escape(k) for k in sorted_keywords))

    if color_map is None:
        color_map = get_color_map(modules=modules)
    type_color_map = color_map
    result = []
    pos = 0
    seq = seq or ""

    # 匹配并构造结果
    while pos < len(seq):
        match = pattern.match(seq, pos)
        if match:
            matched = match.group()
            type_code = component_type_map.get(matched, 'unknown')
            color = type_color_map.get(type_code, 'transparent')
            result.append({
                'char': matched,
                'type': type_code,
                'color': color
            })
            pos += len(matched)
        else:
            # 未知模块（无法匹配），标记为 unknown
            result.append({
                'char': seq[pos],
                'type': 'unknown',
                'color': 'transparent'
            })
            pos += 1


    # --- 选择序列，反转组顺序并让 subs 组合到前一组 main ---
    if seq_type == 'AS':
        #print(f"111111")
        
        groups = []
        current_group = None

        for item in result:
            if item['char'] in ['s', 'o','-']:
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

        # 反转组顺序，连接 subs 到前一组的 main 后面
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

        result = new_result

    #print(result)
    
    return result


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


def get_modify_seq_colored(seq, selected_seq_type, seq_type, dm_modules=None, color_map=None, lk_modules=None):
    parts = detect_embedded_linker(seq or "")
    if parts is not None:
        part1, linker_section, part2 = parts
        if dm_modules is None:
            dm_modules = list(DeliveryModule.objects.all())
        if color_map is None:
            color_map = get_color_map(modules=dm_modules)
        tokens1 = get_modify_seq_colored(part1, selected_seq_type, seq_type, dm_modules, color_map, lk_modules)
        tokens2 = get_modify_seq_colored(part2, selected_seq_type, seq_type, dm_modules, color_map, lk_modules)
        if re.fullmatch(r'-+', linker_section):
            linker_tokens = [{'char': '···', 'type': 'LINKER_DASH', 'count': '',
                              'is_combo': False, 'delivery_label': None, 'delivery_color': None}]
        else:
            linker_tokens = get_modify_seq_colored(
                linker_section.strip('-'), selected_seq_type, seq_type, dm_modules, color_map, lk_modules
            )
        return tokens1 + [_SEP_TOKEN.copy()] + linker_tokens + [_SEP_TOKEN.copy()] + tokens2

    # existing logic below unchanged
    # === 1) 准备输入 ===
    seq = seq or ""

    # === 2) 从 SeqModule 动态构建 base_pattern，从 DeliveryModule 获取 combo 右侧 keyword ===
    sm_keywords = sorted(
        [m.keyword.strip() for m in SeqModule.objects.all() if m.keyword and m.keyword.strip()],
        key=len, reverse=True,
    )
    if lk_modules is not None:
        lk_kws = [m.keyword.strip() for m in lk_modules if m.keyword and m.keyword.strip()]
        sm_keywords = sorted(set(sm_keywords) | set(lk_kws), key=len, reverse=True)
    if dm_modules is None:
        dm_modules = list(DeliveryModule.objects.all())
    dm_keywords = sorted(
        [m.keyword.strip() for m in dm_modules if m.keyword and m.keyword.strip()],
        key=len, reverse=True,
    )
    if color_map is None:
        color_map = get_color_map(modules=dm_modules)
    # keyword → type_code → color
    dm_type_map = {m.keyword.strip(): m.type_code for m in dm_modules if m.keyword}

    keyword_pattern = "|".join(re.escape(k) for k in dm_keywords) if dm_keywords else r"(?!x)x"

    # === 3) base_pattern：SeqModule token + 固定简单 token + 兜底 . ===
    sm_part = "|".join(re.escape(k) for k in sm_keywords) if sm_keywords else r"(?!x)x"
    base_pattern = rf"{sm_part}|ss|s|o|[ACGUT]|."

    # === 4) 组合 token regex（左边 base_pattern，右边 DeliveryModule keyword） ===
    combo_pattern = rf"(?:{base_pattern})-(?:{keyword_pattern})"

    # === 5) 最终 pattern：优先匹配组合 token，再匹配原 base_pattern ===
    final_pattern = rf"{combo_pattern}|{base_pattern}"

    # 使用正则表达式来提取符合条件的片段（IGNORECASE 保证大小写不敏感，如 T(moe)/T(MOE) 均可匹配）
    sequence = re.findall(final_pattern, seq, re.IGNORECASE)

    counter = 0
    result = []

    # === 6) 构造结果 ===
    for char in sequence:
        # 检测 combo token（左=SeqModule, 右=DeliveryModule keyword）
        is_combo = False
        delivery_label = None
        delivery_color = None
        display_char = char

        if char not in ('s', 'ss', 'o'):
            for dk in dm_keywords:
                suffix = '-' + dk
                if char.endswith(suffix):
                    is_combo = True
                    display_char = char[:-len(suffix)]   # e.g. "Cn2"
                    delivery_label = dk                   # e.g. "LP163"
                    dm_type = dm_type_map.get(dk, 'unknown')
                    delivery_color = color_map.get(dm_type, '#cccccc')
                    break

        if display_char in ['s', 'ss', 'o']:
            count = ""
        else:
            counter += 1
            count = counter

        result.append({
            "char": display_char,
            "type": (
                "evp" if display_char == '(EVP)' else
                "moe" if display_char.upper() in ['G(MOE)', 'U(MOE)', 'C(MOE)', 'A(MOE)', 'T(MOE)', 'T(LNA)', 'G(LNA)', 'U(LNA)', 'C(LNA)', 'A(LNA)'] else
                "OCF3" if display_char in ['G(OCF3)', 'U(OCF3)', 'C(OCF3)', 'A(OCF3)'] else
                "GNA" if display_char in ['GA02', 'GU02', 'GC02','GA25','GU25','GC25','GG25','GA30','GU30','GU19','GU18','GU16','GU20','GU05','GU14','GU13','BU01','GU10','GU27'] else
                "TNA" if display_char in ['TA12', 'TC12', 'TG12', 'TU0'] else
                "d" if display_char in ['dA', 'dT', 'dG', 'dC', 'dU','TU'] else
                "f" if display_char in ['Af', 'Cf', 'Uf', 'Gf'] else
                "m" if display_char in ['Am', 'Cm', 'Um', 'Gm'] else
                "I" if display_char in ['I'] else
                "invab" if display_char in ['invab'] else
                "normal" if display_char in ['A', 'C', 'G', 'U'] else
                "others" if (
                    display_char in [
                        'Cn1', 'Uy1', 'Un2', 'U22', 'An1', 'An2', 'Gn2', 'Cn2', 'B04',
                        'Un16','C16','G16','A16','U22','P91','LK1','P93','P96',
                        'U92','C92','G92','A92','VP25A','VPAm','VP25','VP34','VP36','VP37','VP41','VP43','VP44','VP45','VPUm'
                    ]
                    or re.fullmatch(combo_pattern, display_char)
                ) else
                "o" if display_char == 'o' else
                "s" if display_char == 's' else
                "ss" if display_char == 'ss' else
                "unknown"
            ),
            "count": count,
            "is_combo": is_combo,
            "delivery_label": delivery_label,
            "delivery_color": delivery_color,
        })

    # === 7) 展开 LinkerModule combo token（e.g. LK1-L96 → LK1 + L96），过滤裸 - 分隔符 ===
    if lk_modules is not None:
        lk_kw_set = {m.keyword.strip() for m in lk_modules if m.keyword and m.keyword.strip()}
        if lk_kw_set:
            expanded = []
            for tok in result:
                if tok['is_combo'] and tok['char'] in lk_kw_set:
                    expanded.append({**tok, 'is_combo': False, 'delivery_label': None, 'delivery_color': None})
                    expanded.append({'char': tok['delivery_label'], 'type': 'others', 'count': '',
                                     'is_combo': False, 'delivery_label': None, 'delivery_color': None})
                elif tok['char'] == '-' and tok['type'] == 'unknown':
                    pass  # linker section separator, not a nucleotide
                else:
                    expanded.append(tok)
            result = expanded

    # === 8) 保留你原来的 AS 分组反转逻辑 ===
    if seq_type == 'AS':
        result = _reverse_tokens(result)

    return result


def split_tokens_at_sep(tokens):
    """
    Split a token list at two SEP markers (inserted by get_modify_seq_colored for
    dual-segment sequences).  Returns (part1, linker_tokens, part2) or None if fewer
    than two SEP markers are present.
    """
    indices = [i for i, t in enumerate(tokens) if t.get('type') == 'SEP']
    if len(indices) < 2:
        return None
    i1, i2 = indices[0], indices[1]
    return tokens[:i1], tokens[i1+1:i2], tokens[i2+1:]


def align_duplex_tokens(row0_tokens, row1_tokens):
    """
    把两条链的 token 列表按碱基位置配对，返回列列表供嵌套 table 逐列渲染。
    每列: {'col_type': 'linker'|'nuc', 'row0': token|None, 'row1': token|None}
    linker (s/o/ss) 附属在下一个碱基前，作为独立列插入。
    """
    LINKERS = {'s', 'o', 'ss'}

    def to_positions(tokens):
        positions = []
        pending = None
        for t in (tokens or []):
            if t['char'] in LINKERS:
                pending = t
            else:
                positions.append((pending, t))
                pending = None
        return positions

    pos0 = to_positions(row0_tokens)
    pos1 = to_positions(row1_tokens)

    columns = []
    for i in range(max(len(pos0), len(pos1))):
        lk0, nuc0 = pos0[i] if i < len(pos0) else (None, None)
        lk1, nuc1 = pos1[i] if i < len(pos1) else (None, None)
        if lk0 or lk1:
            columns.append({'col_type': 'linker', 'row0': lk0, 'row1': lk1})
        columns.append({'col_type': 'nuc', 'row0': nuc0, 'row1': nuc1})
    return columns


def add_o_to_all_rules(modify_seq):
    """
    将 modify_seq 转换为 linker_seq：在每个修饰 token 后追加连接符（通常为 'o'）。

    追加规则：
      - 如果 token 是序列末尾（无后续字符）：不追加
      - 如果 token 后一位是 's'：不追加
      - 否则：追加 SeqModule.linker_connector（通常 'o'，P91/LK1 等为 '-'）
    """
    modify_seq = modify_seq or ""

    # 从 SeqModule 动态构建 token 正则及连接符映射（按关键字长度降序，最长优先匹配）
    seq_modules = sorted(SeqModule.objects.all(), key=lambda m: len(m.keyword), reverse=True)
    connector_map = {m.keyword.upper(): m.linker_connector for m in seq_modules}
    sm_keywords = [m.keyword for m in seq_modules]
    sm_pattern = "|".join(re.escape(k) for k in sm_keywords) if sm_keywords else r"(?!x)x"
    sm_re = re.compile(sm_pattern, re.IGNORECASE)

    # Combo 正则：LEFT=(SeqModule token + 简单碱基) - RIGHT=(DeliveryModule keyword)
    dm_keywords = sorted(
        [m.keyword.strip() for m in DeliveryModule.objects.all() if m.keyword and m.keyword.strip()],
        key=len, reverse=True,
    )
    dm_pattern = "|".join(re.escape(k) for k in dm_keywords) if dm_keywords else r"(?!x)x"
    left_extras = r'INVAB|I|ss|s|o|[ACGUT]'
    combo_re = re.compile(rf"(?:{sm_pattern}|{left_extras})-(?:{dm_pattern})", re.IGNORECASE)

    linker_seq = ""
    i = 0

    while i < len(modify_seq):
        # 1. Combo 优先：匹配 <token>-<DeliveryModule keyword>
        cm = combo_re.match(modify_seq, i)
        if cm:
            combo = cm.group(0)
            end = i + len(combo)
            if end < len(modify_seq) and modify_seq[end] not in ('s', 'o', '-'):
                linker_seq += combo + 'o'
            else:
                linker_seq += combo
            i = end
            continue

        # 2. SeqModule token 匹配
        sm = sm_re.match(modify_seq, i)
        if sm:
            token = sm.group(0)
            end = i + len(token)
            connector = connector_map.get(token.upper(), '')
            if connector and end < len(modify_seq) and modify_seq[end] not in ('s', 'o', '-'):
                linker_seq += token + connector
            else:
                linker_seq += token
            i = end
            continue

        # 3. 其余字符原样复制
        linker_seq += modify_seq[i]
        i += 1

    return linker_seq


def detect_embedded_linker(modify_seq: str):
    """
    Returns (part1, linker_section, part2) if modify_seq contains an embedded linker,
    or None for normal single-segment sequences.

    Detects:
    - SeqModule linker sandwich: first and last tokens are SeqModule keywords with linker_connector='-' (e.g. -LK1-L96-LK1-)
    - 4+ consecutive dashes (AS placeholder, e.g. ------------)
    Both sides of the match must be non-empty.
    """
    sm_lk_kws = [m.keyword for m in SeqModule.objects.filter(linker_connector='-') if m.keyword]
    lm_kws = [m.keyword for m in LinkerModule.objects.all() if m.keyword]
    linker_keywords = list({*sm_lk_kws, *lm_kws})
    patterns = []
    if linker_keywords:
        kw_pat = '|'.join(re.escape(k) for k in sorted(linker_keywords, key=len, reverse=True))
        # Anchor first and last tokens to linker keywords; middle tokens (0+) can be any alphanumeric token
        patterns.append(rf'-(?:{kw_pat})(?:-(?:[A-Za-z0-9()]+))*-(?:{kw_pat})-')
    patterns.append(r'-{4,}')

    m = re.search('|'.join(patterns), modify_seq)
    if not m:
        return None
    part1 = modify_seq[:m.start()]
    linker_section = m.group(0)
    part2 = modify_seq[m.end():]
    if not part1.strip() or not part2.strip():
        return None
    return part1, linker_section, part2


def add_o_to_all_rules_safe(modify_seq: str) -> str:
    """
    Dual-segment-aware wrapper for add_o_to_all_rules().
    For sequences with an embedded linker, processes Part1 and Part2 separately
    so the linker section keeps its own '-' connectors and is not corrupted.
    """
    parts = detect_embedded_linker(modify_seq or "")
    if parts is None:
        return add_o_to_all_rules(modify_seq or "")
    part1, linker_section, part2 = parts
    return add_o_to_all_rules(part1) + linker_section + add_o_to_all_rules(part2)


def normalize_middle_brackets(modify_seq: str) -> str:
    """将 Modify_seq 中间的 [linker] 括号块替换为 -linker- dash 格式。
    首位括号（delivery5）和末位括号（delivery3）保持不变，只处理中间块。

    例：[invAb]AmUmGm[LK1-L96-LK1]CmAmUm[Vp]
     → [invAb]AmUmGm-LK1-L96-LK1-CmAmUm[Vp]
    """
    if not modify_seq:
        return modify_seq
    blocks = list(re.finditer(r'\[([^\[\]]+)\]', modify_seq))
    if len(blocks) <= 2:
        return modify_seq  # 无中间块，直接返回
    result = modify_seq
    # 从后往前替换，避免字符位移错位；跳过首块（index 0）和末块（index -1）
    for block in reversed(blocks[1:-1]):
        inner = block.group(1)
        result = result[:block.start()] + f'-{inner}-' + result[block.end():]
    return result


def build_duplex_groups(delivery_qs, selected_seq_type):
    # Stub — full implementation in sub-project C (uses new Compound/Strand models)
    return []

