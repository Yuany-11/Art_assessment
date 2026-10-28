"""异步导入任务：RQ Worker 执行入口。"""
import logging

from django.core.files.storage import default_storage
from django.utils import timezone

from common.audit import log_operation
from common.imports import header_map, read_table

from .models import ImportTask, User
from .services.account_import import _process_rows

logger = logging.getLogger(__name__)


def run_teacher_import(task_id: str, actor_id: int, file_key: str,
                       default_password: str | None, overwrite: bool) -> None:
    task = ImportTask.objects.filter(task_id=task_id, deleted_at__isnull=True).first()
    if task is None:
        return

    task.status = ImportTask.Status.PROCESSING
    task.save(update_fields=["status", "updated_at"])

    actor = None
    try:
        actor = User.objects.filter(pk=actor_id, deleted_at__isnull=True).first()
        if actor is None:
            raise RuntimeError("发起账号不存在")

        with default_storage.open(file_key, "rb") as uploaded:
            rows = read_table(uploaded, max_size_mb=5)
        if not rows:
            raise RuntimeError("导入文件为空")

        mapping = header_map(rows[0])
        indexed_rows = [
            (index, row)
            for index, row in enumerate(rows[1:], start=2)
            if any(item.strip() for item in row)
        ]
        success_count, errors = _process_rows(
            actor, indexed_rows, mapping, default_password, overwrite
        )

        task.status = ImportTask.Status.COMPLETED
        task.success_count = success_count
        task.fail_count = len(errors)
        task.errors = errors
        task.finished_at = timezone.now()
        task.save(
            update_fields=[
                "status",
                "success_count",
                "fail_count",
                "errors",
                "finished_at",
                "updated_at",
            ]
        )
        log_operation(
            actor,
            "account.import_teachers",
            "account",
            None,
            f"异步导入教师：成功 {success_count}，失败 {len(errors)}",
        )
    except Exception:
        logger.exception("teacher import task failed: %s", task_id)
        task.status = ImportTask.Status.FAILED
        task.errors = [{"row": 0, "username": "", "message": "导入任务执行失败"}]
        task.finished_at = timezone.now()
        task.save(
            update_fields=["status", "errors", "finished_at", "updated_at"]
        )
        if actor is not None:
            log_operation(
                actor,
                "account.import_teachers",
                "account",
                None,
                "异步导入教师失败",
                result="failed",
            )
    finally:
        try:
            default_storage.delete(file_key)
        except Exception:
            pass
