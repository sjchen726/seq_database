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
from django.urls import re_path
from django.contrib import admin
from django.urls import path

from app01 import views

urlpatterns = [
    path('admin/', admin.site.urls),
    re_path(r'^$', views.login_view), # 用户登录页面
    re_path(r'^login/', views.login_view),     # 登录动作
    re_path(r'^signup/', views.register_view),     # 用户注册页面
    re_path(r'^register/', views.register_view),     # 用户注册页面

    re_path(r'^seq_list/', views.get_sequence_info, name='seq_list'),     # 序列列表视图
    re_path(r'^reg_seq_list/', views.reg_seq_list, name='reg_seq_list'),     # 注册序列列表视图

    re_path(r'^register_seq/', views.register_seq, name='register_seq'),     # 注册序列

    re_path(r'^seq_delivery/', views.upload_delivery_info),     # 上传递送信息

    re_path(r'^author_list/', views.author_list),     # 作者列表
    re_path(r'^add_author/', views.add_author),    # 新增作者
    re_path(r'^drop_author/', views.drop_author),    # 删除作者
    re_path(r'^edit_author/', views.edit_author),    # 编辑作者    
    
    re_path(r'^edit_seq/', views.edit_seq, name='edit_seq'),     # 编辑序列
    re_path(r'^cor_seq/', views.cor_seq),     # 编辑序列

    re_path(r'^change_password/', views.change_password, name='change_password'),     # 修改密码

    re_path(r'^edit_reg_seq/', views.edit_reg_seq),     # 编辑序列

    path('module_list/', views.module_list, name='module_list'),
    re_path(r'^edit_module/', views.edit_module),     # 编辑序列
    path('upload_modules/', views.upload_modules, name='upload_modules'),
    path('delete_module/', views.delete_module, name='delete_module'),

    path('search/', views.search, name='search'),  # 搜索功能
    re_path(r'^clone_delivery/', views.clone_delivery, name='clone_delivery'),


    path('download_selected/', views.download_selected, name='download_selected'),
    path('blast_seq/', views.blast_seq, name='blast_seq'),
    path('multi_blast/', views.multi_blast, name='multi_blast'),

    #path('test_log/', views.test_log, name='test_log'),
    
]   
