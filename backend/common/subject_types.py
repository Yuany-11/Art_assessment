"""学科与题型映射（单一来源）。

前端通过 ``/auth/me`` 的 ``questionTypesBySubject`` 拿到同一张表，禁止各自
硬编码题型列表。``short_answer`` 虽然仍在枚举中，但产品已取消简答题，
因此不进入任何学科的可用题型。
"""
from __future__ import annotations

from common.enums import QuestionType, Role, Subject

SUBJECT_QUESTION_TYPES: dict[str, tuple[str, ...]] = {
    Subject.ART: (
        QuestionType.SINGLE_CHOICE,
        QuestionType.MULTIPLE_CHOICE,
        QuestionType.TRUE_FALSE,
        QuestionType.FILL_BLANK,
        QuestionType.IMAGE_UPLOAD,
        QuestionType.IMAGE_CHOICE_JUDGE,
    ),
    Subject.MUSIC: (
        QuestionType.SINGLE_CHOICE,
        QuestionType.MULTIPLE_CHOICE,
        QuestionType.TRUE_FALSE,
        QuestionType.FILL_BLANK,
        QuestionType.LISTENING,
        QuestionType.AUDIO_UPLOAD,
        QuestionType.AUDIO_CHOICE_JUDGE,
    ),
}

AUDIO_QUESTION_TYPES = frozenset(
    {
        QuestionType.LISTENING,
        QuestionType.AUDIO_UPLOAD,
        QuestionType.AUDIO_CHOICE_JUDGE,
    }
)
ART_QUESTION_TYPES = frozenset({QuestionType.IMAGE_UPLOAD})

ADMIN_ROLES = frozenset(
    {
        Role.SCHOOL_ADMIN,
        Role.DISTRICT_ADMIN,
        Role.CITY_ADMIN,
        Role.PROVINCE_ADMIN,
        Role.QUESTION_ADMIN,
    }
)


def question_types_for_subject(subject: str) -> list[str]:
    return list(SUBJECT_QUESTION_TYPES.get(subject, ()))


def is_subject_question_type(subject: str, question_type: str) -> bool:
    return question_type in SUBJECT_QUESTION_TYPES.get(subject, ())


def allowed_subjects_for_user(user) -> list[str]:
    if user is None:
        return []
    if user.role == Role.TEACHER:
        profile = getattr(user, "teacher_profile", None)
        subject = getattr(profile, "subject", None)
        return [subject] if subject in Subject.values else []
    if user.role in ADMIN_ROLES:
        return [Subject.ART, Subject.MUSIC]
    return []


def allowed_question_types_for_user(user) -> list[str]:
    result: list[str] = []
    for subject in allowed_subjects_for_user(user):
        for item in SUBJECT_QUESTION_TYPES.get(subject, ()):
            if item not in result:
                result.append(item)
    return result


def question_types_by_subject_for_user(user) -> dict[str, list[str]]:
    return {
        subject: question_types_for_subject(subject)
        for subject in allowed_subjects_for_user(user)
    }


def ensure_subject_question_type(subject: str, question_type: str) -> None:
    """学科与题型不匹配时抛出 400，文案直接说明哪个学科不支持什么题型。"""
    from common.exceptions import BusinessError

    if is_subject_question_type(subject, question_type):
        return
    subject_label = dict(Subject.choices).get(subject, subject or "未知学科")
    type_label = dict(QuestionType.choices).get(question_type, question_type or "未知题型")
    raise BusinessError(400, f"{subject_label}学科不支持{type_label}题型")
