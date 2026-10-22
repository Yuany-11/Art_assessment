"""统一分页：请求 pageNum/pageSize，响应 {total, pages, list}。"""
from math import ceil

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    page_size_query_param = "pageSize"
    max_page_size = 100

    def get_paginated_response(self, data):
        total = self.page.paginator.count
        page_size = self.page_size or total
        return Response(
            {
                "code": 200,
                "message": "success",
                "data": {
                    "total": total,
                    "pages": ceil(total / page_size) if page_size else 0,
                    "list": data,
                },
            }
        )
