from collections import defaultdict
import hashlib

from django.http import  HttpResponse, Http404, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login, get_user_model, update_session_auth_hash
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
    reversed_seq_type = selected_seq_type

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
    if seq_type == reversed_seq_type:
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



def get_modify_seq_colored(seq, selected_seq_type, seq_type, dm_modules=None, color_map=None):
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

    reversed_seq_type = selected_seq_type
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

    # === 7) 保留你原来的 SS 分组反转逻辑 ===
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
        user_type = data.get("user_type")  # 获取用户类型
   #     print(user_type)

        raw_premissions_projects = data.get('permissions_project')
       # print(raw_premissions_projects)
        # 将选中的项目转换为逗号分隔的字符串
        new_author_permissions_project = ','.join([proj.strip() for proj in raw_premissions_projects.split(',') if proj.strip()])
       # print(new_author_permissions_project)
        

        # 检查用户名和邮箱是否已存在
        if LmsUser.objects.filter(username=username).exists():
            messages.error(request, '用户名已存在！')
            return redirect('/register/')

        if LmsUser.objects.filter(email=email).exists():
            messages.error(request, '邮箱已注册！')
            return redirect('/register/')

        # 创建用户并保存用户类型
        LmsUser.objects.create(
            username=username,
            email=email,
            user_type=user_type,  # 保存用户类型
            permissions_project=new_author_permissions_project,  # 存储逗号分隔字符串
            password=setPassword(password)  # 保存加密后的密码
            
        )

        return redirect('/login/')  # 注册成功后跳转到登录页面

    return render(request, "register.html")

# 项目人员视图
@login_required
def author_list(request):
    user = LmsUser.objects.all()
    return render(request, 'auth_list.html', {'user_list': user})

# 添加用户
@login_required
def add_author(request):
    if request.method == 'POST':
        new_author_name = request.POST.get('username')
        new_author_email = request.POST.get('email')
        new_author_user_type = request.POST.get('user_type')
        

        raw_premissions_projects = request.POST.get('permissions_project')
    #    print(raw_premissions_projects)
        # 将选中的项目转换为逗号分隔的字符串
        new_author_permissions_project = ','.join([proj.strip() for proj in raw_premissions_projects.split(',') if proj.strip()])
        

         # 设置默认密码
        default_password = 'Bt123456'
        password = setPassword(default_password)  # 加密密码

        # 创建新的用户
        models.LmsUser.objects.create(
            username=new_author_name,
            email=new_author_email,
            user_type=new_author_user_type,
            permissions_project=new_author_permissions_project,  # 存储逗号分隔字符串
            password=password
        )

        return redirect('/author_list/')

    # 获取项目列表（从 Delivery 表动态获取）
    project_list = list(
        Delivery.objects
        .exclude(project__isnull=True).exclude(project='')
        .values_list('project', flat=True)
        .distinct().order_by('project')
    )

    return render(request, 'author_add.html', {'project_choices': project_list})

# 删除用户
@login_required
def drop_author(request):
    if not request.user.is_authenticated or (not request.user.is_superuser and not request.user.is_admin):
        messages.error(request, '您没有权限删除用户信息！')
        return redirect('/author_list/')

    drop_id = request.GET.get('id')

    # 已确认删除（前端通过 Modal 确认后发起请求）
    try:
        drop_obj = LmsUser.objects.get(id=drop_id)
        if str(request.user.id) == drop_id:
            messages.error(request, '不能删除当前登录的管理员账户！')
            return redirect('/author_list/')
        # 不能删除任何管理员账号（is_superuser 或 is_admin）
        if drop_obj.is_superuser or getattr(drop_obj, 'is_admin', False):
            messages.error(request, '不能删除管理员账号！')
            return redirect('/author_list/')
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

        messages.success(request, '密码修改成功，请重新登录！')
        return redirect('/login/')
    
    return render(request, 'change_password.html')

# 编辑用户
@login_required
def edit_author(request):
    # 非管理员禁止访问
    if not request.user.is_authenticated or (not request.user.is_superuser and not request.user.is_admin):
        messages.error(request, '您没有权限编辑用户信息！')
        return redirect('/author_list/')

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
    delivery = get_object_or_404(Delivery, Q(id=seq_id) & Q(Strand_MWs=seq_Strand_MWs))

    # 提取 delivery 对象中的 sequence_id
    delivery_sequence_id = delivery.sequence_id

    # 使用 delivery 中的 sequence_id 查询 SeqInfo 对象
    seqinfo = get_object_or_404(SeqInfo, sequence_id=delivery_sequence_id)

    if request.method == 'POST':
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
     #       print(delivery.project)
     #       print(edit_project)
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
        
    context ={
        'seqinfo': seqinfo,
        'delivery': delivery
        
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
            file_content = uploaded_file.read().decode('utf-8', errors='replace')  # Decode the file content

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
            if end < len(modify_seq) and modify_seq[end] != 's':
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
            if connector and end < len(modify_seq) and modify_seq[end] != 's':
                linker_seq += token + connector
            else:
                linker_seq += token
            i = end
            continue

        # 3. 其余字符原样复制
        linker_seq += modify_seq[i]
        i += 1

    return linker_seq


# 上传递送信息 （分块函数)
def parse_uploaded_csv(request):
    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        raise ValueError("未选择文件！")
    if not uploaded_file.name.endswith('.csv'):
        raise ValueError("请上传 CSV 文件！")

    file_content = uploaded_file.read().decode('utf-8', errors='replace')
    df = pd.read_csv(StringIO(file_content), sep=None, engine='python', encoding='utf-8')
    df = df.fillna('')
    df['__row_id'] = df.index
    df['__original_line'] = df.index + 2  # CSV 原始行号（包含表头）

    required_columns = ['Project', 'Target', 'Seq_type', 'Modify_seq', 'Strand_MWs', 'Parents', 'Remarks']
    if not all(col in df.columns for col in required_columns):
        raise ValueError(f"文件格式错误，必须包含列: {', '.join(required_columns)}")

    return df

def group_sequences(df):
    ss_groups = []         # 有效 SS+AS 组合
    invalid_ss_as = []     # 无效条目记录

    # 对全表按 __row_id 排序（确保顺序匹配）
    group_sorted = df.sort_values(by='__row_id').reset_index(drop=True)

    i = 0
    while i < len(group_sorted):
        row = group_sorted.iloc[i]
        row_id = row['__row_id']
        original_line = row['__original_line']
        seq_type = row['Seq_type'].strip().upper()
        modify_seq = row['Modify_seq']
        project = row['Project']  # 保留项目字段，仅用于显示或后续使用

        if seq_type == 'SS':
            temp_group = [row_id]

            if i + 1 < len(group_sorted):
                next_row = group_sorted.iloc[i + 1]
                next_seq_type = next_row['Seq_type'].strip().upper()

                if next_seq_type == 'AS':
                    temp_group.append(next_row['__row_id'])
                    ss_groups.append((None, project, temp_group))  # batch 用 None 占位
                    i += 1  # 跳过已配对的 AS
                else:
                    invalid_ss_as.append(f"原始行 {original_line}, {modify_seq}, 无效SS：没有 AS 配对")
            else:
                invalid_ss_as.append(f"原始行 {original_line}, {modify_seq}, 无效SS：没有 AS 配对")

        elif seq_type == 'AS':
            invalid_ss_as.append(f"原始行 {original_line}, {modify_seq}, 无效AS：没有配对的 SS")

        i += 1

    return ss_groups, invalid_ss_as


# 同一组SS+AS算重复
def check_duplicates(df, ss_groups):
    repeated_ids = set()
    duplicate_meg = []

    # 
    seen_combinations = set()

    for _, _, group in ss_groups:
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

                # 2️⃣ 与数据库查重（完全不看 project、target、batch）
                dup_id_list = Delivery.objects.filter(
                    modify_seq=ss_clean_seq,
                    delivery5=ss_d5,
                    delivery3=ss_d3
                ).values_list('duplex_id', flat=True)

                for dup_id in dup_id_list:
                    exists_as = Delivery.objects.filter(
                        modify_seq=as_clean_seq,
                        delivery5=as_d5,
                        delivery3=as_d3,
                        duplex_id=dup_id
                    ).exists()

                    if exists_as:
                        duplicate_meg.append(
                            f"重复SS+AS组：{ss_full_seq} + {as_full_seq} 与数据库中已有记录重复（duplex_id: {dup_id}）"
                        )
                        repeated_ids.update([row_ids[i], row_ids[i + 1]])
                        break

    return repeated_ids, duplicate_meg

def assign_duplex_ids(df, ss_groups, repeated_ids):
    duplex_id_map = {}
    valid_groups = [group for _, _, group in ss_groups if not repeated_ids.intersection(group)]

    pattern = re.compile(r"^BP(\d{6})$")
    existing_ids = Delivery.objects.filter(
        duplex_id__startswith="BP"
    ).values_list('duplex_id', flat=True)

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


def normalize_tmp_seq_with_combo(modify_seq: str) -> str:
    """
    先把 modify_seq upper，然后把 combo（LEFT-keyword）展开成 LEFT（保留原样，不做碱基映射）
    """
    tmp_seq = (modify_seq or "").upper()
    combo_re = build_combo_re()

    def combo_to_left(m: re.Match) -> str:
        # 只保留 LEFT，丢掉 -keyword
        return m.group(1).upper()

    tmp_seq = combo_re.sub(combo_to_left, tmp_seq)
    return tmp_seq


@transaction.atomic
def save_deliveries(df, duplex_id_map, username):
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
    if _sm_list:
        _sm_norm_re = re.compile(
            '|'.join(re.escape(m.keyword) for m in _sm_list),
            re.IGNORECASE,
        )
    else:
        _sm_norm_re = None

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
      #      print(d5)
            # 捕获序列最右侧的内容
            d3 = re.search(r'\[([^\[\]]*)\]$', full_seq)
       #     print(d3)
            delivery5 = d5.group(1) if d5 else ''
            delivery3 = d3.group(1) if d3 else ''
            modify_seq = re.sub(r'^\[.*?\]', '', full_seq)
            modify_seq = re.sub(r'\[.*?\]$', '', modify_seq)
         #   print(f"Processing row: {row['__original_line']}, full_seq: {full_seq}, modify_seq: {modify_seq[::-1]}")
            

            # 规范化：strip combo，替换修饰码为裸碱基，提取 naked_seq
            tmp_seq = normalize_tmp_seq_with_combo(modify_seq)  # 去 combo 并大写
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

            if not Sequence.objects.filter(seq=naked_seq).exists():
                all_registered = False

                # 更稳妥地计算当前组的原始行号列表
                group_lines = ",".join(str(r['__original_line']) for r in rows)

                unregistered_meg.append(f"{row['Project']} ➜ {full_seq} ➜ {naked_seq}")
                unregistered_log.append({
                    'Project': row['Project'],
                    'duplex_id': duplex_id,
                    '行号组': group_lines,
                    'origin_line': row['__original_line'],
                    'Modify_seq': full_seq,
                    'Unregistered': naked_seq,
                    '原因': '组内存在未注册序列，整组未上传'
                })

        if not all_registered:
            # 如果整组未注册，跳过后续处理
            continue

        seen_combinations = {}  # key: (base_id, delivery5, linker_seq, delivery3) → delivery_id

        # 处理每个详细行
        for item in detailed_rows:
            row = item['row']
            sequence_obj = Sequence.objects.get(seq=item['naked_seq'])
            base_id = sequence_obj.rm_code
            current_delivery5 = item['delivery5']
            current_delivery3 = item['delivery3']
            current_linker_seq = add_o_to_all_rules(item['modify_seq'])


            key = (base_id, current_delivery5, current_linker_seq, current_delivery3)

            # print(f"Key for this item: {key}")  # 调试输出
            # print(f"Seen combinations so far: {seen_combinations}")  # 调试输出

            # 优先查数据库中是否有重复
            duplicate = Delivery.objects.filter(
         #       id__startswith=base_id,
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
                linker_seq=add_o_to_all_rules(item['modify_seq']),
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


    if request.method == 'POST':
        try:
            df = parse_uploaded_csv(request)
            ss_groups, unpaired_ss_as = group_sequences(df)  # 获取未配对的 SS 和 AS
            repeated_ids, duplicate_meg = check_duplicates(df, ss_groups)
            duplex_id_map = assign_duplex_ids(df, ss_groups, repeated_ids)

            username = request.user.username
            upload_meg, upload_log, unregistered_meg, unregistered_log = save_deliveries(df, duplex_id_map, username)

            write_upload_log(upload_log, username)  # 可保留原日志逻辑
            unregistered_csv = write_unregistered_log(unregistered_log, username)
            request.session['unregistered_csv'] = unregistered_csv  # 💥 必须添加此行！

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
            repeated_ids, duplicate_meg = check_duplicates(df, ss_groups)
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
    优先读取数据库中 LmsUser 的 default_seq_type 字段（如有），
    否则回落到硬编码映射，最终默认 'SS'。
    """
    user_default_seq_map = {
        'Y2325': 'AS',
    }
    username = user.username if user.is_authenticated else ''
    return user_default_seq_map.get(username, 'SS')


def get_permitted_delivery_qs(user):
    """
    根据用户权限返回可见的 Delivery 查询集：
    - 超级管理员：全部
    - 普通用户：仅限 permissions_project 包含的项目
    - 无权限：空集
    """
    if user.is_superuser:
        return Delivery.objects.all()
    allowed = user.get_allowed_projects()
    if allowed:
        return Delivery.objects.filter(project__in=allowed)
    return Delivery.objects.none()


def get_attr(d, key):
    if isinstance(d, dict):
        return d.get(key, '')
    elif isinstance(d, Delivery):
        return getattr(d, key, '')
    return ''

def build_sequence_data(rm_code, seqinfo, sequence, deliveries, linker_seq, selected_seq_type,
                        dm_modules=None, color_map=None):
    """dm_modules / color_map 可由调用方预加载传入，避免循环内重复查询 DB。"""
    if not deliveries:
        deliveries = [{'delivery5': None, 'delivery3': None, 'date': None}]

    update_time = get_attr(deliveries[0], 'created_at') if deliveries else None
    formatted_update_time = update_time.strftime('%Y-%m-%d %H:%M') if update_time else None

    remark = (
        f"{seqinfo.Remark}\n{get_attr(deliveries[0], 'Remark')}"
        if seqinfo and deliveries else
        seqinfo.Remark if seqinfo else
        get_attr(deliveries[0], 'Remark') if deliveries else None
    )

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
        'modify_seq_colored': get_modify_seq_colored(linker_seq, selected_seq_type, seq_type_authoritative, dm_modules=dm_modules, color_map=color_map) if linker_seq and selected_seq_type else None,
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
    # 预加载 DeliveryModule（一次查询，供所有 build_sequence_data 调用复用）
    _dm_modules = list(DeliveryModule.objects.all())
    _color_map = get_color_map(modules=_dm_modules)

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
                    )
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
                )
                duplex_group_map[(project, duplex_id)].append(item)

    sequence_groups = []
    for (project, duplex_id), items in duplex_group_map.items():
        sorted_items = sorted(
            items,
            key=lambda x: x.get('seq_type') != 'SS',
        )
        sequence_groups.append({
            'project': project,
            'duplex_id': duplex_id,
            'items': sorted_items,
        })

    return sequence_groups


@login_required
def get_sequence_info(request):
    user_type = getattr(request.user, 'user_type', 'guest')
    selected_seq_type = request.GET.get('seq_type', get_user_default_seq_type(request.user))

    # allowed_projects：超管为全部，否则取用户权限列表
    if request.user.is_superuser:
        allowed_projects = sorted(filter(None, Delivery.objects.values_list('project', flat=True).distinct()))
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
    if selected_projects:
        safe_selected = [p for p in selected_projects if p in allowed_projects]
        if safe_selected:
            delivery_qs = delivery_qs.filter(project__in=safe_selected)
        else:
            delivery_qs = Delivery.objects.none()

    # === 搜索过滤 ===
    # 全局快速搜索（单框搜索多字段）
    q = request.GET.get('q', '').strip()

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

    if has_search:
        search_qs = delivery_qs

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

    sequence_groups = build_duplex_groups(delivery_qs, selected_seq_type)

    context = {
        'user_type': user_type,
        'sequence_groups': sequence_groups,
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
    delivery = get_object_or_404(Delivery, Q(id=query_id_tmp)&Q(seq_type=seq_type))  # 根据 query_id 获取 Delivery 对象
    query_id = delivery.sequence_id  # 获取该 Delivery 对应的 sequence_id
 #   print(f'3.{query_id}')

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

     # 获取所有不包含 seq_type 为 'duplex' 的 Sequence 数据（prefetch_related 避免 N+1 查询）
    sequences = Sequence.objects.exclude(seq_type='duplex').prefetch_related('target_info')

    sequence_list = []

    for seq in sequences:
        # 根据 seq_type 判断前缀
        if seq.seq_type == 'SS' :
            seq_prefix = 'SS_'
        elif seq.seq_type == 'AS':
            seq_prefix = 'AS_'
        else:
            seq_prefix = ''  # 如果没有匹配的 seq_type，设为空

        # 使用 prefetch_related 缓存获取 SeqInfo，避免 N+1 查询
        seq_info = seq.target_info.first()
        remark = seq_info.Remark if seq_info else ''  # 如果没有找到匹配的 SeqInfo，则 Remark 为空
        pos = seq_info.Pos if seq_info else ''  # 如果没有找到匹配的 SeqInfo，则 Position 为空
        Transcript = seq_info.Transcript if seq_info else ''  # 如果没有找到匹配的 SeqInfo，则 Transcript 为空
        

        # 格式化日期
        formatted_date = seq.created_at.strftime('%Y-%m-%d %H:%M') if seq.created_at else ''

        # 构建字典数据
        sequence_dict = {
            'rm_code': seq.rm_code,
            'seq_prefix': seq_prefix,
       #     'project': project,
            'seq': seq.seq,
            'pos': pos,
            'transcript': Transcript,
            'remark': remark,
            'reg_date': formatted_date,  # 假设 Sequence 模型中有 created_at 字段
        }

        # 将数据加入到 sequence_list
        sequence_list.append(sequence_dict)

    # 渲染页面并传递数据
    return render(request, 'reg_seq_list.html', {'sequence_list': sequence_list})

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
        edit_seq = request.POST.get('edit_project')
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
                part2 = getattr(seqinfo, 'Remark', '') if seqinfo else ''
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

    queryset = DeliveryModule.objects.all().values('id', 'keyword', 'type_code', 'Strand_MWs')
    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(page)

    return render(request, 'module_list.html', {
        'module_list': page_obj.object_list,
        'page_obj': page_obj,
        'page_size': page_size,
    })


@login_required
def edit_module(request):

    if not request.user.is_authenticated or not request.user.can_manage_modules():
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
            return redirect('/module_list/')
        else:
            # === 更新模式（通过 GET id 已加载 module） ===
            if keyword != module.keyword and DeliveryModule.objects.filter(keyword=keyword).exists():
                messages.warning(request, f'模块”{keyword}”已存在，请换一个名称。')
                return render(request, 'edit_module.html', {
                    'module': module,
                    'form_data': {'keyword': keyword, 'type_code': type_code, 'Strand_MWs': Strand_MWs},
                })
            module.keyword = keyword
            module.type_code = type_code
            module.Strand_MWs = Strand_MWs
            module.save()
            return redirect('/module_list/')

    return render(request, 'edit_module.html', {'module': module})



@login_required
def upload_modules(request):

    # 权限控制
    if not request.user.is_authenticated or not request.user.can_manage_modules():
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

    if not request.user.is_authenticated or not request.user.can_manage_modules():
        messages.error(request, '您没有权限删除模块！')
        return redirect('/module_list/')

    module_id = request.POST.get('id')
    try:
        module = DeliveryModule.objects.get(id=module_id)
        module.delete()
        return redirect('/module_list/')  # 推荐跳回列表页
    except DeliveryModule.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '模块不存在'})
    
# ── 序列修饰列表（SeqModule）──────────────────────────────────────────────────

@login_required
def seqmodule_list(request):
    page_size = int(request.GET.get('page_size', 20))
    page = int(request.GET.get('page', 1))

    queryset = SeqModule.objects.all().values('id', 'keyword', 'base_char', 'linker_connector')
    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(page)

    return render(request, 'seqmodule_list.html', {
        'seqmodule_list': page_obj.object_list,
        'page_obj': page_obj,
        'page_size': page_size,
    })


@login_required
def edit_seqmodule(request):
    if not request.user.is_authenticated or not request.user.can_manage_modules():
        messages.error(request, '您没有操作权限！')
        return redirect('/seqmodule_list/')

    module_id = request.GET.get('id')
    module = None

    if module_id:
        module = get_object_or_404(SeqModule, id=module_id)

    if request.method == 'POST':
        keyword = request.POST.get('keyword', '').strip()
        base_char = request.POST.get('base_char', '').strip()
        linker_connector = request.POST.get('linker_connector', 'o').strip() or 'o'

        if module is None:
            if SeqModule.objects.filter(keyword=keyword).exists():
                messages.warning(request, f'修饰模块"{keyword}"已存在，请勿重复添加。')
                return render(request, 'edit_seqmodule.html', {
                    'module': None,
                    'form_data': {'keyword': keyword, 'base_char': base_char, 'linker_connector': linker_connector},
                })
            SeqModule.objects.create(keyword=keyword, base_char=base_char or None, linker_connector=linker_connector)
            return redirect('/seqmodule_list/')
        else:
            if keyword != module.keyword and SeqModule.objects.filter(keyword=keyword).exists():
                messages.warning(request, f'修饰模块"{keyword}"已存在，请换一个名称。')
                return render(request, 'edit_seqmodule.html', {
                    'module': module,
                    'form_data': {'keyword': keyword, 'base_char': base_char, 'linker_connector': linker_connector},
                })
            module.keyword = keyword
            module.base_char = base_char or None
            module.linker_connector = linker_connector
            module.save()
            return redirect('/seqmodule_list/')

    return render(request, 'edit_seqmodule.html', {'module': module})


@login_required
@require_POST
def delete_seqmodule(request):
    if not request.user.is_authenticated or not request.user.can_manage_modules():
        messages.error(request, '您没有权限删除修饰模块！')
        return redirect('/seqmodule_list/')

    module_id = request.POST.get('id')
    try:
        module = SeqModule.objects.get(id=module_id)
        module.delete()
        return redirect('/seqmodule_list/')
    except SeqModule.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '修饰模块不存在'})


@login_required
def upload_seqmodules(request):
    if not request.user.is_authenticated or not request.user.can_manage_modules():
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
