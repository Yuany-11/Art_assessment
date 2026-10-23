"""B→A 数据交接：题库/班级数据驱动 PAP、ASM、ATT 主链路。"""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.classes.integration import build_student_ref, resolve_target_students
from apps.classes.models import ClassTeacher
from apps.exams.models import Score
from apps.exams.services.assessment import publish_assessment
from apps.exams.services.attempt import start_attempt, submit_attempt
from apps.exams.services.paper import create_manual_paper
from apps.qbank.integration import get_question_snapshots, select_approved_questions
from apps.qbank.models import Question, QuestionOption


def _approved_question(teacher, course, chapter):
    question = Question.objects.create(
        subject="music",
        grade=7,
        course=course,
        chapter=chapter,
        type="single_choice",
        difficulty=2,
        stem="下列哪个是四分音符？",
        score=5,
        answer={"value": "A"},
        analysis="四分音符为一拍。",
        scoring_mode="auto",
        status="approved",
        creator=teacher,
    )
    QuestionOption.objects.create(question=question, key="A", text="♩", sort_order=0)
    QuestionOption.objects.create(question=question, key="B", text="♪", sort_order=1)
    return question


@pytest.mark.django_db
def test_b_data_handoff_to_paper_assessment_and_attempt(
    teacher, student, classroom, course, chapter
):
    ClassTeacher.objects.create(
        teacher=teacher, class_obj=classroom, subject="music"
    )
    student.student_profile.classroom = classroom
    student.student_profile.save(update_fields=["classroom", "updated_at"])

    question = _approved_question(teacher, course, chapter)
    selected = select_approved_questions(subject="music", grade=7)
    assert [item.id for item in selected] == [question.id]

    # PAP：A 的组卷服务直接消费 B 的已审核试题
    paper = create_manual_paper(
        teacher,
        {
            "title": "数据交接测评卷",
            "subject": "music",
            "paperType": "formal",
            "grade": 7,
            "scopeType": "class",
            "scopeId": classroom.id,
            "duration": 45,
            "status": "ready",
            "questions": [
                {
                    "questionId": question.id,
                    "order": 1,
                    "sectionName": "客观题",
                    "score": 5,
                }
            ],
        },
    )
    assert paper.question_count == 1
    assert paper.questions.get().resources == []

    # ASM：A 的发布使用 B 的班级/学生数据计算参与名单
    students = resolve_target_students("class", [classroom.id], [7])
    assert [item.id for item in students] == [student.id]
    ref = build_student_ref(student)
    assert ref["classId"] == classroom.id
    assert ref["className"] == classroom.name

    now = timezone.now()
    assessment = publish_assessment(
        teacher,
        {
            "paperId": paper.id,
            "title": "数据交接测评",
            "targetType": "class",
            "targetIds": [classroom.id],
            "startTime": now - timedelta(minutes=1),
            "endTime": now + timedelta(days=1),
            "attemptLimit": 1,
            "showAnswerMode": "after_end",
            "allowLateSubmit": False,
        },
    )
    assert assessment.participant_count == 1

    # ATT：学生拿到的是 B 的题目快照，答案只存在于服务端快照
    attempt = start_attempt(student, assessment)
    assert attempt.questions_snapshot[0]["questionId"] == question.id
    assert attempt.questions_snapshot[0]["answer"] == {"value": "A"}
    assert get_question_snapshots([question.id])[0]["options"][0]["text"] == "♩"

    attempt, duplicate = submit_attempt(
        student,
        attempt,
        payload={
            "submitType": "manual",
            "finalAnswers": [
                {"questionId": question.id, "answer": {"value": "A"}}
            ],
        },
    )
    assert duplicate is False

    score = Score.objects.get(assessment=assessment, student=student)
    assert score.total_score == 5
    assert score.max_score == 5
    assert score.classroom_id == classroom.id
