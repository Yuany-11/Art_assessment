from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from common.enums import Role
from common.permissions import ensure_role
from common.response import ok
from apps.exams.presenters import attempt_detail, submit_result
from apps.exams.serializers import SaveAnswersSerializer, SubmitSerializer
from apps.exams.services import attempt as service
from apps.exams.views.base import BaseAPIView


class AttemptDetailView(BaseAPIView):
    @extend_schema(tags=["答题"], responses={200: OpenApiTypes.OBJECT})
    def get(self, request, attempt_id):
        ensure_role(request.user, Role.STUDENT)
        attempt = service.get_attempt(request.user, attempt_id)
        return ok(attempt_detail(attempt))


class AttemptAnswersView(BaseAPIView):
    @extend_schema(
        tags=["答题"], request=SaveAnswersSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def patch(self, request, attempt_id):
        ensure_role(request.user, Role.STUDENT)
        attempt = service.get_attempt(request.user, attempt_id)
        result = service.save_answers(request.user, attempt, request.data)
        return ok({
            "attemptId": attempt.id,
            "savedCount": result["savedCount"],
            "savedAt": result["savedAt"],
            "serverTime": result["serverTime"],
            "remainingSeconds": result["remainingSeconds"],
        })


class AttemptSubmitView(BaseAPIView):
    @extend_schema(
        tags=["答题"], request=SubmitSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request, attempt_id):
        ensure_role(request.user, Role.STUDENT)
        # 手动交卷不在这里自动关闭，交由 submit_attempt 按 allowLateSubmit 规则判断
        attempt = service.get_attempt(request.user, attempt_id, auto_close=False)

        def produce():
            submitted, already = service.submit_attempt(
                request.user, attempt, request.data or None
            )
            message = "交卷成功" if not already else "答卷已提交，返回首次交卷结果"
            return ok(submit_result(submitted, message=message))

        return self.idempotent(request, produce)
