"""角色菜单树组装。"""
from ..models import MenuItem


def build_menu_tree(role: str) -> list[dict]:
    items = list(
        MenuItem.objects.filter(role=role, deleted_at__isnull=True).order_by("sort_order", "id")
    )
    nodes = {
        item.code: {
            "id": item.code,
            "parentId": item.parent_code,
            "name": item.name,
            "path": item.path,
            "icon": item.icon,
            "sortOrder": item.sort_order,
            "permission": item.permission,
            "children": [],
        }
        for item in items
    }

    roots: list[dict] = []
    for item in items:
        node = nodes[item.code]
        parent = nodes.get(item.parent_code) if item.parent_code else None
        if parent is None:
            roots.append(node)
        else:
            parent["children"].append(node)
    return roots
