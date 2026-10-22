"""班级接口视图（CLS-01 ~ CLS-14）。"""
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.views import APIView

from common.enums import Role
from common.pagination import StandardPagination
from common.permissions import roles_required
from common.response import success
from common.schema import api_response, paged_response

from apps.accounts.account_serializers import StudentItemSerializer

from .imports import import_students
from .serializers import (
    ChangeRequestSerializer,
    ClassCreateSerializer,
    ClassDetailSerializer,
    ClassImportResultSerializer,
    ClassItemSerializer,
    ClassStudentImportSerializer,
    ClassUpdateSerializer,
    DeleteClassResultSerializer,
    JoinRequestCreateSerializer,
    JoinRequestItemSerializer,
    LeaveRequestSerializer,
    RemoveStudentResultSerializer,
    ReviewRequestSerializer,
)
from .services import (
    create_change_request,
    create_class,
    create_join_request,
    create_leave_request,
    delete_class,
    get_class,
    list_classes,
    list_requests,
    list_students,
    remove_student,
    review_request,
    search_class,
    update_class,
)

ADMIN_ROLES = (
    Role.SCHOOL_ADMIN,
    Role.DISTRICT_ADMIN,
    Role.CITY_ADMIN,
    Role.PROVINCE_ADMIN,
)

LIST_PARAMETERS = [
    OpenApiParameter("keyword", OpenApiTypes.STR, OpenApiParameter.QUERY),
    OpenApiParameter("grade", OpenApiTypes.INT, OpenApiParameter.QUERY),
    OpenApiParameter("schoolId", OpenApiTypes.INT, OpenApiParameter.QUERY),
    OpenApiParameter("status", OpenApiTypes.STR, OpenApiParameter.QUERY),
    OpenApiParameter("pageNum", OpenApiTypes.INT, OpenApiParameter.QUERY),
    OpenApiParameter("pageSize", OpenApiTypes.INT, OpenApiParameter.QUERY),
]


def _paginate(request, queryset, serializer_class, view):
    paginator = StandardPagination()
    page = paginator.paginate_queryset(queryset, request, view=view)
    return paginator.get_paginated_response(serializer_class(page, many=True).data)


class ClassListCreateView(APIView):
    permission_classes = [roles_required(Role.TEACHER, *ADMIN_ROLES)]

    @extend_schema(
        tags=["班级管理"],
        summary="CLS-01 查询班级列表",
        operation_id="classes_list",
        parameters=LIST_PARAMETERS,
        responses={200: paged_response("ClassListResponse", ClassItemSerializer(many=True))},
    )
    def get(self, request):
        queryset = list_classes(request.user, request.query_params)
        return _paginate(request, queryset, ClassItemSerializer, self)

    @extend_schema(
        tags=["班级管理"],
        summary="CLS-02 创建班级",
        request=ClassCreateSerializer,
        responses={200: api_response("ClassCreateResponse", ClassDetailSerializer())},
    )
    def post(self, request):
        serializer = ClassCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        classroom = create_class(request.user, serializer.validated_data)
        return success(ClassDetailSerializer(classroom).data)


class ClassSearchView(APIView):
    permission_classes = [roles_required(Role.STUDENT, Role.TEACHER, Role.SCHOOL_ADMIN)]

    @extend_schema(
        tags=["班级管理"],
        summary="CLS-03 按班级号查询班级",
        parameters=[OpenApiParameter("classCode", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True)],
        responses={200: api_response("ClassSearchResponse", ClassDetailSerializer())},
    )
    def get(self, request):
        classroom = search_class(request.user, request.query_params.get("classCode"))
        return success(ClassDetailSerializer(classroom).data)


class ClassDetailView(APIView):
    permission_classes = [roles_required(Role.STUDENT, Role.TEACHER, *ADMIN_ROLES)]

    @extend_schema(
        tags=["班级管理"],
        summary="CLS-04 查询班级详情",
        operation_id="classes_retrieve",
        responses={200: api_response("ClassDetailResponse", ClassDetailSerializer())},
    )
    def get(self, request, class_id: int):
        return success(ClassDetailSerializer(get_class(request.user, class_id)).data)

    @extend_schema(
        tags=["班级管理"],
        summary="CLS-05 修改班级",
        request=ClassUpdateSerializer,
        responses={200: api_response("ClassUpdateResponse", ClassDetailSerializer())},
    )
    def patch(self, request, class_id: int):
        classroom = get_class(request.user, class_id)
        serializer = ClassUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = update_class(request.user, classroom, serializer.validated_data)
        return success(ClassDetailSerializer(updated).data)

    @extend_schema(
        tags=["班级管理"],
        summary="CLS-06 解散班级",
        responses={200: api_response("ClassDeleteResponse", DeleteClassResultSerializer())},
    )
    def delete(self, request, class_id: int):
        classroom = get_class(request.user, class_id)
        return success(delete_class(request.user, classroom))


class ClassJoinView(APIView):
    permission_classes = [roles_required(Role.STUDENT, Role.TEACHER)]

    @extend_schema(
        tags=["班级管理"],
        summary="CLS-07 申请加入班级",
        request=JoinRequestCreateSerializer,
        responses={200: api_response("ClassJoinResponse", JoinRequestItemSerializer())},
    )
    def post(self, request, class_id: int):
        serializer = JoinRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = create_join_request(request.user, class_id, serializer.validated_data)
        return success(JoinRequestItemSerializer(item).data)


class ClassLeaveView(APIView):
    permission_classes = [roles_required(Role.STUDENT)]

    @extend_schema(
        tags=["班级管理"],
        summary="CLS-08 学生申请退出班级",
        request=LeaveRequestSerializer,
        responses={200: api_response("ClassLeaveResponse", JoinRequestItemSerializer())},
    )
    def post(self, request, class_id: int):
        serializer = LeaveRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = create_leave_request(request.user, class_id, serializer.validated_data)
        return success(JoinRequestItemSerializer(item).data)


class ClassChangeView(APIView):
    permission_classes = [roles_required(Role.STUDENT)]

    @extend_schema(
        tags=["班级管理"],
        summary="CLS-09 学生申请更换班级",
        request=ChangeRequestSerializer,
        responses={200: api_response("ClassChangeResponse", JoinRequestItemSerializer())},
    )
    def post(self, request, class_id: int):
        serializer = ChangeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = create_change_request(request.user, class_id, serializer.validated_data)
        return success(JoinRequestItemSerializer(item).data)


class ClassRequestsView(APIView):
    permission_classes = [roles_required(Role.TEACHER, Role.SCHOOL_ADMIN)]

    @extend_schema(
        tags=["班级管理"],
        summary="CLS-10 查询班级申请列表",
        parameters=[
            OpenApiParameter("type", OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter("status", OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter("pageNum", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("pageSize", OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        responses={
            200: paged_response("JoinRequestListResponse", JoinRequestItemSerializer(many=True))
        },
    )
    def get(self, request, class_id: int):
        classroom = get_class(request.user, class_id)
        queryset = list_requests(request.user, classroom, request.query_params)
        return _paginate(request, queryset, JoinRequestItemSerializer, self)


class ClassRequestReviewView(APIView):
    permission_classes = [roles_required(Role.TEACHER, Role.SCHOOL_ADMIN)]

    @extend_schema(
        tags=["班级管理"],
        summary="CLS-11 审核班级申请",
        request=ReviewRequestSerializer,
        responses={200: api_response("JoinRequestReviewResponse", JoinRequestItemSerializer())},
    )
    def post(self, request, class_id: int, request_id: int):
        classroom = get_class(request.user, class_id)
        serializer = ReviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = review_request(request.user, classroom, request_id, serializer.validated_data)
        return success(JoinRequestItemSerializer(item).data)


class ClassStudentsView(APIView):
    permission_classes = [roles_required(Role.TEACHER, *ADMIN_ROLES)]

    @extend_schema(
        tags=["班级管理"],
        summary="CLS-12 查询班级学生",
        parameters=[
            OpenApiParameter("keyword", OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter("status", OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter("pageNum", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("pageSize", OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        responses={200: paged_response("ClassStudentListResponse", StudentItemSerializer(many=True))},
    )
    def get(self, request, class_id: int):
        classroom = get_class(request.user, class_id)
        queryset = list_students(request.user, classroom, request.query_params)
        return _paginate(request, queryset, StudentItemSerializer, self)


class ClassStudentRemoveView(APIView):
    permission_classes = [roles_required(Role.TEACHER, Role.SCHOOL_ADMIN)]

    @extend_schema(
        tags=["班级管理"],
        summary="CLS-13 移除班级学生",
        responses={200: api_response("ClassStudentRemoveResponse", RemoveStudentResultSerializer())},
    )
    def delete(self, request, class_id: int, student_id: int):
        classroom = get_class(request.user, class_id)
        return success(remove_student(request.user, classroom, student_id))


class ClassStudentImportView(APIView):
    permission_classes = [roles_required(Role.TEACHER, Role.SCHOOL_ADMIN)]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        tags=["班级管理"],
        summary="CLS-14 批量导入班级学生",
        request=ClassStudentImportSerializer,
        responses={200: api_response("ClassStudentImportResponse", ClassImportResultSerializer())},
    )
    def post(self, request, class_id: int):
        classroom = get_class(request.user, class_id)
        serializer = ClassStudentImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = import_students(
            request.user,
            classroom,
            serializer.validated_data["file"],
            serializer.validated_data.get("mode", "append"),
        )
        return success(result)
