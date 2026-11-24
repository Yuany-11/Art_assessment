from django.core.management.base import BaseCommand

from apps.exams.services.assessment import finish_expired_assessments


class Command(BaseCommand):
    help = "将已到结束时间的测评标记为已结束"

    def handle(self, *args, **options):
        count = finish_expired_assessments()
        self.stdout.write(self.style.SUCCESS(f"测评结束处理完成：{count} 个"))
