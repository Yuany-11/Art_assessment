from django.contrib import admin

from exams.models import (
    Assessment,
    Attempt,
    Certificate,
    GradingLog,
    ImportTask,
    LearningReport,
    Notification,
    Paper,
    PaperQuestion,
    Score,
    TotalScoreRule,
)


class PaperQuestionInline(admin.TabularInline):
    model = PaperQuestion
    extra = 0


@admin.register(Paper)
class PaperAdmin(admin.ModelAdmin):
    list_display = (
        "id", "title", "subject", "paper_type", "grade", "status",
        "version", "creator", "created_at",
    )
    list_filter = ("subject", "paper_type", "status", "grade")
    search_fields = ("title",)
    inlines = [PaperQuestionInline]


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "subject", "paper_type", "target_type", "status", "start_time", "end_time")
    list_filter = ("subject", "paper_type", "target_type", "status")
    search_fields = ("title",)


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ("id", "assessment", "student", "status", "grading_status", "total_score", "submitted_at")
    list_filter = ("status", "grading_status")
    search_fields = ("student__username", "student__real_name")


@admin.register(Score)
class ScoreAdmin(admin.ModelAdmin):
    list_display = ("id", "assessment", "student_name", "total_score", "level", "status", "source")
    list_filter = ("subject", "level", "status", "source")
    search_fields = ("student_name", "student_no")


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ("id", "certificate_no", "student_name", "assessment", "score", "level", "status")
    list_filter = ("subject", "level", "status")
    search_fields = ("certificate_no", "student_name")


@admin.register(TotalScoreRule)
class TotalScoreRuleAdmin(admin.ModelAdmin):
    list_display = (
        "id", "name", "teacher", "classroom", "subject", "term",
        "usual_weight", "formal_weight", "certificate_weight", "status", "version",
    )
    list_filter = ("subject", "status", "missing_policy")
    search_fields = ("name", "teacher__real_name", "classroom__name")


@admin.register(GradingLog)
class GradingLogAdmin(admin.ModelAdmin):
    list_display = ("id", "attempt", "operator", "action", "finalize", "version", "created_at")
    list_filter = ("action", "finalize")


@admin.register(ImportTask)
class ImportTaskAdmin(admin.ModelAdmin):
    list_display = ("id", "task_id", "assessment", "status", "total", "success_count", "fail_count")
    list_filter = ("status",)


@admin.register(LearningReport)
class LearningReportAdmin(admin.ModelAdmin):
    list_display = ("id", "report_id", "student", "subject", "generated_at")
    list_filter = ("subject",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "type", "title", "read", "created_at")
    list_filter = ("type", "read")
    search_fields = ("user__username", "title", "content")
