import copy
import random
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from common.enums import (
    AttemptStatus,
    GradingStatus,
    PaperType,
    QuestionType,
    Role,
    ScoreSource,
    ScoringMode,
    ShowAnswerMode,
    SubmitType,
)
from common.exceptions import BadRequest, Conflict, Forbidden, NotFound
from common.utils import level_for, round2
from apps.exams.models import Attempt, AttemptAnswer, Score
from apps.exams.serializers import SaveAnswersSerializer, SubmitSerializer
from apps.exams.services import assessment as assessment_service
from apps.exams.services import ranking as ranking_service


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
            "assessment", "paper", "student", "student__student_profile__classroom",
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


def answer_visibility(attempt, now=None):
    """按测评的答案公布方式判断学生现在能否看到标准答案与解析。"""
    assessment = attempt.assessment
    mode = assessment.show_answer_mode
    if mode == ShowAnswerMode.NEVER:
        return False
    if mode == ShowAnswerMode.AFTER_SUBMIT:
        return attempt.status != AttemptStatus.IN_PROGRESS
    if mode == ShowAnswerMode.AFTER_END:
        return assessment.end_time <= (now or timezone.now())
    return False


def review_attempt(user, attempt_id):
    """提交后阅卷：学生可查看自己的作答；标准答案按答案公布时间展示。"""
    from apps.exams.presenters import attempt_question

    attempt = (
        Attempt.objects.select_related(
            "assessment", "assessment__publisher", "paper", "student"
        )
        .prefetch_related("answers")
        .filter(pk=attempt_id)
        .first()
    )
    if attempt is None:
        raise NotFound("答卷不存在")
    if user.role != Role.STUDENT or attempt.student_id != user.id:
        raise Forbidden("无权查看该答卷")

    now = timezone.now()
    if attempt.status == AttemptStatus.IN_PROGRESS:
        if attempt.deadline > now:
            raise Conflict("答卷尚未提交，暂不能查看试卷")
        auto_submit_attempt(attempt, reason="deadline")
        attempt.refresh_from_db()
    visible = answer_visibility(attempt, now)
    snapshots = {q["questionId"]: q for q in attempt.questions_snapshot}
    details = []
    for row in attempt.answers.all():
        snap = snapshots.get(row.question_id, {})
        question = attempt_question(snap)
        details.append({
            "questionId": row.question_id,
            "order": row.order,
            "type": snap.get("type", ""),
            "stem": snap.get("stem", ""),
            "options": question["options"],
            "resources": question["resources"],
            "studentAnswer": row.answer or {},
            "score": round2(row.score) if row.score is not None else None,
            "maxScore": round2(row.max_score),
            "isCorrect": row.is_correct if visible else None,
            "correctAnswer": (snap.get("answer") or None) if visible else None,
            "analysis": snap.get("analysis") if visible else None,
            "comment": row.comment,
            "scoringMode": row.scoring_mode,
        })
    graded = attempt.grading_status == GradingStatus.GRADED
    assessment = attempt.assessment
    return {
        "attemptId": attempt.id,
        "assessmentId": assessment.id,
        "assessmentTitle": assessment.title,
        "subject": assessment.subject,
        "paperType": assessment.paper_type,
        "publisherName": getattr(assessment.publisher, "real_name", ""),
        "startTime": assessment.start_time,
        "endTime": assessment.end_time,
        "submittedAt": attempt.submitted_at,
        "status": attempt.status,
        "gradingStatus": attempt.grading_status,
        "showAnswerMode": assessment.show_answer_mode,
        "answerVisible": visible,
        "objectiveScore": round2(attempt.objective_score),
        "subjectiveScore": round2(attempt.subjective_score) if graded else None,
        "totalScore": round2(attempt.total_score) if graded else None,
        "maxScore": round2(assessment.max_score),
        "scoreReleased": graded,
        "questions": details,
    }


def _validate_answer_payload(attempt, answers):
    question_ids = {q["questionId"] for q in attempt.questions_snapshot}
    snapshots = {q["questionId"]: q for q in attempt.questions_snapshot}
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
        files = item["answer"].get("files")
        if files is not None and snapshots.get(qid, {}).get("type") == QuestionType.IMAGE_UPLOAD:
            if not isinstance(files, list) or len(files) > 3:
                raise BadRequest("单题最多上传 3 张作品照片")
            if any(not isinstance(file, dict) for file in files):
                raise BadRequest("作品照片格式不正确")


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

    if qtype in (
        QuestionType.SINGLE_CHOICE,
        QuestionType.LISTENING,
        QuestionType.AUDIO_CHOICE_JUDGE,
        QuestionType.IMAGE_CHOICE_JUDGE,
    ):
        ok = _normalize(answer.get("value")).upper() == _normalize(correct.get("value")).upper()
        return (max_score if ok else 0.0), ok, True
    if qtype == QuestionType.MULTIPLE_CHOICE:
        given = {
            _normalize(v).upper()
            for v in (answer.get("values") or [])
            if _normalize(v)
        }
        expected = {
            _normalize(v).upper()
            for v in (correct.get("values") or [])
            if _normalize(v)
        }
        if not expected or not given:
            return 0.0, False, True
        # 错选（包含正确答案之外的选项）不得分。
        if given - expected:
            return 0.0, False, True
        # 全对满分；只选对一部分时按选对数量占正确项总数的比例给分。
        if given == expected:
            return max_score, True, True
        if question.get("partialCredit", True):
            score = round2(max_score * len(given & expected) / len(expected))
            return score, False, True
        return 0.0, False, True
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
    pending_types = set()
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
            pending_types.add(question.get("type", ""))
            subjective += row.score or 0
    attempt.objective_score = round2(objective)
    attempt.subjective_score = round2(subjective)
    attempt.total_score = round2(objective + subjective)
    # 随机练习只出客观题、即时出分；即使历史练习卷含实践作品题也不进入教师评分任务。
    practice_release = attempt.assessment.paper_type == PaperType.PRACTICE
    manual_pending = pending_types & {QuestionType.IMAGE_UPLOAD, QuestionType.AUDIO_UPLOAD}
    pending = bool(manual_pending) and not practice_release
    attempt.grading_status = GradingStatus.GRADING if pending else GradingStatus.GRADED
    if not pending:
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
            "total_score": attempt.total_score,
            "max_score": assessment.max_score,
            "level": level_for(attempt.total_score, assessment.max_score),
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

    score = None
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
        from apps.exams.services.wrong_question import collect_from_attempt

        collect_from_attempt(attempt)
        # 含实践作品等人工评分题时先不生成成绩，等教师终评后再公布。
        if attempt.grading_status == GradingStatus.GRADED:
            score = _upsert_score(attempt)
            ranking_service.recompute_ranks(attempt.assessment)

    # 出分后刷新学情报告；正式测评得分率达到 90% 自动发证书。
    if score is not None:
        from apps.exams.services.achievement import after_score_released

        after_score_released(score)
    return attempt, False


def auto_submit_attempt(attempt, reason="deadline"):
    if attempt.status != AttemptStatus.IN_PROGRESS:
        return attempt
    return submit_attempt(attempt.student, attempt, payload=None, auto=True, reason=reason)[0]


def auto_submit_expired():
    now = timezone.now()
    qs = Attempt.objects.filter(
        status=AttemptStatus.IN_PROGRESS, deadline__lte=now
    ).select_related(
        "assessment", "student", "student__student_profile__classroom", "student__org"
    )
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
