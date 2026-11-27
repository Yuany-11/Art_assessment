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


SUBJECT_TEACHER_LABELS = {
    Subject.MUSIC: "音乐老师",
    Subject.ART: "美术老师",
}


def class_identity_for(actor, classroom: Class):
    """返回当前用户在该班级中的身份，用于班级管理列表/详情展示。"""
    if actor is None or not getattr(actor, "is_authenticated", False):
        return None
    if actor.role == Role.STUDENT:
        belongs = StudentProfile.objects.filter(
            classroom=classroom, user=actor, deleted_at__isnull=True
        ).exists()
        return "学生" if belongs else None
    if actor.role == Role.TEACHER:
        labels = []
        if classroom.head_teacher_id == actor.id:
            labels.append("班主任")
        subject = (
            ClassTeacher.objects.filter(
                class_obj=classroom, teacher=actor, deleted_at__isnull=True
            )
            .values_list("subject", flat=True)
            .first()
        )
        if subject:
            labels.append(SUBJECT_TEACHER_LABELS.get(subject, "任课老师"))
        return " · ".join(labels) or None
    labels = {value: label for value, label in Role.choices}
    return labels.get(actor.role)


def build_class_item(classroom: Class, actor=None) -> dict:
    student_count = StudentProfile.objects.filter(
        classroom=classroom, deleted_at__isnull=True, user__deleted_at__isnull=True
    ).count()
    head = classroom.head_teacher
    head_profile = getattr(head, "teacher_profile", None) if head else None
    return {
        "id": classroom.id,
        "classCode": classroom.class_code,
        "name": classroom.name,
        "grade": classroom.grade,
        "schoolId": classroom.school_id,
        "schoolName": classroom.school.name,
        "headTeacherId": classroom.head_teacher_id,
        "headTeacherName": head.real_name if head else None,
        "headTeacherAccount": head.username if head else None,
        "headTeacherSubject": head_profile.subject if head_profile else None,
        "headTeacherPhone": head.phone if head else None,
        "studentCount": student_count,
        "status": classroom.status,
        "myIdentity": class_identity_for(actor, classroom),
        "createdAt": format_datetime(classroom.created_at),
    }


def build_class_detail(classroom: Class, actor=None) -> dict:
    data = build_class_item(classroom, actor)
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
        # 转班双签进度：原班级、目标班级是否已通过。
        "sourceApproved": bool(item.source_approved),
        "targetApproved": bool(item.target_approved),
        # 汇总列表里标注当前账号应使用哪个班级发起审核（转班申请需原班/目标班各自通过）。
        "reviewClassId": getattr(item, "review_class_id", None),
    }


def list_classes(actor, params):
    if actor.role == Role.STUDENT:
        # 转班下拉需要看到本校同年级的其他正常班级；学生只读列表，写操作仍由
        # create_class / update_class 拒绝。
        profile = getattr(actor, "student_profile", None)
        classroom = getattr(profile, "classroom", None)
        school_id = classroom.school_id if classroom else actor.school_id
        grade = (profile.grade if profile else None) or (
            classroom.grade if classroom else None
        )
        if not school_id or not grade:
            return Class.objects.none()
        queryset = Class.objects.filter(
            deleted_at__isnull=True,
            school_id=school_id,
            grade=grade,
            status=ClassStatus.ACTIVE,
        )
    else:
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

    if actor.role == Role.STUDENT:
        return queryset.order_by("name", "id")
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


def ensure_head_teacher_available(head_teacher, exclude_class_id=None):
    """每位班主任同一时间只能管理一个班级。"""
    queryset = Class.objects.filter(
        head_teacher=head_teacher, deleted_at__isnull=True
    )
    if exclude_class_id is not None:
        queryset = queryset.exclude(pk=exclude_class_id)
    if queryset.exists():
        raise BusinessError(
            409, "该教师已是其他班级的班主任，每位班主任只能管理一个班级"
        )


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
        ensure_head_teacher_available(head_teacher)
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
            ensure_head_teacher_available(head_teacher)
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
            if classroom.head_teacher_id != head_teacher.id:
                ensure_head_teacher_available(
                    head_teacher, exclude_class_id=classroom.id
                )
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


def _notify_request_reviewers(classroom, item):
    """班级申请提交后通知班主任和科任教师，避免只能靠页面轮询。"""
    from apps.exams.services import notification
    from common.enums import NotificationType

    recipients = {}
    if classroom.head_teacher_id:
        recipients[classroom.head_teacher_id] = classroom.head_teacher
    for link in classroom.subject_teachers.select_related("teacher"):
        recipients[link.teacher_id] = link.teacher
    for teacher in recipients.values():
        notification.notify(
            teacher,
            type=NotificationType.SYSTEM,
            title="新的班级申请",
            content=(
                f"{item.requester.real_name} 提交了"
                f"{item.get_type_display()}申请（{classroom.name}），请及时审核。"
            ),
            link="/teacher/classes",
        )


def _notify_request_result(item, approved):
    from apps.exams.services import notification
    from common.enums import NotificationType

    notification.notify(
        item.requester,
        type=NotificationType.SYSTEM,
        title="班级申请已通过" if approved else "班级申请未通过",
        content=(
            f"你的{item.get_type_display()}申请（{item.class_obj.name}）"
            f"{'已通过' if approved else '未通过'}。"
        ),
        link="/student/home" if item.requester_role == Role.STUDENT else "/teacher/classes",
    )


def _ensure_student_grade_matches(profile, classroom: Class) -> None:
    """学生年级必须与班级年级一致，避免把七年级学生分到八年级班。"""
    if profile is None or classroom.grade is None:
        return
    # 档案年级缺失时用当前班级年级兜底，保证转班仍然受同年级约束。
    student_grade = profile.grade or (
        profile.classroom.grade if profile.classroom else None
    )
    if student_grade is not None and student_grade != classroom.grade:
        raise BusinessError(
            409,
            f"学生年级为 {student_grade} 年级，与班级的 {classroom.grade} 年级不一致",
        )


def create_join_request(actor, class_id: int, data: dict) -> JoinRequest:
    classroom = Class.objects.filter(pk=class_id, deleted_at__isnull=True).first()
    if classroom is None:
        raise BusinessError(404, "班级不存在")
    if classroom.status != ClassStatus.ACTIVE:
        raise BusinessError(409, "班级已归档，无法申请")
    if actor.role in {Role.STUDENT, Role.TEACHER} and actor.school_id != classroom.school_id:
        raise BusinessError(403, "只能申请加入本校班级")

    profile = getattr(actor, "student_profile", None)

    if actor.role == Role.STUDENT:
        if profile is None:
            raise BusinessError(400, "学生资料不存在")
        if profile.classroom_id is not None:
            if profile.classroom_id == classroom.id:
                raise BusinessError(409, "已在该班级中")
            raise BusinessError(409, "已在其他班级，如需更换班级请提交转班申请")
        _ensure_student_grade_matches(profile, classroom)
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
        _notify_request_reviewers(classroom, item)
        return item

    if actor.role == Role.TEACHER:
        subject = data.get("subject")
        if subject not in Subject.values:
            raise BusinessError(400, "教师申请加入班级必须填写任教学科")
        profile = getattr(actor, "teacher_profile", None)
        if profile is not None and profile.subject and profile.subject != subject:
            raise BusinessError(400, "申请学科必须与本人任教学科一致")
        if ClassTeacher.objects.filter(class_obj=classroom, teacher=actor).exists():
            raise BusinessError(409, "已任教该班级")
        if ClassTeacher.objects.filter(class_obj=classroom, subject=subject).exists():
            label = dict(Subject.choices).get(subject, subject)
            raise BusinessError(409, f"该班已有{label}老师，每个班每学科仅限一位科任老师")
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
        _notify_request_reviewers(classroom, item)
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
    _notify_request_reviewers(classroom, item)
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
    _ensure_student_grade_matches(profile, target)

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
    _notify_request_reviewers(classroom, item)
    _notify_request_reviewers(target, item)
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


def list_pending_requests(actor, params):
    """班主任/学校管理员查看自己可审核的全部待处理申请（免去逐班进入）。"""
    if actor.role == Role.TEACHER:
        managed = Class.objects.filter(
            deleted_at__isnull=True, head_teacher=actor
        )
    elif actor.role == Role.SCHOOL_ADMIN:
        managed = Class.objects.filter(
            deleted_at__isnull=True, school_id=actor.org_id
        )
    else:
        raise BusinessError(403, "只有班主任或学校管理员可以查看班级申请")

    queryset = (
        JoinRequest.objects.filter(
            Q(class_obj__in=managed) | Q(target_class__in=managed),
            deleted_at__isnull=True,
            status=JoinRequestStatus.PENDING,
        )
        .select_related("class_obj", "target_class", "requester", "reviewer")
        .distinct()
        .order_by("-created_at", "-id")
    )
    request_type = params.get("type")
    if request_type:
        queryset = queryset.filter(type=request_type)

    managed_ids = set(managed.values_list("id", flat=True))
    items = list(queryset)
    for item in items:
        item.review_class_id = item.class_obj_id
        if item.type == JoinRequestType.CHANGE:
            if item.class_obj_id in managed_ids and not item.source_approved:
                item.review_class_id = item.class_obj_id
            elif item.target_class_id in managed_ids and not item.target_approved:
                item.review_class_id = item.target_class_id
    return items


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
    if not can_manage_class(actor, classroom):
        raise BusinessError(403, "只有班主任或学校管理员可以审核班级申请")
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
        _notify_request_result(item, False)
        return item

    if item.type == JoinRequestType.JOIN:
        if item.requester.school_id != item.class_obj.school_id:
            raise BusinessError(409, "申请人与班级不属于同一学校，无法通过")
        if item.requester_role == Role.STUDENT:
            profile = getattr(item.requester, "student_profile", None)
            if profile is None:
                raise BusinessError(400, "学生资料不存在")
            if profile.classroom_id is not None:
                raise BusinessError(409, "该学生已在班级中")
            _ensure_student_grade_matches(profile, item.class_obj)
            profile.classroom = item.class_obj
            profile.save(update_fields=["classroom", "updated_at"])
        else:
            teacher_profile = getattr(item.requester, "teacher_profile", None)
            subject = item.subject or (teacher_profile.subject if teacher_profile else None)
            if subject is None:
                raise BusinessError(400, "教师任教学科缺失")
            if teacher_profile is not None and teacher_profile.subject and teacher_profile.subject != subject:
                raise BusinessError(409, "该教师的任教学科与申请学科不一致")
            if ClassTeacher.objects.filter(
                class_obj=item.class_obj, subject=subject
            ).exclude(teacher=item.requester).exists():
                label = dict(Subject.choices).get(subject, subject)
                raise BusinessError(409, f"该班已有{label}老师，每个班每学科仅限一位科任老师")
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
            _ensure_student_grade_matches(profile, item.target_class)
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
    if item.status == JoinRequestStatus.APPROVED:
        _notify_request_result(item, True)
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
    if not can_manage_class(actor, classroom):
        raise BusinessError(403, "只有班主任或学校管理员可以移出学生")

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
