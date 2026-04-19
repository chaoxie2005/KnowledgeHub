# ExtraordinaryBlog (知文汇) - 智能化内容聚合与 RAG 问答平台

[![Django](https://img.shields.io/badge/Framework-Django%204.2-green.svg)](https://www.djangoproject.com/)
[![DRF](https://img.shields.io/badge/API-DRF-red.svg)](https://www.django-rest-framework.org/)
[![AI](https://img.shields.io/badge/AI-LangChain%20%2B%20Doubao-blue.svg)](https://www.langchain.com/)

## 🚀 项目简介
**ExtraordinaryBlog** 是一个基于 Django 构建的现代化博客系统，深度集成大模型（LLM）能力。项目不仅具备完整的文章管理功能，还实现了自动化技术热榜抓取、AI 自动摘要、标题优化，以及基于全站知识库的 RAG（检索增强生成）智能问答。

## 🛠️ 核心技术栈
- **后端**: Django 4.2 + Django REST Framework (DRF)
- **数据库**: SQLite (支持快速迁移 MySQL/PostgreSQL)
- **缓存**: Redis (用于分页数据缓存、接口限流)
- **大模型**: 火山引擎豆包大模型 API + LangChain
- **任务调度**: APScheduler (定时爬虫任务)
- **部署**: Nginx + Gunicorn + WhiteNoise

## ✨ 核心功能亮点

### 🤖 1. AI 赋能内容生产
- **AI 摘要 & 标题优化**: 利用大模型自动提取文章核心摘要并优化标题，提升内容质量与吸引力。
- **全站 RAG 智能问答**: 基于 LangChain 封装，通过数据库检索最相关的文章内容作为上下文，实现精准的智能问答，有效抑制大模型“幻觉”。

### 🕷️ 2. 自动化热榜聚合
- **掘金爬虫**: 自动爬取稀土掘金热榜数据，支持内容去重、标签匹配与 AI 二次加工。
- **定时任务**: 使用 APScheduler 自动执行，确保热榜数据每日更新。

### ⚡ 3. 工业级性能优化
- **Cache-Aside 缓存模式**: 针对高频访问的分页数据，利用 Redis 缓存 ID 列表，显著降低数据库负载。
- **缓存主动失效**: 爬虫任务完成后自动清理旧缓存，保证数据实时一致性。
- **系统降级保护**: 对 Redis/数据库连接进行异常捕获，在中间件故障时自动降级为普通查询，保障服务高可用。

## 📦 快速开始

### 1. 环境准备
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置环境变量
创建 `.env` 文件并配置：
```env
SECRET_KEY=你的Django密钥
DOUBAO_API_KEY=你的火山引擎API密钥
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
```

### 3. 初始化数据库与启动
```bash
python manage.py migrate
python manage.py runserver
```

## 📈 未来规划
- [ ] 接入向量数据库 (Milvus/ChromaDB) 升级语义搜索。
- [ ] 使用 Celery 异步化 AI 处理任务与爬虫流程。
- [ ] 全站 Elasticsearch 全文检索支持。

---
**项目演示**: [114.132.242.177](http://114.132.242.177)