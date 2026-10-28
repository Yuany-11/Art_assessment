"""多级账号接口序列化。"""
from rest_framework import serializers

from common.enums import AccountStatus, Gender, Role, SchoolType, Subject
from common.serializers import StrictSerializer, validate_cn_phone

from .services.account_data import build_account_item, build_org_create_result, build_student_item


class AccountItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    realName = serializers.CharField()
    role = serializers.CharField()
    roleName = serializers.CharField()
    orgId = serializers.IntegerField(allow_null=True)
    orgName = serializers.CharField(allow_null=True)
    phone = serializers.CharField(allow_null=True)
    email = serializers.CharField(allow_null=True)
    subject = serializers.CharField(allow_null=True)
    title = serializers.CharField(allow_null=True)
    studentNo = serializers.CharField(allow_null=True)
    classId = serializers.IntegerField(allow_null=True)
    className = serializers.CharField(allow_null=True)
    status = serializers.CharField()
    createdAt = serializers.CharField()

    def to_representation(self, instance):
        return build_account_item(instance)


class StudentItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    studentNo = serializers.CharField(allow_null=True)
    realName = serializers.CharField()
    gender = serializers.CharField()
    grade = serializers.IntegerField(allow_null=True)
    classId = serializers.IntegerField(allow_null=True)
    className = serializers.CharField(allow_null=True)
    status = serializers.CharField()
    joinedAt = serializers.CharField()

    def to_representation(self, instance):
        return build_student_item(instance)


class OrgOptionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    code = serializers.CharField()
    level = serializers.CharField()
    parentId = serializers.IntegerField(allow_null=True)
    parentName = serializers.CharField(allow_null=True)
    schoolType = serializers.CharField(allow_null=True)


class OrgOptionListSerializer(serializers.Serializer):
    list = OrgOptionSerializer(many=True)


class OrgCreateResultSerializer(serializers.Serializer):
    orgId = serializers.IntegerField()
    orgName = serializers.CharField()
    adminAccount = AccountItemSerializer()

    def to_representation(self, instance):
        return build_org_create_result(instance["org"], instance["admin"])


class TeacherCreateSerializer(StrictSerializer):
    username = serializers.CharField(max_length=64)
    realName = serializers.CharField(min_length=2, max_length=30)
    phone = serializers.CharField(max_length=32)
    email = serializers.EmailField(required=False, allow_null=True)
    subject = serializers.ChoiceField(choices=Subject.choices)
    title = serializers.CharField(max_length=64, required=False, allow_null=True)
    classIds = serializers.ListField(child=serializers.IntegerField(), required=False)
    initialPassword = serializers.CharField(
        min_length=8, max_length=32, required=False, allow_null=True
    )
    status = serializers.ChoiceField(
        choices=AccountStatus.choices, required=False, default=AccountStatus.ACTIVE
    )

    def validate_phone(self, value):
        return validate_cn_phone(value)


class StudentCreateSerializer(StrictSerializer):
    username = serializers.CharField(max_length=64)
    studentNo = serializers.CharField(max_length=32)
    realName = serializers.CharField(min_length=2, max_length=30)
    gender = serializers.ChoiceField(choices=Gender.choices)
    grade = serializers.IntegerField(min_value=1, max_value=12)
    schoolId = serializers.IntegerField(required=False)
    classId = serializers.IntegerField(required=False, allow_null=True)
    phone = serializers.CharField(max_length=32, required=False, allow_null=True)
    guardianPhone = serializers.CharField(max_length=32, required=False, allow_null=True)
    initialPassword = serializers.CharField(
        min_length=8, max_length=32, required=False, allow_null=True
    )

    def validate_phone(self, value):
        return value if value is None else validate_cn_phone(value)

    def validate_guardianPhone(self, value):
        return value if value is None else validate_cn_phone(value)


class SchoolCreateSerializer(StrictSerializer):
    districtId = serializers.IntegerField(required=False)
    cityId = serializers.IntegerField(required=False)
    schoolCode = serializers.CharField(max_length=64)
    schoolName = serializers.CharField(max_length=128)
    schoolType = serializers.ChoiceField(choices=SchoolType.choices)
    address = serializers.CharField(max_length=255, required=False, allow_null=True)
    adminUsername = serializers.CharField(max_length=64)
    adminRealName = serializers.CharField(min_length=2, max_length=30)
    adminPhone = serializers.CharField(max_length=32)
    initialPassword = serializers.CharField(
        min_length=8, max_length=32, required=False, allow_null=True
    )

    def validate_adminPhone(self, value):
        return validate_cn_phone(value)


class DistrictCreateSerializer(StrictSerializer):
    cityId = serializers.IntegerField(required=False)
    districtCode = serializers.CharField(max_length=64)
    districtName = serializers.CharField(max_length=128)
    adminUsername = serializers.CharField(max_length=64)
    adminRealName = serializers.CharField(min_length=2, max_length=30)
    adminPhone = serializers.CharField(max_length=32)
    initialPassword = serializers.CharField(
        min_length=8, max_length=32, required=False, allow_null=True
    )

    def validate_adminPhone(self, value):
        return validate_cn_phone(value)


class CityCreateSerializer(StrictSerializer):
    cityCode = serializers.CharField(max_length=64)
    cityName = serializers.CharField(max_length=128)
    adminUsername = serializers.CharField(max_length=64)
    adminRealName = serializers.CharField(min_length=2, max_length=30)
    adminPhone = serializers.CharField(max_length=32)
    initialPassword = serializers.CharField(
        min_length=8, max_length=32, required=False, allow_null=True
    )

    def validate_adminPhone(self, value):
        return validate_cn_phone(value)


class AccountUpdateSerializer(StrictSerializer):
    realName = serializers.CharField(min_length=2, max_length=30, required=False)
    phone = serializers.CharField(max_length=32, required=False, allow_null=True)
    email = serializers.EmailField(required=False, allow_null=True)
    subject = serializers.ChoiceField(choices=Subject.choices, required=False, allow_null=True)
    title = serializers.CharField(max_length=64, required=False, allow_null=True)
    classId = serializers.IntegerField(required=False, allow_null=True)
    status = serializers.ChoiceField(choices=AccountStatus.choices, required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("至少提供一个可修改字段")
        return attrs

    @staticmethod
    def _reject_blank(value):
        if value == "":
            raise serializers.ValidationError("不能为空字符串，无值时请传 null")
        return value

    def validate_phone(self, value):
        if value is None:
            return value
        self._reject_blank(value)
        return validate_cn_phone(value)

    def validate_email(self, value):
        return self._reject_blank(value)


class ResetPasswordSerializer(StrictSerializer):
    newPassword = serializers.CharField(
        min_length=8, max_length=32, required=False, allow_null=True, trim_whitespace=False
    )
    forceChange = serializers.BooleanField(required=False, default=True)


class TeacherImportSerializer(StrictSerializer):
    file = serializers.FileField()
    defaultPassword = serializers.CharField(
        min_length=8, max_length=32, required=False, allow_null=True
    )
    overwrite = serializers.BooleanField(required=False, default=False)


class ImportResultSerializer(serializers.Serializer):
    taskId = serializers.CharField()
    status = serializers.CharField()
    total = serializers.IntegerField()
    successCount = serializers.IntegerField()
    failCount = serializers.IntegerField()
    errors = serializers.ListField(child=serializers.DictField())


class ImportTaskStatusSerializer(serializers.Serializer):
    taskId = serializers.CharField()
    status = serializers.CharField()
    total = serializers.IntegerField()
    successCount = serializers.IntegerField()
    failCount = serializers.IntegerField()
    errors = serializers.ListField(child=serializers.DictField())

    def to_representation(self, instance):
        return {
            "taskId": instance.task_id,
            "status": instance.status,
            "total": instance.total,
            "successCount": instance.success_count,
            "failCount": instance.fail_count,
            "errors": instance.errors or [],
        }


class DeleteAccountResultSerializer(serializers.Serializer):
    deleted = serializers.BooleanField()
    accountId = serializers.IntegerField()


class ResetPasswordResultSerializer(serializers.Serializer):
    accountId = serializers.IntegerField()
    temporaryPassword = serializers.CharField()
    forceChange = serializers.BooleanField()
