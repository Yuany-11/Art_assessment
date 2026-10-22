"""课程与章节接口（CRS-01 ~ CRS-05、CHP-01 ~ CHP-05）。"""
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.views import APIView

from common.enums import Role
from common.pagination import StandardPagination
from common.permissions import roles_required
from common.response import success
from common.schema import api_response, paged_response

from .serializers import (
    ChapterCreateSerializer,
    ChapterItemSerializer,
    ChapterUpdateSerializer,
    CourseCreateSerializer,
    CourseItemSerializer,
    CourseUpdateSerializer,
    DeleteChapterResultSerializer,
    DeleteCourseResultSerializer,
)
from .services import (
    create_chapter,
    create_course,
    delete_chapter,
    delete_course,
    get_chapter,
    get_course,
    list_chapters,
    list_courses,
    update_chapter,
    update_course,
)

ALL_ROLES = (
    Role.STUDENT,
    Role.TEACHER,
    Role.SCHOOL_ADMIN,
    Role.DISTRICT_ADMIN,
    Role.CITY_ADMIN,
    Role.PROVINCE_ADMIN,
    Role.QUESTION_ADMIN,
)

COURSE_PARAMETERS = [
    OpenApiParameter("subject", OpenApiTypes.STR, OpenApiParameter.QUERY),
    OpenApiParameter("grade", OpenApiTypes.INT, OpenApiParameter.QUERY),
    OpenApiParameter("keyword", OpenApiTypes.STR, OpenApiParameter.QUERY),
    OpenApiParameter("status", OpenApiTypes.STR, OpenApiParameter.QUERY),
    OpenApiParameter("pageNum", OpenApiTypes.INT, OpenApiParameter.QUERY),
    OpenApiParameter("pageSize", OpenApiTypes.INT, OpenApiParameter.QUERY),
]


def _paginate(request, queryset, serializer_class, view):
    paginator = StandardPagination()
    page = paginator.paginate_queryset(queryset, request, view=view)
    return paginator.get_paginated_response(serializer_class(page, many=True).data)


class CourseListCreateView(APIView):
    permission_classes = [roles_required(*ALL_ROLES)]

    @extend_schema(
        tags=["课程与章节"],
        summary="CRS-01 查询课程列表",
        operation_id="courses_list",
        parameters=COURSE_PARAMETERS,
        responses={200: paged_response("CourseListResponse", CourseItemSerializer(many=True))},
    )
    def get(self, request):
        queryset = list_courses(request.user, request.query_params)
        return _paginate(request, queryset, CourseItemSerializer, self)

    @extend_schema(
        tags=["课程与章节"],
        summary="CRS-02 创建课程",
        request=CourseCreateSerializer,
        responses={200: api_response("CourseCreateResponse", CourseItemSerializer())},
    )
    def post(self, request):
        serializer = CourseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        course = create_course(request.user, serializer.validated_data)
        return success(CourseItemSerializer(course).data)


class CourseDetailView(APIView):
    permission_classes = [roles_required(*ALL_ROLES)]

    @extend_schema(
        tags=["课程与章节"],
        summary="CRS-03 查询课程详情",
        operation_id="courses_retrieve",
        responses={200: api_response("CourseDetailResponse", CourseItemSerializer())},
    )
    def get(self, request, course_id: int):
        return success(CourseItemSerializer(get_course(request.user, course_id)).data)

    @extend_schema(
        tags=["课程与章节"],
        summary="CRS-04 修改课程",
        request=CourseUpdateSerializer,
        responses={200: api_response("CourseUpdateResponse", CourseItemSerializer())},
    )
    def patch(self, request, course_id: int):
        course = get_course(request.user, course_id)
        serializer = CourseUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = update_course(request.user, course, serializer.validated_data)
        return success(CourseItemSerializer(updated).data)

    @extend_schema(
        tags=["课程与章节"],
        summary="CRS-05 删除课程",
        responses={200: api_response("CourseDeleteResponse", DeleteCourseResultSerializer())},
    )
    def delete(self, request, course_id: int):
        course = get_course(request.user, course_id)
        return success(delete_course(request.user, course))


class ChapterListCreateView(APIView):
    permission_classes = [roles_required(*ALL_ROLES)]

    @extend_schema(
        tags=["课程与章节"],
        summary="CHP-01 查询课程章节",
        responses={200: api_response("ChapterListResponse", ChapterItemSerializer(many=True))},
    )
    def get(self, request, course_id: int):
        course = get_course(request.user, course_id)
        chapters = list_chapters(request.user, course)
        return success(ChapterItemSerializer(chapters, many=True).data)

    @extend_schema(
        tags=["课程与章节"],
        summary="CHP-02 创建章节",
        request=ChapterCreateSerializer,
        responses={200: api_response("ChapterCreateResponse", ChapterItemSerializer())},
    )
    def post(self, request, course_id: int):
        course = get_course(request.user, course_id)
        serializer = ChapterCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        chapter = create_chapter(request.user, course, serializer.validated_data)
        return success(ChapterItemSerializer(chapter).data)


class ChapterDetailView(APIView):
    permission_classes = [roles_required(*ALL_ROLES)]

    @extend_schema(
        tags=["课程与章节"],
        summary="CHP-03 查询章节详情",
        responses={200: api_response("ChapterDetailResponse", ChapterItemSerializer())},
    )
    def get(self, request, chapter_id: int):
        return success(ChapterItemSerializer(get_chapter(request.user, chapter_id)).data)

    @extend_schema(
        tags=["课程与章节"],
        summary="CHP-04 修改章节",
        request=ChapterUpdateSerializer,
        responses={200: api_response("ChapterUpdateResponse", ChapterItemSerializer())},
    )
    def patch(self, request, chapter_id: int):
        chapter = get_chapter(request.user, chapter_id)
        serializer = ChapterUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = update_chapter(request.user, chapter, serializer.validated_data)
        return success(ChapterItemSerializer(updated).data)

    @extend_schema(
        tags=["课程与章节"],
        summary="CHP-05 删除章节",
        responses={200: api_response("ChapterDeleteResponse", DeleteChapterResultSerializer())},
    )
    def delete(self, request, chapter_id: int):
        chapter = get_chapter(request.user, chapter_id)
        return success(delete_chapter(request.user, chapter))
