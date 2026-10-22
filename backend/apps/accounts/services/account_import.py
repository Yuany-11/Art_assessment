"""教师账号批量导入（ACC-04）。"""
import datetime
import secrets

from django.db import transaction

from common.enums import AccountStatus, Role, Subject
from common.exceptions import BusinessError
from common.imports import cell, header_map, read_table
from common.passwords import generate_password

from ..models import TeacherProfile, User

REQUIRED_HEADERS = ("登录账号", "姓名", "手机号", "任教学科")


def _task_id() -> str:
    return "TIMP" + datetime.datetime.now().strftime("%Y%m%d%H%M%S") + secrets.token_hex(2).upper()


def _import_row(actor, row, mapping, default_password, overwrite):
    from apps.classes.models import Class, ClassTeacher

    username = cell(row, mapping, "登录账号")
    real_name = cell(row, mapping, "姓名")
    phone = cell(row, mapping, "手机号")
    email = cell(row, mapping, "邮箱") or None
    subject = cell(row, mapping, "任教学科")
    title = cell(row, mapping, "职称") or None
    class_codes_raw = cell(row, mapping, "班级号（多个用/分隔）")
    initial_password = cell(row, mapping, "初始密码")

    if not username:
        raise BusinessError(400, "登录账号不能为空")
    if not real_name:
        raise BusinessError(400, "姓名不能为空")
    if not phone:
        raise BusinessError(400, "手机号不能为空")
    if subject not in Subject.values:
        raise BusinessError(400, "任教学科必须为 music 或 art")

    classes = []
    if class_codes_raw:
        for code in [item.strip() for item in class_codes_raw.split("/") if item.strip()]:
            classroom = Class.objects.filter(
                class_code=code, school=actor.org, deleted_at__isnull=True
            ).first()
            if classroom is None:
                raise BusinessError(400, f"班级号 {code} 不存在或不属于本校")
            classes.append(classroom)

    user = User.objects.filter(username=username).first()
    password = initial_password or default_password or generate_password()

    if user is not None:
        if not overwrite:
            raise BusinessError(409, "登录账号已存在")
        if user.role != Role.TEACHER or user.org_id != actor.org_id:
            raise BusinessError(409, "登录账号已存在且不属于本校教师")
        user.real_name = real_name
        user.phone = phone
        user.email = email
        user.save(update_fields=["real_name", "phone", "email", "updated_at"])
        profile, _ = TeacherProfile.objects.get_or_create(user=user)
        profile.subject = subject
        profile.title = title
        profile.save(update_fields=["subject", "title", "updated_at"])
        ClassTeacher.objects.filter(teacher=user, class_obj__school=actor.org).delete()
    else:
        user = User.objects.create_user(
            username=username,
            password=password,
            real_name=real_name,
            role=Role.TEACHER,
            org=actor.org,
            phone=phone,
            email=email,
            status=AccountStatus.ACTIVE,
        )
        TeacherProfile.objects.create(user=user, subject=subject, title=title)

    for classroom in classes:
        ClassTeacher.objects.get_or_create(
            class_obj=classroom, teacher=user, defaults={"subject": subject}
        )


def import_teachers(actor, uploaded_file, default_password=None, overwrite: bool = False) -> dict:
    if actor.role != Role.SCHOOL_ADMIN:
        raise BusinessError(403, "仅学校管理员可批量导入教师")

    rows = read_table(uploaded_file, max_size_mb=5)
    if not rows:
        raise BusinessError(400, "导入文件为空")

    mapping = header_map(rows[0])
    missing = [name for name in REQUIRED_HEADERS if name not in mapping]
    if missing:
        raise BusinessError(400, "缺少模板列：" + "、".join(missing))

    errors: list[dict] = []
    success_count = 0
    total = 0

    for index, row in enumerate(rows[1:], start=2):
        if not any(item.strip() for item in row):
            continue
        total += 1
        username = cell(row, mapping, "登录账号")
        try:
            with transaction.atomic():
                _import_row(actor, row, mapping, default_password, overwrite)
            success_count += 1
        except BusinessError as exc:
            errors.append({"row": index, "username": username, "message": str(exc)})
        except Exception:
            errors.append({"row": index, "username": username, "message": "该行导入失败"})

    return {
        "taskId": _task_id(),
        "status": "completed",
        "total": total,
        "successCount": success_count,
        "failCount": len(errors),
        "errors": errors,
    }
