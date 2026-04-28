from django.urls import path
from . import views

app_name = "core" # 命名空间

urlpatterns = [
    path('', views.index, name='index'), # 博客首页
    path('search/', views.search, name='search'), # 搜索功能
    path('ai-qa/', views.ai_qa, name='ai_qa'), # AI问答页面
    path('study-center/', views.study_center, name='study_center'), # 学习中心
    path('data-visualization/', views.data_visualization, name='data_visualization'), # 数据可视化页面
]
