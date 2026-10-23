from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from common.response import ok
from apps.exams.presenters import grading_attempt_detail, grading_task_item
from apps.exams.serializers import GradingSubmitSerializer
from apps.exams.services import grading as service
from apps.exams.views.base import BaseAPIView


class GradingTaskListView(BaseAPIView):
    @extend_schema(tags=["人工评分"], responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        qs = service.list_tasks(request.user, request.query_params)
        return self.paginate(request, qs, grading_task_item)


class GradingAttemptDetailView(BaseAPIView):
    @extend_schema(tags=["人工评分"], responses={200: OpenApiTypes.OBJECT})
    def get(self, request, attempt_id):
        attempt = service.get_grading_attempt(request.user, attempt_id)
        return ok(grading_attempt_detail(attempt))


class GradingAttemptScoreView(BaseAPIView):
    @extend_schema(
        tags=["人工评分"], request=GradingSubmitSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def patch(self, request, attempt_id):
        attempt = service.get_grading_attempt(request.user, attempt_id)
        attempt, score = service.submit_grading(
            request.user, attempt, request.data, request
        )
        data = grading_attempt_detail(attempt)
        data["scoreId"] = score.id if score else None
        return ok(data)
