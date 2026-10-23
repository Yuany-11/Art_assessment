"""生成演示组织层级，可重复执行。"""
from django.core.management.base import BaseCommand

from apps.organizations.models import Organization
from common.enums import OrganizationLevel


class Command(BaseCommand):
    help = "初始化演示组织：1 个省、1 个市州、1 个区县、1 所学校"

    def handle(self, *args, **options):
        province, _ = Organization.objects.update_or_create(
            code="DEMO-PROVINCE",
            defaults={"level": OrganizationLevel.PROVINCE, "name": "示例省", "parent": None},
        )
        city, _ = Organization.objects.update_or_create(
            code="DEMO-CITY",
            defaults={"level": OrganizationLevel.CITY, "name": "示例市", "parent": province},
        )
        district, _ = Organization.objects.update_or_create(
            code="DEMO-DISTRICT",
            defaults={"level": OrganizationLevel.DISTRICT, "name": "示例区", "parent": city},
        )
        Organization.objects.update_or_create(
            code="DEMO-SCHOOL",
            defaults={"level": OrganizationLevel.SCHOOL, "name": "示范中学", "parent": district},
        )
        self.stdout.write(self.style.SUCCESS("演示组织初始化完成"))
