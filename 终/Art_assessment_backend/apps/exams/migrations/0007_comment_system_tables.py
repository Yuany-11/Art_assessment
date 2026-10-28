"""补齐 MySQL 中所有表和字段注释。

Django 内置表（auth_*、django_*、sessions）以及自动生成的主键 id 无法在模型上
声明 db_comment，这里用一次性 DDL 补齐；业务表的注释由各模型的 db_comment /
db_table_comment 负责。仅在 MySQL 下执行，SQLite 等其它数据库自动跳过。
"""
from django.db import migrations

BUILTIN_TABLE_COMMENTS = {
    "django_content_type": "内容类型表（Django 内置）",
    "auth_permission": "权限表（Django 内置）",
    "auth_group": "权限组表（Django 内置）",
    "auth_group_permissions": "权限组-权限关联表（Django 内置）",
    "users_groups": "用户-权限组关联表（Django 内置）",
    "users_user_permissions": "用户-权限关联表（Django 内置）",
    "django_admin_log": "管理后台操作日志表（Django 内置）",
    "django_migrations": "数据库迁移记录表（Django 内置）",
    "django_session": "登录会话表（Django 内置）",
}

BUILTIN_COLUMN_COMMENTS = {
    ("auth_group", "name"): "权限组名称",
    ("auth_group_permissions", "group_id"): "权限组 ID",
    ("auth_group_permissions", "permission_id"): "权限 ID",
    ("auth_permission", "name"): "权限名称",
    ("auth_permission", "content_type_id"): "内容类型 ID",
    ("auth_permission", "codename"): "权限编码",
    ("users_groups", "user_id"): "用户 ID",
    ("users_groups", "group_id"): "权限组 ID",
    ("users_user_permissions", "user_id"): "用户 ID",
    ("users_user_permissions", "permission_id"): "权限 ID",
    ("django_admin_log", "action_time"): "操作时间",
    ("django_admin_log", "object_id"): "操作对象 ID",
    ("django_admin_log", "object_repr"): "操作对象描述",
    ("django_admin_log", "action_flag"): "操作类型：1 新增 / 2 修改 / 3 删除",
    ("django_admin_log", "change_message"): "变更内容（JSON 文本）",
    ("django_admin_log", "content_type_id"): "内容类型 ID",
    ("django_admin_log", "user_id"): "操作用户 ID",
    ("django_content_type", "app_label"): "应用标签",
    ("django_content_type", "model"): "模型名称",
    ("django_migrations", "app"): "应用名称",
    ("django_migrations", "name"): "迁移文件名称",
    ("django_migrations", "applied"): "应用时间",
    ("django_session", "session_key"): "会话键",
    ("django_session", "session_data"): "会话数据（编码后）",
    ("django_session", "expire_date"): "过期时间",
    ("users", "password"): "密码哈希",
    ("users", "last_login"): "最后登录时间",
    ("users", "is_superuser"): "是否超级管理员",
}

# 这些列在模型里无法声明 db_comment（Django 自动主键），统一补成“主键”。
AUTO_ID_COMMENT = "主键"


def forwards(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "mysql":
        return

    with connection.cursor() as cursor:
        # 1. 自动递增主键（所有业务表 + 内置关联表）
        cursor.execute(
            """
            SELECT TABLE_NAME, COLUMN_TYPE
              FROM information_schema.COLUMNS
             WHERE TABLE_SCHEMA = DATABASE()
               AND COLUMN_NAME = 'id'
               AND COLUMN_COMMENT = ''
               AND EXTRA LIKE '%auto_increment%'
            """
        )
        for table, column_type in cursor.fetchall():
            cursor.execute(
                f"ALTER TABLE `{table}` MODIFY COLUMN `id` {column_type} "
                f"NOT NULL AUTO_INCREMENT COMMENT %s",
                [AUTO_ID_COMMENT],
            )

        # 2. 内置表注释
        for table, comment in BUILTIN_TABLE_COMMENTS.items():
            cursor.execute(f"ALTER TABLE `{table}` COMMENT = %s", [comment])

        # 3. 内置表字段注释（这些列均无 DEFAULT，按信息模式原样重建定义）
        for (table, column), comment in BUILTIN_COLUMN_COMMENTS.items():
            cursor.execute(
                """
                SELECT COLUMN_TYPE, IS_NULLABLE
                  FROM information_schema.COLUMNS
                 WHERE TABLE_SCHEMA = DATABASE()
                   AND TABLE_NAME = %s
                   AND COLUMN_NAME = %s
                """,
                [table, column],
            )
            row = cursor.fetchone()
            if not row:
                continue
            column_type, is_nullable = row
            null_sql = "NULL" if is_nullable == "YES" else "NOT NULL"
            cursor.execute(
                f"ALTER TABLE `{table}` MODIFY COLUMN `{column}` {column_type} "
                f"{null_sql} COMMENT %s",
                [comment],
            )


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0006_alter_notification_table_comment_and_more"),
        ("accounts", "0004_alter_importtask_table_comment_and_more"),
        ("classes", "0002_alter_class_table_comment_and_more"),
        ("files", "0003_fileobject_subject"),
        ("organizations", "0004_alter_organization_table_comment_and_more"),
        ("qbank", "0004_chapter_content"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("admin", "0003_logentry_add_action_flag_choices"),
        ("sessions", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
