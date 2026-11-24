"""文件子路由（删除、作品评分）。"""
from django.urls import path

from .views import (
    FileArtworkReviewView,
    FileAudioAnalysisView,
    FileDeleteView,
)

urlpatterns = [
    path(
        "<int:file_id>/review",
        FileArtworkReviewView.as_view(),
        name="file-artwork-review",
    ),
    path(
        "<int:file_id>/audio-analysis",
        FileAudioAnalysisView.as_view(),
        name="file-audio-analysis",
    ),
    path("<int:file_id>", FileDeleteView.as_view(), name="file-delete"),
]
