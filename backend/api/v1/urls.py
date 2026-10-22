"""API v1 路由汇总。"""
from django.urls import include, path

from apps.accounts.account_views import AccountListView
from apps.classes.views import ClassListCreateView
from apps.files.views import FileUploadView
from apps.qbank.catalog_views import CourseListCreateView
from apps.qbank.log_views import LogListView
from apps.qbank.question_views import QuestionListCreateView

urlpatterns = [
    path("auth/", include("apps.accounts.urls")),
    path("", include("apps.exams.urls")),
    # 集合路径按 api.md 不带末尾斜杠，单独注册后再挂载子路径
    path("accounts", AccountListView.as_view(), name="account-list"),
    path("accounts/", include("apps.accounts.account_urls")),
    path("classes", ClassListCreateView.as_view(), name="class-list-create"),
    path("classes/", include("apps.classes.urls")),
    path("files", FileUploadView.as_view(), name="file-upload"),
    path("files/", include("apps.files.urls")),
    path("courses", CourseListCreateView.as_view(), name="course-list-create"),
    path("courses/", include("apps.qbank.course_urls")),
    path("chapters/", include("apps.qbank.chapter_urls")),
    path("questions", QuestionListCreateView.as_view(), name="question-list-create"),
    path("questions/", include("apps.qbank.question_urls")),
    path("logs", LogListView.as_view(), name="log-list"),
    path("logs/", include("apps.qbank.log_urls")),
]
