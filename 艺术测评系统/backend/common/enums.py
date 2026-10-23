"""全局枚举，与 api.md 1.5 / 1.9 保持一致。"""
from django.db import models


class Role(models.TextChoices):
    STUDENT = "student", "学生"
    TEACHER = "teacher", "教师"
    SCHOOL_ADMIN = "school_admin", "学校管理员"
    DISTRICT_ADMIN = "district_admin", "区县管理员"
    CITY_ADMIN = "city_admin", "市州管理员"
    PROVINCE_ADMIN = "province_admin", "省级管理员"
    QUESTION_ADMIN = "question_admin", "题库管理员"


class Subject(models.TextChoices):
    MUSIC = "music", "音乐"
    ART = "art", "美术"


class QuestionType(models.TextChoices):
    SINGLE_CHOICE = "single_choice", "单选"
    MULTIPLE_CHOICE = "multiple_choice", "多选"
    TRUE_FALSE = "true_false", "判断"
    FILL_BLANK = "fill_blank", "填空"
    SHORT_ANSWER = "short_answer", "简答"
    LISTENING = "listening", "听赏"
    IMAGE_UPLOAD = "image_upload", "图片作品"
    AUDIO_UPLOAD = "audio_upload", "音频作品"


class ScoringMode(models.TextChoices):
    AUTO = "auto", "自动判分"
    MANUAL = "manual", "人工评分"
    AI = "ai", "AI 辅助评分"


class QuestionStatus(models.TextChoices):
    DRAFT = "draft", "草稿"
    PENDING = "pending", "待审核"
    APPROVED = "approved", "已通过"
    REJECTED = "rejected", "已驳回"
    OFFLINE = "offline", "已下架"


class PaperType(models.TextChoices):
    PRACTICE = "practice", "练习卷"
    FORMAL = "formal", "正式测评卷"


class GenerateMode(models.TextChoices):
    MANUAL = "manual", "手动组卷"
    AUTO = "auto", "自动随机组卷"


class ScopeType(models.TextChoices):
    CLASS = "class", "班级"
    SCHOOL = "school", "学校"
    DISTRICT = "district", "区县"
    CITY = "city", "市州"
    PROVINCE = "province", "省"


class PaperStatus(models.TextChoices):
    DRAFT = "draft", "草稿"
    READY = "ready", "已就绪"
    PUBLISHED = "published", "已用于发布"
    ARCHIVED = "archived", "已归档"


class NotificationType(models.TextChoices):
    SYSTEM = "system", "系统通知"


class AssessmentStatus(models.TextChoices):
    PUBLISHED = "published", "已发布"
    WITHDRAWN = "withdrawn", "已撤回"
    FINISHED = "finished", "已结束"


class AttemptStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", "答题中"
    SUBMITTED = "submitted", "已提交"
    GRADED = "graded", "已评分"
    INVALID = "invalid", "无效"


class SubmitType(models.TextChoices):
    MANUAL = "manual", "学生主动交卷"
    AUTO = "auto", "到时自动交卷"


class GradingStatus(models.TextChoices):
    PENDING = "pending", "待判分"
    GRADING = "grading", "判分中"
    GRADED = "graded", "已完成"
    FAILED = "failed", "判分失败"


class ScoreSource(models.TextChoices):
    ONLINE = "online", "线上测评"
    MANUAL = "manual", "教师补录"
    IMPORT = "import", "线下成绩导入"


class ScoreAggregation(models.TextChoices):
    AVERAGE = "average", "平均分"
    LATEST = "latest", "最近一次"
    BEST = "best", "最高分"


class MissingComponentPolicy(models.TextChoices):
    ZERO = "zero", "缺项按 0 分"
    RENORMALIZE = "renormalize", "按剩余权重折算"


class TotalScoreRuleStatus(models.TextChoices):
    DRAFT = "draft", "草稿"
    PUBLISHED = "published", "已发布"
    ARCHIVED = "archived", "已归档"


class ShowAnswerMode(models.TextChoices):
    NEVER = "never", "不展示"
    AFTER_SUBMIT = "after_submit", "交卷后展示"
    AFTER_END = "after_end", "测评结束后展示"


class CertificateStatus(models.TextChoices):
    GENERATING = "generating", "生成中"
    READY = "ready", "可下载"
    FAILED = "failed", "生成失败"


class Level(models.TextChoices):
    EXCELLENT = "excellent", "优秀"
    GOOD = "good", "良好"
    PASS = "pass", "合格"
    FAIL = "fail", "待提升"


class Gender(models.TextChoices):
    MALE = "male", "男"
    FEMALE = "female", "女"
    UNKNOWN = "unknown", "未填写"


class AccountStatus(models.TextChoices):
    ACTIVE = "active", "正常"
    DISABLED = "disabled", "禁用"


class FileCategory(models.TextChoices):
    AVATAR = "avatar", "头像"
    QUESTION_IMAGE = "question_image", "试题图片"
    QUESTION_AUDIO = "question_audio", "试题音频"
    STUDENT_WORK = "student_work", "学生作品"
    CERTIFICATE = "certificate", "证书"
    IMPORT = "import", "导入文件"
    OTHER = "other", "其他"


# 主观题/作品题需要人工或 AI 评分
SUBJECTIVE_TYPES = {
    QuestionType.SHORT_ANSWER,
    QuestionType.IMAGE_UPLOAD,
    QuestionType.AUDIO_UPLOAD,
}
