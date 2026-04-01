#!/usr/bin/env python3
"""
检查已发布的文章数量
"""

import os
import django

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'extraordinaryblog.settings')
django.setup()

from article.models import Article

def check_published_articles():
    """检查已发布的文章"""
    print("=== 已发布的文章 ===")
    articles = Article.objects.filter(status='published')
    print(f"已发布文章数量: {articles.count()}")
    
    for article in articles:
        author_name = article.author.username if article.author else '未知'
        print(f"ID: {article.id}, 标题: {article.title}, 作者: {author_name}")

if __name__ == "__main__":
    check_published_articles()
