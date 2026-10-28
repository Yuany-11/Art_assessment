"""P4 测评主链路支撑：为组卷/发布提供已审核试题与快照。"""
from common.enums import QuestionStatus

from .models import Question
from .services import build_resource


def select_approved_questions(
    *,
    subject: str,
    grade: int,
    question_type: str | None = None,
    difficulty: int | None = None,
    course_id: int | None = None,
    chapter_id: int | None = None,
    limit: int | None = None,
) -> list[Question]:
    """按组卷条件抽取已审核试题；后端 A 组卷服务直接调用。"""
    queryset = Question.objects.filter(
        status=QuestionStatus.APPROVED,
        deleted_at__isnull=True,
        subject=subject,
        grade=grade,
    ).select_related("course", "chapter")
    if question_type:
        queryset = queryset.filter(type=question_type)
    if difficulty:
        queryset = queryset.filter(difficulty=difficulty)
    if course_id:
        queryset = queryset.filter(course_id=course_id)
    if chapter_id:
        queryset = queryset.filter(chapter_id=chapter_id)

    queryset = queryset.order_by("difficulty", "id")
    if limit:
        queryset = queryset[:limit]
    return list(queryset)


def build_question_snapshot(question: Question) -> dict:
    """输出发布/答题所需的题目快照（含答案，仅供后端服务使用）。"""
    options = [
        {
            "key": option.key,
            "text": option.text,
            "mediaUrl": option.media_url,
        }
        for option in question.options.filter(deleted_at__isnull=True).order_by("sort_order", "id")
    ]
    resources = [
        build_resource(resource)
        for resource in question.resources.filter(deleted_at__isnull=True).select_related("file")
    ]
    return {
        "questionId": question.id,
        "subject": question.subject,
        "grade": question.grade,
        "courseId": question.course_id,
        "chapterId": question.chapter_id,
        "type": question.type,
        "difficulty": question.difficulty,
        "stem": question.stem,
        "score": float(question.score),
        "options": options,
        "answer": question.answer,
        "analysis": question.analysis,
        "scoringMode": question.scoring_mode,
        "resources": resources,
    }


def get_question_snapshots(question_ids: list[int]) -> list[dict]:
    """按传入顺序返回快照；不存在或未审核的题目会被跳过。"""
    questions = {
        question.id: question
        for question in Question.objects.filter(
            pk__in=question_ids,
            status=QuestionStatus.APPROVED,
            deleted_at__isnull=True,
        ).select_related("course", "chapter")
    }
    return [
        build_question_snapshot(questions[question_id])
        for question_id in question_ids
        if question_id in questions
    ]
