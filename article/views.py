from django.shortcuts import render, get_object_or_404, redirect
from .models import Article, Category, Tag, Comment, CommentLike, JuejinHotArticle
from .forms import CommentForm
from django.core.paginator import Paginator, PageNotAnInteger, InvalidPage, EmptyPage
from django.db.models import Q
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
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import markdown
from django.views.decorators.http import require_POST
from .ai_utils import optimize_article_title, generate_article_summary
import redis
from utils.redis_client import redis_client
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from django.db.models import Prefetch
from utils.rag_chain import simple_rag_qa


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
    search_fields = ["title", "content"]
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
        
        # 每次都查最新评论，不走缓存
        comments = article.comments.filter(parent=None).select_related("user").prefetch_related(
            Prefetch(
                "replies",
                queryset=Comment.objects.select_related("user").order_by("created_time"),
                to_attr="sorted_replies"
            )
        )
        
        context = {
            "article": article_data,
            "prev_article": prev_article,
            "next_article": next_article,
            "last_articles": last_articles,
            "hot_list": hot_list,
            "categories": categories,
            "comments": comments,
            "articles": articles,
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
        )
    )
    
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
    
    redis_client.set(cache_key, json.dumps(article_data), ex=7200)
    
    context = {
        "article": article_data,
        "prev_article": prev_article,
        "next_article": next_article,
        "last_articles": last_articles,
        "hot_list": hot_list,
        "categories": categories,
        "comments": comments,
        "articles": articles,
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


def spdier(request):
    """爬虫视图（加Redis缓存优化）"""
    page = request.GET.get("page", 1)
    keyword = request.GET.get("keyword", "").strip()
    # 统一页码格式（避免字符串/数字问题）
    try:
        page = int(page)
    except (ValueError, TypeError):
        page = 1

    # ========== 2. 定义缓存键 ==========
    # 基础键：区分关键词（无关键词则用 empty）+ 页码
    keyword_key = keyword if keyword else "empty"
    cache_key = f"juejin:hot:{keyword_key}:page{page}"
    # 静态数据缓存键
    category_cache_key = "global:all_categories"
    last_articles_cache_key = "juejin:hot:last10"

    # 查Redis缓存
    cached_data = redis_client.get(cache_key)
    articles = None

    if cached_data:
        # 缓存存在：解析ID列表，查数据库取最新数据
        article_ids = json.loads(cached_data)
        # 按ID查文章
        article_list = JuejinHotArticle.objects.filter(id__in=article_ids)
        # 按ID排序（保持缓存里的顺序）
        id_to_article = {art.id: art for art in article_list}
        article_list = [id_to_article[id] for id in article_ids if id in id_to_article]

        # 手动构造分页对象
        # 先查总数据量
        total_articles = JuejinHotArticle.objects.all()
        if keyword:
            total_articles = total_articles.filter(
                Q(title__icontains=keyword)
                | Q(summary__icontains=keyword)
                | Q(ai_summary__icontains=keyword)
                | Q(author__icontains=keyword)
            )
        paginator = Paginator(total_articles, 5)
        # 构造分页对象
        articles = paginator.page(page)
        # 替换分页对象的object_list为缓存查出来的文章列表
        articles.object_list = article_list
    else:
        # 缓存不存在 查数据库
        articles_query = JuejinHotArticle.objects.all()
        if keyword:
            articles_query = articles_query.filter(
                Q(title__icontains=keyword)
                | Q(summary__icontains=keyword)
                | Q(ai_summary__icontains=keyword)
            )
        # 分页处理
        paginator = Paginator(articles_query, 5)
        try:
            articles = paginator.page(page)
        except PageNotAnInteger:
            articles = paginator.page(1)
        except EmptyPage:
            articles = paginator.page(paginator.num_pages)
        except Exception:
            articles = paginator.page(1)

        # ========== 存入Redis缓存 ==========
        # 提取当前页的文章ID列表
        article_ids = [art.id for art in articles.object_list]
        # 存入Redis，10分钟（600秒）过期
        redis_client.set(cache_key, json.dumps(article_ids), ex=600)

    # ========== 静态数据缓存（分类+最新10篇） ==========
    # 6.1 分类列表缓存（1小时过期）
    cached_categories = redis_client.get(category_cache_key)
    if cached_categories:
        category_data = json.loads(cached_categories)
        # 转成前端能用的格式（模拟QuerySet）
        categories = [
            {"id": item["id"], "name": item["name"]} for item in category_data
        ]
    else:
        categories = Category.objects.all()
        category_data = [{"id": cat.id, "name": cat.name} for cat in categories]
        redis_client.set(category_cache_key, json.dumps(category_data), ex=3600)

    # 最新10篇文章缓存（10分钟过期）
    cached_last_articles = redis_client.get(last_articles_cache_key)
    if cached_last_articles:
        last_article_ids = json.loads(cached_last_articles)
        last_articles = JuejinHotArticle.objects.filter(id__in=last_article_ids)
        id_to_last = {art.id: art for art in last_articles}
        last_articles = [id_to_last[id] for id in last_article_ids if id in id_to_last]
    else:
        last_articles = JuejinHotArticle.objects.all()[:10]
        last_article_ids = [art.id for art in last_articles]
        redis_client.set(last_articles_cache_key, json.dumps(last_article_ids), ex=600)

    context = {
        "articles": articles,
        "categories": categories,
        "last_articles": last_articles,
    }
    return render(request, "article/juejin_hot.html", context)


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


# ====================== 新增：LangChain RAG 文章问答接口（最终稳定版） ======================
@login_required
@require_POST
def article_ai_qa(request, article_id):
    try:
        # 从数据库直接获取文章（不走缓存，保证拿到原始内容）
        article = Article.objects.get(id=article_id, status="published")
        
        # 获取用户问题
        question = request.POST.get("question", "").strip()
        if not question:
            return JsonResponse({"code": 400, "msg": "请输入问题"})

        # 调用 RAG 函数（导入正确后不会再报错）
        answer = simple_rag_qa(article.content, question)
        return JsonResponse({
            "code": 200,
            "answer": answer
        })

    except Article.DoesNotExist:
        return JsonResponse({"code": 404, "msg": "文章不存在"})
    except Exception as e:
        # 打印详细日志，方便排查
        import traceback
        traceback.print_exc()
        return JsonResponse({"code": 500, "msg": f"服务异常：{str(e)}"})