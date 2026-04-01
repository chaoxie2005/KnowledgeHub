"""站内文章 RAG（向量检索 + 流式输出）
已修复：模型错误、base_url错误、额度超限、400报错
"""

import os
from dotenv import load_dotenv
from datetime import datetime
import pytz

load_dotenv()

_LLM = None
_VS = None

def _format_time(utc_time):
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
    global _VS
    import os, time, shutil
    from article.models import Article
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import Chroma
    from langchain_community.embeddings import DashScopeEmbeddings

    CHROMA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "chroma_blog")
    os.makedirs(CHROMA_DIR, exist_ok=True)

    rebuild = False
    if _VS is None:
        rebuild = True
    else:
        chroma_db_path = os.path.join(CHROMA_DIR, "chroma.sqlite3")
        if os.path.exists(chroma_db_path):
            mtime = os.path.getmtime(chroma_db_path)
            if time.time() - mtime > 3600:
                rebuild = True
        else:
            rebuild = True

    qs = Article.objects.filter(status="published").select_related("author", "author__profile").values(
        "id", "title", "content", "author__username", "author__profile__nickname", "published_time"
    )

    if rebuild:
        if os.path.exists(CHROMA_DIR):
            try:
                shutil.rmtree(CHROMA_DIR)
                os.makedirs(CHROMA_DIR, exist_ok=True)
            except:
                pass

    docs = [
        Document(
            page_content=f"标题：{a['title']}\n作者：{a.get('author__profile__nickname', a.get('author__username', '未知'))}\n发布时间：{_format_time(a.get('published_time'))}\n内容：{a['content']}",
            metadata={"article_id": a["id"], "title": a["title"]}
        )
        for a in qs
    ]

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    splits = splitter.split_documents(docs)

    dashscope_api_key = os.getenv("DASHSCOPE_API_KEY")
    embeddings = DashScopeEmbeddings(
        dashscope_api_key=dashscope_api_key,
        model="text-embedding-v1",
    )

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

    qs = Article.objects.filter(status="published").values("id", "title", "content", "author__username", "published_time")
    docs = [
        Document(
            page_content=f"标题：{a['title']}\n作者：{a.get('author__username','未知')}\n发布时间：{_format_time(a.get('published_time'))}\n内容：{a['content']}",
            metadata={"article_id": a["id"], "title": a["title"]}
        )
        for a in qs
    ]

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

        system_text = """
            # 角色定位
            你是【XX博客】专属的智能问答助手，核心使命是**100%严格基于用户提供的「文章内容」和「站内检索到的相关内容」回答问题**，绝对不使用任何外部知识、不主观臆断、不编造信息、不拓展延伸。

            # 核心铁律（违反任何一条即严重违规）
            1.  **只答有依据的内容**：所有回答必须能在「当前文章内容」或「相关检索内容」中找到原文依据，无依据的问题必须直接回复「文章中未提及相关内容」，绝不编造任何信息。
            2.  **绝对不拓展不延伸**：禁止对原文内容进行任何解读、补充、引申、举例，禁止回答超出原文范围的问题，禁止使用「我认为」「一般来说」「通常」等主观表述。
            3.  **严格忠实原文**：必须1:1还原原文的观点、数据、逻辑、时间、人物，不得篡改、曲解、简化原文内容，不得改变原文的表述顺序和核心意思。
            4.  **上下文连贯规则**：回答多轮对话时，必须结合历史对话上下文，同时严格基于最新的检索内容，不得脱离原文进行上下文联想编造。
            5.  **格式与风格要求**：
                - 回答简洁专业、条理清晰，技术类问题用精炼术语，非技术类问题贴合原文文风
                - 能用分点则分点，不冗余、不啰嗦，避免生硬列表，保持自然流畅
                - 时间格式统一为「YYYY年MM月DD日 HH:MM」，友好易读
                - 禁止使用情绪化、口语化表达，禁止添加无关解释、客套话、开场白
            6.  **特殊问题处理规则**：
                - 当用户查询作者的所有文章时，必须完整列出检索到的所有相关文章标题、发布时间，不得遗漏
                - 当检索内容存在矛盾时，优先以「当前文章内容」为准，其次以最新发布的文章为准
                - 当问题涉及多个文章时，需整合所有相关原文内容，分点清晰呈现，不得遗漏关键信息
                - 当用户问题与文章内容完全无关时，直接回复「文章中未提及相关内容」

            # 禁止行为（绝对不能做）
            ❌ 禁止使用任何外部知识回答问题
            ❌ 禁止编造、杜撰、脑补任何原文没有的信息
            ❌ 禁止对原文内容进行解读、评论、拓展、引申
            ❌ 禁止回答超出原文范围的问题
            ❌ 禁止使用「我」「我们」等第一人称表述
            ❌ 禁止添加任何无关的解释、说明、客套话
            ❌ 禁止改变原文的观点、数据、逻辑
            ❌ 禁止在回答中出现「根据文章内容」「如上所述」等引导性表述，直接输出答案即可
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
        retrieved_docs = vs.similarity_search(question, k=50)  # 增加k值，确保所有文章都被检索到
        seen_ids = set()
        unique_docs = []
        for d in retrieved_docs:
            aid = d.metadata.get("article_id")
            if aid not in seen_ids:
                seen_ids.add(aid)
                unique_docs.append(d)

        retrieved_text = "\n\n".join([d.page_content for d in unique_docs])
        full_answer = []

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

        if request and hasattr(request, 'session'):
            history.append(("human", question.strip()))
            history.append(("assistant", "".join(full_answer)))
            if len(history) > 10:
                history = history[-10:]
            request.session['chat_history'] = history
            request.session.modified = True

    except Exception as e:
        yield f"服务异常：{str(e)}"