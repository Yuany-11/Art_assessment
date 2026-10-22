"""班级相关序列化。"""
from rest_framework import serializers

from common.enums import ClassStatus, Subject
from common.serializers import StrictSerializer

from .services import build_class_detail, build_class_item, build_join_request


class ClassItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    classCode = serializers.CharField()
    name = serializers.CharField()
    grade = serializers.IntegerField()
    schoolId = serializers.IntegerField()
    schoolName = serializers.CharField()
    headTeacherId = serializers.IntegerField(allow_null=True)
    headTeacherName = serializers.CharField(allow_null=True)
    studentCount = serializers.IntegerField()
    status = serializers.CharField()
    createdAt = serializers.CharField()

    def to_representation(self, instance):
        return build_class_item(instance)


class ClassDetailSerializer(ClassItemSerializer):
    description = serializers.CharField(allow_null=True)
    subjectTeachers = serializers.ListField(child=serializers.DictField())
    createdBy = serializers.IntegerField(allow_null=True)
    updatedAt = serializers.CharField()

    def to_representation(self, instance):
        return build_class_detail(instance)


class JoinRequestItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    classId = serializers.IntegerField()
    className = serializers.CharField()
    requesterId = serializers.IntegerField()
    requesterName = serializers.CharField()
    requesterRole = serializers.CharField()
    type = serializers.CharField()
    targetClassId = serializers.IntegerField(allow_null=True)
    targetClassName = serializers.CharField(allow_null=True)
    status = serializers.CharField()
    reason = serializers.CharField(allow_null=True)
    reviewerId = serializers.IntegerField(allow_null=True)
    reviewerName = serializers.CharField(allow_null=True)
    reviewComment = serializers.CharField(allow_null=True)
    reviewedAt = serializers.CharField(allow_null=True)
    createdAt = serializers.CharField()

    def to_representation(self, instance):
        return build_join_request(instance)


class ClassCreateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=128)
    grade = serializers.IntegerField(min_value=1, max_value=12)
    classCode = serializers.CharField(max_length=32, required=False, allow_blank=True)
    headTeacherId = serializers.IntegerField(required=False, allow_null=True)
    description = serializers.CharField(max_length=500, required=False, allow_null=True)


class ClassUpdateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=128, required=False)
    grade = serializers.IntegerField(min_value=1, max_value=12, required=False)
    headTeacherId = serializers.IntegerField(required=False, allow_null=True)
    description = serializers.CharField(max_length=500, required=False, allow_null=True)
    status = serializers.ChoiceField(choices=ClassStatus.choices, required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("至少提供一个可修改字段")
        return attrs


class JoinRequestCreateSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True)
    subject = serializers.ChoiceField(choices=Subject.choices, required=False)


class LeaveRequestSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True)


class ChangeRequestSerializer(StrictSerializer):
    targetClassId = serializers.IntegerField()
    reason = serializers.CharField(max_length=200)


class ReviewRequestSerializer(StrictSerializer):
    action = serializers.ChoiceField(choices=[("approve", "通过"), ("reject", "驳回")])
    comment = serializers.CharField(max_length=200, required=False, allow_blank=True)


class ClassStudentImportSerializer(StrictSerializer):
    file = serializers.FileField()
    mode = serializers.ChoiceField(
        choices=[("append", "仅新增"), ("upsert", "存在则更新")],
        required=False,
        default="append",
    )


class ClassImportResultSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    successCount = serializers.IntegerField()
    failCount = serializers.IntegerField()
    errors = serializers.ListField(child=serializers.DictField())


class DeleteClassResultSerializer(serializers.Serializer):
    deleted = serializers.BooleanField()
    classId = serializers.IntegerField()


class RemoveStudentResultSerializer(serializers.Serializer):
    removed = serializers.BooleanField()
    classId = serializers.IntegerField()
    studentId = serializers.IntegerField()
