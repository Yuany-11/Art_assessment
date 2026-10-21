"""认证与账号资料序列化。"""
import re

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from common.enums import Gender, Role
from common.serializers import StrictSerializer

from .services.profile import build_user_profile


class LoginSerializer(StrictSerializer):
    username = serializers.CharField(max_length=64)
    password = serializers.CharField(max_length=128, trim_whitespace=False)
    role = serializers.ChoiceField(choices=Role.choices, required=False)

    def validate_username(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("登录账号不能为空")
        return value


class RefreshSerializer(StrictSerializer):
    refreshToken = serializers.CharField(max_length=2048)


class LogoutSerializer(StrictSerializer):
    refreshToken = serializers.CharField(max_length=2048, required=False, allow_null=True)


class ProfileUpdateSerializer(StrictSerializer):
    realName = serializers.CharField(min_length=2, max_length=30, required=False)
    gender = serializers.ChoiceField(choices=Gender.choices, required=False)
    phone = serializers.CharField(max_length=32, required=False, allow_null=True)
    email = serializers.EmailField(required=False, allow_null=True)
    avatarUrl = serializers.URLField(max_length=500, required=False, allow_null=True)

    @staticmethod
    def _reject_blank(value):
        if value == "":
            raise serializers.ValidationError("不能为空字符串，无值时请传 null")
        return value

    def validate_phone(self, value):
        return self._reject_blank(value)

    def validate_avatarUrl(self, value):
        return self._reject_blank(value)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("至少提供一个可修改字段")
        return attrs


class PasswordChangeSerializer(StrictSerializer):
    oldPassword = serializers.CharField(max_length=128, trim_whitespace=False)
    newPassword = serializers.CharField(min_length=8, max_length=32, trim_whitespace=False)

    def validate_newPassword(self, value: str) -> str:
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise serializers.ValidationError("新密码需至少包含字母和数字")
        return value


class UserProfileSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    realName = serializers.CharField()
    role = serializers.CharField()
    roleName = serializers.CharField()
    permissions = serializers.ListField(child=serializers.CharField())
    avatarUrl = serializers.CharField(allow_null=True)
    gender = serializers.CharField()
    phone = serializers.CharField(allow_null=True)
    email = serializers.CharField(allow_null=True)
    studentNo = serializers.CharField(allow_null=True)
    teacherNo = serializers.CharField(allow_null=True)
    schoolId = serializers.IntegerField(allow_null=True)
    schoolName = serializers.CharField(allow_null=True)
    districtId = serializers.IntegerField(allow_null=True)
    districtName = serializers.CharField(allow_null=True)
    cityId = serializers.IntegerField(allow_null=True)
    cityName = serializers.CharField(allow_null=True)
    grade = serializers.IntegerField(allow_null=True)
    classId = serializers.IntegerField(allow_null=True)
    className = serializers.CharField(allow_null=True)
    status = serializers.CharField()
    lastLoginAt = serializers.CharField(allow_null=True)
    createdAt = serializers.CharField()

    def to_representation(self, instance):
        return build_user_profile(instance)


class TokenPairSerializer(serializers.Serializer):
    token = serializers.CharField()
    refreshToken = serializers.CharField()
    tokenType = serializers.CharField()
    expiresIn = serializers.IntegerField()
    refreshExpiresIn = serializers.IntegerField()


class LoginResponseSerializer(TokenPairSerializer):
    user = UserProfileSerializer()


class LogoutResultSerializer(serializers.Serializer):
    loggedOut = serializers.BooleanField()


class PasswordChangeResultSerializer(serializers.Serializer):
    changed = serializers.BooleanField()
    reloginRequired = serializers.BooleanField()


class MenuItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    parentId = serializers.CharField(allow_null=True)
    name = serializers.CharField()
    path = serializers.CharField()
    icon = serializers.CharField(allow_null=True)
    sortOrder = serializers.IntegerField()
    permission = serializers.CharField(allow_null=True)
    children = serializers.SerializerMethodField()

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_children(self, obj):
        return MenuItemSerializer(obj.get("children", []), many=True).data
