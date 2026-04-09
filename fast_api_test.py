from fastapi import FastAPI
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
import os
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

from article.ai_utils import generate_article_summary, optimize_article_title


app = FastAPI(title="AI 接口优化", version="1.0.0")

# 配置CORS - 允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，生产环境中应该设置具体的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SummaryRequest(BaseModel):
    content: str = Field(..., min_length=1, description="文章内容不能为空")
    max_length: int = Field(200, ge=50, le=500, description="摘要长度")

class TitleRequest(BaseModel):
    title: str = Field(..., min_length=1, description="标题不能为空")

@app.post('/ai/generate-summary')
async def generate_summary(request: SummaryRequest):
    if not request.content:
        return {'success': False, 'error': "文章内容不能为空"}
    try:
        summary = generate_article_summary(request.content, request.max_length)
        return {'success': True, 'summary': summary}
    except Exception as e:
        return {'success': False, 'error': str(e)}


@app.post('/ai/optimize-title')
async def optimize_title(request: TitleRequest):
    if not request.title:
        return {'success': False, 'error': "标题不能为空"}
    try:
        optimized_title = optimize_article_title(request.title)
        return {'success': True, 'optimized_title': optimized_title}
    except Exception as e:
        return {'success': False, 'error': str(e)}

# 根路径
@app.get("/")
async def root():
    return {
        "message": "AI 功能接口",
        "endpoints": [
            "/ai/generate-summary",
            "/ai/optimize-title"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
