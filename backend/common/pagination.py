"""统一分页：请求 pageNum/pageSize，响应 {total, pages, list}。"""
from math import ceil

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    page_size_query_param = "pageSize"
    max_page_size = 100

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extra_data = {}

    def get_paginated_response(self, data):
        total = self.page.paginator.count
        page_size = (
            getattr(self.page.paginator, "per_page", None) or self.page_size or total
        )
        payload = {
            "total": total,
            "pages": ceil(total / page_size) if page_size else 0,
            "list": data,
        }
        payload.update(self.extra_data)
        return Response(
            {
                "code": 200,
                "message": "success",
                "data": payload,
            }
        )
