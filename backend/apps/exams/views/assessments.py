from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from common.permissions import ALL_VIEW_ROLES, TEACHER_AND_ADMIN, ensure_role
from common.response import ok
from apps.exams.presenters import assessment_item
from apps.exams.serializers import (
    AssessmentCreateSerializer,
    AttemptStartSerializer,
    WithdrawSerializer,
)
from apps.exams.services import assessment as service
from apps.exams.services import attempt as attempt_service
from apps.exams.presenters import attempt_detail
from apps.exams.views.base import BaseAPIView


class AssessmentListCreateView(BaseAPIView):
    @extend_schema(tags=["测评"], operation_id="assessments_list",
                   responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        ensure_role(request.user, *ALL_VIEW_ROLES)
        qs = service.list_assessments(request.user, request.query_params)
        return self.paginate(request, qs, assessment_item)

    @extend_schema(
        tags=["测评"], request=AssessmentCreateSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        ensure_role(request.user, *TEACHER_AND_ADMIN)

        def produce():
            assessment = service.publish_assessment(request.user, request.data, request)
            return ok(assessment_item(assessment))

        return self.idempotent(request, produce)


class AssessmentDetailView(BaseAPIView):
    @extend_schema(tags=["测评"], operation_id="assessment_retrieve",
                   responses={200: OpenApiTypes.OBJECT})
    def get(self, request, assessment_id):
        ensure_role(request.user, *ALL_VIEW_ROLES)
        assessment = service.get_assessment(request.user, assessment_id)
        return ok(assessment_item(assessment))


class AssessmentWithdrawView(BaseAPIView):
    @extend_schema(
        tags=["测评"], request=WithdrawSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request, assessment_id):
        ensure_role(request.user, *TEACHER_AND_ADMIN)
        assessment = service.get_assessment(request.user, assessment_id)

        def produce():
            withdrawn = service.withdraw_assessment(
                request.user, assessment, request.data, request
            )
            return ok(assessment_item(withdrawn))

        return self.idempotent(request, produce)


class AttemptStartView(BaseAPIView):
    @extend_schema(
        tags=["答题"], request=AttemptStartSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request, assessment_id):
        ensure_role(request.user, *ALL_VIEW_ROLES)
        assessment = service.get_assessment(request.user, assessment_id)
        serializer = AttemptStartSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        attempt = attempt_service.start_attempt(
            request.user, assessment, serializer.validated_data.get("deviceType") or "web"
        )
        return ok(attempt_detail(attempt))
