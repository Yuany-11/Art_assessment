<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Plus, Search } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import AudioTagCard from '@/components/AudioTagCard.vue'
import { api } from '@/api'
import { formatAnswer } from '@/utils/answers'
import { useAuthStore } from '@/stores/auth'
import { ensureTeacherSubject } from '@/utils/teacherAccess'
import {
  allowedQuestionTypes,
  allowedSubjects,
  labelsForTypes,
  questionTypesForSubject,
  QUESTION_TYPE_LABELS
} from '@/utils/questionTypes'
import type { AudioTags, Chapter, Course, QgenCatalog, QgenUnit, Question, Subject } from '@/types'

const auth = useAuthStore()
const isQuestionAdmin = computed(() => auth.role === 'question_admin')
const mySubjects = computed(() => allowedSubjects(auth.user))
const isTeacher = computed(() => auth.role === 'teacher')
const showSubjectFilter = computed(() => !isTeacher.value || mySubjects.value.length > 1)
const audioTypes = ['listening', 'audio_upload', 'audio_choice_judge']
const allowedTypes = computed(() => allowedQuestionTypes(auth.user))
const canUseAudio = computed(() => allowedTypes.value.some((type) => audioTypes.includes(type)))
// 筛选下拉用当前用户可管理的全部题型；新建/编辑下拉按所选学科动态渲染。
const filterTypeOptions = computed(() =>
  labelsForTypes(
    filters.subject
      ? questionTypesForSubject(auth.user, filters.subject)
      : allowedTypes.value
  )
)
function isOwnEditable(row: Question) {
  return row.creatorId === auth.user?.id && ['draft', 'rejected'].includes(row.status)
}
function canEditRow(row: Question) {
  return isQuestionAdmin.value || isOwnEditable(row)
}
function canSubmitRow(row: Question) {
  return !isQuestionAdmin.value && isOwnEditable(row)
}

const loading = ref(false)
const rows = ref<Question[]>([])
const total = ref(0)
const pageNum = ref(1)
const pageSize = ref(10)
const filters = reactive({
  subject: '', status: '', type: '', grade: '', keyword: '', favoriteOnly: false,
  genre: '', emotion: ''
})
const favoriteIds = ref<number[]>([])
const favoriteSet = computed(() => new Set(favoriteIds.value))
const dialogOpen = ref(false)
const reviewOpen = ref(false)
const editing = ref<Question | null>(null)
const current = ref<Question | null>(null)
const reviewAction = ref<'approve' | 'reject'>('approve')
const reviewComment = ref('')
const reviewSubmitting = ref(false)
const recentQuestionId = ref<number | null>(null)
const audioOpen = ref(false)
const audioQuestion = ref<Question | null>(null)
const similarItems = ref<Array<Question & { similarity?: number; matchReason?: string }>>([])
const similarLoading = ref(false)
const qgenOpen = ref(false)
const qgenLoading = ref(false)
const qgenCatalog = ref<QgenCatalog | null>(null)
const qgenResult = ref<Question | null>(null)
const qgenForm = reactive({
  grade: 7,
  unitId: '',
  knowledgePoint: '',
  type: 'single_choice',
  difficulty: 1
})
const courses = ref<Course[]>([])
const chapters = ref<Chapter[]>([])
const options = ref<Array<{ key: string; text: string }>>([{ key: 'A', text: '' }, { key: 'B', text: '' }])
const audioInput = ref<HTMLInputElement>()
const audioUploading = ref(false)
const audioResource = ref<{ fileId: number; url: string; name: string } | null>(null)
const imageInput = ref<HTMLInputElement>()
const imageUploading = ref(false)
const imageResource = ref<{ fileId: number; url: string; name: string } | null>(null)
const form = reactive({
  subject: (mySubjects.value[0] ?? 'music') as Subject,
  grade: 7,
  courseId: 0,
  chapterId: '' as string | number,
  type: 'single_choice',
  difficulty: 2,
  stem: '',
  score: 5,
  publishNow: true,
  scoringMode: 'auto',
  answerSingle: 'A',
  answerMulti: [] as string[],
  answerBool: true,
  answerValues: '',
})

const gradeOptions = Array.from({ length: 9 }, (_, index) => index + 1)
const questionTypeLabels = QUESTION_TYPE_LABELS
const choiceTypes = ['single_choice', 'multiple_choice', 'listening', 'audio_choice_judge', 'image_choice_judge']
const isChoice = computed(() => choiceTypes.includes(form.type))

const formTypeOptions = computed(() =>
  labelsForTypes(questionTypesForSubject(auth.user, form.subject))
)
const filteredCourses = computed(() => courses.value.filter((item) => item.subject === form.subject))
const qgenGrades = computed(() => qgenCatalog.value?.grades ?? [])
const qgenUnits = computed<QgenUnit[]>(
  () => qgenGrades.value.find((item) => item.grade === qgenForm.grade)?.units ?? []
)
const qgenUnit = computed(
  () => qgenUnits.value.find((item) => item.unitId === qgenForm.unitId) ?? null
)
const qgenDifficultyOptions = computed(() => {
  const [low, high] = qgenUnit.value?.difficultyRange ?? [1, 3]
  return Array.from({ length: high - low + 1 }, (_, index) => low + index)
})

async function loadCourses() {
  try {
    const result = await api.courses.list({ pageSize: 200 })
    courses.value = result.list
  } catch {
    courses.value = []
  }
}

async function loadChapters() {
  chapters.value = []
  if (!form.courseId) return
  try {
    chapters.value = await api.courses.chapters(Number(form.courseId))
  } catch {
    chapters.value = []
  }
}

function syncCourseSelection() {
  if (!filteredCourses.value.some((item) => item.id === form.courseId)) {
    form.courseId = filteredCourses.value[0]?.id ?? 0
    form.chapterId = ''
  }
  const course = courses.value.find((item) => item.id === Number(form.courseId))
  if (course) form.grade = course.grade
  form.answerSingle = options.value[0]?.key ?? 'A'
  void loadChapters()
}

function defaultScoringMode(type: string) {
  return ['single_choice', 'multiple_choice', 'true_false', 'fill_blank', 'listening', 'audio_choice_judge', 'image_choice_judge'].includes(type) ? 'auto' : 'manual'
}

async function load() {
  loading.value = true
  try {
    const result = await api.questions.list({
      ...filters,
      favoriteOnly: filters.favoriteOnly ? 'true' : '',
      pageNum: pageNum.value,
      pageSize: pageSize.value
    })
    rows.value = result.list
    total.value = result.total
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function loadFavorites() {
  try {
    favoriteIds.value = (await api.questions.favorites()).questionIds
  } catch {
    favoriteIds.value = []
  }
}

async function toggleFavorite(row: Question) {
  try {
    const result = await api.questions.toggleFavorite(row.id)
    favoriteIds.value = result.favorite
      ? [...favoriteIds.value, row.id]
      : favoriteIds.value.filter((id) => id !== row.id)
    ElMessage.success(result.favorite ? '已加入收藏，手动组卷时可筛选' : '已取消收藏')
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function resetQuery() {
  Object.assign(filters, {
    subject: '', status: '', type: '', grade: '', keyword: '', favoriteOnly: false,
    genre: '', emotion: ''
  })
  pageNum.value = 1
  load()
}

function onSubjectFilterChange(value: string | number | boolean) {
  const subject = value as Subject | ''
  if (subject && !ensureTeacherSubject(auth.user, subject)) {
    filters.subject = ''
    return
  }
  // 切换学科后清掉不属于该学科的题型筛选，避免筛出空结果。
  if (subject && filters.type && !questionTypesForSubject(auth.user, subject).includes(filters.type)) {
    filters.type = ''
  }
}

async function openAudioTags(row: Question) {
  try {
    audioQuestion.value = await api.questions.detail(row.id)
    similarItems.value = []
    audioOpen.value = true
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function onResourceAnalyzed(resource: NonNullable<Question['audioResources']>[number], tags: AudioTags) {
  resource.audioTags = tags
  if (audioQuestion.value && !audioQuestion.value.audioTags) audioQuestion.value.audioTags = tags
}

async function loadSimilar() {
  if (!audioQuestion.value) return
  similarLoading.value = true
  try {
    const result = await api.questions.similarAudio(audioQuestion.value.id, 5)
    similarItems.value = result.items
    if (!result.items.length) ElMessage.info('暂未找到标签接近的其他音频题目')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    similarLoading.value = false
  }
}

function changePageSize() {
  pageNum.value = 1
  load()
}

function syncQgenUnit() {
  if (!qgenUnits.value.some((item) => item.unitId === qgenForm.unitId)) {
    qgenForm.unitId = qgenUnits.value[0]?.unitId ?? ''
  }
  onQgenUnitChange()
}

function onQgenGradeChange() {
  qgenForm.knowledgePoint = ''
  syncQgenUnit()
}

function onQgenUnitChange() {
  const unit = qgenUnit.value
  if (!unit) return
  if (!unit.knowledgePoints.includes(qgenForm.knowledgePoint)) {
    qgenForm.knowledgePoint = unit.knowledgePoints[0] ?? ''
  }
  if (!unit.allowedTypes.includes(qgenForm.type)) {
    qgenForm.type = unit.allowedTypes[0] ?? 'single_choice'
  }
  const [low, high] = unit.difficultyRange
  qgenForm.difficulty = Math.min(Math.max(qgenForm.difficulty, low), high)
}

async function openQgen() {
  qgenResult.value = null
  qgenOpen.value = true
  if (!qgenCatalog.value) {
    try {
      qgenCatalog.value = await api.questions.qgenCatalog()
    } catch (error) {
      ElMessage.error((error as Error).message)
      return
    }
  }
  qgenForm.grade = qgenCatalog.value?.grades[0]?.grade ?? 7
  qgenForm.unitId = ''
  qgenForm.knowledgePoint = ''
  qgenForm.difficulty = 1
  syncQgenUnit()
}

async function generateQgen() {
  if (qgenLoading.value) return
  if (!qgenUnit.value || !qgenForm.knowledgePoint) {
    ElMessage.warning('请选择单元和知识点')
    return
  }
  qgenLoading.value = true
  try {
    const result = await api.questions.qgenGenerate({
      unitId: qgenForm.unitId,
      knowledgePoint: qgenForm.knowledgePoint,
      type: qgenForm.type,
      difficulty: qgenForm.difficulty
    })
    qgenResult.value = result.question
    recentQuestionId.value = result.question.id
    // 新题固定落为待审核：清空可能遮挡它的筛选条件，确保第一屏即可看到。
    Object.assign(filters, {
      subject: '',
      status: 'pending',
      type: '',
      grade: '',
      keyword: '',
      favoriteOnly: false,
      genre: '',
      emotion: ''
    })
    ElMessage.success(`已生成待审题 Q${result.question.id}，已定位到列表首行`)
    pageNum.value = 1
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    qgenLoading.value = false
  }
}

function formatQgenAnswer(answer?: Record<string, unknown>) {
  if (!answer) return '—'
  if (typeof answer.value === 'boolean') return answer.value ? '正确' : '错误'
  if (typeof answer.value === 'string') return answer.value
  if (Array.isArray(answer.values)) return (answer.values as unknown[]).join('；')
  if (typeof answer.text === 'string') return answer.text
  return formatAnswer(answer)
}

function openCreate() {
  editing.value = null
  const subject = mySubjects.value[0] ?? 'music'
  Object.assign(form, {
    subject,
    grade: 7,
    courseId: 0,
    chapterId: '',
    type: questionTypesForSubject(auth.user, subject)[0] ?? 'single_choice',
    difficulty: 2,
    stem: '',
    score: 5,
    publishNow: true,
    scoringMode: 'auto',
    answerSingle: 'A',
    answerMulti: [],
    answerBool: true,
    answerValues: '',
    })
  options.value = [{ key: 'A', text: '' }, { key: 'B', text: '' }]
  audioResource.value = null
  imageResource.value = null
  syncCourseSelection()
  dialogOpen.value = true
}

async function openEdit(row: Question) {
  editing.value = row
  const detail =
    ['audio_choice_judge', 'image_choice_judge'].includes(row.type) || !(row.options || row.answer)
      ? await api.questions.detail(row.id).catch(() => row)
      : row
  audioResource.value = detail.audioResources?.[0]
    ? {
        fileId: detail.audioResources[0].fileId,
        url: detail.audioResources[0].url || '',
        name: detail.audioResources[0].name
      }
    : null
  const imageItem = (detail.resources ?? []).find((item) => item.type === 'image')
  imageResource.value = imageItem?.fileId
    ? {
        fileId: imageItem.fileId,
        url: imageItem.url || '',
        name: imageItem.name
      }
    : null
  const answer = (detail.answer ?? {}) as Record<string, unknown>
  Object.assign(form, {
    subject: row.subject,
    grade: row.grade,
    courseId: row.courseId,
    chapterId: row.chapterId ?? '',
    type: row.type,
    difficulty: row.difficulty,
    stem: row.stem,
    score: row.score,
    publishNow: row.status === 'approved',
    scoringMode: row.scoringMode || defaultScoringMode(row.type),
    answerSingle: typeof answer.value === 'string' ? answer.value : 'A',
    answerMulti: Array.isArray(answer.values) ? (answer.values as string[]).map(String) : [],
    answerBool: typeof answer.value === 'boolean' ? answer.value : true,
    answerValues: Array.isArray(answer.values) ? (answer.values as string[]).join('\n') : ''
  })
  options.value = (detail.options ?? []).map((item) => ({ key: item.key, text: item.text }))
  if (!options.value.length && choiceTypes.includes(row.type)) {
    options.value = [{ key: 'A', text: '' }, { key: 'B', text: '' }]
  }
  await loadChapters()
  dialogOpen.value = true
}

async function uploadQuestionAudio(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!file.type.startsWith('audio/')) {
    ElMessage.warning('请选择音频文件')
    return
  }
  audioUploading.value = true
  try {
    const uploaded = await api.files.upload(file, 'question_audio', { subject: form.subject })
    audioResource.value = { fileId: uploaded.fileId, url: uploaded.url, name: uploaded.name }
    ElMessage.success('音频已上传')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    audioUploading.value = false
  }
}

async function uploadQuestionImage(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!file.type.startsWith('image/')) {
    ElMessage.warning('请选择图片文件')
    return
  }
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.warning('图片大小不能超过 10 MB')
    return
  }
  imageUploading.value = true
  try {
    const uploaded = await api.files.upload(file, 'question_image', { subject: form.subject })
    imageResource.value = { fileId: uploaded.fileId, url: uploaded.url, name: uploaded.name }
    ElMessage.success('题干图片已上传')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    imageUploading.value = false
  }
}

function buildAnswer() {
  if (['single_choice', 'listening', 'audio_choice_judge', 'image_choice_judge'].includes(form.type)) return { value: form.answerSingle }
  if (form.type === 'multiple_choice') return { values: form.answerMulti }
  if (form.type === 'true_false') return { value: form.answerBool }
  if (form.type === 'fill_blank') {
    return {
      values: form.answerValues
        .split('\n')
        .map((item) => item.trim())
        .filter(Boolean)
    }
  }
  return {}
}

function validate() {
  if (!form.stem.trim()) return '请填写题干'
  if (!form.courseId) return '请选择课程，课程需与学科和年级一致'
  if (form.type === 'audio_choice_judge' && !audioResource.value) return '音频选择判断题必须上传题目音频'
  if (form.type === 'image_choice_judge' && !imageResource.value) return '图像选择判断题必须上传题干图片'
  if (form.type === 'fill_blank' && !form.answerValues.split('\n').some((item) => item.trim())) {
    return '请按顺序填写填空题答案（每行一个空）'
  }
  if (isChoice.value) {
    if (options.value.length < 2) return '选择题至少需要两个选项'
    if (options.value.some((item) => !item.key.trim() || !item.text.trim())) return '请完整填写选项标识和内容'
    if (form.type === 'multiple_choice' && !form.answerMulti.length) return '请选择多选题答案'
    if (form.type !== 'multiple_choice' && !options.value.some((item) => item.key === form.answerSingle)) return '请选择单选题答案'
  }
  return ''
}

async function save() {
  const message = validate()
  if (message) {
    ElMessage.warning(message)
    return
  }
  const payload: Record<string, unknown> = {
    subject: form.subject,
    grade: Number(form.grade),
    courseId: Number(form.courseId),
    chapterId: form.chapterId ? Number(form.chapterId) : null,
    type: form.type,
    difficulty: Number(form.difficulty),
    stem: form.stem.trim(),
    score: Number(form.score),
    scoringMode: form.scoringMode,
    answer: buildAnswer(),
    options: isChoice.value ? options.value.map((item) => ({ key: item.key.trim(), text: item.text.trim() })) : undefined,
    resourceFileIds: [audioResource.value?.fileId, imageResource.value?.fileId].filter((id): id is number => typeof id === 'number')
  }
  try {
    if (editing.value) {
      await api.questions.update(editing.value.id, payload as Partial<Question>)
      ElMessage.success('试题已更新')
    } else {
      await api.questions.create({ ...payload, publishNow: form.publishNow })
      ElMessage.success(isQuestionAdmin.value && !form.publishNow ? '试题草稿已保存' : '试题已提交，等待题库管理员审核')
    }
    dialogOpen.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function submitForReview(row: Question) {
  try {
    await ElMessageBox.confirm('提交后进入题库管理员审核，审核通过前不会进入公共题库。', '提交试题审核', { type: 'info' })
    await api.questions.submitReview(row.id)
    ElMessage.success('已提交审核')
    await load()
  } catch (error) {
    if (error instanceof Error) ElMessage.error(error.message)
  }
}

function addOption() {
  const keys = 'ABCDEFGH'
  options.value.push({ key: keys[options.value.length] ?? '', text: '' })
}

function removeOption(index: number) {
  options.value.splice(index, 1)
}

watch(() => form.subject, () => {
  // 切学科时立即清掉非法题型，避免提交后才被后端 400。
  const types = questionTypesForSubject(auth.user, form.subject)
  if (!types.includes(form.type)) {
    form.type = types[0] ?? 'single_choice'
    form.scoringMode = defaultScoringMode(form.type)
  }
  syncCourseSelection()
})
watch(() => form.courseId, () => {
  const course = courses.value.find((item) => item.id === Number(form.courseId))
  if (course) form.grade = course.grade
})
watch(() => form.courseId, () => {
  void loadChapters()
})

function rowClassName({ row }: { row: Question }) {
  return row.id === recentQuestionId.value ? 'recent-row' : ''
}

async function openReview(row: Question, action: 'approve' | 'reject') {
  current.value = row
  reviewAction.value = action
  reviewComment.value = ''
  reviewOpen.value = true
  // 列表行不带资源；审核图题前补拉详情，避免看不到题干配图就通过。
  try {
    const detail = await api.questions.detail(row.id)
    if (current.value?.id === row.id) current.value = detail
  } catch {
    // 详情拉取失败不阻塞审核，仍可按题干处理。
  }
}

async function submitReview() {
  if (!current.value || reviewSubmitting.value) return
  if (reviewAction.value === 'reject' && !reviewComment.value.trim()) {
    ElMessage.warning('驳回时必须填写原因')
    return
  }
  reviewSubmitting.value = true
  try {
    await api.questions.review(current.value.id, reviewAction.value, reviewComment.value)
    reviewOpen.value = false
    ElMessage.success(reviewAction.value === 'approve' ? '试题已通过' : '试题已驳回')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    reviewSubmitting.value = false
  }
}

async function remove(row: Question) {
  try {
    await ElMessageBox.confirm('该操作会逻辑删除试题，确定继续吗？', '删除试题', { type: 'warning' })
    await api.questions.remove(row.id)
    ElMessage.success('试题已删除')
    await load()
  } catch (error) {
    if (error instanceof Error) ElMessage.error(error.message)
  }
}

onMounted(() => {
  load()
  loadCourses()
  loadFavorites()
})
</script>

<template>
  <div class="stack">
    <PageHeader title="试题管理" :description="isQuestionAdmin ? '维护公共题库与教师提交试题，完成试题审核。' : '创建和修改本人试题，提交题库管理员审核；审核通过后进入公共题库。'">
      <el-button v-if="isQuestionAdmin" :icon="MagicStick" @click="openQgen">AI 出题</el-button>
      <el-button type="primary" :icon="Plus" @click="openCreate">创建试题</el-button>
    </PageHeader>
    <section class="panel">
      <div class="filter-bar">
        <el-input v-model="filters.keyword" :prefix-icon="Search" clearable placeholder="题干关键词" />
        <el-select v-if="showSubjectFilter" v-model="filters.subject" clearable placeholder="学科" @change="onSubjectFilterChange"><el-option v-for="subject in mySubjects" :key="subject" :label="subject === 'music' ? '音乐' : '美术'" :value="subject" /></el-select>
        <el-tag v-else effect="plain">{{ mySubjects[0] === 'music' ? '音乐' : '美术' }}试题</el-tag>
        <el-select v-model="filters.grade" clearable placeholder="年级"><el-option v-for="grade in gradeOptions" :key="grade" :label="`${grade} 年级`" :value="String(grade)" /></el-select>
        <el-select v-model="filters.status" clearable placeholder="状态"><el-option label="待审核" value="pending" /><el-option label="已通过" value="approved" /><el-option label="已驳回" value="rejected" /></el-select>
        <el-button :type="filters.status === 'pending' ? 'primary' : 'default'" plain @click="filters.status = 'pending'; pageNum = 1; load()">待审核</el-button>
        <el-select v-model="filters.type" clearable placeholder="题型"><el-option v-for="(label, value) in filterTypeOptions" :key="value" :label="label" :value="value" /></el-select>
        <el-checkbox v-model="filters.favoriteOnly" label="只看收藏" border />
        <el-button type="primary" @click="pageNum = 1; load()">查询</el-button>
        <el-button @click="resetQuery">返回全部</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" row-key="id" stripe :row-class-name="rowClassName">
        <el-table-column label="编号" width="80"><template #default="{ $index }">{{ (pageNum - 1) * pageSize + $index + 1 }}</template></el-table-column>
        <el-table-column prop="stem" label="题干" min-width="240" show-overflow-tooltip />
        <el-table-column prop="subject" label="学科" width="80"><template #default="{ row }">{{ row.subject === 'music' ? '音乐' : '美术' }}</template></el-table-column>
        <el-table-column label="题型" width="100"><template #default="{ row }">{{ questionTypeLabels[row.type] || row.type }}</template></el-table-column>
        <el-table-column label="年级" width="70"><template #default="{ row }">{{ row.grade }} 年级</template></el-table-column>
        <el-table-column v-if="canUseAudio" label="音频标签" min-width="190">
          <template #default="{ row }">
            <template v-if="row.audioTags?.status === 'completed'">
              <span class="tag-chip">{{ row.audioTags.genreLabel || row.audioTags.genre }}</span>
              <span class="tag-chip">{{ row.audioTags.emotionLabel || row.audioTags.emotion }}</span>
              <span class="tag-chip">{{ row.audioTags.bpm ? `${Math.round(row.audioTags.bpm)} BPM` : '—' }}</span>
            </template>
            <el-button v-else-if="row.audioTags || ['listening', 'audio_upload', 'audio_choice_judge'].includes(row.type)" link type="primary" @click="openAudioTags(row)">待分析</el-button>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><StatusTag :value="row.status" /></template></el-table-column>
        <el-table-column label="收藏" width="90" fixed="right" align="center">
          <template #default="{ row }">
            <el-button link :type="favoriteSet.has(row.id) ? 'warning' : 'default'" @click="toggleFavorite(row)">{{ favoriteSet.has(row.id) ? '★ 已收藏' : '☆ 收藏' }}</el-button>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button v-if="canEditRow(row)" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="canUseAudio && (row.audioTags || ['listening', 'audio_upload', 'audio_choice_judge'].includes(row.type))" link @click="openAudioTags(row)">音频</el-button>
            <el-button v-if="canSubmitRow(row)" link type="primary" @click="submitForReview(row)">提交审核</el-button>
            <el-button v-if="isQuestionAdmin" link :disabled="row.status !== 'pending'" @click="openReview(row, 'approve')">通过</el-button>
            <el-button v-if="isQuestionAdmin" link type="warning" :disabled="row.status !== 'pending'" @click="openReview(row, 'reject')">驳回</el-button>
            <el-button v-if="canEditRow(row)" link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="table-footer">
        <span>共 {{ total }} 道试题</span>
        <el-pagination
          v-model:current-page="pageNum"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="sizes, prev, pager, next, jumper"
          @size-change="changePageSize"
          @current-change="load"
        />
      </div>
    </section>

    <el-dialog v-model="dialogOpen" :title="editing ? '修改试题' : '创建试题'" width="720px">
      <el-form label-position="top" class="form-grid">
        <el-form-item label="学科"><el-select v-model="form.subject" :disabled="auth.role === 'teacher' || mySubjects.length < 2"><el-option v-for="subject in mySubjects" :key="subject" :label="subject === 'music' ? '音乐' : '美术'" :value="subject" /></el-select></el-form-item>
        <el-form-item label="课程" required>
          <el-select v-model="form.courseId" placeholder="请选择课程">
            <el-option v-for="course in filteredCourses" :key="course.id" :label="course.name" :value="course.id" />
          </el-select>
          <div v-if="!filteredCourses.length" class="form-hint">没有匹配当前学科的课程，请先创建课程。题目年级由所选课程自动确定。</div>
        </el-form-item>
        <el-form-item label="章节">
          <el-select v-model="form.chapterId" clearable placeholder="可不选" :disabled="!form.courseId">
            <el-option v-for="chapter in chapters" :key="chapter.id" :label="chapter.name" :value="chapter.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="题型">
          <el-select v-model="form.type" @change="form.scoringMode = defaultScoringMode(form.type)">
            <el-option v-for="(label, value) in formTypeOptions" :key="value" :label="label" :value="value" />
          </el-select>
        </el-form-item>
        <el-form-item label="默认分值"><el-input-number v-model="form.score" :min="0.5" :max="100" :step="0.5" /></el-form-item>
        <el-form-item label="评分方式">
          <el-select v-model="form.scoringMode">
            <el-option label="自动判分" value="auto" />
            <el-option label="人工评分" value="manual" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="!editing && isQuestionAdmin" label="创建后立即发布"><el-switch v-model="form.publishNow" /></el-form-item>
        <el-form-item label="题干" required class="span-2"><el-input v-model="form.stem" type="textarea" :rows="4" /></el-form-item>

        <el-form-item v-if="form.type === 'image_choice_judge'" label="题干图片" required class="span-2">
          <div class="audio-upload-field">
            <img v-if="imageResource?.url" :src="imageResource.url" alt="题干图片" class="question-image-preview" />
            <div class="audio-upload-actions">
              <span class="muted">{{ imageResource?.name || '尚未上传图片' }}</span>
              <el-button size="small" :loading="imageUploading" @click="imageInput?.click()">{{ imageResource ? '更换图片' : '上传图片' }}</el-button>
              <el-button v-if="imageResource" size="small" text type="danger" @click="imageResource = null">移除</el-button>
              <input ref="imageInput" class="hidden-input" type="file" accept="image/*" @change="uploadQuestionImage" />
            </div>
          </div>
          <div class="form-hint">支持 JPG、PNG、WEBP，单张最大 10 MB；学生端会先展示图片再作答。</div>
        </el-form-item>

        <el-form-item v-if="form.type === 'audio_choice_judge'" label="题目音频" required class="span-2">
          <div class="audio-upload-field">
            <audio v-if="audioResource?.url" :src="audioResource.url" controls preload="metadata"></audio>
            <div class="audio-upload-actions">
              <span class="muted">{{ audioResource?.name || '尚未上传音频' }}</span>
              <el-button size="small" :loading="audioUploading" @click="audioInput?.click()">{{ audioResource ? '更换音频' : '上传音频' }}</el-button>
              <el-button v-if="audioResource" size="small" text type="danger" @click="audioResource = null">移除</el-button>
              <input ref="audioInput" class="hidden-input" type="file" accept="audio/*" @change="uploadQuestionAudio" />
            </div>
          </div>
          <div class="form-hint">支持 MP3、WAV、M4A 等音频，学生答题时可直接播放并选择答案。</div>
        </el-form-item>

        <el-form-item v-if="isChoice" label="选项" class="span-2">
          <div class="option-editor">
            <div v-for="(option, index) in options" :key="index" class="option-row">
              <el-input v-model="option.key" style="width: 72px" placeholder="A" />
              <el-input v-model="option.text" placeholder="选项内容" />
              <el-button link type="danger" :disabled="options.length <= 2" @click="removeOption(index)">删除</el-button>
            </div>
            <el-button link type="primary" @click="addOption">添加选项</el-button>
          </div>
        </el-form-item>

        <el-form-item v-if="['single_choice', 'listening', 'audio_choice_judge'].includes(form.type)" label="正确答案" class="span-2">
          <el-select v-model="form.answerSingle">
            <el-option v-for="option in options" :key="option.key" :label="`${option.key}. ${option.text}`" :value="option.key" />
          </el-select>
        </el-form-item>
        <el-form-item v-else-if="form.type === 'multiple_choice'" label="正确答案" class="span-2">
          <el-select v-model="form.answerMulti" multiple>
            <el-option v-for="option in options" :key="option.key" :label="`${option.key}. ${option.text}`" :value="option.key" />
          </el-select>
        </el-form-item>
        <el-form-item v-else-if="form.type === 'true_false'" label="正确答案" class="span-2">
          <el-radio-group v-model="form.answerBool"><el-radio :value="true">正确</el-radio><el-radio :value="false">错误</el-radio></el-radio-group>
        </el-form-item>
        <el-form-item v-else-if="form.type === 'fill_blank'" label="正确答案" class="span-2">
          <el-input v-model="form.answerValues" type="textarea" :rows="3" placeholder="每行一个空，按题干空格顺序填写" />
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogOpen = false">取消</el-button><el-button type="primary" @click="save">保存试题</el-button></template>
    </el-dialog>

    <el-dialog v-model="qgenOpen" title="AI 出题（美术）" width="720px">
      <el-alert
        v-if="qgenCatalog && !qgenCatalog.enabled"
        type="warning"
        :closable="false"
        show-icon
        title="AI 出题服务未启用"
        description="后端 QGEN_ENABLED=false 或 8002 服务未启动。可先使用 import_qgen_bank 命令离线导入待审题。"
      />
      <el-alert
        v-else
        type="info"
        :closable="false"
        show-icon
        :title="qgenCatalog?.modelNote || '生成结果直接保存为待审核题，不会进入组卷；请逐条审核后使用。'"
        style="margin-bottom: 12px"
      />
      <el-form label-position="top" class="form-grid">
        <el-form-item label="年级">
          <el-select v-model="qgenForm.grade" @change="onQgenGradeChange">
            <el-option v-for="item in qgenGrades" :key="item.grade" :label="`${item.grade} 年级`" :value="item.grade" />
          </el-select>
        </el-form-item>
        <el-form-item label="单元">
          <el-select v-model="qgenForm.unitId" @change="onQgenUnitChange">
            <el-option v-for="unit in qgenUnits" :key="unit.unitId" :label="`${unit.unitName} → ${unit.chapterName}`" :value="unit.unitId" />
          </el-select>
        </el-form-item>
        <el-form-item label="知识点">
          <el-select v-model="qgenForm.knowledgePoint" filterable>
            <el-option v-for="point in qgenUnit?.knowledgePoints ?? []" :key="point" :label="point" :value="point" />
          </el-select>
        </el-form-item>
        <el-form-item label="题型">
          <el-select v-model="qgenForm.type">
            <el-option v-for="type in qgenUnit?.allowedTypes ?? []" :key="type" :label="questionTypeLabels[type] || type" :value="type" />
          </el-select>
        </el-form-item>
        <el-form-item label="难度">
          <el-select v-model="qgenForm.difficulty">
            <el-option v-for="level in qgenDifficultyOptions" :key="level" :label="`难度 ${level}`" :value="level" />
          </el-select>
        </el-form-item>
      </el-form>
      <p v-if="qgenCatalog?.withImage" class="muted qgen-image-hint">
        已开启图题：模型有同题型素材时优先生成带配图的题，没有素材会自动退回文字题。
      </p>
      <div v-if="qgenResult" class="qgen-result">
        <div class="qgen-result-head">
          <StatusTag :value="qgenResult.status" />
          <span class="muted">Q{{ qgenResult.id }} · {{ qgenResult.chapterName }} · {{ questionTypeLabels[qgenResult.type] || qgenResult.type }}</span>
        </div>
        <div v-if="qgenResult.resources?.some((item) => item.type === 'image')" class="qgen-media">
          <img
            v-for="item in qgenResult.resources.filter((resource) => resource.type === 'image')"
            :key="item.resourceId"
            :src="item.url"
            :alt="item.name"
          />
        </div>
        <p class="qgen-stem">{{ qgenResult.stem }}</p>
        <ul v-if="qgenResult.options?.length" class="qgen-options">
          <li v-for="option in qgenResult.options" :key="option.key">{{ option.key }}. {{ option.text }}</li>
        </ul>
        <p><b>答案：</b>{{ formatQgenAnswer(qgenResult.answer) }}</p>
        <p><b>解析：</b>{{ qgenResult.analysis || '—' }}</p>
        <p class="muted">已保存为待审核题，不会进入组卷；请在列表中审核通过后再使用。</p>
      </div>
      <template #footer>
        <el-button @click="qgenOpen = false">关闭</el-button>
        <el-button type="primary" :loading="qgenLoading" :disabled="!qgenCatalog?.enabled || Boolean(qgenResult)" @click="generateQgen">
          {{ qgenResult ? '已生成待审题' : '生成待审题' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="audioOpen" title="音频标签与相似题目" width="760px">
      <template v-if="audioQuestion">
        <p class="muted">第 {{ audioQuestion.id }} 题 · {{ audioQuestion.stem }}</p>
        <div v-if="audioQuestion.audioResources?.length" class="audio-resource-list">
          <article v-for="resource in audioQuestion.audioResources" :key="resource.resourceId" class="audio-resource">
            <audio :src="resource.url" controls preload="metadata"></audio>
            <AudioTagCard
              :tags="resource.audioTags"
              :file-id="resource.fileId"
              show-reference
              title="题目音频参考分析"
              @analyzed="(tags) => onResourceAnalyzed(resource, tags)"
            />
          </article>
        </div>
        <el-empty v-else description="该题没有音频资源，无法生成音频标签" :image-size="70" />
        <div class="audio-similar-actions">
          <el-button type="primary" plain :loading="similarLoading" @click="loadSimilar">查找相似音频题目</el-button>
        </div>
        <el-table v-if="similarItems.length" :data="similarItems" size="small">
          <el-table-column prop="stem" label="题干" min-width="230" show-overflow-tooltip />
          <el-table-column label="标签" min-width="170">
            <template #default="{ row }">
              <span class="tag-chip">{{ row.audioTags?.genreLabel || row.audioTags?.genre || '—' }}</span>
              <span class="tag-chip">{{ row.audioTags?.emotionLabel || row.audioTags?.emotion || '—' }}</span>
              <span class="tag-chip">{{ row.audioTags?.bpm ? `${Math.round(row.audioTags.bpm)} BPM` : '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="相似度" width="90"><template #default="{ row }">{{ Math.round((row.similarity ?? 0) * 100) }}%</template></el-table-column>
          <el-table-column label="匹配依据" min-width="150" prop="matchReason" show-overflow-tooltip />
        </el-table>
      </template>
    </el-dialog>

    <el-dialog v-model="reviewOpen" :title="reviewAction === 'approve' ? '通过试题' : '驳回试题'" width="520px">
      <p class="muted">{{ current?.stem }}</p>
      <div v-if="current?.resources?.some((item) => item.type === 'image')" class="review-media">
        <img
          v-for="item in current.resources.filter((resource) => resource.type === 'image')"
          :key="item.resourceId"
          :src="item.url"
          :alt="item.name"
        />
      </div>
      <el-input v-model="reviewComment" type="textarea" :rows="4" :placeholder="reviewAction === 'reject' ? '驳回原因（必填）' : '审核意见（可选）'" />
      <template #footer><el-button @click="reviewOpen = false">取消</el-button><el-button :type="reviewAction === 'approve' ? 'primary' : 'danger'" :loading="reviewSubmitting" :disabled="reviewSubmitting" @click="submitReview">确认</el-button></template>
    </el-dialog>

  </div>
</template>

<style scoped>
.qgen-result {
  margin-top: 6px;
  padding: 14px;
  border: 1px solid #e5e9f0;
  border-radius: 8px;
  background: #fafbfc;
}
.qgen-result-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.qgen-stem { margin: 6px 0 10px; font-size: 15px; line-height: 1.7; }
.qgen-options { margin: 0 0 10px; padding-left: 20px; }
.qgen-options li { margin-bottom: 4px; }
.question-image-preview {
  max-width: 100%;
  max-height: 220px;
  border-radius: 8px;
  border: 1px solid #e5e9f0;
  object-fit: contain;
}
.qgen-image-hint { margin: 0 0 10px; font-size: 12px; }
.qgen-media,
.review-media {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 6px 0 10px;
}
.qgen-media img,
.review-media img {
  max-width: 100%;
  max-height: 260px;
  border-radius: 8px;
  border: 1px solid #e4e7ec;
  object-fit: contain;
  background: #fff;
}
.audio-resource-list { display: grid; gap: 12px; }
.audio-resource { display: grid; gap: 8px; }
.audio-resource audio { width: 100%; }
.audio-similar-actions { margin: 14px 0 10px; }
.audio-upload-field { display: grid; gap: 8px; width: 100%; }
.audio-upload-field audio { width: 100%; }
.audio-upload-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
:deep(.recent-row) > td { background: #eef6ff !important; }
.tag-chip {
  display: inline-block;
  margin: 0 6px 4px 0;
  padding: 2px 7px;
  border: 1px solid #e5e9f0;
  border-radius: 6px;
  background: #fff;
  font-size: 12px;
  color: #344054;
}
</style>
