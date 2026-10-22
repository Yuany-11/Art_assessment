"""运行 APScheduler 定时任务进程。"""
from apscheduler.schedulers.blocking import BlockingScheduler
from django.conf import settings
from django.core.management.base import BaseCommand

from common.scheduler_jobs import JOBS


class Command(BaseCommand):
    help = "启动定时任务进程（APScheduler）"

    def handle(self, *args, **options):
        scheduler = BlockingScheduler(timezone=str(settings.TIME_ZONE))
        for job_id, job_func in JOBS:
            scheduler.add_job(
                job_func,
                "interval",
                minutes=10,
                id=job_id,
                max_instances=1,
                replace_existing=True,
            )

        self.stdout.write(self.style.SUCCESS(f"定时任务已启动：{len(JOBS)} 个任务"))
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()
            self.stdout.write("定时任务已停止")
