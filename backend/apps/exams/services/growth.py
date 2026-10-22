from datetime import datetime, time

from django.db.models import Avg
from django.utils import timezone
from django.utils.dateparse import parse_date

from common.enums import GradingStatus, PaperType, Role
from common.exceptions import BadRequest, Forbidden, NotFound
from apps.exams.scope import DataScope
from common.utils import date_str, round2, round4
from apps.exams.models import LearningReport, Score
from apps.exams.presenters import growth_payload, learning_report_payload


def _student(user, student_id):
    from apps.accounts.models import User

    student = (
        User.objects.select_related("org")
        .filter(pk=student_id, role=Role.STUDENT)
        .first()
    )
    if student is None:
        raise NotFound("学生不存在")
    if user.role == Role.STUDENT and student.id != user.id:
        raise Forbidden("无权查看他人成长数据")
    if user.role == Role.TEACHER:
        if not student.current_class_id or student.current_class_id not in DataScope(user).class_ids:
            raise Forbidden("无权查看该学生数据")
    elif user.role not in (Role.STUDENT, Role.TEACHER):
        scope = DataScope(user)
        if not scope.is_province_admin and student.school_id not in scope.school_ids:
            raise Forbidden("无权查看该学生数据")
    return student


def growth_curve(user, student_id, params):
    student = _student(user, student_id)
    subject = params.get("subject")
    if not subject:
        raise BadRequest("subject 必填")
    include_practice = str(params.get("includePractice", "")).lower() in ("1", "true", "yes")

    start_date = parse_date(params["startDate"]) if params.get("startDate") else None
    end_date = parse_date(params["endDate"]) if params.get("endDate") else None
    if params.get("startDate") and start_date is None:
        raise BadRequest("startDate 格式应为 YYYY-MM-DD")
    if params.get("endDate") and end_date is None:
        raise BadRequest("endDate 格式应为 YYYY-MM-DD")

    scores = Score.objects.select_related("assessment").filter(
        student=student,
        subject=subject,
        status=GradingStatus.GRADED,
    )
    if not include_practice:
        scores = scores.filter(assessment__paper_type=PaperType.FORMAL)
    tz = timezone.get_current_timezone()
    if start_date:
        scores = scores.filter(
            assessment__end_time__gte=timezone.make_aware(
                datetime.combine(start_date, time.min), tz
            )
        )
    if end_date:
        scores = scores.filter(
            assessment__end_time__lte=timezone.make_aware(
                datetime.combine(end_date, time.max), tz
            )
        )
    scores = scores.order_by("assessment__end_time", "id")

    points = []
    for score in scores:
        class_avg = Score.objects.filter(
            assessment=score.assessment, classroom_id=score.classroom_id,
            status=GradingStatus.GRADED,
        ).aggregate(value=Avg("total_score"))["value"]
        school_avg = Score.objects.filter(
            assessment=score.assessment, school_id=score.school_id,
            status=GradingStatus.GRADED,
        ).aggregate(value=Avg("total_score"))["value"]
        points.append({
            "assessmentId": score.assessment_id,
            "assessmentName": score.assessment.title,
            "date": date_str(score.assessment.end_time),
            "score": round2(score.total_score),
            "classAvg": round2(class_avg) if class_avg is not None else 0,
            "schoolAvg": round2(school_avg) if school_avg is not None else 0,
        })

    if points:
        latest = points[-1]["score"]
        first = points[0]["score"]
        avg = round2(sum(p["score"] for p in points) / len(points))
        best = round2(max(p["score"] for p in points))
        change_rate = round4((latest - first) / first) if first else 0.0
        if change_rate > 0.02:
            trend = "up"
        elif change_rate < -0.02:
            trend = "down"
        else:
            trend = "stable"
    else:
        latest = avg = best = 0
        change_rate = 0.0
        trend = "stable"

    return growth_payload(
        student,
        subject,
        start_date.isoformat() if start_date else (points[0]["date"] if points else ""),
        end_date.isoformat() if end_date else (points[-1]["date"] if points else date_str(timezone.now())),
        points,
        {
            "latestScore": latest,
            "avgScore": avg,
            "bestScore": best,
            "trend": trend,
            "changeRate": change_rate,
        },
    )


def learning_report(user, student_id, params):
    student = _student(user, student_id)
    qs = LearningReport.objects.filter(student=student)
    if params.get("reportId"):
        qs = qs.filter(report_id=params["reportId"])
    if params.get("subject"):
        qs = qs.filter(subject=params["subject"])
    report = qs.order_by("-generated_at").first()
    if report is None:
        raise NotFound("学情报告不存在，请先在后台生成")
    return learning_report_payload(report)
