from django.urls import path
from . import views

app_name = 'authentication'

urlpatterns = [
    path("register/", views.register, name="register"),  # 注册
    path("validate_username/", views.validate_username, name="validate_username"),
    path("validate_email/", views.validate_email, name="validate_email"),
    path('login/', views.login, name='login'), # 登录
]
