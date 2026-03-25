from django.urls import path
from . import views

app_name = 'article'

urlpatterns = [
    path("detail/<int:article_id>", views.detail, name="detail"),  # 文章详情页
    path(
        "category_list/<int:category_id>", views.category_list, name="category_list"
    ),  # 与其分类相关的文章列表页
    path(
        "archive_list/<int:archive_year>/<int:archive_month>",
        views.archive_list,
        name="archive_list",
    ),  # 文章归档列表页
    path("publish_article/", views.publish_article, name="publish_article"),  # 发布文章
    path("drafts/", views.drafts, name="drafts"),  # 草稿箱
    path("edit_draft/<int:draft_id>/", views.edit_draft, name="edit_draft"),  # 编辑草稿
    path(
        "delete_draft/<int:draft_id>/", views.delete_draft, name="delete_draft"
    ),  # 删除草稿
    path("published/", views.published, name="published"),  # 已发布
    path(
        "edit_published/<int:published_id>/",
        views.edit_published,
        name="edit_published",
    ),  # 编辑已发布
    path(
        "delete_published/<int:published_id>/",
        views.delete_published,
        name="delete_published",
    ),  # 删除已发布
    path("upload_image/", views.upload_image, name="upload_image"),
    path("juejin_hot/", views.spdier, name="juejin_hot"),  # 稀土掘金热榜
    path("ai/optimize-title/", views.ai_optimize_title, name="ai_optimize_title"),
    path("ai/generate-summary/", views.ai_generate_summary, name="ai_generate_summary"),
    path("ai-qa/<int:article_id>/", views.article_ai_qa, name="article_ai_qa"),
    
]
