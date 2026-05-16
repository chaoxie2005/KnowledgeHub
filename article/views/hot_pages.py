# 第三方热榜页面：掘金热榜、CSDN 热榜（Redis 缓存）
import logging
import json
import random

from django.shortcuts import render
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.db.models import Q
from django.core.cache import cache

from ..models import JuejinHotArticle, CSDNArticle, Category
from ..ai_utils import generate_article_summary
from .decorators import time_it

logger = logging.getLogger(__name__)


def _get_categories():
    """获取分类列表（缓存 1 小时）"""
    cache_key = "global:all_categories"
    try:
        cached = cache.get(cache_key)
    except Exception:
        cached = None
    if cached:
        return json.loads(cached)
    categories = list(Category.objects.all().values('id', 'name'))
    try:
        cache.set(cache_key, json.dumps(categories), timeout=3600 + random.randint(0, 3600))
    except Exception:
        pass
    return categories


def _get_last_articles(model, order_field, limit=10):
    """获取最新 N 篇热榜文章（缓存 10 分钟）"""
    cache_key = f"{model.__name__.lower()}:hot:last{limit}"
    try:
        cached = cache.get(cache_key)
    except Exception:
        cached = None
    if cached:
        return json.loads(cached)
    articles = list(model.objects.all().order_by(f"-{order_field}").values('title', 'original_url')[:limit])
    try:
        cache.set(cache_key, json.dumps(articles), timeout=600 + random.randint(0, 3600))
    except Exception:
        pass
    return articles


def _ensure_summaries(article_list):
    """保障文章都有摘要（优先已有，其次 AI 生成，最后标题兜底）"""
    for art in article_list:
        current_summary = (art.summary or "").strip() or (art.ai_summary or "").strip()
        if current_summary:
            continue
        try:
            base_text = (art.title or "").strip() or "该文章暂无可用摘要内容"
            generated = generate_article_summary(base_text)
            generated = (generated or "").strip()
            if not generated or generated == "暂无摘要":
                generated = base_text
            art.summary = generated[:500]
            art.ai_summary = generated
            art.save(update_fields=["summary", "ai_summary"])
        except Exception:
            fallback = (art.title or "暂无摘要").strip()
            art.summary = fallback[:500]
            art.ai_summary = fallback
            try:
                art.save(update_fields=["summary", "ai_summary"])
            except Exception:
                pass


def _hot_page_view(request, model, cache_prefix, order_field, template_name,
                   summarizer=None, prefetch=None):
    """
    通用热榜视图：处理缓存命中 / 未命中、分页、关键词搜索。

    - model: 文章模型类
    - cache_prefix: Redis 缓存键前缀 (e.g. "juejin:hot:v2")
    - order_field: 排序字段 (e.g. "published_time" 或 "crawl_time")
    - template_name: 渲染模板名
    - summarizer: 可选，接受 article_list 的摘要保障函数
    - prefetch: 可选，prefetch_related 字段名
    """
    page = request.GET.get("page", 1)
    keyword = request.GET.get("keyword", "").strip()
    try:
        page = int(page)
    except (ValueError, TypeError):
        page = 1

    keyword_key = keyword if keyword else "all"
    cache_key = f"{cache_prefix}:{keyword_key}:p{page}"

    # 尝试从 Redis 读取分页后的 ID 列表
    id_list = None
    try:
        cached_data = cache.get(cache_key)
        if cached_data:
            id_list = json.loads(cached_data)
    except Exception:
        logger.warning("Redis 读取 %s 失败", cache_key, exc_info=True)

    # 命中主列表缓存
    if id_list:
        try:
            qs = model.objects.filter(id__in=id_list)
            if prefetch:
                qs = qs.prefetch_related(prefetch)
            id_map = {art.id: art for art in qs}
            articles_list = [id_map[aid] for aid in id_list if aid in id_map]

            total_count = model.objects.all().count()
            if keyword:
                total_count = model.objects.filter(Q(title__icontains=keyword)).count()

            paginator = Paginator(range(total_count), 5)
            articles = paginator.page(page)
            if summarizer:
                summarizer(articles_list)
            articles.object_list = articles_list
        except Exception:
            logger.warning("处理 %s 缓存数据失败，降级到数据库查询", model.__name__, exc_info=True)
            id_list = None

    # 未命中主列表缓存 — 查数据库
    if not id_list:
        articles_query = model.objects.all().order_by(f"-{order_field}")
        if prefetch:
            articles_query = articles_query.prefetch_related(prefetch)
        if keyword:
            articles_query = articles_query.filter(
                Q(title__icontains=keyword) | Q(summary__icontains=keyword)
            )

        paginator = Paginator(articles_query, 5)
        try:
            articles = paginator.page(page)
        except (PageNotAnInteger, EmptyPage):
            articles = paginator.page(1)

        if summarizer:
            summarizer(articles.object_list)

        try:
            current_ids = [art.id for art in articles.object_list]
            cache.set(cache_key, json.dumps(current_ids), timeout=600 + random.randint(0, 3600))
        except Exception:
            pass

    categories = _get_categories()
    last_articles = _get_last_articles(model, order_field)

    return render(request, template_name, {
        "articles": articles,
        "categories": categories,
        "last_articles": last_articles,
    })


@time_it
def juejin_hot(request):
    """稀土掘金热榜"""
    return _hot_page_view(
        request,
        model=JuejinHotArticle,
        cache_prefix="juejin:hot:v2",
        order_field="published_time",
        template_name="article/juejin_hot.html",
        summarizer=_ensure_summaries,
        prefetch="tags",
    )


@time_it
def csdn_hot(request):
    """CSDN热榜"""
    return _hot_page_view(
        request,
        model=CSDNArticle,
        cache_prefix="csdn:hot:v2",
        order_field="crawl_time",
        template_name="article/csdn_hot.html",
    )
