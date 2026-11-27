import io
import random
import zipfile
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from common.enums import (
    GenerateMode,
    PaperStatus,
    PaperType,
    QuestionStatus,
    QuestionType,
    Role,
    ScopeType,
    Subject,
)
from common.exceptions import BadRequest, Conflict, Forbidden, NotFound, Unprocessable
from apps.exams.scope import DataScope
from apps.exams.resources import build_resource_rows, read_resource, safe_filename
from common.utils import round2
from apps.exams.models import Paper, PaperQuestion
from apps.exams.serializers import (
    PaperAutoCreateSerializer,
    PaperDraftSerializer,
    PaperManualCreateSerializer,
    PaperUpdateSerializer,
    PracticeRandomSerializer,
)
from apps.qbank.models import Chapter, Course, Question

# 自动组卷总分固定 100 分。题型权重保证：
# 单选 < 判断 < 多选 < 实践题，同时题目越多每题分值越低。
AUTO_PAPER_TOTAL_SCORE = 100
AUTO_QUESTION_WEIGHTS = {
    QuestionType.SINGLE_CHOICE: 1.0,
    QuestionType.LISTENING: 1.1,
    QuestionType.AUDIO_CHOICE_JUDGE: 1.1,
    QuestionType.IMAGE_CHOICE_JUDGE: 1.1,
    QuestionType.TRUE_FALSE: 1.2,
    QuestionType.MULTIPLE_CHOICE: 2.0,
    QuestionType.IMAGE_UPLOAD: 4.0,
    QuestionType.AUDIO_UPLOAD: 4.0,
}


def auto_question_scores(counts):
    """按题型数量计算每题分值，所有题目合计恰好 100 分。

    返回 {题型: 每题分值}。先按权重计算并保留两位小数，最后把舍入差额
    补到分值最高的题型上，保证试卷总分为 100。
    """
    total_weight = sum(
        count * AUTO_QUESTION_WEIGHTS.get(qtype, 1.0)
        for qtype, count in counts.items()
        if count
    )
    if not total_weight:
        raise BadRequest("自动组卷至少需要选择一道试题")
    scores = {
        qtype: round2(
            AUTO_PAPER_TOTAL_SCORE * AUTO_QUESTION_WEIGHTS.get(qtype, 1.0) / total_weight
        )
        for qtype, count in counts.items()
        if count
    }
    # 将舍入误差补到权重最高且有题目的题型，避免影响“单选 < 多选 < 实践”的排序。
    adjust_type = max(
        scores,
        key=lambda qtype: (AUTO_QUESTION_WEIGHTS.get(qtype, 1.0), qtype),
    )
    current_total = sum(scores[qtype] * counts[qtype] for qtype in scores)
    scores[adjust_type] = round2(
        scores[adjust_type] + (AUTO_PAPER_TOTAL_SCORE - current_total) / counts[adjust_type]
    )
    return scores


def _scope_name(scope_type, scope_id):
    from apps.classes.models import Class
    from apps.organizations.models import Organization

    if scope_type == ScopeType.CLASS:
        obj = Class.objects.filter(pk=scope_id, deleted_at__isnull=True).first()
    else:
        level = {
            ScopeType.SCHOOL: "school",
            ScopeType.DISTRICT: "district",
            ScopeType.CITY: "city",
            ScopeType.PROVINCE: "province",
        }.get(scope_type)
        if level is None:
            raise BadRequest("scopeType 不合法")
        obj = Organization.objects.filter(
            pk=scope_id, level=level, deleted_at__isnull=True
        ).first()
    if obj is None:
        raise NotFound("归属组织或班级不存在")
    return obj.name


def questions_for_ids(ids):
    rows = Question.objects.filter(
        id__in=ids, deleted_at__isnull=True
    ).select_related("course", "chapter").prefetch_related("options", "resources")
    return {q.id: q for q in rows}


def snapshot_question(question, order, section_name, score):
    return {
        "questionId": question.id,
        "order": order,
        "sectionName": section_name or "",
        "type": question.type,
        "stem": question.stem,
        "score": round2(score),
        "maxScore": round2(score),
        "options": [
            {"key": o.key, "text": o.text, "mediaUrl": o.media_url}
            for o in question.options.all()
        ],
        "resources": build_resource_rows(question),
        "answer": question.answer or {},
        "ruleContext": (question.answer or {}).get("_ruleContext"),
        "analysis": question.analysis,
        "rubric": question.rubric,
        "scoringMode": question.scoring_mode,
    }


def _validate_question(question, paper, strict=True, enforce_grade=True):
    if strict:
        if question.status != QuestionStatus.APPROVED:
            raise Unprocessable(f"试题 {question.id} 未通过审核，不能组卷")
        if question.subject != paper.subject:
            raise Unprocessable(f"试题 {question.id} 学科与试卷不一致")
        if enforce_grade and question.grade != paper.grade:
            raise Unprocessable(
                f"试题 {question.id} 适用于{question.grade}年级，与试卷的{paper.grade}年级不一致"
            )
        if question.type == QuestionType.SHORT_ANSWER:
            raise Unprocessable("系统已取消简答题，请改用实践作品题")
        from common.subject_types import is_subject_question_type

        if not is_subject_question_type(question.subject, question.type):
            raise Unprocessable(
                f"试题 {question.id} 的题型与{question.subject}学科不匹配，不能组卷"
            )


def _ensure_class_grade(scope_type, scope_id, grade):
    """班级试卷必须与目标班级年级一致，防止跨年级组卷/发错班。"""
    if scope_type != ScopeType.CLASS:
        return
    from apps.classes.models import Class

    class_grade = (
        Class.objects.filter(pk=scope_id, deleted_at__isnull=True)
        .values_list("grade", flat=True)
        .first()
    )
    if class_grade is not None and class_grade != grade:
        raise Unprocessable(f"试卷年级为 {grade} 年级，与目标班级的 {class_grade} 年级不一致")


def _build_paper(user, data, generate_mode, questions, enforce_grade=True):
    scope = DataScope(user)
    scope.ensure_paper_scope(data["scopeType"], data["scopeId"], data["subject"])
    scope.ensure_subject(data["subject"])
    _ensure_class_grade(data["scopeType"], data["scopeId"], data["grade"])
    paper = Paper.objects.create(
        title=data["title"],
        subject=data["subject"],
        paper_type=data["paperType"],
        grade=data["grade"],
        scope_type=data["scopeType"],
        scope_id=data["scopeId"],
        scope_name=_scope_name(data["scopeType"], data["scopeId"]),
        duration=data["duration"],
        instructions=data.get("instructions"),
        status=data.get("status", PaperStatus.DRAFT),
        version=1,
        generate_mode=generate_mode,
        creator=user,
    )
    _replace_questions(paper, questions, strict=True, enforce_grade=enforce_grade)
    return paper


def paper_question_from_snapshot(paper, snap):
    """把题目的 JSON 快照转换为 PaperQuestion 模型字段。"""
    return PaperQuestion(
        paper=paper,
        question_id=snap["questionId"],
        order=snap["order"],
        section_name=snap["sectionName"],
        type=snap["type"],
        stem=snap["stem"],
        options=snap["options"],
        resources=snap["resources"],
        answer=snap["answer"],
        analysis=snap["analysis"],
        rubric=snap["rubric"],
        score=snap["score"],
        scoring_mode=snap["scoringMode"],
    )


def _replace_questions(paper, configs, strict=True, enforce_grade=True):
    ids = [c["questionId"] for c in configs]
    questions = questions_for_ids(ids)
    missing = [i for i in ids if i not in questions]
    if missing:
        raise NotFound(f"试题不存在：{missing}")
    PaperQuestion.objects.filter(paper=paper).delete()
    total = 0
    rows = []
    for cfg in sorted(configs, key=lambda c: c["order"]):
        question = questions[cfg["questionId"]]
        _validate_question(
            question, paper, strict=strict, enforce_grade=enforce_grade
        )
        snap = snapshot_question(question, cfg["order"], cfg.get("sectionName", ""), cfg["score"])
        rows.append(paper_question_from_snapshot(paper, snap))
        total += cfg["score"]
    PaperQuestion.objects.bulk_create(rows)
    paper.total_score = round2(total)
    paper.question_count = len(rows)
    paper.save(update_fields=["total_score", "question_count", "updated_at"])


def create_manual_paper(user, payload):
    serializer = PaperManualCreateSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    DataScope(user).ensure_subject(data["subject"])
    with transaction.atomic():
        return _build_paper(user, data, GenerateMode.MANUAL, data["questions"])


def _pick_questions(data, used_ids):
    qs = Question.objects.filter(
        deleted_at__isnull=True,
        status=QuestionStatus.APPROVED,
        subject=data["subject"],
    )
    # 教师可在自动组卷时多选年级；grades=[] 表示不限年级（全题库），
    # 未传 grades 时沿用试卷年级。
    if data.get("grades") is not None:
        if data["grades"]:
            qs = qs.filter(grade__in=data["grades"])
    elif data.get("grade"):
        qs = qs.filter(grade=data["grade"])
    if data.get("courseIds"):
        qs = qs.filter(course_id__in=data["courseIds"])
    if data.get("chapterIds"):
        qs = qs.filter(chapter_id__in=data["chapterIds"])
    return qs


def create_auto_paper(user, payload):
    serializer = PaperAutoCreateSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    DataScope(user).ensure_subject(data["subject"])

    statements = []
    total_needed = 0
    for rule in data["rules"]:
        total_needed += rule["count"]
    if total_needed > 200:
        raise BadRequest("单张试卷题目数量不能超过 200")

    selected = []
    used_ids = set()
    for rule in data["rules"]:
        if rule["type"] == QuestionType.SHORT_ANSWER:
            raise Unprocessable("系统已取消简答题，请改用实践作品题")
        qs = _pick_questions(data, used_ids)
        qs = qs.filter(type=rule["type"])
        if rule.get("difficulty"):
            qs = qs.filter(difficulty=rule["difficulty"])
        pool = list(qs.exclude(id__in=used_ids).values_list("id", flat=True))
        if len(pool) < rule["count"]:
            statements.append({
                "type": rule["type"],
                "difficulty": rule.get("difficulty"),
                "required": rule["count"],
                "available": len(pool),
            })
            continue
        picked = random.sample(pool, rule["count"])
        selected.extend((qid, rule["type"]) for qid in picked)
        used_ids.update(picked)

    if statements:
        message = "题库题目不足：" + "；".join(
            f"{s['type']}"
            + (f"(难度{s['difficulty']})" if s["difficulty"] else "")
            + f" 需要 {s['required']} 道，可用 {s['available']} 道"
            for s in statements
        )
        raise Conflict(message, errors={"shortage": statements})

    counts = {}
    for _, qtype in selected:
        counts[qtype] = counts.get(qtype, 0) + 1
    scores = auto_question_scores(counts)

    section_names = {
        QuestionType.SINGLE_CHOICE: "选择题",
        QuestionType.MULTIPLE_CHOICE: "多选题",
        QuestionType.TRUE_FALSE: "判断题",
        QuestionType.FILL_BLANK: "填空题",
        QuestionType.LISTENING: "听赏题",
        QuestionType.AUDIO_CHOICE_JUDGE: "音频选择判断题",
        QuestionType.IMAGE_CHOICE_JUDGE: "图像选择判断题",
        QuestionType.IMAGE_UPLOAD: "图片作品题",
        QuestionType.AUDIO_UPLOAD: "音频作品题",
    }
    configs = [
        {
            "questionId": qid,
            "order": index,
            "sectionName": section_names.get(qtype, ""),
            "score": scores[qtype],
        }
        for index, (qid, qtype) in enumerate(selected, start=1)
    ]
    # 浮点/两位小数舍入可能留下 0.01 的差额，补到最后一题，确保总分严格 100。
    actual_total = sum(c["score"] for c in configs)
    if configs and abs(actual_total - AUTO_PAPER_TOTAL_SCORE) >= 0.005:
        configs[-1]["score"] = round2(
            configs[-1]["score"] + AUTO_PAPER_TOTAL_SCORE - actual_total
        )
    with transaction.atomic():
        # 自动组卷的抽题范围由 grades/courseIds/chapterIds 决定，可跨年级成卷。
        return _build_paper(
            user, data, GenerateMode.AUTO, configs, enforce_grade=False
        )


def list_papers(user, params):
    qs = Paper.objects.filter(deleted_at__isnull=True)
    if user.role != Role.QUESTION_ADMIN:
        qs = qs.filter(DataScope(user).paper_q())
    # 学生随机练习卷不进入组卷/审核列表；教师和管理员创建的正式卷、练习卷
    # 都应能在列表里看到，否则保存后会出现“组完卷却找不到”的情况。
    if user.role != Role.STUDENT:
        qs = qs.exclude(creator__role=Role.STUDENT)
    qs = qs.select_related("creator")
    mapping = {
        "subject": "subject",
        "paperType": "paper_type",
        "grade": "grade",
        "scopeType": "scope_type",
        "status": "status",
        "reviewStatus": "review_status",
    }
    for param, field in mapping.items():
        value = params.get(param)
        if value:
            qs = qs.filter(**{field: value})
    keyword = params.get("keyword")
    if keyword:
        qs = qs.filter(title__icontains=keyword)
    school_id = params.get("schoolId")
    if school_id:
        qs = qs.filter(
            Q(scope_type="school", scope_id=school_id)
            | Q(creator__org_id=school_id)
        )
    district_id = params.get("districtId")
    if district_id:
        qs = qs.filter(
            Q(scope_type="district", scope_id=district_id)
            | Q(creator__org_id=district_id)
            | Q(creator__org__parent_id=district_id)
        )
    city_id = params.get("cityId")
    if city_id:
        qs = qs.filter(
            Q(scope_type="city", scope_id=city_id)
            | Q(creator__org_id=city_id)
            | Q(creator__org__parent_id=city_id)
            | Q(creator__org__parent__parent_id=city_id)
        )
    province_id = params.get("provinceId")
    if province_id:
        qs = qs.filter(
            Q(scope_type="province", scope_id=province_id)
            | Q(creator__org_id=province_id)
            | Q(creator__org__parent_id=province_id)
            | Q(creator__org__parent__parent_id=province_id)
            | Q(creator__org__parent__parent__parent_id=province_id)
        )
    return qs.order_by("-created_at")


def get_paper(user, paper_id):
    qs = (
        Paper.objects.filter(deleted_at__isnull=True, pk=paper_id)
        .select_related("creator")
    )
    if user.role != Role.QUESTION_ADMIN:
        qs = qs.filter(DataScope(user).paper_q())
    paper = qs.first()
    if paper is None:
        if Paper.objects.filter(pk=paper_id, deleted_at__isnull=True).exists():
            raise Forbidden("无权访问该试卷")
        raise NotFound("试卷不存在")
    return paper


def _ensure_editable(user, paper):
    if paper.status in (PaperStatus.PUBLISHED, PaperStatus.ARCHIVED):
        raise Conflict("已用于发布的试卷不可修改，请复制为新试卷后修改")
    if paper.assessments.exists():
        raise Conflict("试卷已被测评引用，不可修改")
    if paper.review_status == "pending":
        raise Conflict("试卷正在审核中，不可修改")
    if paper.review_status == "approved":
        raise Conflict("试卷已通过审核，如需修改请复制为新试卷")
    scope = DataScope(user)
    if user.role == Role.TEACHER and paper.creator_id != user.id:
        raise Forbidden("教师只能修改本人创建的试卷")
    if user.role != Role.TEACHER:
        scope.ensure_paper_scope(paper.scope_type, paper.scope_id)


def update_paper(user, paper, payload, draft=False):
    if draft:
        serializer = PaperDraftSerializer(data=payload)
    else:
        serializer = PaperUpdateSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    _ensure_editable(user, paper)

    with transaction.atomic():
        for field, value in (
            ("title", data.get("title")),
            ("duration", data.get("duration")),
            ("instructions", data.get("instructions")),
            ("status", data.get("status")),
        ):
            if field in data:
                setattr(paper, field, value)
        paper.version = (paper.version or 1) + 1
        if paper.review_status != "none":
            # 内容变更后原审核结论失效，需要重新提交审核
            paper.review_status = "none"
            paper.reviewer = None
            paper.review_comment = None
            paper.reviewed_at = None
        paper.save()
        if "questions" in data:
            _replace_questions(paper, data["questions"], strict=not draft)
    return paper


def delete_paper(user, paper):
    _ensure_editable(user, paper)
    if paper.status not in (PaperStatus.DRAFT, PaperStatus.READY):
        raise Conflict("仅草稿或已就绪试卷可删除")
    paper.delete()


# 随机练习固定 10 题：6 单选 + 3 多选 + 1 判断，全部为客观题。
# 不抽实践作品题：实践作品需要上传并由教师人工评分，练习无法立即出分。
PRACTICE_COMPOSITION = (
    (QuestionType.SINGLE_CHOICE, 6),
    (QuestionType.MULTIPLE_CHOICE, 3),
    (QuestionType.TRUE_FALSE, 1),
)
# 随机练习与自动组卷一样固定 100 分，按题数平均分配，便于成绩、报告统一比较。
PRACTICE_TOTAL_SCORE = 100
# 题库里“以下哪个术语与 X 直接相关”这类模板题的干扰项与正确答案属于同一类别，
# 答案存在歧义，随机练习不再抽取。
AMBIGUOUS_STEM_KEYWORDS = ("直接相关",)


def _distinct_question_ids(qs):
    """按题干去重：题库中存在同一题干的多条记录，避免一套题里出现重复题。"""
    seen = set()
    ids = []
    for question_id, stem in qs.values_list("id", "stem").order_by("id"):
        key = " ".join((stem or "").split())
        if key in seen:
            continue
        seen.add(key)
        ids.append(question_id)
    return ids


def _practice_question_pool(user, data):
    grade = data.get("grade") or user.grade or (
        user.current_class.grade if user.current_class_id else None
    )
    if not grade:
        raise Unprocessable("无法确定年级，请传入 grade")
    base = Question.objects.filter(
        deleted_at__isnull=True,
        status=QuestionStatus.APPROVED,
        subject=data["subject"],
        grade=grade,
    )
    for keyword in AMBIGUOUS_STEM_KEYWORDS:
        base = base.exclude(stem__contains=keyword)
    if data.get("courseId"):
        base = base.filter(course_id=data["courseId"])
    if data.get("chapterId"):
        base = base.filter(chapter_id=data["chapterId"])
    # 题库按年级分册：随机练习只抽取本年级的题目。
    graded = base

    picked = []
    for qtype, count in PRACTICE_COMPOSITION:
        ids = _distinct_question_ids(graded.filter(type=qtype))
        if len(ids) < count:
            raise Conflict(
                f"题库中符合条件的{_practice_type_label(qtype)}不足：需要 {count} 道，可用 {len(ids)} 道",
                errors={"type": qtype, "required": count, "available": len(ids)},
            )
        picked.extend(random.sample(ids, count))

    return grade, picked


def _practice_question_scores(count):
    """把 100 分平均分给每道题，余数放到最后一题，保证合计正好 100。"""
    if count <= 0:
        return []
    each = round2(PRACTICE_TOTAL_SCORE / count)
    scores = [each] * (count - 1)
    scores.append(round2(PRACTICE_TOTAL_SCORE - each * (count - 1)))
    return scores


def _practice_type_label(qtype):
    if qtype == QuestionType.SINGLE_CHOICE:
        return "单选题"
    if qtype == QuestionType.MULTIPLE_CHOICE:
        return "多选题"
    if qtype == QuestionType.TRUE_FALSE:
        return "判断题"
    if qtype == QuestionType.AUDIO_CHOICE_JUDGE:
        return "音频选择判断题"
    if qtype == QuestionType.IMAGE_CHOICE_JUDGE:
        return "图像选择判断题"
    return "实践题"


def create_practice(user, payload):
    """学生随机练习：建卷 + 建测评 + 建答卷，一次返回 Attempt。"""
    from apps.exams.services import attempt as attempt_service

    serializer = PracticeRandomSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    if user.role != Role.STUDENT:
        raise Forbidden("仅学生可生成随机练习")
    if not user.current_class_id:
        raise Unprocessable("学生尚未加入班级，无法生成练习")

    grade, picked = _practice_question_pool(user, data)
    questions = questions_for_ids(picked)
    duration = 40
    now = timezone.now()
    with transaction.atomic():
        paper = Paper.objects.create(
            title=f"{grade}年级{'音乐' if data['subject'] == Subject.MUSIC else '美术'}随机练习",
            subject=data["subject"],
            paper_type=PaperType.PRACTICE,
            grade=grade,
            scope_type=ScopeType.CLASS,
            scope_id=user.current_class_id,
            scope_name=user.current_class.name,
            duration=duration,
            status=PaperStatus.PUBLISHED,
            generate_mode=GenerateMode.AUTO,
            creator=user,
        )
        total = 0
        rows = []
        question_scores = _practice_question_scores(len(picked))
        for order, (qid, score) in enumerate(zip(picked, question_scores), start=1):
            question = questions[qid]
            snap = snapshot_question(question, order, "随机练习", score)
            rows.append(paper_question_from_snapshot(paper, snap))
            total += score
        PaperQuestion.objects.bulk_create(rows)
        paper.total_score = round2(total)
        paper.question_count = len(rows)
        paper.save(update_fields=["total_score", "question_count", "updated_at"])

        from apps.exams.services.assessment import build_snapshot

        snapshot = build_snapshot(paper)
        assessment = create_practice_assessment(
            paper=paper,
            publisher=user,
            title=paper.title,
            class_id=user.current_class_id,
            class_name=user.current_class.name,
            grade=grade,
            start_time=now,
            end_time=now + timedelta(minutes=duration),
            duration=duration,
            snapshot=snapshot,
            attempt_limit=99,
        )
        return attempt_service.start_attempt(user, assessment)


def create_practice_assessment(
    *, paper, publisher, title, class_id, class_name, grade,
    start_time, end_time, duration, snapshot, attempt_limit,
):
    """练习卷专用：直接创建测评（无需发布校验）。"""
    from apps.exams.models import Assessment, AssessmentGrade, AssessmentTarget

    assessment = Assessment.objects.create(
        paper=paper,
        title=title,
        subject=paper.subject,
        paper_type=paper.paper_type,
        target_type=ScopeType.CLASS,
        target_ids=[class_id],
        target_names=[class_name],
        target_grades=[grade],
        start_time=start_time,
        end_time=end_time,
        duration=duration,
        attempt_limit=attempt_limit,
        show_answer_mode="after_submit",
        instructions="系统随机练习，不计入正式测评统计，不生成证书。",
        status="published",
        publisher=publisher,
        published_at=start_time,
        question_snapshot=snapshot,
        max_score=round2(sum(q["score"] for q in snapshot)),
        participant_count=1,
    )
    AssessmentTarget.objects.create(
        assessment=assessment, target_type=ScopeType.CLASS,
        target_id=class_id, target_name=class_name,
    )
    AssessmentGrade.objects.create(assessment=assessment, grade=grade)
    return assessment


def export_materials(user, paper, question_ids=None, types=None):
    get_paper(user, paper.id)
    questions = paper.questions.all()
    if question_ids:
        questions = [q for q in questions if q.question_id in question_ids]
    question_map = questions_for_ids([q.question_id for q in questions])

    files = []
    for pq in questions:
        source = question_map.get(pq.question_id)
        resources = pq.resources or []
        # 题目快照未携带资源时，回退到题库当前资源，避免旧试卷下载材料报 409。
        if not resources and source is not None:
            resources = build_resource_rows(source)
        for resource in resources:
            rtype = resource.get("type")
            if types and rtype not in types:
                continue
            content = read_resource(resource)
            if content is None:
                continue
            name = safe_filename(resource.get("name") or f"{pq.question_id}.{rtype}")
            files.append((f"{pq.order:02d}-{name}", content))

    if not files:
        raise Conflict("该试卷没有可下载的资源文件")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files:
            zf.writestr(name, content)
        zf.writestr(
            "manifest.txt",
            "\n".join(f"{n}\t{len(c)} bytes" for n, c in files),
        )
    return buffer.getvalue(), f"paper-{paper.id}-materials.zip", len(files)


def export_answers(user, paper, fmt="pdf", include_analysis=True, include_rubric=True):
    get_paper(user, paper.id)
    rows = list(paper.questions.all())
    if fmt == "docx":
        return _answers_docx(paper, rows, include_analysis, include_rubric)
    return _answers_pdf(paper, rows, include_analysis, include_rubric)


def _answer_lines(paper, rows, include_analysis, include_rubric):
    from common.utils import normalize_answer

    lines = [f"试卷：{paper.title}", f"学科：{paper.subject}  年级：{paper.grade}", ""]
    for row in rows:
        lines.append(f"{row.order}. {row.stem}（{row.type}，{round2(row.score)} 分）")
        if row.options:
            for opt in row.options:
                lines.append(f"   {opt.get('key')}. {opt.get('text')}")
        lines.append(f"   标准答案：{normalize_answer(row.answer)}")
        if include_rubric and row.rubric:
            lines.append(f"   评分要点：{row.rubric}")
        if include_analysis and row.analysis:
            lines.append(f"   解析：{row.analysis}")
        lines.append("")
    return lines


def _answers_pdf(paper, rows, include_analysis, include_rubric):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 50
    c.setFont("STSong-Light", 12)
    for line in _answer_lines(paper, rows, include_analysis, include_rubric):
        for chunk in _wrap(line, 48):
            c.drawString(45, y, chunk)
            y -= 18
            if y < 50:
                c.showPage()
                c.setFont("STSong-Light", 12)
                y = height - 50
    c.save()
    return buffer.getvalue(), f"paper-{paper.id}-answers.pdf", "application/pdf"


def _answers_docx(paper, rows, include_analysis, include_rubric):
    from docx import Document

    doc = Document()
    for line in _answer_lines(paper, rows, include_analysis, include_rubric):
        doc.add_paragraph(line)
    buffer = io.BytesIO()
    doc.save(buffer)
    return (
        buffer.getvalue(),
        f"paper-{paper.id}-answers.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def _wrap(text, width):
    return [text[i:i + width] for i in range(0, max(1, len(text)), width)] or [""]
