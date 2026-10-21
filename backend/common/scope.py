"""数据范围解析：所有业务接口复用同一套 scope 规则。"""
from common.enums import OrganizationLevel, Role


def descendant_org_ids(org) -> list[int]:
    """返回组织自身及全部下级组织 ID。"""
    from apps.organizations.models import Organization

    ids = [org.id]
    frontier = [org.id]
    while frontier:
        children = list(
            Organization.objects.filter(
                parent_id__in=frontier, deleted_at__isnull=True
            ).values_list("id", flat=True)
        )
        frontier = [child for child in children if child not in ids]
        ids.extend(frontier)
    return ids


def resolve_scope(user) -> dict:
    """返回当前用户可访问的组织与班级范围。

    level: province / city / district / school / classes / self
    orgIds: 可访问组织 ID 列表
    classIds: 可访问班级 ID 列表（P2 接入班级后生效）
    """
    if user.role == Role.PROVINCE_ADMIN:
        from apps.organizations.models import Organization

        return {
            "level": OrganizationLevel.PROVINCE,
            "orgIds": list(
                Organization.objects.filter(deleted_at__isnull=True).values_list("id", flat=True)
            ),
            "classIds": [],
        }

    org = user.org
    if org is None:
        return {"level": "self", "orgIds": [], "classIds": []}

    if user.role in {Role.SCHOOL_ADMIN, Role.DISTRICT_ADMIN, Role.CITY_ADMIN}:
        return {
            "level": org.level,
            "orgIds": descendant_org_ids(org),
            "classIds": [],
        }

    return {"level": "self", "orgIds": [org.id], "classIds": []}
