"""操作日志路由。"""
from django.urls import path

from .log_views import LogDetailView

urlpatterns = [
    path("<int:log_id>", LogDetailView.as_view(), name="log-detail"),
]
