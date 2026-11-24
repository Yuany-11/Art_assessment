"""试卷审核：提交审核、审核通过/驳回、审核记录。

试卷审核统一由题库管理员处理，其他端只负责组卷和提交审核，
不再按组织层级分配审核人。
"""
from django.db import transaction
from django.utils import timezone

from common.enums import (
    AccountStatus,
    NotificationType,
    PaperReviewAction,
    PaperReviewStatus,
    PaperStatus,
    Role,
)
from common.exceptions import Conflict, Forbidden, Unprocessable
from apps.exams.models import PaperReviewLog
from apps.exams.services import notification as notification_service

ADMIN_ROLES = {
    Role.SCHOOL_ADMIN,
    Role.DISTRICT_ADMIN,
    Role.CITY_ADMIN,
    Role.PROVINCE_ADMIN,
    Role.QUESTION_ADMIN,
}


def _active_users(role):
    from apps.accounts.models import User

    return User.objects.filter(
        role=role, status=AccountStatus.ACTIVE, deleted_at__isnull=True
    )


def resolve_reviewer(paper):
    """试卷统一分配给题库管理员；找不到时返回 None。"""
    return _active_users(Role.QUESTION_ADMIN).exclude(pk=paper.creator_id).first()


def _ensure_can_submit(user, paper):
    if paper.creator_id == user.id:
        return
    if user.role in ADMIN_ROLES:
        return
    raise Forbidden("只有试卷创建人或管理员可以提交审核")


def submit_review(user, paper, version, comment=None):
    _ensure_can_submit(user, paper)
    if version is None:
        version = paper.version
    if int(version) != paper.version:
        raise Conflict("试卷版本已变化，请刷新后重试")
    if paper.status == PaperStatus.PUBLISHED:
        raise Conflict("已发布试卷不能再次提交审核")
    if paper.review_status == PaperReviewStatus.PENDING:
        raise Conflict("试卷已在审核中")
    if paper.review_status == PaperReviewStatus.APPROVED:
        raise Conflict("试卷已审核通过")
    if not paper.questions.exists() or paper.total_score <= 0:
        raise Unprocessable("试卷题目或总分不完整")

    reviewer = resolve_reviewer(paper)
    now = timezone.now()
    with transaction.atomic():
        paper.review_status = PaperReviewStatus.PENDING
        paper.status = PaperStatus.READY
        paper.reviewer = reviewer
        paper.review_comment = None
        paper.submitted_at = now
        paper.reviewed_at = None
        paper.save(
            update_fields=[
                "review_status",
                "status",
                "reviewer",
                "review_comment",
                "submitted_at",
                "reviewed_at",
                "updated_at",
            ]
        )
        PaperReviewLog.objects.create(
            paper=paper,
            version=paper.version,
            action=PaperReviewAction.SUBMIT,
            reviewer=user,
            comment=comment or None,
        )
        if reviewer is not None:
            notification_service.notify(
                reviewer,
                type=NotificationType.PAPER_REVIEW_SUBMITTED,
                title="新的试卷待审核",
                content=f"《{paper.title}》已提交审核，请及时处理。",
                link="/paper-review",
            )
    return paper


def review_paper(user, paper, action, comment, version):
    if user.role != Role.QUESTION_ADMIN:
        raise Forbidden("试卷审核已统一由题库管理员处理")
    if paper.review_status != PaperReviewStatus.PENDING:
        raise Conflict("试卷不在待审核状态")
    if paper.version != int(version):
        raise Conflict("试卷版本已变化，请刷新后重试")
    if paper.creator_id == user.id:
        raise Forbidden("不能审核自己创建的试卷")
    if action not in (PaperReviewAction.APPROVE, PaperReviewAction.REJECT):
        raise Unprocessable("审核动作不合法")
    if action == PaperReviewAction.REJECT and not (comment or "").strip():
        raise Unprocessable("驳回原因不能为空")

    now = timezone.now()
    with transaction.atomic():
        paper.review_status = (
            PaperReviewStatus.APPROVED
            if action == PaperReviewAction.APPROVE
            else PaperReviewStatus.REJECTED
        )
        paper.status = (
            PaperStatus.READY if action == PaperReviewAction.APPROVE else PaperStatus.DRAFT
        )
        paper.review_comment = comment or None
        paper.reviewer = user
        paper.reviewed_at = now
        paper.save(
            update_fields=[
                "review_status",
                "status",
                "review_comment",
                "reviewer",
                "reviewed_at",
                "updated_at",
            ]
        )
        PaperReviewLog.objects.create(
            paper=paper,
            version=paper.version,
            action=action,
            reviewer=user,
            comment=comment or None,
        )
        notification_service.notify(
            paper.creator,
            type=(
                NotificationType.PAPER_REVIEW_APPROVED
                if action == PaperReviewAction.APPROVE
                else NotificationType.PAPER_REVIEW_REJECTED
            ),
            title="试卷审核通过" if action == PaperReviewAction.APPROVE else "试卷审核未通过",
            content=(
                f"《{paper.title}》已审核通过，可以发布。"
                if action == PaperReviewAction.APPROVE
                else f"《{paper.title}》被驳回：{comment}"
            ),
            link="/papers",
        )
    return paper


def review_history(paper):
    return paper.review_logs.select_related("reviewer").all()
