# AI 功能端点：标题优化、摘要生成、文章/全局 RAG 问答、历史清空、TTS 音频生成
import hashlib
import logging
import json
import os

from django.core.files.base import ContentFile
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404

from ..models import Article
from ..ai_utils import optimize_article_title, generate_article_summary
from ..tts_utils import generate_article_audio
from utils.rag_chain import (
    simple_rag_qa,
    article_rag_qa_stream,
    global_rag_qa_stream,
    article_rag_qa_stream_react,
    global_rag_qa_stream_react,
    _get_llm as rag_get_llm,
)

logger = logging.getLogger(__name__)


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
    except Exception:
        logger.exception("AI 标题优化失败")
        return JsonResponse({"success": False, "error": "标题优化失败，请稍后重试"})


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
    except Exception:
        logger.exception("AI 摘要生成失败")
        return JsonResponse({"success": False, "error": "摘要生成失败，请稍后重试"})


@login_required(login_url='authentication:login')
@require_POST
def article_ai_qa(request, article_id):
    """LangChain RAG 文章问答接口"""
    try:
        article = Article.objects.get(id=article_id, status="published")

        question = request.POST.get("question", "").strip()
        if not question:
            return JsonResponse({"code": 400, "msg": "请输入问题"})

        # 在处理请求前检查API Key配置
        llm, error = rag_get_llm()
        if error:
            return JsonResponse({"code": 500, "msg": error})

        # 检查是否使用ReAct模式
        use_react = request.GET.get("react") == "1"

        if request.GET.get("stream") == "1":
            # 选择使用传统模式或ReAct模式
            if use_react:
                response = StreamingHttpResponse(
                    article_rag_qa_stream_react(article.content, question, request),
                    content_type="text/plain; charset=utf-8",
                )
            else:
                response = StreamingHttpResponse(
                    article_rag_qa_stream(article.content, question, request),
                    content_type="text/plain; charset=utf-8",
                )
            response["Cache-Control"] = "no-cache"
            response["X-Accel-Buffering"] = "no"
            return response

        # 非流式请求
        answer = simple_rag_qa(article.content, question)
        return JsonResponse({
            "code": 200,
            "answer": answer
        })

    except Article.DoesNotExist:
        return JsonResponse({"code": 404, "msg": "文章不存在"})
    except Exception:
        logger.exception("文章 AI 问答失败: article_id=%s", article_id)
        return JsonResponse({"code": 500, "msg": "服务异常，请稍后重试"})


def global_ai_qa(request):
    """LangChain RAG 全局问答接口（基于所有文章内容）"""
    try:
        question = request.POST.get("question", "").strip()
        if not question:
            return JsonResponse({"code": 400, "msg": "请输入问题"})

        # 在处理请求前检查API Key配置
        llm, error = rag_get_llm()
        if error:
            return JsonResponse({"code": 500, "msg": error})

        history_raw = request.POST.get("history", "").strip()
        parsed_history = None
        if history_raw:
            try:
                history_data = json.loads(history_raw)
                if isinstance(history_data, list):
                    normalized = []
                    for item in history_data[-10:]:
                        if not isinstance(item, dict):
                            continue
                        q = (item.get("question") or "").strip()
                        a = (item.get("answer") or "").strip()
                        if q:
                            normalized.append(("human", q))
                        if a:
                            normalized.append(("assistant", a))
                    parsed_history = normalized
            except (json.JSONDecodeError, TypeError, KeyError):
                parsed_history = None

        # 检查是否使用ReAct模式
        use_react = request.GET.get("react") == "1"

        if request.GET.get("stream") == "1":
            # 选择使用传统模式或ReAct模式
            if use_react:
                response = StreamingHttpResponse(
                    global_rag_qa_stream_react(question, request),
                    content_type="text/plain; charset=utf-8",
                )
            else:
                response = StreamingHttpResponse(
                    global_rag_qa_stream(question, request, history_override=parsed_history),
                    content_type="text/plain; charset=utf-8",
                )
            response["Cache-Control"] = "no-cache"
            response["X-Accel-Buffering"] = "no"
            return response

        # 对于非流式请求，加载最新文章内容（simple_rag_qa 仅使用前 6000 字符，无需加载全部）
        articles = Article.objects.filter(status="published").order_by("-published_time").values_list('content', flat=True)[:30]
        all_content = "\n\n".join(articles)
        answer = simple_rag_qa(all_content, question)
        return JsonResponse({
            "code": 200,
            "answer": answer
        })

    except Exception:
        logger.exception("全局 AI 问答失败")
        return JsonResponse({"code": 500, "msg": "服务异常，请稍后重试"})


@require_POST
def clear_ai_history(request):
    """清空服务端会话历史，确保新对话生效"""
    user_id = str(request.user.id) if hasattr(request, "user") and hasattr(request.user, "id") else "anonymous"
    history_key = f"chat_history_{user_id}"
    if hasattr(request, "session"):
        request.session[history_key] = []
        request.session.modified = True
    return JsonResponse({"code": 200, "msg": "会话历史已清空"})


@login_required(login_url='authentication:login')
@require_POST
def generate_article_audio_view(request, article_id):
    """生成或重新生成文章 TTS 音频"""
    try:
        article = get_object_or_404(
            Article.objects.only(
                "id", "content", "audio_file", "audio_generated",
                "audio_content_hash", "status",
            ),
            pk=article_id,
            status="published",
        )

        api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
        if not api_key:
            return JsonResponse({
                "success": False,
                "error": "请配置 DASHSCOPE_API_KEY 环境变量",
            })

        content_hash = hashlib.sha256(article.content.encode()).hexdigest()
        if (
            article.audio_generated
            and article.audio_file
            and article.audio_content_hash == content_hash
            and os.path.exists(article.audio_file.path)
        ):
            return JsonResponse({
                "success": True,
                "audio_url": article.audio_file.url,
                "message": "音频已存在且内容未变更",
                "cached": True,
            })

        audio_bytes = generate_article_audio(article.content)
        if not audio_bytes:
            return JsonResponse({
                "success": False,
                "error": "音频生成失败，请稍后重试",
            })

        filename = f"article_{article.id}.mp3"
        article.audio_file.save(filename, ContentFile(audio_bytes), save=False)
        article.audio_generated = True
        article.audio_content_hash = content_hash
        article.save(update_fields=["audio_file", "audio_generated", "audio_content_hash"])

        return JsonResponse({
            "success": True,
            "audio_url": article.audio_file.url,
            "message": "音频生成成功",
            "cached": False,
        })

    except Article.DoesNotExist:
        return JsonResponse({"success": False, "error": "文章不存在或未发布"})
    except Exception:
        logger.exception("TTS generation failed for article %s", article_id)
        return JsonResponse({
            "success": False,
            "error": "音频生成失败，请稍后重试",
        })
