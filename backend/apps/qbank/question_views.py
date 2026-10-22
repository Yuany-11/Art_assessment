"""试题与资源接口（QST-01 ~ QST-07、RES-01 ~ RES-02）。"""
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.views import APIView

from common.enums import Role
from common.pagination import StandardPagination
from common.permissions import roles_required
from common.response import success
from common.schema import api_response, paged_response

from .serializers import (
    DeleteQuestionResultSerializer,
    DeleteResourceResultSerializer,
    QuestionCreateSerializer,
    QuestionDetailSerializer,
    QuestionItemSerializer,
    QuestionResourceItemSerializer,
    QuestionReviewSerializer,
    QuestionUpdateSerializer,
    ResourceUploadSerializer,
    SubmitReviewSerializer,
)
from .services import (
    create_question,
    delete_question,
    delete_resource,
    get_question,
    list_questions,
    review_question,
    submit_review,
    update_question,
    upload_resources,
)

QUESTION_ROLES = (
    Role.TEACHER,
    Role.SCHOOL_ADMIN,
    Role.DISTRICT_ADMIN,
    Role.CITY_ADMIN,
    Role.PROVINCE_ADMIN,
    Role.QUESTION_ADMIN,
)
EDIT_ROLES = (Role.TEACHER, Role.QUESTION_ADMIN)

LIST_PARAMETERS = [
    OpenApiParameter("subject", OpenApiTypes.STR, OpenApiParameter.QUERY),
    OpenApiParameter("difficulty", OpenApiTypes.INT, OpenApiParameter.QUERY),
    OpenApiParameter("type", OpenApiTypes.STR, OpenApiParameter.QUERY),
    OpenApiParameter("grade", OpenApiTypes.INT, OpenApiParameter.QUERY),
    OpenApiParameter("courseId", OpenApiTypes.INT, OpenApiParameter.QUERY),
    OpenApiParameter("chapterId", OpenApiTypes.INT, OpenApiParameter.QUERY),
    OpenApiParameter("keyword", OpenApiTypes.STR, OpenApiParameter.QUERY),
    OpenApiParameter("status", OpenApiTypes.STR, OpenApiParameter.QUERY),
    OpenApiParameter("scope", OpenApiTypes.STR, OpenApiParameter.QUERY, description="all / mine"),
    OpenApiParameter("pageNum", OpenApiTypes.INT, OpenApiParameter.QUERY),
    OpenApiParameter("pageSize", OpenApiTypes.INT, OpenApiParameter.QUERY),
]


class QuestionListCreateView(APIView):
    permission_classes = [roles_required(*QUESTION_ROLES)]

    @extend_schema(
        tags=["题库"],
        summary="QST-01 查询试题列表",
        operation_id="questions_list",
        parameters=LIST_PARAMETERS,
        responses={200: paged_response("QuestionListResponse", QuestionItemSerializer(many=True))},
    )
    def get(self, request):
        queryset = list_questions(request.user, request.query_params)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(QuestionItemSerializer(page, many=True).data)

    @extend_schema(
        tags=["题库"],
        summary="QST-02 创建试题",
        request=QuestionCreateSerializer,
        responses={200: api_response("QuestionCreateResponse", QuestionDetailSerializer())},
    )
    def post(self, request):
        serializer = QuestionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = create_question(request.user, serializer.validated_data, request)
        return success(QuestionDetailSerializer(question).data)


class QuestionDetailView(APIView):
    permission_classes = [roles_required(*QUESTION_ROLES)]

    @extend_schema(
        tags=["题库"],
        summary="QST-03 查询试题详情",
        operation_id="questions_retrieve",
        responses={200: api_response("QuestionDetailResponse", QuestionDetailSerializer())},
    )
    def get(self, request, question_id: int):
        return success(QuestionDetailSerializer(get_question(request.user, question_id)).data)

    @extend_schema(
        tags=["题库"],
        summary="QST-04 修改试题",
        request=QuestionUpdateSerializer,
        responses={200: api_response("QuestionUpdateResponse", QuestionDetailSerializer())},
    )
    def patch(self, request, question_id: int):
        question = get_question(request.user, question_id)
        serializer = QuestionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = update_question(request.user, question, serializer.validated_data, request)
        return success(QuestionDetailSerializer(updated).data)

    @extend_schema(
        tags=["题库"],
        summary="QST-05 删除试题",
        responses={200: api_response("QuestionDeleteResponse", DeleteQuestionResultSerializer())},
    )
    def delete(self, request, question_id: int):
        question = get_question(request.user, question_id)
        return success(delete_question(request.user, question, request))


class QuestionSubmitReviewView(APIView):
    permission_classes = [roles_required(Role.TEACHER)]

    @extend_schema(
        tags=["题库"],
        summary="QST-06 提交试题审核",
        request=SubmitReviewSerializer,
        responses={200: api_response("QuestionSubmitReviewResponse", QuestionDetailSerializer())},
    )
    def post(self, request, question_id: int):
        question = get_question(request.user, question_id)
        serializer = SubmitReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = submit_review(
            request.user, question, serializer.validated_data.get("remark"), request
        )
        return success(QuestionDetailSerializer(updated).data)


class QuestionReviewView(APIView):
    permission_classes = [roles_required(Role.QUESTION_ADMIN)]

    @extend_schema(
        tags=["题库"],
        summary="QST-07 审核试题",
        request=QuestionReviewSerializer,
        responses={200: api_response("QuestionReviewResponse", QuestionDetailSerializer())},
    )
    def post(self, request, question_id: int):
        question = get_question(request.user, question_id)
        serializer = QuestionReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = review_question(
            request.user,
            question,
            serializer.validated_data["action"],
            serializer.validated_data.get("comment"),
            request,
        )
        return success(QuestionDetailSerializer(updated).data)


class QuestionResourceUploadView(APIView):
    permission_classes = [roles_required(*EDIT_ROLES)]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        tags=["题库"],
        summary="RES-01 上传试题资源",
        request=ResourceUploadSerializer,
        responses={
            200: api_response("ResourceUploadResponse", QuestionResourceItemSerializer(many=True))
        },
    )
    def post(self, request, question_id: int):
        question = get_question(request.user, question_id)
        serializer = ResourceUploadSerializer(
            data={"files": request.FILES.getlist("files"), "type": request.data.get("type")}
        )
        serializer.is_valid(raise_exception=True)
        resources = upload_resources(
            request.user,
            question,
            serializer.validated_data["files"],
            serializer.validated_data["type"],
            request,
        )
        return success(QuestionResourceItemSerializer(resources, many=True).data)


class QuestionResourceDeleteView(APIView):
    permission_classes = [roles_required(*EDIT_ROLES)]

    @extend_schema(
        tags=["题库"],
        summary="RES-02 删除试题资源",
        responses={200: api_response("ResourceDeleteResponse", DeleteResourceResultSerializer())},
    )
    def delete(self, request, question_id: int, resource_id: int):
        question = get_question(request.user, question_id)
        return success(delete_resource(request.user, question, resource_id, request))
