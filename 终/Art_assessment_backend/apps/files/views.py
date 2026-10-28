"""文件接口（FILE-01 ~ FILE-02）。"""
from drf_spectacular.utils import extend_schema
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.views import APIView

from common.enums import FileCategory, Role
from common.exceptions import BusinessError
from common.permissions import roles_required
from common.response import success
from common.schema import api_response

from .models import FileObject
from .serializers import FileDeleteResultSerializer, FileObjectSerializer, FileUploadSerializer
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

            qs = qs.filter(
                Q(uploader=request.user)
                | Q(uploader__student_profile__classroom_id__in=scope.class_ids)
            )
        elif request.user.role == Role.QUESTION_ADMIN:
            qs = qs.filter(uploader=request.user)
        else:
            from django.db.models import Q

            qs = qs.filter(
                Q(uploader=request.user) | Q(uploader__org_id__in=scope.school_ids)
            )
        return success([_artwork_item(item) for item in qs.order_by("-id")])

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


def _artwork_item(file_obj):
    """学生作品列表项，字段与前端 StudentArtwork 对齐。"""
    from apps.accounts.services.profile import format_datetime

    uploader = file_obj.uploader
    return {
        "id": file_obj.id,
        "studentId": file_obj.uploader_id,
        "studentName": getattr(uploader, "real_name", ""),
        "fileName": file_obj.original_name,
        "subject": file_obj.subject or "art",
        "uploadedAt": format_datetime(file_obj.created_at),
        "status": "uploaded",
        "preview": file_obj.url,
    }
