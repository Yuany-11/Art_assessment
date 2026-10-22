"""课程与章节路由。"""
from django.urls import path

from .catalog_views import ChapterListCreateView, CourseDetailView

urlpatterns = [
    path("<int:course_id>", CourseDetailView.as_view(), name="course-detail"),
    path("<int:course_id>/chapters", ChapterListCreateView.as_view(), name="course-chapters"),
]
