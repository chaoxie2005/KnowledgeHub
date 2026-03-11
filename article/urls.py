from django.urls import path
from . import views

urlpatterns = [
    path('', views.article_list, name='article_list'), # 文章列表页(全部)
]
