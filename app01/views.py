from collections import defaultdict
import hashlib

from django.http import  HttpResponse, Http404, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login, logout as auth_logout, get_user_model, update_session_auth_hash
from django.contrib.auth.hashers import make_password, check_password   
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
import pandas as pd
from django.contrib import messages
from datetime import datetime
from django.db.models import Q
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
import os, csv
from django.utils.timezone import now
from app01 import models
from .models import *
LmsUser = get_user_model()

import re, json
import urllib.parse
import logging
from django.utils import timezone
from io import StringIO
from django.conf import settings


def _module_list_url(base: str, page, q: str) -> str:
    """构建带 page/q 参数的模块列表页 redirect URL。"""
    qs = f'?page={page}'
    if q:
        qs += f'&q={urllib.parse.quote(str(q))}'
    return f'{base}{qs}'


# 生成颜色映射规则（接受预加载的 modules 避免循环内重复查询）
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



_SEP_TOKEN = {
    'char': '|', 'type': 'SEP', 'count': '',
    'is_combo': False, 'delivery_label': None, 'delivery_color': None,
}


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


# 用户登录视图
def login_view(request):
    if request.method == 'POST' and request.POST:
        username = request.POST.get("username")
        password = request.POST.get("password")

        # 验证用户
      #  print(f"Submitted username: {username}, password: {password}")
        user = authenticate(request, username=username, password=password)

        if user:
            # 使用 login() 登录用户
            login(request, user)

            # 获取用户的跳转 URL
            return redirect('/seq_list/')  # 登录成功后跳转到书籍列表页面
        else:
            # 登录失败，返回错误提示
            messages.error(request, '用户名或密码错误！')
            return redirect('/login/')

    # 默认返回登录页面
    return render(request, "login.html")

# 用户注册
def register_view(request):
    if request.method == "POST":
        data = request.POST
        username = data.get("username")
        email = data.get("email")
        password = data.get("password")

        # 检查用户名和邮箱是否已存在
        if LmsUser.objects.filter(username=username).exists():
            messages.error(request, '用户名已存在！')
            return redirect('/register/')

        if LmsUser.objects.filter(email=email).exists():
            messages.error(request, '邮箱已注册！')
            return redirect('/register/')

        # 自注册用户固定为 'user' 角色，不接受前端传入的 user_type
        LmsUser.objects.create(
            username=username,
            email=email,
            user_type='user',           # always 'user' on self-registration
            permissions_project='',     # starts with no projects
            password=setPassword(password)  # 保存加密后的密码
        )

        return redirect('/login/')  # 注册成功后跳转到登录页面

    return render(request, "register.html")

# 项目人员视图
@login_required
def author_list(request):
    if not _is_superadmin(request.user):
        messages.error(request, '您没有权限访问用户管理页面。')
        return redirect('seq_list')

    users = LmsUser.objects.all().order_by('username')
    pending_project_requests = ProjectAccessRequest.objects.filter(
        status='pending'
    ).select_related('user')
    pending_module_requests = ModulePermissionRequest.objects.filter(
        status='pending'
    ).select_related('user')

    return render(request, 'auth_list.html', {
        'user_list': users,
        'pending_project_requests': pending_project_requests,
        'pending_module_requests': pending_module_requests,
    })

# 添加用户
@login_required
def add_author(request):
    if not _is_superadmin(request.user):
        messages.error(request, '您没有权限添加用户。')
        return redirect('author_list')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        user_type = request.POST.get('user_type', 'user')
        raw_projects = request.POST.get('permissions_project', '')
        permissions_project = ','.join(
            p.strip() for p in raw_projects.split(',') if p.strip()
        )
        raw_module_perms = request.POST.getlist('module_permissions')
        module_permissions = ','.join(raw_module_perms)

        if LmsUser.objects.filter(username=username).exists():
            messages.error(request, '用户名已存在！')
            return redirect('add_author')

        default_password = 'Bt123456'
        LmsUser.objects.create(
            username=username,
            email=email,
            user_type=user_type,
            permissions_project=permissions_project,
            module_permissions=module_permissions,
            password=setPassword(default_password),
        )
        messages.success(request, f'用户 {username} 已创建，默认密码 Bt123456')
        return redirect('author_list')

    # 获取项目列表（从 DeliveryProject 取，含共享项目）
    project_list = list(
        DeliveryProject.objects
        .exclude(project_code__isnull=True).exclude(project_code='')
        .values_list('project_code', flat=True)
        .distinct().order_by('project_code')
    )

    return render(request, 'author_add.html', {'project_choices': project_list})

# 删除用户
@login_required
@require_POST
def drop_author(request):
    if not _is_superadmin(request.user):
        messages.error(request, '您没有权限删除用户信息！')
        return redirect('author_list')

    drop_id = request.POST.get('id')

    # 已确认删除（前端通过 Modal 确认后发起请求）
    try:
        drop_obj = LmsUser.objects.get(id=drop_id)
        if str(request.user.id) == drop_id:
            messages.error(request, '不能删除当前登录的管理员账户！')
            return redirect('/author_list/')
        # 不能删除超级管理员账号
        if drop_obj.user_type == 'superadmin' or drop_obj.is_superuser:
            messages.error(request, '不能删除超级管理员账号！')
            return redirect('author_list')
        # 删除用户之前记录日志
        # 获取当前时间
        delete_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 设置日志文件路径
        log_directory = 'bms/logs'
        if not os.path.exists(log_directory):
            os.makedirs(log_directory)

        log_filename = 'author_delete.log'
        log_file_path = os.path.join(log_directory, log_filename)

        # 设置日志配置
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.FileHandler(log_file_path, encoding='utf-8')]
        )
        logger = logging.getLogger('author_delete')

        # 构建日志信息
        log_message = f"用户 {request.user.username} 于 {delete_datetime} 删除了用户 {drop_obj.username} (ID: {drop_obj.id}) \n"
        log_message += "========================================================================\n"

        # 记录日志
        logger.info(log_message)

        # 删除用户
        drop_obj.delete()

        messages.success(request, '人员已被成功删除！')
        return redirect('/author_list/')
    except LmsUser.DoesNotExist:
        messages.error(request, '用户不存在或已被删除')
        return redirect('/author_list/')

@require_POST
@login_required
def logout_view(request):
    """POST-only logout — clears session and redirects to login."""
    auth_logout(request)
    return redirect('login')


@login_required
def change_password(request):
    if request.method == "POST":
        old_password = request.POST.get("old_password")
        new_password1 = request.POST.get("new_password1")
        new_password2 = request.POST.get("new_password2")

        user = request.user

        if not user.check_password(old_password):
            return render(request, 'change_password.html', {'error': '原密码错误'})

        if new_password1 != new_password2:
            return render(request, 'change_password.html', {'error': '两次输入的新密码不一致'})

        if len(new_password1) < 6:
            return render(request, 'change_password.html', {'error': '新密码长度不能少于6位'})

        # 设置新密码
        user.set_password(new_password1)
        user.save()

        # 更新 session，避免修改密码后被登出
        update_session_auth_hash(request, user)

        messages.success(request, '密码修改成功。')
        if _is_superadmin(request.user):
            return redirect('seq_list')
        return redirect('user_profile')
    
    return render(request, 'change_password.html')

# 编辑用户
@login_required
def edit_author(request):
    # 非超级管理员禁止访问
    if not _is_superadmin(request.user):
        messages.error(request, '您没有权限编辑用户信息！')
        return redirect('author_list')

    # 获取用户对象
    edit_id = request.GET.get('id')
    try:
        edit_obj = LmsUser.objects.get(id=edit_id)
    except LmsUser.DoesNotExist:
        raise Http404("Author not found")

    if request.method == 'POST':
        # 获取表单提交的数据
        new_author_name = request.POST.get('edit_username')
        new_author_email = request.POST.get('edit_email')
        new_author_user_type = request.POST.get('edit_user_type')
        

        # 获取复选框选中的项目权限
        raw_premissions_projects = request.POST.get('edit_permissions_project')

        if not new_author_user_type:
            return render(request, 'edit_author.html', {
                'edit_obj': edit_obj,
                'error_msg': '请选择用户类型'
        })

        # 将选中的项目权限转换为逗号分隔的字符串
        new_author_permissions_project_str = ','.join([proj.strip() for proj in raw_premissions_projects.split(',') if proj.strip()])

        # 记录旧的值
        old_author_name = edit_obj.username
        old_author_email = edit_obj.email
        old_author_user_type = edit_obj.user_type
        old_author_permissions_project_str = edit_obj.permissions_project

        # 更新作者对象
        edit_obj.username = new_author_name
        edit_obj.email = new_author_email
        edit_obj.user_type = new_author_user_type
        edit_obj.permissions_project = new_author_permissions_project_str  # 存储逗号分隔的字符串
        raw_module_perms = request.POST.getlist('module_permissions')
        edit_obj.module_permissions = ','.join(raw_module_perms)
        edit_obj.save()

        # 获取当前时间
        edit_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 设置日志文件路径
        log_directory = 'bms/logs'
        if not os.path.exists(log_directory):
            os.makedirs(log_directory)

        log_filename = 'author_edit.log'
        log_file_path = os.path.join(log_directory, log_filename)

        # 设置日志配置
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.FileHandler(log_file_path, encoding='utf-8')]
        )
        logger = logging.getLogger('author_edit')

        # 构建日志信息
        log_message = f"用户 {request.user.username} 于 {edit_datetime}编辑了{old_author_name}的信息，更改信息为: \n"

        changes = []

        # 只记录有变化的字段
        if new_author_name != old_author_name:
            changes.append(f"用户名: {old_author_name} -> {new_author_name}")
        if new_author_email != old_author_email:
            changes.append(f"电子邮件: {old_author_email} -> {new_author_email}")
        if new_author_user_type != old_author_user_type:
            changes.append(f"用户类型: {old_author_user_type} -> {new_author_user_type}")
        if new_author_permissions_project_str != old_author_permissions_project_str:
            changes.append(f"项目权限: {old_author_permissions_project_str} -> {new_author_permissions_project_str}")

        # 如果有变化，记录日志
        if changes:
            log_message += "\n".join(changes)
            log_message += "\n========================================================================\n"
            logger.info(log_message)

        # 跳转到作者列表页面
        return redirect('/author_list/')

    return render(request, 'auth_edit.html', {
        'user': edit_obj,
        'module_perms_list': [m for m in (edit_obj.module_permissions or '').split(',') if m],
    })

@login_required
def drop_book(request):
    # 始终显示需要OA审批的提示信息
    messages.error(request, '您没有权限删除序列信息，如需删除，请走OA审批！')
    return redirect('/seq_list/')

# 编辑序列
@login_required
def edit_seq(request):

    seq_id = request.GET.get('id')
#    print(seq_id)
    seq_Strand_MWs = request.GET.get('strand_MWs')
   # seq_id_query = seq_id.split('_')[1]  # 获取 rm_code
   #print(seq_id_query)

   # 根据 seq_id 查询 Delivery 对象
    delivery = get_object_or_404(get_permitted_delivery_qs(request.user), Q(id=seq_id) & Q(Strand_MWs=seq_Strand_MWs))

    # 提取 delivery 对象中的 sequence_id
    delivery_sequence_id = delivery.sequence_id

    # 使用 delivery 中的 sequence_id 查询 SeqInfo 对象
    seqinfo = get_object_or_404(SeqInfo, sequence_id=delivery_sequence_id)

    if request.method == 'POST':
        if not user_can_edit_delivery(request.user, delivery):
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("权限不足：你只有部分项目权限，无法编辑跨项目样品。")
        # 获取表单数据
        edit_project = request.POST.get('edit_project')
        edit_delivery5 = request.POST.get('edit_delivery5')
    #    edit_seq = request.POST.get('edit_seq')
        edit_delivery3 = request.POST.get('edit_delivery3')
    #    edit_transcript = request.POST.get('edit_Transcript')
        edit_target = request.POST.get('edit_Target')
    #    edit_position = request.POST.get('edit_position')
        edit_strand_mws = request.POST.get('edit_Strand_MWs')
        edit_parents = request.POST.get('edit_parents')
        edit_remark = request.POST.get('edit_Remark')
        edit_date = request.POST.get('edit_date')
        # 获取当前时间（如果没有提供更新日期，则使用当前时间）
        if not edit_date:
            edit_date = datetime.now().strftime('%Y-%m-%dT%H:%M')
        # 将前端传递的字符串日期转换为 naive datetime
        naive_datetime = datetime.strptime(edit_date, "%Y-%m-%dT%H:%M")
        # 将 naive datetime 转换为 aware datetime（带时区）
        #new_datetime = timezone.make_aware(naive_datetime)
        new_datetime = naive_datetime
    
    # **检查是否有字段修改**
        changes = []
        if delivery and delivery.project != edit_project:
            changes.append(f"Project: {delivery.project} → {edit_project}")
            delivery.project = edit_project
        if delivery and delivery.delivery5 != edit_delivery5:
            changes.append(f"5' Delivery: {delivery.delivery5} → {edit_delivery5}")
            delivery.delivery5 = edit_delivery5
       # if seqinfo.seq != edit_seq:
        #    changes.append(f"Sequence: {seqinfo.seq} → {edit_seq}")
         #   seqinfo.seq = edit_seq 
        if delivery and delivery.delivery3 != edit_delivery3:
            changes.append(f"3' Delivery: {delivery.delivery3} → {edit_delivery3}")
            delivery.delivery3 = edit_delivery3
        if delivery and delivery.Target != edit_target:
            changes.append(f"Target: {delivery.Target} → {edit_target}")
            delivery.Target = edit_target   
        if delivery and delivery.Strand_MWs != edit_strand_mws:
            changes.append(f"Strand MWs: {delivery.Strand_MWs} → {edit_strand_mws}")
            delivery.Strand_MWs = edit_strand_mws
        if delivery and delivery.parents != edit_parents:
            changes.append(f"Parents: {delivery.parents} → {edit_parents}")
            delivery.parents = edit_parents
        if delivery.Remark != edit_remark:
            changes.append(f"Remarks: {delivery.Remark} → {edit_remark}")
            delivery.Remark = edit_remark

        # **如果有变化，则更新数据库**
        if changes:
            # 更新 SeqInfo 对象 和 delivery 对象
        #    seqinfo.created_at = new_datetime  # 更新时间
            delivery.created_at = new_datetime  # 更新时
            delivery.save()
      #      seqinfo.save()

             # 记录修改日志
            log_directory = 'bms/logs'  # 日志文件夹
            if not os.path.exists(log_directory):
                os.makedirs(log_directory)
            log_filename = f"edit_seqs.log"
            log_file = os.path.join(log_directory, log_filename)
            
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(log_file),
                    logging.StreamHandler()
                ]
            )

            logger = logging.getLogger('edit_seqs')

            log_message = f"用户 {request.user.username} 在 {new_datetime} 编辑了项目 {delivery.project}中ID为 {delivery.delivery_id} 的序列 ，修改内容为: "
            log_details = []

            for change in changes:
                log_details.append(f"{change}")

            if log_details:
                log_message += "\n" + "\n".join(log_details) + "\n========================================================================\n"
                logger.info(log_message)

            messages.success(request, "序列信息已成功更新！")
            # return redirect('seq_list')  # 返回列表页

        else:
            # **如果没有变化，提示用户**
            messages.info(request, "您未做任何修改。")
            # return redirect('seq_list')  # 返回列表页
            
        # Safely handle `next` which may be URL-encoded. Decode and merge query params
        raw_next = request.POST.get("next") or request.GET.get("next") or "/seq_list/"
        try:
            # If double-encoded, unquote once
            decoded_next = urllib.parse.unquote(raw_next)
        except Exception:
            decoded_next = raw_next

        try:
            parts = urllib.parse.urlsplit(decoded_next)
            # parse_qsl returns list of (k,v) preserving duplicates
            qsl = urllib.parse.parse_qsl(parts.query or '', keep_blank_values=True)
        except Exception:
            parts = urllib.parse.urlsplit("/seq_list/")
            qsl = []

        # Remove any existing dt_page or highlight params from qsl
        filtered = [(k, v) for (k, v) in qsl if k not in ('dt_page', 'highlight_duplex', 'highlight_delivery', 'highlight_seq_type')]

        dt_page = request.POST.get("dt_page") or request.GET.get("dt_page")
        if dt_page:
            filtered.append(('dt_page', str(dt_page)))

        # 如果本次有修改，附加高亮参数（duplex_id 与 delivery DB id）
        if changes:
            try:
                highlight_duplex = getattr(delivery, 'duplex_id', None)
                highlight_delivery = getattr(delivery, 'id', None)
                highlight_seq_type = getattr(delivery, 'seq_type', None)
                if highlight_duplex:
                    filtered.append(('highlight_duplex', str(highlight_duplex)))
                if highlight_delivery:
                    filtered.append(('highlight_delivery', str(highlight_delivery)))
                if highlight_seq_type:
                    filtered.append(('highlight_seq_type', str(highlight_seq_type)))
            except Exception:
                pass

        # Rebuild URL preserving path and fragment. For relative paths this will produce '/path?query'
        try:
            new_query = urllib.parse.urlencode(filtered, doseq=True)
            next_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))
            # If next_url is empty path (shouldn't), fallback
            if not parts.path:
                next_url = '/seq_list/' + ('?' + new_query if new_query else '')
        except Exception:
            next_url = decoded_next

        return redirect(next_url)
        
    context = {
        'seqinfo': seqinfo,
        'delivery': delivery,
        'delivery_projects': list(delivery.project_links.values_list('project_code', flat=True)),
        'can_edit': user_can_edit_delivery(request.user, delivery),
    }

    return render(request, 'seq_edit.html', context)

# 密码加密
def setPassword(password):
    """
    加密密码,算法单次md5
    :param apssword: 传入的密码
    :return: 加密后的密码
    """
    return make_password(password)

# 定义 clean_value，防止脏数据，比如 NaN/null，并处理 int 转换
def clean_value(value):
    if pd.isna(value) or value is None:
        return ''
    if isinstance(value, int):  # 如果是整数，转换为字符串
        return str(value)
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()

@login_required
def register_seq(request):
    if request.method == 'POST':
        uploaded_file = request.FILES.get('file')

        if not uploaded_file:
            messages.error(request, "未选择文件！")
            return render(request, 'register_seq.html')

        if not uploaded_file.name.endswith('.csv'):
            messages.error(request, "请上传 CSV 文件！")
            return render(request, 'register_seq.html')

        try:
            # Read the file, decode bytes to string if necessary
            file_content = uploaded_file.read().decode('utf-8-sig', errors='replace')  # Decode the file content

            # Automatically detect the delimiter (space or tab or comma)

            df = pd.read_csv(StringIO(file_content), sep=None, engine='python', encoding='utf-8')  # Auto-detect delimiter
            df = df.fillna('')  # Handle empty values by replacing them with an empty string
        #    print(df.columns.to_list())  # Print the columns to check

            # 检查必需列
            required_columns = ['SS', 'AS', 'Transcript', 'Position', 'Remarks']
          #  print(df.columns.to_list())  # 打印列名
            if not all(col in df.columns for col in required_columns):
                messages.error(request, f"文件格式错误，必须包含列: {', '.join(required_columns)}")
                return render(request, 'register_seq.html')

            # 时间戳
            created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            username = request.user.username
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")

            # 确保日志目录存在
            log_dir = os.path.join(settings.BASE_DIR, 'bms', 'logs')
            os.makedirs(log_dir, exist_ok=True)
            log_filename = os.path.join(log_dir, f"{username}_register_log_{timestamp}.txt")

            duplicate_meg = []
            register_meg = []
            Relation_meg = []

            with open(log_filename, "a", encoding="utf-8") as log_file:

                for _, row in df.iterrows():
                    # 清洗每一行
                    cleaned_row = {col: clean_value(row[col]) for col in required_columns}
                    SS = cleaned_row['SS']
                    AS = cleaned_row['AS']
                    duplex = f"{AS}, {SS}"
                    Transcript = cleaned_row['Transcript']
                    Pos = cleaned_row['Position']
                    project = cleaned_row.get('Project', '')  # 获取项目列
              #      Parents = cleaned_row['Parents']
              #      Target = cleaned_row['Target']
                    Remarks = cleaned_row['Remarks']

                    # 创建 Duplex
                    duplex_obj, duplex_created = Sequence.objects.get_or_create(
                        seq=duplex, seq_type='duplex', defaults={'created_at': created_at}
                    )
                    if duplex_created:
                        register_meg.append(f"Duplex: {duplex}")
                    else:
                        duplicate_meg.append(f"Duplex: {duplex}")

                    # 创建 AS
                    as_obj, as_created = Sequence.objects.get_or_create(
                        seq=AS, seq_type='AS', defaults={'created_at': created_at}
                    )
                    if as_created:
                        register_meg.append(f"AS: {AS}")
                    else:
                        duplicate_meg.append(f"AS: {AS}")

                    # 创建 SS
                    ss_obj, ss_created = Sequence.objects.get_or_create(
                        seq=SS, seq_type='SS', defaults={'created_at': created_at}
                    )
                    if ss_created:
                        register_meg.append(f"SS: {SS}")
                    else:
                        duplicate_meg.append(f"SS: {SS}")

                    # 建立 Duplex 关系
                    rel_exists = DuplexRelationship.objects.filter(
                        as_seq=as_obj, ss_seq=ss_obj, duplex_seq=duplex_obj
                    ).exists()
                    if not rel_exists:
                        DuplexRelationship.objects.create(as_seq=as_obj, ss_seq=ss_obj, duplex_seq=duplex_obj)
                        Relation_meg.append(f"关系建立: {AS} <-> {SS} <-> {duplex}")
                    else:
                        Relation_meg.append(f"关系已存在: {AS} <-> {SS} <-> {duplex}")

                    # 更新或创建 SS 对应的 SeqInfo
                    seqinfo_SS = SeqInfo.objects.filter(sequence=ss_obj).first()
                    if seqinfo_SS:
                        existing_fields = {
                            "Transcript": set(seqinfo_SS.Transcript.split(', ')) if seqinfo_SS.Transcript else set(),
                    #       "Target": set(seqinfo_SS.Target.split(', ')) if seqinfo_SS.Target else set(),
                            "Pos": set(seqinfo_SS.Pos.split(', ')) if seqinfo_SS.Pos else set(),
                    #         "Parents": set(seqinfo_SS.parents.split(', ')) if seqinfo_SS.parents else set(),
                            "Remarks": set(seqinfo_SS.Remark.split(', ')) if seqinfo_SS.Remark else set()
                        }
                        new_fields = {
                            "Transcript": set(Transcript.split(';')) if Transcript else set(),
                 #            "Target": set(Target.split(';')) if Target else set(),
                            "Pos": set(Pos.split(';')) if Pos else set(),
                 #           "Parents": set(Parents.split(';')) if Parents else set(),
                            "Remarks": set(Remarks.split(';')) if Remarks else set()
                        }
                        for field in new_fields:
                            existing_fields[field] |= new_fields[field]
                            setattr(seqinfo_SS, field, ", ".join(existing_fields[field]))
                        seqinfo_SS.sequence = ss_obj
                        seqinfo_SS.save()
                    else:
                        SeqInfo.objects.create(
                            sequence=ss_obj,
                            Transcript=Transcript,
                            Pos=Pos,
                            Remark=Remarks,
                            created_at=created_at
                        )

                    # 更新或创建 AS 对应的 SeqInfo
                    seqinfo_AS = SeqInfo.objects.filter(sequence=as_obj).first()
                    if seqinfo_AS:
                        existing_fields = {
                            "Transcript": set(seqinfo_AS.Transcript.split(', ')) if seqinfo_AS.Transcript else set(),
                 #           "Target": set(seqinfo_AS.Target.split(', ')) if seqinfo_AS.Target else set(),
                            "Pos": set(seqinfo_AS.Pos.split(', ')) if seqinfo_AS.Pos else set(),
                 #           "Parents": set(seqinfo_AS.parents.split(', ')) if seqinfo_AS.parents else set(),
                            "Remarks": set(seqinfo_AS.Remark.split(', ')) if seqinfo_AS.Remark else set()
                        }
                        new_fields = {
                            "Transcript": set(Transcript.split(';')) if Transcript else set(),
                  #          "Target": set(Target.split(';')) if Target else set(),
                            "Pos": set(Pos.split(';')) if Pos else set(),
                    #        "Parents": set(Parents.split(';')) if Parents else set(),
                            "Remarks": set(Remarks.split(';')) if Remarks else set()
                        }
                        for field in new_fields:
                            existing_fields[field] |= new_fields[field]
                            setattr(seqinfo_AS, field, ", ".join(existing_fields[field]))
                        seqinfo_AS.sequence = as_obj
                        seqinfo_AS.save()
                    else:
                        SeqInfo.objects.create(
                            sequence=as_obj,
                            Transcript=Transcript,
                            Pos=Pos,
                            Remark=Remarks,
                            created_at=created_at
                        )

                # 反馈信息
                if register_meg or duplicate_meg:
                    register_seqs = [seq.split(": ")[1] for seq in register_meg if "Duplex" not in seq]
                    duplicate_seqs = [seq.split(": ")[1] for seq in duplicate_meg if "Duplex" not in seq]
                    warning_meg = ""

                    if register_seqs:
                        num_register = len(register_seqs)
                        warning_meg += f"\n {num_register} 条序列成功注册！\n"
                    else:
                        warning_meg += f"\n 无新的序列注册！\n"

                    if duplicate_seqs:
                        num_duplicates = len(duplicate_seqs)
                        warning_meg += f"\n {num_duplicates} 条序列已存在，未重复注册！\n" + "\n"

                    # 显示合并的警告消息
                    if warning_meg:
                        messages.warning(request, warning_meg)

                    with open(log_filename, "a") as log_file:
                        log_file.write(f"\n >>>Registered Sequences:\n\n")
                        for seq in register_meg:
                            if "Duplex" not in seq:
                                log_file.write(f"  {seq}\n")
                        log_file.write(f"========================================================================\n")

                        log_file.write(f"\n >>>Duplicate Sequences:\n\n")
                        for seq in duplicate_meg:
                            if "Duplex" not in seq:
                                log_file.write(f"  {seq}\n")
                        log_file.write(f"========================================================================\n")

                if Relation_meg:
                    with open(log_filename, "a") as log_file:
                        log_file.write(f"\n >>>Created Relationships:\n\n")
                        for relation in Relation_meg:
                            log_file.write(f"  {relation}\n")
                        log_file.write(f"========================================================================\n")

                # 成功消息
                messages.success(request, f"注册完成！成功: {len(register_meg)} 条（含duplex), 重复: {len(duplicate_meg)} 条")
                return redirect('register_seq')

        except Exception as e:
            messages.error(request, f"文件处理失败：{e}")
            return render(request, 'register_seq.html')

    return render(request, 'register_seq.html')


def build_seq_search_regex(val: str) -> str:
    """
    将修饰序列搜索词转为 MySQL REGEXP 正则表达式。
    token 之间插入 [os-]* 以匹配任意骨架连接符（o/s/-）。
    例如：'CmAmUm' → 'Cm[os-]*Am[os-]*Um'
         可匹配 modify_seq 中的 'CmsAmUm' 和 linker_seq 中的 'CmsAmoUm'
    """
    val = (val or "").strip()
    if not val:
        return ""
    seq_modules = sorted(SeqModule.objects.all(), key=lambda m: len(m.keyword), reverse=True)
    sm_pattern = "|".join(re.escape(m.keyword) for m in seq_modules if m.keyword)
    left_extras = r'INVAB|I|ss|s|o|[ACGUT]'
    token_re = re.compile(rf"(?:{sm_pattern}|{left_extras})", re.IGNORECASE)
    tokens = []
    i = 0
    while i < len(val):
        m = token_re.match(val, i)
        if m:
            tokens.append(re.escape(m.group(0)))
            i += len(m.group(0))
        else:
            tokens.append(re.escape(val[i]))
            i += 1
    return r'[os-]*'.join(tokens)


# 遍历modify_seq, 遇见 "m" 或 "f" 在后面添加 "o"，并处理 "(EVP)A", "(EVP)U", "(EVP)C", "(EVP)G", "(EVP)T"

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
    linker_keywords = [
        mod.keyword for mod in SeqModule.objects.filter(linker_connector='-')
        if mod.keyword
    ]
    patterns = []
    if linker_keywords:
        kw_pat = '|'.join(re.escape(k) for k in sorted(linker_keywords, key=len, reverse=True))
        # Anchor first and last tokens to SeqModule linker keywords; middle tokens (0+) can be any alphanumeric token
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


# 上传递送信息 （分块函数)
def parse_uploaded_csv(request):
    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        raise ValueError("未选择文件！")
    if not uploaded_file.name.endswith('.csv'):
        raise ValueError("请上传 CSV 文件！")

    file_content = uploaded_file.read().decode('utf-8-sig', errors='replace')
    df = pd.read_csv(StringIO(file_content), sep=None, engine='python', encoding='utf-8')
    df = df.fillna('')
    df['__row_id'] = df.index
    df['__original_line'] = df.index + 2  # CSV 原始行号（包含表头）

    required_columns = ['Project', 'Target', 'Seq_type', 'Modify_seq', 'Strand_MWs', 'Parents', 'Remarks']
    if not all(col in df.columns for col in required_columns):
        raise ValueError(f"文件格式错误，必须包含列: {', '.join(required_columns)}")

    return df

def group_sequences(df):
    """
    Pair consecutive SS+AS or AS+SS rows.
    Pairing rule: scan left to right; consume two adjacent rows if their Seq_type
    is (SS,AS) or (AS,SS). Unpaired rows are reported in invalid_ss_as.
    Within each group, SS __row_id is always first, AS __row_id second.
    """
    ss_groups = []
    invalid_ss_as = []

    group_sorted = df.sort_values(by='__row_id').reset_index(drop=True)
    rows = [group_sorted.iloc[i] for i in range(len(group_sorted))]

    i = 0
    while i < len(rows):
        row = rows[i]
        seq_type = row['Seq_type'].strip().upper()

        if i + 1 < len(rows):
            next_row = rows[i + 1]
            next_seq_type = next_row['Seq_type'].strip().upper()

            if seq_type == 'SS' and next_seq_type == 'AS':
                temp_group = [row['__row_id'], next_row['__row_id']]
                ss_groups.append((None, row['Project'], temp_group))
                i += 2
                continue

            if seq_type == 'AS' and next_seq_type == 'SS':
                # SS first in group regardless of CSV order
                temp_group = [next_row['__row_id'], row['__row_id']]
                ss_groups.append((None, next_row['Project'], temp_group))
                i += 2
                continue

        # Could not pair with next row
        invalid_ss_as.append(
            f"原始行 {row['__original_line']}, {row['Modify_seq']}, 无法配对（{seq_type}）"
        )
        i += 1

    return ss_groups, invalid_ss_as


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

    # 预加载 DeliveryModule 关键词集合，并构建用于 unknown-check 的正则（longest-match）
    dm_keywords = set(DeliveryModule.objects.values_list('keyword', flat=True))
    _dm_sorted = sorted([k for k in dm_keywords if k], key=len, reverse=True)
    _dm_strip_re = (
        re.compile('|'.join(re.escape(k) for k in _dm_sorted), re.IGNORECASE)
        if _dm_sorted else None
    )

    # 预加载 LinkerModule 关键词（如 LK1）——出现在序列中间 [] 括号内，
    # 是双段序列的结构性连接词，注册裸序列时忽略，未知 token 检查中也应剔除
    _lk_module_keywords = sorted(
        [m.keyword for m in LinkerModule.objects.all() if m.keyword],
        key=len, reverse=True,
    )
    _lk_strip_re = (
        re.compile('|'.join(re.escape(k) for k in _lk_module_keywords), re.IGNORECASE)
        if _lk_module_keywords else None
    )

    # 预编译 combo 正则（避免循环内每次调用 normalize_tmp_seq_with_combo 都重复查 DB）
    _combo_re = build_combo_re()

    has_transcript_col = 'Transcript' in df.columns
    has_position_col = 'Position' in df.columns

    auto_register_pairs = []
    unknown_module_pairs = []
    unknown_delivery_warnings = []
    ambiguous_pairs = []           # 新增
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
        pair_delivery_warnings = []
        pair_ambig_tokens = {}   # { 'BU01': ['A', 'U'] }

        extracted = {}  # 'ss' or 'as' → {naked_seq, delivery5, delivery3, row_id, original_line}

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

            # 一次规范化，复用 tmp for both naked_seq and unknown check
            tmp = normalize_tmp_seq_with_combo(clean_seq, combo_re=_combo_re)

            # ── [新增] 检测多值 token（必须在 sm 替换之前） ──
            if _ambig_re:
                for match in _ambig_re.finditer(tmp):
                    token_upper = match.group(0).upper()
                    if token_upper not in pair_ambig_tokens:
                        pair_ambig_tokens[token_upper] = [
                            c.strip() for c in _ambig_map[token_upper].split(',')
                        ]

            if _sm_norm_re:
                tmp = _sm_norm_re.sub(lambda m: _sm_map[m.group(0).upper()], tmp)

            # ── naked_seq（与 save_deliveries 完全一致）──
            tmp_no_paren = re.sub(r'\(.*?\)', '', tmp)
            naked_seq = ''.join(re.findall(r'(INVAB|[AUGCI])', tmp_no_paren))

            extracted[label] = {
                'naked_seq': naked_seq,
                'delivery5': delivery5,
                'delivery3': delivery3,
                'row_id': int(row['__row_id']),
                'original_line': int(row['__original_line']),
            }

            # ── 检测未知 SeqModule token（复用 tmp）──
            # 移除 DeliveryModule 关键词（如 L96）
            tmp_check = _dm_strip_re.sub('', tmp) if _dm_strip_re else tmp
            # 移除 LinkerModule 关键词（如 LK1）——双段序列中间 [] 内的连接词，不是修饰 token
            tmp_check = _lk_strip_re.sub('', tmp_check) if _lk_strip_re else tmp_check
            # 去掉括号、连字符、数字
            tmp_check = re.sub(r'[\(\)\[\]\-\d]', '', tmp_check)
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
                pair_delivery_warnings.append({
                    'row_id': extracted[label]['row_id'],
                    'unknown_tokens': row_dm_unknowns,
                    'original_line': extracted[label]['original_line'],
                })

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

        if pair_has_unknown_module:
            skip_group_indices.add(group_idx)
            unknown_module_pairs.append({
                'ss_row_id': extracted['ss']['row_id'],
                'as_row_id': extracted['as']['row_id'],
                'unknown_tokens': list(set(pair_unknown_tokens)),
                'original_lines': pair_original_lines,
            })
            continue

        # Only add delivery warnings for pairs that reach the clean path
        if pair_delivery_warnings:
            unknown_delivery_warnings.extend(pair_delivery_warnings)

        # ── 检查裸序列是否已注册 ──
        ss_exists = Sequence.objects.filter(seq=extracted['ss']['naked_seq'], seq_type='SS').exists()
        as_exists = Sequence.objects.filter(seq=extracted['as']['naked_seq'], seq_type='AS').exists()

        if not ss_exists or not as_exists:
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
        'ambiguous_pairs': ambiguous_pairs,
        'clean_groups': clean_groups,
    }


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
                # ── 基本校验 ──
                if not naked_ss or not naked_as:
                    raise ValueError(f"naked_ss or naked_as is empty/None: ss={naked_ss!r}, as={naked_as!r}")

                # ── SS ──
                ss_obj, ss_created = Sequence.objects.get_or_create(
                    seq=naked_ss, seq_type='SS',
                    defaults={'created_at': created_at},
                )

                # ── AS ──
                as_obj, as_created = Sequence.objects.get_or_create(
                    seq=naked_as, seq_type='AS',
                    defaults={'created_at': created_at},
                )

                if ss_created or as_created:
                    registered_log.append({
                        'naked_ss': naked_ss,
                        'naked_as': naked_as,
                        'ss_created': ss_created,
                        'as_created': as_created,
                        'ss_rm_code': ss_obj.rm_code,
                        'as_rm_code': as_obj.rm_code,
                        'username': username,
                    })

                # ── Duplex ──
                duplex_seq_str = f"{naked_as}, {naked_ss}"
                duplex_obj, duplex_created = Sequence.objects.get_or_create(
                    seq=duplex_seq_str, seq_type='duplex',
                    defaults={'created_at': created_at},
                )

                # ── DuplexRelationship ──
                DuplexRelationship.objects.get_or_create(
                    as_seq=as_obj, ss_seq=ss_obj,
                    defaults={'duplex_seq': duplex_obj},
                )

                # ── SeqInfo SS（如不存在则创建）──
                if not SeqInfo.objects.filter(sequence=ss_obj).exists():
                    SeqInfo.objects.create(
                        sequence=ss_obj,
                        Transcript=transcript,
                        Pos=position,
                        project=project,
                        Remark='',
                        created_at=created_at,
                    )

                # ── SeqInfo AS（如不存在则创建）──
                if not SeqInfo.objects.filter(sequence=as_obj).exists():
                    SeqInfo.objects.create(
                        sequence=as_obj,
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


# 同一组SS+AS算重复
def check_duplicates(df, ss_groups):
    repeated_ids = set()
    duplicate_meg = []
    cross_project_duplicates = []

    # Preload SeqModule once for naked_seq computation
    _sm_list = sorted(
        SeqModule.objects.filter(base_char__isnull=False).exclude(base_char=''),
        key=lambda m: len(m.keyword), reverse=True,
    )
    _sm_map = {m.keyword.upper(): m.base_char for m in _sm_list}
    _sm_norm_re = (
        re.compile('|'.join(re.escape(m.keyword) for m in _sm_list), re.IGNORECASE)
        if _sm_list else None
    )

    seen_combinations = set()

    for _, group_project, group in ss_groups:
        modify_seqs, delivery_keys, row_ids = [], [], []

        for row_id in group:
            row = df.loc[row_id]
            full_seq = row['Modify_seq']

            d5 = re.search(r'^\[([^\[\]]*)\]', full_seq)
            d3 = re.search(r'\[([^\[\]]*)\]$', full_seq)
            d5 = d5.group(1) if d5 else ''
            d3 = d3.group(1) if d3 else ''

            clean_seq = re.sub(r'^\[.*?\]', '', full_seq)
            clean_seq = re.sub(r'\[.*?\]$', '', clean_seq)

            modify_seqs.append((clean_seq, d5, d3))
            delivery_keys.append(full_seq)
            row_ids.append(row_id)

        for i in range(0, len(modify_seqs), 2):
            if i + 1 < len(modify_seqs):
                ss_clean_seq, ss_d5, ss_d3 = modify_seqs[i]
                as_clean_seq, as_d5, as_d3 = modify_seqs[i + 1]
                ss_full_seq = delivery_keys[i]
                as_full_seq = delivery_keys[i + 1]

                combo_key = (
                    ss_clean_seq, ss_d5, ss_d3,
                    as_clean_seq, as_d5, as_d3
                )

                # 1️⃣ 本次上传内去重
                if combo_key in seen_combinations:
                    duplicate_meg.append(
                        f"重复SS+AS组：{ss_full_seq} + {as_full_seq} 在上传数据中重复"
                    )
                    repeated_ids.update([row_ids[i], row_ids[i + 1]])
                    continue
                seen_combinations.add(combo_key)

                # 2️⃣ 与数据库查重 — 完整匹配：裸序列 + delivery5/3 + 中间修饰码
                # modify_seq 直接取自 CSV（与 save_deliveries 存库时相同），无格式转换风险
                # naked_seq 作为辅助过滤（利用数据库索引加速），modify_seq 保证精确匹配
                ss_naked = extract_naked_seq(ss_clean_seq, _sm_map, _sm_norm_re)
                as_naked = extract_naked_seq(as_clean_seq, _sm_map, _sm_norm_re)

                if not ss_naked or not as_naked:
                    # Empty naked seq means all-unknown tokens — skip silently
                    continue

                ss_deliveries = list(Delivery.objects.filter(
                    sequence__seq=ss_naked,
                    delivery5=ss_d5,
                    delivery3=ss_d3,
                    modify_seq=ss_clean_seq,   # 中间修饰码也必须完全相同
                ).prefetch_related('project_links'))

                if ss_deliveries:
                    ss_duplex_ids = [d.duplex_id for d in ss_deliveries]
                    matched_as_duplex_ids = set(
                        Delivery.objects.filter(
                            sequence__seq=as_naked,
                            delivery5=as_d5,
                            delivery3=as_d3,
                            modify_seq=as_clean_seq,   # AS 端同样精确匹配
                            duplex_id__in=ss_duplex_ids,
                        ).values_list('duplex_id', flat=True)
                    )
                else:
                    matched_as_duplex_ids = set()

                for ss_del in ss_deliveries:
                    exists_as = ss_del.duplex_id in matched_as_duplex_ids

                    if exists_as:
                        existing_projects = list(
                            ss_del.project_links.values_list('project_code', flat=True)
                        )
                        # 同项目重复 → 跳过
                        if group_project and group_project in existing_projects:
                            duplicate_meg.append(
                                f"重复SS+AS组：{ss_full_seq} + {as_full_seq} 与数据库中已有记录重复（duplex_id: {ss_del.duplex_id}）"
                            )
                            repeated_ids.update([row_ids[i], row_ids[i + 1]])
                        else:
                            # 跨项目重复 → 收集待确认，不跳过
                            cross_project_duplicates.append({
                                'row_ids': [int(row_ids[i]), int(row_ids[i + 1])],
                                'existing_duplex_id': ss_del.duplex_id,
                                'existing_delivery_id': ss_del.id,
                                'existing_projects': existing_projects,
                                'target_project': group_project or '',
                                'delivery5': ss_d5,
                                'modify_seq': ss_clean_seq,
                                'delivery3': ss_d3,
                            })
                        break

    return repeated_ids, duplicate_meg, cross_project_duplicates

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

def build_combo_re():
    """
    构造 combo_re，用于匹配形如:
      <LEFT>-<module.keyword>
    LEFT 侧从 SeqModule 动态读取，RIGHT 侧从 DeliveryModule 动态读取。
    """
    dm_keywords = sorted(
        [m.keyword.strip() for m in DeliveryModule.objects.all() if m.keyword and m.keyword.strip()],
        key=len, reverse=True,
    )
    dm_pattern = "|".join(re.escape(k) for k in dm_keywords) if dm_keywords else r"(?!x)x"

    sm_keywords = sorted(
        [m.keyword.strip() for m in SeqModule.objects.all() if m.keyword and m.keyword.strip()],
        key=len, reverse=True,
    )
    sm_pattern = "|".join(re.escape(k) for k in sm_keywords) if sm_keywords else r"(?!x)x"

    # 额外的简单 token（不在 SeqModule 中，但可出现在 combo 左侧）
    left_extras = r'INVAB|I|ss|s|o|[ACGUT]'
    left_token_pat = rf"(?:{sm_pattern}|{left_extras})"

    combo_re = re.compile(rf'({left_token_pat})-({dm_pattern})', re.IGNORECASE)
    return combo_re


def normalize_tmp_seq_with_combo(modify_seq: str, combo_re=None) -> str:
    """
    先把 modify_seq upper，然后把 combo（LEFT-keyword）展开成 LEFT（保留原样，不做碱基映射）。

    Args:
        modify_seq: 原始修饰序列字符串。
        combo_re:   可选的预编译 combo 正则（由调用方预加载以避免循环内重复查 DB）。
                    若为 None，则调用 build_combo_re() 即时构建（向后兼容）。
    """
    tmp_seq = (modify_seq or "").upper()
    if combo_re is None:
        combo_re = build_combo_re()

    def combo_to_left(m: re.Match) -> str:
        # 只保留 LEFT，丢掉 -keyword
        return m.group(1).upper()

    tmp_seq = combo_re.sub(combo_to_left, tmp_seq)
    return tmp_seq


def extract_naked_seq(clean_seq: str, sm_map: dict, sm_norm_re, combo_re=None) -> str:
    """
    Derive the bare nucleotide sequence (AUGCI and INVAB tokens) from a clean modify_seq
    (brackets already stripped). Uses the caller-preloaded SeqModule map/regex
    to avoid repeated DB hits.

    Args:
        clean_seq:   modify_seq with leading/trailing [...] already removed.
        sm_map:      {keyword.upper(): base_char} from SeqModule.
        sm_norm_re:  compiled regex of SeqModule keywords (or None if empty).
        combo_re:    optional pre-compiled combo regex (avoids DB hit if provided).

    Returns:
        Bare nucleotide/INVAB token string, e.g. "AUGCAUGC" or "INVABAUGCAU".
    """
    tmp = normalize_tmp_seq_with_combo(clean_seq, combo_re=combo_re)
    if sm_norm_re:
        tmp = sm_norm_re.sub(lambda m: sm_map[m.group(0).upper()], tmp)
    tmp = re.sub(r'\(.*?\)', '', tmp)
    return ''.join(re.findall(r'(INVAB|[AUGCI])', tmp))


@transaction.atomic
def save_deliveries(df, duplex_id_map, username, sm_overrides=None):
    upload_log = []
    upload_meg = []
    unregistered_meg = []
    unregistered_log = []

    # 构建：duplex_id → [row1, row2]
    duplex_groups = defaultdict(list)
    for row_id, duplex_id in duplex_id_map.items():
        duplex_groups[duplex_id].append(df.loc[df['__row_id'] == row_id].iloc[0])

    # 预加载 SeqModule 规范化规则（只查一次 DB，避免循环内重复查询）
    _sm_list = sorted(SeqModule.objects.filter(base_char__isnull=False).exclude(base_char=''),
                      key=lambda m: len(m.keyword), reverse=True)
    _sm_map = {m.keyword.upper(): m.base_char for m in _sm_list}
    # 应用外部消歧覆盖（供含多值 token 的序列上传后正确推导裸序列）
    if sm_overrides:
        _sm_map.update({k.upper(): v for k, v in sm_overrides.items()})
    if _sm_list:
        _sm_norm_re = re.compile(
            '|'.join(re.escape(m.keyword) for m in _sm_list),
            re.IGNORECASE,
        )
    else:
        _sm_norm_re = None

    # 预编译 combo 正则（避免循环内每次调用 normalize_tmp_seq_with_combo 都重复查 DB）
    _combo_re = build_combo_re()

    for duplex_id, rows in duplex_groups.items():
        all_registered = True
       # naked_seqs = []
        detailed_rows = []

        for row in rows:

            row = {
                k: ('' if isinstance(v, str) and v.strip() == '' else v)
                for k, v in row.items()
            }

            full_seq = row['Modify_seq']
            # 捕获序列最左侧的内容
            d5 = re.search(r'^\[([^\[\]]*)\]', full_seq)
            # 捕获序列最右侧的内容
            d3 = re.search(r'\[([^\[\]]*)\]$', full_seq)
            delivery5 = d5.group(1) if d5 else ''
            delivery3 = d3.group(1) if d3 else ''
            modify_seq = re.sub(r'^\[.*?\]', '', full_seq)
            modify_seq = re.sub(r'\[.*?\]$', '', modify_seq)

            # 规范化：strip combo，替换修饰码为裸碱基，提取 naked_seq
            tmp_seq = normalize_tmp_seq_with_combo(modify_seq, combo_re=_combo_re)  # 去 combo 并大写
            if _sm_norm_re:
                tmp_seq = _sm_norm_re.sub(lambda m: _sm_map[m.group(0).upper()], tmp_seq)
            tmp_seq = re.sub(r'\(.*?\)', '', tmp_seq)           # 移除残余括号内容
            matches = re.findall(r'(INVAB|[AUGCI])', tmp_seq)
            naked_seq = ''.join(matches)
            naked_length = len(matches)

            detailed_rows.append({
                'row': row,
                'full_seq': full_seq,
                'delivery5': delivery5,
                'delivery3': delivery3,
                'modify_seq': modify_seq,
                'naked_seq': naked_seq,
                'naked_length': naked_length
            })

        # ── 批量查询本组所有裸序列（1 次 DB 查询代替 N 次）──
        _naked_seqs = [item['naked_seq'] for item in detailed_rows]
        _seq_cache = {s.seq: s for s in Sequence.objects.filter(seq__in=_naked_seqs)}

        for item in detailed_rows:
            if item['naked_seq'] not in _seq_cache:
                all_registered = False
                group_lines = ",".join(str(r['__original_line']) for r in rows)
                unregistered_meg.append(f"{item['row']['Project']} ➜ {item['full_seq']} ➜ {item['naked_seq']}")
                unregistered_log.append({
                    'Project': item['row']['Project'],
                    'duplex_id': duplex_id,
                    '行号组': group_lines,
                    'origin_line': item['row']['__original_line'],
                    'Modify_seq': item['full_seq'],
                    'Unregistered': item['naked_seq'],
                    '原因': '组内存在未注册序列，整组未上传'
                })

        if not all_registered:
            # 如果整组未注册，跳过后续处理
            continue

        seen_combinations = {}  # key: (base_id, delivery5, linker_seq, delivery3) → delivery_id

        # 处理每个详细行
        for item in detailed_rows:
            row = item['row']
            sequence_obj = _seq_cache[item['naked_seq']]
            base_id = sequence_obj.rm_code
            current_delivery5 = item['delivery5']
            current_delivery3 = item['delivery3']
            current_linker_seq = add_o_to_all_rules_safe(item['modify_seq'])


            key = (base_id, current_delivery5, current_linker_seq, current_delivery3)

            # 优先查数据库中是否有重复
            duplicate = Delivery.objects.filter(
                sequence=sequence_obj,
                delivery5=current_delivery5,
                delivery3=current_delivery3,
                linker_seq=current_linker_seq
            ).first()

            if duplicate:
                delivery_id = duplicate.delivery_id
            elif key in seen_combinations:
                delivery_id = seen_combinations[key]
            else:
                existing_ids = Delivery.objects.filter(delivery_id__startswith=base_id).values_list('delivery_id', flat=True)
                suffix_numbers = [
                    int(i.split(".")[-1]) for i in existing_ids
                    if "." in i and i.split(".")[0] == base_id and i.split(".")[-1].isdigit()
                ]
                next_suffix = max(suffix_numbers, default=0) + 1
                delivery_id = f"{base_id}.{next_suffix}"
                seen_combinations[key] = delivery_id

            Delivery.objects.create(
                delivery_id=delivery_id,
                sequence=sequence_obj,
                modify_seq=item['modify_seq'],
                linker_seq=current_linker_seq,
                naked_length=item['naked_length'],
                project=row['Project'],
                parents=row['Parents'],
                delivery5=item['delivery5'],
                delivery3=item['delivery3'],
                Strand_MWs=row['Strand_MWs'],
                Target=row['Target'],
                seq_type=row['Seq_type'],
                Remark=row['Remarks'],
                duplex_id=duplex_id,
                created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            )

            upload_meg.append(item['full_seq'])
            upload_log.append({
                'Time': now().strftime('%Y-%m-%d %H:%M:%S'),
                'User': username,
                'Project': row['Project'],
                'duplex_id': duplex_id,
                'Type': row['Seq_type'],
                'Modified_Sequence': item['full_seq'],
                'Remarks': row['Remarks']
            })


    return upload_meg, upload_log, unregistered_meg, unregistered_log


def write_upload_log(upload_log, username):
    user_dir = os.path.join('logs', username)
    os.makedirs(user_dir, exist_ok=True)
    filepath = os.path.join(user_dir, f'{username}_upload_log.csv')

    with open(filepath, 'a', encoding='utf-8', newline='') as log_file:
        fieldnames = ['Time', 'User', 'Project', 'duplex_id', 'Type', 'Modified_Sequence','Remarks']
        writer = csv.DictWriter(log_file, fieldnames=fieldnames)

        for entry in upload_log:
            writer.writerow(entry)


def write_unregistered_log(unregistered_log, username):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    user_dir = os.path.join('logs', username)
    os.makedirs(user_dir, exist_ok=True)
    filename = f'{username}_unregistered_{timestamp}.csv'
    filepath = os.path.join(user_dir, filename)

    with open(filepath, 'w', encoding='utf-8-sig', newline='') as log_file:
        fieldnames = ['Project', 'duplex_id', '行号组', 'origin_line', 'Modify_seq', 'Unregistered', '原因']
        writer = csv.DictWriter(log_file, fieldnames=fieldnames)
        writer.writeheader()
        for entry in unregistered_log:
            writer.writerow(entry)

    return filepath


def write_unpaired_ss_as_log(unpaired_ss_as, username):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    user_dir = os.path.join('logs', username)
    os.makedirs(user_dir, exist_ok=True)
    filename = f'{username}_unpaired_ss_as_{timestamp}.csv'
    filepath = os.path.join(user_dir, filename)

    # 写入 CSV 文件
    with open(filepath, 'w', encoding='utf-8-sig', newline='') as log_file:
        writer = csv.writer(log_file)
        writer.writerow(["Message"])  # 写入表头
        for item in unpaired_ss_as:
            writer.writerow([item])  # 写入每一行无效的 SS 或 AS 序列

    return filepath


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
                    'Project': str(row.get('Project', '')),
                    'Target': str(row.get('Target', '')),
                    'Seq_type': str(row.get('Seq_type', '')),
                    'Modify_seq': str(row.get('Modify_seq', '')),
                    'Strand_MWs': str(row.get('Strand_MWs', '')),
                    'Parents': str(row.get('Parents', '')),
                    'Remarks': str(row.get('Remarks', '')),
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


def write_repeated_log(repeated_df, username):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    user_dir = os.path.join('logs', username)
    os.makedirs(user_dir, exist_ok=True)
    filename = f'{username}_repeated_{timestamp}.csv'
    filepath = os.path.join(user_dir, filename)

    repeated_df.to_csv(filepath, index=False, encoding='utf-8-sig')  # 防乱码
    return filepath


def save_repeated_to_session(request, df, repeated_ids, unregistered_log, username):
    repeated_df = df[df['__row_id'].isin(repeated_ids)]
    repeated_path = write_repeated_log(repeated_df, username)
    request.session['repeated_path'] = repeated_path
    unregistered_path = write_unregistered_log(unregistered_log, username)
    request.session['unregistered_path'] = unregistered_path

@login_required
def upload_delivery_info(request):
    if request.method == 'GET':
        if request.GET.get('download') == 'repeats':
            repeated_path = request.session.get('repeated_path')
            if repeated_path and os.path.exists(repeated_path):
                with open(repeated_path, 'rb') as f:
                    response = HttpResponse(f.read(), content_type='text/csv')
                    response['Content-Disposition'] = f'attachment; filename="{os.path.basename(repeated_path)}"'
                    return response

        elif request.GET.get('download') == 'unregistered':
            unregistered_path = request.session.get('unregistered_path')
            if unregistered_path and os.path.exists(unregistered_path):
                with open(unregistered_path, 'rb') as f:
                    response = HttpResponse(f.read(), content_type='text/csv')
                    response['Content-Disposition'] = f'attachment; filename="{os.path.basename(unregistered_path)}"'
                    return response
            
        elif request.GET.get('download') == 'unpaired_ss_as':
            unpaired_ss_as_path = request.session.get('unpaired_ss_as_path')
            if unpaired_ss_as_path and os.path.exists(unpaired_ss_as_path):
                with open(unpaired_ss_as_path, 'rb') as f:
                    response = HttpResponse(f.read(), content_type='text/csv')
                    response['Content-Disposition'] = f'attachment; filename="{os.path.basename(unpaired_ss_as_path)}"'
                    return response

        elif request.GET.get('download') == 'template':
            template_path = os.path.join(settings.BASE_DIR, 'static', 'templates', 'upload_seq_template.csv')
            if os.path.exists(template_path):
                with open(template_path, 'rb') as f:
                    response = HttpResponse(f.read(), content_type='text/csv; charset=utf-8-sig')
                    response['Content-Disposition'] = 'attachment; filename="upload_seq_template.csv"'
                    return response


    if request.method == 'POST':
        try:
            df = parse_uploaded_csv(request)
            # 标准化 Modify_seq 中的中间 linker 括号：[LK1-L96-LK1] → -LK1-L96-LK1-
            df['Modify_seq'] = df['Modify_seq'].apply(normalize_middle_brackets)
            ss_groups, unpaired_ss_as = group_sequences(df)

            # ── 预检分析 ──
            preflight = run_preflight_check(df, ss_groups)
            needs_confirm = (
                bool(preflight['auto_register_pairs'])
                or bool(preflight['unknown_module_pairs'])
                or bool(preflight['unknown_delivery_warnings'])
                or bool(preflight.get('ambiguous_pairs'))
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
                    'ambiguous_pairs': preflight.get('ambiguous_pairs', []),
                }
                clean_groups_serializable = [
                    [g[0], g[1], [int(rid) for rid in g[2]]] for g in preflight['clean_groups']
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

            repeated_ids, duplicate_meg, cross_project_duplicates = check_duplicates(
                df, ss_groups
            )

            # 有跨项目重复 → 暂存数据，跳转到确认页让用户决定是否共享
            if cross_project_duplicates:
                cross_row_ids = set()
                for item in cross_project_duplicates:
                    cross_row_ids.update(item['row_ids'])
                df_normal = df[~df.index.isin(cross_row_ids)].copy()

                request.session['pending_shares'] = cross_project_duplicates
                request.session['pending_upload_df'] = df_normal.to_json()
                request.session['pending_repeated_ids'] = [int(x) for x in repeated_ids]
                request.session['pending_unpaired'] = unpaired_ss_as or []
                return redirect('confirm_share')

            duplex_id_map = assign_duplex_ids(df, ss_groups, repeated_ids)

            username = request.user.username
            upload_meg, upload_log, unregistered_meg, unregistered_log = save_deliveries(df, duplex_id_map, username)

            write_upload_log(upload_log, username)
            unregistered_csv = write_unregistered_log(unregistered_log, username)
            request.session['unregistered_csv'] = unregistered_csv

            save_repeated_to_session(request, df, repeated_ids, unregistered_log, username)

            # 生成未成组 SS 或 AS 的 CSV 文件
            if unpaired_ss_as:
                unpaired_ss_as_path = write_unpaired_ss_as_log(unpaired_ss_as, username)
                request.session['unpaired_ss_as_path'] = unpaired_ss_as_path  # 保存路径到 session
                # 提示用户有未成对的 SS 或 AS 序列
                messages.warning(request, f"有未成对的 SS 或 AS 序列，请查看并下载未配对的序列文件。")

            if upload_meg:
                messages.success(request, f"共 {len(upload_meg)} 条序列成功上传！")
            if repeated_ids:
                messages.warning(request, f"有 {len(duplicate_meg)} 条重复序列！")
            if unregistered_meg:
                messages.warning(request, f"有 {len(unregistered_meg)} 条序列未注册，请先注册！")
            if not upload_meg:
                messages.error(request, "无新的序列信息上传")

            return render(request, 'upload_delivery_info.html', {
                'success': True,
                'repeated_count': len(repeated_ids)
            })

        except Exception as e:
            messages.error(request, f"文件处理失败：{e}")
            return render(request, 'upload_delivery_info.html')


    return render(request, 'upload_delivery_info.html')


@login_required
def confirm_share_deliveries(request):
    if not (_is_superadmin(request.user) or
            getattr(request.user, 'user_type', '') == 'sub_admin'):
        messages.error(request, '您没有权限执行此操作。')
        return redirect('seq_list')

    if request.method == 'GET':
        pending = request.session.get('pending_shares', [])
        if not pending:
            return redirect('seq_delivery')
        return render(request, 'confirm_share.html', {'pending_shares': pending})

    if request.method == 'POST':

        from .models import DeliveryProject
        import pandas as pd

        pending = request.session.pop('pending_shares', [])
        pending_df_json = request.session.pop('pending_upload_df', None)
        pending_repeated_ids = request.session.pop('pending_repeated_ids', [])
        request.session.pop('pending_unpaired', None)  # clean up session key

        choices = request.POST.getlist('action')
        shared_count = 0

        try:
            with transaction.atomic():
                for i, item in enumerate(pending):
                    action = choices[i] if i < len(choices) else 'skip'
                    if action == 'share':
                        # Share all deliveries in the duplex (SS + AS), not just the SS strand
                        duplex_id = item['existing_duplex_id']
                        target_proj = item['target_project']
                        for d in Delivery.objects.filter(duplex_id=duplex_id):
                            DeliveryProject.objects.get_or_create(
                                delivery_id=d.id,
                                project_code=target_proj,
                            )
                        shared_count += 1

                if pending_df_json:
                    df = pd.read_json(pending_df_json)
                    if not df.empty:
                        ss_groups, _ = group_sequences(df)
                        repeated_ids, _, _ = check_duplicates(df, ss_groups)
                        repeated_ids.update(pending_repeated_ids)
                        duplex_id_map = assign_duplex_ids(df, ss_groups, repeated_ids)
                        username = request.user.username
                        upload_meg, upload_log, unregistered_meg, unregistered_log = save_deliveries(
                            df, duplex_id_map, username
                        )
                        write_upload_log(upload_log, username)
                        write_unregistered_log(unregistered_log, username)
                        if upload_meg:
                            messages.success(request, f"共 {len(upload_meg)} 条序列成功上传！")
        except Exception as e:
            _logger = logging.getLogger('edit_book_log')
            _logger.exception("confirm_share_deliveries 事务失败")
            messages.error(request, f"操作失败，所有更改已回滚：{e}")
            return redirect('seq_delivery')

        skip_count = len(pending) - shared_count
        messages.success(request, f"成功共享 {shared_count} 条，跳过 {skip_count} 条。")
        return redirect('seq_delivery')


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
        if not isinstance(preflight, dict):
            messages.error(request, "会话数据已损坏，请重新上传文件")
            return redirect('seq_delivery')
        return render(request, 'confirm_upload_preflight.html', {
            'auto_register_pairs': preflight.get('auto_register_pairs', []),
            'unknown_module_pairs': preflight.get('unknown_module_pairs', []),
            'unknown_delivery_warnings': preflight.get('unknown_delivery_warnings', []),
            'ambiguous_pairs': preflight.get('ambiguous_pairs', []),
        })

    if request.method == 'POST':
        try:
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

            # 构建全局 sm_overrides（token→单值）
            sm_overrides = {}
            for token_choices in disambig_choices.values():
                for token, char in token_choices.items():
                    sm_overrides.setdefault(token.upper(), char)

            preflight = request.session.get('preflight_result', {})
            df_json = request.session.get('preflight_df_json', None)
            clean_groups_json = request.session.get('preflight_clean_groups', None)

            if not isinstance(preflight, dict):
                messages.error(request, "会话数据已损坏，请重新上传文件")
                return redirect('seq_delivery')

            if not df_json or not clean_groups_json:
                messages.error(request, "会话已过期，请重新上传文件")
                return redirect('seq_delivery')

            auto_register_pairs = preflight.get('auto_register_pairs', [])

            # ── 1. 自动注册（guest 跳过）──
            user_type = getattr(request.user, 'user_type', 'guest')
            skipped_log = []
            if user_type != 'guest' and auto_register_pairs:
                registered_log, skipped_log = auto_register_bare_sequences(
                    auto_register_pairs, request.user.username
                )
                if registered_log:
                    messages.success(request, f"已自动注册 {len(registered_log)} 条序列")
                if skipped_log:
                    messages.warning(request, f"{len(skipped_log)} 对注册失败，已跳过")

            # ── 2. 从 session 恢复 df 和 clean_groups ──
            df = pd.read_json(StringIO(df_json))
            df = df.fillna('')
            # 恢复 index 以支持 df.loc[row_id]
            if '__row_id' in df.columns:
                df.index = df['__row_id'].astype(int)

            raw_groups = json.loads(clean_groups_json)
            clean_groups = [(g[0], g[1], g[2]) for g in raw_groups]

            # ── [新增] 消歧对处理：将用户选择的 base_char 用于推导裸序列，并入 clean_groups ──
            ambiguous_pairs_session = preflight.get('ambiguous_pairs', [])
            if ambiguous_pairs_session and disambig_choices:
                # 构建用于裸序列推导的 sm_map（含消歧覆盖）
                _sm_for_disambig = sorted(
                    SeqModule.objects.filter(base_char__isnull=False).exclude(base_char=''),
                    key=lambda m: len(m.keyword), reverse=True,
                )
                _sm_map_disambig = {m.keyword.upper(): m.base_char for m in _sm_for_disambig}
                _sm_map_disambig.update({k.upper(): v for k, v in sm_overrides.items()})
                _sm_re_disambig = (
                    re.compile('|'.join(re.escape(m.keyword) for m in _sm_for_disambig), re.IGNORECASE)
                    if _sm_for_disambig else None
                )
                # 预编译 combo 正则（避免循环内每次调用都重复查 DB）
                _combo_re_disambig = build_combo_re()

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
                        tmp = normalize_tmp_seq_with_combo(clean_seq, combo_re=_combo_re_disambig)
                        if _sm_re_disambig:
                            tmp = _sm_re_disambig.sub(
                                lambda m: _sm_map_disambig[m.group(0).upper()], tmp
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

            # Remove failed-registration pairs from clean_groups to avoid confusing
            # "unregistered" warnings from save_deliveries
            if skipped_log:
                # Collect naked_ss values of failed pairs
                failed_naked_ss = {entry['naked_ss'] for entry in skipped_log if entry.get('naked_ss')}
                # Map naked_ss back to row_ids via auto_register_pairs
                failed_row_ids = set()
                for pair in auto_register_pairs:
                    if pair.get('naked_ss') in failed_naked_ss:
                        if pair.get('ss_row_id') is not None:
                            failed_row_ids.add(pair['ss_row_id'])
                        if pair.get('as_row_id') is not None:
                            failed_row_ids.add(pair['as_row_id'])
                if failed_row_ids:
                    clean_groups = [
                        g for g in clean_groups
                        if not any(rid in failed_row_ids for rid in g[2])
                    ]

            # ── 3. 继续现有上传管道 ──
            repeated_ids, duplicate_meg, cross_project_duplicates = check_duplicates(
                df, clean_groups
            )

            # 有跨项目重复 → 暂存数据，跳转到确认页让用户决定是否共享
            if cross_project_duplicates:
                cross_row_ids = set()
                for item in cross_project_duplicates:
                    cross_row_ids.update(item['row_ids'])
                df_normal = df[~df.index.isin(cross_row_ids)].copy()
                request.session['pending_shares'] = cross_project_duplicates
                request.session['pending_upload_df'] = df_normal.to_json()
                request.session['pending_repeated_ids'] = [int(x) for x in repeated_ids]
                request.session['pending_unpaired'] = []
                request.session.pop('preflight_skip_csv_path', None)
                return redirect('confirm_share')

            duplex_id_map = assign_duplex_ids(df, clean_groups, repeated_ids)
            username = request.user.username
            upload_meg, upload_log, unregistered_meg, unregistered_log = save_deliveries(
                df, duplex_id_map, username, sm_overrides=sm_overrides or None
            )
            write_upload_log(upload_log, username)
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

            # Clear session keys after successful upload
            for key in ['preflight_result', 'preflight_df_json', 'preflight_clean_groups', 'preflight_skip_csv_path']:
                request.session.pop(key, None)

            return render(request, 'upload_delivery_info.html', {
                'success': True,
                'repeated_count': len(repeated_ids),
            })

        except KeyError as e:
            messages.error(request, f"会话数据损坏，请重新上传文件（缺少字段: {e}）")
            for key in ['preflight_result', 'preflight_df_json', 'preflight_clean_groups', 'preflight_skip_csv_path']:
                request.session.pop(key, None)
            return render(request, 'upload_delivery_info.html')
        except (json.JSONDecodeError, ValueError) as e:
            messages.error(request, f"数据解析失败，请重新上传文件：{e}")
            for key in ['preflight_result', 'preflight_df_json', 'preflight_clean_groups', 'preflight_skip_csv_path']:
                request.session.pop(key, None)
            return render(request, 'upload_delivery_info.html')
        except Exception as e:
            _logger = logging.getLogger('edit_book_log')
            _logger.exception("confirm_upload_preflight 未预期错误")
            messages.error(request, f"文件处理失败，请联系管理员：{e}")
            for key in ['preflight_result', 'preflight_df_json', 'preflight_clean_groups', 'preflight_skip_csv_path']:
                request.session.pop(key, None)
            return render(request, 'upload_delivery_info.html')


def _generate_next_bp():
    import re
    pattern = re.compile(r"^BP(\d{6})$")
    existing_ids = Delivery.objects.filter(duplex_id__startswith="BP").values_list('duplex_id', flat=True)
    existing_numbers = [int(m.group(1)) for d in existing_ids if (m := pattern.match(d))]
    next_number = max(existing_numbers, default=0) + 1
    return f"BP{next_number:06d}"


@login_required
def clone_delivery(request):
    """GET: return JSON of deliveries for given strand_id (duplex_id)
       POST: accept JSON list of edited delivery rows and create cloned Delivery records
    """
    # Role guard: only superadmin or sub_admin may clone
    if not (_is_superadmin(request.user) or
            getattr(request.user, 'user_type', '') == 'sub_admin'):
        return JsonResponse({'error': '权限不足'}, status=403)

    # GET: fetch deliveries
    if request.method == 'GET':
        strand_id = request.GET.get('strand_id')
        if not strand_id:
            return JsonResponse({'error': 'strand_id is required'}, status=400)

        deliveries = list(Delivery.objects.filter(duplex_id=strand_id))
        if not deliveries:
            return JsonResponse({'error': 'not found'}, status=404)

        # permission check: reuse project permission logic
        if not request.user.is_superuser:
            perms = getattr(request.user, 'permissions_project', '')
            if perms:
                allowed = [p.strip() for p in perms.split(',')]
                for d in deliveries:
                    if d.project not in allowed:
                        return JsonResponse({'error': 'no permission'}, status=403)
            else:
                return JsonResponse({'error': 'no permission'}, status=403)

        data = []
        for d in deliveries:
            data.append({
                'id': d.id,
                'Project': d.project,
                'Target': d.Target,
                'Seq_type': d.seq_type,
                'Modify_seq': d.modify_seq,
                'delivery5': d.delivery5,
                'delivery3': d.delivery3,
                'Strand_MWs': d.Strand_MWs,
                'Parents': d.parents,
                'Remark': d.Remark,
            })

        return JsonResponse({'deliveries': data})

    # POST: perform clone
    if request.method == 'POST':
        try:
            body = request.body.decode('utf-8')
            payload = json.loads(body) if body else {}
        except Exception:
            payload = request.POST.dict()

        rows = payload.get('deliveries') or []
        if not isinstance(rows, list) or len(rows) == 0:
            return JsonResponse({'error': 'deliveries list is required'}, status=400)

        # permission check: ensure user can clone these projects
        if not request.user.is_superuser:
            perms = getattr(request.user, 'permissions_project', '')
            if perms:
                allowed = [p.strip() for p in perms.split(',')]
                for r in rows:
                    if r.get('Project') not in allowed:
                        return JsonResponse({'error': 'no permission to clone this project'}, status=403)
            else:
                return JsonResponse({'error': 'no permission'}, status=403)

        # Build a DataFrame that matches save_deliveries expectations
        df_rows = []
        for idx, r in enumerate(rows):
            # construct Modify_seq with delivery5 and delivery3 wrapped in [] if provided
            left = r.get('delivery5') if r.get('delivery5') is not None else r.get('delivery5', '')
            right = r.get('delivery3') if r.get('delivery3') is not None else r.get('delivery3', '')
            base_modify = r.get('Modify_seq') or r.get('modify_seq') or ''
            modify_full = base_modify
            if left:
                modify_full = f'[{left}]' + modify_full
            if right:
                modify_full = modify_full + f'[{right}]'

            df_rows.append({
                '__row_id': idx,
                '__original_line': idx + 1,
                'Project': r.get('Project', ''),
                'Target': r.get('Target', ''),
                'Seq_type': r.get('Seq_type', ''),
                'Modify_seq': modify_full,
                'Strand_MWs': r.get('Strand_MWs', ''),
                'Parents': r.get('Parents', ''),
                'Remarks': r.get('Remark', '') if r.get('Remark') is not None else r.get('Remarks', ''),
                'delivery5': left,
                'delivery3': right,
            })

        df = pd.DataFrame(df_rows)

        # Before creating, run grouping and duplicate check (reuse existing logic)
        try:
            ss_groups, unpaired = group_sequences(df)
            repeated_ids, duplicate_meg, _ = check_duplicates(df, ss_groups)
        except Exception as e:
            return JsonResponse({'error': f'precheck failed: {e}'}, status=500)

        if duplicate_meg:
            # 返回中文提示并带上重复明细
            return JsonResponse({'error': '检测到重复的序列组合', 'detail': duplicate_meg}, status=400)

        # Assign a new duplex_id for this clone group
        new_duplex = _generate_next_bp()
        duplex_id_map = {row['__row_id']: new_duplex for row in df_rows}

        username = request.user.username
        try:
            upload_meg, upload_log, unregistered_meg, unregistered_log = save_deliveries(df, duplex_id_map, username)
        except Exception as e:
            return JsonResponse({'error': f'clone failed: {e}'}, status=500)

        if unregistered_meg:
            # 返回中文提示并在错误消息中列出未注册的裸序列（便于用户一目了然），同时保留 detail 数组
            try:
                # 尝试提取裸序列部分（最后一个 '➜ ' 后面为裸序列）
                naked_list = [s.split('➜')[-1].strip() for s in unregistered_meg]
                naked_list_str = '; '.join(naked_list)
                err_msg = f"请先注册以下未登记的序列： {naked_list_str}"
            except Exception:
                err_msg = '发现未注册的序列，整组未上传。请先注册相关序列。'
            return JsonResponse({'error': err_msg, 'detail': unregistered_meg}, status=400)

        return JsonResponse({'success': True, 'duplex_id': new_duplex, 'created': upload_meg})

    return JsonResponse({'error': 'method not allowed'}, status=405)

# ─────────────────────────────────────────────────────────────
# 通用辅助函数
# ─────────────────────────────────────────────────────────────

def get_user_default_seq_type(user):
    """
    返回指定用户的默认序列方向（SS / AS）。
    读取 LmsUser.default_seq_type 字段，未登录用户或字段为空时回落到 'SS'。
    """
    if not user.is_authenticated:
        return 'SS'
    return getattr(user, 'default_seq_type', 'SS') or 'SS'


def _is_superadmin(user) -> bool:
    """Return True for Django superusers and SeqDB superadmin role."""
    return user.is_superuser or getattr(user, 'user_type', '') == 'superadmin'


def get_permitted_delivery_qs(user):
    """
    Return the Delivery queryset visible to this user:
    - superadmin: all records
    - sub_admin / user: only records in their approved projects
    - no approved projects: empty queryset
    """
    if _is_superadmin(user):
        return Delivery.objects.all()
    allowed = user.get_allowed_projects()
    if allowed:
        # distinct() required: JOIN across DeliveryProject produces one row per
        # matching project link, not per Delivery.
        return Delivery.objects.filter(
            project_links__project_code__in=allowed
        ).distinct()
    return Delivery.objects.none()


def user_can_edit_delivery(user, delivery):
    """
    Return True if user may edit/delete/clone this Delivery record.

    Rules:
    - superadmin: always True
    - sub_admin: True only when user holds ALL projects the delivery belongs to
    - user: always False
    """
    if _is_superadmin(user):
        return True
    if getattr(user, 'user_type', '') != 'sub_admin':
        return False
    delivery_projects = set(
        delivery.project_links.values_list('project_code', flat=True)
    )
    if not delivery_projects:
        return False  # delivery with no project links is not editable by sub_admin
    user_projects = set(user.get_allowed_projects())
    return delivery_projects.issubset(user_projects)


def _user_can_access_duplex(user, duplex_id):
    """Return True if user can view/edit experiments for this duplex."""
    if _is_superadmin(user):
        return True
    return get_permitted_delivery_qs(user).filter(duplex_id=duplex_id).exists()


def get_attr(d, key):
    if isinstance(d, dict):
        return d.get(key, '')
    elif isinstance(d, Delivery):
        return getattr(d, key, '')
    return ''

def build_sequence_data(rm_code, seqinfo, sequence, deliveries, linker_seq, selected_seq_type,
                        dm_modules=None, color_map=None, lk_modules=None):
    """dm_modules / color_map / lk_modules 可由调用方预加载传入，避免循环内重复查询 DB。"""
    if not deliveries:
        deliveries = [{'delivery5': None, 'delivery3': None, 'date': None}]

    update_time = get_attr(deliveries[0], 'created_at') if deliveries else None
    formatted_update_time = update_time.strftime('%Y-%m-%d %H:%M') if update_time else None

    _remark_parts = [
        seqinfo.Remark if seqinfo and seqinfo.Remark else None,
        get_attr(deliveries[0], 'Remark') if deliveries else None,
    ]
    remark = '\n'.join(p for p in _remark_parts if p) or None

    # sequence.seq_type 是权威来源（来自 Sequence 注册），
    # Delivery.seq_type 可能因历史 CSV 上传标签错误而不可靠，不应用于排序/着色。
    seq_type_authoritative = sequence.seq_type if sequence else None

    return {
        'rm_code': rm_code,
        'seq_type': seq_type_authoritative,
        'seq_prefix': (
            "RA_" if sequence and sequence.seq_type == "AS"
            else "RS_" if sequence and sequence.seq_type == "SS"
            else "RM_" if sequence and sequence.seq_type == "duplex"
            else ""
        ),
        'seq': sequence.seq if sequence else None,
        'Project': get_attr(deliveries[0], 'project') if deliveries else None,
        'Transcript': seqinfo.Transcript if seqinfo else None,
        'Pos': seqinfo.Pos if seqinfo else None,
        'Remark': remark,
        'formatted_update_time': formatted_update_time,
        'linker_seq': linker_seq,
        'modify_seq_colored': get_modify_seq_colored(linker_seq, selected_seq_type, seq_type_authoritative, dm_modules=dm_modules, color_map=color_map, lk_modules=lk_modules) if linker_seq and selected_seq_type else [],
        'selected_seq_type': selected_seq_type,
        'deliveries': [
            {
                'duplex_id': getattr(d, 'duplex_id', None),
                'Parents': getattr(d, 'parents', None),
                'Target': getattr(d, 'Target', None),
                'Seq_type': seq_type_authoritative,
                'delivery_id': getattr(d, 'delivery_id', None),
                'delivery5': getattr(d, 'delivery5', None),
                'delivery3': getattr(d, 'delivery3', None),
                'Strand_MWs': getattr(d, 'Strand_MWs', None),
                'delivery3_colored': get_delivery_colored(
                    get_attr(d, 'delivery3'), selected_seq_type, seq_type_authoritative,
                    modules=dm_modules, color_map=color_map),
                'delivery5_colored': get_delivery_colored(
                    get_attr(d, 'delivery5'), selected_seq_type, seq_type_authoritative,
                    modules=dm_modules, color_map=color_map),
            }
            for d in deliveries
        ]
    }

def _suggest_duplex_id(term, base_qs):
    """
    For a no-result search term, try to suggest a correctly zero-padded duplex_id.
    e.g. "BP0002" → "BP000002" (same prefix + same numeric value, 6-digit padded).
    Returns the suggested ID string, or None if no match found.
    """
    m = re.match(r'^([A-Za-z]{1,4})(\d+)$', term.strip())
    if not m:
        return None
    prefix, digits = m.groups()
    padded = prefix.upper() + str(int(digits)).zfill(6)
    if padded.lower() != term.lower() and base_qs.filter(duplex_id__iexact=padded).exists():
        return padded
    return None


def _filter_delivery_qs_by_term(base_qs, term):
    """Filter base_qs by a single search term and expand result to full duplex pairs (AS+SS)."""
    q_obj = (
        Q(duplex_id__icontains=term) |
        Q(Target__icontains=term) |
        Q(project__icontains=term) |
        Q(modify_seq__icontains=term) |
        Q(parents__icontains=term) |
        Q(delivery_id__icontains=term) |
        Q(linker_seq__icontains=term)
    )
    matched_qs = base_qs.filter(q_obj)
    if not matched_qs.exists():
        return base_qs.none()
    matched_pairs = matched_qs.values_list('project', 'duplex_id').distinct()
    q_objects = Q()
    for proj, dup_id in matched_pairs:
        q_objects |= Q(project=proj, duplex_id=dup_id)
    return base_qs.filter(q_objects)

def build_duplex_groups(delivery_qs, selected_seq_type):
    """
    给定一个 Delivery 查询集，构建按 (project, duplex_id) 分组的展示数据。

    返回值格式：
        [
            {
                'project': str,
                'duplex_id': str,
                'items': [build_sequence_data(...), ...],  # SS 在前
            },
            ...
        ]

    注意：
        delivery_id_to_seq_id 的 key 是 Delivery.id（自增整数），
        value 是 Sequence.rm_code（6 位字符串）。
        此处命名保留原逻辑，避免影响 build_sequence_data 及模板。
    """
    # 预取 project_links，避免后续访问产生 N+1 查询
    delivery_qs = delivery_qs.prefetch_related('project_links')
    # 预加载 DeliveryModule 和 LinkerModule（一次查询，供所有 build_sequence_data 调用复用）
    _dm_modules = list(DeliveryModule.objects.all())
    _color_map = get_color_map(modules=_dm_modules)
    _lk_modules = list(LinkerModule.objects.all())

    delivery_id_to_seq_id = {}
    delivery_map = defaultdict(list)

    for d in delivery_qs:
        if d.id and d.sequence_id:
            delivery_id_to_seq_id[d.id] = d.sequence_id
            delivery_map[d.id].append(d)

    sequence_ids = list(set(delivery_id_to_seq_id.values()))

    sequence_map = {
        s.rm_code: s for s in Sequence.objects.filter(rm_code__in=sequence_ids)
    }
    seqinfo_map = {
        s.sequence_id: s for s in SeqInfo.objects.filter(sequence_id__in=sequence_ids)
    }

    duplex_group_map = defaultdict(list)

    for delivery_id, sequence_id in delivery_id_to_seq_id.items():
        sequence = sequence_map.get(sequence_id)
        seqinfo = seqinfo_map.get(sequence_id)
        deliveries = delivery_map.get(delivery_id, [])

        grouped_deliveries = defaultdict(list)
        for d in deliveries:
            project = getattr(d, 'project', None)
            duplex_id = getattr(d, 'duplex_id', None)
            if project and duplex_id:
                grouped_deliveries[(project, duplex_id)].append(d)

        for (project, duplex_id), group_deliveries in grouped_deliveries.items():
            linker_seqs = [d.linker_seq for d in group_deliveries if getattr(d, 'linker_seq', None)]
            if linker_seqs:
                for linker_seq in linker_seqs:
                    item = build_sequence_data(
                        rm_code=delivery_id,
                        seqinfo=seqinfo,
                        sequence=sequence,
                        deliveries=group_deliveries,
                        linker_seq=linker_seq,
                        selected_seq_type=selected_seq_type,
                        dm_modules=_dm_modules,
                        color_map=_color_map,
                        lk_modules=_lk_modules,
                    )
                    # 计算共享项目（超出原始 Delivery.project 的额外项目）
                    first_d = group_deliveries[0]
                    all_projs = [pl.project_code for pl in first_d.project_links.all()]
                    item['shared_projects'] = [p for p in all_projs if p != first_d.project]
                    duplex_group_map[(project, duplex_id)].append(item)
            else:
                item = build_sequence_data(
                    rm_code=delivery_id,
                    seqinfo=seqinfo,
                    sequence=sequence,
                    deliveries=group_deliveries,
                    linker_seq=None,
                    selected_seq_type=selected_seq_type,
                    dm_modules=_dm_modules,
                    color_map=_color_map,
                    lk_modules=_lk_modules,
                )
                # 计算共享项目（超出原始 Delivery.project 的额外项目）
                first_d = group_deliveries[0]
                all_projs = [pl.project_code for pl in first_d.project_links.all()]
                item['shared_projects'] = [p for p in all_projs if p != first_d.project]
                duplex_group_map[(project, duplex_id)].append(item)

    sequence_groups = []
    for (project, duplex_id), items in duplex_group_map.items():
        sorted_items = sorted(
            items,
            key=lambda x: x.get('seq_type') != 'SS',
        )
        aligned = None
        if len(sorted_items) >= 2:
            ss_tokens = sorted_items[0].get('modify_seq_colored') or []
            as_tokens = sorted_items[1].get('modify_seq_colored') or []
            ss_split = split_tokens_at_sep(ss_tokens)
            as_split = split_tokens_at_sep(as_tokens)
            if ss_split and as_split:
                ss_p1, ss_lk, ss_p2 = ss_split
                as_p1, _as_lk, as_p2 = as_split  # AS linker (···) rendered by template; discard here
                aligned = (
                    align_duplex_tokens(ss_p1, as_p1)
                    + [{'col_type': 'segment_sep', 'linker_tokens': ss_lk}]
                    + align_duplex_tokens(ss_p2, _reverse_tokens(as_p2))
                )
            else:
                # Strip any SEP tokens before flat alignment to avoid | appearing as a nucleotide column
                ss_flat = [t for t in ss_tokens if t.get('type') != 'SEP']
                as_flat = [t for t in as_tokens if t.get('type') != 'SEP']
                aligned = align_duplex_tokens(ss_flat, as_flat)
        times = [item.get('formatted_update_time') for item in sorted_items
                 if item.get('formatted_update_time')]
        sequence_groups.append({
            'project': project,
            'duplex_id': duplex_id,
            'items': sorted_items,
            'aligned_columns': aligned,
            'latest_update_time': max(times) if times else None,
            'shared_projects': sorted(set().union(*[it.get('shared_projects', []) for it in items]) - {project}),
        })

    return sequence_groups


@login_required
def get_sequence_info(request):
    user_type = getattr(request.user, 'user_type', 'guest')
    selected_seq_type = request.GET.get('seq_type', get_user_default_seq_type(request.user))

    # allowed_projects：超管为全部（含共享项目），否则取用户权限列表
    # 用 DeliveryProject.project_code 而非 Delivery.project，确保共享项目也出现在列表中
    if request.user.is_superuser:
        allowed_projects = sorted(filter(None, DeliveryProject.objects.values_list('project_code', flat=True).distinct()))
    else:
        allowed_projects = request.user.get_allowed_projects()

    # 解析 GET 中的 projects 参数：支持 ?projects=A&projects=B 或 ?projects=A,B
    raw_projects = request.GET.getlist('projects') or request.GET.get('projects', '')
    selected_projects = []
    if isinstance(raw_projects, list) and raw_projects:
        for p in raw_projects:
            selected_projects += [x.strip() for x in str(p).split(',') if x.strip()]
    elif isinstance(raw_projects, str) and raw_projects:
        selected_projects = [x.strip() for x in raw_projects.split(',') if x.strip()]

    if not selected_projects:
        selected_projects = allowed_projects[:]

    # 获取权限内的 Delivery 集合
    delivery_qs = get_permitted_delivery_qs(request.user)

    # 在权限范围内进一步按 selected_projects 过滤（防止越权）
    # 用 project_links__project_code__in 而非 project__in，确保共享序列也能被过滤到
    if selected_projects:
        safe_selected = [p for p in selected_projects if p in allowed_projects]
        if safe_selected:
            delivery_qs = delivery_qs.filter(
                project_links__project_code__in=safe_selected
            ).distinct()
        else:
            delivery_qs = Delivery.objects.none()

    # === 搜索过滤 ===
    # 全局快速搜索（单框搜索多字段）
    q = request.GET.get('q', '').strip()
    terms = split_terms(q)[:5] if q else []
    is_multi_term = len(terms) > 1

    # 高级字段搜索
    SEARCH_FIELD_MAP = {
        'filterSequence':    'duplex_id__icontains',
        'filterNakedSeq':    'sequence__seq__icontains',
        'filter5Delivery':   'delivery5__icontains',
        'filter3Delivery':   'delivery3__icontains',
        'filterTarget':      'Target__icontains',
        'filterProject':     'project__icontains',
        'filterSeqType':     'seq_type__iexact',
        'filterTranscript':  'linker_seq__icontains',
        'filterParents':     'parents__icontains',
        'filterRemarks':     'Remark__icontains',
    }
    field_filters = {k: request.GET.get(k, '').strip() for k in SEARCH_FIELD_MAP}
    # filterSeq 支持多值（列表），每个值之间为 AND 关系（同时包含所有片段）
    filter_seq_list = [v.strip() for v in request.GET.getlist('filterSeq') if v.strip()]
    field_filters['filterSeq'] = filter_seq_list
    has_search = bool(q) or any(field_filters.get(k) for k in SEARCH_FIELD_MAP) or bool(filter_seq_list)

    # filterSequence 多词分组支持（仅当 q 为空时触发）
    filter_seq_terms = split_terms(field_filters.get('filterSequence', ''))[:5]
    is_filter_seq_multi = len(filter_seq_terms) > 1 and not q

    if has_search:
        search_qs = delivery_qs

        if q and not is_multi_term:
            if terms:
                q_obj = Q()
                for term in terms:
                    q_obj |= (
                        Q(duplex_id__icontains=term) |
                        Q(Target__icontains=term) |
                        Q(project__icontains=term) |
                        Q(modify_seq__icontains=term) |
                        Q(parents__icontains=term) |
                        Q(delivery_id__icontains=term) |
                        Q(linker_seq__icontains=term)
                    )
                search_qs = search_qs.filter(q_obj)

        for form_key, lookup in SEARCH_FIELD_MAP.items():
            search_qs = apply_or_terms(search_qs, lookup, field_filters.get(form_key))

        # Modify Sequence 多值 AND 过滤：每个值单独 .filter()，要求同时包含所有片段
        # 构建正则 token[os-]*token[os-]*... 以匹配任意骨架连接符（o/s/-）
        # 同时搜索 modify_seq 和 linker_seq
        for val in filter_seq_list:
            pattern = build_seq_search_regex(val)
            if pattern:
                search_qs = search_qs.filter(
                    Q(modify_seq__iregex=pattern) | Q(linker_seq__iregex=pattern)
                )

        if not is_multi_term and not is_filter_seq_multi:
            if not search_qs.exists():
                messages.warning(request, '没有搜索到指定内容')
                delivery_qs = Delivery.objects.none()
            else:
                # 展开到完整的 duplex 对（保证 AS+SS 同时显示）
                matched_pairs = search_qs.values_list('project', 'duplex_id').distinct()
                q_objects = Q()
                for proj, dup_id in matched_pairs:
                    q_objects |= Q(project=proj, duplex_id=dup_id)
                delivery_qs = delivery_qs.filter(q_objects)
                # 若用户指定了 Seq Type，展开后重新收窄，只显示匹配的链型
                if field_filters.get('filterSeqType'):
                    delivery_qs = delivery_qs.filter(seq_type__iexact=field_filters['filterSeqType'])

    if is_multi_term:
        search_term_groups = []
        base_qs = search_qs  # field-filtered base; q-filter applied per term below
        for i, term in enumerate(terms):
            term_qs = _filter_delivery_qs_by_term(base_qs, term)
            term_seq_groups = build_duplex_groups(term_qs, selected_seq_type)
            duplex_ids = list({g['duplex_id'] for g in term_seq_groups if g.get('duplex_id')})
            term_exp_map = get_experiment_summary(duplex_ids)
            for g in term_seq_groups:
                g['exp_summary'] = term_exp_map.get(g.get('duplex_id'), '')
            suggestion = _suggest_duplex_id(term, base_qs) if not term_seq_groups else None
            search_term_groups.append({
                'term': term,
                'sequence_groups': term_seq_groups,
                'color_idx': i,
                'suggestion': suggestion,
            })
        sequence_groups = []
        is_multi_term = True
    elif is_filter_seq_multi:
        # Strand ID 多词分组：每个词单独按 duplex_id 过滤，展开完整 duplex 对后建组
        search_term_groups = []
        for i, term in enumerate(filter_seq_terms):
            term_matched = search_qs.filter(duplex_id__icontains=term)
            if term_matched.exists():
                matched_pairs = term_matched.values_list('project', 'duplex_id').distinct()
                q_objects = Q()
                for proj, dup_id in matched_pairs:
                    q_objects |= Q(project=proj, duplex_id=dup_id)
                term_qs = delivery_qs.filter(q_objects)
            else:
                term_qs = delivery_qs.none()
            term_seq_groups = build_duplex_groups(term_qs, selected_seq_type)
            duplex_ids = list({g['duplex_id'] for g in term_seq_groups if g.get('duplex_id')})
            term_exp_map = get_experiment_summary(duplex_ids)
            for g in term_seq_groups:
                g['exp_summary'] = term_exp_map.get(g.get('duplex_id'), '')
            suggestion = _suggest_duplex_id(term, delivery_qs) if not term_seq_groups else None
            search_term_groups.append({
                'term': term,
                'sequence_groups': term_seq_groups,
                'color_idx': i,
                'suggestion': suggestion,
            })
        sequence_groups = []
        is_multi_term = True
    else:
        search_term_groups = []
        sequence_groups = build_duplex_groups(delivery_qs, selected_seq_type)
        all_duplex_ids = list({g['duplex_id'] for g in sequence_groups if g.get('duplex_id')})
        exp_summary_map = get_experiment_summary(all_duplex_ids)
        for group in sequence_groups:
            group['exp_summary'] = exp_summary_map.get(group.get('duplex_id'), '')

    context = {
        'user_type': user_type,
        'sequence_groups': sequence_groups,
        'search_term_groups': search_term_groups,
        'is_multi_term': is_multi_term,
        'selected_seq_type': selected_seq_type,
        'allowed_projects': allowed_projects,
        'selected_projects': selected_projects,
        'search_q': q,
        'field_filters': field_filters,
        'has_search': has_search,
    }

    return render(request, 'seq_list.html', context)

@login_required
def cor_seq(request):
    query_id_tmp = request.GET.get('id')
    seq_type = request.GET.get('seq_type')

    selected_seq_type = request.GET.get('sorted_seq_type', get_user_default_seq_type(request.user))
    user_type = getattr(request.user, 'user_type', 'guest')

    # 权限过滤，获取当前用户可见的 sequence_id 集合
    base_delivery_qs = get_permitted_delivery_qs(request.user)
    visible_seq_ids = base_delivery_qs.values_list('sequence_id', flat=True)
    
    # 获取 Delivery 对象并获取 sequence_id
    delivery = get_object_or_404(base_delivery_qs, Q(id=query_id_tmp)&Q(seq_type=seq_type))  # 根据 query_id 获取 Delivery 对象
    query_id = delivery.sequence_id  # 获取该 Delivery 对应的 sequence_id

    # 根据前缀查双链关系
    if seq_type == "AS":

        related_duplex = DuplexRelationship.objects.filter(as_seq_id=query_id)
        related_ss_ids = [rel.ss_seq_id for rel in related_duplex if rel.ss_seq_id in visible_seq_ids]

        related_ids = Delivery.objects.filter(sequence_id__in=related_ss_ids).values_list('id', flat=True)  #delivery_id

    elif seq_type == "SS":

        related_duplex = DuplexRelationship.objects.filter(ss_seq_id=query_id)
        related_as_ids = [rel.as_seq_id for rel in related_duplex if rel.as_seq_id in visible_seq_ids]

        related_ids = Delivery.objects.filter(sequence_id__in=related_as_ids).values_list('id', flat=True)  #delivery_id

    else:
        return render(request, 'cor_seq.html', {'error': '无效的 seq_prefix'})


    # 收集当前及关联的 Delivery id 列表
    related_ids = list(related_ids)
    related_ids.insert(0, query_id_tmp)

    delivery_qs = Delivery.objects.filter(id__in=related_ids)
    all_sequence_ids = list(delivery_qs.values_list('sequence_id', flat=True))

    sequence_map = {s.rm_code: s for s in Sequence.objects.filter(rm_code__in=all_sequence_ids)}
    seqinfo_map = {s.sequence_id: s for s in SeqInfo.objects.filter(sequence_id__in=all_sequence_ids)}

    # 构建展示数据（cor_seq 为扁平列表，不按 duplex_id 分组）
    delivery_id_to_seq_id = {d.id: d.sequence_id for d in delivery_qs if d.id and d.sequence_id}
    delivery_map = defaultdict(list)
    for d in delivery_qs:
        delivery_map[d.id].append(d)

    seq_list = []
    for d_id, seq_id in delivery_id_to_seq_id.items():
        sequence = sequence_map.get(seq_id)
        seqinfo = seqinfo_map.get(seq_id)
        deliveries = delivery_map.get(d_id, [])
        linker_seqs = [d.linker_seq for d in deliveries if getattr(d, 'linker_seq', None)]

        if linker_seqs:
            for linker_seq in linker_seqs:
                seq_list.append(build_sequence_data(
                    rm_code=seq_id,
                    seqinfo=seqinfo,
                    sequence=sequence,
                    deliveries=deliveries,
                    linker_seq=linker_seq,
                    selected_seq_type=selected_seq_type,
                ))
        else:
            seq_list.append(build_sequence_data(
                rm_code=seq_id,
                seqinfo=seqinfo,
                sequence=sequence,
                deliveries=deliveries,
                linker_seq=None,
                selected_seq_type=selected_seq_type,
            ))

    return render(request, 'cor_seq.html', {
        'user_type': user_type,
        'sequence_list': seq_list,
        'query_id': query_id,
        'selected_seq_type': selected_seq_type,
    })

@login_required
def reg_seq_list(request):
    q = request.GET.get('q', '').strip()
    try:
        page_size = int(request.GET.get('page_size', 20))
    except (ValueError, TypeError):
        page_size = 20

    sequences = (
        Sequence.objects
        .exclude(seq_type='duplex')
        .prefetch_related('target_info')
        .order_by('rm_code')
    )
    if q:
        sequences = sequences.filter(rm_code__icontains=q)

    # DB-level pagination — only fetch the current page's rows
    paginator = Paginator(sequences, page_size)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    sequence_list = []
    for seq in page_obj.object_list:
        if seq.seq_type == 'SS':
            seq_prefix = 'SS_'
        elif seq.seq_type == 'AS':
            seq_prefix = 'AS_'
        else:
            seq_prefix = ''

        seq_info = seq.target_info.first()
        sequence_list.append({
            'rm_code': seq.rm_code,
            'seq_prefix': seq_prefix,
            'seq': seq.seq,
            'pos': seq_info.Pos if seq_info else '',
            'transcript': seq_info.Transcript if seq_info else '',
            'remark': seq_info.Remark if seq_info else '',
            'reg_date': seq.created_at.strftime('%Y-%m-%d %H:%M') if seq.created_at else '',
        })

    return render(request, 'reg_seq_list.html', {
        'sequence_list': sequence_list,
        'page_obj': page_obj,
        'page_size': page_size,
        'q': q,
    })

@login_required
def edit_reg_seq(request):
    rm_code = request.GET.get('id')
   #print(rm_code)
   # seq_Strand_MWs = request.GET.get('strand_MWs')
   # seq_id_query = seq_id.split('_')[1]  # 获取 rm_code
   #print(seq_id_query)

   # 根据 seq_id 查询 Delivery 对象
    Seq = get_object_or_404(Sequence, rm_code=rm_code)

    # 使用 rm_code 查询 SeqInfo 对象
    seqinfo = get_object_or_404(SeqInfo, sequence_id=rm_code)

    if request.method == 'POST':
        # 获取表单数据
        edit_project = request.POST.get('edit_project')
        edit_position = request.POST.get('edit_position')
        edit_transcript = request.POST.get('edit_Transcript')
        edit_remark = request.POST.get('edit_Remark')
        edit_date = request.POST.get('edit_date')
        # 获取当前时间（如果没有提供更新日期，则使用当前时间）
        if not edit_date:
            edit_date = datetime.now().strftime('%Y-%m-%dT%H:%M')
        # 将前端传递的字符串日期转换为 naive datetime
        naive_datetime = datetime.strptime(edit_date, "%Y-%m-%dT%H:%M")
        # 将 naive datetime 转换为 aware datetime（带时区）
        #new_datetime = timezone.make_aware(naive_datetime)
        new_datetime = naive_datetime
    
    # **检查是否有字段修改**
        changes = []
        if seqinfo and seqinfo.Pos != edit_position:
            changes.append(f"Position: {seqinfo.Pos} → {edit_position}")
            seqinfo.Pos = edit_position
        if seqinfo and seqinfo.Transcript != edit_transcript:
            changes.append(f"Transcript: {seqinfo.Transcript} → {edit_transcript}")
            seqinfo.Transcript = edit_transcript
        if seqinfo.Remark != edit_remark:
            changes.append(f"Remark: {seqinfo.Remark} → {edit_remark}")
            seqinfo.Remark = edit_remark
        if seqinfo and seqinfo.project != edit_project:
            changes.append(f"Project: {seqinfo.project} → {edit_project}")
            seqinfo.project = edit_project

        # **如果有变化，则更新数据库**
        if changes:
            # 更新 SeqInfo 对象 和 delivery 对象
            seqinfo.created_at = new_datetime  # 更新时间
            Seq.created_at = new_datetime  # 更新时间
            Seq.save()
            seqinfo.save()

             # 记录修改日志
            log_directory = 'bms/logs'  # 日志文件夹
            if not os.path.exists(log_directory):
                os.makedirs(log_directory)
            log_filename = f"edit_reg_seqs.log"
            log_file = os.path.join(log_directory, log_filename)
            
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(log_file),
                    logging.StreamHandler()
                ]
            )

            logger = logging.getLogger('edit_seqs')

            log_message = f"用户 {request.user.username} 在 {new_datetime} 编辑了ID为 {rm_code} 的序列 ，修改内容为: "
            log_details = []

            for change in changes:
                log_details.append(f"{change}")

            if log_details:
                log_message += "\n" + "\n".join(log_details) + "\n========================================================================\n"
                logger.info(log_message)

            messages.success(request, "序列信息已成功更新！")
            return redirect('reg_seq_list')  # 返回列表页

        else:
            # **如果没有变化，提示用户**
            messages.info(request, "您未做任何修改。")
            return redirect('reg_seq_list')  # 返回列表页
        
    context ={
        'seq': Seq,
        'seqinfo': seqinfo,
        
    } 

    return render(request, 'reg_seq_edit.html', context)


# 下载选中序列
@login_required
@require_POST
def download_selected(request):
    download_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    selected_ids = request.POST.get('selected_ids')
    selected_columns = request.POST.get('selected_columns')

    if not selected_ids or not selected_columns:
        return HttpResponse("参数缺失", status=400)

    try:
        ids = json.loads(selected_ids)
        columns = json.loads(selected_columns)
    except json.JSONDecodeError:
        return HttpResponse("参数格式错误", status=400)

    base_qs = get_permitted_delivery_qs(request.user)
    deliveries = base_qs.filter(duplex_id__in=ids)\
        .select_related('sequence')\
        .prefetch_related('sequence__target_info')

    if not deliveries.exists():
        return HttpResponse("未找到匹配的序列", status=404)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="selected_sequences_{download_time}.csv"'
    response.write('\ufeff')  # 防止 Excel 打开中文乱码

    writer = csv.writer(response)
    writer.writerow(columns)

    for d in deliveries:
        seqinfo = d.sequence.target_info.first() if hasattr(d.sequence, 'target_info') else None
        row = []

        for col in columns:
            col_lc = col.lower()

            # ✅ 特殊处理 remarks 字段（拼接两个来源）
            if col_lc == 'remarks':
                val = ''
                part1 = getattr(d, 'Remark', '') or ''
                part2 = (getattr(seqinfo, 'Remark', '') or '') if seqinfo else ''
                val = f"{part1}\n{part2}".strip("\n") if (part1 or part2) else ''

            elif col_lc == 'id':
            # 假设 seq_type 是从 `d.sequence.seq_type` 获取的
                seq_type = getattr(d, 'seq_type', '')
                delivery_id = getattr(d, 'delivery_id', '')  # 获取 delivery_id
                val = f"{seq_type}_{delivery_id}"  # 拼接 seq_type 和 delivery_id
            
            # ✅ 其他字段
            elif hasattr(d, col):
                val = getattr(d, col, '')
            elif col_lc == 'transcript':
                val = getattr(seqinfo, 'Transcript', '') if seqinfo else ''
            elif col_lc == 'pos':
                val = getattr(seqinfo, 'Pos', '') if seqinfo else ''
            else:
                val = ''

            row.append(val)

        writer.writerow(row)

    return response


@login_required
def module_list(request):
    page_size = int(request.GET.get('page_size', 20))
    page = int(request.GET.get('page', 1))
    q = request.GET.get('q', '').strip()

    queryset = DeliveryModule.objects.all().values('id', 'keyword', 'type_code', 'Strand_MWs')
    if q:
        queryset = queryset.filter(keyword__icontains=q)
    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(page)

    return render(request, 'module_list.html', {
        'module_list': page_obj.object_list,
        'page_obj': page_obj,
        'page_size': page_size,
        'q': q,
    })


@login_required
def edit_module(request):

    if not request.user.can_manage_module('delivery'):
        messages.error(request, '您没有操作权限！')
        return redirect('/module_list/')

    module_id = request.GET.get('id')
    module = None

    if module_id:
        module = get_object_or_404(DeliveryModule, id=module_id)

    if request.method == 'POST':
        keyword = request.POST.get('keyword').strip()
        type_code = request.POST.get('type_code').strip()
        Strand_MWs = request.POST.get('Strand_MWs').strip()
        

        if module is None:
            # === 新增模式 ===
            if DeliveryModule.objects.filter(keyword=keyword).exists():
                # 提示模块已存在
                messages.warning(request, f"模块“{keyword}”已存在，请勿重复增加。")
                return render(request, 'edit_module.html', {
                    'module': None,
                    'form_data': {'keyword': keyword, 'type_code': type_code, 'Strand_MWs': Strand_MWs}
                })

            # 创建新模块
            new_module = DeliveryModule(keyword=keyword, type_code=type_code, Strand_MWs=Strand_MWs)
            new_module.save()
            page = request.POST.get('page', 1)
            q = request.POST.get('q', '')
            return redirect(_module_list_url('/module_list/', page, q))
        else:
            # === 更新模式（通过 GET id 已加载 module） ===
            if keyword != module.keyword and DeliveryModule.objects.filter(keyword=keyword).exists():
                messages.warning(request, f'模块”{keyword}”已存在，请换一个名称。')
                return render(request, 'edit_module.html', {
                    'module': module,
                    'form_data': {'keyword': keyword, 'type_code': type_code, 'Strand_MWs': Strand_MWs},
                    'page': request.POST.get('page', 1),
                    'q': request.POST.get('q', ''),
                })
            module.keyword = keyword
            module.type_code = type_code
            module.Strand_MWs = Strand_MWs
            module.save()
            page = request.POST.get('page', 1)
            q = request.POST.get('q', '')
            return redirect(_module_list_url('/module_list/', page, q))

    page = request.GET.get('page', 1)
    q = request.GET.get('q', '')
    return render(request, 'edit_module.html', {'module': module, 'page': page, 'q': q})



@login_required
def upload_modules(request):

    # 权限控制
    if not request.user.can_manage_module('delivery'):
        messages.error(request, '您没有操作权限！')
        return redirect('/module_list/')

    if request.method == 'POST' and request.FILES.get('file'):
        csv_file = request.FILES['file']

        try:
            # 读取 CSV 文件到 DataFrame
            df = pd.read_csv(csv_file)

            # 检查文件是否包含 'module' 和 'type' 列
            if 'Module' not in df.columns or 'Type' not in df.columns or 'Molecular_Weight' not in df.columns:
                messages.error(request, "CSV 文件必须包含 'Module','Type'和'Molecular_Weight' 列！")
                return render(request, 'upload_modules.html')

            # 用来记录哪些模块已经存在
            existing_modules = []
            success_count = 0      # 统计成功上传数量

            # 遍历 DataFrame 行并保存到 DeliveryModule
            for _, row in df.iterrows():
                module_name = str(row['Module']).strip()
                type_code = str(row['Type']).strip()
                Strand_MWs = str(row['Molecular_Weight']).strip()

                # 检查 DeliveryModule 是否已经存在相同的模块
                if DeliveryModule.objects.filter(keyword=module_name).exists():
                    existing_modules.append(module_name)
                    continue  # 如果已经存在，跳过这行，继续下一个模块

                # 创建并保存模块对象
                DeliveryModule.objects.create(keyword=module_name, type_code=type_code, Strand_MWs=Strand_MWs)
                success_count += 1

            if existing_modules:
                messages.warning(request, f"以下模块已存在，未重复导入： {', '.join(existing_modules)}")

            if success_count > 0:
                messages.success(request, f"共成功注册{success_count} 条新模块")

            if success_count == 0:
                messages.success(request, f"未注册任何新模块")

            return redirect('module_list')

        except Exception as e:
            messages.error(request, f"处理文件时出错：{str(e)}")
            return render(request, 'upload_modules.html')
        
        # GET 请求时显示上传表单
    return render(request, 'upload_modules.html')

@login_required
@require_POST
def delete_module(request):

    if not request.user.can_manage_module('delivery'):
        messages.error(request, '您没有权限删除模块！')
        return redirect('/module_list/')

    module_id = request.POST.get('id')
    try:
        module = DeliveryModule.objects.get(id=module_id)
        module.delete()
        page = request.POST.get('page', 1)
        q = request.POST.get('q', '')
        return redirect(_module_list_url('/module_list/', page, q))
    except DeliveryModule.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '模块不存在'})
    
# ── 序列修饰列表（SeqModule）──────────────────────────────────────────────────

@login_required
def seqmodule_list(request):
    page_size = int(request.GET.get('page_size', 20))
    page = int(request.GET.get('page', 1))
    q = request.GET.get('q', '').strip()

    queryset = SeqModule.objects.all()
    if q:
        queryset = queryset.filter(keyword__icontains=q)
    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(page)

    return render(request, 'seqmodule_list.html', {
        'seqmodule_list': page_obj.object_list,
        'page_obj': page_obj,
        'page_size': page_size,
        'q': q,
    })


@login_required
def edit_seqmodule(request):
    if not request.user.can_manage_module('seq'):
        messages.error(request, '您没有操作权限！')
        return redirect('/seqmodule_list/')

    module_id = request.GET.get('id')
    page = request.GET.get('page', 1)
    q = request.GET.get('q', '')
    module = None

    if module_id:
        module = get_object_or_404(SeqModule, id=module_id)

    if request.method == 'POST':
        keyword = request.POST.get('keyword', '').strip()
        base_char = request.POST.get('base_char', '').strip()
        linker_connector = request.POST.get('linker_connector', 'o').strip() or 'o'

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
                    'page': request.POST.get('page', 1),
                    'q': request.POST.get('q', ''),
                })

        if module is None:
            if SeqModule.objects.filter(keyword=keyword).exists():
                messages.warning(request, f'修饰模块"{keyword}"已存在，请勿重复添加。')
                return render(request, 'edit_seqmodule.html', {
                    'module': None,
                    'form_data': {'keyword': keyword, 'base_char': base_char, 'linker_connector': linker_connector},
                    'page': request.POST.get('page', 1),
                    'q': request.POST.get('q', ''),
                })
            SeqModule.objects.create(keyword=keyword, base_char=base_char or None, linker_connector=linker_connector)
            page = request.POST.get('page', 1)
            q = request.POST.get('q', '')
            return redirect(_module_list_url('/seqmodule_list/', page, q))
        else:
            if keyword != module.keyword and SeqModule.objects.filter(keyword=keyword).exists():
                messages.warning(request, f'修饰模块"{keyword}"已存在，请换一个名称。')
                return render(request, 'edit_seqmodule.html', {
                    'module': module,
                    'form_data': {'keyword': keyword, 'base_char': base_char, 'linker_connector': linker_connector},
                    'page': request.POST.get('page', 1),
                    'q': request.POST.get('q', ''),
                })
            module.keyword = keyword
            module.base_char = base_char or None
            module.linker_connector = linker_connector
            module.save()
            page = request.POST.get('page', 1)
            q = request.POST.get('q', '')
            return redirect(_module_list_url('/seqmodule_list/', page, q))

    return render(request, 'edit_seqmodule.html', {'module': module, 'page': page, 'q': q})


@login_required
@require_POST
def delete_seqmodule(request):
    if not request.user.can_manage_module('seq'):
        messages.error(request, '您没有权限删除修饰模块！')
        return redirect('/seqmodule_list/')

    module_id = request.POST.get('id')
    try:
        module = SeqModule.objects.get(id=module_id)
        module.delete()
        page = request.POST.get('page', 1)
        q = request.POST.get('q', '')
        return redirect(_module_list_url('/seqmodule_list/', page, q))
    except SeqModule.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '修饰模块不存在'})


@login_required
def upload_seqmodules(request):
    if not request.user.can_manage_module('seq'):
        messages.error(request, '您没有操作权限！')
        return redirect('/seqmodule_list/')

    if request.method == 'POST' and request.FILES.get('file'):
        csv_file = request.FILES['file']
        try:
            df = pd.read_csv(csv_file)
            if 'Keyword' not in df.columns or 'Base_Char' not in df.columns:
                messages.error(request, "CSV 文件必须包含 'Keyword' 和 'Base_Char' 列！")
                return render(request, 'upload_seqmodules.html')

            existing = []
            success_count = 0
            for _, row in df.iterrows():
                keyword = str(row['Keyword']).strip()
                base_char = str(row['Base_Char']).strip()
                base_char = None if base_char in ('', 'nan', 'None') else base_char

                if SeqModule.objects.filter(keyword=keyword).exists():
                    existing.append(keyword)
                    continue
                SeqModule.objects.create(keyword=keyword, base_char=base_char)
                success_count += 1

            if existing:
                messages.warning(request, f"以下修饰模块已存在，未重复导入：{', '.join(existing)}")
            if success_count > 0:
                messages.success(request, f"共成功上传 {success_count} 条新修饰模块")
            return redirect('seqmodule_list')

        except Exception as e:
            messages.error(request, f"处理文件时出错：{str(e)}")
            return render(request, 'upload_seqmodules.html')

    return render(request, 'upload_seqmodules.html')


def split_terms(raw: str):
    if not raw:
        return []
    # 支持：逗号、中文逗号、空格、分号
    return [p for p in re.split(r"[,\s;，；]+", raw.strip()) if p]

def make_fuzzy_seq_regex(term: str) -> str:
    """
    将搜索词转换为允许 s/o 连接符的正则表达式。
    例：'UmUfUm'  → 'Um[so]*Uf[so]*Um'
        'UmsUfsUm' → 'Um[so]*Uf[so]*Um'（自动忽略 s/o）
    支持括号修饰如 (MOE)、(LNA)。
    """
    # 按 token 拆分：括号内容 | 大写字母开头的词 | 其余单字符
    tokens = re.findall(r'\([^)]*\)|[A-Za-z][a-z]*|[^A-Za-z\s]', term)
    # 过滤掉单独的 s/o 连接符 token
    base_tokens = [t for t in tokens if t not in ('s', 'o')]
    if not base_tokens:
        return re.escape(term)
    return '[so]*'.join(re.escape(t) for t in base_tokens)

def apply_or_terms(qs, lookup: str, raw: str):
    terms = split_terms(raw)
    if not terms:
        return qs
    q = Q()
    for t in terms:
        q |= Q(**{lookup: t})
    return qs.filter(q)

@login_required
def search(request):
    user_type = getattr(request.user, 'user_type', 'guest')
    selected_seq_type = request.GET.get('seq_type', get_user_default_seq_type(request.user))
    delivery_qs = get_permitted_delivery_qs(request.user)

    q = request.GET.get('q', '').strip()

    # 高级字段过滤条件
    filters = {
        'filterSequence':   request.GET.get('filterSequence', '').strip(),
        'filter5Delivery':  request.GET.get('filter5Delivery', '').strip(),
        'filter3Delivery':  request.GET.get('filter3Delivery', '').strip(),
        'filterTarget':     request.GET.get('filterTarget', '').strip(),
        'filterStrandMWs':  request.GET.get('filterStrandMWs', '').strip(),
        'filterRemarks':    request.GET.get('filterRemarks', '').strip(),
        'filterSeqType':    request.GET.get('filterSeqType', '').strip(),
        'filterProject':    request.GET.get('filterProject', '').strip(),
        'filterModifySeq':  request.GET.get('filterModifySeq', '').strip(),
        'filterTranscript': request.GET.get('filterTranscript', '').strip(),
        'filterParents':    request.GET.get('filterParents', '').strip(),
    }

    # 字段名到 ORM lookup 的映射（同字段多词 OR，字段间 AND）
    FIELD_MAP = {
        'filterSequence':   'duplex_id__icontains',
        'filter5Delivery':  'delivery5__icontains',
        'filter3Delivery':  'delivery3__icontains',
        'filterTarget':     'Target__icontains',
        'filterStrandMWs':  'Strand_MWs__icontains',
        'filterRemarks':    'Remark__icontains',
        'filterSeqType':    'seq_type__iexact',
        'filterProject':    'project__icontains',
        'filterTranscript': 'linker_seq__icontains',
        'filterParents':    'parents__icontains',
    }

    filtered_qs = delivery_qs

    # 快速搜索（q 参数）：OR 跨多字段
    if q:
        terms = split_terms(q)
        if terms:
            q_obj = Q()
            for term in terms:
                q_obj |= (
                    Q(duplex_id__icontains=term) |
                    Q(Target__icontains=term) |
                    Q(project__icontains=term) |
                    Q(modify_seq__icontains=term) |
                    Q(parents__icontains=term) |
                    Q(delivery_id__icontains=term) |
                    Q(linker_seq__icontains=term)
                )
            filtered_qs = filtered_qs.filter(q_obj)

    for form_key, lookup in FIELD_MAP.items():
        filtered_qs = apply_or_terms(filtered_qs, lookup, filters.get(form_key))

    # filterModifySeq：模糊正则同时搜 modify_seq 和 linker_seq，忽略 s/o 连接符
    modify_seq_raw = filters.get('filterModifySeq')
    if modify_seq_raw:
        terms = split_terms(modify_seq_raw)
        if terms:
            q_obj = Q()
            for t in terms:
                pattern = make_fuzzy_seq_regex(t)
                q_obj |= Q(modify_seq__iregex=pattern) | Q(linker_seq__iregex=pattern)
            filtered_qs = filtered_qs.filter(q_obj)

    has_search = bool(q) or any(filters.values())
    if has_search and not filtered_qs.exists():
        messages.warning(request, '没有搜索到指定内容')
        return redirect('seq_list')

    if has_search:
        matched_pairs = filtered_qs.values_list('project', 'duplex_id').distinct()
        q_objects = Q()
        for proj, dup_id in matched_pairs:
            q_objects |= Q(project=proj, duplex_id=dup_id)
        delivery_qs = delivery_qs.filter(q_objects)
        # 若用户指定了 Seq Type，展开后重新收窄，只显示匹配的链型
        if filters.get('filterSeqType'):
            delivery_qs = delivery_qs.filter(seq_type__iexact=filters['filterSeqType'])

    sequence_groups = build_duplex_groups(delivery_qs, selected_seq_type)

    context = {
        'user_type': user_type,
        'sequence_groups': sequence_groups,
        'selected_seq_type': selected_seq_type,
        'search_q': q,
        'filters': filters,
        'has_search': has_search,
    }

    return render(request, 'search_results.html', context)


@login_required
def blast_seq(request):
    """展示与指定 Delivery 相同裸序列、相同 seq_type 的所有修饰版本（不做 duplex 配对）。"""
    delivery_id = request.GET.get('delivery_id')
    seq_type = request.GET.get('seq_type')

    if not delivery_id or not seq_type:
        return HttpResponse('参数缺失', status=400)

    # 获取来源 Delivery，确认其裸序列
    source_delivery = get_object_or_404(
        get_permitted_delivery_qs(request.user),
        id=delivery_id
    )
    sequence_obj = source_delivery.sequence
    naked_seq = sequence_obj.seq if sequence_obj else None

    if not naked_seq:
        messages.warning(request, '该序列无裸序列信息')
        return redirect('seq_list')

    # 查找所有权限内、相同裸序列、相同 seq_type 的 Delivery
    delivery_qs = (
        get_permitted_delivery_qs(request.user)
        .filter(sequence__seq=naked_seq, seq_type=seq_type)
        .select_related('sequence')
        .order_by('project', 'duplex_id', 'delivery_id')
    )

    # 构建展示数据（复用 build_sequence_data，每条 Delivery 单独一行）
    seqinfo_cache = {
        s.sequence_id: s
        for s in SeqInfo.objects.filter(
            sequence_id__in=delivery_qs.values_list('sequence_id', flat=True)
        )
    }

    results = []
    for d in delivery_qs:
        seqinfo = seqinfo_cache.get(d.sequence_id)
        item = build_sequence_data(
            rm_code=d.id,
            seqinfo=seqinfo,
            sequence=d.sequence,
            deliveries=[d],
            linker_seq=d.linker_seq,
            selected_seq_type=seq_type,
        )
        results.append(item)

    context = {
        'naked_seq': naked_seq,
        'seq_type': seq_type,
        'selected_seq_type': seq_type,
        'results': results,
        'result_count': len(results),
        'source_duplex_id': source_delivery.duplex_id,
    }
    return render(request, 'blast_results.html', context)


def _resolve_duplex_id(seq_id, user):
    """根据输入 ID 解析出对应的 duplex_id。支持多种格式。"""
    qs = get_permitted_delivery_qs(user)

    # 格式 "AS_xxx" / "SS_xxx"
    m = re.match(r'^(AS|SS)_(.+)$', seq_id, re.IGNORECASE)
    if m:
        d = qs.filter(delivery_id=m.group(2), seq_type=m.group(1).upper()).first()
        if d and d.duplex_id:
            return d.duplex_id

    # 直接 Strand ID (duplex_id)
    if qs.filter(duplex_id=seq_id).exists():
        return seq_id

    # delivery_id
    d = qs.filter(delivery_id=seq_id).first()
    if d and d.duplex_id:
        return d.duplex_id

    # Delivery 整数主键（seq_list 的 data-rm-code 存的是 Delivery.id）
    try:
        d = qs.filter(id=int(seq_id)).first()
        if d and d.duplex_id:
            return d.duplex_id
    except (ValueError, TypeError):
        pass

    return None


def _build_all_mods(naked_seq, seq_type, user):
    """获取某裸序列+链型的所有修饰版本展示数据。"""
    all_deliveries = (
        get_permitted_delivery_qs(user)
        .filter(sequence__seq=naked_seq, seq_type=seq_type)
        .select_related('sequence')
        .order_by('project', 'duplex_id', 'delivery_id')
    )
    seqinfo_cache = {
        s.sequence_id: s
        for s in SeqInfo.objects.filter(
            sequence_id__in=all_deliveries.values_list('sequence_id', flat=True)
        )
    }
    return [
        build_sequence_data(
            rm_code=d.id,
            seqinfo=seqinfo_cache.get(d.sequence_id),
            sequence=d.sequence,
            deliveries=[d],
            linker_seq=d.linker_seq,
            selected_seq_type=seq_type,
        )
        for d in all_deliveries
    ]


@login_required
def multi_blast(request):
    """GET → 输入页面；POST → SS/AS 分组横向比对结果页面。"""
    if request.method == 'GET':
        return render(request, 'multi_blast.html', {})

    seq_ids = [s.strip() for s in request.POST.getlist('seq_id') if s.strip()]
    base_qs = get_permitted_delivery_qs(request.user).select_related('sequence')

    ss_entries = []
    as_entries = []
    not_found = []
    seen_duplex = set()

    # 第一轮：解析所有 duplex_id，收集所有 deliveries，避免 N+1 查询
    all_duplex_deliveries = {}  # {duplex_id: (seq_id, deliveries)}
    all_seq_ids_for_seqinfo = set()

    for seq_id in seq_ids:
        duplex_id = _resolve_duplex_id(seq_id, request.user)
        if not duplex_id:
            not_found.append(seq_id)
            continue
        if duplex_id in seen_duplex:
            continue
        seen_duplex.add(duplex_id)

        deliveries = list(base_qs.filter(duplex_id=duplex_id))
        all_duplex_deliveries[duplex_id] = (seq_id, deliveries)
        for d in deliveries:
            all_seq_ids_for_seqinfo.add(d.sequence_id)

    # 批量查询 SeqInfo，避免循环内单条查询
    seqinfo_cache = {
        s.sequence_id: s
        for s in SeqInfo.objects.filter(sequence_id__in=all_seq_ids_for_seqinfo)
    }

    # 第二轮：构建 entries
    for duplex_id, (seq_id, deliveries) in all_duplex_deliveries.items():
        ss_list = [d for d in deliveries if d.seq_type == 'SS']
        as_list = [d for d in deliveries if d.seq_type == 'AS']

        def make_entry(d, seq_id=seq_id, duplex_id=duplex_id, _cache=seqinfo_cache):
            seqinfo = _cache.get(d.sequence_id)
            item = build_sequence_data(
                rm_code=d.id,
                seqinfo=seqinfo,
                sequence=d.sequence,
                deliveries=[d],
                linker_seq=d.linker_seq,
                selected_seq_type=d.seq_type,
            )
            naked_seq = d.sequence.seq if d.sequence else None
            all_mods = _build_all_mods(naked_seq, d.seq_type, request.user) if naked_seq else []
            return {
                'input_id': seq_id,
                'duplex_id': duplex_id,
                'item': item,
                'naked_seq': naked_seq,
                'all_mods': all_mods,
                'all_mods_count': len(all_mods),
            }

        if ss_list:
            ss_entries.append(make_entry(ss_list[0]))
        if as_list:
            as_entries.append(make_entry(as_list[0]))

    return render(request, 'multi_blast_results.html', {
        'ss_entries': ss_entries,
        'as_entries': as_entries,
        'not_found': not_found,
        'seq_ids': seq_ids,
    })

# ─────────────────────────────────────────────────────────────────────────────
# Transcript alignment views
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def transcript_align_prepare(request):
    """准备页：接收来自 seq_list 的 rm_code 列表（step='init'），
    或接收填好 NM 号的表单（step='run'）触发比对。"""
    if request.method != 'POST':
        return redirect('seq_list')

    step = request.POST.get('step', 'init')
    _raw_back = request.POST.get('back_url', '')
    back_url = _raw_back if _raw_back.startswith('/') else reverse('seq_list')

    # ── step='init'：收集选中序列，渲染填写表格 ──────────────────────
    if step == 'init':
        rm_codes = request.POST.getlist('rm_code')
        if not rm_codes:
            messages.warning(request, '请先勾选至少一条序列')
            return redirect(back_url)

        from app01.transcript_align import get_ss_naked_dna
        rows = []
        seen_duplex = set()
        for rm_code in rm_codes:
            duplex_id = _resolve_duplex_id(rm_code, request.user)
            if not duplex_id or duplex_id in seen_duplex:
                continue
            seen_duplex.add(duplex_id)

            # SS 裸序列预览（注意：get_ss_naked_dna 返回 3-tuple）
            naked_dna, seq_rm_code, used_rc = get_ss_naked_dna(duplex_id, request.user)
            if naked_dna:
                preview = naked_dna[:15] + ('…' if len(naked_dna) > 15 else '')
                if used_rc:
                    preview += ' (RC)'
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


@login_required
def transcript_align_results(request):
    """结果预览页：GET 从 session 读结果；POST 写 DB。"""
    if request.method == 'GET':
        ta_results = request.session.get('ta_results')
        if not ta_results:
            messages.warning(request, '无比对结果，请重新操作')
            return redirect('seq_list')
        score_threshold = getattr(settings, 'SW_SCORE_THRESHOLD', 15)
        return render(request, 'transcript_align_results.html', {
            'ta_results': ta_results,
            'back_url': request.session.get('ta_back_url', '/seq_list/'),
            'score_threshold': score_threshold,
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


# ─────────────────────────────────────────────────────────────────────────────
# Experiment data views
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@login_required
def download_experiment_template(request):
    """返回实验数据 CSV 上传模板。"""
    import csv
    from django.http import HttpResponse
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="experiment_template.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'duplex_id', 'exp_type', 'assay_type', 'batch', 'exp_date',
        'cell_line', 'animal_species', 'transfection_reagent', 'route',
        'readout_type', 'value', 'value_unit', 'conc', 'conc_unit',
        'timepoint', 'replicate', 'notes',
    ])
    writer.writerow([
        'BP000001', 'in_vitro', 'single_point', 'Batch-001', '2026-05-01',
        'HepG2', '', 'Lipofectamine', '',
        'mRNA_remaining', '15', '%', '10', 'nM',
        '48h', 'n=3', '',
    ])
    writer.writerow([
        'BP000001', 'in_vivo', 'in_vivo_efficacy', 'Batch-001', '2026-05-10',
        '', 'mouse', '', 'SC',
        'mRNA_remaining', '20', '%', '3', 'mg_kg',
        'Day14', 'n=5', '',
    ])
    return response


def get_experiment_summary(duplex_ids):
    """
    给定 duplex_id 列表，返回 {duplex_id: summary_str} 字典。
    summary 规则：
    - 体外：取最佳 mRNA_remaining（最低值），格式 "KD {100-value}%@{conc}{unit}"
    - 体内：取最佳 mRNA_remaining，格式 "in vivo {100-value}%@{dose}{unit}"
    - 都有：体外/体内各一行（用 " / " 分隔）
    - 无：返回空字符串
    """
    from .models import Experiment, DataPoint
    if not duplex_ids:
        return {}

    conc_labels = dict(DataPoint.CONC_UNIT_CHOICES)

    experiments = (
        Experiment.objects
        .filter(duplex_id__in=duplex_ids)
        .prefetch_related('datapoints')
    )

    exp_by_duplex = defaultdict(list)
    for exp in experiments:
        exp_by_duplex[exp.duplex_id].append(exp)

    result = {}
    for duplex_id in duplex_ids:
        exps = exp_by_duplex.get(duplex_id, [])
        if not exps:
            result[duplex_id] = ''
            continue

        vitro_summary = ''
        vivo_summary = ''

        vitro_points = []
        vivo_points = []
        pk_points = []
        for exp in exps:
            for dp in exp.datapoints.all():
                if dp.readout_type in ('knockdown_pct', 'mRNA_remaining'):
                    if exp.exp_type == 'in_vitro':
                        vitro_points.append(dp)
                    elif exp.exp_type == 'in_vivo':
                        vivo_points.append(dp)
                elif dp.readout_type in ('plasma_conc', 'tissue_conc') and exp.assay_type == 'pk':
                    pk_points.append((exp, dp))

        if vitro_points:
            kd_points = [dp for dp in vitro_points if dp.readout_type == 'knockdown_pct']
            mr_points = [dp for dp in vitro_points if dp.readout_type == 'mRNA_remaining']
            if kd_points:
                best = max(kd_points, key=lambda dp: dp.value if dp.value is not None else -999)
                conc_str = f"@{best.concentration_or_dose}{conc_labels.get(best.conc_unit, best.conc_unit)}" if best.concentration_or_dose is not None else ''
                vitro_summary = f"KD {best.value:.0f}%{conc_str}"
            elif mr_points:
                best = min(mr_points, key=lambda dp: dp.value if dp.value is not None else 9999)
                kd_val = 100 - best.value
                conc_str = f"@{best.concentration_or_dose}{conc_labels.get(best.conc_unit, best.conc_unit)}" if best.concentration_or_dose is not None else ''
                vitro_summary = f"KD {kd_val:.0f}%{conc_str}"

        if vivo_points:
            kd_points = [dp for dp in vivo_points if dp.readout_type == 'knockdown_pct']
            mr_points = [dp for dp in vivo_points if dp.readout_type == 'mRNA_remaining']
            if kd_points:
                best = max(kd_points, key=lambda dp: dp.value if dp.value is not None else -999)
                dose_str = f"@{best.concentration_or_dose}{conc_labels.get(best.conc_unit, best.conc_unit)}" if best.concentration_or_dose is not None else ''
                vivo_summary = f"in vivo {best.value:.0f}%{dose_str}"
            elif mr_points:
                best = min(mr_points, key=lambda dp: dp.value if dp.value is not None else 9999)
                kd_val = 100 - best.value
                dose_str = f"@{best.concentration_or_dose}{conc_labels.get(best.conc_unit, best.conc_unit)}" if best.concentration_or_dose is not None else ''
                vivo_summary = f"in vivo {kd_val:.0f}%{dose_str}"

        if pk_points and not vivo_summary:
            # Show PK summary: first available plasma or tissue concentration with timepoint
            _, best_pk = pk_points[0]
            pk_label = conc_labels.get(best_pk.conc_unit, best_pk.conc_unit or '')
            tp_str = f" {best_pk.timepoint}" if best_pk.timepoint else ''
            vivo_summary = f"PK {best_pk.value:.1f}{pk_label}{tp_str}"

        parts = [s for s in [vitro_summary, vivo_summary] if s]
        result[duplex_id] = ' / '.join(parts)

    return result


@login_required
def experiment_detail(request, duplex_id):
    """展示某个 duplex_id 的所有实验记录，按 exp_type 分组。"""
    from .models import Experiment
    from django.http import Http404

    if not _user_can_access_duplex(request.user, duplex_id):
        raise Http404

    experiments = (
        Experiment.objects
        .filter(duplex_id=duplex_id)
        .prefetch_related('datapoints', 'attachments')
        .order_by('exp_type', '-created_at')
    )

    vitro_exps = [e for e in experiments if e.exp_type == 'in_vitro']
    vivo_exps  = [e for e in experiments if e.exp_type == 'in_vivo']

    can_edit = (
        request.user.is_superuser or
        getattr(request.user, 'user_type', '') in ('data_admin', 'admin', 'superadmin')
    )

    return render(request, 'experiment_detail.html', {
        'duplex_id':  duplex_id,
        'vitro_exps': vitro_exps,
        'vivo_exps':  vivo_exps,
        'can_edit':   can_edit,
    })


@login_required
def add_experiment(request):
    """手动录入实验记录 + 数据点 + 附件。"""
    from .models import Experiment, DataPoint, ExperimentAttachment
    from datetime import date
    import json as _json

    if request.method == 'GET':
        duplex_id = request.GET.get('duplex_id', '')
        edit_id = request.GET.get('edit', '').strip()
        prefill = {}
        dp_rows_json_init = '[]'

        if edit_id:
            try:
                editing_exp = Experiment.objects.prefetch_related('datapoints').get(pk=edit_id)
            except Experiment.DoesNotExist:
                messages.error(request, '实验记录不存在。')
                return redirect('seq_list')
            if not _user_can_access_duplex(request.user, editing_exp.duplex_id):
                messages.error(request, '您没有权限编辑该实验记录。')
                return redirect('seq_list')
            duplex_id = editing_exp.duplex_id
            prefill = {
                'duplex_id': editing_exp.duplex_id,
                'exp_type': editing_exp.exp_type,
                'assay_type': editing_exp.assay_type,
                'batch': editing_exp.batch,
                'exp_date': str(editing_exp.exp_date) if editing_exp.exp_date else '',
                'cell_line': editing_exp.cell_line or '',
                'animal_species': editing_exp.animal_species or '',
                'transfection_reagent': editing_exp.transfection_reagent or '',
                'route': editing_exp.route or '',
                'notes': editing_exp.notes or '',
            }
            dp_rows_json_init = _json.dumps([
                {
                    'conc': str(dp.concentration_or_dose) if dp.concentration_or_dose is not None else '',
                    'conc_unit': dp.conc_unit or '',
                    'timepoint': dp.timepoint or '',
                    'readout_type': dp.readout_type or '',
                    'value': str(dp.value),
                    'value_unit': dp.value_unit or '',
                    'replicate': dp.replicate or '',
                }
                for dp in editing_exp.datapoints.all()
            ])

        return render(request, 'add_experiment.html', {
            'duplex_id': duplex_id,
            'editing_exp_id': edit_id,
            'form_data': prefill,
            'dp_rows_json': dp_rows_json_init,
            'exp_type_choices':   Experiment.EXP_TYPE_CHOICES,
            'assay_type_choices': Experiment.ASSAY_TYPE_CHOICES,
            'conc_unit_choices':  DataPoint.CONC_UNIT_CHOICES,
            'readout_type_choices': DataPoint.READOUT_TYPE_CHOICES,
        })

    # Parse all POST fields up front so they can be re-populated on error
    editing_exp_id = request.POST.get('exp_id', '').strip()
    duplex_id  = request.POST.get('duplex_id', '').strip()
    exp_type   = request.POST.get('exp_type', '')
    assay_type = request.POST.get('assay_type', '')
    cell_line  = request.POST.get('cell_line', '').strip() or None
    animal_species = request.POST.get('animal_species', '').strip() or None
    batch      = request.POST.get('batch', '').strip()
    exp_date_str = request.POST.get('exp_date', '').strip()
    transfection_reagent = request.POST.get('transfection_reagent', '').strip() or None
    route      = request.POST.get('route', '').strip() or None
    notes      = request.POST.get('notes', '').strip() or None

    exp_date = None
    if exp_date_str:
        try:
            exp_date = date.fromisoformat(exp_date_str)
        except ValueError:
            pass

    concs         = request.POST.getlist('dp_conc')
    conc_units    = request.POST.getlist('dp_conc_unit')
    timepoints    = request.POST.getlist('dp_timepoint')
    readout_types = request.POST.getlist('dp_readout_type')
    values        = request.POST.getlist('dp_value')
    value_units   = request.POST.getlist('dp_value_unit')
    replicates    = request.POST.getlist('dp_replicate')

    def _render_form():
        dp_rows = [
            {
                'conc': concs[i] if i < len(concs) else '',
                'conc_unit': conc_units[i] if i < len(conc_units) else '',
                'timepoint': timepoints[i] if i < len(timepoints) else '',
                'readout_type': readout_types[i] if i < len(readout_types) else '',
                'value': values[i] if i < len(values) else '',
                'value_unit': value_units[i] if i < len(value_units) else '',
                'replicate': replicates[i] if i < len(replicates) else '',
            }
            for i in range(len(values))
            if (values[i].strip() if i < len(values) else False)
        ]
        return render(request, 'add_experiment.html', {
            'duplex_id': duplex_id,
            'editing_exp_id': editing_exp_id,
            'exp_type_choices':   Experiment.EXP_TYPE_CHOICES,
            'assay_type_choices': Experiment.ASSAY_TYPE_CHOICES,
            'conc_unit_choices':  DataPoint.CONC_UNIT_CHOICES,
            'readout_type_choices': DataPoint.READOUT_TYPE_CHOICES,
            'form_data': request.POST,
            'dp_rows_json': _json.dumps(dp_rows),
        })

    if not duplex_id or not exp_type or not assay_type or not batch:
        messages.error(request, '请填写必填字段：Duplex ID、实验类型、检测类型、批次号。')
        return _render_form()

    if not Delivery.objects.filter(duplex_id=duplex_id).exists():
        messages.error(request, f'Duplex ID "{duplex_id}" 不存在，请确认后重试。')
        return _render_form()

    if not _user_can_access_duplex(request.user, duplex_id):
        messages.error(request, '您没有权限录入该 Duplex ID 的实验数据。')
        return _render_form()

    valid_dp_indices = [
        i for i in range(len(values))
        if i < len(values) and values[i].strip()
    ]
    if not valid_dp_indices:
        messages.error(request, '请至少录入一个有效的数据点。')
        return _render_form()

    # Edit mode: load and verify existing record
    exp_to_edit = None
    if editing_exp_id:
        try:
            exp_to_edit = Experiment.objects.get(pk=editing_exp_id)
        except Experiment.DoesNotExist:
            messages.error(request, '要编辑的实验记录不存在。')
            return _render_form()
        if not _user_can_access_duplex(request.user, exp_to_edit.duplex_id):
            messages.error(request, '您没有权限编辑该实验记录。')
            return _render_form()

    with transaction.atomic():
        if exp_to_edit:
            exp_to_edit.duplex_id = duplex_id
            exp_to_edit.exp_type = exp_type
            exp_to_edit.assay_type = assay_type
            exp_to_edit.cell_line = cell_line
            exp_to_edit.animal_species = animal_species
            exp_to_edit.batch = batch
            exp_to_edit.exp_date = exp_date
            exp_to_edit.transfection_reagent = transfection_reagent
            exp_to_edit.route = route
            exp_to_edit.notes = notes
            exp_to_edit.save()
            exp_to_edit.datapoints.all().delete()
            exp = exp_to_edit
        else:
            exp = Experiment.objects.create(
                duplex_id=duplex_id,
                exp_type=exp_type,
                assay_type=assay_type,
                cell_line=cell_line,
                animal_species=animal_species,
                batch=batch,
                exp_date=exp_date,
                transfection_reagent=transfection_reagent,
                route=route,
                notes=notes,
                created_by=request.user.username,
            )

        for i in valid_dp_indices:
            try:
                val = float(values[i].strip())
            except ValueError:
                continue
            raw_conc = concs[i].strip() if i < len(concs) else ''
            conc_val = None
            if raw_conc:
                try:
                    conc_val = float(raw_conc)
                except ValueError:
                    pass
            DataPoint.objects.create(
                experiment=exp,
                concentration_or_dose=conc_val,
                conc_unit=conc_units[i] if i < len(conc_units) else '',
                timepoint=timepoints[i].strip() if i < len(timepoints) else None,
                readout_type=readout_types[i] if i < len(readout_types) else '',
                value=val,
                value_unit=value_units[i].strip() if i < len(value_units) else None,
                replicate=replicates[i].strip() if i < len(replicates) else None,
            )

        att_labels = request.POST.getlist('att_label')
        att_urls   = request.POST.getlist('att_url')
        att_files  = request.FILES.getlist('att_file')

        max_att = max(len(att_labels), len(att_urls), len(att_files), default=0)
        for i in range(max_att):
            label = att_labels[i].strip() if i < len(att_labels) else ''
            url   = att_urls[i].strip() if i < len(att_urls) else ''
            f     = att_files[i] if i < len(att_files) else None
            if not label and not url and not f:
                continue
            ExperimentAttachment.objects.create(
                experiment=exp,
                file=f,
                external_url=url or None,
                label=label or (f.name if f else url),
            )

    action = '已更新' if exp_to_edit else '已保存'
    messages.success(request, f'实验记录{action}（ID={exp.id}）。')
    return redirect(f'/experiment/{duplex_id}/')


@login_required
def delete_experiment(request, exp_id):
    """删除实验记录（仅 data_admin 及以上，且需有项目权限）。POST only。"""
    from .models import Experiment
    from django.http import HttpResponseNotAllowed
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    if not (_is_superadmin(request.user) or
            getattr(request.user, 'user_type', '') == 'sub_admin'):
        messages.error(request, '您没有权限删除实验记录。')
        return redirect('seq_list')
    try:
        exp = Experiment.objects.get(pk=exp_id)
    except Experiment.DoesNotExist:
        messages.error(request, '实验记录不存在。')
        return redirect('seq_list')
    if not _user_can_access_duplex(request.user, exp.duplex_id):
        messages.error(request, '您没有权限删除该项目的实验记录。')
        return redirect(f'/experiment/{exp.duplex_id}/')
    duplex_id = exp.duplex_id
    exp.delete()
    messages.success(request, '实验记录已删除。')
    return redirect(f'/experiment/{duplex_id}/')


@login_required
def upload_experiment(request):
    """批量上传实验数据 CSV。
    支持两种格式：
    1. duplex_id 列直接指定
    2. modify_seq 列（AS+SS 上下两行为一组），系统匹配 duplex_id
    """
    from collections import defaultdict as _dd

    if not (request.method == 'POST' and request.FILES.get('csv_file')):
        return render(request, 'upload_experiment.html')

    try:
        df = pd.read_csv(request.FILES['csv_file'], dtype=str).fillna('')
        df.columns = [c.strip() for c in df.columns]
    except Exception as e:
        messages.error(request, f"CSV 解析失败：{e}")
        return render(request, 'upload_experiment.html')

    errors = []
    created_exp = 0
    created_dp = 0

    has_duplex_col = 'duplex_id' in df.columns
    has_modify_col = 'modify_seq' in df.columns

    if not has_duplex_col and not has_modify_col:
        messages.error(request, "CSV 必须包含 duplex_id 或 modify_seq 列")
        return render(request, 'upload_experiment.html')

    if has_modify_col and not has_duplex_col:
        df = df.reset_index(drop=True)
        if len(df) % 2 != 0:
            messages.error(request, "modify_seq 格式要求 AS+SS 上下两行配对，行数必须为偶数")
            return render(request, 'upload_experiment.html')

        # Batch-query all unique sequences in one DB call
        all_seqs = set()
        for i in range(0, len(df), 2):
            all_seqs.add(df.iloc[i]['modify_seq'].strip())
            all_seqs.add(df.iloc[i + 1]['modify_seq'].strip())

        seq_to_duplexes = _dd(set)
        for row in Delivery.objects.filter(modify_seq__in=all_seqs).values('modify_seq', 'duplex_id'):
            if row['duplex_id']:
                seq_to_duplexes[row['modify_seq']].add(row['duplex_id'])

        resolved_rows = []
        for i in range(0, len(df), 2):
            r1 = df.iloc[i]
            r2 = df.iloc[i + 1]
            seq1 = r1['modify_seq'].strip()
            seq2 = r2['modify_seq'].strip()
            d1 = seq_to_duplexes[seq1]
            d2 = seq_to_duplexes[seq2]
            common = d1 & d2
            if not common:
                errors.append(f"行 {i+2}-{i+3}：未找到 AS+SS 匹配的 duplex_id")
                continue
            if len(common) > 1:
                errors.append(f"行 {i+2}-{i+3}：匹配到多个 duplex_id ({', '.join(sorted(common))})，请改用 duplex_id 列")
                continue
            duplex_id = common.pop()
            merged = {col: r1.get(col, '') or r2.get(col, '') for col in df.columns}
            merged['duplex_id'] = duplex_id
            resolved_rows.append(merged)

        if not resolved_rows:
            messages.error(request, "没有可处理的行：" + " | ".join(errors[:5]))
            return render(request, 'upload_experiment.html')

        df = pd.DataFrame(resolved_rows)

    # exp_type is now included in grouping so in_vitro/in_vivo are not merged
    grouping_keys = ['duplex_id', 'exp_type', 'batch', 'assay_type', 'cell_line', 'animal_species', 'exp_date']
    for key in grouping_keys:
        if key not in df.columns:
            df[key] = ''

    groups = _dd(list)
    for idx, row in df.iterrows():
        key = tuple(str(row.get(k, '') or '') for k in grouping_keys)
        groups[key].append(row)

    from datetime import date as _date
    skipped_dup = 0
    with transaction.atomic():
        for key, rows in groups.items():
            first = rows[0]
            duplex_id_val  = str(first.get('duplex_id', '')).strip()
            exp_type_val   = str(first.get('exp_type', 'in_vitro')).strip() or 'in_vitro'
            assay_type_val = str(first.get('assay_type', 'single_point')).strip() or 'single_point'
            batch_val      = str(first.get('batch', '')).strip()

            # Duplicate detection: skip if same (duplex, exp_type, assay_type, batch) already exists
            if Experiment.objects.filter(
                duplex_id=duplex_id_val,
                exp_type=exp_type_val,
                assay_type=assay_type_val,
                batch=batch_val,
            ).exists():
                skipped_dup += 1
                continue

            # Parse date with strict ISO format validation
            raw_date = str(first.get('exp_date', '')).strip()
            exp_date = None
            if raw_date:
                try:
                    exp_date = _date.fromisoformat(raw_date)
                except ValueError:
                    errors.append(
                        f"日期格式错误（duplex={duplex_id_val}）：{raw_date!r}，"
                        f"请使用 YYYY-MM-DD 格式，该组已跳过"
                    )
                    continue

            # Collect notes from all rows in group (deduplicated)
            seen_notes: set = set()
            unique_notes = []
            for r in rows:
                n = str(r.get('notes', '')).strip()
                if n and n not in seen_notes:
                    seen_notes.add(n)
                    unique_notes.append(n)
            notes_val = '; '.join(unique_notes) or None

            try:
                with transaction.atomic():
                    exp = Experiment.objects.create(
                        duplex_id=duplex_id_val,
                        exp_type=exp_type_val,
                        assay_type=assay_type_val,
                        cell_line=str(first.get('cell_line', '')).strip() or None,
                        animal_species=str(first.get('animal_species', '')).strip() or None,
                        batch=batch_val,
                        exp_date=exp_date,
                        transfection_reagent=str(first.get('transfection_reagent', '')).strip() or None,
                        route=str(first.get('route', '')).strip() or None,
                        notes=notes_val,
                        created_by=request.user.username,
                    )
                created_exp += 1
            except Exception as e:
                errors.append(f"创建实验失败（{duplex_id_val}）：{e}")
                continue

            for row in rows:
                val_str = str(row.get('value', '')).strip()
                if not val_str:
                    continue
                try:
                    v = float(val_str)
                except ValueError:
                    errors.append(f"数值格式错误（duplex={duplex_id_val}）：{val_str!r} 不是数字")
                    continue
                conc = str(row.get('conc', '') or row.get('dose', '')).strip()
                conc_val = None
                if conc:
                    try:
                        conc_val = float(conc)
                    except ValueError:
                        pass
                try:
                    with transaction.atomic():
                        DataPoint.objects.create(
                            experiment=exp,
                            concentration_or_dose=conc_val,
                            conc_unit=str(row.get('conc_unit', '')).strip(),
                            timepoint=str(row.get('timepoint', '')).strip() or None,
                            readout_type=str(row.get('readout_type', 'mRNA_remaining')).strip() or 'mRNA_remaining',
                            value=v,
                            value_unit=str(row.get('value_unit', '')).strip() or None,
                            replicate=str(row.get('replicate', '')).strip() or None,
                        )
                    created_dp += 1
                except Exception as e:
                    errors.append(f"创建数据点失败（duplex={duplex_id_val}）：{e}")

    success_msg = f"成功创建 {created_exp} 条实验记录，{created_dp} 个数据点。"
    if skipped_dup:
        success_msg += f" 跳过 {skipped_dup} 条重复记录（相同 duplex/exp_type/assay/batch 已存在）。"
    messages.success(request, success_msg)
    if errors:
        messages.warning(request, "部分行处理失败：" + " | ".join(errors[:10]))
    return redirect('upload_experiment')


@login_required
def linkermodule_list(request):
    page_size = int(request.GET.get('page_size', 20))
    page = int(request.GET.get('page', 1))
    q = request.GET.get('q', '').strip()

    queryset = LinkerModule.objects.all().values('id', 'keyword', 'description')
    if q:
        queryset = queryset.filter(keyword__icontains=q)
    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(page)

    return render(request, 'linkermodule_list.html', {
        'linkermodule_list': page_obj.object_list,
        'page_obj': page_obj,
        'page_size': page_size,
        'q': q,
    })


@login_required
def edit_linkermodule(request):
    if not request.user.can_manage_module('linker'):
        messages.error(request, '您没有操作权限！')
        return redirect('/linkermodule_list/')

    module_id = request.GET.get('id')
    module = None
    if module_id:
        module = get_object_or_404(LinkerModule, id=module_id)
    page = request.GET.get('page', 1)
    q = request.GET.get('q', '')

    if request.method == 'POST':
        keyword = request.POST.get('keyword', '').strip()
        description = request.POST.get('description', '').strip()

        if module is None:
            if LinkerModule.objects.filter(keyword=keyword).exists():
                messages.warning(request, f'Linker 模块"{keyword}"已存在，请勿重复添加。')
                return render(request, 'edit_linkermodule.html', {
                    'module': None,
                    'form_data': {'keyword': keyword, 'description': description},
                    'page': request.POST.get('page', 1),
                    'q': request.POST.get('q', ''),
                })
            LinkerModule.objects.create(keyword=keyword, description=description or None)
            page = request.POST.get('page', 1)
            q = request.POST.get('q', '')
            return redirect(_module_list_url('/linkermodule_list/', page, q))
        else:
            if keyword != module.keyword and LinkerModule.objects.filter(keyword=keyword).exists():
                messages.warning(request, f'Linker 模块"{keyword}"已存在，请换一个名称。')
                return render(request, 'edit_linkermodule.html', {
                    'module': module,
                    'form_data': {'keyword': keyword, 'description': description},
                    'page': request.POST.get('page', 1),
                    'q': request.POST.get('q', ''),
                })
            module.keyword = keyword
            module.description = description or None
            module.save()
            page = request.POST.get('page', 1)
            q = request.POST.get('q', '')
            return redirect(_module_list_url('/linkermodule_list/', page, q))

    return render(request, 'edit_linkermodule.html', {'module': module, 'page': page, 'q': q})


@login_required
@require_POST
def delete_linkermodule(request):
    if not request.user.can_manage_module('linker'):
        messages.error(request, '您没有权限删除 Linker 模块！')
        return redirect('/linkermodule_list/')

    module_id = request.POST.get('id')
    try:
        module = LinkerModule.objects.get(id=module_id)
        module.delete()
        page = request.POST.get('page', 1)
        q = request.POST.get('q', '')
        return redirect(_module_list_url('/linkermodule_list/', page, q))
    except LinkerModule.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Linker 模块不存在'})


# ── Profile & Project Access Request ─────────────────────────────────────────

@login_required
def user_profile(request):
    """Personal profile page for non-superadmin users."""
    if _is_superadmin(request.user):
        return redirect('author_list')

    user = request.user
    project_reqs = ProjectAccessRequest.objects.filter(user=user).order_by('-requested_at')
    module_reqs = ModulePermissionRequest.objects.filter(user=user).order_by('-requested_at')

    # Merge both request types into a single sorted list for combined history table
    combined = []
    for r in project_reqs:
        combined.append({
            'req_type': '项目',
            'content': r.project_codes,
            'status': r.status,
            'review_note': r.review_note,
            'requested_at': r.requested_at,
        })
    for r in module_reqs:
        combined.append({
            'req_type': '模块',
            'content': r.modules_requested,
            'status': r.status,
            'review_note': r.review_note,
            'requested_at': r.requested_at,
        })
    combined.sort(key=lambda x: x['requested_at'], reverse=True)

    return render(request, 'profile.html', {
        'profile_user': user,
        'combined_requests': combined,
        'approved_projects': user.get_allowed_projects(),
        'module_perms': [m for m in (user.module_permissions or '').split(',') if m],
    })


@login_required
@require_POST
def request_project_access(request):
    """Submit a new project access request."""
    if _is_superadmin(request.user):
        messages.error(request, '超级管理员无需申请项目权限。')
        return redirect('author_list')

    raw = request.POST.get('project_codes', '').strip()
    note = request.POST.get('note', '').strip()

    if not raw:
        messages.error(request, '请填写至少一个项目号。')
        return redirect('user_profile')

    project_codes = ','.join(p.strip() for p in raw.split(',') if p.strip())
    # Prevent duplicate pending requests
    if ProjectAccessRequest.objects.filter(user=request.user, status='pending').exists():
        messages.warning(request, '您有一个待审批的申请，请等待处理后再提交新申请。')
        return redirect('user_profile')
    ProjectAccessRequest.objects.create(user=request.user, project_codes=project_codes, note=note)
    messages.success(request, '申请已提交，等待超级管理员审批。')
    return redirect('user_profile')


@login_required
@require_POST
def approve_project_request(request, req_id):
    """Approve or reject a project access request. Superadmin only."""
    if not _is_superadmin(request.user):
        messages.error(request, '您没有权限执行此操作。')
        return redirect('seq_list')

    try:
        req = ProjectAccessRequest.objects.select_related('user').get(pk=req_id)
    except ProjectAccessRequest.DoesNotExist:
        messages.error(request, '申请记录不存在。')
        return redirect('author_list')

    if req.status != 'pending':
        messages.warning(request, f'该申请已处理（当前状态：{req.get_status_display()}）。')
        return redirect('author_list')

    action = request.POST.get('action')
    review_note = request.POST.get('review_note', '').strip()

    req.reviewed_by = request.user
    req.reviewed_at = timezone.now()
    req.review_note = review_note

    if action == 'approve':
        req.status = 'approved'
        user = req.user
        existing = set(user.get_allowed_projects())
        new_codes = {p.strip() for p in req.project_codes.split(',') if p.strip()}
        merged = sorted(existing | new_codes)
        user.permissions_project = ','.join(merged)
        user.save(update_fields=['permissions_project'])
        messages.success(request, f'已批准 {user.username} 的项目权限申请。')
    elif action == 'reject':
        req.status = 'rejected'
        messages.success(request, f'已拒绝申请，备注：{review_note or "无"}。')
    else:
        messages.error(request, '无效操作。')
        return redirect('author_list')

    req.save()
    return redirect('author_list')


@login_required
@require_POST
def request_module_access(request):
    """Submit a new module permission request."""
    if _is_superadmin(request.user):
        messages.error(request, '超级管理员无需申请模块权限。')
        return redirect('author_list')

    modules = request.POST.getlist('modules_requested')
    note = request.POST.get('note', '').strip()

    # Only accept known valid values
    valid = {'delivery', 'seq', 'linker'}
    modules = [m for m in modules if m in valid]

    if not modules:
        messages.error(request, '请至少选择一个模块。')
        return redirect('user_profile')

    if ModulePermissionRequest.objects.filter(user=request.user, status='pending').exists():
        messages.warning(request, '您有一个待审批的模块权限申请，请等待处理后再提交新申请。')
        return redirect('user_profile')

    ModulePermissionRequest.objects.create(
        user=request.user,
        modules_requested=','.join(sorted(modules)),
        note=note,
    )
    messages.success(request, '模块权限申请已提交，等待超级管理员审批。')
    return redirect('user_profile')


@login_required
@require_POST
def approve_module_request(request, req_id):
    """Approve or reject a module permission request. Superadmin only."""
    if not _is_superadmin(request.user):
        messages.error(request, '您没有权限执行此操作。')
        return redirect('seq_list')

    try:
        req = ModulePermissionRequest.objects.select_related('user').get(pk=req_id)
    except ModulePermissionRequest.DoesNotExist:
        messages.error(request, '申请记录不存在。')
        return redirect('author_list')

    if req.status != 'pending':
        messages.warning(request, f'该申请已处理（当前状态：{req.get_status_display()}）。')
        return redirect('author_list')

    action = request.POST.get('action')
    review_note = request.POST.get('review_note', '').strip()

    req.reviewed_by = request.user
    req.reviewed_at = timezone.now()
    req.review_note = review_note

    if action == 'approve':
        req.status = 'approved'
        user = req.user
        existing = {m for m in (user.module_permissions or '').split(',') if m}
        new_mods = {m for m in req.modules_requested.split(',') if m}
        merged = sorted(existing | new_mods)
        user.module_permissions = ','.join(merged)
        user.save(update_fields=['module_permissions'])
        messages.success(request, f'已批准 {user.username} 的模块权限申请。')
    elif action == 'reject':
        req.status = 'rejected'
        messages.success(request, f'已拒绝申请，备注：{review_note or "无"}。')
    else:
        messages.error(request, '无效操作。')
        return redirect('author_list')

    req.save()
    return redirect('author_list')

