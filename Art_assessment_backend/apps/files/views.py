"""文件接口（FILE-01 ~ FILE-03）。"""
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.views import APIView

from common.enums import FileCategory, Role
from common.exceptions import BusinessError
from common.permissions import roles_required
from common.response import success
from common.schema import api_response

from .audio_tags import analysis_payload, analyze_audio
from .models import FileObject
from .serializers import (
    ArtworkReviewSerializer,
    FileDeleteResultSerializer,
    FileObjectSerializer,
    FileUploadSerializer,
)
from .services import delete_file, save_upload

ALL_ROLES = tuple(Role.values)


class FileUploadView(APIView):
    permission_classes = [roles_required(*ALL_ROLES)]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        tags=["文件"],
        summary="FILE-01 查询文件列表（学生作品等）",
        responses={200: api_response("FileListResponse", FileObjectSerializer(many=True))},
    )
    def get(self, request):
        category = request.query_params.get("category") or FileCategory.STUDENT_WORK
        qs = FileObject.objects.filter(
            category=category, deleted_at__isnull=True
        ).select_related("uploader")
        from apps.exams.scope import DataScope

        scope = DataScope(request.user)
        if request.user.role == Role.STUDENT:
            qs = qs.filter(uploader=request.user)
        elif request.user.role == Role.TEACHER:
            from django.db.models import Q

            # 只展示本人任教班级该学科的作品，班主任身份不扩权。
            visibility = Q(uploader=request.user)
            for class_id, subject in scope.teaching_pairs:
                class_q = Q(uploader__student_profile__classroom_id=class_id)
                if subject == "art":
                    # 作品未填学科时按美术处理，与评分时的默认口径一致。
                    visibility |= class_q & (
                        Q(subject="art") | Q(subject="") | Q(subject__isnull=True)
                    )
                else:
                    visibility |= class_q & Q(subject=subject)
            qs = qs.filter(visibility)
        elif request.user.role == Role.QUESTION_ADMIN:
            qs = qs.filter(uploader=request.user)
        else:
            from django.db.models import Q

            qs = qs.filter(
                Q(uploader=request.user) | Q(uploader__org_id__in=scope.school_ids)
            )
        include_reference = request.user.role != Role.STUDENT
        return success(
            [
                _artwork_item(item, include_reference=include_reference)
                for item in qs.order_by("-id")
            ]
        )

    @extend_schema(
        tags=["文件"],
        summary="FILE-01 通用文件上传",
        request=FileUploadSerializer,
        responses={200: api_response("FileUploadResponse", FileObjectSerializer())},
    )
    def post(self, request):
        serializer = FileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file_obj = save_upload(
            serializer.validated_data["file"],
            serializer.validated_data["category"],
            request.user,
            serializer.validated_data.get("bizId"),
            serializer.validated_data.get("subject"),
        )
        return success(FileObjectSerializer(file_obj).data)


class FileDeleteView(APIView):
    permission_classes = [roles_required(*ALL_ROLES)]

    @extend_schema(
        tags=["文件"],
        summary="FILE-02 删除文件",
        responses={200: api_response("FileDeleteResponse", FileDeleteResultSerializer())},
    )
    def delete(self, request, file_id: int):
        file_obj = FileObject.objects.filter(pk=file_id, deleted_at__isnull=True).first()
        if file_obj is None:
            raise BusinessError(404, "文件不存在")
        return success(delete_file(request.user, file_obj))


class FileArtworkReviewView(APIView):
    permission_classes = [roles_required(Role.TEACHER, Role.SCHOOL_ADMIN)]

    @extend_schema(
        tags=["文件"],
        summary="FILE-03 教师评分课外作品",
        request=ArtworkReviewSerializer,
        responses={200: api_response("ArtworkReviewResponse", OpenApiTypes.OBJECT)},
    )
    def patch(self, request, file_id: int):
        from django.utils import timezone

        from apps.exams.scope import DataScope

        file_obj = (
            FileObject.objects.filter(
                pk=file_id, category=FileCategory.STUDENT_WORK, deleted_at__isnull=True
            )
            .select_related("uploader")
            .first()
        )
        if file_obj is None:
            raise BusinessError(404, "作品不存在")
        uploader = file_obj.uploader
        scope = DataScope(request.user)
        if uploader is None:
            raise BusinessError(400, "作品缺少上传学生")
        if request.user.role == Role.TEACHER:
            class_id = getattr(
                getattr(uploader, "student_profile", None), "classroom_id", None
            )
            if not scope.teaches_subject_in_class(
                class_id, file_obj.subject or "art"
            ):
                raise BusinessError(403, "只能评价本人任教班级该学科学生的作品")
        elif getattr(uploader, "org_id", None) != scope.school_id:
            raise BusinessError(403, "只能评价本校学生的作品")
        serializer = ArtworkReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file_obj.review_score = serializer.validated_data["score"]
        file_obj.review_comment = serializer.validated_data.get("comment") or ""
        file_obj.reviewed_by = request.user
        file_obj.reviewed_at = timezone.now()
        file_obj.save(
            update_fields=[
                "review_score",
                "review_comment",
                "reviewed_by",
                "reviewed_at",
                "updated_at",
            ]
        )
        return success(_artwork_item(file_obj, include_reference=True))


class FileAudioAnalysisView(APIView):
    permission_classes = [roles_required(*ALL_ROLES)]

    @extend_schema(
        tags=["文件"],
        summary="FILE-04 查询音频标签分析",
        responses={200: api_response("AudioAnalysisResponse", OpenApiTypes.OBJECT)},
    )
    def get(self, request, file_id: int):
        file_obj = _get_visible_file(request.user, file_id)
        payload = analysis_payload(
            file_obj, include_reference=request.user.role != Role.STUDENT
        )
        if payload is None:
            raise BusinessError(400, "该文件不是音频")
        return success(payload)

    @extend_schema(
        tags=["文件"],
        summary="FILE-05 生成/刷新音频标签分析",
        request=OpenApiTypes.OBJECT,
        responses={200: api_response("AudioAnalysisRunResponse", OpenApiTypes.OBJECT)},
    )
    def post(self, request, file_id: int):
        file_obj = _get_visible_file(request.user, file_id)
        force = str(request.data.get("force", "")).lower() in {"1", "true", "yes"}
        analysis = analyze_audio(file_obj, force=force)
        payload = analysis_payload(
            file_obj, include_reference=request.user.role != Role.STUDENT
        )
        # analyze_audio 已保证是音频，这里仅做类型兜底。
        assert payload is not None and analysis.status
        return success(payload)


def _get_visible_file(user, file_id: int) -> FileObject:
    file_obj = (
        FileObject.objects.filter(pk=file_id, deleted_at__isnull=True)
        .select_related("uploader")
        .first()
    )
    if file_obj is None:
        raise BusinessError(404, "文件不存在")
    if not _can_view_file(user, file_obj):
        raise BusinessError(403, "无权访问该文件")
    return file_obj


def _can_view_file(user, file_obj: FileObject) -> bool:
    if user.role == Role.STUDENT:
        return file_obj.uploader_id == user.id

    from apps.exams.scope import DataScope

    scope = DataScope(user)
    if file_obj.category in {FileCategory.QUESTION_AUDIO, FileCategory.QUESTION_IMAGE}:
        return True
    if file_obj.uploader_id == user.id:
        return True
    uploader = file_obj.uploader
    if uploader is None:
        return False
    if user.role == Role.TEACHER:
        if file_obj.category != FileCategory.STUDENT_WORK:
            return False
        class_id = getattr(
            getattr(uploader, "student_profile", None), "classroom_id", None
        )
        return scope.teaches_subject_in_class(class_id, file_obj.subject or "art")
    if user.role == Role.QUESTION_ADMIN:
        return False
    return uploader.org_id in scope.school_ids


def _artwork_item(file_obj, *, include_reference: bool = True):
    """学生作品列表项，字段与前端 StudentArtwork 对齐。"""
    from apps.accounts.services.profile import format_datetime

    uploader = file_obj.uploader
    return {
        "id": file_obj.id,
        "studentId": file_obj.uploader_id,
        "studentName": getattr(uploader, "real_name", ""),
        "fileName": file_obj.original_name,
        "mimeType": file_obj.mime_type,
        "subject": file_obj.subject or "art",
        "uploadedAt": format_datetime(file_obj.created_at),
        "status": "reviewed" if file_obj.review_score is not None else "uploaded",
        "score": float(file_obj.review_score) if file_obj.review_score is not None else None,
        "comment": file_obj.review_comment or "",
        "reviewedBy": file_obj.reviewed_by.real_name if file_obj.reviewed_by else None,
        "reviewedAt": format_datetime(file_obj.reviewed_at) if file_obj.reviewed_at else None,
        "preview": file_obj.url,
        "audioTags": analysis_payload(
            file_obj, include_reference=include_reference
        ),
    }
