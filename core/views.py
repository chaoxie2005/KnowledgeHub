from django.shortcuts import render
from article.models import Article
from django.db.models import Q
from django.core.paginator import Paginator, PageNotAnInteger, InvalidPage, EmptyPage
from django.contrib.auth.decorators import login_required


@login_required(login_url="authentication:login")
def index(request):
    articles = Article.objects.filter(status="published").order_by('-created_time')
    page = request.GET.get("page", "")
    keyword = request.GET.get("keyword", "")

    if keyword:
        articles = articles.filter(
            Q(title__icontains=keyword)
            | Q(summary__icontains=keyword)
            | Q(content__icontains=keyword)
        )
    paginator = Paginator(articles, 5)
    try:
        articles = paginator.page(page)
    except PageNotAnInteger as e:
        articles = paginator.page(1)
    except EmptyPage:
        articles = paginator.page(paginator.num_pages)

    context = {
        "articles": articles,
        'keyword': keyword,
    }
    return render(request, "core/index.html", context)
