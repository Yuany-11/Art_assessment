from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView

from common.pagination import StandardPagination
from common.response import success
from common.utils import iso

from . import services
from .presenters import notification_item


class NotificationListView(APIView):
    @extend_schema(
        tags=["通知中心"],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        unread_only = str(request.query_params.get("unreadOnly", "")).lower() in (
            "1",
            "true",
            "yes",
        )
        qs = services.list_for_user(
            request.user,
            unread_only=unread_only,
            ntype=request.query_params.get("type"),
        )
        paginator = StandardPagination()
        paginator.page_size = 20
        page = paginator.paginate_queryset(qs, request, view=self)
        paginator.extra_data = {"unreadCount": services.unread_count(request.user)}
        return paginator.get_paginated_response(
            [notification_item(item) for item in page]
        )


class NotificationReadView(APIView):
    @extend_schema(
        tags=["通知中心"],
        request=None,
        responses={200: OpenApiTypes.OBJECT},
    )
    def patch(self, request, notification_id):
        notification = services.mark_read(request.user, notification_id)
        return success(
            {
                "id": notification.id,
                "read": True,
                "readAt": iso(notification.read_at),
            }
        )


class NotificationReadAllView(APIView):
    @extend_schema(
        tags=["通知中心"],
        request=None,
        responses={200: OpenApiTypes.OBJECT},
    )
    def patch(self, request):
        count, read_at = services.mark_all_read(request.user)
        return success({"updatedCount": count, "readAt": iso(read_at)})
