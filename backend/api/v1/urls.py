"""API v1 路由汇总。"""
from django.urls import include, path

from apps.accounts.account_views import AccountListView
from apps.classes.views import ClassListCreateView

urlpatterns = [
    path("auth/", include("apps.accounts.urls")),
    # 集合路径按 api.md 不带末尾斜杠，单独注册后再挂载子路径
    path("accounts", AccountListView.as_view(), name="account-list"),
    path("accounts/", include("apps.accounts.account_urls")),
    path("classes", ClassListCreateView.as_view(), name="class-list-create"),
    path("classes/", include("apps.classes.urls")),
]
