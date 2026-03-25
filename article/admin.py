from django.contrib import admin
from django.template.response import TemplateResponse
from django.conf import settings
from .models import Article, Category, Tag, Comment, JuejinHotArticle
from .ai_utils import optimize_article_title

@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "author",
        "category",
        "status",
        "read_count",
        "created_time",
    ]  # 列表显示字段
    list_filter = ["status", "category", "tags"]  # 筛选条件
    search_fields = ["title", "content"]  # 搜索字段
    date_hierarchy = "created_time"  # 按时间筛选

    # 新增：添加AI优化按钮
    change_form_template = "admin/article/change_form.html"

    def save_model(self, request, obj, form, change):
        """保存文章时，若勾选AI优化则自动优化标题"""
        # 检查是否勾选了AI优化标题
        if "optimize_title" in request.POST:
            obj.title = optimize_article_title(obj.title)
        # 执行原有保存逻辑
        super().save_model(request, obj, form, change)


@admin.register(JuejinHotArticle)
class JuejinHotArticleAdmin(admin.ModelAdmin):
    list_display = ["title", "author", "source", "published_time", "juejin_article_id"]
    list_filter = ["source"]
    search_fields = ["title", "author", "juejin_article_id"]
    date_hierarchy = "published_time"
    change_form_template = "admin/article/change_form.html"

    def save_model(self, request, obj, form, change):
        if "optimize_title" in request.POST:
            obj.title = optimize_article_title(obj.title)
        super().save_model(request, obj, form, change)


# 保留原有注册
admin.site.register(Category)
admin.site.register(Tag)
admin.site.register(Comment)
