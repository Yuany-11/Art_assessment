"""教师总评规则与计算。

总评 = 平时测试 + 正式测评 + 证书，三项按教师配置的权重合成。
平时/正式成绩统一折算成 0-100 的得分率，证书按等级映射成分数。
缺项时可选择“按 0 分”或“按剩余权重折算”。
"""
from collections import defaultdict
from pathlib import Path

import yaml
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User
from apps.classes.models import ClassTeacher
from apps.exams.models import Certificate, Score, TotalScoreRule
from apps.exams.scope import DataScope
from apps.exams.serializers import (
    TotalScoreRuleCreateSerializer,
    TotalScoreRuleUpdateSerializer,
)
from common.audit import log_action
from common.enums import (
    AccountStatus,
    CertificateStatus,
    GradingStatus,
    Level,
    MissingComponentPolicy,
    PaperType,
    Role,
    ScoreAggregation,
    Subject,
    TotalScoreRuleStatus,
)
from common.exceptions import BadRequest, Forbidden, NotFound
from common.utils import date_str, iso, round2, round4

DEFAULTS_FILE = Path(__file__).resolve().parent.parent / "rules" / "teacher_total.yaml"
_DEFAULTS_CACHE = None

COMPONENT_LABELS = {
    "usual": "平时测试",
    "formal": "正式测评",
    "certificate": "证书",
}
LEVEL_LABELS = dict(Level.choices)


def load_defaults():
    global _DEFAULTS_CACHE
    if _DEFAULTS_CACHE is not None:
        return _DEFAULTS_CACHE
    if not DEFAULTS_FILE.exists():
        raise RuntimeError(f"总评规则默认值文件不存在：{DEFAULTS_FILE}")
    with DEFAULTS_FILE.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    defaults = data.get("defaults") or {}
    required = ("weights", "aggregation", "certificateLevelScores", "lines")
    missing = [key for key in required if key not in defaults]
    if missing:
        raise RuntimeError(f"总评规则默认值缺少：{', '.join(missing)}")
    _DEFAULTS_CACHE = defaults
    return defaults


def _ensure_teacher(user):
    if user.role != Role.TEACHER:
        raise Forbidden("总评规则仅限教师操作")


def _ensure_class(user, class_id, subject=None):
    scope = DataScope(user)
    if class_id not in scope.class_ids:
        raise Forbidden("只能为任教班级配置总评规则")
    if subject is None:
        return
    if not ClassTeacher.objects.filter(
        teacher=user, class_obj_id=class_id, subject=subject,
        deleted_at__isnull=True,
    ).exists():
        raise Forbidden("未在该班级任教该学科")


def _ensure_owner(user, rule):
    _ensure_teacher(user)
    if rule.teacher_id != user.id:
        raise Forbidden("无权访问该总评规则")


def _int_param(value, label):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise BadRequest(f"{label} 必须为整数")


def _as_bool(value):
    return str(value).lower() in ("1", "true", "yes", "on")


def list_rules(user, params):
    _ensure_teacher(user)
    qs = TotalScoreRule.objects.filter(teacher=user).select_related(
        "classroom", "teacher"
    )
    if not _as_bool(params.get("includeArchived")):
        qs = qs.exclude(status=TotalScoreRuleStatus.ARCHIVED)
    if params.get("subject"):
        if params["subject"] not in Subject.values:
            raise BadRequest("subject 必须为 music 或 art")
        qs = qs.filter(subject=params["subject"])
    if params.get("classId"):
        class_id = _int_param(params["classId"], "classId")
        _ensure_class(user, class_id, params.get("subject"))
        qs = qs.filter(classroom_id=class_id)
    if params.get("term"):
        qs = qs.filter(term=params["term"])
    if params.get("status"):
        qs = qs.filter(status=params["status"])
    if params.get("keyword"):
        qs = qs.filter(name__icontains=params["keyword"])
    return qs.order_by("-updated_at")


def get_rule(user, rule_id):
    _ensure_teacher(user)
    rule = (
        TotalScoreRule.objects.select_related("classroom", "teacher")
        .filter(pk=rule_id)
        .first()
    )
    if rule is None:
        raise NotFound("总评规则不存在")
    if rule.teacher_id != user.id:
        raise Forbidden("无权访问该总评规则")
    return rule


def _validate_config(values):
    weights = [
        float(values["usual_weight"]),
        float(values["formal_weight"]),
        float(values["certificate_weight"]),
    ]
    for weight in weights:
        if not 0 <= weight <= 1:
            raise BadRequest("各项权重必须在 0-1 之间")
    if abs(sum(weights) - 1) > 1e-6:
        raise BadRequest("三项权重之和必须为 1")
    lines = [
        float(values["excellent_line"]),
        float(values["good_line"]),
        float(values["pass_line"]),
    ]
    for line in lines:
        if not 0 <= line <= 100:
            raise BadRequest("等级分数线必须在 0-100 之间")
    if not lines[0] >= lines[1] >= lines[2]:
        raise BadRequest("等级分数线必须满足 优秀线 >= 良好线 >= 合格线")
    start_date = values.get("start_date")
    end_date = values.get("end_date")
    if start_date and end_date and start_date > end_date:
        raise BadRequest("startDate 不能晚于 endDate")
    level_scores = values.get("certificate_level_scores") or {}
    if not isinstance(level_scores, dict):
        raise BadRequest("certificateLevelScores 必须为对象")
    for key, score in level_scores.items():
        if key not in dict(Level.choices):
            raise BadRequest(f"未知证书等级：{key}")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            raise BadRequest(f"证书等级 {key} 的分数必须为数字")
        if not 0 <= float(score) <= 100:
            raise BadRequest(f"证书等级 {key} 的分数必须在 0-100 之间")


def _values_from_payload(data):
    defaults = load_defaults()
    weights = defaults["weights"]
    aggregation = defaults["aggregation"]
    lines = defaults["lines"]
    return {
        "name": data["name"],
        "subject": data["subject"],
        "classroom_id": data["classId"],
        "term": data.get("term", ""),
        "start_date": data.get("startDate"),
        "end_date": data.get("endDate"),
        "usual_weight": data.get("usualWeight", weights["usual"]),
        "formal_weight": data.get("formalWeight", weights["formal"]),
        "certificate_weight": data.get("certificateWeight", weights["certificate"]),
        "usual_aggregation": data.get("usualAggregation", aggregation["usual"]),
        "formal_aggregation": data.get("formalAggregation", aggregation["formal"]),
        "certificate_aggregation": data.get(
            "certificateAggregation", aggregation["certificate"]
        ),
        "certificate_level_scores": data.get(
            "certificateLevelScores", defaults["certificateLevelScores"]
        ),
        "missing_policy": data.get("missingPolicy", defaults["missingPolicy"]),
        "excellent_line": data.get("excellentLine", lines["excellent"]),
        "good_line": data.get("goodLine", lines["good"]),
        "pass_line": data.get("passLine", lines["pass"]),
        "note": data.get("note") or "",
    }


UPDATE_FIELDS = {
    "name": "name",
    "term": "term",
    "startDate": "start_date",
    "endDate": "end_date",
    "usualWeight": "usual_weight",
    "formalWeight": "formal_weight",
    "certificateWeight": "certificate_weight",
    "usualAggregation": "usual_aggregation",
    "formalAggregation": "formal_aggregation",
    "certificateAggregation": "certificate_aggregation",
    "certificateLevelScores": "certificate_level_scores",
    "missingPolicy": "missing_policy",
    "excellentLine": "excellent_line",
    "goodLine": "good_line",
    "passLine": "pass_line",
    "note": "note",
}


def create_rule(user, payload, request=None):
    _ensure_teacher(user)
    serializer = TotalScoreRuleCreateSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    _ensure_class(user, data["classId"], data["subject"])
    values = _values_from_payload(data)
    _validate_config(values)
    with transaction.atomic():
        rule = TotalScoreRule.objects.create(teacher=user, **values)
        log_action(
            user, "total_score_rule.create", "total_score_rule", rule.id,
            f"创建总评规则：{rule.name}", {"weights": _weights_dict(rule)}, request=request,
        )
    return rule


def update_rule(user, rule, payload, request=None):
    _ensure_owner(user, rule)
    serializer = TotalScoreRuleUpdateSerializer(data=payload, partial=True)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    values = {
        "usual_weight": rule.usual_weight,
        "formal_weight": rule.formal_weight,
        "certificate_weight": rule.certificate_weight,
        "excellent_line": rule.excellent_line,
        "good_line": rule.good_line,
        "pass_line": rule.pass_line,
        "start_date": rule.start_date,
        "end_date": rule.end_date,
        "certificate_level_scores": rule.certificate_level_scores,
    }
    for api_name, field in UPDATE_FIELDS.items():
        if api_name in data:
            setattr(rule, field, data[api_name])
            values[field] = data[api_name]
    _validate_config(values)
    rule.version += 1
    rule.save()
    log_action(
        user, "total_score_rule.update", "total_score_rule", rule.id,
        f"修改总评规则：{rule.name}", {"weights": _weights_dict(rule)}, request=request,
    )
    return rule


def publish_rule(user, rule, request=None):
    _ensure_owner(user, rule)
    _validate_config({
        "usual_weight": rule.usual_weight,
        "formal_weight": rule.formal_weight,
        "certificate_weight": rule.certificate_weight,
        "excellent_line": rule.excellent_line,
        "good_line": rule.good_line,
        "pass_line": rule.pass_line,
        "start_date": rule.start_date,
        "end_date": rule.end_date,
        "certificate_level_scores": rule.certificate_level_scores,
    })
    with transaction.atomic():
        others = TotalScoreRule.objects.filter(
            teacher=user,
            classroom_id=rule.classroom_id,
            subject=rule.subject,
            term=rule.term,
            status=TotalScoreRuleStatus.PUBLISHED,
        ).exclude(pk=rule.pk)
        for other in others:
            other.status = TotalScoreRuleStatus.ARCHIVED
            other.version += 1
            other.save(update_fields=["status", "version", "updated_at"])
        rule.status = TotalScoreRuleStatus.PUBLISHED
        rule.published_at = timezone.now()
        rule.version += 1
        rule.save()
        log_action(
            user, "total_score_rule.publish", "total_score_rule", rule.id,
            f"发布总评规则：{rule.name}", {"weights": _weights_dict(rule)}, request=request,
        )
    return rule


def archive_rule(user, rule, request=None):
    _ensure_owner(user, rule)
    if rule.status != TotalScoreRuleStatus.ARCHIVED:
        rule.status = TotalScoreRuleStatus.ARCHIVED
        rule.version += 1
        rule.save(update_fields=["status", "version", "updated_at"])
        log_action(
            user, "total_score_rule.archive", "total_score_rule", rule.id,
            f"归档总评规则：{rule.name}", None, request=request,
        )
    return rule


def _weights_dict(rule):
    return {
        "usual": round4(rule.usual_weight),
        "formal": round4(rule.formal_weight),
        "certificate": round4(rule.certificate_weight),
    }


def _score_ratio(score):
    if not score.max_score or score.max_score <= 0:
        return 0.0
    return max(0.0, min(1.0, score.total_score / score.max_score))


def _score_detail(score):
    return {
        "assessmentId": score.assessment_id,
        "title": getattr(score.assessment, "title", ""),
        "score": round2(score.total_score),
        "maxScore": round2(score.max_score),
        "ratio": round4(_score_ratio(score)),
        "gradedAt": iso(score.graded_at or score.created_at),
    }


def _aggregate(items, mode, value_key="ratio"):
    if not items:
        return None, []
    if mode == ScoreAggregation.BEST:
        best = max(items, key=lambda item: item[value_key])
        return best[value_key], [best]
    if mode == ScoreAggregation.LATEST:
        latest = items[-1]
        return latest[value_key], [latest]
    average = sum(item[value_key] for item in items) / len(items)
    return average, items


def _load_scores(rule, student_ids):
    qs = (
        Score.objects.filter(
            student_id__in=student_ids,
            subject=rule.subject,
            status=GradingStatus.GRADED,
            deleted_at__isnull=True,
        )
        .select_related("assessment")
        .order_by("created_at", "id")
    )
    if rule.start_date:
        qs = qs.filter(created_at__date__gte=rule.start_date)
    if rule.end_date:
        qs = qs.filter(created_at__date__lte=rule.end_date)
    grouped = defaultdict(lambda: {"practice": [], "formal": []})
    for score in qs:
        paper_type = getattr(score.assessment, "paper_type", None)
        if paper_type == PaperType.PRACTICE:
            grouped[score.student_id]["practice"].append(_score_detail(score))
        elif paper_type == PaperType.FORMAL:
            grouped[score.student_id]["formal"].append(_score_detail(score))
    return grouped


def _certificate_level_scores(rule):
    defaults = load_defaults()["certificateLevelScores"]
    return {**defaults, **(rule.certificate_level_scores or {})}


def _load_certificates(rule, student_ids):
    qs = Certificate.objects.filter(
        student_id__in=student_ids,
        subject=rule.subject,
        status=CertificateStatus.READY,
        deleted_at__isnull=True,
    ).order_by("issue_date", "id")
    if rule.start_date:
        qs = qs.filter(issue_date__gte=rule.start_date)
    if rule.end_date:
        qs = qs.filter(issue_date__lte=rule.end_date)
    level_scores = _certificate_level_scores(rule)
    grouped = defaultdict(list)
    for cert in qs:
        mapped = float(level_scores.get(cert.level, 0))
        grouped[cert.student_id].append({
            "certificateId": cert.id,
            "certificateNo": cert.certificate_no,
            "level": cert.level,
            "levelLabel": LEVEL_LABELS.get(cert.level, cert.level),
            "score": mapped,
            "ratio": round4(mapped / 100),
            "issueDate": date_str(cert.issue_date),
        })
    return grouped


def _band(rule, total):
    if total is None:
        return None, None
    if total >= rule.excellent_line:
        return "excellent", "优秀"
    if total >= rule.good_line:
        return "good", "良好"
    if total >= rule.pass_line:
        return "pass", "合格"
    return "fail", "待提升"


def _component(key, weight, score, aggregation, details, count, note=""):
    return {
        "key": key,
        "name": COMPONENT_LABELS[key],
        "weight": round4(weight),
        "aggregation": aggregation,
        "available": score is not None,
        "score": round2(score) if score is not None else None,
        "contribution": round2(score * weight) if score is not None else None,
        "count": count,
        "details": details,
        "note": note,
    }


def _compute_student(rule, student, score_map, cert_map):
    components = []
    warnings = []
    available_weight = 0.0
    weighted_score = 0.0
    zero_policy = rule.missing_policy == MissingComponentPolicy.ZERO

    definitions = (
        ("usual", rule.usual_weight, rule.usual_aggregation,
         score_map.get(student.id, {}).get("practice", [])),
        ("formal", rule.formal_weight, rule.formal_aggregation,
         score_map.get(student.id, {}).get("formal", [])),
        ("certificate", rule.certificate_weight, rule.certificate_aggregation,
         cert_map.get(student.id, [])),
    )
    for key, weight, aggregation, items in definitions:
        weight = float(weight)
        if weight <= 0:
            continue
        ratio, used = _aggregate(items, aggregation)
        if ratio is None:
            note = "无数据，按 0 分计入" if zero_policy else "无数据，已从分母剔除"
            components.append(_component(key, weight, 0 if zero_policy else None,
                                         aggregation, [], 0, note))
            if zero_policy:
                available_weight += weight
            warnings.append(f"{COMPONENT_LABELS[key]}{note}")
            continue
        score = round2(ratio * 100)
        available_weight += weight
        weighted_score += score * weight
        components.append(_component(
            key, weight, score, aggregation, used, len(items)
        ))

    if available_weight <= 0:
        total = None
        warnings.append("所有计分项均无数据，无法计算总评")
    else:
        total = round2(weighted_score / available_weight)
    band, band_label = _band(rule, total)
    return {
        "studentId": student.id,
        "studentNo": student.student_no or "",
        "studentName": student.real_name,
        "classId": rule.classroom_id,
        "className": rule.classroom.name,
        "totalScore": total,
        "level": band,
        "levelLabel": band_label,
        "components": components,
        "warnings": warnings,
    }


def _summary(rows):
    totals = [row["totalScore"] for row in rows if row["totalScore"] is not None]
    levels = {"excellent": 0, "good": 0, "pass": 0, "fail": 0}
    for row in rows:
        if row["level"] in levels:
            levels[row["level"]] += 1
    passed = levels["excellent"] + levels["good"] + levels["pass"]
    return {
        "studentCount": len(rows),
        "computedCount": len(totals),
        "incompleteCount": len(rows) - len(totals),
        "averageScore": round2(sum(totals) / len(totals)) if totals else None,
        "highestScore": round2(max(totals)) if totals else None,
        "lowestScore": round2(min(totals)) if totals else None,
        "passRate": round4(passed / len(totals)) if totals else 0.0,
        "excellentRate": round4(levels["excellent"] / len(totals)) if totals else 0.0,
        "levelCounts": levels,
    }


def compute_results(user, rule, params):
    _ensure_owner(user, rule)
    students = (
        User.objects.filter(
            role=Role.STUDENT,
            status=AccountStatus.ACTIVE,
            deleted_at__isnull=True,
            student_profile__classroom_id=rule.classroom_id,
            student_profile__deleted_at__isnull=True,
        )
        .select_related("student_profile")
        .order_by("student_profile__student_no", "id")
    )
    if params.get("studentId"):
        student_id = _int_param(params["studentId"], "studentId")
        students = students.filter(pk=student_id)
        if not students.exists():
            raise NotFound("该学生不在规则所属班级")
    if params.get("studentKeyword"):
        keyword = params["studentKeyword"]
        students = students.filter(
            Q(student_profile__student_no__icontains=keyword)
            | Q(real_name__icontains=keyword)
        )
    students = list(students)
    student_ids = [student.id for student in students]
    score_map = _load_scores(rule, student_ids)
    cert_map = _load_certificates(rule, student_ids)
    rows = [
        _compute_student(rule, student, score_map, cert_map)
        for student in students
    ]
    return {"summary": _summary(rows), "students": rows}
