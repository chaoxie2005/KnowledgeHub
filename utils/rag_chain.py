# utils/rag_chain.py
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# 加载环境变量（和你 ai_utils.py 完全一致）
load_dotenv()

# 豆包模型（和你标题/摘要接口用同一个，100% 兼容）
llm = ChatOpenAI(
    api_key=os.getenv("DOUBAO_API_KEY"),
    base_url=os.getenv("DOUBAO_BASE_URL"),
    model="doubao-seed-2-0-lite-260215",
    temperature=0.1,
)

def simple_rag_qa(article_content: str, question: str) -> str:
    """
    LangChain 实现的 RAG 文章问答
    只根据文章内容回答，不编造，完全兼容豆包
    """
    if not article_content or not question:
        return "请输入有效问题"

    try:
        # 截取文章长度，避免 token 超限
        content = article_content[:6000]

        prompt = f"""
你是文章智能问答助手，必须严格遵守以下规则：
1. 只根据下面的【文章内容】回答问题，绝对不能编造信息
2. 尽量根据读者的问题，在不偏离文章原意的前提下回答内容
3. 回答简洁、专业、有条理，符合技术博客读者的阅读习惯
4. 如果不是技术博客内容的，回答符合偏文章内容风格的阅读习惯 


文章内容：
{content}

用户问题：{question}
"""
        response = llm.invoke(prompt)
        return response.content.strip()
    except Exception as e:
        return f"AI 服务异常：{str(e)}"