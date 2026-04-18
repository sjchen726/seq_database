"""bms URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path

from app01 import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.login_view),                          # 根路径 → 登录页面
    path('login/', views.login_view, name='login'),      # 登录动作
    path('signup/', views.register_view, name='signup'),     # 用户注册页面
    path('register/', views.register_view, name='register'),     # 用户注册页面

    path('seq_list/', views.get_sequence_info, name='seq_list'),         # 序列列表视图
    path('reg_seq_list/', views.reg_seq_list, name='reg_seq_list'),       # 注册序列列表视图

    path('register_seq/', views.register_seq, name='register_seq'),       # 注册序列

    path('seq_delivery/', views.upload_delivery_info, name='seq_delivery'),  # 上传递送信息

    path('author_list/', views.author_list, name='author_list'),           # 作者列表
    path('add_author/', views.add_author, name='add_author'),              # 新增作者
    path('drop_author/', views.drop_author, name='drop_author'),           # 删除作者
    path('edit_author/', views.edit_author, name='edit_author'),           # 编辑作者

    path('edit_seq/', views.edit_seq, name='edit_seq'),                    # 编辑序列
    path('cor_seq/', views.cor_seq, name='cor_seq'),                       # 核实序列

    path('change_password/', views.change_password, name='change_password'),  # 修改密码

    path('edit_reg_seq/', views.edit_reg_seq, name='edit_reg_seq'),        # 编辑注册序列

    path('module_list/', views.module_list, name='module_list'),
    path('edit_module/', views.edit_module, name='edit_module'),           # 编辑模块
    path('upload_modules/', views.upload_modules, name='upload_modules'),
    path('delete_module/', views.delete_module, name='delete_module'),

    path('seqmodule_list/', views.seqmodule_list, name='seqmodule_list'),
    path('edit_seqmodule/', views.edit_seqmodule, name='edit_seqmodule'),
    path('upload_seqmodules/', views.upload_seqmodules, name='upload_seqmodules'),
    path('delete_seqmodule/', views.delete_seqmodule, name='delete_seqmodule'),

    path('search/', views.search, name='search'),                          # 搜索功能
    path('clone_delivery/', views.clone_delivery, name='clone_delivery'),

    path('download_selected/', views.download_selected, name='download_selected'),
    path('blast_seq/', views.blast_seq, name='blast_seq'),
    path('multi_blast/', views.multi_blast, name='multi_blast'),

    #path('test_log/', views.test_log, name='test_log'),
]
