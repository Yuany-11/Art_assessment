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
  provinceId?: number | null
  provinceName?: string | null
  avatarUrl: string | null
  gender?: 'male' | 'female' | 'unknown'
  phone?: string | null
  email?: string | null
  studentNo?: string | null
  teacherNo?: string | null
  subject?: Subject | null
  teacherSubjects?: Subject[]
  allowedSubjects?: Subject[]
  allowedQuestionTypes?: string[]
  questionTypesBySubject?: Record<string, string[]>
  isHeadTeacher?: boolean
  title?: string | null
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
  teachingClasses?: Array<{
    id: number
    classCode: string
    name: string
    subject: Subject
    role: 'head' | 'subject'
  }>
  status: 'active' | 'disabled'
  createdAt: string
  initialPassword?: string
  hasTemporaryPassword?: boolean
}

export interface OrgOption {
  id: number
  name: string
  code: string
  level: 'province' | 'city' | 'district' | 'school'
  parentId: number | null
  parentName: string | null
  schoolType: string | null
}

export interface SchoolClass {
  id: number
  classCode: string
  name: string
  grade: number
  schoolName: string
  headTeacherName: string
  headTeacherId?: number | null
  headTeacherAccount?: string | null
  headTeacherSubject?: Subject | null
  headTeacherPhone?: string | null
  subjectTeachers?: Array<{ id: number; realName: string; subject: Subject }>
  studentCount: number
  status: 'active' | 'archived'
  myIdentity?: string | null
  createdAt: string
}

export interface ClassRequest {
  id: number
  classId: number
  className: string
  requesterId?: number | null
  requesterName: string
  requesterRole: 'student' | 'teacher'
  type: 'join' | 'change' | 'leave'
  targetClassId?: number | null
  targetClassName?: string | null
  status: 'pending' | 'approved' | 'rejected'
  reason: string
  reviewComment?: string | null
  reviewedAt?: string | null
  sourceApproved?: boolean
  targetApproved?: boolean
  reviewClassId?: number | null
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
  reviewStatus: 'none' | 'pending' | 'approved' | 'rejected'
  reviewComment: string | null
  reviewerId: number | null
  reviewerName: string | null
  reviewedAt: string | null
  version: number
  creatorId: number
  creatorName: string
  createdAt: string
  updatedAt: string
  instructions?: string | null
  questions?: Array<{
    questionId: number
    stem: string
    type: string
    score: number
    sectionName?: string
    analysis?: string | null
    options?: Array<{ key: string; text: string; mediaUrl?: string | null }>
    resources?: Array<{ type: string; name: string; url?: string }>
  }>
}

export interface PaperReviewLog {
  id: number
  paperId: number
  version: number
  action: 'submit' | 'approve' | 'reject'
  reviewerId: number | null
  reviewerName: string | null
  comment: string | null
  createdAt: string
}

export interface PaperReviewResult {
  paperId: number
  reviewStatus: Paper['reviewStatus']
  version: number
  submittedAt: string | null
  reviewerId: number | null
  reviewerName: string | null
  reviewComment: string | null
  reviewedAt: string | null
}

export interface Assessment {
  id: number
  title: string
  paperId: number
  paperTitle: string
  totalScore?: number
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
  difficulty?: number | null
  difficultyLabel?: string | null
  attemptLimit: number
  showAnswerMode: 'never' | 'after_submit' | 'after_end'
  status: 'published' | 'withdrawn' | 'finished'
  phase?: 'not_started' | 'in_progress' | 'ended'
  isEnded?: boolean
  isStarted?: boolean
  publisherId?: number
  publisherName: string
  participantCount: number
  submittedCount: number
  instructions?: string
  myAttempt?: {
    attemptId: number
    status: 'in_progress' | 'submitted' | 'graded'
    attemptNo: number
    remainingSeconds: number
  } | null
}

export interface AudioTags {
  fileId: number
  status: 'pending' | 'completed' | 'failed'
  genre?: string | null
  genreLabel?: string | null
  genreConfidence?: number | null
  genreProbs?: Record<string, number>
  emotion?: string | null
  emotionLabel?: string | null
  emotionConfidence?: number | null
  emotionProbs?: Record<string, number>
  mode?: string | null
  modeLabel?: string | null
  modeConfidence?: number | null
  modeProbs?: Record<string, number>
  bpm?: number | null
  bpmIsEstimate?: boolean
  segments?: number | null
  key?: string | null
  duration?: number | null
  referenceScore?: number | null
  rawReferenceScore?: number | null
  calibrated?: boolean
  referenceGrade?: string | null
  dimensions?: Array<{ key: string; name: string; weight: number; score: number }>
  penalties?: Array<{ reason: string; delta: number }>
  metrics?: Record<string, number | boolean | string | null>
  modelVersion?: string | null
  rubricId?: string | null
  analyzedAt?: string | null
  errorMessage?: string | null
  disclaimer?: string
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
  difficultyLabel?: string | null
  stem: string
  score: number
  status: 'draft' | 'pending' | 'approved' | 'rejected' | 'offline'
  creatorId?: number
  creatorName: string
  resourceCount: number
  options?: Array<{ key: string; text: string }>
  answer?: Record<string, unknown>
  scoringMode?: 'auto' | 'manual'
  analysis?: string | null
  knowledgePoint?: string | null
  sourceMeta?: Record<string, unknown>
  resources?: Array<{ resourceId: number; fileId?: number; type: 'image' | 'audio'; name: string; url?: string }>
  audioResources?: Array<{ resourceId: number; fileId: number; type: 'image' | 'audio'; name: string; url?: string; audioTags?: AudioTags | null }>
  audioTags?: AudioTags | null
  createdAt: string
  updatedAt: string
}

export interface QgenUnit {
  unitId: string
  unitName: string
  courseId: number
  courseName: string
  chapterId: number
  chapterName: string
  knowledgePoints: string[]
  allowedTypes: string[]
  difficultyRange: [number, number]
}

export interface QgenCatalog {
  provider: string
  enabled: boolean
  withImage?: boolean
  allowedTypes: string[]
  modelNote: string
  grades: Array<{ grade: number; units: QgenUnit[] }>
  missingMappings: Array<{ unitId: string; reason: string }>
}

export interface QgenGenerateResult {
  question: Question
  warnings: string[]
  model: Record<string, unknown>
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
  content: string | null
  questionCount: number
  sortOrder: number
}

export interface ChapterQuestion {
  id: number
  type: string
  difficulty: number
  difficultyLabel?: string | null
  stem: string
  score: number
  options: Array<{ key: string; text: string; mediaUrl?: string | null }>
  answer: Record<string, unknown>
  analysis: string | null
  scoringMode: 'auto' | 'manual'
  resources: Array<{ resourceId: number; type: 'image' | 'audio'; name: string; url?: string }>
}

export interface ChapterQuestionBundle {
  chapter: Chapter
  questions: ChapterQuestion[]
  total: number
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
  attemptId?: number | null
  assessmentId: number
  assessmentTitle: string
  paperType?: 'practice' | 'formal'
  subject: Subject
  studentNo: string
  studentName: string
  className: string
  objectiveScore: number
  subjectiveScore: number
  totalScore: number
  maxScore?: number
  level: 'excellent' | 'good' | 'pass' | 'fail'
  status: 'pending' | 'grading' | 'graded' | 'failed'
  source: 'online' | 'manual' | 'import'
  createdAt: string
  answerVisible?: boolean
  answerDetails?: Array<{
    questionId: number
    order: number
    stem: string
    studentAnswer: unknown
    correctAnswer: unknown
    score: number
    maxScore: number
    comment: string
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
  studentId?: number | null
  studentNo?: string | null
  studentName: string
  assessmentTitle: string
  subject: Subject
  score: number
  level: string
  issueDate: string
  status: 'generating' | 'ready' | 'failed'
}

export interface AnswerFile {
  fileId: number
  url: string
  name: string
  mimeType: string
  size: number
  captureMode?: 'camera' | 'album' | 'file'
}

export interface AttemptAnswer {
  value?: string | boolean
  values?: string[]
  text?: string
  fileId?: number
  url?: string
  name?: string
  mimeType?: string
  size?: number
  /** 作品来源：拍照 / 相册 / 文件，便于教师端区分。 */
  captureMode?: 'camera' | 'album' | 'file'
  /** 美术作品多图；fileId/url 等主字段仍保留第一张，兼容旧判分与 AI。 */
  files?: AnswerFile[]
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
  studentId?: number | null
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
  savedAnswers: Array<{ questionId: number; answer: AttemptAnswer }>
  wrongQuestionId?: number
  autoSubmittedAt?: string | null
}

export interface AttemptReviewItem {
  questionId: number
  order: number
  type: string
  stem: string
  options: Array<{ key: string; text: string }>
  resources: Array<{ type: 'audio' | 'image'; name: string; url?: string }>
  studentAnswer: AttemptAnswer
  score: number | null
  maxScore: number
  isCorrect: boolean | null
  correctAnswer: AttemptAnswer | null
  analysis: string | null
  comment: string | null
  scoringMode: string
}

export interface AttemptReview {
  attemptId: number
  assessmentId: number
  assessmentTitle: string
  subject: Subject
  paperType: 'practice' | 'formal'
  publisherName: string
  startTime: string
  endTime: string
  submittedAt: string | null
  status: string
  gradingStatus: string
  showAnswerMode: 'never' | 'after_submit' | 'after_end'
  answerVisible: boolean
  objectiveScore: number
  subjectiveScore: number | null
  totalScore: number | null
  maxScore: number
  scoreReleased: boolean
  questions: AttemptReviewItem[]
}

export interface AiSuggestion {
  questionId: number
  status: 'completed' | 'pending' | 'failed' | 'missing' | 'disabled'
  suggestedScore: number | null
  maxScore: number
  rawScore: number | null
  rawScoreMax?: number
  grade: string | null
  confidence: number | null
  needsReview: boolean
  rubricId?: string | null
  analyzedAt?: string | null
  message: string
  disclaimer: string
  audioTags?: AudioTags | null
  // 美术作品评分维度；音乐建议分没有该字段。
  dimensions?: Array<{
    key: string
    label: string
    score: number
    weight: number
    maxScore: number
  }>
  method?: string | null
  degraded?: boolean
  analysis?: string | null
}

export interface AiSuggestionResult {
  attemptId: number
  items: AiSuggestion[]
  confidenceThreshold: number
  sourceScoreMax: number
  disclaimer: string
}

export interface GradingQuestion {
  questionId: number
  order: number
  type: string
  stem: string
  studentAnswer: unknown
  correctAnswer: unknown
  rubric: string
  maxScore: number
  currentScore: number | null
  comment: string | null
  audioTags?: AudioTags | null
  aiSuggestion?: AiSuggestion | null
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
  gradingStatus: 'pending' | 'grading' | 'graded' | 'failed'
  version?: number
  objectiveScore: number
  currentScore: number
  maxScore: number
  pendingCount: number
  aiScoringEnabled?: boolean
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
  mimeType?: string
  subject: Subject
  uploadedAt: string
  status: 'uploaded' | 'reviewed'
  score?: number | null
  comment?: string
  reviewedBy?: string | null
  reviewedAt?: string | null
  preview: string
  audioTags?: AudioTags | null
}

export interface WrongQuestionItem {
  id: number
  questionId: number
  subject: Subject
  type: string
  stem: string
  wrongCount: number
  lastWrongAt: string
  masteryStatus: 'unmastered' | 'reviewing' | 'mastered'
  sourceType: 'practice' | 'formal' | 'manual' | 'import'
  sourceAssessmentTitle: string | null
}

export interface WrongQuestionDetail extends WrongQuestionItem {
  options: Array<{ key: string; text: string }>
  correctAnswer: Record<string, unknown>
  studentAnswer: Record<string, unknown> | null
  analysis: string | null
  resources: Array<{ type: string; name: string; url?: string }>
  note: string | null
  records: Array<{
    attemptId: number
    answer: Record<string, unknown>
    createdAt: string
  }>
}

export type NotificationType =
  | 'paper_review_submitted'
  | 'paper_review_approved'
  | 'paper_review_rejected'
  | 'question_review_approved'
  | 'question_review_rejected'
  | 'system'

export interface NotificationItem {
  id: number
  type: NotificationType
  title: string
  content: string
  link: string | null
  read: boolean
  createdAt: string
}

export interface WrongQuestionStatistics {
  total: number
  unmastered: number
  reviewing: number
  mastered: number
  recent7Days: number
  bySubject: Array<{ subject: Subject; count: number }>
  byType: Array<{ type: string; count: number }>
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
