"""多级账号管理业务逻辑（ACC-01 ~ ACC-11）。"""
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q

from common.audit import log_operation
from common.constants import (
    GRADE_MAX,
    GRADE_MIN,
    TEMPORARY_PASSWORD_CACHE_PREFIX,
    TEMPORARY_PASSWORD_TTL_SECONDS,
)
from common.enums import AccountStatus, ClassStatus, OrganizationLevel, Role, SchoolType
from common.exceptions import BusinessError
from common.passwords import PASSWORD_REQUIREMENT, generate_password, is_strong_password
from common.scope import descendant_org_ids

from ..models import StudentProfile, TeacherProfile, User
from ..validators import is_valid_student_no, is_valid_username


def _resolve_initial_password(data: dict) -> str:
    password = data.get("initialPassword") or settings.DEFAULT_INITIAL_PASSWORD
    if not is_strong_password(password):
        raise BusinessError(400, PASSWORD_REQUIREMENT)
    return password

MANAGED_ROLES: dict[str, set[str]] = {
    Role.SCHOOL_ADMIN: {Role.TEACHER, Role.STUDENT},
    Role.DISTRICT_ADMIN: {Role.SCHOOL_ADMIN, Role.TEACHER, Role.STUDENT},
    Role.CITY_ADMIN: {
        Role.DISTRICT_ADMIN,
        Role.SCHOOL_ADMIN,
        Role.TEACHER,
        Role.STUDENT,
    },
    Role.PROVINCE_ADMIN: {
        Role.CITY_ADMIN,
        Role.DISTRICT_ADMIN,
        Role.SCHOOL_ADMIN,
        Role.TEACHER,
        Role.STUDENT,
    },
}


def _bad(message: str, status: int = 400):
    raise BusinessError(status, message)


def account_in_scope(actor, target) -> bool:
    if actor.role == Role.PROVINCE_ADMIN:
        return True
    if actor.org is None or target.org_id is None:
        return False
    return target.org_id in descendant_org_ids(actor.org)


def can_manage_account(actor, target, allow_self: bool = False) -> bool:
    if target.deleted_at is not None:
        return False
    if target.pk == actor.pk and not allow_self:
        return False
    if target.role not in MANAGED_ROLES.get(actor.role, set()):
        return False
    return account_in_scope(actor, target)


def teacher_can_view_student(actor, student) -> bool:
    from apps.classes.models import Class, ClassTeacher

    profile = getattr(student, "student_profile", None)
    if profile is None or profile.classroom_id is None:
        return False
    return (
        ClassTeacher.objects.filter(
            teacher=actor, class_obj_id=profile.classroom_id
        ).exists()
        or Class.objects.filter(pk=profile.classroom_id, head_teacher=actor).exists()
    )


def teacher_can_manage_student(actor, student) -> bool:
    """班主任可维护本班学生账号；科任老师只能查看，不能增删改。"""
    from apps.classes.models import Class

    profile = getattr(student, "student_profile", None)
    if profile is None or profile.classroom_id is None:
        return False
    return Class.objects.filter(
        pk=profile.classroom_id, head_teacher=actor, deleted_at__isnull=True
    ).exists()


def list_accounts(actor, params):
    if actor.role == Role.TEACHER:
        return _list_teacher_students(actor, params)

    roles = MANAGED_ROLES.get(actor.role)
    if roles is None:
        raise BusinessError(403, "当前角色无权查看账号列表")

    queryset = User.objects.filter(deleted_at__isnull=True, role__in=roles).select_related(
        "org", "teacher_profile", "student_profile__classroom"
    )

    if actor.role != Role.PROVINCE_ADMIN:
        queryset = queryset.filter(org_id__in=descendant_org_ids(actor.org))

    role = params.get("role")
    if role:
        if role not in roles:
            raise BusinessError(403, "无权查询该角色账号")
        queryset = queryset.filter(role=role)

    keyword = (params.get("keyword") or "").strip()
    if keyword:
        queryset = queryset.filter(
            Q(username__icontains=keyword)
            | Q(real_name__icontains=keyword)
            | Q(phone__icontains=keyword)
            | Q(student_profile__student_no__icontains=keyword)
        )

    status = params.get("status")
    if status:
        queryset = queryset.filter(status=status)

    org_id = params.get("orgId")
    if org_id:
        try:
            org_id = int(org_id)
        except (TypeError, ValueError):
            raise BusinessError(400, "orgId 必须为整数")
        if actor.role != Role.PROVINCE_ADMIN and org_id not in descendant_org_ids(actor.org):
            raise BusinessError(403, "无权查询该组织账号")
        queryset = queryset.filter(org_id=org_id)

    class_id = params.get("classId")
    if class_id:
        try:
            class_id = int(class_id)
        except (TypeError, ValueError):
            raise BusinessError(400, "classId 必须为整数")
        queryset = queryset.filter(student_profile__classroom_id=class_id)

    return queryset.order_by("-created_at", "-id")


def _list_teacher_students(actor, params):
    """教师只能查看自己任教班级的学生账号。"""
    from apps.classes.models import Class, ClassTeacher

    class_ids = set(
        ClassTeacher.objects.filter(teacher=actor).values_list("class_obj_id", flat=True)
    ) | set(
        Class.objects.filter(head_teacher=actor, deleted_at__isnull=True).values_list(
            "id", flat=True
        )
    )
    queryset = (
        User.objects.filter(
            deleted_at__isnull=True,
            role=Role.STUDENT,
            student_profile__classroom_id__in=class_ids,
        )
        .select_related("org", "student_profile__classroom")
    )
    keyword = (params.get("keyword") or "").strip()
    if keyword:
        queryset = queryset.filter(
            Q(username__icontains=keyword)
            | Q(real_name__icontains=keyword)
            | Q(student_profile__student_no__icontains=keyword)
        )
    status = params.get("status")
    if status:
        queryset = queryset.filter(status=status)
    class_id = params.get("classId")
    if class_id:
        queryset = queryset.filter(student_profile__classroom_id=class_id)
    return queryset.order_by("-created_at", "-id")


def get_account(actor, account_id: int):
    target = (
        User.objects.filter(pk=account_id, deleted_at__isnull=True)
        .select_related("org", "teacher_profile", "student_profile__classroom")
        .first()
    )
    if target is None:
        raise BusinessError(404, "账号不存在")

    if actor.role == Role.TEACHER:
        if target.role != Role.STUDENT or not teacher_can_view_student(actor, target):
            raise BusinessError(403, "无权访问该账号")
        return target

    if not can_manage_account(actor, target):
        raise BusinessError(403, "无权访问该账号")
    return target


def create_teacher(actor, data: dict):
    if actor.role != Role.SCHOOL_ADMIN or actor.org is None:
        raise BusinessError(403, "仅学校管理员可创建教师账号")
    if actor.org.level != OrganizationLevel.SCHOOL:
        raise BusinessError(403, "当前账号不属于学校组织")

    username = data["username"].strip()
    if not is_valid_username(username):
        raise BusinessError(400, "登录账号需为 4~32 位字母、数字或下划线")
    if User.objects.filter(username__iexact=username).exists():
        raise BusinessError(409, "登录账号已存在")

    password = _resolve_initial_password(data)
    status = data.get("status") or AccountStatus.ACTIVE

    with transaction.atomic():
        user = User.objects.create_user(
            username=username,
            password=password,
            real_name=data["realName"].strip(),
            role=Role.TEACHER,
            org=actor.org,
            phone=data["phone"].strip(),
            email=data.get("email"),
            status=status,
        )
        TeacherProfile.objects.create(
            user=user,
            subject=data["subject"],
            title=data.get("title"),
        )

        class_ids = data.get("classIds") or []
        if class_ids:
            from apps.classes.models import Class, ClassTeacher

            classes = list(
                Class.objects.filter(
                    pk__in=class_ids, school=actor.org, deleted_at__isnull=True
                )
            )
            if len(classes) != len(set(class_ids)):
                raise BusinessError(400, "班级不存在或不属于本校")
            taken = ClassTeacher.objects.filter(
                class_obj__in=classes, subject=data["subject"]
            ).values_list("class_obj__name", flat=True)
            if taken:
                raise BusinessError(
                    409, "以下班级已有该学科老师：" + "、".join(sorted(set(taken)))
                )
            ClassTeacher.objects.bulk_create(
                [
                    ClassTeacher(class_obj=cls, teacher=user, subject=data["subject"])
                    for cls in classes
                ]
            )
    log_operation(
        actor, "account.create_teacher", "account", user.id, f"创建教师账号 {username}"
    )
    return user, password


def create_student(actor, data: dict):
    if actor.role == Role.TEACHER:
        from apps.classes.models import Class

        school = actor.org
        if school is None or school.level != OrganizationLevel.SCHOOL:
            raise BusinessError(403, "当前账号不属于学校组织")
        class_id = data.get("classId")
        classroom = Class.objects.filter(
            pk=class_id, school=school, head_teacher=actor, deleted_at__isnull=True
        ).first()
        if classroom is None:
            raise BusinessError(403, "只有班主任可以向本班添加学生")
        data["grade"] = classroom.grade
    elif actor.role == Role.SCHOOL_ADMIN:
        if actor.org is None or actor.org.level != OrganizationLevel.SCHOOL:
            raise BusinessError(403, "当前账号不属于学校组织")
        school = actor.org
        school_id = data.get("schoolId")
        if school_id and int(school_id) != actor.org_id:
            raise BusinessError(403, "无权在其他学校创建学生")
    else:
        from apps.organizations.models import Organization

        school_id = data.get("schoolId")
        if not school_id:
            raise BusinessError(400, "必须指定 schoolId")
        school = Organization.objects.filter(
            pk=school_id, level=OrganizationLevel.SCHOOL, deleted_at__isnull=True
        ).first()
        if school is None:
            raise BusinessError(404, "学校不存在")
        if actor.role != Role.PROVINCE_ADMIN and school.id not in descendant_org_ids(actor.org):
            raise BusinessError(403, "无权在该学校创建学生")

    username = data["username"].strip()
    student_no = data["studentNo"].strip()
    if not is_valid_username(username):
        raise BusinessError(400, "登录账号需为 4~32 位字母、数字或下划线")
    if not is_valid_student_no(student_no):
        from ..validators import STUDENT_NO_REQUIREMENT

        raise BusinessError(400, STUDENT_NO_REQUIREMENT)
    if User.objects.filter(username__iexact=username).exists():
        raise BusinessError(409, "登录账号已存在")
    if StudentProfile.objects.filter(student_no__iexact=student_no).exists():
        raise BusinessError(409, "学籍号已存在")
    grade = data.get("grade")
    if grade is not None and not GRADE_MIN <= int(grade) <= GRADE_MAX:
        raise BusinessError(400, f"年级需为 {GRADE_MIN}~{GRADE_MAX}")

    classroom = None
    class_id = data.get("classId")
    if class_id:
        from apps.classes.models import Class

        classroom = Class.objects.filter(
            pk=class_id, school=school, deleted_at__isnull=True
        ).first()
        if classroom is None:
            raise BusinessError(400, "班级不存在或不属于该学校")
        if data.get("grade") not in (None, classroom.grade):
            raise BusinessError(
                400,
                f"学生年级 {data['grade']} 与班级的 {classroom.grade} 年级不一致",
            )
        data["grade"] = classroom.grade

    password = _resolve_initial_password(data)
    with transaction.atomic():
        user = User.objects.create_user(
            username=username,
            password=password,
            real_name=data["realName"].strip(),
            role=Role.STUDENT,
            org=school,
            phone=data.get("phone"),
            gender=data["gender"],
        )
        StudentProfile.objects.create(
            user=user,
            student_no=student_no,
            grade=data["grade"],
            guardian_phone=data.get("guardianPhone"),
            classroom=classroom,
        )
    log_operation(
        actor, "account.create_student", "account", user.id, f"创建学生账号 {username}"
    )
    return user, password


def list_org_options(actor, params):
    """返回账号创建表单可选的下级组织（市州/区县/学校）。"""
    from apps.organizations.models import Organization

    level = params.get("level")
    if level not in {
        OrganizationLevel.PROVINCE,
        OrganizationLevel.CITY,
        OrganizationLevel.DISTRICT,
        OrganizationLevel.SCHOOL,
    }:
        raise BusinessError(400, "level 必须为 province/city/district/school")
    if actor.role not in {
        Role.PROVINCE_ADMIN,
        Role.CITY_ADMIN,
        Role.DISTRICT_ADMIN,
        Role.QUESTION_ADMIN,
    }:
        raise BusinessError(403, "当前角色无权查询组织选项")

    queryset = Organization.objects.filter(
        level=level, deleted_at__isnull=True
    ).select_related("parent")
    if actor.role not in {Role.PROVINCE_ADMIN, Role.QUESTION_ADMIN}:
        if actor.org is None:
            return []
        queryset = queryset.filter(id__in=descendant_org_ids(actor.org))

    parent_id = params.get("parentId")
    if parent_id:
        try:
            parent_id = int(parent_id)
        except (TypeError, ValueError):
            raise BusinessError(400, "parentId 必须为整数")
        queryset = queryset.filter(parent_id=parent_id)

    keyword = (params.get("keyword") or "").strip()
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword) | Q(code__icontains=keyword))

    return [
        {
            "id": org.id,
            "name": org.name,
            "code": org.code,
            "level": org.level,
            "parentId": org.parent_id,
            "parentName": org.parent.name if org.parent else None,
            "schoolType": org.school_type,
        }
        for org in queryset.order_by("name", "id")[:500]
    ]


def _ensure_org_code(parent, code: str, message: str = "组织编码已存在"):
    from apps.organizations.models import Organization

    if Organization.objects.filter(parent=parent, code=code, deleted_at__isnull=True).exists():
        raise BusinessError(409, message)


def _create_admin_account(
    org, role: str, username: str, real_name: str, phone: str, password: str | None = None
):
    username = username.strip()
    if not is_valid_username(username):
        raise BusinessError(400, "登录账号需为 4~32 位字母、数字或下划线")
    if User.objects.filter(username__iexact=username).exists():
        raise BusinessError(409, "管理员登录账号已存在")
    password = password or settings.DEFAULT_INITIAL_PASSWORD
    if not is_strong_password(password):
        raise BusinessError(400, PASSWORD_REQUIREMENT)
    user = User.objects.create_user(
        username=username,
        password=password,
        real_name=real_name,
        role=role,
        org=org,
        phone=phone,
        status=AccountStatus.ACTIVE,
    )
    return user, password


def create_city(actor, data: dict):
    from apps.organizations.models import Organization

    if actor.role != Role.PROVINCE_ADMIN or actor.org is None:
        raise BusinessError(403, "仅省级管理员可创建市州")
    if actor.org.level != OrganizationLevel.PROVINCE:
        raise BusinessError(403, "当前账号不属于省级组织")

    code = data["cityCode"].strip()
    _ensure_org_code(actor.org, code)
    with transaction.atomic():
        org = Organization.objects.create(
            level=OrganizationLevel.CITY,
            parent=actor.org,
            name=data["cityName"].strip(),
            code=code,
        )
        admin, password = _create_admin_account(
            org,
            Role.CITY_ADMIN,
            data["adminUsername"].strip(),
            data["adminRealName"].strip(),
            data["adminPhone"].strip(),
            data.get("initialPassword"),
        )
    log_operation(
        actor, "account.create_city", "account", admin.id, f"创建市州 {org.name} 及管理员"
    )
    return {"org": org, "admin": admin, "initialPassword": password}


def _resolve_city_parent(actor, city_id):
    from apps.organizations.models import Organization

    if actor.role == Role.CITY_ADMIN:
        if city_id and int(city_id) != actor.org_id:
            raise BusinessError(403, "无权在其他市州创建区县")
        return actor.org
    if actor.role == Role.PROVINCE_ADMIN:
        if not city_id:
            raise BusinessError(400, "必须指定 cityId")
        city = Organization.objects.filter(
            pk=city_id, level=OrganizationLevel.CITY, deleted_at__isnull=True
        ).first()
        if city is None:
            raise BusinessError(404, "市州不存在")
        return city
    raise BusinessError(403, "当前角色无权创建区县")


def create_district(actor, data: dict):
    from apps.organizations.models import Organization

    # 区县由所属市州管理员维护；省级只管理市州，区县管理员只管理本校/本区学校。
    if actor.role != Role.CITY_ADMIN:
        raise BusinessError(403, "仅市州管理员可创建和管理区县")
    parent = _resolve_city_parent(actor, data.get("cityId"))
    code = data["districtCode"].strip()
    _ensure_org_code(parent, code)

    with transaction.atomic():
        org = Organization.objects.create(
            level=OrganizationLevel.DISTRICT,
            parent=parent,
            name=data["districtName"].strip(),
            code=code,
        )
        admin, password = _create_admin_account(
            org,
            Role.DISTRICT_ADMIN,
            data["adminUsername"].strip(),
            data["adminRealName"].strip(),
            data["adminPhone"].strip(),
            data.get("initialPassword"),
        )
    log_operation(
        actor, "account.create_district", "account", admin.id, f"创建区县 {org.name} 及管理员"
    )
    return {"org": org, "admin": admin, "initialPassword": password}


def _resolve_school_parent(actor, data: dict):
    from apps.organizations.models import Organization

    district_id = data.get("districtId")
    city_id = data.get("cityId")

    if actor.role == Role.DISTRICT_ADMIN:
        if district_id and int(district_id) != actor.org_id:
            raise BusinessError(403, "无权在其他区县创建学校")
        return actor.org, OrganizationLevel.DISTRICT

    if actor.role in {Role.CITY_ADMIN, Role.PROVINCE_ADMIN}:
        if not district_id and not city_id:
            if actor.role == Role.CITY_ADMIN and actor.org is not None:
                # 市州管理员未指定区县时，默认创建市直属学校。
                return actor.org, OrganizationLevel.CITY
            raise BusinessError(400, "必须指定 districtId 或 cityId")
        if district_id:
            parent = Organization.objects.filter(
                pk=district_id, level=OrganizationLevel.DISTRICT, deleted_at__isnull=True
            ).first()
            if parent is None:
                raise BusinessError(404, "区县不存在")
            if actor.role == Role.CITY_ADMIN and parent.id not in descendant_org_ids(actor.org):
                raise BusinessError(403, "无权在该区县创建学校")
            return parent, OrganizationLevel.DISTRICT
        parent = Organization.objects.filter(
            pk=city_id, level=OrganizationLevel.CITY, deleted_at__isnull=True
        ).first()
        if parent is None:
            raise BusinessError(404, "市州不存在")
        if actor.role == Role.CITY_ADMIN and parent.id != actor.org_id:
            raise BusinessError(403, "无权在其他市州创建市直属学校")
        return parent, OrganizationLevel.CITY

    raise BusinessError(403, "当前角色无权创建学校")


def create_school(actor, data: dict):
    from apps.organizations.models import Organization

    if actor.role not in {Role.DISTRICT_ADMIN, Role.CITY_ADMIN, Role.PROVINCE_ADMIN}:
        raise BusinessError(403, "当前角色无权创建学校")
    parent, parent_level = _resolve_school_parent(actor, data)
    if parent_level == OrganizationLevel.DISTRICT and actor.role != Role.PROVINCE_ADMIN:
        if parent.id not in descendant_org_ids(actor.org) and parent.id != actor.org_id:
            raise BusinessError(403, "无权在该区县创建学校")

    code = data["schoolCode"].strip()
    _ensure_org_code(parent, code)

    with transaction.atomic():
        org = Organization.objects.create(
            level=OrganizationLevel.SCHOOL,
            parent=parent,
            name=data["schoolName"].strip(),
            code=code,
            school_type=data["schoolType"],
            address=data.get("address"),
        )
        admin, password = _create_admin_account(
            org,
            Role.SCHOOL_ADMIN,
            data["adminUsername"].strip(),
            data["adminRealName"].strip(),
            data["adminPhone"].strip(),
            data.get("initialPassword"),
        )
    log_operation(
        actor, "account.create_school", "account", admin.id, f"创建学校 {org.name} 及管理员"
    )
    return {"org": org, "admin": admin, "initialPassword": password}


def _can_manage_class_account(actor, target, allow_self: bool = False) -> bool:
    """账号更新/删除/重置密码的统一权限判定。"""
    if actor.role == Role.TEACHER:
        return target.role == Role.STUDENT and teacher_can_manage_student(actor, target)
    # 省端只读查看区县及区县管理员，创建/编辑/删除/重置由所属市州管理员负责。
    if actor.role == Role.PROVINCE_ADMIN and target.role == Role.DISTRICT_ADMIN:
        return False
    return can_manage_account(actor, target, allow_self=allow_self)


def update_account(actor, target, data: dict):
    if not _can_manage_class_account(actor, target):
        raise BusinessError(403, "无权修改该账号")

    if "subject" in data or "title" in data:
        if target.role != Role.TEACHER:
            raise BusinessError(400, "仅教师账号可修改学科与职称")
        profile = getattr(target, "teacher_profile", None)
        if profile is None:
            profile = TeacherProfile.objects.create(user=target)
        if "subject" in data:
            from apps.classes.models import ClassTeacher

            if (
                profile.subject
                and profile.subject != data["subject"]
                and ClassTeacher.objects.filter(
                    teacher=target, class_obj__deleted_at__isnull=True
                ).exists()
            ):
                raise BusinessError(409, "该教师已在班级任教，请先解除任课关系再修改任教学科")
            profile.subject = data["subject"]
        if "title" in data:
            profile.title = data["title"]
        profile.save(update_fields=["subject", "title", "updated_at"])

    if {"studentNo", "grade", "classId"} & set(data):
        if target.role != Role.STUDENT:
            raise BusinessError(400, "仅学生账号可修改学籍号、年级或班级")
        from apps.classes.models import Class

        profile = getattr(target, "student_profile", None)
        if profile is None:
            raise BusinessError(400, "学生资料不存在")

        if "studentNo" in data and data["studentNo"] is not None:
            student_no = str(data["studentNo"]).strip()
            # 历史学籍号不批量改写：未修改时允许保存；一旦变更必须符合固定格式。
            if student_no != (profile.student_no or "").strip() and not is_valid_student_no(
                student_no
            ):
                from ..validators import STUDENT_NO_REQUIREMENT

                raise BusinessError(400, STUDENT_NO_REQUIREMENT)
            if (
                StudentProfile.objects.filter(student_no__iexact=student_no)
                .exclude(pk=profile.pk)
                .exists()
            ):
                raise BusinessError(409, "学籍号已存在")
            profile.student_no = student_no

        new_grade = data.get("grade", profile.grade)
        if "grade" in data:
            if data["grade"] is None:
                raise BusinessError(400, "年级不能为空")
            new_grade = int(data["grade"])
            if not GRADE_MIN <= new_grade <= GRADE_MAX:
                raise BusinessError(400, f"年级需为 {GRADE_MIN}~{GRADE_MAX}")

        classroom = profile.classroom
        if "classId" in data:
            classroom = None
            if data["classId"] is not None:
                classroom = Class.objects.filter(
                    pk=data["classId"], school=target.org, deleted_at__isnull=True
                ).first()
                if classroom is None:
                    raise BusinessError(400, "班级不存在或不属于该学生所在学校")

        if classroom is not None:
            if new_grade is not None and new_grade != classroom.grade:
                raise BusinessError(
                    409,
                    f"学生年级为 {new_grade} 年级，与班级的 {classroom.grade} 年级不一致",
                )
            if new_grade is None:
                new_grade = classroom.grade

        profile.grade = new_grade
        profile.classroom = classroom
        profile.save(update_fields=["student_no", "grade", "classroom", "updated_at"])

    changed = []
    for api_field, model_field in (
        ("realName", "real_name"),
        ("phone", "phone"),
        ("email", "email"),
        ("status", "status"),
    ):
        if api_field in data:
            value = data[api_field]
            if api_field == "realName":
                value = value.strip()
            setattr(target, model_field, value)
            changed.append(model_field)

    if "status" in data and data["status"] == AccountStatus.DISABLED:
        target.token_version += 1
        changed.append("token_version")

    if changed:
        target.save(update_fields=[*changed, "updated_at"])
    log_operation(
        actor, "account.update", "account", target.id, f"修改账号 {target.username}"
    )
    return target


def delete_account(actor, target):
    from apps.classes.models import Class, ClassTeacher
    from apps.organizations.models import Organization

    if not _can_manage_class_account(actor, target):
        raise BusinessError(403, "无权删除该账号")

    if target.headed_classes.filter(deleted_at__isnull=True, status=ClassStatus.ACTIVE).exists():
        raise BusinessError(409, "该账号仍担任班主任，请先调整班级")
    if ClassTeacher.objects.filter(
        teacher=target, class_obj__deleted_at__isnull=True
    ).exists():
        raise BusinessError(409, "该教师仍任教班级，请先解除任课关系")
    if target.role in {Role.CITY_ADMIN, Role.DISTRICT_ADMIN, Role.SCHOOL_ADMIN}:
        if Organization.objects.filter(parent=target.org, deleted_at__isnull=True).exists():
            raise BusinessError(409, "存在下属组织，无法删除该账号")

    target.token_version += 1
    target.save(update_fields=["token_version", "updated_at"])
    target.delete()
    log_operation(
        actor, "account.delete", "account", target.id, f"删除账号 {target.username}"
    )
    return {"deleted": True, "accountId": target.id}


def reset_password(actor, target, new_password: str | None, force_change: bool = True):
    if not _can_manage_class_account(actor, target):
        raise BusinessError(403, "无权重置该账号密码")

    if new_password and not is_strong_password(new_password):
        raise BusinessError(400, PASSWORD_REQUIREMENT)

    password = new_password or generate_password()
    target.set_password(password)
    target.token_version += 1
    target.must_change_password = force_change
    target.save(
        update_fields=["password", "token_version", "must_change_password", "updated_at"]
    )
    # 仅保留 10 分钟，避免临时密码长期以明文驻留；管理员仍可在有效期内复查。
    cache.set(
        f"{TEMPORARY_PASSWORD_CACHE_PREFIX}{target.id}",
        password,
        TEMPORARY_PASSWORD_TTL_SECONDS,
    )
    log_operation(
        actor, "account.reset_password", "account", target.id, f"重置账号 {target.username} 密码"
    )
    return {
        "accountId": target.id,
        "temporaryPassword": password,
        "forceChange": force_change,
    }


def get_temporary_password(actor, target):
    """读取最近一次重置产生、且仍在有效期内的临时密码。"""
    if not _can_manage_class_account(actor, target):
        raise BusinessError(403, "无权重置该账号密码")
    password = cache.get(f"{TEMPORARY_PASSWORD_CACHE_PREFIX}{target.id}")
    if not password:
        raise BusinessError(404, "临时密码已过期，请重新重置")
    return {
        "accountId": target.id,
        "temporaryPassword": password,
        "expiresIn": TEMPORARY_PASSWORD_TTL_SECONDS,
    }
