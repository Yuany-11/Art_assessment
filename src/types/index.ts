export type Role =
  | 'student'
  | 'teacher'
  | 'school_admin'
  | 'district_admin'
  | 'city_admin'
  | 'province_admin'
  | 'question_admin'

export type AccountKind = 'teachers' | 'students' | 'schools' | 'districts' | 'cities'
export type ScopeType = 'class' | 'school' | 'district' | 'city' | 'province'
export type Subject = 'music' | 'art'
export type Priority = 'P0' | 'P1'

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export interface PageResult<T> {
  total: number
  pages: number
  list: T[]
}

export interface UserProfile {
  id: number
  username: string
  realName: string
  role: Role
  roleName: string
  schoolId: number | null
  schoolName: string | null
  districtId: number | null
  districtName: string | null
  cityId: number | null
  cityName: string | null
  avatarUrl: string | null
  permissions: string[]
  grade?: number | null
  classId?: number | null
  className?: string | null
}

export interface AuthSession {
  token: string
  refreshToken: string
  tokenType: 'Bearer'
  expiresIn: number
  refreshExpiresIn: number
  user: UserProfile
}

export interface Account {
  id: number
  kind: AccountKind
  username: string
  realName: string
  role: Role
  roleName: string
  orgId: number | null
  orgName: string | null
  studentNo: string | null
  phone: string | null
  email: string | null
  subject: Subject | null
  grade: number | null
  classId: number | null
  className: string | null
  status: 'active' | 'disabled'
  createdAt: string
}

export interface SchoolClass {
  id: number
  classCode: string
  name: string
  grade: number
  schoolName: string
  headTeacherName: string
  studentCount: number
  status: 'active' | 'archived'
  createdAt: string
}

export interface ClassRequest {
  id: number
  classId: number
  className: string
  requesterName: string
  requesterRole: 'student' | 'teacher'
  type: 'join' | 'change' | 'leave'
  status: 'pending' | 'approved' | 'rejected'
  reason: string
  createdAt: string
}

export interface Paper {
  id: number
  title: string
  subject: Subject
  paperType: 'practice' | 'formal'
  grade: number
  scopeType: ScopeType
  scopeId: number
  scopeName: string
  totalScore: number
  questionCount: number
  duration: number
  generateMode: 'manual' | 'auto'
  status: 'draft' | 'ready' | 'published' | 'archived'
  creatorName: string
  createdAt: string
  updatedAt: string
  questions?: Array<{ questionId: number; stem: string; type: string; score: number; analysis?: string | null }>
}

export interface Assessment {
  id: number
  title: string
  paperId: number
  paperTitle: string
  subject: Subject
  paperType: 'practice' | 'formal'
  grade: number
  targetType: ScopeType
  targetIds: number[]
  targetNames: string[]
  targetGrades: number[]
  startTime: string
  endTime: string
  duration: number
  attemptLimit: number
  showAnswerMode: 'never' | 'after_submit' | 'after_end'
  status: 'published' | 'withdrawn' | 'finished'
  publisherName: string
  participantCount: number
  submittedCount: number
  instructions?: string
}

export interface Question {
  id: number
  subject: Subject
  grade: number
  courseId: number
  courseName: string
  chapterId: number | null
  chapterName: string | null
  type: string
  difficulty: number
  stem: string
  score: number
  status: 'draft' | 'pending' | 'approved' | 'rejected' | 'offline'
  creatorName: string
  resourceCount: number
  options?: Array<{ key: string; text: string }>
  answer?: Record<string, unknown>
  analysis?: string | null
  resources?: Array<{ resourceId: number; type: 'image' | 'audio'; name: string; url?: string }>
  createdAt: string
  updatedAt: string
}

export interface Course {
  id: number
  name: string
  subject: Subject
  grade: number
  description: string | null
  chapterCount: number
  status: 'active' | 'disabled'
  sortOrder: number
}

export interface Chapter {
  id: number
  courseId: number
  courseName: string
  name: string
  description: string | null
  questionCount: number
  sortOrder: number
}

export interface OperationLog {
  id: number
  operatorName: string
  role: Role
  action: string
  resourceType: string
  resourceId: number | null
  description: string
  ip: string
  result: 'success' | 'failed'
  createdAt: string
}

export interface Score {
  id: number
  assessmentId: number
  assessmentTitle: string
  subject: Subject
  studentNo: string
  studentName: string
  className: string
  objectiveScore: number
  subjectiveScore: number
  aiScore: number
  totalScore: number
  level: 'excellent' | 'good' | 'pass' | 'fail'
  status: 'pending' | 'grading' | 'graded' | 'failed'
  source: 'online' | 'manual' | 'import'
  createdAt: string
  answerVisible?: boolean
  answerDetails?: Array<{
    questionId: number
    order: number
    stem: string
    studentAnswer: string
    correctAnswer: string
    score: number
    maxScore: number
    comment: string
    aiAnalysis: string | null
  }>
}

export interface StatRow {
  rank: number
  dimension: string
  targetId: number
  targetName: string
  studentCount: number
  participantCount: number
  participationRate: number
  avgScore: number
  passRate: number
  excellentRate: number
}

export interface Certificate {
  id: number
  certificateNo: string
  studentName: string
  assessmentTitle: string
  subject: Subject
  score: number
  level: string
  issueDate: string
  status: 'generating' | 'ready' | 'failed'
}

export interface AttemptQuestion {
  questionId: number
  order: number
  type: string
  stem: string
  score: number
  options: Array<{ key: string; text: string }>
  resources: Array<{ type: 'audio' | 'image'; name: string; url?: string }>
  answerConfig?: { blankCount?: number; maxLength?: number; playLimit?: number }
  correctAnswer?: string
  analysis?: string | null
}

export interface Attempt {
  attemptId: number
  assessmentId: number
  paperId: number
  title: string
  subject: Subject
  status: 'in_progress' | 'submitted' | 'graded'
  startedAt: string
  deadline: string
  serverTime: string
  remainingSeconds: number
  totalScore: number
  questions: AttemptQuestion[]
  savedAnswers: Array<{ questionId: number; answer: { value?: string; text?: string } }>
}

export interface GradingQuestion {
  questionId: number
  order: number
  type: string
  stem: string
  studentAnswer: string
  correctAnswer: string
  rubric: string
  maxScore: number
  currentScore: number | null
  aiScore: number | null
  aiAnalysis: string | null
  comment: string | null
}

export interface GradingTask {
  attemptId: number
  assessmentId: number
  assessmentTitle: string
  subject: Subject
  studentId: number
  studentName: string
  studentNo: string
  className: string
  submittedAt: string
  gradingStatus: 'pending' | 'grading' | 'failed'
  objectiveScore: number
  currentScore: number
  maxScore: number
  pendingCount: number
  questions: GradingQuestion[]
}

export interface LearningReport {
  reportId: string
  studentId: number
  subject: Subject
  generatedAt: string
  summary: string
  strengths: string[]
  weaknesses: string[]
  suggestions: string[]
  scoreTrend: Array<{ date: string; score: number }>
  rawText: string
  modelVersion: string
}

export interface StudentArtwork {
  id: number
  studentId: number
  studentName: string
  fileName: string
  subject: Subject
  uploadedAt: string
  status: 'uploaded' | 'reviewed'
  preview: string
}

export interface TaskItem {
  id: string
  module: string
  submodule: string
  feature: string
  priority: Priority
  owner: '前端 B' | '前端 A/B'
  backend: string
}
