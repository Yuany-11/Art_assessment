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
  NotificationItem,
  OperationLog,
  PageResult,
  Paper,
  PaperReviewLog,
  PaperReviewResult,
  Question,
  Role,
  Score,
  SchoolClass,
  StatRow,
  Subject,
  StudentArtwork,
  WrongQuestionDetail,
  WrongQuestionStatistics
} from '@/types'

const STORAGE_KEY = 'art-assessment-mock-db-v9'

interface MockDatabase {
  accounts: Account[]
  classes: SchoolClass[]
  classRequests: ClassRequest[]
  papers: Paper[]
  paperReviews: PaperReviewLog[]
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
  wrongQuestions: WrongQuestionDetail[]
  notifications: Array<NotificationItem & { recipientRole: Role }>
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
    { id: 6101, courseId: 6001, courseName: '七年级音乐鉴赏', name: '节奏与节拍', description: '认识常见拍号', content: `· 2/4 拍：以四分音符为一拍，每小节两拍，强弱规律为 强、弱。
· 3/4 拍：每小节三拍，强弱规律为 强、弱、弱。
· 4/4 拍：每小节四拍，强弱规律为 强、弱、次强、弱。`, questionCount: 18, sortOrder: 1 },
    { id: 6102, courseId: 6001, courseName: '七年级音乐鉴赏', name: '旋律与音色', description: '感受旋律和音色', content: `· 旋律是高低起伏的音线，级进平稳、跳进活跃。
· 音色是不同乐器或人声的嗓音特色：木管柔和、铜管明亮、弦乐温暖。`, questionCount: 22, sortOrder: 2 },
    { id: 6201, courseId: 6002, courseName: '七年级美术鉴赏', name: '构图基础', description: '理解画面组织', content: `· 构图是画面的组织方式，决定视觉重心。
· 三分法：把画面横竖各三等分，主体放在交点附近更耐看。
· 主体不宜顶天立地，也要避免缩在角落。`, questionCount: 16, sortOrder: 1 },
    { id: 6202, courseId: 6002, courseName: '七年级美术鉴赏', name: '色彩基础', description: '认识色彩关系', content: `· 色彩三要素：色相、明度、纯度。
· 红与绿、蓝与橙是互补色，对比强烈；蓝与绿是邻近色，和谐统一。`, questionCount: 20, sortOrder: 2 }
  ]
  const questions: Question[] = [
    { id: 9001, subject: 'music', grade: 7, courseId: 6001, courseName: '七年级音乐鉴赏', chapterId: 6101, chapterName: '节奏与节拍', type: 'single_choice', difficulty: 2, stem: '聆听音频，判断这段旋律的拍号。', score: 5, status: 'approved', creatorName: '李老师', resourceCount: 1, options: [{ key: 'A', text: '2/4' }, { key: 'B', text: '3/4' }, { key: 'C', text: '4/4' }, { key: 'D', text: '6/8' }], answer: { value: 'B' }, analysis: '旋律呈现强弱弱的周期性规律，应为三拍子。', resources: [{ resourceId: 9101, type: 'audio', name: '听赏示例音频' }], createdAt: '2026-10-01T09:00:00+08:00', updatedAt: '2026-10-02T09:00:00+08:00' },
    { id: 9002, subject: 'music', grade: 7, courseId: 6001, courseName: '七年级音乐鉴赏', chapterId: 6102, chapterName: '旋律与音色', type: 'short_answer', difficulty: 3, stem: '分析乐曲的情绪与节奏特点。', score: 15, status: 'pending', creatorName: '李老师', resourceCount: 0, answer: { text: '节奏鲜明、旋律跳跃，整体情绪欢快热烈。' }, analysis: '从情绪、节奏、旋律三个维度作答。', resources: [], createdAt: '2026-10-03T09:00:00+08:00', updatedAt: '2026-10-03T09:00:00+08:00' },
    { id: 9003, subject: 'art', grade: 7, courseId: 6002, courseName: '七年级美术鉴赏', chapterId: 6201, chapterName: '构图基础', type: 'image_upload', difficulty: 4, stem: '上传一幅静物素描作品。', score: 25, status: 'approved', creatorName: '赵老师', resourceCount: 0, answer: { rubric: '构图 8 分；造型 8 分；细节 5 分；完整度 4 分。' }, analysis: '重点观察构图重心、比例关系和明暗层次。', resources: [], createdAt: '2026-10-04T09:00:00+08:00', updatedAt: '2026-10-04T09:00:00+08:00' }
  ]
  questions.push(
    { id: 9004, subject: 'music', grade: 7, courseId: 6001, courseName: '七年级音乐鉴赏', chapterId: 6101, chapterName: '节奏与节拍', type: 'single_choice', difficulty: 2, stem: '下列力度记号中，表示“很强”的是？', score: 5, status: 'approved', creatorName: '李老师', resourceCount: 0, options: [{ key: 'A', text: 'ff' }, { key: 'B', text: 'p' }, { key: 'C', text: 'mp' }, { key: 'D', text: 'mf' }], answer: { value: 'A' }, analysis: 'ff 是 fortissimo 的缩写，表示很强。', resources: [], createdAt: '2026-10-05T09:00:00+08:00', updatedAt: '2026-10-05T09:00:00+08:00' },
    { id: 9005, subject: 'music', grade: 7, courseId: 6001, courseName: '七年级音乐鉴赏', chapterId: 6102, chapterName: '旋律与音色', type: 'true_false', difficulty: 2, stem: '木管乐器中的单簧管属于铜管乐器组。', score: 5, status: 'approved', creatorName: '李老师', resourceCount: 0, options: [{ key: 'A', text: '正确' }, { key: 'B', text: '错误' }], answer: { value: 'B' }, analysis: '单簧管属于木管乐器组。', resources: [], createdAt: '2026-10-05T10:00:00+08:00', updatedAt: '2026-10-05T10:00:00+08:00' },
    { id: 9006, subject: 'music', grade: 7, courseId: 6001, courseName: '七年级音乐鉴赏', chapterId: 6102, chapterName: '旋律与音色', type: 'short_answer', difficulty: 3, stem: '简述旋律进行中“级进”和“跳进”的区别。', score: 10, status: 'approved', creatorName: '李老师', resourceCount: 0, answer: { text: '级进是相邻音级之间平稳进行；跳进是跨越多个音级的进行，起伏更明显。' }, analysis: '可从音程距离和旋律起伏两个方面作答。', resources: [], createdAt: '2026-10-06T09:00:00+08:00', updatedAt: '2026-10-06T09:00:00+08:00' },
    { id: 9007, subject: 'art', grade: 7, courseId: 6002, courseName: '七年级美术鉴赏', chapterId: 6202, chapterName: '色彩基础', type: 'single_choice', difficulty: 2, stem: '红色与绿色在色相环上属于哪类色彩关系？', score: 5, status: 'approved', creatorName: '赵老师', resourceCount: 0, options: [{ key: 'A', text: '同类色' }, { key: 'B', text: '邻近色' }, { key: 'C', text: '互补色' }, { key: 'D', text: '冷暖色' }], answer: { value: 'C' }, analysis: '红与绿位于色相环相对位置，是典型互补色。', resources: [], createdAt: '2026-10-05T09:30:00+08:00', updatedAt: '2026-10-05T09:30:00+08:00' },
    { id: 9008, subject: 'art', grade: 7, courseId: 6002, courseName: '七年级美术鉴赏', chapterId: 6201, chapterName: '构图基础', type: 'true_false', difficulty: 2, stem: '三分法构图通常将主体安排在画面三等分线或交点附近。', score: 5, status: 'approved', creatorName: '赵老师', resourceCount: 0, options: [{ key: 'A', text: '正确' }, { key: 'B', text: '错误' }], answer: { value: 'A' }, analysis: '三分法利用三等分线和交点组织视觉重心。', resources: [], createdAt: '2026-10-05T10:30:00+08:00', updatedAt: '2026-10-05T10:30:00+08:00' },
    { id: 9009, subject: 'art', grade: 7, courseId: 6002, courseName: '七年级美术鉴赏', chapterId: 6202, chapterName: '色彩基础', type: 'short_answer', difficulty: 3, stem: '简述冷暖色在画面中分别可以营造怎样的视觉感受。', score: 10, status: 'approved', creatorName: '赵老师', resourceCount: 0, answer: { text: '暖色常带来热情、温暖、前进的感受；冷色常带来安静、冷静、后退的感受。' }, analysis: '结合心理感受和空间感说明色彩倾向。', resources: [], createdAt: '2026-10-06T10:00:00+08:00', updatedAt: '2026-10-06T10:00:00+08:00' }
  )
  const papers: Paper[] = [
    { id: 11001, title: '2026 秋季七年级音乐测评卷', subject: 'music', paperType: 'formal', grade: 7, scopeType: 'school', scopeId: 301, scopeName: '示范中学', totalScore: 20, questionCount: 2, duration: 45, generateMode: 'manual', status: 'ready', reviewStatus: 'approved', reviewComment: '题目与分值检查无误，同意发布。', reviewerId: 2201, reviewerName: '刘主任', reviewedAt: '2026-10-22T10:10:00+08:00', version: 3, creatorId: 3001, creatorName: '孙校长', instructions: '请独立完成，听力题音频播放两遍。', createdAt: '2026-10-21T09:00:00+08:00', updatedAt: '2026-10-21T09:30:00+08:00', questions: [{ questionId: 9001, stem: '聆听音频，判断这段旋律的拍号。', type: 'single_choice', score: 5, sectionName: '听力选择', options: [{ key: 'A', text: '2/4' }, { key: 'B', text: '3/4' }, { key: 'C', text: '4/4' }, { key: 'D', text: '6/8' }], resources: [{ type: 'audio', name: '听赏示例音频' }], analysis: '旋律呈现强弱弱的周期性规律。' }, { questionId: 9002, stem: '分析乐曲的情绪与节奏特点。', type: 'short_answer', score: 15, sectionName: '简答题', options: [], resources: [], analysis: '从情绪、节奏、旋律三个维度作答。' }] },
    { id: 11002, title: '七年级美术构图练习卷', subject: 'art', paperType: 'practice', grade: 7, scopeType: 'district', scopeId: 22, scopeName: '示例区', totalScore: 25, questionCount: 1, duration: 30, generateMode: 'auto', status: 'draft', reviewStatus: 'pending', reviewComment: null, reviewerId: 3011, reviewerName: '周局长', reviewedAt: null, version: 2, creatorId: 2201, creatorName: '刘主任', instructions: '上传一幅能够体现空间层次和主体关系的静物素描作品。', createdAt: '2026-10-21T10:00:00+08:00', updatedAt: '2026-10-21T10:00:00+08:00', questions: [{ questionId: 9003, stem: '上传一幅静物素描作品。', type: 'image_upload', score: 25, sectionName: '作品题', options: [], resources: [], analysis: '重点观察构图、比例和明暗层次。' }] }
  ]
  const paperReviews: PaperReviewLog[] = [
    { id: 9301, paperId: 11001, version: 3, action: 'approve', reviewerId: 2201, reviewerName: '刘主任', comment: '题目与分值检查无误，同意发布。', createdAt: '2026-10-22T10:10:00+08:00' },
    { id: 9302, paperId: 11001, version: 3, action: 'submit', reviewerId: null, reviewerName: null, comment: '请审核本学期七年级音乐期中卷。', createdAt: '2026-10-22T09:30:00+08:00' },
    { id: 9303, paperId: 11002, version: 2, action: 'submit', reviewerId: null, reviewerName: null, comment: '提交美术构图练习卷审核。', createdAt: '2026-10-22T11:00:00+08:00' }
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
    { id: 5001, classCode: 'C20260701', name: '七年级（1）班', grade: 7, schoolName: '示范中学', headTeacherId: 2001, headTeacherName: '李老师', headTeacherAccount: 'teacher1001', headTeacherSubject: 'music', headTeacherPhone: '13800002001', studentCount: 42, status: 'active', createdAt: '2026-09-01T10:00:00+08:00' },
    { id: 5002, classCode: 'C20260702', name: '七年级（2）班', grade: 7, schoolName: '示范中学', headTeacherId: 2002, headTeacherName: '赵老师', headTeacherAccount: 'teacher1002', headTeacherSubject: 'art', headTeacherPhone: '13800002002', studentCount: 40, status: 'active', createdAt: '2026-09-01T10:10:00+08:00' }
  ]
  const classRequests: ClassRequest[] = [
    { id: 7001, classId: 5001, className: '七年级（1）班', requesterId: 1001, requesterName: '王小明', requesterRole: 'student', type: 'join', status: 'pending', reason: '本人为该班学生', createdAt: '2026-10-20T11:30:00+08:00' }
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
    { id: 15001, certificateNo: 'YS2026-MUSIC-000001', studentId: 1001, studentNo: 'S20260001', studentName: '王小明', assessmentTitle: assessments[0].title, subject: 'music', score: 88, level: '良好', issueDate: '2026-10-26', status: 'ready' },
    { id: 15002, certificateNo: 'YS2026-MUSIC-000002', studentId: 1002, studentNo: 'S20260002', studentName: '陈小雨', assessmentTitle: assessments[0].title, subject: 'music', score: 80, level: '良好', issueDate: '2026-10-26', status: 'ready' }
  ]
  const logs: OperationLog[] = [
    { id: 12001, operatorName: '题库管理员', role: 'question_admin', action: 'question.review', resourceType: 'question', resourceId: 9001, description: '审核试题 9001：通过', ip: '10.0.0.15', result: 'success', createdAt: '2026-10-20T15:00:00+08:00' },
    { id: 12002, operatorName: '孙校长', role: 'school_admin', action: 'assessment.publish', resourceType: 'assessment', resourceId: 12001, description: '发布七年级音乐正式测评', ip: '10.0.0.31', result: 'success', createdAt: '2026-10-21T11:00:00+08:00' }
  ]
  const attempt: Attempt = {
    attemptId: 13001,
    studentId: 1001,
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
  const wrongQuestions: WrongQuestionDetail[] = [
    {
      id: 91001,
      questionId: 9001,
      subject: 'music',
      type: 'single_choice',
      stem: '聆听音频，判断这段旋律的拍号。',
      options: [{ key: 'A', text: '2/4' }, { key: 'B', text: '3/4' }, { key: 'C', text: '4/4' }, { key: 'D', text: '6/8' }],
      correctAnswer: { value: 'B' },
      studentAnswer: { value: 'A' },
      analysis: '旋律呈现强弱弱的周期性规律，应为三拍子。',
      resources: [{ type: 'audio', name: '听赏示例音频' }],
      note: '需要再听一遍强弱规律。',
      wrongCount: 2,
      lastWrongAt: '2026-10-21T15:20:00+08:00',
      masteryStatus: 'unmastered',
      sourceType: 'formal',
      sourceAssessmentTitle: '2026 秋季七年级音乐正式测评',
      records: [{ attemptId: 81001, answer: { value: 'A' }, createdAt: '2026-10-21T15:20:00+08:00' }, { attemptId: 81002, answer: { value: 'A' }, createdAt: '2026-10-18T10:10:00+08:00' }]
    },
    {
      id: 91002,
      questionId: 9003,
      subject: 'art',
      type: 'image_upload',
      stem: '上传一幅静物素描作品。',
      options: [],
      correctAnswer: { rubric: '构图 8 分；造型 8 分；细节 5 分；完整度 4 分。' },
      studentAnswer: { text: '构图偏右，明暗关系较弱。' },
      analysis: '重点观察构图重心、比例关系和明暗层次。',
      resources: [],
      note: null,
      wrongCount: 1,
      lastWrongAt: '2026-10-20T09:30:00+08:00',
      masteryStatus: 'reviewing',
      sourceType: 'formal',
      sourceAssessmentTitle: '七年级美术构图测评',
      records: [{ attemptId: 81003, answer: { text: '构图偏右，明暗关系较弱。' }, createdAt: '2026-10-20T09:30:00+08:00' }]
    }
  ]
  const notifications: Array<NotificationItem & { recipientRole: Role }> = [
    { id: 70001, type: 'paper_review_submitted', title: '新的试卷待审核', content: '《七年级美术构图练习卷》已提交审核，请及时处理。', link: '/papers', read: false, createdAt: '2026-10-22T11:00:00+08:00', recipientRole: 'city_admin' },
    { id: 70002, type: 'paper_review_approved', title: '试卷审核通过', content: '《2026 秋季七年级音乐测评卷》已审核通过，可以发布。', link: '/papers', read: false, createdAt: '2026-10-22T10:10:00+08:00', recipientRole: 'school_admin' },
    { id: 70003, type: 'system', title: '错题本功能已上线', content: '现在可以查看错题、标记掌握状态并进行错题重做。', link: '/student/wrong-questions', read: false, createdAt: '2026-10-22T08:30:00+08:00', recipientRole: 'student' }
  ]
  return { accounts, classes, classRequests, papers, paperReviews, assessments, questions, courses, chapters, scores, gradingTasks, certificates, logs, attempts: [attempt], reports, artworks, wrongQuestions, notifications }
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

function shuffle<T>(items: T[]) {
  const result = [...items]
  for (let index = result.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1))
    ;[result[index], result[swapIndex]] = [result[swapIndex], result[index]]
  }
  return result
}

function wait(ms = 180) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function includes(value: string | null | undefined, keyword: string) {
  return !keyword || String(value ?? '').toLowerCase().includes(keyword.toLowerCase())
}

function currentSession() {
  const stored = localStorage.getItem('art-assessment-session') ?? sessionStorage.getItem('art-assessment-session')
  if (!stored) return { role: 'school_admin' as Role, realName: '当前用户', id: 3001 }
  try {
    const parsed = JSON.parse(stored) as { role?: Role; user?: { realName?: string; id?: number } }
    return {
      role: parsed.role ?? ('school_admin' as Role),
      realName: parsed.user?.realName ?? '当前用户',
      id: parsed.user?.id ?? 3001
    }
  } catch {
    return { role: 'school_admin' as Role, realName: '当前用户', id: 3001 }
  }
}

function assertCertificateAccess(certificate: Certificate) {
  const session = currentSession()
  if (session.role === 'student') {
    const student = db.accounts.find((row) => row.kind === 'students' && row.id === session.id)
    if (certificate.studentNo !== student?.studentNo && certificate.studentId !== student?.id) {
      throw new Error('无权查看其他学生证书')
    }
  }
  if (session.role === 'teacher') {
    const student = db.accounts.find((row) => (
      row.kind === 'students' &&
      (row.id === certificate.studentId || row.studentNo === certificate.studentNo || row.realName === certificate.studentName)
    ))
    const classInfo = db.classes.find((row) => row.id === student?.classId)
    if (classInfo?.headTeacherId !== session.id && classInfo?.headTeacherName !== session.realName) {
      throw new Error('无权查看非任教班级学生证书')
    }
  }
}

function reviewerForRole(_role: Role): Role {
  return 'question_admin'
}

function roleUserId(role: Role) {
  const map: Record<Role, number> = {
    student: 1001,
    teacher: 2001,
    school_admin: 3001,
    district_admin: 2201,
    city_admin: 3011,
    province_admin: 4001,
    question_admin: 7001
  }
  return map[role]
}

function pushNotification(recipientRole: Role, type: NotificationItem['type'], title: string, content: string, link: string | null) {
  db.notifications.unshift({
    id: nextId(db.notifications),
    recipientRole,
    type,
    title,
    content,
    link,
    read: false,
    createdAt: now()
  })
}

function upsertWrongQuestion(question: {
  questionId: number
  subject: Subject
  type: string
  stem: string
  score: number
  options?: Array<{ key: string; text: string }>
  correctAnswer?: string | Record<string, unknown>
  analysis?: string | null
  resources?: Array<{ type: string; name: string; url?: string }>
}, answer: Record<string, unknown>, attemptId: number, sourceType: WrongQuestionDetail['sourceType'], sourceTitle: string | null) {
  let item = db.wrongQuestions.find((wrong) => wrong.questionId === question.questionId)
  const optionSnapshot = question.options ?? []
  if (!item) {
    item = {
      id: nextId(db.wrongQuestions),
      questionId: question.questionId,
      subject: db.questions.find((row) => row.id === question.questionId)?.subject ?? 'music',
      type: question.type,
      stem: question.stem,
      options: optionSnapshot,
      correctAnswer: typeof question.correctAnswer === 'string' ? { value: question.correctAnswer } : question.correctAnswer ?? {},
      studentAnswer: answer,
      analysis: question.analysis ?? null,
      resources: question.resources ?? [],
      note: null,
      wrongCount: 0,
      lastWrongAt: now(),
      masteryStatus: 'unmastered',
      sourceType,
      sourceAssessmentTitle: sourceTitle,
      records: []
    }
    db.wrongQuestions.unshift(item)
  }
  if (!item.records.some((record) => record.attemptId === attemptId)) {
    item.wrongCount += 1
    item.records.unshift({ attemptId, answer, createdAt: now() })
  }
  item.studentAnswer = answer
  item.lastWrongAt = now()
  item.sourceType = sourceType
  item.sourceAssessmentTitle = sourceTitle
}

export const mockApi = {
  async listClasses(params: Record<string, string | number | undefined> = {}) {
    await wait()
    const items = db.classes.filter((item) =>
      includes(`${item.name} ${item.classCode}`, String(params.keyword ?? '')) &&
      (!params.classCode || item.classCode.toLowerCase() === String(params.classCode).toLowerCase()) &&
      (!params.status || item.status === params.status)
    )
    return page(items, Number(params.pageNum ?? 1), Number(params.pageSize ?? 10))
  },
  async searchClass(classCode: string) {
    await wait()
    const normalized = classCode.trim().toLowerCase()
    return db.classes.find((item) => item.classCode.toLowerCase() === normalized) ?? null
  },
  async createClass(values: Partial<SchoolClass>) {
    await wait()
    const classCode = values.classCode?.trim() || `C${Date.now().toString().slice(-8)}`
    if (db.classes.some((item) => item.classCode.toLowerCase() === classCode.toLowerCase())) {
      throw new Error('班级号已存在，请更换后重试')
    }
    const headTeacher = db.accounts.find((item) =>
      item.kind === 'teachers' &&
      (item.id === values.headTeacherId || item.realName === values.headTeacherName || item.username === values.headTeacherAccount)
    )
    const item: SchoolClass = {
      id: nextId(db.classes),
      classCode,
      name: values.name?.trim() ?? '新班级',
      grade: Number(values.grade ?? 7),
      schoolName: values.schoolName ?? '示范中学',
      headTeacherId: headTeacher?.id ?? values.headTeacherId ?? null,
      headTeacherName: headTeacher?.realName ?? values.headTeacherName ?? '待指定',
      headTeacherAccount: headTeacher?.username ?? values.headTeacherAccount ?? null,
      headTeacherSubject: headTeacher?.subject ?? values.headTeacherSubject ?? null,
      headTeacherPhone: headTeacher?.phone ?? values.headTeacherPhone ?? null,
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
    const nextCode = values.classCode?.trim()
    if (nextCode && db.classes.some((row) => row.id !== id && row.classCode.toLowerCase() === nextCode.toLowerCase())) {
      throw new Error('班级号已被其他班级使用')
    }
    const oldName = item.name
    const headTeacher = db.accounts.find((row) =>
      row.kind === 'teachers' &&
      (row.id === values.headTeacherId || row.realName === values.headTeacherName || row.username === values.headTeacherAccount)
    )
    const teacherChanged = values.headTeacherId !== undefined || values.headTeacherName !== undefined || values.headTeacherAccount !== undefined
    Object.assign(item, values, {
      classCode: nextCode || item.classCode,
      name: values.name?.trim() || item.name,
      headTeacherId: headTeacher?.id ?? values.headTeacherId ?? (teacherChanged ? null : item.headTeacherId),
      headTeacherName: headTeacher?.realName ?? values.headTeacherName ?? item.headTeacherName,
      headTeacherAccount: headTeacher?.username ?? values.headTeacherAccount ?? (teacherChanged ? null : item.headTeacherAccount),
      headTeacherSubject: headTeacher?.subject ?? values.headTeacherSubject ?? (teacherChanged ? null : item.headTeacherSubject),
      headTeacherPhone: headTeacher?.phone ?? values.headTeacherPhone ?? (teacherChanged ? null : item.headTeacherPhone)
    })
    if (oldName !== item.name) {
      db.accounts.filter((row) => row.classId === id).forEach((student) => {
        student.className = item.name
      })
      db.classRequests.filter((row) => row.classId === id).forEach((request) => {
        request.className = item.name
      })
    }
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
    return db.classRequests
      .filter((item) => item.classId === classId)
      .sort((a, b) => Number(a.status !== 'pending') - Number(b.status !== 'pending') || b.createdAt.localeCompare(a.createdAt))
  },
  async reviewClassRequest(id: number, action: 'approve' | 'reject') {
    await wait()
    const item = db.classRequests.find((row) => row.id === id)
    if (!item) throw new Error('申请不存在')
    item.status = action === 'approve' ? 'approved' : 'rejected'
    item.reviewedAt = now()
    item.reviewComment = action === 'approve' ? '审核通过' : '审核驳回'
    if (action === 'approve' && item.requesterRole === 'student') {
      const student = db.accounts.find((row) => row.kind === 'students' && (
        (item.requesterId && row.id === item.requesterId) || row.realName === item.requesterName
      ))
      if (student) {
        const oldClass = db.classes.find((row) => row.id === student.classId)
        const targetClass = item.type === 'leave'
          ? null
          : db.classes.find((row) => row.id === (item.type === 'change' ? item.targetClassId : item.classId))
        if (oldClass?.id !== targetClass?.id) {
          if (oldClass) oldClass.studentCount = Math.max(0, oldClass.studentCount - 1)
          if (targetClass) targetClass.studentCount += 1
        }
        student.classId = targetClass?.id ?? null
        student.className = targetClass?.name ?? null
        student.grade = targetClass?.grade ?? student.grade
      }
    }
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
      requesterId: currentSession().id,
      requesterName,
      requesterRole,
      type,
      targetClassId: targetClassId ?? null,
      status: 'pending',
      reason: reason || '学生提交申请',
      createdAt: now()
    }
    db.classRequests.unshift(request)
    if (type === 'change' && targetClassId) {
      const target = db.classes.find((item) => item.id === targetClassId)
      if (target) {
        request.targetClassName = target.name
        request.className = `${classInfo.name} → ${target.name}`
      }
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
    const classInfo = db.classes.find((item) => item.id === classId)
    if (classInfo) classInfo.studentCount = Math.max(0, classInfo.studentCount - 1)
    student.classId = null
    student.className = null
    save()
    return { removed: true }
  },
  async importClassStudents(fileName: string) {
    await wait()
    return {
      taskId: `STU${Date.now()}`,
      status: 'completed',
      total: 45,
      successCount: 43,
      failCount: 2,
      fileName,
      errors: [{ row: 12, studentNo: 'S20260045', message: '学籍号已存在' }, { row: 30, studentNo: 'S20260063', message: '性别格式不正确' }],
      credentials: [
        { studentNo: 'S20260010', name: '王小明', username: 'student_010', password: 'Stu@2026a' },
        { studentNo: 'S20260011', name: '李小雨', username: 'student_011', password: 'Stu@2026b' }
      ]
    }
  },
  async listAccounts(kind: AccountKind, params: Record<string, string | number | undefined> = {}) {
    await wait()
    const keyword = String(params.keyword ?? '')
    const status = String(params.status ?? '')
    const session = currentSession()
    const teacherClassIds = session.role === 'teacher'
      ? db.classes
          .filter((item) => item.headTeacherId === session.id || item.headTeacherName === session.realName)
          .map((item) => item.id)
      : []
    const items = db.accounts.filter((item) =>
      item.kind === kind &&
      includes(`${item.username} ${item.realName} ${item.studentNo ?? ''}`, keyword) &&
      (!status || item.status === status) &&
      (!params.classId || item.classId === Number(params.classId)) &&
      (kind !== 'students' || session.role !== 'teacher' || teacherClassIds.includes(item.classId ?? -1)) &&
      (kind !== 'students' || session.role !== 'student' || item.id === session.id)
    )
    return page(items, Number(params.pageNum ?? 1), Number(params.pageSize ?? 10))
  },
  async orgOptions(params: { level: 'city' | 'district' | 'school'; parentId?: number; keyword?: string }) {
    await wait()
    const kind: AccountKind = params.level === 'school' ? 'schools' : params.level === 'district' ? 'districts' : 'cities'
    const keyword = String(params.keyword ?? '')
    const seen = new Set<number>()
    const list = db.accounts
      .filter((item) => item.kind === kind)
      .filter((item) => !keyword || `${item.realName}${item.username}`.includes(keyword))
      .flatMap((item) => {
        const id = item.orgId ?? item.id
        if (seen.has(id)) return []
        seen.add(id)
        return [{
          id,
          name: item.orgName ?? item.realName,
          code: item.username,
          level: params.level,
          parentId: null,
          parentName: null,
          schoolType: null
        }]
      })
    return { list }
  },
  async getAccount(id: number) {
    await wait()
    const session = currentSession()
    const item = db.accounts.find((account) => account.id === id)
    if (!item) throw new Error('学生信息不存在')
    if (session.role === 'student' && item.id !== session.id) throw new Error('无权查看其他学生信息')
    if (session.role === 'teacher' && item.kind === 'students') {
      const classInfo = db.classes.find((row) => row.id === item.classId)
      const isOwnClass = classInfo?.headTeacherId === session.id || classInfo?.headTeacherName === session.realName
      if (!isOwnClass) throw new Error('无权查看非任教班级学生信息')
    }
    return item
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
      (!params.reviewStatus || item.reviewStatus === params.reviewStatus) &&
      includes(item.title, String(params.keyword ?? ''))
    )
    return page(items, Number(params.pageNum ?? 1), Number(params.pageSize ?? 10))
  },
  async getPaper(id: number) {
    await wait()
    const item = db.papers.find((paper) => paper.id === id)
    if (!item) throw new Error('试卷不存在')
    return {
      ...item,
      questions: item.questions?.map((question) => {
        const source = db.questions.find((row) => row.id === question.questionId)
        return {
          ...question,
          options: question.options ?? source?.options ?? [],
          resources: question.resources ?? source?.resources?.map((resource) => ({ type: resource.type, name: resource.name, url: resource.url })) ?? []
        }
      })
    }
  },
  async createPaper(values: Record<string, unknown>, mode: 'manual' | 'auto') {
    await wait()
    const session = currentSession()
    const requestedIds = Array.isArray(values.questionIds) ? values.questionIds.map(Number) : []
    const matchingQuestions = db.questions.filter((question) =>
      question.subject === ((values.subject as Subject) ?? 'music') &&
      (requestedIds.length ? requestedIds.includes(question.id) : true)
    )
    const questionSnapshots = matchingQuestions.slice(0, Number(values.questionCount ?? 2)).map((question) => ({
      questionId: question.id,
      stem: question.stem,
      type: question.type,
      score: question.score,
      sectionName: '试题',
      analysis: question.analysis,
      options: question.options ?? [],
      resources: question.resources?.map((resource) => ({ type: resource.type, name: resource.name, url: resource.url })) ?? []
    }))
    const item: Paper = {
      id: nextId(db.papers),
      title: String(values.title ?? '未命名试卷'),
      subject: (values.subject as Subject) ?? 'music',
      paperType: (values.paperType as Paper['paperType']) ?? 'practice',
      grade: Number(values.grade ?? 7),
      scopeType: (values.scopeType as Paper['scopeType']) ?? 'school',
      scopeId: Number(values.scopeId ?? 301),
      scopeName: String(values.scopeName ?? '示范中学'),
      totalScore: questionSnapshots.reduce((sum, question) => sum + question.score, 0),
      questionCount: questionSnapshots.length,
      duration: Number(values.duration ?? 45),
      generateMode: mode,
      status: (values.status as Paper['status']) ?? 'draft',
      reviewStatus: 'none',
      reviewComment: null,
      reviewerId: null,
      reviewerName: null,
      reviewedAt: null,
      version: 1,
      creatorId: session.id,
      creatorName: session.realName,
      instructions: String(values.instructions ?? ''),
      createdAt: now(),
      updatedAt: now(),
      questions: questionSnapshots
    }
    db.papers.unshift(item)
    save()
    return item
  },
  async updatePaper(id: number, values: Partial<Paper>) {
    await wait()
    const item = db.papers.find((paper) => paper.id === id)
    if (!item) throw new Error('试卷不存在')
    const contentChanged = Object.keys(values).some((key) => !['status', 'reviewStatus', 'reviewComment', 'reviewerId', 'reviewerName', 'reviewedAt', 'version'].includes(key))
    Object.assign(item, values)
    if (contentChanged) {
      item.version += 1
      item.reviewStatus = 'none'
      item.reviewComment = null
      item.reviewerId = null
      item.reviewerName = null
      item.reviewedAt = null
      item.status = 'draft'
    }
    item.updatedAt = now()
    save()
    return item
  },
  async removePaper(id: number) {
    await wait()
    const item = db.papers.find((paper) => paper.id === id)
    if (!item) throw new Error('试卷不存在')
    if (['pending', 'approved', 'published'].includes(item.reviewStatus) || item.status === 'published') {
      throw new Error('待审核、审核通过或已发布试卷不能删除')
    }
    db.papers = db.papers.filter((paper) => paper.id !== id)
    save()
    return { deleted: true }
  },
  async submitPaperReview(id: number, version: number, comment?: string) {
    await wait()
    const paper = db.papers.find((item) => item.id === id)
    if (!paper) throw new Error('试卷不存在')
    if (paper.version !== version) throw new Error('试卷版本已变化，请刷新后重试')
    if (!['draft', 'ready', 'rejected'].includes(paper.reviewStatus) && paper.reviewStatus !== 'none') throw new Error('当前试卷状态不允许提交审核')
    if (!paper.questions?.length || paper.totalScore <= 0) throw new Error('试卷题目或总分不完整')
    const session = currentSession()
    const reviewerRole = reviewerForRole(session.role)
    paper.reviewStatus = 'pending'
    paper.status = 'ready'
    paper.reviewComment = null
    paper.reviewerId = roleUserId(reviewerRole)
    paper.reviewerName = roleName[reviewerRole]
    paper.reviewedAt = null
    db.paperReviews.unshift({ id: nextId(db.paperReviews), paperId: id, version, action: 'submit', reviewerId: null, reviewerName: null, comment: comment || null, createdAt: now() })
    pushNotification(reviewerRole, 'paper_review_submitted', '新的试卷待审核', `《${paper.title}》已提交审核，请及时处理。`, '/papers')
    save()
    return {
      paperId: id,
      reviewStatus: 'pending',
      version,
      submittedAt: now(),
      reviewerId: paper.reviewerId,
      reviewerName: paper.reviewerName,
      reviewComment: null,
      reviewedAt: null
    } satisfies PaperReviewResult
  },
  async reviewPaper(id: number, action: 'approve' | 'reject', comment: string, version: number) {
    await wait()
    const paper = db.papers.find((item) => item.id === id)
    if (!paper) throw new Error('试卷不存在')
    if (paper.reviewStatus !== 'pending') throw new Error('试卷不在待审核状态')
    if (paper.version !== version) throw new Error('试卷版本已变化，请刷新后重试')
    const session = currentSession()
    if (paper.creatorId === session.id) throw new Error('不能审核自己创建的试卷')
    if (paper.reviewerId !== session.id) throw new Error('当前账号不是该试卷的指定审核人')
    if (action === 'reject' && !comment.trim()) throw new Error('驳回原因不能为空')
    paper.reviewStatus = action === 'approve' ? 'approved' : 'rejected'
    paper.status = action === 'approve' ? 'ready' : 'draft'
    paper.reviewComment = comment || null
    paper.reviewerId = session.id
    paper.reviewerName = session.realName
    paper.reviewedAt = now()
    db.paperReviews.unshift({ id: nextId(db.paperReviews), paperId: id, version, action, reviewerId: session.id, reviewerName: session.realName, comment: comment || null, createdAt: now() })
    const creatorRole: Role = paper.scopeType === 'class'
      ? 'teacher'
      : paper.scopeType === 'district'
        ? 'district_admin'
        : paper.scopeType === 'city'
          ? 'city_admin'
          : paper.scopeType === 'province'
            ? 'province_admin'
            : 'school_admin'
    pushNotification(
      creatorRole,
      action === 'approve' ? 'paper_review_approved' : 'paper_review_rejected',
      action === 'approve' ? '试卷审核通过' : '试卷审核未通过',
      action === 'approve' ? `《${paper.title}》已审核通过，可以发布。` : `《${paper.title}》被驳回：${comment}`,
      '/papers'
    )
    save()
    return {
      paperId: id,
      reviewStatus: paper.reviewStatus,
      version,
      submittedAt: null,
      reviewerId: paper.reviewerId,
      reviewerName: paper.reviewerName,
      reviewComment: paper.reviewComment,
      reviewedAt: paper.reviewedAt
    } satisfies PaperReviewResult
  },
  async listPaperReviews(id: number) {
    await wait()
    return db.paperReviews.filter((item) => item.paperId === id).sort((a, b) => b.createdAt.localeCompare(a.createdAt))
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
    if (paper.reviewStatus !== 'approved' || paper.status !== 'ready') {
      throw new Error('试卷必须审核通过且处于已就绪状态才能发布')
    }
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
    const item = await this.getQuestion(id)
    const result = await this.updateQuestion(id, { status: action === 'approve' ? 'approved' : 'rejected' })
    pushNotification(
      'teacher',
      action === 'approve' ? 'question_review_approved' : 'question_review_rejected',
      action === 'approve' ? '试题审核通过' : '试题审核未通过',
      `试题 ${item.id}《${item.stem.slice(0, 28)}》${action === 'approve' ? '已通过审核。' : '已被驳回，请修改后重新提交。'}`,
      '/teacher/questions'
    )
    save()
    return result
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
      content: values.content ?? '',
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
    const session = currentSession()
    const student = db.accounts.find((item) => item.kind === 'students' && item.id === session.id)
    const teacherClasses = session.role === 'teacher'
      ? db.classes.filter((item) => item.headTeacherId === session.id || item.headTeacherName === session.realName).map((item) => item.name)
      : []
    const items = db.scores.filter((item) =>
      (!params.subject || item.subject === params.subject) &&
      includes(`${item.studentName} ${item.studentNo}`, String(params.keyword ?? '')) &&
      (session.role !== 'student' || item.studentNo === student?.studentNo) &&
      (session.role !== 'teacher' || teacherClasses.includes(item.className))
    )
    return page(items, Number(params.pageNum ?? 1), Number(params.pageSize ?? 10))
  },
  async getScore(id: number) {
    await wait()
    const item = db.scores.find((score) => score.id === id)
    if (!item) throw new Error('成绩不存在')
    const session = currentSession()
    if (session.role === 'student') {
      const student = db.accounts.find((row) => row.kind === 'students' && row.id === session.id)
      if (item.studentNo !== student?.studentNo) throw new Error('无权查看其他学生成绩')
    }
    if (session.role === 'teacher') {
      const teacherClasses = db.classes
        .filter((row) => row.headTeacherId === session.id || row.headTeacherName === session.realName)
        .map((row) => row.name)
      if (!teacherClasses.includes(item.className)) throw new Error('无权查看非任教班级学生成绩')
    }
    return item
  },
  async regradeScore(id: number, reason: string) {
    await wait()
    const item = db.scores.find((score) => score.id === id)
    if (!item) throw new Error('成绩不存在')
    if (!reason.trim()) throw new Error('请填写重新判分原因')
    if (item.source !== 'online') throw new Error('补录/导入成绩没有答卷，不支持重新判分')
    const totalScore = Math.round((item.objectiveScore + item.subjectiveScore + item.aiScore) * 100) / 100
    Object.assign(item, {
      totalScore,
      level: totalScore >= 90 ? 'excellent' : totalScore >= 80 ? 'good' : totalScore >= 60 ? 'pass' : 'fail',
      status: 'graded'
    })
    save()
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
    if (finalize) {
      const attempt = db.attempts.find((row) => row.attemptId === attemptId)
      task.questions.forEach((question) => {
        if ((question.currentScore ?? 0) < question.maxScore) {
          const source = db.questions.find((row) => row.id === question.questionId)
          upsertWrongQuestion(
            {
              questionId: question.questionId,
              subject: task.subject,
              type: question.type,
              stem: question.stem,
              score: question.maxScore,
              options: source?.options ?? [],
              correctAnswer: question.correctAnswer as string | Record<string, unknown> | undefined,
              analysis: source?.analysis ?? null,
              resources: source?.resources?.map((resource) => ({ type: resource.type, name: resource.name, url: resource.url })) ?? []
            },
            { text: typeof question.studentAnswer === 'string' ? question.studentAnswer : JSON.stringify(question.studentAnswer) },
            attemptId,
            'formal',
            task.assessmentTitle
          )
        }
      })
      if (attempt) attempt.status = 'graded'
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
  async listCertificates(params: Record<string, string | number | undefined> = {}) {
    await wait()
    const session = currentSession()
    const student = db.accounts.find((item) => item.kind === 'students' && item.id === session.id)
    const teacherClasses = session.role === 'teacher'
      ? db.classes.filter((item) => item.headTeacherId === session.id || item.headTeacherName === session.realName).map((item) => item.name)
      : []
    return db.certificates.filter((item) => {
      const studentInfo = db.accounts.find((account) => (
        account.kind === 'students' &&
        (account.id === item.studentId || account.studentNo === item.studentNo || account.realName === item.studentName)
      ))
      return (!params.subject || item.subject === params.subject) &&
        includes(`${item.studentName} ${item.certificateNo} ${item.assessmentTitle}`, String(params.keyword ?? '')) &&
        (session.role !== 'student' || item.studentNo === student?.studentNo || item.studentId === student?.id) &&
        (session.role !== 'teacher' || teacherClasses.includes(studentInfo?.className ?? ''))
    })
  },
  async getCertificate(id: number) {
    await wait()
    const item = db.certificates.find((certificate) => certificate.id === id)
    if (!item) throw new Error('证书不存在')
    assertCertificateAccess(item)
    return item
  },
  async downloadCertificate(id: number) {
    await wait(100)
    const item = db.certificates.find((certificate) => certificate.id === id)
    if (!item) throw new Error('证书不存在')
    assertCertificateAccess(item)
    return new Blob([`艺术素质测评证书 ${item.certificateNo}\n学生：${item.studentName}\n${item.assessmentTitle}\n成绩：${item.score}\n`], { type: 'application/pdf' })
  },
  async updateCertificate(id: number, values: Partial<Certificate>) {
    await wait()
    if (currentSession().role === 'student') throw new Error('学生不能修改证书')
    const item = db.certificates.find((certificate) => certificate.id === id)
    if (!item) throw new Error('证书不存在')
    assertCertificateAccess(item)
    if (values.certificateNo !== undefined) {
      const nextNo = values.certificateNo.trim()
      if (db.certificates.some((certificate) => certificate.id !== id && certificate.certificateNo === nextNo)) {
        throw new Error('证书编号已存在')
      }
      item.certificateNo = nextNo
    }
    if (values.studentId !== undefined) item.studentId = values.studentId
    if (values.studentNo !== undefined) item.studentNo = values.studentNo
    if (values.studentName !== undefined) item.studentName = values.studentName.trim()
    if (values.assessmentTitle !== undefined) item.assessmentTitle = values.assessmentTitle.trim()
    if (values.subject !== undefined) item.subject = values.subject
    if (values.score !== undefined) item.score = Number(values.score)
    if (values.level !== undefined) item.level = values.level
    if (values.issueDate !== undefined) item.issueDate = values.issueDate
    if (values.status !== undefined) item.status = values.status
    save()
    return item
  },
  async generateCertificates(assessmentId: number, subject: Subject) {
    await wait()
    const levelLabels: Record<Score['level'], string> = { excellent: '优秀', good: '良好', pass: '合格', fail: '待提升' }
    const scores = db.scores.filter((item) => item.assessmentId === assessmentId && item.subject === subject && item.status === 'graded')
    const skippedCount = scores.filter((score) => db.certificates.some((certificate) => certificate.studentNo === score.studentNo && certificate.assessmentTitle === score.assessmentTitle)).length
    const created = scores.filter((score) => !db.certificates.some((certificate) => certificate.studentNo === score.studentNo && certificate.assessmentTitle === score.assessmentTitle))
    created.forEach((score) => {
      const student = db.accounts.find((item) => item.kind === 'students' && item.studentNo === score.studentNo)
      const sequence = db.certificates.length + 1
      db.certificates.push({
        id: nextId(db.certificates),
        certificateNo: `YS2026-${subject === 'music' ? 'MUSIC' : 'ART'}-${String(sequence).padStart(6, '0')}`,
        studentId: student?.id ?? null,
        studentNo: score.studentNo,
        studentName: score.studentName,
        assessmentTitle: score.assessmentTitle,
        subject,
        score: score.totalScore,
        level: levelLabels[score.level],
        issueDate: now().slice(0, 10),
        status: 'ready'
      })
    })
    save()
    return { taskId: `CERT${Date.now()}`, status: 'completed', generatedCount: created.length, skippedCount, assessmentId, subject }
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
  async listWrongQuestions(params: Record<string, string | number | boolean | undefined> = {}) {
    await wait()
    const keyword = String(params.keyword ?? '')
    const dateFrom = String(params.dateFrom ?? '')
    const dateTo = String(params.dateTo ?? '')
    const items = db.wrongQuestions.filter((item) =>
      (!params.subject || item.subject === params.subject) &&
      (!params.questionType || item.type === params.questionType) &&
      (!params.masteryStatus || item.masteryStatus === params.masteryStatus) &&
      (!params.sourceType || item.sourceType === params.sourceType) &&
      includes(item.stem, keyword) &&
      (!dateFrom || item.lastWrongAt.slice(0, 10) >= dateFrom) &&
      (!dateTo || item.lastWrongAt.slice(0, 10) <= dateTo)
    )
    return page(items, Number(params.pageNum ?? 1), Number(params.pageSize ?? 10))
  },
  async getWrongQuestion(id: number) {
    await wait()
    const item = db.wrongQuestions.find((wrong) => wrong.id === id)
    if (!item) throw new Error('错题不存在')
    return item
  },
  async updateWrongQuestion(id: number, values: { masteryStatus?: WrongQuestionDetail['masteryStatus']; note?: string | null }) {
    await wait()
    const item = db.wrongQuestions.find((wrong) => wrong.id === id)
    if (!item) throw new Error('错题不存在')
    if (values.masteryStatus) item.masteryStatus = values.masteryStatus
    if (values.note !== undefined) item.note = values.note
    save()
    return item
  },
  async removeWrongQuestion(id: number) {
    await wait()
    db.wrongQuestions = db.wrongQuestions.filter((wrong) => wrong.id !== id)
    save()
    return { deleted: true, wrongId: id }
  },
  async redoWrongQuestion(id: number) {
    await wait()
    const wrong = db.wrongQuestions.find((item) => item.id === id)
    if (!wrong) throw new Error('错题不存在')
    const attempt: Attempt = {
      attemptId: Math.max(0, ...db.attempts.map((item) => item.attemptId)) + 1,
      assessmentId: 12991,
      paperId: 11991,
      title: '错题重做',
      subject: wrong.subject,
      status: 'in_progress',
      startedAt: now(),
      deadline: new Date(Date.now() + 20 * 60000).toISOString(),
      serverTime: now(),
      remainingSeconds: 1200,
      totalScore: 5,
      questions: [{
        questionId: wrong.questionId,
        order: 1,
        type: wrong.type,
        stem: wrong.stem,
        score: 5,
        options: wrong.options,
        resources: wrong.resources
          .filter((resource): resource is { type: 'image' | 'audio'; name: string; url?: string } => resource.type === 'image' || resource.type === 'audio')
          .map((resource) => ({ ...resource })),
        answerConfig: { maxLength: 500 },
        correctAnswer: typeof wrong.correctAnswer.value === 'string' ? wrong.correctAnswer.value : '',
        analysis: wrong.analysis
      }],
      savedAnswers: [],
      wrongQuestionId: id
    }
    db.attempts.push(attempt)
    save()
    return { attemptId: attempt.attemptId, wrongId: id, question: attempt.questions[0] }
  },
  async getWrongQuestionStatistics() {
    await wait()
    const recent = Date.now() - 7 * 24 * 60 * 60 * 1000
    const stats: WrongQuestionStatistics = {
      total: db.wrongQuestions.length,
      unmastered: db.wrongQuestions.filter((item) => item.masteryStatus === 'unmastered').length,
      reviewing: db.wrongQuestions.filter((item) => item.masteryStatus === 'reviewing').length,
      mastered: db.wrongQuestions.filter((item) => item.masteryStatus === 'mastered').length,
      recent7Days: db.wrongQuestions.filter((item) => new Date(item.lastWrongAt).getTime() >= recent).length,
      bySubject: [...new Set(db.wrongQuestions.map((item) => item.subject))].map((subject) => ({ subject, count: db.wrongQuestions.filter((item) => item.subject === subject).length })),
      byType: [...new Set(db.wrongQuestions.map((item) => item.type))].map((type) => ({ type, count: db.wrongQuestions.filter((item) => item.type === type).length }))
    }
    return stats
  },
  async listNotifications(params: Record<string, string | number | boolean | undefined> = {}) {
    await wait()
    const role = currentSession().role
    const roleItems = db.notifications.filter((item) => item.recipientRole === role)
    const items = roleItems.filter((item) =>
      (!params.unreadOnly || !item.read) &&
      (!params.type || item.type === params.type)
    )
    const paged = page(items, Number(params.pageNum ?? 1), Number(params.pageSize ?? 20))
    return { ...paged, unreadCount: roleItems.filter((item) => !item.read).length, list: paged.list.map(({ recipientRole: _recipientRole, ...item }) => item) }
  },
  async markNotificationRead(id: number) {
    await wait()
    const item = db.notifications.find((notification) => notification.id === id)
    if (!item) throw new Error('通知不存在')
    item.read = true
    save()
    return { id, read: true, readAt: now() }
  },
  async markAllNotificationsRead() {
    await wait()
    const role = currentSession().role
    const items = db.notifications.filter((item) => item.recipientRole === role && !item.read)
    items.forEach((item) => { item.read = true })
    save()
    return { updatedCount: items.length, readAt: now() }
  },
  async startAttempt(assessmentId: number) {
    await wait()
    const existing = db.attempts.find((item) => item.assessmentId === assessmentId && item.status === 'in_progress')
    if (existing) return existing
    const assessment = db.assessments.find((item) => item.id === assessmentId)
    if (!assessment) throw new Error('测评不存在或已下线')
    const paper = db.papers.find((item) => item.id === assessment.paperId)
    const paperQuestions: Attempt['questions'] = (paper?.questions ?? []).map((question, index) => {
      const source = db.questions.find((item) => item.id === question.questionId)
      const answer = source?.answer
      return {
        questionId: question.questionId,
        order: index + 1,
        type: question.type,
        stem: question.stem,
        score: question.score,
        options: question.options ?? source?.options ?? [],
        resources: (question.resources ?? source?.resources?.map((resource) => ({ type: resource.type, name: resource.name, url: resource.url })) ?? [])
          .filter((resource): resource is { type: 'image' | 'audio'; name: string; url?: string } => resource.type === 'image' || resource.type === 'audio'),
        answerConfig: { maxLength: 500, playLimit: 2 },
        correctAnswer: typeof answer?.value === 'string' ? answer.value : typeof answer?.text === 'string' ? answer.text : answer ? JSON.stringify(answer) : '',
        analysis: question.analysis ?? source?.analysis ?? null
      }
    })
    const questions = paperQuestions.length ? paperQuestions : seed().attempts[0].questions
    const attempt: Attempt = {
      ...seed().attempts[0],
      attemptId: Math.max(0, ...db.attempts.map((item) => item.attemptId)) + 1,
      studentId: currentSession().id,
      assessmentId,
      paperId: assessment.paperId,
      title: assessment.title,
      subject: assessment.subject,
      status: 'in_progress',
      startedAt: now(),
      deadline: new Date(Date.now() + assessment.duration * 60000).toISOString(),
      serverTime: now(),
      remainingSeconds: assessment.duration * 60,
      totalScore: questions.reduce((sum, question) => sum + question.score, 0),
      questions,
      savedAnswers: []
    }
    db.attempts.push(attempt)
    save()
    return attempt
  },
  async getAttempt(attemptId: number) {
    await wait()
    const attempt = db.attempts.find((item) => item.attemptId === attemptId)
    if (!attempt) throw new Error('答卷不存在')
    attempt.serverTime = now()
    attempt.remainingSeconds = Math.max(0, Math.ceil((new Date(attempt.deadline).getTime() - Date.now()) / 1000))
    save()
    return attempt
  },
  async startPractice(subject: Subject, questionChapterId?: number) {
    await wait()
    const approved = db.questions.filter((item) => item.subject === subject && item.status === 'approved')
    if (!approved.length) throw new Error(`暂无${subject === 'music' ? '音乐' : '美术'}练习题`)
    // 与后端一致：本章优先，取 6 单选 + 3 多选 + 1 实践题，不足时用同科题目补齐。
    const chapterPool = questionChapterId ? approved.filter((item) => item.chapterId === questionChapterId) : []
    const sourceQuestions = chapterPool.length ? chapterPool : approved
    const practicalType = subject === 'music' ? 'audio_upload' : 'image_upload'
    const picked = [
      ...shuffle(sourceQuestions.filter((item) => item.type === 'single_choice')).slice(0, 6),
      ...shuffle(sourceQuestions.filter((item) => item.type === 'multiple_choice')).slice(0, 3),
      ...shuffle(sourceQuestions.filter((item) => item.type === practicalType)).slice(0, 1)
    ]
    if (!picked.length) throw new Error(`暂无${subject === 'music' ? '音乐' : '美术'}练习题`)
    const practiceQuestions = picked.map((item, index) => ({
      questionId: item.id,
      order: index + 1,
      type: item.type,
      stem: item.stem,
      score: item.score,
      options: item.options ?? [],
      resources: item.resources?.map((resource) => ({ type: resource.type, name: resource.name, url: resource.url })) ?? [],
      answerConfig: { maxLength: 500, playLimit: 2 },
      correctAnswer: typeof item.answer?.value === 'string'
        ? item.answer.value
        : typeof item.answer?.text === 'string'
          ? item.answer.text
          : item.answer
            ? JSON.stringify(item.answer)
            : '',
      analysis: item.analysis
    }))
    const attempt: Attempt = {
      ...seed().attempts[0],
      attemptId: Math.max(0, ...db.attempts.map((item) => item.attemptId)) + 1,
      studentId: currentSession().id,
      assessmentId: 12990,
      paperId: 11990,
      title: `${subject === 'music' ? '音乐' : '美术'}随机练习`,
      subject,
      status: 'in_progress',
      startedAt: now(),
      deadline: new Date(Date.now() + 40 * 60000).toISOString(),
      serverTime: now(),
      remainingSeconds: 2400,
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
  async submitAttempt(attemptId: number, submitType: 'manual' | 'auto' = 'manual') {
    await wait()
    const attempt = db.attempts.find((item) => item.attemptId === attemptId)
    if (!attempt) throw new Error('答卷不存在')
    attempt.status = 'submitted'
    attempt.autoSubmittedAt = submitType === 'auto' ? now() : null
    const answerDetails = attempt.questions.map((question) => {
      const saved = attempt.savedAnswers.find((item) => item.questionId === question.questionId)
      const studentAnswer = String(saved?.answer.value ?? saved?.answer.text ?? '未作答')
      const correct = String(question.correctAnswer ?? '')
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
    const sourceType: WrongQuestionDetail['sourceType'] = attempt.wrongQuestionId || attempt.title.includes('随机练习') ? 'practice' : 'formal'
    answerDetails.forEach((detail) => {
      const question = attempt.questions.find((item) => item.questionId === detail.questionId)
      const saved = attempt.savedAnswers.find((item) => item.questionId === detail.questionId)
      const isObjective = ['single_choice', 'multiple_choice', 'true_false', 'listening'].includes(question?.type ?? '')
      if (question && isObjective && detail.score < detail.maxScore) {
        upsertWrongQuestion(
          {
            questionId: question.questionId,
            subject: attempt.subject,
            type: question.type,
            stem: question.stem,
            score: question.score,
            options: question.options,
            correctAnswer: question.correctAnswer,
            analysis: question.analysis,
            resources: question.resources
          },
          (saved?.answer ?? { value: detail.studentAnswer }) as Record<string, unknown>,
          attemptId,
          sourceType,
          attempt.title
        )
      }
    })
    if (attempt.wrongQuestionId) {
      const wrong = db.wrongQuestions.find((item) => item.id === attempt.wrongQuestionId)
      if (wrong && answerDetails.every((detail) => detail.score === detail.maxScore)) wrong.masteryStatus = 'reviewing'
    }
    const student = db.accounts.find((item) => item.kind === 'students' && item.id === (attempt.studentId ?? currentSession().id))
    const assessment = db.assessments.find((item) => item.id === attempt.assessmentId)
    const scoreId = nextId(db.scores)
    db.scores.unshift({
      id: scoreId,
      assessmentId: attempt.assessmentId,
      assessmentTitle: attempt.title,
      subject: attempt.subject,
      studentNo: student?.studentNo ?? 'S20260001',
      studentName: student?.realName ?? '王小明',
      className: student?.className ?? '七年级（1）班',
      objectiveScore,
      subjectiveScore: 0,
      aiScore: 0,
      totalScore,
      level,
      status: 'grading',
      source: 'online',
      createdAt: now(),
      answerVisible: attempt.title.includes('随机练习') || attempt.wrongQuestionId !== undefined || (assessment?.showAnswerMode ?? 'after_submit') !== 'never',
      answerDetails
    })
    save()
    return { attemptId, scoreId, status: 'submitted', submitType, gradingStatus: 'grading', totalScore }
  },
  reset() {
    localStorage.removeItem(STORAGE_KEY)
  }
}
