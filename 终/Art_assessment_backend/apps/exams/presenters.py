"""响应对象构造。字段命名严格遵循 api.md 4.1 的模型定义。"""
from django.db.models import Count, Q

from common.enums import AttemptStatus, QuestionType, Role, ScoringMode
from common.utils import date_str, iso, round2, round4


def _question_options(rows):
    return [
        {
            "key": row.get("key", ""),
            "text": row.get("text", ""),
            "mediaUrl": row.get("mediaUrl") or row.get("media_url"),
        }
        for row in rows or []
    ]


def _question_resources(rows):
    return [
        {
            "type": row.get("type", ""),
            "url": row.get("url", ""),
            "name": row.get("name", ""),
        }
        for row in rows or []
    ]


def _answer_config(qtype, answer):
    if qtype == QuestionType.FILL_BLANK:
        values = (answer or {}).get("values") or []
        return {"blankCount": max(1, len(values))}
    if qtype in (QuestionType.SHORT_ANSWER, QuestionType.IMAGE_UPLOAD, QuestionType.AUDIO_UPLOAD):
        return {"maxLength": 500}
    return {}


def paper_item(paper):
    return {
        "id": paper.id,
        "title": paper.title,
        "subject": paper.subject,
        "paperType": paper.paper_type,
        "grade": paper.grade,
        "scopeType": paper.scope_type,
        "scopeId": paper.scope_id,
        "scopeName": paper.scope_name,
        "totalScore": round2(paper.total_score),
        "questionCount": paper.question_count,
        "duration": paper.duration,
        "generateMode": paper.generate_mode,
        "status": paper.status,
        "reviewStatus": paper.review_status,
        "reviewComment": paper.review_comment,
        "reviewerId": paper.reviewer_id,
        "reviewerName": getattr(paper.reviewer, "real_name", None),
        "submittedAt": iso(paper.submitted_at),
        "reviewedAt": iso(paper.reviewed_at),
        "version": paper.version,
        "creatorId": paper.creator_id,
        "creatorName": getattr(paper.creator, "real_name", ""),
        "createdAt": iso(paper.created_at),
        "updatedAt": iso(paper.updated_at),
    }


def paper_detail(paper):
    data = paper_item(paper)
    data["instructions"] = paper.instructions
    data["questions"] = [
        {
            "questionId": q.question_id,
            "order": q.order,
            "sectionName": q.section_name,
            "type": q.type,
            "stem": q.stem,
            "score": round2(q.score),
            "options": q.options or [],
            "resources": q.resources or [],
            "analysis": q.analysis,
            "rubric": q.rubric,
            "scoringMode": q.scoring_mode,
        }
        for q in paper.questions.all()
    ]
    return data


def assessment_item(assessment, user=None):
    submitted = (
        assessment.attempts.filter(
            status__in=[AttemptStatus.SUBMITTED, AttemptStatus.GRADED, AttemptStatus.INVALID]
        )
        .values("student_id")
        .distinct()
        .count()
    )
    data = {
        "id": assessment.id,
        "title": assessment.title,
        "paperId": assessment.paper_id,
        "paperTitle": assessment.paper.title,
        "totalScore": round2(assessment.paper.total_score),
        "subject": assessment.subject,
        "paperType": assessment.paper_type,
        "targetType": assessment.target_type,
        "targetIds": assessment.target_ids or [],
        "targetNames": assessment.target_names or [],
        "targetGrades": assessment.target_grades or [],
        "startTime": iso(assessment.start_time),
        "endTime": iso(assessment.end_time),
        "duration": assessment.duration,
        "attemptLimit": assessment.attempt_limit,
        "showAnswerMode": assessment.show_answer_mode,
        "status": assessment.status,
        "publisherId": assessment.publisher_id,
        "publisherName": getattr(assessment.publisher, "real_name", ""),
        "publishedAt": iso(assessment.published_at),
        "participantCount": assessment.participant_count,
        "submittedCount": submitted,
        "myAttempt": None,
    }
    if user is not None and user.role == Role.STUDENT:
        attempts = getattr(assessment, "my_attempts", None)
        if attempts is None:
            attempt = (
                assessment.attempts.filter(student=user)
                .order_by("-attempt_no")
                .first()
            )
        else:
            attempt = attempts[0] if attempts else None
        if attempt is not None:
            data["myAttempt"] = {
                "attemptId": attempt.id,
                "status": attempt.status,
                "attemptNo": attempt.attempt_no,
                "remainingSeconds": attempt.remaining_seconds,
            }
    return data


def attempt_question(snapshot):
    qtype = snapshot.get("type", "")
    answer = snapshot.get("answer") or {}
    return {
        "questionId": snapshot["questionId"],
        "order": snapshot["order"],
        "type": qtype,
        "stem": snapshot.get("stem", ""),
        "score": round2(snapshot.get("score", 0)),
        "options": _question_options(snapshot.get("options")),
        "resources": _question_resources(snapshot.get("resources")),
        "answerConfig": snapshot.get("answerConfig") or _answer_config(qtype, answer),
    }


def attempt_detail(attempt):
    answers = []
    for row in attempt.answers.all():
        if row.answer is not None:
            answers.append({
                "questionId": row.question_id,
                "answer": row.answer,
                "updatedAt": iso(row.updated_at),
            })
    return {
        "attemptId": attempt.id,
        "assessmentId": attempt.assessment_id,
        "paperId": attempt.paper_id,
        "title": attempt.assessment.title,
        "subject": attempt.assessment.subject,
        "attemptNo": attempt.attempt_no,
        "status": attempt.status,
        "startedAt": iso(attempt.started_at),
        "deadline": iso(attempt.deadline),
        "serverTime": iso(__import__("django.utils.timezone", fromlist=["now"]).now()),
        "remainingSeconds": attempt.remaining_seconds,
        "totalScore": round2(attempt.assessment.max_score),
        "questions": [attempt_question(q) for q in attempt.questions_snapshot],
        "savedAnswers": answers,
    }


def submit_result(attempt, message=None):
    from apps.exams.models import Score

    graded = attempt.grading_status == "graded"
    if message is None:
        message = "交卷成功"
        if attempt.grading_status == "grading":
            message = "交卷成功，简答题等待教师评分，评分完成后公布成绩"
        elif attempt.grading_status == "failed":
            message = "交卷成功，AI 评分失败，等待教师人工评分"
    score_id = (
        Score.objects.filter(attempt=attempt).values_list("id", flat=True).first()
        if graded
        else None
    )
    return {
        "attemptId": attempt.id,
        "scoreId": score_id,
        "status": attempt.status,
        "submittedAt": iso(attempt.submitted_at),
        "autoSubmitted": attempt.auto_submitted,
        "objectiveScore": round2(attempt.objective_score),
        # 未完成人工评分前不公布主观分和总分。
        "subjectiveScore": round2(attempt.subjective_score) if graded else None,
        "aiScore": round2(attempt.ai_score) if graded else None,
        "totalScore": round2(attempt.total_score) if graded else None,
        "gradingStatus": attempt.grading_status,
        "scoreReleased": graded,
        "message": message,
    }


def score_item(score):
    return {
        "id": score.id,
        "attemptId": score.attempt_id,
        "assessmentId": score.assessment_id,
        "assessmentTitle": score.assessment.title,
        "paperType": score.assessment.paper_type,
        "subject": score.subject,
        "studentId": score.student_id,
        "studentName": score.student_name,
        "studentNo": score.student_no,
        "classId": score.classroom_id,
        "className": score.class_name,
        "schoolId": score.school_id,
        "schoolName": score.school_name,
        "objectiveScore": round2(score.objective_score),
        "subjectiveScore": round2(score.subjective_score),
        "aiScore": round2(score.ai_score),
        "totalScore": round2(score.total_score),
        "level": score.level,
        "classRank": score.class_rank,
        "gradeRank": score.grade_rank,
        "status": score.status,
        "source": score.source,
        "gradedAt": iso(score.graded_at),
        "createdAt": iso(score.created_at),
    }


def score_detail(score, answer_visible, certificate_id=None):
    data = score_item(score)
    data["answerVisible"] = answer_visible
    data["certificateId"] = certificate_id
    details = []
    if score.attempt_id:
        snapshot = {q["questionId"]: q for q in score.attempt.questions_snapshot}
        for row in score.attempt.answers.all():
            snap = snapshot.get(row.question_id, {})
            details.append({
                "questionId": row.question_id,
                "order": row.order,
                "stem": snap.get("stem", ""),
                "studentAnswer": row.answer,
                "correctAnswer": (snap.get("answer") or None) if answer_visible else None,
                "score": round2(row.score) if row.score is not None else None,
                "maxScore": round2(row.max_score),
                "comment": row.comment,
                "aiAnalysis": row.ai_analysis,
                "analysis": snap.get("analysis") if answer_visible else None,
            })
    data["answerDetails"] = details
    return data


def grading_task_item(attempt):
    answers = list(attempt.answers.all())
    subjective = [a for a in answers if a.scoring_mode != ScoringMode.AUTO]
    ai_count = sum(1 for a in subjective if a.scoring_mode == ScoringMode.AI)
    subjective_count = sum(1 for a in subjective if a.scoring_mode == ScoringMode.MANUAL)
    pending = sum(1 for a in subjective if a.score is None)
    current = (attempt.subjective_score or 0) + (attempt.ai_score or 0)
    return {
        "attemptId": attempt.id,
        "assessmentId": attempt.assessment_id,
        "assessmentTitle": attempt.assessment.title,
        "subject": attempt.assessment.subject,
        "studentId": attempt.student_id,
        "studentName": attempt.student.real_name,
        "studentNo": attempt.student.student_no or "",
        "classId": attempt.student.current_class_id,
        "className": attempt.student.current_class.name if attempt.student.current_class_id else "",
        "submittedAt": iso(attempt.submitted_at),
        "gradingStatus": attempt.grading_status,
        "objectiveScore": round2(attempt.objective_score),
        "currentScore": round2(current),
        "maxScore": round2(attempt.assessment.max_score),
        "subjectiveCount": subjective_count,
        "aiCount": ai_count,
        "pendingCount": pending,
    }


def grading_question_item(row, snap):
    return {
        "questionId": row.question_id,
        "order": row.order,
        "type": snap.get("type", ""),
        "stem": snap.get("stem", ""),
        "studentAnswer": row.answer,
        "correctAnswer": snap.get("answer") or None,
        "rubric": snap.get("rubric") or None,
        "maxScore": round2(row.max_score),
        "currentScore": round2(row.score) if row.score is not None else None,
        "aiScore": round2(row.ai_score) if row.ai_score is not None else None,
        "aiAnalysis": row.ai_analysis,
        "comment": row.comment,
    }


def grading_attempt_detail(attempt):
    snapshot = {q["questionId"]: q for q in attempt.questions_snapshot}
    rows = [a for a in attempt.answers.all() if a.scoring_mode != ScoringMode.AUTO]
    can_finalize = bool(rows) and all(r.score is not None for r in rows)
    student = attempt.student
    return {
        "attemptId": attempt.id,
        "assessmentId": attempt.assessment_id,
        "assessmentTitle": attempt.assessment.title,
        "subject": attempt.assessment.subject,
        "studentId": student.id,
        "studentName": student.real_name,
        "studentNo": student.student_no or "",
        "classId": student.current_class_id,
        "className": student.current_class.name if student.current_class_id else "",
        "submittedAt": iso(attempt.submitted_at),
        "status": attempt.status,
        "gradingStatus": attempt.grading_status,
        "objectiveScore": round2(attempt.objective_score),
        "subjectiveScore": round2(attempt.subjective_score),
        "aiScore": round2(attempt.ai_score),
        "totalScore": round2(attempt.total_score),
        "maxScore": round2(attempt.assessment.max_score),
        "version": attempt.version,
        "canFinalize": can_finalize,
        "questions": [
            grading_question_item(r, snapshot.get(r.question_id, {})) for r in rows
        ],
    }


def certificate_item(cert):
    return {
        "id": cert.id,
        "certificateNo": cert.certificate_no,
        "studentId": cert.student_id,
        "studentName": cert.student_name,
        "assessmentId": cert.assessment_id,
        "assessmentTitle": cert.assessment.title,
        "subject": cert.subject,
        "score": round2(cert.score),
        "level": cert.level,
        "issueDate": date_str(cert.issue_date),
        "status": cert.status,
        "downloadUrl": (
            f"/api/v1/certificates/{cert.id}/download"
            if cert.status == "ready" else None
        ),
        "createdAt": iso(cert.created_at),
    }


def growth_payload(student, subject, start_date, end_date, points, summary):
    return {
        "studentId": student.id,
        "studentName": student.real_name,
        "subject": subject,
        "range": {"startDate": start_date, "endDate": end_date},
        "points": points,
        "summary": summary,
    }


def learning_report_payload(report):
    return {
        "reportId": report.report_id,
        "studentId": report.student_id,
        "subject": report.subject,
        "generatedAt": iso(report.generated_at),
        "summary": report.summary,
        "strengths": report.strengths or [],
        "weaknesses": report.weaknesses or [],
        "suggestions": report.suggestions or [],
        "scoreTrend": report.score_trend or [],
        "rawText": report.raw_text,
        "modelVersion": report.model_version,
    }


def total_score_rule_item(rule):
    return {
        "id": rule.id,
        "name": rule.name,
        "subject": rule.subject,
        "classId": rule.classroom_id,
        "className": getattr(rule.classroom, "name", ""),
        "term": rule.term,
        "startDate": date_str(rule.start_date),
        "endDate": date_str(rule.end_date),
        "weights": {
            "usual": round4(rule.usual_weight),
            "formal": round4(rule.formal_weight),
            "certificate": round4(rule.certificate_weight),
        },
        "aggregation": {
            "usual": rule.usual_aggregation,
            "formal": rule.formal_aggregation,
            "certificate": rule.certificate_aggregation,
        },
        "certificateLevelScores": rule.certificate_level_scores,
        "missingPolicy": rule.missing_policy,
        "lines": {
            "excellent": round2(rule.excellent_line),
            "good": round2(rule.good_line),
            "pass": round2(rule.pass_line),
        },
        "status": rule.status,
        "version": rule.version,
        "note": rule.note,
        "teacherId": rule.teacher_id,
        "teacherName": getattr(rule.teacher, "real_name", ""),
        "publishedAt": iso(rule.published_at),
        "createdAt": iso(rule.created_at),
        "updatedAt": iso(rule.updated_at),
    }


def notification_item(notification):
    return {
        "id": notification.id,
        "type": notification.type,
        "title": notification.title,
        "content": notification.content,
        "link": notification.link,
        "read": notification.read,
        "createdAt": iso(notification.created_at),
    }


def paper_review_log_item(log):
    return {
        "id": log.id,
        "paperId": log.paper_id,
        "version": log.version,
        "action": log.action,
        "reviewerId": log.reviewer_id,
        "reviewerName": getattr(log.reviewer, "real_name", None),
        "comment": log.comment,
        "createdAt": iso(log.created_at),
    }


def wrong_question_item(item):
    return {
        "id": item.id,
        "questionId": item.question_id,
        "subject": item.subject,
        "type": item.type,
        "stem": item.stem,
        "wrongCount": item.wrong_count,
        "lastWrongAt": iso(item.last_wrong_at),
        "masteryStatus": item.mastery_status,
        "sourceType": item.source_type,
        "sourceAssessmentTitle": item.source_assessment_title,
    }


def wrong_question_detail(item, records=None):
    data = wrong_question_item(item)
    data.update({
        "options": item.options or [],
        "correctAnswer": item.correct_answer or {},
        "studentAnswer": item.student_answer,
        "analysis": item.analysis,
        "resources": item.resources or [],
        "note": item.note,
        "records": [
            {
                "attemptId": row.attempt_id,
                "answer": row.answer,
                "createdAt": iso(row.created_at),
            }
            for row in (records or [])
        ],
    })
    return data
