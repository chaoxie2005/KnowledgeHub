# 知文汇安全漏洞修复文档

> 修复日期：2026-05-16  
> 修复数量：8 个安全问题

---

## 修复 1：XSS 跨站脚本注入（Critical）

**文件**：[article/views/display.py](article/views/display.py)

**问题**：用户提交的 Markdown 内容通过 `markdown.markdown()` 渲染后直接用 `|safe` 输出到模板。Python `markdown` 库默认允许原始 HTML 通过，攻击者可在文章中嵌入 `<script>alert('xss')</script>` 等恶意代码。

**修复方案**：
1. 引入 `bleach` 库（已在环境中 `6.3.0` 版本）
2. 在 display.py 新增 `_safe_markdown()` 函数，HTML 白名单化处理：

```python
_ALLOWED_TAGS = [
    "h1","h2","h3","h4","h5","h6","p","br","hr","a","img",
    "ul","ol","li","blockquote","pre","code","em","strong","del",
    "table","thead","tbody","tr","th","td","caption","colgroup","col",
    "span","div","dl","dt","dd","sup","sub","details","summary",
]
_ALLOWED_ATTRS = {
    "a": ["href","title","name"],
    "img": ["src","alt","title","width","height"],
    "th": ["align"], "td": ["align"],
    "col": ["width"], "colgroup": ["width"],
}
_ALLOWED_PROTOCOLS = ["http","https","mailto","ftp"]

def _safe_markdown(content, extensions=None):
    html = markdown.markdown(content, extensions=extensions or [])
    return bleach.clean(html, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, protocols=_ALLOWED_PROTOCOLS, strip=True)
```

3. 将 4 处 `markdown.markdown()` 调用全部替换为 `_safe_markdown()`

**防御效果**：所有 `<script>`、`onerror=`、`onclick=` 等事件处理属性、未知标签被自动删除。

---

## 修复 2：Debug Toolbar 暴露公网（Critical）

**文件**：
- [extraordinaryblog/settings.py](extraordinaryblog/settings.py#L19-L21)
- [extraordinaryblog/urls.py](extraordinaryblog/urls.py#L20)

**问题**：
- `INTERNAL_IPS` 包含公网 IP ，允许远程访问 Debug Toolbar
- `debug_toolbar` 中间件和 `__debug__/` URL 无条件加载，不检测 DEBUG 状态

**修复方案**：

settings.py：
```python


# 中间件改为按 DEBUG 条件加载
*(["debug_toolbar.middleware.DebugToolbarMiddleware"] if DEBUG else []),

# INSTALLED_APPS 同理
*(["debug_toolbar"] if DEBUG else []),
```

urls.py：
```python
# 修复前
path("__debug__/", include("debug_toolbar.urls")),

# 修复后
*([path("__debug__/", include("debug_toolbar.urls"))] if settings.DEBUG else []),
```

**防御效果**：`DEBUG=False` 时 Debug Toolbar 完全不加载，无法通过任何方式访问 SQL 查询面板。

---

## 修复 3：邮箱 SSL 证书验证禁用（Critical）

**文件**：[extraordinaryblog/email_backend.py](extraordinaryblog/email_backend.py)

**问题**：自定义邮件后端禁用了全部 SSL 证书验证：
```python
self.ssl_context.check_hostname = False
self.ssl_context.verify_mode = ssl.CERT_NONE
self.ssl_context.set_ciphers("ALL:@SECLEVEL=1")
```

这导致密码重置邮件在传输过程中可以被中间人攻击窃取。

**修复方案**：移除所有自定义 SSL 上下文配置，使用 `ssl.create_default_context()` 的默认安全设置：

```python
class CustomEmailBackend(SMTPEmailBackend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ssl_context = ssl.create_default_context()
```

**防御效果**：恢复标准的 SSL 证书验证和主机名校验。

---

## 修复 4：内容审核"失效即放行"（Critical）

**文件**：[utils/content_audit.py](utils/content_audit.py)

**问题**：当 LLM 服务不可用或调用失败时，审核返回 `passed=True`，有害内容可以绕过审核直接发布。

```python
# 修复前：LLM 失败 → 放行
return {"passed": True, "risk_level": "low", ...}
```

**修复方案**：改为"失效即拒绝"策略（fail-closed），安全优先：

```python
# 修复后：LLM 失败 → 拒绝并建议人工审核
if not self.llm:
    logger.warning("大模型未初始化，内容审核拒绝通过，建议人工审核")
    return {
        "passed": False,
        "risk_level": "medium",
        "violation_reasons": ["AI审核服务不可用"],
        "suggestion": "AI审核不可用，请人工审核后再发布"
    }
```

LLM 调用异常同理，返回 `passed=False`。

**防御效果**：AI 审核服务故障时，内容全部拦截等待人工审核，不会被自动放行。

---

## 修复 5：Cookie 安全标记缺失（High）

**文件**：[extraordinaryblog/settings.py](extraordinaryblog/settings.py)

**问题**：`SESSION_COOKIE_SECURE`、`CSRF_COOKIE_SECURE`、`SESSION_COOKIE_SAMESITE` 全部未设置，导致：
- Cookie 可通过 HTTP 明文传输
- 无法防御 CSRF 跨站请求伪造

**修复方案**：

```python
# 新增项
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG        # 生产强制 HTTPS
CSRF_COOKIE_SECURE = not DEBUG           # 生产强制 HTTPS
CSRF_COOKIE_HTTPONLY = True              # JS 不可读
```

设计考量：开发环境（`DEBUG=True`）使用 HTTP 本地测试，故 `SECURE` 标记在开发期关闭。

**防御效果**：生产环境 Cookie 仅通过 HTTPS 传输，SameSite=Lax 防止跨站请求携带 Cookie。

---

## 修复 6：密码重置 Token 复用（Medium）

**文件**：[authentication/views.py](authentication/views.py#L206-L234)

**问题**：密码重置 Token 在用户成功重置后没有显式失效机制。虽然 `default_token_generator` 依赖用户密码哈希（修改密码后旧 Token 自动失效），但在密码修改的 GET→POST 窗口期内 Token 可被复用。

**修复方案**：在 Redis 缓存中记录已使用的 Token：

```python
# 检查 token 是否已被使用
token_used_key = f"pwd_reset_used:{pk}:{token}"
if cache.get(token_used_key):
    return HttpResponseBadRequest("Token 已被使用，请重新申请找回密码")

# 密码修改成功后，标记为已使用（7天有效期）
cache.set(token_used_key, True, timeout=86400 * 7)
```

**防御效果**：每个密码重置链接只能使用一次，用后即废。

---

## 修复 7：CORS 允许所有来源（Medium）

**文件**：[middleware/cors.py](middleware/cors.py)

**问题**：`Access-Control-Allow-Origin: *` 无条件允许任意网站发起跨域请求，可被恶意网站利用窃取用户数据。

**修复方案**：
1. 从环境变量 `CORS_ALLOWED_ORIGINS` 读取可信域名列表
2. 动态匹配请求的 `Origin` 头，不对直接返回
3. DEBUG 模式下保留宽松策略方便开发

```python
class CORSMiddleware:
    def __init__(self, get_response):
        ...
        raw = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")
        self.allowed_origins = [o.strip() for o in raw.split(",") if o.strip()]

    def __call__(self, request):
        ...
        origin = request.headers.get("Origin", "")
        if origin in self.allowed_origins:
            response['Access-Control-Allow-Origin'] = origin
        elif settings.DEBUG:
            response['Access-Control-Allow-Origin'] = '*'
        else:
            response['Access-Control-Allow-Origin'] = self.allowed_origins[0] if self.allowed_origins else ''

        response['Access-Control-Allow-Credentials'] = 'true'
```

生产环境需在 `.env` 中设置：
```
CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

---

## 修复 8：爬虫脚本明文 Cookie（Medium）

**文件**：
- [article/crawl_csdn.py](article/crawl_csdn.py#L49-L50)
- [article/crawl_juejin.py](article/crawl_juejin.py#L50-L51)

**问题**：CSDN 和掘金爬虫的认证 Cookie 以明文硬编码在代码中，包含 `UserName`、`UserToken`、`passport_csrf_token` 等敏感会话数据。代码一旦提交到 Git 仓库，Cookie 永久泄露。

**修复方案**：改为从环境变量读取：

```python
# 修复前
COOKIE_STRING = "uuid_tt_dd=10_28832...; fid=20_9172846...; ..."

# 修复后
from dotenv import load_dotenv
load_dotenv()
COOKIE_STRING = os.getenv("CSDN_COOKIE_STRING", "")
COOKIE_STRING = os.getenv("JUEJIN_COOKIE_STRING", "")
```

需在 `.env` 中添加：
```
CSDN_COOKIE_STRING=your_csdn_cookie_here
JUEJIN_COOKIE_STRING=your_juejin_cookie_here
```

> 注意：`.env` 文件已在 `.gitignore` 中，不会被提交到仓库。

---

## 验证结果

```
$ python manage.py check
System check identified no issues (0 silenced).

$ python -c "from article.views import ...; from utils.rag_chain import ...; from utils.content_audit import ..."
All imports OK
```

---

## .env 新增配置项

修复完成后，需在 `.env` 中添加以下配置：

```bash
# CORS 可信来源（生产环境替换为实际域名，逗号分隔）
CORS_ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000

# 爬虫 Cookie（用于 CSDN/掘金热榜爬取）
CSDN_COOKIE_STRING=
JUEJIN_COOKIE_STRING=
```
