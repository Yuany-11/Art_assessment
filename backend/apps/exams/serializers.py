"""请求校验 Serializer。响应统一在 presenters.py 中构造，保证字段名与文档一致。"""
from rest_framework import serializers

from common.enums import (
    Level,
    MissingComponentPolicy,
    PaperStatus,
    PaperType,
    QuestionType,
    ScoreAggregation,
    ScopeType,
    ScoringMode,
    ShowAnswerMode,
    Subject,
)


class QuestionConfigSerializer(serializers.Serializer):
    questionId = serializers.IntegerField(min_value=1)
    order = serializers.IntegerField(min_value=1)
    sectionName = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    score = serializers.FloatField(min_value=0.01)


class PaperManualCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=128)
    subject = serializers.ChoiceField(choices=Subject.choices)
    paperType = serializers.ChoiceField(choices=PaperType.choices)
    grade = serializers.IntegerField(min_value=1, max_value=12)
    scopeType = serializers.ChoiceField(choices=ScopeType.choices)
    scopeId = serializers.IntegerField(min_value=1)
    duration = serializers.IntegerField(min_value=1, max_value=300)
    instructions = serializers.CharField(max_length=2000, required=False, allow_null=True)
    status = serializers.ChoiceField(
        choices=[PaperStatus.DRAFT, PaperStatus.READY], required=False, default=PaperStatus.DRAFT
    )
    questions = QuestionConfigSerializer(many=True, allow_empty=False)

    def validate_questions(self, value):
        orders = [item["order"] for item in value]
        if len(orders) != len(set(orders)):
            raise serializers.ValidationError("题目顺序 order 不可重复")
        ids = [item["questionId"] for item in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("同一试卷不可重复添加同一道试题")
        return value


class AutoRuleSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=QuestionType.choices)
    difficulty = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)
    count = serializers.IntegerField(min_value=1, max_value=100)
    scorePerQuestion = serializers.FloatField(min_value=0.01)


class PaperAutoCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=128)
    subject = serializers.ChoiceField(choices=Subject.choices)
    paperType = serializers.ChoiceField(choices=PaperType.choices)
    grade = serializers.IntegerField(min_value=1, max_value=12)
    scopeType = serializers.ChoiceField(choices=ScopeType.choices)
    scopeId = serializers.IntegerField(min_value=1)
    duration = serializers.IntegerField(min_value=1, max_value=300)
    courseIds = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, default=list
    )
    chapterIds = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, default=list
    )
    rules = AutoRuleSerializer(many=True, allow_empty=False)
    status = serializers.ChoiceField(
        choices=[PaperStatus.DRAFT, PaperStatus.READY], required=False, default=PaperStatus.DRAFT
    )
    instructions = serializers.CharField(max_length=2000, required=False, allow_null=True)


class PaperUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=128, required=False)
    duration = serializers.IntegerField(min_value=1, max_value=300, required=False)
    instructions = serializers.CharField(max_length=2000, required=False, allow_null=True)
    questions = QuestionConfigSerializer(many=True, required=False, allow_empty=False)
    status = serializers.ChoiceField(
        choices=[PaperStatus.DRAFT, PaperStatus.READY], required=False
    )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("至少需要提交一个可修改字段")
        if "questions" in attrs:
            ids = [q["questionId"] for q in attrs["questions"]]
            orders = [q["order"] for q in attrs["questions"]]
            if len(ids) != len(set(ids)):
                raise serializers.ValidationError({"questions": "同一试卷不可重复添加同一道试题"})
            if len(orders) != len(set(orders)):
                raise serializers.ValidationError({"questions": "题目顺序 order 不可重复"})
        return attrs


class PaperDraftSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=128, required=False)
    duration = serializers.IntegerField(min_value=1, max_value=300, required=False)
    instructions = serializers.CharField(max_length=2000, required=False, allow_null=True)
    questions = QuestionConfigSerializer(many=True, required=False, allow_empty=True)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("至少需要提交一个字段")
        return attrs


class PracticeRandomSerializer(serializers.Serializer):
    subject = serializers.ChoiceField(choices=Subject.choices)
    grade = serializers.IntegerField(min_value=1, max_value=12, required=False)
    courseId = serializers.IntegerField(min_value=1, required=False)
    chapterId = serializers.IntegerField(min_value=1, required=False)
    questionCount = serializers.IntegerField(min_value=1, max_value=30, required=False, default=10)
    difficulty = serializers.IntegerField(min_value=1, max_value=5, required=False)
    questionTypes = serializers.ListField(
        child=serializers.ChoiceField(choices=QuestionType.choices),
        required=False, default=list,
    )


class AssessmentCreateSerializer(serializers.Serializer):
    paperId = serializers.IntegerField(min_value=1)
    title = serializers.CharField(max_length=128)
    targetType = serializers.ChoiceField(choices=ScopeType.choices)
    targetIds = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=False
    )
    targetGrades = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=12),
        required=False, default=list,
    )
    startTime = serializers.DateTimeField()
    endTime = serializers.DateTimeField()
    attemptLimit = serializers.IntegerField(min_value=1, max_value=20, required=False, default=1)
    shuffleQuestions = serializers.BooleanField(required=False, default=False)
    shuffleOptions = serializers.BooleanField(required=False, default=False)
    showAnswerMode = serializers.ChoiceField(
        choices=ShowAnswerMode.choices, required=False, default=ShowAnswerMode.AFTER_END
    )
    allowLateSubmit = serializers.BooleanField(required=False, default=False)
    instructions = serializers.CharField(max_length=2000, required=False, allow_null=True)

    def validate(self, attrs):
        if attrs["endTime"] <= attrs["startTime"]:
            raise serializers.ValidationError({"endTime": "结束时间必须晚于开始时间"})
        if len(attrs["targetIds"]) != len(set(attrs["targetIds"])):
            raise serializers.ValidationError({"targetIds": "发布目标不可重复"})
        return attrs


class WithdrawSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class AttemptStartSerializer(serializers.Serializer):
    deviceType = serializers.ChoiceField(
        choices=["web", "mobile", "tablet"], required=False, allow_blank=True
    )


class AnswerItemSerializer(serializers.Serializer):
    questionId = serializers.IntegerField(min_value=1)
    answer = serializers.JSONField()
    clientUpdatedAt = serializers.DateTimeField(required=False, allow_null=True)


class SaveAnswersSerializer(serializers.Serializer):
    answers = AnswerItemSerializer(many=True, allow_empty=False)
    clientUpdatedAt = serializers.DateTimeField(required=False, allow_null=True)


class SubmitSerializer(serializers.Serializer):
    finalAnswers = AnswerItemSerializer(many=True, required=False, allow_empty=True)
    submitType = serializers.ChoiceField(choices=["manual"], required=False, default="manual")


class ManualScoreItemSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=64)
    score = serializers.FloatField(min_value=0)
    maxScore = serializers.FloatField(min_value=0.01)

    def validate(self, attrs):
        if attrs["score"] > attrs["maxScore"]:
            raise serializers.ValidationError("分项得分不能超过满分")
        return attrs


class ManualScoreSerializer(serializers.Serializer):
    studentId = serializers.IntegerField(min_value=1)
    assessmentId = serializers.IntegerField(min_value=1)
    subject = serializers.ChoiceField(choices=Subject.choices)
    scoreItems = ManualScoreItemSerializer(many=True, allow_empty=False)
    totalScore = serializers.FloatField(min_value=0, required=False, allow_null=True)
    reason = serializers.CharField(max_length=255)
    evidenceFileIds = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, default=list
    )
    overwrite = serializers.BooleanField(required=False, default=False)


class RegradeSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)
    aiReevaluate = serializers.BooleanField(required=False, default=False)


class GradingItemSerializer(serializers.Serializer):
    questionId = serializers.IntegerField(min_value=1)
    score = serializers.FloatField(min_value=0)
    comment = serializers.CharField(max_length=500, required=False, allow_null=True)


class GradingSubmitSerializer(serializers.Serializer):
    items = GradingItemSerializer(many=True, allow_empty=False)
    finalize = serializers.BooleanField(required=False, default=False)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)
    version = serializers.IntegerField(min_value=0, required=False, allow_null=True)

    def validate_items(self, value):
        ids = [item["questionId"] for item in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("同一题目不可重复评分")
        return value


class CertificateGenerateSerializer(serializers.Serializer):
    assessmentId = serializers.IntegerField(min_value=1)
    subject = serializers.ChoiceField(choices=Subject.choices)
    studentIds = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, default=list
    )
    templateId = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    forceRegenerate = serializers.BooleanField(required=False, default=False)


class ScoreImportMetaSerializer(serializers.Serializer):
    assessmentId = serializers.IntegerField(min_value=1)
    subject = serializers.ChoiceField(choices=Subject.choices)
    overwrite = serializers.BooleanField(required=False, default=False)


class ScoreImportUploadSerializer(ScoreImportMetaSerializer):
    """仅供 OpenAPI 文档展示上传字段，实际校验使用 Meta 序列化器。"""

    file = serializers.FileField(required=False, help_text="CSV/XLSX 文件，最大 10MB")


class TotalScoreRuleBaseSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=128, required=False)
    term = serializers.CharField(max_length=32, required=False, allow_blank=True)
    startDate = serializers.DateField(required=False, allow_null=True)
    endDate = serializers.DateField(required=False, allow_null=True)
    usualWeight = serializers.FloatField(min_value=0, max_value=1, required=False)
    formalWeight = serializers.FloatField(min_value=0, max_value=1, required=False)
    certificateWeight = serializers.FloatField(min_value=0, max_value=1, required=False)
    usualAggregation = serializers.ChoiceField(
        choices=ScoreAggregation.choices, required=False
    )
    formalAggregation = serializers.ChoiceField(
        choices=ScoreAggregation.choices, required=False
    )
    certificateAggregation = serializers.ChoiceField(
        choices=ScoreAggregation.choices, required=False
    )
    certificateLevelScores = serializers.DictField(required=False)
    missingPolicy = serializers.ChoiceField(
        choices=MissingComponentPolicy.choices, required=False
    )
    excellentLine = serializers.FloatField(min_value=0, max_value=100, required=False)
    goodLine = serializers.FloatField(min_value=0, max_value=100, required=False)
    passLine = serializers.FloatField(min_value=0, max_value=100, required=False)
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True)

    def validate_certificateLevelScores(self, value):
        for key, score in value.items():
            if key not in dict(Level.choices):
                raise serializers.ValidationError(f"未知证书等级：{key}")
            if not isinstance(score, (int, float)) or isinstance(score, bool):
                raise serializers.ValidationError(f"证书等级 {key} 的分数必须为数字")
            if not 0 <= float(score) <= 100:
                raise serializers.ValidationError(f"证书等级 {key} 的分数必须在 0-100 之间")
        return value


class TotalScoreRuleCreateSerializer(TotalScoreRuleBaseSerializer):
    name = serializers.CharField(max_length=128)
    subject = serializers.ChoiceField(choices=Subject.choices)
    classId = serializers.IntegerField(min_value=1)


class TotalScoreRuleUpdateSerializer(TotalScoreRuleBaseSerializer):
    pass


class RuleEvaluateSerializer(serializers.Serializer):
    subject = serializers.ChoiceField(choices=Subject.choices)
    category = serializers.CharField(max_length=32)
    level = serializers.IntegerField(min_value=1, max_value=10, required=False, allow_null=True)
    maxScore = serializers.FloatField(min_value=0.01, required=False, default=100)
    metrics = serializers.DictField(child=serializers.JSONField(), allow_empty=False)
    confidence = serializers.FloatField(min_value=0, max_value=1, required=False, allow_null=True)
    evidence = serializers.DictField(required=False, allow_empty=True)
