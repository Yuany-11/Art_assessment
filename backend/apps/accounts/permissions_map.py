"""角色 → 权限码映射，供 /auth/me 与前端按钮级权限使用。"""
from common.enums import Role

ROLE_PERMISSIONS: dict[str, list[str]] = {
    Role.STUDENT: [
        "assessment.attempt",
        "score.self.view",
        "certificate.self.view",
        "growth.self.view",
        "class.join",
    ],
    Role.TEACHER: [
        "class.manage",
        "student.view",
        "question.create",
        "question.edit.own",
        "paper.create",
        "assessment.publish",
        "score.view",
        "score.import",
        "grading.submit",
        "certificate.generate",
    ],
    Role.SCHOOL_ADMIN: [
        "account.teacher.manage",
        "account.student.manage",
        "class.manage",
        "paper.create",
        "assessment.publish",
        "score.view",
        "score.import",
        "statistics.school.view",
        "certificate.generate",
    ],
    Role.DISTRICT_ADMIN: [
        "account.school.manage",
        "paper.create",
        "assessment.publish",
        "score.view",
        "score.import",
        "statistics.district.view",
        "certificate.view",
    ],
    Role.CITY_ADMIN: [
        "account.district.manage",
        "account.school.manage",
        "paper.create",
        "assessment.publish",
        "score.view",
        "score.import",
        "statistics.city.view",
        "certificate.view",
    ],
    Role.PROVINCE_ADMIN: [
        "account.city.manage",
        "account.district.manage",
        "account.school.manage",
        "paper.create",
        "assessment.publish",
        "score.view",
        "score.import",
        "statistics.province.view",
        "log.view",
    ],
    Role.QUESTION_ADMIN: [
        "question.create",
        "question.edit",
        "question.review",
        "course.manage",
        "chapter.manage",
        "resource.manage",
        "log.view",
    ],
}


def permissions_for(role: str) -> list[str]:
    return list(ROLE_PERMISSIONS.get(role, []))
