"""API v1 路由汇总。"""
from django.urls import include, path

urlpatterns = [
    path("auth/", include("apps.accounts.urls")),
]
