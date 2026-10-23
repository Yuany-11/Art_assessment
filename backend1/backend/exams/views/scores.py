from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from common.enums import Role
from common.permissions import ADMIN_ROLES, ALL_VIEW_ROLES, ensure_role
from common.responses import ok
from exams.models import Certificate
from exams.presenters import score_detail, score_item
from exams.serializers import (
    ManualScoreSerializer,
    RegradeSerializer,
    ScoreImportMetaSerializer,
    ScoreImportUploadSerializer,
)
from exams.services import grading as grading_service
from exams.services import score as service
from exams.services import statistics
from exams.views.base import BaseAPIView, file_response

SCORE_ROLES = {Role.TEACHER, *ADMIN_ROLES}


class MyScoresView(BaseAPIView):
    @extend_schema(tags=["成绩"], responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        ensure_role(request.user, Role.STUDENT)
        qs = service.my_scores(request.user, request.query_params)
        return self.paginate(request, qs, score_item)


class ScoreListView(BaseAPIView):
    @extend_schema(tags=["成绩"], operation_id="scores_list",
                   responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        ensure_role(request.user, *SCORE_ROLES)
        qs = service.list_scores(request.user, request.query_params)
        return self.paginate(request, qs, score_item)


class ScoreDetailView(BaseAPIView):
    @extend_schema(tags=["成绩"], operation_id="score_retrieve",
                   responses={200: OpenApiTypes.OBJECT})
    def get(self, request, score_id):
        ensure_role(request.user, *ALL_VIEW_ROLES)
        score = service.get_score(request.user, score_id)
        cert = Certificate.objects.filter(
            assessment_id=score.assessment_id, student_id=score.student_id
        ).first()
        return ok(score_detail(
            score,
            service.answer_visible(request.user, score),
            cert.id if cert else None,
        ))


class StatisticsOverviewView(BaseAPIView):
    @extend_schema(tags=["统计"], responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        ensure_role(request.user, *SCORE_ROLES)
        return ok(statistics.stat_overview(request.user, request.query_params))


class StatisticsListView(BaseAPIView):
    @extend_schema(tags=["统计"], responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        ensure_role(request.user, *SCORE_ROLES)
        rows = statistics.stat_list_rows(request.user, request.query_params)
        return self.paginate(request, rows, lambda row: row)


class StatisticsExportView(BaseAPIView):
    @extend_schema(tags=["统计"], responses={200: OpenApiTypes.BINARY})
    def get(self, request):
        ensure_role(request.user, *SCORE_ROLES)
        content, filename = statistics.export_xlsx_bytes(
            request.user, request.query_params
        )
        return file_response(
            content, filename,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class ManualScoreView(BaseAPIView):
    @extend_schema(
        tags=["成绩"], request=ManualScoreSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        ensure_role(request.user, *SCORE_ROLES)

        def produce():
            score = service.manual_score(request.user, request.data, request)
            return ok(score_item(score))

        return self.idempotent(request, produce)


class ScoreImportView(BaseAPIView):
    @extend_schema(
        tags=["成绩"], request=ScoreImportUploadSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        ensure_role(request.user, *SCORE_ROLES)
        meta_serializer = ScoreImportMetaSerializer(data=request.data)
        meta_serializer.is_valid(raise_exception=True)
        file = request.FILES.get("file")

        def produce():
            task, mode = service.import_scores(
                request.user, file, meta_serializer.validated_data, request
            )
            return ok({
                "taskId": task.task_id,
                "status": task.status,
                "mode": mode,
                "total": task.total,
                "successCount": task.success_count,
                "failCount": task.fail_count,
                "errors": task.errors or [],
            })

        return self.idempotent(request, produce)


class RegradeView(BaseAPIView):
    @extend_schema(
        tags=["成绩"], request=RegradeSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request, score_id):
        ensure_role(request.user, *SCORE_ROLES)
        score = service.get_score(request.user, score_id)
        score, ai_error = grading_service.regrade_score(
            request.user, score, request.data, request
        )
        data = score_item(score)
        data["aiError"] = ai_error
        return ok(data)
