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
    path('compounds/', views.compound_list, name='compound_list'),
    path('compounds/<str:compound_id>/', views.compound_detail, name='compound_detail'),
    path('authors/', views.author_list, name='author_list'),
    path('profile/', views.user_profile, name='user_profile'),
]
