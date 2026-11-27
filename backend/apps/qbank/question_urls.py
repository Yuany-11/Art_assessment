"""试题路由：静态子路径必须先于 /questions/<int:question_id> 之外的参数冲突。"""
from django.urls import path

from .question_views import (
    QuestionDetailView,
    QuestionFavoriteView,
    QuestionQgenCatalogView,
    QuestionQgenGenerateView,
    QuestionResourceDeleteView,
    QuestionResourceUploadView,
    QuestionReviewView,
    QuestionSimilarAudioView,
    QuestionSubmitReviewView,
)

urlpatterns = [
    path("favorites", QuestionFavoriteView.as_view(), name="question-favorites"),
    path("qgen/catalog", QuestionQgenCatalogView.as_view(), name="question-qgen-catalog"),
    path("qgen/generate", QuestionQgenGenerateView.as_view(), name="question-qgen-generate"),
    path(
        "<int:question_id>/favorite",
        QuestionFavoriteView.as_view(),
        name="question-favorite",
    ),
    path("<int:question_id>", QuestionDetailView.as_view(), name="question-detail"),
    path(
        "<int:question_id>/submit-review",
        QuestionSubmitReviewView.as_view(),
        name="question-submit-review",
    ),
    path("<int:question_id>/review", QuestionReviewView.as_view(), name="question-review"),
    path(
        "<int:question_id>/similar-audio",
        QuestionSimilarAudioView.as_view(),
        name="question-similar-audio",
    ),
    path(
        "<int:question_id>/resources",
        QuestionResourceUploadView.as_view(),
        name="question-resource-upload",
    ),
    path(
        "<int:question_id>/resources/<int:resource_id>",
        QuestionResourceDeleteView.as_view(),
        name="question-resource-delete",
    ),
]
