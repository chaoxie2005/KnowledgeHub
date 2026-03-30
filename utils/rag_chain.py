import os
from dotenv import load_dotenv

load_dotenv()

# 模型初始化
_LLM = None


def _get_llm():
    global _LLM
    if _LLM is not None:
        return _LLM, None

    try:
        from langchain_community.chat_models.tongyi import ChatTongyi
    except ModuleNotFoundError:
        return (
            None,
            "未安装 langchain-community/langchain-core，请在虚拟环境中执行：pip install langchain-community langchain-core",
        )

    api_key = os.getenv("QWEN_API_KEY")
    base_url = os.getenv("QWEN_BASE_URL")
    if not api_key or not base_url:
        return None, "未配置 QWEN_API_KEY / QWEN_BASE_URL，AI 问答暂不可用"

    try:
        _LLM = ChatTongyi(
            api_key=api_key,
            base_url=base_url,
            model="qwen3-max",
            temperature=0.1,
            streaming=True,
        )
    except TypeError:
        _LLM = ChatTongyi(
            api_key=api_key,
            base_url=base_url,
            model="qwen3-max",
            temperature=0.1,
        )

    return _LLM, None


def simple_rag_qa(article_content: str, question: str) -> str:
    """
    非链式输出（暂无用处）
    LangChain 实现的 RAG 文章问答
    只根据文章内容回答，不编造 
    """
    if not article_content or not question:
        return "请输入有效问题"

    llm, error = _get_llm()
    if error:
        return error

    try:
        from langchain_core.prompts import ChatPromptTemplate
    except ModuleNotFoundError:
        return "未安装 langchain-core，请在虚拟环境中执行：pip install langchain-core"

    try:
        content = (article_content or "").strip()[:6000]

        system_text = """角色定位：你是专业、严谨、只基于原文作答的文章智能问答助手，严格遵循用户提供的文章内容，不添加任何外部信息、不主观臆断、不编造内容。
        核心规则（必须 100% 遵守）
        1. 只依据给定文章内容回答，无原文依据的问题直接回复「文章中未提及相关内容」，绝不编造
        2. 回答不偏离原文原意，忠实还原作者观点、数据、逻辑
        3. 回答风格：简洁、专业、条理清晰
        - 技术类文章：适配技术博客读者，语言精炼、重点突出
        - 非技术类文章：贴合原文文风，简洁通顺
        4. 结构优先：能用分点则分点，不冗余、不啰嗦
        输出要求
        1. 不添加无关解释、不拓展延伸
        2. 不使用情绪化、口语化表达
        3. 技术问题优先使用术语，保持专业度
        4. 答案严格来源于文章，一字不杜撰"""

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_text),
                ("human", "文章内容：\n{content}\n\n用户问题：{question}"),
            ]
        )

        chain = prompt | llm
        response = chain.invoke({"content": content, "question": question.strip()})
        return (response.content or "").strip()
    except Exception as e:
        return f"AI 服务异常：{str(e)}"



def simple_rag_qa_stream(article_content: str, question: str):
    """
    链式输出内容（正在用）
    LangChain 实现的 RAG 文章问答
    只根据文章内容回答，不编造
    """
    try:
        if not article_content or not question:
            yield "请输入有效问题"
            return

        llm, error = _get_llm()
        if error:
            yield error
            return

        try:
            from langchain_core.prompts import ChatPromptTemplate
        except ModuleNotFoundError:
            yield "未安装 langchain-core，请在虚拟环境中执行：pip install langchain-core"
            return

        content = (article_content or "").strip()[:6000]

        system_text = """角色定位：你是专业、严谨、只基于原文作答的文章智能问答助手，严格遵循用户提供的文章内容，不添加任何外部信息、不主观臆断、不编造内容。
        核心规则（必须 100% 遵守）
        1. 只依据给定文章内容回答，无原文依据的问题直接回复「文章中未提及相关内容」，绝不编造
        2. 回答不偏离原文原意，忠实还原作者观点、数据、逻辑
        3. 回答风格：简洁、专业、条理清晰
        - 技术类文章：适配技术博客读者，语言精炼、重点突出
        - 非技术类文章：贴合原文文风，简洁通顺
        4. 结构优先：能用分点则分点，不冗余、不啰嗦
        输出要求
        1. 不添加无关解释、不拓展延伸
        2. 不使用情绪化、口语化表达
        3. 技术问题优先使用术语，保持专业度
        4. 答案严格来源于文章，一字不杜撰"""

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_text),
                ("human", "文章内容：\n{content}\n\n用户问题：{question}"),
            ]
        )

        chain = prompt | llm

        try:
            for chunk in chain.stream({"content": content, "question": question.strip()}):
                if isinstance(chunk, str):
                    text = chunk
                else:
                    text = getattr(chunk, "content", "")
                if text:
                    yield text
        except Exception as e:
            yield f"\n\nAI 服务异常：{str(e)}"
    except Exception as e:
        yield f"AI 服务异常：{str(e)}"
