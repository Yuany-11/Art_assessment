import io
import random
from datetime import datetime

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from common.audit import log_action
from common.enums import CertificateStatus, GradingStatus, Level, PaperType, Role
from common.exceptions import Conflict, Forbidden, NotFound, Unprocessable
from apps.exams.scope import DataScope
from apps.exams.storage import read_certificate, save_certificate
from apps.exams.models import Assessment, Certificate, Score
from apps.exams.serializers import CertificateGenerateSerializer

LEVEL_LABEL = {
    "excellent": "优秀",
    "good": "良好",
    "pass": "合格",
    "fail": "待提升",
}
SUBJECT_LABEL = {"music": "音乐", "art": "美术"}
# 证书只发给完成教师/学校端发布测评且达到 90 分（得分率 90%）的学生。
CERTIFICATE_PASS_RATE = 0.9
CERTIFICATE_PUBLISHER_ROLES = {
    Role.TEACHER,
    Role.SCHOOL_ADMIN,
    Role.DISTRICT_ADMIN,
    Role.CITY_ADMIN,
    Role.PROVINCE_ADMIN,
}


def _task_id():
    return "CERT" + datetime.now().strftime("%Y%m%d%H%M%S") + f"{random.randint(0, 9999):04d}"


def _certificate_no(subject):
    year = timezone.localdate().year
    prefix = f"YS{year}-{subject.upper()}-"
    last = (
        Certificate.objects.filter(certificate_no__startswith=prefix)
        .order_by("-certificate_no")
        .values_list("certificate_no", flat=True)
        .first()
    )
    sequence = int(last.rsplit("-", 1)[-1]) + 1 if last else 1
    return f"{prefix}{sequence:06d}"


def _short(text, limit: int) -> str:
    value = (str(text) if text is not None else "").strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _pdf(cert):
    """生成横版艺术素质测评证书：奶油底色、深青金边、绶带式成绩区与红色印章。"""
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    font = "STSong-Light"
    width, height = landscape(A4)
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(width, height))
    c.setTitle(f"艺术素质测评证书 {cert.certificate_no}")
    c.setAuthor("艺术素质测评系统")
    c.setSubject("艺术素质测评证书")

    cream = HexColor("#FCF9F2")
    navy = HexColor("#1E2D4F")
    teal = HexColor("#2F6F6B")
    gold = HexColor("#C6A15B")
    gold_soft = HexColor("#E8D8B8")
    ink = HexColor("#26324A")
    muted = HexColor("#6D778D")
    seal_red = HexColor("#B23A48")

    # 纸张底色与柔和光晕
    c.setFillColor(cream)
    c.rect(0, 0, width, height, stroke=0, fill=1)
    c.saveState()
    c.setFillAlpha(0.35)
    c.setFillColor(HexColor("#EAF2EF"))
    c.circle(width - 70, height - 58, 155, stroke=0, fill=1)
    c.setFillColor(HexColor("#F4EDE2"))
    c.circle(52, 48, 130, stroke=0, fill=1)
    c.restoreState()

    # 双层边框：深青外框 + 金色内线
    c.setStrokeColor(navy)
    c.setLineWidth(5)
    c.rect(20, 20, width - 40, height - 40)
    c.setStrokeColor(gold)
    c.setLineWidth(1.2)
    c.rect(31, 31, width - 62, height - 62)
    c.setStrokeColor(gold_soft)
    c.setLineWidth(0.6)
    c.rect(38, 38, width - 76, height - 76)

    # 四角装饰纹样
    c.setStrokeColor(gold)
    c.setLineWidth(1.6)
    for x, y, dx, dy in (
        (52, 52, 1, 1),
        (width - 52, 52, -1, 1),
        (52, height - 52, 1, -1),
        (width - 52, height - 52, -1, -1),
    ):
        c.line(x, y, x + 54 * dx, y)
        c.line(x, y, x, y + 54 * dy)
        c.line(x + 10 * dx, y + 10 * dy, x + 36 * dx, y + 10 * dy)
        c.line(x + 10 * dx, y + 10 * dy, x + 10 * dx, y + 36 * dy)
        c.setFillColor(gold)
        c.circle(x, y, 2.4, stroke=0, fill=1)

    # 顶部徽标：同心圆 + 金色“艺”字
    cx, cy = width / 2, height - 70
    c.setFillColor(navy)
    c.circle(cx, cy, 27, stroke=0, fill=1)
    c.setStrokeColor(gold)
    c.setLineWidth(1.4)
    c.circle(cx, cy, 22, stroke=1, fill=0)
    c.setFillColor(gold)
    c.setFont(font, 21)
    c.drawCentredString(cx, cy - 7, "艺")
    c.setStrokeColor(gold_soft)
    c.setLineWidth(0.8)
    c.line(cx - 170, cy, cx - 52, cy)
    c.line(cx + 52, cy, cx + 170, cy)
    c.setFillColor(gold)
    for offset in (-58, 58):
        c.circle(cx + offset, cy, 2, stroke=0, fill=1)

    # 标题
    c.setFillColor(navy)
    c.setFont(font, 34)
    c.drawCentredString(width / 2, height - 135, "艺术素质测评证书")
    c.setFillColor(gold)
    c.setFont(font, 9)
    c.drawCentredString(
        width / 2, height - 155, "CERTIFICATE OF ARTISTIC LITERACY ASSESSMENT"
    )
    c.setStrokeColor(gold_soft)
    c.setLineWidth(0.9)
    c.line(width / 2 - 208, height - 170, width / 2 + 208, height - 170)
    c.saveState()
    c.translate(width / 2, height - 170)
    c.rotate(45)
    c.setFillColor(gold)
    c.rect(-3.2, -3.2, 6.4, 6.4, stroke=0, fill=1)
    c.restoreState()

    # 正文：姓名单独放大，保持中文证书的庄重感
    c.setFillColor(muted)
    c.setFont(font, 13)
    c.drawCentredString(width / 2, height - 208, "兹 证 明")
    c.setFillColor(navy)
    c.setFont(font, 27)
    c.drawCentredString(width / 2, height - 242, _short(cert.student_name, 18))
    c.setStrokeColor(gold)
    c.setLineWidth(1)
    name_width = min(240, max(110, len(cert.student_name) * 27))
    c.line(
        width / 2 - name_width / 2,
        height - 252,
        width / 2 + name_width / 2,
        height - 252,
    )
    c.setFillColor(ink)
    c.setFont(font, 13)
    c.drawCentredString(
        width / 2,
        height - 282,
        f"在《{_short(cert.assessment.title, 32)}》艺术素质测评中",
    )
    c.drawCentredString(
        width / 2,
        height - 302,
        "认真完成各项测评任务，展现出良好的艺术感知与表现能力。",
    )

    # 绶带式成绩区
    ribbon_y, ribbon_h = 238, 40
    ribbon_width = 330
    ribbon_x = (width - ribbon_width) / 2
    c.setFillColor(teal)
    c.roundRect(ribbon_x, ribbon_y, ribbon_width, ribbon_h, 21, stroke=0, fill=1)
    c.setStrokeColor(gold)
    c.setLineWidth(0.8)
    c.roundRect(
        ribbon_x + 5, ribbon_y + 5, ribbon_width - 10, ribbon_h - 10, 15, stroke=1, fill=0
    )
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont(font, 17)
    c.drawCentredString(
        width / 2,
        ribbon_y + 15,
        f"测评成绩  {cert.score:.1f} 分    ·    评定等级  {LEVEL_LABEL.get(cert.level, cert.level)}",
    )
    # 绶带两侧的菱形装饰
    c.setFillColor(gold)
    for offset in (-13, ribbon_width + 13):
        c.saveState()
        c.translate(ribbon_x + offset, ribbon_y + ribbon_h / 2)
        c.rotate(45)
        c.rect(-4, -4, 8, 8, stroke=0, fill=1)
        c.restoreState()

    # 信息栏：四列分栏，细线分隔
    panel_x, panel_y, panel_h = 92, 166, 58
    panel_w = width - panel_x * 2
    c.setFillColor(HexColor("#F7F2E7"))
    c.setStrokeColor(gold_soft)
    c.setLineWidth(0.8)
    c.roundRect(panel_x, panel_y, panel_w, panel_h, 9, stroke=1, fill=1)
    columns = [
        ("测评学科", SUBJECT_LABEL.get(cert.subject, cert.subject), 8),
        ("所在班级", cert.class_name or "—", 14),
        ("所在学校", cert.school_name or "—", 13),
        ("证书编号", cert.certificate_no, 24),
    ]
    step = panel_w / len(columns)
    for index, (label, value, limit) in enumerate(columns):
        x = panel_x + index * step + 18
        if index:
            c.setStrokeColor(gold_soft)
            c.setLineWidth(0.6)
            c.line(
                panel_x + index * step,
                panel_y + 12,
                panel_x + index * step,
                panel_y + panel_h - 12,
            )
        c.setFillColor(muted)
        c.setFont(font, 8.5)
        c.drawString(x, panel_y + panel_h - 22, label)
        c.setFillColor(ink)
        c.setFont(font, 10)
        c.drawString(x, panel_y + 15, _short(value, limit))

    # 发证单位、日期与签名线
    sign_x, sign_y = 104, 112
    c.setStrokeColor(gold)
    c.setLineWidth(0.9)
    c.line(sign_x, sign_y, sign_x + 190, sign_y)
    c.setFillColor(muted)
    c.setFont(font, 8.5)
    c.drawString(sign_x, sign_y - 15, "发证单位：艺术素质测评系统")
    c.drawString(sign_x, sign_y - 31, f"发证日期：{cert.issue_date.isoformat()}")
    c.setFillColor(navy)
    c.setFont(font, 11)
    c.drawString(sign_x + 42, sign_y + 8, "艺术素质测评委员会")

    # 红色印章
    seal_x, seal_y, seal_r = width - 148, 116, 42
    c.setStrokeColor(seal_red)
    c.setLineWidth(2.2)
    c.circle(seal_x, seal_y, seal_r, stroke=1, fill=0)
    c.setLineWidth(0.7)
    c.circle(seal_x, seal_y, seal_r - 8, stroke=1, fill=0)
    c.setFillColor(seal_red)
    c.setFont(font, 9.5)
    c.drawCentredString(seal_x, seal_y + 11, "艺术素质测评")
    c.setFont(font, 7.5)
    c.drawCentredString(seal_x, seal_y - 5, "认证专用章")
    c.setFont(font, 6)
    c.drawCentredString(seal_x, seal_y - 20, "ART ASSESSMENT")

    # 页脚
    c.setStrokeColor(gold_soft)
    c.setLineWidth(0.5)
    c.line(80, 66, width - 80, 66)
    c.setFillColor(muted)
    c.setFont(font, 7.5)
    c.drawCentredString(
        width / 2,
        48,
        f"本证书由艺术素质测评系统生成 · 证书编号 {cert.certificate_no} · 可通过平台核验",
    )
    c.save()
    return buffer.getvalue()


def _scope_qs(user):
    scope = DataScope(user)
    qs = Certificate.objects.all()
    if scope.is_student:
        return qs.filter(student=scope.user)
    if scope.is_teacher:
        return qs.filter(scope.teacher_pair_q("classroom_id", "subject"))
    if scope.is_province_admin:
        return qs
    if scope.is_city_admin or scope.is_district_admin:
        return qs.filter(school_id__in=scope.school_ids)
    if scope.school_id:
        return qs.filter(school_id=scope.school_id)
    return qs.none()


def certificate_eligible(score):
    """证书条件：教师/学校端发布的正式测评、已出分、得分率达到 90%。

    学生自主生成的随机练习和教师发布的练习测评均不颁发证书，只有正式
    测评的 90 分成绩才符合条件；证书等级统一为优秀。
    """
    if score is None or score.status != GradingStatus.GRADED:
        return False
    assessment = score.assessment
    if assessment.paper_type != PaperType.FORMAL:
        return False
    if assessment.publisher is None:
        return False
    if assessment.publisher.role not in CERTIFICATE_PUBLISHER_ROLES:
        return False
    if not score.max_score:
        return False
    return score.total_score / score.max_score >= CERTIFICATE_PASS_RATE


def _fill_certificate(cert, score, template_id=None):
    cert.student_name = score.student_name
    cert.subject = score.assessment.subject
    cert.classroom = score.classroom
    cert.class_name = score.class_name
    cert.school = score.school
    cert.school_name = score.school_name
    cert.score = score.total_score
    # 证书只发给得分率 ≥ 90% 的成绩，等级固定为优秀。
    cert.level = Level.EXCELLENT
    cert.issue_date = timezone.localdate()
    if template_id is not None:
        cert.template_id = template_id
    return cert


def issue_certificate_for_score(score, force=False, template_id=None, uploader=None):
    """为一条达到 90 分的教师发布测评成绩生成证书；未达标返回 None。"""
    if not certificate_eligible(score):
        return None
    assessment = score.assessment
    existing = Certificate.objects.filter(
        assessment=assessment, student=score.student
    ).first()
    if existing and not force and existing.status == CertificateStatus.READY:
        return existing
    cert = existing or Certificate(
        assessment=assessment,
        student=score.student,
        certificate_no=_certificate_no(assessment.subject),
    )
    _fill_certificate(cert, score, template_id)
    cert.status = CertificateStatus.GENERATING
    cert.error = ""
    cert.save()
    try:
        cert.file_path = save_certificate(cert.certificate_no, _pdf(cert), uploader)
        cert.status = CertificateStatus.READY
        cert.save(update_fields=["file_path", "status", "updated_at"])
    except OSError as exc:
        cert.status = CertificateStatus.FAILED
        cert.error = str(exc)[:255]
        cert.save(update_fields=["status", "error", "updated_at"])
    return cert


def generate_certificates(user, payload, request=None):
    if user.role in (Role.STUDENT, Role.QUESTION_ADMIN):
        raise Forbidden("无权生成证书")
    serializer = CertificateGenerateSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    assessment = Assessment.objects.filter(pk=data["assessmentId"]).first()
    if assessment is None:
        raise NotFound("测评不存在")
    if assessment.subject != data["subject"]:
        raise Unprocessable("subject 与测评学科不一致")

    scope = DataScope(user)
    if scope.is_teacher:
        target_ids = set(assessment.target_ids or [])
        if assessment.target_type != "class" or not any(
            scope.teaches_subject_in_class(class_id, assessment.subject)
            for class_id in target_ids
        ):
            raise Forbidden("无权为该测评生成证书")
    elif not scope.is_province_admin and assessment.publisher_id != user.id:
        allowed = {
            "class": scope.class_ids,
            "school": scope.school_ids,
            "district": scope.district_ids,
            "city": scope.city_ids,
        }.get(assessment.target_type, set())
        if not set(assessment.target_ids or []) & allowed:
            raise Forbidden("无权为该测评生成证书")

    score_qs = Score.objects.filter(
        assessment=assessment, status=GradingStatus.GRADED
    ).select_related("student", "classroom", "school")
    if data.get("studentIds"):
        score_qs = score_qs.filter(student_id__in=data["studentIds"])

    generated = 0
    skipped = 0
    failed = 0
    with transaction.atomic():
        for score in score_qs:
            if not certificate_eligible(score):
                skipped += 1
                continue
            existing = Certificate.objects.filter(
                assessment=assessment, student=score.student
            ).first()
            if existing and not data["forceRegenerate"]:
                skipped += 1
                continue
            cert = issue_certificate_for_score(
                score, force=True, template_id=data.get("templateId"), uploader=user
            )
            if cert is not None and cert.status == CertificateStatus.READY:
                generated += 1
            else:
                failed += 1
        log_action(
            user, "certificate.generate", "assessment", assessment.id,
            f"生成证书：成功 {generated}，跳过 {skipped}，失败 {failed}",
            {"generated": generated, "skipped": skipped, "failed": failed},
            request=request,
        )
    status = "ready" if failed == 0 else "failed"
    return {
        "taskId": _task_id(),
        "status": status,
        "generatedCount": generated,
        "skippedCount": skipped,
    }


def list_certificates(user, params):
    if user.role == Role.QUESTION_ADMIN:
        raise Forbidden("题库管理员无权访问证书")
    qs = _scope_qs(user).select_related("assessment", "student")
    if params.get("assessmentId"):
        qs = qs.filter(assessment_id=params["assessmentId"])
    if params.get("subject"):
        qs = qs.filter(subject=params["subject"])
    if params.get("status"):
        qs = qs.filter(status=params["status"])
    keyword = params.get("studentKeyword")
    if keyword:
        qs = qs.filter(
            Q(student_name__icontains=keyword)
            | Q(student__student_profile__student_no__icontains=keyword)
        )
    return qs.order_by("-created_at")


def get_certificate(user, certificate_id):
    cert = (
        Certificate.objects.select_related("assessment")
        .filter(pk=certificate_id)
        .first()
    )
    if cert is None:
        raise NotFound("证书不存在")
    if user.role == Role.STUDENT and cert.student_id != user.id:
        raise Forbidden("无权查看他人证书")
    if user.role == Role.QUESTION_ADMIN:
        raise Forbidden("题库管理员无权访问证书")
    if user.role != Role.STUDENT and not _scope_qs(user).filter(pk=cert.id).exists():
        raise Forbidden("无权查看该证书")
    return cert


def download_certificate(user, certificate_id):
    cert = get_certificate(user, certificate_id)
    if cert.status != CertificateStatus.READY:
        raise Conflict("证书尚未生成完成")
    content = read_certificate(cert.file_path)
    if content is None:
        raise NotFound("证书文件不存在，请重新生成")
    return content, f"certificate-{cert.certificate_no}.pdf"


def generate_for_assessment(assessment, force=False):
    """定时任务：测评结束后为达到 90 分的学生批量生成证书。"""
    scores = Score.objects.filter(
        assessment=assessment, status=GradingStatus.GRADED
    ).select_related("student", "classroom", "school")
    count = 0
    for score in scores:
        if not certificate_eligible(score):
            continue
        existing = Certificate.objects.filter(
            assessment=assessment, student=score.student
        ).first()
        if existing and not force:
            continue
        cert = issue_certificate_for_score(score, force=True)
        if cert is not None and cert.status == CertificateStatus.READY:
            count += 1
    return count
