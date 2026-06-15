from django.contrib import admin
from django.urls import path
from app01 import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('upload/', views.upload_view, name='upload'),
    path('upload/confirm/', views.upload_confirm_view, name='upload_confirm'),
    path('upload/success/', views.upload_success_view, name='upload_success'),
    path('compounds/', views.compound_list, name='compound_list'),
    path('compounds/<str:compound_id>/', views.compound_detail, name='compound_detail'),
    path('profile/', views.user_profile, name='user_profile'),
    path('batches/', views.batch_list, name='batch_list'),
    path('batches/<str:batch_label>/delete/', views.batch_delete, name='batch_delete'),
    path('upload/invivo/', views.invivo_upload_view, name='invivo_upload'),
    path('upload/invivo/confirm/', views.invivo_upload_confirm_view, name='invivo_upload_confirm'),
    path('upload/smart/', views.smart_upload_view, name='smart_upload'),
    path('upload/smart/confirm/', views.smart_upload_confirm_view, name='smart_upload_confirm'),
    path('attachments/<int:pk>/download/', views.attachment_download, name='attachment_download'),
]
