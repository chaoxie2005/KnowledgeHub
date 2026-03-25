import os
import django

# 配置Django环境（必须）
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "extraordinaryblog.settings")
django.setup()

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from article.crawl_juejin import crawl_and_save_juejin_hot  # 导入爬虫核心函数
import logging

# 配置日志（可选，方便查看定时任务执行情况）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="crawl_juejin.log",  # 日志保存到项目根目录
)
logger = logging.getLogger("掘金爬虫定时任务")


def start_scheduler():
    """启动定时任务调度器"""
    # 创建后台调度器（不阻塞Django运行）
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")  # 用北京时间

    # 添加定时任务：每天上午9点和下午3点各爬取一次（可自定义时间）
    # Cron表达式说明：分 时 日 月 周（*表示任意）
    scheduler.add_job(
        func=crawl_and_save_juejin_hot,  # 要执行的爬虫函数
        trigger=CronTrigger(hour="9,15", minute="0"),  # 每天9:00、15:00执行
        id="juejin_hot_crawl",  # 任务唯一ID（方便管理）
        replace_existing=True,  # 重复启动时替换原有任务
        misfire_grace_time=300,  # 任务错过执行时，允许延迟5分钟
    )

    # 启动调度器
    try:
        scheduler.start()
        logger.info("掘金爬虫定时任务已启动，每天9:00、15:00自动执行")
        print("掘金爬虫定时任务已启动，每天9:00、15:00自动执行")
    except Exception as e:
        logger.error(f"定时任务启动失败：{str(e)}")
        scheduler.shutdown()  # 启动失败则关闭调度器


if __name__ == "__main__":
    start_scheduler()
    # 保持进程运行（单独测试时用）
    import time
    while True:
        time.sleep(3600)
