from collections import defaultdict
import statistics as _statistics
import copy
import re
import json
import os
import csv
import math
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
    ExperimentAttachment, ProjectAccessRequest, AuditLog,
)

logger = logging.getLogger("bprdb_log")


def _has_module(user, module: str) -> bool:
    if user.is_superuser or user.user_type == 'superadmin':
        return True
    if user.user_type == 'sub_admin':
        return module in (user.module_permissions or '').split(',')
    return False


def _get_permitted_projects(user):
    if user.is_superuser or user.user_type == 'superadmin':
        return None
    return [p.strip() for p in (user.permissions_project or '').split(',') if p.strip()]


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
        project_code = request.POST.get('project_code', '').strip()
        new_user = LmsUser.objects.create_user(
            username=username, password=password,
            user_type='sub_admin',
            module_permissions='upload,data,compound,batch',
            permissions_project=project_code,
        )
        from app01.models import AuditLog as _AuditLog
        import json as _json_reg
        _AuditLog.objects.create(
            actor=new_user,
            action='register',
            detail=_json_reg.dumps({'project': project_code}),
        )
        from django.contrib import messages
        messages.success(request, f'账号 {username} 注册成功，请登录')
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
    parse_seq_file, parse_summary_csv,
    build_preview,
    parse_invivo_kd_file, parse_body_weight_file,
    _BytesFile, canonicalize_compound_id,
    normalize_phase, diff_strands, dedup_phase,
)



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
    projects = [p.strip() for p in (user.permissions_project or '').split(',') if p.strip()]
    access_requests = ProjectAccessRequest.objects.filter(user=user)
    return render(request, 'profile.html', {
        'msg': msg,
        'projects': projects,
        'access_requests': access_requests,
    })


@login_required
def profile_request_project(request):
    if request.method != 'POST':
        return redirect('user_profile')
    project_code = request.POST.get('project_code', '').strip()
    if not project_code:
        messages.error(request, '项目代码不能为空')
        return redirect('user_profile')
    user = request.user
    existing = [p.strip() for p in (user.permissions_project or '').split(',') if p.strip()]
    if project_code in existing:
        messages.warning(request, f'你已拥有项目 {project_code} 的访问权限')
        return redirect('user_profile')
    if ProjectAccessRequest.objects.filter(user=user, project_code=project_code, status='pending').exists():
        messages.warning(request, f'项目 {project_code} 的申请已在审批中')
        return redirect('user_profile')
    ProjectAccessRequest.objects.create(user=user, project_code=project_code)
    AuditLog.objects.create(
        actor=user,
        action='project_request',
        detail=json.dumps({'project': project_code}),
    )
    messages.success(request, f'已提交项目 {project_code} 的访问申请，等待 superadmin 审批')
    return redirect('user_profile')


def _build_vitro_rows(datapoints):
    """One row per concentration, only Mean replicate, sorted high to low."""
    mean_points = [
        dp for dp in datapoints
        if dp.replicate == 'Mean' and not dp.is_control and dp.x_type == 'concentration'
    ]
    mean_points.sort(key=lambda dp: -dp.x_value)

    rep_counts = defaultdict(int)
    for dp in datapoints:
        if dp.replicate not in ('Mean', 'SD') and not dp.is_control and dp.x_type == 'concentration':
            rep_counts[dp.x_value] += 1

    result = []
    for dp in mean_points:
        mrna = dp.value * 100
        n = rep_counts.get(dp.x_value) or None
        result.append({'dose': dp.x_value, 'mean': mrna, 'kd_pct': round(max(0.0, 100.0 - mrna), 1), 'n': n})
    return result


def _build_invivo_rows(datapoints, time_unit):
    """One row per timepoint with mean/SD/CV. For 'day' unit, shows only multiples of 7."""
    grouped = defaultdict(list)
    for dp in datapoints:
        if not dp.is_control and dp.replicate not in ('Mean', 'SD') and dp.x_type == 'timepoint':
            if time_unit == 'day' and dp.x_value % 7 != 0:
                continue
            grouped[dp.x_value].append(dp.value)

    def _make_label(timepoint):
        if time_unit == 'day':
            return f'Day {int(timepoint)}'
        elif time_unit == 'week':
            return f'Week {int(timepoint)}'
        return f'{int(timepoint)} {time_unit}'

    # Fallback: use stored Mean/SD when no individual replicates exist
    if not grouped:
        mean_map, sd_map = {}, {}
        for dp in datapoints:
            if dp.x_type == 'timepoint' and not dp.is_control:
                if time_unit == 'day' and dp.x_value % 7 != 0:
                    continue
                if dp.replicate == 'Mean':
                    mean_map[dp.x_value] = dp.value
                elif dp.replicate == 'SD':
                    sd_map[dp.x_value] = dp.value
        rows = []
        for timepoint in sorted(mean_map):
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


# ---------------------------------------------------------------------------
# Batch-grouping helpers for the redesigned compound list
# ---------------------------------------------------------------------------

_CONTROL_KEYWORDS = {'saline', 'pbs', 'vehicle', 'control', 'nc', 'neg'}


def _is_control_arm(dose_info: str) -> bool:
    return dose_info.lower().strip() in _CONTROL_KEYWORDS


def _get_strand_seqs(compound):
    """Return {'AS': modify_seq_str, 'SS': modify_seq_str} for a compound's strands."""
    result = {}
    for strand in compound.strands.all():
        result[strand.strand_type] = strand.modify_seq
    return result


def _build_vivo_schedule_data(vivo_exps_for_compound):
    """
    Returns:
        readout_data: list of {
            'readout': str,
            'schedules': {sched_key: {days, days_json, groups, groups_json,
                                      control, control_json, key_days, day_range,
                                      summary_rows}}
        }
        summary: {'max_bw_drop': float|None, 'peak_kd': float|None}
    """
    control_exps   = [e for e in vivo_exps_for_compound if     _is_control_arm(e.dose_info)]
    treatment_exps = [e for e in vivo_exps_for_compound if not _is_control_arm(e.dose_info)]

    all_readout_types = sorted({
        dp.readout_type
        for exp in vivo_exps_for_compound
        for dp in exp.datapoints.all()
        if dp.x_type == 'timepoint' and dp.readout_type
    })

    schedule_keys = sorted({e.schedule or '' for e in treatment_exps}) or ['']

    def _select_key_days(days):
        if not days or len(days) <= 5:
            return list(days)
        key = {days[0], days[-1]}
        for d in days:
            if d in (7.0, 14.0):
                key.add(d)
        return sorted(key)

    def _arm_series(exp, days, readout_type):
        mean_map = {
            dp.x_value: dp.value
            for dp in exp.datapoints.all()
            if (dp.x_type == 'timepoint'
                and dp.replicate == 'Mean'
                and dp.readout_type == readout_type)
        }
        if readout_type == 'body_weight':
            day0 = mean_map.get(0.0)
            if day0:
                return [
                    round((mean_map[d] - day0) / day0 * 100, 2) if d in mean_map else None
                    for d in days
                ]
        return [mean_map.get(d) for d in days]

    def _arm_vals_at_key(series, key_days, all_days):
        idx = {d: i for i, d in enumerate(all_days)}
        return [series[idx[d]] if d in idx else None for d in key_days]

    readout_data = []
    for rt in all_readout_types:
        sched_dict = {}
        for sched in schedule_keys:
            t_arms = [e for e in treatment_exps if (e.schedule or '') == sched]
            c_arms = [e for e in control_exps   if (e.schedule or '') == sched]
            if not c_arms:
                c_arms = control_exps[:1]

            all_days = sorted({
                dp.x_value
                for exp in t_arms + c_arms
                for dp in exp.datapoints.all()
                if (dp.x_type == 'timepoint'
                    and dp.replicate == 'Mean'
                    and dp.readout_type == rt)
            })
            if not all_days:
                continue

            key_days  = _select_key_days(all_days)
            day_range = f'Day {int(all_days[0])}–{int(all_days[-1])}' if all_days else ''

            groups = [
                {'label': exp.dose_info, 'data': _arm_series(exp, all_days, rt)}
                for exp in t_arms
            ]
            control = None
            if c_arms:
                ctrl_series = _arm_series(c_arms[0], all_days, rt)
                if any(v is not None for v in ctrl_series):
                    control = {'label': c_arms[0].dose_info, 'data': ctrl_series}

            summary_rows = []
            if control:
                summary_rows.append({
                    'label': control['label'], 'is_control': True,
                    'values': _arm_vals_at_key(control['data'], key_days, all_days),
                })
            for g in groups:
                summary_rows.append({
                    'label': g['label'], 'is_control': False,
                    'values': _arm_vals_at_key(g['data'], key_days, all_days),
                })

            sched_dict[sched] = {
                'days':         all_days,
                'days_json':    json.dumps([float(d) for d in all_days]),
                'groups':       groups,
                'groups_json':  json.dumps(groups),
                'control':      control,
                'control_json': json.dumps(control),
                'key_days':     key_days,
                'day_range':    day_range,
                'summary_rows': summary_rows,
            }

        if sched_dict:
            readout_data.append({'readout': rt, 'schedules': sched_dict})

    # Summary stats
    max_bw_drop = None  # maximum % drop from Day 0 baseline (most negative value)
    peak_kd = None
    for exp in treatment_exps:
        summary = getattr(exp, 'summary', None)
        if summary and summary.max_kd_pct is not None:
            peak_kd = max(peak_kd or 0, summary.max_kd_pct)
        bw_map = {
            dp.x_value: dp.value
            for dp in exp.datapoints.all()
            if dp.readout_type == 'body_weight' and dp.replicate == 'Mean'
        }
        day0 = bw_map.get(0.0)
        if day0:
            for val in bw_map.values():
                pct = (val - day0) / day0 * 100
                if max_bw_drop is None or pct < max_bw_drop:
                    max_bw_drop = pct

    return readout_data, {'max_bw_drop': max_bw_drop, 'peak_kd': peak_kd}


def _build_vitro_compound_entry(compound, vitro_exps):
    """One entry per compound for the vitro sub-table. Uses the first experiment."""
    exp = vitro_exps[0]
    summary = getattr(exp, 'summary', None)
    all_dps = list(exp.datapoints.all())
    rows = _build_vitro_rows(all_dps)
    seqs = _get_strand_seqs(compound)

    mrna_pts = [
        [round(math.log10(r['dose']), 4), round(r['mean'], 2)]
        for r in rows
        if r.get('dose') and r['dose'] > 0 and r.get('mean') is not None
    ]
    kd_pts = [[x, round(max(0.0, 100 - y), 2)] for x, y in mrna_pts]

    return {
        'compound': compound,
        'experiment': exp,
        'exp_ids': [e.id for e in vitro_exps],
        'ic50_str': f"{summary.ic50_nm:.2f}" if summary and summary.ic50_nm is not None else '',
        'ic50_nm': summary.ic50_nm if summary else None,
        'max_kd_pct': summary.max_kd_pct if summary else None,
        'vitro_rows': rows,
        'mrna_pts': mrna_pts,
        'kd_pts': kd_pts,
        'as_seq': seqs.get('AS', ''),
        'ss_seq': seqs.get('SS', ''),
        'attachments': list(exp.attachments.all()),
    }


def _build_vivo_compound_entry(compound, vivo_exps):
    """One entry per compound for the vivo sub-table."""
    readout_data, summary = _build_vivo_schedule_data(vivo_exps)
    readouts = [rd['readout'] for rd in readout_data]
    seqs = _get_strand_seqs(compound)

    # Build dose_groups from summary_rows (already has is_control flag)
    dose_groups = []
    if readout_data:
        first_sched = next(iter(readout_data[0]['schedules'].values()), None)
        if first_sched:
            seen = set()
            for row in first_sched['summary_rows']:
                if row['label'] not in seen:
                    seen.add(row['label'])
                    dose_groups.append({'label': row['label'], 'is_control': row['is_control']})

    all_attachments = []
    seen_att = set()
    for exp in vivo_exps:
        for att in exp.attachments.all():
            if att.pk not in seen_att:
                seen_att.add(att.pk)
                all_attachments.append(att)

    return {
        'compound': compound,
        'exp_ids': [e.id for e in vivo_exps],
        'readout_data': readout_data,
        'readouts': readouts,
        'summary': summary,
        'dose_groups': dose_groups,
        'as_seq': seqs.get('AS', ''),
        'ss_seq': seqs.get('SS', ''),
        'attachments': all_attachments,
    }


def _build_batch_group_new(batch_label, experiments, compound_map):
    """
    Build one batch_group dict from a list of Experiment objects sharing a batch_label.
    compound_map: dict[compound_id -> Compound] (pre-fetched with strands).
    """
    vitro_exps = [e for e in experiments if e.exp_type == 'in_vitro']
    vivo_exps  = [e for e in experiments if e.exp_type == 'in_vivo']

    if vitro_exps and vivo_exps:
        batch_type = 'mixed'
    elif vitro_exps:
        batch_type = 'in_vitro'
    else:
        batch_type = 'in_vivo'

    rep = experiments[0]

    vitro_by_cid = defaultdict(list)
    for e in vitro_exps:
        vitro_by_cid[e.compound_id].append(e)

    vitro_compounds = [
        _build_vitro_compound_entry(compound_map[cid], exps)
        for cid, exps in sorted(vitro_by_cid.items())
        if cid in compound_map
    ]

    vivo_by_cid = defaultdict(list)
    for e in vivo_exps:
        vivo_by_cid[e.compound_id].append(e)

    vivo_compounds = [
        _build_vivo_compound_entry(compound_map[cid], exps)
        for cid, exps in sorted(vivo_by_cid.items())
        if cid in compound_map
    ]

    cell_lines = sorted({e.cell_line for e in vitro_exps if e.cell_line})
    targets = sorted({
        compound_map[e.compound_id].target_name
        for e in experiments
        if e.compound_id in compound_map and compound_map[e.compound_id].target_name
    })

    # Batch-level attachments: collect all unique attachments from every experiment
    # in the batch so every compound's expand panel shows the same source files.
    batch_att_pks = set()
    batch_atts = []
    for e in experiments:
        for att in e.attachments.all():
            if att.pk not in batch_att_pks:
                batch_att_pks.add(att.pk)
                batch_atts.append(att)
    for vc in vitro_compounds:
        vc['attachments'] = batch_atts
    for vc in vivo_compounds:
        vc['attachments'] = batch_atts

    # Aggregate schedules and readouts for batch header display
    all_batch_schedules = sorted({
        s
        for vc in vivo_compounds
        for rd_item in vc['readout_data']
        for s in rd_item['schedules']
    })
    all_batch_readouts = sorted({r for vc in vivo_compounds for r in vc['readouts']})

    meta = {
        'date': rep.date,
        'cell_line': ', '.join(cell_lines),
        'target': ', '.join(targets),
        'animal': f"{rep.gender} {rep.animal_strain}".strip() if vivo_exps else '',
        'route': rep.route if vivo_exps else '',
        'n_vitro': len(vitro_by_cid),
        'n_vivo': len(vivo_by_cid),
        'n_compounds': len(set(vitro_by_cid) | set(vivo_by_cid)),
        'schedules': all_batch_schedules,
        'readouts': all_batch_readouts,
    }

    return {
        'batch_label': batch_label,
        'type': batch_type,
        'meta': meta,
        'vitro_compounds': vitro_compounds,
        'vivo_compounds': vivo_compounds,
    }


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


def _build_vitro_batch_card(exp, best_ic50):
    summary = getattr(exp, 'summary', None)
    all_dps = list(exp.datapoints.all())
    rows = _build_vitro_rows(all_dps)
    mrna_pts = [
        [round(math.log10(r['dose']), 4), round(r['mean'], 2)]
        for r in rows if r.get('dose') and r['dose'] > 0 and r.get('mean') is not None
    ]
    kd_pts = [[x, round(max(0.0, 100 - y), 2)] for x, y in mrna_pts]
    ic50_nm = summary.ic50_nm if summary else None
    return {
        'batch_label': exp.batch_label,
        'date': exp.date,
        'cell_line': exp.cell_line or '',
        'ic50_nm': ic50_nm,
        'max_kd_pct': summary.max_kd_pct if summary else None,
        'is_best': ic50_nm is not None and best_ic50 is not None and ic50_nm == best_ic50,
        'vitro_rows': rows,
        'mrna_pts': mrna_pts,
        'kd_pts': kd_pts,
        'attachments': list(exp.attachments.all()),
    }


def _build_vivo_batch_card(batch_exps):
    """One card per unique batch_label for a compound's vivo experiments."""
    readout_data, summary = _build_vivo_schedule_data(batch_exps)
    exp = batch_exps[0]
    seen, atts = set(), []
    for e in batch_exps:
        for att in e.attachments.all():
            if att.pk not in seen:
                seen.add(att.pk)
                atts.append(att)
    return {
        'batch_label': exp.batch_label,
        'date': exp.date,
        'animal': f"{exp.gender or ''} {exp.animal_strain or ''}".strip(),
        'route': exp.route or '',
        'schedule': exp.schedule or '',
        'peak_kd': summary.get('peak_kd'),
        'max_bw_drop': summary.get('max_bw_drop'),
        'readout_data': readout_data,
        'attachments': atts,
    }


def _build_compound_entry(compound, experiments):
    vitro_exps = [e for e in experiments if e.exp_type == 'in_vitro']
    vivo_exps  = [e for e in experiments if e.exp_type == 'in_vivo']
    seqs = _get_strand_seqs(compound)

    vitro_ic50s = [
        e.summary.ic50_nm for e in vitro_exps
        if getattr(e, 'summary', None) and e.summary.ic50_nm is not None
    ]
    vitro_kds = [
        e.summary.max_kd_pct for e in vitro_exps
        if getattr(e, 'summary', None) and e.summary.max_kd_pct is not None
    ]
    best_ic50   = min(vitro_ic50s) if vitro_ic50s else None
    best_kd_pct = max(vitro_kds)   if vitro_kds   else None

    vitro_batches = sorted(
        [_build_vitro_batch_card(e, best_ic50) for e in vitro_exps],
        key=lambda x: str(x['date'] or ''), reverse=True
    )

    vivo_by_batch = defaultdict(list)
    for e in vivo_exps:
        vivo_by_batch[e.batch_label].append(e)
    vivo_batches = sorted(
        [_build_vivo_batch_card(exps) for exps in vivo_by_batch.values()],
        key=lambda x: str(x['date'] or ''), reverse=True
    )

    return {
        'compound': compound,
        'as_seq': seqs.get('AS', ''),
        'ss_seq': seqs.get('SS', ''),
        'best_ic50': best_ic50,
        'best_kd_pct': best_kd_pct,
        'n_vitro': len(vitro_batches),
        'n_vivo': len(vivo_batches),
        'vitro_batches': vitro_batches,
        'vivo_batches': vivo_batches,
    }


def _build_compound_centric_page(exp_qs, page, sort='', order='desc'):
    cid_map = defaultdict(list)
    for exp in exp_qs:
        cid_map[exp.compound_id].append(exp)

    def _cid_sort_key(cid):
        exps = cid_map[cid]
        if sort == 'compound_id':
            return cid
        elif sort == 'ic50':
            vals = [e.summary.ic50_nm for e in exps if getattr(e, 'summary', None) and e.summary.ic50_nm is not None]
            return min(vals) if vals else float('inf')
        elif sort == 'kd':
            vals = [e.summary.max_kd_pct for e in exps if getattr(e, 'summary', None) and e.summary.max_kd_pct is not None]
            return max(vals) if vals else -1
        elif sort == 'n_vitro':
            return sum(1 for e in exps if e.exp_type == 'in_vitro')
        elif sort == 'n_vivo':
            return sum(1 for e in exps if e.exp_type == 'in_vivo')
        else:
            labels = [e.batch_label for e in exps if e.batch_label]
            return max(labels) if labels else ''

    reverse = (order == 'desc')
    if sort == 'compound_id':
        reverse = (order == 'desc')

    sorted_cids = sorted(cid_map.keys(), key=_cid_sort_key, reverse=reverse)
    paginator = Paginator(sorted_cids, 20)
    try:
        page_obj = paginator.page(int(page))
    except (ValueError, InvalidPage):
        page_obj = paginator.page(1)

    page_cids = list(page_obj.object_list)
    compound_map = {
        c.compound_id: c
        for c in Compound.objects.filter(compound_id__in=page_cids)
                          .prefetch_related('strands')
    }
    entries = [
        _build_compound_entry(compound_map[cid], cid_map[cid])
        for cid in page_cids
        if cid in compound_map
    ]
    return entries, page_obj


@login_required
def compound_list(request):
    q = request.GET.get('q', '').strip()
    project_filter = request.GET.get('project', '').strip()
    target_name_filter = request.GET.get('target_name', '').strip()
    tag = request.GET.get('tag', '').strip()
    view_mode = request.GET.get('view', 'batch')
    sort  = request.GET.get('sort', '').strip()
    order = request.GET.get('order', 'desc').strip()
    if order not in ('asc', 'desc'):
        order = 'desc'

    # ── Project-level permission enforcement ──
    _permitted = _get_permitted_projects(request.user)

    # ── Fetch and filter experiments ──
    exp_qs = (
        Experiment.objects
        .select_related('compound', 'summary')
        .prefetch_related('datapoints', 'attachments')
        .order_by('batch_label', 'compound__compound_id')
    )
    if _permitted is not None:
        exp_qs = exp_qs.filter(compound__project__in=_permitted)
    if q:
        exp_qs = exp_qs.filter(
            Q(compound__compound_id__icontains=q) |
            Q(compound__target_name__icontains=q) |
            Q(compound__strands__modify_seq__icontains=q)
        ).distinct()
    if project_filter:
        exp_qs = exp_qs.filter(compound__project=project_filter)
    if target_name_filter:
        exp_qs = exp_qs.filter(compound__target_name__icontains=target_name_filter)
    if tag:
        exp_qs = exp_qs.filter(exp_type=tag)

    # ── Branch by view_mode ──
    if view_mode == 'compound':
        compound_entries, page_obj = _build_compound_centric_page(
            exp_qs, request.GET.get('page', 1), sort=sort, order=order
        )
        batch_groups = []
    else:
        compound_entries = []
        # ── Group experiments by batch_label ──
        batch_map = defaultdict(list)
        for exp in exp_qs:
            batch_map[exp.batch_label].append(exp)

        sorted_batches = sorted(batch_map.items(), key=lambda x: x[0], reverse=True)

        paginator = Paginator(sorted_batches, 10)
        try:
            page_obj = paginator.page(int(request.GET.get('page', 1)))
        except (ValueError, InvalidPage):
            page_obj = paginator.page(1)

        page_cids = {
            exp.compound_id
            for _, exps in page_obj.object_list
            for exp in exps
        }
        compound_map = {
            c.compound_id: c
            for c in Compound.objects.filter(compound_id__in=page_cids)
                              .prefetch_related('strands')
        }
        batch_groups = [
            _build_batch_group_new(bl, exps, compound_map)
            for bl, exps in page_obj.object_list
        ]

    _proj_qs = Compound.objects.exclude(project='').order_by()
    if _permitted is not None:
        _proj_qs = _proj_qs.filter(project__in=_permitted)
    all_projects = sorted(_proj_qs.values_list('project', flat=True).distinct())
    all_targets = sorted(
        Compound.objects.exclude(target_name='').order_by().values_list('target_name', flat=True).distinct()
    )

    # ── Stats bar data ──
    total_compounds = Compound.objects.count()
    total_vitro_batches = (
        exp_qs.filter(exp_type='in_vitro')
        .values('batch_label').distinct().count()
    )
    total_vivo_batches = (
        exp_qs.filter(exp_type='in_vivo')
        .values('batch_label').distinct().count()
    )
    filtered_compound_count = None
    if any([q, project_filter, target_name_filter, tag]):
        filtered_compound_count = exp_qs.values('compound_id').distinct().count()

    per_page = page_obj.paginator.per_page
    page_start = (page_obj.number - 1) * per_page + 1
    page_end   = min(page_obj.number * per_page, page_obj.paginator.count)
    page_total = page_obj.paginator.count

    return render(request, 'compound_list.html', {
        'batch_groups': batch_groups,
        'page_obj': page_obj,
        'all_projects': all_projects,
        'all_targets': all_targets,
        'q': q,
        'project': project_filter,
        'target_name': target_name_filter,
        'tag': tag,
        'total_compounds': total_compounds,
        'total_vitro_batches': total_vitro_batches,
        'total_vivo_batches': total_vivo_batches,
        'filtered_compound_count': filtered_compound_count,
        'view_mode': view_mode,
        'compound_entries': compound_entries,
        'sort': sort,
        'order': order,
        'page_start': page_start,
        'page_end': page_end,
        'page_total': page_total,
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
    if not _has_module(user, 'data'):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('权限不足')
    if not Experiment.objects.filter(batch_label=batch_label).exists():
        from django.http import Http404
        raise Http404
    Experiment.objects.filter(batch_label=batch_label).delete()
    messages.success(request, f'批次 {batch_label} 已删除（化合物记录保留）')
    return redirect('batch_list')


@login_required
def experiments_bulk_delete(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    if not _has_module(request.user, 'data'):
        return JsonResponse({'error': '权限不足'}, status=403)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'invalid JSON'}, status=400)
    exp_ids = data.get('exp_ids', [])
    _, breakdown = Experiment.objects.filter(id__in=exp_ids).delete()
    count = breakdown.get('app01.Experiment', 0)
    return JsonResponse({'deleted': count})


@login_required
def experiments_export_csv(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'invalid JSON'}, status=400)
    exp_ids = data.get('exp_ids', [])
    exps = (
        Experiment.objects
        .filter(id__in=exp_ids)
        .select_related('compound', 'summary')
        .prefetch_related('datapoints')
    )
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="compound_export.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'compound_id', 'batch_label', 'exp_type', 'assay_name',
        'cell_line', 'date', 'ic50_nm', 'max_kd_pct',
        'x_type', 'x_value', 'readout_type', 'replicate', 'value',
    ])
    for exp in exps:
        try:
            ic50 = exp.summary.ic50_nm
            max_kd = exp.summary.max_kd_pct
        except ExperimentSummary.DoesNotExist:
            ic50 = None
            max_kd = None
        for dp in exp.datapoints.all():
            writer.writerow([
                exp.compound_id, exp.batch_label, exp.exp_type,
                exp.assay_name, exp.cell_line, exp.date,
                ic50, max_kd,
                dp.x_type, dp.x_value, dp.readout_type, dp.replicate, dp.value,
            ])
    return response


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
    """Return today's rolling batch label, e.g. 20260617-001. Atomic under concurrent uploads."""
    from datetime import date
    from django.db import transaction
    prefix = date.today().strftime('%Y%m%d')
    with transaction.atomic():
        existing = list(
            Experiment.objects
            .select_for_update()
            .filter(batch_label__startswith=prefix + '-')
            .values_list('batch_label', flat=True)
        )
        used = set()
        for bl in existing:
            tail = bl[len(prefix) + 1:]
            if tail.isdigit():
                used.add(int(tail))
        n = 1
        while n in used:
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


def _collect_unique_compound_ids(invitro, invivo_groups):
    """Return ordered list of unique compound IDs across invitro experiments and invivo groups."""
    seen = set()
    result = []
    for exp in (invitro.get('experiments', []) if invitro else []):
        cid = exp['compound_id']
        if cid not in seen:
            seen.add(cid)
            result.append(cid)
    for group in invivo_groups:
        for g in group.get('groups', []):
            cid = g['compound_id']
            if cid not in seen:
                seen.add(cid)
                result.append(cid)
    return result


def _build_smart_preview(file_detections: list, project_code: str) -> dict:
    """
    Build the smart upload preview from user-classified files.

    Each `file_detections` entry MUST have:
      filename, saved_path, file_type_code, readout_code

    Known parsing codes: vitro_summary / vitro_seq / invivo_summary.
    Anything else (including custom_attachment + user-added)
    lands in `source_files` with no parsing.
    """
    from app01.models import UploadVocabulary

    invitro_type_files = {
        'vitro_seq': [],
        'vitro_summary': [],
    }
    invivo_groups = []
    source_files = []
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
                readout_code = det.get('readout_code') or ''
                # Use user-selected readout to pick the correct parser
                if readout_code == 'body_weight':
                    parsed = parse_body_weight_file(f)
                else:
                    parsed = parse_invivo_kd_file(f)
                readout_code = readout_code or parsed.readout_type
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
                            'dose': g.dose,
                            'schedule': g.schedule,
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

        # Anything else → source file, no parsing
        source_files.append({
            'filename': det['filename'],
            'saved_path': det['saved_path'],
            'vocab_code': code,
            'label': vocab_label_by_code.get(code, code),
        })

    seq_parsed = None
    summary_parsed = None

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

    invitro = None
    if seq_parsed or summary_parsed:
        try:
            assay_name = summary_parsed.assay_name if summary_parsed else ''
            invitro = build_preview(
                seq_parsed, summary_parsed, [],
                batch_label='', assay_name=assay_name, exp_date=None,
                transfection_parsed=None,
            )
        except Exception as e:
            errors.append(f'体外数据整合失败：{e}')

    has_no_seq = bool(invitro) and not (invitro.get('strand_map') or seq_parsed)

    has_exp_data = (
        bool(invitro and invitro.get('experiments')) or
        bool(invitro and invitro.get('strand_map')) or
        bool(invivo_groups)
    )
    is_source_only = bool(source_files) and not has_exp_data

    return {
        'project_code': project_code,
        'file_detections': file_detections,
        'invitro': invitro,
        'invivo_groups': invivo_groups,
        'source_files': source_files,
        'errors': errors,
        'has_no_seq': has_no_seq,
        'is_source_only': is_source_only,
        'unique_compound_ids': _collect_unique_compound_ids(invitro, invivo_groups),
    }


@login_required
def smart_upload_view(request):
    if not _has_module(request.user, 'upload'):
        messages.error(request, '权限不足，无法访问上传页面')
        return redirect('compound_list')
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
        import json as _json
        preview_data = request.session['smart_preview']
        proj = preview_data.get('project_code', '')
        qs = Experiment.objects.filter(compound__project=proj) if proj else Experiment.objects
        available_batches = list(
            qs.order_by().values_list('batch_label', flat=True)
            .distinct().order_by('-batch_label')
        )
        # Build {batch_label: [{exp_type, label, pk}]} for JS checkbox population
        batch_experiments = {}
        for exp in qs.order_by('-batch_label'):
            bl = exp.batch_label
            if not bl:
                continue
            if bl not in batch_experiments:
                batch_experiments[bl] = []
            label = exp.assay_name or bl
            batch_experiments[bl].append({
                'exp_type': exp.exp_type,
                'label': label,
                'pk': exp.pk,
            })
        return render(request, 'smart_upload.html', {
            'preview': preview_data,
            'vocab_file_types': vocab_file_types,
            'vocab_readouts': vocab_readouts,
            'suggested_batch_label': _generate_batch_label(),
            'available_batches': available_batches,
            'batch_experiments_json': _json.dumps(batch_experiments),
        })

    if 'smart_preview' in request.session:
        del request.session['smart_preview']
    return render(request, 'smart_upload.html', {
        'vocab_file_types': vocab_file_types,
        'vocab_readouts': vocab_readouts,
    })


@login_required
def smart_upload_preview_view(request):
    if not _has_module(request.user, 'upload'):
        messages.error(request, '权限不足，无法访问上传页面')
        return redirect('compound_list')
    if request.method != 'POST':
        return redirect('smart_upload')

    smart_preview = request.session.get('smart_preview')
    if not smart_preview:
        return redirect('smart_upload')

    project_code = smart_preview.get('project_code', '')
    invitro = smart_preview.get('invitro') or {}
    invivo_groups = smart_preview.get('invivo_groups', [])

    # Preserve form values in session so confirm view can read them without re-POST
    upload_meta = {
        'batch_label':   request.POST.get('batch_label', '').strip(),
        'assay_name':    request.POST.get('assay_name', '').strip(),
        'exp_date':      request.POST.get('exp_date', '').strip() or None,
        'target_name':   request.POST.get('target_name', '').strip(),
        'source_batch':  request.POST.get('source_batch', '').strip(),
        'attach_vitro':  request.POST.get('source_exp_vitro') == '1',
        'attach_vivo':   request.POST.get('source_exp_vivo') == '1',
    }
    # Capture per-group invivo metadata so confirm view can read from session
    for i in range(len(invivo_groups)):
        for fname in ['time_unit', 'dose_override', 'animal_species', 'animal_strain', 'route', 'gender']:
            key = f'{fname}_{i}'
            upload_meta[key] = request.POST.get(key, '').strip()
    request.session['upload_meta'] = upload_meta

    pipeline_result = {
        'errors': [],
        'warnings': [],
        'remap_log': [],
        'strand_diffs': [],
        'dedup_report': {'exp_conflicts': [], 'dp_conflicts': []},
    }

    # Phase 1: collect warnings from build_preview (already parsed in smart_upload_view)
    pipeline_result['warnings'].extend(invitro.get('warnings', []))
    pipeline_result['warnings'].extend(smart_preview.get('parse_warnings', []))

    # Phase 2: normalize all compound IDs
    all_cids = list(set(
        list(invitro.get('strand_map', {}).keys())
        + [e['compound_id'] for e in invitro.get('experiments', [])]
        + [g['compound_id'] for grp in invivo_groups for g in grp.get('groups', [])]
    ))
    if all_cids:
        norm_result = normalize_phase(all_cids, project_code)
        pipeline_result['errors'].extend(norm_result.errors)
        pipeline_result['warnings'].extend(norm_result.warnings)
        pipeline_result['remap_log'].extend(norm_result.remap_log)
        request.session['normalize_id_map'] = norm_result.id_map
    else:
        request.session['normalize_id_map'] = {}

    # Phase 3: strand conflict detection
    id_map = request.session.get('normalize_id_map', {})
    upload_strands = []
    for cid, seq_data in invitro.get('strand_map', {}).items():
        resolved = id_map.get(cid, cid)
        if seq_data.get('ss_seq'):
            upload_strands.append({'compound_id': resolved, 'strand_type': 'SS', 'new_seq': seq_data['ss_seq']})
        if seq_data.get('as_seq'):
            upload_strands.append({'compound_id': resolved, 'strand_type': 'AS', 'new_seq': seq_data['as_seq']})
    if upload_strands:
        diffs = diff_strands(upload_strands)
        pipeline_result['strand_diffs'] = [
            {'compound_id': d.compound_id, 'strand_type': d.strand_type,
             'old_seq': d.old_seq, 'new_seq': d.new_seq,
             'diff_positions': d.diff_positions, 'user_choice': None}
            for d in diffs
        ]

    # Phase 4: dedup detection (only if batch_label and assay_name provided)
    batch_label = upload_meta['batch_label']
    assay_name = upload_meta['assay_name']
    if batch_label and assay_name and invitro.get('experiments'):
        upload_records = [
            {
                'compound_id': id_map.get(e['compound_id'], e['compound_id']),
                'batch_label': batch_label,
                'assay_name': assay_name,
                'datapoints': e.get('datapoints', []),
            }
            for e in invitro.get('experiments', [])
        ]
        pipeline_result['dedup_report'] = dedup_phase(upload_records)

    request.session['pipeline_result'] = pipeline_result

    import json as _json
    from app01.models import UploadVocabulary
    qs = Experiment.objects.filter(compound__project=project_code) if project_code else Experiment.objects
    available_batches = list(qs.order_by().values_list('batch_label', flat=True).distinct().order_by('-batch_label'))
    batch_experiments = {}
    for exp in qs.order_by('-batch_label'):
        bl = exp.batch_label
        if not bl:
            continue
        if bl not in batch_experiments:
            batch_experiments[bl] = []
        batch_experiments[bl].append({'exp_type': exp.exp_type, 'label': exp.assay_name or bl, 'pk': exp.pk})

    return render(request, 'smart_upload.html', {
        'preview': smart_preview,
        'upload_meta': upload_meta,
        'pipeline_result': pipeline_result,
        'show_conflict_panels': True,
        'vocab_file_types': list(UploadVocabulary.objects.filter(category='file_type').order_by('-is_builtin', 'label')),
        'vocab_readouts': list(UploadVocabulary.objects.filter(category='invivo_readout').order_by('-is_builtin', 'label')),
        'suggested_batch_label': _generate_batch_label(),
        'available_batches': available_batches,
        'batch_experiments_json': _json.dumps(batch_experiments),
    })


def _cleanup_upload_session(request, smart_preview):
    for det in (smart_preview or {}).get('file_detections', []):
        path = det.get('saved_path', '')
        if path:
            try:
                if default_storage.exists(path):
                    default_storage.delete(path)
            except Exception:
                pass
    request.session.pop('smart_preview', None)
    request.session.pop('pipeline_result', None)
    request.session.pop('upload_meta', None)
    request.session.pop('normalize_id_map', None)


def _build_user_cid_remap(post_data: dict):
    """Parse cid_orig_N / cid_new_N POST pairs into a remap dict.

    Returns (remap, errors).  remap only contains pairs where new != orig.
    """
    errors = []
    remap = {}
    i = 0
    while f'cid_orig_{i}' in post_data:
        orig = post_data[f'cid_orig_{i}']
        new = post_data.get(f'cid_new_{i}', '').strip()
        if not new:
            errors.append(f'化合物 ID 不能为空（原值：{orig}）')
        elif new != orig:
            remap[orig] = new
        i += 1
    return remap, errors


@login_required
def smart_upload_confirm_view(request):
    if not _has_module(request.user, 'upload'):
        messages.error(request, '权限不足，无法访问上传页面')
        return redirect('compound_list')
    if request.method != 'POST':
        return redirect('smart_upload')

    smart_preview = request.session.get('smart_preview')
    if not smart_preview:
        return redirect('smart_upload')

    invitro = smart_preview.get('invitro')
    invivo_groups = smart_preview.get('invivo_groups', [])
    source_files = smart_preview.get('source_files', [])
    project_code = smart_preview.get('project_code', '')

    pipeline_result = request.session.get('pipeline_result', {})
    upload_meta = request.session.get('upload_meta', {})
    _normalize_id_map = request.session.get('normalize_id_map', {})

    batch_label = upload_meta.get('batch_label', '')
    assay_name = upload_meta.get('assay_name', '')
    exp_date = upload_meta.get('exp_date') or None
    target_name_input = upload_meta.get('target_name', '')
    source_batch = upload_meta.get('source_batch', '')
    attach_vitro = upload_meta.get('attach_vitro', False)
    attach_vivo = upload_meta.get('attach_vivo', False)

    is_source_only = smart_preview.get('is_source_only', False)

    user_cid_remap, remap_errors = _build_user_cid_remap(request.POST)
    errors = list(remap_errors)

    def _resolve_cid(raw: str) -> str:
        # Check normalize_id_map first (from Phase 2 of pipeline)
        if raw in _normalize_id_map:
            return _normalize_id_map[raw]
        remapped = user_cid_remap.get(raw, raw)
        return canonicalize_compound_id(remapped, project_code)

    if not target_name_input:
        errors.append('靶点必填,不能为空')

    # Sequences (vitro_seq) only update Strand records — no batch needed.
    # Batch is required only when creating Experiment/DataPoint records.
    has_exp_data = bool(invitro and invitro.get('experiments')) or bool(invivo_groups)

    if has_exp_data and not batch_label:
        errors.append('批次名称为必填项')

    if is_source_only and not source_batch:
        errors.append('请选择要附加到的批次')
    if is_source_only and source_batch and not (attach_vitro or attach_vivo):
        errors.append('请至少选择一种实验类型（体外或体内）')

    # Read conflict choices from POST (only these are in the new confirm form)
    strand_diffs = pipeline_result.get('strand_diffs', [])
    for diff in strand_diffs:
        choice_key = f'strand_choice_{diff["compound_id"]}_{diff["strand_type"]}'
        diff['user_choice'] = request.POST.get(choice_key, 'keep')

    dp_conflicts = pipeline_result.get('dedup_report', {}).get('dp_conflicts', [])
    for dpc in dp_conflicts:
        choice_key = f'dp_choice_{dpc["compound_id"]}_{dpc["batch_label"]}'
        dpc['skip'] = request.POST.get(choice_key, 'skip') == 'skip'

    invivo_meta = []
    for i, group in enumerate(invivo_groups):
        # Body weight files always use 'day'; KD files require user input
        if group.get('readout_code') == 'body_weight':
            time_unit = 'day'
        else:
            time_unit = upload_meta.get(f'time_unit_{i}', '')
        dose_override = upload_meta.get(f'dose_override_{i}', '')
        animal_species = upload_meta.get(f'animal_species_{i}', '')
        animal_strain = upload_meta.get(f'animal_strain_{i}', '')
        route = upload_meta.get(f'route_{i}', '')
        gender = upload_meta.get(f'gender_{i}', '')

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
        # Clean up session now so repeated validation failures don't accumulate stale state.
        _cleanup_upload_session(request, smart_preview)
        import json as _json
        from app01.models import UploadVocabulary
        qs_err = Experiment.objects.filter(compound__project=project_code) if project_code else Experiment.objects
        batch_exp_err = {}
        for exp in qs_err.order_by('-batch_label'):
            bl = exp.batch_label
            if not bl:
                continue
            if bl not in batch_exp_err:
                batch_exp_err[bl] = []
            batch_exp_err[bl].append({'exp_type': exp.exp_type, 'label': exp.assay_name or bl, 'pk': exp.pk})
        return render(request, 'smart_upload.html', {
            'preview': smart_preview,
            'upload_meta': upload_meta,
            'pipeline_result': pipeline_result,
            'show_conflict_panels': True,
            'errors': errors,
            'vocab_file_types': list(UploadVocabulary.objects.filter(category='file_type').order_by('-is_builtin', 'label')),
            'vocab_readouts': list(UploadVocabulary.objects.filter(category='invivo_readout').order_by('-is_builtin', 'label')),
            'suggested_batch_label': _generate_batch_label(),
            'available_batches': list(qs_err.order_by().values_list('batch_label', flat=True).distinct().order_by('-batch_label')),
            'batch_experiments_json': _json.dumps(batch_exp_err),
        })

    n_experiments = 0
    n_strands = 0
    n_invivo = 0
    n_attachments = 0
    invitro_errors = []
    invivo_errors = []
    dup_warnings = []  # filenames skipped because already attached to that experiment

    # Write in-vitro (one atomic transaction)
    vitro_experiments = []  # collected for source-file attachment below
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
                    compound, _ = Compound.objects.get_or_create(
                        compound_id=_resolve_cid(c['compound_id'])
                    )
                    if project_code:
                        compound.project = project_code
                        compound.save(update_fields=['project'])

                id_remap = preview_copy.get('id_format_mismatch', {})
                for cid, seq_data in preview_copy.get('strand_map', {}).items():
                    resolved = id_remap.get(cid, cid)
                    resolved = _resolve_cid(resolved)
                    compound, _ = Compound.objects.get_or_create(compound_id=resolved)
                    for strand_type, seq_key, seq_id_sfx in [
                        ('SS', 'ss_seq', 'SS'), ('AS', 'as_seq', 'AS')
                    ]:
                        new_seq = seq_data.get(seq_key, '')
                        if not new_seq:
                            continue
                        diff_choice = next(
                            (d['user_choice'] for d in strand_diffs
                             if _resolve_cid(d['compound_id']) == resolved and d['strand_type'] == strand_type),
                            None,
                        )
                        existing = Strand.objects.filter(
                            compound=compound, strand_type=strand_type
                        ).first()
                        if existing:
                            if diff_choice == 'overwrite':
                                existing.modify_seq = new_seq
                                existing.save(update_fields=['modify_seq'])
                                n_strands += 1
                            # else keep: do nothing
                        else:
                            Strand.objects.create(
                                compound=compound,
                                strand_type=strand_type,
                                sequence_id=f'{resolved}_{seq_id_sfx}',
                                modify_seq=new_seq,
                            )
                            n_strands += 1

                for exp_data in preview_copy.get('experiments', []):
                    cid = _resolve_cid(exp_data['compound_id'])
                    compound, _ = Compound.objects.get_or_create(compound_id=cid)
                    if project_code:
                        compound.project = project_code
                        compound.save(update_fields=['project'])

                    # Determine version: check if this experiment is in exp_conflicts
                    is_new_version = any(
                        c['compound_id'] == cid
                        and c['batch_label'] == preview_copy['batch_label']
                        and c['assay_name'] == preview_copy['assay_name']
                        for c in pipeline_result.get('dedup_report', {}).get('exp_conflicts', [])
                    )
                    if is_new_version:
                        latest = Experiment.objects.filter(
                            compound=compound,
                            batch_label=preview_copy['batch_label'],
                            assay_name=preview_copy['assay_name'],
                        ).order_by('-version').first()
                        next_version = (latest.version + 1) if latest else 1
                    else:
                        next_version = 1

                    exp = Experiment.objects.create(
                        compound=compound,
                        exp_type=exp_data.get('exp_type', 'in_vitro'),
                        assay_name=preview_copy['assay_name'],
                        batch_label=preview_copy['batch_label'],
                        cell_line=preview_copy.get('cell_line', ''),
                        notes=preview_copy.get('notes', ''),
                        date=exp_date_obj,
                        version=next_version,
                    )
                    vitro_experiments.append(exp)
                    n_experiments += 1

                    # Build skip set from dp_conflicts
                    skip_fps = set()
                    for dpc in dp_conflicts:
                        if (dpc['compound_id'] == cid
                                and dpc['batch_label'] == preview_copy['batch_label']
                                and dpc['assay_name'] == preview_copy['assay_name']
                                and dpc.get('skip', True)):
                            for dp in dpc['datapoints']:
                                skip_fps.add((
                                    round(float(dp.get('x_value') or 0), 4),
                                    dp.get('replicate', ''),
                                    round(float(dp.get('value') or 0), 4) if dp.get('value') is not None else None,
                                    dp.get('readout_type', ''),
                                    bool(dp.get('is_control', False)),
                                ))

                    dp_objs = []
                    for dp in exp_data.get('datapoints', []):
                        fp = (
                            round(float(dp.get('x_value') or 0), 4),
                            dp.get('replicate', ''),
                            round(float(dp.get('value') or 0), 4) if dp.get('value') is not None else None,
                            dp.get('readout_type', ''),
                            bool(dp.get('is_control', False)),
                        )
                        if fp in skip_fps:
                            continue
                        dp_objs.append(DataPoint(
                            experiment=exp,
                            x_value=dp['x_value'],
                            x_type=dp['x_type'],
                            replicate=dp['replicate'],
                            value=dp['value'],
                            readout_type=dp['readout_type'],
                            is_control=dp.get('is_control', False),
                            raw_cp=dp.get('raw_cp'),
                        ))
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

    # Auto-attach all source files to newly created vitro experiments
    if vitro_experiments and source_files and not invitro_errors:
        from django.core.files.base import ContentFile as CF
        for sf in source_files:
            saved_path = sf.get('saved_path', '')
            if not saved_path or not default_storage.exists(saved_path):
                continue
            if ExperimentAttachment.objects.filter(
                    experiment=vitro_experiments[0], label=sf['filename']).exists():
                dup_warnings.append(sf['filename'])
                continue
            try:
                with default_storage.open(saved_path, 'rb') as fh:
                    content = fh.read()
                att = ExperimentAttachment(
                    experiment=vitro_experiments[0], label=sf['filename'])
                att.file.save(sf['filename'], CF(content), save=True)
                n_attachments += 1
            except Exception as e:
                logger.error(f'smart_upload source vitro attachment error: {e}')

    # Source-only upload: attach source files to experiments in the selected batch
    if is_source_only and source_batch and source_files:
        from django.core.files.base import ContentFile as CF
        target_exps = []
        if attach_vitro:
            exp = Experiment.objects.filter(batch_label=source_batch, exp_type='in_vitro').first()
            if exp:
                target_exps.append(exp)
            else:
                invitro_errors.append(f'批次 {source_batch} 无体外实验记录')
        if attach_vivo:
            exp = Experiment.objects.filter(batch_label=source_batch, exp_type='in_vivo').first()
            if exp:
                target_exps.append(exp)
            else:
                invivo_errors.append(f'批次 {source_batch} 无体内实验记录')
        if target_exps:
            for sf in source_files:
                saved_path = sf.get('saved_path', '')
                if not saved_path or not default_storage.exists(saved_path):
                    continue
                try:
                    with default_storage.open(saved_path, 'rb') as fh:
                        content = fh.read()
                    for exp in target_exps:
                        if ExperimentAttachment.objects.filter(
                                experiment=exp, label=sf['filename']).exists():
                            dup_warnings.append(sf['filename'])
                            continue
                        att = ExperimentAttachment(experiment=exp, label=sf['filename'])
                        att.file.save(sf['filename'], CF(content), save=True)
                        n_attachments += 1
                    default_storage.delete(saved_path)
                except Exception as e:
                    logger.error(f'smart_upload source-only attachment error: {e}')

    # Write all in-vivo groups in a single outer transaction (all-or-nothing)
    all_invivo_exps = []
    try:
        with transaction.atomic():                     # outer: all-or-nothing
            for i, group in enumerate(invivo_groups):
                meta = invivo_meta[i]
                batch_label_iv = batch_label
                readout_code = group['readout_code']
                readout_label = group.get('readout_label', readout_code)
                assay_name_iv = f'{readout_label} 时间曲线'
                invivo_exps = []

                try:
                    with transaction.atomic():         # inner: savepoint per group
                        for g in group['groups']:
                            compound, _ = Compound.objects.get_or_create(
                                compound_id=_resolve_cid(g['compound_id'])
                            )
                            if project_code:
                                compound.project = project_code
                                compound.save(update_fields=['project'])
                            dose_info = g.get('dose') or meta['dose_override']
                            schedule = g.get('schedule', '')

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
                                schedule=schedule,
                            )
                            invivo_exps.append(exp)
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

                        # Attach source file to the FIRST experiment only (batch-level)
                        saved_path = group.get('saved_path', '')
                        if invivo_exps and saved_path and default_storage.exists(saved_path):
                            from django.core.files.base import ContentFile as CF
                            with default_storage.open(saved_path, 'rb') as fh:
                                content = fh.read()
                            att = ExperimentAttachment(
                                experiment=invivo_exps[0], label=group['filename'])
                            att.file.save(group['filename'], CF(content), save=True)
                            n_attachments += 1
                            default_storage.delete(saved_path)

                        all_invivo_exps.extend(invivo_exps)
                except Exception as e:
                    logger.error(f'smart_upload_confirm invivo error: {e}')
                    invivo_errors.append(f'文件 {group["filename"]}: {e}')
                    raise                              # trigger outer rollback
    except Exception:
        pass                                           # invivo_errors already populated

    # Auto-attach source files to the first new in-vivo experiment (once, post-loop)
    if all_invivo_exps and source_files and not vitro_experiments and not invivo_errors:
        from django.core.files.base import ContentFile as CF
        for sf in source_files:
            sf_path = sf.get('saved_path', '')
            if not sf_path or not default_storage.exists(sf_path):
                continue
            if ExperimentAttachment.objects.filter(
                    experiment=all_invivo_exps[0], label=sf['filename']).exists():
                dup_warnings.append(sf['filename'])
                continue
            try:
                with default_storage.open(sf_path, 'rb') as fh:
                    sf_content = fh.read()
                att = ExperimentAttachment(
                    experiment=all_invivo_exps[0], label=sf['filename'])
                att.file.save(sf['filename'], CF(sf_content), save=True)
                n_attachments += 1
            except Exception as e:
                logger.error(f'smart_upload source vivo attachment error: {e}')

    # Clean up any remaining temp files.
    # invivo_groups saved_paths are deleted inside their transaction block — skip them.
    # source_files may or may not have been deleted by the attach blocks above, so
    # let the loop below handle them (default_storage.exists check prevents double-delete).
    handled_paths = set()
    for group in invivo_groups:
        if group.get('saved_path'):
            handled_paths.add(group['saved_path'])
    for det in smart_preview.get('file_detections', []):
        path = det.get('saved_path', '')
        if path and path not in handled_paths:
            try:
                if default_storage.exists(path):
                    default_storage.delete(path)
            except Exception:
                pass

    # Update target_name for all compounds touched in this upload (required; validated above)
    if not (invitro_errors or invivo_errors):
        touched_cids = set()
        if invitro:
            for cid in invitro.get('strand_map', {}):
                touched_cids.add(_resolve_cid(cid))
            for exp_data in invitro.get('experiments', []):
                touched_cids.add(_resolve_cid(exp_data['compound_id']))
        for group in invivo_groups:
            for g in group['groups']:
                touched_cids.add(_resolve_cid(g['compound_id']))
        if touched_cids:
            Compound.objects.filter(compound_id__in=touched_cids, target_name='').update(
                target_name=target_name_input
            )

    del request.session['smart_preview']
    request.session.pop('pipeline_result', None)
    request.session.pop('upload_meta', None)
    request.session.pop('normalize_id_map', None)

    parts = []
    if n_experiments:
        parts.append(f'{n_experiments} 条体外实验')
    if n_strands:
        parts.append(f'{n_strands} 条序列')
    if n_invivo:
        parts.append(f'{n_invivo} 条体内实验')
    if n_attachments:
        parts.append(f'{n_attachments} 个附件')

    all_err = invitro_errors + invivo_errors
    if all_err:
        messages.warning(request, f'部分写入失败：{"；".join(all_err)}')
    else:
        messages.success(request, f'数据已上传：{", ".join(parts) or "0 条"}')

    if dup_warnings:
        unique_dups = sorted(set(dup_warnings))
        messages.warning(request, f'以下文件已存在于目标实验，跳过重复上传：{"、".join(unique_dups)}')

    return redirect('smart_upload')


@login_required
def attachment_download(request, pk):
    att = get_object_or_404(ExperimentAttachment, pk=pk)
    if not att.file:
        raise Http404
    filename = os.path.basename(att.file.name)
    return FileResponse(att.file.open('rb'), as_attachment=True, filename=filename)

@login_required
def attachment_preview(request, pk):
    """Return first 50 rows of a CSV attachment as JSON for inline preview.

    When the CSV has many duplicate column headers (multi-animal body-weight
    format), automatically aggregates same-named columns into their mean so the
    preview is readable without horizontal scrolling.
    """
    import itertools
    import csv
    from io import StringIO
    att = get_object_or_404(ExperimentAttachment, pk=pk)
    if not att.file:
        return JsonResponse({'headers': [], 'rows': []}, status=404)
    try:
        with att.file.open('rb') as f:
            text = f.read().decode('utf-8', errors='replace')
        reader = csv.reader(StringIO(text))
        rows = list(itertools.islice(reader, 51))
        if not rows:
            return JsonResponse({'headers': [], 'rows': []})

        raw_headers = [h.lstrip('﻿').strip() for h in rows[0]]
        data_rows = rows[1:]

        # Detect multi-animal format: many columns with duplicate names
        value_headers = [h for h in raw_headers[1:] if h]
        unique_names = set(value_headers)
        if len(raw_headers) > 10 and unique_names and len(unique_names) < len(value_headers) * 0.7:
            # Group column indices by header name (preserving insertion order)
            groups = {}
            for i, h in enumerate(raw_headers):
                if i == 0:
                    continue
                name = h or f'Col{i}'
                groups.setdefault(name, []).append(i)

            agg_headers = [raw_headers[0] or 'Day'] + list(groups.keys())
            agg_rows = []
            for row in data_rows:
                if not row or not str(row[0]).strip():
                    continue
                agg_row = [row[0]]
                for indices in groups.values():
                    vals = []
                    for idx in indices:
                        if idx < len(row):
                            try:
                                vals.append(float(row[idx].rstrip('*').strip()))
                            except (ValueError, TypeError):
                                pass
                    agg_row.append(f'{sum(vals)/len(vals):.2f}' if vals else '—')
                agg_rows.append(agg_row)

            note = f'已按组合并均值（{len(groups)} 组 · 原 {len(value_headers)} 列动物数据）'
            return JsonResponse({'headers': agg_headers, 'rows': agg_rows, 'note': note})

        return JsonResponse({'headers': raw_headers, 'rows': data_rows})
    except Exception:
        return JsonResponse({'headers': [], 'rows': []})


@login_required
def user_management_view(request):
    if not (request.user.is_superuser or request.user.user_type == 'superadmin'):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('此页面仅 superadmin 可访问')
    pending_requests = ProjectAccessRequest.objects.filter(status='pending').select_related('user')
    all_users = LmsUser.objects.all().order_by('date_joined')
    audit_logs = AuditLog.objects.select_related('actor', 'target_user')[:30]
    return render(request, 'user_management.html', {
        'pending_requests': pending_requests,
        'all_users': all_users,
        'audit_logs': audit_logs,
    })


@login_required
def user_edit_view(request, user_id):
    if not (request.user.is_superuser or request.user.user_type == 'superadmin'):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('此操作仅 superadmin 可执行')
    target = get_object_or_404(LmsUser, id=user_id)
    if request.method == 'POST':
        old_type = target.user_type
        old_mods = target.module_permissions
        old_proj = target.permissions_project
        new_type = request.POST.get('user_type', target.user_type)
        new_mods = ','.join(m.strip() for m in request.POST.getlist('module_permissions') if m.strip())
        new_proj = request.POST.get('permissions_project', '').strip()
        target.user_type = new_type
        target.module_permissions = new_mods
        target.permissions_project = new_proj
        target.save()
        import json as _json_mod
        AuditLog.objects.create(
            actor=request.user,
            action='user_role_changed',
            target_user=target,
            detail=_json_mod.dumps({
                'before': {'user_type': old_type, 'module_permissions': old_mods, 'permissions_project': old_proj},
                'after':  {'user_type': new_type, 'module_permissions': new_mods, 'permissions_project': new_proj},
            }),
        )
        messages.success(request, f'用户 {target.username} 已更新')
        return redirect('user_management')
    return render(request, 'user_edit.html', {'target': target})


@login_required
def user_delete_view(request, user_id):
    if not (request.user.is_superuser or request.user.user_type == 'superadmin'):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('此操作仅 superadmin 可执行')
    if request.method != 'POST':
        return redirect('user_management')
    target = get_object_or_404(LmsUser, id=user_id)
    import json as _json_mod
    username = target.username
    AuditLog.objects.create(
        actor=request.user,
        action='user_deleted',
        detail=_json_mod.dumps({'username': username}),
    )
    target.delete()
    messages.success(request, f'用户 {username} 已删除')
    return redirect('user_management')


@login_required
def project_request_approve(request, req_id):
    if not (request.user.is_superuser or request.user.user_type == 'superadmin'):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('此操作仅 superadmin 可执行')
    if request.method != 'POST':
        return redirect('user_management')
    import json as _json_mod
    import datetime
    req = get_object_or_404(ProjectAccessRequest, id=req_id)
    req.status = 'approved'
    req.reviewed_by = request.user
    req.reviewed_at = datetime.datetime.now()
    req.save()
    user = req.user
    existing = [p.strip() for p in (user.permissions_project or '').split(',') if p.strip()]
    if req.project_code not in existing:
        existing.append(req.project_code)
    user.permissions_project = ','.join(existing)
    user.save()
    AuditLog.objects.create(
        actor=request.user,
        action='project_approved',
        target_user=user,
        detail=_json_mod.dumps({'project': req.project_code}),
    )
    messages.success(request, f'已批准 {user.username} 访问 {req.project_code}')
    return redirect('user_management')


@login_required
def project_request_reject(request, req_id):
    if not (request.user.is_superuser or request.user.user_type == 'superadmin'):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('此操作仅 superadmin 可执行')
    if request.method != 'POST':
        return redirect('user_management')
    import json as _json_mod
    import datetime
    req = get_object_or_404(ProjectAccessRequest, id=req_id)
    req.status = 'rejected'
    req.reviewed_by = request.user
    req.reviewed_at = datetime.datetime.now()
    req.save()
    AuditLog.objects.create(
        actor=request.user,
        action='project_rejected',
        target_user=req.user,
        detail=_json_mod.dumps({'project': req.project_code}),
    )
    messages.success(request, f'已拒绝 {req.user.username} 访问 {req.project_code}')
    return redirect('user_management')
