from collections import defaultdict
import hashlib

from django.http import HttpResponseRedirect, HttpResponse, Http404, JsonResponse
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
import os, csv
from django.utils.timezone import now
from app01 import models
from .models import *
LmsUser = get_user_model()

import re, json
import logging
from django.utils import timezone
from io import StringIO
from django.conf import settings


# 处理空值
def clean_value(value):
        return None if pd.isna(value) or value == '' else value

def get_delivery_colored(seq: str):
    """
    给任意 delivery 序列添加颜色标记（不区分 5'/3'）
    返回：
        [{"char": ..., "type": ...}, ...]
    """
    # 正则匹配规则，包含需要标记的所有部分
    regex = r"C6-S-LP415|invAb|s|C6-S-40KPEG2|o|NH2-C6|cPrp|avb3-SM2|L4-C6|L96|P98|."
    
    # 颜色映射规则
    color_map = {
        'C6-S-LP415': 't1',
        'invAb': 't2',
        's': 's',
        'C6-S-40KPEG2': 't3',
        'o': 'o',
        'NH2-C6': 't4',
        'cPrp': 't5',
        'avb3-SM2': 't6',
        'L4-C6': 't7',
        'L96': 't8',
        'P98': 't9',
        
    }

    # 查找所有匹配的字符串
    matches = re.findall(regex, seq or "")

    # 通过 `re.sub` 移除空格，并返回颜色标记
    return [
        {
            "char": char.strip(),  # 去掉每个字符的前后空格
            "type": color_map.get(char.strip(), "unknown")  # 获取颜色类型
        }
        for char in matches
    ]

# ✅ 生成修饰序列的颜色标记
def get_modify_seq_colored(seq, seq_type):
    # 使用正则表达式来提取符合条件的片段
    sequence = re.findall(
        r'G\(moe\)|U\(moe\)|C\(moe\)|A\(moe\)|G\(OCF3\)|U\(OCF3\)|C\(OCF3\)|A\(OCF3\)|I|invab|GA02|GU02|GC02|TA12|TC12|TG12|TU0|ss|Af|Cf|Uf|Gf|Am|Cm|Um|Gm|dA|dT|dG|dC|dU|s|ss|o|[ACGUT]|.', seq or ""
    )

    # delivery = Delivery.objects.filter(linker_seq=seq).first()

    # if seq_type == 'AS':
    #     counter = 0
    # elif seq_type == 'SS':
    #     counter = int(delivery.naked_length) + 1 if delivery and delivery.naked_length else 22
    # else:
    #     counter = 0

    counter = 0

    result = []

   # print(f"Processing sequence: {seq}, type: {seq_type}, initial counter: {counter}")

    # 将匹配的字符按要求存储在结果中
    for char in sequence:
        if char in ['s', 'ss', 'o']:
            count = ""
        else:
            counter += 1
            count = counter

        result.append({
            "char": char,
            "type": (
                "evp" if char == '(EVP)' else
                "moe" if char in ['G(moe)', 'U(moe)', 'C(moe)', 'A(moe)'] else
                "OCF3" if char in ['G(OCF3)', 'U(OCF3)', 'C(OCF3)', 'A(OCF3)'] else
                "GNA" if char in ['GA02', 'GU02', 'GC02'] else
                "TNA" if char in ['TA12', 'TC12', 'TG12', 'TU0'] else
                "d" if char in ['dA', 'dT', 'dG', 'dC', 'dU'] else
                "f" if char in ['Af', 'Cf', 'Uf', 'Gf'] else
                "m" if char in ['Am', 'Cm', 'Um', 'Gm'] else
                "I" if char in ['I'] else
                "invab" if char in ['invab'] else
                "normal" if char in ['A', 'C', 'G', 'U'] else
                "o" if char == 'o' else
                "s" if char == 's' else
                "ss" if char == 'ss' else
                "unknown"
            ),
            "count": count
        })

    # Add grouping and reversal logic for SS type
    if seq_type == 'SS':
        # Group elements with following 'ss', 's', 'o'
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
   #         print(f"Processing item: {item}, current_group: {current_group}")

        if current_group is not None:
            groups.append(current_group)
  #          print(f"Grouped SS sequence: {groups}")   
        
        # Reverse groups and flatten
        reversed_groups = reversed(groups)
  #      print(list(reversed_groups))

        new_result = []
        for group in reversed_groups:
            
            new_result.append(group['main'])
            new_result.extend(group['subs'])
        result = new_result

     #   print(f"Reversed SS sequence: {result}")

    return result


# 用户登录视图
def login_view(request):
    if request.method == 'POST' and request.POST:
        username = request.POST.get("username")
        password = request.POST.get("password")

        # 验证用户
        print(f"Submitted username: {username}, password: {password}")
        user = authenticate(request, username=username, password=password)

        if user:
            # 使用 login() 登录用户
            login(request, user)

            # 获取用户的跳转 URL
            return redirect('/seq_list/')  # 登录成功后跳转到书籍列表页面
        else:
            # 登录失败，返回错误提示
            return HttpResponse("""
                <script>
                    alert('用户名或密码错误！');
                    window.location.href = '/login/';
                </script>
            """)

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
            return HttpResponse("""
                <script>
                    alert('用户名已存在！');
                    window.location.href = '/register/';
                </script>
            """)

        if LmsUser.objects.filter(email=email).exists():
            return HttpResponse("""
                <script>
                    alert('邮箱已注册！');
                    window.location.href = '/register/';
                </script>
            """)

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
def author_list(request):
    user = LmsUser.objects.all()
    return render(request, 'auth_list.html', {'user_list': user})

# 添加用户
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

    # 获取项目列表
    project_choices = SeqInfo.project_choices

    return render(request, 'author_add.html', {'project_choices': project_choices})

# 删除用户
def drop_author(request):
    if not request.user.is_authenticated or (not request.user.is_superuser and not request.user.is_admin):
        return HttpResponse("""
            <script>
                alert('您没有权限删除用户信息！');
                window.location.href = '/author_list/';
            </script>
        """, content_type="text/html; charset=utf-8")

    drop_id = request.GET.get('id')
    confirm = request.GET.get('confirm')  # 是否已经确认删除

    if not confirm:
        # 第一次访问，弹出确认框，要求用户确认
        return HttpResponse(f"""
            <script>
                if (confirm('确定要删除该用户吗？此操作不可恢复！')) {{
                    window.location.href = '/drop_author/?id={drop_id}&confirm=1';
                }} else {{
                    window.location.href = '/author_list/';
                }}
            </script>
        """, content_type="text/html; charset=utf-8")

    # 已确认删除
    try:
        drop_obj = LmsUser.objects.get(id=drop_id)
        if str(request.user.id) == drop_id:
            return HttpResponse("""
                <script>
                    alert('不能删除当前登录的管理员账户！');
                    window.location.href = '/author_list/';
                </script>
            """, content_type="text/html; charset=utf-8")
        # 不能删除任何管理员账号（is_superuser 或 is_admin）
        if drop_obj.is_superuser or getattr(drop_obj, 'is_admin', False):
            return HttpResponse("""
                <script>
                    alert('不能删除管理员账号！');
                    window.location.href = '/author_list/';
                </script>
            """, content_type="text/html; charset=utf-8")
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

        return HttpResponse("""
            <script>
                alert('人员已被成功删除！');
                window.location.href = '/author_list/';
            </script>
        """, content_type="text/html; charset=utf-8")
    except LmsUser.DoesNotExist:
        return HttpResponse("""
            <script>
                alert('用户不存在或已被删除');
                window.location.href = '/author_list/';
            </script>
        """, content_type="text/html; charset=utf-8")

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

        # ✅ 修改成功后使用 JavaScript 弹窗 + 跳转
        return HttpResponse("""
            <script>
                alert('密码修改成功，请重新登录！');
                window.location.href = '/login/';
            </script>
        """)
    
    return render(request, 'change_password.html')

# 编辑用户
def edit_author(request):
    # 非管理员禁止访问
    if not request.user.is_authenticated or (not request.user.is_superuser and not request.user.is_admin):
        return HttpResponse("""
            <script>
                alert('您没有权限编辑用户信息！');
                window.location.href = '/author_list/';
            </script>
        """, content_type="text/html; charset=utf-8")

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

def drop_book(request):
    
    # 始终显示需要OA审批的提示信息
    return HttpResponse("""
        <script>
            alert('您没有权限删除序列信息，如需删除，请走OA审批！');
            window.location.href = '/book_list/';
        </script>
    """)

# 编辑序列
def edit_seq(request):
    '''
    if not request.user.is_authenticated or (not request.user.is_superuser and not request.user.is_admin):
        return HttpResponse("""
            <script>               
                alert('您没有权限编辑序列信息！');
                window.location.href = '/seq_list';
            </script>
        """)
    '''
    
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

            log_message = f"用户 {request.user.username} 在 {new_datetime} 编辑了项目 {delivery.project}中ID为 {delivery.sequence_id} 的序列 ，修改内容为: "
            log_details = []

            for change in changes:
                log_details.append(f"{change}")

            if log_details:
                log_message += "\n" + "\n".join(log_details) + "\n========================================================================\n"
                logger.info(log_message)

            messages.success(request, "序列信息已成功更新！")
            return redirect('seq_list')  # 返回列表页

        else:
            # **如果没有变化，提示用户**
            messages.info(request, "您未做任何修改。")
            return redirect('seq_list')  # 返回列表页
        
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
                    seqinfo_SS = SeqInfo.objects.filter(seq=SS).first()
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
                            seq=SS,
                            Transcript=Transcript,
                   #         Target=Target,
                            Pos=Pos,
                   #         parents=Parents,
                            Remark=Remarks,
                            created_at=created_at
                        )

                    # 更新或创建 AS 对应的 SeqInfo
                    seqinfo_AS = SeqInfo.objects.filter(seq=AS).first()
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
                            seq=AS,
                            Transcript=Transcript,
                       #     Target=Target,
                            Pos=Pos,
                            # parents=Parents,
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

# 上传序列信息
def upload_seq_info(request):
    if request.method == 'POST':
        uploaded_file = request.FILES.get('file')

        if not uploaded_file:
            messages.error(request, "未选择文件！")
            return render(request, 'upload_seq_info.html')

        if not uploaded_file.name.endswith('.csv'):
            messages.error(request, "请上传 CSV 文件！")
            return render(request, 'upload_seq_info.html')

        try:
            # 使用 pandas 读取 CSV 文件
            df = pd.read_csv(uploaded_file)

            # 检查必需列
            required_columns = ['Project', 'seq', 'Transcript', 'Target', 'Pos', 'Parents']
            if not all(col in df.columns for col in required_columns):
                messages.error(request, f"文件格式错误，必须包含列: {', '.join(required_columns)}")
                return render(request, 'upload_seq_info.html')            

            duplicate_meg = []  # 用于存储重复的序列信息
            upload_meg = []  # 用于存储上传的序列信息
            unregistered_meg = []  # 存储未注册的序列

            # 遍历并保存数据到数据库
            for _, row in df.iterrows():
                cleaned_row = {col: clean_value(row[col]) for col in ['Project', 'seq', 'Transcript', 'Target', 'Pos', 'Parents']}
         #       print(cleaned_row['seq'])
                project = cleaned_row['Project']
                seq_input = cleaned_row['seq']  # 用户输入的序列
                Transcript = cleaned_row['Transcript']
                Target = cleaned_row['Target']
                Pos = cleaned_row['Pos']
                parents = cleaned_row['Parents']
          #      Remarks = cleaned_row['Remarks']
                created_at = timezone.now().strftime('%Y-%m-%d %H:%M:%S')  # 获取当前时间
                
     #           print(seq_input, project, Transcript, Target, Pos, parents, Remarks)

                
                # 查找已注册的 Sequence 记录
                sequence = Sequence.objects.filter(seq=seq_input).first()
                if not sequence:
                    unregistered_meg.append(seq_input)
                    continue  # 跳过此循环，继续检查下一个序列

                # 查找是否已有 SeqInfo 记录
                seq_info = SeqInfo.objects.filter(seq=seq_input).first()
                    
                if seq_info:
                    # 解析已有数据（用 set() 进行去重）
                    existing_values ={
                        "Target": set(seq_info.Target.split(', ')) if seq_info.Target else set(),
                        "Pos": set(seq_info.Pos.split(", ")) if seq_info.Pos else set(),
                        "parents": set(seq_info.parents.split(", ")) if seq_info.parents else set(),
                        "project": set(seq_info.project.split(", ")) if seq_info.project else set(),
                        "Transcript": set(seq_info.Transcript.split(", ")) if seq_info.Transcript else set()
                    } 

                    # 解析上传数据（避免重复）
                    new_values = {
                        "Target":  set(Target.split(";")) if Target else set(),
                        "Pos": set(Pos.split(";")) if Pos else set(),
                        "parents": set(parents.split(";")) if parents else set(),
                        "project": set(project.split(";")) if project else set(),
                        "Transcript": set(Transcript.split(";")) if Transcript else set()
                    }

                    # 检查是否所有字段都已包含
                    is_duplicate = all(new_values[field].issubset(existing_values[field]) for field in new_values)

                    if is_duplicate:
                        duplicate_meg.append(f"{seq_input}")
                    else:
                        # 更新 SeqInfo 记录
                        for field in new_values:
                            existing_values[field] |= new_values[field]  # 合并数据（去重）
                        #    print(existing_values[field])

                        seq_info.Target = ", ".join(existing_values["Target"])
                        seq_info.Pos = ", ".join(existing_values["Pos"])
                        seq_info.parents = ", ".join(existing_values["parents"])
                        seq_info.project = ", ".join(existing_values["project"])
                        seq_info.Transcript = ", ".join(existing_values["Transcript"])
             #           seq_info.Remark = f"{seq_info.Remark}, {Remarks}" if seq_info.Remark else Remarks
                        seq_info.save()

                        upload_meg.append(f"{seq_input}")
                    
                else:
                    # 创建 SeqInfo 对象并与 Sequence 关联
                    SeqInfo.objects.create(
                        sequence = sequence,
                        seq = seq_input,
                        Target = Target,
                        Pos = Pos,
                        parents = parents,
                        project = project,
                        Transcript = Transcript,
                        Remark = Remarks,
                        created_at = created_at,
                    )
                    upload_meg.append(f"{seq_input}")
                
            # 反馈上传信息
            error_messages = []

            if duplicate_meg:
                error_messages.append(f"{'; '.join(duplicate_meg)}，已有信息，如需修改请点击编辑！")
            if unregistered_meg:
                error_messages.append(f"{'; '.join(unregistered_meg)}，未注册，请先注册！")

            if error_messages:
                messages.error(request, " ".join(error_messages))

            if upload_meg:
                messages.success(request, f"序列信息上传成功：{'; '.join(upload_meg)}")
                return render(request, 'upload_seq_info.html', {'success': True})
            else:
                messages.error(request, "无新的序列信息上传！")
                return render(request, 'upload_seq_info.html')
                #return redirect('/upload_books/')  # 上传成功后跳转到 book_list.html

        except Exception as e:
            messages.error(request, f"文件处理失败：{e}")
            return render(request, 'upload_seq_info.html')

    return render(request, 'upload_seq_info.html')

# 遍历modify_seq, 遇见 "m" 或 "f" 在后面添加 "o"，并处理 "(EVP)A", "(EVP)U", "(EVP)C", "(EVP)G", "(EVP)T"
def add_o_to_all_rules(modify_seq):
    linker_seq = ""
    i = 0

    while i < len(modify_seq):
        char = modify_seq[i]

        # 1. "I" 后面加 "o"
        if char == 'I' and not (i + 1 < len(modify_seq) and modify_seq[i + 1] == 's'):
            linker_seq += char + 'o'

        elif char in ['m', 'f'] and not (i + 1 < len(modify_seq) and modify_seq[i + 1] == 's'):
            linker_seq += char + 'o'

        # 2. "(EVP)A/U/C/G/T/A(moe)/U(moe)/C(moe)/G(moe)后面加 "o"
        elif i + 5 < len(modify_seq) and modify_seq[i:i+6].upper() in [
            '(EVP)A', '(EVP)U', '(EVP)C', '(EVP)G', '(EVP)T','A(MOE)', 'U(MOE)', 'C(MOE)', 'G(MOE)', 'T(MOE)', 
        ]:
            # 判断紧跟  后面那个字符是不是 's'
            if i + 6 >= len(modify_seq) or modify_seq[i + 6] != 's':
                linker_seq += modify_seq[i:i+6] + 'o'
            else:
                linker_seq += modify_seq[i:i+6]  # 不加 'o'
            i += 5

        # 3. GA02/GC02/GU02/TA12/TG12/TC12 后面加 "o"
        elif i + 3 < len(modify_seq) and modify_seq[i:i+4].upper() in [
            'GA02', 'GC02', 'GU02','TA12','TC12','TG12'
        ]:
            # 判断紧跟后面那个字符是不是 's'
            if i + 4 >= len(modify_seq) or modify_seq[i + 4] != 's':
                linker_seq += modify_seq[i:i+4] + 'o'
            else:
                linker_seq += modify_seq[i:i+4]  # 不加 'o'
            i += 3

        # 4. TU0 后面加 "o"
        elif i + 2 < len(modify_seq) and modify_seq[i:i+3].upper() in [
            'TU0'
        ]:
             # 判断紧跟后面那个字符是不是 's'
            if i + 3 >= len(modify_seq) or modify_seq[i + 3] != 's':
                linker_seq += modify_seq[i:i+3] + 'o'
            else:
                linker_seq += modify_seq[i:i+3]  # 不加 'o'
            i += 2

        # 5. dA/dT/dU/dG/dC 后面加 "o"，除非 i+2 是 's'
        elif i + 1 < len(modify_seq) and modify_seq[i:i+2] in [
            'dA', 'dT', 'dU', 'dG', 'dC'
        ]:
            # 判断紧跟 dX 后面那个字符是不是 's'
            if i + 2 >= len(modify_seq) or modify_seq[i + 2] != 's':
                linker_seq += modify_seq[i:i+2] + 'o'
            else:
                linker_seq += modify_seq[i:i+2]  # 不加 'o'
            i += 1


        # 6. A(OCF3)/U(OCF3)/C(OCF3)/G(OCF3) 后面加 "o"
        elif i + 6 < len(modify_seq) and modify_seq[i:i+7].upper() in [
            'A(OCF3)', 'U(OCF3)', 'C(OCF3)', 'G(OCF3)', 'T(OCF3)',
        ]:
             # 判断紧跟后面那个字符是不是 's'
            if i + 7 >= len(modify_seq) or modify_seq[i + 7] != 's':
                linker_seq += modify_seq[i:i+7] + 'o'
            else:
                linker_seq += modify_seq[i:i+7]  # 不加 'o'
            i += 6

        # 7. "invab "o"
        elif i + 4 < len(modify_seq) and modify_seq[i:i+5].upper() in [
            'INVAB', 
        ]:
             # 判断紧跟后面那个字符是不是 's'
            if i + 5 >= len(modify_seq) or modify_seq[i + 5] != 's':
                linker_seq += modify_seq[i:i+5] + 'o'
            else:
                linker_seq += modify_seq[i:i+5]  # 不加 'o'
            i += 4

        else:
            linker_seq += char

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

    required_columns = ['Batch', 'Project', 'Target', 'Seq_type', 'Modify_seq', 'Strand_MWs', 'Parents', 'Remarks']
    if not all(col in df.columns for col in required_columns):
        raise ValueError(f"文件格式错误，必须包含列: {', '.join(required_columns)}")

    return df

def group_sequences(df):
    ss_groups = []  # 用于存储有效的 SS+AS 组合
    invalid_ss_as = []  # 用于存储无效的 SS 和 AS
    grouped = df.groupby('Batch')  # 按照批次分组数据

    for batch, group in grouped:
        # 按 __row_id 排序后处理
        group_sorted = group.sort_values(by='__row_id').reset_index(drop=True)
        i = 0

        while i < len(group_sorted):
            row = group_sorted.iloc[i]
            row_id = row['__row_id']
            original_line = row['__original_line']
            seq_type = row['Seq_type'].strip().upper()
            modify_seq = row['Modify_seq']

            if seq_type == 'SS':
                temp_group = [row_id]

                if i + 1 < len(group_sorted):
                    next_row = group_sorted.iloc[i + 1]
                    next_seq_type = next_row['Seq_type'].strip().upper()

                    if next_seq_type == 'AS':
                        temp_group.append(next_row['__row_id'])
                        i += 1  # 跳过 AS，因为已经配对
                        ss_groups.append((int(batch), row['Project'], temp_group))
                    else:
                        invalid_ss_as.append(f"原始行 {original_line}, {modify_seq}, 无效SS：没有 AS 配对")
                else:
                    invalid_ss_as.append(f"原始行 {original_line}, {modify_seq}, 无效SS：没有 AS 配对")

            elif seq_type == 'AS':
                invalid_ss_as.append(f"原始行 {original_line}, {modify_seq}, 无效AS：没有配对的 SS")

            i += 1

    return ss_groups, invalid_ss_as

# 同一批次，同一项目，统一靶点，算重复
def check_duplicates(df, ss_groups):
    repeated_ids = set()
    duplicate_meg = []

    # 同批次内组合查重缓存
    seen_seqs_in_batch = set()

    for batch, project, group in ss_groups:
        modify_seqs, delivery_keys, row_ids, targets = [], [], [], []

        for row_id in group:
            row = df.loc[row_id]
            full_seq = row['Modify_seq']

            # 提取 5' 和 3' 修饰
            d5 = re.search(r'^\[([^\[\]]*)\]', full_seq)
            d3 = re.search(r'\[([^\[\]]*)\]$', full_seq)
            d5 = d5.group(1) if d5 else ''
            d3 = d3.group(1) if d3 else ''

            # 去除 5' 和 3' 修饰，保留中间序列
            clean_seq = re.sub(r'^\[.*?\]', '', full_seq)
            clean_seq = re.sub(r'\[.*?\]$', '', clean_seq)

            modify_seqs.append((clean_seq, d5, d3))
            delivery_keys.append(full_seq)
            row_ids.append(row_id)
            targets.append(row['Target'])

        #    print(f'modify_seqs: {modify_seqs},row_ids: {row_id},  targets: {targets}')

        for i in range(0, len(modify_seqs), 2):
            if i + 1 < len(modify_seqs):
                ss_clean_seq, ss_d5, ss_d3 = modify_seqs[i]
                as_clean_seq, as_d5, as_d3 = modify_seqs[i + 1]
                ss_full_seq = delivery_keys[i]
                as_full_seq = delivery_keys[i + 1]
                target = targets[i]

                # 当前组组合键：项目+批次+靶点+SS+AS
                combo_key = (
                    project, batch, target,
                    ss_clean_seq, ss_d5, ss_d3,
                    as_clean_seq, as_d5, as_d3
                )

                # 1️⃣ 批次内重复判断
                if combo_key in seen_seqs_in_batch:
                    duplicate_meg.append(
                        f"重复SS+AS组（项目: {project}，批次: {batch}，靶点: {target}）："
                        f"{ss_full_seq} + {as_full_seq} 在当前批次中重复"
                    )
                    repeated_ids.add(row_ids[i])
                    repeated_ids.add(row_ids[i + 1])
                else:
                    seen_seqs_in_batch.add(combo_key)

                # 2️⃣ 与数据库比较（限制在当前批次前缀一致时才查重）
                current_batch_prefix = str(batch).zfill(2)
        #        print(f"当前批次前缀: {current_batch_prefix}")

                dup_id_list = Delivery.objects.filter(
                    project=project,
                    Target=target,
                    modify_seq=ss_clean_seq,
                    delivery5=ss_d5,
                    delivery3=ss_d3
                ).values_list('duplex_id', flat=True)

            
                for dup_id in dup_id_list:
                    # 获取数据库中 duplex_id 的批次前缀
                    try:
                        db_batch_prefix = dup_id.split("_")[1][:2]
                    except IndexError:
                        continue  # 格式错误，跳过

                    # 只有批次前缀一致才比较
                    if db_batch_prefix != current_batch_prefix:
                        continue

                    exists_as = Delivery.objects.filter(
                        project=project,
                        Target=target,
                        modify_seq=as_clean_seq,
                        delivery5=as_d5,
                        delivery3=as_d3,
                        duplex_id=dup_id
                    ).exists()

                    if exists_as:
                        duplicate_meg.append(
                            f"重复SS+AS组（项目: {project}，批次: {batch}，靶点: {target}）："
                            f"{ss_full_seq} + {as_full_seq} 与数据库中已有记录重复（duplex_id: {dup_id}）"
                        )
                        repeated_ids.add(row_ids[i])
                        repeated_ids.add(row_ids[i + 1])
                        break  # 找到即退出查找
                
            #    print(duplicate_meg)

    return repeated_ids, duplicate_meg


def assign_duplex_ids(df, ss_groups, repeated_ids):
    duplex_id_map = {}
    batch_project_groups = defaultdict(list)

    for batch, project, group in ss_groups:
        if not repeated_ids.intersection(group):
            batch_project_groups[(project, int(batch))].append(group)

    for (project, batch), valid_groups in batch_project_groups.items():
        batch_str = f"{batch:02d}"
        prefix = f"{project}_{batch_str}"

        # 只匹配符合“项目_批次+4位数字”的duplex_id
        pattern = re.compile(rf"^{re.escape(prefix)}(\d{{4}})$")

        existing_ids = Delivery.objects.filter(
            project=project,
            duplex_id__startswith=prefix
        ).values_list('duplex_id', flat=True)

        existing_numbers = [
            int(m.group(1)) for d in existing_ids if (m := pattern.match(d))
        ]

        next_number = max(existing_numbers, default=0) + 1

        for group in valid_groups:
            serial = f"{next_number:04d}"
            duplex_id = f"{prefix}{serial}"  # e.g. BPR-307_010001
            for row_id in group:
                duplex_id_map[row_id] = duplex_id
            next_number += 1

    return duplex_id_map

def save_deliveries(df, duplex_id_map, username):
    upload_log = []
    upload_meg = []
    unregistered_meg = []  
    unregistered_log = []

    # 构建：duplex_id → [row1, row2]
    duplex_groups = defaultdict(list)
    for row_id, duplex_id in duplex_id_map.items():
        duplex_groups[duplex_id].append(df.loc[df['__row_id'] == row_id].iloc[0])

    for duplex_id, rows in duplex_groups.items():
        all_registered = True
       # naked_seqs = []
        detailed_rows = []

        for row in rows:
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
            

            tmp_seq = modify_seq.upper()
            tmp_seq = re.sub(r'GA02', 'A', tmp_seq)
            tmp_seq = re.sub(r'GC02', 'C', tmp_seq)
            tmp_seq = re.sub(r'GU02', 'U', tmp_seq)
            tmp_seq = re.sub(r'TA12', 'A', tmp_seq)
            tmp_seq = re.sub(r'TC12', 'C', tmp_seq)
            tmp_seq = re.sub(r'TG12', 'G', tmp_seq)
            tmp_seq = re.sub(r'TU0', 'U', tmp_seq)
            tmp_seq = re.sub(r'\(.*?\)', '', tmp_seq)
            matches = re.findall(r'(INVAB|[AUGCTI])', tmp_seq)
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

        for item in detailed_rows:
            row = item['row']
            Delivery.objects.create(
                sequence=Sequence.objects.get(seq=item['naked_seq']),
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
                'Modified_Sequence': item['full_seq']
            })

    return upload_meg, upload_log, unregistered_meg, unregistered_log


def write_upload_log(upload_log, username):
    user_dir = os.path.join('logs', username)
    os.makedirs(user_dir, exist_ok=True)
    filepath = os.path.join(user_dir, f'{username}_upload_log.csv')

    with open(filepath, 'a', encoding='utf-8', newline='') as log_file:
        fieldnames = ['Time', 'User', 'Project', 'duplex_id', 'Type', 'Modified_Sequence']
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

def get_attr(d, key):
    if isinstance(d, dict):
        return d.get(key, '')
    elif isinstance(d, Delivery):
        return getattr(d, key, '')
    return ''

def build_sequence_data(rm_code, seqinfo, sequence, deliveries, linker_seq):
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

    return {
        'rm_code': rm_code,
      #  'seq_type': sequence.seq_type if sequence else None,
        'seq_prefix': (
            "RA_" if sequence and sequence.seq_type == "AS"
            else "RS_" if sequence and sequence.seq_type == "SS"
            else "RM_" if sequence and sequence.seq_type == "duplex"
            else ""
        ),
        'seq': sequence.seq if sequence else None,
        'Project': get_attr(deliveries[0], 'project') if deliveries else None,
        'Transcript': seqinfo.Transcript if seqinfo else None,
        #'Target': seqinfo.Pos if seqinfo else None,
        'Pos': seqinfo.Pos if seqinfo else None,
        'Remark': remark,
        'formatted_update_time': formatted_update_time,
        'linker_seq': linker_seq,
        'modify_seq_colored': get_modify_seq_colored(linker_seq, sequence.seq_type) if linker_seq and sequence else None,
        'deliveries': [
            {
                'duplex_id': getattr(d, 'duplex_id', None),
                'Parents': getattr(d, 'parents', None),
                'Target': getattr(d, 'Target', None),
                'Seq_type': getattr(d, 'seq_type', None),
                'delivery5': getattr(d, 'delivery5', None),
                'delivery3': getattr(d, 'delivery3', None),
                'Strand_MWs': getattr(d, 'Strand_MWs', None),
                'delivery3_colored': get_delivery_colored(get_attr(d, 'delivery3')),
                'delivery5_colored': get_delivery_colored(get_attr(d, 'delivery5')),
            }
            for d in deliveries
        ]
    }


def get_sequence_info(request):
    permissions_projects = getattr(request.user, 'permissions_project', '')
    user_type = getattr(request.user, 'user_type', 'guest')

    if request.user.is_superuser:
        delivery_qs = Delivery.objects.all()
    elif permissions_projects:
        allowed_projects = [p.strip() for p in permissions_projects.split(',')]
        delivery_qs = Delivery.objects.filter(project__in=allowed_projects)
    else:
        delivery_qs = Delivery.objects.none()

    rmcode_to_seqid = {}
    delivery_map = defaultdict(list)

    for d in delivery_qs:
        if d.id and d.sequence_id:
            rmcode_to_seqid[d.id] = d.sequence_id
            delivery_map[d.id].append(d)

    rm_codes = list(rmcode_to_seqid.keys())
    sequence_ids = list(set(rmcode_to_seqid.values()))

    sequence_map = {
        s.rm_code: s for s in Sequence.objects.filter(rm_code__in=sequence_ids)
    }
    seqinfo_map = {
        s.sequence_id: s for s in SeqInfo.objects.filter(sequence_id__in=sequence_ids)
    }

    # 分组数据结构，key: duplex_id, value: list of items
    # ✅ 正确分组结构
    duplex_group_map = defaultdict(list)

    for rm_code in rm_codes:
        sequence_id = rmcode_to_seqid[rm_code]
        sequence = sequence_map.get(sequence_id)
        seqinfo = seqinfo_map.get(sequence_id)
        deliveries = delivery_map.get(rm_code, [])

        # ✅ 改成按 project + duplex_id 分组
        grouped_deliveries = defaultdict(list)
        for d in deliveries:
            project = getattr(d, 'project', None)
            duplex_id = getattr(d, 'duplex_id', None)
            if project and duplex_id:
                grouped_deliveries[(project, duplex_id)].append(d)

        # ✅ 每组生成 item
        for (project, duplex_id), group_deliveries in grouped_deliveries.items():
            linker_seqs = [d.linker_seq for d in group_deliveries if getattr(d, 'linker_seq', None)]

            if linker_seqs:
                for linker_seq in linker_seqs:
                    item = build_sequence_data(
                        rm_code=rm_code,
                        seqinfo=seqinfo,
                        sequence=sequence,
                        deliveries=group_deliveries,
                        linker_seq=linker_seq
                    )
                    duplex_group_map[(project, duplex_id)].append(item)
            else:
                item = build_sequence_data(
                    rm_code=rm_code,
                    seqinfo=seqinfo,
                    sequence=sequence,
                    deliveries=group_deliveries,
                    linker_seq=None
                )
                duplex_group_map[(project, duplex_id)].append(item)

    # 更新 sequence_groups，包含 project 和 duplex_id
    sequence_groups = []

    for (project, duplex_id), items in duplex_group_map.items():
        # 按照 SS -> AS 排序（默认 SS 在前）
        sorted_items = sorted(
            items,
            key=lambda item: (
                item['deliveries'][0]['Seq_type'] != 'SS'  # SS 为 False, AS 为 True
                if item['deliveries'] else True
            )
        )

        sequence_groups.append({
            'project': project,
            'duplex_id': duplex_id,
            'items': sorted_items,
        })
    

    context = {
        'user_type': user_type,
        'sequence_groups': sequence_groups,
    }

    return render(request, 'seq_list.html', context)

def cor_seq(request):
   
    query_id_tmp  = request.GET.get('id')  # 获取 URL 参数
   # print(query_id_tmp)
   # print(query_id)
    
    seq_type = request.GET.get('seq_type')  # 获取 URL 参数
   # print(f'1,{seq_type}')
  #  print(query_prefix)
    #seq_prefix = request.GET.get('seq_prefix', '')  # 获取 seq_prefix 参数

    # 获取当前用户的 'permissions_project' 字段，存储允许查看的项目号
    permissions_projects = getattr(request.user, 'permissions_project', '')
    # 获取用户类型（默认为 'guest'）
    user_type = getattr(request.user, 'user_type', 'guest')

    # 获取权限范围（项目过滤）
    if request.user.is_superuser:
        # 超级管理员可见全部
        delivery_qs = Delivery.objects.all()
    elif permissions_projects:
        allowed_projects = [p.strip() for p in permissions_projects.split(',')]
        delivery_qs = Delivery.objects.filter(project__in=allowed_projects)
    else:
        delivery_qs = Delivery.objects.none()

    # 获取当前用户可见的序列ID（以交付表为基础）
    visible_seq_ids = delivery_qs.values_list('sequence_id', flat=True)
    
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


    # --------------------------
    # 3. 获取相关表数据
    # --------------------------

    related_ids = list(related_ids)  # 将查询结果转换为列表
    related_ids.insert(0, query_id_tmp)  # 将当前查询的 ID 添加到列表中
    
   # print(related_ids)

    delivery_qs = Delivery.objects.filter(id__in=related_ids)

    # 获取所有对应的 sequence_id
    all_sequence_ids = delivery_qs.values_list('sequence_id', flat=True)

    #  查询 SeqInfo 和 Sequence 表
    seqinfo_qs = SeqInfo.objects.filter(sequence_id__in=all_sequence_ids)
    sequence_qs = Sequence.objects.filter(rm_code__in=all_sequence_ids)  # 假设 rm_code = sequence_id


    # --------------------------
    # 4. 构建映射（同 get_sequence_info）
    # --------------------------
    rmcode_to_seqid = {}
    delivery_map = defaultdict(list)

    for d in delivery_qs:
        if d.id and d.sequence_id:
            rmcode_to_seqid[d.id] = d.sequence_id
            delivery_map[d.id].append(d)

    sequence_map = {
        s.rm_code: s for s in sequence_qs
    }

    seqinfo_map = {
        s.sequence_id: s for s in seqinfo_qs
    }

    # --------------------------
    # 5. 构建最终展示数据
    # --------------------------
    seq_list = []

    for rm_code, sequence_id in rmcode_to_seqid.items():
        sequence = sequence_map.get(sequence_id)
        seqinfo = seqinfo_map.get(sequence_id)
        deliveries = delivery_map.get(rm_code, [])

        linker_seqs = [d.linker_seq for d in deliveries if getattr(d, 'linker_seq', None)]

        if linker_seqs:
            for linker_seq in linker_seqs:
                seq_list.append(build_sequence_data(
                    rm_code=sequence_id,
                    seqinfo=seqinfo,
                    sequence=sequence,
                    deliveries=deliveries,
                    linker_seq=linker_seq
                ))
        else:
            seq_list.append(build_sequence_data(
                rm_code=sequence_id,
                seqinfo=seqinfo,
                sequence=sequence,
                deliveries=deliveries,
                linker_seq=None
            ))

    # --------------------------
    # 6. 渲染页面
    # --------------------------
    user_type = getattr(request.user, 'user_type', 'guest')

    return render(request, 'cor_seq.html', {
        'user_type': user_type,
        'sequence_list': seq_list,
        'query_id': query_id,
    })

def reg_seq_list(request):

     # 获取所有不包含 seq_type 为 'duplex' 的 Sequence 数据
    sequences = Sequence.objects.exclude(seq_type='duplex')

    sequence_list = []

    for seq in sequences:
        # 根据 seq_type 判断前缀
        if seq.seq_type == 'SS' or seq.seq_type == 'RS':
            seq_prefix = 'RS_'
        elif seq.seq_type == 'AS':
            seq_prefix = 'RA_'
        else:
            seq_prefix = ''  # 如果没有匹配的 seq_type，设为空

        # 根据 rm_code 获取 SeqInfo 的 Remark
        seq_info = SeqInfo.objects.filter(sequence_id=seq.rm_code).first()
        remark = seq_info.Remark if seq_info else ''  # 如果没有找到匹配的 SeqInfo，则 Remark 为空
        pos = seq_info.Pos if seq_info else ''  # 如果没有找到匹配的 SeqInfo，则 Position 为空
        Transcript = seq_info.Transcript if seq_info else ''  # 如果没有找到匹配的 SeqInfo，则 Transcript 为空
   #     project = seq_info.project if seq_info else ''  # 如果没有找到匹配的 SeqInfo，则 Project 为空
        

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

def edit_reg_seq(request):
    '''
    if not request.user.is_authenticated or (not request.user.is_superuser and not request.user.is_admin):
        return HttpResponse("""
            <script>               
                alert('您没有权限编辑序列信息！');
                window.location.href = '/seq_list';
            </script>
        """)
    '''
    
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
            Seq.save
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
        columns = json.loads(selected_columns)
    except json.JSONDecodeError:
        return HttpResponse("参数格式错误", status=400)

    query = Q()
    for duplex_id, seq_type in zip(ids, types):
        query |= Q(duplex_id=duplex_id, seq_type=seq_type)

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
            if col_lc == 'remark':
                val = ''
                part1 = getattr(d, 'Remark', '') or ''
                part2 = getattr(seqinfo, 'Remark', '') if seqinfo else ''
                val = f"{part1}\n{part2}".strip("\n") if (part1 or part2) else ''
      #          print(val)
            
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
