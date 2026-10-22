"""账号管理路由：静态路径必须先于 /accounts/<int:account_id> 注册。"""
from django.urls import path

from .account_views import (
    AccountDetailView,
    CityCreateView,
    DistrictCreateView,
    ImportTaskStatusView,
    ResetPasswordView,
    SchoolCreateView,
    StudentCreateView,
    TeacherCreateView,
    TeacherImportView,
)

urlpatterns = [
    path("teachers", TeacherCreateView.as_view(), name="account-teacher-create"),
    path("teachers/import", TeacherImportView.as_view(), name="account-teacher-import"),
    path("imports/<str:task_id>", ImportTaskStatusView.as_view(), name="account-import-task"),
    path("students", StudentCreateView.as_view(), name="account-student-create"),
    path("schools", SchoolCreateView.as_view(), name="account-school-create"),
    path("districts", DistrictCreateView.as_view(), name="account-district-create"),
    path("cities", CityCreateView.as_view(), name="account-city-create"),
    path("<int:account_id>", AccountDetailView.as_view(), name="account-detail"),
    path(
        "<int:account_id>/reset-password",
        ResetPasswordView.as_view(),
        name="account-reset-password",
    ),
]
