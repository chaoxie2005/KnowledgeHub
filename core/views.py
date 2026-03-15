from django.shortcuts import render
from article.models import Article, Category
from django.db.models import Q, Count
from django.core.paginator import Paginator, PageNotAnInteger, InvalidPage, EmptyPage
from django.contrib.auth.decorators import login_required
from django.db.models.functions import ExtractYear, ExtractMonth
from django.contrib.auth.models import User


def index(request):
    """首页"""
    article_qs = Article.objects.filter(status="published").order_by("-created_time")

    # 2. 处理热门文章：增加空值判断，避免索引越界
    hot_articles = article_qs.order_by("-read_count")[:8]
    # 用 get 或默认值，避免列表索引报错
    hot_one = hot_articles.first() if hot_articles else None
    hot_two = hot_articles[1] if len(hot_articles) >= 2 else None

    # 3. 处理最新文章：空值保护
    latest_articles = article_qs.first()  # 替代 [0]，空时返回 None

    # 4. 获取分页和搜索参数：设置默认值为 1，避免空字符串
    page = request.GET.get("page", 1)
    keyword = request.GET.get("keyword", "").strip()  # 去除首尾空格，避免无效搜索

    # 5. 搜索逻辑：仅当关键词非空时才过滤，减少无效查询
    if keyword:
        article_qs = article_qs.filter(
            Q(title__icontains=keyword)
            | Q(summary__icontains=keyword)
            | Q(content__icontains=keyword)
        )

    # 6. 分页处理：优化异常捕获，统一变量名
    paginator = Paginator(article_qs, 5)
    try:
        paginated_articles = paginator.page(page)
    except PageNotAnInteger:
        paginated_articles = paginator.page(1)
    except EmptyPage:
        paginated_articles = paginator.page(paginator.num_pages)
    # 增加通用异常捕获，避免未预期的错误
    except Exception:
        paginated_articles = paginator.page(1)

    last_articles = Article.objects.filter(status="published").order_by(
        "-published_time"
    )[
        :5
    ]  # 最新文章列表页

    hot_list = hot_articles[:5]

    categories = Category.objects.all()

    # ====== 文章归档 =======
    archive_data = (
        Article.objects.filter(status="published")
        # 用 Django 内置函数提取年/月，自动适配数据库
        .annotate(
            year=ExtractYear("published_time"), month=ExtractMonth("published_time")
        )
        .values("year", "month")
        .annotate(article_count=Count("id"))
        .order_by("-year", "-month")
    )

    # 7. 上下文数据：区分分页后的文章和原始查询集，变量名更清晰
    context = {
        "articles": paginated_articles,  # 分页后的文章列表
        "keyword": keyword,
        "latest_articles": latest_articles,
        "hot_one": hot_one,
        "hot_two": hot_two,
        "last_articles": last_articles,  # 最新文章列表页
        "hot_list": hot_list,  # 热门文章列表页
        "categories": categories,
        "archive_data": archive_data,
    }
    return render(request, "core/index.html", context)
