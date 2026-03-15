from django.shortcuts import render, get_object_or_404, redirect
from .models import Article, Category, Tag, Comment, CommentLike
from .forms import CommentForm
from django.core.paginator import Paginator, PageNotAnInteger, InvalidPage, EmptyPage
from django.db.models import Q
from django.utils.text import gettext_lazy as _
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.contrib.auth.models import User

def detail(request, article_id):
    """文章详情页"""
    article = get_object_or_404(Article, pk=article_id, status="published")

    article.read_count += 1  # 阅读量增加
    article.save(update_fields=["read_count"])

    prev_article = Article.objects.filter(id__lt=article_id, status='published').order_by("-id").first()
    next_article = Article.objects.filter(id__gt=article_id, status='published').order_by("id").first()

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

    # 只取 parent=None 的一级评论，按时间倒序（和模型 ordering 一致）
    comments = article.comments.filter(parent=None)

    # 处理评论提交
    if request.method == "POST" and request.user.is_authenticated:
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.article = article
            comment.user = request.user
            # 处理回复：如果有 parent 参数，设置父评论
            parent_id = request.POST.get("parent")
            if parent_id:
                try:
                    parent_comment = Comment.objects.get(id=parent_id, article=article)
                    comment.parent = parent_comment
                except Comment.DoesNotExist:
                    comment.parent = None
            comment.save()
            return redirect("article:detail", article_id=article_id)

    articles = Article.objects.filter(status='published')[:5]

    context = {
        "article": article,
        "prev_article": prev_article,
        "next_article": next_article,
        "last_articles": last_articles,  # 最新文章列表页
        "hot_list": hot_list,  # 热门文章列表页
        "categories": categories,  # 分类
        "comments": comments,  # 评论
        "articles": articles, # 推荐文章，按阅读量排序
    }
    return render(request, "article/article_detail.html", context)


def category_list(request, category_id):
    """与其标签相关的文章列表页"""
    articles = Article.objects.filter(category_id=category_id, status="published").order_by('-published_time')
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
    return render(request, "article/category_list.html", context)


def archive_list(request, archive_year, archive_month):
    """文章归档列表"""
    articles = Article.objects.filter(published_time__year=archive_year, published_time__month=archive_month, status="published").order_by('-published_time')

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

# 必须登录才能发布文章
@login_required(login_url='authentication:login')
def publish_article(request):
    """发布文章"""
    categories = Category.objects.all()
    tags = Tag.objects.all()

    if request.method == "GET":
        # 传递分类/标签到前端模板
        context = {"categories": categories, "tags": tags}
        return render(request, "article/publish_article.html", context)

    elif request.method == "POST":
        # 1. 初始化新文章对象，绑定作者
        article = Article()
        article.author = request.user

        # 2. 处理标题（必填 + 长度校验）
        title = request.POST.get("title", "").strip()
        if not title:
            messages.error(request, "文章标题不能为空！")
            return render(
                request,
                "article/publish_article.html",
                {"categories": categories, "tags": tags, "values": request.POST},
            )
        if len(title) > 200:  # 模型中title是max_length=200
            messages.error(request, "文章标题不能超过200字！")
            return render(
                request,
                "article/publish_article.html",
                {"categories": categories, "tags": tags, 'values': request.POST},
            )
        article.title = title

        # 3. 处理封面图（格式/大小校验）
        cover = request.FILES.get("cover")
        if cover:
            # 校验文件格式
            allowed_extensions = ["jpg", "jpeg", "png", "webp"]
            file_name = cover.name
            if not file_name or "." not in file_name:
                messages.error(request, "封面图格式无效，请上传jpg/jpeg/png/webp格式！")
                return render(
                    request,
                    "article/publish_article.html",
                    {"categories": categories, "tags": tags},
                )

            file_ext = file_name.split(".")[-1].lower()
            if file_ext not in allowed_extensions:
                messages.error(
                    request, f'封面图仅支持{"/".join(allowed_extensions)}格式！'
                )
                return render(
                    request,
                    "article/publish_article.html",
                    {"categories": categories, "tags": tags},
                )

            # 校验文件大小（2MB）
            max_size = 2 * 1024 * 1024  # 2MB
            if cover.size > max_size:
                messages.error(request, "封面图大小不能超过2MB！")
                return render(
                    request,
                    "article/publish_article.html",
                    {"categories": categories, "tags": tags},
                )

            # 校验通过，赋值封面图
            article.cover = cover

        # 4. 处理摘要（可选，模型中允许空）
        summary = request.POST.get("summary", "").strip()
        if summary and len(summary) > 500:
            messages.error(request, "文章摘要不能超过500字！")
            return render(
                request,
                "article/publish_article.html",
                {"categories": categories, "tags": tags, "values": request.POST},
            )
        article.summary = summary

        # 5. 处理正文（必填）
        content = request.POST.get("content", "").strip()
        if not content:
            messages.error(request, "文章内容不能为空！")
            return render(
                request,
                "article/publish_article.html",
                {"categories": categories, "tags": tags, "values": request.POST},
            )
        article.content = content

        # 6. 处理分类（可选，模型中允许空）
        category_id = request.POST.get("category")
        if category_id:
            try:
                category = Category.objects.get(id=category_id)
                article.category = category
            except Category.DoesNotExist:
                messages.warning(request, "选择的分类不存在，已自动置为空！")

        # 7. 处理发布/草稿状态
        action = request.POST.get("action", "draft")
        if action == "publish":
            article.status = "published"
            article.published_time = timezone.now()  # 发布时记录发布时间
        else:
            article.status = "draft"
            article.published_time = None  # 草稿不记录发布时间

        # 8. 保存文章主表（先保存才能处理多对多标签）
        article.save()

        # 9. 处理标签（多对多关系）
        tag_ids = request.POST.getlist("tags")  # 获取多选的标签ID列表
        if tag_ids:
            # 过滤有效的标签ID
            valid_tags = Tag.objects.filter(id__in=tag_ids)
            article.tags.set(valid_tags)  # 替换标签（清空原有 + 添加新的）

        # 10. 提示信息 + 跳转
        if action == "publish":
            messages.success(request, "文章发布成功！")
        else:
            messages.success(request, "文章已保存为草稿！")

        # 跳转到个人中心/文章列表（根据你的路由调整）
        return redirect("core:index")

    # 非GET/POST请求默认返回发布页面
    context = {"categories": categories, "tags": tags}
    return render(request, "article/publish_article.html", context)


@login_required(login_url="authentication:login")
def drafts(request):
    """草稿箱"""
    drafts = Article.objects.filter(author=request.user, status="draft")
    context = {"drafts": drafts,}
    return render(request, 'article/drafts.html', context)


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
    messages.success(request, '草稿删除成功！')
    return redirect(to='article:drafts')


@login_required(login_url="authentication:login")
def published(request):
    """已发布"""
    publisheds = Article.objects.filter(author=request.user, status="published")
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
