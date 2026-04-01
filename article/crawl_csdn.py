import sys
import requests
from lxml import etree
from django.utils import timezone
from django.db import IntegrityError
import os
import django
import random
import time
import hashlib

# 设置默认编码为UTF-8
sys.stdout.reconfigure(encoding='utf-8')

# 获取项目根目录并加入 sys.path，以便独立运行脚本时能找到 article 模块
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 在导入 Django 模型之前必须先配置环境并调用 setup()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "extraordinaryblog.settings")
django.setup()

from article.models import CSDNArticle

"""爬取CSDN数据"""

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
COOKIE_STRING = "uuid_tt_dd=10_28832532610-1745132351491-177576; fid=20_91728460241-1745132351881-967354; UN=2301_80282636; c_dl_fref= https://so.csdn.net/so/search; Hm_ct_6bcd52f51e9b3dce32bec4a3997715ac=6525*1*10_28832532610-1745132351491-177576!5744*1*2301_80282636; UserName=2301_80282636; UserInfo=d9e8f3d878b940899736baeebf902faa; UserToken=d9e8f3d878b940899736baeebf902faa; UserNick=%E8%B0%A2%E8%B0%A20000; AU=6CA; BT=1761190618377; p_uid=U010000; c_dl_prid=1762584964497_418580; c_dl_rid=1762585424498_430158; c_dl_fpage=/download/zhengyvxiang/86179509; c_dl_um=distribute.pc_search_result.none-task-download-2%7Eall%7Einsert_commercial%7Edefault-2-10733323-null-null.142%5Ev102%5Epc_search_result_base5; c_adb=1; csdn_newcert_2301_80282636=1; c_ab_test=1; _ga_JJBD2VG1H7=GS2.1.s1773829705$o2$g0$t1773829710$j55$l0$h0; _ga_7W1N0GEY1P=GS2.1.s1774876494$o18$g1$t1774876883$j60$l0$h0; _ga=GA1.2.1305449770.1766673951; csrfToken=VXAkHXvdsE9_u4DjnGcDvsN3; c_segment=8; Hm_lvt_6bcd52f51e9b3dce32bec4a3997715ac=1774846099,1774928647,1774957421,1775026255; HMACCOUNT=26FAD4314C20E141; dc_sid=c83e1c678fe3f44dd53b17bb4c928f4f; _clck=1kq1ix4%5E2%5Eg4u%5E0%5E1936; creative_btn_mp=3; historyList-new=%5B%5D; is_advert=1; c_first_ref=default; c_first_page=https%3A//www.csdn.net/; fe_request_id=1775029633000_1671_5211151; c_utm_source=cknow_so_nontop_query; _clsk=25gs8z%5E1775029664671%5E14%5E0%5Eh.clarity.ms%2Fcollect; dc_session_id=10_1775055448494.873322; c_pref=default; c_ref=default; c_page_id=default; c-sidebar-collapse=0; log_Id_click=1; c_dsid=11_1775057138236.314103; log_Id_pv=9; Hm_lpvt_6bcd52f51e9b3dce32bec4a3997715ac=1775057139; log_Id_view=580; dc_tos=tctng8"

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
    """爬取csdn数据"""
    url = "https://www.csdn.net/"

    payload = ""
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Pragma": "no-cache",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": get_random_user_agent(),
        "Cookie": COOKIE_STRING,
        "Accept-Encoding": "gzip, deflate, br",
        "Host": "www.csdn.net"
    }

    try:
        response = requests.request("GET", url, data=payload, headers=headers, timeout=REQUEST_TIMEOUT, proxies=PROXIES)
        # 指定编码
        response.encoding = "utf-8"
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"请求CSDN失败: {e}")
        return ""

def parse(content):
    """解析csdn数据"""
    tree = etree.HTML(content)
    # 提取文章列表
    article_list = tree.xpath('//div[@class="article-item"]')
    print(f"找到 {len(article_list)} 篇文章")
    
    articles_data = []
    for article in article_list:
        try:
            author = article.xpath('.//span/text()')[0]

            # 文章链接
            url = article.xpath('.//a[contains(@class, "article-title")]/@href')[0]
            if not url.startswith('http'):
                url = f"https://www.csdn.net{url}"
            
            title = article.xpath('.//a[contains(@class, "article-title")]/text()')[0].strip()
            summary = article.xpath('.//a[contains(@class, "article-desc")]/text()')[0].strip()
            
            articles_data.append({
                "title": title,
                "url": url,
                "author": author,
                "summary": summary
            })
            
            print(f"标题: {title}")
            print(f"作者: {author}")
            print(f"链接: {url}")
            print(f"摘要: {summary[:50]}..." if summary else "摘要: (空)")
            print()
            
        except Exception as e:
            print(f"解析文章项失败: {e}")
            continue
    
    return articles_data

def save_csdn_article(article_data, csdn_article_id):
    """保存CSDN文章到模型"""
    if not article_data.get("title"):
        print("文章标题为空，跳过保存")
        return None

    try:
        if CSDNArticle.objects.filter(
            csdn_article_id=csdn_article_id
        ).exists():
            print(
                f"CSDN文章ID {csdn_article_id} 已存在，跳过：{article_data['title']}"
            )
            return None

        article = CSDNArticle(
            csdn_article_id=csdn_article_id,
            title=article_data["title"],
            summary=article_data.get("summary", ""),
            original_url=article_data["url"],
            author=article_data["author"],
            source=article_data.get("source", "CSDN"),
        )
        article.save()

        print(
            f"成功保存CSDN文章：{article_data['title']} (ID: {csdn_article_id})"
        )
        return article

    except IntegrityError as e:
        print(f"数据库完整性错误（可能ID重复），保存失败: {e}")
    except Exception as e:
        print(f"保存文章失败 {article_data['title']}: {e}")

    return None

def crawl_and_save_csdn():
    """主函数：爬取CSDN文章并保存到模型"""
    print("开始爬取CSDN文章...")

    content = spider()
    if not content:
        print("未获取到CSDN数据")
        return

    articles_data = parse(content)
    if not articles_data:
        print("未解析到文章数据")
        return

    print(f"\n获取到 {len(articles_data)} 篇文章，开始保存...\n")

    saved_count = 0
    for item in articles_data[:MAX_ARTICLES_TO_CRAWL]:
        try:
            article_url = item.get("url")
            if not article_url:
                print("  跳过：没有链接")
                continue

            # 提取CSDN文章ID
            csdn_article_id = ""
            import re
            match = re.search(r'/([a-zA-Z0-9_-]+)\.html$', article_url)
            if match:
                csdn_article_id = match.group(1)
            else:
                # 尝试从URL中提取其他形式的ID
                match = re.search(r'/article/details/(\d+)', article_url)
                if match:
                    csdn_article_id = match.group(1)
                else:
                    # 生成基于URL的唯一ID
                    csdn_article_id = hashlib.md5(article_url.encode()).hexdigest()[:10]

            article_data = {
                "title": item.get("title"),
                "url": article_url,
                "author": item.get("author"),
                "summary": item.get("summary"),
                "source": "CSDN"
            }

            if save_csdn_article(article_data, csdn_article_id):
                saved_count += 1
                # 避免请求过于频繁
                time.sleep(random.uniform(2, 4))

        except Exception as e:
            print(f"处理文章失败: {e}")
            import traceback
            traceback.print_exc()
            continue

    print(f"\n爬取完成！共保存 {saved_count} 篇CSDN文章")


if __name__ == "__main__":
    import os
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "extraordinaryblog.settings")
    django.setup()

    crawl_and_save_csdn()
