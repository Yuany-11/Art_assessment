from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from common.pagination import StandardPagination
from common.responses import ok
from common.utils import iso
from exams.presenters import notification_item
from exams.services import notification as service
from exams.views.base import BaseAPIView


class NotificationListView(BaseAPIView):
    @extend_schema(tags=["通知"], responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        qs = service.list_notifications(request.user, request.query_params)
        paginator = StandardPagination()
        paginator.page_size = 20  # NT-01 默认每页 20 条
        page = paginator.paginate_queryset(qs, request, view=self)
        response = paginator.get_paginated_response(
            [notification_item(item) for item in page]
        )
        response.data["data"]["unreadCount"] = service.unread_count(request.user)
        return response


class NotificationReadView(BaseAPIView):
    @extend_schema(tags=["通知"], request=None, responses={200: OpenApiTypes.OBJECT})
    def patch(self, request, notification_id):
        notification = service.mark_read(request.user, notification_id)
        return ok({
            "id": notification.id,
            "read": True,
            "readAt": iso(notification.read_at),
        })


class NotificationReadAllView(BaseAPIView):
    @extend_schema(tags=["通知"], request=None, responses={200: OpenApiTypes.OBJECT})
    def patch(self, request):
        updated, read_at = service.mark_all_read(request.user)
        return ok({"updatedCount": updated, "readAt": iso(read_at)})
