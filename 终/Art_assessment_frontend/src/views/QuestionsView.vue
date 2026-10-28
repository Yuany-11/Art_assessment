<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Upload } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import { api } from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { Chapter, Course, Question, Subject } from '@/types'

const auth = useAuthStore()
const isQuestionAdmin = computed(() => auth.role === 'question_admin')
function isOwnEditable(row: Question) {
  return row.creatorId === auth.user?.id && ['draft', 'rejected'].includes(row.status)
}
function canEditRow(row: Question) {
  return isQuestionAdmin.value || isOwnEditable(row)
}
function canSubmitRow(row: Question) {
  return !isQuestionAdmin.value && isOwnEditable(row)
}
function canManageResources(row: Question) {
  return isQuestionAdmin.value || (row.creatorId === auth.user?.id && ['draft', 'pending', 'rejected'].includes(row.status))
}

const loading = ref(false)
const rows = ref<Question[]>([])
const total = ref(0)
const pageNum = ref(1)
const pageSize = ref(10)
const filters = reactive({ subject: '', status: '', type: '', difficulty: '', keyword: '' })
const dialogOpen = ref(false)
const reviewOpen = ref(false)
const resourceOpen = ref(false)
const editing = ref<Question | null>(null)
const current = ref<Question | null>(null)
const reviewAction = ref<'approve' | 'reject'>('approve')
const reviewComment = ref('')
const courses = ref<Course[]>([])
const chapters = ref<Chapter[]>([])
const options = ref<Array<{ key: string; text: string }>>([{ key: 'A', text: '' }, { key: 'B', text: '' }])
const form = reactive({
  subject: 'music' as Subject,
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
  answerText: ''
})

const questionTypeLabels: Record<string, string> = {
  single_choice: '单选题',
  multiple_choice: '多选题',
  true_false: '判断题',
  fill_blank: '填空题',
  short_answer: '简答题',
  listening: '听赏题',
  image_upload: '图片作品',
  audio_upload: '音频作品'
}
const choiceTypes = ['single_choice', 'multiple_choice', 'listening']
const isChoice = computed(() => choiceTypes.includes(form.type))

const filteredCourses = computed(() => courses.value.filter((item) => item.subject === form.subject && item.grade === Number(form.grade)))

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
  form.answerSingle = options.value[0]?.key ?? 'A'
  void loadChapters()
}

function defaultScoringMode(type: string) {
  return ['single_choice', 'multiple_choice', 'true_false', 'fill_blank', 'listening'].includes(type) ? 'auto' : 'manual'
}

async function load() {
  loading.value = true
  try {
    const result = await api.questions.list({ ...filters, pageNum: pageNum.value, pageSize: pageSize.value })
    rows.value = result.list
    total.value = result.total
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

function changePageSize() {
  pageNum.value = 1
  load()
}

function openCreate() {
  editing.value = null
  Object.assign(form, {
    subject: 'music',
    grade: 7,
    courseId: 0,
    chapterId: '',
    type: 'single_choice',
    difficulty: 2,
    stem: '',
    score: 5,
    publishNow: true,
    scoringMode: 'auto',
    answerSingle: 'A',
    answerMulti: [],
    answerBool: true,
    answerValues: '',
    answerText: ''
  })
  options.value = [{ key: 'A', text: '' }, { key: 'B', text: '' }]
  syncCourseSelection()
  dialogOpen.value = true
}

async function openEdit(row: Question) {
  editing.value = row
  const detail = row.options || row.answer ? row : await api.questions.detail(row.id).catch(() => row)
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
    answerValues: Array.isArray(answer.values) ? (answer.values as string[]).join('\n') : '',
    answerText: typeof answer.text === 'string' ? answer.text : ''
  })
  options.value = (detail.options ?? []).map((item) => ({ key: item.key, text: item.text }))
  if (!options.value.length && choiceTypes.includes(row.type)) {
    options.value = [{ key: 'A', text: '' }, { key: 'B', text: '' }]
  }
  await loadChapters()
  dialogOpen.value = true
}

function buildAnswer() {
  if (form.type === 'single_choice' || form.type === 'listening') return { value: form.answerSingle }
  if (form.type === 'multiple_choice') return { values: form.answerMulti }
  if (form.type === 'true_false') return { value: form.answerBool }
  if (form.type === 'fill_blank') {
    return { values: form.answerValues.split('\n').map((item) => item.trim()).filter(Boolean) }
  }
  if (form.type === 'short_answer') return { text: form.answerText.trim() }
  return {}
}

function validate() {
  if (!form.stem.trim()) return '请填写题干'
  if (!form.courseId) return '请选择课程，课程需与学科和年级一致'
  if (isChoice.value) {
    if (options.value.length < 2) return '选择题至少需要两个选项'
    if (options.value.some((item) => !item.key.trim() || !item.text.trim())) return '请完整填写选项标识和内容'
    if (form.type === 'multiple_choice' && !form.answerMulti.length) return '请选择多选题答案'
    if (form.type !== 'multiple_choice' && !options.value.some((item) => item.key === form.answerSingle)) return '请选择单选题答案'
  }
  if (form.type === 'fill_blank' && !form.answerValues.trim()) return '请填写填空题答案'
  if (form.type === 'short_answer' && !form.answerText.trim()) return '请填写简答题参考答案'
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
    options: isChoice.value ? options.value.map((item) => ({ key: item.key.trim(), text: item.text.trim() })) : undefined
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

watch(() => [form.subject, form.grade], syncCourseSelection)
watch(() => form.courseId, () => {
  void loadChapters()
})

function openReview(row: Question, action: 'approve' | 'reject') {
  current.value = row
  reviewAction.value = action
  reviewComment.value = ''
  reviewOpen.value = true
}

async function submitReview() {
  if (!current.value) return
  if (reviewAction.value === 'reject' && !reviewComment.value.trim()) {
    ElMessage.warning('驳回时必须填写原因')
    return
  }
  await api.questions.review(current.value.id, reviewAction.value, reviewComment.value)
  reviewOpen.value = false
  ElMessage.success(reviewAction.value === 'approve' ? '试题已通过' : '试题已驳回')
  await load()
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

function openResources(row: Question) {
  current.value = row
  resourceOpen.value = true
}

async function uploadResource(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file || !current.value) return
  await api.questions.uploadResource(current.value.id, file)
  ElMessage.success(`资源 ${file.name} 已上传并关联`)
  resourceOpen.value = false
  await load()
  ;(event.target as HTMLInputElement).value = ''
}

async function clearResources() {
  if (!current.value) return
  const detail = await api.questions.detail(current.value.id).catch(() => current.value)
  const resources = detail?.resources ?? []
  if (!resources.length) {
    ElMessage.info('当前试题没有可删除的资源')
    return
  }
  try {
    for (const resource of resources) {
      await api.questions.removeResource(current.value.id, resource.resourceId)
    }
    ElMessage.success('试题资源已删除')
    resourceOpen.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

onMounted(() => {
  load()
  loadCourses()
})
</script>

<template>
  <div class="stack">
    <PageHeader title="试题管理" :description="isQuestionAdmin ? '维护公共题库与教师提交试题，完成审核和音视频资源关联。' : '创建和修改本人试题，提交题库管理员审核；审核通过后进入公共题库。'">
      <el-button type="primary" :icon="Plus" @click="openCreate">创建试题</el-button>
    </PageHeader>
    <section class="panel">
      <div class="filter-bar">
        <el-input v-model="filters.keyword" :prefix-icon="Search" clearable placeholder="题干关键词" />
        <el-select v-model="filters.subject" clearable placeholder="学科"><el-option label="音乐" value="music" /><el-option label="美术" value="art" /></el-select>
        <el-select v-model="filters.status" clearable placeholder="状态"><el-option label="待审核" value="pending" /><el-option label="已通过" value="approved" /><el-option label="已驳回" value="rejected" /></el-select>
        <el-select v-model="filters.type" clearable placeholder="题型"><el-option v-for="(label, value) in questionTypeLabels" :key="value" :label="label" :value="value" /></el-select>
        <el-select v-model="filters.difficulty" clearable placeholder="难度"><el-option v-for="d in 5" :key="d" :label="`难度 ${d}`" :value="String(d)" /></el-select>
        <el-button type="primary" @click="pageNum = 1; load()">查询</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" row-key="id" stripe>
        <el-table-column prop="id" label="编号" width="90" />
        <el-table-column prop="stem" label="题干" min-width="280" show-overflow-tooltip />
        <el-table-column prop="subject" label="学科" width="80"><template #default="{ row }">{{ row.subject === 'music' ? '音乐' : '美术' }}</template></el-table-column>
        <el-table-column prop="grade" label="年级" width="70" />
        <el-table-column label="题型" width="110"><template #default="{ row }">{{ questionTypeLabels[row.type] || row.type }}</template></el-table-column>
        <el-table-column prop="difficulty" label="难度" width="70" />
        <el-table-column prop="score" label="分值" width="70" />
        <el-table-column prop="resourceCount" label="资源" width="70" />
        <el-table-column label="状态" width="100"><template #default="{ row }"><StatusTag :value="row.status" /></template></el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button v-if="canEditRow(row)" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="canSubmitRow(row)" link type="primary" @click="submitForReview(row)">提交审核</el-button>
            <el-button v-if="isQuestionAdmin && row.status === 'pending'" link @click="openReview(row, 'approve')">通过</el-button>
            <el-button v-if="isQuestionAdmin && row.status === 'pending'" link type="warning" @click="openReview(row, 'reject')">驳回</el-button>
            <el-button v-if="canManageResources(row)" link @click="openResources(row)">资源</el-button>
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
        <el-form-item label="学科"><el-select v-model="form.subject"><el-option label="音乐" value="music" /><el-option label="美术" value="art" /></el-select></el-form-item>
        <el-form-item label="年级"><el-select v-model="form.grade"><el-option v-for="g in 12" :key="g" :label="`${g} 年级`" :value="g" /></el-select></el-form-item>
        <el-form-item label="课程" required>
          <el-select v-model="form.courseId" placeholder="请选择课程">
            <el-option v-for="course in filteredCourses" :key="course.id" :label="course.name" :value="course.id" />
          </el-select>
          <div v-if="!filteredCourses.length" class="form-hint">没有匹配当前学科和年级的课程，请先创建课程。</div>
        </el-form-item>
        <el-form-item label="章节">
          <el-select v-model="form.chapterId" clearable placeholder="可不选" :disabled="!form.courseId">
            <el-option v-for="chapter in chapters" :key="chapter.id" :label="chapter.name" :value="chapter.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="题型">
          <el-select v-model="form.type" @change="form.scoringMode = defaultScoringMode(form.type)">
            <el-option v-for="(label, value) in questionTypeLabels" :key="value" :label="label" :value="value" />
          </el-select>
        </el-form-item>
        <el-form-item label="难度"><el-select v-model="form.difficulty"><el-option v-for="d in 5" :key="d" :label="`难度 ${d}`" :value="d" /></el-select></el-form-item>
        <el-form-item label="默认分值"><el-input-number v-model="form.score" :min="0.5" :max="100" :step="0.5" /></el-form-item>
        <el-form-item label="评分方式">
          <el-select v-model="form.scoringMode">
            <el-option label="自动判分" value="auto" />
            <el-option label="人工评分" value="manual" />
            <el-option label="AI 辅助评分" value="ai" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="!editing && isQuestionAdmin" label="创建后立即发布"><el-switch v-model="form.publishNow" /></el-form-item>
        <el-form-item label="题干" required class="span-2"><el-input v-model="form.stem" type="textarea" :rows="4" /></el-form-item>

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

        <el-form-item v-if="form.type === 'single_choice' || form.type === 'listening'" label="正确答案" class="span-2">
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
        <el-form-item v-else-if="form.type === 'fill_blank'" label="正确答案（每行一个空）" class="span-2">
          <el-input v-model="form.answerValues" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item v-else-if="form.type === 'short_answer'" label="参考答案" class="span-2">
          <el-input v-model="form.answerText" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogOpen = false">取消</el-button><el-button type="primary" @click="save">保存试题</el-button></template>
    </el-dialog>

    <el-dialog v-model="reviewOpen" :title="reviewAction === 'approve' ? '通过试题' : '驳回试题'" width="520px">
      <p class="muted">{{ current?.stem }}</p>
      <el-input v-model="reviewComment" type="textarea" :rows="4" :placeholder="reviewAction === 'reject' ? '驳回原因（必填）' : '审核意见（可选）'" />
      <template #footer><el-button @click="reviewOpen = false">取消</el-button><el-button :type="reviewAction === 'approve' ? 'primary' : 'danger'" @click="submitReview">确认</el-button></template>
    </el-dialog>

    <el-dialog v-model="resourceOpen" title="试题资源管理" width="520px">
      <p class="muted">当前已关联 {{ current?.resourceCount || 0 }} 个图片或音频资源。</p>
      <label class="upload-zone">
        <el-icon><Upload /></el-icon>
        <b>点击上传图片或音频</b>
        <span>支持 JPG、PNG、WEBP、MP3、WAV</span>
        <input type="file" accept="image/*,audio/*" @change="uploadResource" />
      </label>
      <el-button v-if="current?.resourceCount" type="danger" plain class="full-button" @click="clearResources">删除全部资源</el-button>
    </el-dialog>
  </div>
</template>
