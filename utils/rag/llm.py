# 共享 LLM 单例工厂：按 (model, temperature) 缓存 ChatTongyi 实例
import os
from dotenv import load_dotenv

load_dotenv()

_LLM_CACHE = {}


def _get_llm(model="qwen-turbo", temperature=0.1):
    """
    获取或初始化通义千问LLM实例（按 model+temperature 缓存）

    Args:
        model: 模型名称，默认 qwen-turbo
        temperature: 温度参数，默认 0.1

    Returns:
        tuple: (llm实例, 错误信息) - 如果成功，错误信息为None
    """
    cache_key = (model, temperature)
    if cache_key in _LLM_CACHE:
        return _LLM_CACHE[cache_key], None

    try:
        from langchain_community.chat_models.tongyi import ChatTongyi
    except ModuleNotFoundError:
        return None, "请安装：pip install langchain-community langchain-core"

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return None, "未配置 DASHSCOPE_API_KEY"

    try:
        llm = ChatTongyi(
            api_key=api_key,
            model=model,
            temperature=temperature,
            streaming=True,
        )
    except TypeError:
        llm = ChatTongyi(
            api_key=api_key,
            model=model,
            temperature=temperature,
        )

    # 快速验证 API Key 是否可用，避免后续调用时出现误导性的 KeyError('request')
    try:
        from dashscope import Generation
        resp = Generation.call(
            model=model,
            api_key=api_key,
            messages=[{"role": "user", "content": "ping"}],
            result_format="message",
            max_tokens=1,
        )
        if resp.status_code != 200:
            code = getattr(resp, "code", "Unknown")
            message = getattr(resp, "message", "未知错误")
            return None, f"AI 服务异常：{message}（错误码：{code}）"
    except Exception:
        pass  # 验证失败不影响使用，后续调用时会暴露具体错误

    _LLM_CACHE[cache_key] = llm
    return llm, None
