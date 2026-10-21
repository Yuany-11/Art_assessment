"""组织层级：省 / 市州 / 区县 / 学校 单表自关联。"""
from django.db import models

from common.enums import OrganizationLevel
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
    code = models.CharField("组织编码", max_length=64, unique=True)
    status = models.CharField(
        "状态", max_length=16, choices=Status.choices, default=Status.ACTIVE
    )

    class Meta:
        db_table = "organizations"
        ordering = ["level", "id"]

    def __str__(self) -> str:
        return self.name
