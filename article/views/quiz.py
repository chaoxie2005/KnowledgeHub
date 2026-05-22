# 测验系统：LLM 出题、提交答案、错题本
import logging
import json
import concurrent.futures

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.db.models import Max

from ..models import Article, QuizQuestion, QuizAttempt, WrongQuestionRecord
from ..ai_utils import _get_llm as ai_utils_get_llm

logger = logging.getLogger(__name__)


def _fallback_quiz_questions(article):
    """当LLM不可用时，使用固定模板生成题目，保证功能可用"""
    base = article.summary or article.content[:400]
    short_title = article.title[:30]
    return [
        {
            "question": f"《{short_title}》最核心解决的问题是什么？",
            "options": {
                "A": "提升前端页面动画表现",
                "B": "围绕文章主题完成技术问题分析与实现",
                "C": "只讨论数据库表结构设计",
                "D": "仅介绍团队管理经验",
            },
            "answer": "B",
            "explanation": "文章的核心通常是围绕主题问题提出方案并给出实现路径。",
            "knowledge_point": "主题理解",
        },
        {
            "question": "学习这篇文章时，最推荐的方式是什么？",
            "options": {
                "A": "只看标题，不看正文",
                "B": "先看摘要，再结合正文和问答复盘",
                "C": "只收藏，不实践",
                "D": "只看评论区",
            },
            "answer": "B",
            "explanation": "先建立框架再深入细节，有助于提高理解效率。",
            "knowledge_point": "学习方法",
        },
        {
            "question": f"以下哪项最可能属于《{short_title}》的关键知识点？",
            "options": {
                "A": "随机娱乐资讯",
                "B": "与主题相关的技术实现细节",
                "C": "纯文学赏析",
                "D": "体育赛事总结",
            },
            "answer": "B",
            "explanation": "技术文章的关键知识点通常是与主题直接相关的实现细节。",
            "knowledge_point": "关键知识点识别",
        },
        {
            "question": "如果你要将本文内容用于项目实践，第一步最合理的是？",
            "options": {
                "A": "提炼目标场景与输入输出",
                "B": "直接上线到生产环境",
                "C": "忽略边界条件",
                "D": "删除原有代码后再说",
            },
            "answer": "A",
            "explanation": "先明确场景和目标，再进行实现更稳妥。",
            "knowledge_point": "工程实践",
        },
        {
            "question": "关于本文学习复盘，以下做法最佳的是？",
            "options": {
                "A": "不做记录",
                "B": "记录关键结论、错题和下一步行动",
                "C": "只截图保存",
                "D": "只记住术语",
            },
            "answer": "B",
            "explanation": "复盘应覆盖结论、薄弱点和行动计划，形成学习闭环。",
            "knowledge_point": "学习复盘",
        },
    ]


def _generate_quiz_by_llm(article):
    try:
        # 优先复用问答链路使用的同一LLM配置，避免"问答可用但出题不可用"
        llm, error = ai_utils_get_llm()
        if error:
            logger.warning("【出题LLM初始化失败】%s", error)
            return None

        try:
            from langchain_core.prompts import ChatPromptTemplate
        except ModuleNotFoundError as e:
            logger.warning("【出题LLM依赖缺失】%s", e)
            return None

        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "你是一位出题老师。请基于文章内容生成5道单选题，覆盖核心概念、实现细节和实践要点。"
                "必须输出合法JSON数组，每个元素格式为："
                "{{\"question\":\"...\",\"options\":{{\"A\":\"...\",\"B\":\"...\",\"C\":\"...\",\"D\":\"...\"}},"
                "\"answer\":\"A|B|C|D\",\"explanation\":\"...\",\"knowledge_point\":\"...\"}}。"
                "不要输出除JSON以外的任何文字。",
            ),
            ("human", "文章标题：{title}\n文章内容：{content}"),
        ])
        chain = prompt | llm

        # 由于LLM配置为流式输出模式，需要使用stream()方法收集完整响应
        # 不能使用invoke()，因为流式模式下invoke()返回的result.content可能为空
        text = ""
        for chunk in chain.stream({"title": article.title, "content": article.content[:4000]}):
            # 兼容不同类型的chunk返回值（字符串或带content属性的对象）
            chunk_text = chunk if isinstance(chunk, str) else getattr(chunk, "content", "")
            text += chunk_text

        text = text.strip()
        if not text:
            logger.warning("【出题LLM返回为空】流式收集结果为空")
            return None

        # 兼容模型输出 ```json ... ``` 包裹格式
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1:
            logger.warning("【出题LLM返回格式异常】未找到JSON数组，原始输出前200字符：%s", text[:200])
            return None
        payload = text[start : end + 1]
        parsed = json.loads(payload)
        if not isinstance(parsed, list) or len(parsed) < 5:
            logger.warning("【出题LLM返回题目不足】期望5题，实际%d题", len(parsed) if isinstance(parsed, list) else 0)
            return None
        return parsed[:5]
    except Exception as e:
        logger.exception("【出题LLM异常】%s", e)
        return None


@login_required(login_url="authentication:login")
@require_POST
def generate_article_quiz(request, article_id):
    """功能A：为文章生成5道测验题"""
    article = get_object_or_404(Article, id=article_id, status="published")
    force_regen = request.POST.get("force") == "1"
    logger.info("【出题请求】文章ID: %d, 文章标题: %s, 强制重新生成: %s", article_id, article.title, force_regen)

    if force_regen:
        QuizQuestion.objects.filter(article=article).delete()
        logger.info("【出题请求】已删除文章 %d 的现有题目", article_id)

    existing = list(QuizQuestion.objects.filter(article=article).order_by("-created_time")[:5])
    if len(existing) >= 5 and not force_regen:
        logger.info("【出题请求】使用缓存题目，数量: %d", len(existing))
        data = [
            {
                "id": q.id,
                "question": q.question,
                "options": {"A": q.option_a, "B": q.option_b, "C": q.option_c, "D": q.option_d},
                "knowledge_point": q.knowledge_point,
            }
            for q in existing
        ]
        return JsonResponse({"code": 200, "questions": data, "msg": "已返回现有题目"})

    generated = None
    try:
        # 避免第三方LLM偶发阻塞导致前端一直等待，这里设置超时自动降级
        # 增加超时时间到60秒，因为流式输出可能较慢
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_generate_quiz_by_llm, article)
            generated = future.result(timeout=60)
    except concurrent.futures.TimeoutError:
        logger.warning("【出题请求】LLM调用超时（超过60秒），使用降级模板")
        generated = None
    except Exception as e:
        logger.warning("【出题请求】LLM调用异常: %s", str(e))
        generated = None

    if generated:
        logger.info("【出题请求】LLM成功生成 %d 道题目", len(generated))
    else:
        logger.warning("【出题请求】LLM生成失败，使用降级模板")

    generated = generated or _fallback_quiz_questions(article)
    created_questions = []
    for item in generated[:5]:
        options = item.get("options", {})
        answer = (item.get("answer") or "A").upper()
        if answer not in ("A", "B", "C", "D"):
            answer = "A"
        q = QuizQuestion.objects.create(
            article=article,
            question=item.get("question", "这篇文章最重要的知识点是什么？"),
            option_a=options.get("A", "选项A"),
            option_b=options.get("B", "选项B"),
            option_c=options.get("C", "选项C"),
            option_d=options.get("D", "选项D"),
            correct_option=answer,
            explanation=item.get("explanation", ""),
            knowledge_point=item.get("knowledge_point", ""),
        )
        created_questions.append(
            {
                "id": q.id,
                "question": q.question,
                "options": {"A": q.option_a, "B": q.option_b, "C": q.option_c, "D": q.option_d},
                "knowledge_point": q.knowledge_point,
            }
        )
    return JsonResponse({"code": 200, "questions": created_questions, "msg": "题目生成成功"})


@login_required(login_url="authentication:login")
@require_POST
def submit_quiz_answer(request, question_id):
    """功能B：提交答案并写入错题本"""
    question = get_object_or_404(QuizQuestion, id=question_id)
    selected = (request.POST.get("selected_option", "") or "").upper().strip()
    if selected not in ("A", "B", "C", "D"):
        return JsonResponse({"code": 400, "msg": "答案选项无效"})

    is_correct = selected == question.correct_option
    QuizAttempt.objects.create(
        user=request.user,
        question=question,
        selected_option=selected,
        is_correct=is_correct,
    )

    if is_correct:
        WrongQuestionRecord.objects.filter(user=request.user, question=question, resolved=False).update(resolved=True)
    else:
        WrongQuestionRecord.objects.create(
            user=request.user,
            question=question,
            selected_option=selected,
            correct_option=question.correct_option,
            knowledge_point=question.knowledge_point,
        )

    return JsonResponse(
        {
            "code": 200,
            "is_correct": is_correct,
            "correct_option": question.correct_option,
            "explanation": question.explanation,
            "knowledge_point": question.knowledge_point,
        }
    )


@login_required(login_url="authentication:login")
def wrong_question_book(request):
    """功能B：错题本列表（保留历史，支持反复刷题，支持分页）"""
    include_resolved = request.GET.get("include_resolved", "1") == "1"
    base_qs = WrongQuestionRecord.objects.filter(user=request.user).select_related("question", "question__article")
    if not include_resolved:
        base_qs = base_qs.filter(resolved=False)
    else:
        base_qs = base_qs.filter(resolved=True)

    # 分页参数
    try:
        page = int(request.GET.get("page", "1"))
        page = max(1, page)
    except (ValueError, TypeError):
        page = 1
    try:
        page_size = int(request.GET.get("page_size", "20"))
        page_size = max(5, min(page_size, 50))
    except (ValueError, TypeError):
        page_size = 20

    # 按题目分组分页：先获取最近出错的题目 ID 列表，再切分
    ordered_qids = list(
        base_qs.values("question_id")
        .annotate(last_wrong=Max("created_time"))
        .order_by("-last_wrong")
        .values_list("question_id", flat=True)
    )
    total_groups = len(ordered_qids)
    start = (page - 1) * page_size
    end = start + page_size
    page_qids = ordered_qids[start:end]

    records = base_qs.filter(question_id__in=page_qids).order_by("-created_time") if page_qids else base_qs.none()

    data = []
    grouped = {}
    for r in records:
        item = {
            "record_id": r.id,
            "article_id": r.question.article_id,
            "article_title": r.question.article.title,
            "question_id": r.question.id,
            "question": r.question.question,
            "selected_option": r.selected_option,
            "correct_option": r.correct_option,
            "knowledge_point": r.knowledge_point or r.question.knowledge_point,
            "explanation": r.question.explanation,
            "resolved": r.resolved,
            "created_time": r.created_time.strftime("%Y-%m-%d %H:%M"),
            "options": {
                "A": r.question.option_a,
                "B": r.question.option_b,
                "C": r.question.option_c,
                "D": r.question.option_d,
            },
        }
        data.append(item)

        qid = r.question_id
        if qid not in grouped:
            grouped[qid] = {
                "question_id": qid,
                "question": r.question.question,
                "article_title": r.question.article.title,
                "knowledge_point": r.knowledge_point or r.question.knowledge_point,
                "correct_option": r.correct_option,
                "resolved": r.resolved,
                "attempts": [],
                "options": {
                    "A": r.question.option_a,
                    "B": r.question.option_b,
                    "C": r.question.option_c,
                    "D": r.question.option_d,
                },
            }
        grouped[qid]["attempts"].append(
            {
                "record_id": r.id,
                "selected_option": r.selected_option,
                "resolved": r.resolved,
                "created_time": r.created_time.strftime("%Y-%m-%d %H:%M"),
            }
        )
        grouped[qid]["resolved"] = grouped[qid]["resolved"] and r.resolved

    has_next = page * page_size < total_groups
    return JsonResponse({
        "code": 200,
        "records": data,
        "grouped_records": list(grouped.values()),
        "page": page,
        "page_size": page_size,
        "total_groups": total_groups,
        "has_next": has_next,
    })
