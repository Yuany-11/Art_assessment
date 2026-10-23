"""多级账号接口视图（ACC-01 ~ ACC-11）。"""
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.views import APIView

from common.enums import Role
from common.exceptions import BusinessError
from common.permissions import roles_required
from common.response import success
from common.schema import api_response, paged_response
from common.pagination import StandardPagination

from .account_serializers import (
    AccountItemSerializer,
    AccountUpdateSerializer,
    CityCreateSerializer,
    DeleteAccountResultSerializer,
    DistrictCreateSerializer,
    ImportResultSerializer,
    ImportTaskStatusSerializer,
    OrgCreateResultSerializer,
    ResetPasswordResultSerializer,
    ResetPasswordSerializer,
    SchoolCreateSerializer,
    StudentCreateSerializer,
    TeacherCreateSerializer,
    TeacherImportSerializer,
)
from .services.account_import import import_teachers
from .models import ImportTask
from .services.accounts import (
    create_city,
    create_district,
    create_school,
    create_student,
    create_teacher,
    delete_account,
    get_account,
    list_accounts,
    reset_password,
    update_account,
)

ADMIN_ROLES = (
    Role.SCHOOL_ADMIN,
    Role.DISTRICT_ADMIN,
    Role.CITY_ADMIN,
    Role.PROVINCE_ADMIN,
)
DETAIL_ROLES = (Role.TEACHER, *ADMIN_ROLES)

LIST_PARAMETERS = [
    OpenApiParameter("role", OpenApiTypes.STR, OpenApiParameter.QUERY, description="目标角色"),
    OpenApiParameter("keyword", OpenApiTypes.STR, OpenApiParameter.QUERY, description="账号/姓名/手机号/学籍号"),
    OpenApiParameter("status", OpenApiTypes.STR, OpenApiParameter.QUERY, description="active/disabled"),
    OpenApiParameter("orgId", OpenApiTypes.INT, OpenApiParameter.QUERY, description="组织 ID"),
    OpenApiParameter("classId", OpenApiTypes.INT, OpenApiParameter.QUERY, description="班级 ID"),
    OpenApiParameter("pageNum", OpenApiTypes.INT, OpenApiParameter.QUERY),
    OpenApiParameter("pageSize", OpenApiTypes.INT, OpenApiParameter.QUERY),
]


def _paginate(request, queryset, serializer_class, view):
    paginator = StandardPagination()
    page = paginator.paginate_queryset(queryset, request, view=view)
    return paginator.get_paginated_response(serializer_class(page, many=True).data)


class AccountListView(APIView):
    permission_classes = [roles_required(*ADMIN_ROLES)]

    @extend_schema(
        tags=["账号管理"],
        summary="ACC-01 查询下级账号列表",
        operation_id="accounts_list",
        parameters=LIST_PARAMETERS,
        responses={200: paged_response("AccountListResponse", AccountItemSerializer(many=True))},
    )
    def get(self, request):
        queryset = list_accounts(request.user, request.query_params)
        return _paginate(request, queryset, AccountItemSerializer, self)


class AccountDetailView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [roles_required(*DETAIL_ROLES)()]
        return [roles_required(*ADMIN_ROLES)()]

    @extend_schema(
        tags=["账号管理"],
        summary="ACC-02 查询账号详情",
        operation_id="accounts_retrieve",
        responses={200: api_response("AccountDetailResponse", AccountItemSerializer())},
    )
    def get(self, request, account_id: int):
        return success(AccountItemSerializer(get_account(request.user, account_id)).data)

    @extend_schema(
        tags=["账号管理"],
        summary="ACC-09 修改账号信息",
        request=AccountUpdateSerializer,
        responses={200: api_response("AccountUpdateResponse", AccountItemSerializer())},
    )
    def patch(self, request, account_id: int):
        target = get_account(request.user, account_id)
        serializer = AccountUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = update_account(request.user, target, serializer.validated_data)
        return success(AccountItemSerializer(updated).data)

    @extend_schema(
        tags=["账号管理"],
        summary="ACC-10 删除账号",
        responses={200: api_response("AccountDeleteResponse", DeleteAccountResultSerializer())},
    )
    def delete(self, request, account_id: int):
        target = get_account(request.user, account_id)
        return success(delete_account(request.user, target))


class TeacherCreateView(APIView):
    permission_classes = [roles_required(Role.SCHOOL_ADMIN)]

    @extend_schema(
        tags=["账号管理"],
        summary="ACC-03 创建教师账号",
        request=TeacherCreateSerializer,
        responses={200: api_response("TeacherCreateResponse", AccountItemSerializer())},
    )
    def post(self, request):
        serializer = TeacherCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = create_teacher(request.user, serializer.validated_data)
        return success(AccountItemSerializer(user).data)


class TeacherImportView(APIView):
    permission_classes = [roles_required(Role.SCHOOL_ADMIN)]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        tags=["账号管理"],
        summary="ACC-04 批量导入教师账号",
        request=TeacherImportSerializer,
        responses={200: api_response("TeacherImportResponse", ImportResultSerializer())},
    )
    def post(self, request):
        serializer = TeacherImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = import_teachers(
            request.user,
            serializer.validated_data["file"],
            serializer.validated_data.get("defaultPassword"),
            serializer.validated_data.get("overwrite", False),
        )
        return success(result)


class StudentCreateView(APIView):
    permission_classes = [roles_required(*ADMIN_ROLES)]

    @extend_schema(
        tags=["账号管理"],
        summary="ACC-05 创建学生账号",
        request=StudentCreateSerializer,
        responses={200: api_response("StudentCreateResponse", AccountItemSerializer())},
    )
    def post(self, request):
        serializer = StudentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = create_student(request.user, serializer.validated_data)
        return success(AccountItemSerializer(user).data)


class SchoolCreateView(APIView):
    permission_classes = [
        roles_required(Role.DISTRICT_ADMIN, Role.CITY_ADMIN, Role.PROVINCE_ADMIN)
    ]

    @extend_schema(
        tags=["账号管理"],
        summary="ACC-06 创建学校账号",
        request=SchoolCreateSerializer,
        responses={200: api_response("SchoolCreateResponse", OrgCreateResultSerializer())},
    )
    def post(self, request):
        serializer = SchoolCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = create_school(request.user, serializer.validated_data)
        return success(OrgCreateResultSerializer(result).data)


class DistrictCreateView(APIView):
    permission_classes = [roles_required(Role.CITY_ADMIN, Role.PROVINCE_ADMIN)]

    @extend_schema(
        tags=["账号管理"],
        summary="ACC-07 创建区县账号",
        request=DistrictCreateSerializer,
        responses={200: api_response("DistrictCreateResponse", OrgCreateResultSerializer())},
    )
    def post(self, request):
        serializer = DistrictCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = create_district(request.user, serializer.validated_data)
        return success(OrgCreateResultSerializer(result).data)


class CityCreateView(APIView):
    permission_classes = [roles_required(Role.PROVINCE_ADMIN)]

    @extend_schema(
        tags=["账号管理"],
        summary="ACC-08 创建市州账号",
        request=CityCreateSerializer,
        responses={200: api_response("CityCreateResponse", OrgCreateResultSerializer())},
    )
    def post(self, request):
        serializer = CityCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = create_city(request.user, serializer.validated_data)
        return success(OrgCreateResultSerializer(result).data)


class ResetPasswordView(APIView):
    permission_classes = [roles_required(*DETAIL_ROLES)]

    @extend_schema(
        tags=["账号管理"],
        summary="ACC-11 重置账号密码",
        request=ResetPasswordSerializer,
        responses={200: api_response("ResetPasswordResponse", ResetPasswordResultSerializer())},
    )
    def post(self, request, account_id: int):
        target = get_account(request.user, account_id)
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = reset_password(
            request.user,
            target,
            serializer.validated_data.get("newPassword"),
            serializer.validated_data.get("forceChange", True),
        )
        return success(result)


class ImportTaskStatusView(APIView):
    permission_classes = [roles_required(*ADMIN_ROLES)]

    @extend_schema(
        tags=["账号管理"],
        summary="查询导入任务状态（导入扩展接口）",
        operation_id="accounts_import_task",
        responses={200: api_response("ImportTaskStatusResponse", ImportTaskStatusSerializer())},
    )
    def get(self, request, task_id: str):
        task = ImportTask.objects.filter(task_id=task_id, deleted_at__isnull=True).first()
        if task is None:
            raise BusinessError(404, "导入任务不存在")
        if task.requested_by_id != request.user.id and request.user.role != Role.PROVINCE_ADMIN:
            raise BusinessError(403, "无权查看该导入任务")
        return success(ImportTaskStatusSerializer(task).data)
