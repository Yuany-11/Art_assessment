"""根路由：/admin、OpenAPI schema、/api/v1。"""
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/v1/", include("api.v1.urls")),
]
