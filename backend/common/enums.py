"""全局枚举，与 api.md 1.9 保持一致。"""
from django.db import models


class Role(models.TextChoices):
    STUDENT = "student", "学生"
    TEACHER = "teacher", "教师"
    SCHOOL_ADMIN = "school_admin", "学校管理员"
    DISTRICT_ADMIN = "district_admin", "区县管理员"
    CITY_ADMIN = "city_admin", "市州管理员"
    PROVINCE_ADMIN = "province_admin", "省级管理员"
    QUESTION_ADMIN = "question_admin", "题库管理员"


class OrganizationLevel(models.TextChoices):
    PROVINCE = "province", "省"
    CITY = "city", "市州"
    DISTRICT = "district", "区县"
    SCHOOL = "school", "学校"


class SchoolType(models.TextChoices):
    PRIMARY = "primary", "小学"
    MIDDLE = "middle", "初中"
    HIGH = "high", "高中"
    COMBINED = "combined", "九年/十二年一贯制"


class ClassStatus(models.TextChoices):
    ACTIVE = "active", "正常"
    ARCHIVED = "archived", "已归档"


class CourseStatus(models.TextChoices):
    ACTIVE = "active", "已发布"
    DISABLED = "disabled", "已停用"


class ResourceType(models.TextChoices):
    IMAGE = "image", "图片"
    AUDIO = "audio", "音频"


class OperationResult(models.TextChoices):
    SUCCESS = "success", "成功"
    FAILED = "failed", "失败"


class AccountStatus(models.TextChoices):
    ACTIVE = "active", "正常"
    DISABLED = "disabled", "禁用"


class Gender(models.TextChoices):
    MALE = "male", "男"
    FEMALE = "female", "女"
    UNKNOWN = "unknown", "未填写"


class Subject(models.TextChoices):
    MUSIC = "music", "音乐"
    ART = "art", "美术"


class FileCategory(models.TextChoices):
    AVATAR = "avatar", "头像"
    QUESTION_IMAGE = "question_image", "试题图片"
    QUESTION_AUDIO = "question_audio", "试题音频"
    STUDENT_WORK = "student_work", "学生作品"
    CERTIFICATE = "certificate", "证书"
    IMPORT = "import", "导入文件"
    OTHER = "other", "其他"


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


class ReviewAction(models.TextChoices):
    APPROVE = "approve", "通过"
    REJECT = "reject", "驳回"


class ScoreLevel(models.TextChoices):
    EXCELLENT = "excellent", "优秀"
    GOOD = "good", "良好"
    PASS = "pass", "合格"
    FAIL = "fail", "待提升"


class JoinRequestType(models.TextChoices):
    JOIN = "join", "加入"
    CHANGE = "change", "转班"
    LEAVE = "leave", "退出"


class JoinRequestStatus(models.TextChoices):
    PENDING = "pending", "待审核"
    APPROVED = "approved", "已通过"
    REJECTED = "rejected", "已驳回"
    CANCELLED = "cancelled", "已取消"
