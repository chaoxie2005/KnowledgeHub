from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    path("user_center/", views.user_center, name="user_center"),  # 用户个人中心
]
