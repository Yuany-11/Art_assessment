from django.urls import path

from .views import NotificationListView, NotificationReadAllView, NotificationReadView

urlpatterns = [
    # 静态路径必须在参数化路径之前
    path("read-all", NotificationReadAllView.as_view()),
    path("<int:notification_id>/read", NotificationReadView.as_view()),
]
