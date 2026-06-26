from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView
from app01 import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('upload/', RedirectView.as_view(url='/upload/smart/', permanent=True), name='upload'),
    path('upload/confirm/', RedirectView.as_view(url='/upload/smart/', permanent=True), name='upload_confirm'),
    path('upload/success/', RedirectView.as_view(url='/upload/smart/', permanent=True), name='upload_success'),
    path('compounds/', views.compound_list, name='compound_list'),
    path('compounds/<str:compound_id>/', views.compound_detail, name='compound_detail'),
    path('profile/', views.user_profile, name='user_profile'),
    path('profile/request-project/', views.profile_request_project, name='profile_request_project'),
    path('batches/', views.batch_list, name='batch_list'),
    path('batches/<str:batch_label>/delete/', views.batch_delete, name='batch_delete'),
    path('upload/invivo/', RedirectView.as_view(url='/upload/smart/', permanent=True), name='invivo_upload'),
    path('upload/invivo/confirm/', RedirectView.as_view(url='/upload/smart/', permanent=True), name='invivo_upload_confirm'),
    path('upload/smart/', views.smart_upload_view, name='smart_upload'),
    path('upload/smart/confirm/', views.smart_upload_confirm_view, name='smart_upload_confirm'),
    path('attachments/<int:pk>/download/', views.attachment_download, name='attachment_download'),
    path('attachments/<int:pk>/preview/', views.attachment_preview, name='attachment_preview'),
    path('api/experiments/bulk-delete/', views.experiments_bulk_delete, name='experiments_bulk_delete'),
    path('api/experiments/export-csv/', views.experiments_export_csv, name='experiments_export_csv'),
    path('users/', views.user_management_view, name='user_management'),
    path('users/requests/<int:req_id>/approve/', views.project_request_approve, name='project_request_approve'),
    path('users/requests/<int:req_id>/reject/', views.project_request_reject, name='project_request_reject'),
    path('users/<int:user_id>/edit/', views.user_edit_view, name='user_edit'),
    path('users/<int:user_id>/delete/', views.user_delete_view, name='user_delete'),
]
