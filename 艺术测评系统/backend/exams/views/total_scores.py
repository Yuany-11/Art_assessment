from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema

from common.enums import Role
from common.permissions import ensure_role
from common.responses import deleted, ok
from exams.presenters import total_score_rule_item
from exams.serializers import (
    TotalScoreRuleCreateSerializer,
    TotalScoreRuleUpdateSerializer,
)
from exams.services import total_score as service
from exams.views.base import BaseAPIView


class TotalScoreRuleDefaultsView(BaseAPIView):
    @extend_schema(
        tags=["教师总评"], operation_id="total_score_rule_defaults",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        ensure_role(request.user, Role.TEACHER)
        return ok(service.load_defaults())


class TotalScoreRuleListView(BaseAPIView):
    @extend_schema(
        tags=["教师总评"], operation_id="total_score_rules_list",
        parameters=[
            OpenApiParameter(name="subject", type=str, required=False),
            OpenApiParameter(name="classId", type=int, required=False),
            OpenApiParameter(name="term", type=str, required=False),
            OpenApiParameter(name="status", type=str, required=False),
            OpenApiParameter(name="keyword", type=str, required=False),
            OpenApiParameter(name="includeArchived", type=bool, required=False),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        ensure_role(request.user, Role.TEACHER)
        qs = service.list_rules(request.user, request.query_params)
        return self.paginate(request, qs, total_score_rule_item)

    @extend_schema(
        tags=["教师总评"], operation_id="total_score_rules_create",
        request=TotalScoreRuleCreateSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        ensure_role(request.user, Role.TEACHER)
        rule = service.create_rule(request.user, request.data, request=request)
        rule = service.get_rule(request.user, rule.id)
        return ok(total_score_rule_item(rule))


class TotalScoreRuleDetailView(BaseAPIView):
    @extend_schema(
        tags=["教师总评"], operation_id="total_score_rules_retrieve",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, rule_id):
        ensure_role(request.user, Role.TEACHER)
        rule = service.get_rule(request.user, rule_id)
        return ok(total_score_rule_item(rule))

    @extend_schema(
        tags=["教师总评"], operation_id="total_score_rules_update",
        request=TotalScoreRuleUpdateSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def patch(self, request, rule_id):
        ensure_role(request.user, Role.TEACHER)
        rule = service.get_rule(request.user, rule_id)
        rule = service.update_rule(request.user, rule, request.data, request=request)
        return ok(total_score_rule_item(rule))

    @extend_schema(
        tags=["教师总评"], operation_id="total_score_rules_archive",
        responses={200: OpenApiTypes.OBJECT},
    )
    def delete(self, request, rule_id):
        ensure_role(request.user, Role.TEACHER)
        rule = service.get_rule(request.user, rule_id)
        service.archive_rule(request.user, rule, request=request)
        return deleted(ruleId=rule_id)


class TotalScoreRulePublishView(BaseAPIView):
    @extend_schema(
        tags=["教师总评"], operation_id="total_score_rules_publish",
        request=None, responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request, rule_id):
        ensure_role(request.user, Role.TEACHER)
        rule = service.get_rule(request.user, rule_id)
        rule = service.publish_rule(request.user, rule, request=request)
        return ok(total_score_rule_item(rule))


class TotalScoreRuleResultsView(BaseAPIView):
    @extend_schema(
        tags=["教师总评"], operation_id="total_score_rules_results",
        parameters=[
            OpenApiParameter(name="studentId", type=int, required=False),
            OpenApiParameter(name="studentKeyword", type=str, required=False),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, rule_id):
        ensure_role(request.user, Role.TEACHER)
        rule = service.get_rule(request.user, rule_id)
        result = service.compute_results(request.user, rule, request.query_params)
        return ok({"rule": total_score_rule_item(rule), **result})
