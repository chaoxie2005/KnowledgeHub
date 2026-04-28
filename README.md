# ExtraordinaryBlog (知文汇) - 智能化内容聚合与 RAG 问答平台

[![Django](https://img.shields.io/badge/Framework-Django%204.2-green.svg)](https://www.djangoproject.com/)
[![DRF](https://img.shields.io/badge/API-DRF-red.svg)](https://www.django-rest-framework.org/)
[![AI](https://img.shields.io/badge/AI-LangChain%20%2B%20Doubao-blue.svg)](https://www.langchain.com/)

## 项目简介

**ExtraordinaryBlog** 是一个基于 Django 构建的现代化博客系统，深度集成大模型（LLM）能力。项目不仅具备完整的文章管理功能，还实现了自动化技术热榜抓取、AI 自动摘要、标题优化，以及基于全站知识库的 RAG（检索增强生成）智能问答。

## 技术架构

### 核心技术栈

- **后端框架**: Django 4.2 + Django REST Framework (DRF)
- **数据库**: MySQL / SQLite
- **缓存**: Redis（分页缓存、接口限流）
- **大模型**: 火山引擎豆包大模型 API + LangChain
- **任务调度**: APScheduler（定时爬虫任务）
- **部署**: Nginx + Gunicorn + WhiteNoise

### 项目模块

| 模块 | 功能描述 |
|------|----------|
| `core` | 核心功能：首页、搜索、AI问答、数据可视化、学习中心 |
| `authentication` | 用户认证：注册、登录、密码重置、账号激活 |
| `article` | 文章管理：CRUD、评论、点赞、热榜爬取、AI处理 |
| `users` | 用户中心：个人信息管理 |
| `middleware` | 中间件：CORS、安全头、Gzip压缩、IP限流、维护模式 |

## 核心功能

### 1. AI 赋能内容生产

- **AI 摘要生成**: 利用大模型自动提取文章核心摘要
- **标题优化**: AI 智能优化文章标题，提升吸引力
- **全站 RAG 智能问答**: 基于 LangChain，通过向量检索最相关文章作为上下文，实现精准智能问答

### 2. 自动化热榜聚合

- **掘金爬虫**: 自动爬取稀土掘金热榜数据，支持内容去重、标签匹配与 AI 二次加工
- **CSDN 爬虫**: 支持 CSDN 热榜数据抓取
- **定时任务**: 使用 APScheduler 自动执行，确保热榜数据每日更新

### 3. 博客核心功能

- **文章管理**: 支持 Markdown 写作、分类、标签、多媒体封面
- **评论系统**: 支持嵌套回复、点赞、敏感词审核
- **用户系统**: 注册、登录、个人中心、积分体系
- **内容审核**: 自动审核机制，违规内容检测

### 4. 学习中心

- **quiz 题库**: 学习问答模块
- **学习计划**: 个性化学习路径规划
- **错题本**: 记录并分析学习薄弱点

### 5. 性能优化

- **Cache-Aside 缓存模式**: Redis 缓存高频访问数据
- **主动缓存失效**: 数据更新时自动清理旧缓存
- **系统降级保护**: 异常时自动降级为普通查询
- **Gzip 压缩**: HTTP 响应压缩，减少传输体积
- **IP 限流**: 防止恶意请求

## 项目结构

```
ExtraordinaryBlog/
├── article/                  # 文章模块
│   ├── models.py            # 文章、分类、标签、评论模型
│   ├── views.py             # 文章视图与API
│   ├── serializers.py        # DRF序列化器
│   ├── crawl_juejin.py       # 掘金爬虫
│   ├── crawl_csdn.py         # CSDN爬虫
│   └── ai_utils.py          # AI工具函数
├── authentication/           # 认证模块
│   ├── views.py             # 注册、登录等视图
│   ├── forms.py             # 表单验证
│   └── urls.py              # 路由配置
├── core/                     # 核心模块
│   ├── views.py             # 首页、搜索、AI问答
│   └── urls.py              # 核心路由
├── users/                    # 用户模块
│   ├── models.py            # 用户扩展模型
│   ├── views.py             # 用户中心视图
│   └── forms.py             # 用户表单
├── middleware/              # 自定义中间件
│   ├── cors.py              # 跨域中间件
│   ├── gzip.py              # Gzip压缩
│   ├── security_headers.py  # 安全头
│   ├── ip_rate_limit.py     # IP限流
│   └── request_log.py       # 请求日志
├── utils/                   # 工具函数
│   ├── rag_chain.py         # RAG问答链
│   └── content_audit.py     # 内容审核
├── templates/               # 模板文件
├── extraordinaryblog/       # 项目配置
│   ├── settings.py          # Django配置
│   ├── urls.py              # 主路由
│   └── wsgi.py              # WSGI入口
└── requirements.txt         # 依赖列表
```

## 快速开始

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

# 数据库配置（使用MySQL时）
MYSQL_DATABASE_NAME=your_database_name
MYSQL_PASSWORD=your_password

# 邮件配置
EMAIL_HOST_USER=your_email@example.com
EMAIL_HOST_PASSWORD=your_email_password
```

### 3. 初始化数据库

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 4. 启动服务

```bash
# 开发环境
python manage.py runserver

# 生产环境
gunicorn extraordinaryblog.wsgi:application -w 4 -b 0.0.0.0:8000
```

## API 接口

项目提供完整的 RESTful API，支持以下功能：

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/articles/` | GET/POST | 文章列表/创建 |
| `/api/articles/{id}/` | GET/PUT/DELETE | 文章详情/修改/删除 |
| `/api/categories/` | GET/POST | 分类列表/创建 |
| `/api/comments/` | GET/POST | 评论列表/创建 |

## 定时任务

项目使用 APScheduler 管理定时任务：

- **热榜爬取**: 每日自动爬取掘金/CSDN热榜
- **缓存清理**: 定期清理过期缓存

## 部署

项目支持 Nginx + Gunicorn 部署：

```nginx
# nginx.conf 示例
server {
    listen 80;
    server_name your_domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /static/ {
        alias /path/to/static/;
    }
}
```

## 未来规划

- [ ] 接入向量数据库 (Milvus/ChromaDB) 升级语义搜索
- [ ] 使用 Celery 异步化 AI 处理任务与爬虫流程
- [ ] 全站 Elasticsearch 全文检索支持
- [ ] 用户行为分析与个性化推荐

## 演示地址

**项目演示**: [114.132.242.177](http://114.132.242.177)

## 许可证

本项目仅供学习交流使用。
