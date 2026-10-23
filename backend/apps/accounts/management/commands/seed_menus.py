"""初始化 7 个角色的菜单树，可重复执行。"""
from django.core.management.base import BaseCommand

from apps.accounts.models import MenuItem
from common.enums import Role

# (code, parent_code, name, path, icon, sort_order, permission)
MENUS: dict[str, list[tuple]] = {
    Role.STUDENT: [
        ("student.home", None, "首页", "/student/home", "HomeFilled", 10, None),
        ("student.class", None, "我的班级", "/student/class", "School", 20, None),
        ("student.assessments", None, "测评列表", "/student/assessments", "List", 30, None),
        ("student.scores", None, "我的成绩", "/student/scores", "DataLine", 40, "score.self.view"),
        ("student.wrong_questions", None, "错题本", "/student/wrong-questions", "Notebook", 45, "wrong_question.self.view"),
        ("student.certificates", None, "我的证书", "/student/certificates", "Medal", 50, "certificate.self.view"),
        ("student.growth", None, "成长曲线", "/student/growth", "TrendCharts", 60, "growth.self.view"),
        ("student.profile", None, "个人信息", "/student/profile", "User", 70, None),
        ("student.notifications", None, "通知中心", "/notifications", "Bell", 80, "notification.view"),
    ],
    Role.TEACHER: [
        ("teacher.workbench", None, "教师工作台", "/teacher/workbench", "Odometer", 10, None),
        ("teacher.classes", None, "班级管理", "/teacher/classes", "School", 20, "class.manage"),
        ("teacher.students", None, "学生管理", "/teacher/students", "User", 30, "student.view"),
        ("teacher.papers", None, "组卷管理", "/teacher/papers", "EditPen", 40, "paper.create"),
        ("teacher.assessments", None, "测评发布", "/teacher/assessments", "Promotion", 50, "assessment.publish"),
        ("teacher.grading", None, "人工评分", "/teacher/grading", "Checked", 60, "grading.submit"),
        ("teacher.scores", None, "成绩管理", "/teacher/scores", "DataLine", 70, "score.view"),
        ("teacher.profile", None, "个人资料", "/teacher/profile", "User", 80, None),
        ("teacher.notifications", None, "通知中心", "/notifications", "Bell", 90, "notification.view"),
    ],
    Role.SCHOOL_ADMIN: [
        ("school.dashboard", None, "学校概览", "/school/dashboard", "Odometer", 10, None),
        ("school.accounts", None, "账号管理", "/school/accounts", "User", 20, None),
        ("school.accounts.teachers", "school.accounts", "教师账号", "/school/accounts/teachers", None, 21, "account.teacher.manage"),
        ("school.accounts.students", "school.accounts", "学生账号", "/school/accounts/students", None, 22, "account.student.manage"),
        ("school.classes", None, "班级管理", "/school/classes", "School", 30, "class.manage"),
        ("school.papers", None, "组卷管理", "/school/papers", "EditPen", 40, "paper.create"),
        ("school.assessments", None, "测评管理", "/school/assessments", "Promotion", 50, "assessment.publish"),
        ("school.paper_review", None, "试卷审核", "/school/paper-review", "Checked", 55, "paper:review"),
        ("school.scores", None, "成绩管理", "/school/scores", "DataLine", 60, "score.view"),
        ("school.statistics", None, "数据统计", "/school/statistics", "PieChart", 70, "statistics.school.view"),
        ("school.certificates", None, "证书管理", "/school/certificates", "Medal", 80, "certificate.generate"),
        ("school.notifications", None, "通知中心", "/notifications", "Bell", 90, "notification.view"),
    ],
    Role.DISTRICT_ADMIN: [
        ("district.dashboard", None, "区县概览", "/district/dashboard", "Odometer", 10, None),
        ("district.accounts", None, "学校账号", "/district/accounts", "User", 20, "account.school.manage"),
        ("district.papers", None, "组卷管理", "/district/papers", "EditPen", 30, "paper.create"),
        ("district.assessments", None, "测评管理", "/district/assessments", "Promotion", 40, "assessment.publish"),
        ("district.paper_review", None, "试卷审核", "/district/paper-review", "Checked", 45, "paper:review"),
        ("district.scores", None, "成绩管理", "/district/scores", "DataLine", 50, "score.view"),
        ("district.statistics", None, "数据统计", "/district/statistics", "PieChart", 60, "statistics.district.view"),
        ("district.certificates", None, "证书查询", "/district/certificates", "Medal", 70, "certificate.view"),
        ("district.notifications", None, "通知中心", "/notifications", "Bell", 80, "notification.view"),
    ],
    Role.CITY_ADMIN: [
        ("city.dashboard", None, "市州概览", "/city/dashboard", "Odometer", 10, None),
        ("city.accounts", None, "账号管理", "/city/accounts", "User", 20, None),
        ("city.accounts.districts", "city.accounts", "区县账号", "/city/accounts/districts", None, 21, "account.district.manage"),
        ("city.accounts.schools", "city.accounts", "直属学校", "/city/accounts/schools", None, 22, "account.school.manage"),
        ("city.papers", None, "组卷管理", "/city/papers", "EditPen", 30, "paper.create"),
        ("city.assessments", None, "测评管理", "/city/assessments", "Promotion", 40, "assessment.publish"),
        ("city.paper_review", None, "试卷审核", "/city/paper-review", "Checked", 45, "paper:review"),
        ("city.scores", None, "成绩管理", "/city/scores", "DataLine", 50, "score.view"),
        ("city.statistics", None, "数据统计", "/city/statistics", "PieChart", 60, "statistics.city.view"),
        ("city.certificates", None, "证书查询", "/city/certificates", "Medal", 70, "certificate.view"),
        ("city.notifications", None, "通知中心", "/notifications", "Bell", 80, "notification.view"),
    ],
    Role.PROVINCE_ADMIN: [
        ("province.dashboard", None, "全省概览", "/province/dashboard", "Odometer", 10, None),
        ("province.accounts", None, "账号管理", "/province/accounts", "User", 20, None),
        ("province.accounts.cities", "province.accounts", "市州账号", "/province/accounts/cities", None, 21, "account.city.manage"),
        ("province.accounts.districts", "province.accounts", "区县账号", "/province/accounts/districts", None, 22, "account.district.manage"),
        ("province.accounts.schools", "province.accounts", "学校账号", "/province/accounts/schools", None, 23, "account.school.manage"),
        ("province.papers", None, "组卷管理", "/province/papers", "EditPen", 30, "paper.create"),
        ("province.assessments", None, "测评管理", "/province/assessments", "Promotion", 40, "assessment.publish"),
        ("province.paper_review", None, "试卷审核", "/province/paper-review", "Checked", 45, "paper:review"),
        ("province.scores", None, "成绩管理", "/province/scores", "DataLine", 50, "score.view"),
        ("province.statistics", None, "数据统计", "/province/statistics", "PieChart", 60, "statistics.province.view"),
        ("province.logs", None, "系统日志", "/province/logs", "Document", 70, "log.view"),
        ("province.notifications", None, "通知中心", "/notifications", "Bell", 80, "notification.view"),
    ],
    Role.QUESTION_ADMIN: [
        ("qbank.dashboard", None, "题库概览", "/qbank/dashboard", "Odometer", 10, None),
        ("qbank.questions", None, "试题管理", "/qbank/questions", "Document", 20, "question.create"),
        ("qbank.review", None, "试题审核", "/qbank/review", "Checked", 30, "question.review"),
        ("qbank.courses", None, "课程管理", "/qbank/courses", "Reading", 40, "course.manage"),
        ("qbank.chapters", None, "章节管理", "/qbank/chapters", "Collection", 50, "chapter.manage"),
        ("qbank.logs", None, "题库日志", "/qbank/logs", "Tickets", 60, "log.view"),
        ("qbank.notifications", None, "通知中心", "/notifications", "Bell", 70, "notification.view"),
    ],
}


class Command(BaseCommand):
    help = "初始化 7 个角色的菜单树"

    def handle(self, *args, **options):
        total = 0
        for role, items in MENUS.items():
            for code, parent, name, path, icon, sort_order, permission in items:
                MenuItem.objects.update_or_create(
                    code=code,
                    defaults={
                        "role": role,
                        "parent_code": parent,
                        "name": name,
                        "path": path,
                        "icon": icon,
                        "sort_order": sort_order,
                        "permission": permission,
                        "deleted_at": None,
                    },
                )
                total += 1
        self.stdout.write(self.style.SUCCESS(f"菜单初始化完成，共 {total} 项"))
