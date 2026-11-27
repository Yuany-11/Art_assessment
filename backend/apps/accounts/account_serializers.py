"""多级账号接口序列化。"""
from rest_framework import serializers

from common.constants import GRADE_MAX, GRADE_MIN
from common.enums import AccountStatus, Gender, Role, SchoolType, Subject
from common.serializers import StrictSerializer, StrongPasswordField

from .services.account_data import build_account_item, build_org_create_result, build_student_item
from .validators import (
    STUDENT_NO_MAX_LENGTH,
    STUDENT_NO_MIN_LENGTH,
    STUDENT_NO_REQUIREMENT,
    validate_mobile,
    validate_student_no,
    validate_username,
)


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
    grade = serializers.IntegerField(allow_null=True)
    classId = serializers.IntegerField(allow_null=True)
    className = serializers.CharField(allow_null=True)
    teachingClasses = serializers.ListField(child=serializers.DictField(), required=False)
    status = serializers.CharField()
    hasTemporaryPassword = serializers.BooleanField(required=False)
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
    initialPassword = serializers.CharField()

    def to_representation(self, instance):
        return build_org_create_result(
            instance["org"], instance["admin"], instance.get("initialPassword")
        )


class TeacherCreateSerializer(StrictSerializer):
    username = serializers.CharField(min_length=4, max_length=32)
    realName = serializers.CharField(min_length=2, max_length=30)
    phone = serializers.CharField(max_length=32)
    email = serializers.EmailField(required=False, allow_null=True)
    subject = serializers.ChoiceField(choices=Subject.choices)
    title = serializers.CharField(max_length=64, required=False, allow_null=True)
    classIds = serializers.ListField(child=serializers.IntegerField(), required=False)
    initialPassword = StrongPasswordField(
        required=False, allow_null=True, allow_blank=True
    )
    status = serializers.ChoiceField(
        choices=AccountStatus.choices, required=False, default=AccountStatus.ACTIVE
    )

    def validate_username(self, value):
        return validate_username(value)

    def validate_phone(self, value):
        return validate_mobile(value)


class StudentCreateSerializer(StrictSerializer):
    username = serializers.CharField(min_length=4, max_length=32)
    studentNo = serializers.CharField(
        min_length=STUDENT_NO_MIN_LENGTH,
        max_length=STUDENT_NO_MAX_LENGTH,
        error_messages={
            "min_length": STUDENT_NO_REQUIREMENT,
            "max_length": STUDENT_NO_REQUIREMENT,
        },
    )
    realName = serializers.CharField(min_length=2, max_length=30)
    gender = serializers.ChoiceField(choices=Gender.choices)
    grade = serializers.IntegerField(min_value=GRADE_MIN, max_value=GRADE_MAX)
    schoolId = serializers.IntegerField(required=False)
    classId = serializers.IntegerField(required=False, allow_null=True)
    phone = serializers.CharField(max_length=32, required=False, allow_null=True)
    guardianPhone = serializers.CharField(max_length=32, required=False, allow_null=True)
    initialPassword = StrongPasswordField(
        required=False, allow_null=True, allow_blank=True
    )

    def validate_username(self, value):
        return validate_username(value)

    def validate_studentNo(self, value):
        return validate_student_no(value)

    def validate_phone(self, value):
        return validate_mobile(value, allow_blank=True)

    def validate_guardianPhone(self, value):
        return validate_mobile(value, label="监护人手机号", allow_blank=True)


class SchoolCreateSerializer(StrictSerializer):
    districtId = serializers.IntegerField(required=False)
    cityId = serializers.IntegerField(required=False)
    schoolCode = serializers.CharField(max_length=64)
    schoolName = serializers.CharField(max_length=128)
    schoolType = serializers.ChoiceField(choices=SchoolType.choices)
    address = serializers.CharField(max_length=255, required=False, allow_null=True)
    adminUsername = serializers.CharField(
        min_length=4, max_length=32, validators=[validate_username]
    )
    adminRealName = serializers.CharField(min_length=2, max_length=30)
    adminPhone = serializers.CharField(max_length=32)
    initialPassword = StrongPasswordField(
        required=False, allow_null=True, allow_blank=True
    )

    def validate_adminPhone(self, value):
        return validate_mobile(value, label="管理员手机号")


class DistrictCreateSerializer(StrictSerializer):
    cityId = serializers.IntegerField(required=False)
    districtCode = serializers.CharField(max_length=64)
    districtName = serializers.CharField(max_length=128)
    adminUsername = serializers.CharField(
        min_length=4, max_length=32, validators=[validate_username]
    )
    adminRealName = serializers.CharField(min_length=2, max_length=30)
    adminPhone = serializers.CharField(max_length=32)
    initialPassword = StrongPasswordField(
        required=False, allow_null=True, allow_blank=True
    )

    def validate_adminPhone(self, value):
        return validate_mobile(value, label="管理员手机号")


class CityCreateSerializer(StrictSerializer):
    cityCode = serializers.CharField(max_length=64)
    cityName = serializers.CharField(max_length=128)
    adminUsername = serializers.CharField(
        min_length=4, max_length=32, validators=[validate_username]
    )
    adminRealName = serializers.CharField(min_length=2, max_length=30)
    adminPhone = serializers.CharField(max_length=32)
    initialPassword = StrongPasswordField(
        required=False, allow_null=True, allow_blank=True
    )


class AccountUpdateSerializer(StrictSerializer):
    realName = serializers.CharField(min_length=2, max_length=30, required=False)
    phone = serializers.CharField(max_length=32, required=False, allow_null=True)
    email = serializers.EmailField(required=False, allow_null=True)
    subject = serializers.ChoiceField(choices=Subject.choices, required=False, allow_null=True)
    title = serializers.CharField(max_length=64, required=False, allow_null=True)
    # 编辑时允许原样提交历史学籍号；是否合法由服务层按“是否变更”判断。
    studentNo = serializers.CharField(required=False, allow_null=True)
    grade = serializers.IntegerField(
        min_value=GRADE_MIN, max_value=GRADE_MAX, required=False, allow_null=True
    )
    classId = serializers.IntegerField(required=False, allow_null=True)
    classIds = serializers.ListField(child=serializers.IntegerField(), required=False)
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
        return validate_mobile(self._reject_blank(value))

    def validate_email(self, value):
        return self._reject_blank(value)


class ResetPasswordSerializer(StrictSerializer):
    newPassword = StrongPasswordField(required=False, allow_null=True)
    forceChange = serializers.BooleanField(required=False, default=True)


class TeacherImportSerializer(StrictSerializer):
    file = serializers.FileField()
    defaultPassword = StrongPasswordField(required=False, allow_null=True)
    overwrite = serializers.BooleanField(required=False, default=False)


class ImportResultSerializer(serializers.Serializer):
    taskId = serializers.CharField()
    status = serializers.CharField()
    total = serializers.IntegerField()
    successCount = serializers.IntegerField()
    failCount = serializers.IntegerField()
    errors = serializers.ListField(child=serializers.DictField())
    credentials = serializers.ListField(child=serializers.DictField(), required=False)


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


class TemporaryPasswordResultSerializer(serializers.Serializer):
    accountId = serializers.IntegerField()
    temporaryPassword = serializers.CharField()
    expiresIn = serializers.IntegerField()
