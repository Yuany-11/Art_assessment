from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone

from common.audit import log_action
from common.enums import (
    AccountStatus,
    AssessmentStatus,
    PaperStatus,
    PaperType,
    Role,
    ScopeType,
)
from common.exceptions import BadRequest, Conflict, Forbidden, NotFound, Unprocessable
from apps.exams.scope import DataScope
from common.utils import round2
from apps.exams.models import (
    Assessment,
    AssessmentGrade,
    AssessmentTarget,
    Attempt,
    AttemptStatus,
    Paper,
)
from apps.exams.serializers import AssessmentCreateSerializer, WithdrawSerializer


def build_snapshot(paper):
    """发布/练习时冻结的题目快照。"""
    snapshot = []
    for row in paper.questions.all():
        snapshot.append({
            "questionId": row.question_id,
            "order": row.order,
            "sectionName": row.section_name,
            "type": row.type,
            "stem": row.stem,
            "score": round2(row.score),
            "maxScore": round2(row.score),
            "options": row.options or [],
            "resources": row.resources or [],
            "answer": row.answer or {},
            "ruleContext": (row.answer or {}).get("_ruleContext"),
            "analysis": row.analysis,
            "rubric": row.rubric,
            "scoringMode": row.scoring_mode,
        })
    return snapshot


def _target_name(target_type, target_id):
    from apps.classes.models import Class
    from apps.organizations.models import Organization

    if target_type == ScopeType.CLASS:
        obj = Class.objects.filter(pk=target_id, deleted_at__isnull=True).first()
    else:
        level = {
            ScopeType.SCHOOL: "school",
            ScopeType.DISTRICT: "district",
            ScopeType.CITY: "city",
            ScopeType.PROVINCE: "province",
        }.get(target_type)
        obj = (
            Organization.objects.filter(
                pk=target_id, level=level, deleted_at__isnull=True
            ).first()
            if level
            else None
        )
    if obj is None:
        raise NotFound(f"发布目标不存在：{target_type}/{target_id}")
    return obj.name


def _validate_targets(scope, target_type, target_ids):
    for target_id in target_ids:
        scope.ensure_paper_scope(target_type, target_id)


def students_for_target(target_type, target_ids, grades=None):
    from apps.accounts.models import User
    from apps.organizations.models import Organization

    qs = User.objects.filter(role=Role.STUDENT, status=AccountStatus.ACTIVE)
    school_ids = set()
    if target_type == ScopeType.CLASS:
        qs = qs.filter(student_profile__classroom_id__in=target_ids)
    else:
        if target_type == ScopeType.SCHOOL:
            school_ids = set(target_ids)
        elif target_type == ScopeType.DISTRICT:
            school_ids = set(
                Organization.objects.filter(
                    level="school", parent_id__in=target_ids, deleted_at__isnull=True
                ).values_list("id", flat=True)
            )
        elif target_type == ScopeType.CITY:
            school_ids = set(
                Organization.objects.filter(
                    level="school",
                    parent__parent_id__in=target_ids,
                    deleted_at__isnull=True,
                ).values_list("id", flat=True)
            )
        elif target_type == ScopeType.PROVINCE:
            school_ids = set(
                Organization.objects.filter(
                    level="school",
                    parent__parent__parent_id__in=target_ids,
                    deleted_at__isnull=True,
                ).values_list("id", flat=True)
            )
        else:
            return qs.none()
        qs = qs.filter(org_id__in=school_ids)
    if grades:
        qs = qs.filter(student_profile__grade__in=grades)
    return qs


def publish_assessment(user, payload, request=None):
    serializer = AssessmentCreateSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    scope = DataScope(user)

    paper = Paper.objects.filter(
        pk=data["paperId"], deleted_at__isnull=True
    ).select_related("creator").first()
    if paper is None:
        raise NotFound("试卷不存在")
    if not Paper.objects.filter(pk=paper.id).filter(scope.paper_q()).exists():
        raise Forbidden("无权发布该试卷")
    if paper.status in (PaperStatus.PUBLISHED, PaperStatus.ARCHIVED):
        raise Conflict("该试卷已被发布，如需再次使用请复制为新试卷")
    if paper.status != PaperStatus.READY:
        raise Conflict("只有已就绪（ready）的试卷才能发布")
    if paper.review_status in ("pending", "rejected"):
        raise Conflict("试卷尚未通过审核，不能发布")

    _validate_targets(scope, data["targetType"], data["targetIds"])
    if data["targetType"] == ScopeType.PROVINCE and user.role != Role.PROVINCE_ADMIN:
        raise Forbidden("仅省级管理员可发布全省测评")
    if user.role == Role.TEACHER and data["targetType"] != ScopeType.CLASS:
        raise Forbidden("教师只能发布到任教班级")

    snapshot = build_snapshot(paper)
    if not snapshot:
        raise Unprocessable("试卷没有题目，不能发布")

    target_names = [_target_name(data["targetType"], tid) for tid in data["targetIds"]]
    grades = data.get("targetGrades") or []
    participant_count = students_for_target(
        data["targetType"], data["targetIds"], grades
    ).count()

    with transaction.atomic():
        assessment = Assessment.objects.create(
            paper=paper,
            title=data["title"],
            subject=paper.subject,
            paper_type=paper.paper_type,
            target_type=data["targetType"],
            target_ids=data["targetIds"],
            target_names=target_names,
            target_grades=grades,
            start_time=data["startTime"],
            end_time=data["endTime"],
            duration=paper.duration,
            attempt_limit=data["attemptLimit"],
            shuffle_questions=data["shuffleQuestions"],
            shuffle_options=data["shuffleOptions"],
            show_answer_mode=data["showAnswerMode"],
            allow_late_submit=data["allowLateSubmit"],
            instructions=data.get("instructions"),
            status=AssessmentStatus.PUBLISHED,
            publisher=user,
            published_at=timezone.now(),
            question_snapshot=snapshot,
            max_score=round2(sum(q["score"] for q in snapshot)),
            participant_count=participant_count,
        )
        AssessmentTarget.objects.bulk_create([
            AssessmentTarget(
                assessment=assessment, target_type=data["targetType"],
                target_id=tid, target_name=name,
            )
            for tid, name in zip(data["targetIds"], target_names)
        ])
        AssessmentGrade.objects.bulk_create([
            AssessmentGrade(assessment=assessment, grade=g) for g in grades
        ])
        paper.status = PaperStatus.PUBLISHED
        paper.save(update_fields=["status", "updated_at"])
        log_action(
            user, "assessment.publish", "assessment", assessment.id,
            f"发布测评 {assessment.title}，目标 {target_names}",
            {"paperId": paper.id, "targetType": data["targetType"], "targetIds": data["targetIds"]},
            request=request,
        )
    return assessment


def student_visible_q(user):
    q = Q(pk__in=[])
    target_ids = []
    if user.current_class_id:
        target_ids.append((ScopeType.CLASS, user.current_class_id))
    if user.school_id:
        target_ids.append((ScopeType.SCHOOL, user.school_id))
    if user.school_id:
        target_ids.append((ScopeType.DISTRICT, user.district_id))
        target_ids.append((ScopeType.CITY, user.city_id))
        target_ids.append((ScopeType.PROVINCE, user.province_id))
    for target_type, target_id in target_ids:
        q |= Q(target_rows__target_type=target_type, target_rows__target_id=target_id)
    # 随机练习是个人练习，只有发起学生本人可见，避免同班同学互相看到/作答。
    q &= ~Q(paper_type=PaperType.PRACTICE) | Q(publisher=user)
    return q


def _student_can_access(user, assessment):
    if (
        assessment.paper_type == PaperType.PRACTICE
        and assessment.publisher_id != user.id
    ):
        return False
    target_pairs = []
    if user.current_class_id:
        target_pairs.append((ScopeType.CLASS, user.current_class_id))
    if user.school_id:
        target_pairs.append((ScopeType.SCHOOL, user.school_id))
        target_pairs.append((ScopeType.DISTRICT, user.district_id))
        target_pairs.append((ScopeType.CITY, user.city_id))
        target_pairs.append((ScopeType.PROVINCE, user.province_id))
    rows = set(assessment.target_rows.values_list("target_type", "target_id"))
    if not any(pair in rows for pair in target_pairs):
        return False
    if assessment.target_grades and user.grade not in assessment.target_grades:
        return False
    return True


def list_assessments(user, params):
    qs = Assessment.objects.select_related("paper", "publisher").prefetch_related(
        "target_rows", "grade_rows"
    )
    if user.role == Role.STUDENT:
        qs = qs.filter(student_visible_q(user))
        if user.grade:
            qs = qs.filter(Q(grade_rows__isnull=True) | Q(grade_rows__grade=user.grade))
        qs = qs.distinct().prefetch_related(
            Prefetch(
                "attempts",
                queryset=Attempt.objects.filter(student=user).order_by("-attempt_no"),
                to_attr="my_attempts",
            )
        )
    else:
        scope = DataScope(user)
        if not scope.is_province_admin:
            q = Q(pk__in=[])
            for target_type in (ScopeType.CLASS, ScopeType.SCHOOL,
                                ScopeType.DISTRICT, ScopeType.CITY):
                allowed = {
                    ScopeType.CLASS: scope.class_ids,
                    ScopeType.SCHOOL: scope.school_ids,
                    ScopeType.DISTRICT: scope.district_ids,
                    ScopeType.CITY: scope.city_ids,
                }[target_type]
                if allowed:
                    q |= Q(target_rows__target_type=target_type,
                           target_rows__target_id__in=allowed)
            q |= Q(publisher=user)
            qs = qs.filter(q).distinct()

    mapping = {
        "subject": "subject",
        "status": "status",
        "paperType": "paper_type",
        "targetType": "target_type",
    }
    for param, field in mapping.items():
        if params.get(param):
            qs = qs.filter(**{field: params[param]})
    if params.get("keyword"):
        qs = qs.filter(title__icontains=params["keyword"])
    return qs.order_by("-published_at")


def get_assessment(user, assessment_id):
    assessment = (
        Assessment.objects.select_related("paper", "publisher")
        .prefetch_related("target_rows", "grade_rows")
        .filter(pk=assessment_id)
        .first()
    )
    if assessment is None:
        raise NotFound("测评不存在")
    if user.role == Role.STUDENT:
        if not _student_can_access(user, assessment):
            raise Forbidden("无权访问该测评")
        return assessment
    scope = DataScope(user)
    if scope.is_province_admin:
        return assessment
    if assessment.publisher_id == user.id:
        return assessment
    allowed = {
        ScopeType.CLASS: scope.class_ids,
        ScopeType.SCHOOL: scope.school_ids,
        ScopeType.DISTRICT: scope.district_ids,
        ScopeType.CITY: scope.city_ids,
    }.get(assessment.target_type, set())
    if not set(assessment.target_ids or []) & allowed:
        raise Forbidden("无权访问该测评")
    return assessment


def withdraw_assessment(user, assessment, payload, request=None):
    serializer = WithdrawSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    reason = serializer.validated_data["reason"]
    scope = DataScope(user)
    if user.role == Role.STUDENT:
        raise Forbidden("学生不能撤回测评")
    if not scope.is_province_admin and assessment.publisher_id != user.id:
        allowed = {
            ScopeType.CLASS: scope.class_ids,
            ScopeType.SCHOOL: scope.school_ids,
            ScopeType.DISTRICT: scope.district_ids,
            ScopeType.CITY: scope.city_ids,
        }.get(assessment.target_type, set())
        if not set(assessment.target_ids or []) & allowed:
            raise Forbidden("无权撤回该测评")
        if user.role == Role.TEACHER:
            raise Forbidden("教师只能撤回本人发布的测评")
    if assessment.status != AssessmentStatus.PUBLISHED:
        raise Conflict("只有已发布且未结束的测评可以撤回")
    if assessment.end_time <= timezone.now():
        raise Conflict("测评已结束，不能撤回")

    from apps.exams.services import attempt as attempt_service

    with transaction.atomic():
        assessment.status = AssessmentStatus.WITHDRAWN
        assessment.withdrawn_at = timezone.now()
        assessment.withdraw_reason = reason
        assessment.save(update_fields=["status", "withdrawn_at", "withdraw_reason", "updated_at"])
        attempts = assessment.attempts.filter(status=AttemptStatus.IN_PROGRESS)
        for attempt in attempts:
            attempt_service.auto_submit_attempt(attempt, reason="assessment_withdrawn")
        log_action(
            user, "assessment.withdraw", "assessment", assessment.id,
            f"撤回测评 {assessment.title}：{reason}", {"reason": reason}, request=request,
        )
    return assessment


def finish_expired_assessments():
    """定时任务：结束已到结束时间的测评。"""
    now = timezone.now()
    qs = Assessment.objects.filter(
        status=AssessmentStatus.PUBLISHED, end_time__lte=now
    )
    count = 0
    for assessment in qs.iterator():
        assessment.status = AssessmentStatus.FINISHED
        assessment.finished_at = now
        assessment.save(update_fields=["status", "finished_at", "updated_at"])
        count += 1
    return count


def can_start(assessment, user):
    if assessment.status != AssessmentStatus.PUBLISHED:
        raise Conflict("测评未发布或已撤回，不能作答")
    now = timezone.now()
    if now < assessment.start_time:
        raise Conflict("测评尚未开始")
    if now >= assessment.end_time:
        raise Conflict("测评已结束")
    if user.role != Role.STUDENT:
        raise Forbidden("仅学生可以作答")
    if not _student_can_access(user, assessment):
        raise Forbidden("该测评未发布给当前学生")
    return True


def attempt_count(assessment, student):
    return Attempt.objects.filter(assessment=assessment, student=student).count()
