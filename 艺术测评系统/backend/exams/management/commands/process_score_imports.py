from django.core.management.base import BaseCommand

from exams.models import ImportTask
from exams.services.score import process_import_task


class Command(BaseCommand):
    help = "处理排队中的成绩导入任务（大文件异步导入）"

    def handle(self, *args, **options):
        tasks = ImportTask.objects.filter(status="queued").order_by("created_at")
        count = 0
        for task in tasks:
            process_import_task(task)
            count += 1
        self.stdout.write(self.style.SUCCESS(f"已处理 {count} 个导入任务"))
