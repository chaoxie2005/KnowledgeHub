from django.urls import path
from . import views

app_name = 'article'

urlpatterns = [
    path("detail/<int:article_id>", views.detail, name="detail"),  # 文章详情页
    path(
        "category_list/<int:category_id>", views.category_list, name="category_list"
    ),  # 与其分类相关的文章列表页
]
