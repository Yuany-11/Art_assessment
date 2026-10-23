"""P4 支撑：组卷选题与题目快照。"""
import pytest

from apps.files.models import FileObject
from apps.qbank.integration import (
    build_question_snapshot,
    get_question_snapshots,
    select_approved_questions,
)
from apps.qbank.models import Question, QuestionResource

from conftest import PASSWORD


def _create_question(creator, course, chapter, status, stem, question_type="single_choice"):
    return Question.objects.create(
        subject=course.subject,
        grade=course.grade,
        course=course,
        chapter=chapter,
        type=question_type,
        difficulty=2,
        stem=stem,
        score=5,
        answer={"value": "A"},
        scoring_mode="auto",
        status=status,
        creator=creator,
    )


@pytest.mark.django_db
def test_select_only_approved_questions(question_admin, course, chapter):
    approved = _create_question(question_admin, course, chapter, "approved", "已通过")
    _create_question(question_admin, course, chapter, "pending", "待审核")

    selected = select_approved_questions(subject="music", grade=7)
    assert [item.id for item in selected] == [approved.id]

    assert select_approved_questions(
        subject="music", grade=7, question_type="multiple_choice"
    ) == []


@pytest.mark.django_db
def test_question_snapshot_with_resources(question_admin, course, chapter):
    question = _create_question(question_admin, course, chapter, "approved", "带资源题目")
    question.options.create(key="A", text="2/4", sort_order=0)
    question.options.create(key="B", text="3/4", sort_order=1)
    file_obj = FileObject.objects.create(
        uploader=question_admin,
        category="question_image",
        original_name="q.png",
        object_key="question_image/q.png",
        mime_type="image/png",
        size=128,
        storage_backend="local",
    )
    QuestionResource.objects.create(question=question, file=file_obj, type="image")

    snapshot = build_question_snapshot(question)
    assert snapshot["questionId"] == question.id
    assert snapshot["options"][0] == {"key": "A", "text": "2/4", "mediaUrl": None}
    assert snapshot["resources"][0]["url"] == "/media/question_image/q.png"
    assert snapshot["answer"] == {"value": "A"}

    ordered = get_question_snapshots([question.id, 99999])
    assert len(ordered) == 1
    assert ordered[0]["questionId"] == question.id
