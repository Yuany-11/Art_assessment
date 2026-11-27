"""统一分页：请求 pageNum/pageSize，响应 {total, pages, list}。"""
from math import ceil

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    page_query_param = "pageNum"
    page_size_query_param = "pageSize"
    max_page_size = 100

    def get_paginated_response(self, data):
        total = self.page.paginator.count
        # 用实际分页器的每页条数（pageSize 可能覆盖类默认值），不能读
        # self.page_size —— DRF 在 paginate_queryset 里只用局部变量，不会回写该属性，
        # 否则 pages 恒按默认 10 计算，前端按 pages 翻页会 404。
        page_size = self.page.paginator.per_page or total
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
