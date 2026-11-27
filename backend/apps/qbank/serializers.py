"""题库接口序列化。"""
from decimal import Decimal

from rest_framework import serializers

from common.constants import GRADE_MAX, GRADE_MIN
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
    build_learner_question,
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
    content = serializers.CharField(allow_null=True)
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
    difficultyLabel = serializers.CharField(allow_null=True)
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


class LearnerQuestionSerializer(serializers.Serializer):
    def to_representation(self, instance: Question):
        return build_learner_question(instance)


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
    grade = serializers.IntegerField(min_value=GRADE_MIN, max_value=GRADE_MAX)
    description = serializers.CharField(max_length=500, required=False, allow_null=True, allow_blank=True)
    sortOrder = serializers.IntegerField(required=False, default=0)
    status = serializers.ChoiceField(choices=CourseStatus.choices, required=False)


class CourseUpdateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=128, required=False)
    subject = serializers.ChoiceField(choices=Subject.choices, required=False)
    grade = serializers.IntegerField(
        min_value=GRADE_MIN, max_value=GRADE_MAX, required=False
    )
    description = serializers.CharField(max_length=500, required=False, allow_null=True, allow_blank=True)
    sortOrder = serializers.IntegerField(required=False)
    status = serializers.ChoiceField(choices=CourseStatus.choices, required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("至少提供一个可修改字段")
        return attrs


class ChapterCreateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=128)
    description = serializers.CharField(max_length=500, required=False, allow_null=True, allow_blank=True)
    content = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    sortOrder = serializers.IntegerField(required=False, default=0)


class ChapterUpdateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=128, required=False)
    description = serializers.CharField(max_length=500, required=False, allow_null=True, allow_blank=True)
    content = serializers.CharField(required=False, allow_null=True, allow_blank=True)
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
    # 年级由课程决定；保留字段兼容旧前端，不再作为题目分类依据。
    grade = serializers.IntegerField(
        min_value=GRADE_MIN, max_value=GRADE_MAX, required=False
    )
    courseId = serializers.IntegerField()
    chapterId = serializers.IntegerField(required=False, allow_null=True)
    type = serializers.ChoiceField(choices=QuestionType.choices)
    difficulty = serializers.IntegerField(min_value=1, max_value=4)
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


class QgenGenerateSerializer(StrictSerializer):
    unitId = serializers.CharField(max_length=32)
    knowledgePoint = serializers.CharField(max_length=128)
    type = serializers.ChoiceField(choices=["single_choice", "true_false"])
    difficulty = serializers.IntegerField(min_value=1, max_value=3)


class QuestionUpdateSerializer(StrictSerializer):
    subject = serializers.ChoiceField(choices=Subject.choices, required=False)
    grade = serializers.IntegerField(
        min_value=GRADE_MIN, max_value=GRADE_MAX, required=False
    )
    courseId = serializers.IntegerField(required=False)
    chapterId = serializers.IntegerField(required=False, allow_null=True)
    type = serializers.ChoiceField(choices=QuestionType.choices, required=False)
    difficulty = serializers.IntegerField(min_value=1, max_value=4, required=False)
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
