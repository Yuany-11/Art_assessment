import io
import random
from datetime import datetime

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from common.audit import log_action
from common.enums import CertificateStatus, GradingStatus, PaperType, Role
from common.exceptions import BadRequest, Conflict, Forbidden, NotFound, Unprocessable
from common.scope import DataScope
from common.storage import read_certificate, save_certificate
from exams.models import Assessment, Certificate, Score
from exams.serializers import CertificateGenerateSerializer

LEVEL_LABEL = {
    "excellent": "优秀",
    "good": "良好",
    "pass": "合格",
    "fail": "待提升",
}
SUBJECT_LABEL = {"music": "音乐", "art": "美术"}


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


def _pdf(cert):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    c.setFont("STSong-Light", 26)
    c.drawCentredString(width / 2, height - 120, "艺术素质测评证书")
    c.setFont("STSong-Light", 16)
    lines = [
        f"证书编号：{cert.certificate_no}",
        f"学生姓名：{cert.student_name}",
        f"测评名称：{cert.assessment.title}",
        f"测评学科：{SUBJECT_LABEL.get(cert.subject, cert.subject)}",
        f"测评成绩：{cert.score:.2f} 分",
        f"成绩等级：{LEVEL_LABEL.get(cert.level, cert.level)}",
        f"发证日期：{cert.issue_date.isoformat()}",
    ]
    y = height - 220
    for line in lines:
        c.drawString(90, y, line)
        y -= 40
    c.setFont("STSong-Light", 10)
    c.drawCentredString(width / 2, 80, "本证书由艺术素质测评系统生成，可通过证书编号核验。")
    c.save()
    return buffer.getvalue()


def _scope_qs(user):
    scope = DataScope(user)
    qs = Certificate.objects.all()
    if scope.is_student:
        return qs.filter(student=scope.user)
    if scope.is_teacher:
        return qs.filter(classroom_id__in=scope.class_ids)
    if scope.is_province_admin:
        return qs
    if scope.is_city_admin:
        return qs.filter(school__district__city_id=scope.city_id)
    if scope.is_district_admin:
        return qs.filter(school__district_id=scope.district_id)
    if scope.school_id:
        return qs.filter(school_id=scope.school_id)
    return qs.none()


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
    if assessment.paper_type != PaperType.FORMAL:
        raise Unprocessable("练习测评不生成证书")

    scope = DataScope(user)
    if not scope.is_province_admin and assessment.publisher_id != user.id:
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
            existing = Certificate.objects.filter(
                assessment=assessment, student=score.student
            ).first()
            if existing and not data["forceRegenerate"]:
                skipped += 1
                continue
            cert = existing or Certificate(
                assessment=assessment,
                student=score.student,
                certificate_no=_certificate_no(assessment.subject),
            )
            cert.student_name = score.student_name
            cert.subject = assessment.subject
            cert.classroom = score.classroom
            cert.class_name = score.class_name
            cert.school = score.school
            cert.school_name = score.school_name
            cert.score = score.total_score
            cert.level = score.level
            cert.issue_date = timezone.localdate()
            cert.template_id = data.get("templateId")
            cert.status = CertificateStatus.GENERATING
            cert.error = ""
            cert.save()
            try:
                save_certificate(cert.certificate_no, _pdf(cert))
                cert.status = CertificateStatus.READY
                cert.save(update_fields=["status", "updated_at"])
                generated += 1
            except OSError as exc:
                cert.status = CertificateStatus.FAILED
                cert.error = str(exc)[:255]
                cert.save(update_fields=["status", "error", "updated_at"])
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
            Q(student_name__icontains=keyword) | Q(student__student_no__icontains=keyword)
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
    content = read_certificate(cert.certificate_no)
    if content is None:
        raise NotFound("证书文件不存在，请重新生成")
    return content, f"certificate-{cert.certificate_no}.pdf"


def generate_for_assessment(assessment, force=False):
    """定时任务：测评结束后批量生成证书。"""
    if assessment.paper_type != PaperType.FORMAL:
        return 0
    scores = Score.objects.filter(
        assessment=assessment, status=GradingStatus.GRADED
    ).select_related("student", "classroom", "school")
    count = 0
    for score in scores:
        existing = Certificate.objects.filter(
            assessment=assessment, student=score.student
        ).first()
        if existing and not force:
            continue
        cert = existing or Certificate(
            assessment=assessment,
            student=score.student,
            certificate_no=_certificate_no(assessment.subject),
        )
        cert.student_name = score.student_name
        cert.subject = assessment.subject
        cert.classroom = score.classroom
        cert.class_name = score.class_name
        cert.school = score.school
        cert.school_name = score.school_name
        cert.score = score.total_score
        cert.level = score.level
        cert.issue_date = timezone.localdate()
        cert.status = CertificateStatus.GENERATING
        cert.save()
        try:
            save_certificate(cert.certificate_no, _pdf(cert))
            cert.status = CertificateStatus.READY
            cert.save(update_fields=["status", "updated_at"])
            count += 1
        except OSError as exc:
            cert.status = CertificateStatus.FAILED
            cert.error = str(exc)[:255]
            cert.save(update_fields=["status", "error", "updated_at"])
    return count
