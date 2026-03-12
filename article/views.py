from django.shortcuts import render, get_object_or_404
from .models import Article, Category
from django.core.paginator import Paginator, PageNotAnInteger, InvalidPage, EmptyPage
from django.db.models import Q


def detail(request, article_id):
    """文章详情页"""
    article = get_object_or_404(Article, pk=article_id, status="published")

    article.read_count += 1  # 阅读量增加
    article.save(update_fields=["read_count"])

    prev_article = Article.objects.filter(id__lt=article_id).order_by("-id").first()
    next_article = Article.objects.filter(id__gt=article_id).order_by("id").first()

    hot_list = (
        Article.objects.filter(status="published")
        .order_by("-created_time")
        .order_by("-read_count")[:5]
    )
    last_articles = Article.objects.filter(status="published").order_by(
        "-published_time"
    )[
        :5
    ]  # 最新文章列表页

    categories = Category.objects.all()
    context = {
        "article": article,
        "prev_article": prev_article,
        "next_article": next_article,
        "last_articles": last_articles,  # 最新文章列表页
        "hot_list": hot_list,  # 热门文章列表页
        "categories": categories,  # 分类
    }
    return render(request, "article/article_detail.html", context)


def category_list(request, category_id):
    """与其标签相关的文章列表页"""
    articles = Article.objects.filter(category_id=category_id, status="published")
    page = request.GET.get("page", 1)
    keyword = request.GET.get("keyword", "").strip()

    if keyword:
        articles = articles.filter(
            Q(title__icontains=keyword)
            | Q(summary__icontains=keyword)
            | Q(content__icontains=keyword)
        )

    # 6. 分页处理：优化异常捕获，统一变量名
    paginator = Paginator(articles, 5)
    try:
        articles = paginator.page(page)
    except PageNotAnInteger:
        articles = paginator.page(1)
    except EmptyPage:
        articles = paginator.page(paginator.num_pages)
    # 增加通用异常捕获，避免未预期的错误
    except Exception:
        articles = paginator.page(1)

    hot_list = (
        Article.objects.filter(status="published")
        .order_by("-created_time")
        .order_by("-read_count")[:5]
    )
    last_articles = Article.objects.filter(status="published").order_by(
        "-published_time"
    )[
        :5
    ]  # 最新文章列表页
    categories = Category.objects.all()
    context = {
        "articles": articles,
        "last_articles": last_articles,  # 最新文章列表页
        "hot_list": hot_list,  # 热门文章列表页
        "categories": categories,
    }
    return render(request, "article/category_list.html", context)
