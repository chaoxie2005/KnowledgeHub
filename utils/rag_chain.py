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
        
        # 添加作者信息块（用于作者查询）- 这个块专门用于检索作者的所有文章
        docs.append(Document(
            page_content=f"作者：{author_name}\n文章标题：{a['title']}\n发布时间：{_format_time(a.get('published_time'))}",
            metadata={"article_id": a["id"], "title": a["title"], "author": author_name, "type": "author_info"}
        ))
        # 添加完整文章内容块
        docs.append(Document(
            page_content=article_info,
            metadata={"article_id": a["id"], "title": a["title"], "author": author_name, "type": "content"}
        ))

    # 文档分割：每700字符一个块，重叠120字符
    splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=120)
    splits = splitter.split_documents(docs)

    # 使用DashScope的embedding模型
    dashscope_api_key = os.getenv("DASHSCOPE_API_KEY")
    embeddings = DashScopeEmbeddings(
        dashscope_api_key=dashscope_api_key,
        model="text-embedding-v2",
    )

    try:
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
        # 如果构建失败，尝试使用内存存储
        import traceback
        traceback.print_exc()
        # 使用内存存储作为备用方案
        vs = Chroma.from_documents(
            documents=splits,
            embedding=embeddings,
        )
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
        system_text = f"""
        # 角色定位
        你是【知文汇】博客平台的专属智能问答助手，拥有全站文章检索与整合能力，所有回答严格基于站内已发布文章，不使用任何外部知识。

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
        - 第二步：按发布时间从新到旧排序，完整列出所有匹配文章
        - 强制格式（必须严格遵守，不得修改）：
          ```
          1. 《文章标题1》（2026年04月12日）
          2. 《文章标题2》（2026年04月11日）
          3. 《文章标题3》（2026年04月10日）
          ```

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
        - 直接回复：「站内文章未提及相关内容」

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
            ("human", "文章内容：\n{content}"),
            ("human", "相关检索内容：\n{retrieved_docs}"),
        ])

        chain = prompt | llm
        
        # 尝试构建向量库并检索相关内容
        retrieved_text = ""
        try:
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
        except Exception as e:
            # 如果向量库构建失败，使用空字符串作为检索内容
            import traceback
            traceback.print_exc()
            retrieved_text = ""
        
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
