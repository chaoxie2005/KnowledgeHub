from django.shortcuts import render
from article.models import Article, Category, JuejinHotArticle, CSDNArticle
from django.db.models import Q, Count
from django.core.paginator import Paginator, PageNotAnInteger, InvalidPage, EmptyPage
from django.contrib.auth.decorators import login_required
from django.db.models.functions import ExtractYear, ExtractMonth
from django.contrib.auth.models import User
from django.core.cache import cache
import json
import random


def index(request):
    """首页"""
    # 缓存键定义
    sidebar_cache_key = "sidebar:data"
    hot_articles_cache_key = "hot:articles"
    latest_articles_cache_key = "latest:articles"
    archive_cache_key = "archive:data"
    
    # 尝试从缓存获取侧边栏数据
    cached_sidebar = cache.get(sidebar_cache_key)
    if cached_sidebar:
        sidebar_data = json.loads(cached_sidebar)
        categories = Category.objects.all()
    else:
        # 缓存未命中，查询数据库
        categories = Category.objects.all()
        
        # 准备缓存数据
        sidebar_data = {
            "categories": [(cat.id, cat.name) for cat in categories]
        }
        # 缓存数据，设置过期时间
        cache.set(sidebar_cache_key, json.dumps(sidebar_data), timeout=3600 + random.randint(0, 3600))
    
    # 尝试从缓存获取热门文章
    cached_hot = cache.get(hot_articles_cache_key)
    if cached_hot:
        hot_articles_data = json.loads(cached_hot)
    else:
        # 缓存未命中，查询数据库
        article_qs = Article.objects.filter(status="published").prefetch_related("tags").order_by("-created_time")
        hot_articles = article_qs.order_by("-read_count")[:8]
        
        # 准备缓存数据
        hot_articles_data = {
            "hot_articles_ids": [art.id for art in hot_articles]
        }
        # 缓存数据，设置过期时间
        cache.set(hot_articles_cache_key, json.dumps(hot_articles_data), timeout=1800 + random.randint(0, 1800))
    
    # 尝试从缓存获取最新文章
    cached_latest = cache.get(latest_articles_cache_key)
    if cached_latest:
        latest_data = json.loads(cached_latest)
    else:
        # 缓存未命中，查询数据库
        article_qs = Article.objects.filter(status="published").prefetch_related("tags").order_by("-created_time")
        latest_articles = article_qs.first()  # 替代 [0]，空时返回 None
        
        # 准备缓存数据
        latest_data = {
            "latest_article_id": latest_articles.id if latest_articles else None
        }
        # 缓存数据，设置过期时间
        cache.set(latest_articles_cache_key, json.dumps(latest_data), timeout=1800 + random.randint(0, 1800))
    
    # 尝试从缓存获取归档数据
    cached_archive = cache.get(archive_cache_key)
    if cached_archive:
        archive_data = json.loads(cached_archive)
    else:
        # 缓存未命中，查询数据库
        archive_data = (
            Article.objects.filter(status="published")
            .annotate(
                year=ExtractYear("published_time"), month=ExtractMonth("published_time")
            )
            .values("year", "month")
            .annotate(article_count=Count("id"))
            .order_by("-year", "-month")
        )
        # 转换为可序列化格式
        archive_data_list = list(archive_data)
        # 缓存数据，设置过期时间
        cache.set(archive_cache_key, json.dumps(archive_data_list), timeout=7200 + random.randint(0, 3600))
    
    # 从缓存的ID列表获取实际的文章对象
    hot_articles = []
    if hot_articles_data.get("hot_articles_ids"):
        hot_articles = Article.objects.filter(id__in=hot_articles_data.get("hot_articles_ids")).prefetch_related("tags")
        # 保持原始顺序
        id_to_article = {art.id: art for art in hot_articles}
        hot_articles = [id_to_article[id] for id in hot_articles_data.get("hot_articles_ids") if id in id_to_article]
    else:
        hot_articles = Article.objects.filter(status="published").prefetch_related("tags").order_by("-read_count")[:8]
    
    # 处理热门文章
    hot_one = hot_articles[0] if hot_articles else None
    hot_two = hot_articles[1] if len(hot_articles) >= 2 else None
    hot_list = hot_articles[:5]
    
    # 处理最新文章
    latest_articles = None
    if latest_data.get("latest_article_id"):
        try:
            latest_articles = Article.objects.get(id=latest_data.get("latest_article_id"))
        except Article.DoesNotExist:
            latest_articles = Article.objects.filter(status="published").order_by("-created_time").first()
    else:
        latest_articles = Article.objects.filter(status="published").order_by("-created_time").first()
    
    # 处理最新文章列表
    last_articles = Article.objects.filter(status="published").prefetch_related("tags").order_by("-published_time")[:5]
    
    # 4. 获取分页和搜索参数：设置默认值为 1，避免空字符串
    page = request.GET.get("page", 1)
    keyword = request.GET.get("keyword", "").strip()  # 去除首尾空格，避免无效搜索

    # 5. 搜索逻辑：仅当关键词非空时才过滤，减少无效查询
    article_qs = Article.objects.filter(status="published").prefetch_related("tags").order_by("-created_time")
    if keyword:
        article_qs = article_qs.filter(
            Q(title__icontains=keyword)
            | Q(summary__icontains=keyword)
            | Q(content__icontains=keyword)
            | Q(category__name__icontains=keyword)
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


def search(request):
    """搜索功能"""
    keyword = request.GET.get("keyword", "").strip()
    page = request.GET.get("page", 1)
    
    # 缓存键定义
    search_cache_key = f"search:results:{keyword}:{page}"
    sidebar_cache_key = "sidebar:data"
    archive_cache_key = "archive:data"
    
    # 尝试从缓存获取搜索结果
    cached_search = cache.get(search_cache_key)
    if cached_search:
        search_data = json.loads(cached_search)
        search_results = search_data.get("search_results", [])
        total_results = search_data.get("total_results", 0)
    else:
        # 缓存未命中，查询数据库
        search_results = []
        total_results = 0
        
        if keyword:
            # 1. 本地文章搜索
            local_articles = Article.objects.filter(
                Q(status="published")
                & (
                    Q(title__icontains=keyword)
                    | Q(summary__icontains=keyword)
                    | Q(content__icontains=keyword)
                    | Q(category__name__icontains=keyword)
                    | Q(tags__name__icontains=keyword)
                    | Q(author__username__icontains=keyword)
                    | Q(author__profile__nickname__icontains=keyword)
                )
            ).order_by("-created_time").distinct()
            
            # 添加本地文章到搜索结果
            for article in local_articles:
                search_results.append({
                    "id": article.id,
                    "title": article.title,
                    "summary": article.summary or "",
                    "url": f"/article/detail/{article.id}/",
                    "type": "local",
                    "source": "本地文章",
                    "author": article.author.profile.nickname if hasattr(article.author, 'profile') and article.author.profile.nickname else article.author.username,
                    "created_time": article.created_time.isoformat(),
                    "read_count": article.read_count,
                    "cover": str(article.cover) if article.cover else ""
                })
            
            # 2. 掘金热榜文章搜索
            juejin_articles = JuejinHotArticle.objects.filter(
                Q(title__icontains=keyword)
                | Q(summary__icontains=keyword)
                | Q(ai_summary__icontains=keyword)
                | Q(author__icontains=keyword)
                | Q(source__icontains=keyword)
            ).order_by("-crawl_time")
            
            # 添加掘金文章到搜索结果
            for article in juejin_articles:
                search_results.append({
                    "id": article.juejin_article_id,
                    "title": article.title,
                    "summary": article.summary or article.ai_summary or "",
                    "url": article.original_url,
                    "type": "juejin",
                    "source": article.source or "掘金",
                    "author": article.author or "未知",
                    "created_time": article.crawl_time.isoformat(),
                    "read_count": 0
                })
            
            # 3. CSDN文章搜索
            csdn_articles = CSDNArticle.objects.filter(
                Q(title__icontains=keyword)
                | Q(summary__icontains=keyword)
                | Q(author__icontains=keyword)
                | Q(source__icontains=keyword)
            ).order_by("-crawl_time")
            
            # 添加CSDN文章到搜索结果
            for article in csdn_articles:
                search_results.append({
                    "id": article.csdn_article_id,
                    "title": article.title,
                    "summary": article.summary or "",
                    "url": article.original_url,
                    "type": "csdn",
                    "source": article.source or "CSDN",
                    "author": article.author or "未知",
                    "created_time": article.crawl_time.isoformat(),
                    "read_count": 0
                })
            
            # 排序：按时间倒序
            search_results.sort(key=lambda x: x['created_time'], reverse=True)
            total_results = len(search_results)
        
        # 缓存搜索结果
        search_data = {
            "search_results": search_results,
            "total_results": total_results
        }
        cache.set(search_cache_key, json.dumps(search_data), timeout=300 + random.randint(0, 300))
    
    # 尝试从缓存获取侧边栏数据
    cached_sidebar = cache.get(sidebar_cache_key)
    if cached_sidebar:
        sidebar_data = json.loads(cached_sidebar)
    else:
        # 缓存未命中，查询数据库
        sidebar_data = {
            "last_articles": [(art.id, art.title, art.published_time.strftime("%Y-%m-%d")) for art in Article.objects.filter(status="published").order_by("-published_time")[:5]],
            "hot_list": [(art.id, art.title, art.read_count) for art in Article.objects.filter(status="published").order_by("-read_count")[:5]],
            "categories": [(cat.id, cat.name) for cat in Category.objects.all()]
        }
        cache.set(sidebar_cache_key, json.dumps(sidebar_data), timeout=3600 + random.randint(0, 3600))
    
    # 尝试从缓存获取归档数据
    cached_archive = cache.get(archive_cache_key)
    if cached_archive:
        archive_data = json.loads(cached_archive)
    else:
        # 缓存未命中，查询数据库
        archive_data = (
            Article.objects.filter(status="published")
            .annotate(
                year=ExtractYear("published_time"), month=ExtractMonth("published_time")
            )
            .values("year", "month")
            .annotate(article_count=Count("id"))
            .order_by("-year", "-month")
        )
        archive_data_list = list(archive_data)
        cache.set(archive_cache_key, json.dumps(archive_data_list), timeout=7200 + random.randint(0, 3600))
    
    # 从缓存数据获取实际对象
    last_articles = Article.objects.filter(id__in=[item[0] for item in sidebar_data.get("last_articles", [])]).order_by("-published_time")
    hot_articles = Article.objects.filter(id__in=[item[0] for item in sidebar_data.get("hot_list", [])]).order_by("-read_count")
    hot_list = hot_articles[:5]
    categories = Category.objects.all()
    
    # 分页处理
    paginator = Paginator(search_results, 10)
    try:
        paginated_articles = paginator.page(page)
    except PageNotAnInteger:
        paginated_articles = paginator.page(1)
    except EmptyPage:
        paginated_articles = paginator.page(paginator.num_pages)
    except Exception:
        paginated_articles = paginator.page(1)
    
    # 上下文数据
    context = {
        "keyword": keyword,
        "articles": paginated_articles,
        "total_results": total_results,
        "last_articles": last_articles,  # 最新文章列表页
        "hot_list": hot_list,  # 热门文章列表页
        "categories": categories,
        "archive_data": archive_data,
    }
    
    return render(request, "core/search.html", context)


def ai_qa(request):
    """AI问答页面"""
    # 侧边栏数据
    last_articles = Article.objects.filter(status="published").order_by(
        "-published_time"
    )[:5]  # 最新文章列表页

    hot_articles = Article.objects.filter(status="published").order_by("-read_count")[:5]
    hot_list = hot_articles[:5]

    categories = Category.objects.all()

    # 文章归档
    archive_data = (
        Article.objects.filter(status="published")
        .annotate(
            year=ExtractYear("published_time"), month=ExtractMonth("published_time")
        )
        .values("year", "month")
        .annotate(article_count=Count("id"))
        .order_by("-year", "-month")
    )
    
    # 上下文数据
    context = {
        "last_articles": last_articles,  # 最新文章列表页
        "hot_list": hot_list,  # 热门文章列表页
        "categories": categories,
        "archive_data": archive_data,
    }
    
    return render(request, "core/ai_qa.html", context)


def data_visualization(request):
    """数据可视化页面"""
    # 侧边栏数据
    last_articles = Article.objects.filter(status="published").order_by(
        "-published_time"
    )[:5]  # 最新文章列表页

    hot_articles = Article.objects.filter(status="published").order_by("-read_count")[:5]
    hot_list = hot_articles[:5]

    categories = Category.objects.all()

    # 文章归档
    archive_data = (
        Article.objects.filter(status="published")
        .annotate(
            year=ExtractYear("published_time"), month=ExtractMonth("published_time")
        )
        .values("year", "month")
        .annotate(article_count=Count("id"))
        .order_by("-year", "-month")
    )
    
    # 准备可视化数据
    # 1. 文章分类分布
    category_data = list(Category.objects.annotate(article_count=Count('article')).values('name', 'article_count'))
    
    # 2. 文章发布时间趋势
    time_data = list(
        Article.objects.filter(status="published")
        .annotate(year=ExtractYear("published_time"), month=ExtractMonth("published_time"))
        .values("year", "month")
        .annotate(article_count=Count("id"))
        .order_by("year", "month")
    )
    
    # 3. 文章来源分布
    local_count = Article.objects.filter(status="published").count()
    juejin_count = JuejinHotArticle.objects.count()
    csdn_count = CSDNArticle.objects.count()
    source_data = [
        {"name": "本地文章", "value": local_count},
        {"name": "掘金", "value": juejin_count},
        {"name": "CSDN", "value": csdn_count}
    ]
    
    # 4. 热门文章阅读量
    hot_article_data = list(
        Article.objects.filter(status="published")
        .order_by("-read_count")[:10]
        .values("title", "read_count")
    )
    
    # 上下文数据
    context = {
        "last_articles": last_articles,  # 最新文章列表页
        "hot_list": hot_list,  # 热门文章列表页
        "categories": categories,
        "archive_data": archive_data,
        "category_data": category_data,
        "time_data": time_data,
        "source_data": source_data,
        "hot_article_data": hot_article_data,
        "local_count": local_count,  # 文章总数
    }
    
    return render(request, "core/data_visualization.html", context)
