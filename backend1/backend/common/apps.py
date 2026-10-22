from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "common"
    verbose_name = "公共组件"

    def ready(self):
        from common import schema  # noqa: F401 - 注册 OpenAPI Bearer 鉴权方案
