# 评论功能：点赞/取消点赞(Redis 事务)、删除、评论管理页
import logging
import random

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import F
from django.core.cache import cache
from django_redis import get_redis_connection

from ..models import Comment, CommentLike

logger = logging.getLogger(__name__)


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
        # 使用底层Redis客户端
        redis_conn = get_redis_connection()

        # 1. 检查用户是否已在 Redis 集合中（判断是否点赞）
        is_liked = redis_conn.sismember(likes_set_key, user_id)

        # 2. 开启 Redis Pipeline (实现事务原子性)
        pipe = redis_conn.pipeline()

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

        # 5. 获取最新点赞数：pipeline 已 incr/decr 到 raw key，用 raw get 读取
        new_like_count = redis_conn.get(like_count_key)
        if new_like_count is None:
            comment.refresh_from_db()
            new_like_count = comment.like_count
            redis_conn.set(like_count_key, new_like_count, ex=86400 + random.randint(0, 3600))
        else:
            new_like_count = int(new_like_count)
            if new_like_count < 0:
                new_like_count = 0
                redis_conn.set(like_count_key, 0)

        return JsonResponse({
            "status": "success",
            "action": action,
            "like_count": new_like_count
        })

    except Exception:
        logger.exception("评论点赞失败: comment_id=%s, user_id=%s", comment_id, user_id)
        return JsonResponse({"status": "error", "msg": "操作失败"}, status=500)


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
        # 1. 先删数据库，避免并发窗口
        comment.delete()

        # 2. 再清理缓存
        redis_conn = get_redis_connection()
        redis_conn.delete(f"comment:likes:set:{comment_id}", f"comment:like_count:{comment_id}")
        cache.delete(f"article:detail:{article_id}")

        return JsonResponse({"status": "success", "msg": "评论已删除"})
    except Exception:
        logger.exception("删除评论失败: comment_id=%s", comment_id)
        return JsonResponse({"status": "error", "msg": "删除失败"}, status=500)


def comment_management(request):
    """评论管理"""
    return render(request, 'article/comment_management.html')
