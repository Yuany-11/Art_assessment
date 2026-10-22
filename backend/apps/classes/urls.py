"""班级路由：/search 必须先于 /<int:class_id> 注册。"""
from django.urls import path

from .views import (
    ClassChangeView,
    ClassDetailView,
    ClassJoinView,
    ClassLeaveView,
    ClassRequestReviewView,
    ClassRequestsView,
    ClassSearchView,
    ClassStudentImportView,
    ClassStudentRemoveView,
    ClassStudentsView,
)

urlpatterns = [
    path("search", ClassSearchView.as_view(), name="class-search"),
    path("<int:class_id>", ClassDetailView.as_view(), name="class-detail"),
    path("<int:class_id>/join", ClassJoinView.as_view(), name="class-join"),
    path("<int:class_id>/leave", ClassLeaveView.as_view(), name="class-leave"),
    path("<int:class_id>/change", ClassChangeView.as_view(), name="class-change"),
    path("<int:class_id>/requests", ClassRequestsView.as_view(), name="class-requests"),
    path(
        "<int:class_id>/requests/<int:request_id>/review",
        ClassRequestReviewView.as_view(),
        name="class-request-review",
    ),
    path("<int:class_id>/students", ClassStudentsView.as_view(), name="class-students"),
    path(
        "<int:class_id>/students/<int:student_id>",
        ClassStudentRemoveView.as_view(),
        name="class-student-remove",
    ),
    path(
        "<int:class_id>/students/import",
        ClassStudentImportView.as_view(),
        name="class-student-import",
    ),
]
