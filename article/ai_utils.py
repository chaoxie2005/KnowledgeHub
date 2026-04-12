# -*- coding: utf-8 -*-
import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 全局变量：缓存LLM实例
_LLM = None


def safe_print(text):
    """安全打印中文，兼容 Windows 终端编码"""
    try:
        print(text)
    except UnicodeEncodeError:
        if sys.platform == "win32":
            print(text.encode("utf-8").decode("gbk", errors="ignore"))
        else:
            print(text.encode("utf-8").decode("utf-8", errors="ignore"))


def _get_llm():
    """
    获取或初始化LLM实例（单例模式）
    
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

    api_key = os.getenv("QWEN_API_KEY")
    if not api_key:
        return None, "未配置 QWEN_API_KEY"

    try:
        _LLM = ChatTongyi(
            api_key=api_key,
            model="deepseek-r1-distill-qwen-7b",
            temperature=0.8,
            streaming=True,
        )
    except TypeError:
        _LLM = ChatTongyi(
            api_key=api_key,
            model="deepseek-r1-distill-qwen-7b",
            temperature=0.8,
        )
    return _LLM, None


def generate_article_summary(content: str, max_length: int = 500) -> str:
    """生成技术文章AI摘要"""
    if not content or len(content.strip()) == 0:
        return "暂无摘要"

    llm, error = _get_llm()
    if error:
        safe_print(f"【AI摘要生成失败】错误信息：{error}")
        return "暂无摘要"

    try:
        from langchain_core.prompts import ChatPromptTemplate
    except ModuleNotFoundError:
        safe_print("【AI摘要生成失败】请安装：pip install langchain-core")
        return "暂无摘要"

    try:
        system_text = f"""你是一位专业的技术博客摘要专家，擅长从技术文章中提取核心内容并进行结构化总结。请按照以下步骤和要求生成摘要：

        ## 工作步骤
        1.  首先阅读并理解文章内容，识别文章类型和核心主题
        2.  提取文章的核心技术点、关键实现步骤、核心结论和技术选型理由
        3.  按照"是什么—怎么做—有什么用"的逻辑结构组织摘要内容
        4.  检查摘要长度，确保不超过{max_length}字

        ## 核心要求
        1.  **长度控制**：摘要长度严格控制在{max_length}字以内（含标点符号），优先保留关键信息，适当精简次要细节
        2.  **内容准确**：严格基于原文内容，不篡改原意、不增减技术细节、不添加个人主观判断
        3.  **语言规范**：
            - 风格：简洁干练、逻辑清晰、专业严谨，符合技术读者阅读习惯
            - 术语：准确使用原文中的技术术语，不随意替换或简写
            - 句式：以短句为主，避免冗长复杂句式，可适当使用分号分隔相关技术点
        4.  **重点突出**：
            - 开发类博客：重点保留技术选型、核心代码逻辑、实现步骤、注意事项
            - 运维/部署类博客：重点保留部署环境、部署步骤、配置要点、故障排查方法
            - 技术解析类博客：重点保留技术原理、核心特性、对比分析、应用场景
            - 实战教程类博客：重点保留教程目标、前置准备、关键步骤、最终效果
            - 技术复盘类博客：重点保留项目背景、核心技术难点、解决思路、复盘结论
            - 技术资讯/更新类博客：重点保留技术更新亮点、版本迭代内容、新特性介绍
            - 入门科普类博客：重点保留技术定义、核心用途、入门要点、学习路径
            - 踩坑经验类博客：重点保留问题背景、报错信息、排查过程、解决方案

        ## 输出格式
        - 只返回摘要内容，不添加任何额外说明、标题或标识
        - 不换行、不分段，纯文本呈现
        - 确保摘要可直接复制使用
        """
        
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_text),
            ("human", "请为以下技术文章生成摘要：\n{content}"),
        ])
        
        chain = prompt | llm
        response = chain.invoke({"content": content})
        summary = response.content.strip()
        
        return summary[:max_length] if len(summary) > max_length else summary
    except Exception as e:
        safe_print(f"【AI摘要生成失败】错误信息：{str(e)}")
        return "暂无摘要"


def optimize_article_title(title: str) -> str:
    """优化技术博客标题"""
    if not title or len(title.strip()) == 0:
        return title

    llm, error = _get_llm()
    if error:
        safe_print(f"【标题优化失败】错误信息：{error}")
        return title

    try:
        from langchain_core.prompts import ChatPromptTemplate
    except ModuleNotFoundError:
        safe_print("【标题优化失败】请安装：pip install langchain-core")
        return title

    try:
        system_text = f"""你是一位资深的技术博客标题优化专家，擅长为技术文章创建吸引人且专业的标题。请按照以下步骤和要求优化标题：
        ## 工作步骤
        1.  首先分析原标题，识别核心关键词和主题
        2.  根据文章类型选择合适的优化策略
        3.  添加适当的emoji和亮点词汇
        4.  调整标题长度和结构
        5.  检查优化后的标题是否符合所有要求

        ## 核心要求
        1.  **核心一致性**：严格保留原标题的核心关键词，不替换、删减核心关键词，不改变原标题的核心原意
        2.  **吸引力优化**：
            - emoji使用：添加1-2个贴合技术场景的emoji（如🔥、💡、🔧、🚀、🛠️、📝、💻、⚡等），放置在标题开头或中间，不堆砌、不使用与技术无关的emoji
            - 语气适配：使用引导式、痛点式或价值式语气，兼顾专业度与吸引力，不浮夸、不低俗
            - 亮点突出：结合文章核心价值，适当强化标题亮点，不添加与原文无关的内容
        3.  **长度控制**：标题长度严格控制在20-30字（含标点符号、emoji），若原标题过短可补充贴合主题的辅助词汇，若过长可精简冗余表述，不改变核心含义
        4.  **适配性要求**：
            - 搜索引擎友好：核心技术关键词位置尽量靠前，避免堆砌关键词、重复表述
            - 社区阅读友好：句式简洁干练，不使用晦涩难懂的表述，兼顾专业性与可读性，便于传播
            - 分类型适配：
                - 开发/实战类：突出"实战""拆解""实现""教程"等关键词，搭配🔧、💻等emoji
                - 踩坑/故障类：突出"避坑""排查""解决""报错"等关键词，搭配⚠️、🔍等emoji
                - 入门/科普类：突出"零基础""入门""详解""科普"等关键词，搭配💡、📝等emoji
                - 资讯/更新类：突出"更新""新特性""迭代""指南"等关键词，搭配🚀、⚡等emoji
                - 优化/技巧类：突出"优化""高效""技巧""实战总结"等关键词，搭配🔥、🛠️等emoji

        ## 输出格式
        - 只返回优化后的标题，不添加任何额外说明、解释或标识
        - 不换行、不分段，纯文本呈现（含emoji）
        - 确保标题可直接复制使用，无多余空格、标点错误

        ## 示例
        输入："Docker容器化部署Python应用"
        输出："🚀 Docker容器化部署Python应用实战指南"

        输入："Vue性能优化技巧"
        输出："🔥 Vue性能优化实战技巧：让应用飞起来"
        """
        
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_text),
            ("human", "优化这个技术博客标题：{title}"),
        ])
        
        chain = prompt | llm
        response = chain.invoke({"title": title})
        optimized_title = response.content.strip()
        
        return optimized_title if optimized_title else title
    except Exception as e:
        safe_print(f"【标题优化失败】错误信息：{str(e)}")
        return title
