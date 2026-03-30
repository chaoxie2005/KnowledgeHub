from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import DashScopeEmbeddings

# 嵌入模型初始化
embeddings = DashScopeEmbeddings(
    dashscope_api_key="sk-325e1c4f1efe4ffcacea526cce8c9e7b",
    model="text-embedding-v3",
)

# 模型初始化
model = ChatTongyi(
    api_key="sk-325e1c4f1efe4ffcacea526cce8c9e7b",
    base_url="https://api.dashscope.com/v1",
    model="qwen3-max",
    temperature=0.1,
)

# 向量数据库初始化
vector_store = Chroma(
    collection_name='blog_articles',
    embedding_function=embeddings,
    persist_directory="./blog_chroma_db",  # 博客向量库
)

# RAG 问答提示模板
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "你是我的博客智能助手，基于我所有博客文章内容回答问题。禁止编造。"),
        ("human", "用户问题：{question}"),
        ("human", "以下是博客相关内容：{retrieved_docs}"),
    ]
)

db = SQLDatabase.from_uri(
    f"mysql+pymysql://ubuntu:123456@localhost:3306/{BASE_DIR}/db.sqlite3"
)

# 查询所有已发布文章
sql = "SELECT title, content, author FROM blog_articles WHERE status = 'published'"
articles = db.run(sql, fetch="all")  # [(标题1, 内容1, 作者1), (标题2, 内容2, 作者2), ...]

# 转成 LangChain 文档格式
docs = []
for title, content in articles:
    full_text = f"标题：{title}\n内容：{content}"
    docs.append(Document(page_content=full_text))
    
    
# ====================== 6. 文本分割（防止文章太长） ======================
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=100
)
splits = text_splitter.split_documents(docs)

vector_store.add_documents(
    documents=splits,
    ids=[str(i) for i in range(1, len(splits) + 1)]
)

# ====================== 8. 用户提问 + 检索博客内容 ======================
question = "Python 是不是简单易学？"  # 你可以换成任何问题

retrieved_docs = vector_store.similarity_search(
    query=question,
    k=3
)

chain = prompt | model
response = chain.invoke({
    "question": question,
    "retrieved_docs": retrieved_docs
})

# 输出最终答案
print("===== 博客智能回答 =====")
print(response.content)