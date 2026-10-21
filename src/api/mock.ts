import type {
  Account,
  AccountKind,
  Assessment,
  Attempt,
  Certificate,
  Chapter,
  ClassRequest,
  Course,
  GradingTask,
  LearningReport,
  OperationLog,
  PageResult,
  Paper,
  Question,
  Role,
  Score,
  SchoolClass,
  StatRow,
  Subject,
  StudentArtwork
} from '@/types'

const STORAGE_KEY = 'art-assessment-mock-db-v4'

interface MockDatabase {
  accounts: Account[]
  classes: SchoolClass[]
  classRequests: ClassRequest[]
  papers: Paper[]
  assessments: Assessment[]
  questions: Question[]
  courses: Course[]
  chapters: Chapter[]
  scores: Score[]
  gradingTasks: GradingTask[]
  certificates: Certificate[]
  logs: OperationLog[]
  attempts: Attempt[]
  reports: LearningReport[]
  artworks: StudentArtwork[]
}

const now = () => new Date().toISOString()

const roleByKind: Record<AccountKind, Role> = {
  teachers: 'teacher',
  students: 'student',
  schools: 'school_admin',
  districts: 'district_admin',
  cities: 'city_admin'
}

const roleName: Record<Role, string> = {
  student: '学生',
  teacher: '教师',
  school_admin: '学校管理员',
  district_admin: '区县管理员',
  city_admin: '市州管理员',
  province_admin: '省级管理员',
  question_admin: '题库管理员'
}

function createAccount(
  id: number,
  kind: AccountKind,
  username: string,
  realName: string,
  extra: Partial<Account> = {}
): Account {
  const role = roleByKind[kind]
  return {
    id,
    kind,
    username,
    realName,
    role,
    roleName: roleName[role],
    orgId: 301,
    orgName: '示范中学',
    studentNo: null,
    phone: `1380000${String(id).padStart(4, '0')}`,
    email: null,
    subject: kind === 'teachers' ? 'music' : null,
    grade: kind === 'students' ? 7 : null,
    classId: kind === 'students' ? 5001 : null,
    className: kind === 'students' ? '七年级（1）班' : null,
    status: 'active',
    createdAt: '2026-09-01T10:00:00+08:00',
    ...extra
  }
}

function seed(): MockDatabase {
  const courses: Course[] = [
    { id: 6001, name: '七年级音乐鉴赏', subject: 'music', grade: 7, description: '音乐鉴赏基础课程', chapterCount: 2, status: 'active', sortOrder: 1 },
    { id: 6002, name: '七年级美术鉴赏', subject: 'art', grade: 7, description: '美术鉴赏基础课程', chapterCount: 2, status: 'active', sortOrder: 2 }
  ]
  const chapters: Chapter[] = [
    { id: 6101, courseId: 6001, courseName: '七年级音乐鉴赏', name: '节奏与节拍', description: '认识常见拍号', questionCount: 18, sortOrder: 1 },
    { id: 6102, courseId: 6001, courseName: '七年级音乐鉴赏', name: '旋律与音色', description: '感受旋律和音色', questionCount: 22, sortOrder: 2 },
    { id: 6201, courseId: 6002, courseName: '七年级美术鉴赏', name: '构图基础', description: '理解画面组织', questionCount: 16, sortOrder: 1 },
    { id: 6202, courseId: 6002, courseName: '七年级美术鉴赏', name: '色彩基础', description: '认识色彩关系', questionCount: 20, sortOrder: 2 }
  ]
  const questions: Question[] = [
    { id: 9001, subject: 'music', grade: 7, courseId: 6001, courseName: '七年级音乐鉴赏', chapterId: 6101, chapterName: '节奏与节拍', type: 'single_choice', difficulty: 2, stem: '聆听音频，判断这段旋律的拍号。', score: 5, status: 'approved', creatorName: '李老师', resourceCount: 1, options: [{ key: 'A', text: '2/4' }, { key: 'B', text: '3/4' }, { key: 'C', text: '4/4' }, { key: 'D', text: '6/8' }], answer: { value: 'B' }, analysis: '旋律呈现强弱弱的周期性规律，应为三拍子。', resources: [{ resourceId: 9101, type: 'audio', name: '听赏示例音频' }], createdAt: '2026-10-01T09:00:00+08:00', updatedAt: '2026-10-02T09:00:00+08:00' },
    { id: 9002, subject: 'music', grade: 7, courseId: 6001, courseName: '七年级音乐鉴赏', chapterId: 6102, chapterName: '旋律与音色', type: 'short_answer', difficulty: 3, stem: '分析乐曲的情绪与节奏特点。', score: 15, status: 'pending', creatorName: '李老师', resourceCount: 0, answer: { text: '节奏鲜明、旋律跳跃，整体情绪欢快热烈。' }, analysis: '从情绪、节奏、旋律三个维度作答。', resources: [], createdAt: '2026-10-03T09:00:00+08:00', updatedAt: '2026-10-03T09:00:00+08:00' },
    { id: 9003, subject: 'art', grade: 7, courseId: 6002, courseName: '七年级美术鉴赏', chapterId: 6201, chapterName: '构图基础', type: 'image_upload', difficulty: 4, stem: '上传一幅静物素描作品。', score: 25, status: 'approved', creatorName: '赵老师', resourceCount: 0, answer: { rubric: '构图 8 分；造型 8 分；细节 5 分；完整度 4 分。' }, analysis: '重点观察构图重心、比例关系和明暗层次。', resources: [], createdAt: '2026-10-04T09:00:00+08:00', updatedAt: '2026-10-04T09:00:00+08:00' }
  ]
  const papers: Paper[] = [
    { id: 11001, title: '2026 秋季七年级音乐测评卷', subject: 'music', paperType: 'formal', grade: 7, scopeType: 'school', scopeId: 301, scopeName: '示范中学', totalScore: 100, questionCount: 20, duration: 45, generateMode: 'manual', status: 'ready', creatorName: '孙校长', createdAt: '2026-10-21T09:00:00+08:00', updatedAt: '2026-10-21T09:30:00+08:00', questions: [{ questionId: 9001, stem: '聆听音频，判断这段旋律的拍号。', type: 'single_choice', score: 5, analysis: '旋律呈现强弱弱的周期性规律。' }, { questionId: 9002, stem: '分析乐曲的情绪与节奏特点。', type: 'short_answer', score: 15, analysis: '从情绪、节奏、旋律三个维度作答。' }] },
    { id: 11002, title: '七年级美术构图练习卷', subject: 'art', paperType: 'practice', grade: 7, scopeType: 'district', scopeId: 22, scopeName: '示例区', totalScore: 100, questionCount: 15, duration: 30, generateMode: 'auto', status: 'draft', creatorName: '刘主任', createdAt: '2026-10-21T10:00:00+08:00', updatedAt: '2026-10-21T10:00:00+08:00', questions: [{ questionId: 9003, stem: '上传一幅静物素描作品。', type: 'image_upload', score: 25, analysis: '重点观察构图、比例和明暗层次。' }] }
  ]
  const assessments: Assessment[] = [
    { id: 12001, title: '2026 秋季七年级音乐正式测评', paperId: 11001, paperTitle: '2026 秋季七年级音乐测评卷', subject: 'music', paperType: 'formal', grade: 7, targetType: 'school', targetIds: [301], targetNames: ['示范中学'], targetGrades: [7], startTime: '2026-10-25T09:00:00+08:00', endTime: '2026-10-25T18:00:00+08:00', duration: 45, attemptLimit: 1, showAnswerMode: 'after_end', status: 'published', publisherName: '孙校长', participantCount: 126, submittedCount: 98, instructions: '请在规定时间内完成，逾期系统自动交卷。' }
  ]
  const accounts: Account[] = [
    createAccount(2001, 'teachers', 'teacher1001', '李老师', { subject: 'music' }),
    createAccount(2002, 'teachers', 'teacher1002', '赵老师', { subject: 'art' }),
    createAccount(1001, 'students', 'student2026001', '王小明', { studentNo: 'S20260001' }),
    createAccount(1002, 'students', 'student2026002', '陈小雨', { studentNo: 'S20260002', className: '七年级（2）班', classId: 5002 }),
    createAccount(3001, 'schools', 'school301', '孙校长', { orgName: '示范中学' }),
    createAccount(3002, 'schools', 'school302', '钱校长', { orgId: 302, orgName: '实验中学' }),
    createAccount(2201, 'districts', 'district22', '刘主任', { orgId: 22, orgName: '示例区' }),
    createAccount(2202, 'districts', 'district23', '陈主任', { orgId: 23, orgName: '示例第二区' }),
    createAccount(3011, 'cities', 'city03', '周局长', { orgId: 3, orgName: '示例市' }),
    createAccount(3012, 'cities', 'city04', '吴局长', { orgId: 4, orgName: '示例第二市' })
  ]
  const classes: SchoolClass[] = [
    { id: 5001, classCode: 'C20260701', name: '七年级（1）班', grade: 7, schoolName: '示范中学', headTeacherName: '李老师', studentCount: 42, status: 'active', createdAt: '2026-09-01T10:00:00+08:00' },
    { id: 5002, classCode: 'C20260702', name: '七年级（2）班', grade: 7, schoolName: '示范中学', headTeacherName: '赵老师', studentCount: 40, status: 'active', createdAt: '2026-09-01T10:10:00+08:00' }
  ]
  const classRequests: ClassRequest[] = [
    { id: 7001, classId: 5001, className: '七年级（1）班', requesterName: '王小明', requesterRole: 'student', type: 'join', status: 'pending', reason: '本人为该班学生', createdAt: '2026-10-20T11:30:00+08:00' }
  ]
  const scores: Score[] = [
    {
      id: 14001,
      assessmentId: 12001,
      assessmentTitle: assessments[0].title,
      subject: 'music',
      studentNo: 'S20260001',
      studentName: '王小明',
      className: '七年级（1）班',
      objectiveScore: 35,
      subjectiveScore: 48,
      aiScore: 5,
      totalScore: 88,
      level: 'good',
      status: 'graded',
      source: 'online',
      createdAt: '2026-10-25T09:44:10+08:00',
      answerVisible: true,
      answerDetails: [
        { questionId: 9001, order: 1, stem: '聆听音频，判断这段旋律的拍号。', studentAnswer: 'B. 3/4', correctAnswer: 'B. 3/4', score: 5, maxScore: 5, comment: '回答正确', aiAnalysis: null },
        { questionId: 9002, order: 2, stem: '分析乐曲的情绪与节奏特点。', studentAnswer: '节奏明快，情绪热烈。', correctAnswer: '节奏鲜明、旋律跳跃，整体情绪欢快热烈。', score: 12, maxScore: 15, comment: '要点基本完整，可补充力度变化。', aiAnalysis: '覆盖节奏和情绪，但力度、音色分析不足。' }
      ]
    },
    { id: 14002, assessmentId: 12001, assessmentTitle: assessments[0].title, subject: 'music', studentNo: 'S20260002', studentName: '陈小雨', className: '七年级（2）班', objectiveScore: 32, subjectiveScore: 43, aiScore: 5, totalScore: 80, level: 'good', status: 'graded', source: 'online', createdAt: '2026-10-25T09:51:10+08:00' },
    { id: 14003, assessmentId: 12001, assessmentTitle: assessments[0].title, subject: 'music', studentNo: 'S20260003', studentName: '李晨', className: '七年级（1）班', objectiveScore: 28, subjectiveScore: 32, aiScore: 4, totalScore: 64, level: 'pass', status: 'graded', source: 'online', createdAt: '2026-10-25T10:05:10+08:00' }
  ]
  const certificates: Certificate[] = [
    { id: 15001, certificateNo: 'YS2026-MUSIC-000001', studentName: '王小明', assessmentTitle: assessments[0].title, subject: 'music', score: 88, level: '良好', issueDate: '2026-10-26', status: 'ready' },
    { id: 15002, certificateNo: 'YS2026-MUSIC-000002', studentName: '陈小雨', assessmentTitle: assessments[0].title, subject: 'music', score: 80, level: '良好', issueDate: '2026-10-26', status: 'ready' }
  ]
  const logs: OperationLog[] = [
    { id: 12001, operatorName: '题库管理员', role: 'question_admin', action: 'question.review', resourceType: 'question', resourceId: 9001, description: '审核试题 9001：通过', ip: '10.0.0.15', result: 'success', createdAt: '2026-10-20T15:00:00+08:00' },
    { id: 12002, operatorName: '孙校长', role: 'school_admin', action: 'assessment.publish', resourceType: 'assessment', resourceId: 12001, description: '发布七年级音乐正式测评', ip: '10.0.0.31', result: 'success', createdAt: '2026-10-21T11:00:00+08:00' }
  ]
  const attempt: Attempt = {
    attemptId: 13001,
    assessmentId: 12001,
    paperId: 11001,
    title: assessments[0].title,
    subject: 'music',
    status: 'in_progress',
    startedAt: now(),
    deadline: new Date(Date.now() + 45 * 60 * 1000).toISOString(),
    serverTime: now(),
    remainingSeconds: 2700,
    totalScore: 100,
    questions: [
      { questionId: 9001, order: 1, type: 'single_choice', stem: '聆听音频，判断这段旋律的拍号。', score: 5, options: [{ key: 'A', text: '2/4' }, { key: 'B', text: '3/4' }, { key: 'C', text: '4/4' }, { key: 'D', text: '6/8' }], resources: [{ type: 'audio', name: '听赏示例音频' }], answerConfig: { playLimit: 2 }, correctAnswer: 'B', analysis: '旋律呈现强弱弱的周期性规律，应为三拍子。' },
      { questionId: 9002, order: 2, type: 'short_answer', stem: '分析乐曲的情绪与节奏特点。', score: 15, options: [], resources: [], answerConfig: { maxLength: 500 }, correctAnswer: '节奏鲜明、旋律跳跃，整体情绪欢快热烈。', analysis: '从情绪、节奏、旋律三个维度作答。' },
      { questionId: 9003, order: 3, type: 'image_upload', stem: '上传一幅与“秋日”主题相关的作品照片。', score: 25, options: [], resources: [{ type: 'image', name: '示例图片', url: 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22640%22 height=%22360%22%3E%3Crect width=%22640%22 height=%22360%22 fill=%22%23fff7ed%22/%3E%3Ccircle cx=%22520%22 cy=%22100%22 r=%2248%22 fill=%22%23fb923c%22/%3E%3Cpath d=%22M0 310 L170 150 L300 285 L430 110 L640 310 Z%22 fill=%22%23ea580c%22/%3E%3C/svg%3E' }], answerConfig: { maxLength: 120 }, correctAnswer: '构图完整、主题突出、细节丰富。', analysis: '重点观察构图重心、比例关系和明暗层次。' }
    ],
    savedAnswers: []
  }

  const gradingTasks: GradingTask[] = [
    {
      attemptId: 13002,
      assessmentId: 12001,
      assessmentTitle: assessments[0].title,
      subject: 'music',
      studentId: 1002,
      studentName: '陈小雨',
      studentNo: 'S20260002',
      className: '七年级（2）班',
      submittedAt: '2026-10-25T09:51:10+08:00',
      gradingStatus: 'grading',
      objectiveScore: 32,
      currentScore: 5,
      maxScore: 100,
      pendingCount: 2,
      questions: [
        { questionId: 9010, order: 10, type: 'short_answer', stem: '分析乐曲的情绪与节奏特点。', studentAnswer: '节奏较快，情绪积极。', correctAnswer: '节奏鲜明、旋律跳跃，整体情绪欢快热烈。', rubric: '情绪 5 分；节奏 5 分；力度与音色 5 分。', maxScore: 15, currentScore: null, aiScore: 11, aiAnalysis: '概括了情绪和速度，但分析维度不足。', comment: null },
        { questionId: 9011, order: 11, type: 'audio_upload', stem: '上传一段 60 秒的歌曲演唱音频。', studentAnswer: '已上传演唱音频', correctAnswer: '无固定标准答案', rubric: '音准 10 分；节奏 10 分；表现力 5 分。', maxScore: 25, currentScore: null, aiScore: 21, aiAnalysis: '音准较好，高音区略有偏差。', comment: null }
      ]
    }
  ]
  const reports: LearningReport[] = [
    {
      reportId: 'LR202610250001',
      studentId: 1001,
      subject: 'music',
      generatedAt: '2026-10-25T12:00:00+08:00',
      summary: '本学年音乐成绩稳步提升，节奏和听辨表现较好，乐曲分析的力度与音色维度仍需加强。',
      strengths: ['节拍识别准确', '听辨题正确率较高', '能够结合旋律分析情绪'],
      weaknesses: ['高音区音准偶有波动', '乐曲分析维度不足', '复杂节奏的速度控制不稳定'],
      suggestions: ['每天进行 10 分钟高音区模唱', '使用“情绪—节奏—力度—音色”四步法分析乐曲', '完成附点与切分节奏专项练习'],
      scoreTrend: [{ date: '2026-04-15', score: 76 }, { date: '2026-10-25', score: 88 }],
      rawText: '王小明同学在本学年音乐学习中表现出稳步提升。节拍识别与基础听辨较为扎实，乐曲分析能够抓住情绪与节奏，但力度、音色辨识仍有遗漏。建议加强高音区音准训练，并使用四步分析框架完善主观题作答。',
      modelVersion: 'learning-report-v1.0.0'
    }
  ]
  const artworks: StudentArtwork[] = [
    {
      id: 16001,
      studentId: 1001,
      studentName: '王小明',
      fileName: '秋日校园.png',
      subject: 'art',
      uploadedAt: '2026-10-18T16:20:00+08:00',
      status: 'reviewed',
      preview: 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22400%22 height=%22240%22%3E%3Crect width=%22400%22 height=%22240%22 fill=%22%23fff7ed%22/%3E%3Ccircle cx=%22320%22 cy=%2270%22 r=%2234%22 fill=%22%23fb923c%22/%3E%3Cpath d=%22M0 210 L110 90 L220 205 L310 55 L400 210 Z%22 fill=%22%23f97316%22/%3E%3C/svg%3E'
    }
  ]
  return { accounts, classes, classRequests, papers, assessments, questions, courses, chapters, scores, gradingTasks, certificates, logs, attempts: [attempt], reports, artworks }
}

function load(): MockDatabase {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored) {
    try {
      return JSON.parse(stored) as MockDatabase
    } catch {
      localStorage.removeItem(STORAGE_KEY)
    }
  }
  const initial = seed()
  localStorage.setItem(STORAGE_KEY, JSON.stringify(initial))
  return initial
}

const db = load()

function save() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(db))
}

function nextId(items: Array<{ id: number }>) {
  return Math.max(0, ...items.map((item) => item.id)) + 1
}

function page<T>(items: T[], pageNum = 1, pageSize = 10): PageResult<T> {
  const total = items.length
  const start = (pageNum - 1) * pageSize
  return { total, pages: Math.max(1, Math.ceil(total / pageSize)), list: items.slice(start, start + pageSize) }
}

function wait(ms = 180) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function includes(value: string | null | undefined, keyword: string) {
  return !keyword || String(value ?? '').toLowerCase().includes(keyword.toLowerCase())
}

export const mockApi = {
  async listClasses(params: Record<string, string | number | undefined> = {}) {
    await wait()
    const items = db.classes.filter((item) => includes(`${item.name} ${item.classCode}`, String(params.keyword ?? '')))
    return page(items, Number(params.pageNum ?? 1), Number(params.pageSize ?? 10))
  },
  async searchClass(classCode: string) {
    await wait()
    return db.classes.find((item) => item.classCode === classCode) ?? null
  },
  async createClass(values: Partial<SchoolClass>) {
    await wait()
    const item: SchoolClass = {
      id: nextId(db.classes),
      classCode: values.classCode || `C${Date.now().toString().slice(-8)}`,
      name: values.name ?? '新班级',
      grade: Number(values.grade ?? 7),
      schoolName: '示范中学',
      headTeacherName: values.headTeacherName ?? '李老师',
      studentCount: 0,
      status: 'active',
      createdAt: now()
    }
    db.classes.unshift(item)
    save()
    return item
  },
  async updateClass(id: number, values: Partial<SchoolClass>) {
    await wait()
    const item = db.classes.find((row) => row.id === id)
    if (!item) throw new Error('班级不存在')
    Object.assign(item, values)
    save()
    return item
  },
  async removeClass(id: number) {
    await wait()
    db.classes = db.classes.filter((row) => row.id !== id)
    save()
    return { deleted: true }
  },
  async listClassRequests(classId: number) {
    await wait()
    return db.classRequests.filter((item) => item.classId === classId)
  },
  async reviewClassRequest(id: number, action: 'approve' | 'reject') {
    await wait()
    const item = db.classRequests.find((row) => row.id === id)
    if (!item) throw new Error('申请不存在')
    item.status = action === 'approve' ? 'approved' : 'rejected'
    save()
    return item
  },
  async submitClassRequest(classId: number, type: 'join' | 'change' | 'leave', reason: string, targetClassId?: number) {
    await wait()
    const classInfo = db.classes.find((item) => item.id === classId)
    if (!classInfo) throw new Error('班级不存在')
    const session = localStorage.getItem('art-assessment-session') ?? sessionStorage.getItem('art-assessment-session')
    let requesterName = '王小明'
    let requesterRole: ClassRequest['requesterRole'] = 'student'
    if (session) {
      try {
        const parsed = JSON.parse(session) as { role?: string; user?: { realName?: string } }
        requesterName = parsed.user?.realName ?? requesterName
        requesterRole = parsed.role === 'teacher' ? 'teacher' : 'student'
      } catch {
        // Keep the student demo identity when stored session data is unavailable.
      }
    }
    const request: ClassRequest = {
      id: nextId(db.classRequests),
      classId,
      className: classInfo.name,
      requesterName,
      requesterRole,
      type,
      status: 'pending',
      reason: reason || '学生提交申请',
      createdAt: now()
    }
    db.classRequests.unshift(request)
    if (type === 'change' && targetClassId) {
      const target = db.classes.find((item) => item.id === targetClassId)
      if (target) request.className = `${classInfo.name} → ${target.name}`
    }
    save()
    return request
  },
  async listClassStudents(classId: number, params: Record<string, string | number | undefined> = {}) {
    await wait()
    const keyword = String(params.keyword ?? '')
    const items = db.accounts.filter((item) =>
      item.kind === 'students' &&
      item.classId === classId &&
      includes(`${item.realName} ${item.studentNo} ${item.username}`, keyword)
    )
    return page(items, Number(params.pageNum ?? 1), Number(params.pageSize ?? 10))
  },
  async removeClassStudent(classId: number, studentId: number) {
    await wait()
    const student = db.accounts.find((item) => item.id === studentId && item.classId === classId)
    if (!student) throw new Error('学生不在当前班级')
    student.classId = null
    student.className = null
    save()
    return { removed: true }
  },
  async importClassStudents(fileName: string) {
    await wait()
    return { taskId: `STU${Date.now()}`, status: 'completed', total: 45, successCount: 43, failCount: 2, fileName, errors: [{ row: 12, studentNo: 'S20260045', message: '学籍号已存在' }, { row: 30, studentNo: 'S20260063', message: '性别格式不正确' }] }
  },
  async listAccounts(kind: AccountKind, params: Record<string, string | number | undefined> = {}) {
    await wait()
    const keyword = String(params.keyword ?? '')
    const status = String(params.status ?? '')
    const items = db.accounts.filter((item) =>
      item.kind === kind &&
      includes(`${item.username} ${item.realName} ${item.studentNo ?? ''}`, keyword) &&
      (!status || item.status === status)
    )
    return page(items, Number(params.pageNum ?? 1), Number(params.pageSize ?? 10))
  },
  async createAccount(kind: AccountKind, values: Record<string, unknown>) {
    await wait()
    const role = roleByKind[kind]
    const account = createAccount(nextId(db.accounts), kind, String(values.username ?? `user${Date.now()}`), String(values.realName ?? '新账号'), {
      phone: String(values.phone ?? '') || null,
      email: String(values.email ?? '') || null,
      studentNo: kind === 'students' ? String(values.studentNo ?? `S${Date.now()}`) : null,
      subject: kind === 'teachers' ? (values.subject as Subject) : null,
      grade: values.grade ? Number(values.grade) : null,
      orgName: String(values.orgName ?? (kind === 'schools' ? values.realName : '示范中学')),
      role,
      roleName: roleName[role]
    })
    db.accounts.unshift(account)
    db.logs.unshift({ id: nextId(db.logs), operatorName: '当前用户', role, action: 'account.create', resourceType: 'account', resourceId: account.id, description: `创建账号 ${account.username}`, ip: '127.0.0.1', result: 'success', createdAt: now() })
    save()
    return account
  },
  async updateAccount(id: number, values: Partial<Account>) {
    await wait()
    const item = db.accounts.find((account) => account.id === id)
    if (!item) throw new Error('账号不存在')
    Object.assign(item, values)
    save()
    return item
  },
  async removeAccount(id: number) {
    await wait()
    db.accounts = db.accounts.filter((account) => account.id !== id)
    save()
    return { deleted: true }
  },
  async resetPassword(id: number) {
    await wait()
    const temporaryPassword = `Art#${Math.random().toString(36).slice(2, 8)}`
    return { accountId: id, temporaryPassword, forceChange: true }
  },
  async listPapers(params: Record<string, string | number | undefined> = {}) {
    await wait()
    const items = db.papers.filter((item) =>
      (!params.subject || item.subject === params.subject) &&
      (!params.paperType || item.paperType === params.paperType) &&
      (!params.status || item.status === params.status) &&
      includes(item.title, String(params.keyword ?? ''))
    )
    return page(items, Number(params.pageNum ?? 1), Number(params.pageSize ?? 10))
  },
  async getPaper(id: number) {
    await wait()
    const item = db.papers.find((paper) => paper.id === id)
    if (!item) throw new Error('试卷不存在')
    return item
  },
  async createPaper(values: Record<string, unknown>, mode: 'manual' | 'auto') {
    await wait()
    const item: Paper = {
      id: nextId(db.papers),
      title: String(values.title ?? '未命名试卷'),
      subject: (values.subject as Subject) ?? 'music',
      paperType: (values.paperType as Paper['paperType']) ?? 'practice',
      grade: Number(values.grade ?? 7),
      scopeType: (values.scopeType as Paper['scopeType']) ?? 'school',
      scopeId: Number(values.scopeId ?? 301),
      scopeName: String(values.scopeName ?? '示范中学'),
      totalScore: Number(values.totalScore ?? 100),
      questionCount: Number(values.questionCount ?? 10),
      duration: Number(values.duration ?? 45),
      generateMode: mode,
      status: (values.status as Paper['status']) ?? 'draft',
      creatorName: '当前用户',
      createdAt: now(),
      updatedAt: now(),
      questions: db.questions.filter((question) => question.subject === ((values.subject as Subject) ?? 'music')).slice(0, Number(values.questionCount ?? 2)).map((question) => ({
        questionId: question.id,
        stem: question.stem,
        type: question.type,
        score: question.score,
        analysis: question.analysis
      }))
    }
    db.papers.unshift(item)
    save()
    return item
  },
  async updatePaper(id: number, values: Partial<Paper>) {
    await wait()
    const item = db.papers.find((paper) => paper.id === id)
    if (!item) throw new Error('试卷不存在')
    Object.assign(item, values, { updatedAt: now() })
    save()
    return item
  },
  async removePaper(id: number) {
    await wait()
    db.papers = db.papers.filter((paper) => paper.id !== id)
    save()
    return { deleted: true }
  },
  async listAssessments(params: Record<string, string | number | undefined> = {}) {
    await wait()
    const items = db.assessments.filter((item) =>
      (!params.subject || item.subject === params.subject) &&
      (!params.status || item.status === params.status) &&
      includes(item.title, String(params.keyword ?? ''))
    )
    return page(items, Number(params.pageNum ?? 1), Number(params.pageSize ?? 10))
  },
  async getAssessment(id: number) {
    await wait()
    const item = db.assessments.find((assessment) => assessment.id === id)
    if (!item) throw new Error('测评不存在')
    return item
  },
  async createAssessment(values: Record<string, unknown>) {
    await wait()
    const paper = db.papers.find((item) => item.id === Number(values.paperId))
    if (!paper) throw new Error('试卷不存在')
    const item: Assessment = {
      id: nextId(db.assessments),
      title: String(values.title ?? paper.title),
      paperId: paper.id,
      paperTitle: paper.title,
      subject: paper.subject,
      paperType: paper.paperType,
      grade: paper.grade,
      targetType: (values.targetType as Assessment['targetType']) ?? 'school',
      targetIds: Array.isArray(values.targetIds) ? (values.targetIds as number[]) : [301],
      targetNames: ['目标范围'],
      targetGrades: Array.isArray(values.targetGrades) ? (values.targetGrades as number[]) : [7],
      startTime: String(values.startTime ?? now()),
      endTime: String(values.endTime ?? new Date(Date.now() + 86400000).toISOString()),
      duration: paper.duration,
      attemptLimit: Number(values.attemptLimit ?? 1),
      showAnswerMode: (values.showAnswerMode as Assessment['showAnswerMode']) ?? 'after_end',
      status: 'published',
      publisherName: '当前用户',
      participantCount: 42,
      submittedCount: 0,
      instructions: String(values.instructions ?? '')
    }
    db.assessments.unshift(item)
    paper.status = 'published'
    save()
    return item
  },
  async withdrawAssessment(id: number, reason: string) {
    await wait()
    const item = db.assessments.find((assessment) => assessment.id === id)
    if (!item) throw new Error('测评不存在')
    item.status = 'withdrawn'
    db.logs.unshift({ id: nextId(db.logs), operatorName: '当前用户', role: 'school_admin', action: 'assessment.withdraw', resourceType: 'assessment', resourceId: id, description: reason, ip: '127.0.0.1', result: 'success', createdAt: now() })
    save()
    return item
  },
  async listQuestions(params: Record<string, string | number | undefined> = {}) {
    await wait()
    const items = db.questions.filter((item) =>
      (!params.subject || item.subject === params.subject) &&
      (!params.status || item.status === params.status) &&
      (!params.type || item.type === params.type) &&
      (!params.difficulty || item.difficulty === Number(params.difficulty)) &&
      includes(item.stem, String(params.keyword ?? ''))
    )
    return page(items, Number(params.pageNum ?? 1), Number(params.pageSize ?? 10))
  },
  async getQuestion(id: number) {
    await wait()
    const item = db.questions.find((question) => question.id === id)
    if (!item) throw new Error('试题不存在')
    return item
  },
  async createQuestion(values: Record<string, unknown>) {
    await wait()
    const course = db.courses.find((item) => item.id === Number(values.courseId))
    const item: Question = {
      id: nextId(db.questions),
      subject: (values.subject as Subject) ?? course?.subject ?? 'music',
      grade: Number(values.grade ?? 7),
      courseId: Number(values.courseId ?? 6001),
      courseName: course?.name ?? '未关联课程',
      chapterId: values.chapterId ? Number(values.chapterId) : null,
      chapterName: null,
      type: String(values.type ?? 'single_choice'),
      difficulty: Number(values.difficulty ?? 2),
      stem: String(values.stem ?? ''),
      score: Number(values.score ?? 5),
      status: values.publishNow ? 'approved' : 'pending',
      creatorName: '当前用户',
      resourceCount: 0,
      createdAt: now(),
      updatedAt: now()
    }
    db.questions.unshift(item)
    save()
    return item
  },
  async updateQuestion(id: number, values: Partial<Question>) {
    await wait()
    const item = db.questions.find((question) => question.id === id)
    if (!item) throw new Error('试题不存在')
    Object.assign(item, values, { updatedAt: now() })
    save()
    return item
  },
  async reviewQuestion(id: number, action: 'approve' | 'reject') {
    return this.updateQuestion(id, { status: action === 'approve' ? 'approved' : 'rejected' })
  },
  async removeQuestion(id: number) {
    await wait()
    db.questions = db.questions.filter((question) => question.id !== id)
    save()
    return { deleted: true }
  },
  async listCourses(params: Record<string, string | number | undefined> = {}) {
    await wait()
    const items = db.courses.filter((item) =>
      (!params.subject || item.subject === params.subject) &&
      includes(item.name, String(params.keyword ?? ''))
    )
    return page(items, Number(params.pageNum ?? 1), Number(params.pageSize ?? 10))
  },
  async createCourse(values: Partial<Course>) {
    await wait()
    const course: Course = {
      id: nextId(db.courses),
      name: values.name ?? '新课程',
      subject: values.subject ?? 'music',
      grade: Number(values.grade ?? 7),
      description: values.description ?? '',
      chapterCount: 0,
      status: values.status ?? 'active',
      sortOrder: Number(values.sortOrder ?? 0)
    }
    db.courses.push(course)
    save()
    return course
  },
  async updateCourse(id: number, values: Partial<Course>) {
    await wait()
    const item = db.courses.find((course) => course.id === id)
    if (!item) throw new Error('课程不存在')
    Object.assign(item, values)
    save()
    return item
  },
  async removeCourse(id: number) {
    await wait()
    db.courses = db.courses.filter((course) => course.id !== id)
    db.chapters = db.chapters.filter((chapter) => chapter.courseId !== id)
    save()
    return { deleted: true }
  },
  async listChapters(courseId: number) {
    await wait()
    return db.chapters.filter((item) => item.courseId === courseId)
  },
  async createChapter(courseId: number, values: Partial<Chapter>) {
    await wait()
    const course = db.courses.find((item) => item.id === courseId)
    const chapter: Chapter = {
      id: nextId(db.chapters),
      courseId,
      courseName: course?.name ?? '',
      name: values.name ?? '新章节',
      description: values.description ?? '',
      questionCount: 0,
      sortOrder: Number(values.sortOrder ?? 0)
    }
    db.chapters.push(chapter)
    if (course) course.chapterCount = db.chapters.filter((item) => item.courseId === courseId).length
    save()
    return chapter
  },
  async updateChapter(id: number, values: Partial<Chapter>) {
    await wait()
    const item = db.chapters.find((chapter) => chapter.id === id)
    if (!item) throw new Error('章节不存在')
    Object.assign(item, values)
    save()
    return item
  },
  async removeChapter(id: number) {
    await wait()
    db.chapters = db.chapters.filter((chapter) => chapter.id !== id)
    save()
    return { deleted: true }
  },
  async listScores(params: Record<string, string | number | undefined> = {}) {
    await wait()
    const items = db.scores.filter((item) =>
      (!params.subject || item.subject === params.subject) &&
      includes(`${item.studentName} ${item.studentNo}`, String(params.keyword ?? ''))
    )
    return page(items, Number(params.pageNum ?? 1), Number(params.pageSize ?? 10))
  },
  async getScore(id: number) {
    await wait()
    const item = db.scores.find((score) => score.id === id)
    if (!item) throw new Error('成绩不存在')
    return item
  },
  async createManualScore(values: Record<string, unknown>) {
    await wait()
    const totalScore = Number(values.totalScore ?? 0)
    const item: Score = {
      id: nextId(db.scores),
      assessmentId: Number(values.assessmentId ?? 12001),
      assessmentTitle: '手工补录成绩',
      subject: (values.subject as Subject) ?? 'music',
      studentNo: String(values.studentNo ?? ''),
      studentName: String(values.studentName ?? ''),
      className: String(values.className ?? ''),
      objectiveScore: 0,
      subjectiveScore: totalScore,
      aiScore: 0,
      totalScore,
      level: totalScore >= 90 ? 'excellent' : totalScore >= 80 ? 'good' : totalScore >= 60 ? 'pass' : 'fail',
      status: 'graded',
      source: 'manual',
      createdAt: now()
    }
    db.scores.unshift(item)
    save()
    return item
  },
  async listGradingTasks(params: Record<string, string | number | undefined> = {}) {
    await wait()
    const items = db.gradingTasks.filter((item) =>
      (!params.gradingStatus || item.gradingStatus === params.gradingStatus) &&
      includes(`${item.studentName} ${item.studentNo} ${item.assessmentTitle}`, String(params.keyword ?? ''))
    )
    return page(items, Number(params.pageNum ?? 1), Number(params.pageSize ?? 10))
  },
  async getGradingTask(attemptId: number) {
    await wait()
    const item = db.gradingTasks.find((task) => task.attemptId === attemptId)
    if (!item) throw new Error('待评分答卷不存在')
    return item
  },
  async submitGrading(attemptId: number, items: Array<{ questionId: number; score: number; comment: string | null }>, finalize: boolean) {
    await wait()
    const task = db.gradingTasks.find((row) => row.attemptId === attemptId)
    if (!task) throw new Error('待评分答卷不存在')
    items.forEach((submitted) => {
      const question = task.questions.find((row) => row.questionId === submitted.questionId)
      if (question) {
        question.currentScore = submitted.score
        question.comment = submitted.comment
      }
    })
    task.currentScore = task.objectiveScore + task.questions.reduce((sum, row) => sum + (row.currentScore ?? 0), 0)
    task.gradingStatus = 'grading'
    task.pendingCount = task.questions.filter((row) => row.currentScore === null).length
    const score = db.scores.find((row) => row.assessmentId === task.assessmentId && row.studentNo === task.studentNo)
    if (score) {
      score.subjectiveScore = task.questions.reduce((sum, row) => sum + (row.currentScore ?? 0), 0)
      score.totalScore = task.currentScore
      score.status = finalize ? 'graded' : 'grading'
    }
    if (finalize && task.pendingCount === 0) {
      db.gradingTasks = db.gradingTasks.filter((row) => row.attemptId !== attemptId)
    }
    save()
    return { attemptId, gradingStatus: finalize ? 'graded' : task.gradingStatus, subjectiveScore: score?.subjectiveScore ?? 0, totalScore: task.currentScore, finalized: finalize, updatedAt: now() }
  },
  async importScores(fileName: string) {
    await wait()
    return { taskId: `IMP${Date.now()}`, status: 'completed', total: 12, successCount: 11, failCount: 1, fileName, errors: [{ row: 6, studentNo: 'S20260006', message: '学籍号不属于当前测评范围' }] }
  },
  async importAccounts(kind: AccountKind, fileName: string) {
    await wait()
    return { taskId: `ACC${Date.now()}`, status: 'completed', total: 8, successCount: 7, failCount: 1, fileName, kind, errors: [{ row: 4, username: 'teacher1004', message: '登录账号已存在' }] }
  },
  async listStatistics(params: Record<string, string | number | undefined> = {}) {
    await wait()
    const filterRank = (rows: StatRow[]) => {
      const keyword = String(params.keyword ?? '')
      return rows.filter((row) => includes(row.targetName, keyword))
    }
    const cityRows: StatRow[] = [
      { rank: 1, dimension: 'city', targetId: 3, targetName: '示例市', studentCount: 12600, participantCount: 11970, participationRate: 0.95, avgScore: 81.42, passRate: 0.91, excellentRate: 0.21 },
      { rank: 2, dimension: 'city', targetId: 4, targetName: '示例第二市', studentCount: 9800, participantCount: 9016, participationRate: 0.92, avgScore: 79.86, passRate: 0.88, excellentRate: 0.17 }
    ]
    const districtRows: StatRow[] = [
      { rank: 1, dimension: 'district', targetId: 22, targetName: '示例区', studentCount: 5200, participantCount: 5010, participationRate: 0.9635, avgScore: 82.1, passRate: 0.92, excellentRate: 0.24 },
      { rank: 2, dimension: 'district', targetId: 23, targetName: '示例第二区', studentCount: 4300, participantCount: 3980, participationRate: 0.9256, avgScore: 79.4, passRate: 0.87, excellentRate: 0.18 }
    ]
    const schoolRows: StatRow[] = [
      { rank: 1, dimension: 'school', targetId: 301, targetName: '示范中学', studentCount: 1260, participantCount: 1210, participationRate: 0.96, avgScore: 82.36, passRate: 0.93, excellentRate: 0.23 },
      { rank: 2, dimension: 'school', targetId: 302, targetName: '实验中学', studentCount: 1080, participantCount: 990, participationRate: 0.9167, avgScore: 78.5, passRate: 0.86, excellentRate: 0.16 }
    ]
    const classRows: StatRow[] = [
      { rank: 1, dimension: 'class', targetId: 5001, targetName: '七年级（1）班', studentCount: 42, participantCount: 40, participationRate: 0.9524, avgScore: 82.36, passRate: 0.9231, excellentRate: 0.2308 },
      { rank: 2, dimension: 'class', targetId: 5002, targetName: '七年级（2）班', studentCount: 40, participantCount: 37, participationRate: 0.925, avgScore: 79.8, passRate: 0.89, excellentRate: 0.19 }
    ]
    const groupBy = String(params.groupBy ?? 'school')
    const rows = groupBy === 'city' ? cityRows : groupBy === 'district' ? districtRows : groupBy === 'class' ? classRows : schoolRows
    return { list: filterRank(rows), summary: { studentCount: rows.reduce((sum, row) => sum + row.studentCount, 0), participantCount: rows.reduce((sum, row) => sum + row.participantCount, 0), avgScore: 80.91, participationRate: 0.938 } }
  },
  async listLogs(params: Record<string, string | number | undefined> = {}) {
    await wait()
    const items = db.logs.filter((item) => includes(`${item.operatorName} ${item.action} ${item.description}`, String(params.keyword ?? '')))
    return page(items, Number(params.pageNum ?? 1), Number(params.pageSize ?? 10))
  },
  async getLog(id: number) {
    await wait()
    const item = db.logs.find((log) => log.id === id)
    if (!item) throw new Error('日志不存在')
    return item
  },
  async listCertificates() {
    await wait()
    return db.certificates
  },
  async getCertificate(id: number) {
    await wait()
    const item = db.certificates.find((certificate) => certificate.id === id)
    if (!item) throw new Error('证书不存在')
    return item
  },
  async generateCertificates(assessmentId: number, subject: Subject) {
    await wait()
    return { taskId: `CERT${Date.now()}`, status: 'generating', generatedCount: 0, skippedCount: 0, assessmentId, subject }
  },
  async getReport(studentId: number, subject?: Subject) {
    await wait()
    return db.reports.find((item) => item.studentId === studentId && (!subject || item.subject === subject)) ?? null
  },
  async listArtworks() {
    await wait()
    return db.artworks
  },
  async uploadArtwork(fileName: string, subject: Subject, preview?: string) {
    await wait()
    const item: StudentArtwork = {
      id: nextId(db.artworks),
      studentId: 1001,
      studentName: '王小明',
      fileName,
      subject,
      uploadedAt: now(),
      status: 'uploaded',
      preview: preview || 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22400%22 height=%22240%22%3E%3Crect width=%22400%22 height=%22240%22 fill=%22%23eef4ff%22/%3E%3Ctext x=%22200%22 y=%22125%22 text-anchor=%22middle%22 font-size=%2220%22 fill=%22%232563eb%22%3E学生作品%3C/text%3E%3C/svg%3E'
    }
    db.artworks.unshift(item)
    save()
    return item
  },
  async removeArtwork(id: number) {
    await wait()
    db.artworks = db.artworks.filter((item) => item.id !== id)
    save()
    return { deleted: true }
  },
  async startAttempt(assessmentId: number) {
    await wait()
    const existing = db.attempts.find((item) => item.assessmentId === assessmentId && item.status === 'in_progress')
    if (existing) return existing
    const assessment = db.assessments.find((item) => item.id === assessmentId)
    const attempt: Attempt = {
      ...seed().attempts[0],
      attemptId: Math.max(0, ...db.attempts.map((item) => item.attemptId)) + 1,
      assessmentId,
      title: assessment?.title ?? '随机练习',
      deadline: new Date(Date.now() + (assessment?.duration ?? 45) * 60000).toISOString()
    }
    db.attempts.push(attempt)
    save()
    return attempt
  },
  async getAttempt(attemptId: number) {
    await wait()
    const attempt = db.attempts.find((item) => item.attemptId === attemptId)
    if (!attempt) throw new Error('答卷不存在')
    return attempt
  },
  async startPractice(subject: Subject) {
    await wait()
    const sourceQuestions = db.questions.filter((item) => item.subject === subject && item.status === 'approved')
    const practiceQuestions = (sourceQuestions.length ? sourceQuestions : db.questions.filter((item) => item.status === 'approved')).slice(0, 3).map((item, index) => ({
      questionId: item.id,
      order: index + 1,
      type: item.type,
      stem: item.stem,
      score: item.score,
      options: item.options ?? [],
      resources: item.resources?.map((resource) => ({ type: resource.type, name: resource.name, url: resource.url })) ?? [],
      answerConfig: { maxLength: 500, playLimit: 2 },
      correctAnswer: typeof item.answer?.value === 'string' ? item.answer.value : typeof item.answer?.text === 'string' ? item.answer.text : '',
      analysis: item.analysis
    }))
    const attempt: Attempt = {
      ...seed().attempts[0],
      attemptId: Math.max(0, ...db.attempts.map((item) => item.attemptId)) + 1,
      assessmentId: 12990,
      paperId: 11990,
      title: `${subject === 'music' ? '音乐' : '美术'}随机练习`,
      subject,
      deadline: new Date(Date.now() + 40 * 60000).toISOString(),
      totalScore: practiceQuestions.reduce((sum, question) => sum + question.score, 0),
      questions: practiceQuestions,
      savedAnswers: []
    }
    db.attempts.push(attempt)
    save()
    return attempt
  },
  async saveAnswers(attemptId: number, answers: Attempt['savedAnswers']) {
    await wait(100)
    const attempt = db.attempts.find((item) => item.attemptId === attemptId)
    if (!attempt) throw new Error('答卷不存在')
    const merged = new Map(attempt.savedAnswers.map((item) => [item.questionId, item]))
    answers.forEach((item) => merged.set(item.questionId, item))
    attempt.savedAnswers = [...merged.values()]
    attempt.serverTime = now()
    save()
    return { savedCount: answers.length, savedAt: now(), serverTime: now(), remainingSeconds: attempt.remainingSeconds }
  },
  async submitAttempt(attemptId: number) {
    await wait()
    const attempt = db.attempts.find((item) => item.attemptId === attemptId)
    if (!attempt) throw new Error('答卷不存在')
    attempt.status = 'submitted'
    const answerDetails = attempt.questions.map((question) => {
      const saved = attempt.savedAnswers.find((item) => item.questionId === question.questionId)
      const studentAnswer = saved?.answer.value ?? saved?.answer.text ?? '未作答'
      const correct = question.correctAnswer ?? ''
      const isObjective = ['single_choice', 'multiple_choice', 'true_false', 'listening'].includes(question.type)
      const isCorrect = isObjective && studentAnswer.trim().toLowerCase() === correct.trim().toLowerCase()
      return {
        questionId: question.questionId,
        order: question.order,
        stem: question.stem,
        studentAnswer: String(studentAnswer),
        correctAnswer: correct,
        score: isCorrect ? question.score : 0,
        maxScore: question.score,
        comment: isCorrect ? '回答正确' : isObjective ? '答案不正确' : '等待教师或 AI 评分',
        aiAnalysis: question.analysis ?? null
      }
    })
    const objectiveScore = answerDetails.filter((detail) => ['single_choice', 'multiple_choice', 'true_false', 'listening'].includes(attempt.questions.find((question) => question.questionId === detail.questionId)?.type ?? '')).reduce((sum, detail) => sum + detail.score, 0)
    const totalScore = answerDetails.reduce((sum, detail) => sum + detail.score, 0)
    const maxScore = attempt.questions.reduce((sum, question) => sum + question.score, 0)
    const percentage = maxScore ? (totalScore / maxScore) * 100 : 0
    const level: Score['level'] = percentage >= 90 ? 'excellent' : percentage >= 75 ? 'good' : percentage >= 60 ? 'pass' : 'fail'
    if (!db.scores.some((score) => score.assessmentTitle === attempt.title && score.studentName === '王小明')) {
      db.scores.unshift({
        id: nextId(db.scores),
        assessmentId: attempt.assessmentId,
        assessmentTitle: attempt.title,
        subject: attempt.subject,
        studentNo: 'S20260001',
        studentName: '王小明',
        className: '七年级（1）班',
        objectiveScore,
        subjectiveScore: 0,
        aiScore: 0,
        totalScore,
        level,
        status: 'grading',
        source: 'online',
        createdAt: now(),
        answerVisible: true,
        answerDetails
      })
    }
    save()
    return { attemptId, status: 'submitted', gradingStatus: 'grading', totalScore: 88 }
  },
  reset() {
    localStorage.removeItem(STORAGE_KEY)
  }
}
