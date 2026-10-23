from django.conf import settings
from django.db import models
from django.utils import timezone

from common.enums import (
    AssessmentStatus,
    AttemptStatus,
    CertificateStatus,
    GenerateMode,
    GradingStatus,
    Level,
    MissingComponentPolicy,
    NotificationType,
    PaperStatus,
    PaperType,
    ScoreAggregation,
    ScoreSource,
    ScopeType,
    ScoringMode,
    ShowAnswerMode,
    Subject,
    TotalScoreRuleStatus,
)
from common.models import SoftDeleteModel, TimeStampedModel


class Paper(SoftDeleteModel):
    title = models.CharField(max_length=128)
    subject = models.CharField(max_length=16, choices=Subject.choices, db_index=True)
    paper_type = models.CharField(max_length=16, choices=PaperType.choices)
    grade = models.PositiveSmallIntegerField(db_index=True)
    scope_type = models.CharField(max_length=16, choices=ScopeType.choices)
    scope_id = models.BigIntegerField()
    scope_name = models.CharField(max_length=128)
    duration = models.PositiveIntegerField(default=45)
    instructions = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=PaperStatus.choices, default=PaperStatus.DRAFT, db_index=True
    )
    version = models.PositiveIntegerField(default=1)
    generate_mode = models.CharField(
        max_length=16, choices=GenerateMode.choices, default=GenerateMode.MANUAL
    )
    total_score = models.FloatField(default=0)
    question_count = models.PositiveIntegerField(default=0)
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_papers"
    )

    class Meta:
        db_table = "exam_paper"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["subject", "paper_type", "status"]),
            models.Index(fields=["scope_type", "scope_id"]),
        ]

    def __str__(self):
        return self.title


class PaperQuestion(TimeStampedModel):
    """试卷题目快照，题目后续在题库中修改不会影响本试卷。"""

    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="questions")
    question_id = models.BigIntegerField(db_index=True)
    order = models.PositiveIntegerField()
    section_name = models.CharField(max_length=64, blank=True, default="")
    type = models.CharField(max_length=32)
    stem = models.TextField()
    options = models.JSONField(default=list, blank=True)
    resources = models.JSONField(default=list, blank=True)
    answer = models.JSONField(default=dict, blank=True)
    analysis = models.TextField(null=True, blank=True)
    rubric = models.TextField(null=True, blank=True)
    score = models.FloatField()
    scoring_mode = models.CharField(
        max_length=16, choices=ScoringMode.choices, default=ScoringMode.AUTO
    )

    class Meta:
        db_table = "exam_paper_question"
        ordering = ["order", "id"]
        unique_together = [("paper", "order")]


class Assessment(TimeStampedModel):
    paper = models.ForeignKey(Paper, on_delete=models.PROTECT, related_name="assessments")
    title = models.CharField(max_length=128)
    subject = models.CharField(max_length=16, choices=Subject.choices, db_index=True)
    paper_type = models.CharField(max_length=16, choices=PaperType.choices)
    target_type = models.CharField(max_length=16, choices=ScopeType.choices)
    target_ids = models.JSONField(default=list)
    target_names = models.JSONField(default=list)
    target_grades = models.JSONField(default=list, blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    duration = models.PositiveIntegerField()
    attempt_limit = models.PositiveIntegerField(default=1)
    shuffle_questions = models.BooleanField(default=False)
    shuffle_options = models.BooleanField(default=False)
    show_answer_mode = models.CharField(
        max_length=16, choices=ShowAnswerMode.choices, default=ShowAnswerMode.AFTER_END
    )
    allow_late_submit = models.BooleanField(default=False)
    instructions = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=AssessmentStatus.choices,
        default=AssessmentStatus.PUBLISHED, db_index=True,
    )
    publisher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="published_assessments"
    )
    published_at = models.DateTimeField(default=timezone.now)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    withdraw_reason = models.CharField(max_length=255, blank=True, default="")
    finished_at = models.DateTimeField(null=True, blank=True)
    question_snapshot = models.JSONField(default=list)
    max_score = models.FloatField(default=0)
    participant_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "exam_assessment"
        ordering = ["-published_at"]
        indexes = [
            models.Index(fields=["subject", "status"]),
            models.Index(fields=["target_type", "status"]),
        ]

    def __str__(self):
        return self.title

    @property
    def is_ended(self):
        return self.end_time <= timezone.now()

    def targets_include_class(self, class_id):
        return self.target_type == ScopeType.CLASS and class_id in (self.target_ids or [])


class AssessmentTarget(models.Model):
    """发布目标的规范化存储，便于学生端可见性与统计做 SQL 过滤。"""

    assessment = models.ForeignKey(
        Assessment, on_delete=models.CASCADE, related_name="target_rows"
    )
    target_type = models.CharField(max_length=16, choices=ScopeType.choices)
    target_id = models.BigIntegerField()
    target_name = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        db_table = "exam_assessment_target"
        unique_together = [("assessment", "target_type", "target_id")]
        indexes = [models.Index(fields=["target_type", "target_id"])]


class AssessmentGrade(models.Model):
    """测评限定年级；无记录表示不限年级。"""

    assessment = models.ForeignKey(
        Assessment, on_delete=models.CASCADE, related_name="grade_rows"
    )
    grade = models.PositiveSmallIntegerField()

    class Meta:
        db_table = "exam_assessment_grade"
        unique_together = [("assessment", "grade")]


class Attempt(TimeStampedModel):
    assessment = models.ForeignKey(
        Assessment, on_delete=models.CASCADE, related_name="attempts"
    )
    paper = models.ForeignKey(Paper, on_delete=models.PROTECT, related_name="attempts")
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attempts"
    )
    attempt_no = models.PositiveIntegerField(default=1)
    questions_snapshot = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=16, choices=AttemptStatus.choices,
        default=AttemptStatus.IN_PROGRESS, db_index=True,
    )
    started_at = models.DateTimeField(default=timezone.now)
    deadline = models.DateTimeField(db_index=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    submit_type = models.CharField(max_length=16, blank=True, default="")
    auto_submitted = models.BooleanField(default=False)
    objective_score = models.FloatField(default=0)
    subjective_score = models.FloatField(default=0)
    ai_score = models.FloatField(default=0)
    total_score = models.FloatField(default=0)
    grading_status = models.CharField(
        max_length=16, choices=GradingStatus.choices, default=GradingStatus.PENDING,
        db_index=True,
    )
    version = models.PositiveIntegerField(default=0)
    last_answer_saved_at = models.DateTimeField(null=True, blank=True)
    ai_error = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "exam_attempt"
        ordering = ["-started_at"]
        unique_together = [("assessment", "student", "attempt_no")]

    @property
    def remaining_seconds(self):
        delta = (self.deadline - timezone.now()).total_seconds()
        return max(0, int(delta))

    @property
    def is_expired(self):
        return timezone.now() >= self.deadline


class AttemptAnswer(TimeStampedModel):
    attempt = models.ForeignKey(
        Attempt, on_delete=models.CASCADE, related_name="answers"
    )
    question_id = models.BigIntegerField()
    order = models.PositiveIntegerField()
    answer = models.JSONField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)
    max_score = models.FloatField(default=0)
    scoring_mode = models.CharField(
        max_length=16, choices=ScoringMode.choices, default=ScoringMode.AUTO
    )
    is_correct = models.BooleanField(null=True, blank=True)
    ai_score = models.FloatField(null=True, blank=True)
    ai_analysis = models.TextField(null=True, blank=True)
    comment = models.CharField(max_length=500, null=True, blank=True)
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="graded_answers",
    )
    graded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "exam_attempt_answer"
        ordering = ["order", "id"]
        unique_together = [("attempt", "question_id")]


class Score(TimeStampedModel):
    attempt = models.OneToOneField(
        Attempt, null=True, blank=True, on_delete=models.SET_NULL, related_name="score"
    )
    assessment = models.ForeignKey(
        Assessment, on_delete=models.CASCADE, related_name="scores"
    )
    subject = models.CharField(max_length=16, choices=Subject.choices, db_index=True)
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="scores"
    )
    student_name = models.CharField(max_length=64)
    student_no = models.CharField(max_length=32, blank=True, default="")
    classroom = models.ForeignKey(
        "accounts.Class", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="scores",
    )
    class_name = models.CharField(max_length=64, blank=True, default="")
    school = models.ForeignKey(
        "accounts.School", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="scores",
    )
    school_name = models.CharField(max_length=128, blank=True, default="")
    grade = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    objective_score = models.FloatField(default=0)
    subjective_score = models.FloatField(default=0)
    ai_score = models.FloatField(default=0)
    total_score = models.FloatField(default=0)
    max_score = models.FloatField(default=0)
    level = models.CharField(max_length=16, choices=Level.choices, blank=True, default="")
    class_rank = models.PositiveIntegerField(null=True, blank=True)
    grade_rank = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=GradingStatus.choices, default=GradingStatus.GRADED,
        db_index=True,
    )
    source = models.CharField(
        max_length=16, choices=ScoreSource.choices, default=ScoreSource.ONLINE
    )
    score_items = models.JSONField(default=list, blank=True)
    reason = models.CharField(max_length=255, blank=True, default="")
    evidence_file_ids = models.JSONField(default=list, blank=True)
    graded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "exam_score"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "student"], name="uniq_score_assessment_student"
            )
        ]
        indexes = [
            models.Index(fields=["assessment", "classroom"]),
            models.Index(fields=["assessment", "school", "grade"]),
        ]


class Certificate(TimeStampedModel):
    certificate_no = models.CharField(max_length=64, unique=True)
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="certificates"
    )
    student_name = models.CharField(max_length=64)
    assessment = models.ForeignKey(
        Assessment, on_delete=models.CASCADE, related_name="certificates"
    )
    subject = models.CharField(max_length=16, choices=Subject.choices)
    classroom = models.ForeignKey(
        "accounts.Class", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="certificates",
    )
    class_name = models.CharField(max_length=64, blank=True, default="")
    school = models.ForeignKey(
        "accounts.School", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="certificates",
    )
    school_name = models.CharField(max_length=128, blank=True, default="")
    score = models.FloatField()
    level = models.CharField(max_length=16, choices=Level.choices)
    issue_date = models.DateField()
    status = models.CharField(
        max_length=16, choices=CertificateStatus.choices,
        default=CertificateStatus.GENERATING,
    )
    file_path = models.CharField(max_length=512, blank=True, default="")
    template_id = models.BigIntegerField(null=True, blank=True)
    error = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "exam_certificate"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "student"], name="uniq_certificate_assessment_student"
            )
        ]


class TotalScoreRule(TimeStampedModel):
    """教师总评规则：平时测试、正式测评、证书按权重合成学期总评。"""

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="total_score_rules",
    )
    name = models.CharField(max_length=128)
    subject = models.CharField(max_length=16, choices=Subject.choices, db_index=True)
    classroom = models.ForeignKey(
        "accounts.Class", on_delete=models.CASCADE, related_name="total_score_rules"
    )
    term = models.CharField(max_length=32, blank=True, default="")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    usual_weight = models.FloatField(default=0.4)
    formal_weight = models.FloatField(default=0.4)
    certificate_weight = models.FloatField(default=0.2)
    usual_aggregation = models.CharField(
        max_length=16, choices=ScoreAggregation.choices,
        default=ScoreAggregation.AVERAGE,
    )
    formal_aggregation = models.CharField(
        max_length=16, choices=ScoreAggregation.choices,
        default=ScoreAggregation.AVERAGE,
    )
    certificate_aggregation = models.CharField(
        max_length=16, choices=ScoreAggregation.choices,
        default=ScoreAggregation.BEST,
    )
    certificate_level_scores = models.JSONField(default=dict, blank=True)
    missing_policy = models.CharField(
        max_length=16, choices=MissingComponentPolicy.choices,
        default=MissingComponentPolicy.RENORMALIZE,
    )
    excellent_line = models.FloatField(default=90)
    good_line = models.FloatField(default=80)
    pass_line = models.FloatField(default=60)
    note = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=TotalScoreRuleStatus.choices,
        default=TotalScoreRuleStatus.DRAFT, db_index=True,
    )
    version = models.PositiveIntegerField(default=1)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "exam_total_score_rule"
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "classroom", "subject", "term"],
                condition=models.Q(status=TotalScoreRuleStatus.PUBLISHED),
                name="uniq_published_total_score_rule",
            )
        ]
        indexes = [
            models.Index(fields=["teacher", "subject"]),
            models.Index(fields=["classroom", "subject", "term"]),
        ]

    def __str__(self):
        return self.name


class GradingLog(TimeStampedModel):
    attempt = models.ForeignKey(
        Attempt, on_delete=models.CASCADE, related_name="grading_logs"
    )
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="grading_logs",
    )
    action = models.CharField(max_length=32)  # submit / finalize / regrade
    items = models.JSONField(default=list, blank=True)
    finalize = models.BooleanField(default=False)
    reason = models.CharField(max_length=255, blank=True, default="")
    version = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "exam_grading_log"
        ordering = ["-created_at"]


class ImportTask(TimeStampedModel):
    task_id = models.CharField(max_length=64, unique=True)
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="score_import_tasks",
    )
    assessment = models.ForeignKey(
        Assessment, on_delete=models.CASCADE, related_name="import_tasks"
    )
    subject = models.CharField(max_length=16)
    status = models.CharField(max_length=16, default="queued")
    total = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    fail_count = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)
    file_name = models.CharField(max_length=255, blank=True, default="")
    file_path = models.CharField(max_length=512, blank=True, default="")
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "exam_import_task"
        ordering = ["-created_at"]


class Notification(models.Model):
    """站内通知，只面向接收人本人。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    type = models.CharField(max_length=32, choices=NotificationType.choices, db_index=True)
    title = models.CharField(max_length=128)
    content = models.TextField()
    link = models.CharField(max_length=255, null=True, blank=True)
    read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "exam_notification"
        ordering = ["-created_at", "-id"]


class LearningReport(models.Model):
    report_id = models.CharField(max_length=64, unique=True)
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="learning_reports"
    )
    subject = models.CharField(max_length=16, choices=Subject.choices)
    generated_at = models.DateTimeField(default=timezone.now)
    summary = models.TextField(blank=True, default="")
    strengths = models.JSONField(default=list, blank=True)
    weaknesses = models.JSONField(default=list, blank=True)
    suggestions = models.JSONField(default=list, blank=True)
    score_trend = models.JSONField(default=list, blank=True)
    raw_text = models.TextField(blank=True, default="")
    model_version = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "exam_learning_report"
        ordering = ["-generated_at"]
