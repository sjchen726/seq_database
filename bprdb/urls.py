from django.contrib import admin
from django.urls import path
from app01 import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('upload/', views.upload_view, name='upload'),
    path('upload/confirm/', views.upload_confirm_view, name='upload_confirm'),
    path('upload/success/', views.upload_success_view, name='upload_success'),
    # Sidebar stubs (referenced by base.html)
    path('seq/', views.seq_list, name='seq_list'),
    path('reg-seq/', views.reg_seq_list, name='reg_seq_list'),
    path('register/', views.register_seq, name='register_seq'),
    path('delivery/', views.seq_delivery, name='seq_delivery'),
    path('upload-experiment/', views.upload_experiment, name='upload_experiment'),
    path('blast/', views.multi_blast, name='multi_blast'),
    path('modules/', views.module_list, name='module_list'),
    path('seqmodules/', views.seqmodule_list, name='seqmodule_list'),
    path('linkermodules/', views.linkermodule_list, name='linkermodule_list'),
    path('authors/', views.author_list, name='author_list'),
    path('profile/', views.user_profile, name='user_profile'),
]
