from collections import defaultdict
import statistics as _statistics
import copy
import re, json, os, csv, math
from django.shortcuts import render, redirect, get_object_or_404
from django.http import FileResponse, HttpResponse, Http404, JsonResponse
from django.contrib.auth import authenticate, login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Min, Max, Count, F, Prefetch
from django.core.paginator import InvalidPage, Paginator
from django.db import transaction
from datetime import date as date_type, datetime
from django.contrib import messages
from django.core.files.storage import default_storage
import logging

from app01.models import (
    LmsUser, SeqModule, LinkerModule, DeliveryModule,
    Compound, Strand, Experiment, DataPoint, ExperimentSummary,
    ExperimentAttachment,
)

logger = logging.getLogger("bprdb_log")


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


def register_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        confirm  = request.POST.get('confirm_password', '')
        if not username:
            return render(request, 'register.html', {'error': '用户名不能为空'})
        if len(password) < 6:
            return render(request, 'register.html', {'error': '密码长度不能少于 6 位', 'username': username})
        if password != confirm:
            return render(request, 'register.html', {'error': '两次密码不一致', 'username': username})
        from app01.models import LmsUser
        if LmsUser.objects.filter(username=username).exists():
            return render(request, 'register.html', {'error': '用户名已存在', 'username': username})
        LmsUser.objects.create_user(username=username, password=password, user_type='guest')
        from django.contrib import messages
        messages.success(request, f'账号 {username} 注册成功，请登录（初始权限为 guest，联系管理员升级）')
        return redirect('login')
    return render(request, 'register.html')


@login_required
def index(request):
    return redirect('compound_list')


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


from app01.upload_pipeline import (
    parse_seq_file, parse_summary_csv, parse_cp_file,
    build_preview, normalize_compound_ids, parse_transfection_file,
    parse_invivo_kd_file, parse_body_weight_file, detect_invivo_file_type,
    _BytesFile,
)


@login_required
def upload_view(request):
    if request.method == 'POST':
        batch_label = request.POST.get('batch_label', '').strip()
        assay_name = request.POST.get('assay_name', '').strip()
        exp_date = request.POST.get('exp_date', '').strip() or None

        errors = []
        seq_parsed = None
        summary_parsed = None
        cp_parsed_list = []

        if not batch_label:
            errors.append('批次名称为必填项')

        if 'seq_file' in request.FILES and request.FILES['seq_file'].name:
            try:
                seq_parsed = parse_seq_file(request.FILES['seq_file'])
            except Exception as e:
                errors.append(f'序列文件解析失败：{e}')

        if 'summary_file' in request.FILES and request.FILES['summary_file'].name:
            try:
                summary_parsed = parse_summary_csv(request.FILES['summary_file'])
                if not assay_name and summary_parsed.assay_name:
                    assay_name = summary_parsed.assay_name
            except Exception as e:
                errors.append(f'体外汇总表解析失败：{e}')

        for cp_file in request.FILES.getlist('cp_files'):
            if not cp_file.name:
                continue
            try:
                parsed = parse_cp_file(cp_file)
                cp_parsed_list.append(parsed)
                if not assay_name and parsed.assay_name:
                    assay_name = parsed.assay_name
            except Exception as e:
                errors.append(f'Cp 文件 {cp_file.name} 解析失败：{e}')

        transfection_parsed = None
        if 'transfection_file' in request.FILES and request.FILES['transfection_file'].name:
            try:
                transfection_parsed = parse_transfection_file(
                    request.FILES['transfection_file']
                )
            except Exception as e:
                errors.append(f'转染方案文件解析失败：{e}')

        if not seq_parsed and not summary_parsed and not cp_parsed_list and not errors:
            errors.append('请至少上传序列文件或体外汇总表')

        if errors:
            return render(request, 'upload.html', {'errors': errors})

        try:
            preview = build_preview(
                seq_parsed, summary_parsed, cp_parsed_list,
                batch_label, assay_name, exp_date,
                transfection_parsed=transfection_parsed,
            )
        except Exception as e:
            return render(request, 'upload.html', {'errors': [f'解析错误：{e}']})

        request.session['upload_preview'] = preview
        return redirect('/upload/?preview=1')

    # GET
    preview = None
    if request.GET.get('preview') and 'upload_preview' in request.session:
        preview = request.session['upload_preview']
    return render(request, 'upload.html', {'preview': preview})


@login_required
def upload_confirm_view(request):
    if request.method != 'POST':
        return redirect('upload')

    preview = request.session.get('upload_preview')
    if not preview:
        return redirect('upload')

    preview = copy.deepcopy(preview)

    # Handle optional ID format unification
    chosen_format = request.POST.get('chosen_format')
    if chosen_format and preview.get('id_format_conflict'):
        def _norm(cid):
            return normalize_compound_ids([cid], chosen_format)[0]

        for exp in preview.get('experiments', []):
            exp['compound_id'] = _norm(exp['compound_id'])
            for dp in exp.get('datapoints', []):
                if dp.get('compound_id'):
                    dp['compound_id'] = _norm(dp['compound_id'])
        preview['new_compounds'] = [
            {**c, 'compound_id': _norm(c['compound_id'])}
            for c in preview.get('new_compounds', [])
        ]
        preview['strand_map'] = {
            _norm(cid): data
            for cid, data in preview.get('strand_map', {}).items()
        }

    batch_label = preview['batch_label']
    assay_name = preview['assay_name']
    exp_date_str = preview.get('exp_date')
    exp_date_obj = None
    if exp_date_str:
        try:
            exp_date_obj = date_type.fromisoformat(exp_date_str)
        except ValueError:
            pass

    n_compounds = 0
    n_experiments = 0

    strand_map = preview.get('strand_map', {})

    try:
        with transaction.atomic():
            # Create new compounds
            for c in preview.get('new_compounds', []):
                compound, created = Compound.objects.get_or_create(
                    compound_id=c['compound_id']
                )
                if created:
                    n_compounds += 1

            # Upsert strands for every compound that has sequence data
            for cid, seq_data in strand_map.items():
                compound, _ = Compound.objects.get_or_create(compound_id=cid)
                if seq_data.get('ss_seq'):
                    Strand.objects.get_or_create(
                        compound=compound,
                        strand_type='SS',
                        defaults={
                            'sequence_id': f"{cid}_SS",
                            'modify_seq': seq_data['ss_seq'],
                        },
                    )
                if seq_data.get('as_seq'):
                    Strand.objects.get_or_create(
                        compound=compound,
                        strand_type='AS',
                        defaults={
                            'sequence_id': f"{cid}_AS",
                            'modify_seq': seq_data['as_seq'],
                        },
                    )

            # Create experiments
            for exp_data in preview.get('experiments', []):
                cid = exp_data['compound_id']
                compound, _ = Compound.objects.get_or_create(compound_id=cid)

                exp, exp_created = Experiment.objects.get_or_create(
                    compound=compound,
                    batch_label=batch_label,
                    assay_name=assay_name,
                    defaults={
                        'exp_type': exp_data.get('exp_type', 'in_vitro'),
                        'cell_line': preview.get('cell_line', ''),
                        'notes': preview.get('notes', ''),
                        'date': exp_date_obj,
                    },
                )
                if exp_created:
                    n_experiments += 1

                    dp_objs = [
                        DataPoint(
                            experiment=exp,
                            x_value=dp['x_value'],
                            x_type=dp['x_type'],
                            replicate=dp['replicate'],
                            value=dp['value'],
                            readout_type=dp['readout_type'],
                            is_control=dp.get('is_control', False),
                            raw_cp=dp.get('raw_cp'),
                        )
                        for dp in exp_data.get('datapoints', [])
                    ]
                    DataPoint.objects.bulk_create(dp_objs)

                    if exp_data.get('summary'):
                        s = exp_data['summary']
                        ExperimentSummary.objects.create(
                            experiment=exp,
                            max_kd_pct=s.get('max_kd_pct'),
                            ic50_nm=s.get('ic50_nm'),
                            rank=s.get('rank'),
                        )
    except Exception as e:
        logger.error(f'upload_confirm error: {e}')
        return render(request, 'upload.html', {
            'errors': [f'写库失败：{e}'],
            'preview': preview,
        })

    request.session['upload_stats'] = {
        'n_compounds': n_compounds,
        'n_experiments': n_experiments,
        'batch_label': batch_label,
    }
    del request.session['upload_preview']
    return redirect('upload_success')


@login_required
def upload_success_view(request):
    stats = request.session.pop('upload_stats', {})
    return render(request, 'upload_success.html', {'stats': stats})


@login_required
def user_profile(request):
    user = request.user
    msg = None
    if request.method == 'POST':
        old_pw = request.POST.get('old_password', '')
        new_pw = request.POST.get('new_password', '')
        confirm_pw = request.POST.get('confirm_password', '')
        if not user.check_password(old_pw):
            msg = ('error', '旧密码不正确')
        elif new_pw != confirm_pw:
            msg = ('error', '两次输入的新密码不一致')
        elif len(new_pw) < 6:
            msg = ('error', '新密码长度不能少于 6 位')
        else:
            user.set_password(new_pw)
            user.save()
            login(request, user)
            msg = ('success', '密码已修改')
    projects = [p.strip() for p in user.permissions_project.split(',') if p.strip()]
    return render(request, 'profile.html', {'msg': msg, 'projects': projects})


def _build_vitro_rows(datapoints):
    """One row per concentration, only Mean replicate, sorted high to low."""
    mean_points = [
        dp for dp in datapoints
        if dp.replicate == 'Mean' and not dp.is_control and dp.x_type == 'concentration'
    ]
    mean_points.sort(key=lambda dp: -dp.x_value)
    return [{'dose': dp.x_value, 'mean': dp.value * 100} for dp in mean_points]


def _build_invivo_rows(datapoints, time_unit):
    """One row per filtered timepoint with mean/SD/CV.

    Prefers computing from individual replicates (1/2/3/A/B).
    Falls back to stored Mean/SD replicates when no individual replicates exist
    (which is the case for files uploaded via smart_upload / invivo_upload).
    """
    grouped = defaultdict(list)
    for dp in datapoints:
        if not dp.is_control and dp.replicate not in ('Mean', 'SD') and dp.x_type == 'timepoint':
            grouped[dp.x_value].append(dp.value)

    def _make_label(timepoint):
        if time_unit == 'day':
            return f'Day {int(timepoint)}'
        elif time_unit == 'week':
            return f'Week {int(timepoint)}'
        return f'{int(timepoint)} {time_unit}'

    def _passes_filter(timepoint):
        return not (time_unit == 'day' and timepoint % 7 != 0 and timepoint != 0)

    # Fallback: use stored Mean/SD when no individual replicates exist
    if not grouped:
        mean_map, sd_map = {}, {}
        for dp in datapoints:
            if dp.x_type == 'timepoint' and not dp.is_control:
                if dp.replicate == 'Mean':
                    mean_map[dp.x_value] = dp.value
                elif dp.replicate == 'SD':
                    sd_map[dp.x_value] = dp.value
        rows = []
        for timepoint in sorted(mean_map):
            if not _passes_filter(timepoint):
                continue
            mean = mean_map[timepoint]
            sd = sd_map.get(timepoint)
            cv = (sd / abs(mean) * 100) if (sd is not None and mean) else None
            rows.append({
                'label': _make_label(timepoint),
                'x_value': timepoint,
                'mean': round(mean, 2) if mean is not None else None,
                'sd': round(sd, 2) if sd is not None else None,
                'cv': round(cv, 1) if cv is not None else None,
                'n': None,
            })
        return rows

    rows = []
    for timepoint in sorted(grouped):
        if not _passes_filter(timepoint):
            continue

        vals = grouped[timepoint]
        n = len(vals)
        mean = _statistics.mean(vals) if n else None
        sd = _statistics.stdev(vals) if n >= 2 else None
        cv = (sd / abs(mean) * 100) if (sd is not None and mean) else None

        rows.append({
            'label': _make_label(timepoint),
            'x_value': timepoint,
            'mean': round(mean, 2) if mean is not None else None,
            'sd': round(sd, 2) if sd is not None else None,
            'cv': round(cv, 1) if cv is not None else None,
            'n': n,
        })
    return rows


def _build_batch_groups(experiments):
    """Convert a list of Experiment objects into template-ready batch group dicts.

    Experiments should be pre-ordered newest-first (by batch_label desc).
    The first group gets default_open=True; all others default_open=False.
    """
    groups = []
    for idx, exp in enumerate(experiments):
        summary = getattr(exp, 'summary', None)
        all_dps = list(exp.datapoints.all())
        invivo_readout = None  # always defined; overwritten in the in_vivo branch

        if exp.exp_type == 'in_vitro':
            rows = _build_vitro_rows(all_dps)
            header_ic50 = summary.ic50_nm if summary else None
            header_maxkd = summary.max_kd_pct if summary else None
        else:
            rows = _build_invivo_rows(all_dps, exp.time_unit or 'day')
            header_ic50 = None
            header_maxkd = summary.max_kd_pct if summary else None
            readout_types = {dp.readout_type for dp in all_dps if dp.x_type == 'timepoint' and not dp.is_control}
            if 'knockdown_pct' in readout_types:
                invivo_readout = 'knockdown_pct'
            elif readout_types:
                invivo_readout = next(iter(readout_types))
            else:
                invivo_readout = 'knockdown_pct'

        groups.append({
            'experiment': exp,
            'summary': summary,
            'rows': rows,
            'attachments': list(exp.attachments.all()),
            'tag_label': '体外' if exp.exp_type == 'in_vitro' else '体内',
            'tag_css': 'tag-vitro' if exp.exp_type == 'in_vitro' else 'tag-invivo',
            'header_ic50': header_ic50,
            'header_maxkd': header_maxkd,
            'timepoint_labels': [r['label'] for r in rows] if exp.exp_type == 'in_vivo' else [],
            'invivo_readout': invivo_readout if exp.exp_type == 'in_vivo' else None,
            'default_open': idx == 0,
        })
    return groups


def build_invivo_summary(experiments):
    """Return {compound_id: [{batch_label, timepoints}]}. Uses Mean replicates if any exist for an experiment; otherwise averages A/B."""
    result = defaultdict(list)
    for exp in experiments:
        all_dps = list(exp.datapoints.all())
        mean_dps = {
            dp.x_value: dp.value
            for dp in all_dps
            if dp.replicate == 'Mean' and dp.readout_type == 'knockdown_pct'
        }
        if mean_dps:
            dps = mean_dps
        else:
            ab = defaultdict(list)
            for dp in all_dps:
                if dp.replicate in ('A', 'B') and dp.readout_type == 'knockdown_pct':
                    ab[dp.x_value].append(dp.value)
            dps = {day: sum(vals) / len(vals) for day, vals in ab.items()}
        if not dps:
            continue
        timepoints = [
            {'day': day, 'kd_pct': round(kd, 1)}
            for day, kd in sorted(dps.items())
        ]
        result[exp.compound_id].append({
            'batch_label': exp.batch_label,
            'timepoints': timepoints,
        })
    return dict(result)


@login_required
def compound_list(request):
    q = request.GET.get('q', '').strip()
    project = request.GET.get('project', '').strip()
    target_name_filter = request.GET.get('target_name', '').strip()
    tag = request.GET.get('tag', '').strip()
    group = request.GET.get('group', 'batch').strip()

    qs = Compound.objects.prefetch_related(
        Prefetch('strands', queryset=Strand.objects.order_by('-strand_type')),
        Prefetch(
            'experiments',
            queryset=Experiment.objects.select_related('summary')
                .prefetch_related('datapoints', 'attachments')
                .order_by('-batch_label'),
        ),
    ).order_by('compound_id')

    if q:
        qs = qs.filter(compound_id__icontains=q)
    if project:
        qs = qs.filter(project=project)
    if target_name_filter:
        qs = qs.filter(target_name__icontains=target_name_filter)
    if tag:
        qs = qs.filter(experiments__exp_type=tag).distinct()

    paginator = Paginator(qs, 20)
    try:
        page_obj = paginator.page(int(request.GET.get('page', 1)))
    except (ValueError, InvalidPage):
        page_obj = paginator.page(1)

    row_data = []
    cl_invivo_charts = []
    cl_vitro_charts = []
    for compound in page_obj:
        exps = list(compound.experiments.all())
        if tag:
            exps = [e for e in exps if e.exp_type == tag]
        strand_map = [
            {
                'strand_type': s.strand_type,
                'modify_seq': s.modify_seq,
            }
            for s in compound.strands.all()
        ]
        groups = _build_batch_groups(exps)
        for g in groups:
            exp = g['experiment']
            if exp.exp_type == 'in_vivo':
                pts = [[r['x_value'], r['mean']] for r in g['rows'] if r.get('mean') is not None]
                if pts:
                    cl_invivo_charts.append({
                        'exp_id': exp.id,
                        'readout_type': g['invivo_readout'],
                        'time_unit': exp.time_unit or 'day',
                        'points': pts,
                    })
            else:
                mrna_pts = [
                    [round(math.log10(r['dose']), 4), round(r['mean'], 2)]
                    for r in g['rows']
                    if r.get('dose') and r['dose'] > 0 and r.get('mean') is not None
                ]
                if mrna_pts:
                    kd_pts = [[x, round(max(0.0, 100 - y), 2)] for x, y in mrna_pts]
                    cl_vitro_charts.append({
                        'exp_id': exp.id,
                        'mrna_pts': mrna_pts,
                        'kd_pts': kd_pts,
                    })
            ic50_val = getattr(getattr(exp, 'summary', None), 'ic50_nm', None)
            ic50_str = f'{ic50_val:.2f}' if ic50_val is not None else ''
            row_data.append({
                'compound': compound,
                'strand_map': strand_map,
                'group': g,
                'ic50_str': ic50_str,
            })

    all_projects = sorted(
        Compound.objects.exclude(project='').values_list('project', flat=True).distinct()
    )
    all_targets = sorted(
        Compound.objects.exclude(target_name='').values_list('target_name', flat=True).distinct()
    )

    return render(request, 'compound_list.html', {
        'row_data': row_data,
        'page_obj': page_obj,
        'all_projects': all_projects,
        'all_targets': all_targets,
        'q': q,
        'project': project,
        'target_name': target_name_filter,
        'tag': tag,
        'group': group,
        'cl_invivo_charts': cl_invivo_charts,
        'cl_vitro_charts': cl_vitro_charts,
    })


def _build_vitro_chart_data(exp):
    all_dps = list(exp.datapoints.all())
    conc_dps = [dp for dp in all_dps if dp.x_type == 'concentration']

    def series(readout, rep):
        scale = 100.0 if readout == 'mRNA_remaining' else 1.0
        return sorted(
            [(dp.x_value, dp.value * scale)
             for dp in conc_dps
             if dp.readout_type == readout and dp.replicate == rep],
            key=lambda p: p[0]
        )

    try:
        ic50 = exp.summary.ic50_nm
        max_kd = exp.summary.max_kd_pct
    except ExperimentSummary.DoesNotExist:
        ic50 = None
        max_kd = None

    def kd_from_mrna(mrna_series):
        return [(x, max(0.0, 100.0 - y)) for x, y in mrna_series]

    mrna_mean = series('mRNA_remaining', 'Mean')
    mrna_a    = series('mRNA_remaining', 'A') if not mrna_mean else []
    mrna_b    = series('mRNA_remaining', 'B') if not mrna_mean else []

    has_kd_dp = any(dp.readout_type == 'knockdown_pct' for dp in conc_dps)
    if has_kd_dp:
        kd_mean = series('knockdown_pct', 'Mean')
        kd_a    = series('knockdown_pct', 'A') if not kd_mean else []
        kd_b    = series('knockdown_pct', 'B') if not kd_mean else []
    else:
        kd_mean = kd_from_mrna(mrna_mean)
        kd_a    = kd_from_mrna(mrna_a)
        kd_b    = kd_from_mrna(mrna_b)

    return {
        'exp_id':      exp.id,
        'batch_label': exp.batch_label,
        'ic50_nm':     ic50,
        'max_kd_pct':  max_kd,
        'mrna_mean':   mrna_mean,
        'mrna_a':      mrna_a,
        'mrna_b':      mrna_b,
        'kd_mean':     kd_mean,
        'kd_a':        kd_a,
        'kd_b':        kd_b,
    }


def _build_invivo_chart_data(exp):
    all_dps = list(exp.datapoints.all())
    timepoint_dps = [
        dp for dp in all_dps
        if dp.x_type == 'timepoint' and not dp.is_control
        and dp.x_value is not None and dp.value is not None
    ]
    if not timepoint_dps:
        return {
            'exp_id':       exp.id,
            'batch_label':  exp.batch_label,
            'readout_type': 'knockdown_pct',  # safe default for empty series; chart never renders
            'time_unit':    exp.time_unit or 'day',
            'series':       [],
        }

    readout_types = {dp.readout_type for dp in timepoint_dps}
    if 'knockdown_pct' in readout_types:
        readout_type = 'knockdown_pct'
    elif 'body_weight' in readout_types:
        readout_type = 'body_weight'
    else:
        readout_type = next(iter(readout_types))

    dps = [dp for dp in timepoint_dps if dp.readout_type == readout_type]
    individual = [dp for dp in dps if dp.replicate not in ('Mean', 'SD')]

    if individual:
        grouped = defaultdict(list)
        for dp in individual:
            grouped[dp.x_value].append(dp.value)
        points = []
        for x in sorted(grouped):
            vals = grouped[x]
            n = len(vals)
            mean = _statistics.mean(vals)
            sd = _statistics.stdev(vals) if n >= 2 else 0.0
            points.append({'x': x, 'mean': round(mean, 2), 'sd': round(sd, 2), 'n': n})
    else:
        mean_map = {dp.x_value: dp.value for dp in dps if dp.replicate == 'Mean'}
        sd_map   = {dp.x_value: dp.value for dp in dps if dp.replicate == 'SD'}
        points = []
        for x in sorted(mean_map):
            mean = mean_map[x]
            sd   = sd_map.get(x, 0.0) or 0.0
            points.append({'x': x, 'mean': round(mean, 2), 'sd': round(sd, 2), 'n': 1})

    label = (exp.dose_info or '').strip() or exp.batch_label

    return {
        'exp_id':       exp.id,
        'batch_label':  exp.batch_label,
        'readout_type': readout_type,
        'time_unit':    exp.time_unit or 'day',
        'series': [{'label': label, 'points': points}] if points else [],
    }


@login_required
def compound_detail(request, compound_id):
    compound = get_object_or_404(Compound, pk=compound_id)
    strands = list(compound.strands.all())
    vitro = list(
        compound.experiments
        .filter(exp_type='in_vitro')
        .select_related('summary')
        .prefetch_related('datapoints')
        .order_by('batch_label')
    )
    vivo = list(
        compound.experiments
        .filter(exp_type='in_vivo')
        .prefetch_related('datapoints')
        .order_by('batch_label')
    )
    vitro_chart_data = [_build_vitro_chart_data(exp) for exp in vitro]
    invivo_batches = build_invivo_summary(vivo).get(compound_id, [])
    invivo_chart_data = [_build_invivo_chart_data(exp) for exp in vivo]
    all_attachments = list(
        ExperimentAttachment.objects.filter(
            experiment__compound_id=compound_id
        ).select_related('experiment').order_by('-uploaded_at')
    )
    return render(request, 'compound_detail.html', {
        'compound':          compound,
        'strands':           strands,
        'vitro_batches':     vitro,
        'vitro_chart_data':  vitro_chart_data,
        'invivo_batches':    invivo_batches,
        'invivo_chart_data': invivo_chart_data,
        'all_attachments':   all_attachments,
    })


@login_required
def batch_list(request):
    batches = (
        Experiment.objects
        .values('batch_label')
        .annotate(
            assay_name=Min('assay_name'),
            compound_count=Count('compound_id', distinct=True),
            exp_count=Count('id'),
            dp_count=Count('datapoints'),
            cp_count=Count('datapoints', filter=Q(datapoints__raw_cp__isnull=False)),
        )
        .order_by('-batch_label')
    )
    return render(request, 'batch_manage.html', {'batches': batches})


@login_required
def batch_delete(request, batch_label):
    if request.method != 'POST':
        return redirect('batch_list')
    user = request.user
    allowed = (
        user.is_superuser
        or getattr(user, 'user_type', '') in ('data_admin', 'admin', 'superadmin')
    )
    if not allowed:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('权限不足，需要 data_admin 或以上角色')
    if not Experiment.objects.filter(batch_label=batch_label).exists():
        from django.http import Http404
        raise Http404
    Experiment.objects.filter(batch_label=batch_label).delete()
    messages.success(request, f'批次 {batch_label} 已删除（化合物记录保留）')
    return redirect('batch_list')


@login_required
def invivo_upload_view(request):
    if request.method == 'POST':
        project_code = request.POST.get('project_code', '').strip()
        file_type_override = request.POST.get('file_type_override', '').strip()
        errors = []

        if not project_code:
            errors.append('项目号为必填项')

        if 'invivo_file' not in request.FILES or not request.FILES['invivo_file'].name:
            errors.append('请上传体内数据文件（.csv）')

        if errors:
            return render(request, 'invivo_upload.html', {'errors': errors})

        invivo_file = request.FILES['invivo_file']
        filename = invivo_file.name
        file_bytes = invivo_file.read()

        class _BytesFile:
            def read(self, size=-1):
                return file_bytes

        if file_type_override:
            file_type = file_type_override
        else:
            file_type = detect_invivo_file_type(_BytesFile())

        if file_type not in ('knockdown_pct', 'body_weight'):
            return render(request, 'invivo_upload.html', {
                'errors': [],
                'ask_file_type': True,
                'project_code': project_code,
            })

        try:
            if file_type == 'knockdown_pct':
                parsed = parse_invivo_kd_file(_BytesFile())
            else:
                parsed = parse_body_weight_file(_BytesFile())
        except Exception as e:
            return render(request, 'invivo_upload.html', {'errors': [f'文件解析失败：{e}']})

        if not parsed.groups:
            return render(request, 'invivo_upload.html', {'errors': ['文件解析结果为空，请检查格式']})

        from django.core.files.base import ContentFile
        saved_path = default_storage.save(f'_tmp_invivo/{filename}', ContentFile(file_bytes))

        preview = {
            'project_code': project_code,
            'filename': filename,
            'saved_path': saved_path,
            'readout_type': parsed.readout_type,
            'inferred_time_unit': parsed.inferred_time_unit,
            'needs_dose': parsed.needs_dose,
            'groups': [
                {
                    'compound_id': g.compound_id,
                    'dose_info': g.dose_info,
                    'timepoints': [
                        {'time': tp.time, 'mean': round(tp.mean, 4),
                         'sd': round(tp.sd, 4), 'n': tp.n}
                        for tp in g.timepoints
                    ],
                }
                for g in parsed.groups
            ],
        }
        request.session['invivo_preview'] = preview
        return redirect('/upload/invivo/?preview=1')

    # GET
    preview = None
    if request.GET.get('preview') and 'invivo_preview' in request.session:
        preview = request.session['invivo_preview']
    return render(request, 'invivo_upload.html', {'preview': preview})


@login_required
def invivo_upload_confirm_view(request):
    if request.method != 'POST':
        return redirect('invivo_upload')

    preview = request.session.get('invivo_preview')
    if not preview:
        return redirect('invivo_upload')

    time_unit = request.POST.get('time_unit', '').strip()
    dose_override = request.POST.get('dose_override', '').strip()
    animal_species = request.POST.get('animal_species', '').strip()
    animal_strain = request.POST.get('animal_strain', '').strip()
    route = request.POST.get('route', '').strip()
    gender = request.POST.get('gender', '').strip()

    errors = []
    if not time_unit:
        errors.append('请填写时间单位（天 / 周）')
    if preview['needs_dose'] and not dose_override:
        errors.append('请填写剂量信息（文件中未检测到剂量）')
    if not animal_species:
        errors.append('请填写动物物种')
    if not animal_strain:
        errors.append('请填写动物品系')
    if not route:
        errors.append('请填写给药途径')
    if not gender:
        errors.append('请填写动物性别')

    if errors:
        return render(request, 'invivo_upload.html', {
            'preview': preview,
            'errors': errors,
        })

    batch_label = datetime.now().strftime('B%Y%m%d%H%M%S')
    readout_type = preview['readout_type']
    assay_name_label = 'KD% 时间曲线' if readout_type == 'knockdown_pct' else '体重时间曲线'
    first_exp = None

    try:
        with transaction.atomic():
            for g in preview['groups']:
                compound, _ = Compound.objects.get_or_create(compound_id=g['compound_id'])
                dose_info = g['dose_info'] or dose_override

                exp = Experiment.objects.create(
                    compound=compound,
                    exp_type='in_vivo',
                    assay_name=assay_name_label,
                    batch_label=batch_label,
                    animal_species=animal_species,
                    animal_strain=animal_strain,
                    route=route,
                    gender=gender,
                    time_unit=time_unit,
                    dose_info=dose_info,
                )
                if first_exp is None:
                    first_exp = exp

                dp_objs = []
                for tp in g['timepoints']:
                    dp_objs.append(DataPoint(
                        experiment=exp,
                        x_value=tp['time'],
                        x_type='timepoint',
                        replicate='Mean',
                        value=tp['mean'],
                        readout_type=readout_type,
                    ))
                    dp_objs.append(DataPoint(
                        experiment=exp,
                        x_value=tp['time'],
                        x_type='timepoint',
                        replicate='SD',
                        value=tp['sd'],
                        readout_type=readout_type,
                    ))
                DataPoint.objects.bulk_create(dp_objs)

            saved_path = preview.get('saved_path', '')
            if first_exp and saved_path and default_storage.exists(saved_path):
                from django.core.files.base import ContentFile
                with default_storage.open(saved_path, 'rb') as f:
                    content = f.read()
                att = ExperimentAttachment(experiment=first_exp, label=preview['filename'])
                att.file.save(preview['filename'], ContentFile(content), save=True)
                default_storage.delete(saved_path)

    except Exception as e:
        logger.error(f'invivo_upload_confirm error: {e}')
        return render(request, 'invivo_upload.html', {
            'preview': preview,
            'errors': [f'写库失败：{e}'],
        })

    del request.session['invivo_preview']
    messages.success(request, f'体内数据已上传，批次号 {batch_label}，共 {len(preview["groups"])} 个化合物')
    return redirect('invivo_upload')


def _read_from_storage(path: str):
    """Read bytes from default_storage path; returns None if missing or on error."""
    try:
        if not default_storage.exists(path):
            return None
        with default_storage.open(path, 'rb') as f:
            return f.read()
    except Exception:
        return None


def _generate_batch_label() -> str:
    """Return today's rolling batch label, e.g. 20260617-001."""
    from datetime import date
    prefix = date.today().strftime('%Y%m%d')
    existing = Experiment.objects.filter(
        batch_label__startswith=prefix + '-'
    ).values_list('batch_label', flat=True)
    used_nums = set()
    for bl in existing:
        tail = bl[len(prefix) + 1:]
        if tail.isdigit():
            used_nums.add(int(tail))
    n = 1
    while n in used_nums:
        n += 1
    return f'{prefix}-{n:03d}'


def _slugify_custom_code(label: str) -> str:
    """Stable slug for user-typed custom labels (handles CJK via allow_unicode=True)."""
    from django.utils.text import slugify
    s = slugify(label, allow_unicode=True)
    return s or f'custom_{abs(hash(label)) % 100000}'


def _ensure_vocab(category: str, label: str):
    """Upsert a UploadVocabulary entry; returns the row. Raises ValueError on empty label."""
    from app01.models import UploadVocabulary
    label = label.strip()
    if not label:
        raise ValueError('label cannot be empty')
    code = _slugify_custom_code(label)
    obj, _created = UploadVocabulary.objects.get_or_create(
        category=category, code=code,
        defaults={'label': label, 'is_builtin': False},
    )
    return obj


def _build_smart_preview(file_detections: list, project_code: str) -> dict:
    """
    Build the smart upload preview from user-classified files.

    Each `file_detections` entry MUST have:
      filename, saved_path, file_type_code, readout_code

    Known parsing codes: vitro_summary / vitro_seq / vitro_cp / vitro_transfection
    / invivo_summary. Anything else (including custom_attachment + user-added)
    lands in `attachment_files` with no parsing.
    """
    from app01.models import UploadVocabulary

    invitro_type_files = {
        'vitro_seq': [], 'vitro_summary': [],
        'vitro_cp': [], 'vitro_transfection': [],
    }
    invivo_groups = []
    attachment_files = []
    errors = []

    vocab_label_by_code = {
        v.code: v.label
        for v in UploadVocabulary.objects.all()
    }

    for det in file_detections:
        code = det.get('file_type_code') or ''
        if not code:
            continue  # not yet classified

        file_bytes = _read_from_storage(det['saved_path'])
        if file_bytes is None:
            errors.append(f'{det["filename"]}: 无法读取临时文件')
            continue

        if code in invitro_type_files:
            invitro_type_files[code].append((det['filename'], file_bytes))
            continue

        if code == 'invivo_summary':
            try:
                f = _BytesFile(file_bytes)
                try:
                    parsed = parse_invivo_kd_file(f)
                except Exception:
                    f = _BytesFile(file_bytes)
                    parsed = parse_body_weight_file(f)
                readout_code = det.get('readout_code') or parsed.readout_type
                invivo_groups.append({
                    'filename': det['filename'],
                    'saved_path': det['saved_path'],
                    'readout_code': readout_code,
                    'readout_label': vocab_label_by_code.get(readout_code, readout_code),
                    'inferred_time_unit': parsed.inferred_time_unit,
                    'needs_dose': parsed.needs_dose,
                    'groups': [
                        {
                            'compound_id': g.compound_id,
                            'dose_info': g.dose_info,
                            'timepoints': [
                                {'time': tp.time, 'mean': tp.mean, 'sd': tp.sd, 'n': tp.n}
                                for tp in g.timepoints
                            ],
                        }
                        for g in parsed.groups
                    ],
                })
            except Exception as e:
                errors.append(f'{det["filename"]}: 体内数据解析失败 {e}')
            continue

        # Anything else → store as attachment, no parsing
        attachment_files.append({
            'filename': det['filename'],
            'saved_path': det['saved_path'],
            'vocab_code': code,
            'label': vocab_label_by_code.get(code, code),
        })

    seq_parsed = None
    summary_parsed = None
    cp_parsed_list = []
    transfection_parsed = None

    for filename, file_bytes in invitro_type_files['vitro_seq']:
        try:
            seq_parsed = parse_seq_file(_BytesFile(file_bytes))
        except Exception as e:
            errors.append(f'{filename}: 序列文件解析失败 {e}')

    for filename, file_bytes in invitro_type_files['vitro_summary']:
        try:
            summary_parsed = parse_summary_csv(_BytesFile(file_bytes))
        except Exception as e:
            errors.append(f'{filename}: 汇总表解析失败 {e}')

    for filename, file_bytes in invitro_type_files['vitro_cp']:
        try:
            cp_parsed_list.append(parse_cp_file(_BytesFile(file_bytes)))
        except Exception as e:
            errors.append(f'{filename}: Cp 文件解析失败 {e}')

    for filename, file_bytes in invitro_type_files['vitro_transfection']:
        try:
            transfection_parsed = parse_transfection_file(_BytesFile(file_bytes))
        except Exception as e:
            errors.append(f'{filename}: 转染文件解析失败 {e}')

    invitro = None
    if seq_parsed or summary_parsed or cp_parsed_list:
        try:
            assay_name = (
                (summary_parsed.assay_name if summary_parsed else '')
                or (cp_parsed_list[0].assay_name if cp_parsed_list else '')
            )
            invitro = build_preview(
                seq_parsed, summary_parsed, cp_parsed_list,
                batch_label='', assay_name=assay_name, exp_date=None,
                transfection_parsed=transfection_parsed,
            )
        except Exception as e:
            errors.append(f'体外数据整合失败：{e}')

    has_no_seq = bool(invitro) and not (invitro.get('strand_map') or seq_parsed)

    return {
        'project_code': project_code,
        'file_detections': file_detections,
        'invitro': invitro,
        'invivo_groups': invivo_groups,
        'attachment_files': attachment_files,
        'errors': errors,
        'has_no_seq': has_no_seq,
    }


@login_required
def smart_upload_view(request):
    if request.method == 'POST':
        # ── Phase 2: re-parse with user-selected types ──
        if request.POST.get('reparse'):
            smart_preview = request.session.get('smart_preview', {})
            project_code = smart_preview.get('project_code', '')
            allowed_paths = {
                det['saved_path']
                for det in smart_preview.get('file_detections', [])
            }
            try:
                file_count = int(request.POST.get('file_count', 0))
            except ValueError:
                file_count = 0

            file_detections = []
            for i in range(file_count):
                filename = request.POST.get(f'filename_{i}', '')
                saved_path = request.POST.get(f'saved_path_{i}', '')
                file_type_code = request.POST.get(f'file_type_{i}', '')

                if not (filename and saved_path and saved_path in allowed_paths):
                    continue
                if not file_type_code:
                    continue  # user left "-- 请选择 --"

                # Custom file type — upsert vocabulary
                if file_type_code == '__new__':
                    label = request.POST.get(f'custom_label_{i}', '').strip()
                    if not label:
                        continue
                    vocab = _ensure_vocab('file_type', label)
                    file_type_code = vocab.code

                # Invivo readout (only meaningful when file_type_code == 'invivo_summary')
                readout_code = request.POST.get(f'readout_{i}', '').strip()
                if readout_code == '__new__':
                    rlabel = request.POST.get(f'readout_custom_{i}', '').strip()
                    if rlabel:
                        rvocab = _ensure_vocab('invivo_readout', rlabel)
                        readout_code = rvocab.code
                    else:
                        readout_code = ''

                file_detections.append({
                    'filename': filename,
                    'saved_path': saved_path,
                    'file_type_code': file_type_code,
                    'readout_code': readout_code,
                })

            preview = _build_smart_preview(file_detections, project_code)
            request.session['smart_preview'] = preview
            return redirect('/upload/smart/?preview=1')

        # ── Phase 1: initial upload — save files, no detection ──
        project_code = request.POST.get('project_code', '').strip()
        files = request.FILES.getlist('files')
        if not files:
            return render(request, 'smart_upload.html', {
                'errors': ['请至少上传一个文件'],
                'project_code': project_code,
            })

        from django.core.files.base import ContentFile

        file_detections = []
        for f in files:
            filename = f.name
            file_bytes = f.read()

            saved_path_key = f'_tmp_smart/{filename}'
            if default_storage.exists(saved_path_key):
                default_storage.delete(saved_path_key)
            actual_path = default_storage.save(saved_path_key, ContentFile(file_bytes))

            file_detections.append({
                'filename': filename,
                'saved_path': actual_path,
                'file_type_code': '',
                'readout_code': '',
            })

        preview = _build_smart_preview(file_detections, project_code)
        request.session['smart_preview'] = preview
        return redirect('/upload/smart/?preview=1')

    # GET — pass vocabularies for the dropdowns
    from app01.models import UploadVocabulary
    vocab_file_types = list(
        UploadVocabulary.objects.filter(category='file_type').order_by('-is_builtin', 'label')
    )
    vocab_readouts = list(
        UploadVocabulary.objects.filter(category='invivo_readout').order_by('-is_builtin', 'label')
    )

    if request.GET.get('preview') and 'smart_preview' in request.session:
        return render(request, 'smart_upload.html', {
            'preview': request.session['smart_preview'],
            'vocab_file_types': vocab_file_types,
            'vocab_readouts': vocab_readouts,
            'suggested_batch_label': _generate_batch_label(),
        })

    if 'smart_preview' in request.session:
        del request.session['smart_preview']
    return render(request, 'smart_upload.html', {
        'vocab_file_types': vocab_file_types,
        'vocab_readouts': vocab_readouts,
    })


@login_required
def smart_upload_confirm_view(request):
    if request.method != 'POST':
        return redirect('smart_upload')

    smart_preview = request.session.get('smart_preview')
    if not smart_preview:
        return redirect('smart_upload')

    invitro = smart_preview.get('invitro')
    invivo_groups = smart_preview.get('invivo_groups', [])
    attachment_files = smart_preview.get('attachment_files', [])
    project_code = smart_preview.get('project_code', '')

    batch_label = request.POST.get('batch_label', '').strip()
    assay_name = request.POST.get('assay_name', '').strip()
    exp_date = request.POST.get('exp_date', '').strip() or None
    target_name_input = request.POST.get('target_name', '').strip()

    errors = []

    if not target_name_input:
        errors.append('靶点必填,不能为空')

    # Sequences (vitro_seq) only update Strand records — no batch needed.
    # Batch is required only when creating Experiment/DataPoint records.
    has_exp_data = bool(invitro and invitro.get('experiments')) or bool(invivo_groups)

    if has_exp_data and not batch_label:
        errors.append('批次名称为必填项')

    if batch_label and has_exp_data:
        # Collect compound IDs being uploaded in this batch
        upload_cids = set()
        if invitro:
            upload_cids.update(e['compound_id'] for e in invitro.get('experiments', []))
        for grp in invivo_groups:
            upload_cids.update(g['compound_id'] for g in grp.get('groups', []))

        # Duplicate = same compound already has DataPoints in this batch
        dup_cids = list(
            DataPoint.objects.filter(
                experiment__batch_label=batch_label,
                experiment__compound_id__in=upload_cids,
            ).values_list('experiment__compound_id', flat=True).distinct()
        )
        if dup_cids:
            ids_str = '、'.join(sorted(dup_cids)[:10])
            if len(dup_cids) > 10:
                ids_str += f' 等共 {len(dup_cids)} 个'
            errors.append(f'批次 {batch_label} 中以下化合物已有实验数据：{ids_str}。请更改批次号或先删除旧批次')

    invivo_meta = []
    for i, group in enumerate(invivo_groups):
        time_unit = request.POST.get(f'time_unit_{i}', '').strip()
        dose_override = request.POST.get(f'dose_override_{i}', '').strip()
        animal_species = request.POST.get(f'animal_species_{i}', '').strip()
        animal_strain = request.POST.get(f'animal_strain_{i}', '').strip()
        route = request.POST.get(f'route_{i}', '').strip()
        gender = request.POST.get(f'gender_{i}', '').strip()

        if not time_unit:
            errors.append(f'文件 {group["filename"]}: 请填写时间单位')
        if group['needs_dose'] and not dose_override:
            errors.append(f'文件 {group["filename"]}: 请填写剂量信息')
        if not animal_species:
            errors.append(f'文件 {group["filename"]}: 请填写动物物种')
        if not animal_strain:
            errors.append(f'文件 {group["filename"]}: 请填写动物品系')
        if not route:
            errors.append(f'文件 {group["filename"]}: 请填写给药途径')
        if not gender:
            errors.append(f'文件 {group["filename"]}: 请填写动物性别')
        if not group.get('readout_code'):
            errors.append(f'文件 {group["filename"]}: 请选择 readout 类型')

        invivo_meta.append({
            'time_unit': time_unit,
            'dose_override': dose_override,
            'animal_species': animal_species,
            'animal_strain': animal_strain,
            'route': route,
            'gender': gender,
        })

    if errors:
        from app01.models import UploadVocabulary
        return render(request, 'smart_upload.html', {
            'preview': smart_preview,
            'errors': errors,
            'vocab_file_types': list(UploadVocabulary.objects.filter(category='file_type').order_by('-is_builtin', 'label')),
            'vocab_readouts': list(UploadVocabulary.objects.filter(category='invivo_readout').order_by('-is_builtin', 'label')),
            'suggested_batch_label': _generate_batch_label(),
        })

    n_experiments = 0
    n_invivo = 0
    n_attachments = 0
    invitro_errors = []
    invivo_errors = []
    attachment_errors = []

    # Write in-vitro (one atomic transaction)
    if invitro:
        preview_copy = copy.deepcopy(invitro)
        preview_copy['batch_label'] = batch_label
        preview_copy['assay_name'] = assay_name or preview_copy.get('assay_name', '')
        exp_date_obj = None
        if exp_date:
            try:
                exp_date_obj = date_type.fromisoformat(exp_date)
            except ValueError:
                pass

        try:
            with transaction.atomic():
                for c in preview_copy.get('new_compounds', []):
                    Compound.objects.get_or_create(compound_id=c['compound_id'])

                id_remap = preview_copy.get('id_format_mismatch', {})
                for cid, seq_data in preview_copy.get('strand_map', {}).items():
                    resolved = id_remap.get(cid, cid)
                    compound, _ = Compound.objects.get_or_create(compound_id=resolved)
                    if seq_data.get('ss_seq'):
                        Strand.objects.get_or_create(
                            compound=compound, strand_type='SS',
                            defaults={'sequence_id': f'{resolved}_SS', 'modify_seq': seq_data['ss_seq']},
                        )
                    if seq_data.get('as_seq'):
                        Strand.objects.get_or_create(
                            compound=compound, strand_type='AS',
                            defaults={'sequence_id': f'{resolved}_AS', 'modify_seq': seq_data['as_seq']},
                        )

                for exp_data in preview_copy.get('experiments', []):
                    cid = exp_data['compound_id']
                    compound, _ = Compound.objects.get_or_create(compound_id=cid)
                    exp, exp_created = Experiment.objects.get_or_create(
                        compound=compound,
                        batch_label=preview_copy['batch_label'],
                        assay_name=preview_copy['assay_name'],
                        defaults={
                            'exp_type': exp_data.get('exp_type', 'in_vitro'),
                            'cell_line': preview_copy.get('cell_line', ''),
                            'notes': preview_copy.get('notes', ''),
                            'date': exp_date_obj,
                        },
                    )
                    if exp_created:
                        n_experiments += 1
                        dp_objs = [
                            DataPoint(
                                experiment=exp,
                                x_value=dp['x_value'],
                                x_type=dp['x_type'],
                                replicate=dp['replicate'],
                                value=dp['value'],
                                readout_type=dp['readout_type'],
                                is_control=dp.get('is_control', False),
                                raw_cp=dp.get('raw_cp'),
                            )
                            for dp in exp_data.get('datapoints', [])
                        ]
                        DataPoint.objects.bulk_create(dp_objs)

                        if exp_data.get('summary'):
                            s = exp_data['summary']
                            ExperimentSummary.objects.create(
                                experiment=exp,
                                max_kd_pct=s.get('max_kd_pct'),
                                ic50_nm=s.get('ic50_nm'),
                                rank=s.get('rank'),
                            )
        except Exception as e:
            logger.error(f'smart_upload_confirm invitro error: {e}')
            invitro_errors.append(str(e))

    # Write each in-vivo group in its own atomic transaction (independent)
    for i, group in enumerate(invivo_groups):
        meta = invivo_meta[i]
        batch_label_iv = batch_label
        readout_code = group['readout_code']
        readout_label = group.get('readout_label', readout_code)
        assay_name_iv = f'{readout_label} 时间曲线'
        first_exp = None

        try:
            with transaction.atomic():
                for g in group['groups']:
                    compound, _ = Compound.objects.get_or_create(compound_id=g['compound_id'])
                    dose_info = g['dose_info'] or meta['dose_override']

                    exp = Experiment.objects.create(
                        compound=compound,
                        exp_type='in_vivo',
                        assay_name=assay_name_iv,
                        batch_label=batch_label_iv,
                        animal_species=meta['animal_species'],
                        animal_strain=meta['animal_strain'],
                        route=meta['route'],
                        gender=meta['gender'],
                        time_unit=meta['time_unit'],
                        dose_info=dose_info,
                    )
                    if first_exp is None:
                        first_exp = exp
                    n_invivo += 1

                    dp_objs = []
                    for tp in g['timepoints']:
                        dp_objs.append(DataPoint(
                            experiment=exp, x_value=tp['time'], x_type='timepoint',
                            replicate='Mean', value=tp['mean'], readout_type=readout_code,
                        ))
                        dp_objs.append(DataPoint(
                            experiment=exp, x_value=tp['time'], x_type='timepoint',
                            replicate='SD', value=tp['sd'], readout_type=readout_code,
                        ))
                    DataPoint.objects.bulk_create(dp_objs)

                saved_path = group.get('saved_path', '')
                if first_exp and saved_path and default_storage.exists(saved_path):
                    from django.core.files.base import ContentFile as CF
                    with default_storage.open(saved_path, 'rb') as fh:
                        content = fh.read()
                    att = ExperimentAttachment(experiment=first_exp, label=group['filename'])
                    att.file.save(group['filename'], CF(content), save=True)
                    default_storage.delete(saved_path)
        except Exception as e:
            logger.error(f'smart_upload_confirm invivo error: {e}')
            invivo_errors.append(f'文件 {group["filename"]}: {e}')

    # Write project attachments (custom-typed files)
    if attachment_files:
        from app01.models import ProjectAttachment
        from django.core.files.base import ContentFile as CF
        for att_idx, af in enumerate(attachment_files):
            saved_path = af['saved_path']
            try:
                if not default_storage.exists(saved_path):
                    attachment_errors.append(f'文件 {af["filename"]}: 临时文件已丢失')
                    continue
                with default_storage.open(saved_path, 'rb') as fh:
                    content = fh.read()
                att_context = request.POST.get(f'att_{att_idx}_context', '').strip()
                att_notes = {}
                if att_context == 'vitro':
                    att_notes = {
                        'context': 'vitro',
                        'cell_line': request.POST.get(f'att_{att_idx}_cell_line', '').strip(),
                    }
                elif att_context == 'invivo':
                    att_notes = {
                        'context': 'invivo',
                        'animal_model': request.POST.get(f'att_{att_idx}_animal_model', '').strip(),
                        'dose': request.POST.get(f'att_{att_idx}_dose', '').strip(),
                        'data_type': request.POST.get(f'att_{att_idx}_data_type', '').strip(),
                    }
                pa = ProjectAttachment(
                    project=project_code,
                    label=af['label'],
                    vocab_code=af['vocab_code'],
                    original_filename=af['filename'],
                    uploaded_by=request.user if request.user.is_authenticated else None,
                    notes=att_notes or None,
                )
                pa.file.save(af['filename'], CF(content), save=True)
                default_storage.delete(saved_path)
                n_attachments += 1
            except Exception as e:
                logger.error(f'smart_upload_confirm attachment error: {e}')
                attachment_errors.append(f'文件 {af["filename"]}: {e}')

    # Clean up any remaining temp files (in-vivo + attachment paths already handled above)
    handled_paths = set()
    for group in invivo_groups:
        if group.get('saved_path'):
            handled_paths.add(group['saved_path'])
    for af in attachment_files:
        if af.get('saved_path'):
            handled_paths.add(af['saved_path'])
    for det in smart_preview.get('file_detections', []):
        path = det.get('saved_path', '')
        if path and path not in handled_paths:
            try:
                if default_storage.exists(path):
                    default_storage.delete(path)
            except Exception:
                pass

    # Update target_name for all compounds touched in this upload (required; validated above)
    if not (invitro_errors and invivo_errors):
        touched_cids = set()
        if invitro:
            for cid in invitro.get('strand_map', {}):
                touched_cids.add(cid)
            for exp_data in invitro.get('experiments', []):
                touched_cids.add(exp_data['compound_id'])
        for group in invivo_groups:
            for g in group['groups']:
                touched_cids.add(g['compound_id'])
        if touched_cids:
            Compound.objects.filter(compound_id__in=touched_cids, target_name='').update(
                target_name=target_name_input
            )

    del request.session['smart_preview']

    parts = []
    if n_experiments:
        parts.append(f'{n_experiments} 条体外实验')
    if n_invivo:
        parts.append(f'{n_invivo} 条体内实验')
    if n_attachments:
        parts.append(f'{n_attachments} 个附件')

    all_err = invitro_errors + invivo_errors + attachment_errors
    if all_err:
        messages.warning(request, f'部分写入失败：{"；".join(all_err)}')
    else:
        messages.success(request, f'数据已上传：{", ".join(parts) or "0 条"}')

    return redirect('smart_upload')


@login_required
def attachment_download(request, pk):
    att = get_object_or_404(ExperimentAttachment, pk=pk)
    if not att.file:
        raise Http404
    filename = os.path.basename(att.file.name)
    return FileResponse(att.file.open('rb'), as_attachment=True, filename=filename)
