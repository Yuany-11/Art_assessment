from django.core.management.base import BaseCommand

from exams.services.attempt import auto_submit_expired


class Command(BaseCommand):
    help = "扫描并自动提交已到截止时间的答卷（幂等，可重复执行）"

    def handle(self, *args, **options):
        count = auto_submit_expired()
        self.stdout.write(self.style.SUCCESS(f"自动交卷完成：{count} 份"))
