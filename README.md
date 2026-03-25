# KnowledgeHub
基于 Django 搭建的一站式内容服务平台，集成大模型能力与 LangChain 框架，实现 AI 辅助创作、内容智能问答及技术热榜聚合，已完成工程化部署。

## 项目介绍
- 开发框架：Django + Django REST Framework
- 数据存储：MySQL + Redis
- AI 能力：豆包大模型 API + LangChain (RAG)
- 部署方式：Nginx + Gunicorn
- 项目定位：内容管理 + AI 交互 + 热榜数据聚合平台

## 核心功能
### 内容管理模块
- 文章发布、编辑、删除、状态管理
- 分类与标签体系，支持多维度筛选
- 内容列表、详情页、分页、搜索功能
- 用户权限、个人资料、评论管理

### AI 增强功能
- 基于 LangChain 实现文章内容精准问答
- AI 标题优化、自动摘要生成
- 提示词约束，确保回答不编造、不离题
- 内容长度自动控制，避免大模型 Token 超限

### 热榜聚合模块
- 定时爬虫自动抓取技术平台热榜
- 数据清洗、去重、结构化入库
- 热榜展示、排序、分类筛选

### 性能优化
- Redis 缓存热点数据，降低数据库压力
- MySQL 索引优化，解决 ORM N+1 查询问题
- 生产环境部署，支持公网稳定访问

## 技术栈
- 后端：Python、Django、DRF
- 数据库：MySQL、Redis
- AI 框架：LangChain、豆包大模型 API
- 爬虫：Requests、re
- 部署：Nginx、Gunicorn、Linux、Git LFS
- 前端：HTML、CSS、JavaScript、Bootstrap

## 快速启动
```bash
git clone https://github.com/chaoxie2005/KnowledgeHub.git
cd KnowledgeHub

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 数据库迁移
python manage.py makemigrations
python manage.py migrate

# 启动项目
python manage.py runserver

项目亮点
前后端完整实现，独立开发、部署上线
分场景使用 AI 能力，简单生成 + 复杂问答结合
Redis + MySQL 双重性能优化，工程化落地
模块化结构清晰，低耦合、易扩展、易维护
Git LFS 支持大文件管理，适合学习与二次开发

核心问题与解决方案
AI 问答编造内容：使用 LangChain 提示词约束，仅依据文章内容回答
列表加载缓慢：Redis 缓存 + 索引优化，提升接口响应速度
大模型 Token 超限：自动截取内容，保证调用稳定
大文件上传：使用 Git LFS 管理媒体与静态资源
