"""试题路由：静态子路径必须先于 /questions/<int:question_id> 之外的参数冲突。"""
from django.urls import path

from .question_views import (
    QuestionDetailView,
    QuestionResourceDeleteView,
    QuestionResourceUploadView,
    QuestionReviewView,
    QuestionSubmitReviewView,
)

urlpatterns = [
    path("<int:question_id>", QuestionDetailView.as_view(), name="question-detail"),
    path(
        "<int:question_id>/submit-review",
        QuestionSubmitReviewView.as_view(),
        name="question-submit-review",
    ),
    path("<int:question_id>/review", QuestionReviewView.as_view(), name="question-review"),
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
