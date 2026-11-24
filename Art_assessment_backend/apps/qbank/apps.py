from django.apps import AppConfig


class QbankConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.qbank"
    label = "qbank"
    verbose_name = "题库管理"
