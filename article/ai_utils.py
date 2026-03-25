# -*- coding: utf-8 -*-
import os
import sys
from openai import OpenAI
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 初始化火山引擎豆包 AI 客户端
client = OpenAI(
    api_key=os.getenv("DOUBAO_API_KEY"),
    base_url=os.getenv("DOUBAO_BASE_URL"),
)


def safe_print(text):
    """安全打印中文，兼容 Windows 终端编码"""
    try:
        print(text)
    except UnicodeEncodeError:
        if sys.platform == "win32":
            print(text.encode("utf-8").decode("gbk", errors="ignore"))
        else:
            print(text.encode("utf-8").decode("utf-8", errors="ignore"))


def generate_article_summary(content: str, max_length: int = 200) -> str:
    """生成技术文章AI摘要"""
    if not content or len(content.strip()) == 0:
        return "暂无摘要"

    try:
        response = client.chat.completions.create(
            model="doubao-seed-2-0-lite-260215",  # 你的模型ID
            messages=[
                {
                    "role": "system",
                    "content": f"""你是专业的技术博客摘要助手，需遵守以下规则：
                    1. 摘要长度严格控制在{max_length}字以内，根据文章内容生成
                    2. 保留文章核心技术点和关键步骤，不改变原意
                    3. 语言简洁、逻辑清晰，特色鲜明，符合技术读者阅读习惯
                    4. 只返回摘要内容，不添加额外说明""",
                },
                {"role": "user", "content": f"请为以下技术文章生成摘要：\n{content}"},
            ],
            temperature=0.7,
            max_tokens=max_length + 20,
        )
        summary = response.choices[0].message.content.strip()
        return summary[:max_length] if len(summary) > max_length else summary
    except Exception as e:
        safe_print(f"【AI摘要生成失败】错误信息：{str(e)}")
        return "暂无摘要"


def optimize_article_title(title: str) -> str:
    """优化技术博客标题"""
    if not title or len(title.strip()) == 0:
        return title

    try:
        response = client.chat.completions.create(
            model="doubao-seed-2-0-lite-260215",  # 你的模型ID
            messages=[
                {
                    "role": "system",
                    "content": """你是资深技术博客标题优化专家，需遵守以下规则：
                    1. 保留原标题核心关键词，不改变原意
                    2. 标题更吸引技术读者，可适当添加emoji（如🔥、💡）
                    3. 长度控制在20-30字，符合搜索引擎和社区阅读习惯
                    4. 只返回优化后的标题，不添加额外说明""",
                },
                {"role": "user", "content": f"优化这个技术博客标题：{title}"},
            ],
            temperature=0.8,
        )
        optimized_title = response.choices[0].message.content.strip()
        return optimized_title if optimized_title else title
    except Exception as e:
        safe_print(f"【标题优化失败】错误信息：{str(e)}")
        return title
