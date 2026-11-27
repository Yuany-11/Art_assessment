import { ElMessage } from 'element-plus'
import type { Subject, UserProfile } from '@/types'

export const TEACHER_SUBJECT_DENIED = '您不是该科的老师，无法使用该功能'

const SUBJECTS: Subject[] = ['music', 'art']

/** 教师实际任教的学科：优先使用后端推导的 teacherSubjects，旧会话回退到档案学科。 */
export function teacherSubjects(user: UserProfile | null | undefined): Subject[] {
  if (!user || user.role !== 'teacher') return []
  const subjects = (user.teacherSubjects ?? []).filter((item): item is Subject =>
    SUBJECTS.includes(item)
  )
  if (subjects.length) return Array.from(new Set(subjects))
  return user.subject ? [user.subject] : []
}

export function isHeadTeacher(user: UserProfile | null | undefined): boolean {
  return Boolean(user?.role === 'teacher' && user.isHeadTeacher)
}

export function isSubjectTeacher(
  user: UserProfile | null | undefined,
  subject: Subject
): boolean {
  return teacherSubjects(user).includes(subject)
}

/** 教师切换学科时调用：非本学科直接拦截并提示。非教师角色始终放行。 */
export function ensureTeacherSubject(
  user: UserProfile | null | undefined,
  subject: Subject | '' | null | undefined
): boolean {
  if (!user || user.role !== 'teacher' || !subject) return true
  if (isSubjectTeacher(user, subject)) return true
  ElMessage.warning(TEACHER_SUBJECT_DENIED)
  return false
}
