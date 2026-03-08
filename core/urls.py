from django.urls import path
from . import views

app_name = "core" # 命名空间

urlpatterns = [
    path('', views.index, name='index'), # 博客首页
]
