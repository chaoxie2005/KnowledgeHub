# 文章增删改查：发布、草稿箱、已发布编辑/删除
import json
import logging

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.core.cache import cache
from django.db.models import Q

from ..models import Article, Category, Tag

logger = logging.getLogger(__name__)


def _audit_article_content(article):
    """对文章内容执行 AI 审核并设置审核状态字段"""
    from utils.content_audit import ContentAuditService
    audit_service = ContentAuditService()
    audit_result = audit_service.audit_content(article.content, "article")
    article.is_audited = True
    article.audit_passed = audit_result['passed']
    article.violation_reasons = audit_result['violation_reasons']
    article.audit_time = timezone.now()
    return audit_result


def _process_article_tags(request, article):
    """解析请求中的标签字符串，创建/获取 Tag 并关联到文章"""
    tag_str = request.POST.get("tags", "")
    logger.info(f"[TAG_DEBUG] 原始 tags 值: {repr(tag_str)}")
    logger.info(f"[TAG_DEBUG] POST keys: {list(request.POST.keys())}")
    tag_names = [t.strip() for t in tag_str.split(",") if t.strip()]
    logger.info(f"[TAG_DEBUG] 解析后 tag_names: {tag_names}")
    final_tags = []
    for name in tag_names:
        tag, _created = Tag.objects.get_or_create(name=name)
        final_tags.append(tag)
        logger.info(f"[TAG_DEBUG] 标签 '{name}' {'已创建' if _created else '已存在'}")
    article.tags.set(final_tags)
    logger.info(f"[TAG_DEBUG] article.tags.set({[t.name for t in final_tags]}) 完成")


@login_required(login_url="authentication:login")
def publish_article(request):
    """发布文章（支持：选择已有标签 + 自定义标签自动创建（暂时有bug，不能正确自定义标签入库））"""
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
            max_size = 4 * 1024 * 1024
            if cover.size > max_size:
                messages.error(request, "封面不能超过4MB！")
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

        # 9. AI内容审核
        audit_result = _audit_article_content(article)
        if not audit_result['passed']:
            messages.error(request, f"文章未通过审核：{'; '.join(audit_result['violation_reasons'])}")
            return render(
                request,
                "article/publish_article.html",
                {"categories": categories, "tags": tags, "values": request.POST},
            )

        # 10. 保存文章
        article.save()

        # 标签核心逻辑：支持选择 + 自定义
        _process_article_tags(request, article)

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
    cached_data = cache.get(cache_key)

    # ======================
    # 永远优先查数据库，缓存只用来加速，不影响正确性
    # ======================
    drafts = Article.objects.filter(
        author=request.user,
        status="draft"
    ).select_related("author", "category").prefetch_related("tags").order_by("-created_time")

    # 刷新缓存（保证缓存和数据库一致）
    article_ids = list(drafts.values_list("id", flat=True))
    cache.set(cache_key, json.dumps(article_ids), timeout=600)

    context = {"drafts": drafts}
    return render(request, "article/drafts.html", context)


@login_required(login_url="authentication:login")
def edit_draft(request, draft_id):
    """编辑草稿箱"""
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
            max_size = 4 * 1024 * 1024  # 4MB
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

        # 更新状态（草稿/发布）
        if action == "publish":
            article.status = "published"
            article.published_time = timezone.now()  # 发布时记录时间
        else:
            article.status = "draft"

        # AI内容审核
        audit_result = _audit_article_content(article)
        if not audit_result['passed']:
            messages.error(request, f"文章未通过审核：{'; '.join(audit_result['violation_reasons'])}")
            return render(
                request,
                "article/edit_draft.html",
                {"article": article, "categories": categories, "tags": tags},
            )

        # 保存修改
        article.save()

        # 更新标签（支持选择 + 自定义，放在 save 之后确保数据一致性）
        _process_article_tags(request, article)

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
    """已发布文章"""
    # 1. 强制从数据库拿真实数据（保证一定能显示）
    publisheds = Article.objects.filter(
        author=request.user,
        status="published"
    ).select_related("author", "category").prefetch_related("tags").order_by("-published_time")

    # 2. 刷新缓存（保证缓存最新）
    cache_key = f'user:{request.user.id}:published_articles'
    article_ids = list(publisheds.values_list('id', flat=True))
    cache.set(cache_key, json.dumps(article_ids), timeout=600)

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
            max_size = 4 * 1024 * 1024  # 4MB
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

        # 核心调整：已发布文章编辑后的状态逻辑
        if action == "publish":
            article.status = "published"
            # 已发布文章编辑后，发布时间不重置（保留首次发布时间）
            article.updated_time = timezone.now()
        else:
            # 改为草稿时，清空发布时间
            article.status = "draft"
            article.published_time = None

        # AI内容审核
        audit_result = _audit_article_content(article)
        if not audit_result['passed']:
            messages.error(request, f"文章未通过审核：{'; '.join(audit_result['violation_reasons'])}")
            return render(
                request,
                "article/edit_published.html",
                {"article": article, "categories": categories, "tags": tags},
            )

        # 保存修改
        article.save()

        # 更新标签（支持选择 + 自定义，放在 save 之后确保数据一致性）
        _process_article_tags(request, article)

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
