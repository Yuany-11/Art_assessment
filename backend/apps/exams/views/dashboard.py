"""工作台概览接口。"""
from apps.exams.services.dashboard import dashboard_summary
from apps.exams.views.base import BaseAPIView
from common.response import ok


class DashboardSummaryView(BaseAPIView):
    def get(self, request):
        return ok(dashboard_summary(request.user))
