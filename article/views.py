from django.shortcuts import render
from . import views
from .models import Article, Category, Tag
from django.core.paginator import Paginator, PageNotAnInteger, InvalidPage, EmptyPage


def article_list(request):
    """全部文章列表页"""
    articles = Article.objects.all().order_by("-published_time")
    page = request.GET.get(page, "")
    paginator = Paginator(articles, 5)
    try:
        articles = paginator.page(page)
    except PageNotAnInteger as e:
        articles = paginator.page(1)
    except EmptyPage:
        articles = paginator.page(paginator.num_pages)

    context = {
        "articles": articles,
    }
    return render(request, 'article/list.html', context)
