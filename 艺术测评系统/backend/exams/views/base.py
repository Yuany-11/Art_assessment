from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from common.pagination import StandardPagination
from common.utils import idempotency_get, idempotency_set


class BaseAPIView(APIView):
    def paginate(self, request, data, presenter):
        paginator = StandardPagination()
        page = paginator.paginate_queryset(data, request, view=self)
        return paginator.get_paginated_response([presenter(item) for item in page])

    def idempotent(self, request, produce):
        key = request.headers.get("Idempotency-Key")
        if key:
            cached = idempotency_get(request.user.id, key)
            if cached is not None:
                return Response(cached)
        response = produce()
        if key and 200 <= response.status_code < 300:
            idempotency_set(
                request.user.id, key, response.data, _ttl()
            )
        return response


def _ttl():
    from django.conf import settings

    return settings.IDEMPOTENCY_TTL_SECONDS


def file_response(content, filename, content_type, extra_headers=None):
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    for key, value in (extra_headers or {}).items():
        response[key] = str(value)
    return response


def int_query(request, name):
    value = request.query_params.get(name)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        from common.exceptions import BadRequest

        raise BadRequest(f"{name} 必须为整数")
