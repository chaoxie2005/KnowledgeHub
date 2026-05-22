# AI 文章音频化（TTS）功能文档

## 概述

为"知文汇"博客平台增加 AI 语音朗读功能。用户点击文章详情页的"听文章"按钮，系统调用阿里云 DashScope CosyVoice 大模型将 Markdown 文章内容转为 MP3 音频，页面右下角弹出浮动播放器直接播放。

## 技术架构

```
用户点击"听文章"
    │
    ▼
前端 JS (fetch POST)
    │
    ▼
POST /article/ai/generate-audio/<article_id>/
    │ @login_required
    ▼
generate_article_audio_view()
    │
    ├── 内容未变 + 文件存在 → 直接返回已有 audio_url (缓存命中)
    │
    └── 需生成
        │
        ▼
    generate_article_audio(content)
        ├── _strip_markdown_to_plain_text()   Markdown → 纯文本
        ├── _chunk_text()                     按段落分块 (每块 ≤1500字)
        ├── _synthesize_single_chunk()        DashScope CosyVoice v2
        └── pydub 拼接多块 MP3
            │
            ▼
    ContentFile 保存到 Article.audio_file
    save(update_fields=[...])
            │
            ▼
    返回 JSON { success: true, audio_url: "/media/article/audio/article_X.mp3" }
```

## 涉及文件

| 文件 | 说明 |
|------|------|
| `article/models.py` | Article 模型新增 `audio_file`、`audio_generated`、`audio_content_hash` 字段 |
| `article/tts_utils.py` | TTS 核心工具模块（新建） |
| `article/views/ai.py` | `generate_article_audio_view` 视图端点 |
| `article/views/display.py` | 缓存数据字典增加音频字段透传 |
| `article/urls.py` | 路由 `ai/generate-audio/<int:article_id>/` |
| `article/views/__init__.py` | 导出新视图 |
| `templates/article/article_detail.html` | 前端 UI（按钮 + 浮动播放器 + JS） |

## 模型字段

Article 模型新增三个字段（`article/models.py`）：

```python
audio_file = models.FileField(
    upload_to="article/audio/", blank=True, null=True, verbose_name="文章音频"
)
audio_generated = models.BooleanField(default=False, verbose_name="音频已生成")
audio_content_hash = models.CharField(
    max_length=64, blank=True, default="", verbose_name="音频内容哈希"
)
```

- `audio_file`：MP3 文件，存储在 `media/article/audio/`
- `audio_generated`：标记是否已生成过音频
- `audio_content_hash`：文章内容 SHA256，用于检测内容变更

## API 端点

### 生成文章音频

```
POST /article/ai/generate-audio/<article_id>/
```

**鉴权**：需要登录（`@login_required`），未登录返回 302 重定向到登录页。

**请求体**：空 JSON `{}` 即可。

**成功响应**：
```json
{
    "success": true,
    "audio_url": "/media/article/audio/article_102.mp3",
    "message": "音频生成成功",
    "cached": false
}
```

**缓存命中**（内容未变更）：
```json
{
    "success": true,
    "audio_url": "/media/article/audio/article_102.mp3",
    "message": "音频已存在且内容未变更",
    "cached": true
}
```

**失败响应**：
```json
{
    "success": false,
    "error": "音频生成失败，请稍后重试"
}
```

## TTS 引擎配置

使用 **DashScope CosyVoice v2**（阿里云通义千问语音合成）：

| 参数 | 值 | 说明 |
|------|------|------|
| 模型 | `cosyvoice-v1` | 可通过环境变量 `DASHSCOPE_TTS_MODEL` 覆盖 |
| 语音 | `longxiaochun` | 可通过环境变量 `DASHSCOPE_TTS_VOICE` 覆盖 |
| 格式 | MP3 48000Hz Mono 256kbps | `AudioFormat.MP3_48000HZ_MONO_256KBPS` |
| 分块大小 | 1500 字符/块 | 可通过环境变量 `TTS_MAX_CHUNK_CHARS` 调整 |
| API Key | `DASHSCOPE_API_KEY` 或 `QWEN_API_KEY` | 从 `.env` 读取 |

### 环境变量

```bash
# 必需
DASHSCOPE_API_KEY=your_key_here

# 可选
DASHSCOPE_TTS_MODEL=cosyvoice-v1       # TTS 模型
DASHSCOPE_TTS_VOICE=longxiaochun       # 语音角色
TTS_MAX_CHUNK_CHARS=1500               # 单次合成最大字符数
```

## 前端交互

### 听文章按钮

- 位置：文章详情页操作栏，导出 Markdown 和导出 PDF 按钮旁边
- 样式：绿色渐变（`#11998e → #38ef7d`），与紫色/粉色下载按钮风格统一
- 图标：SVG 喇叭 + 声波图标
- 三态：听文章 → 生成中（旋转动画）→ 重新生成

### 浮动播放器

- 定位：`position: fixed`，右下角，`z-index: 1050`
- 收起态：48px 绿色圆形浮动按钮（FAB），脉冲动画提示
- 展开态：320px 宽度卡片，包含文章标题、HTML5 `<audio>` 控件、关闭按钮
- 拖拽：按住标题栏可拖拽到屏幕任意位置
- 暗黑主题：完整适配（深绿背景 + audio 控件反色）

## 缓存策略

采用 **三层缓存** 保证效率：

1. **文件缓存**：MP3 持久化存储在 `media/article/audio/`，Nginx 直接 serve，不经过 Django
2. **哈希检测**：对比 `audio_content_hash` 与当前 `article.content` 的 SHA256，内容未变则直接返回已有 URL
3. **Redis 页面缓存**：`display.py` 的 `_build_article_cache_data()` 将 `audio_file` 和 `audio_generated` 纳入文章详情页缓存字典

## 错误处理

| 场景 | 前端表现 | 后端行为 |
|------|----------|----------|
| 未登录 | — | 302 重定向到登录页 |
| API Key 未配置 | "请配置 DASHSCOPE_API_KEY" | 返回 error JSON |
| 文章不存在/未发布 | — | 404 |
| TTS API 调用失败 | "生成失败" + 3秒后恢复按钮 | logging 记录 + 返回 error JSON |
| 网络错误 | "网络错误，请稍后重试" | — |
| 内容为空 | "生成失败" | 返回 None，不上传文件 |

## 系统依赖

```bash
# Python 包
pip install dashscope pydub

# 系统依赖（pydub MP3 拼接需要）
sudo apt install ffmpeg
```

## 使用示例

### 命令行测试

```python
python manage.py shell

from article.tts_utils import generate_article_audio
from article.models import Article

article = Article.objects.get(id=102, status="published")
audio_bytes = generate_article_audio(article.content)
with open("test.mp3", "wb") as f:
    f.write(audio_bytes)
```

### cURL 测试

```bash
# 需要先获取 CSRF token 和 session cookie
curl -X POST http://localhost:8000/article/ai/generate-audio/102/ \
  -H "X-CSRFToken: <token>" \
  -H "Cookie: sessionid=<sessionid>" \
  -H "Content-Type: application/json" \
  -d '{}'
```

## 未来可扩展方向

- **自动生成**：发布文章时自动异步生成音频（Celery 任务）
- **多语音选择**：支持多种音色（男声/女声/童声等）切换
- **语速控制**：播放器增加 0.75x / 1x / 1.5x / 2x 变速
- **音频下载**：增加"下载 MP3"按钮，离线收听
- **播放列表**：连续播放多篇文章
- **进度同步**：记录播放进度，下次打开继续播放
