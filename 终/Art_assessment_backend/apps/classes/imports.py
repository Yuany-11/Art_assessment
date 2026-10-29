"""班级学生批量导入（CLS-14）。"""
from django.db import transaction

from common.audit import log_operation
from common.enums import AccountStatus, Gender, Role
from common.exceptions import BusinessError
from common.imports import cell, header_map, read_table
from common.passwords import generate_password
from common.serializers import is_cn_phone

from apps.accounts.models import StudentProfile, User

from .models import Class
from .services import can_view_class_students

REQUIRED_HEADERS = ("学籍号", "姓名", "性别", "年级", "登录账号")
GENDER_MAP = {"男": Gender.MALE, "女": Gender.FEMALE, "未知": Gender.UNKNOWN}


def _import_row(classroom: Class, row, mapping, mode: str):
    student_no = cell(row, mapping, "学籍号")
    real_name = cell(row, mapping, "姓名")
    gender_raw = cell(row, mapping, "性别")
    grade_raw = cell(row, mapping, "年级")
    username = cell(row, mapping, "登录账号")
    phone = cell(row, mapping, "手机号") or None
    guardian_phone = cell(row, mapping, "监护人手机号") or None
    initial_password = cell(row, mapping, "初始密码")

    if not student_no:
        raise BusinessError(400, "学籍号不能为空")
    if not real_name:
        raise BusinessError(400, "姓名不能为空")
    if gender_raw not in GENDER_MAP:
        raise BusinessError(400, "性别必须为男/女/未知")
    if not grade_raw:
        raise BusinessError(400, "年级不能为空")
    try:
        grade = int(grade_raw)
    except ValueError:
        raise BusinessError(400, "年级必须为整数")
    if grade != classroom.grade:
        raise BusinessError(400, "年级必须与班级年级一致")
    if not username and mode == "append":
        raise BusinessError(400, "登录账号不能为空")
    if phone and not is_cn_phone(phone):
        raise BusinessError(400, "手机号需为 11 位数字")
    if guardian_phone and not is_cn_phone(guardian_phone):
        raise BusinessError(400, "监护人手机号需为 11 位数字")

    gender = GENDER_MAP[gender_raw]
    existing = (
        StudentProfile.objects.filter(student_no=student_no, deleted_at__isnull=True)
        .select_related("user")
        .first()
    )

    if existing is not None:
        if mode == "append":
            raise BusinessError(409, "学籍号已存在")
        if existing.user.org_id != classroom.school_id:
            raise BusinessError(409, "学籍号属于其他学校")
        user = existing.user
        user.real_name = real_name
        user.gender = gender
        user.phone = phone
        user.save(update_fields=["real_name", "gender", "phone", "updated_at"])
        existing.grade = grade
        existing.guardian_phone = guardian_phone
        existing.classroom = classroom
        existing.save(
            update_fields=["grade", "guardian_phone", "classroom", "updated_at"]
        )
        return None

    if not username:
        raise BusinessError(400, "登录账号不能为空")
    if User.objects.filter(username=username).exists():
        raise BusinessError(409, "登录账号已存在")

    password = initial_password or generate_password()
    user = User.objects.create_user(
        username=username,
        password=password,
        real_name=real_name,
        role=Role.STUDENT,
        org=classroom.school,
        phone=phone,
        gender=gender,
        status=AccountStatus.ACTIVE,
    )
    StudentProfile.objects.create(
        user=user,
        student_no=student_no,
        grade=grade,
        guardian_phone=guardian_phone,
        classroom=classroom,
    )
    # 返回新建账号的临时密码，供导入后一次性展示，避免教师逐个重置。
    return {
        "studentNo": student_no,
        "name": real_name,
        "username": username,
        "password": password,
    }


def import_students(actor, classroom: Class, uploaded_file, mode: str = "append") -> dict:
    if actor.role not in {Role.TEACHER, Role.SCHOOL_ADMIN}:
        raise BusinessError(403, "当前角色无权导入班级学生")
    if not can_view_class_students(actor, classroom):
        raise BusinessError(403, "无权操作该班级")

    rows = read_table(uploaded_file, max_size_mb=10)
    if not rows:
        raise BusinessError(400, "导入文件为空")

    mapping = header_map(rows[0])
    missing = [name for name in REQUIRED_HEADERS if name not in mapping]
    if missing:
        raise BusinessError(400, "缺少模板列：" + "、".join(missing))

    errors: list[dict] = []
    credentials: list[dict] = []
    success_count = 0
    total = 0

    for index, row in enumerate(rows[1:], start=2):
        if not any(item.strip() for item in row):
            continue
        total += 1
        student_no = cell(row, mapping, "学籍号")
        try:
            with transaction.atomic():
                credential = _import_row(classroom, row, mapping, mode)
            if credential:
                credentials.append(credential)
            success_count += 1
        except BusinessError as exc:
            errors.append({"row": index, "studentNo": student_no, "message": str(exc)})
        except Exception:
            errors.append({"row": index, "studentNo": student_no, "message": "该行导入失败"})

    result = {
        "total": total,
        "successCount": success_count,
        "failCount": len(errors),
        "errors": errors,
        "credentials": credentials,
    }
    log_operation(
        actor,
        "class.student_import",
        "system",
        classroom.id,
        f"批量导入班级学生：成功 {success_count}，失败 {len(errors)}",
    )
    return result
