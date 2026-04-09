"""站内文章 RAG（向量检索 + 流式输出）
已修复：模型错误、base_url错误、额度超限、400报错
"""

import os
from dotenv import load_dotenv
from datetime import datetime
import pytz

# 加载环境变量
load_dotenv()

# 全局变量：缓存LLM和向量存储实例
_LLM = None
_VS = None


def _format_time(utc_time):
    """
    将UTC时间格式化为北京时间字符串
    
    Args:
        utc_time: UTC时间（字符串或datetime对象）
    
    Returns:
        str: 格式化后的北京时间字符串，格式为"YYYY年MM月DD日 HH:MM"
    """
    if not utc_time:
        return "未知"
    try:
        local_tz = pytz.timezone('Asia/Shanghai')
        if isinstance(utc_time, str):
            utc_time = datetime.fromisoformat(utc_time.replace('Z', '+00:00'))
        if utc_time.tzinfo is None:
            utc_time = pytz.UTC.localize(utc_time)
        local_time = utc_time.astimezone(local_tz)
        return local_time.strftime('%Y年%m月%d日 %H:%M')
    except Exception:
        return str(utc_time)


def _get_llm():
    """
    获取或初始化通义千问LLM实例（单例模式）
    
    Returns:
        tuple: (llm实例, 错误信息) - 如果成功，错误信息为None
    """
    global _LLM
    if _LLM is not None:
        return _LLM, None

    try:
        from langchain_community.chat_models.tongyi import ChatTongyi
    except ModuleNotFoundError:
        return None, "请安装：pip install langchain-community langchain-core"

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return None, "未配置 DASHSCOPE_API_KEY"

    try:
        _LLM = ChatTongyi(
            api_key=api_key,
            model="qwen-plus-2025-07-28",
            temperature=0.1,
            streaming=True,
        )
    except TypeError:
        _LLM = ChatTongyi(
            api_key=api_key,
            model="qwen-plus-2025-07-28",
            temperature=0.1,
        )
    return _LLM, None


def _build_vector_store_from_db():
    """
    从数据库构建向量存储（Chroma）
    
    功能说明：
    - 每篇文章会生成两个文档块：
      1. 作者信息块：专门用于作者查询，包含作者名、文章标题、发布时间
      2. 内容块：完整文章内容，用于内容问答
    - 文档会被分割成1000字符的块，重叠100字符
    - 使用DashScope的text-embedding-v1模型生成向量
    - 向量库每小时自动重建一次
    
    Returns:
        Chroma: 向量存储实例
    """
    global _VS
    import os, time, shutil
    from article.models import Article
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import Chroma
    from langchain_community.embeddings import DashScopeEmbeddings

    # 向量库存储路径
    CHROMA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "chroma_blog")
    os.makedirs(CHROMA_DIR, exist_ok=True)

    # 判断是否需要重建向量库
    rebuild = False
    if _VS is None:
        rebuild = True
    else:
        chroma_db_path = os.path.join(CHROMA_DIR, "chroma.sqlite3")
        if os.path.exists(chroma_db_path):
            mtime = os.path.getmtime(chroma_db_path)
            if time.time() - mtime > 3600 * 24:  # 超过1天自动重建
                rebuild = True
        else:
            rebuild = True

    # 查询所有已发布的文章，包含作者信息
    qs = Article.objects.filter(status="published").select_related("author", "author__profile").values(
        "id", "title", "content", "author__username", "author__profile__nickname", "published_time"
    )

    # 如果需要重建，删除旧的向量库
    if rebuild:
        if os.path.exists(CHROMA_DIR):
            try:
                shutil.rmtree(CHROMA_DIR)
                os.makedirs(CHROMA_DIR, exist_ok=True)
            except:
                pass

    # 构建文档列表，为每篇文章添加作者信息块
    docs = []
    for a in qs:
        author_name = a.get('author__profile__nickname') or a.get('author__username', '未知')
        # 添加作者信息块（用于作者查询）- 这个块专门用于检索作者的所有文章
        docs.append(Document(
            page_content=f"作者：{author_name}\n文章标题：{a['title']}\n发布时间：{_format_time(a.get('published_time'))}",
            metadata={"article_id": a["id"], "title": a["title"], "author": author_name, "type": "author_info"}
        ))
        # 添加完整文章内容块
        docs.append(Document(
            page_content=f"标题：{a['title']}\n作者：{author_name}\n发布时间：{_format_time(a.get('published_time'))}\n内容：{a['content']}",
            metadata={"article_id": a["id"], "title": a["title"], "author": author_name, "type": "content"}
        ))

    # 文档分割：每1000字符一个块，重叠120字符
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=120)
    splits = splitter.split_documents(docs)

    # 使用DashScope的embedding模型
    dashscope_api_key = os.getenv("DASHSCOPE_API_KEY")
    embeddings = DashScopeEmbeddings(
        dashscope_api_key=dashscope_api_key,
        model="text-embedding-v2",
    )

    # 构建Chroma向量库
    vs = Chroma.from_documents(
        documents=splits,
        embedding=embeddings,
        persist_directory=CHROMA_DIR,
        collection_name="blog_articles",
    )
    vs.persist()
    _VS = vs
    return _VS


def simple_rag_qa(article_content: str, question: str) -> str:
    """
    简单的RAG问答（非流式）
    
    Args:
        article_content: 文章内容
        question: 用户问题
    
    Returns:
        str: AI回答
    """
    if not article_content or not question:
        return "请输入有效问题"

    llm, error = _get_llm()
    if error:
        return error

    try:
        from langchain_core.prompts import ChatPromptTemplate
    except ModuleNotFoundError:
        return "请安装：pip install langchain-core"

    try:
        content = (article_content or "")[:6000]
        system_text = """角色定位：你是专业、严谨、只基于原文作答的文章智能问答助手。
        核心规则：
        1. 只依据文章内容回答，无依据则回复「文章中未提及相关内容」
        2. 不编造、不拓展
        3. 简洁专业、条理清晰
        """
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_text),
            ("human", "文章内容：\n{content}\n\n用户问题：{question}"),
        ])
        chain = prompt | llm
        response = chain.invoke({"content": content, "question": question.strip()})
        return (response.content or "").strip()
    except Exception as e:
        return f"AI 服务异常：{str(e)}"


def update_vector_store():
    """
    手动更新向量库
    
    用于手动触发向量库重建，例如：
    - 新增文章后
    - 修改文章内容后
    - 需要强制刷新向量库时
    
    Returns:
        str: 更新结果信息
    """
    global _VS
    from article.models import Article
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import Chroma
    from langchain_community.embeddings import DashScopeEmbeddings
    import os

    CHROMA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "chroma_blog")
    os.makedirs(CHROMA_DIR, exist_ok=True)

    dashscope_api_key = os.getenv("DASHSCOPE_API_KEY")
    embeddings = DashScopeEmbeddings(
        dashscope_api_key=dashscope_api_key,
        model="text-embedding-v1",
    )

    # 查询所有已发布的文章
    qs = Article.objects.filter(status="published").select_related("author", "author__profile").values(
        "id", "title", "content", "author__username", "author__profile__nickname", "published_time"
    )
    
    # 构建文档列表，为每篇文章添加作者信息块
    docs = []
    for a in qs:
        author_name = a.get('author__profile__nickname') or a.get('author__username', '未知')
        # 添加作者信息块（用于作者查询）
        docs.append(Document(
            page_content=f"作者：{author_name}\n文章标题：{a['title']}\n发布时间：{_format_time(a.get('published_time'))}",
            metadata={"article_id": a["id"], "title": a["title"], "author": author_name, "type": "author_info"}
        ))
        # 添加完整文章内容块
        docs.append(Document(
            page_content=f"标题：{a['title']}\n作者：{author_name}\n发布时间：{_format_time(a.get('published_time'))}\n内容：{a['content']}",
            metadata={"article_id": a["id"], "title": a["title"], "author": author_name, "type": "content"}
        ))

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    splits = splitter.split_documents(docs)

    _VS = Chroma.from_documents(
        documents=splits,
        embedding=embeddings,
        persist_directory=CHROMA_DIR,
    )
    _VS.persist()
    return "向量库已更新"


def simple_rag_qa_stream(article_content: str, question: str, request=None):
    """
    流式RAG问答（用于全局AI问答）
    
    功能说明：
    - 基于全站文章内容进行问答
    - 支持流式输出，实时显示AI回答
    - 使用向量检索获取相关文章内容
    - 支持多轮对话（通过session保存历史记录）
    
    Args:
        article_content: 当前文章内容（可选）
        question: 用户问题
        request: HTTP请求对象（用于获取session历史记录）
    
    Yields:
        str: AI回答的文本片段（流式输出）
    """
    try:
        if not article_content or not question:
            yield "请输入有效问题"
            return

        llm, error = _get_llm()
        if error:
            yield error
            return

        from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
        content = (article_content or "")[:6000]
        history = request.session.get('chat_history', []) if request and hasattr(request, 'session') else []

        # 系统提示词：定义AI的角色和行为规则
        system_text = """
            # 角色定位
            你是【知文汇】博客平台的智能问答助手，核心使命是**基于全站文章内容为用户提供准确、全面的回答**。你拥有访问全站所有文章内容的权限，可以跨文章整合信息，但必须严格基于站内已有内容，不使用外部知识。

            # 核心能力
            1. **全站检索能力**：可以检索和引用站内所有文章的内容，不限于单篇文章
            2. **跨文章整合**：当问题涉及多个主题时，能够整合多篇文章的相关内容进行回答
            3. **智能匹配**：根据用户问题，自动匹配最相关的文章内容

            # 核心铁律（违反任何一条即严重违规）
            1. **只答有依据的内容**：所有回答必须能在站内文章内容中找到依据，无依据的问题直接回复「站内文章未提及相关内容」，绝不编造。
            2. **严格忠实原文**：必须准确还原原文的观点、数据、逻辑，不得篡改、曲解。
            3. **多文章整合规则**：
               - 当检索到多篇相关文章时，整合所有相关信息，分点清晰呈现
               - 标注信息来源（文章标题），让用户知道答案来自哪篇文章
               - 若多篇文章内容有冲突，以最新发布的文章为准
            4. **上下文连贯规则**：回答多轮对话时，结合历史对话上下文，同时严格基于检索内容。
            5. **格式与风格要求**：
               - 回答简洁专业、条理清晰
               - 能用分点则分点，保持自然流畅
               - 引用文章时标注「出自《文章标题》」
               - 时间格式统一为「YYYY年MM月DD日」
               - 禁止情绪化、口语化表达
            6.  **特殊问题处理规则（强制执行）**:
                - **查询作者的所有文章（最重要，必须严格遵守）**：
                  - 当用户询问某个作者有哪些文章时，必须列出「相关检索内容」中该作者的**所有文章**，一个都不能遗漏
                  - 格式要求：
                    ```
                    1. 《文章标题1》（发布时间）
                    2. 《文章标题2》（发布时间）
                    3. 《文章标题3》（发布时间）
                    ...（列出所有检索到的文章）
                    ```
                  - **关键规则**：如果「相关检索内容」中包含多篇文章，必须**全部列出**，禁止只返回部分
                  - 绝对禁止只回答数量（如"有5篇"），必须列出所有标题
                - 查询某类技术/话题：列出站内所有相关文章，简要说明每篇的核心内容
                - 比较类问题：分点对比不同文章的观点，标注来源
                - 时间线类问题：按时间顺序整理相关文章，标注发布时间
                - 站内文章未提及相关内容时：直接回复「站内文章未提及相关内容」

            # 回答策略
            ✅ **优先全站检索**：先查看「相关检索内容」中的多篇文章，再参考「当前文章内容」
            ✅ **信息来源标注**：引用文章内容时，标注出自哪篇文章
            ✅ **全面性优先**：对于开放性问题（如"有哪些文章"、"如何学习"），尽可能全面回答
            ✅ **结构化呈现**：使用分点、表格等方式组织多文章信息
            ✅ **完整性要求**：当检索到多篇文章时，必须全部列出，禁止遗漏

            # 禁止行为（绝对不能做）
            ❌ 禁止使用任何外部知识回答问题
            ❌ 禁止编造、杜撰站内文章没有的信息
            ❌ 禁止对原文内容进行主观解读、评论
            ❌ 禁止使用「我」「我们」等第一人称表述
            ❌ 禁止添加无关的解释、说明、客套话
            ❌ 禁止遗漏关键信息（特别是列举类问题）
            ❌ 禁止在回答中出现「根据文章内容」「如上所述」等引导性表述
            """
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_text),
            MessagesPlaceholder(variable_name="history"),
            ("human", "用户问题：{question}"),
            ("human", "文章内容：\n{content}"),
            ("human", "相关检索内容：\n{retrieved_docs}"),
        ])

        chain = prompt | llm
        vs = _build_vector_store_from_db()
        
        # 使用向量检索获取相关文章内容（k=200表示最多检索200个文档块）
        retrieved_docs = vs.similarity_search(question, k=200)
        seen_ids = set()
        unique_docs = []
        for d in retrieved_docs:
            aid = d.metadata.get("article_id")
            if aid not in seen_ids:
                seen_ids.add(aid)
                unique_docs.append(d)
        retrieved_text = "\n\n".join([d.page_content for d in unique_docs])
        full_answer = []

        # 流式输出AI回答
        for chunk in chain.stream({
            "question": question.strip(),
            "content": content,
            "retrieved_docs": retrieved_text,
            "history": history,
        }):
            text = chunk if isinstance(chunk, str) else getattr(chunk, "content", "")
            if text:
                full_answer.append(text)
                yield text

        # 保存对话历史到session（最多保存10轮）
        if request and hasattr(request, 'session'):
            history.append(("human", question.strip()))
            history.append(("assistant", "".join(full_answer)))
            if len(history) > 10:
                history = history[-10:]
            request.session['chat_history'] = history
            request.session.modified = True

    except Exception as e:
        yield f"服务异常：{str(e)}"
