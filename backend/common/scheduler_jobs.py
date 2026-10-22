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


def process_score_imports() -> None:
    """处理排队的成绩导入任务。"""
    from apps.exams.models import ImportTask
    from apps.exams.services.score import process_import_task

    for task in ImportTask.objects.filter(status="queued").order_by("created_at")[:50]:
        process_import_task(task)


def generate_exam_certificates() -> None:
    """为已结束的正式测评批量生成证书。"""
    from apps.exams.models import Assessment
    from apps.exams.services.certificate import generate_for_assessment
    from common.enums import AssessmentStatus, PaperType

    qs = Assessment.objects.filter(
        paper_type=PaperType.FORMAL, status=AssessmentStatus.FINISHED
    )
    for assessment in qs.iterator():
        generate_for_assessment(assessment, force=False)


def _exam_jobs():
    from apps.exams.services.assessment import finish_expired_assessments
    from apps.exams.services.attempt import auto_submit_expired

    return [
        ("auto_submit_attempts", auto_submit_expired),
        ("finish_assessments", finish_expired_assessments),
        ("process_score_imports", process_score_imports),
        ("generate_certificates", generate_exam_certificates),
    ]


JOBS = [
    ("fail_stale_import_tasks", fail_stale_import_tasks, 600),
    ("auto_submit_attempts", None, 30),
    ("finish_assessments", None, 60),
    ("process_score_imports", None, 60),
    ("generate_certificates", None, 300),
]


def build_jobs():
    """组装 (job_id, func, interval_seconds) 列表。"""
    mapping = {job_id: func for job_id, func in _exam_jobs()}
    mapping["fail_stale_import_tasks"] = fail_stale_import_tasks
    return [(job_id, mapping[job_id], seconds) for job_id, _, seconds in JOBS]
