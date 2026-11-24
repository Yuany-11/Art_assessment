"""操作日志接口（LOG-01 ~ LOG-02）。"""
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.views import APIView

from common.enums import Role
from common.pagination import StandardPagination
from common.permissions import roles_required
from common.response import success
from common.schema import api_response, paged_response

from .serializers import OperationLogItemSerializer
from .services import get_log, list_logs


class LogListView(APIView):
    permission_classes = [roles_required(Role.QUESTION_ADMIN, Role.PROVINCE_ADMIN)]

    @extend_schema(
        tags=["题库"],
        summary="LOG-01 查询操作日志列表",
        operation_id="logs_list",
        parameters=[
            OpenApiParameter("operatorId", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("action", OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter("resourceType", OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter("resourceId", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("result", OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter("keyword", OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter("startTime", OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter("endTime", OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter("pageNum", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("pageSize", OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        responses={200: paged_response("LogListResponse", OperationLogItemSerializer(many=True))},
    )
    def get(self, request):
        queryset = list_logs(request.user, request.query_params)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            OperationLogItemSerializer(page, many=True).data
        )


class LogDetailView(APIView):
    permission_classes = [roles_required(Role.QUESTION_ADMIN, Role.PROVINCE_ADMIN)]

    @extend_schema(
        tags=["题库"],
        summary="LOG-02 查询操作日志详情",
        operation_id="logs_retrieve",
        responses={200: api_response("LogDetailResponse", OperationLogItemSerializer())},
    )
    def get(self, request, log_id: int):
        return success(OperationLogItemSerializer(get_log(request.user, log_id)).data)
