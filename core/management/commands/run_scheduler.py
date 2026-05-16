"""Django management command to run APScheduler in a dedicated process.

Usage: python manage.py run_scheduler

This avoids the multi-worker problem where each Gunicorn worker starts its
own scheduler instance. In production, run this as a separate process.
"""
import logging
import signal
import time

from django.core.management.base import BaseCommand
from cron_jobs import start_scheduler

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run APScheduler in a dedicated process (separate from WSGI workers)"

    def handle(self, *args, **options):
        start_scheduler()

        # Keep the process alive — wait for SIGTERM/SIGINT
        stop_event = False

        def _shutdown(signum, frame):
            nonlocal stop_event
            stop_event = True

        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)

        self.stdout.write(self.style.SUCCESS("Scheduler running. Send SIGTERM/SIGINT to stop."))

        while not stop_event:
            time.sleep(10)

        self.stdout.write(self.style.WARNING("Scheduler stopped."))
