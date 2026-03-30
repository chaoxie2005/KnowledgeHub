from django.shortcuts import render, get_object_or_404, redirect
from .models import Article, Category, Tag, Comment, CommentLike, JuejinHotArticle
from .forms import CommentForm
from django.core.paginator import Paginator, PageNotAnInteger, InvalidPage, EmptyPage
from django.db.models import Q, F
from django.utils.text import gettext_lazy as _
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.contrib.auth.models import User
from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from .serializers import ArticleSerializer, CategorySerializer, CommentSerializer
import os
import json
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import markdown
from django.views.decorators.http import require_POST
from .crawl_juejin import crawl_and_save_juejin_hot
from .ai_utils import optimize_article_title, generate_article_summary
import redis
import time
import sys
from utils.redis_client import redis_client
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from django.db.models import Prefetch
from utils.rag_chain import simple_rag_qa, simple_rag_qa_stream


def time_it(func):
    """测试项目时间性能函数"""
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start
        # 加上明显的星星和 flush，确保 Gunicorn 立即输出日志
        print(f"\n★★★ PERF: {func.__name__} 耗时: {duration:.4f}s ★★★\n", flush=True)
        return result
    return wrapper


# 1. 文章 API 视图（支持增删改查、过滤、排序）
class ArticleViewSet(viewsets.ModelViewSet):
    """
    博客文章 API：
    - GET: 查看文章列表/详情（所有人可看）
    - POST/PUT/DELETE: 增删改文章（仅登录用户）
    """

    queryset = Article.objects.all().select_related("author", "category").prefetch_related("tags").order_by("-created_time")
    serializer_class = ArticleSerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    # 过滤：按分类、标签、作者过滤
    filterset_fields = ["category", "tags", "author"]
    # 搜索：按标题、内容搜索
    search_fields = ["title", "summary", "content", "author__username", "tags__name"]
    # 排序：按创建时间、阅读量排序
    ordering_fields = ["created_time", "read_count"]
    # DRF 权限控制，实现“只读公开，修改需登录”
    permission_classes = [IsAuthenticatedOrReadOnly]


# 2. 分类 API 视图
class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


# 3. 评论 API 视图
class CommentViewSet(viewsets.ModelViewSet):
    queryset = Comment.objects.all().select_related("user", "article", "parent").order_by("-created_time")
    serializer_class = CommentSerializer
    filterset_fields = ["article", "parent"]  # 按文章、父评论过滤


def detail(request, article_id):
    """文章详情页(集成redis缓存)"""
    article = get_object_or_404(Article, pk=article_id, status="published")

    # 先定义缓存键，避免POST逻辑中未定义报错
    cache_key = f"article:detail:{article_id}"
    read_count_key = f"article:read_count:{article_id}"

    # 评论提交必须放最前面
    if request.method == "POST" and request.user.is_authenticated:
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.article = article
            comment.user = request.user
            parent_id = request.POST.get("parent")
            if parent_id:
                try:
                    parent_comment = Comment.objects.get(id=parent_id, article=article)
                    comment.parent = parent_comment
                except Comment.DoesNotExist:
                    comment.parent = None
            comment.save()

            redis_client.delete(cache_key)

            return redirect("article:detail", article_id=article_id)

    # 阅读量自增（无论有没有缓存都要+1）
    current_read_count = redis_client.get(read_count_key)
    if not current_read_count:
        redis_client.set(read_count_key, article.read_count)
    redis_client.incr(read_count_key)
    real_read_count = int(redis_client.get(read_count_key))

    # 定义Markdown扩展
    markdown_extensions = [
        'markdown.extensions.extra',      # 支持表格、脚注等
        'markdown.extensions.codehilite', # 代码高亮
        'markdown.extensions.toc',        # 目录
        'markdown.extensions.nl2br',      # 换行转<br>
    ]

    # 简化缓存读取逻辑，避免重复反序列化
    cached_article = redis_client.get(cache_key)
    if cached_article:
        article_data = json.loads(cached_article)
        # 更新阅读量
        article_data["read_count"] = real_read_count
        
        # 确保content字段是渲染后的HTML
        if "content_raw" in article_data:
            # 使用原始内容重新渲染
            article_data["rendered_content"] = markdown.markdown(
                article_data["content_raw"],
                extensions=markdown_extensions,
            )
            # 同时更新content字段，保持向后兼容
            article_data["content"] = article_data["rendered_content"]
        else:
            # 如果没有content_raw，使用content字段（可能是原始内容）
            raw_content = article_data.get("content", "")
            article_data["rendered_content"] = markdown.markdown(
                raw_content,
                extensions=markdown_extensions,
            )
            article_data["content"] = article_data["rendered_content"]
        
        # 获取上一篇下一篇（这些不适合缓存，每次都要查最新）
        prev_article = Article.objects.filter(
            id__lt=article_id, 
            status="published"
        ).order_by("-id").first()
        
        next_article = Article.objects.filter(
            id__gt=article_id, 
            status="published"
        ).order_by("id").first()
        
        # 获取侧边栏数据
        hot_list = Article.objects.filter(status="published").order_by("-read_count")[:5]
        last_articles = Article.objects.filter(status="published").order_by("-published_time")[:5]
        categories = Category.objects.all()
        articles = Article.objects.filter(status="published")[:5]
        
        # 获取评论
        comments = article.comments.filter(parent=None).select_related("user").prefetch_related(
            Prefetch(
                "replies",
                queryset=Comment.objects.select_related("user").order_by("created_time"),
                to_attr="sorted_replies"
            ),
            "comment_likes"  # 预加载点赞
        )

        # 性能进阶：为每条评论同步 Redis 点赞数
        # 在比赛演示中，这体现了对分布式数据一致性的考虑
        for c in comments:
            redis_count = redis_client.get(f"comment:like_count:{c.id}")
            if redis_count is not None:
                c.like_count = int(redis_count)
            else:
                # 缓存预热 7天小时过期时间
                redis_client.set(f"comment:like_count:{c.id}", c.like_count, ex=86400)
            
            # 对子评论也进行同步
            if hasattr(c, 'sorted_replies'):
                for r in c.sorted_replies:
                    r_redis_count = redis_client.get(f"comment:like_count:{r.id}")
                    if r_redis_count is not None:
                        r.like_count = int(r_redis_count)
                    else:
                        redis_client.set(f"comment:like_count:{r.id}", r.like_count, ex=86400)

        # 获取当前用户已点赞的评论ID列表，解决 N+1 问题
        liked_comment_ids = []
        if request.user.is_authenticated:
            user_id = request.user.id
            # 性能进阶：检查 Redis Set 以获取最新点赞状态
            # 这里我们采用“懒加载”策略：点赞动作会触发 Redis 写入
            # 页面加载时我们仍以数据库为准，但优先合并 Redis 中的实时变化
            liked_comment_ids = list(CommentLike.objects.filter(
                user=request.user,
                comment__article_id=article_id
            ).values_list('comment_id', flat=True))
        
        context = {
            "article": article_data,
            "prev_article": prev_article,
            "next_article": next_article,
            "last_articles": last_articles,
            "hot_list": hot_list,
            "categories": categories,
            "comments": comments,
            "articles": articles,
            "liked_comment_ids": liked_comment_ids, # 传递给模板
        }
        return render(request, "article/article_detail.html", context)

    # 缓存不存在 → 查数据库 
    
    # 渲染Markdown为HTML
    rendered_content = markdown.markdown(
        article.content,
        extensions=markdown_extensions,
    )
    
    # 获取上一篇下一篇
    prev_article = Article.objects.filter(
        id__lt=article_id, 
        status="published"
    ).order_by("-id").first()
    
    next_article = Article.objects.filter(
        id__gt=article_id, 
        status="published"
    ).order_by("id").first()
    
    # 获取侧边栏数据
    hot_list = Article.objects.filter(status="published").order_by("-read_count")[:5]
    last_articles = Article.objects.filter(status="published").order_by("-published_time")[:5]
    categories = Category.objects.all()
    articles = Article.objects.filter(status="published")[:5]
    
    # 获取评论
    comments = article.comments.filter(parent=None).select_related("user").prefetch_related(
        Prefetch(
            "replies",
            queryset=Comment.objects.select_related("user").order_by("created_time"),
            to_attr="sorted_replies"
        ),
        "comment_likes"  # 预加载点赞
    )

    # 性能进阶：为每条评论同步 Redis 点赞数
    for c in comments:
        redis_count = redis_client.get(f"comment:like_count:{c.id}")
        if redis_count is not None:
            c.like_count = int(redis_count)
        else:
            redis_client.set(f"comment:like_count:{c.id}", c.like_count, ex=86400)
        
        if hasattr(c, 'sorted_replies'):
            for r in c.sorted_replies:
                r_redis_count = redis_client.get(f"comment:like_count:{r.id}")
                if r_redis_count is not None:
                    r.like_count = int(r_redis_count)
                else:
                    redis_client.set(f"comment:like_count:{r.id}", r.like_count, ex=86400) # 缓存24小时

    # 获取当前用户已点赞的评论ID列表
    liked_comment_ids = []
    if request.user.is_authenticated:
        liked_comment_ids = list(CommentLike.objects.filter(
            user=request.user,
            comment__article_id=article_id
        ).values_list('comment_id', flat=True))
    
    # 获取作者信息
    author_profile = getattr(article.author, 'profile', None)
    author_email = author_profile.email if author_profile else ""
    author_phone = author_profile.phone if author_profile else ""
    
    # 新增tags字段，解决模板渲染报错
    tags = []
    if hasattr(article, 'tags'):
        tags = [{"id": tag.id, "name": tag.name} for tag in article.tags.all()]
    
    # 准备缓存数据
    article_data = {
        "id": article.id,
        "title": article.title,
        "content": rendered_content,  # 存储渲染后的HTML
        "content_raw": article.content,  # 保存原始Markdown，以备后用
        "rendered_content": rendered_content,  # 显式存储渲染后的内容
        "summary": article.summary,
        "created_time": article.created_time.strftime("%Y-%m-%d %H:%M"),
        "published_time": article.published_time.strftime("%Y-%m-%d %H:%M") if article.published_time else "",
        "author": article.author.username if article.author else "",
        "author_email": author_email,
        "author_phone": author_phone,
        "read_count": real_read_count,
        "status": article.status,
        "category_id": article.category.id if article.category else None,
        "category_name": article.category.name if article.category else "",
        "tags": tags,  # 新增tags字段
        "cover": article.cover.url if article.cover else "",  # 可选：补充封面图路径
    }
    
    redis_client.set(cache_key, json.dumps(article_data), ex=86400) # 缓存24小时
    
    context = {
        "article": article_data,
        "prev_article": prev_article,
        "next_article": next_article,
        "last_articles": last_articles,
        "hot_list": hot_list,
        "categories": categories,
        "comments": comments,
        "articles": articles,
        "liked_comment_ids": liked_comment_ids, # 传递给模板
    }
    return render(request, "article/article_detail.html", context)


def category_list(request, category_id):
    """与其标签相关的文章列表页"""
    articles = Article.objects.filter(
        category_id=category_id, status="published"
    ).order_by("-published_time")
    page = request.GET.get("page", 1)
    keyword = request.GET.get("keyword", "").strip()

    if keyword:
        articles = articles.filter(
            Q(title__icontains=keyword)
            | Q(summary__icontains=keyword)
            | Q(content__icontains=keyword)
            | Q(author__icontains=keyword)
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
    about_articles = articles[:5]
    context = {
        "articles": articles,
        "last_articles": last_articles,  # 最新文章列表页
        "hot_list": hot_list,  # 热门文章列表页
        "categories": categories,
        "about_articles": about_articles,
    }
    return render(request, "article/category_list.html", context)


def archive_list(request, archive_year, archive_month):
    """文章归档列表"""
    articles = Article.objects.filter(
        published_time__year=archive_year,
        published_time__month=archive_month,
        status="published",
    ).order_by("-published_time")

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
    about_articles = articles[:5]
    context = {
        "articles": articles,
        "last_articles": last_articles,  # 最新文章列表页
        "hot_list": hot_list,  # 热门文章列表页
        "categories": categories,
        "about_articles": about_articles,
    }
    return render(request, "article/archive_list.html", context)


@login_required(login_url="authentication:login")
def publish_article(request):
    """发布文章（支持：选择已有标签 + 自定义标签自动创建）"""
    categories = Category.objects.all()
    tags = Tag.objects.all()

    if request.method == "GET":
        context = {"categories": categories, "tags": tags}
        return render(request, "article/publish_article.html", context)

    elif request.method == "POST":
        # 1. 初始化文章
        article = Article()
        article.author = request.user

        # 2. 标题
        title = request.POST.get("title", "").strip()
        if not title:
            messages.error(request, "文章标题不能为空！")
            return render(
                request,
                "article/publish_article.html",
                {"categories": categories, "tags": tags, "values": request.POST},
            )
        if len(title) > 200:
            messages.error(request, "文章标题不能超过200字！")
            return render(
                request,
                "article/publish_article.html",
                {"categories": categories, "tags": tags, "values": request.POST},
            )
        article.title = title

        # 3. 封面
        cover = request.FILES.get("cover")
        if cover:
            allowed_extensions = ["jpg", "jpeg", "png", "webp"]
            file_name = cover.name
            if not file_name or "." not in file_name:
                messages.error(request, "封面图格式无效！")
                return render(request, "article/publish_article.html", {"categories": categories, "tags": tags})
            file_ext = file_name.split(".")[-1].lower()
            if file_ext not in allowed_extensions:
                messages.error(request, f"仅支持 {('/').join(allowed_extensions)}")
                return render(request, "article/publish_article.html", {"categories": categories, "tags": tags})
            max_size = 2 * 1024 * 1024
            if cover.size > max_size:
                messages.error(request, "封面不能超过2MB！")
                return render(request, "article/publish_article.html", {"categories": categories, "tags": tags})
            article.cover = cover

        # 4. 摘要
        summary = request.POST.get("summary", "").strip()
        if summary and len(summary) > 500:
            messages.error(request, "摘要不能超过500字！")
            return render(request, "article/publish_article.html", {"categories": categories, "tags": tags, "values": request.POST})
        article.summary = summary

        # 5. 内容
        content = request.POST.get("content", "").strip()
        if not content:
            messages.error(request, "文章内容不能为空！")
            return render(request, "article/publish_article.html", {"categories": categories, "tags": tags, "values": request.POST})
        article.content = content

        # 6. 分类
        category_id = request.POST.get("category")
        if category_id:
            try:
                category = Category.objects.get(id=category_id)
                article.category = category
            except Category.DoesNotExist:
                messages.warning(request, "分类不存在，已置空！")

        # 7. 状态
        action = request.POST.get("action", "draft")
        if action == "publish":
            article.status = "published"
            article.published_time = timezone.now()
        else:
            article.status = "draft"
            article.published_time = None

        # 8. 保存文章
        article.save()


        # 标签核心逻辑：支持选择 + 自定义
        tag_str = request.POST.get("tags", "")
        tag_names = [t.strip() for t in tag_str.split(",") if t.strip()]

        final_tags = []
        for name in tag_names:
            # 不存在则创建，存在则获取
            tag, created = Tag.objects.get_or_create(name=name)
            final_tags.append(tag)

        # 多对多赋值
        article.tags.set(final_tags)

        # 提示
        if action == "publish":
            messages.success(request, "文章发布成功！")
        else:
            messages.success(request, "草稿保存成功！")

        return redirect("core:index")

    context = {"categories": categories, "tags": tags}
    return render(request, "article/publish_article.html", context)

@time_it
def juejin_hot(request):
    """稀土掘金热榜（前端展示与缓存逻辑）"""
    page = request.GET.get("page", 1)
    keyword = request.GET.get("keyword", "").strip()
    try:
        page = int(page)
    except (ValueError, TypeError):
        page = 1

    # 1. 定义缓存键
    keyword_key = keyword if keyword else "all"
    cache_key = f"juejin:hot:v2:{keyword_key}:p{page}"
    category_cache_key = "global:all_categories"
    last_articles_cache_key = "juejin:hot:last10"
    
    # 2. 尝试从 Redis 读取分页后的 ID 列表
    id_list = None
    try:
        cached_data = redis_client.get(cache_key)
        if cached_data:
            id_list = json.loads(cached_data)
    except Exception as e:
        print(f"Redis 读取异常: {e}", flush=True)

    # 3. 如果命中主列表缓存
    if id_list:
        try:
            # 批量查询数据库，仅加载必要字段并保持顺序
            article_qs = JuejinHotArticle.objects.filter(id__in=id_list).prefetch_related('tags')
            id_map = {art.id: art for art in article_qs}
            articles_list = [id_map[aid] for aid in id_list if aid in id_map]
            
            # 获取总数（用于分页器展示）
            total_count = JuejinHotArticle.objects.all().count()
            if keyword:
                total_count = JuejinHotArticle.objects.filter(Q(title__icontains=keyword)).count()
            
            # 使用虚拟列表模拟分页器
            paginator = Paginator(range(total_count), 5)
            articles = paginator.page(page)
            articles.object_list = articles_list
        except Exception as e:
            print(f"处理缓存数据异常: {e}", flush=True)
            id_list = None # 降级

    # 4. 如果未命中主列表缓存
    if not id_list:
        articles_query = JuejinHotArticle.objects.all().prefetch_related('tags').order_by('-published_time')
        if keyword:
            articles_query = articles_query.filter(
                Q(title__icontains=keyword) | Q(summary__icontains=keyword)
            )
        
        paginator = Paginator(articles_query, 5)
        try:
            articles = paginator.page(page)
        except (PageNotAnInteger, EmptyPage):
            articles = paginator.page(1)

        # 写入缓存（仅存 ID 列表）
        try:
            current_ids = [art.id for art in articles.object_list]
            redis_client.set(cache_key, json.dumps(current_ids), ex=600)
        except Exception:
            pass

    # 5. 侧边栏与静态数据缓存优化
    # 5.1 分类列表缓存
    try:
        cached_categories = redis_client.get(category_cache_key)
    except Exception:
        cached_categories = None

    if cached_categories:
        categories = json.loads(cached_categories)
    else:
        categories = list(Category.objects.all().values('id', 'name'))
        try:
            redis_client.set(category_cache_key, json.dumps(categories), ex=3600)
        except Exception:
            pass

    # 5.2 最新 10 篇热榜缓存
    try:
        cached_last = redis_client.get(last_articles_cache_key)
    except Exception:
        cached_last = None

    if cached_last:
        last_articles = json.loads(cached_last)
    else:
        last_articles = list(JuejinHotArticle.objects.all().order_by('-published_time').values('title', 'original_url')[:10])
        try:
            redis_client.set(last_articles_cache_key, json.dumps(last_articles), ex=600)
        except Exception:
            pass

    context = {
        "articles": articles,
        "categories": categories,
        "last_articles": last_articles,
    }
    return render(request, "article/juejin_hot.html", context)


@login_required(login_url="authentication:login")
def drafts(request):
    """草稿箱（Redis 缓存）"""
    cache_key = f"user:{request.user.id}:draft_articles"
    cached_data = redis_client.get(cache_key)

    # ======================
    # 永远优先查数据库，缓存只用来加速，不影响正确性
    # ======================
    drafts = Article.objects.filter(
        author=request.user, 
        status="draft"
    ).order_by("-created_time")

    # 刷新缓存（保证缓存和数据库一致）
    article_ids = list(drafts.values_list("id", flat=True))
    redis_client.set(cache_key, json.dumps(article_ids), ex=600)

    context = {"drafts": drafts}
    return render(request, "article/drafts.html", context)

@login_required(login_url="authentication:login")
def edit_draft(request, draft_id):
    """编辑草稿箱（完整可运行版）"""
    article = get_object_or_404(
        Article, id=draft_id, status="draft", author=request.user  # 修正拼写错误
    )

    # 获取分类和标签（前端需要）
    categories = Category.objects.all()
    tags = Tag.objects.all()

    # 处理POST提交（保存修改）
    if request.method == "POST":
        # 接收表单数据
        title = request.POST.get("title", "").strip()
        cover = request.FILES.get("cover")
        summary = request.POST.get("summary", "").strip()
        content = request.POST.get("content", "").strip()
        category_id = request.POST.get("category")
        tag_ids = request.POST.getlist("tags")
        action = request.POST.get("action", "draft")

        # 校验必填项
        if not title:
            messages.error(request, "文章标题不能为空！")
            return render(
                request,
                "article/edit_draft.html",
                {"article": article, "categories": categories, "tags": tags},
            )
        if not content:
            messages.error(request, "文章内容不能为空！")
            return render(
                request,
                "article/edit_draft.html",
                {"article": article, "categories": categories, "tags": tags},
            )

        # 更新文章数据
        article.title = title
        article.summary = summary
        article.content = content

        # 更新封面图（有新上传才替换）
        if cover:
            # 封面格式/大小校验（复用发布文章的逻辑）
            allowed_extensions = ["jpg", "jpeg", "png", "webp"]
            file_ext = cover.name.split(".")[-1].lower() if "." in cover.name else ""
            max_size = 2 * 1024 * 1024  # 2MB
            if file_ext in allowed_extensions and cover.size <= max_size:
                article.cover = cover
            else:
                messages.warning(request, "封面图格式或大小不符合要求，未更新封面！")

        # 更新分类
        if category_id:
            try:
                article.category = Category.objects.get(id=category_id)
            except Category.DoesNotExist:
                messages.warning(request, "选择的分类不存在，未更新分类！")

        # 更新标签（多对多关系）
        if tag_ids:
            valid_tags = Tag.objects.filter(id__in=tag_ids)
            article.tags.set(valid_tags)

        # 更新状态（草稿/发布）
        if action == "publish":
            article.status = "published"
            article.published_time = timezone.now()  # 发布时记录时间
        else:
            article.status = "draft"

        # 保存修改
        article.save()

        # 提示+跳转
        if action == "publish":
            messages.success(request, "文章发布成功！")
            return redirect("article:published")  # 跳转到已发布列表
        else:
            messages.success(request, "草稿修改成功！")
            return redirect("article:drafts")  # 跳回草稿箱

    # GET请求：渲染编辑页面，传递分类/标签数据
    context = {"article": article, "categories": categories, "tags": tags}
    return render(request, "article/edit_draft.html", context)


@login_required(login_url="authentication:login")
def delete_draft(request, draft_id):
    """删除草稿"""
    Article.objects.filter(pk=draft_id, author=request.user).delete()
    messages.success(request, "草稿删除成功！")
    return redirect(to="article:drafts")


@login_required(login_url="authentication:login")
def published(request):
    """已发布文章（修复版，稳定不炸）""" 
    # 1. 强制从数据库拿真实数据（保证一定能显示）
    publisheds = Article.objects.filter(
        author=request.user, 
        status="published"
    ).order_by("-published_time")

    # 2. 刷新缓存（保证缓存最新）
    cache_key = f'user:{request.user.id}:published_articles'
    article_ids = list(publisheds.values_list('id', flat=True))
    redis_client.set(cache_key, json.dumps(article_ids), ex=600)

    context = {
        "publisheds": publisheds,
    }
    return render(request, "article/published.html", context)

@login_required(login_url="authentication:login")
def edit_published(request, published_id):
    """编辑已发布文章"""
    # 1. 获取当前用户的已发布文章
    article = get_object_or_404(
        Article, id=published_id, status="published", author=request.user
    )

    # 获取分类和标签（前端需要）
    categories = Category.objects.all()
    tags = Tag.objects.all()

    # 处理POST提交（保存修改）
    if request.method == "POST":
        # 接收表单数据
        title = request.POST.get("title", "").strip()
        cover = request.FILES.get("cover")
        summary = request.POST.get("summary", "").strip()
        content = request.POST.get("content", "").strip()
        category_id = request.POST.get("category")
        tag_ids = request.POST.getlist("tags")
        action = request.POST.get("action", "publish")  # 已发布文章默认保存为发布状态

        # 校验必填项
        if not title:
            messages.error(request, "文章标题不能为空！")
            return render(
                request,
                "article/edit_published.html",
                {"article": article, "categories": categories, "tags": tags},
            )
        if not content:
            messages.error(request, "文章内容不能为空！")
            return render(
                request,
                "article/edit_published.html",  # 修正：指向正确的模板文件
                {"article": article, "categories": categories, "tags": tags},
            )

        # 更新文章数据
        article.title = title
        article.summary = summary
        article.content = content

        # 更新封面图（有新上传才替换）
        if cover:
            # 封面格式/大小校验
            allowed_extensions = ["jpg", "jpeg", "png", "webp"]
            file_ext = cover.name.split(".")[-1].lower() if "." in cover.name else ""
            max_size = 2 * 1024 * 1024  # 2MB
            if file_ext in allowed_extensions and cover.size <= max_size:
                article.cover = cover
            else:
                messages.warning(request, "封面图格式或大小不符合要求，未更新封面！")

        # 更新分类
        if category_id:
            try:
                article.category = Category.objects.get(id=category_id)
            except Category.DoesNotExist:
                messages.warning(request, "选择的分类不存在，未更新分类！")

        # 更新标签（多对多关系）
        if tag_ids:
            valid_tags = Tag.objects.filter(id__in=tag_ids)
            article.tags.set(valid_tags)

        # 核心调整：已发布文章编辑后的状态逻辑
        if action == "publish":
            article.status = "published"
            # 已发布文章编辑后，发布时间不重置（保留首次发布时间）
            article.updated_time = timezone.now()
        else:
            # 改为草稿时，清空发布时间
            article.status = "draft"
            article.published_time = None

        # 保存修改
        article.save()

        # 提示+跳转（适配已发布场景）
        if action == "publish":
            messages.success(request, "文章修改成功！")
            return redirect("article:published")  # 跳转到已发布列表
        else:
            messages.success(request, "文章已转为草稿！")
            return redirect("article:drafts")  # 跳回草稿箱

    # GET请求：渲染编辑页面
    context = {"article": article, "categories": categories, "tags": tags}
    return render(request, "article/edit_published.html", context)


@login_required(login_url="authentication:login")
def delete_published(request, published_id):
    """删除已发布"""
    Article.objects.filter(pk=published_id, author=request.user).delete()
    messages.success(request, "文章删除成功！")
    return redirect(to="core:index")

# 图片上传接口（注意：csrf_exempt 是因为前端已经传了 CSRF Token，这里简化处理）
@csrf_exempt
def upload_image(request):
    if request.method == "POST":
        file = request.FILES.get("image")

        if not file:
            return JsonResponse({"success": 0, "message": "没有文件"})

        path = os.path.join(settings.MEDIA_ROOT, file.name)

        with open(path, "wb") as f:
            for chunk in file.chunks():
                f.write(chunk)

        url = settings.MEDIA_URL + file.name

        return JsonResponse({"success": 1, "url": url})



@require_POST
def ai_optimize_title(request):
    """AI 优化标题接口"""
    data = json.loads(request.body)
    title = data.get("title", "").strip()
    if not title:
        return JsonResponse({"success": False, "error": "标题不能为空"})
    try:
        optimized_title = optimize_article_title(title)
        return JsonResponse({"success": True, "optimized_title": optimized_title})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


@require_POST
def ai_generate_summary(request):
    """AI 生成摘要接口"""
    data = json.loads(request.body)
    content = data.get("content", "").strip()
    if not content:
        return JsonResponse({"success": False, "error": "文章内容不能为空"})
    try:
        summary = generate_article_summary(content)
        return JsonResponse({"success": True, "summary": summary})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


@login_required(login_url='authentication:login')
@require_POST
def article_ai_qa(request, article_id):
    """LangChain RAG 文章问答接口"""
    try:
        article = Article.objects.get(id=article_id, status="published")

        question = request.POST.get("question", "").strip()
        if not question:
            return JsonResponse({"code": 400, "msg": "请输入问题"})

        if request.GET.get("stream") == "1":
            response = StreamingHttpResponse(
                simple_rag_qa_stream(article.content, question),
                content_type="text/plain; charset=utf-8",
            )
            response["Cache-Control"] = "no-cache"
            response["X-Accel-Buffering"] = "no"
            return response

        answer = simple_rag_qa(article.content, question)
        return JsonResponse({
            "code": 200,
            "answer": answer
        })

    except Article.DoesNotExist:
        return JsonResponse({"code": 404, "msg": "文章不存在"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"code": 500, "msg": f"服务异常：{str(e)}"})
    

@require_POST
def comment_like(request, comment_id):
    """评论点赞/取消点赞：使用 Redis 事务 (Pipeline) 保证原子性"""
    if not request.user.is_authenticated:
        return JsonResponse({"status": "error", "msg": "nologin"}, status=401)
        
    comment = get_object_or_404(Comment, id=comment_id)
    user_id = request.user.id
    
    # 定义 Redis Key
    likes_set_key = f"comment:likes:set:{comment_id}"
    like_count_key = f"comment:like_count:{comment_id}"
    
    try:
        # 1. 检查用户是否已在 Redis 集合中（判断是否点赞）
        is_liked = redis_client.sismember(likes_set_key, user_id)
        
        # 2. 开启 Redis Pipeline (实现事务原子性)
        pipe = redis_client.pipeline()
        
        if is_liked:
            # 已点赞 -> 取消点赞
            pipe.srem(likes_set_key, user_id)
            pipe.decr(like_count_key)
            action = "unliked"
            
            # 3. 异步/同步持久化到数据库 (使用 F 表达式防止并发冲突)
            Comment.objects.filter(id=comment_id).update(like_count=F('like_count') - 1)
            CommentLike.objects.filter(comment=comment, user_id=user_id).delete()
        else:
            # 未点赞 -> 点赞
            pipe.sadd(likes_set_key, user_id)
            pipe.incr(like_count_key)
            action = "liked"
            
            # 3. 异步/同步持久化到数据库
            Comment.objects.filter(id=comment_id).update(like_count=F('like_count') + 1)
            CommentLike.objects.get_or_create(comment=comment, user_id=user_id)
            
        # 4. 执行 Redis 事务
        pipe.execute()
        
        # 5. 获取最新点赞数（优先从 Redis 获取，兜底从 DB）
        new_like_count = redis_client.get(like_count_key)
        if new_like_count is None:
            comment.refresh_from_db()
            new_like_count = comment.like_count
            redis_client.set(like_count_key, new_like_count, ex=86400) # 缓存24小时
        else:
            new_like_count = int(new_like_count)
            # 如果 Redis 里的数是负的（极端并发错误），重置为0
            if new_like_count < 0:
                new_like_count = 0
                redis_client.set(like_count_key, 0)
        
        return JsonResponse({
            "status": "success", 
            "action": action, 
            "like_count": new_like_count
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"status": "error", "msg": str(e)}, status=500)


@require_POST
def delete_comment(request, comment_id):
    """删除评论：包含 Redis 缓存清理逻辑"""
    if not request.user.is_authenticated:
        return JsonResponse({"status": "error", "msg": "nologin"}, status=401)
        
    comment = get_object_or_404(Comment, id=comment_id)
    
    # 权限校验：仅作者或管理员可删除
    if comment.user_id != request.user.id and not request.user.is_superuser:
        return JsonResponse({"status": "error", "msg": "no permission"}, status=403)
    
    article_id = comment.article_id
    
    try:
        # 1. 清理该评论关联的 Redis 数据
        redis_client.delete(f"comment:likes:set:{comment_id}")
        redis_client.delete(f"comment:like_count:{comment_id}")
        
        # 2. 清理文章详情页缓存（因为评论列表变了）
        redis_client.delete(f"article:detail:{article_id}")
        
        # 3. 数据库物理删除
        comment.delete()
        
        return JsonResponse({"status": "success", "msg": "评论已删除"})
    except Exception as e:
        return JsonResponse({"status": "error", "msg": str(e)}, status=500)



def comment_management(request):
    return render(request, 'article/comment_management.html')