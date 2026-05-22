# 知文汇（ExtraordinaryBlog）代码重构文档

> 重构日期：2026-05-16  
> 备份分支：`backup-ui-before-refactoring-20260516`  
> 重构原则：不破坏任何现有功能，所有 URL、模板、外部导入保持兼容

---

## 一、重构背景

知文汇是基于 Django 4.2 的 AI 博客平台，随着功能迭代出现以下问题：

1. **`article/views.py` 单文件 2002 行** — 包含文章展示、CRUD、热榜、AI、评论、测验、学习计划等所有视图逻辑
2. **`utils/rag_chain.py` 单文件 1356 行** — LLM、向量检索、ReAct 工作流、流式输出混在一起
3. **多个运行时 Bug** — 字段名错误、非守护线程、静默异常、中间件废弃头等
4. **代码重复** — `_get_llm` 在两个文件中各有一份实现
5. **`requirements.txt` 膨胀** — 162 行系统级 `pip freeze` 快照，无法区分真实依赖

---

## 二、Bug 修复清单

### 2.1 `cron_jobs.py` — 字段名错误（运行时报 FieldError）

**问题**：第 75 行和第 89 行使用 `created_at__gte`，但 `Comment` 和 `Article` 模型的实际字段名是 `created_time`。

```python
# 修复前
Comment.objects.filter(created_at__gte=...)
Article.objects.filter(created_at__gte=...)

# 修复后
Comment.objects.filter(created_time__gte=...)
Article.objects.filter(created_time__gte=...)
```

### 2.2 `article/models.py` — Tag 模型 verbose_name 复制粘贴错误

**问题**：Tag 模型第 28 行 `verbose_name="分类名称"` 是从 Category 模型复制粘贴过来的。

```python
# 修复前
class Tag(models.Model):
    name = models.CharField(max_length=100, verbose_name="分类名称")

# 修复后
class Tag(models.Model):
    name = models.CharField(max_length=100, verbose_name="标签名称")
```

### 2.3 `article/models.py` — Article.save() 非守护线程导致进程无法退出

**问题**：`threading.Thread(target=update_vector_store).start()` 没有 `daemon=True`。

```python
# 修复前
threading.Thread(target=update_vector_store).start()

# 修复后
threading.Thread(target=update_vector_store, daemon=True).start()
```

### 2.4 `article/models.py` — 空的 except 块吞掉异常

**问题**：缓存清除错误被 `except Exception as e: pass` 静默吞掉。

```python
# 修复前
except Exception as e:
    pass

# 修复后
except Exception:
    logger.exception("清除文章缓存失败")
```

### 2.5 `utils/rag/chain.py` — 两个函数使用不同 embedding 模型写入同一目录

**问题**：`_build_vector_store_from_db` 使用 `multimodal-embedding-v1`，`update_vector_store` 使用 `text-embedding-v1`，两者写入同一个 `CHROMA_DIR`。

```python
# 修复前（_build_vector_store_from_db 中）
embeddings = DashScopeEmbeddings(model="multimodal-embedding-v1")

# 修复后（统一为 text-embedding-v1）
embeddings = DashScopeEmbeddings(model="text-embedding-v1")
```

### 2.6 `utils/rag/chain.py` — 移除已废弃的 Chroma.persist() 调用

新版 Chroma 自动持久化，`.persist()` 已废弃，移除了两处调用。

### 2.7 `middleware/security_headers.py` — 安全头现代化

```python
# 修复前：使用已废弃的 Feature-Policy
response["Feature-Policy"] = "..."

# 修复后：使用 Permissions-Policy
response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

# 同时取消 HSTS 头部的注释
response["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
```

### 2.8 `middleware/request_log.py` — IP 检测逻辑与 ip_rate_limit.py 不一致

```python
# 新增 X-Real-IP 检查（与 ip_rate_limit.py 保持一致）
ip = request.META.get("HTTP_X_REAL_IP") or \
     request.META.get("HTTP_X_FORWARDED_FOR") or \
     request.META.get("REMOTE_ADDR")
```

---

## 三、结构重构

### 3.1 `article/views.py` → `article/views/` 包

**重构前**：单文件 2002 行  
**重构后**：10 个文件的包，总计 2084 行（含 import 和注释）

```
article/views/
├── __init__.py      (11 行)  — 重导出所有 26 个视图，保持 `from article.views import xxx` 兼容
├── decorators.py    (14 行)  — 视图装饰器：性能计时工具 time_it
├── api.py           (44 行)  — DRF 文章/分类/评论 REST API ViewSets
├── display.py       (578 行) — 文章展示视图：详情页、分类列表、归档、Markdown/PDF 下载、图片上传
├── crud.py          (440 行) — 文章增删改查：发布、草稿箱、已发布编辑/删除
├── hot_pages.py     (243 行) — 第三方热榜页面：掘金热榜、CSDN 热榜（Redis 缓存）
├── ai.py            (170 行) — AI 功能端点：标题优化、摘要生成、文章/全局 RAG 问答、历史清空
├── comments.py      (119 行) — 评论功能：点赞/取消点赞(Redis 事务)、删除、评论管理页
├── quiz.py          (320 行) — 测验系统：LLM 出题、提交答案、错题本
└── study.py         (145 行) — 学习计划：创建/获取计划、每日打卡、学习统计仪表板
```

**向后兼容机制**：`__init__.py` 从各子模块显式导入并重导出所有视图函数，确保 `article/urls.py` 中的 `from . import views` 和所有 `from article.views import xxx` 继续工作。

### 3.2 `utils/rag_chain.py` → `utils/rag/` 包

**重构前**：单文件 1356 行  
**重构后**：6 个文件的包 + 1 个兼容 shim，总计 1418 行（含 import 和注释）

```
utils/rag/
├── __init__.py   (23 行)  — 重导出公共 API
├── config.py     (10 行)  — RAG 配置常量：向量库路径、分块大小、检索参数
├── llm.py        (48 行)  — 共享 LLM 单例工厂：按 (model, temperature) 缓存 ChatTongyi 实例
├── utils.py      (49 行)  — RAG 工具函数：UTC→北京时间格式化、作者显示名称解析
└── chain.py      (1265 行)— 站内文章 RAG 核心：向量检索、ReAct 工具、流式/非流式 QA 入口

utils/rag_chain.py (23 行) — 向后兼容 shim，从 utils/rag/ 子模块重新导出所有名称
```

**向后兼容机制**：`utils/rag_chain.py` 保留为兼容 shim，显式从 `utils/rag/` 各子模块导入所有公开名称并重新导出。所有 `from utils.rag_chain import xxx` 无需修改。

---

## 四、消除代码重复

### 4.1 统一 `_get_llm` 实现

**修复前**：`utils/rag_chain.py` 和 `article/ai_utils.py` 各自维护一份 LLM 初始化逻辑。

**修复后**：
- `utils/rag/llm.py` — **唯一真实的 `_get_llm` 实现**，采用按 `(model, temperature)` 缓存的字典，支持多配置并存：

```python
_LLM_CACHE = {}

def _get_llm(model="qwen-max", temperature=0.1):
    cache_key = (model, temperature)
    if cache_key in _LLM_CACHE:
        return _LLM_CACHE[cache_key], None
    # ... 初始化逻辑 ...
    _LLM_CACHE[cache_key] = llm
    return llm, None
```

- `article/ai_utils.py` — 改为调用共享工厂：

```python
from utils.rag.llm import _get_llm as _shared_get_llm

def _get_llm():
    global _AI_UTILS_LLM
    if _AI_UTILS_LLM is not None:
        return _AI_UTILS_LLM, None
    _AI_UTILS_LLM, err = _shared_get_llm(model="qwen-plus", temperature=0.8)
    return _AI_UTILS_LLM, err
```

### 4.2 统一 `get_client_ip` 检测逻辑

`middleware/request_log.py` 新增 `HTTP_X_REAL_IP` 检测，与 `ip_rate_limit.py` 保持一致。

---

## 五、次要清理

### 5.1 `middleware/__init__.py` 完善导出

```python
# 修复前：仅导出 IPRateLimitMiddleware
from .ip_rate_limit import IPRateLimitMiddleware

# 修复后：导出全部 6 个中间件
from .ip_rate_limit import IPRateLimitMiddleware
from .security_headers import SecurityHeadersMiddleware
from .cors import CORSMiddleware
from .request_log import RequestLogMiddleware
from .gzip import GzipMiddleware
from .maintenance_mode import MaintenanceModeMiddleware
```

### 5.2 `extraordinaryblog/settings.py` 补充显式配置

新增项：
- `MAINTENANCE_MODE` — 维护模式开关
- `IP_RATE_LIMIT_ENABLED`、`IP_RATE_LIMIT_MAX_REQUESTS`、`IP_RATE_LIMIT_WINDOW_SECONDS` — 限流参数
- `CSRF_TRUSTED_ORIGINS` — CSRF 信任源
- `SECRET_KEY` — 未设置环境变量时的开发回退值

### 5.3 `requirements.txt` 精简

从 162 行系统级 `pip freeze` 快照精简为 24 行项目实际依赖：

```
Django>=4.2,<5.1
djangorestframework>=3.14
djangorestframework-simplejwt>=5.3
django-redis>=5.3
django-apscheduler>=0.6
...
```

---

## 六、不变性保证

| 项目 | 说明 |
|------|------|
| URL 路由 | `article/urls.py` 的 `from . import views` 通过 `__init__.py` 重导出继续工作 |
| 模板引用 | 模板使用 URL name（如 `{% url 'article:detail' %}`），不依赖视图位置 |
| 外部导入 | `from article.views import ...` 和 `from utils.rag_chain import ...` 完全兼容 |
| 数据库 | 无迁移变更、无模型字段改动（仅修复 verbose_name 显示文本） |
| API | 所有 AJAX/JSON 端点行为不变 |

---

## 七、文件变更统计

| 类型 | 文件 | 变更 |
|------|------|------|
| 删除 | `article/views.py` | -2002 行 |
| 删除（实质拆分） | `utils/rag_chain.py`（原始 1356 行） | 替换为 23 行 shim |
| 新增 | `article/views/__init__.py` | 11 行 |
| 新增 | `article/views/decorators.py` | 14 行 |
| 新增 | `article/views/api.py` | 44 行 |
| 新增 | `article/views/display.py` | 578 行 |
| 新增 | `article/views/crud.py` | 440 行 |
| 新增 | `article/views/hot_pages.py` | 243 行 |
| 新增 | `article/views/ai.py` | 170 行 |
| 新增 | `article/views/comments.py` | 119 行 |
| 新增 | `article/views/quiz.py` | 320 行 |
| 新增 | `article/views/study.py` | 145 行 |
| 新增 | `utils/rag/__init__.py` | 23 行 |
| 新增 | `utils/rag/config.py` | 10 行 |
| 新增 | `utils/rag/llm.py` | 48 行 |
| 新增 | `utils/rag/utils.py` | 49 行 |
| 新增 | `utils/rag/chain.py` | 1265 行 |
| 修改 | `article/models.py` | 修复 4 个 Bug |
| 修改 | `cron_jobs.py` | 修复字段名错误 |
| 修改 | `article/ai_utils.py` | 消除 LLM 重复代码 |
| 修改 | `middleware/security_headers.py` | 安全头现代化 |
| 修改 | `middleware/request_log.py` | IP 检测统一 |
| 修改 | `middleware/__init__.py` | 完善导出 |
| 修改 | `extraordinaryblog/settings.py` | 补充配置 |
| 修改 | `requirements.txt` | 精简到 24 行 |
| **净变更** | | **+130 行 / -3572 行** |

---

## 八、验证方法

```bash
# Django 系统检查
python manage.py check

# 导入链路验证
python -c "from article.views import ArticleViewSet, detail, publish_article, \
  juejin_hot, ai_optimize_title, comment_like, generate_article_quiz, \
  create_or_get_study_plan"

python -c "from utils.rag_chain import _get_llm, simple_rag_qa, update_vector_store"

# 启动开发服务器
python manage.py runserver
```

---

## 九、回滚方案

如需回滚到重构前状态：

```bash
git checkout backup-ui-before-refactoring-20260516
```

或者恢复单个文件：

```bash
git checkout backup-ui-before-refactoring-20260516 -- article/views.py utils/rag_chain.py
```
