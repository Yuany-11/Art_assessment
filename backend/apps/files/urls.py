"""文件子路由（删除）。"""
from django.urls import path

from .views import FileDeleteView

urlpatterns = [
    path("<int:file_id>", FileDeleteView.as_view(), name="file-delete"),
]
