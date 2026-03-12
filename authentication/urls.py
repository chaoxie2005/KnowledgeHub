from django.urls import path
from . import views

app_name = 'authentication'

urlpatterns = [
    path("register/", views.register, name="register"),  # 注册
    path("validate_username/", views.validate_username, name="validate_username"),
    path("validate_email/", views.validate_email, name="validate_email"),
    path("login/", views.login, name="login"),  # 登录
    path(
        "verify_account/<str:username>/", views.verify_account, name="verify_account"
    ),  # 激活帐号
    path(
        "forget_password/", views.forget_password, name="forget_password"
    ),  # 进入重置密码视图
    path(
        "reset_password/<int:pk>/<str:token>",
        views.reset_password,
        name="reset_password",
    ),  # 重置密码
    path("captcha/", views.captcha, name="captcha"),  # 验证码
    path('change_password', views.change_password, name='change_password'), # 修改密码
]
