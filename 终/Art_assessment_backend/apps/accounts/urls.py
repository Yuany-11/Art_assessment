"""认证路由，路径不带末尾斜杠，与 api.md 保持一致。"""
from django.urls import path

from .views import (
    LoginView,
    LogoutView,
    MeView,
    MenusView,
    PasswordView,
    RefreshView,
    RegisterCodeView,
    RegisterView,
)

urlpatterns = [
    path("login", LoginView.as_view(), name="auth-login"),
    path("register/code", RegisterCodeView.as_view(), name="auth-register-code"),
    path("register", RegisterView.as_view(), name="auth-register"),
    path("refresh", RefreshView.as_view(), name="auth-refresh"),
    path("logout", LogoutView.as_view(), name="auth-logout"),
    path("me", MeView.as_view(), name="auth-me"),
    path("password", PasswordView.as_view(), name="auth-password"),
    path("menus", MenusView.as_view(), name="auth-menus"),
]
