"""运行 APScheduler 定时任务进程。"""
from apscheduler.schedulers.blocking import BlockingScheduler
from django.conf import settings
from django.core.management.base import BaseCommand

from common.scheduler_jobs import build_jobs


class Command(BaseCommand):
    help = "启动定时任务进程（APScheduler）"

    def handle(self, *args, **options):
        scheduler = BlockingScheduler(timezone=str(settings.TIME_ZONE))
        jobs = build_jobs()
        for job_id, job_func, seconds in jobs:
            scheduler.add_job(
                job_func,
                "interval",
                seconds=seconds,
                id=job_id,
                max_instances=1,
                replace_existing=True,
            )

        self.stdout.write(self.style.SUCCESS(f"定时任务已启动：{len(jobs)} 个任务"))
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()
            self.stdout.write("定时任务已停止")
