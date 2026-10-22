"""APScheduler 定时任务：独立进程运行，使用 Redis 锁避免重复执行。"""
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from apps.accounts.models import ImportTask


def fail_stale_import_tasks() -> None:
    """将超过 1 小时仍排队/处理中的导入任务标记为失败。"""
    lock_key = "scheduler:fail_stale_import_tasks"
    if not cache.add(lock_key, 1, 600):
        return
    try:
        deadline = timezone.now() - timedelta(hours=1)
        ImportTask.objects.filter(
            status__in=[ImportTask.Status.QUEUED, ImportTask.Status.PROCESSING],
            created_at__lt=deadline,
            deleted_at__isnull=True,
        ).update(
            status=ImportTask.Status.FAILED,
            errors=[{"row": 0, "username": "", "message": "导入任务超时"}],
            finished_at=timezone.now(),
            updated_at=timezone.now(),
        )
    finally:
        cache.delete(lock_key)


JOBS = [
    ("fail_stale_import_tasks", fail_stale_import_tasks),
]
