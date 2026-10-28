"""题库领域事件。

审核通知由模块三（后端 A）的通知中心接入，本模块只负责发出事件，
不持有通知数据，避免越界实现通知中心。
"""
from django.dispatch import Signal, receiver

# 参数：question、actor、action（approve/reject）、comment
question_reviewed = Signal()


@receiver(question_reviewed)
def _notify_question_creator(sender, question, actor, action, comment=None, **kwargs):
    """试题审核结果写入通知中心，供出题教师查看。"""
    if question.creator_id == actor.id:
        return
    from common.enums import NotificationType
    from apps.exams.services import notification

    approved = action == "approve"
    notification.notify(
        question.creator,
        type=(
            NotificationType.QUESTION_REVIEW_APPROVED
            if approved else NotificationType.QUESTION_REVIEW_REJECTED
        ),
        title="试题审核通过" if approved else "试题审核未通过",
        content=(
            f"试题 #{question.id} 已审核通过。"
            if approved
            else f"试题 #{question.id} 被驳回：{comment or '无审核意见'}"
        ),
        link="/teacher/questions",
    )
