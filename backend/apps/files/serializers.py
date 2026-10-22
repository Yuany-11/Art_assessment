"""文件接口序列化。"""
from rest_framework import serializers

from common.enums import FileCategory
from common.serializers import StrictSerializer

from .models import FileObject


class FileUploadSerializer(StrictSerializer):
    file = serializers.FileField()
    category = serializers.ChoiceField(choices=FileCategory.choices)
    bizId = serializers.IntegerField(required=False, allow_null=True)


class FileObjectSerializer(serializers.Serializer):
    fileId = serializers.IntegerField()
    url = serializers.CharField()
    name = serializers.CharField()
    mimeType = serializers.CharField()
    size = serializers.IntegerField()
    category = serializers.CharField()
    createdAt = serializers.CharField()

    def to_representation(self, instance: FileObject):
        from apps.accounts.services.profile import format_datetime

        return {
            "fileId": instance.id,
            "url": instance.url,
            "name": instance.original_name,
            "mimeType": instance.mime_type,
            "size": instance.size,
            "category": instance.category,
            "createdAt": format_datetime(instance.created_at),
        }


class FileDeleteResultSerializer(serializers.Serializer):
    deleted = serializers.BooleanField()
    fileId = serializers.IntegerField()
