import copy
import random
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from common.enums import (
    AttemptStatus,
    GradingStatus,
    QuestionType,
    Role,
    ScoreSource,
    ScoringMode,
    SubmitType,
)
from common.exceptions import BadRequest, Conflict, Forbidden, NotFound
from common.utils import round2
from exams.models import Attempt, AttemptAnswer, Score
from exams.serializers import SaveAnswersSerializer, SubmitSerializer
from exams.services import assessment as assessment_service
from exams.services import ranking as ranking_service


def _error(message, code=409):
    from common.exceptions import BusinessError

    return BusinessError(code, message)


def _prepare_questions(assessment):
    snapshot = copy.deepcopy(assessment.question_snapshot or [])
    if assessment.shuffle_questions:
        random.shuffle(snapshot)
    for index, question in enumerate(snapshot, start=1):
        question["order"] = index
        if assessment.shuffle_options and question.get("options"):
            options = list(question["options"])
            random.shuffle(options)
            question["options"] = options
    return snapshot


def start_attempt(user, assessment, device_type="web"):
    assessment_service.can_start(assessment, user)
    now = timezone.now()

    existing = (
        Attempt.objects.filter(
            assessment=assessment, student=user, status=AttemptStatus.IN_PROGRESS
        )
        .order_by("-attempt_no")
        .first()
    )
    if existing:
        if existing.deadline > now:
            return existing
        auto_submit_attempt(existing, reason="deadline")

    used = Attempt.objects.filter(assessment=assessment, student=user).count()
    if used >= assessment.attempt_limit:
        raise Conflict(f"已达到允许作答次数（{assessment.attempt_limit} 次）")

    deadline = min(now + timedelta(minutes=assessment.duration), assessment.end_time)
    snapshot = _prepare_questions(assessment)
    try:
        with transaction.atomic():
            attempt = Attempt.objects.create(
                assessment=assessment,
                paper=assessment.paper,
                student=user,
                attempt_no=used + 1,
                status=AttemptStatus.IN_PROGRESS,
                started_at=now,
                deadline=deadline,
                grading_status=GradingStatus.PENDING,
                questions_snapshot=snapshot,
            )
            AttemptAnswer.objects.bulk_create([
                AttemptAnswer(
                    attempt=attempt,
                    question_id=q["questionId"],
                    order=q["order"],
                    max_score=q.get("score", 0),
                    scoring_mode=q.get("scoringMode", ScoringMode.AUTO),
                )
                for q in snapshot
            ])
    except IntegrityError:
        raise Conflict("并发开始答题，请刷新后重试")
    return attempt


def get_attempt(user, attempt_id, auto_close=True):
    attempt = (
        Attempt.objects.select_related(
            "assessment", "paper", "student", "student__current_class",
        )
        .filter(pk=attempt_id)
        .first()
    )
    if attempt is None:
        raise NotFound("答卷不存在")
    if user.role != Role.STUDENT:
        raise Forbidden("该接口仅限学生本人使用")
    if attempt.student_id != user.id:
        raise Forbidden("无权查看他人答卷")
    if (
        auto_close
        and attempt.status == AttemptStatus.IN_PROGRESS
        and attempt.deadline <= timezone.now()
    ):
        auto_submit_attempt(attempt, reason="deadline")
    return attempt


def _validate_answer_payload(attempt, answers):
    question_ids = {q["questionId"] for q in attempt.questions_snapshot}
    seen = set()
    for item in answers:
        qid = item["questionId"]
        if qid not in question_ids:
            raise BadRequest(f"试题 {qid} 不属于本答卷")
        if qid in seen:
            raise BadRequest(f"试题 {qid} 重复提交")
        seen.add(qid)
        if not isinstance(item["answer"], dict):
            raise BadRequest("answer 必须是对象")


def save_answers(user, attempt, payload):
    if user.role != Role.STUDENT or attempt.student_id != user.id:
        raise Forbidden("无权保存该答卷")
    if attempt.status != AttemptStatus.IN_PROGRESS:
        raise Conflict("答卷已提交，不能继续保存答案")
    if attempt.deadline <= timezone.now():
        auto_submit_attempt(attempt, reason="deadline")
        raise Conflict("已超过作答截止时间，系统已自动交卷")

    serializer = SaveAnswersSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    _validate_answer_payload(attempt, data["answers"])

    now = timezone.now()
    saved = 0
    with transaction.atomic():
        for item in data["answers"]:
            updated = AttemptAnswer.objects.filter(
                attempt=attempt, question_id=item["questionId"]
            ).update(answer=item["answer"], updated_at=now)
            saved += updated
        Attempt.objects.filter(pk=attempt.pk).update(last_answer_saved_at=now, updated_at=now)
    attempt.refresh_from_db()
    return {
        "savedCount": saved,
        "savedAt": now,
        "serverTime": now,
        "remainingSeconds": attempt.remaining_seconds,
    }


def _normalize(value):
    if value is None:
        return ""
    return str(value).strip()


def grade_objective(question, answer):
    """返回 (score, is_correct, graded)。非客观题返回 graded=False。"""
    mode = question.get("scoringMode", ScoringMode.AUTO)
    qtype = question.get("type", "")
    if mode != ScoringMode.AUTO or qtype in {
        QuestionType.SHORT_ANSWER, QuestionType.IMAGE_UPLOAD, QuestionType.AUDIO_UPLOAD
    }:
        return None, None, False
    correct = question.get("answer") or {}
    max_score = float(question.get("score", 0))
    if answer is None:
        return 0.0, False, True

    if qtype in (QuestionType.SINGLE_CHOICE, QuestionType.LISTENING):
        ok = _normalize(answer.get("value")).upper() == _normalize(correct.get("value")).upper()
        return (max_score if ok else 0.0), ok, True
    if qtype == QuestionType.MULTIPLE_CHOICE:
        given = {_normalize(v).upper() for v in (answer.get("values") or [])}
        expected = {_normalize(v).upper() for v in (correct.get("values") or [])}
        ok = given == expected
        return (max_score if ok else 0.0), ok, True
    if qtype == QuestionType.TRUE_FALSE:
        def _bool(v):
            if isinstance(v, bool):
                return v
            return _normalize(v).lower() in ("true", "1", "正确", "对")
        ok = _bool(answer.get("value")) == _bool(correct.get("value"))
        return (max_score if ok else 0.0), ok, True
    if qtype == QuestionType.FILL_BLANK:
        given = answer.get("values") or []
        expected = correct.get("values") or []
        if not expected:
            return 0.0, False, True
        matched = sum(
            1 for g, e in zip(given, expected) if _normalize(g) == _normalize(e)
        )
        # 多写的空白不额外得分，按正确项占比给分
        score = round2(max_score * matched / len(expected))
        return score, matched == len(expected) and len(given) == len(expected), True
    return None, None, False


def _apply_grading(attempt):
    snapshot = {q["questionId"]: q for q in attempt.questions_snapshot}
    objective = 0.0
    subjective = 0.0
    ai = 0.0
    pending_non_auto = False
    for row in attempt.answers.select_related().all():
        question = snapshot.get(row.question_id, {})
        score, correct, graded = grade_objective(question, row.answer)
        if graded:
            row.score = score
            row.is_correct = correct
            row.graded_at = timezone.now()
            row.save(update_fields=["score", "is_correct", "graded_at", "updated_at"])
            objective += score or 0
        else:
            pending_non_auto = True
            if row.scoring_mode == ScoringMode.AI:
                ai += row.score or 0
            else:
                subjective += row.score or 0
    attempt.objective_score = round2(objective)
    attempt.subjective_score = round2(subjective)
    attempt.ai_score = round2(ai)
    attempt.total_score = round2(objective + subjective + ai)
    attempt.grading_status = (
        GradingStatus.GRADING if pending_non_auto else GradingStatus.GRADED
    )
    if not pending_non_auto:
        attempt.status = AttemptStatus.GRADED
    return attempt


def _upsert_score(attempt):
    assessment = attempt.assessment
    student = attempt.student
    classroom = student.current_class
    score, _ = Score.objects.update_or_create(
        assessment=assessment,
        student=student,
        defaults={
            "attempt": attempt,
            "subject": assessment.subject,
            "student_name": student.real_name,
            "student_no": student.student_no or "",
            "classroom": classroom,
            "class_name": classroom.name if classroom else "",
            "school": student.school,
            "school_name": student.school.name if student.school else "",
            "grade": student.grade or (classroom.grade if classroom else None),
            "objective_score": attempt.objective_score,
            "subjective_score": attempt.subjective_score,
            "ai_score": attempt.ai_score,
            "total_score": attempt.total_score,
            "max_score": assessment.max_score,
            "status": attempt.grading_status,
            "source": ScoreSource.ONLINE,
            "graded_at": timezone.now() if attempt.status == AttemptStatus.GRADED else None,
        },
    )
    return score


def submit_attempt(user, attempt, payload=None, auto=False, reason=""):
    if attempt.student_id != user.id and not auto:
        raise Forbidden("无权提交他人答卷")

    if attempt.status != AttemptStatus.IN_PROGRESS:
        # 幂等：重复提交返回第一次结果
        return attempt, True

    now = timezone.now()
    if not auto and now > attempt.deadline:
        assessment = attempt.assessment
        grace_deadline = assessment.end_time + timedelta(
            minutes=settings.LATE_SUBMIT_GRACE_MINUTES
        )
        if not assessment.allow_late_submit or now > grace_deadline:
            raise Conflict("已超过作答截止时间，系统将自动交卷")
        # 宽限期内允许手动提交

    if payload:
        serializer = SubmitSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        final_answers = serializer.validated_data.get("finalAnswers") or []
        if final_answers:
            _validate_answer_payload(attempt, final_answers)
            with transaction.atomic():
                for item in final_answers:
                    AttemptAnswer.objects.filter(
                        attempt=attempt, question_id=item["questionId"]
                    ).update(answer=item["answer"], updated_at=now)

    with transaction.atomic():
        attempt = _apply_grading(attempt)
        attempt.status = (
            AttemptStatus.GRADED if attempt.grading_status == GradingStatus.GRADED
            else AttemptStatus.SUBMITTED
        )
        attempt.submitted_at = now
        attempt.submit_type = SubmitType.AUTO if auto else SubmitType.MANUAL
        attempt.auto_submitted = auto
        attempt.save()
        _upsert_score(attempt)
        if attempt.grading_status == GradingStatus.GRADED:
            ranking_service.recompute_ranks(attempt.assessment)
    return attempt, False


def auto_submit_attempt(attempt, reason="deadline"):
    if attempt.status != AttemptStatus.IN_PROGRESS:
        return attempt
    return submit_attempt(attempt.student, attempt, payload=None, auto=True, reason=reason)[0]


def auto_submit_expired():
    now = timezone.now()
    qs = Attempt.objects.filter(
        status=AttemptStatus.IN_PROGRESS, deadline__lte=now
    ).select_related("assessment", "student", "student__current_class", "student__school")
    count = 0
    for attempt in qs.iterator():
        try:
            auto_submit_attempt(attempt, reason="deadline")
            count += 1
        except Exception:  # 单份失败不影响其余答卷
            continue
    return count


def attempt_deadline(assessment, started_at):
    return min(started_at + timedelta(minutes=assessment.duration), assessment.end_time)
