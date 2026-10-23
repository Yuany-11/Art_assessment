from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from common.permissions import ALL_VIEW_ROLES, ensure_role
from common.response import ok
from apps.exams.services import growth as service
from apps.exams.views.base import BaseAPIView


class GrowthCurveView(BaseAPIView):
    @extend_schema(tags=["成长与报告"], responses={200: OpenApiTypes.OBJECT})
    def get(self, request, student_id):
        ensure_role(request.user, *ALL_VIEW_ROLES)
        return ok(service.growth_curve(request.user, student_id, request.query_params))


class LearningReportView(BaseAPIView):
    @extend_schema(tags=["成长与报告"], responses={200: OpenApiTypes.OBJECT})
    def get(self, request, student_id):
        ensure_role(request.user, *ALL_VIEW_ROLES)
        return ok(service.learning_report(request.user, student_id, request.query_params))
