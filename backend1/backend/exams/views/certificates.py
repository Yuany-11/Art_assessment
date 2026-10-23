from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from common.enums import Role
from common.permissions import ALL_VIEW_ROLES, ensure_role
from common.responses import ok
from exams.presenters import certificate_item
from exams.serializers import CertificateGenerateSerializer
from exams.services import certificate as service
from exams.views.base import BaseAPIView, file_response


class CertificateGenerateView(BaseAPIView):
    @extend_schema(
        tags=["证书"], request=CertificateGenerateSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        ensure_role(request.user, Role.TEACHER, Role.SCHOOL_ADMIN,
                    Role.DISTRICT_ADMIN, Role.CITY_ADMIN, Role.PROVINCE_ADMIN)

        def produce():
            return ok(service.generate_certificates(request.user, request.data, request))

        return self.idempotent(request, produce)


class CertificateListView(BaseAPIView):
    @extend_schema(tags=["证书"], operation_id="certificates_list",
                   responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        ensure_role(request.user, *ALL_VIEW_ROLES)
        qs = service.list_certificates(request.user, request.query_params)
        return self.paginate(request, qs, certificate_item)


class CertificateDetailView(BaseAPIView):
    @extend_schema(tags=["证书"], operation_id="certificate_retrieve",
                   responses={200: OpenApiTypes.OBJECT})
    def get(self, request, certificate_id):
        ensure_role(request.user, *ALL_VIEW_ROLES)
        cert = service.get_certificate(request.user, certificate_id)
        return ok(certificate_item(cert))


class CertificateDownloadView(BaseAPIView):
    @extend_schema(tags=["证书"], responses={200: OpenApiTypes.BINARY})
    def get(self, request, certificate_id):
        ensure_role(request.user, *ALL_VIEW_ROLES)
        content, filename = service.download_certificate(request.user, certificate_id)
        return file_response(content, filename, "application/pdf")
