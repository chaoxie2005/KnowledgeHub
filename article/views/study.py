# 学习计划：创建/获取计划、每日打卡、学习统计仪表板
import logging
import json

from datetime import timedelta
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Count

from ..models import Article, StudyPlan, StudyPlanItem, QuizAttempt, WrongQuestionRecord

logger = logging.getLogger(__name__)


@login_required(login_url="authentication:login")
@require_POST
def create_or_get_study_plan(request):
    """功能C：创建/获取学习计划（支持7天自动推荐 + 自定义计划）"""
    today = timezone.localdate()
    custom_items_raw = request.POST.get("custom_items", "").strip()
    plan_id = request.POST.get("plan_id", "").strip()

    if custom_items_raw:
        try:
            custom_items = json.loads(custom_items_raw)
            if not isinstance(custom_items, list) or not custom_items:
                return JsonResponse({"code": 400, "msg": "自定义计划数据格式无效"})
        except (json.JSONDecodeError, TypeError):
            return JsonResponse({"code": 400, "msg": "自定义计划解析失败"})

        title = (request.POST.get("title", "") or "").strip() or "自定义学习计划"
        start_date_str = (request.POST.get("start_date", "") or "").strip()
        start_date = today
        if start_date_str:
            try:
                start_date = timezone.datetime.strptime(start_date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                start_date = today

        plan = StudyPlan.objects.create(
            user=request.user,
            title=title,
            total_days=max(1, len(custom_items)),
            start_date=start_date,
        )
        for idx, item in enumerate(custom_items, start=1):
            article_id = item.get("article_id")
            minutes = item.get("target_minutes", 20)
            article = Article.objects.filter(id=article_id, status="published").first() if article_id else None
            try:
                minutes = int(minutes)
            except (ValueError, TypeError):
                minutes = 20
            minutes = max(5, min(minutes, 300))
            StudyPlanItem.objects.create(plan=plan, day_index=idx, article=article, target_minutes=minutes)
    else:
        plan = None
        if plan_id:
            plan = StudyPlan.objects.filter(id=plan_id, user=request.user).prefetch_related("items__article").first()
        if not plan:
            plan = StudyPlan.objects.filter(user=request.user).prefetch_related("items__article").order_by("-created_time").first()

        if not plan:
            plan = StudyPlan.objects.create(user=request.user, title="7天学习计划", total_days=7, start_date=today)
            candidates = list(Article.objects.filter(status="published").select_related("author", "category").order_by("-read_count", "-published_time")[:30])
            if not candidates:
                return JsonResponse({"code": 400, "msg": "暂无可推荐文章，请先发布内容"})
            for day in range(1, 8):
                article = candidates[(day - 1) % len(candidates)]
                StudyPlanItem.objects.create(plan=plan, day_index=day, article=article, target_minutes=20)

    items = plan.items.select_related("article").order_by("day_index")
    data = []
    for item in items:
        recommend_date = plan.start_date + timedelta(days=item.day_index - 1)
        data.append(
            {
                "item_id": item.id,
                "day_index": item.day_index,
                "date": recommend_date.strftime("%Y-%m-%d"),
                "article_id": item.article_id,
                "article_title": item.article.title if item.article else "暂无推荐",
                "target_minutes": item.target_minutes,
                "is_checked_in": item.is_checked_in,
            }
        )
    checked_count = sum(1 for i in data if i["is_checked_in"])
    return JsonResponse(
        {
            "code": 200,
            "plan_id": plan.id,
            "title": plan.title,
            "total_days": plan.total_days,
            "start_date": plan.start_date.strftime("%Y-%m-%d"),
            "progress": f"{checked_count}/{plan.total_days}",
            "items": data,
        }
    )


@login_required(login_url="authentication:login")
@require_POST
def study_plan_checkin(request, item_id):
    """功能C：学习计划每日打卡"""
    item = get_object_or_404(StudyPlanItem, id=item_id, plan__user=request.user)
    if not item.is_checked_in:
        item.is_checked_in = True
        item.checked_in_at = timezone.now()
        item.save(update_fields=["is_checked_in", "checked_in_at"])
    return JsonResponse({"code": 200, "msg": "打卡成功", "checked_in": True})


@login_required(login_url="authentication:login")
def learning_dashboard_stats(request):
    """学习中心统计数据"""
    total_attempts = QuizAttempt.objects.filter(user=request.user).count()
    correct_attempts = QuizAttempt.objects.filter(user=request.user, is_correct=True).count()
    wrong_pending = WrongQuestionRecord.objects.filter(user=request.user, resolved=False).count()
    knowledge_points = (
        WrongQuestionRecord.objects.filter(user=request.user, resolved=False)
        .exclude(knowledge_point="")
        .values("knowledge_point")
        .annotate(total=Count("id"))
        .order_by("-total")[:5]
    )
    active_plan = StudyPlan.objects.filter(user=request.user).order_by("-created_time").first()
    checked_days = 0
    if active_plan:
        checked_days = active_plan.items.filter(is_checked_in=True).count()
    accuracy = round((correct_attempts / total_attempts) * 100, 2) if total_attempts else 0
    return JsonResponse(
        {
            "code": 200,
            "stats": {
                "total_attempts": total_attempts,
                "accuracy": accuracy,
                "wrong_pending": wrong_pending,
                "checked_days": checked_days,
                "top_knowledge_points": list(knowledge_points),
            },
        }
    )
