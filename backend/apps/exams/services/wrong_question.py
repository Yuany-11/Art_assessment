"""学生错题本：错题归集、查询、掌握状态、重做。"""
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from common.enums import (
    AttemptStatus,
    PaperStatus,
    PaperType,
    QuestionStatus,
    Role,
    ScopeType,
)
from common.exceptions import Forbidden, NotFound, Unprocessable
from apps.exams.models import AttemptAnswer, Paper, PaperQuestion, WrongQuestion
from apps.exams.presenters import wrong_question_detail, wrong_question_item
from apps.exams.services import paper as paper_service

MASTERY_VALUES = {"unmastered", "reviewing", "mastered"}


def _source_type(attempt):
    paper_type = getattr(attempt.paper, "paper_type", PaperType.FORMAL)
    return "practice" if paper_type == PaperType.PRACTICE else "formal"


def collect_from_attempt(attempt):
    """交卷判分后归集客观题错题（幂等：同一题累计错误次数）。"""
    if attempt.status == AttemptStatus.IN_PROGRESS:
        return
    snapshot = {q["questionId"]: q for q in attempt.questions_snapshot or []}
    source_type = _source_type(attempt)
    now = timezone.now()
    updated = 0
    for row in attempt.answers.all():
        if row.is_correct is not False:
            continue
        question = snapshot.get(row.question_id) or {}
        answer = question.get("answer") or {}
        item, created = WrongQuestion.objects.get_or_create(
            student=attempt.student,
            question_id=row.question_id,
            defaults={
                "subject": question.get("subject") or attempt.assessment.subject,
                "type": question.get("type", ""),
                "stem": question.get("stem", ""),
                "options": question.get("options") or [],
                "resources": question.get("resources") or [],
                "correct_answer": answer,
                "student_answer": row.answer,
                "analysis": question.get("analysis"),
                "wrong_count": 1,
                "last_wrong_at": attempt.submitted_at or now,
                "source_type": source_type,
                "source_assessment_id": attempt.assessment_id,
                "source_assessment_title": attempt.assessment.title,
            },
        )
        if created:
            updated += 1
            continue
        item.deleted_at = None
        item.wrong_count = (item.wrong_count or 0) + 1
        item.last_wrong_at = attempt.submitted_at or now
        item.student_answer = row.answer
        item.source_type = source_type
        item.source_assessment_id = attempt.assessment_id
        item.source_assessment_title = attempt.assessment.title
        if item.stem != (question.get("stem") or item.stem):
            item.stem = question.get("stem") or item.stem
        item.save()
        updated += 1
    return updated


def _base_qs(user):
    return WrongQuestion.objects.filter(
        student=user, deleted_at__isnull=True
    ).select_related("student")


def list_wrong_questions(user, params):
    qs = _base_qs(user)
    if params.get("subject"):
        qs = qs.filter(subject=params["subject"])
    if params.get("questionType"):
        qs = qs.filter(type=params["questionType"])
    if params.get("masteryStatus"):
        qs = qs.filter(mastery_status=params["masteryStatus"])
    if params.get("sourceType"):
        qs = qs.filter(source_type=params["sourceType"])
    keyword = (params.get("keyword") or "").strip()
    if keyword:
        qs = qs.filter(stem__icontains=keyword)
    if params.get("dateFrom"):
        qs = qs.filter(last_wrong_at__date__gte=params["dateFrom"])
    if params.get("dateTo"):
        qs = qs.filter(last_wrong_at__date__lte=params["dateTo"])
    return qs.order_by("-last_wrong_at", "-id")


def get_wrong_question(user, wrong_id):
    item = _base_qs(user).filter(pk=wrong_id).first()
    if item is None:
        raise NotFound("错题不存在")
    return item


def update_wrong_question(user, item, payload):
    if "masteryStatus" in payload and payload["masteryStatus"] is not None:
        if payload["masteryStatus"] not in MASTERY_VALUES:
            raise Unprocessable("掌握状态不合法")
        item.mastery_status = payload["masteryStatus"]
    if "note" in payload:
        item.note = payload["note"]
    item.save(update_fields=["mastery_status", "note", "updated_at"])
    return item


def remove_wrong_question(user, item):
    item.delete()
    return item


def detail_payload(user, item):
    records = (
        AttemptAnswer.objects.filter(attempt__student=user, question_id=item.question_id)
        .select_related("attempt")
        .order_by("-attempt__submitted_at", "-id")[:20]
    )
    return wrong_question_detail(item, records)


def list_payload(user, qs, paginator, view):
    page = paginator.paginate_queryset(qs, request=None, view=view)
    return page


def statistics(user):
    qs = _base_qs(user)
    total = qs.count()
    counts = dict(qs.values_list("mastery_status").annotate(count=Count("id")))
    recent = timezone.now() - timedelta(days=7)
    by_subject = list(qs.values("subject").annotate(count=Count("id")).order_by("subject"))
    by_type = list(qs.values("type").annotate(count=Count("id")).order_by("type"))
    return {
        "total": total,
        "unmastered": counts.get("unmastered", 0),
        "reviewing": counts.get("reviewing", 0),
        "mastered": counts.get("mastered", 0),
        "recent7Days": qs.filter(last_wrong_at__gte=recent).count(),
        "bySubject": by_subject,
        "byType": by_type,
    }


def redo_wrong_question(user, item):
    """基于错题生成一份单题练习并开始作答。"""
    from apps.exams.services import attempt as attempt_service
    from apps.exams.services.assessment import build_snapshot
    from apps.qbank.models import Question

    if user.role != Role.STUDENT:
        raise Forbidden("仅学生可重做错题")
    question = Question.objects.filter(pk=item.question_id, deleted_at__isnull=True).first()
    if question is None or question.status != QuestionStatus.APPROVED:
        raise NotFound("原试题已不可用，无法重做")
    class_id = getattr(
        getattr(user, "student_profile", None), "classroom_id", None
    )
    if not class_id:
        raise Unprocessable("尚未加入班级，无法重做错题")

    now = timezone.now()
    paper = Paper.objects.create(
        title=f"错题重做：{question.stem[:30]}",
        subject=question.subject,
        paper_type=PaperType.PRACTICE,
        grade=question.grade,
        scope_type=ScopeType.CLASS,
        scope_id=class_id,
        scope_name=user.current_class.name if user.current_class else "错题重做",
        duration=30,
        status=PaperStatus.PUBLISHED,
        generate_mode="manual",
        creator=user,
    )
    score = float(question.score or 5)
    snap = paper_service.snapshot_question(question, 1, "错题重做", score)
    PaperQuestion.objects.create(**{
        "paper": paper,
        "question_id": question.id,
        "order": 1,
        "section_name": "错题重做",
        "type": snap["type"],
        "stem": snap["stem"],
        "options": snap["options"],
        "resources": snap["resources"],
        "answer": snap["answer"],
        "analysis": snap["analysis"],
        "rubric": snap["rubric"],
        "score": score,
        "scoring_mode": snap["scoringMode"],
    })
    paper.total_score = score
    paper.question_count = 1
    paper.save(update_fields=["total_score", "question_count", "updated_at"])

    snapshot = build_snapshot(paper)
    assessment = paper_service.create_practice_assessment(
        paper=paper,
        publisher=user,
        title=paper.title,
        class_id=class_id,
        class_name=paper.scope_name,
        grade=question.grade,
        start_time=now,
        end_time=now + timedelta(minutes=30),
        duration=30,
        snapshot=snapshot,
        attempt_limit=99,
    )
    attempt = attempt_service.start_attempt(user, assessment)
    return attempt, snap
