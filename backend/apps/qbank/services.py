"""题库业务逻辑：课程、章节、试题、资源与操作日志。"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from common.enums import (
    CourseStatus,
    OperationResult,
    QuestionStatus,
    QuestionType,
    ResourceType,
    Role,
)
from common.exceptions import BusinessError

from apps.accounts.services.profile import format_datetime
from apps.files.models import FileObject
from apps.files.services import save_upload

from .models import Chapter, Course, OperationLog, Question, QuestionOption, QuestionResource

CHOICE_TYPES = {QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE, QuestionType.LISTENING}


def log_action(actor, action: str, resource_type: str, resource_id=None, description: str = "",
               request=None, result: str = OperationResult.SUCCESS) -> None:
    OperationLog.objects.create(
        operator=actor,
        operator_role=actor.role if actor else "",
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        description=description[:500],
        ip=request.META.get("REMOTE_ADDR") if request else None,
        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:255] if request else None,
        result=result,
    )


# --------------------------------------------------------------------------- 课程


def build_course(course: Course) -> dict:
    return {
        "id": course.id,
        "name": course.name,
        "subject": course.subject,
        "grade": course.grade,
        "description": course.description,
        "chapterCount": course.chapters.filter(deleted_at__isnull=True).count(),
        "sortOrder": course.sort_order,
        "status": course.status,
        "createdAt": format_datetime(course.created_at),
        "updatedAt": format_datetime(course.updated_at),
    }


def list_courses(actor, params):
    queryset = Course.objects.filter(deleted_at__isnull=True)

    if actor.role == Role.STUDENT:
        profile = getattr(actor, "student_profile", None)
        grade = profile.grade if profile else None
        queryset = queryset.filter(status=CourseStatus.ACTIVE, grade=grade)
    else:
        status = params.get("status")
        if status:
            queryset = queryset.filter(status=status)

    subject = params.get("subject")
    if subject:
        queryset = queryset.filter(subject=subject)

    grade = params.get("grade")
    if grade and actor.role != Role.STUDENT:
        try:
            queryset = queryset.filter(grade=int(grade))
        except (TypeError, ValueError):
            raise BusinessError(400, "grade 必须为整数")

    keyword = (params.get("keyword") or "").strip()
    if keyword:
        queryset = queryset.filter(name__icontains=keyword)

    return queryset.order_by("sort_order", "id")


def get_course(actor, course_id: int) -> Course:
    course = Course.objects.filter(pk=course_id, deleted_at__isnull=True).first()
    if course is None:
        raise BusinessError(404, "课程不存在")
    if actor.role == Role.STUDENT:
        profile = getattr(actor, "student_profile", None)
        if course.status != CourseStatus.ACTIVE or (profile and course.grade != profile.grade):
            raise BusinessError(403, "无权查看该课程")
    return course


def create_course(actor, data: dict) -> Course:
    if actor.role != Role.QUESTION_ADMIN:
        raise BusinessError(403, "仅题库管理员可创建课程")
    course = Course.objects.create(
        name=data["name"].strip(),
        subject=data["subject"],
        grade=data["grade"],
        description=data.get("description"),
        sort_order=data.get("sortOrder", 0),
        status=data.get("status") or CourseStatus.ACTIVE,
    )
    log_action(actor, "course.create", "course", course.id, f"创建课程 {course.name}")
    return course


def update_course(actor, course: Course, data: dict) -> Course:
    if actor.role != Role.QUESTION_ADMIN:
        raise BusinessError(403, "仅题库管理员可修改课程")

    new_subject = data.get("subject", course.subject)
    new_grade = data.get("grade", course.grade)
    if new_subject != course.subject or new_grade != course.grade:
        if course.questions.filter(deleted_at__isnull=True).exclude(
            subject=new_subject, grade=new_grade
        ).exists():
            raise BusinessError(409, "课程下已有试题，无法修改学科或年级")

    for api_field, model_field in (
        ("name", "name"),
        ("subject", "subject"),
        ("grade", "grade"),
        ("description", "description"),
        ("sortOrder", "sort_order"),
        ("status", "status"),
    ):
        if api_field in data:
            value = data[api_field]
            if api_field == "name":
                value = value.strip()
            setattr(course, model_field, value)
    course.save()
    log_action(actor, "course.update", "course", course.id, f"修改课程 {course.name}")
    return course


def delete_course(actor, course: Course) -> dict:
    if actor.role != Role.QUESTION_ADMIN:
        raise BusinessError(403, "仅题库管理员可删除课程")
    if course.chapters.filter(deleted_at__isnull=True).exists():
        raise BusinessError(409, "课程下存在章节，无法删除")
    if course.questions.filter(deleted_at__isnull=True).exists():
        raise BusinessError(409, "课程下存在试题，无法删除")
    course.delete()
    log_action(actor, "course.delete", "course", course.id, f"删除课程 {course.name}")
    return {"deleted": True, "courseId": course.id}


# --------------------------------------------------------------------------- 章节


def build_chapter(chapter: Chapter) -> dict:
    return {
        "id": chapter.id,
        "courseId": chapter.course_id,
        "courseName": chapter.course.name,
        "name": chapter.name,
        "description": chapter.description,
        "questionCount": chapter.questions.filter(deleted_at__isnull=True).count(),
        "sortOrder": chapter.sort_order,
        "createdAt": format_datetime(chapter.created_at),
        "updatedAt": format_datetime(chapter.updated_at),
    }


def list_chapters(actor, course: Course):
    if actor.role == Role.STUDENT and course.status != CourseStatus.ACTIVE:
        raise BusinessError(403, "无权查看该课程章节")
    return list(
        Chapter.objects.filter(course=course, deleted_at__isnull=True)
        .select_related("course")
        .order_by("sort_order", "id")
    )


def get_chapter(actor, chapter_id: int) -> Chapter:
    chapter = (
        Chapter.objects.filter(pk=chapter_id, deleted_at__isnull=True)
        .select_related("course")
        .first()
    )
    if chapter is None:
        raise BusinessError(404, "章节不存在")
    if actor.role == Role.STUDENT:
        profile = getattr(actor, "student_profile", None)
        if (
            chapter.course.status != CourseStatus.ACTIVE
            or (profile and chapter.course.grade != profile.grade)
        ):
            raise BusinessError(403, "无权查看该章节")
    return chapter


def create_chapter(actor, course: Course, data: dict) -> Chapter:
    if actor.role != Role.QUESTION_ADMIN:
        raise BusinessError(403, "仅题库管理员可创建章节")
    chapter = Chapter.objects.create(
        course=course,
        name=data["name"].strip(),
        description=data.get("description"),
        sort_order=data.get("sortOrder", 0),
    )
    log_action(actor, "chapter.create", "chapter", chapter.id, f"创建章节 {chapter.name}")
    return chapter


def update_chapter(actor, chapter: Chapter, data: dict) -> Chapter:
    if actor.role != Role.QUESTION_ADMIN:
        raise BusinessError(403, "仅题库管理员可修改章节")
    for api_field, model_field in (
        ("name", "name"),
        ("description", "description"),
        ("sortOrder", "sort_order"),
    ):
        if api_field in data:
            value = data[api_field]
            if api_field == "name":
                value = value.strip()
            setattr(chapter, model_field, value)
    chapter.save()
    log_action(actor, "chapter.update", "chapter", chapter.id, f"修改章节 {chapter.name}")
    return chapter


def delete_chapter(actor, chapter: Chapter) -> dict:
    if actor.role != Role.QUESTION_ADMIN:
        raise BusinessError(403, "仅题库管理员可删除章节")
    if chapter.questions.filter(deleted_at__isnull=True).exists():
        raise BusinessError(409, "章节下存在试题，无法删除")
    chapter.delete()
    log_action(actor, "chapter.delete", "chapter", chapter.id, f"删除章节 {chapter.name}")
    return {"deleted": True, "chapterId": chapter.id}


# --------------------------------------------------------------------------- 试题


def _can_view_question(actor, question: Question) -> bool:
    if actor.role == Role.TEACHER:
        return question.status == QuestionStatus.APPROVED or question.creator_id == actor.id
    return True


def build_question_item(question: Question) -> dict:
    return {
        "id": question.id,
        "subject": question.subject,
        "grade": question.grade,
        "courseId": question.course_id,
        "courseName": question.course.name,
        "chapterId": question.chapter_id,
        "chapterName": question.chapter.name if question.chapter else None,
        "type": question.type,
        "difficulty": question.difficulty,
        "stem": question.stem,
        "score": float(question.score),
        "status": question.status,
        "creatorId": question.creator_id,
        "creatorName": question.creator.real_name,
        "reviewerId": question.reviewer_id,
        "reviewerName": question.reviewer.real_name if question.reviewer else None,
        "reviewComment": question.review_comment,
        "resourceCount": question.resources.filter(deleted_at__isnull=True).count(),
        "createdAt": format_datetime(question.created_at),
        "updatedAt": format_datetime(question.updated_at),
    }


def build_resource(item: QuestionResource) -> dict:
    return {
        "resourceId": item.id,
        "fileId": item.file_id,
        "type": item.type,
        "url": item.file.url,
        "name": item.file.original_name,
        "mimeType": item.file.mime_type,
        "size": item.file.size,
        "createdAt": format_datetime(item.created_at),
    }


def build_question_detail(question: Question) -> dict:
    data = build_question_item(question)
    options = [
        {"key": item.key, "text": item.text, "mediaUrl": item.media_url}
        for item in question.options.filter(deleted_at__isnull=True).order_by("sort_order", "id")
    ]
    resources = [
        build_resource(item)
        for item in question.resources.filter(deleted_at__isnull=True).select_related("file")
    ]
    data.update(
        {
            "options": options,
            "answer": question.answer,
            "analysis": question.analysis,
            "scoringMode": question.scoring_mode,
            "resources": resources,
        }
    )
    return data


def list_questions(actor, params):
    queryset = Question.objects.filter(deleted_at__isnull=True).select_related(
        "course", "chapter", "creator", "reviewer"
    )

    scope = params.get("scope", "all")
    status = params.get("status")
    if actor.role == Role.TEACHER:
        if scope == "mine":
            queryset = queryset.filter(creator=actor)
        else:
            queryset = queryset.filter(status=QuestionStatus.APPROVED)
            if status and status != QuestionStatus.APPROVED:
                raise BusinessError(403, "教师仅可筛选本人题目的非公开状态")

    if status:
        queryset = queryset.filter(status=status)

    for field in ("subject", "type", "courseId", "chapterId"):
        value = params.get(field)
        if value:
            queryset = queryset.filter(**{field: value})

    difficulty = params.get("difficulty")
    if difficulty:
        try:
            queryset = queryset.filter(difficulty=int(difficulty))
        except (TypeError, ValueError):
            raise BusinessError(400, "difficulty 必须为整数")

    grade = params.get("grade")
    if grade:
        try:
            queryset = queryset.filter(grade=int(grade))
        except (TypeError, ValueError):
            raise BusinessError(400, "grade 必须为整数")

    keyword = (params.get("keyword") or "").strip()
    if keyword:
        queryset = queryset.filter(stem__icontains=keyword)

    return queryset.order_by("-created_at", "-id")


def get_question(actor, question_id: int) -> Question:
    question = (
        Question.objects.filter(pk=question_id, deleted_at__isnull=True)
        .select_related("course", "chapter", "creator", "reviewer")
        .first()
    )
    if question is None:
        raise BusinessError(404, "试题不存在")
    if not _can_view_question(actor, question):
        raise BusinessError(403, "无权访问该试题")
    return question


def _validate_catalog(question: Question | None, data: dict) -> tuple[Course, Chapter | None]:
    course_id = data.get("courseId", question.course_id if question else None)
    course = Course.objects.filter(pk=course_id, deleted_at__isnull=True).first()
    if course is None:
        raise BusinessError(404, "课程不存在")

    chapter = None
    chapter_id = data.get("chapterId", question.chapter_id if question else None)
    if chapter_id:
        chapter = Chapter.objects.filter(
            pk=chapter_id, course=course, deleted_at__isnull=True
        ).first()
        if chapter is None:
            raise BusinessError(400, "章节不存在或不属于该课程")

    subject = data.get("subject", question.subject if question else None)
    grade = data.get("grade", question.grade if question else None)
    if subject and subject != course.subject:
        raise BusinessError(400, "试题学科必须与课程一致")
    if grade and int(grade) != course.grade:
        raise BusinessError(400, "试题年级必须与课程一致")
    return course, chapter


def _validate_options(question_type: str, options: list | None) -> None:
    if question_type in CHOICE_TYPES:
        if not options or len(options) < 2:
            raise BusinessError(400, "选择题至少需要两个选项")
        keys = [item.get("key") for item in options]
        if any(not key for key in keys) or len(set(keys)) != len(keys):
            raise BusinessError(400, "选项标识不能为空且不能重复")


def _validate_answer(question_type: str, answer, options: list | None) -> None:
    if not isinstance(answer, dict):
        raise BusinessError(400, "标准答案格式不正确")
    if question_type in {QuestionType.SINGLE_CHOICE, QuestionType.LISTENING}:
        keys = {item.get("key") for item in options or []}
        if answer.get("value") not in keys:
            raise BusinessError(400, "标准答案必须为有效选项")
    elif question_type == QuestionType.MULTIPLE_CHOICE:
        keys = {item.get("key") for item in options or []}
        values = answer.get("values")
        if not isinstance(values, list) or not values or any(item not in keys for item in values):
            raise BusinessError(400, "多选题答案必须为有效选项数组")
    elif question_type == QuestionType.TRUE_FALSE:
        if not isinstance(answer.get("value"), bool):
            raise BusinessError(400, "判断题答案必须为布尔值")
    elif question_type == QuestionType.FILL_BLANK:
        values = answer.get("values")
        if not isinstance(values, list) or not values or any(not str(item).strip() for item in values):
            raise BusinessError(400, "填空题答案不能为空")
    elif question_type == QuestionType.SHORT_ANSWER:
        if not str(answer.get("text") or "").strip():
            raise BusinessError(400, "简答题参考答案不能为空")
    elif question_type in {QuestionType.IMAGE_UPLOAD, QuestionType.AUDIO_UPLOAD}:
        if "rubric" in answer and not isinstance(answer["rubric"], dict):
            raise BusinessError(400, "作品题评分量表必须为对象")


def _attach_files(question: Question, file_ids: list[int], actor):
    files = list(FileObject.objects.filter(pk__in=file_ids, deleted_at__isnull=True))
    if len(files) != len(set(file_ids)):
        raise BusinessError(400, "资源文件不存在")
    current = question.resources.filter(deleted_at__isnull=True)
    image_count = current.filter(type=ResourceType.IMAGE).count()
    audio_count = current.filter(type=ResourceType.AUDIO).count()
    order = current.count()
    for file in files:
        resource_type = ResourceType.AUDIO if file.mime_type.startswith("audio") else ResourceType.IMAGE
        if resource_type == ResourceType.IMAGE:
            image_count += 1
            if image_count > 5:
                raise BusinessError(400, "单题最多 5 个图片资源")
        else:
            audio_count += 1
            if audio_count > 3:
                raise BusinessError(400, "单题最多 3 个音频资源")
        QuestionResource.objects.get_or_create(
            question=question,
            file=file,
            defaults={"type": resource_type, "sort_order": order},
        )
        order += 1


def create_question(actor, data: dict, request=None) -> Question:
    if actor.role not in {Role.TEACHER, Role.QUESTION_ADMIN}:
        raise BusinessError(403, "当前角色无权创建试题")

    course, chapter = _validate_catalog(None, data)
    _validate_options(data["type"], data.get("options"))
    _validate_answer(data["type"], data["answer"], data.get("options"))

    if actor.role == Role.TEACHER:
        status = QuestionStatus.PENDING
    else:
        status = QuestionStatus.APPROVED if data.get("publishNow") else QuestionStatus.DRAFT

    with transaction.atomic():
        question = Question.objects.create(
            subject=data["subject"],
            grade=data["grade"],
            course=course,
            chapter=chapter,
            type=data["type"],
            difficulty=data["difficulty"],
            stem=data["stem"].strip(),
            score=Decimal(str(data["score"])),
            answer=data["answer"],
            analysis=data.get("analysis"),
            scoring_mode=data["scoringMode"],
            status=status,
            creator=actor,
        )
        for index, item in enumerate(data.get("options") or []):
            QuestionOption.objects.create(
                question=question,
                key=item["key"],
                text=item["text"],
                media_url=item.get("mediaUrl"),
                sort_order=index,
            )
        if data.get("resourceFileIds"):
            _attach_files(question, data["resourceFileIds"], actor)

    log_action(actor, "question.create", "question", question.id, f"创建试题 {question.id}", request)
    return question


def update_question(actor, question: Question, data: dict, request=None) -> Question:
    if actor.role == Role.TEACHER:
        if question.creator_id != actor.id or question.status not in {
            QuestionStatus.DRAFT,
            QuestionStatus.REJECTED,
        }:
            raise BusinessError(403, "仅可修改本人草稿或已驳回试题")
    elif actor.role != Role.QUESTION_ADMIN:
        raise BusinessError(403, "当前角色无权修改试题")

    merged = {
        "subject": data.get("subject", question.subject),
        "grade": data.get("grade", question.grade),
        "courseId": data.get("courseId", question.course_id),
        "chapterId": data.get("chapterId", question.chapter_id),
        "type": data.get("type", question.type),
    }
    course, chapter = _validate_catalog(question, merged)

    options = data.get("options")
    if options is not None:
        _validate_options(merged["type"], options)
    answer = data.get("answer", question.answer)
    _validate_answer(merged["type"], answer, options or [
        {"key": item.key} for item in question.options.filter(deleted_at__isnull=True)
    ])

    with transaction.atomic():
        for api_field, model_field in (
            ("subject", "subject"),
            ("grade", "grade"),
            ("type", "type"),
            ("difficulty", "difficulty"),
            ("stem", "stem"),
            ("scoringMode", "scoring_mode"),
            ("analysis", "analysis"),
        ):
            if api_field in data:
                value = data[api_field]
                if api_field == "stem":
                    value = value.strip()
                setattr(question, model_field, value)
        if "score" in data:
            question.score = Decimal(str(data["score"]))
        question.course = course
        question.chapter = chapter
        if "answer" in data:
            question.answer = answer
        question.save()

        if options is not None:
            question.options.all().delete()
            for index, item in enumerate(options):
                QuestionOption.objects.create(
                    question=question,
                    key=item["key"],
                    text=item["text"],
                    media_url=item.get("mediaUrl"),
                    sort_order=index,
                )
        if data.get("resourceFileIds"):
            _attach_files(question, data["resourceFileIds"], actor)

    log_action(actor, "question.update", "question", question.id, f"修改试题 {question.id}", request)
    return question


def delete_question(actor, question: Question, request=None) -> dict:
    if actor.role == Role.TEACHER:
        if question.creator_id != actor.id or question.status not in {
            QuestionStatus.DRAFT,
            QuestionStatus.REJECTED,
        }:
            raise BusinessError(403, "仅可删除本人草稿或已驳回试题")
    elif actor.role != Role.QUESTION_ADMIN:
        raise BusinessError(403, "当前角色无权删除试题")

    question.delete()
    log_action(actor, "question.delete", "question", question.id, f"删除试题 {question.id}", request)
    return {"deleted": True, "questionId": question.id}


def submit_review(actor, question: Question, remark: str | None, request=None) -> Question:
    if actor.role != Role.TEACHER or question.creator_id != actor.id:
        raise BusinessError(403, "仅创建人可提交审核")
    if question.status not in {QuestionStatus.DRAFT, QuestionStatus.REJECTED}:
        raise BusinessError(409, "当前状态不可提交审核")

    question.status = QuestionStatus.PENDING
    question.reviewer = None
    question.review_comment = None
    question.reviewed_at = None
    question.save(update_fields=["status", "reviewer", "review_comment", "reviewed_at", "updated_at"])
    log_action(actor, "question.submit_review", "question", question.id, remark or "提交审核", request)
    return question


def review_question(actor, question: Question, action: str, comment: str | None, request=None) -> Question:
    if actor.role != Role.QUESTION_ADMIN:
        raise BusinessError(403, "仅题库管理员可审核试题")
    if question.status != QuestionStatus.PENDING:
        raise BusinessError(409, "仅待审核试题可审核")
    if action == "reject" and not (comment or "").strip():
        raise BusinessError(400, "驳回时必须填写审核意见")

    question.status = QuestionStatus.APPROVED if action == "approve" else QuestionStatus.REJECTED
    question.reviewer = actor
    question.review_comment = comment
    question.reviewed_at = timezone.now()
    question.save(
        update_fields=["status", "reviewer", "review_comment", "reviewed_at", "updated_at"]
    )
    log_action(
        actor,
        "question.review",
        "question",
        question.id,
        f"审核试题 {question.id}：{'通过' if action == 'approve' else '驳回'}",
        request,
    )
    return question


def upload_resources(actor, question: Question, files, resource_type: str, request=None):
    if actor.role == Role.TEACHER:
        if question.creator_id != actor.id or question.status not in {
            QuestionStatus.DRAFT,
            QuestionStatus.PENDING,
            QuestionStatus.REJECTED,
        }:
            raise BusinessError(403, "仅可为本人未发布试题上传资源")
    elif actor.role != Role.QUESTION_ADMIN:
        raise BusinessError(403, "当前角色无权上传资源")

    category = "question_audio" if resource_type == ResourceType.AUDIO else "question_image"
    created = []
    for uploaded in files:
        file_obj = save_upload(uploaded, category, actor, question.id)
        current = question.resources.filter(deleted_at__isnull=True)
        limit = 3 if resource_type == ResourceType.AUDIO else 5
        if current.filter(type=resource_type).count() >= limit:
            file_obj.delete()
            raise BusinessError(400, f"单题最多 {limit} 个{'音频' if resource_type == ResourceType.AUDIO else '图片'}资源")
        created.append(
            QuestionResource.objects.create(
                question=question,
                file=file_obj,
                type=resource_type,
                sort_order=current.count(),
            )
        )
    log_action(
        actor,
        "resource.upload",
        "resource",
        question.id,
        f"上传试题 {question.id} 资源 {len(created)} 个",
        request,
    )
    return created


def delete_resource(actor, question: Question, resource_id: int, request=None):
    resource = QuestionResource.objects.filter(
        pk=resource_id, question=question, deleted_at__isnull=True
    ).select_related("file").first()
    if resource is None:
        raise BusinessError(404, "资源不存在")
    if actor.role == Role.TEACHER:
        if question.creator_id != actor.id or question.status not in {
            QuestionStatus.DRAFT,
            QuestionStatus.PENDING,
            QuestionStatus.REJECTED,
        }:
            raise BusinessError(403, "仅可删除本人未发布试题的资源")
    elif actor.role != Role.QUESTION_ADMIN:
        raise BusinessError(403, "当前角色无权删除资源")

    resource.delete()
    log_action(actor, "resource.delete", "resource", resource.id, f"删除试题资源 {resource.id}", request)
    return {"deleted": True, "questionId": question.id, "resourceId": resource.id}


# --------------------------------------------------------------------------- 操作日志


def list_logs(actor, params):
    if actor.role not in {Role.QUESTION_ADMIN, Role.PROVINCE_ADMIN}:
        raise BusinessError(403, "当前角色无权查看操作日志")

    queryset = OperationLog.objects.filter(deleted_at__isnull=True).select_related("operator")
    if actor.role == Role.QUESTION_ADMIN:
        queryset = queryset.filter(
            resource_type__in=["question", "course", "chapter", "resource"]
        )

    for field in ("action", "resourceType", "result"):
        value = params.get(field)
        if value:
            queryset = queryset.filter(**{field: value})

    operator_id = params.get("operatorId")
    if operator_id:
        try:
            queryset = queryset.filter(operator_id=int(operator_id))
        except (TypeError, ValueError):
            raise BusinessError(400, "operatorId 必须为整数")

    resource_id = params.get("resourceId")
    if resource_id:
        try:
            queryset = queryset.filter(resource_id=int(resource_id))
        except (TypeError, ValueError):
            raise BusinessError(400, "resourceId 必须为整数")

    keyword = (params.get("keyword") or "").strip()
    if keyword:
        queryset = queryset.filter(description__icontains=keyword)

    start_time = params.get("startTime")
    if start_time:
        queryset = queryset.filter(created_at__gte=start_time)
    end_time = params.get("endTime")
    if end_time:
        queryset = queryset.filter(created_at__lte=end_time)

    return queryset.order_by("-created_at", "-id")


def get_log(actor, log_id: int):
    if actor.role not in {Role.QUESTION_ADMIN, Role.PROVINCE_ADMIN}:
        raise BusinessError(403, "当前角色无权查看操作日志")
    log = OperationLog.objects.filter(pk=log_id, deleted_at__isnull=True).select_related("operator").first()
    if log is None:
        raise BusinessError(404, "日志不存在")
    if actor.role == Role.QUESTION_ADMIN and log.resource_type not in {
        "question",
        "course",
        "chapter",
        "resource",
    }:
        raise BusinessError(404, "日志不存在")
    return log


def build_log(log: OperationLog) -> dict:
    return {
        "id": log.id,
        "operatorId": log.operator_id,
        "operatorName": log.operator.real_name if log.operator else "已删除账号",
        "role": log.operator_role,
        "action": log.action,
        "resourceType": log.resource_type,
        "resourceId": log.resource_id,
        "description": log.description,
        "ip": log.ip,
        "userAgent": log.user_agent,
        "result": log.result,
        "createdAt": format_datetime(log.created_at),
    }
