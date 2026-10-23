"""题库接口序列化。"""
from decimal import Decimal

from rest_framework import serializers

from common.enums import (
    CourseStatus,
    QuestionStatus,
    QuestionType,
    ResourceType,
    ScoringMode,
    Subject,
)
from common.serializers import StrictSerializer

from .models import Chapter, Course, OperationLog, Question
from .services import (
    build_chapter,
    build_course,
    build_log,
    build_question_detail,
    build_question_item,
    build_resource,
)


class CourseItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    subject = serializers.CharField()
    grade = serializers.IntegerField()
    description = serializers.CharField(allow_null=True)
    chapterCount = serializers.IntegerField()
    sortOrder = serializers.IntegerField()
    status = serializers.CharField()
    createdAt = serializers.CharField()
    updatedAt = serializers.CharField()

    def to_representation(self, instance: Course):
        return build_course(instance)


class ChapterItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    courseId = serializers.IntegerField()
    courseName = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_null=True)
    questionCount = serializers.IntegerField()
    sortOrder = serializers.IntegerField()
    createdAt = serializers.CharField()
    updatedAt = serializers.CharField()

    def to_representation(self, instance: Chapter):
        return build_chapter(instance)


class QuestionItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    subject = serializers.CharField()
    grade = serializers.IntegerField()
    courseId = serializers.IntegerField()
    courseName = serializers.CharField()
    chapterId = serializers.IntegerField(allow_null=True)
    chapterName = serializers.CharField(allow_null=True)
    type = serializers.CharField()
    difficulty = serializers.IntegerField()
    stem = serializers.CharField()
    score = serializers.FloatField()
    status = serializers.CharField()
    creatorId = serializers.IntegerField()
    creatorName = serializers.CharField()
    reviewerId = serializers.IntegerField(allow_null=True)
    reviewerName = serializers.CharField(allow_null=True)
    reviewComment = serializers.CharField(allow_null=True)
    resourceCount = serializers.IntegerField()
    createdAt = serializers.CharField()
    updatedAt = serializers.CharField()

    def to_representation(self, instance: Question):
        return build_question_item(instance)


class QuestionDetailSerializer(QuestionItemSerializer):
    options = serializers.ListField(child=serializers.DictField())
    answer = serializers.DictField()
    analysis = serializers.CharField(allow_null=True)
    scoringMode = serializers.CharField()
    resources = serializers.ListField(child=serializers.DictField())

    def to_representation(self, instance: Question):
        return build_question_detail(instance)


class QuestionResourceItemSerializer(serializers.Serializer):
    resourceId = serializers.IntegerField()
    fileId = serializers.IntegerField()
    type = serializers.CharField()
    url = serializers.CharField()
    name = serializers.CharField()
    mimeType = serializers.CharField()
    size = serializers.IntegerField()
    createdAt = serializers.CharField()

    def to_representation(self, instance):
        return build_resource(instance)


class OperationLogItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    operatorId = serializers.IntegerField(allow_null=True)
    operatorName = serializers.CharField()
    role = serializers.CharField()
    action = serializers.CharField()
    resourceType = serializers.CharField()
    resourceId = serializers.IntegerField(allow_null=True)
    description = serializers.CharField()
    ip = serializers.CharField(allow_null=True)
    userAgent = serializers.CharField(allow_null=True)
    result = serializers.CharField()
    createdAt = serializers.CharField()

    def to_representation(self, instance: OperationLog):
        return build_log(instance)


class CourseCreateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=128)
    subject = serializers.ChoiceField(choices=Subject.choices)
    grade = serializers.IntegerField(min_value=1, max_value=12)
    description = serializers.CharField(max_length=500, required=False, allow_null=True)
    sortOrder = serializers.IntegerField(required=False, default=0)
    status = serializers.ChoiceField(choices=CourseStatus.choices, required=False)


class CourseUpdateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=128, required=False)
    subject = serializers.ChoiceField(choices=Subject.choices, required=False)
    grade = serializers.IntegerField(min_value=1, max_value=12, required=False)
    description = serializers.CharField(max_length=500, required=False, allow_null=True)
    sortOrder = serializers.IntegerField(required=False)
    status = serializers.ChoiceField(choices=CourseStatus.choices, required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("至少提供一个可修改字段")
        return attrs


class ChapterCreateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=128)
    description = serializers.CharField(max_length=500, required=False, allow_null=True)
    sortOrder = serializers.IntegerField(required=False, default=0)


class ChapterUpdateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=128, required=False)
    description = serializers.CharField(max_length=500, required=False, allow_null=True)
    sortOrder = serializers.IntegerField(required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("至少提供一个可修改字段")
        return attrs


class QuestionOptionInputSerializer(StrictSerializer):
    key = serializers.CharField(max_length=8)
    text = serializers.CharField(max_length=1000)
    mediaUrl = serializers.CharField(max_length=500, required=False, allow_null=True)


class QuestionCreateSerializer(StrictSerializer):
    subject = serializers.ChoiceField(choices=Subject.choices)
    grade = serializers.IntegerField(min_value=1, max_value=12)
    courseId = serializers.IntegerField()
    chapterId = serializers.IntegerField(required=False, allow_null=True)
    type = serializers.ChoiceField(choices=QuestionType.choices)
    difficulty = serializers.IntegerField(min_value=1, max_value=5)
    stem = serializers.CharField(min_length=1, max_length=5000)
    score = serializers.DecimalField(
        max_digits=6, decimal_places=2, min_value=Decimal("0.5"), max_value=Decimal("100")
    )
    options = QuestionOptionInputSerializer(many=True, required=False)
    answer = serializers.JSONField()
    analysis = serializers.CharField(max_length=5000, required=False, allow_null=True)
    scoringMode = serializers.ChoiceField(choices=ScoringMode.choices)
    resourceFileIds = serializers.ListField(child=serializers.IntegerField(), required=False)
    publishNow = serializers.BooleanField(required=False, default=False)


class QuestionUpdateSerializer(StrictSerializer):
    subject = serializers.ChoiceField(choices=Subject.choices, required=False)
    grade = serializers.IntegerField(min_value=1, max_value=12, required=False)
    courseId = serializers.IntegerField(required=False)
    chapterId = serializers.IntegerField(required=False, allow_null=True)
    type = serializers.ChoiceField(choices=QuestionType.choices, required=False)
    difficulty = serializers.IntegerField(min_value=1, max_value=5, required=False)
    stem = serializers.CharField(min_length=1, max_length=5000, required=False)
    score = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        min_value=Decimal("0.5"),
        max_value=Decimal("100"),
        required=False,
    )
    options = QuestionOptionInputSerializer(many=True, required=False)
    answer = serializers.JSONField(required=False)
    analysis = serializers.CharField(max_length=5000, required=False, allow_null=True)
    scoringMode = serializers.ChoiceField(choices=ScoringMode.choices, required=False)
    resourceFileIds = serializers.ListField(child=serializers.IntegerField(), required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("至少提供一个可修改字段")
        return attrs


class SubmitReviewSerializer(StrictSerializer):
    remark = serializers.CharField(max_length=500, required=False, allow_blank=True)


class QuestionReviewSerializer(StrictSerializer):
    action = serializers.ChoiceField(choices=[("approve", "通过"), ("reject", "驳回")])
    comment = serializers.CharField(max_length=500, required=False, allow_blank=True)


class ResourceUploadSerializer(StrictSerializer):
    files = serializers.ListField(child=serializers.FileField(), allow_empty=False)
    type = serializers.ChoiceField(choices=ResourceType.choices)


class DeleteQuestionResultSerializer(serializers.Serializer):
    deleted = serializers.BooleanField()
    questionId = serializers.IntegerField()


class DeleteCourseResultSerializer(serializers.Serializer):
    deleted = serializers.BooleanField()
    courseId = serializers.IntegerField()


class DeleteChapterResultSerializer(serializers.Serializer):
    deleted = serializers.BooleanField()
    chapterId = serializers.IntegerField()


class DeleteResourceResultSerializer(serializers.Serializer):
    deleted = serializers.BooleanField()
    questionId = serializers.IntegerField()
    resourceId = serializers.IntegerField()


class QuestionStatusFilterSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=QuestionStatus.choices, required=False)
