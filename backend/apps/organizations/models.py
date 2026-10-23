"""组织层级：省 / 市州 / 区县 / 学校 单表自关联。"""
from django.db import models

from common.enums import OrganizationLevel, SchoolType
from common.models import BaseModel


class Organization(BaseModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "正常"
        ARCHIVED = "archived", "已归档"

    level = models.CharField("层级", max_length=16, choices=OrganizationLevel.choices, db_index=True)
    parent = models.ForeignKey(
        "self",
        verbose_name="上级组织",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    name = models.CharField("组织名称", max_length=128)
    code = models.CharField("组织编码", max_length=64)
    status = models.CharField(
        "状态", max_length=16, choices=Status.choices, default=Status.ACTIVE
    )
    school_type = models.CharField(
        "学校类型", max_length=16, choices=SchoolType.choices, null=True, blank=True
    )
    address = models.CharField("地址", max_length=255, null=True, blank=True)

    class Meta:
        db_table = "organizations"
        ordering = ["level", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "code"], name="uniq_org_code_per_parent"
            )
        ]

    def __str__(self) -> str:
        return self.name
