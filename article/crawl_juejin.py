import requests
import re
import json
import datetime
from django.utils import timezone
from django.db import IntegrityError
from .models import JuejinHotArticle, Tag

# 新增：导入AI工具函数
from .ai_utils import generate_article_summary, optimize_article_title

"""爬取稀土掘金的掘金热榜（集成AI摘要和标题优化）"""

# 配置项
REQUEST_TIMEOUT = 10  # 请求超时时间
MAX_ARTICLES_TO_CRAWL = 20  # 每次爬取的最大文章数

def get_or_create_tags(tag_names):
    """批量获取或创建标签"""
    tags = []
    for tag_name in tag_names:
        tag_name = tag_name.strip()
        if tag_name:  # 过滤空标签
            tag, created = Tag.objects.get_or_create(name=tag_name)
            tags.append(tag)
    return tags


def spider():
    """爬取掘金热榜接口数据"""
    cookies = {
        "_tea_utm_cache_2608": "undefined",
        "__tea_cookie_tokens_2608": "%257B%2522web_id%2522%253A%25227495787047023838760%2522%252C%2522user_unique_id%2522%253A%25227495787047023838760%2522%252C%2522timestamp%2522%253A1745248943786%257D",
        "passport_csrf_token": "5670c8be6aea3dc7eb90027d940d1b96",
        "passport_csrf_token_default": "5670c8be6aea3dc7eb90027d940d1b96",
        "odin_tt": "21770152b6d9beb854a15f6dde529f856c0432ce11dbf716d87b2602d31e2a89831cb27d972acdafb39c49b3ed57050570b817a4fc667773a675a2619f4532e4",
        "_ga": "GA1.2.979893466.1772948845",
        "_ga_S695FMNGPJ": "GS2.2.s1772948845$o1$g0$t1772948845$j60$l0$h0",
        "n_mh": "QgN8ycIE1mLmvYammYTgizVxWH5yfUziwXl-3A2wvEY",
        "passport_auth_status": "7c721dc747f905a0a97b14bd3b05ba75%2C",
        "passport_auth_status_ss": "7c721dc747f905a0a97b14bd3b05ba75%2C",
        "sid_guard": "fd0010ff444197d9fdaacdd73526c186%7C1773475449%7C31536000%7CSun%2C+14-Mar-2027+08%3A04%3A09+GMT",
        "uid_tt": "8d89eba567b1b899747a79dd4f755000",
        "uid_tt_ss": "8d89eba567b1b899747a79dd4f755000",
        "sid_tt": "fd0010ff444197d9fdaacdd73526c186",
        "sessionid": "fd0010ff444197d9fdaacdd73526c186",
        "sessionid_ss": "fd0010ff444197d9fdaacdd73526c186",
        "session_tlb_tag": "sttt%7C13%7C_QAQ_0RBl9n9qs3XNSbBhv_________Q6RkZNuAZHgoHWI_21YZqvZjnNGGLOrmqYOH26xdD-PQ%3D",
        "is_staff_user": "false",
        "sid_ucp_v1": "1.0.0-KDM3MGFlM2ZjMmM4ZTI4NzBkYjJlM2E4ZWI1MjZhZjJmNWJmOTBmZDAKFwjc6uGGra3KAxD5rNTNBhiwFDgCQPEHGgJsZiIgZmQwMDEwZmY0NDQxOTdkOWZkYWFjZGQ3MzUyNmMxODY",
        "ssid_ucp_v1": "1.0.0-KDM3MGFlM2ZjMmM4ZTI4NzBkYjJlM2E4ZWI1MjZhZjJmNWJmOTBmZDAKFwjc6uGGra3KAxD5rNTNBhiwFDgCQPEHGgJsZiIgZmQwMDEwZmY0NDQxOTdkOWZkYWFjZGQ3MzUyNmMxODY",
        "_tea_utm_cache_576092": "undefined",
        "csrf_session_id": "7b7e6247fdcd10998ec7cc3d292e378e",
    }

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
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
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
        )
        response.raise_for_status()  # 抛出HTTP错误
        return response.json()["data"]
    except requests.exceptions.RequestException as e:
        print(f"请求掘金热榜接口失败: {e}")
        return []


def get_content(url):
    """获取文章详情页HTML"""
    cookies = {
        "_tea_utm_cache_2608": "undefined",
        "__tea_cookie_tokens_2608": "%257B%2522web_id%2522%253A%25227495787047023838760%2522%252C%2522user_unique_id%2522%253A%25227495787047023838760%2522%252C%2522timestamp%2522%253A1745248943786%257D",
        "s_v_web_id": "verify_mkjuystm_zMDrjXIG_frat_4BTK_A70D_YKeUWEfWj3qU",
        "passport_csrf_token": "5670c8be6aea3dc7eb90027d940d1b96",
        "passport_csrf_token_default": "5670c8be6aea3dc7eb90027d940d1b96",
        "odin_tt": "21770152b6d9beb854a15f6dde529f856c0432ce11dbf716d87b2602d31e2a89831cb27d972acdafb39c49b3ed57050570b817a4fc667773a675a2619f4532e4",
        "_ga": "GA1.2.979893466.1772948845",
        "_ga_S695FMNGPJ": "GS2.2.s1772948845$o1$g0$t1772948845$j60$l0$h0",
        "n_mh": "QgN8ycIE1mLmvYammYTgizVxWH5yfUziwXl-3A2wvEY",
        "passport_auth_status": "7c721dc747f905a0a97b14bd3b05ba75%2C",
        "passport_auth_status_ss": "7c721dc747f905a0a97b14bd3b05ba75%2C",
        "sid_guard": "fd0010ff444197d9fdaacdd73526c186%7C1773475449%7C31536000%7CSun%2C+14-Mar-2027+08%3A04%3A09+GMT",
        "uid_tt": "8d89eba567b1b899747a79dd4f755000",
        "uid_tt_ss": "8d89eba567b1b899747a79dd4f755000",
        "sid_tt": "fd0010ff444197d9fdaacdd73526c186",
        "sessionid": "fd0010ff444197d9fdaacdd73526c186",
        "sessionid_ss": "fd0010ff444197d9fdaacdd73526c186",
        "session_tlb_tag": "sttt%7C13%7C_QAQ_0RBl9n9qs3XNSbBhv_________Q6RkZNuAZHgoHWI_21YZqvZjnNGGLOrmqYOH26xdD-PQ%3D",
        "is_staff_user": "false",
        "sid_ucp_v1": "1.0.0-KDM3MGFlM2ZjMmM4ZTI4NzBkYjJlM2E4ZWI1MjZhZjJmNWJmOTBmZDAKFwjc6uGGra3KAxD5rNTNBhiwFDgCQPEHGgJsZiIgZmQwMDEwZmY0NDQxOTdkOWZkYWFjZGQ3MzUyNmMxODY",
        "ssid_ucp_v1": "1.0.0-KDM3MGFlM2ZjMmM4ZTI4NzBkYjJlM2E4ZWI1MjZhZjJmNWJmOTBmZDAKFwjc6uGGra3KAxD5rNTNBhiwFDgCQPEHGgJsZiIgZmQwMDEwZmY0NDQxOTdkOWZkYWFjZGQ3MzUyNmMxODY",
        "_tea_utm_cache_576092": "undefined",
    }

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
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    }

    try:
        response = requests.get(
            url, cookies=cookies, headers=headers, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
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
        "source": "",  # 文章来源
        "published_time": None,
        "tags": [],
        "content": "",  # 新增：解析完整文章内容（用于AI摘要）
    }

    # 匹配核心JSON数据
    pattern = r'<script.*?type="application/ld\+json".*?>([\s\S]*?)</script>'
    match = re.search(pattern, html_content)
    tags_match = re.search(
        r'<meta\s+itemprop="keywords".*?content="([^"]+)"[^>]*>', html_content
    )

    # 新增：匹配文章完整内容（掘金的文章内容在特定div中）
    content_pattern = r'<div class="article-content-container[\s\S]*?>([\s\S]*?)</div>'
    content_match = re.search(content_pattern, html_content)
    if content_match:
        # 清理HTML标签，提取纯文本内容
        content = re.sub(r"<[^>]+>", "", content_match.group(1))
        result["content"] = re.sub(r"\s+", " ", content).strip()

    if not match:
        print("未匹配到文章核心数据")
        return result

    try:
        # 解析JSON数据
        json_str = match.group(1).strip()
        json_data = json.loads(json_str)[0]

        # 提取基础信息
        result["title"] = json_data.get("headline", "")
        result["summary"] = json_data.get("description", "")
        result["url"] = json_data.get("mainEntityOfPage", {}).get("@id", "")
        result["author"] = json_data.get("author", {}).get("name", "")
        result["source"] = json_data.get("publisher", {}).get(
            "name", ""
        )  # 解析文章来源

        # 解析发布时间
        pub_time_str = json_data.get("datePublished", "")
        if pub_time_str:
            try:
                # 直接解析带时区的时间，避免make_aware冲突
                result["published_time"] = datetime.datetime.fromisoformat(
                    pub_time_str.replace("Z", "+00:00")
                )
            except ValueError as e:
                print(f"解析发布时间失败: {e}")
                result["published_time"] = timezone.now()

        # 解析标签
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
    # 基础校验
    if not article_data.get("title"):
        print("文章标题为空，跳过保存")
        return None

    try:
        # 核心去重：通过掘金ID判断是否已存在
        if JuejinHotArticle.objects.filter(
            juejin_article_id=juejin_article_id
        ).exists():
            print(
                f"掘金文章ID {juejin_article_id} 已存在，跳过：{article_data['title']}"
            )
            return None

        # 新增：AI优化标题
        optimized_title = optimize_article_title(article_data["title"])

        # 新增：AI生成摘要（优先用完整内容，无则用原摘要）
        ai_summary = generate_article_summary(
            article_data.get("content") or article_data.get("summary", "")
        )

        # 创建文章（使用AI优化后的标题，保存AI摘要）
        article = JuejinHotArticle(
            juejin_article_id=juejin_article_id,
            title=optimized_title,  # 替换为AI优化后的标题
            summary=ai_summary,  # 替换为AI生成的摘要
            original_url=article_data["url"],
            author=article_data["author"],
            source=article_data["source"],  # 新增：文章来源
            published_time=article_data["published_time"],
        )
        article.save()

        # 添加标签（多对多关系需要先保存文章）
        tags = get_or_create_tags(article_data["tags"])
        article.tags.add(*tags)

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

    # 1. 获取热榜列表
    hot_list = spider()
    if not hot_list:
        print("未获取到掘金热榜数据")
        return

    # 2. 遍历热榜文章（限制数量）
    crawled_count = 0
    for item in hot_list[:MAX_ARTICLES_TO_CRAWL]:
        try:
            # 提取掘金唯一文章ID（核心去重标识）
            juejin_article_id = item["content"]["content_id"]
            article_url = f"https://juejin.cn/post/{juejin_article_id}"

            # 先检查ID是否已存在，存在则直接跳过（无需爬取详情，提升效率）
            if JuejinHotArticle.objects.filter(
                juejin_article_id=juejin_article_id
            ).exists():
                print(f"掘金文章ID {juejin_article_id} 已存在，跳过：{article_url}")
                continue

            # 3. 获取并解析文章详情
            html_content = get_content(article_url)
            if not html_content:
                continue

            article_data = parse_article_detail(html_content)
            if not article_data["title"]:
                continue

            # 4. 保存到数据库（自动AI优化）
            if save_juejin_article(article_data, juejin_article_id):
                crawled_count += 1

        except KeyError as e:
            print(f"热榜数据格式异常: {e}")
            continue
        except Exception as e:
            print(f"处理文章失败: {e}")
            continue

    print(f"爬取完成！共新增 {crawled_count} 篇掘金热榜文章（均已AI优化）")


# 执行爬虫（在Django环境中运行）
if __name__ == "__main__":
    # 重要：在独立运行时需要配置Django环境
    import os
    import django

    # 请替换为你的项目settings路径
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "extraordinaryblog.settings")
    django.setup()

    # 执行爬取（带AI优化）
    crawl_and_save_juejin_hot()
