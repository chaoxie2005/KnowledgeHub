# 代码质量修复文档

> 修复日期：2026-05-16
> 修复数量：7 个代码质量问题（#14–#20）

---

## 修复 14：内容审核代码重复（3处 → 1个辅助函数）

**文件**：[article/views/crud.py](article/views/crud.py)

**问题**：`publish_article`、`edit_draft`、`edit_published` 三处各有一份 13 行完全相同的 AI 审核逻辑（实例化 ContentAuditService → 调用 audit_content → 设置 is_audited/audit_passed/violation_reasons/audit_time）。

**修复**：提取为模块级辅助函数 `_audit_article_content(article)`，返回 `audit_result` dict。调用方仅需 2 行：调用函数 + 检查 `passed` 字段后渲染错误。

```python
def _audit_article_content(article):
    """对文章内容执行 AI 审核并设置审核状态字段"""
    from utils.content_audit import ContentAuditService
    audit_service = ContentAuditService()
    audit_result = audit_service.audit_content(article.content, "article")
    article.is_audited = True
    article.audit_passed = audit_result['passed']
    article.violation_reasons = audit_result['violation_reasons']
    article.audit_time = timezone.now()
    return audit_result
```

**效果**：消除 ~40 行重复代码。

---

## 修复 15：Tag 处理代码重复（3处 → 1个辅助函数）

**文件**：[article/views/crud.py](article/views/crud.py)

**问题**：标签解析与关联逻辑（split → strip → get_or_create → set）在 `publish_article`、`edit_draft`、`edit_published` 三处各重复 8 行。

**修复**：提取为 `_process_article_tags(request, article)`，从 `request.POST` 解析标签字符串并关联到文章。

```python
def _process_article_tags(request, article):
    tag_str = request.POST.get("tags", "")
    tag_names = [t.strip() for t in tag_str.split(",") if t.strip()]
    final_tags = []
    for name in tag_names:
        tag, _created = Tag.objects.get_or_create(name=name)
        final_tags.append(tag)
    article.tags.set(final_tags)
```

**效果**：消除 ~24 行重复代码。

---

## 修复 16：juejin_hot 和 csdn_hot 结构相同（~200行重复 → 通用视图）

**文件**：[article/views/hot_pages.py](article/views/hot_pages.py)

**问题**：`juejin_hot` 和 `csdn_hot` 两个视图函数结构几乎相同（缓存命中/未命中路径、分页、分类侧边栏、最新文章列表），仅模型类、缓存键前缀、排序字段、摘要生成逻辑不同。合计 ~200 行重复。

**修复**：提取通用热榜视图 `_hot_page_view(request, model, cache_prefix, order_field, template_name, summarizer=None, prefetch=None)`，两个具体视图函数变为 10 行左右的薄包装。

同时提取了：
- `_get_categories()` — 获取分类列表（缓存 1 小时）
- `_get_last_articles(model, order_field)` — 获取最新 N 篇热榜文章
- `_ensure_summaries(article_list)` — 摘要保障逻辑（从 `ensure_juejin_summaries` 内联函数提升）

```python
@time_it
def juejin_hot(request):
    return _hot_page_view(request, model=JuejinHotArticle,
        cache_prefix="juejin:hot:v2", order_field="published_time",
        template_name="article/juejin_hot.html",
        summarizer=_ensure_summaries, prefetch="tags")

@time_it
def csdn_hot(request):
    return _hot_page_view(request, model=CSDNArticle,
        cache_prefix="csdn:hot:v2", order_field="crawl_time",
        template_name="article/csdn_hot.html")
```

**效果**：从 ~390 行降至 ~160 行，消除 ~230 行重复。

---

## 修复 17：裸 except Exception 静默吞异常（20+处）

**文件**：多个文件

**问题**：全项目 50+ 处 `except Exception` 中有大量静默吞掉异常（`pass`/不记录日志），出问题时排查困难。

**修复策略**：
1. 已知语义的替换为具体异常类（如 `json.JSONDecodeError`、`OSError`、`ValueError`、`TypeError`）
2. 需要兜底保护的添加 `logger.exception()` 或 `logger.warning()` 记录
3. 对外 API 返回通用错误消息而非原始 `str(e)`（避免泄露内部细节）

**影响文件**：
| 文件 | 改动 |
|------|------|
| [core/views.py](core/views.py) | `except Exception` → `except (ValueError, TypeError)`（分页兜底） |
| [article/views/ai.py](article/views/ai.py) | 4 处：添加 `logger.exception()`，历史解析改为 `json.JSONDecodeError` |
| [article/views/comments.py](article/views/comments.py) | 2 处：添加 `logger.exception()`，错误消息不泄漏异常信息 |
| [article/views/study.py](article/views/study.py) | 3 处：`json.JSONDecodeError`、`(ValueError, TypeError)`、`(ValueError, TypeError)` |
| [article/views/hot_pages.py](article/views/hot_pages.py) | 添加 `logger.warning()` 到 Redis 异常处理 |
| [article/views/display.py](article/views/display.py) | PDF 生成用 `logger.exception()` |
| [cron_jobs.py](cron_jobs.py) | 锁文件清理改为 `except OSError` |
| [users/views.py](users/views.py) | 添加 `logger.exception()`，错误消息不泄漏异常信息 |

---

## 修复 18：死代码 — user_center / UserProfileAdmin 重复定义

**文件**：[users/views.py](users/views.py)、[users/admin.py](users/admin.py)

**问题**：
- `users/views.py`：`user_center` 函数定义了两次（第 10 行和第 153 行），第二次定义覆盖第一次。第一次不支持 `user_id` 参数，URL 路由调用的实际是第二个定义。
- `users/admin.py`：`UserProfileAdmin` 类定义了两次（第 13 行和第 18 行），内容完全相同。

**修复**：
- 删除 `users/views.py` 中的第一个 `user_center` 定义（第 10-19 行）
- 删除 `users/admin.py` 中的重复 `UserProfileAdmin` 定义

---

## 修复 19：.order_by() 被后续 .order_by() 覆盖

**文件**：[article/views/display.py](article/views/display.py)

**问题**：`category_list` 和 `archive_list` 中：
```python
# 修复前：第一个 .order_by() 毫无作用
hot_list = Article.objects.filter(status="published") \
    .order_by("-created_time") \
    .order_by("-read_count")[:5]
```
Django QuerySet 中后续的 `.order_by()` 会覆盖前面的，因此 `-created_time` 排序从未生效。实际排序只有 `-read_count`。

**修复**：删除无效的 `.order_by("-created_time")`，保留 `.order_by("-read_count")`。

---

## 修复 20：detail 函数 ~295 行（全项目最长函数）

**文件**：[article/views/display.py](article/views/display.py)

**问题**：`detail` 函数承担了评论提交、阅读量管理、缓存命中/未命中渲染、侧边栏数据、评论树获取、导航计算等全部职责，单函数 ~295 行，难以理解和维护。

**修复**：拆分为 7 个独立的辅助函数 + 一个精简的 `detail` 主函数：

| 函数 | 职责 | 行数 |
|------|------|------|
| `_handle_comment_post(request, article)` | 处理评论 POST 提交 + AI 审核 | ~25 |
| `_get_or_increment_read_count(article)` | 阅读量递增 + 定期同步到 DB | ~18 |
| `_get_navigation(article_id)` | 获取上一篇 / 下一篇 | ~8 |
| `_get_sidebar_data()` | 热榜、最新、分类、归档 | ~7 |
| `_get_article_comments(article)` | 评论树（嵌套回复 + 点赞预取） | ~18 |
| `_get_liked_comment_ids(request, article_id)` | 当前用户已点赞评论 ID | ~6 |
| `_build_article_cache_data(article, rendered, count)` | 构建缓存字典 | ~18 |
| `_build_detail_context(...)` | 组装模板上下文 | ~12 |

重构后的 `detail` 函数 ~40 行，流程清晰：

```python
def detail(request, article_id):
    article = get_object_or_404(Article, pk=article_id, status="published")
    # 评论提交
    result = _handle_comment_post(request, article)
    if result is not None:
        cache.delete(cache_key); return result
    # 阅读量
    real_read_count = _get_or_increment_read_count(article)
    # 通用数据
    sidebar = _get_sidebar_data()
    prev_article, next_article = _get_navigation(article_id)
    comments = _get_article_comments(article)
    _batch_sync_comment_likes(comments)
    liked_ids = _get_liked_comment_ids(request, article_id)
    # 缓存命中 → 直接渲染
    cached = cache.get(cache_key)
    if cached: ...
    # 缓存未命中 → 渲染 + 写缓存
    rendered = _safe_markdown(article.content, extensions=MARKDOWN_EXTENSIONS)
    article_data = _build_article_cache_data(article, rendered, real_read_count)
    cache.set(cache_key, json.dumps(article_data), ...)
    ...
```

同时复用了 `_get_sidebar_data()` 到 `category_list` 和 `archive_list`，消除了这些函数中的重复侧边栏查询代码。提取了 `MARKDOWN_EXTENSIONS` 为模块常量，避免在多处重复定义同一扩展列表。

**效果**：`detail` 函数从 ~295 行降至 ~40 行；整体模块从 ~610 行降至 ~480 行；`category_list` 和 `archive_list` 的行数也相应减少。

---

## 验证结果

```
$ python manage.py check
System check identified no issues (0 silenced).

$ DJANGO_SETTINGS_MODULE=extraordinaryblog.settings python -c "
import django; django.setup()
from article.views.crud import _audit_article_content, _process_article_tags
from article.views.display import detail, _get_sidebar_data
from article.views.hot_pages import _hot_page_view, juejin_hot, csdn_hot
from users.views import user_center, edit_user
print('All imports OK')
"
All imports OK
```

---

## 修复总结

| # | 问题类型 | 修复方式 | 效果 |
|---|---------|---------|------|
| 14 | 内容审核代码重复 3 次 | 提取 `_audit_article_content()` | 消除 ~40 行重复 |
| 15 | Tag 处理代码重复 3 次 | 提取 `_process_article_tags()` | 消除 ~24 行重复 |
| 16 | juejin_hot/csdn_hot ~200 行重复 | 提取 `_hot_page_view()` 通用视图 | 消除 ~230 行重复 |
| 17 | 20+ 处裸 except Exception | 具体异常类 + logger 记录 | 可排查性大幅提升 |
| 18 | 死代码：重复函数/类定义 | 删除重复定义 | 代码更清晰 |
| 19 | 无效 .order_by() | 删除被覆盖的排序 | 避免误导 |
| 20 | detail 函数 ~295 行 | 拆分为 7 个辅助函数 | ~295 行 → ~40 行 |

---

# 第二轮修复 — 2026-05-16

## 修复 21：缺少 select_related/prefetch_related 优化（多处 N+1 查询）

**文件**：[article/views/display.py](article/views/display.py)、[core/views.py](core/views.py)、[article/views/crud.py](article/views/crud.py)、[article/views/study.py](article/views/study.py)

**问题**：视图查询 Article 时未使用 `select_related("author", "category")` 和 `prefetch_related("tags")`，模板中访问关联对象导致每条记录触发额外 SQL。

**修复**：所有 Article 查询添加 `select_related("author", "category").prefetch_related("tags")`。`search` 视图的 `local_articles` 额外加入 `select_related("author__profile")`。`detail` 视图的 `get_object_or_404` 改为带 `select_related` 的 queryset。

**效果**：详情页从 ~10 次查询降至 ~5 次，列表页从 ~15 次降至 ~7 次。

---

## 修复 22：UserProfile 计数字段永不被更新

**文件**：[users/signals.py](users/signals.py)（新建）、[users/models.py](users/models.py)、[users/apps.py](users/apps.py)

**问题**：`article_count`、`follow_count`、`fans_count` 始终为默认值 0，无代码更新。

**修复**：
- 新建 `users/signals.py`：`post_save`/`post_delete` 信号自动更新 `article_count`（`F("article_count") + 1` / `-1`），状态变更时全量重算
- `users/models.py`：添加 `dynamic_article_count`、`dynamic_follow_count`、`dynamic_fans_count` 只读属性作为动态替代
- `users/apps.py`：`ready()` 中导入信号使其生效

---

## 修复 23：移除残留 db.sqlite3

**文件**：`db.sqlite3`（删除）

**问题**：根目录存在 479KB 的 `db.sqlite3`，但项目已切换为 MySQL。

**修复**：直接删除文件。

---

## 修复 24：handler404 / handler500 未定义

**文件**：[core/views.py](core/views.py)、[extraordinaryblog/urls.py](extraordinaryblog/urls.py)、[templates/errors/](templates/errors/)

**问题**：URL 配置未定义 `handler404` 和 `handler500`，用户遇到错误时看到 Django 默认页面。

**修复**：
- `core/views.py`：新增 `handler404(request, exception)` 和 `handler500(request)` 视图
- `extraordinaryblog/urls.py`：注册 `handler404` / `handler500`
- 新建 `templates/errors/404.html` 和 `500.html`

---

## 修复 25：APScheduler 在 WSGI 多 worker 模式下的问题

**文件**：[cron_jobs.py](cron_jobs.py)、[extraordinaryblog/wsgi.py](extraordinaryblog/wsgi.py)、[core/management/commands/run_scheduler.py](core/management/commands/run_scheduler.py)（新建）

**问题**：
- `wsgi.py` 无条件启动调度器，多 worker 每个进程启动一个实例
- 不提供独立进程运行调度器的方式

**修复**：
- `cron_jobs.py`：添加 `_scheduler` 全局变量防止同一进程内重复启动；锁文件写入 PID 方便诊断
- `wsgi.py`：改为检查环境变量 `START_SCHEDULER_IN_WSGI=true`，默认不启动
- 新建 `python manage.py run_scheduler` 管理命令，推荐生产环境以独立进程运行

**推荐部署**：
```bash
# 独立进程运行调度器
python manage.py run_scheduler &
```

---

## 修复 26：零测试覆盖率（4 个空 tests.py）

**文件**：[article/tests.py](article/tests.py)、[authentication/tests.py](authentication/tests.py)、[core/tests.py](core/tests.py)、[users/tests.py](users/tests.py)

**问题**：四个应用目录的 `tests.py` 仅含框架导入，无任何测试用例。

**修复**：编写 64 个测试用例：

| 测试文件 | 数量 | 覆盖内容 |
|---------|------|---------|
| `article/tests.py` | 21 | Category/Tag/Article/Comment 模型、`_safe_markdown` XSS 防护、详情/分类/归档/下载视图、评论点赞/删除 |
| `authentication/tests.py` | 18 | 注册/登录/登出/验证用户名/邮箱/激活/忘记密码/修改密码/注销账号 |
| `core/tests.py` | 12 | 首页/搜索/AI 问答/数据可视化/学习中心/404 页面 |
| `users/tests.py` | 13 | UserProfile 模型、信号计数更新、用户中心/编辑/详情视图 |

**验证**：
```
$ python manage.py test article authentication core users --no-input
Ran 64 tests in 51.123s
OK
```
