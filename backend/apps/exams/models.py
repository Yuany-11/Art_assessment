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
    PaperStatus,
    PaperType,
    ScoreSource,
    ScopeType,
    ScoringMode,
    ShowAnswerMode,
    Subject,
)
from common.models import BaseModel


class Paper(BaseModel):
    title = models.CharField(max_length=128, db_comment="试卷标题")
    subject = models.CharField(
        max_length=16, choices=Subject.choices, db_index=True,
        db_comment="学科：music/art",
    )
    paper_type = models.CharField(
        max_length=16, choices=PaperType.choices,
        db_comment="试卷类型：practice/formal",
    )
    grade = models.PositiveSmallIntegerField(db_index=True, db_comment="适用年级（1~12）")
    scope_type = models.CharField(
        max_length=16, choices=ScopeType.choices,
        db_comment="可见范围类型：class/school/district/city/province",
    )
    scope_id = models.BigIntegerField(db_comment="范围对象 ID")
    scope_name = models.CharField(max_length=128, db_comment="范围名称快照")
    duration = models.PositiveIntegerField(default=45, db_comment="考试时长（分钟）")
    instructions = models.TextField(null=True, blank=True, db_comment="考试说明")
    status = models.CharField(
        max_length=16, choices=PaperStatus.choices, default=PaperStatus.DRAFT,
        db_index=True, db_comment="状态：draft/ready/published/archived",
    )
    generate_mode = models.CharField(
        max_length=16, choices=GenerateMode.choices, default=GenerateMode.MANUAL,
        db_comment="组卷方式：manual/auto",
    )
    total_score = models.FloatField(default=0, db_comment="试卷总分")
    question_count = models.PositiveIntegerField(default=0, db_comment="题目数量")
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="created_papers", db_comment="创建人用户 ID",
    )

    class Meta:
        db_table = "exam_paper"
        db_table_comment = "试卷表"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["subject", "paper_type", "status"]),
            models.Index(fields=["scope_type", "scope_id"]),
        ]

    def __str__(self):
        return self.title


class PaperQuestion(BaseModel):
    """试卷题目快照，题目后续在题库中修改不会影响本试卷。"""

    paper = models.ForeignKey(
        Paper, on_delete=models.CASCADE, related_name="questions",
        db_comment="试卷 ID",
    )
    question_id = models.BigIntegerField(
        db_index=True, db_comment="原题库试题 ID（快照，不做外键）"
    )
    order = models.PositiveIntegerField(db_comment="题目顺序")
    section_name = models.CharField(
        max_length=64, blank=True, default="", db_comment="大题/板块名称"
    )
    type = models.CharField(max_length=32, db_comment="题型快照")
    stem = models.TextField(db_comment="题干快照")
    options = models.JSONField(
        default=list, blank=True, db_comment="选项快照 JSON"
    )
    resources = models.JSONField(
        default=list, blank=True, db_comment="资源快照 JSON"
    )
    answer = models.JSONField(default=dict, blank=True, db_comment="标准答案快照")
    analysis = models.TextField(null=True, blank=True, db_comment="解析快照")
    rubric = models.TextField(null=True, blank=True, db_comment="评分标准快照")
    score = models.FloatField(db_comment="本题分值")
    scoring_mode = models.CharField(
        max_length=16, choices=ScoringMode.choices, default=ScoringMode.AUTO,
        db_comment="评分方式：auto/manual/ai",
    )

    class Meta:
        db_table = "exam_paper_question"
        db_table_comment = "试卷题目快照表"
        ordering = ["order", "id"]
        unique_together = [("paper", "order")]


class Assessment(BaseModel):
    paper = models.ForeignKey(
        Paper, on_delete=models.PROTECT, related_name="assessments",
        db_comment="试卷 ID",
    )
    title = models.CharField(max_length=128, db_comment="测评标题")
    subject = models.CharField(
        max_length=16, choices=Subject.choices, db_index=True,
        db_comment="学科：music/art",
    )
    paper_type = models.CharField(
        max_length=16, choices=PaperType.choices,
        db_comment="试卷类型：practice/formal",
    )
    target_type = models.CharField(
        max_length=16, choices=ScopeType.choices,
        db_comment="发布对象类型：class/school/district/city/province",
    )
    target_ids = models.JSONField(default=list, db_comment="发布对象 ID 列表")
    target_names = models.JSONField(default=list, db_comment="发布对象名称列表")
    target_grades = models.JSONField(
        default=list, blank=True, db_comment="限定年级列表，空表示不限"
    )
    start_time = models.DateTimeField(db_comment="测评开始时间")
    end_time = models.DateTimeField(db_comment="测评结束时间")
    duration = models.PositiveIntegerField(db_comment="答题时长（分钟）")
    attempt_limit = models.PositiveIntegerField(default=1, db_comment="允许答题次数")
    shuffle_questions = models.BooleanField(default=False, db_comment="是否打乱题目顺序")
    shuffle_options = models.BooleanField(default=False, db_comment="是否打乱选项顺序")
    show_answer_mode = models.CharField(
        max_length=16, choices=ShowAnswerMode.choices,
        default=ShowAnswerMode.AFTER_END,
        db_comment="答案展示时机：never/after_submit/after_end",
    )
    allow_late_submit = models.BooleanField(default=False, db_comment="是否允许超时补交")
    instructions = models.TextField(null=True, blank=True, db_comment="测评说明")
    status = models.CharField(
        max_length=16, choices=AssessmentStatus.choices,
        default=AssessmentStatus.PUBLISHED, db_index=True,
        db_comment="状态：published/withdrawn/finished",
    )
    publisher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="published_assessments", db_comment="发布人用户 ID",
    )
    published_at = models.DateTimeField(default=timezone.now, db_comment="发布时间")
    withdrawn_at = models.DateTimeField(null=True, blank=True, db_comment="撤回时间")
    withdraw_reason = models.CharField(
        max_length=255, blank=True, default="", db_comment="撤回原因"
    )
    finished_at = models.DateTimeField(null=True, blank=True, db_comment="结束时间")
    question_snapshot = models.JSONField(
        default=list, db_comment="题目快照 JSON（发布时固化）"
    )
    max_score = models.FloatField(default=0, db_comment="满分")
    participant_count = models.PositiveIntegerField(default=0, db_comment="参与人数")

    class Meta:
        db_table = "exam_assessment"
        db_table_comment = "测评任务表"
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
        Assessment, on_delete=models.CASCADE, related_name="target_rows",
        db_comment="测评 ID",
    )
    target_type = models.CharField(
        max_length=16, choices=ScopeType.choices,
        db_comment="对象类型：class/school/district/city/province",
    )
    target_id = models.BigIntegerField(db_comment="对象 ID")
    target_name = models.CharField(
        max_length=128, blank=True, default="", db_comment="对象名称快照"
    )

    class Meta:
        db_table = "exam_assessment_target"
        db_table_comment = "测评发布对象表"
        unique_together = [("assessment", "target_type", "target_id")]
        indexes = [models.Index(fields=["target_type", "target_id"])]


class AssessmentGrade(models.Model):
    """测评限定年级；无记录表示不限年级。"""

    assessment = models.ForeignKey(
        Assessment, on_delete=models.CASCADE, related_name="grade_rows",
        db_comment="测评 ID",
    )
    grade = models.PositiveSmallIntegerField(db_comment="限定年级（1~12）")

    class Meta:
        db_table = "exam_assessment_grade"
        db_table_comment = "测评限定年级表"
        unique_together = [("assessment", "grade")]


class Attempt(BaseModel):
    assessment = models.ForeignKey(
        Assessment, on_delete=models.CASCADE, related_name="attempts",
        db_comment="测评 ID",
    )
    paper = models.ForeignKey(
        Paper, on_delete=models.PROTECT, related_name="attempts",
        db_comment="试卷 ID",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="attempts", db_comment="学生用户 ID",
    )
    attempt_no = models.PositiveIntegerField(default=1, db_comment="第几次作答")
    questions_snapshot = models.JSONField(
        default=list, blank=True, db_comment="本次答卷题目快照 JSON"
    )
    status = models.CharField(
        max_length=16, choices=AttemptStatus.choices,
        default=AttemptStatus.IN_PROGRESS, db_index=True,
        db_comment="状态：in_progress/submitted/graded/invalid",
    )
    started_at = models.DateTimeField(default=timezone.now, db_comment="开始答题时间")
    deadline = models.DateTimeField(db_index=True, db_comment="答题截止时间")
    submitted_at = models.DateTimeField(null=True, blank=True, db_comment="交卷时间")
    submit_type = models.CharField(
        max_length=16, blank=True, default="", db_comment="交卷方式：manual/auto"
    )
    auto_submitted = models.BooleanField(default=False, db_comment="是否自动交卷")
    objective_score = models.FloatField(default=0, db_comment="客观题得分")
    subjective_score = models.FloatField(default=0, db_comment="主观题得分")
    ai_score = models.FloatField(default=0, db_comment="AI 评分得分")
    total_score = models.FloatField(default=0, db_comment="总得分")
    grading_status = models.CharField(
        max_length=16, choices=GradingStatus.choices, default=GradingStatus.PENDING,
        db_index=True, db_comment="判分状态：pending/grading/graded/failed",
    )
    version = models.PositiveIntegerField(default=0, db_comment="答案版本号（乐观锁）")
    last_answer_saved_at = models.DateTimeField(
        null=True, blank=True, db_comment="最后一次保存答案时间"
    )
    ai_error = models.CharField(
        max_length=255, blank=True, default="", db_comment="AI 评分失败原因"
    )

    class Meta:
        db_table = "exam_attempt"
        db_table_comment = "答卷表"
        ordering = ["-started_at"]
        unique_together = [("assessment", "student", "attempt_no")]

    @property
    def remaining_seconds(self):
        delta = (self.deadline - timezone.now()).total_seconds()
        return max(0, int(delta))

    @property
    def is_expired(self):
        return timezone.now() >= self.deadline


class AttemptAnswer(BaseModel):
    attempt = models.ForeignKey(
        Attempt, on_delete=models.CASCADE, related_name="answers",
        db_comment="答卷 ID",
    )
    question_id = models.BigIntegerField(db_comment="快照题目 ID")
    order = models.PositiveIntegerField(db_comment="题目顺序")
    answer = models.JSONField(null=True, blank=True, db_comment="学生作答内容 JSON")
    score = models.FloatField(null=True, blank=True, db_comment="本题得分")
    max_score = models.FloatField(default=0, db_comment="本题满分")
    scoring_mode = models.CharField(
        max_length=16, choices=ScoringMode.choices, default=ScoringMode.AUTO,
        db_comment="评分方式：auto/manual/ai",
    )
    is_correct = models.BooleanField(null=True, blank=True, db_comment="是否答对")
    ai_score = models.FloatField(null=True, blank=True, db_comment="AI 评分")
    ai_analysis = models.TextField(null=True, blank=True, db_comment="AI 评分说明")
    comment = models.CharField(
        max_length=500, null=True, blank=True, db_comment="教师评分评语"
    )
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="graded_answers",
        db_comment="评分教师用户 ID",
    )
    graded_at = models.DateTimeField(null=True, blank=True, db_comment="评分时间")

    class Meta:
        db_table = "exam_attempt_answer"
        db_table_comment = "答卷答案表"
        ordering = ["order", "id"]
        unique_together = [("attempt", "question_id")]


class Score(BaseModel):
    attempt = models.OneToOneField(
        Attempt, null=True, blank=True, on_delete=models.SET_NULL, related_name="score",
        db_comment="关联答卷 ID（线下补录时为空）",
    )
    assessment = models.ForeignKey(
        Assessment, on_delete=models.CASCADE, related_name="scores",
        db_comment="测评 ID",
    )
    subject = models.CharField(
        max_length=16, choices=Subject.choices, db_index=True,
        db_comment="学科：music/art",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="scores",
        db_comment="学生用户 ID",
    )
    student_name = models.CharField(max_length=64, db_comment="学生姓名快照")
    student_no = models.CharField(
        max_length=32, blank=True, default="", db_comment="学籍号快照"
    )
    classroom = models.ForeignKey(
        "classes.Class", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="scores",
        db_comment="班级 ID",
    )
    class_name = models.CharField(
        max_length=64, blank=True, default="", db_comment="班级名称快照"
    )
    school = models.ForeignKey(
        "organizations.Organization", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="scores",
        db_comment="学校 ID",
    )
    school_name = models.CharField(
        max_length=128, blank=True, default="", db_comment="学校名称快照"
    )
    grade = models.PositiveSmallIntegerField(
        null=True, blank=True, db_index=True, db_comment="年级"
    )
    objective_score = models.FloatField(default=0, db_comment="客观题得分")
    subjective_score = models.FloatField(default=0, db_comment="主观题得分")
    ai_score = models.FloatField(default=0, db_comment="AI 评分得分")
    total_score = models.FloatField(default=0, db_comment="总得分")
    max_score = models.FloatField(default=0, db_comment="满分")
    level = models.CharField(
        max_length=16, choices=Level.choices, blank=True, default="",
        db_comment="成绩等级：excellent/good/pass/fail",
    )
    class_rank = models.PositiveIntegerField(
        null=True, blank=True, db_comment="班级排名"
    )
    grade_rank = models.PositiveIntegerField(
        null=True, blank=True, db_comment="年级排名"
    )
    status = models.CharField(
        max_length=16, choices=GradingStatus.choices, default=GradingStatus.GRADED,
        db_index=True, db_comment="判分状态：pending/grading/graded/failed",
    )
    source = models.CharField(
        max_length=16, choices=ScoreSource.choices, default=ScoreSource.ONLINE,
        db_comment="成绩来源：online/manual/import",
    )
    score_items = models.JSONField(
        default=list, blank=True, db_comment="各题得分明细 JSON"
    )
    reason = models.CharField(
        max_length=255, blank=True, default="", db_comment="补录/调整原因"
    )
    evidence_file_ids = models.JSONField(
        default=list, blank=True, db_comment="佐证文件 ID 列表"
    )
    graded_at = models.DateTimeField(null=True, blank=True, db_comment="评分时间")

    class Meta:
        db_table = "exam_score"
        db_table_comment = "成绩表"
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


class Certificate(BaseModel):
    certificate_no = models.CharField(
        max_length=64, unique=True, db_comment="证书编号（唯一）"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="certificates",
        db_comment="学生用户 ID",
    )
    student_name = models.CharField(max_length=64, db_comment="学生姓名快照")
    assessment = models.ForeignKey(
        Assessment, on_delete=models.CASCADE, related_name="certificates",
        db_comment="测评 ID",
    )
    subject = models.CharField(
        max_length=16, choices=Subject.choices, db_comment="学科：music/art"
    )
    classroom = models.ForeignKey(
        "classes.Class", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="certificates",
        db_comment="班级 ID",
    )
    class_name = models.CharField(
        max_length=64, blank=True, default="", db_comment="班级名称快照"
    )
    school = models.ForeignKey(
        "organizations.Organization", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="certificates",
        db_comment="学校 ID",
    )
    school_name = models.CharField(
        max_length=128, blank=True, default="", db_comment="学校名称快照"
    )
    score = models.FloatField(db_comment="测评得分")
    level = models.CharField(
        max_length=16, choices=Level.choices,
        db_comment="成绩等级：excellent/good/pass/fail",
    )
    issue_date = models.DateField(db_comment="颁发日期")
    status = models.CharField(
        max_length=16, choices=CertificateStatus.choices,
        default=CertificateStatus.GENERATING,
        db_comment="状态：generating/ready/failed",
    )
    file_path = models.CharField(
        max_length=512, blank=True, default="", db_comment="证书文件存储路径"
    )
    template_id = models.BigIntegerField(
        null=True, blank=True, db_comment="证书模板 ID"
    )
    error = models.CharField(
        max_length=255, blank=True, default="", db_comment="生成失败原因"
    )

    class Meta:
        db_table = "exam_certificate"
        db_table_comment = "测评证书表"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "student"], name="uniq_certificate_assessment_student"
            )
        ]


class GradingLog(BaseModel):
    attempt = models.ForeignKey(
        Attempt, on_delete=models.CASCADE, related_name="grading_logs",
        db_comment="答卷 ID",
    )
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="grading_logs", db_comment="操作人用户 ID",
    )
    action = models.CharField(
        max_length=32, db_comment="动作：submit/finalize/regrade"
    )
    items = models.JSONField(default=list, blank=True, db_comment="评分项明细 JSON")
    finalize = models.BooleanField(default=False, db_comment="是否完成评分")
    reason = models.CharField(
        max_length=255, blank=True, default="", db_comment="操作原因"
    )
    version = models.PositiveIntegerField(default=0, db_comment="评分版本号")

    class Meta:
        db_table = "exam_grading_log"
        db_table_comment = "人工评分日志表"
        ordering = ["-created_at"]


class ImportTask(BaseModel):
    task_id = models.CharField(max_length=64, unique=True, db_comment="导入任务 ID（唯一）")
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="score_import_tasks", db_comment="操作人用户 ID",
    )
    assessment = models.ForeignKey(
        Assessment, on_delete=models.CASCADE, related_name="import_tasks",
        db_comment="测评 ID",
    )
    subject = models.CharField(max_length=16, db_comment="学科：music/art")
    status = models.CharField(
        max_length=16, default="queued", db_comment="状态：queued/processing/completed/failed"
    )
    total = models.PositiveIntegerField(default=0, db_comment="导入总行数")
    success_count = models.PositiveIntegerField(default=0, db_comment="成功条数")
    fail_count = models.PositiveIntegerField(default=0, db_comment="失败条数")
    errors = models.JSONField(default=list, blank=True, db_comment="失败明细 JSON")
    file_name = models.CharField(
        max_length=255, blank=True, default="", db_comment="导入文件名"
    )
    file_path = models.CharField(
        max_length=512, blank=True, default="", db_comment="导入文件存储路径"
    )
    finished_at = models.DateTimeField(null=True, blank=True, db_comment="完成时间")

    class Meta:
        db_table = "exam_import_task"
        db_table_comment = "线下成绩导入任务表"
        ordering = ["-created_at"]


class LearningReport(models.Model):
    report_id = models.CharField(max_length=64, unique=True, db_comment="学情报告 ID（唯一）")
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="learning_reports", db_comment="学生用户 ID",
    )
    subject = models.CharField(
        max_length=16, choices=Subject.choices, db_comment="学科：music/art"
    )
    generated_at = models.DateTimeField(
        default=timezone.now, db_comment="报告生成时间"
    )
    summary = models.TextField(blank=True, default="", db_comment="学情总结")
    strengths = models.JSONField(default=list, blank=True, db_comment="优势项 JSON")
    weaknesses = models.JSONField(default=list, blank=True, db_comment="薄弱项 JSON")
    suggestions = models.JSONField(default=list, blank=True, db_comment="学习建议 JSON")
    score_trend = models.JSONField(default=list, blank=True, db_comment="成绩趋势 JSON")
    raw_text = models.TextField(blank=True, default="", db_comment="AI 原始输出文本")
    model_version = models.CharField(
        max_length=64, blank=True, default="", db_comment="生成模型版本"
    )

    class Meta:
        db_table = "exam_learning_report"
        db_table_comment = "学生学情报告表"
        ordering = ["-generated_at"]
