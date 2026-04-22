import requests
import re
import json
import datetime
from django.utils import timezone
from django.db import IntegrityError
import sys
import os
import django
import random
import time

# 获取项目根目录并加入 sys.path，以便独立运行脚本时能找到 article 模块
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 在导入 Django 模型之前必须先配置环境并调用 setup()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "extraordinaryblog.settings")
django.setup()

from article.models import JuejinHotArticle

# 新增：导入AI工具函数
from article.ai_utils import generate_article_summary, optimize_article_title

"""爬取稀土掘金的掘金热榜（集成AI摘要和标题优化）"""

# 配置项
REQUEST_TIMEOUT = 10
MAX_ARTICLES_TO_CRAWL = 10

# User-Agent轮换池
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
]

def get_random_user_agent():
    """随机获取一个User-Agent"""
    return random.choice(USER_AGENTS)

# 代理配置（如果不需要代理，设置为 None）
# 格式：{'http': 'http://ip:port', 'https': 'http://ip:port'}
PROXIES = None

# Cookies配置（需要定期更新）
COOKIE_STRING = "_tea_utm_cache_2608=undefined; __tea_cookie_tokens_2608=%257B%2522web_id%2522%253A%25227495787047023838760%2522%252C%2522user_unique_id%2522%253A%25227495787047023838760%2522%252C%2522timestamp%2522%253A1745248943786%257D; odin_tt=21770152b6d9beb854a15f6dde529f856c0432ce11dbf716d87b2602d31e2a89831cb27d972acdafb39c49b3ed57050570b817a4fc667773a675a2619f4532e4; _ga=GA1.2.979893466.1772948845; _ga_S695FMNGPJ=GS2.2.s1772948845$o1$g0$t1772948845$j60$l0$h0; n_mh=QgN8ycIE1mLmvYammYTgizVxWH5yfUziwXl-3A2wvEY; passport_csrf_token=16d20439f043b6163720e4880f98fa7b; passport_csrf_token_default=16d20439f043b6163720e4880f98fa7b; passport_auth_status=3d27969088473f937793f3e1a6e43ddc%2C7c721dc747f905a0a97b14bd3b05ba75; passport_auth_status_ss=3d27969088473f937793f3e1a6e43ddc%2C7c721dc747f905a0a97b14bd3b05ba75; sid_guard=8858bd4ccfbe422b5b9bd44d42ef9437%7C1774586719%7C31536000%7CSat%2C+27-Mar-2027+04%3A45%3A19+GMT; uid_tt=4653e2ce00659599b1fdb08d67df4dbe; uid_tt_ss=4653e2ce00659599b1fdb08d67df4dbe; sid_tt=8858bd4ccfbe422b5b9bd44d42ef9437; sessionid=8858bd4ccfbe422b5b9bd44d42ef9437; sessionid_ss=8858bd4ccfbe422b5b9bd44d42ef9437; session_tlb_tag=sttt%7C10%7CiFi9TM--Qitbm9RNQu-UN__________UsDpqteQc1aMMnQMNt0hZMFuE9dH7bp_VT7coXs4Sl94%3D; is_staff_user=false; use_biz_token=true; sid_ucp_v1=1.0.0-KDU2NjA4MjM0NWZjYjAzYjFhZmYzM2I5NzcwZWYzMTViY2FhYWY5ZTIKFwjc6uGGra3KAxDflpjOBhiwFDgCQPEHGgJsZiIgODg1OGJkNGNjZmJlNDIyYjViOWJkNDRkNDJlZjk0Mzc; ssid_ucp_v1=1.0.0-KDU2NjA4MjM0NWZjYjAzYjFhZmYzM2I5NzcwZWYzMTViY2FhYWY5ZTIKFwjc6uGGra3KAxDflpjOBhiwFDgCQPEHGgJsZiIgODg1OGJkNGNjZmJlNDIyYjViOWJkNDRkNDJlZjk0Mzc; csrf_session_id=7b7e6247fdcd10998ec7cc3d292e378e"

def parse_cookies(cookie_string):
    """将Cookie字符串解析为字典"""
    cookies = {}
    if not cookie_string:
        return cookies
    for item in cookie_string.split(';'):
        item = item.strip()
        if '=' in item:
            key, value = item.split('=', 1)
            cookies[key.strip()] = value.strip()
    return cookies

def spider():
    """爬取掘金热榜接口数据"""
    cookies = parse_cookies(COOKIE_STRING)

    headers = {
        "accept": "*/*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "origin": "https://juejin.cn",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "referer": "https://juejin.cn/",
        "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": get_random_user_agent(),
    }

    params = {
        "category_id": "1",
        "type": "hot",
        "aid": "2608",
        "uuid": "7495787047023838760",
        "spider": "0",
    }

    try:
        response = requests.get(
            "https://api.juejin.cn/content_api/v1/content/article_rank",
            params=params,
            cookies=cookies,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            proxies=PROXIES,
        )
        response.raise_for_status()
        return response.json()["data"]
    except requests.exceptions.RequestException as e:
        print(f"请求掘金热榜接口失败: {e}")
        return []


def get_content(url):
    """获取文章详情页HTML"""
    time.sleep(random.uniform(5, 10))
    cookies = parse_cookies(COOKIE_STRING)

    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "priority": "u=0, i",
        "referer": "https://juejin.cn/hot/articles",
        "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": get_random_user_agent(),
    }

    try:
        response = requests.get(
            url, cookies=cookies, headers=headers, timeout=REQUEST_TIMEOUT, proxies=PROXIES
        )
        response.raise_for_status()
        if "Please wait..." in response.text or "访问过于频繁" in response.text:
            print(f"警告：被 WAF 拦截或访问频繁: {url}")
            return ""
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"获取文章详情失败 {url}: {e}")
        return ""


def parse_article_detail(html_content):
    """解析文章详情，返回结构化数据（适配新模型）"""
    result = {
        "title": "",
        "summary": "",
        "url": "",
        "author": "",
        "source": "",
        "published_time": None,
        "tags": [],
        "content": "",
    }

    pattern = r'<script.*?type="application/ld\+json".*?>([\s\S]*?)</script>'
    match = re.search(pattern, html_content)
    tags_match = re.search(
        r'<meta\s+itemprop="keywords".*?content="([^"]+)"[^>]*>', html_content
    )

    content_pattern = r'<div class="article-content"[\s\S]*?>([\s\S]*?)</div>'
    content_match = re.search(content_pattern, html_content)
    if content_match:
        content = re.sub(r"<[^>]+>", "", content_match.group(1))
        result["content"] = re.sub(r"\s+", " ", content).strip()

    if not match:
        print("未匹配到文章核心数据")
        return result

    try:
        json_str = match.group(1).strip()
        json_data = json.loads(json_str)[0]

        result["title"] = json_data.get("headline", "")
        result["summary"] = json_data.get("description", "")
        result["url"] = json_data.get("mainEntityOfPage", {}).get("@id", "")
        result["author"] = json_data.get("author", {}).get("name", "")
        result["source"] = json_data.get("publisher", {}).get("name", "")

        pub_time_str = json_data.get("datePublished", "")
        if pub_time_str:
            try:
                result["published_time"] = datetime.datetime.fromisoformat(
                    pub_time_str.replace("Z", "+00:00")
                )
            except ValueError as e:
                print(f"解析发布时间失败: {e}")
                result["published_time"] = timezone.now()

        if tags_match:
            tags_str = tags_match.group(1)
            result["tags"] = [tag.strip() for tag in tags_str.split(",") if tag.strip()]

    except json.JSONDecodeError as e:
        print(f"JSON解析失败: {e}")
    except Exception as e:
        print(f"解析文章数据失败: {e}")
    return result


def save_juejin_article(article_data, juejin_article_id):
    """保存掘金文章到新模型（集成AI摘要和标题优化）"""
    if not article_data.get("title"):
        print("文章标题为空，跳过保存")
        return None

    try:
        if JuejinHotArticle.objects.filter(
            juejin_article_id=juejin_article_id
        ).exists():
            print(
                f"掘金文章ID {juejin_article_id} 已存在，跳过：{article_data['title']}"
            )
            return None

        # AI优化降级处理
        try:
            optimized_title = optimize_article_title(article_data["title"])
        except Exception as e:
            print(f"AI标题优化失败，使用原始标题: {e}")
            optimized_title = article_data["title"]

        try:
            ai_summary = generate_article_summary(
                article_data.get("content") or article_data.get("summary", "")
            )
        except Exception as e:
            print(f"AI摘要生成失败，使用原始摘要: {e}")
            ai_summary = article_data.get("summary", "")

        article = JuejinHotArticle(
            juejin_article_id=juejin_article_id,
            title=optimized_title,
            summary=ai_summary,
            ai_summary=ai_summary,
            original_url=article_data["url"],
            author=article_data["author"],
            source=article_data["source"],
            published_time=article_data["published_time"],
        )
        article.save()

        print(
            f"成功保存掘金文章（AI优化）：{optimized_title} (ID: {juejin_article_id})"
        )
        return article

    except IntegrityError as e:
        print(f"数据库完整性错误（可能ID重复），保存失败: {e}")
    except Exception as e:
        print(f"保存文章失败 {article_data['title']}: {e}")

    return None


def crawl_and_save_juejin_hot():
    """主函数：爬取掘金热榜并保存到新模型（集成AI功能）"""
    print("开始爬取掘金热榜（集成AI摘要和标题优化）...")

    hot_list = spider()
    if not hot_list:
        print("未获取到掘金热榜数据")
        return

    print(f"\n获取到 {len(hot_list)} 篇文章，开始处理...\n")

    crawled_count = 0
    for item in hot_list[:MAX_ARTICLES_TO_CRAWL]:
        try:
            content = item.get("content", {})
            
            print(f"\n正在处理文章数据：")
            print(f"  item keys: {list(item.keys())}")
            print(f"  content keys: {list(content.keys())}")
            
            juejin_article_id = content.get("content_id", "")
            
            if not juejin_article_id:
                print("  跳过：没有content_id")
                continue

            article_url = f"https://juejin.cn/post/{juejin_article_id}"

            if JuejinHotArticle.objects.filter(
                juejin_article_id=juejin_article_id
            ).exists():
                print(f"  掘金文章ID {juejin_article_id} 已存在，跳过")
                continue

            # 从 item 层级获取作者信息（掘金API结构变化）
            article_author = item.get("author", {}) or content.get("author", {})
            author_name = article_author.get("name", "未知作者") if article_author else "未知作者"
            
            article_title = content.get("title", "")
            article_brief = content.get("brief", "")
            article_desc = content.get("description", "")
            
            if not article_brief:
                article_brief = article_desc
            
            # 如果仍然没有摘要，使用标题作为摘要
            if not article_brief:
                article_brief = article_title
            
            print(f"  标题: {article_title}")
            print(f"  作者: {author_name}")
            print(f"  摘要: {article_brief[:50]}..." if article_brief else "  摘要: (空)")

            if not article_title:
                print("  跳过：没有标题")
                continue

            article_data = {
                "title": article_title,
                "summary": article_brief or article_title,
                "url": article_url,
                "author": author_name,
                "source": "掘金",
                "published_time": timezone.now(),
                "content": article_brief or article_title,
            }

            if save_juejin_article(article_data, juejin_article_id):
                crawled_count += 1

        except KeyError as e:
            print(f"热榜数据格式异常: {e}")
            import traceback
            traceback.print_exc()
            continue
        except Exception as e:
            print(f"处理文章失败: {e}")
            import traceback
            traceback.print_exc()
            continue

    print(f"\n爬取完成！共新增 {crawled_count} 篇掘金热榜文章（均已AI优化）")


if __name__ == "__main__":
    import os
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "extraordinaryblog.settings")
    django.setup()

    crawl_and_save_juejin_hot()
