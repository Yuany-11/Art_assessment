import csv
import io
import os
import random
from datetime import datetime

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from common.audit import log_action
from common.enums import (
    AttemptStatus,
    GradingStatus,
    PaperType,
    Role,
    ScoreSource,
    ScopeType,
    ShowAnswerMode,
)
from common.exceptions import BadRequest, Conflict, Forbidden, NotFound, Unprocessable
from apps.exams.scope import DataScope
from common.utils import level_for, round2
from apps.exams.models import Assessment, ImportTask, Score
from apps.exams.serializers import ManualScoreSerializer
from apps.exams.services import ranking as ranking_service
from apps.exams.services.assessment import students_for_target


def _int_param(value, label):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise BadRequest(f"{label} 必须为整数")


def _dt_param(value, label):
    dt = parse_datetime(value)
    if dt is None:
        raise BadRequest(f"{label} 必须为 ISO 8601 时间")
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


def _score_scope_qs(scope):
    qs = Score.objects.all()
    if scope.is_province_admin:
        return qs
    if scope.is_city_admin or scope.is_district_admin:
        return qs.filter(school_id__in=scope.school_ids)
    if scope.is_teacher:
        return qs.filter(classroom_id__in=scope.class_ids)
    if scope.is_student:
        return qs.filter(student=scope.user)
    if scope.school_id:
        return qs.filter(school_id=scope.school_id)
    return qs.none()


def my_scores(user, params):
    if user.role != Role.STUDENT:
        raise Forbidden("该接口仅限学生")
    qs = Score.objects.select_related("assessment", "classroom", "school").filter(
        student=user
    )
    if params.get("subject"):
        qs = qs.filter(subject=params["subject"])
    if params.get("assessmentId"):
        qs = qs.filter(assessment_id=params["assessmentId"])
    return qs.order_by("-created_at")


def list_scores(user, params):
    if user.role == Role.STUDENT:
        raise Forbidden("学生请使用 /scores/me")
    if user.role == Role.QUESTION_ADMIN:
        raise Forbidden("题库管理员无权访问成绩数据")
    scope = DataScope(user)
    qs = _score_scope_qs(scope).select_related("assessment", "classroom", "school")
    # 成绩管理默认只看正式测评；随机练习属于练习反馈，避免刷屏。
    paper_type = params.get("paperType")
    if paper_type in {PaperType.FORMAL, PaperType.PRACTICE}:
        qs = qs.filter(assessment__paper_type=paper_type)
    elif paper_type != "all":
        qs = qs.filter(assessment__paper_type=PaperType.FORMAL)
    filters = {
        "assessmentId": "assessment_id",
        "subject": "subject",
        "grade": "grade",
        "level": "level",
        "source": "source",
    }
    for param, field in filters.items():
        if params.get(param):
            qs = qs.filter(**{field: params[param]})
    if params.get("classId"):
        class_id = _int_param(params["classId"], "classId")
        scope.ensure_class(class_id)
        qs = qs.filter(classroom_id=class_id)
    if params.get("schoolId"):
        school_id = _int_param(params["schoolId"], "schoolId")
        scope.ensure_school(school_id)
        qs = qs.filter(school_id=school_id)
    if params.get("districtId"):
        from apps.exams.services.statistics import _school_ids_under

        qs = qs.filter(
            school_id__in=_school_ids_under(
                ScopeType.DISTRICT, _int_param(params["districtId"], "districtId")
            )
        )
    if params.get("cityId"):
        from apps.exams.services.statistics import _school_ids_under

        qs = qs.filter(
            school_id__in=_school_ids_under(
                ScopeType.CITY, _int_param(params["cityId"], "cityId")
            )
        )
    keyword = params.get("studentKeyword")
    if keyword:
        qs = qs.filter(
            Q(student_name__icontains=keyword)
            | Q(student_no__icontains=keyword)
            | Q(student__username__icontains=keyword)
        )
    if params.get("startTime"):
        qs = qs.filter(created_at__gte=_dt_param(params["startTime"], "startTime"))
    if params.get("endTime"):
        qs = qs.filter(created_at__lte=_dt_param(params["endTime"], "endTime"))
    return qs.order_by("-created_at")


def get_score(user, score_id):
    score = (
        Score.objects.select_related(
            "assessment", "attempt", "student", "classroom", "school"
        )
        .filter(pk=score_id)
        .first()
    )
    if score is None:
        raise NotFound("成绩不存在")
    if user.role == Role.STUDENT:
        if score.student_id != user.id:
            raise Forbidden("无权查看他人成绩")
        return score
    if user.role == Role.QUESTION_ADMIN:
        raise Forbidden("题库管理员无权访问成绩数据")
    scope = DataScope(user)
    if not _score_scope_qs(scope).filter(pk=score.id).exists():
        raise Forbidden("无权查看该成绩")
    return score


def answer_visible(user, score):
    if user.role != Role.STUDENT:
        return True
    if not score.attempt_id:
        return False
    assessment = score.assessment
    mode = assessment.show_answer_mode
    if mode == ShowAnswerMode.NEVER:
        return False
    if mode == ShowAnswerMode.AFTER_SUBMIT:
        return score.attempt.status in (
            AttemptStatus.SUBMITTED, AttemptStatus.GRADED, AttemptStatus.INVALID
        )
    if mode == ShowAnswerMode.AFTER_END:
        return assessment.end_time <= timezone.now()
    return False


def _ensure_student_in_scope(scope, student):
    if student.role != Role.STUDENT:
        raise Unprocessable("studentId 必须为学生账号")
    if scope.is_province_admin:
        return
    if scope.school_id and student.school_id != scope.school_id and not (
        scope.is_district_admin or scope.is_city_admin
    ):
        raise Forbidden("该学生不在当前账号数据范围内")
    if scope.is_district_admin and student.district_id != scope.district_id:
        raise Forbidden("该学生不在本区县范围内")
    if scope.is_city_admin and student.city_id != scope.city_id:
        raise Forbidden("该学生不在本市州范围内")
    if scope.is_teacher:
        if not student.current_class_id or student.current_class_id not in scope.class_ids:
            raise Forbidden("只能操作任教班级的学生")


def _ensure_student_in_assessment(assessment, student):
    qs = students_for_target(
        assessment.target_type, assessment.target_ids, assessment.target_grades
    )
    if not qs.filter(pk=student.pk).exists():
        raise Unprocessable("该学生不属于本测评目标范围")


def _ensure_formal_assessment(assessment):
    if assessment.paper_type != PaperType.FORMAL:
        raise Unprocessable("随机练习卷不支持补录或导入成绩，请选择正式测评")


def manual_score(user, payload, request=None):
    if user.role == Role.STUDENT or user.role == Role.QUESTION_ADMIN:
        raise Forbidden("无权补录成绩")
    serializer = ManualScoreSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    scope = DataScope(user)

    assessment = Assessment.objects.filter(pk=data["assessmentId"]).first()
    if assessment is None:
        raise NotFound("测评不存在")
    if assessment.subject != data["subject"]:
        raise Unprocessable("subject 与测评学科不一致")
    _ensure_formal_assessment(assessment)
    from apps.accounts.models import User

    student = User.objects.select_related("org").filter(pk=data["studentId"]).first()
    if student is None:
        raise NotFound("学生不存在")
    _ensure_student_in_scope(scope, student)
    _ensure_student_in_assessment(assessment, student)

    items = data["scoreItems"]
    computed = round2(sum(item["score"] for item in items))
    total = round2(data["totalScore"]) if data.get("totalScore") is not None else computed
    if total != computed:
        raise Unprocessable("totalScore 必须等于分项得分之和")
    if total > assessment.max_score:
        raise Unprocessable(f"总分不能超过试卷满分 {round2(assessment.max_score)}")

    existing = Score.objects.filter(assessment=assessment, student=student).first()
    if existing and not data["overwrite"]:
        raise Conflict("该学生该测评已有成绩，如需覆盖请传 overwrite=true")

    classroom = student.current_class
    with transaction.atomic():
        if existing is None:
            score = Score(assessment=assessment, student=student)
        else:
            score = existing
        score.attempt = None
        score.subject = assessment.subject
        score.student_name = student.real_name
        score.student_no = student.student_no or ""
        score.classroom = classroom
        score.class_name = classroom.name if classroom else ""
        score.school = student.school
        score.school_name = student.school.name if student.school else ""
        score.grade = student.grade or (classroom.grade if classroom else None)
        score.objective_score = 0
        score.subjective_score = total
        score.ai_score = 0
        score.total_score = total
        score.max_score = assessment.max_score
        score.level = level_for(total, assessment.max_score)
        score.class_rank = None
        score.grade_rank = None
        score.status = GradingStatus.GRADED
        score.source = ScoreSource.MANUAL
        score.score_items = items
        score.reason = data["reason"]
        score.evidence_file_ids = data.get("evidenceFileIds") or []
        score.graded_at = timezone.now()
        score.save()
        ranking_service.recompute_ranks(assessment)
        log_action(
            user, "score.manual", "score", score.id,
            f"补录成绩：{student.real_name} / {assessment.title}",
            {"totalScore": total, "reason": data["reason"], "overwrite": data["overwrite"]},
            request=request,
        )
    return score


# ---------------------------------------------------------------------------
# 批量导入
# ---------------------------------------------------------------------------
HEADER = ["学籍号", "姓名", "客观题得分", "主观题得分", "AI得分", "总分", "备注"]


def _parse_number(value, label, row_no, errors):
    if value in (None, ""):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        errors.append({"row": row_no, "studentNo": "", "message": f"{label}不是合法数字"})
        return None
    if number < 0:
        errors.append({"row": row_no, "studentNo": "", "message": f"{label}不能为负数"})
        return None
    return number


def _read_file_rows(file):
    name = (file.name or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        import openpyxl

        workbook = openpyxl.load_workbook(file, read_only=True, data_only=True)
        sheet = workbook.active
        return [list(row) for row in sheet.iter_rows(values_only=True)]
    raw = file.read()
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise BadRequest("无法识别文件编码，请使用 UTF-8 或 GBK 的 CSV")
    return [row for row in csv.reader(io.StringIO(text))]


def _parse_rows(rows):
    if not rows:
        raise BadRequest("文件为空")
    header = [str(cell).strip() if cell is not None else "" for cell in rows[0]]
    missing = [name for name in HEADER if name not in header and name != "备注"]
    if missing:
        raise BadRequest(f"缺少表头列：{', '.join(missing)}")
    index = {name: header.index(name) for name in HEADER if name in header}
    parsed = []
    for row_no, row in enumerate(rows[1:], start=2):
        values = list(row) + [None] * (len(header) - len(row))
        if all(v in (None, "") for v in values):
            continue
        record = {
            "row": row_no,
            "studentNo": str(values[index["学籍号"]] or "").strip(),
            "name": str(values[index["姓名"]] or "").strip(),
            "objective": values[index["客观题得分"]] if "客观题得分" in index else 0,
            "subjective": values[index["主观题得分"]] if "主观题得分" in index else 0,
            "ai": values[index["AI得分"]] if "AI得分" in index else 0,
            "total": values[index["总分"]] if "总分" in index else None,
            "remark": values[index["备注"]] if "备注" in index else "",
        }
        parsed.append(record)
    return parsed


def _validate_rows(parsed, assessment, subject, scope):
    errors = []
    valid = []
    seen = set()
    for record in parsed:
        row_no = record["row"]
        student_no = record["studentNo"]
        if not student_no:
            errors.append({"row": row_no, "studentNo": "", "message": "学籍号不能为空"})
            continue
        if student_no in seen:
            errors.append({"row": row_no, "studentNo": student_no, "message": "文件内学籍号重复"})
            continue
        seen.add(student_no)
        objective = _parse_number(record["objective"], "客观题得分", row_no, errors)
        subjective = _parse_number(record["subjective"], "主观题得分", row_no, errors)
        ai = _parse_number(record["ai"], "AI得分", row_no, errors)
        if None in (objective, subjective, ai):
            continue
        if record["total"] in (None, ""):
            total = round2(objective + subjective + ai)
        else:
            total = _parse_number(record["total"], "总分", row_no, errors)
            if total is None:
                continue
            if round2(objective + subjective + ai) != round2(total):
                errors.append({
                    "row": row_no, "studentNo": student_no,
                    "message": "总分与分项得分之和不一致",
                })
                continue
        if total > assessment.max_score:
            errors.append({
                "row": row_no, "studentNo": student_no,
                "message": f"总分超过试卷满分 {round2(assessment.max_score)}",
            })
            continue

        from apps.accounts.models import User

        student = User.objects.select_related("org").filter(
            role=Role.STUDENT, student_profile__student_no=student_no
        ).first()
        if student is None:
            errors.append({"row": row_no, "studentNo": student_no, "message": "学籍号不存在"})
            continue
        try:
            _ensure_student_in_scope(scope, student)
            _ensure_student_in_assessment(assessment, student)
        except (Forbidden, Unprocessable) as exc:
            errors.append({"row": row_no, "studentNo": student_no, "message": str(exc)})
            continue
        if record["name"] and student.real_name != record["name"]:
            errors.append({
                "row": row_no, "studentNo": student_no,
                "message": f"姓名与学籍号不匹配（应为 {student.real_name}）",
            })
            continue
        valid.append({
            "record": record, "student": student,
            "objective": objective, "subjective": subjective,
            "ai": ai, "total": total,
        })
    return valid, errors


def _write_import_rows(valid, assessment, subject, scope, overwrite):
    success = 0
    errors = []
    for item in valid:
        student = item["student"]
        with transaction.atomic():
            existing = Score.objects.filter(assessment=assessment, student=student).first()
            if existing and not overwrite:
                errors.append({
                    "row": item["record"]["row"],
                    "studentNo": item["record"]["studentNo"],
                    "message": "该学生该测评已有成绩",
                })
                continue
            score = existing or Score(assessment=assessment, student=student)
            classroom = student.current_class
            score.attempt = None
            score.subject = subject
            score.student_name = student.real_name
            score.student_no = student.student_no or ""
            score.classroom = classroom
            score.class_name = classroom.name if classroom else ""
            score.school = student.school
            score.school_name = student.school.name if student.school else ""
            score.grade = student.grade or (classroom.grade if classroom else None)
            score.objective_score = item["objective"]
            score.subjective_score = item["subjective"]
            score.ai_score = item["ai"]
            score.total_score = item["total"]
            score.max_score = assessment.max_score
            score.level = level_for(item["total"], assessment.max_score)
            score.status = GradingStatus.GRADED
            score.source = ScoreSource.IMPORT
            score.reason = "批量导入线下成绩"
            score.graded_at = timezone.now()
            score.save()
            success += 1
    ranking_service.recompute_ranks(assessment)
    return success, errors


def _task_id():
    return "IMP" + datetime.now().strftime("%Y%m%d%H%M%S") + f"{random.randint(0, 9999):04d}"


def import_scores(user, file, meta, request=None):
    if user.role == Role.STUDENT or user.role == Role.QUESTION_ADMIN:
        raise Forbidden("无权导入成绩")
    if file is None:
        raise BadRequest("请上传文件")
    if file.size > settings.SCORE_IMPORT_MAX_BYTES:
        raise BadRequest("文件超过 10 MB 限制")
    assessment = Assessment.objects.filter(pk=meta["assessmentId"]).first()
    if assessment is None:
        raise NotFound("测评不存在")
    if assessment.subject != meta["subject"]:
        raise Unprocessable("subject 与测评学科不一致")
    _ensure_formal_assessment(assessment)
    scope = DataScope(user)
    if user.role == Role.TEACHER:
        allowed = set(assessment.target_ids or [])
        if not allowed & scope.class_ids:
            raise Forbidden("无权导入该测评成绩")
    elif not scope.is_province_admin:
        if assessment.publisher_id != user.id:
            target_allowed = {
                "class": scope.class_ids,
                "school": scope.school_ids,
                "district": scope.district_ids,
                "city": scope.city_ids,
            }.get(assessment.target_type, set())
            if not set(assessment.target_ids or []) & target_allowed:
                raise Forbidden("无权导入该测评成绩")

    rows = _read_file_rows(file)
    parsed = _parse_rows(rows)
    valid, validation_errors = _validate_rows(parsed, assessment, meta["subject"], scope)

    task = ImportTask.objects.create(
        task_id=_task_id(),
        operator=user,
        assessment=assessment,
        subject=meta["subject"],
        status="queued",
        total=len(parsed),
        file_name=os.path.basename(file.name or ""),
    )

    async_mode = len(parsed) > settings.SCORE_IMPORT_ASYNC_THRESHOLD
    if async_mode:
        imports_dir = os.path.join(settings.MEDIA_ROOT, "imports")
        os.makedirs(imports_dir, exist_ok=True)
        path = os.path.join(imports_dir, f"{task.task_id}-{task.file_name or 'scores.csv'}")
        file.seek(0)
        with open(path, "wb") as handle:
            for chunk in file.chunks():
                handle.write(chunk)
        task.file_path = path
        task.errors = validation_errors
        task.save(update_fields=["file_path", "errors", "updated_at"])
        log_action(
            user, "score.import.queued", "assessment", assessment.id,
            f"导入任务 {task.task_id} 已排队", {"total": len(parsed)}, request=request,
        )
        return task, "queued"

    success, write_errors = _write_import_rows(
        valid, assessment, meta["subject"], scope, meta.get("overwrite", False)
    )
    errors = validation_errors + write_errors
    task.status = "completed"
    task.success_count = success
    task.fail_count = len(parsed) - success
    task.errors = errors
    task.finished_at = timezone.now()
    task.save()
    log_action(
        user, "score.import", "assessment", assessment.id,
        f"导入成绩 {task.task_id}：成功 {success}，失败 {task.fail_count}",
        {"total": len(parsed), "success": success, "fail": task.fail_count},
        request=request,
    )
    return task, "completed"


def process_import_task(task):
    """RQ/管理命令调用：处理已排队的导入任务。"""
    if task.status == "completed":
        return task
    from apps.accounts.models import User

    operator = task.operator or User.objects.filter(role=Role.PROVINCE_ADMIN).first()
    scope = DataScope(operator)
    if not task.file_path or not os.path.exists(task.file_path):
        task.status = "failed"
        task.errors = [{"row": 0, "studentNo": "", "message": "导入文件不存在"}]
        task.finished_at = timezone.now()
        task.save()
        return task

    class _File:
        name = task.file_name

        def __init__(self, path):
            self._handle = open(path, "rb")
            self.size = os.path.getsize(path)

        def read(self):
            return self._handle.read()

        def seek(self, pos):
            return self._handle.seek(pos)

        def chunks(self):
            while True:
                chunk = self._handle.read(65536)
                if not chunk:
                    break
                yield chunk

        def close(self):
            self._handle.close()

    handle = _File(task.file_path)
    try:
        rows = _read_file_rows(handle)
    finally:
        handle.close()
    parsed = _parse_rows(rows)
    valid, validation_errors = _validate_rows(parsed, task.assessment, task.subject, scope)
    success, write_errors = _write_import_rows(
        valid, task.assessment, task.subject, scope, overwrite=False
    )
    task.total = len(parsed)
    task.success_count = success
    task.fail_count = len(parsed) - success
    task.errors = validation_errors + write_errors
    task.status = "completed"
    task.finished_at = timezone.now()
    task.save()
    return task


def import_task_item(task):
    return {
        "taskId": task.task_id,
        "assessmentId": task.assessment_id,
        "status": task.status,
        "total": task.total,
        "successCount": task.success_count,
        "failCount": task.fail_count,
        "errors": task.errors or [],
        "fileName": task.file_name,
        "finishedAt": task.finished_at.isoformat() if task.finished_at else None,
    }


def get_import_task(user, task_id):
    """查询成绩导入任务进度，仅本人或有管理范围的管理员可见。"""
    if user.role in {Role.STUDENT, Role.QUESTION_ADMIN}:
        raise Forbidden("无权查看成绩导入任务")
    task = (
        ImportTask.objects.select_related("operator", "assessment")
        .filter(task_id=task_id)
        .first()
    )
    if task is None:
        raise NotFound("导入任务不存在")
    if task.operator_id != user.id and not DataScope(user).is_province_admin:
        raise Forbidden("无权查看该导入任务")
    return task
