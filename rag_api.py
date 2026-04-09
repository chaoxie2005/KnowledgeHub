"""RAG 功能 FastAPI 接口"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
import os
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

# 导入 RAG 功能
from utils.rag_chain import simple_rag_qa, simple_rag_qa_stream, update_vector_store

app = FastAPI(title="RAG 功能接口", version="1.0")

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 定义请求模型
class RQARequest(BaseModel):
    article_content: str = Field(..., description="文章内容")
    question: str = Field(..., description="用户问题")

class UpdateVectorStoreRequest(BaseModel):
    force: bool = Field(False, description="是否强制更新")

# 普通 RAG 问答接口
@app.post("/rag/qa")
async def rag_qa(request: RQARequest):
    try:
        answer = simple_rag_qa(request.article_content, request.question)
        return {
            "success": True,
            "answer": answer
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

# 流式 RAG 问答接口
@app.post("/rag/qa/stream")
async def rag_qa_stream(request: Request, rqa_request: RQARequest):
    try:
        # 流式生成回答
        async def generate():
            for chunk in simple_rag_qa_stream(rqa_request.article_content, rqa_request.question, request):
                yield chunk
        
        return generate()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 更新向量库接口
@app.post("/rag/update-vector-store")
async def rag_update_vector_store(request: UpdateVectorStoreRequest):
    try:
        result = update_vector_store()
        return {
            "success": True,
            "message": result
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

# 根路径
@app.get("/")
async def root():
    return {
        "message": "RAG 功能接口",
        "endpoints": [
            "/rag/qa",
            "/rag/qa/stream",
            "/rag/update-vector-store"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
