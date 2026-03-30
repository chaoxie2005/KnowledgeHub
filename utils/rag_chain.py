"""站内文章 RAG（向量检索 + 流式输出）

核心流程（对齐你的 rag_text.py 思路）：
- 聊天模型初始化（ChatTongyi）
- 嵌入模型初始化（DashScopeEmbeddings）
- 模板初始化（ChatPromptTemplate）
- 向量库初始化/持久化（Chroma persist_directory）
- 数据库读取已发布文章（Django ORM）→ Document
- 文本分割（RecursiveCharacterTextSplitter）→ chunks
- 写入向量库（add_documents + persist）
- 向量库检索（similarity_search TopK）
- 检索内容 + 用户提问 → 交给聊天模型流式生成

注意：API Key 不允许硬编码在代码里；请使用环境变量配置。
"""

import os
from dotenv import load_dotenv
from datetime import datetime
import pytz

load_dotenv()  # 读取 .env 环境变量（如 QWEN_API_KEY / DASHSCOPE_API_KEY 等）

# 模型初始化
_LLM = None
# 向量库实例（持久化复用）
_VS = None

# 辅助函数：将 UTC 时间转换为本地时间
def _format_time(utc_time):
    """将 UTC 时间转换为本地时间并格式化"""
    if not utc_time:
        return "未知"
    try:
        # 转换为本地时间
        local_tz = pytz.timezone('Asia/Shanghai')
        if isinstance(utc_time, str):
            # 如果是字符串，先解析
            utc_time = datetime.fromisoformat(utc_time.replace('Z', '+00:00'))
        # 确保是带时区的 datetime 对象
        if utc_time.tzinfo is None:
            utc_time = pytz.UTC.localize(utc_time)
        # 转换为本地时间
        local_time = utc_time.astimezone(local_tz)
        # 格式化输出
        return local_time.strftime('%Y年%m月%d日 %H:%M')
    except Exception:
        # 出错时返回原始时间
        return str(utc_time)


def _get_llm():
    """
    获取聊天模型实例
    
    尝试使用 Qwen3-Max 模型，失败则降级到不使用 streaming 参数的版本
    会缓存模型实例，避免重复初始化
    
    Returns:
        tuple: (LLM 实例, 错误信息)，如果成功，错误信息为 None
    """
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

    # 从环境变量读取 API Key 和基础 URL
    api_key = os.getenv("QWEN_API_KEY")
    base_url = os.getenv("QWEN_BASE_URL")
    if not api_key or not base_url:
        return None, "未配置 QWEN_API_KEY / QWEN_BASE_URL，AI 问答暂不可用"

    # 尝试初始化聊天模型，支持流式输出
    try:
        _LLM = ChatTongyi(
            api_key=api_key,
            base_url=base_url,
            model="qwen3-max",
            temperature=0.1,  # 低温度，减少随机性
            streaming=True,  # 启用流式输出
        )
    except TypeError:
        # 降级到不使用 streaming 参数的版本
        _LLM = ChatTongyi(
            api_key=api_key,
            base_url=base_url,
            model="qwen3-max",
            temperature=0.1,
        )

    return _LLM, None

# 从数据库构建向量库：已发布文章 → Document → 分割 → Chroma（持久化复用）
def _build_vector_store_from_db():
    """
    从数据库构建向量库
    
    首次访问时自动调用，会从数据库加载所有已发布的文章并构建向量库
    后续访问会复用缓存的向量库，每小时重新构建一次以确保数据同步
    
    Returns:
        Chroma: 向量库实例
    """
    global _VS

    # 导入必要的模块
    import os
    import time
    import shutil

    # 数据来源：读取“已发布文章”
    from article.models import Article

    # LangChain 文档结构：page_content 存文本，metadata 存可追溯信息
    from langchain_core.documents import Document

    # 文本分割：避免单篇文章过长导致 embedding/检索效果差
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    # 向量库与嵌入模型：Chroma + DashScopeEmbeddings
    from langchain_community.vectorstores import Chroma
    from langchain_community.embeddings import DashScopeEmbeddings

    # 向量库持久化目录（会在此目录生成 chroma 数据文件）
    CHROMA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "chroma_blog")
    
    # 确保目录存在
    os.makedirs(CHROMA_DIR, exist_ok=True)
    
    # 检查向量库是否存在，以及是否需要重新构建
    # 如果向量库不存在，或者上次构建时间超过 1 小时，则重新构建
    rebuild = False
    if _VS is None:
        rebuild = True
    else:
        # 检查向量库文件的修改时间
        chroma_db_path = os.path.join(CHROMA_DIR, "chroma.sqlite3")
        if os.path.exists(chroma_db_path):
            mtime = os.path.getmtime(chroma_db_path) # 获取文件的最后修改时间（时间戳格式）
            current_time = time.time()
            # 如果上次修改时间超过 1 小时，则重新构建
            if current_time - mtime > 3600:
                rebuild = True
        else:
            rebuild = True

    # ORM 查询：只取需要的字段，避免把整行模型对象加载进内存
    qs = Article.objects.filter(status="published").select_related("author", "author__profile").values("id", "title", "content", "author__username", "author__profile__nickname", "published_time")
    
    # 打印已发布文章数量，用于调试
    print(f"已发布文章数量：{qs.count()}")

    # 如果需要重新构建向量库，先删除旧的向量库文件
    if rebuild:
        print("删除旧的向量库文件")
        if os.path.exists(CHROMA_DIR):
            try:
                shutil.rmtree(CHROMA_DIR) # 递归删除整个目录及其所有内容（包括子目录和文件）
                os.makedirs(CHROMA_DIR, exist_ok=True)
            except Exception as e:
                print(f"删除旧向量库文件失败：{str(e)}")

    # 转成 Document：把标题、作者（用户名+昵称）、发布时间与内容拼成一个可检索的文本块
    docs = [
        Document(
            page_content=f"标题：{a['title']}\n作者：{a.get('author__profile__nickname', a.get('author__username', '未知'))}\n发布时间：{_format_time(a.get('published_time'))}\n内容：{a['content']}",
            metadata={"article_id": a["id"], "title": a["title"], "author": a.get('author__profile__nickname', a.get('author__username', '未知')), "username": a.get('author__username', '未知'), "published_time": str(a.get('published_time')) if a.get('published_time') else None},
        )
        for a in qs
    ]

    # 分割参数：chunk_size 和 chunk_overlap 需要根据文章平均长度调整，过大可能导致 embedding 失败，过小可能导致语义丢失
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    splits = splitter.split_documents(docs)

    # 嵌入模型初始化
    dashscope_api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
    embeddings = DashScopeEmbeddings(
        dashscope_api_key=dashscope_api_key,
        model="text-embedding-v3",
    )

    # 向量库初始化：使用 from_documents 方法创建新的向量库
    vs = Chroma.from_documents(
        documents=splits,
        embedding=embeddings,
        persist_directory=CHROMA_DIR,
        collection_name="blog_articles",
    )

    # 持久化向量库
    vs.persist()

    # 更新全局缓存
    _VS = vs
    return _VS


def simple_rag_qa(article_content: str, question: str) -> str:
    """
    非流式输出 RAG 文章问答
    
    根据文章内容回答用户问题，不编造内容
    适用于不需要实时显示回答过程的场景
    
    Args:
        article_content: 文章内容
        question: 用户问题
    
    Returns:
        str: AI 回答
    """
    # 基础参数校验
    if not article_content or not question:
        return "请输入有效问题"

    # 获取聊天模型
    llm, error = _get_llm()
    if error:
        return error

    # 导入必要的模块
    try:
        from langchain_core.prompts import ChatPromptTemplate
    except ModuleNotFoundError:
        return "未安装 langchain-core，请在虚拟环境中执行：pip install langchain-core"

    try:
        # 处理文章内容，限制长度
        content = (article_content or "").strip()[:6000]

        # 系统提示词，定义助手角色和规则
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

        # 构建提示模板
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_text),
                ("human", "文章内容：\n{content}\n\n用户问题：{question}"),
            ]
        )

        # 构建链并调用
        chain = prompt | llm
        response = chain.invoke({"content": content, "question": question.strip()})
        return (response.content or "").strip()
    except Exception as e:
        return f"AI 服务异常：{str(e)}"




def update_vector_store():
    """
    增量更新向量库
    
    在文章保存时通过钩子自动调用，确保向量库与数据库同步
    会重新构建整个向量库，确保包含所有已发布的文章
    
    Returns:
        str: 更新结果消息
    """
    global _VS
    
    # 导入必要的模块
    from article.models import Article
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import Chroma
    from langchain_community.embeddings import DashScopeEmbeddings
    import os
    
    # 向量库持久化目录
    CHROMA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "chroma_blog")
    
    # 确保目录存在
    os.makedirs(CHROMA_DIR, exist_ok=True)
    
    # 初始化嵌入模型
    dashscope_api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
    embeddings = DashScopeEmbeddings(
        dashscope_api_key=dashscope_api_key,
        model="text-embedding-v3",
    )
    
    # 获取所有已发布的文章
    qs = Article.objects.filter(status="published").select_related("author", "author__profile").values("id", "title", "content", "author__username", "author__profile__nickname", "published_time")
    
    # 打印已发布文章数量，用于调试
    print(f"已发布文章数量：{qs.count()}")
    
    # 转换为 Document 对象
    docs = [
        Document(
            page_content=f"标题：{a['title']}\n作者：{a.get('author__profile__nickname', a.get('author__username', '未知'))}\n发布时间：{_format_time(a.get('published_time'))}\n内容：{a['content']}",
            metadata={"article_id": a["id"], "title": a["title"], "author": a.get('author__profile__nickname', a.get('author__username', '未知')), "username": a.get('author__username', '未知'), "published_time": str(a.get('published_time')) if a.get('published_time') else None},
        )
        for a in qs
    ]
    
    # 文本分割
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    splits = splitter.split_documents(docs)
    
    # 创建新的向量库
    _VS = Chroma.from_documents(
        documents=splits,
        embedding=embeddings,
        persist_directory=CHROMA_DIR,
        collection_name="blog_articles",
    )
    
    # 持久化向量库
    _VS.persist()
    
    return "向量库已成功更新"


def simple_rag_qa_stream(article_content: str, question: str, request=None):
    """
    流式输出 RAG 文章问答
    
    面向前端逐字/逐段输出，自动记录历史会话
    支持多轮对话上下文理解，确保回答的连贯性
    
    Args:
        article_content: 文章内容
        question: 用户问题
        request: Django 请求对象，用于存储历史会话
    
    Yields:
        str: AI 回答的片段，逐字/逐段输出
    """
    
    """
    流程：
    1) 初始化 LLM（ChatTongyi，streaming=True）
    2) 初始化 Prompt（system + 历史会话 + 用户问题 + 检索片段）
    3) 构建/加载向量库（Chroma 持久化）
    4) TopK 检索：similarity_search(question, k=20)
    5) 将检索到的内容拼接后喂给模型，使用 chain.stream() 流式返回
    6) 自动记录历史会话到 session
    """


    try:
        # 基础参数校验：无内容/无问题直接返回
        if not article_content or not question:
            yield "请输入有效问题"
            return

        # 聊天模型初始化（复用全局单例）
        llm, error = _get_llm()
        if error:
            yield error
            return

        # Prompt 模板初始化：这里用 LangChain 的 ChatPromptTemplate
        try:
            from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
        except ModuleNotFoundError:
            yield "未安装 langchain-core，请在虚拟环境中执行：pip install langchain-core"
            return

        # 文章原文（当前没直接喂给模型，仅用于你后续扩展：引用溯源/对齐检查等）
        content = (article_content or "").strip()[:6000]

        # 从 session 中获取历史会话
        history = []
        if request and hasattr(request, 'session'):
            history = request.session.get('chat_history', [])

        # system 约束：控制模型必须基于检索内容回答，找不到就说明未提及
        system_text = """角色定位：你是专业、严谨、只基于原文作答的文章智能问答助手，严格遵循用户提供的文章内容，不添加任何外部信息、不主观臆断、不编造内容。
        核心规则（必须 100% 遵守）
        1. 只依据给定文章内容回答，无原文依据的问题直接回复「文章中未提及相关内容」，绝不编造
        2. 回答不偏离原文原意，忠实还原作者观点、数据、逻辑
        3. 回答风格：简洁、专业、条理清晰
        - 技术类文章：适配技术博客读者，语言精炼、重点突出
        - 非技术类文章：贴合原文文风，简洁通顺
        4. 结构优先：能用分点则分点，不冗余、不啰嗦
        5. 格式要求：回答要自然流畅，避免生硬的列表格式，时间格式要友好易读
        6. 上下文理解：要考虑历史对话内容，保持回答的连贯性
        7. 完整性要求：当查询作者的所有文章时，必须列出检索到的所有相关文章，不要遗漏
        输出要求
        1. 不添加无关解释、不拓展延伸
        2. 不使用情绪化、口语化表达
        3. 技术问题优先使用术语，保持专业度
        4. 答案严格来源于文章，一字不杜撰"""

        # 5) Prompt 结构：使用 MessagesPlaceholder 处理历史会话，包含当前文章内容
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_text),
                MessagesPlaceholder(variable_name="history"),
                ("human", "用户问题：{question}"),
                ("human", "以下是当前文章内容：\n{content}"),
                ("human", "以下是站内检索到的相关内容：\n{retrieved_docs}"),
            ]
        )

        # 6) 组装链：prompt | llm 形成 LCEL chain
        chain = prompt | llm

        try:
            # 向量库构建/加载：首次会从 DB 构建并持久化，后续复用
            vs = _build_vector_store_from_db()

            # 向量检索 TopK：返回一组 Document（按相似度排序）
            retrieved_docs = vs.similarity_search(question, k=20)

            # 优化去重逻辑，确保同一作者的多篇文章都能被检索到
            seen_article_ids = set()
            unique_docs = []
            for doc in retrieved_docs:
                article_id = doc.metadata.get("article_id")
                if article_id not in seen_article_ids:
                    seen_article_ids.add(article_id)
                    unique_docs.append(doc)
            retrieved_docs = unique_docs

            # 将检索片段拼接成模型可消费的上下文
            retrieved_text = "\n\n".join([d.page_content for d in retrieved_docs])

            # 收集模型的回答
            full_answer = []
            # 流式调用：模型边生成边 yield，前端可实时展示
            for chunk in chain.stream(
                {
                    "question": question.strip(),
                    "content": content,  # 传递当前文章内容
                    "retrieved_docs": retrieved_text,
                    "history": history,  # 传递历史会话
                }
            ):
                # 兼容不同 LangChain 版本/实现的 chunk 结构
                text = chunk if isinstance(chunk, str) else getattr(chunk, "content", "")
                if text:
                    full_answer.append(text)
                    yield text

            # 自动记录历史会话到 session
            if request and hasattr(request, 'session'):
                # 将新的对话对添加到历史会话
                history.append(("human", question.strip()))
                history.append(("assistant", "".join(full_answer)))
                # 限制历史会话长度，避免 session 过大
                if len(history) > 10:  # 只保留最近的 5 轮对话
                    history = history[-10:]
                # 保存到 session
                request.session['chat_history'] = history
                request.session.modified = True

        except Exception as e:
            # 兜底：任何检索/模型错误都输出明确错误，避免前端看到整段 500 HTML
            yield f"\n\nAI 服务异常：{str(e)}"
    except Exception as e:
        yield f"AI 服务异常：{str(e)}"