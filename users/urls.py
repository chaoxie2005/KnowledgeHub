from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    path("user_center/", views.user_center, name="user_center"),  # 用户个人中心
    path("edit_user/", views.edit_user, name="edit_user"),  # 编辑用户信息
    # 新增：查看他人个人中心（通过 user_id）
    path("center/<int:user_id>/", views.user_center, name="user_center"),
]
