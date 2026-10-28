<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Plus, Search } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import { api } from '@/api'
import { saveBlob } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { Paper, PaperReviewLog, Question, ScopeType, Subject } from '@/types'

const auth = useAuthStore()
function canManagePaper(row: Paper) {
  return auth.role !== 'teacher' || row.creatorId === auth.user?.id
}
const loading = ref(false)
const rows = ref<Paper[]>([])
const total = ref(0)
const pageNum = ref(1)
const pageSize = ref(10)
const filters = reactive({ subject: '', paperType: '', status: '', reviewStatus: '', keyword: '' })
const dialogOpen = ref(false)
const mode = ref<'manual' | 'auto'>('manual')
const editing = ref<Paper | null>(null)
const detailOpen = ref(false)
const current = ref<Paper | null>(null)
const questionPickerOpen = ref(false)
const questionOptions = ref<Question[]>([])
const selectedQuestionIds = ref<number[]>([])
const selectedQuestions = ref<Question[]>([])
const scopes = ref<Array<{ id: number; name: string }>>([])
const questionFilters = reactive({ subject: '', difficulty: '', type: '' })
const historyOpen = ref(false)
const reviewHistory = ref<PaperReviewLog[]>([])
const form = reactive({
  title: '',
  subject: 'music' as Subject,
  paperType: 'formal' as Paper['paperType'],
  grade: 7,
  scopeType: 'school' as ScopeType,
  scopeId: 0,
  scopeName: '',
  duration: 45,
  status: 'draft' as Paper['status'],
  questionCount: 10,
  totalScore: 100,
  autoType: 'single_choice',
  instructions: ''
})
const autoRules = reactive<Record<string, number>>({
  single_choice: 10,
  multiple_choice: 5,
  short_answer: 2,
  image_upload: 1,
  audio_upload: 1
})
const AUTO_WEIGHTS: Record<string, number> = {
  single_choice: 1,
  multiple_choice: 2,
  short_answer: 3,
  image_upload: 4,
  audio_upload: 4
}
const practiceType = computed(() => (form.subject === 'art' ? 'image_upload' : 'audio_upload'))
const autoRows = computed(() => [
  { type: 'single_choice', label: '单选题', count: autoRules.single_choice },
  { type: 'multiple_choice', label: '多选题', count: autoRules.multiple_choice },
  { type: 'short_answer', label: '简答题', count: autoRules.short_answer },
  {
    type: practiceType.value,
    label: form.subject === 'art' ? '画画实践题' : '唱歌实践题',
    count: autoRules[practiceType.value] ?? 0
  }
])
const autoTotalWeight = computed(() =>
  autoRows.value.reduce((sum, row) => sum + row.count * (AUTO_WEIGHTS[row.type] ?? 1), 0)
)
const autoScoreRows = computed(() =>
  autoRows.value.map((row) => ({
    ...row,
    score: autoTotalWeight.value ? (100 * (AUTO_WEIGHTS[row.type] ?? 1)) / autoTotalWeight.value : 0
  }))
)
const autoQuestionTotal = computed(() => autoRows.value.reduce((sum, row) => sum + row.count, 0))

const scopeByRole: Record<string, ScopeType> = {
  teacher: 'class',
  school_admin: 'school',
  district_admin: 'district',
  city_admin: 'city',
  province_admin: 'province'
}

const scopeLabels: Record<ScopeType, string> = {
  class: '班级',
  school: '学校',
  district: '区县',
  city: '市州',
  province: '全省'
}

const questionTypeLabels: Record<string, string> = {
  single_choice: '单选',
  multiple_choice: '多选',
  true_false: '判断',
  fill_blank: '填空',
  short_answer: '简答',
  listening: '听赏',
  image_upload: '图片作品',
  audio_upload: '音频作品'
}

async function load() {
  loading.value = true
  try {
    const result = await api.papers.list({ ...filters, pageNum: pageNum.value, pageSize: pageSize.value })
    rows.value = result.list
    total.value = result.total
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function loadScopes() {
  const role = auth.role ?? 'school_admin'
  const user = auth.user
  try {
    if (role === 'teacher') {
      const result = await api.classes.list({ pageSize: 100 })
      scopes.value = result.list.map((item) => ({ id: item.id, name: item.name }))
    } else if (role === 'school_admin' && user?.schoolId) {
      scopes.value = [{ id: user.schoolId, name: user.schoolName || '本校' }]
    } else if (role === 'district_admin' && user?.districtId) {
      scopes.value = [{ id: user.districtId, name: user.districtName || '本区县' }]
    } else if (role === 'city_admin' && user?.cityId) {
      scopes.value = [{ id: user.cityId, name: user.cityName || '本市州' }]
    } else if (role === 'province_admin' && user?.provinceId) {
      scopes.value = [{ id: user.provinceId, name: user.provinceName || '全省' }]
    } else {
      scopes.value = []
    }
  } catch {
    scopes.value = []
  }
}

function resetForm() {
  const scopeType = scopeByRole[auth.role ?? 'school_admin'] ?? 'school'
  Object.assign(form, {
    title: '',
    subject: 'music',
    paperType: 'formal',
    grade: 7,
    scopeType,
    scopeId: scopes.value[0]?.id ?? 0,
    scopeName: scopes.value[0]?.name ?? '',
    duration: 45,
    status: 'draft',
    questionCount: 10,
    totalScore: 100,
    autoType: 'single_choice',
    instructions: ''
  })
  Object.assign(autoRules, {
    single_choice: 10,
    multiple_choice: 5,
    short_answer: 2,
    image_upload: 1,
    audio_upload: 1
  })
  selectedQuestionIds.value = []
  selectedQuestions.value = []
}

async function openCreate(nextMode: 'manual' | 'auto') {
  editing.value = null
  mode.value = nextMode
  await loadScopes()
  resetForm()
  dialogOpen.value = true
}

async function openEdit(row: Paper) {
  editing.value = row
  mode.value = row.generateMode
  await loadScopes()
  Object.assign(form, {
    title: row.title,
    subject: row.subject,
    paperType: row.paperType,
    grade: row.grade,
    scopeType: row.scopeType,
    scopeId: row.scopeId,
    scopeName: row.scopeName,
    duration: row.duration,
    status: row.status === 'published' ? 'ready' : row.status,
    questionCount: row.questionCount,
    totalScore: row.totalScore,
    autoType: 'single_choice',
    instructions: row.instructions ?? ''
  })
  selectedQuestions.value = (row.questions ?? []).map((item) => ({
    id: item.questionId,
    stem: item.stem,
    type: item.type,
    score: item.score
  } as Question))
  selectedQuestionIds.value = selectedQuestions.value.map((item) => item.id)
  Object.assign(autoRules, {
    single_choice: 0,
    multiple_choice: 0,
    short_answer: 0,
    image_upload: 0,
    audio_upload: 0
  })
  selectedQuestions.value.forEach((question) => {
    if (question.type in autoRules) {
      autoRules[question.type as keyof typeof autoRules] += 1
    }
  })
  dialogOpen.value = true
}

function buildQuestionConfigs() {
  return selectedQuestions.value.map((question, index) => ({
    questionId: question.id,
    order: index + 1,
    score: question.score
  }))
}

async function save() {
  if (!form.title.trim()) {
    ElMessage.warning('请填写试卷名称')
    return
  }
  try {
    if (editing.value) {
      const values: Record<string, unknown> = {
        title: form.title.trim(),
        duration: form.duration,
        instructions: form.instructions || null,
        status: form.status === 'published' ? 'ready' : form.status
      }
      if (mode.value === 'manual' && selectedQuestions.value.length) {
        values.questions = buildQuestionConfigs()
      }
      await api.papers.update(editing.value.id, values as Partial<Paper>)
      ElMessage.success('试卷已更新')
    } else {
      if (!form.scopeId) {
        ElMessage.warning('当前账号没有可用的归属范围，请先联系管理员配置组织信息')
        return
      }
      if (mode.value === 'manual' && !selectedQuestions.value.length) {
        ElMessage.warning('请至少选择一道试题')
        return
      }
      if (mode.value === 'auto') {
        const rules = autoRows.value.filter((row) => row.count > 0)
        if (!rules.length) {
          ElMessage.warning('请至少为一种题型设置抽题数量')
          return
        }
        if (autoQuestionTotal.value > 200) {
          ElMessage.warning('自动组卷题目总数不能超过 200 道')
          return
        }
      }
      const base = {
        title: form.title.trim(),
        subject: form.subject,
        paperType: form.paperType,
        grade: form.grade,
        scopeType: form.scopeType,
        scopeId: form.scopeId,
        duration: form.duration,
        instructions: form.instructions || null,
        status: form.status === 'published' ? 'ready' : form.status
      }
      if (mode.value === 'manual') {
        await api.papers.create({ ...base, questions: buildQuestionConfigs() }, 'manual')
      } else {
        await api.papers.create({
          ...base,
          rules: autoRows.value
            .filter((row) => row.count > 0)
            .map((row) => ({ type: row.type, count: row.count }))
        }, 'auto')
      }
      ElMessage.success(mode.value === 'manual' ? '手动组卷已保存' : '自动组卷已完成')
    }
    dialogOpen.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function toggleReady(row: Paper) {
  await api.papers.update(row.id, { status: row.status === 'ready' ? 'draft' : 'ready' })
  ElMessage.success(row.status === 'ready' ? '已转为草稿' : '试卷已就绪')
  await load()
}

async function submitForReview(row: Paper) {
  try {
    const result = await ElMessageBox.prompt('可填写提交说明，版本号将用于审核并发校验。', '提交试卷审核', {
      inputPlaceholder: '提交说明（可选）',
      inputValue: '',
      confirmButtonText: '提交审核'
    })
    await api.papers.submitReview(row.id, row.version, result.value || undefined)
    ElMessage.success('试卷已提交审核')
    await load()
  } catch (error) {
    if (error instanceof Error) ElMessage.error(error.message)
  }
}

async function openReviewHistory(row: Paper) {
  try {
    reviewHistory.value = await api.papers.reviewHistory(row.id)
    current.value = row
    historyOpen.value = true
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function handlePaperAction(command: string, row: Paper) {
  if (command === 'detail') void detail(row)
  if (command === 'edit') openEdit(row)
  if (command === 'submit') void submitForReview(row)
  if (command === 'history') void openReviewHistory(row)
  if (command === 'toggle') void toggleReady(row)
  if (command === 'delete') void remove(row)
}

async function remove(row: Paper) {
  try {
    await ElMessageBox.confirm(`确定删除“${row.title}”吗？`, '删除试卷', { type: 'warning' })
    await api.papers.remove(row.id)
    ElMessage.success('试卷已删除')
    await load()
  } catch (error) {
    if (error instanceof Error) ElMessage.error(error.message)
  }
}

async function detail(row: Paper) {
  try {
    current.value = await api.papers.detail(row.id)
    detailOpen.value = true
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function download(type: 'materials' | 'answers', row: Paper) {
  try {
    const blob = type === 'materials' ? await api.papers.downloadMaterials(row.id) : await api.papers.downloadAnswers(row.id)
    saveBlob(blob, `${row.title}-${type === 'materials' ? '材料' : '答案'}-${dayjs().format('YYYYMMDD')}`)
    ElMessage.success('下载已开始')
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function openQuestionPicker() {
  questionPickerOpen.value = true
  if (!questionFilters.subject) questionFilters.subject = form.subject
  await searchQuestions()
  selectedQuestionIds.value = selectedQuestions.value.map((item) => item.id)
}

function handleQuestionSelection(selection: Question[]) {
  selectedQuestions.value = selection
  selectedQuestionIds.value = selection.map((item) => item.id)
}

async function searchQuestions() {
  const result = await api.questions.list({
    subject: questionFilters.subject || form.subject,
    difficulty: questionFilters.difficulty,
    type: questionFilters.type,
    pageSize: 100
  })
  questionOptions.value = result.list
}

function confirmQuestions() {
  form.questionCount = selectedQuestions.value.length || form.questionCount
  const total = selectedQuestions.value.reduce((sum, item) => sum + item.score, 0)
  if (total > 0) form.totalScore = total
  questionPickerOpen.value = false
}

onMounted(load)
</script>

<template>
  <div class="stack">
    <PageHeader title="组卷管理" description="手动或自动生成适配当前组织范围的练习卷和正式测评卷。">
      <el-button @click="openCreate('auto')">自动组卷</el-button>
      <el-button type="primary" :icon="Plus" @click="openCreate('manual')">手动组卷</el-button>
    </PageHeader>

    <section class="panel">
      <div class="filter-bar">
        <el-input v-model="filters.keyword" :prefix-icon="Search" clearable placeholder="搜索试卷名称" @keyup.enter="load" />
        <el-select v-model="filters.subject" clearable placeholder="学科">
          <el-option label="音乐" value="music" />
          <el-option label="美术" value="art" />
        </el-select>
        <el-select v-model="filters.paperType" clearable placeholder="试卷类型">
          <el-option label="练习卷" value="practice" />
          <el-option label="正式卷" value="formal" />
        </el-select>
        <el-select v-model="filters.status" clearable placeholder="状态">
          <el-option label="草稿" value="draft" />
          <el-option label="已就绪" value="ready" />
          <el-option label="已发布" value="published" />
          <el-option label="已归档" value="archived" />
        </el-select>
        <el-select v-model="filters.reviewStatus" clearable placeholder="审核状态">
          <el-option label="未提交" value="none" />
          <el-option label="待审核" value="pending" />
          <el-option label="审核通过" value="approved" />
          <el-option label="已驳回" value="rejected" />
        </el-select>
        <el-button type="primary" @click="pageNum = 1; load()">查询</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" row-key="id" stripe>
        <el-table-column prop="title" label="试卷名称" min-width="210" show-overflow-tooltip />
        <el-table-column prop="subject" label="学科" width="75">
          <template #default="{ row }">{{ row.subject === 'music' ? '音乐' : '美术' }}</template>
        </el-table-column>
        <el-table-column prop="paperType" label="类型" width="90">
          <template #default="{ row }">{{ row.paperType === 'formal' ? '正式卷' : '练习卷' }}</template>
        </el-table-column>
        <el-table-column prop="scopeName" label="归属范围" min-width="120" show-overflow-tooltip />
        <el-table-column prop="duration" label="时长" width="70" />
        <el-table-column label="题目 / 总分" width="125">
          <template #default="{ row }"><span class="paper-question-count">{{ row.questionCount }} 题 / {{ row.totalScore }} 分</span></template>
        </el-table-column>
        <el-table-column label="状态" width="90"><template #default="{ row }"><StatusTag :value="row.status" /></template></el-table-column>
        <el-table-column label="审核信息" width="125">
          <template #default="{ row }">
            <StatusTag :value="row.reviewStatus" />
            <div class="review-cell-meta"><span>v{{ row.version }}</span><span>{{ row.reviewerName || '待分配' }}</span></div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="detail(row)">查看</el-button>
            <el-dropdown v-if="canManagePaper(row)" trigger="click" @command="(command: string) => handlePaperAction(command, row)">
              <el-button link class="table-more-button">更多操作</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="edit" :disabled="row.reviewStatus === 'pending' || row.status === 'published'">编辑试卷</el-dropdown-item>
                  <el-dropdown-item v-if="row.reviewStatus === 'none' || row.reviewStatus === 'rejected'" command="submit">{{ row.reviewStatus === 'rejected' ? '重新提交审核' : '提交审核' }}</el-dropdown-item>
                  <el-dropdown-item command="history">审核记录</el-dropdown-item>
                  <el-dropdown-item command="toggle" :disabled="row.reviewStatus === 'pending' || row.reviewStatus === 'approved'">{{ row.status === 'ready' ? '转为草稿' : '设为就绪' }}</el-dropdown-item>
                  <el-dropdown-item command="delete" divided :disabled="['pending', 'approved', 'published'].includes(row.reviewStatus) || row.status === 'published'">删除试卷</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>
      <div class="table-footer">
        <span>共 {{ total }} 份试卷</span>
        <el-pagination v-model:current-page="pageNum" v-model:page-size="pageSize" :total="total" layout="prev, pager, next" @change="load" />
      </div>
    </section>

    <el-dialog v-model="dialogOpen" :title="editing ? '修改试卷' : mode === 'manual' ? '手动组卷' : '自动组卷'" width="760px">
      <el-form label-position="top" class="form-grid">
        <el-form-item label="试卷名称" required class="span-2"><el-input v-model="form.title" /></el-form-item>
        <el-form-item label="学科">
          <el-select v-model="form.subject"><el-option label="音乐" value="music" /><el-option label="美术" value="art" /></el-select>
        </el-form-item>
        <el-form-item label="试卷类型">
          <el-select v-model="form.paperType"><el-option label="练习卷" value="practice" /><el-option label="正式卷" value="formal" /></el-select>
        </el-form-item>
        <el-form-item label="年级"><el-select v-model="form.grade"><el-option v-for="g in 12" :key="g" :label="`${g} 年级`" :value="g" /></el-select></el-form-item>
        <el-form-item label="时长（分钟）"><el-input-number v-model="form.duration" :min="1" :max="300" /></el-form-item>
        <el-form-item label="归属层级">
          <el-select v-model="form.scopeType" disabled>
            <el-option v-for="(label, value) in scopeLabels" :key="value" :label="label" :value="value" />
          </el-select>
        </el-form-item>
        <el-form-item label="归属对象" :required="!editing">
          <el-input v-if="editing" :model-value="form.scopeName" disabled />
          <el-select v-else v-model="form.scopeId" placeholder="请选择归属对象">
            <el-option v-for="item in scopes" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="mode === 'manual'" label="选题" class="span-2">
          <div class="inline-action"><span>已选择 {{ selectedQuestionIds.length }} 道题，共 {{ selectedQuestions.reduce((sum, item) => sum + item.score, 0) }} 分</span><el-button @click="openQuestionPicker">从题库选题</el-button></div>
          <div v-if="selectedQuestions.length" class="paper-question-preview">
            <article v-for="(question, index) in selectedQuestions" :key="question.id">
              <div><b>第 {{ index + 1 }} 题 · {{ question.score }} 分</b><span>{{ question.type }}</span></div>
              <p>{{ question.stem }}</p>
            </article>
          </div>
        </el-form-item>
        <el-form-item v-else label="题型与抽题数量（总分固定 100 分）" class="span-2">
          <div class="auto-rule-list">
            <div v-for="row in autoScoreRows" :key="row.type" class="auto-rule-row">
              <b>{{ row.label }}</b>
              <el-input-number v-model="autoRules[row.type]" :min="0" :max="100" />
              <span>每题约 {{ row.score.toFixed(2) }} 分</span>
            </div>
            <p class="form-hint">
              共 {{ autoQuestionTotal }} 题，总分固定 100 分；题目越多每题分值越低。
              分值权重：单选 &lt; 多选 &lt; 简答 &lt; {{ form.subject === 'art' ? '画画实践' : '唱歌实践' }}。
              实际分值为两位小数，最后一道题会补齐舍入差额。
            </p>
          </div>
        </el-form-item>
        <el-form-item label="总分">
          <el-input :model-value="mode === 'auto' ? '100 分（固定）' : `${form.totalScore} 分`" disabled />
        </el-form-item>
        <el-form-item label="状态"><el-radio-group v-model="form.status"><el-radio value="draft">草稿</el-radio><el-radio value="ready">就绪</el-radio></el-radio-group></el-form-item>
        <el-form-item label="考试说明" class="span-2"><el-input v-model="form.instructions" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogOpen = false">取消</el-button><el-button type="primary" @click="save">保存试卷</el-button></template>
    </el-dialog>

    <el-drawer v-model="questionPickerOpen" title="从题库选题" size="760px">
      <div class="filter-bar">
        <el-select v-model="questionFilters.subject" clearable placeholder="学科" @change="searchQuestions"><el-option label="音乐" value="music" /><el-option label="美术" value="art" /></el-select>
        <el-select v-model="questionFilters.difficulty" clearable placeholder="难度" @change="searchQuestions"><el-option v-for="d in 5" :key="d" :label="`难度 ${d}`" :value="String(d)" /></el-select>
        <el-select v-model="questionFilters.type" clearable placeholder="题型" @change="searchQuestions">
          <el-option v-for="(label, value) in questionTypeLabels" :key="value" :label="label" :value="value" />
        </el-select>
      </div>
      <el-table :data="questionOptions" row-key="id" @selection-change="handleQuestionSelection">
        <el-table-column type="selection" width="44" />
        <el-table-column prop="stem" label="题干" min-width="300" />
        <el-table-column prop="difficulty" label="难度" width="70" />
        <el-table-column prop="score" label="分值" width="70" />
      </el-table>
      <template #footer><el-button @click="questionPickerOpen = false">取消</el-button><el-button type="primary" @click="confirmQuestions">确认选题</el-button></template>
    </el-drawer>

    <el-drawer v-model="detailOpen" title="试卷详情" size="560px">
      <template v-if="current">
        <div class="detail-title"><div><h2>{{ current.title }}</h2><p>{{ current.subject === 'music' ? '音乐' : '美术' }} · {{ current.paperType === 'formal' ? '正式卷' : '练习卷' }}</p></div><StatusTag :value="current.status" /></div>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="归属范围">{{ current.scopeName }}</el-descriptions-item>
          <el-descriptions-item label="年级">{{ current.grade }} 年级</el-descriptions-item>
          <el-descriptions-item label="题目数量">{{ current.questionCount }}</el-descriptions-item>
          <el-descriptions-item label="总分">{{ current.totalScore }}</el-descriptions-item>
          <el-descriptions-item label="考试时长">{{ current.duration }} 分钟</el-descriptions-item>
          <el-descriptions-item label="创建人">{{ current.creatorName }}</el-descriptions-item>
          <el-descriptions-item label="审核状态"><StatusTag :value="current.reviewStatus" /></el-descriptions-item>
          <el-descriptions-item label="版本号">v{{ current.version }}</el-descriptions-item>
          <el-descriptions-item label="审核人">{{ current.reviewerName || '—' }}</el-descriptions-item>
          <el-descriptions-item label="审核时间">{{ current.reviewedAt || '—' }}</el-descriptions-item>
          <el-descriptions-item label="审核意见" :span="2">{{ current.reviewComment || '—' }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="current.questions?.length" class="paper-question-preview">
          <h3>试题与解析</h3>
          <article v-for="(question, index) in current.questions" :key="question.questionId">
            <div><b>第 {{ index + 1 }} 题 · {{ question.score }} 分</b><span>{{ question.type }}</span></div>
            <p>{{ question.stem }}</p>
            <small>解析：{{ question.analysis || '暂无解析' }}</small>
          </article>
        </div>
        <div class="drawer-actions">
          <el-button :icon="Download" @click="download('materials', current)">下载音视频与图片材料</el-button>
          <el-button :icon="Download" @click="download('answers', current)">下载答案与解析</el-button>
        </div>
      </template>
    </el-drawer>

    <el-drawer v-model="historyOpen" title="试卷审核记录" size="520px">
      <div class="panel-head"><div><h3>{{ current?.title }}</h3><span>当前版本 v{{ current?.version }}</span></div></div>
      <el-timeline v-if="reviewHistory.length">
        <el-timeline-item v-for="item in reviewHistory" :key="item.id" :timestamp="item.createdAt.replace('T', ' ').slice(0, 16)" :type="item.action === 'reject' ? 'danger' : item.action === 'approve' ? 'success' : 'primary'">
          <div class="review-history-item">
            <b>{{ item.action === 'submit' ? '提交审核' : item.action === 'approve' ? '审核通过' : '审核驳回' }}</b>
            <span>版本 v{{ item.version }} · {{ item.reviewerName || current?.creatorName }}</span>
            <p>{{ item.comment || '无补充说明' }}</p>
          </div>
        </el-timeline-item>
      </el-timeline>
      <div v-else class="empty-card student-card">暂无审核记录</div>
    </el-drawer>
  </div>
</template>
