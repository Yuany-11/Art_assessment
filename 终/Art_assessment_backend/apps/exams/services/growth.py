from datetime import datetime, time

from django.db.models import Avg
from django.utils import timezone
from django.utils.dateparse import parse_date

from common.enums import GradingStatus, PaperType, QuestionType, Role, Subject
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


def _type_performance(scores):
    """按题型汇总得分率，用于生成优势/薄弱项。"""
    buckets = {}
    for score in scores:
        attempt = getattr(score, "attempt", None)
        if attempt is None:
            continue
        snapshot = {q.get("questionId"): q for q in attempt.questions_snapshot or []}
        for row in attempt.answers.all():
            question = snapshot.get(row.question_id)
            if not question or not row.max_score:
                continue
            key = question.get("type") or ""
            bucket = buckets.setdefault(key, {"earned": 0.0, "max": 0.0})
            bucket["earned"] += row.score or 0
            bucket["max"] += row.max_score or 0
    result = {}
    for key, bucket in buckets.items():
        if bucket["max"]:
            result[key] = bucket["earned"] / bucket["max"]
    return result


def _build_learning_report(student, subject):
    scores = list(
        Score.objects.select_related("assessment", "attempt")
        .prefetch_related("attempt__answers")
        .filter(
            student=student,
            subject=subject,
            status=GradingStatus.GRADED,
            assessment__paper_type=PaperType.FORMAL,
        )
        .order_by("assessment__end_time", "id")
    )
    if not scores:
        return None

    points = [
        {
            "assessmentId": score.assessment_id,
            "assessmentName": score.assessment.title,
            "date": date_str(score.assessment.end_time),
            "score": round2(score.total_score),
        }
        for score in scores
    ]
    latest = points[-1]["score"]
    first = points[0]["score"]
    avg = round2(sum(point["score"] for point in points) / len(points))
    change = round2(latest - first)

    labels = {value: label for value, label in QuestionType.choices}
    performance = _type_performance(scores)
    ranked = sorted(performance.items(), key=lambda item: item[1], reverse=True)
    strengths = [
        f"{labels.get(key, key)}掌握较好（得分率 {round(rate * 100)}%）"
        for key, rate in ranked if rate >= 0.8
    ][:3]
    weaknesses = [
        f"{labels.get(key, key)}得分率偏低（{round(rate * 100)}%）"
        for key, rate in sorted(performance.items(), key=lambda item: item[1])
        if rate < 0.6
    ][:3]
    if not strengths:
        strengths = [f"已完成 {len(points)} 次正式测评，学习记录完整"]
    if not weaknesses:
        weaknesses = ["暂无明显薄弱题型，建议继续巩固综合表现"]

    suggestions = []
    if weaknesses and performance:
        weak_label = labels.get(
            sorted(performance.items(), key=lambda item: item[1])[0][0], "薄弱题型"
        )
        suggestions.append(f"针对{weak_label}进行专项练习，并复盘对应错题。")
    if change >= 1:
        suggestions.append(f"最近一次成绩较首次提升 {change} 分，建议保持当前学习节奏。")
    elif change <= -1:
        suggestions.append(f"最近一次成绩较首次下降 {abs(change)} 分，建议回顾失分题型并寻求教师指导。")
    else:
        suggestions.append("成绩总体稳定，可通过随机练习扩大题型覆盖面。")
    suggestions.append("每周至少完成一次随机练习，及时订正错题本中的题目。")

    summary = (
        f"已完成 {len(points)} 次正式测评，平均分 {avg} 分，"
        f"最新一次 {latest} 分，较首次{'提升' if change > 0 else '下降' if change < 0 else '持平'}"
        f"{abs(change) if change else ''} 分。"
    )
    raw_text = "\n".join(
        [summary, "优势表现：", *[f"- {item}" for item in strengths],
         "需要加强：", *[f"- {item}" for item in weaknesses],
         "学习建议：", *[f"- {item}" for item in suggestions]]
    )
    report, _ = LearningReport.objects.update_or_create(
        report_id=f"RPT-{student.id}-{subject}",
        defaults={
            "student": student,
            "subject": subject,
            "summary": summary,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "suggestions": suggestions,
            "score_trend": points,
            "raw_text": raw_text,
            "model_version": "rule-v1",
        },
    )
    return report


def learning_report(user, student_id, params):
    student = _student(user, student_id)
    qs = LearningReport.objects.filter(student=student)
    if params.get("reportId"):
        qs = qs.filter(report_id=params["reportId"])
    if params.get("subject"):
        qs = qs.filter(subject=params["subject"])
    report = qs.order_by("-generated_at").first()
    subject = params.get("subject") or (report.subject if report else None)
    if subject in Subject.values:
        latest_graded = (
            Score.objects.filter(
                student=student,
                subject=subject,
                status=GradingStatus.GRADED,
                assessment__paper_type=PaperType.FORMAL,
            )
            .order_by("-graded_at")
            .values_list("graded_at", flat=True)
            .first()
        )
        # 有新成绩后重新生成，避免学情报告长期停留在旧数据。
        if report is None or (
            latest_graded is not None and latest_graded > report.generated_at
        ):
            report = _build_learning_report(student, subject)
    if report is None:
        raise NotFound("暂无学情报告，完成正式测评后可查看")
    return learning_report_payload(report)
