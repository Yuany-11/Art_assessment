"""章节路由。"""
from django.urls import path

from .catalog_views import ChapterDetailView, ChapterQuestionListView

urlpatterns = [
    path("<int:chapter_id>", ChapterDetailView.as_view(), name="chapter-detail"),
    path(
        "<int:chapter_id>/questions",
        ChapterQuestionListView.as_view(),
        name="chapter-questions",
    ),
]
