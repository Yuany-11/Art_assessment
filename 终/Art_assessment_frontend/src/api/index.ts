import { mockApi } from './mock'
import { download, request } from './client'
import type {
  Account,
  AccountKind,
  AnswerFile,
  AuthSession,
  Assessment,
  Attempt,
  Certificate,
  Chapter,
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
  Question,
  Score,
  SchoolClass,
  StudentArtwork,
  Subject,
  WrongQuestionDetail,
  WrongQuestionItem,
  WrongQuestionStatistics
} from '@/types'

const useMock = import.meta.env.VITE_USE_MOCK !== 'false'

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
      request({ url: '/auth/logout', method: 'POST', data: { refreshToken } })
  },
  classes: {
    list: (params: Record<string, string | number | undefined> = {}): Promise<PageResult<SchoolClass>> =>
      useMock ? mockApi.listClasses(params) : request({ url: '/classes', params: query(params) }),
    search: (classCode: string): Promise<SchoolClass | null> =>
      useMock ? mockApi.searchClass(classCode) : request({ url: '/classes/search', params: { classCode } }),
    detail: async (id: number): Promise<SchoolClass> => {
      if (useMock) {
        const result = await mockApi.listClasses({ pageSize: 100 })
        const found = result.list.find((item) => item.id === id)
        if (!found) throw new Error('班级不存在')
        return found
      }
      return request<SchoolClass>({ url: `/classes/${id}` })
    },
    create: (values: Partial<SchoolClass>): Promise<SchoolClass> =>
      useMock ? mockApi.createClass(values) : request({ url: '/classes', method: 'POST', data: values }),
    update: (id: number, values: Partial<SchoolClass>): Promise<SchoolClass> =>
      useMock ? mockApi.updateClass(id, values) : request({ url: `/classes/${id}`, method: 'PATCH', data: values }),
    remove: (id: number): Promise<{ deleted: boolean }> =>
      useMock ? mockApi.removeClass(id) : request({ url: `/classes/${id}`, method: 'DELETE' }),
    requests: (id: number): Promise<ClassRequest[]> =>
      useMock ? mockApi.listClassRequests(id) : request({ url: `/classes/${id}/requests` }),
    review: (classId: number, requestId: number, action: 'approve' | 'reject', comment: string): Promise<ClassRequest> =>
      useMock ? mockApi.reviewClassRequest(requestId, action) : request({ url: `/classes/${classId}/requests/${requestId}/review`, method: 'POST', data: { action, comment } }),
    request: (type: 'join' | 'change' | 'leave', classId: number, reason: string, targetClassId?: number, subject?: 'music' | 'art'): Promise<ClassRequest> => {
      if (useMock) return mockApi.submitClassRequest(classId, type, reason, targetClassId)
      const url = type === 'join' ? `/classes/${classId}/join` : type === 'leave' ? `/classes/${classId}/leave` : `/classes/${classId}/change`
      return request({ url, method: 'POST', data: { reason, targetClassId, ...(subject ? { subject } : {}) } })
    },
    students: (classId: number, params: Record<string, string | number | undefined> = {}): Promise<PageResult<Account>> =>
      useMock ? mockApi.listClassStudents(classId, params) : request({ url: `/classes/${classId}/students`, params: query(params) }),
    removeStudent: (classId: number, studentId: number): Promise<{ removed: boolean }> =>
      useMock ? mockApi.removeClassStudent(classId, studentId) : request({ url: `/classes/${classId}/students/${studentId}`, method: 'DELETE' }),
    importStudents: async (classId: number, file: File): Promise<Record<string, unknown>> => {
      if (useMock) return mockApi.importClassStudents(file.name)
      const form = new FormData()
      form.append('file', file)
      form.append('mode', 'append')
      return request({ url: `/classes/${classId}/students/import`, method: 'POST', data: form })
    }
  },
  accounts: {
    list: (kind: AccountKind, params: Record<string, string | number | undefined> = {}): Promise<PageResult<Account>> =>
      useMock ? mockApi.listAccounts(kind, params) : request({ url: '/accounts', params: query({ ...params, role: ACCOUNT_ROLE[kind] }) }),
    detail: (id: number): Promise<Account> =>
      useMock ? mockApi.getAccount(id) : request({ url: `/accounts/${id}` }),
    orgOptions: (params: { level: 'city' | 'district' | 'school'; parentId?: number; keyword?: string }): Promise<{ list: OrgOption[] }> =>
      useMock ? mockApi.orgOptions(params) : request({ url: '/accounts/org-options', params: query(params) }),
    create: (kind: AccountKind, values: Record<string, unknown>): Promise<Account> =>
      useMock ? mockApi.createAccount(kind, values) : request({ url: `/accounts/${kind === 'teachers' ? 'teachers' : kind === 'students' ? 'students' : kind}`, method: 'POST', data: values }),
    update: (id: number, values: Partial<Account>): Promise<Account> =>
      useMock ? mockApi.updateAccount(id, values) : request({ url: `/accounts/${id}`, method: 'PATCH', data: values }),
    remove: (id: number): Promise<{ deleted: boolean }> =>
      useMock ? mockApi.removeAccount(id) : request({ url: `/accounts/${id}`, method: 'DELETE' }),
    resetPassword: (id: number): Promise<{ accountId: number; temporaryPassword: string }> =>
      useMock ? mockApi.resetPassword(id) : request({ url: `/accounts/${id}/reset-password`, method: 'POST', data: {} }),
    import: async (kind: AccountKind, file: File, classId?: number): Promise<Record<string, unknown>> => {
      if (useMock) return mockApi.importAccounts(kind, file.name)
      const form = new FormData()
      form.append('file', file)
      if (kind === 'students') {
        if (!classId) throw new Error('请先选择导入的目标班级')
        return request({ url: `/classes/${classId}/students/import`, method: 'POST', data: form })
      }
      return request({ url: '/accounts/teachers/import', method: 'POST', data: form })
    },
    importTask: (taskId: string): Promise<Record<string, unknown>> => {
      if (useMock) return mockApi.importAccounts('teachers', taskId)
      return request({ url: `/accounts/imports/${taskId}` })
    }
  },
  papers: {
    list: (params: Record<string, string | number | undefined> = {}): Promise<PageResult<Paper>> =>
      useMock ? mockApi.listPapers(params) : request({ url: '/papers', params: query(params) }),
    detail: (id: number): Promise<Paper> =>
      useMock ? mockApi.getPaper(id) : request({ url: `/papers/${id}` }),
    create: (values: Record<string, unknown>, mode: 'manual' | 'auto'): Promise<Paper> =>
      useMock ? mockApi.createPaper(values, mode) : request({ url: `/papers/${mode}`, method: 'POST', data: values }),
    update: (id: number, values: Partial<Paper>): Promise<Paper> =>
      useMock ? mockApi.updatePaper(id, values) : request({ url: `/papers/${id}`, method: 'PATCH', data: values }),
    draft: (id: number, values: Record<string, unknown>): Promise<Paper> =>
      useMock ? mockApi.updatePaper(id, values as Partial<Paper>) : request({ url: `/papers/${id}/draft`, method: 'PATCH', data: values }),
    remove: (id: number): Promise<{ deleted: boolean }> =>
      useMock ? mockApi.removePaper(id) : request({ url: `/papers/${id}`, method: 'DELETE' }),
    downloadMaterials: (id: number): Promise<Blob> =>
      useMock ? Promise.resolve(new Blob([`试卷 ${id} 的音频与图片材料清单\n`], { type: 'application/zip' })) : download(`/papers/${id}/materials/download`),
    downloadAnswers: (id: number): Promise<Blob> =>
      useMock ? Promise.resolve(new Blob([`试卷 ${id} 的标准答案与解析\n`], { type: 'application/pdf' })) : download(`/papers/${id}/answers/download`),
    submitReview: (id: number, version: number, comment?: string): Promise<PaperReviewResult> =>
      useMock ? mockApi.submitPaperReview(id, version, comment) : request({ url: `/papers/${id}/submit-review`, method: 'POST', data: { version, comment } }),
    review: (id: number, action: 'approve' | 'reject', comment: string, version: number): Promise<PaperReviewResult> =>
      useMock ? mockApi.reviewPaper(id, action, comment, version) : request({ url: `/papers/${id}/review`, method: 'POST', data: { action, comment, version } }),
    reviewHistory: (id: number): Promise<PaperReviewLog[]> =>
      useMock ? mockApi.listPaperReviews(id) : request({ url: `/papers/${id}/review-history` })
  },
  assessments: {
    list: (params: Record<string, string | number | undefined> = {}): Promise<PageResult<Assessment>> =>
      useMock ? mockApi.listAssessments(params) : request({ url: '/assessments', params: query(params) }),
    detail: (id: number): Promise<Assessment> =>
      useMock ? mockApi.getAssessment(id) : request({ url: `/assessments/${id}` }),
    create: (values: Record<string, unknown>): Promise<Assessment> =>
      useMock ? mockApi.createAssessment(values) : request({ url: '/assessments', method: 'POST', data: values }),
    withdraw: (id: number, reason: string): Promise<Assessment> =>
      useMock ? mockApi.withdrawAssessment(id, reason) : request({ url: `/assessments/${id}/withdraw`, method: 'POST', data: { reason } })
  },
  questions: {
    list: (params: Record<string, string | number | undefined> = {}): Promise<PageResult<Question>> =>
      useMock ? mockApi.listQuestions(params) : request({ url: '/questions', params: query(params) }),
    detail: (id: number): Promise<Question> =>
      useMock ? mockApi.getQuestion(id) : request({ url: `/questions/${id}` }),
    create: (values: Record<string, unknown>): Promise<Question> =>
      useMock ? mockApi.createQuestion(values) : request({ url: '/questions', method: 'POST', data: values }),
    update: (id: number, values: Partial<Question>): Promise<Question> =>
      useMock ? mockApi.updateQuestion(id, values) : request({ url: `/questions/${id}`, method: 'PATCH', data: values }),
    review: (id: number, action: 'approve' | 'reject', comment: string): Promise<Question> =>
      useMock ? mockApi.reviewQuestion(id, action) : request({ url: `/questions/${id}/review`, method: 'POST', data: { action, comment } }),
    submitReview: (id: number, remark?: string): Promise<Question> =>
      useMock ? mockApi.getQuestion(id) : request({ url: `/questions/${id}/submit-review`, method: 'POST', data: { remark } }),
    remove: (id: number): Promise<{ deleted: boolean }> =>
      useMock ? mockApi.removeQuestion(id) : request({ url: `/questions/${id}`, method: 'DELETE' }),
    uploadResource: async (id: number, file: File): Promise<Record<string, unknown>> => {
      if (useMock) {
        const existing = (await mockApi.listQuestions({ pageSize: 100 })).list.find((item) => item.id === id)
        await mockApi.updateQuestion(id, { resourceCount: (existing?.resourceCount ?? 0) + 1 })
        return { uploaded: true, fileName: file.name }
      }
      const form = new FormData()
      form.append('files', file)
      form.append('type', file.type.startsWith('audio/') ? 'audio' : 'image')
      return request({ url: `/questions/${id}/resources`, method: 'POST', data: form })
    },
    removeResource: (id: number, resourceId: number): Promise<{ deleted: boolean; resourceId: number }> =>
      useMock ? Promise.resolve({ deleted: true, resourceId }) : request({ url: `/questions/${id}/resources/${resourceId}`, method: 'DELETE' })
  },
  courses: {
    list: (params: Record<string, string | number | undefined> = {}): Promise<PageResult<Course>> =>
      useMock ? mockApi.listCourses(params) : request({ url: '/courses', params: query(params) }),
    create: (values: Partial<Course>): Promise<Course> =>
      useMock ? mockApi.createCourse(values) : request({ url: '/courses', method: 'POST', data: values }),
    update: (id: number, values: Partial<Course>): Promise<Course> =>
      useMock ? mockApi.updateCourse(id, values) : request({ url: `/courses/${id}`, method: 'PATCH', data: values }),
    remove: (id: number): Promise<{ deleted: boolean }> =>
      useMock ? mockApi.removeCourse(id) : request({ url: `/courses/${id}`, method: 'DELETE' }),
    chapters: (id: number): Promise<Chapter[]> =>
      useMock ? mockApi.listChapters(id) : request({ url: `/courses/${id}/chapters` }),
    createChapter: (id: number, values: Partial<Chapter>): Promise<Chapter> =>
      useMock ? mockApi.createChapter(id, values) : request({ url: `/courses/${id}/chapters`, method: 'POST', data: values }),
    updateChapter: (id: number, values: Partial<Chapter>): Promise<Chapter> =>
      useMock ? mockApi.updateChapter(id, values) : request({ url: `/chapters/${id}`, method: 'PATCH', data: values }),
    removeChapter: (id: number): Promise<{ deleted: boolean }> =>
      useMock ? mockApi.removeChapter(id) : request({ url: `/chapters/${id}`, method: 'DELETE' })
  },
  scores: {
    list: (params: Record<string, string | number | undefined> = {}): Promise<PageResult<Score>> =>
      useMock ? mockApi.listScores(params) : request({ url: '/scores', params: query(params) }),
    mine: (params: Record<string, string | number | undefined> = {}): Promise<PageResult<Score>> =>
      useMock ? mockApi.listScores(params) : request({ url: '/scores/me', params: query(params) }),
    detail: (id: number): Promise<Score> =>
      useMock ? mockApi.getScore(id) : request({ url: `/scores/${id}` }),
    manual: (values: Record<string, unknown>): Promise<Score> =>
      useMock ? mockApi.createManualScore(values) : request({ url: '/scores/manual', method: 'POST', data: values }),
    import: (file: File, assessmentId?: number, subject?: 'music' | 'art'): Promise<Record<string, unknown>> => {
      if (useMock) return mockApi.importScores(file.name)
      if (!assessmentId || !subject) throw new Error('请先选择导入的测评')
      const form = new FormData()
      form.append('file', file)
      form.append('assessmentId', String(assessmentId))
      form.append('subject', subject)
      return request({ url: '/scores/import', method: 'POST', data: form })
    },
    importTask: (taskId: string): Promise<Record<string, unknown>> => {
      if (useMock) return mockApi.importScores(taskId)
      return request({ url: `/scores/imports/${taskId}` })
    },
    regrade: (id: number, reason: string, aiReevaluate = false): Promise<Score> => {
      if (useMock) return mockApi.regradeScore(id, reason)
      return request({ url: `/scores/${id}/regrade`, method: 'POST', data: { reason, aiReevaluate } })
    }
  },
  statistics: {
    list: async (params: Record<string, string | number | undefined> = {}): Promise<{ list: import('@/types').StatRow[]; summary: { studentCount: number; participantCount: number; avgScore: number; participationRate: number } }> => {
      if (useMock) return mockApi.listStatistics(params)
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
      useMock ? Promise.resolve(new Blob(['排名,对象,平均分\n1,示例市,81.42\n'], { type: 'text/csv;charset=utf-8' })) : download('/scores/statistics/export', query(params))
  },
  logs: {
    list: (params: Record<string, string | number | undefined> = {}): Promise<PageResult<OperationLog>> =>
      useMock ? mockApi.listLogs(params) : request({ url: '/logs', params: query(params) }),
    detail: (id: number): Promise<OperationLog> =>
      useMock ? mockApi.getLog(id) : request({ url: `/logs/${id}` })
  },
  certificates: {
    list: async (params: Record<string, string | number | undefined> = {}): Promise<Certificate[]> => {
      if (useMock) return mockApi.listCertificates(params)
      const result = await request<PageResult<Certificate>>({ url: '/certificates', params: query(params) })
      return result.list
    },
    detail: (id: number): Promise<Certificate> =>
      useMock ? mockApi.getCertificate(id) : request({ url: `/certificates/${id}` }),
    update: (id: number, values: Partial<Certificate>): Promise<Certificate> =>
      useMock ? mockApi.updateCertificate(id, values) : request({ url: `/certificates/${id}`, method: 'PATCH', data: values }),
    download: (id: number): Promise<Blob> =>
      useMock ? mockApi.downloadCertificate(id) : download(`/certificates/${id}/download`),
    generate: (assessmentId: number, subject: 'music' | 'art'): Promise<Record<string, unknown>> =>
      useMock ? mockApi.generateCertificates(assessmentId, subject) : request({ url: '/certificates/generate', method: 'POST', data: { assessmentId, subject } })
  },
  attempts: {
    start: (assessmentId: number): Promise<Attempt> =>
      useMock ? mockApi.startAttempt(assessmentId) : request({ url: `/assessments/${assessmentId}/attempts`, method: 'POST', data: { deviceType: 'web' } }),
    get: (attemptId: number): Promise<Attempt> =>
      useMock ? mockApi.getAttempt(attemptId) : request({ url: `/attempts/${attemptId}` }),
    startPractice: (subject: 'music' | 'art'): Promise<Attempt> =>
      useMock ? mockApi.startPractice(subject) : request({ url: '/papers/practice/random', method: 'POST', data: { subject } }),
    save: (attemptId: number, answers: Attempt['savedAnswers']): Promise<Record<string, unknown>> =>
      useMock ? mockApi.saveAnswers(attemptId, answers) : request({ url: `/attempts/${attemptId}/answers`, method: 'PATCH', data: { answers } }),
    uploadAnswer: (attemptId: number, file: File, subject: Subject): Promise<AnswerFile> => {
      if (useMock) {
        return Promise.resolve({
          fileId: Date.now(),
          url: URL.createObjectURL(file),
          name: file.name,
          mimeType: file.type,
          size: file.size
        })
      }
      const form = new FormData()
      form.append('file', file)
      form.append('category', 'other')
      form.append('subject', subject)
      form.append('bizId', String(attemptId))
      return request({ url: '/files', method: 'POST', data: form })
    },
    submit: (attemptId: number, submitType: 'manual' | 'auto' = 'manual'): Promise<Record<string, unknown>> =>
      useMock ? mockApi.submitAttempt(attemptId, submitType) : request({ url: `/attempts/${attemptId}/submit`, method: 'POST', data: { submitType, finalAnswers: [] } })
  },
  grading: {
    list: (params: Record<string, string | number | undefined> = {}): Promise<PageResult<GradingTask>> =>
      useMock ? mockApi.listGradingTasks(params) : request({ url: '/grading/tasks', params: query(params) }),
    detail: (attemptId: number): Promise<GradingTask> =>
      useMock ? mockApi.getGradingTask(attemptId) : request({ url: `/grading/attempts/${attemptId}` }),
    submit: (attemptId: number, items: Array<{ questionId: number; score: number; comment: string | null }>, finalize: boolean, reason: string, version?: number): Promise<Record<string, unknown>> =>
      useMock ? mockApi.submitGrading(attemptId, items, finalize) : request({ url: `/grading/attempts/${attemptId}/scores`, method: 'PATCH', data: { items, finalize, reason, version } })
  },
  reports: {
    get: (studentId: number, subject?: 'music' | 'art'): Promise<LearningReport | null> =>
      useMock ? mockApi.getReport(studentId, subject) : request({ url: `/students/${studentId}/learning-report`, params: query({ subject }) })
  },
  artworks: {
    list: (): Promise<StudentArtwork[]> =>
      useMock ? mockApi.listArtworks() : request({ url: '/files', params: { category: 'student_work' } }),
    upload: (file: File, subject: 'music' | 'art'): Promise<StudentArtwork> => {
      if (useMock) {
        const preview = new Promise<string>((resolve) => {
          const reader = new FileReader()
          reader.onload = () => resolve(String(reader.result ?? ''))
          reader.readAsDataURL(file)
        })
        return preview.then((dataUrl) => mockApi.uploadArtwork(file.name, subject, dataUrl))
      }
      const form = new FormData()
      form.append('file', file)
      form.append('category', 'student_work')
      form.append('subject', subject)
      return request({ url: '/files', method: 'POST', data: form })
    },
    remove: (id: number): Promise<{ deleted: boolean }> =>
      useMock ? mockApi.removeArtwork(id) : request({ url: `/files/${id}`, method: 'DELETE' })
  },
  wrongQuestions: {
    list: (params: Record<string, string | number | boolean | undefined> = {}): Promise<PageResult<WrongQuestionItem>> =>
      useMock ? mockApi.listWrongQuestions(params) : request({ url: '/students/me/wrong-questions', params: query(params as Record<string, string | number | undefined>) }),
    detail: (id: number): Promise<WrongQuestionDetail> =>
      useMock ? mockApi.getWrongQuestion(id) : request({ url: `/students/me/wrong-questions/${id}` }),
    update: (id: number, values: { masteryStatus?: WrongQuestionDetail['masteryStatus']; note?: string | null }): Promise<WrongQuestionDetail> =>
      useMock ? mockApi.updateWrongQuestion(id, values) : request({ url: `/students/me/wrong-questions/${id}`, method: 'PATCH', data: values }),
    remove: (id: number): Promise<{ deleted: boolean; wrongId: number }> =>
      useMock ? mockApi.removeWrongQuestion(id) : request({ url: `/students/me/wrong-questions/${id}`, method: 'DELETE' }),
    redo: (id: number): Promise<{ attemptId: number; wrongId: number; question: unknown }> =>
      useMock ? mockApi.redoWrongQuestion(id) : request({ url: `/students/me/wrong-questions/${id}/redo`, method: 'POST', data: {} }),
    statistics: (): Promise<WrongQuestionStatistics> =>
      useMock ? mockApi.getWrongQuestionStatistics() : request({ url: '/students/me/wrong-questions/statistics' })
  },
  notifications: {
    list: (params: Record<string, string | number | boolean | undefined> = {}): Promise<PageResult<NotificationItem> & { unreadCount: number }> =>
      useMock ? mockApi.listNotifications(params) : request({ url: '/notifications', params: query(params as Record<string, string | number | undefined>) }),
    read: (id: number): Promise<{ id: number; read: boolean; readAt: string }> =>
      useMock ? mockApi.markNotificationRead(id) : request({ url: `/notifications/${id}/read`, method: 'PATCH', data: {} }),
    readAll: (): Promise<{ updatedCount: number; readAt: string }> =>
      useMock ? mockApi.markAllNotificationsRead() : request({ url: '/notifications/read-all', method: 'PATCH', data: {} })
  },
  profile: {
    update: (values: Record<string, unknown>): Promise<Record<string, unknown>> =>
      useMock ? Promise.resolve(values) : request({ url: '/auth/me', method: 'PATCH', data: values }),
    changePassword: (oldPassword: string, newPassword: string): Promise<Record<string, unknown>> =>
      useMock ? Promise.resolve({ changed: true, reloginRequired: true }) : request({ url: '/auth/password', method: 'PATCH', data: { oldPassword, newPassword } })
  }
}
