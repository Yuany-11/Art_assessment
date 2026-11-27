"""工作台概览：真实统计数据，替代前端写死的数字。"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.exams.models import Score
from apps.exams.scope import DataScope
from apps.exams.services.assessment import list_assessments
from apps.exams.services.paper import list_papers
from apps.qbank.services import list_questions
from common.enums import (
    AssessmentStatus,
    PaperReviewStatus,
    PaperStatus,
    QuestionStatus,
    Role,
)


def _month_start():
    now = timezone.localtime()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _month_participation_rate(user) -> float:
    """本月参与率 = 本月产生成绩的学生数 / 数据范围内在册学生数。"""
    scope = DataScope(user)
    school_ids = scope.school_ids
    if not school_ids:
        return 0.0
    participant_ids = set(
        Score.objects.filter(
            created_at__gte=_month_start(), school_id__in=school_ids
        ).values_list("student_id", flat=True)
    )
    User = get_user_model()
    total = User.objects.filter(
        role=Role.STUDENT,
        status="active",
        deleted_at__isnull=True,
        org_id__in=school_ids,
    ).count()
    if not total:
        return 0.0
    return round(len(participant_ids) / total * 100, 1)


def dashboard_summary(user):
    summary = {
        "month": timezone.localtime().strftime("%Y-%m"),
        "pendingPublishPapers": None,
        "runningAssessments": None,
        "pendingQuestions": None,
        "pendingReviewPapers": None,
        "participationRate": None,
    }
    if user.role == Role.STUDENT:
        return summary

    papers = list_papers(user, {})
    summary["pendingPublishPapers"] = papers.filter(
        status__in=[PaperStatus.DRAFT, PaperStatus.READY]
    ).count()

    if user.role == Role.QUESTION_ADMIN:
        summary["pendingQuestions"] = list_questions(
            user, {"status": QuestionStatus.PENDING}
        ).count()
        summary["pendingReviewPapers"] = papers.filter(
            review_status=PaperReviewStatus.PENDING
        ).count()
    else:
        summary["runningAssessments"] = (
            list_assessments(user, {"status": AssessmentStatus.PUBLISHED})
            .filter(end_time__gt=timezone.now())
            .count()
        )
        summary["participationRate"] = _month_participation_rate(user)
    return summary
