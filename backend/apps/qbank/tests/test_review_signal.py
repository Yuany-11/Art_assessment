"""试题审核领域事件。"""
import pytest

from apps.qbank.models import Question
from apps.qbank.services import review_question
from apps.qbank.signals import question_reviewed
from common.enums import QuestionStatus, Subject


@pytest.mark.django_db
def test_review_question_emits_event(teacher, question_admin, course):
    received = []

    def receiver(sender, **kwargs):
        received.append(kwargs)

    question_reviewed.connect(receiver)
    try:
        question = Question.objects.create(
            subject=Subject.MUSIC,
            grade=7,
            course=course,
            type="single_choice",
            stem="审核事件测试题",
            score=5,
            answer={"value": "A"},
            status=QuestionStatus.PENDING,
            creator=teacher,
        )
        review_question(question_admin, question, "approve", "符合要求")
    finally:
        question_reviewed.disconnect(receiver)

    assert len(received) == 1
    assert received[0]["question"].id == question.id
    assert received[0]["actor"].id == question_admin.id
    assert received[0]["action"] == "approve"
    assert received[0]["comment"] == "符合要求"
