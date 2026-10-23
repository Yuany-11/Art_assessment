from django.apps import AppConfig


class QuestionBankConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "questionbank"
    verbose_name = "题库（对接后端 B）"
