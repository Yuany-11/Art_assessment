from math import ceil

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    page_size_query_param = "pageSize"
    page_query_param = "pageNum"
    page_size = 10
    max_page_size = 100

    def get_page_size(self, request):
        raw = request.query_params.get(self.page_size_query_param)
        if raw in (None, ""):
            return self.page_size
        try:
            size = int(raw)
        except (TypeError, ValueError):
            from common.exceptions import BusinessError

            raise BusinessError(400, "pageSize 必须为整数")
        if size < 1:
            from common.exceptions import BusinessError

            raise BusinessError(400, "pageSize 必须大于 0")
        return min(size, self.max_page_size)

    def get_page_num(self, request):
        raw = request.query_params.get(self.page_query_param)
        if raw in (None, ""):
            return 1
        try:
            num = int(raw)
        except (TypeError, ValueError):
            from common.exceptions import BusinessError

            raise BusinessError(400, "pageNum 必须为整数")
        if num < 1:
            from common.exceptions import BusinessError

            raise BusinessError(400, "pageNum 必须大于 0")
        return num

    def paginate_queryset(self, queryset, request, view=None):
        self.page_size = self.get_page_size(request)
        page_num = self.get_page_num(request)
        paginator = self.django_paginator_class(queryset, self.page_size)
        self.page = paginator.page(min(page_num, paginator.num_pages) if paginator.num_pages else 1)
        return list(self.page)

    def get_paginated_response(self, data):
        total = self.page.paginator.count
        return Response({
            "code": 200,
            "message": "success",
            "data": {
                "total": total,
                "pages": ceil(total / self.page_size) if self.page_size else 0,
                "list": data,
            },
        })

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "code": {"type": "integer", "example": 200},
                "message": {"type": "string", "example": "success"},
                "data": {
                    "type": "object",
                    "properties": {
                        "total": {"type": "integer"},
                        "pages": {"type": "integer"},
                        "list": schema,
                    },
                },
            },
        }
