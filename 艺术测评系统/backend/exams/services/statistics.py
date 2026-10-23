import io
from datetime import datetime, time

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date

from common.enums import (
    AccountStatus,
    AttemptStatus,
    GradingStatus,
    Role,
    ScopeType,
)
from common.exceptions import BadRequest, Forbidden, NotFound, Unprocessable
from common.scope import DataScope
from common.utils import round2, round4
from exams.models import Assessment, Attempt, Score
from exams.services import assessment as assessment_service
from exams.services.assessment import students_for_target

DIMENSION_TARGET_MODEL = {
    ScopeType.CLASS: ("accounts.models", "Class"),
    ScopeType.SCHOOL: ("accounts.models", "School"),
    ScopeType.DISTRICT: ("accounts.models", "District"),
    ScopeType.CITY: ("accounts.models", "City"),
    ScopeType.PROVINCE: ("accounts.models", "Province"),
}

GROUP_PERMISSIONS = {
    Role.TEACHER: {ScopeType.CLASS},
    Role.SCHOOL_ADMIN: {ScopeType.CLASS, ScopeType.SCHOOL},
    Role.DISTRICT_ADMIN: {ScopeType.CLASS, ScopeType.SCHOOL, ScopeType.DISTRICT},
    Role.CITY_ADMIN: {ScopeType.CLASS, ScopeType.SCHOOL, ScopeType.DISTRICT, ScopeType.CITY},
    Role.PROVINCE_ADMIN: {ScopeType.CLASS, ScopeType.SCHOOL, ScopeType.DISTRICT, ScopeType.CITY},
}

DIMENSION_ASSESSMENT = "assessment"

DISTRIBUTION_BINS = [
    ("90-100", 90, 101),
    ("80-89", 80, 90),
    ("70-79", 70, 80),
    ("60-69", 60, 70),
    ("0-59", 0, 60),
]


def _model_for(dimension):
    module_name, class_name = DIMENSION_TARGET_MODEL[dimension]
    module = __import__(module_name, fromlist=[class_name])
    return getattr(module, class_name)


def _target_name(dimension, target_id):
    model = _model_for(dimension)
    obj = model.objects.filter(pk=target_id).first()
    if obj is None:
        raise NotFound("统计对象不存在")
    return obj.name


def _ensure_dimension_scope(scope, dimension, target_id):
    if dimension == ScopeType.PROVINCE:
        if scope.is_province_admin:
            return
        raise Forbidden("无权查看全省统计")
    if dimension == ScopeType.CITY:
        if target_id not in scope.city_ids:
            raise Forbidden("无权查看该市州统计")
    elif dimension == ScopeType.DISTRICT:
        if target_id not in scope.district_ids:
            raise Forbidden("无权查看该区县统计")
    elif dimension == ScopeType.SCHOOL:
        if target_id not in scope.school_ids:
            raise Forbidden("无权查看该学校统计")
    elif dimension == ScopeType.CLASS:
        scope.ensure_class(target_id)
    elif dimension == DIMENSION_ASSESSMENT:
        return


def _date_range(params):
    start = parse_date(params["startDate"]) if params.get("startDate") else None
    end = parse_date(params["endDate"]) if params.get("endDate") else None
    if params.get("startDate") and start is None:
        raise BadRequest("startDate 格式应为 YYYY-MM-DD")
    if params.get("endDate") and end is None:
        raise BadRequest("endDate 格式应为 YYYY-MM-DD")
    tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(datetime.combine(start, time.min), tz) if start else None
    end_dt = timezone.make_aware(datetime.combine(end, time.max), tz) if end else None
    return start_dt, end_dt


def _assessments_qs(user, params):
    if params.get("assessmentId"):
        assessment = assessment_service.get_assessment(user, int(params["assessmentId"]))
        return Assessment.objects.filter(pk=assessment.pk), assessment
    qs = assessment_service.list_assessments(user, {"subject": params.get("subject")})
    start_dt, end_dt = _date_range(params)
    if start_dt:
        qs = qs.filter(end_time__gte=start_dt)
    if end_dt:
        qs = qs.filter(end_time__lte=end_dt)
    return qs, None


def _candidates(dimension, target_id, grade, assessment=None):
    from accounts.models import User

    qs = User.objects.filter(role=Role.STUDENT, status=AccountStatus.ACTIVE)
    if dimension == DIMENSION_ASSESSMENT:
        qs = students_for_target(
            assessment.target_type, assessment.target_ids, assessment.target_grades
        )
    elif dimension == ScopeType.CLASS:
        qs = qs.filter(current_class_id=target_id)
    elif dimension == ScopeType.SCHOOL:
        qs = qs.filter(school_id=target_id)
    elif dimension == ScopeType.DISTRICT:
        qs = qs.filter(school__district_id=target_id)
    elif dimension == ScopeType.CITY:
        qs = qs.filter(school__district__city_id=target_id)
    elif dimension == ScopeType.PROVINCE:
        qs = qs.filter(school__district__city__province_id=target_id)
    else:
        return qs.none()
    if grade:
        qs = qs.filter(grade=grade)
    if assessment is not None and dimension != DIMENSION_ASSESSMENT:
        target_ids = students_for_target(
            assessment.target_type, assessment.target_ids, assessment.target_grades
        ).values_list("id", flat=True)
        qs = qs.filter(id__in=target_ids)
    return qs


def _scores_qs(dimension, target_id, assessments, subject, grade, assessment=None):
    qs = Score.objects.filter(
        status=GradingStatus.GRADED, assessment__in=assessments
    )
    if dimension == DIMENSION_ASSESSMENT:
        qs = qs.filter(assessment=assessment)
    elif dimension == ScopeType.CLASS:
        qs = qs.filter(classroom_id=target_id)
    elif dimension == ScopeType.SCHOOL:
        qs = qs.filter(school_id=target_id)
    elif dimension == ScopeType.DISTRICT:
        qs = qs.filter(school__district_id=target_id)
    elif dimension == ScopeType.CITY:
        qs = qs.filter(school__district__city_id=target_id)
    elif dimension == ScopeType.PROVINCE:
        qs = qs.filter(school__district__city__province_id=target_id)
    if subject:
        qs = qs.filter(subject=subject)
    if grade:
        qs = qs.filter(grade=grade)
    return qs


def _attempts_qs(assessments, dimension, target_id, candidate_ids, subject=None):
    qs = Attempt.objects.filter(assessment__in=assessments, student_id__in=candidate_ids)
    if subject:
        qs = qs.filter(assessment__subject=subject)
    if dimension == ScopeType.CLASS:
        qs = qs.filter(student__current_class_id=target_id)
    elif dimension == ScopeType.SCHOOL:
        qs = qs.filter(student__school_id=target_id)
    elif dimension == ScopeType.DISTRICT:
        qs = qs.filter(student__school__district_id=target_id)
    elif dimension == ScopeType.CITY:
        qs = qs.filter(student__school__district__city_id=target_id)
    elif dimension == ScopeType.PROVINCE:
        qs = qs.filter(student__school__district__city__province_id=target_id)
    return qs


def _distribution(scores):
    bins = {label: 0 for label, _, _ in DISTRIBUTION_BINS}
    for score in scores:
        if not score.max_score:
            percent = 0
        else:
            percent = score.total_score / score.max_score * 100
        for label, low, high in DISTRIBUTION_BINS:
            if low <= percent < high:
                bins[label] += 1
                break
    return [{"range": label, "count": bins[label]} for label, _, _ in DISTRIBUTION_BINS]


def _rate(count, denominator):
    return round4(count / denominator) if denominator else 0.0


def compute_overview(*, dimension, target_id, target_name, assessments, assessment,
                     subject, grade, candidate_qs, assessment_id=None):
    candidate_ids = list(candidate_qs.values_list("id", flat=True))
    scores = list(
        _scores_qs(dimension, target_id, assessments, subject, grade, assessment)
        .filter(student_id__in=candidate_ids)
    )
    attempts = _attempts_qs(assessments, dimension, target_id, candidate_ids, subject)
    # 补录/导入成绩没有答卷，也应计入参与与提交人数
    participant_ids = set(
        attempts.values_list("student_id", flat=True)
    ) | {s.student_id for s in scores}
    submitted_ids = set(
        attempts.filter(
            status__in=[AttemptStatus.SUBMITTED, AttemptStatus.GRADED]
        ).values_list("student_id", flat=True)
    ) | {s.student_id for s in scores}
    participants = len(participant_ids)
    submitted = len(submitted_ids)

    graded = len(scores)
    total_scores = [s.total_score for s in scores]
    avg = round2(sum(total_scores) / graded) if graded else 0
    highest = round2(max(total_scores)) if graded else 0
    lowest = round2(min(total_scores)) if graded else 0
    levels = [s.level for s in scores]
    excellent = levels.count("excellent")
    good = levels.count("good")
    passed = excellent + good + levels.count("pass")

    by_subject = []
    subjects = sorted({s.subject for s in scores}) if not subject else [subject]
    for subj in subjects:
        subj_scores = [s for s in scores if s.subject == subj]
        subj_attempts = _attempts_qs(
            assessments, dimension, target_id, candidate_ids, subj
        )
        subj_participants = len(
            set(subj_attempts.values_list("student_id", flat=True))
            | {s.student_id for s in subj_scores}
        )
        by_subject.append({
            "subject": subj,
            "avgScore": round2(sum(s.total_score for s in subj_scores) / len(subj_scores))
            if subj_scores else 0,
            "participationRate": _rate(subj_participants, len(candidate_ids)),
        })

    return {
        "dimension": dimension,
        "targetId": target_id,
        "targetName": target_name,
        "rank": None,
        "assessmentId": assessment_id,
        "subject": subject or (assessment.subject if assessment else ""),
        "studentCount": len(candidate_ids),
        "participantCount": participants,
        "submittedCount": submitted,
        "participationRate": _rate(participants, len(candidate_ids)),
        "avgScore": avg,
        "highestScore": highest,
        "lowestScore": lowest,
        "excellentRate": _rate(excellent, graded),
        "goodRate": _rate(good, graded),
        "passRate": _rate(passed, graded),
        "distribution": _distribution(scores),
        "bySubject": by_subject,
    }


def stat_overview(user, params):
    if user.role in (Role.STUDENT, Role.QUESTION_ADMIN):
        raise Forbidden("无权查看统计")
    dimension = params.get("dimension")
    if dimension not in {*ScopeType.values, DIMENSION_ASSESSMENT}:
        raise BadRequest("dimension 不合法")
    scope = DataScope(user)
    assessments, assessment = _assessments_qs(user, params)
    subject = params.get("subject")
    grade = int(params["grade"]) if params.get("grade") else None

    if dimension == DIMENSION_ASSESSMENT:
        if assessment is None:
            raise BadRequest("dimension=assessment 时必须传 assessmentId")
        target_id = assessment.id
        target_name = assessment.title
    else:
        target_id = int(params["targetId"]) if params.get("targetId") else None
        if dimension == ScopeType.PROVINCE:
            target_id = target_id or scope.province_id
        if not target_id:
            raise BadRequest("targetId 必填")
        _ensure_dimension_scope(scope, dimension, target_id)
        target_name = _target_name(dimension, target_id)
        if assessment is not None:
            assessments = Assessment.objects.filter(pk=assessment.pk)

    candidates = _candidates(dimension, target_id, grade, assessment)
    return compute_overview(
        dimension=dimension,
        target_id=target_id,
        target_name=target_name,
        assessments=assessments,
        assessment=assessment,
        subject=subject,
        grade=grade,
        candidate_qs=candidates,
        assessment_id=assessment.id if assessment else None,
    )


def _group_targets(user, group_by, parent_id, keyword=None):
    from accounts.models import Class, District, City, School

    scope = DataScope(user)
    if group_by not in GROUP_PERMISSIONS.get(user.role, set()):
        raise Forbidden("当前角色不支持该分组维度")

    if group_by == ScopeType.CLASS:
        qs = Class.objects.filter(deleted_at__isnull=True)
        if user.role == Role.TEACHER:
            qs = qs.filter(id__in=scope.class_ids)
        elif scope.is_province_admin:
            pass
        elif scope.is_city_admin:
            qs = qs.filter(school__district__city_id=scope.city_id)
        elif scope.is_district_admin:
            qs = qs.filter(school__district_id=scope.district_id)
        else:
            qs = qs.filter(school_id=scope.school_id)
        if parent_id:
            qs = qs.filter(school_id=parent_id)
        return [(c.id, c.name) for c in qs.order_by("grade", "name")]

    if group_by == ScopeType.SCHOOL:
        qs = School.objects.all()
        if scope.is_city_admin:
            qs = qs.filter(district__city_id=scope.city_id)
        elif scope.is_district_admin:
            qs = qs.filter(district_id=scope.district_id)
        elif scope.school_id and not scope.is_province_admin:
            qs = qs.filter(id=scope.school_id)
        if parent_id:
            qs = qs.filter(district_id=parent_id)
        if keyword:
            qs = qs.filter(name__icontains=keyword)
        return [(s.id, s.name) for s in qs.order_by("id")]

    if group_by == ScopeType.DISTRICT:
        qs = District.objects.all()
        if scope.is_city_admin:
            qs = qs.filter(city_id=scope.city_id)
        if parent_id:
            qs = qs.filter(city_id=parent_id)
        if keyword:
            qs = qs.filter(name__icontains=keyword)
        return [(d.id, d.name) for d in qs.order_by("id")]

    if group_by == ScopeType.CITY:
        qs = City.objects.all()
        if not scope.is_province_admin:
            qs = qs.filter(id__in=scope.city_ids)
        if keyword:
            qs = qs.filter(name__icontains=keyword)
        return [(c.id, c.name) for c in qs.order_by("id")]

    raise BadRequest("groupBy 不合法")


def stat_list_rows(user, params):
    group_by = params.get("groupBy")
    if group_by not in {ScopeType.CLASS, ScopeType.SCHOOL, ScopeType.DISTRICT, ScopeType.CITY}:
        raise BadRequest("groupBy 必须为 class/school/district/city")
    scope = DataScope(user)
    parent_id = int(params["parentId"]) if params.get("parentId") else None
    if parent_id:
        if group_by == ScopeType.CLASS:
            scope.ensure_school(parent_id)
        elif group_by == ScopeType.SCHOOL:
            if parent_id not in scope.district_ids:
                raise Forbidden("无权查看该区县统计")
        elif group_by == ScopeType.DISTRICT:
            if parent_id not in scope.city_ids:
                raise Forbidden("无权查看该市州统计")

    assessments, assessment = _assessments_qs(user, params)
    subject = params.get("subject")
    grade = int(params["grade"]) if params.get("grade") else None
    targets = _group_targets(user, group_by, parent_id, params.get("keyword"))

    rows = []
    for target_id, target_name in targets:
        candidates = _candidates(group_by, target_id, grade, assessment)
        row = compute_overview(
            dimension=group_by,
            target_id=target_id,
            target_name=target_name,
            assessments=assessments,
            assessment=assessment,
            subject=subject,
            grade=grade,
            candidate_qs=candidates,
            assessment_id=assessment.id if assessment else None,
        )
        rows.append(row)

    sort_by = params.get("sortBy") or "avgScore"
    sort_order = params.get("sortOrder") or "desc"
    if sort_by not in {
        "avgScore", "participationRate", "passRate", "excellentRate", "studentCount"
    }:
        raise BadRequest("sortBy 不合法")
    if sort_order not in ("asc", "desc"):
        raise BadRequest("sortOrder 必须为 asc/desc")
    rows.sort(key=lambda r: r["targetId"])
    rows.sort(key=lambda r: r[sort_by], reverse=(sort_order == "desc"))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def export_xlsx(user, params):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    if params.get("groupBy"):
        rows = stat_list_rows(user, params)
        ws.title = "区域统计"
        headers = [
            "排名", "统计维度", "对象ID", "对象名称", "测评ID", "学科", "应参与人数",
            "参与人数", "已提交人数", "参与率", "平均分", "最高分", "最低分",
            "优秀率", "良好率", "合格率",
        ]
        ws.append(headers)
        for row in rows:
            ws.append([
                row["rank"], row["dimension"], row["targetId"], row["targetName"],
                row["assessmentId"], row["subject"], row["studentCount"],
                row["participantCount"], row["submittedCount"], row["participationRate"],
                row["avgScore"], row["highestScore"], row["lowestScore"],
                row["excellentRate"], row["goodRate"], row["passRate"],
            ])
        filename = f"score-statistics-{timezone.localdate():%Y%m%d}.xlsx"
        return wb, filename

    dimension = params.get("dimension")
    if dimension == "student":
        from accounts.models import User

        student_id = int(params.get("targetId") or 0)
        student = User.objects.filter(pk=student_id, role=Role.STUDENT).first()
        if student is None:
            raise NotFound("学生不存在")
        if user.role == Role.STUDENT:
            raise Forbidden("学生请使用本人成绩接口")
        scope = DataScope(user)
        if not scope.is_province_admin and student.school_id not in scope.school_ids:
            raise Forbidden("无权导出该学生成绩")
        if user.role == Role.TEACHER and student.current_class_id not in scope.class_ids:
            raise Forbidden("无权导出该学生成绩")
        scores = Score.objects.select_related("assessment").filter(
            student=student, status=GradingStatus.GRADED,
            assessment__paper_type="formal",
        ).order_by("created_at")
        ws.title = "学生成绩"
        ws.append(["测评名称", "学科", "总分", "等级", "班级排名", "年级排名", "完成时间"])
        for score in scores:
            ws.append([
                score.assessment.title, score.subject, score.total_score, score.level,
                score.class_rank, score.grade_rank,
                score.graded_at.strftime("%Y-%m-%d %H:%M:%S") if score.graded_at else "",
            ])
        filename = f"student-{student.id}-scores.xlsx"
        return wb, filename

    overview = stat_overview(user, params)
    ws.title = "成绩统计"
    ws.append([
        "统计维度", "对象名称", "学科", "应参与人数", "参与人数", "已提交人数",
        "参与率", "平均分", "最高分", "最低分", "优秀率", "良好率", "合格率",
    ])
    ws.append([
        overview["dimension"], overview["targetName"], overview["subject"],
        overview["studentCount"], overview["participantCount"], overview["submittedCount"],
        overview["participationRate"], overview["avgScore"], overview["highestScore"],
        overview["lowestScore"], overview["excellentRate"], overview["goodRate"],
        overview["passRate"],
    ])
    ws.append([])
    ws.append(["分数段", "人数"])
    for item in overview["distribution"]:
        ws.append([item["range"], item["count"]])
    filename = f"score-statistics-{timezone.localdate():%Y%m%d}.xlsx"
    return wb, filename


def export_xlsx_bytes(user, params):
    wb, filename = export_xlsx(user, params)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue(), filename
