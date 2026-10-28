"""组织层级：省 / 市州 / 区县 / 学校 单表自关联。"""
from django.db import models

from common.enums import OrganizationLevel, SchoolType
from common.models import BaseModel


class Organization(BaseModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "正常"
        ARCHIVED = "archived", "已归档"

    level = models.CharField(
        "层级",
        max_length=16,
        choices=OrganizationLevel.choices,
        db_index=True,
        db_comment="层级：province/city/district/school",
    )
    parent = models.ForeignKey(
        "self",
        verbose_name="上级组织",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
        db_comment="上级组织 ID，NULL 表示顶级",
    )
    name = models.CharField("组织名称", max_length=128, db_comment="组织名称")
    code = models.CharField(
        "组织编码", max_length=64, db_comment="组织编码（同一上级下唯一）"
    )
    status = models.CharField(
        "状态",
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_comment="状态：active/archived",
    )
    school_type = models.CharField(
        "学校类型",
        max_length=16,
        choices=SchoolType.choices,
        null=True,
        blank=True,
        db_comment="学校类型：primary/middle/high/combined，非学校为 NULL",
    )
    address = models.CharField(
        "地址", max_length=255, null=True, blank=True, db_comment="组织地址"
    )

    class Meta:
        db_table = "organizations"
        db_table_comment = "组织层级表（省/市州/区县/学校）"
        ordering = ["level", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "code"], name="uniq_org_code_per_parent"
            )
        ]

    def __str__(self) -> str:
        return self.name
