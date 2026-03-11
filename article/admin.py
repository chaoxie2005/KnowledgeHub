from django.contrib import admin
from .models import Article, Category, Tag


# 自定义文章后台显示
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


# 注册分类和标签
admin.site.register(Category)
admin.site.register(Tag)
