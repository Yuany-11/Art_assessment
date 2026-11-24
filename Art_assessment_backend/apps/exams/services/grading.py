from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from common.audit import log_action
from common.enums import (
    AttemptStatus,
    GradingStatus,
    NotificationType,
    QuestionType,
    Role,
    ScoringMode,
)
from common.exceptions import BadRequest, Conflict, Forbidden, NotFound, Unprocessable
from apps.exams.scope import DataScope
from common.utils import level_for, round2
from apps.exams.models import Attempt, GradingLog, Score
from apps.exams.serializers import GradingSubmitSerializer
from apps.exams.services import ranking as ranking_service

MANUAL_GRADING_TYPES = {QuestionType.IMAGE_UPLOAD, QuestionType.AUDIO_UPLOAD}


def _ensure_can_grade(user, attempt):
    if user.role not in (Role.TEACHER, Role.SCHOOL_ADMIN):
        raise Forbidden("仅教师或学校管理员可以评分")
    classroom = attempt.student.current_class
    if user.role == Role.TEACHER:
        scope = DataScope(user)
        if not classroom or not scope.teaches_subject_in_class(
            classroom.id, attempt.assessment.subject
        ):
            raise Forbidden("只能评分本人任教班级该学科学生的答卷")
    else:
        if not classroom or classroom.school_id != user.school_id:
            raise Forbidden("不能评分本校以外学生的答卷")


def list_tasks(user, params):
    if user.role not in (Role.TEACHER, Role.SCHOOL_ADMIN):
        raise Forbidden("仅教师或学校管理员可以查看评分任务")
    qs = Attempt.objects.select_related(
        "assessment", "student", "student__student_profile__classroom"
    ).prefetch_related("answers").filter(
        status__in=[AttemptStatus.SUBMITTED, AttemptStatus.GRADED],
        answers__scoring_mode=ScoringMode.MANUAL,
    ).distinct()
    if user.role == Role.TEACHER:
        scope = DataScope(user)
        qs = qs.filter(
            scope.teacher_pair_q(
                "student__student_profile__classroom_id", "assessment__subject"
            )
        )
    else:
        qs = qs.filter(student__org_id=user.school_id)

    grading_status = params.get("gradingStatus")
    if grading_status:
        qs = qs.filter(grading_status=grading_status)
    else:
        qs = qs.filter(
            grading_status__in=[
                GradingStatus.PENDING, GradingStatus.GRADING, GradingStatus.FAILED
            ]
        )
    if params.get("assessmentId"):
        qs = qs.filter(assessment_id=params["assessmentId"])
    if params.get("classId"):
        qs = qs.filter(student__student_profile__classroom_id=params["classId"])
    if params.get("subject"):
        qs = qs.filter(assessment__subject=params["subject"])
    if params.get("keyword"):
        keyword = params["keyword"]
        qs = qs.filter(
            Q(student__real_name__icontains=keyword)
            | Q(student__student_profile__student_no__icontains=keyword)
        )
    return qs.order_by("submitted_at", "id")


def get_grading_attempt(user, attempt_id):
    attempt = (
        Attempt.objects.select_related(
            "assessment", "student", "student__student_profile__classroom", "student__org"
        )
        .prefetch_related("answers")
        .filter(pk=attempt_id)
        .first()
    )
    if attempt is None:
        raise NotFound("答卷不存在")
    _ensure_can_grade(user, attempt)
    if attempt.status not in (AttemptStatus.SUBMITTED, AttemptStatus.GRADED):
        raise Conflict("答卷尚未提交，不能评分")
    return attempt


def _score_attempt(attempt):
    """根据逐题得分汇总客观/主观分数。"""
    objective = subjective = 0.0
    for row in attempt.answers.all():
        if row.scoring_mode == ScoringMode.AUTO:
            objective += row.score or 0
        else:
            subjective += row.score or 0
    attempt.objective_score = round2(objective)
    attempt.subjective_score = round2(subjective)
    attempt.total_score = round2(objective + subjective)


def submit_grading(user, attempt, payload, request=None):
    _ensure_can_grade(user, attempt)
    if attempt.status not in (AttemptStatus.SUBMITTED, AttemptStatus.GRADED):
        raise Conflict("答卷尚未提交，不能评分")
    already_graded = attempt.status == AttemptStatus.GRADED

    serializer = GradingSubmitSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    if already_graded and not data["finalize"]:
        raise Conflict("该答卷已完成终评，修改分数时请勾选“完成终评并生成最终成绩”")
    if data.get("version") is not None and data["version"] != attempt.version:
        raise Conflict("评分版本已变化，请刷新后重试")

    snapshot = {q["questionId"]: q for q in attempt.questions_snapshot}
    rows = {r.question_id: r for r in attempt.answers.all()}
    items = data["items"]
    for item in items:
        row = rows.get(item["questionId"])
        if row is None:
            raise BadRequest(f"试题 {item['questionId']} 不属于本答卷")
        if row.scoring_mode == ScoringMode.AUTO:
            raise Unprocessable(f"试题 {item['questionId']} 为客观题，无需人工评分")
        if snapshot.get(item["questionId"], {}).get("type") not in MANUAL_GRADING_TYPES:
            raise Unprocessable("人工评分只用于实践作品题和课外作品")
        if item["score"] > row.max_score:
            raise Unprocessable(
                f"试题 {item['questionId']} 得分超过满分 {round2(row.max_score)}"
            )

    finalize = data["finalize"]
    with transaction.atomic():
        for item in items:
            row = rows[item["questionId"]]
            row.score = round2(item["score"])
            row.comment = item.get("comment")
            row.graded_by = user
            row.graded_at = timezone.now()
            row.save(update_fields=[
                "score", "comment", "graded_by", "graded_at", "updated_at"
            ])

        pending = [
            r for r in attempt.answers.all()
            if r.scoring_mode != ScoringMode.AUTO
            and snapshot.get(r.question_id, {}).get("type") in MANUAL_GRADING_TYPES
            and r.score is None
        ]
        if finalize and pending:
            raise Unprocessable(
                f"仍有 {len(pending)} 道题未评分，不能终评",
                errors={"pendingQuestionIds": [r.question_id for r in pending]},
            )

        _score_attempt(attempt)
        attempt.version += 1
        if finalize:
            attempt.status = AttemptStatus.GRADED
            attempt.grading_status = GradingStatus.GRADED
        else:
            attempt.status = AttemptStatus.SUBMITTED
            attempt.grading_status = GradingStatus.GRADING
        attempt.save()

        # 保存草稿（未终评）不生成成绩，避免学生提前看到部分分数。
        score = None
        if finalize:
            score = Score.objects.filter(attempt=attempt).first()
            if score is None:
                score = Score.objects.filter(
                    assessment=attempt.assessment, student=attempt.student
                ).first()
            if score is None:
                from apps.exams.services.attempt import _upsert_score

                score = _upsert_score(attempt)
            score.objective_score = attempt.objective_score
            score.subjective_score = attempt.subjective_score
            score.total_score = attempt.total_score
            score.status = attempt.grading_status
            score.level = level_for(score.total_score, score.max_score)
            score.graded_at = timezone.now()
            score.save()
            ranking_service.recompute_ranks(attempt.assessment)

        GradingLog.objects.create(
            attempt=attempt,
            operator=user,
            action="finalize" if finalize else "submit",
            items=items,
            finalize=finalize,
            reason=data.get("reason") or "",
            version=attempt.version,
        )
        log_action(
            user, "grading.finalize" if finalize else "grading.submit",
            "attempt", attempt.id,
            data.get("reason") or "提交人工评分",
            {"items": items, "finalize": finalize, "version": attempt.version},
            request=request,
        )

    if finalize:
        from apps.exams.services import notification

        notification.notify(
            attempt.student,
            type=NotificationType.SYSTEM,
            title="测评成绩已发布",
            content=f"《{attempt.assessment.title}》已完成评分，可在“我的成绩”查看。",
            link="/student/results",
        )
        if score is not None:
            from apps.exams.services.achievement import after_score_released

            after_score_released(score)
    return attempt, score


REGRADE_ROLES = (
    Role.TEACHER,
    Role.SCHOOL_ADMIN,
    Role.DISTRICT_ADMIN,
    Role.CITY_ADMIN,
    Role.PROVINCE_ADMIN,
)


def _ensure_can_regrade(user, score):
    if user.role not in REGRADE_ROLES:
        raise Forbidden("无权重新判分")
    scope = DataScope(user)
    if scope.is_province_admin:
        return
    if user.role == Role.TEACHER:
        if not score.classroom_id or not scope.teaches_subject_in_class(
            score.classroom_id, score.subject
        ):
            raise Forbidden("只能重新判分本人任教班级该学科的成绩")
        return
    if score.school_id not in scope.school_ids:
        raise Forbidden("该成绩不在当前账号数据范围内")


def regrade_score(user, score, payload, request=None):
    from common.enums import ScoreSource
    from apps.exams.scope import DataScope
    from common.exceptions import BusinessError

    from apps.exams.serializers import RegradeSerializer

    serializer = RegradeSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    if score.attempt_id is None:
        raise Conflict("补录/导入成绩没有答卷，不支持重新判分，请重新补录")
    attempt = score.attempt
    _ensure_can_regrade(user, score)

    original = {
        "objectiveScore": score.objective_score,
        "subjectiveScore": score.subjective_score,
        "totalScore": score.total_score,
    }

    from apps.exams.services.attempt import grade_objective

    snapshot = {q["questionId"]: q for q in attempt.questions_snapshot}
    with transaction.atomic():
        objective = 0.0
        for row in attempt.answers.all():
            if row.scoring_mode != ScoringMode.AUTO:
                continue
            value, correct, graded = grade_objective(snapshot.get(row.question_id, {}), row.answer)
            row.score = value
            row.is_correct = correct
            row.graded_at = timezone.now()
            row.save(update_fields=["score", "is_correct", "graded_at", "updated_at"])
            objective += value or 0
        _score_attempt(attempt)
        # 保留人工已确认分数，仅重算客观题
        attempt.objective_score = round2(objective)
        attempt.total_score = round2(
            attempt.objective_score + attempt.subjective_score
        )
        attempt.version += 1
        attempt.save()

        score.objective_score = attempt.objective_score
        score.subjective_score = attempt.subjective_score
        score.total_score = attempt.total_score
        score.level = level_for(score.total_score, score.max_score)
        score.status = attempt.grading_status
        score.graded_at = timezone.now()
        score.save()
        ranking_service.recompute_ranks(score.assessment)
        GradingLog.objects.create(
            attempt=attempt, operator=user, action="regrade", items=[],
            finalize=True, reason=data["reason"], version=attempt.version,
        )
        log_action(
            user, "score.regrade", "score", score.id,
            data["reason"],
            {"before": original, "after": {
                "objectiveScore": score.objective_score,
                "subjectiveScore": score.subjective_score,
                "totalScore": score.total_score,
            }},
            request=request,
        )
    from apps.exams.services.achievement import after_score_released

    after_score_released(score)
    return score
