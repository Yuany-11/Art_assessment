"""APScheduler 常驻进程：自动交卷、结束测评、证书生成、导入任务。

生产环境可由 systemd / supervisor 托管；测试环境直接用管理命令单次执行。
"""
from django.core.management.base import BaseCommand

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from exams.services.assessment import finish_expired_assessments
from exams.services.attempt import auto_submit_expired


def tick_auto_submit():
    auto_submit_expired()


def tick_finish_assessments():
    finish_expired_assessments()


class Command(BaseCommand):
    help = "启动定时任务调度器（阻塞运行，Ctrl+C 退出）"

    def handle(self, *args, **options):
        scheduler = BlockingScheduler(timezone="Asia/Shanghai")
        scheduler.add_job(
            tick_auto_submit,
            IntervalTrigger(seconds=30),
            id="auto_submit_attempts",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            tick_finish_assessments,
            IntervalTrigger(minutes=1),
            id="finish_assessments",
            max_instances=1,
            coalesce=True,
        )
        self.stdout.write(self.style.SUCCESS("调度器已启动，Ctrl+C 退出"))
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            self.stdout.write("调度器已停止")
