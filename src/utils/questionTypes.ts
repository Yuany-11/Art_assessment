import type { Subject, UserProfile } from '@/types'

/** 题型中文名。所有页面共用，避免各页各写一份。 */
export const QUESTION_TYPE_LABELS: Record<string, string> = {
  single_choice: '单选题',
  multiple_choice: '多选题',
  true_false: '判断题',
  fill_blank: '填空题',
  short_answer: '简答题',
  listening: '听赏题',
  audio_choice_judge: '音频选择判断题',
  image_choice_judge: '图像选择判断题',
  image_upload: '图片作品',
  audio_upload: '音频作品'
}

/** 后端未下发映射时的兜底（与 common/subject_types.py 保持一致）。 */
const FALLBACK_TYPES: Record<string, string[]> = {
  art: ['single_choice', 'multiple_choice', 'true_false', 'fill_blank', 'image_upload', 'image_choice_judge'],
  music: ['single_choice', 'multiple_choice', 'true_false', 'fill_blank', 'listening', 'audio_upload', 'audio_choice_judge']
}

export function allowedSubjects(user: UserProfile | null | undefined): Subject[] {
  if (!user) return []
  if (user.allowedSubjects?.length) return user.allowedSubjects
  if (user.role === 'teacher') {
    if (user.teacherSubjects?.length) return user.teacherSubjects
    return user.subject ? [user.subject] : []
  }
  if (user.role && user.role !== 'student') return ['music', 'art']
  return []
}

export function questionTypesForSubject(
  user: UserProfile | null | undefined,
  subject: string
): string[] {
  const fromApi = user?.questionTypesBySubject?.[subject]
  if (fromApi?.length) return fromApi
  return FALLBACK_TYPES[subject] ?? []
}

export function allowedQuestionTypes(user: UserProfile | null | undefined): string[] {
  if (user?.allowedQuestionTypes?.length) return user.allowedQuestionTypes
  const result: string[] = []
  for (const subject of allowedSubjects(user)) {
    for (const type of questionTypesForSubject(user, subject)) {
      if (!result.includes(type)) result.push(type)
    }
  }
  return result
}

export function labelsForTypes(types: string[]): Record<string, string> {
  return Object.fromEntries(
    types.map((type) => [type, QUESTION_TYPE_LABELS[type] || type])
  )
}
