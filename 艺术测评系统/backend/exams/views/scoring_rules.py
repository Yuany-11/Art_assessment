from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema

from common.permissions import ALL_VIEW_ROLES, TEACHER_AND_ADMIN, ensure_role
from common.responses import ok
from exams.serializers import RuleEvaluateSerializer
from exams.services import scoring_rules as service
from exams.views.base import BaseAPIView


class ScoringRuleListView(BaseAPIView):
    @extend_schema(
        tags=["评分规则"], operation_id="scoring_rules_list",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        ensure_role(request.user, *ALL_VIEW_ROLES)
        return ok(service.list_rules())


class ScoringRuleDetailView(BaseAPIView):
    @extend_schema(
        tags=["评分规则"], operation_id="scoring_rules_retrieve",
        parameters=[
            OpenApiParameter(
                name="level", type=int, required=False,
                description="考级级别 1-10；不传则使用通用基线",
            ),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, subject, category):
        ensure_role(request.user, *ALL_VIEW_ROLES)
        level = request.query_params.get("level")
        return ok(service.get_rule(subject, category, level=level))


class ScoringRuleEvaluateView(BaseAPIView):
    @extend_schema(
        tags=["评分规则"], operation_id="scoring_rules_evaluate",
        request=RuleEvaluateSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        ensure_role(request.user, *TEACHER_AND_ADMIN)
        serializer = RuleEvaluateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = service.evaluate(
            data["subject"],
            data["category"],
            level=data.get("level"),
            metrics=data["metrics"],
            max_score=data.get("maxScore", 100),
            confidence=data.get("confidence"),
        )
        return ok(result)
