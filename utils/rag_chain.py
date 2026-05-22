"""站内文章 RAG（向量检索 + 流式输出）
基于ReAct模式的RAG对话系统重构
"""

import os
from dotenv import load_dotenv
from datetime import datetime
import pytz
from typing import TypedDict, List, Optional
from langchain_core.documents import Document

# 加载环境变量
load_dotenv()

# 全局变量：缓存LLM和向量存储实例
_LLM = None
_VS = None


class RAGState(TypedDict):
    """RAG系统状态定义"""
    question: str
    thoughts: List[str]
    actions: List[str]
    observations: List[str]
    retrieved_docs: List[Document]
    context: str
    answer: str
    step_count: int
    max_steps: int
    should_continue: bool


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
            model="qwen-turbo",
            temperature=0.1,
            streaming=True,
        )
    except TypeError:
        _LLM = ChatTongyi(
            api_key=api_key,
            model="qwen-turbo",
            temperature=0.1,
        )

    # 快速验证 API Key 是否可用，避免后续调用时出现误导性的 KeyError('request')
    try:
        from dashscope import Generation
        resp = Generation.call(
            model="qwen-turbo",
            api_key=api_key,
            messages=[{"role": "user", "content": "ping"}],
            result_format="message",
            max_tokens=1,
        )
        if resp.status_code != 200:
            code = getattr(resp, "code", "Unknown")
            message = getattr(resp, "message", "未知错误")
            _LLM = None
            return None, f"AI 服务异常：{message}（错误码：{code}）"
    except Exception:
        pass  # 验证失败不影响使用，后续调用时会暴露具体错误

    return _LLM, None


from langchain_core.tools import tool


@tool
def vector_search_tool(question: str, k: int = 10) -> str:
    """
    向量搜索工具：根据问题检索相关文章
    
    Args:
        question: 用户问题
        k: 检索结果数量
    
    Returns:
        str: 检索到的文章内容
    """
    vs = _build_vector_store_from_db()
    docs = vs.similarity_search(question, k=k)
    return "\n\n".join([d.page_content for d in docs])


@tool
def author_search_tool(author_name: str) -> str:
    """
    作者搜索工具：查询指定作者的所有文章
    
    Args:
        author_name: 作者名称
    
    Returns:
        str: 作者的文章列表
    """
    from article.models import Article
    articles = Article.objects.filter(status="published").select_related("author", "author__profile")
    author_articles = []
    for a in articles:
        article_author = a.author.profile.nickname if hasattr(a.author, 'profile') and hasattr(a.author.profile, 'nickname') and a.author.profile.nickname else a.author.username
        if author_name in article_author or article_author in author_name:
            author_articles.append(a)
    
    author_articles.sort(key=lambda x: x.published_time, reverse=True)
    
    result = []
    for a in author_articles:
        article_author = a.author.profile.nickname if hasattr(a.author, 'profile') and hasattr(a.author.profile, 'nickname') and a.author.profile.nickname else a.author.username
        content = f"作者：{article_author}\n文章标题：{a.title}\n发布时间：{_format_time(a.published_time)}"
        result.append(content)
    
    if not result:
        return f"未找到作者 {author_name} 的文章"
    return "\n\n".join(result)


@tool
def date_search_tool(date_str: str) -> str:
    """
    日期搜索工具：查询指定日期的文章
    
    Args:
        date_str: 日期字符串，格式为YYYY-MM-DD
    
    Returns:
        str: 该日期发布的文章列表
    """
    from article.models import Article
    from datetime import datetime
    
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        articles = Article.objects.filter(
            status="published",
            published_time__date=target_date
        ).select_related("author", "author__profile")
        
        result = []
        for a in articles:
            author_name = a.author.profile.nickname if hasattr(a.author, 'profile') and hasattr(a.author.profile, 'nickname') and a.author.profile.nickname else a.author.username
            content = f"标题：{a.title}\n作者：{author_name}\n发布时间：{_format_time(a.published_time)}"
            result.append(content)
        
        if not result:
            return f"未找到 {date_str} 发布的文章"
        return "\n\n".join(result)
    except Exception as e:
        return f"日期格式错误，请使用YYYY-MM-DD格式"


@tool
def year_search_tool(year: str) -> str:
    """
    年份搜索工具：查询指定年份的文章
    
    Args:
        year: 年份字符串，格式为YYYY
    
    Returns:
        str: 该年份发布的文章列表
    """
    from article.models import Article
    from datetime import datetime
    
    try:
        year_int = int(year)
        # 查询该年份的所有文章
        articles = Article.objects.filter(
            status="published",
            published_time__year=year_int
        ).select_related("author", "author__profile")
        
        # 按发布时间从新到旧排序
        articles = articles.order_by('-published_time')
        
        result = []
        for a in articles:
            author_name = a.author.profile.nickname if hasattr(a.author, 'profile') and hasattr(a.author.profile, 'nickname') and a.author.profile.nickname else a.author.username
            content = f"标题：{a.title}\n作者：{author_name}\n发布时间：{_format_time(a.published_time)}"
            result.append(content)
        
        if not result:
            return f"未找到 {year} 年发布的文章"
        return "\n\n".join(result)
    except Exception as e:
        return f"年份格式错误，请使用YYYY格式"


@tool
def category_search_tool(category_name: str) -> str:
    """
    分类搜索工具：查询指定分类的文章
    
    Args:
        category_name: 分类名称
    
    Returns:
        str: 该分类下的文章列表
    """
    from article.models import Article
    articles = Article.objects.filter(
        status="published",
        category__name=category_name
    ).select_related("author", "author__profile")
    
    result = []
    for a in articles:
        author_name = a.author.profile.nickname if hasattr(a.author, 'profile') and hasattr(a.author.profile, 'nickname') and a.author.profile.nickname else a.author.username
        content = f"标题：{a.title}\n作者：{author_name}\n发布时间：{_format_time(a.published_time)}"
        result.append(content)
    
    if not result:
        return f"未找到分类 {category_name} 的文章"
    return "\n\n".join(result)


@tool
def tag_search_tool(tag_name: str) -> str:
    """
    标签搜索工具：查询指定标签的文章
    
    Args:
        tag_name: 标签名称
    
    Returns:
        str: 该标签下的文章列表
    """
    from article.models import Article
    articles = Article.objects.filter(
        status="published"
    ).select_related("author", "author__profile").prefetch_related("tags")
    
    result = []
    for a in articles:
        if any(tag.name == tag_name for tag in a.tags.all()):
            author_name = a.author.profile.nickname if hasattr(a.author, 'profile') and hasattr(a.author.profile, 'nickname') and a.author.profile.nickname else a.author.username
            content = f"标题：{a.title}\n作者：{author_name}\n发布时间：{_format_time(a.published_time)}"
            result.append(content)
    
    if not result:
        return f"未找到标签 {tag_name} 的文章"
    return "\n\n".join(result)


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
    from article.models import Article, JuejinHotArticle, CSDNArticle
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import Chroma
    from langchain_community.embeddings import DashScopeEmbeddings

    # 向量库存储路径
    CHROMA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "chroma_blog")
    os.makedirs(CHROMA_DIR, exist_ok=True)

    # 始终重建向量库，避免旧文件导致的问题
    rebuild = True

    # 查询所有已发布的文章，包含作者、分类和标签信息
    qs = Article.objects.filter(status="published").select_related("author", "author__profile", "category").prefetch_related("tags").values(
        "id", "title", "content", "summary", "cover", "author__username", "author__profile__nickname", 
        "category__name", "status", "read_count", "is_top", "published_time", "created_time", "updated_time"
    )
    
    # 为每个文章添加标签信息
    articles_with_tags = []
    for a in qs:
        article = Article.objects.get(id=a['id'])
        a['tags'] = [tag.name for tag in article.tags.all()]
        articles_with_tags.append(a)
    qs = articles_with_tags

    # 构建文档列表，为每篇文章添加作者信息块
    docs = []
    
    # 添加本地文章
    for a in qs:
        author_name = a.get('author__profile__nickname') or a.get('author__username', '未知')
        category_name = a.get('category__name', '未分类')
        tags = a.get('tags', [])
        tag_names = ', '.join(tags) if tags else '无标签'
        
        # 构建完整的文章信息
        article_info = f"标题：{a['title']}\n"
        article_info += f"作者：{author_name}\n"
        article_info += f"分类：{category_name}\n"
        article_info += f"标签：{tag_names}\n"
        article_info += f"状态：{a.get('status', '未知')}\n"
        article_info += f"阅读量：{a.get('read_count', 0)}\n"
        article_info += f"发布时间：{_format_time(a.get('published_time'))}\n"
        article_info += f"创建时间：{_format_time(a.get('created_time'))}\n"
        article_info += f"更新时间：{_format_time(a.get('updated_time'))}\n"
        article_info += f"摘要：{a.get('summary', '无摘要')}\n"
        article_info += f"内容：{a.get('content', '无内容')}\n"
        
        # 添加作者信息块（用于作者查询）- 这个块专门用于检索作者的所有文章
        # 为了提高检索精度，添加多个作者信息块，使用不同的表述方式
        docs.append(Document(
            page_content=f"作者：{author_name}\n文章标题：{a['title']}\n发布时间：{_format_time(a.get('published_time'))}",
            metadata={"article_id": a["id"], "title": a["title"], "author": author_name, "published_time": _format_time(a.get('published_time')), "type": "author_info", "source": "本地文章"}
        ))
        # 添加另一个作者信息块，使用不同的表述方式，提高检索概率
        docs.append(Document(
            page_content=f"{author_name}发布的文章：{a['title']}\n发布时间：{_format_time(a.get('published_time'))}",
            metadata={"article_id": a["id"], "title": a["title"], "author": author_name, "published_time": _format_time(a.get('published_time')), "type": "author_info_alt", "source": "本地文章"}
        ))
        # 添加完整文章内容块
        docs.append(Document(
            page_content=article_info,
            metadata={"article_id": a["id"], "title": a["title"], "author": author_name, "published_time": _format_time(a.get('published_time')), "type": "content", "source": "本地文章"}
        ))
    
    # 添加掘金热榜文章
    juejin_articles = JuejinHotArticle.objects.all().select_related().prefetch_related("tags")
    for article in juejin_articles:
        author_name = article.author or '未知'
        tags = [tag.name for tag in article.tags.all()]
        tag_names = ', '.join(tags) if tags else '无标签'
        
        # 构建掘金文章信息
        article_info = f"标题：{article.title}\n"
        article_info += f"作者：{author_name}\n"
        article_info += f"标签：{tag_names}\n"
        article_info += f"来源：{article.source or '掘金'}\n"
        article_info += f"发布时间：{_format_time(article.published_time)}\n"
        article_info += f"爬取时间：{_format_time(article.crawl_time)}\n"
        article_info += f"摘要：{article.summary or article.ai_summary or '无摘要'}\n"
        article_info += f"原文链接：{article.original_url}\n"
        
        # 添加掘金文章到向量库
        docs.append(Document(
            page_content=f"作者：{author_name}\n文章标题：{article.title}\n发布时间：{_format_time(article.published_time)}\n来源：掘金",
            metadata={"article_id": article.juejin_article_id, "title": article.title, "author": author_name, "published_time": _format_time(article.published_time), "type": "author_info", "source": "掘金"}
        ))
        docs.append(Document(
            page_content=article_info,
            metadata={"article_id": article.juejin_article_id, "title": article.title, "author": author_name, "published_time": _format_time(article.published_time), "type": "content", "source": "掘金"}
        ))
    
    # 添加CSDN文章
    csdn_articles = CSDNArticle.objects.all()
    for article in csdn_articles:
        author_name = article.author or '未知'
        
        # 构建CSDN文章信息
        article_info = f"标题：{article.title}\n"
        article_info += f"作者：{author_name}\n"
        article_info += f"来源：{article.source or 'CSDN'}\n"
        article_info += f"爬取时间：{_format_time(article.crawl_time)}\n"
        article_info += f"摘要：{article.summary or '无摘要'}\n"
        article_info += f"原文链接：{article.original_url}\n"
        
        # 添加CSDN文章到向量库
        docs.append(Document(
            page_content=f"作者：{author_name}\n文章标题：{article.title}\n来源：CSDN",
            metadata={"article_id": article.csdn_article_id, "title": article.title, "author": author_name, "published_time": _format_time(article.crawl_time), "type": "author_info", "source": "CSDN"}
        ))
        docs.append(Document(
            page_content=article_info,
            metadata={"article_id": article.csdn_article_id, "title": article.title, "author": author_name, "published_time": _format_time(article.crawl_time), "type": "content", "source": "CSDN"}
        ))

    # 文档分割：每700字符一个块，重叠120字符
    splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=120)
    splits = splitter.split_documents(docs)

    # 使用DashScope的embedding模型
    dashscope_api_key = os.getenv("DASHSCOPE_API_KEY")
    
    if not dashscope_api_key:
        raise ValueError("DASHSCOPE_API_KEY 环境变量未设置")
    
    try:
        embeddings = DashScopeEmbeddings(
            dashscope_api_key=dashscope_api_key,
            model="multimodal-embedding-v1",
        )
        
        # 尝试构建Chroma向量库
        vs = Chroma.from_documents(
            documents=splits,
            embedding=embeddings,
            persist_directory=CHROMA_DIR,
            collection_name="blog_articles",
        )
        vs.persist()
        _VS = vs
        return _VS
    except Exception as e:
        # 提供更详细的错误信息
        import traceback
        traceback.print_exc()
        error_msg = f"向量库构建失败：{str(e)}"
        if "API key" in str(e) or "DASHSCOPE" in str(e):
            error_msg = "向量库构建失败：DashScope API 密钥无效或服务不可用"
        raise Exception(error_msg)


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
        error_msg = str(e)
        if error_msg == "'request'":
            return "AI 服务异常：API 调用失败，请检查 API Key 是否正确配置，以及免费额度是否已用完"
        return f"AI 服务异常：{error_msg}"


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
            metadata={"article_id": a["id"], "title": a["title"], "author": author_name, "published_time": _format_time(a.get('published_time')), "type": "author_info"}
        ))
        # 添加完整文章内容块
        docs.append(Document(
            page_content=f"标题：{a['title']}\n作者：{author_name}\n发布时间：{_format_time(a.get('published_time'))}\n内容：{a['content']}",
            metadata={"article_id": a["id"], "title": a["title"], "author": author_name, "published_time": _format_time(a.get('published_time')), "type": "content"}
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


def article_rag_qa_stream(article_content: str, question: str, request=None):
    """
    文章详情页专属的流式RAG问答
    
    功能说明：
    - 基于当前文章内容进行问答
    - 支持流式输出，实时显示AI回答
    - 优先使用当前文章内容，不依赖向量检索
    - 特别优化了文章总结功能
    
    Args:
        article_content: 当前文章内容
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
        # 获取用户ID，实现会话隔离
        user_id = str(request.user.id) if request and hasattr(request, 'user') and hasattr(request.user, 'id') else 'anonymous'
        history_key = f'chat_history_{user_id}'
        history = request.session.get(history_key, []) if request and hasattr(request, 'session') else []

        # 检查是否是总结文章的请求
        import re
        is_summary_request = bool(re.search(r'总结|概括|摘要|概述|总结这篇文章|概括这篇文章|摘要这篇文章|概述这篇文章', question))

        # 系统提示词：定义AI的角色和行为规则
        system_text = f"""
        # 角色定位
        你是【知文汇】博客平台的专属智能问答助手，专注于基于当前文章内容进行问答，所有回答严格基于文章原文，不使用任何外部知识。

        # 核心能力
        1. 文章理解：深入理解文章内容，准确提取核心信息
        2. 精准总结：对文章进行结构化、全面的总结
        3. 内容解析：回答基于文章内容的具体问题
        4. 细节提取：从文章中提取特定信息和数据

        # 核心铁律（必须严格遵守）
        1. 只基于当前文章内容回答，无依据则回复「文章中未提及相关内容」
        2. 绝不编造、杜撰、脑补任何文章中不存在的信息
        3. 忠实原文，不篡改、不夸张、不主观解读
        4. 回答简洁专业、条理清晰，能用分点则分点
        5. 多轮对话需结合历史上下文，但仍严格基于文章内容

        # 文章总结规范
        - 结构统一：核心观点 + 主要内容 + 关键结论
        - 内容必须全部来自原文，不添加主观评价
        - 输出格式：
          ```
          文章总结：
          核心观点：文章的核心观点
          主要内容：
          1. 主要内容点1
          2. 主要内容点2
          3. 主要内容点3
          关键结论：文章的关键结论
          ```

        # 输出格式规范
        1. 总结文章：结构清晰，分段明确，不用复杂 Markdown
        2. 技术问答：分点作答，来源标注清楚
        3. 禁止使用第一人称、口语化、情绪化表达
        4. 禁止添加开场白、客套话、多余解释

        # 禁止行为
        - 禁止使用外部知识回答任何问题
        - 禁止编造文章内容、作者、时间等信息
        - 禁止主观评论、引申、扩展原文含义
        """

        # 为总结请求添加特殊提示
        if is_summary_request:
            system_text += "\n\n# 特别注意：当用户请求总结当前文章时，请优先使用提供的文章内容进行详细总结，确保覆盖文章的核心观点、主要内容和关键结论。"

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_text),
            MessagesPlaceholder(variable_name="history"),
            ("human", "用户问题：{question}"),
            ("human", "文章内容：\n{content}"),
        ])

        chain = prompt | llm
        
        full_answer = []

        # 流式输出AI回答
        for chunk in chain.stream({
            "question": question.strip(),
            "content": content,
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
            request.session[history_key] = history
            request.session.modified = True

    except Exception as e:
        error_msg = str(e)
        if error_msg == "'request'":
            yield "服务异常：AI 服务调用失败，请检查 API Key 是否正确配置，以及免费额度是否已用完"
        else:
            yield f"服务异常：{error_msg}"


def global_rag_qa_stream(question: str, request=None, history_override=None):
    """
    首页全站AI功能专属的流式RAG问答
    
    功能说明：
    - 基于全站文章内容进行问答
    - 支持流式输出，实时显示AI回答
    - 使用向量检索获取相关文章内容
    - 特别优化了作者文章查询功能
    
    Args:
        question: 用户问题
        request: HTTP请求对象（用于获取session历史记录）
    
    Yields:
        str: AI回答的文本片段（流式输出）
    """
    try:
        if not question:
            yield "请输入有效问题"
            return

        llm, error = _get_llm()
        if error:
            yield error
            return

        from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
        # 获取用户ID，实现会话隔离
        user_id = str(request.user.id) if request and hasattr(request, 'user') and hasattr(request.user, 'id') else 'anonymous'
        history_key = f'chat_history_{user_id}'
        history = request.session.get(history_key, []) if request and hasattr(request, 'session') else []
        if history_override is not None:
            history = history_override

        # 系统提示词：定义AI的角色和行为规则
        system_text = f"""
        # 角色定位
        你是【知文汇】平台的专属智能问答助手，拥有全站文章检索与整合能力，所有回答严格基于站内已发布文章，不使用任何外部知识。

        # 核心能力
        1. 全站检索：可检索、引用、整合站内所有文章内容
        2. 多维度筛选：支持按**日期、时间段、作者、标签、分类**筛选文章
        3. 信息整合：跨文章提取、归纳、对比相关内容
        4. 精准总结：对单篇或多篇文章进行结构化总结
        5. 完整列举：对列表类问题做到不遗漏、不省略

        # 核心铁律（必须严格遵守）
        1. 只基于站内内容回答，无相关内容时统一回复：「站内文章未提及相关内容」
        2. 绝不编造、杜撰、脑补任何站内不存在的信息
        3. 忠实原文，不篡改、不夸张、不主观解读
        4. 列举类问题必须**全部列出**，禁止只给数量、禁止遗漏
        5. 引用内容必须标注来源：《文章标题》
        6. 时间格式统一为：YYYY年MM月DD日
        7. 回答简洁专业、条理清晰，能用分点则分点
        8. 多轮对话需结合历史上下文，但仍严格基于检索内容

        # 高频场景处理规则
        ## 1. 查询阅读量最高/最多的文章
        - 识别关键词：阅读量最高、阅读量最多、最多阅读、最高阅读
        - 处理步骤：
          1. 从「相关检索内容」中提取所有包含阅读量信息的文章
          2. 按阅读量从高到低排序
          3. 完整列出前10篇文章（如果不足10篇则列出全部）
          4. 每篇文章包含：标题、阅读量、作者、发布时间、核心内容简介
        - 输出格式：
          ```
          阅读量最高的文章列表（按阅读量从高到低排序）：
          1. 《文章标题1》（阅读量：1000）
             作者：作者名
             发布时间：2026年04月12日
             核心内容：文章的主要内容简介
          2. 《文章标题2》（阅读量：800）
             作者：作者名
             发布时间：2026年04月11日
             核心内容：文章的主要内容简介
          ```

        ## 2. 查询「某作者发布了哪些文章」（最高优先级，零容忍漏答）
        - 第一步：逐篇遍历「相关检索内容」，**筛选出所有作者匹配的文章，确保一篇不漏**
        - 第二步：按发布时间从新到旧排序，**完整列出所有匹配文章，绝对不允许遗漏任何一篇**
        - 强制格式（必须严格遵守，不得修改）：
          ```
          1. 《文章标题1》（2026年04月12日）
          2. 《文章标题2》（2026年04月11日）
          3. 《文章标题3》（2026年04月10日）
          ...
          N. 《文章标题N》（2026年04月01日）
          ```
        - 重要要求：无论有多少篇文章，都必须全部列出，不得省略或只返回部分

        ## 3. 查询某日期 / 某月份 / 某时间段的文章
        - 先筛选出全部匹配文章，再完整列出
        - 按时间顺序排列
        - 输出格式：
          ```
          2026年03月31日发布的文章：
          1. 《文章标题1》（2026年03月31日）
             核心内容：文章的主要内容简介
          2. 《文章标题2》（2026年03月31日）
             核心内容：文章的主要内容简介
          ```

        ## 4. 查询某标签 / 某分类的文章
        - 列出该分类/标签下**全部相关文章**
        - 每篇附带一句话核心简介
        - 输出格式：
          ```
          标签/分类：Python的文章：
          1. 《文章标题1》（2026年04月12日）
             核心内容：文章的主要内容简介
          2. 《文章标题2》（2026年04月11日）
             核心内容：文章的主要内容简介
          ```

        ## 5. 总结单篇文章 / 多篇文章
        - 结构统一：标题 + 时间 + 核心观点 + 主要内容 + 关键结论
        - 内容必须全部来自原文，不添加主观评价
        - 输出格式：
          ```
          文章总结：
          《文章标题》（2026年04月12日）
          核心观点：文章的核心观点
          主要内容：
          1. 主要内容点1
          2. 主要内容点2
          3. 主要内容点3
          关键结论：文章的关键结论
          ```

        ## 6. 对比类 / 技术类问题
        - 分点对比不同文章的观点、方法、结论
        - 每条均标注来源文章标题

        ## 7. 无匹配内容
        - 如果检索内容包含错误信息（如"系统错误"），直接展示该错误信息
        - 否则直接回复：「站内文章未提及相关内容」

        # 输出格式规范
        1. 列举文章：纯数字序号列表，不加多余符号
        2. 总结文章：结构清晰，分段明确，不用复杂 Markdown
        3. 技术问答：分点作答，来源标注清楚
        4. 禁止使用第一人称、口语化、情绪化表达
        5. 禁止添加开场白、客套话、多余解释

        # 禁止行为
        - 禁止使用外部知识回答任何问题
        - 禁止编造文章标题、内容、作者、时间
        - 禁止只说“有X篇”而不列出具体标题
        - 禁止遗漏检索到的相关文章
        - 禁止主观评论、引申、扩展原文含义
        """

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_text),
            MessagesPlaceholder(variable_name="history"),
            ("human", "用户问题：{question}"),
            ("human", "相关检索内容：\n{retrieved_docs}"),
        ])

        chain = prompt | llm
        
        # 尝试构建向量库并检索相关内容
        retrieved_text = ""
        try:
            vs = _build_vector_store_from_db()
            
            # 检查是否是作者查询问题
            import re
            author_match = re.search(r'作者(.+?)发布了哪些文章', question)
            
            if author_match:
                # 对于作者查询，使用更精确的检索方式
                author_name = author_match.group(1).strip()
                
                # 直接从数据库获取所有该作者的文章，确保时间信息正确
                from article.models import Article
                # 查询该作者的所有已发布文章
                articles = Article.objects.filter(status="published").select_related("author", "author__profile")
                author_articles = []
                for a in articles:
                    # 获取作者名称（优先使用昵称，其次使用用户名）
                    article_author = a.author.profile.nickname if hasattr(a.author, 'profile') and hasattr(a.author.profile, 'nickname') and a.author.profile.nickname else a.author.username
                    # 更宽松的匹配方式，确保能匹配到所有相关文章
                    if author_name in article_author or article_author in author_name:
                        author_articles.append(a)
                
                # 按发布时间从新到旧排序
                author_articles.sort(key=lambda x: x.published_time, reverse=True)
                
                # 构建检索结果
                retrieved_text = ""
                for a in author_articles:
                    # 构建作者信息块
                    article_author = a.author.profile.nickname if hasattr(a.author, 'profile') and hasattr(a.author.profile, 'nickname') and a.author.profile.nickname else a.author.username
                    doc_content = f"作者：{article_author}\n文章标题：{a.title}\n发布时间：{_format_time(a.published_time)}"
                    # 添加到检索结果中
                    retrieved_text += doc_content + "\n\n"
                
                # 如果没有匹配的文章，添加提示信息
                if not author_articles:
                    retrieved_text = f"未找到作者 {author_name} 的文章"
            else:
                # 非作者查询：先粗召回，再按关键词重排，减少噪音提升准确率
                import re
                raw_docs = vs.similarity_search(question, k=40)
                keywords = [k for k in re.split(r"[^\w\u4e00-\u9fa5]+", question.lower()) if len(k) >= 2]

                seen_ids = set()
                dedup_docs = []
                for d in raw_docs:
                    aid = d.metadata.get("article_id")
                    if aid in seen_ids:
                        continue
                    seen_ids.add(aid)
                    dedup_docs.append(d)

                def score_doc(doc):
                    text = (doc.page_content or "").lower()
                    if not keywords:
                        return 0
                    return sum(1 for kw in keywords if kw in text)

                ranked_docs = sorted(dedup_docs, key=score_doc, reverse=True)[:8]
                if not ranked_docs:
                    ranked_docs = dedup_docs[:8]

                # 限制上下文长度，避免无关长文本干扰
                chunks = []
                total_len = 0
                max_len = 12000
                for d in ranked_docs:
                    piece = (d.page_content or "").strip()
                    if not piece:
                        continue
                    if total_len + len(piece) > max_len:
                        break
                    chunks.append(piece)
                    total_len += len(piece)
                retrieved_text = "\n\n".join(chunks)
        except Exception as e:
            # 如果向量库构建失败，尝试从数据库直接获取文章内容作为备用方案
            import traceback
            traceback.print_exc()
            
            # 从数据库获取所有已发布文章
            from article.models import Article, JuejinHotArticle, CSDNArticle
            
            # 构建文章信息
            article_contents = []
            total_length = 0
            max_length = 25000  # 限制总长度，留一些余量
            
            # 添加本地文章（最多10篇）
            local_articles = Article.objects.filter(status="published").select_related("author", "author__profile", "category").prefetch_related("tags")[:10]
            for a in local_articles:
                author_name = a.author.profile.nickname if hasattr(a.author, 'profile') and hasattr(a.author.profile, 'nickname') and a.author.profile.nickname else a.author.username
                category_name = a.category.name if a.category else '未分类'
                tags = [tag.name for tag in a.tags.all()]
                tag_names = ', '.join(tags) if tags else '无标签'
                
                article_info = f"标题：{a.title}\n"
                article_info += f"作者：{author_name}\n"
                article_info += f"分类：{category_name}\n"
                article_info += f"标签：{tag_names}\n"
                article_info += f"发布时间：{_format_time(a.published_time)}\n"
                article_info += f"摘要：{a.summary if a.summary else '无摘要'}\n"
                article_info += f"内容：{a.content[:1000]}..."  # 限制内容长度
                article_info += f"来源：本地文章\n"
                
                # 检查长度
                if total_length + len(article_info) < max_length:
                    article_contents.append(article_info)
                    total_length += len(article_info)
                else:
                    break
            
            # 添加掘金热榜文章（最多20篇）
            if total_length < max_length:
                juejin_articles = JuejinHotArticle.objects.all().select_related().prefetch_related("tags")[:20]
                for article in juejin_articles:
                    author_name = article.author or '未知'
                    tags = [tag.name for tag in article.tags.all()]
                    tag_names = ', '.join(tags) if tags else '无标签'
                    
                    article_info = f"标题：{article.title}\n"
                    article_info += f"作者：{author_name}\n"
                    article_info += f"标签：{tag_names}\n"
                    article_info += f"来源：{article.source or '掘金'}\n"
                    article_info += f"发布时间：{_format_time(article.published_time)}\n"
                    article_info += f"爬取时间：{_format_time(article.crawl_time)}\n"
                    article_info += f"摘要：{article.summary or article.ai_summary or '无摘要'}\n"
                    article_info += f"原文链接：{article.original_url}\n"
                    
                    # 检查长度
                    if total_length + len(article_info) < max_length:
                        article_contents.append(article_info)
                        total_length += len(article_info)
                    else:
                        break
            
            # 添加CSDN文章（最多20篇）
            if total_length < max_length:
                csdn_articles = CSDNArticle.objects.all()[:20]
                for article in csdn_articles:
                    author_name = article.author or '未知'
                    
                    article_info = f"标题：{article.title}\n"
                    article_info += f"作者：{author_name}\n"
                    article_info += f"来源：{article.source or 'CSDN'}\n"
                    article_info += f"爬取时间：{_format_time(article.crawl_time)}\n"
                    article_info += f"摘要：{article.summary or '无摘要'}\n"
                    article_info += f"原文链接：{article.original_url}\n"
                    
                    # 检查长度
                    if total_length + len(article_info) < max_length:
                        article_contents.append(article_info)
                        total_length += len(article_info)
                    else:
                        break
            
            # 构建检索结果
            retrieved_text = "\n\n".join(article_contents)
            
            # 如果没有文章，添加提示信息
            if not article_contents:
                retrieved_text = "系统错误：向量库构建失败，且数据库中没有已发布的文章"
            else:
                # 添加错误提示，但仍然提供文章内容
                retrieved_text = f"系统提示：向量库构建失败，使用数据库文章内容作为备用方案\n\n{retrieved_text}"


        
        full_answer = []

        # 流式输出AI回答
        try:
            if not retrieved_text.strip():
                yield "站内文章未提及相关内容"
                return
            # 尝试获取流式响应
            result = chain.stream({
                "question": question.strip(),
                "retrieved_docs": retrieved_text,
                "history": history,
            })
            
            # 检查result是否是可迭代对象
            if hasattr(result, '__iter__'):
                for chunk in result:
                    text = chunk if isinstance(chunk, str) else getattr(chunk, "content", "")
                    if text:
                        full_answer.append(text)
                        yield text
            else:
                # 如果不是可迭代对象，直接yield结果
                yield str(result)
        except Exception as e:
            yield f"流式输出失败：{str(e)}"

        # 保存对话历史到session（最多保存10轮）
        if request and hasattr(request, 'session') and hasattr(request.session, 'modified'):
            history.append(("human", question.strip()))
            history.append(("assistant", "".join(full_answer)))
            if len(history) > 10:
                history = history[-10:]
            request.session[history_key] = history
            request.session.modified = True

    except Exception as e:
        error_msg = str(e)
        if error_msg == "'request'":
            yield "服务异常：AI 服务调用失败，请检查 API Key 是否正确配置，以及免费额度是否已用完"
        else:
            yield f"服务异常：{error_msg}"


def simple_rag_qa_stream(article_content: str, question: str, request=None):
    """
    兼容旧版本的流式RAG问答（用于全局AI问答）
    
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
    # 调用新的全局RAG问答函数
    return global_rag_qa_stream(question, request)


from langgraph.graph import StateGraph, END
from langchain_core.prompts import ChatPromptTemplate


def create_react_rag_graph():
    """
    创建基于ReAct模式的RAG工作流
    
    Returns:
        Compiled LangGraph workflow
    """
    tools = [vector_search_tool, author_search_tool, date_search_tool, year_search_tool, category_search_tool, tag_search_tool]
    llm, _ = _get_llm()
    llm_with_tools = llm.bind_tools(tools)

    # 提示词模板
    reasoner_prompt = ChatPromptTemplate.from_messages([
        ("system", "使用ReAct模式推理，分析问题并选择合适的工具执行查询。\n" +
         "你需要：\n" +
         "1. 分析用户问题的意图\n" +
         "2. 选择合适的工具进行查询\n" +
         "3. 规划下一步动作\n" +
         "4. 当信息充足时，决定是否结束推理"),
        ("human", "问题：{question}\n" +
         "历史思考：{thoughts}\n" +
         "历史行动：{actions}\n" +
         "历史观察：{observations}\n" +
         "当前上下文：{context}")
    ])
    
    answer_prompt = ChatPromptTemplate.from_messages([
        ("system", "仅基于检索内容回答，不编造，标注来源。\n" +
         "核心规则：\n" +
         "1. 只依据检索内容回答，无依据则回复「站内文章未提及相关内容」\n" +
         "2. 不编造、不拓展\n" +
         "3. 简洁专业、条理清晰\n" +
         "4. 引用内容必须标注来源：《文章标题》"),
        ("human", "问题：{question}\n" +
         "上下文：{context}")
    ])

    # 节点函数
    def question_analyzer(state: RAGState) -> RAGState:
        """问题分析器：识别查询类型"""
        return {
            **state,
            "thoughts": ["分析问题类型，确定检索策略"],
            "step_count": state["step_count"] + 1
        }

    def reasoner(state: RAGState) -> RAGState:
        """思考器：规划推理步骤"""
        chain = reasoner_prompt | llm_with_tools
        result = chain.invoke({
            "question": state["question"],
            "thoughts": "\n".join(state["thoughts"]),
            "actions": "\n".join(state["actions"]),
            "observations": "\n".join(state["observations"]),
            "context": state["context"]
        })
        
        thoughts = state["thoughts"].copy()
        thoughts.append(f"思考：{result.content}")
        
        return {
            **state,
            "thoughts": thoughts,
            "actions": state["actions"].copy(),
            "step_count": state["step_count"] + 1
        }

    def tool_selector(state: RAGState) -> RAGState:
        """工具选择器：匹配并调用对应检索工具"""
        try:
            question = state["question"]
            result = ""
            
            # 根据问题类型选择合适的工具
            import re
            
            # 1. 检查是否是年份查询
            year_match = re.search(r'(\d{4})年', question)
            if year_match:
                year = year_match.group(1)
                result = year_search_tool.invoke({"year": year})
            
            # 2. 检查是否是作者查询
            elif re.search(r'作者|发布者', question):
                author_match = re.search(r'作者(.+?)发布', question) or re.search(r'(.+?)发布', question)
                if author_match:
                    author_name = author_match.group(1).strip()
                    result = author_search_tool.invoke({"author_name": author_name})
                else:
                    result = vector_search_tool.invoke({"question": question, "k": 10})
            
            # 3. 检查是否是分类查询
            elif re.search(r'分类|类别', question):
                category_match = re.search(r'分类(.+?)的文章', question) or re.search(r'(.+?)分类', question)
                if category_match:
                    category_name = category_match.group(1).strip()
                    result = category_search_tool.invoke({"category_name": category_name})
                else:
                    result = vector_search_tool.invoke({"question": question, "k": 10})
            
            # 4. 检查是否是标签查询
            elif re.search(r'标签', question):
                tag_match = re.search(r'标签(.+?)的文章', question) or re.search(r'(.+?)标签', question)
                if tag_match:
                    tag_name = tag_match.group(1).strip()
                    result = tag_search_tool.invoke({"tag_name": tag_name})
                else:
                    result = vector_search_tool.invoke({"question": question, "k": 10})
            
            # 5. 检查是否是日期查询
            elif re.search(r'日期|时间|什么时候', question):
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', question)
                if date_match:
                    date_str = date_match.group(1)
                    result = date_search_tool.invoke({"date_str": date_str})
                else:
                    result = vector_search_tool.invoke({"question": question, "k": 10})
            
            # 6. 默认使用向量搜索
            else:
                result = vector_search_tool.invoke({"question": question, "k": 10})
            
            observations = state["observations"].copy()
            observations.append(f"观察：{result}")
            
            return {
                **state,
                "observations": observations,
                "context": state["context"] + "\n" + result,
                "step_count": state["step_count"] + 1
            }
        except Exception as e:
            return {
                **state,
                "observations": state["observations"] + [f"观察：工具调用失败：{str(e)}"],
                "step_count": state["step_count"] + 1
            }

    def context_integrator(state: RAGState) -> RAGState:
        """上下文整合器：合并多轮检索信息"""
        return {
            **state,
            "step_count": state["step_count"] + 1
        }

    def answer_generator(state: RAGState) -> RAGState:
        """答案生成器：依据上下文生成规范回答"""
        chain = answer_prompt | llm
        result = chain.invoke({
            "question": state["question"],
            "context": state["context"]
        })
        
        return {
            **state,
            "answer": result.content,
            "step_count": state["step_count"] + 1
        }

    def decider(state: RAGState) -> str:
        """决策器：控制推理循环是否继续"""
        if state["step_count"] >= state["max_steps"]:
            return "generate_answer"
        return "reason" if state["should_continue"] else "generate_answer"

    # 构建工作流
    workflow = StateGraph(RAGState)
    workflow.add_node("question_analyzer", question_analyzer)
    workflow.add_node("reasoner", reasoner)
    workflow.add_node("tool_selector", tool_selector)
    workflow.add_node("context_integrator", context_integrator)
    workflow.add_node("answer_generator", answer_generator)

    workflow.set_entry_point("question_analyzer")
    workflow.add_edge("question_analyzer", "reasoner")
    workflow.add_edge("reasoner", "tool_selector")
    workflow.add_edge("tool_selector", "context_integrator")
    workflow.add_conditional_edges(
        "context_integrator",
        lambda s: "reason" if s["step_count"] < s["max_steps"] and s["should_continue"] else "generate_answer",
        {"reason": "reasoner", "generate_answer": "answer_generator"}
    )
    workflow.add_edge("answer_generator", END)
    
    return workflow.compile()


def react_rag_qa_stream(question: str, request=None, max_steps=5):
    """
    基于ReAct模式的流式RAG问答
    
    Args:
        question: 用户问题
        request: HTTP请求对象（用于获取session历史记录）
        max_steps: 最大推理步骤
    
    Yields:
        str: AI回答的文本片段（流式输出）
    """
    try:
        if not question:
            yield "请输入有效问题"
            return

        graph = create_react_rag_graph()
        initial_state = {
            "question": question,
            "thoughts": [],
            "actions": [],
            "observations": [],
            "retrieved_docs": [],
            "context": "",
            "answer": "",
            "step_count": 0,
            "max_steps": max_steps,
            "should_continue": True
        }
        
        final_state = graph.invoke(initial_state)
        
        # 流式输出回答
        for c in final_state["answer"]:
            yield c
        
        # 保存对话历史
        if request and hasattr(request, 'session'):
            history = request.session.get('chat_history', [])
            history.append(("human", question.strip()))
            history.append(("assistant", final_state["answer"]))
            if len(history) > 10:
                history = history[-10:]
            request.session['chat_history'] = history
            request.session.modified = True

    except Exception as e:
        error_msg = str(e)
        if error_msg == "'request'":
            yield "服务异常：AI 服务调用失败，请检查 API Key 是否正确配置，以及免费额度是否已用完"
        else:
            yield f"服务异常：{error_msg}"


def global_rag_qa_stream_react(question: str, request=None):
    """
    基于ReAct模式的全局RAG问答
    
    Args:
        question: 用户问题
        request: HTTP请求对象
    
    Yields:
        str: AI回答的文本片段
    """
    return react_rag_qa_stream(question, request)


def article_rag_qa_stream_react(article_content: str, question: str, request=None):
    """
    基于ReAct模式的文章专属RAG问答
    
    Args:
        article_content: 文章内容
        question: 用户问题
        request: HTTP请求对象
    
    Yields:
        str: AI回答的文本片段
    """
    return react_rag_qa_stream(question, request)
