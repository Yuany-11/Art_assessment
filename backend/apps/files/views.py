"""文件接口（FILE-01 ~ FILE-02）。"""
from drf_spectacular.utils import extend_schema
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.views import APIView

from common.enums import Role
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
