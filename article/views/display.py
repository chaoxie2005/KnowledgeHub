# 文章展示视图：详情页、分类列表、归档、Markdown/PDF 下载、图片上传
import logging
import json
import random
import os
import markdown
import bleach
import urllib.parse

# 允许的 HTML 标签/属性白名单（Markdown 渲染后仅保留安全元素）
_ALLOWED_TAGS = [
    "h1","h2","h3","h4","h5","h6","p","br","hr","a","img",
    "ul","ol","li","blockquote","pre","code","em","strong","del",
    "table","thead","tbody","tr","th","td","caption","colgroup","col",
    "span","div","dl","dt","dd","sup","sub","details","summary",
]
_ALLOWED_ATTRS = {
    "a": ["href","title","name"],
    "img": ["src","alt","title","width","height"],
    "th": ["align"], "td": ["align"],
    "col": ["width"], "colgroup": ["width"],
}
_ALLOWED_PROTOCOLS = ["http","https","mailto","ftp"]

def _safe_markdown(content, extensions=None):
    """将 Markdown 渲染为 HTML 并移除 XSS 风险标签（script、on* 等）"""
    html = markdown.markdown(content, extensions=extensions or [])
    return bleach.clean(html, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, protocols=_ALLOWED_PROTOCOLS, strip=True)

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.db.models import Q, Prefetch
from django.contrib.auth.models import User
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.core.cache import cache
from django_redis import get_redis_connection
from django.utils import timezone

from ..models import Article, Category, Comment, CommentLike
from ..forms import CommentForm
from .decorators import time_it

logger = logging.getLogger(__name__)

MARKDOWN_EXTENSIONS = [
    'markdown.extensions.extra',
    'markdown.extensions.codehilite',
    'markdown.extensions.toc',
    'markdown.extensions.nl2br',
]


def _batch_sync_comment_likes(comments):
    """批量同步 Redis 点赞数到评论对象，单次 Redis mget 避免 O(n) 往返"""
    all_ids = []
    for c in comments:
        all_ids.append(c.id)
        if hasattr(c, 'sorted_replies'):
            for r in c.sorted_replies:
                all_ids.append(r.id)

    if not all_ids:
        return

    redis_conn = get_redis_connection()
    keys = [f"comment:like_count:{cid}" for cid in all_ids]
    values = redis_conn.mget(keys)

    id_map = {}
    missing_ids = []
    for cid, val in zip(all_ids, values):
        if val is not None:
            id_map[cid] = int(val)
        else:
            missing_ids.append(cid)

    for c in comments:
        if c.id in id_map:
            c.like_count = id_map[c.id]
        elif c.id in missing_ids:
            cache.set(f"comment:like_count:{c.id}", c.like_count, timeout=86400 + random.randint(0, 3600))

        for r in (c.sorted_replies if hasattr(c, 'sorted_replies') else []):
            if r.id in id_map:
                r.like_count = id_map[r.id]
            elif r.id in missing_ids:
                cache.set(f"comment:like_count:{r.id}", r.like_count, timeout=86400 + random.randint(0, 3600))


# ---------------------------------------------------------------------------
# detail 辅助函数
# ---------------------------------------------------------------------------

def _handle_comment_post(request, article):
    """处理评论 POST 提交，返回 redirect 或 None（非 POST 请求）"""
    if request.method != "POST" or not request.user.is_authenticated:
        return None

    form = CommentForm(request.POST)
    if not form.is_valid():
        return None

    comment = form.save(commit=False)
    comment.article = article
    comment.user = request.user
    parent_id = request.POST.get("parent")
    if parent_id:
        try:
            comment.parent = Comment.objects.get(id=parent_id, article=article)
        except Comment.DoesNotExist:
            comment.parent = None

    from utils.content_audit import ContentAuditService
    audit_result = ContentAuditService().audit_content(comment.content, "comment")
    comment.is_audited = True
    comment.audit_passed = audit_result['passed']
    comment.violation_reasons = audit_result['violation_reasons']
    comment.audit_time = timezone.now()

    if not audit_result['passed']:
        messages.error(request, f"评论未通过审核：{'; '.join(audit_result['violation_reasons'])}")
        return redirect("article:detail", article_id=article.id)

    comment.save()
    return redirect("article:detail", article_id=article.id)


def _get_or_increment_read_count(article):
    """获取/递增文章阅读量，每 10 次访问同步到数据库"""
    read_count_key = f"article:read_count:{article.id}"
    current = cache.get(read_count_key)
    if not current:
        cache.set(read_count_key, article.read_count)

    redis_conn = get_redis_connection()
    redis_conn.incr(read_count_key)
    real_count = int(redis_conn.get(read_count_key))

    sync_key = f"article:sync_counter:{article.id}"
    sync_counter = int(cache.get(sync_key) or 0) + 1
    cache.set(sync_key, sync_counter)

    if sync_counter % 10 == 0:
        article.read_count = real_count
        article.save(update_fields=['read_count'])

    return real_count


def _get_navigation(article_id):
    prev_article = Article.objects.filter(
        id__lt=article_id, status="published"
    ).select_related("author", "category").order_by("-id").first()
    next_article = Article.objects.filter(
        id__gt=article_id, status="published"
    ).select_related("author", "category").order_by("id").first()
    return prev_article, next_article


def _get_sidebar_data():
    article_base = Article.objects.filter(status="published").select_related("author", "category").prefetch_related("tags")
    return {
        "hot_list": article_base.order_by("-read_count")[:5],
        "last_articles": article_base.order_by("-published_time")[:5],
        "categories": Category.objects.all(),
        "articles": article_base[:5],
        "archives": Article.objects.filter(status="published").dates('published_time', 'month', order='DESC'),
    }


def _get_article_comments(article):
    """获取文章的评论树（含嵌套回复 + 点赞预取）"""
    return article.comments.filter(parent=None).select_related("user").prefetch_related(
        Prefetch(
            "replies",
            queryset=Comment.objects.select_related("user").prefetch_related(
                Prefetch(
                    "replies",
                    queryset=Comment.objects.select_related("user").order_by("created_time"),
                    to_attr="sorted_replies"
                )
            ).order_by("created_time"),
            to_attr="sorted_replies"
        ),
        "comment_likes"
    )


def _get_liked_comment_ids(request, article_id):
    """获取当前用户在该文章下已点赞的评论 ID 列表"""
    if not request.user.is_authenticated:
        return []
    return list(CommentLike.objects.filter(
        user=request.user,
        comment__article_id=article_id
    ).values_list('comment_id', flat=True))


def _build_article_cache_data(article, rendered_content, read_count):
    """构建文章缓存字典"""
    author_profile = getattr(article.author, 'profile', None)
    tags = []
    if hasattr(article, 'tags'):
        tags = [{"id": t.id, "name": t.name} for t in article.tags.all()]

    return {
        "id": article.id,
        "title": article.title,
        "content": rendered_content,
        "content_raw": article.content,
        "rendered_content": rendered_content,
        "summary": article.summary,
        "created_time": article.created_time.strftime("%Y-%m-%d %H:%M"),
        "published_time": article.published_time.strftime("%Y-%m-%d %H:%M") if article.published_time else "",
        "author": article.author.username if article.author else "",
        "author_email": author_profile.email if author_profile else "",
        "author_phone": author_profile.phone if author_profile else "",
        "read_count": read_count,
        "status": article.status,
        "category_id": article.category.id if article.category else None,
        "category_name": article.category.name if article.category else "",
        "tags": tags,
        "cover": article.cover.url if article.cover else "",
    }


def _build_detail_context(article_data, prev_article, next_article,
                          sidebar, comments, liked_ids):
    """组装文章详情页模板上下文"""
    return {
        "article": article_data,
        "prev_article": prev_article,
        "next_article": next_article,
        "last_articles": sidebar["last_articles"],
        "hot_list": sidebar["hot_list"],
        "categories": sidebar["categories"],
        "comments": comments,
        "articles": sidebar["articles"],
        "archives": sidebar["archives"],
        "liked_comment_ids": liked_ids,
    }


# ---------------------------------------------------------------------------
# 视图函数
# ---------------------------------------------------------------------------

@time_it
def detail(request, article_id):
    """文章详情页（集成 Redis 缓存）"""
    article = get_object_or_404(
        Article.objects.select_related("author__profile", "category").prefetch_related("tags"),
        pk=article_id, status="published")
    cache_key = f"article:detail:{article_id}"

    # 评论提交
    result = _handle_comment_post(request, article)
    if result is not None:
        cache.delete(cache_key)
        return result

    # 阅读量
    real_read_count = _get_or_increment_read_count(article)

    # 侧边栏 & 导航 & 评论（缓存命中/未命中都需要）
    sidebar = _get_sidebar_data()
    prev_article, next_article = _get_navigation(article_id)
    comments = _get_article_comments(article)
    _batch_sync_comment_likes(comments)
    liked_ids = _get_liked_comment_ids(request, article_id)

    # 尝试缓存命中
    cached_article = cache.get(cache_key)
    if cached_article:
        article_data = json.loads(cached_article)
        article_data["read_count"] = real_read_count

        if "content_raw" in article_data:
            article_data["rendered_content"] = _safe_markdown(
                article_data["content_raw"], extensions=MARKDOWN_EXTENSIONS)
        else:
            raw = article_data.get("content", "")
            article_data["rendered_content"] = _safe_markdown(raw, extensions=MARKDOWN_EXTENSIONS)
        article_data["content"] = article_data["rendered_content"]

        context = _build_detail_context(
            article_data, prev_article, next_article, sidebar, comments, liked_ids)
        return render(request, "article/article_detail.html", context)

    # 缓存未命中 — 渲染 Markdown 并写入缓存
    rendered_content = _safe_markdown(article.content, extensions=MARKDOWN_EXTENSIONS)
    article_data = _build_article_cache_data(article, rendered_content, real_read_count)
    cache.set(cache_key, json.dumps(article_data), timeout=86400 + random.randint(0, 3600))

    context = _build_detail_context(
        article_data, prev_article, next_article, sidebar, comments, liked_ids)
    return render(request, "article/article_detail.html", context)


def category_list(request, category_id):
    """分类文章列表页"""
    try:
        category = Category.objects.get(id=category_id)
    except Category.DoesNotExist:
        category = None

    articles = Article.objects.filter(
        category_id=category_id, status="published"
    ).select_related("author", "category").prefetch_related("tags").order_by("-published_time")

    page = request.GET.get("page", 1)
    keyword = request.GET.get("keyword", "").strip()

    if keyword:
        articles = articles.filter(
            Q(title__icontains=keyword)
            | Q(summary__icontains=keyword)
            | Q(content__icontains=keyword)
            | Q(author__icontains=keyword)
        )

    paginator = Paginator(articles, 5)
    try:
        articles = paginator.page(page)
    except PageNotAnInteger:
        articles = paginator.page(1)
    except EmptyPage:
        articles = paginator.page(paginator.num_pages)

    sidebar = _get_sidebar_data()
    context = {
        "category": category,
        "articles": articles,
        "last_articles": sidebar["last_articles"],
        "hot_list": sidebar["hot_list"],
        "categories": sidebar["categories"],
        "about_articles": articles[:5],
        "archives": sidebar["archives"],
    }
    return render(request, "article/category_list.html", context)


def archive_list(request, archive_year, archive_month):
    """文章归档列表"""
    articles = Article.objects.filter(
        published_time__year=archive_year,
        published_time__month=archive_month,
        status="published",
    ).select_related("author", "category").prefetch_related("tags").order_by("-published_time")

    page = request.GET.get("page", 1)
    keyword = request.GET.get("keyword", "").strip()

    if keyword:
        articles = articles.filter(
            Q(title__icontains=keyword)
            | Q(summary__icontains=keyword)
            | Q(content__icontains=keyword)
        )

    paginator = Paginator(articles, 5)
    try:
        articles = paginator.page(page)
    except PageNotAnInteger:
        articles = paginator.page(1)
    except EmptyPage:
        articles = paginator.page(paginator.num_pages)

    sidebar = _get_sidebar_data()
    context = {
        "articles": articles,
        "last_articles": sidebar["last_articles"],
        "hot_list": sidebar["hot_list"],
        "categories": sidebar["categories"],
        "about_articles": articles[:5],
        "archives": sidebar["archives"],
        "year": archive_year,
        "month": archive_month,
        "article": {"year": archive_year, "month": archive_month},
    }
    return render(request, "article/archive_list.html", context)


def download_markdown(request, article_id):
    """下载文章 Markdown 文件"""
    article = get_object_or_404(Article, pk=article_id)
    response = HttpResponse(article.content, content_type='text/markdown; charset=utf-8')
    encoded_filename = urllib.parse.quote(f"{article.title}.md")
    response['Content-Disposition'] = f'attachment; filename="{encoded_filename}"'
    return response


def download_PDF(request, article_id):
    """下载文章 PDF 文件（支持缓存）"""
    article = get_object_or_404(Article, pk=article_id)

    pdf_cache_key = f"pdf:content:{article_id}:{article.updated_time.timestamp()}"
    cached_pdf = cache.get(pdf_cache_key)

    if cached_pdf:
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{article.title}.pdf"'
        response.write(cached_pdf)
        return response

    from weasyprint import HTML
    from io import BytesIO

    html_content = _safe_markdown(article.content, extensions=['extra', 'codehilite'])

    full_html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>{article.title}</title>
        <style>
            @font-face {{
                font-family: 'Noto Sans CJK SC';
                src: local('Noto Sans CJK SC'), local('NotoSansCJK-Regular');
            }}
            body {{
                font-family: 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'DejaVu Sans', 'Symbola', sans-serif;
                line-height: 1.6;
                margin: 20px;
                color: #333;
            }}
            h1, h2, h3, h4, h5, h6 {{
                font-family: 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'DejaVu Sans', 'Symbola', sans-serif;
                color: #2c3e50;
                margin-top: 1.5em;
                margin-bottom: 0.5em;
            }}
            p {{ margin-bottom: 1em; }}
            code {{
                background: #f4f4f4;
                padding: 2px 4px;
                border-radius: 3px;
                font-family: 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'DejaVu Sans', 'Symbola', monospace;
            }}
            pre {{
                background: #f4f4f4;
                padding: 10px;
                border-radius: 5px;
                overflow-x: auto;
            }}
            pre code {{ background: none; padding: 0; }}
            blockquote {{
                border-left: 4px solid #3498db;
                padding-left: 10px;
                margin: 1em 0;
                color: #666;
            }}
            img {{ max-width: 100%; height: auto; }}
        </style>
    </head>
    <body>
        <h1>{article.title}</h1>
        <p><em>发布时间: {article.published_time.strftime('%Y-%m-%d %H:%M')}</em></p>
        {html_content}
    </body>
    </html>
    '''

    pdf_buffer = BytesIO()
    try:
        HTML(string=full_html).write_pdf(pdf_buffer)
    except Exception:
        logger.exception("PDF 生成失败: article_id=%s", article_id)
        return HttpResponse("PDF生成失败", status=500)
    pdf_buffer.seek(0)

    pdf_content = pdf_buffer.read()
    cache.set(pdf_cache_key, pdf_content, timeout=86400)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{article.title}.pdf"'
    response.write(pdf_content)
    return response


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
