"""学生错题本接口（WQ-01 ~ WQ-06）。"""
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from common.enums import Role
from common.permissions import ensure_role
from common.response import ok
from apps.exams.presenters import attempt_question, wrong_question_item
from apps.exams.services import wrong_question as service
from apps.exams.views.base import BaseAPIView


class WrongQuestionListView(BaseAPIView):
    @extend_schema(tags=["错题本"], responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        ensure_role(request.user, Role.STUDENT)
        qs = service.list_wrong_questions(request.user, request.query_params)
        return self.paginate(request, qs, wrong_question_item)


class WrongQuestionStatisticsView(BaseAPIView):
    @extend_schema(tags=["错题本"], responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        ensure_role(request.user, Role.STUDENT)
        return ok(service.statistics(request.user))


class WrongQuestionDetailView(BaseAPIView):
    @extend_schema(tags=["错题本"], responses={200: OpenApiTypes.OBJECT})
    def get(self, request, wrong_id):
        ensure_role(request.user, Role.STUDENT)
        item = service.get_wrong_question(request.user, wrong_id)
        return ok(service.detail_payload(request.user, item))

    @extend_schema(tags=["错题本"], request=OpenApiTypes.OBJECT,
                   responses={200: OpenApiTypes.OBJECT})
    def patch(self, request, wrong_id):
        ensure_role(request.user, Role.STUDENT)
        item = service.get_wrong_question(request.user, wrong_id)
        item = service.update_wrong_question(request.user, item, request.data)
        return ok(service.detail_payload(request.user, item))

    @extend_schema(tags=["错题本"], responses={200: OpenApiTypes.OBJECT})
    def delete(self, request, wrong_id):
        ensure_role(request.user, Role.STUDENT)
        item = service.get_wrong_question(request.user, wrong_id)
        service.remove_wrong_question(request.user, item)
        return ok({"deleted": True, "wrongId": wrong_id})


class WrongQuestionRedoView(BaseAPIView):
    @extend_schema(tags=["错题本"], request=None, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, wrong_id):
        ensure_role(request.user, Role.STUDENT)
        item = service.get_wrong_question(request.user, wrong_id)
        attempt, snapshot = service.redo_wrong_question(request.user, item)
        return ok({
            "attemptId": attempt.id,
            "wrongId": item.id,
            "question": attempt_question(snapshot),
        })
