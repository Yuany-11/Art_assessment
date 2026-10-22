from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from common.permissions import TEACHER_AND_ADMIN, ensure_role
from common.response import deleted, ok
from apps.exams.presenters import paper_detail, paper_item
from apps.exams.serializers import (
    PaperAutoCreateSerializer,
    PaperDraftSerializer,
    PaperManualCreateSerializer,
    PaperUpdateSerializer,
    PracticeRandomSerializer,
)
from apps.exams.services import paper as service
from apps.exams.views.base import BaseAPIView, file_response


class PaperListView(BaseAPIView):
    @extend_schema(tags=["试卷"], operation_id="papers_list",
                   responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        ensure_role(request.user, *TEACHER_AND_ADMIN)
        qs = service.list_papers(request.user, request.query_params)
        return self.paginate(request, qs, paper_item)


class PaperManualCreateView(BaseAPIView):
    @extend_schema(
        tags=["试卷"], request=PaperManualCreateSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        ensure_role(request.user, *TEACHER_AND_ADMIN)
        paper = service.create_manual_paper(request.user, request.data)
        return ok(paper_detail(paper))


class PaperAutoCreateView(BaseAPIView):
    @extend_schema(
        tags=["试卷"], request=PaperAutoCreateSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        ensure_role(request.user, *TEACHER_AND_ADMIN)
        paper = service.create_auto_paper(request.user, request.data)
        return ok(paper_detail(paper))


class PracticeRandomView(BaseAPIView):
    @extend_schema(
        tags=["试卷"], request=PracticeRandomSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        from common.enums import Role
        from apps.exams.presenters import attempt_detail

        ensure_role(request.user, Role.STUDENT)
        attempt = service.create_practice(request.user, request.data)
        return ok(attempt_detail(attempt))


class PaperDetailView(BaseAPIView):
    @extend_schema(tags=["试卷"], operation_id="paper_retrieve",
                   responses={200: OpenApiTypes.OBJECT})
    def get(self, request, paper_id):
        ensure_role(request.user, *TEACHER_AND_ADMIN)
        paper = service.get_paper(request.user, paper_id)
        return ok(paper_detail(paper))

    @extend_schema(
        tags=["试卷"], request=PaperUpdateSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def patch(self, request, paper_id):
        ensure_role(request.user, *TEACHER_AND_ADMIN)
        paper = service.get_paper(request.user, paper_id)
        paper = service.update_paper(request.user, paper, request.data)
        return ok(paper_detail(paper))

    @extend_schema(tags=["试卷"], responses={200: OpenApiTypes.OBJECT})
    def delete(self, request, paper_id):
        ensure_role(request.user, *TEACHER_AND_ADMIN)
        paper = service.get_paper(request.user, paper_id)
        service.delete_paper(request.user, paper)
        return deleted(paperId=paper_id)


class PaperDraftView(BaseAPIView):
    @extend_schema(
        tags=["试卷"], request=PaperDraftSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def patch(self, request, paper_id):
        ensure_role(request.user, *TEACHER_AND_ADMIN)
        paper = service.get_paper(request.user, paper_id)
        paper = service.update_paper(request.user, paper, request.data, draft=True)
        return ok(paper_detail(paper))


class PaperMaterialsDownloadView(BaseAPIView):
    @extend_schema(
        tags=["试卷"],
        responses={(200, "application/zip"): OpenApiTypes.BINARY},
    )
    def get(self, request, paper_id):
        ensure_role(request.user, *TEACHER_AND_ADMIN)
        paper = service.get_paper(request.user, paper_id)
        question_ids = None
        if request.query_params.get("questionIds"):
            try:
                question_ids = [
                    int(value) for value in request.query_params["questionIds"].split(",")
                    if value.strip()
                ]
            except ValueError:
                from common.exceptions import BadRequest

                raise BadRequest("questionIds 必须为逗号分隔的整数")
        types = None
        if request.query_params.get("types"):
            types = set(request.query_params["types"].split(","))
            if not types <= {"audio", "image"}:
                from common.exceptions import BadRequest

                raise BadRequest("types 仅支持 audio/image")
        content, filename, count = service.export_materials(
            request.user, paper, question_ids, types
        )
        return file_response(
            content, filename, "application/zip", {"X-Resource-Count": count}
        )


class PaperAnswersDownloadView(BaseAPIView):
    @extend_schema(tags=["试卷"], responses={200: OpenApiTypes.BINARY})
    def get(self, request, paper_id):
        ensure_role(request.user, *TEACHER_AND_ADMIN)
        paper = service.get_paper(request.user, paper_id)
        fmt = request.query_params.get("format", "pdf")
        if fmt not in ("pdf", "docx"):
            from common.exceptions import BadRequest

            raise BadRequest("format 仅支持 pdf/docx")
        include_analysis = request.query_params.get("includeAnalysis", "true").lower() != "false"
        include_rubric = request.query_params.get("includeRubric", "true").lower() != "false"
        content, filename, content_type = service.export_answers(
            request.user, paper, fmt, include_analysis, include_rubric
        )
        return file_response(content, filename, content_type)
