"""文件对象与本地存储。"""
from django.conf import settings
from django.db import models

from common.enums import AudioAnalysisStatus, FileCategory
from common.models import BaseModel


class FileObject(BaseModel):
    uploader = models.ForeignKey(
        "accounts.User",
        verbose_name="上传人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="uploaded_files",
        db_comment="上传人用户 ID",
    )
    category = models.CharField(
        "文件分类",
        max_length=32,
        choices=FileCategory.choices,
        db_comment="文件分类：avatar/question_image/question_audio/student_work/certificate/import/other",
    )
    original_name = models.CharField(
        "原始文件名", max_length=255, db_comment="原始文件名"
    )
    object_key = models.CharField(
        "对象 Key", max_length=500, unique=True, db_comment="存储对象 Key（唯一）"
    )
    mime_type = models.CharField(
        "MIME 类型", max_length=100, db_comment="文件 MIME 类型"
    )
    size = models.BigIntegerField("文件大小", db_comment="文件大小（字节）")
    storage_backend = models.CharField(
        "存储后端", max_length=16, default="local", db_comment="存储后端：local/minio"
    )
    biz_id = models.BigIntegerField(
        "关联业务 ID", null=True, blank=True, db_comment="关联业务 ID，如试题 ID、测评 ID"
    )
    subject = models.CharField(
        "学科",
        max_length=16,
        null=True,
        blank=True,
        db_comment="学科（学生作品等分类使用）：music/art",
    )
    review_score = models.DecimalField(
        "作品评分",
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        db_comment="教师对课外作品的评分（0~100）",
    )
    review_comment = models.TextField(
        "评价意见", null=True, blank=True, db_comment="教师对课外作品的评价"
    )
    reviewed_by = models.ForeignKey(
        "accounts.User",
        verbose_name="评分教师",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_artworks",
        db_comment="评分教师用户 ID",
    )
    reviewed_at = models.DateTimeField(
        "评分时间", null=True, blank=True, db_comment="作品评分时间"
    )

    class Meta:
        db_table = "files"
        db_table_comment = "文件对象表"
        ordering = ["-id"]

    def __str__(self) -> str:
        return self.original_name

    @property
    def url(self) -> str:
        if self.storage_backend == "minio":
            from .minio import presigned_url

            return presigned_url(self.object_key)
        return f"{settings.MEDIA_URL}{self.object_key}"


class AudioAnalysis(BaseModel):
    """音频标签与规则参考分析。

    只记录音频的客观标签和规则参考分，不参与自动判分，也不写入
    ``Attempt`` / ``AttemptAnswer`` / ``Score`` 的任何分数字段。
    """

    file = models.OneToOneField(
        FileObject,
        verbose_name="文件",
        on_delete=models.CASCADE,
        related_name="audio_analysis",
        db_comment="音频文件 ID",
    )
    status = models.CharField(
        "分析状态",
        max_length=16,
        choices=AudioAnalysisStatus.choices,
        default=AudioAnalysisStatus.PENDING,
        db_index=True,
        db_comment="状态：pending/completed/failed",
    )
    genre = models.CharField(
        "曲风", max_length=32, blank=True, db_index=True, db_comment="模型预测曲风标签"
    )
    genre_label = models.CharField(
        "曲风名称", max_length=32, blank=True, db_comment="曲风中文名称"
    )
    genre_confidence = models.FloatField(
        "曲风置信度", null=True, blank=True, db_comment="曲风 top-1 概率"
    )
    genre_probs = models.JSONField(
        "曲风概率", default=dict, blank=True, db_comment="13 类曲风概率 JSON"
    )
    emotion = models.CharField(
        "情绪", max_length=16, blank=True, db_index=True, db_comment="模型预测情绪标签"
    )
    emotion_label = models.CharField(
        "情绪名称", max_length=16, blank=True, db_comment="情绪中文名称"
    )
    emotion_confidence = models.FloatField(
        "情绪置信度", null=True, blank=True, db_comment="情绪 top-1 概率"
    )
    emotion_probs = models.JSONField(
        "情绪概率", default=dict, blank=True, db_comment="4 类情绪概率 JSON"
    )
    mode = models.CharField(
        "调式", max_length=16, blank=True, db_comment="major/minor"
    )
    mode_label = models.CharField(
        "调式名称", max_length=16, blank=True, db_comment="调式中文名称"
    )
    mode_confidence = models.FloatField(
        "调式置信度", null=True, blank=True, db_comment="调式 top-1 概率"
    )
    mode_probs = models.JSONField(
        "调式概率", default=dict, blank=True, db_comment="大小调概率 JSON"
    )
    bpm = models.FloatField(
        "BPM", null=True, blank=True, db_index=True, db_comment="模型预测速度"
    )
    key = models.CharField(
        "调性", max_length=32, blank=True, db_comment="DSP 估计调性，如 C major"
    )
    duration = models.FloatField(
        "时长（秒）", null=True, blank=True, db_comment="音频总时长"
    )
    reference_score = models.FloatField(
        "规则参考分",
        null=True,
        blank=True,
        db_comment="规则产出的参考分（非成绩，不参与评分）",
    )
    reference_grade = models.CharField(
        "参考等级", max_length=16, blank=True, db_comment="规则参考等级"
    )
    metrics = models.JSONField(
        "DSP 指标", default=dict, blank=True, db_comment="削波、动态范围、节拍稳定度等"
    )
    dimensions = models.JSONField(
        "规则维度", default=list, blank=True, db_comment="参考分各维度明细 JSON"
    )
    penalties = models.JSONField(
        "规则扣分", default=list, blank=True, db_comment="参考分扣分项 JSON"
    )
    model_version = models.CharField(
        "模型版本", max_length=64, blank=True, db_comment="模型权重与轮次"
    )
    rubric_id = models.CharField(
        "规则编号", max_length=64, blank=True, db_comment="评分规则 ID"
    )
    raw = models.JSONField(
        "原始结果", default=dict, blank=True, db_comment="分析服务原始返回 JSON"
    )
    error_message = models.TextField(
        "失败原因", blank=True, default="", db_comment="分析失败原因"
    )
    analyzed_at = models.DateTimeField(
        "分析时间", null=True, blank=True, db_comment="最近一次分析完成时间"
    )

    class Meta:
        db_table = "file_audio_analyses"
        db_table_comment = "音频标签与规则参考分析表"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["status", "genre", "emotion"]),
        ]

    def __str__(self) -> str:
        return f"{self.file_id} {self.status}"
