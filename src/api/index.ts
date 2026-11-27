import { download, request } from './client'
import type {
  Account,
  AccountKind,
  AiSuggestionResult,
  AnswerFile,
  AudioTags,
  AuthSession,
  Assessment,
  Attempt,
  AttemptReview,
  Certificate,
  Chapter,
  ChapterQuestionBundle,
  ClassRequest,
  Course,
  GradingTask,
  LearningReport,
  NotificationItem,
  OperationLog,
  OrgOption,
  PageResult,
  Paper,
  PaperReviewLog,
  PaperReviewResult,
  QgenCatalog,
  QgenGenerateResult,
  Question,
  Score,
  SchoolClass,
  StudentArtwork,
  Subject,
  WrongQuestionDetail,
  WrongQuestionItem,
  WrongQuestionStatistics
} from '@/types'

const ACCOUNT_ROLE: Record<AccountKind, string> = {
  teachers: 'teacher',
  students: 'student',
  schools: 'school_admin',
  districts: 'district_admin',
  cities: 'city_admin'
}

function query(params: Record<string, string | number | undefined>) {
  return Object.fromEntries(Object.entries(params).filter(([, value]) => value !== undefined && value !== ''))
}

export const api = {
  auth: {
    login: (username: string, password: string, role?: string): Promise<AuthSession> =>
      request({
        url: '/auth/login',
        method: 'POST',
        data: role ? { username, password, role } : { username, password }
      }),
    logout: (refreshToken: string): Promise<{ loggedOut: boolean }> =>
      request({ url: '/auth/logout', method: 'POST', data: { refreshToken } }),
    me: (): Promise<import('@/types').UserProfile> => request({ url: '/auth/me' })
  },
  classes: {
    list: (params: Record<string, string | number | undefined> = {}): Promise<PageResult<SchoolClass>> =>
      request({ url: '/classes', params: query(params) }),
    search: (classCode: string): Promise<SchoolClass | null> =>
      request({ url: '/classes/search', params: { classCode } }),
    detail: (id: number): Promise<SchoolClass> =>
      request<SchoolClass>({ url: `/classes/${id}` }),
    create: (values: Partial<SchoolClass>): Promise<SchoolClass> =>
      request({ url: '/classes', method: 'POST', data: values }),
    update: (id: number, values: Partial<SchoolClass>): Promise<SchoolClass> =>
      request({ url: `/classes/${id}`, method: 'PATCH', data: values }),
    remove: (id: number): Promise<{ deleted: boolean }> =>
      request({ url: `/classes/${id}`, method: 'DELETE' }),
    requests: async (id: number): Promise<ClassRequest[]> =>
      (await request<PageResult<ClassRequest>>({ url: `/classes/${id}/requests`, params: { pageSize: 100 } })).list,
    pendingRequests: async (params: Record<string, string | number | undefined> = {}): Promise<ClassRequest[]> =>
      (await request<PageResult<ClassRequest>>({ url: '/classes/requests', params: query({ pageSize: 100, ...params }) })).list,
    review: (classId: number, requestId: number, action: 'approve' | 'reject', comment: string): Promise<ClassRequest> =>
      request({ url: `/classes/${classId}/requests/${requestId}/review`, method: 'POST', data: { action, comment } }),
    request: (type: 'join' | 'change' | 'leave', classId: number, reason: string, targetClassId?: number, subject?: 'music' | 'art'): Promise<ClassRequest> => {
      const url = type === 'join' ? `/classes/${classId}/join` : type === 'leave' ? `/classes/${classId}/leave` : `/classes/${classId}/change`
      return request({ url, method: 'POST', data: { reason, targetClassId, ...(subject ? { subject } : {}) } })
    },
    students: (classId: number, params: Record<string, string | number | undefined> = {}): Promise<PageResult<Account>> =>
      request({ url: `/classes/${classId}/students`, params: query(params) }),
    removeStudent: (classId: number, studentId: number): Promise<{ removed: boolean }> =>
      request({ url: `/classes/${classId}/students/${studentId}`, method: 'DELETE' }),
    importStudents: async (classId: number, file: File): Promise<Record<string, unknown>> => {
      const form = new FormData()
      form.append('file', file)
      form.append('mode', 'append')
      return request({ url: `/classes/${classId}/students/import`, method: 'POST', data: form })
    }
  },
  accounts: {
    list: (kind: AccountKind, params: Record<string, string | number | undefined> = {}): Promise<PageResult<Account>> =>
      request({ url: '/accounts', params: query({ ...params, role: ACCOUNT_ROLE[kind] }) }),
    detail: (id: number): Promise<Account> =>
      request({ url: `/accounts/${id}` }),
    orgOptions: (params: { level: 'province' | 'city' | 'district' | 'school'; parentId?: number; keyword?: string }): Promise<{ list: OrgOption[] }> =>
      request({ url: '/accounts/org-options', params: query(params) }),
    create: (kind: AccountKind, values: Record<string, unknown>): Promise<Account> =>
      request({ url: `/accounts/${kind === 'teachers' ? 'teachers' : kind === 'students' ? 'students' : kind}`, method: 'POST', data: values }),
    update: (id: number, values: Record<string, unknown>): Promise<Account> =>
      request({ url: `/accounts/${id}`, method: 'PATCH', data: values }),
    remove: (id: number): Promise<{ deleted: boolean }> =>
      request({ url: `/accounts/${id}`, method: 'DELETE' }),
    resetPassword: (id: number, newPassword?: string): Promise<{ accountId: number; temporaryPassword: string }> =>
      request({
        url: `/accounts/${id}/reset-password`,
        method: 'POST',
        data: newPassword ? { newPassword } : {}
      }),
    temporaryPassword: (id: number): Promise<{ accountId: number; temporaryPassword: string; expiresIn: number }> =>
      request({ url: `/accounts/${id}/temporary-password` }),
    import: async (kind: AccountKind, file: File, classId?: number): Promise<Record<string, unknown>> => {
      const form = new FormData()
      form.append('file', file)
      if (kind === 'students') {
        if (!classId) throw new Error('请先选择导入的目标班级')
        return request({ url: `/classes/${classId}/students/import`, method: 'POST', data: form })
      }
      return request({ url: '/accounts/teachers/import', method: 'POST', data: form })
    },
    importTask: (taskId: string): Promise<Record<string, unknown>> =>
      request({ url: `/accounts/imports/${taskId}` })
  },
  papers: {
    list: (params: Record<string, string | number | undefined> = {}): Promise<PageResult<Paper>> =>
      request({ url: '/papers', params: query(params) }),
    detail: (id: number): Promise<Paper> =>
      request({ url: `/papers/${id}` }),
    create: (values: Record<string, unknown>, mode: 'manual' | 'auto'): Promise<Paper> =>
      request({ url: `/papers/${mode}`, method: 'POST', data: values }),
    update: (id: number, values: Partial<Paper>): Promise<Paper> =>
      request({ url: `/papers/${id}`, method: 'PATCH', data: values }),
    draft: (id: number, values: Record<string, unknown>): Promise<Paper> =>
      request({ url: `/papers/${id}/draft`, method: 'PATCH', data: values }),
    remove: (id: number): Promise<{ deleted: boolean }> =>
      request({ url: `/papers/${id}`, method: 'DELETE' }),
    downloadMaterials: (id: number): Promise<Blob> =>
      download(`/papers/${id}/materials/download`),
    downloadAnswers: (id: number): Promise<Blob> =>
      download(`/papers/${id}/answers/download`),
    submitReview: (id: number, version: number, comment?: string): Promise<PaperReviewResult> =>
      request({ url: `/papers/${id}/submit-review`, method: 'POST', data: { version, comment } }),
    review: (id: number, action: 'approve' | 'reject', comment: string, version: number): Promise<PaperReviewResult> =>
      request({ url: `/papers/${id}/review`, method: 'POST', data: { action, comment, version } }),
    reviewHistory: (id: number): Promise<PaperReviewLog[]> =>
      request({ url: `/papers/${id}/review-history` })
  },
  assessments: {
    list: (params: Record<string, string | number | undefined> = {}): Promise<PageResult<Assessment>> =>
      request({ url: '/assessments', params: query(params) }),
    detail: (id: number): Promise<Assessment> =>
      request({ url: `/assessments/${id}` }),
    create: (values: Record<string, unknown>): Promise<Assessment> =>
      request({ url: '/assessments', method: 'POST', data: values }),
    withdraw: (id: number, reason: string): Promise<Assessment> =>
      request({ url: `/assessments/${id}/withdraw`, method: 'POST', data: { reason } })
  },
  questions: {
    list: (params: Record<string, string | number | undefined> = {}): Promise<PageResult<Question>> =>
      request({ url: '/questions', params: query(params) }),
    detail: (id: number): Promise<Question> =>
      request({ url: `/questions/${id}` }),
    create: (values: Record<string, unknown>): Promise<Question> =>
      request({ url: '/questions', method: 'POST', data: values }),
    update: (id: number, values: Partial<Question>): Promise<Question> =>
      request({ url: `/questions/${id}`, method: 'PATCH', data: values }),
    review: (id: number, action: 'approve' | 'reject', comment: string): Promise<Question> =>
      request({ url: `/questions/${id}/review`, method: 'POST', data: { action, comment } }),
    submitReview: (id: number, remark?: string): Promise<Question> =>
      request({ url: `/questions/${id}/submit-review`, method: 'POST', data: { remark } }),
    remove: (id: number): Promise<{ deleted: boolean }> =>
      request({ url: `/questions/${id}`, method: 'DELETE' }),
    favorites: (): Promise<{ questionIds: number[] }> =>
      request({ url: '/questions/favorites' }),
    toggleFavorite: (id: number): Promise<{ questionId: number; favorite: boolean }> =>
      request({ url: `/questions/${id}/favorite`, method: 'POST', data: {} }),
    similarAudio: (id: number, limit = 5): Promise<{ source: Record<string, unknown>; items: Question[] }> =>
      request({ url: `/questions/${id}/similar-audio`, params: { limit } }),
    qgenCatalog: (): Promise<QgenCatalog> =>
      request({ url: '/questions/qgen/catalog' }),
    qgenGenerate: (values: {
      unitId: string
      knowledgePoint: string
      type: string
      difficulty: number
    }): Promise<QgenGenerateResult> =>
      request({ url: '/questions/qgen/generate', method: 'POST', data: values })
  },
  courses: {
    list: (params: Record<string, string | number | undefined> = {}): Promise<PageResult<Course>> =>
      request({ url: '/courses', params: query(params) }),
    create: (values: Partial<Course>): Promise<Course> =>
      request({ url: '/courses', method: 'POST', data: values }),
    update: (id: number, values: Partial<Course>): Promise<Course> =>
      request({ url: `/courses/${id}`, method: 'PATCH', data: values }),
    remove: (id: number): Promise<{ deleted: boolean }> =>
      request({ url: `/courses/${id}`, method: 'DELETE' }),
    chapters: (id: number): Promise<Chapter[]> =>
      request({ url: `/courses/${id}/chapters` }),
    chapterQuestions: (id: number): Promise<ChapterQuestionBundle> =>
      request({ url: `/chapters/${id}/questions` }),
    createChapter: (id: number, values: Partial<Chapter>): Promise<Chapter> =>
      request({ url: `/courses/${id}/chapters`, method: 'POST', data: values }),
    updateChapter: (id: number, values: Partial<Chapter>): Promise<Chapter> =>
      request({ url: `/chapters/${id}`, method: 'PATCH', data: values }),
    removeChapter: (id: number): Promise<{ deleted: boolean }> =>
      request({ url: `/chapters/${id}`, method: 'DELETE' })
  },
  scores: {
    list: (params: Record<string, string | number | undefined> = {}): Promise<PageResult<Score>> =>
      request({ url: '/scores', params: query(params) }),
    mine: (params: Record<string, string | number | undefined> = {}): Promise<PageResult<Score>> =>
      request({ url: '/scores/me', params: query(params) }),
    detail: (id: number): Promise<Score> =>
      request({ url: `/scores/${id}` }),
    manual: (values: Record<string, unknown>): Promise<Score> =>
      request({ url: '/scores/manual', method: 'POST', data: values }),
    import: (file: File, assessmentId?: number, subject?: 'music' | 'art'): Promise<Record<string, unknown>> => {
      if (!assessmentId || !subject) throw new Error('请先选择导入的测评')
      const form = new FormData()
      form.append('file', file)
      form.append('assessmentId', String(assessmentId))
      form.append('subject', subject)
      return request({ url: '/scores/import', method: 'POST', data: form })
    },
    importTask: (taskId: string): Promise<Record<string, unknown>> =>
      request({ url: `/scores/imports/${taskId}` }),
    regrade: (id: number, reason: string): Promise<Score> =>
      request({ url: `/scores/${id}/regrade`, method: 'POST', data: { reason } })
  },
  dashboard: {
    summary: (): Promise<{
      month: string
      pendingPublishPapers: number | null
      runningAssessments: number | null
      pendingQuestions: number | null
      pendingReviewPapers: number | null
      participationRate: number | null
    }> => request({ url: '/dashboard/summary' })
  },
  statistics: {
    list: async (params: Record<string, string | number | undefined> = {}): Promise<{ list: import('@/types').StatRow[]; summary: { studentCount: number; participantCount: number; avgScore: number; participationRate: number } }> => {
      const result = await request<PageResult<import('@/types').StatRow>>({
        url: '/scores/statistics/list',
        params: query({ pageSize: 200, ...params })
      })
      const rows = result.list
      const studentCount = rows.reduce((sum, row) => sum + row.studentCount, 0)
      const participantCount = rows.reduce((sum, row) => sum + row.participantCount, 0)
      const weightedAvg = rows.reduce((sum, row) => sum + row.avgScore * row.studentCount, 0)
      return {
        list: rows,
        summary: {
          studentCount,
          participantCount,
          avgScore: studentCount ? weightedAvg / studentCount : 0,
          participationRate: studentCount ? participantCount / studentCount : 0
        }
      }
    },
    export: (params: Record<string, string | number | undefined> = {}): Promise<Blob> =>
      download('/scores/statistics/export', query(params))
  },
  logs: {
    list: (params: Record<string, string | number | undefined> = {}): Promise<PageResult<OperationLog>> =>
      request({ url: '/logs', params: query(params) }),
    detail: (id: number): Promise<OperationLog> =>
      request({ url: `/logs/${id}` })
  },
  certificates: {
    list: async (params: Record<string, string | number | undefined> = {}): Promise<Certificate[]> => {
      const result = await request<PageResult<Certificate>>({ url: '/certificates', params: query(params) })
      return result.list
    },
    detail: (id: number): Promise<Certificate> =>
      request({ url: `/certificates/${id}` }),
    download: (id: number): Promise<Blob> =>
      download(`/certificates/${id}/download`),
    generate: (assessmentId: number, subject: 'music' | 'art'): Promise<Record<string, unknown>> =>
      request({ url: '/certificates/generate', method: 'POST', data: { assessmentId, subject } })
  },
  attempts: {
    start: (assessmentId: number): Promise<Attempt> =>
      request({ url: `/assessments/${assessmentId}/attempts`, method: 'POST', data: { deviceType: 'web' } }),
    get: (attemptId: number): Promise<Attempt> =>
      request({ url: `/attempts/${attemptId}` }),
    review: (attemptId: number): Promise<AttemptReview> =>
      request({ url: `/attempts/${attemptId}/review` }),
    startPractice: (subject: 'music' | 'art', chapterId?: number): Promise<Attempt> =>
      request({ url: '/papers/practice/random', method: 'POST', data: { subject, chapterId } }),
    save: (attemptId: number, answers: Attempt['savedAnswers']): Promise<Record<string, unknown>> =>
      request({ url: `/attempts/${attemptId}/answers`, method: 'PATCH', data: { answers } }),
    uploadAnswer: (attemptId: number, file: File, subject: Subject): Promise<AnswerFile> => {
      const form = new FormData()
      form.append('file', file)
      // 与课外作品统一归类，练习/测评上传的图片和音频会显示在作品库与 media/student_work 目录
      form.append('category', 'student_work')
      form.append('subject', subject)
      form.append('bizId', String(attemptId))
      return request({ url: '/files', method: 'POST', data: form })
    },
    submit: (attemptId: number, submitType: 'manual' | 'auto' = 'manual'): Promise<Record<string, unknown>> =>
      request({ url: `/attempts/${attemptId}/submit`, method: 'POST', data: { submitType, finalAnswers: [] } })
  },
  grading: {
    list: (params: Record<string, string | number | undefined> = {}): Promise<PageResult<GradingTask>> =>
      request({ url: '/grading/tasks', params: query(params) }),
    detail: (attemptId: number): Promise<GradingTask> =>
      request({ url: `/grading/attempts/${attemptId}` }),
    submit: (attemptId: number, items: Array<{ questionId: number; score: number; comment: string | null }>, finalize: boolean, reason: string, version?: number): Promise<Record<string, unknown>> =>
      request({ url: `/grading/attempts/${attemptId}/scores`, method: 'PATCH', data: { items, finalize, reason, version } }),
    aiSuggestions: (attemptId: number, force = false): Promise<AiSuggestionResult> =>
      request({ url: `/grading/attempts/${attemptId}/ai-suggestions`, method: 'POST', data: { force } })
  },
  reports: {
    get: (studentId: number, subject?: 'music' | 'art'): Promise<LearningReport | null> =>
      request({ url: `/students/${studentId}/learning-report`, params: query({ subject }) })
  },
  files: {
    upload: (file: File, category: string, extra: { subject?: string; bizId?: number } = {}): Promise<{ fileId: number; url: string; name: string; mimeType: string; size: number; category: string }> => {
      const form = new FormData()
      form.append('file', file)
      form.append('category', category)
      if (extra.subject) form.append('subject', extra.subject)
      if (extra.bizId) form.append('bizId', String(extra.bizId))
      return request({ url: '/files', method: 'POST', data: form })
    },
    audioAnalysis: (fileId: number): Promise<AudioTags> =>
      request({ url: `/files/${fileId}/audio-analysis` }),
    analyzeAudio: (fileId: number, force = false): Promise<AudioTags> =>
      request({ url: `/files/${fileId}/audio-analysis`, method: 'POST', data: { force } })
  },
  artworks: {
    list: (): Promise<StudentArtwork[]> =>
      request({ url: '/files', params: { category: 'student_work' } }),
    upload: (file: File, subject: 'music' | 'art'): Promise<StudentArtwork> => {
      const form = new FormData()
      form.append('file', file)
      form.append('category', 'student_work')
      form.append('subject', subject)
      return request({ url: '/files', method: 'POST', data: form })
    },
    remove: (id: number): Promise<{ deleted: boolean }> =>
      request({ url: `/files/${id}`, method: 'DELETE' }),
    review: (id: number, score: number, comment: string): Promise<StudentArtwork> =>
      request({ url: `/files/${id}/review`, method: 'PATCH', data: { score, comment } })
  },
  wrongQuestions: {
    list: (params: Record<string, string | number | boolean | undefined> = {}): Promise<PageResult<WrongQuestionItem>> =>
      request({ url: '/students/me/wrong-questions', params: query(params as Record<string, string | number | undefined>) }),
    detail: (id: number): Promise<WrongQuestionDetail> =>
      request({ url: `/students/me/wrong-questions/${id}` }),
    update: (id: number, values: { masteryStatus?: WrongQuestionDetail['masteryStatus']; note?: string | null }): Promise<WrongQuestionDetail> =>
      request({ url: `/students/me/wrong-questions/${id}`, method: 'PATCH', data: values }),
    remove: (id: number): Promise<{ deleted: boolean; wrongId: number }> =>
      request({ url: `/students/me/wrong-questions/${id}`, method: 'DELETE' }),
    redo: (id: number): Promise<{ attemptId: number; wrongId: number; question: unknown }> =>
      request({ url: `/students/me/wrong-questions/${id}/redo`, method: 'POST', data: {} }),
    statistics: (): Promise<WrongQuestionStatistics> =>
      request({ url: '/students/me/wrong-questions/statistics' })
  },
  notifications: {
    list: (params: Record<string, string | number | boolean | undefined> = {}): Promise<PageResult<NotificationItem> & { unreadCount: number }> =>
      request({ url: '/notifications', params: query(params as Record<string, string | number | undefined>) }),
    read: (id: number): Promise<{ id: number; read: boolean; readAt: string }> =>
      request({ url: `/notifications/${id}/read`, method: 'PATCH', data: {} }),
    readAll: (): Promise<{ updatedCount: number; readAt: string }> =>
      request({ url: '/notifications/read-all', method: 'PATCH', data: {} })
  },
  profile: {
    update: (values: Record<string, unknown>): Promise<Record<string, unknown>> =>
      request({ url: '/auth/me', method: 'PATCH', data: values }),
    changePassword: (oldPassword: string, newPassword: string): Promise<Record<string, unknown>> =>
      request({ url: '/auth/password', method: 'PATCH', data: { oldPassword, newPassword } })
  }
}
