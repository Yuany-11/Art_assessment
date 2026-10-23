"""班级业务逻辑（CLS-01 ~ CLS-13）。"""
import datetime
import secrets

from django.db.models import Q
from django.utils import timezone

from common.audit import log_operation
from common.enums import (
    ClassStatus,
    JoinRequestStatus,
    JoinRequestType,
    OrganizationLevel,
    Role,
    Subject,
)
from common.exceptions import BusinessError
from common.scope import descendant_org_ids

from apps.accounts.models import StudentProfile, User
from apps.accounts.services.profile import format_datetime

from .models import Class, ClassTeacher, JoinRequest


def _bad(message: str, status: int = 400):
    raise BusinessError(status, message)


def class_queryset_for(actor):
    queryset = Class.objects.filter(deleted_at__isnull=True).select_related(
        "school", "head_teacher"
    )
    if actor.role == Role.PROVINCE_ADMIN:
        return queryset
    if actor.role in {Role.CITY_ADMIN, Role.DISTRICT_ADMIN, Role.SCHOOL_ADMIN}:
        return queryset.filter(school_id__in=descendant_org_ids(actor.org))
    if actor.role == Role.TEACHER:
        return queryset.filter(
            Q(head_teacher=actor) | Q(subject_teachers__teacher=actor)
        ).distinct()
    if actor.role == Role.STUDENT:
        return queryset.filter(students__user=actor, students__deleted_at__isnull=True).distinct()
    return queryset.none()


def can_view_class(actor, classroom: Class) -> bool:
    return class_queryset_for(actor).filter(pk=classroom.pk).exists()


def can_manage_class(actor, classroom: Class) -> bool:
    if actor.role == Role.TEACHER:
        return classroom.head_teacher_id == actor.id
    if actor.role == Role.SCHOOL_ADMIN:
        return classroom.school_id == actor.org_id
    return False


def can_view_requests(actor, classroom: Class) -> bool:
    if actor.role == Role.SCHOOL_ADMIN:
        return classroom.school_id == actor.org_id
    if actor.role == Role.TEACHER:
        return (
            classroom.head_teacher_id == actor.id
            or ClassTeacher.objects.filter(class_obj=classroom, teacher=actor).exists()
        )
    return False


def build_class_item(classroom: Class) -> dict:
    student_count = StudentProfile.objects.filter(
        classroom=classroom, deleted_at__isnull=True, user__deleted_at__isnull=True
    ).count()
    return {
        "id": classroom.id,
        "classCode": classroom.class_code,
        "name": classroom.name,
        "grade": classroom.grade,
        "schoolId": classroom.school_id,
        "schoolName": classroom.school.name,
        "headTeacherId": classroom.head_teacher_id,
        "headTeacherName": classroom.head_teacher.real_name if classroom.head_teacher else None,
        "studentCount": student_count,
        "status": classroom.status,
        "createdAt": format_datetime(classroom.created_at),
    }


def build_class_detail(classroom: Class) -> dict:
    data = build_class_item(classroom)
    teachers = ClassTeacher.objects.filter(
        class_obj=classroom, deleted_at__isnull=True
    ).select_related("teacher")
    data.update(
        {
            "description": classroom.description,
            "subjectTeachers": [
                {
                    "id": item.teacher_id,
                    "realName": item.teacher.real_name,
                    "subject": item.subject,
                }
                for item in teachers
            ],
            "createdBy": classroom.created_by_id,
            "updatedAt": format_datetime(classroom.updated_at),
        }
    )
    return data


def build_join_request(item: JoinRequest) -> dict:
    return {
        "id": item.id,
        "classId": item.class_obj_id,
        "className": item.class_obj.name,
        "requesterId": item.requester_id,
        "requesterName": item.requester.real_name,
        "requesterRole": item.requester_role,
        "type": item.type,
        "targetClassId": item.target_class_id,
        "targetClassName": item.target_class.name if item.target_class else None,
        "status": item.status,
        "reason": item.reason,
        "reviewerId": item.reviewer_id,
        "reviewerName": item.reviewer.real_name if item.reviewer else None,
        "reviewComment": item.review_comment,
        "reviewedAt": format_datetime(item.reviewed_at),
        "createdAt": format_datetime(item.created_at),
    }


def list_classes(actor, params):
    queryset = class_queryset_for(actor)

    keyword = (params.get("keyword") or "").strip()
    if keyword:
        queryset = queryset.filter(
            Q(name__icontains=keyword) | Q(class_code__icontains=keyword)
        )

    grade = params.get("grade")
    if grade:
        try:
            queryset = queryset.filter(grade=int(grade))
        except (TypeError, ValueError):
            raise BusinessError(400, "grade 必须为整数")

    school_id = params.get("schoolId")
    if school_id:
        try:
            school_id = int(school_id)
        except (TypeError, ValueError):
            raise BusinessError(400, "schoolId 必须为整数")
        if actor.role != Role.PROVINCE_ADMIN and school_id not in descendant_org_ids(actor.org):
            raise BusinessError(403, "无权查询该学校班级")
        queryset = queryset.filter(school_id=school_id)

    status = params.get("status")
    if status:
        queryset = queryset.filter(status=status)

    return queryset.order_by("-created_at", "-id")


def search_class(actor, class_code: str):
    if actor.role not in {Role.STUDENT, Role.TEACHER, Role.SCHOOL_ADMIN}:
        raise BusinessError(403, "当前角色无权使用班级号查询")
    code = (class_code or "").strip()
    if not code:
        raise BusinessError(400, "班级号不能为空")
    classroom = Class.objects.filter(
        class_code=code, deleted_at__isnull=True
    ).select_related("school", "head_teacher").first()
    if classroom is None:
        raise BusinessError(404, "班级不存在")
    return classroom


def get_class(actor, class_id: int) -> Class:
    classroom = Class.objects.filter(pk=class_id, deleted_at__isnull=True).select_related(
        "school", "head_teacher"
    ).first()
    if classroom is None:
        raise BusinessError(404, "班级不存在")
    if not can_view_class(actor, classroom):
        raise BusinessError(403, "无权访问该班级")
    return classroom


def _generate_class_code() -> str:
    year = datetime.date.today().year
    for _ in range(20):
        code = f"C{year}{secrets.randbelow(90000) + 10000}"
        if not Class.objects.filter(class_code=code).exists():
            return code
    raise BusinessError(500, "班级号生成失败，请重试")


def create_class(actor, data: dict) -> Class:
    if actor.role == Role.TEACHER:
        if actor.org is None or actor.org.level != OrganizationLevel.SCHOOL:
            raise BusinessError(403, "教师不属于学校组织")
        school = actor.org
        head_teacher = actor
    elif actor.role == Role.SCHOOL_ADMIN:
        if actor.org is None or actor.org.level != OrganizationLevel.SCHOOL:
            raise BusinessError(403, "学校管理员不属于学校组织")
        school = actor.org
        head_teacher = None
        head_id = data.get("headTeacherId")
        if head_id:
            head_teacher = User.objects.filter(
                pk=head_id, org=school, role=Role.TEACHER, deleted_at__isnull=True
            ).first()
            if head_teacher is None:
                raise BusinessError(400, "班主任必须是本校教师")
    else:
        raise BusinessError(403, "当前角色无权创建班级")

    class_code = (data.get("classCode") or "").strip() or _generate_class_code()
    if Class.objects.filter(class_code=class_code).exists():
        raise BusinessError(409, "班级号已存在")

    classroom = Class.objects.create(
        name=data["name"].strip(),
        class_code=class_code,
        grade=data["grade"],
        school=school,
        head_teacher=head_teacher,
        description=data.get("description"),
        created_by=actor,
        status=ClassStatus.ACTIVE,
    )
    log_operation(actor, "class.create", "system", classroom.id, f"创建班级 {classroom.name}")
    return classroom


def update_class(actor, classroom: Class, data: dict) -> Class:
    if not can_manage_class(actor, classroom):
        raise BusinessError(403, "无权修改该班级")

    if "headTeacherId" in data:
        head_id = data["headTeacherId"]
        if head_id is None:
            classroom.head_teacher = None
        else:
            head_teacher = User.objects.filter(
                pk=head_id,
                org=classroom.school_id,
                role=Role.TEACHER,
                deleted_at__isnull=True,
            ).first()
            if head_teacher is None:
                raise BusinessError(400, "班主任必须是本校教师")
            classroom.head_teacher = head_teacher

    for api_field, model_field in (
        ("name", "name"),
        ("grade", "grade"),
        ("description", "description"),
        ("status", "status"),
    ):
        if api_field in data:
            value = data[api_field]
            if api_field == "name":
                value = value.strip()
            setattr(classroom, model_field, value)

    if data:
        classroom.save()
    log_operation(actor, "class.update", "system", classroom.id, f"修改班级 {classroom.name}")
    return classroom


def delete_class(actor, classroom: Class):
    if not can_manage_class(actor, classroom):
        raise BusinessError(403, "无权解散该班级")
    if StudentProfile.objects.filter(
        classroom=classroom, deleted_at__isnull=True, user__deleted_at__isnull=True
    ).exists():
        raise BusinessError(409, "班级仍有学生，请先转班或移除学生")
    if JoinRequest.objects.filter(
        Q(class_obj=classroom) | Q(target_class=classroom),
        status=JoinRequestStatus.PENDING,
        deleted_at__isnull=True,
    ).exists():
        raise BusinessError(409, "仍有待审核申请，无法解散班级")

    classroom.status = ClassStatus.ARCHIVED
    classroom.save(update_fields=["status", "updated_at"])
    classroom.delete()
    log_operation(actor, "class.delete", "system", classroom.id, f"解散班级 {classroom.name}")
    return {"deleted": True, "classId": classroom.id}


def create_join_request(actor, class_id: int, data: dict) -> JoinRequest:
    classroom = Class.objects.filter(pk=class_id, deleted_at__isnull=True).first()
    if classroom is None:
        raise BusinessError(404, "班级不存在")
    if classroom.status != ClassStatus.ACTIVE:
        raise BusinessError(409, "班级已归档，无法申请")

    profile = getattr(actor, "student_profile", None)

    if actor.role == Role.STUDENT:
        if profile is None:
            raise BusinessError(400, "学生资料不存在")
        if profile.classroom_id is not None:
            raise BusinessError(409, "已在班级中，如需更换班级请提交转班申请")
        if JoinRequest.objects.filter(
            requester=actor,
            type=JoinRequestType.JOIN,
            status=JoinRequestStatus.PENDING,
            deleted_at__isnull=True,
        ).exists():
            raise BusinessError(409, "已存在待审核的加入申请")
        item = JoinRequest.objects.create(
            class_obj=classroom,
            requester=actor,
            requester_role=Role.STUDENT,
            type=JoinRequestType.JOIN,
            reason=data.get("reason"),
        )
        log_operation(
            actor, "class.join_apply", "system", item.id, f"申请加入班级 {classroom.name}"
        )
        return item

    if actor.role == Role.TEACHER:
        subject = data.get("subject")
        if subject not in Subject.values:
            raise BusinessError(400, "教师申请加入班级必须填写任教学科")
        if ClassTeacher.objects.filter(class_obj=classroom, teacher=actor).exists():
            raise BusinessError(409, "已任教该班级")
        if JoinRequest.objects.filter(
            requester=actor,
            class_obj=classroom,
            type=JoinRequestType.JOIN,
            status=JoinRequestStatus.PENDING,
            deleted_at__isnull=True,
        ).exists():
            raise BusinessError(409, "已存在待审核的加入申请")
        item = JoinRequest.objects.create(
            class_obj=classroom,
            requester=actor,
            requester_role=Role.TEACHER,
            type=JoinRequestType.JOIN,
            subject=subject,
            reason=data.get("reason"),
        )
        log_operation(
            actor, "class.join_apply", "system", item.id, f"教师申请任教班级 {classroom.name}"
        )
        return item

    raise BusinessError(403, "当前角色无权申请加入班级")


def create_leave_request(actor, class_id: int, data: dict) -> JoinRequest:
    classroom = Class.objects.filter(pk=class_id, deleted_at__isnull=True).first()
    if classroom is None:
        raise BusinessError(404, "班级不存在")
    if actor.role != Role.STUDENT:
        raise BusinessError(403, "仅学生可申请退出班级")

    profile = getattr(actor, "student_profile", None)
    if profile is None or profile.classroom_id != classroom.id:
        raise BusinessError(400, "当前不在该班级")
    if JoinRequest.objects.filter(
        requester=actor,
        class_obj=classroom,
        type=JoinRequestType.LEAVE,
        status=JoinRequestStatus.PENDING,
        deleted_at__isnull=True,
    ).exists():
        raise BusinessError(409, "已存在待审核的退出申请")

    item = JoinRequest.objects.create(
        class_obj=classroom,
        requester=actor,
        requester_role=Role.STUDENT,
        type=JoinRequestType.LEAVE,
        reason=data.get("reason"),
    )
    log_operation(actor, "class.leave_apply", "system", item.id, f"申请退出班级 {classroom.name}")
    return item


def create_change_request(actor, class_id: int, data: dict) -> JoinRequest:
    classroom = Class.objects.filter(pk=class_id, deleted_at__isnull=True).first()
    if classroom is None:
        raise BusinessError(404, "班级不存在")
    if actor.role != Role.STUDENT:
        raise BusinessError(403, "仅学生可申请更换班级")

    profile = getattr(actor, "student_profile", None)
    if profile is None or profile.classroom_id != classroom.id:
        raise BusinessError(400, "当前不在该班级")

    target = Class.objects.filter(pk=data["targetClassId"], deleted_at__isnull=True).first()
    if target is None:
        raise BusinessError(404, "目标班级不存在")
    if target.id == classroom.id:
        raise BusinessError(400, "目标班级不能与当前班级相同")
    if target.school_id != classroom.school_id:
        raise BusinessError(400, "仅支持同校转班")
    if target.status != ClassStatus.ACTIVE:
        raise BusinessError(409, "目标班级已归档")

    if JoinRequest.objects.filter(
        requester=actor,
        type=JoinRequestType.CHANGE,
        status=JoinRequestStatus.PENDING,
        deleted_at__isnull=True,
    ).exists():
        raise BusinessError(409, "已存在待审核的转班申请")

    item = JoinRequest.objects.create(
        class_obj=classroom,
        requester=actor,
        requester_role=Role.STUDENT,
        type=JoinRequestType.CHANGE,
        target_class=target,
        reason=data["reason"],
    )
    log_operation(
        actor,
        "class.change_apply",
        "system",
        item.id,
        f"申请从 {classroom.name} 转至 {target.name}",
    )
    return item


def list_requests(actor, classroom: Class, params):
    if not can_view_requests(actor, classroom):
        raise BusinessError(403, "无权查看该班级申请")
    queryset = JoinRequest.objects.filter(
        Q(class_obj=classroom) | Q(target_class=classroom), deleted_at__isnull=True
    ).select_related("class_obj", "target_class", "requester", "reviewer")

    request_type = params.get("type")
    if request_type:
        queryset = queryset.filter(type=request_type)

    status = params.get("status", JoinRequestStatus.PENDING)
    if status:
        queryset = queryset.filter(status=status)

    return queryset.order_by("-created_at", "-id")


def _get_pending_request(class_id: int, request_id: int) -> JoinRequest:
    item = JoinRequest.objects.filter(pk=request_id, deleted_at__isnull=True).select_related(
        "class_obj", "target_class", "requester"
    ).first()
    if item is None:
        raise BusinessError(404, "申请不存在")
    if item.class_obj_id != class_id and item.target_class_id != class_id:
        raise BusinessError(404, "申请不存在")
    if item.status != JoinRequestStatus.PENDING:
        raise BusinessError(409, "该申请已处理")
    return item


def review_request(actor, classroom: Class, request_id: int, data: dict) -> JoinRequest:
    if not can_view_requests(actor, classroom):
        raise BusinessError(403, "无权审核该班级申请")
    item = _get_pending_request(classroom.id, request_id)

    action = data["action"]
    item.reviewer = actor
    item.review_comment = data.get("comment")
    item.reviewed_at = timezone.now()

    if action == "reject":
        item.status = JoinRequestStatus.REJECTED
        item.save()
        log_operation(
            actor,
            "class.review",
            "system",
            item.id,
            f"驳回 {item.get_type_display()} 申请（{item.class_obj.name}）",
        )
        return item

    if item.type == JoinRequestType.JOIN:
        if item.requester_role == Role.STUDENT:
            profile = getattr(item.requester, "student_profile", None)
            if profile is None:
                raise BusinessError(400, "学生资料不存在")
            if profile.classroom_id is not None:
                raise BusinessError(409, "该学生已在班级中")
            profile.classroom = item.class_obj
            profile.save(update_fields=["classroom", "updated_at"])
        else:
            teacher_profile = getattr(item.requester, "teacher_profile", None)
            subject = item.subject or (teacher_profile.subject if teacher_profile else None)
            if subject is None:
                raise BusinessError(400, "教师任教学科缺失")
            ClassTeacher.objects.get_or_create(
                class_obj=item.class_obj, teacher=item.requester, defaults={"subject": subject}
            )
        item.status = JoinRequestStatus.APPROVED
    elif item.type == JoinRequestType.LEAVE:
        profile = getattr(item.requester, "student_profile", None)
        if profile is None or profile.classroom_id != item.class_obj_id:
            raise BusinessError(409, "学生已不在该班级")
        profile.classroom = None
        profile.save(update_fields=["classroom", "updated_at"])
        item.status = JoinRequestStatus.APPROVED
    elif item.type == JoinRequestType.CHANGE:
        if classroom.id == item.class_obj_id:
            item.source_approved = True
        if classroom.id == item.target_class_id:
            item.target_approved = True
        if item.source_approved and item.target_approved:
            profile = getattr(item.requester, "student_profile", None)
            if profile is None or profile.classroom_id != item.class_obj_id:
                raise BusinessError(409, "学生已不在原班级")
            profile.classroom = item.target_class
            profile.save(update_fields=["classroom", "updated_at"])
            item.status = JoinRequestStatus.APPROVED
    else:
        raise BusinessError(400, "未知的申请类型")

    item.save()
    log_operation(
        actor,
        "class.review",
        "system",
        item.id,
        f"审核通过 {item.get_type_display()} 申请（{item.class_obj.name}）",
    )
    return item


def can_view_class_students(actor, classroom: Class) -> bool:
    if actor.role == Role.SCHOOL_ADMIN:
        return classroom.school_id == actor.org_id
    if actor.role in {Role.DISTRICT_ADMIN, Role.CITY_ADMIN, Role.PROVINCE_ADMIN}:
        return can_view_class(actor, classroom)
    if actor.role == Role.TEACHER:
        return can_view_requests(actor, classroom)
    return False


def list_students(actor, classroom: Class, params):
    if not can_view_class_students(actor, classroom):
        raise BusinessError(403, "无权查看该班级学生")

    queryset = (
        User.objects.filter(
            role=Role.STUDENT,
            deleted_at__isnull=True,
            student_profile__classroom=classroom,
            student_profile__deleted_at__isnull=True,
        )
        .select_related("student_profile__classroom")
        .order_by("-created_at")
    )

    keyword = (params.get("keyword") or "").strip()
    if keyword:
        queryset = queryset.filter(
            Q(real_name__icontains=keyword)
            | Q(username__icontains=keyword)
            | Q(student_profile__student_no__icontains=keyword)
        )
    status = params.get("status")
    if status:
        queryset = queryset.filter(status=status)
    return queryset


def remove_student(actor, classroom: Class, student_id: int):
    if not can_view_class_students(actor, classroom):
        raise BusinessError(403, "无权移除该班级学生")
    if actor.role not in {Role.TEACHER, Role.SCHOOL_ADMIN}:
        raise BusinessError(403, "当前角色无权移除学生")

    profile = StudentProfile.objects.filter(
        user_id=student_id, deleted_at__isnull=True
    ).first()
    if profile is None:
        raise BusinessError(404, "学生不存在")
    if profile.classroom_id != classroom.id:
        raise BusinessError(400, "该学生不在当前班级")

    profile.classroom = None
    profile.save(update_fields=["classroom", "updated_at"])
    log_operation(
        actor, "class.student_remove", "system", classroom.id, f"移除班级学生 {student_id}"
    )
    return {"removed": True, "classId": classroom.id, "studentId": student_id}
