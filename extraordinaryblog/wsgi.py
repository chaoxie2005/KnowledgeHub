"""
WSGI config for extraordinaryblog project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'extraordinaryblog.settings')

application = get_wsgi_application()

# 新增：启动定时任务
try:
    from cron_jobs import start_scheduler

    start_scheduler()
except Exception as e:
    print(f"定时任务启动失败：{e}")
