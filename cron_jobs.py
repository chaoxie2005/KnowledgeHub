import os
import django
import fcntl
import atexit
from datetime import timedelta
from django.utils import timezone

# 配置Django环境（必须）
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "extraordinaryblog.settings")
django.setup()

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from article.crawl_juejin import crawl_and_save_juejin_hot  # 导入掘金爬虫核心函数
from article.crawl_csdn import crawl_and_save_csdn  # 导入CSDN爬虫核心函数
from utils.rag_chain import _build_vector_store_from_db  # 导入向量库更新函数
from utils.content_audit import ContentAuditService
from article.models import Comment, Article
import logging

_lock_fh = None


def _release_lock():
    global _lock_fh
    if _lock_fh is None:
        return
    try:
        fcntl.flock(_lock_fh.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass
    try:
        _lock_fh.close()
    except Exception:
        pass
    _lock_fh = None


def _acquire_lock(lock_path: str) -> bool:
    global _lock_fh
    if _lock_fh is not None:
        return True

    fh = open(lock_path, "w")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        try:
            fh.close()
        except Exception:
            pass
        return False

    _lock_fh = fh
    atexit.register(_release_lock)
    return True

# 配置日志（可选，方便查看定时任务执行情况）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="crawl_juejin.log",  # 日志保存到项目根目录
)
logger = logging.getLogger("掘金爬虫定时任务")
csdn_logger = logging.getLogger("CSDN爬虫定时任务")


def audit_existing_content():
    """定期审核已发布的内容"""
    audit_service = ContentAuditService()
    logger = logging.getLogger("内容审核定时任务")
    
    # 审核最近7天的未审核评论
    recent_comments = Comment.objects.filter(
        created_at__gte=timezone.now() - timedelta(days=7),
        is_audited=False
    )
    for comment in recent_comments:
        audit_result = audit_service.audit_content(comment.content, "comment")
        comment.is_audited = True
        comment.audit_passed = audit_result['passed']
        comment.violation_reasons = audit_result['violation_reasons']
        comment.audit_time = timezone.now()
        comment.save()
        if not audit_result['passed']:
            logger.info(f"评论审核未通过: ID={comment.id}, 原因={audit_result['violation_reasons']}")
    
    # 审核最近7天的未审核文章
    recent_articles = Article.objects.filter(
        created_at__gte=timezone.now() - timedelta(days=7),
        is_audited=False
    )
    for article in recent_articles:
        audit_result = audit_service.audit_content(article.content, "article")
        article.is_audited = True
        article.audit_passed = audit_result['passed']
        article.violation_reasons = audit_result['violation_reasons']
        article.audit_time = timezone.now()
        article.save()
        if not audit_result['passed']:
            logger.info(f"文章审核未通过: ID={article.id}, 原因={audit_result['violation_reasons']}")


def start_scheduler():
    """启动定时任务调度器"""
    if not _acquire_lock("/tmp/extraordinaryblog_juejin_scheduler.lock"):
        logger.warning("定时任务已在其他进程中运行，当前进程跳过启动")
        print("定时任务已在其他进程中运行，当前进程跳过启动")
        return

    # 创建后台调度器（不阻塞Django运行）
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")  # 用北京时间

    # 添加定时任务：每天上午9点和下午3点各爬取一次（可自定义时间）
    # Cron表达式说明：分 时 日 月 周（*表示任意）
    scheduler.add_job(
        func=crawl_and_save_juejin_hot,  # 要执行的爬虫函数
        trigger=CronTrigger(hour="9, 15", minute="0"),  # 每天9:00、15:00执行
        id="juejin_hot_crawl",  # 任务唯一ID（方便管理）
        replace_existing=True,  # 重复启动时替换原有任务
        misfire_grace_time=300,  # 任务错过执行时，允许延迟5分钟
    )

    # 添加定时任务：CSDN爬虫，每天上午10点和下午4点各爬取一次
    scheduler.add_job(
        func=crawl_and_save_csdn,  # 要执行的CSDN爬虫函数
        trigger=CronTrigger(hour="10, 16", minute="0"),  # 每天10:00、16:00执行
        id="csdn_hot_crawl",  # 任务唯一ID（方便管理）
        replace_existing=True,  # 重复启动时替换原有任务
        misfire_grace_time=300,  # 任务错过执行时，允许延迟5分钟
    )

    # 添加定时任务：每小时更新一次向量库
    scheduler.add_job(
        func=_build_vector_store_from_db,  # 要执行的向量库更新函数
        trigger=CronTrigger(minute="0"),  # 每小时整点执行
        id="vector_store_update",  # 任务唯一ID
        replace_existing=True,  # 重复启动时替换原有任务
        misfire_grace_time=300,  # 任务错过执行时，允许延迟5分钟
    )

    # 内容（包含评论和文章）审核定时任务：每半个月执行一次
    scheduler.add_job(
        func=audit_existing_content,  # 要执行的审核函数
        trigger=CronTrigger(day="1,16", hour="0", minute="0"),  # 每月1号和16号零点执行 半个月执行一次
        id="content_audit",  # 任务唯一ID
        replace_existing=True,  # 重复启动时替换原有任务
        misfire_grace_time=300,  # 任务错过执行时，允许延迟5分钟
    )

    # 启动调度器
    try:
        scheduler.start()
        logger.info("定时任务已启动：掘金爬虫(每天9:00、15:00)，CSDN爬虫(每天10:00、16:00)，向量库更新(每小时)，内容审核(每半个月)")
        print("定时任务已启动：掘金爬虫(每天9:00、15:00)，CSDN爬虫(每天10:00、16:00)，向量库更新(每小时)，内容审核(每半个月)")
    except Exception as e:
        logger.error(f"定时任务启动失败：{str(e)}")
        scheduler.shutdown()  # 启动失败则关闭调度器


if __name__ == "__main__":
    start_scheduler()
    # 保持进程运行（单独测试时用）
    import time
    while True:
        time.sleep(3600)
