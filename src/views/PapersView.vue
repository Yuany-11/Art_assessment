<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Plus, Search } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import { api } from '@/api'
import { saveBlob } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { Paper, Question, ScopeType, Subject } from '@/types'

const auth = useAuthStore()
const loading = ref(false)
const rows = ref<Paper[]>([])
const total = ref(0)
const pageNum = ref(1)
const pageSize = ref(10)
const filters = reactive({ subject: '', paperType: '', status: '', keyword: '' })
const dialogOpen = ref(false)
const mode = ref<'manual' | 'auto'>('manual')
const editing = ref<Paper | null>(null)
const detailOpen = ref(false)
const current = ref<Paper | null>(null)
const questionPickerOpen = ref(false)
const questionOptions = ref<Question[]>([])
const selectedQuestionIds = ref<number[]>([])
const questionFilters = reactive({ subject: '', difficulty: '', type: '' })
const form = reactive({
  title: '',
  subject: 'music' as Subject,
  paperType: 'formal' as Paper['paperType'],
  grade: 7,
  scopeType: 'school' as ScopeType,
  scopeId: 301,
  scopeName: '示范中学',
  duration: 45,
  status: 'draft' as Paper['status'],
  questionCount: 10,
  totalScore: 100,
  instructions: ''
})

const scopeByRole: Record<string, ScopeType> = {
  teacher: 'class',
  school_admin: 'school',
  district_admin: 'district',
  city_admin: 'city',
  province_admin: 'province'
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

function resetForm() {
  const scopeType = scopeByRole[auth.role ?? 'school_admin'] ?? 'school'
  Object.assign(form, {
    title: '',
    subject: 'music',
    paperType: 'formal',
    grade: 7,
    scopeType,
    scopeId: scopeType === 'class' ? 5001 : scopeType === 'school' ? 301 : scopeType === 'district' ? 22 : scopeType === 'city' ? 3 : 1,
    scopeName: scopeType === 'class' ? '七年级（1）班' : scopeType === 'school' ? '示范中学' : scopeType === 'district' ? '示例区' : scopeType === 'city' ? '示例市' : '全省',
    duration: 45,
    status: 'draft',
    questionCount: 10,
    totalScore: 100,
    instructions: ''
  })
  selectedQuestionIds.value = []
}

function openCreate(nextMode: 'manual' | 'auto') {
  editing.value = null
  mode.value = nextMode
  resetForm()
  dialogOpen.value = true
}

function openEdit(row: Paper) {
  editing.value = row
  mode.value = row.generateMode
  Object.assign(form, {
    title: row.title,
    subject: row.subject,
    paperType: row.paperType,
    grade: row.grade,
    scopeType: row.scopeType,
    scopeId: row.scopeId,
    scopeName: row.scopeName,
    duration: row.duration,
    status: row.status,
    questionCount: row.questionCount,
    totalScore: row.totalScore,
    instructions: ''
  })
  dialogOpen.value = true
}

async function save() {
  if (!form.title.trim()) {
    ElMessage.warning('请填写试卷名称')
    return
  }
  try {
    const values = { ...form, questionCount: selectedQuestionIds.value.length || form.questionCount }
    if (editing.value) {
      await api.papers.update(editing.value.id, values)
      ElMessage.success('试卷已更新')
    } else {
      await api.papers.create(values, mode.value)
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
  const result = await api.questions.list({
    subject: questionFilters.subject || form.subject,
    difficulty: questionFilters.difficulty,
    type: questionFilters.type,
    pageSize: 100
  })
  questionOptions.value = result.list
}

function searchQuestions() {
  api.questions.list({
    subject: questionFilters.subject || form.subject,
    difficulty: questionFilters.difficulty,
    type: questionFilters.type,
    pageSize: 100
  }).then((result) => {
    questionOptions.value = result.list
  })
}

function confirmQuestions() {
  form.questionCount = selectedQuestionIds.value.length || form.questionCount
  form.totalScore = questionOptions.value
    .filter((item) => selectedQuestionIds.value.includes(item.id))
    .reduce((sum, item) => sum + item.score, 0) || form.totalScore
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
        <el-button type="primary" @click="pageNum = 1; load()">查询</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" row-key="id" stripe>
        <el-table-column prop="title" label="试卷名称" min-width="240" />
        <el-table-column prop="subject" label="学科" width="90">
          <template #default="{ row }">{{ row.subject === 'music' ? '音乐' : '美术' }}</template>
        </el-table-column>
        <el-table-column prop="paperType" label="类型" width="100">
          <template #default="{ row }">{{ row.paperType === 'formal' ? '正式卷' : '练习卷' }}</template>
        </el-table-column>
        <el-table-column prop="scopeName" label="归属范围" min-width="140" />
        <el-table-column prop="duration" label="时长" width="90" />
        <el-table-column label="题目 / 总分" width="120">
          <template #default="{ row }">{{ row.questionCount }} 题 / {{ row.totalScore }} 分</template>
        </el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><StatusTag :value="row.status" /></template></el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="detail(row)">查看</el-button>
            <el-button link @click="openEdit(row)">编辑</el-button>
            <el-button link @click="toggleReady(row)">{{ row.status === 'ready' ? '转草稿' : '设为就绪' }}</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
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
        <el-form-item label="归属层级"><el-input v-model="form.scopeType" disabled /></el-form-item>
        <el-form-item label="归属对象"><el-input v-model="form.scopeName" /></el-form-item>
        <el-form-item v-if="mode === 'manual'" label="选题" class="span-2">
          <div class="inline-action"><span>已选择 {{ selectedQuestionIds.length }} 道题</span><el-button @click="openQuestionPicker">从题库选题</el-button></div>
        </el-form-item>
        <el-form-item v-else label="抽题数量"><el-input-number v-model="form.questionCount" :min="1" :max="50" /></el-form-item>
        <el-form-item label="总分"><el-input-number v-model="form.totalScore" :min="1" :max="1000" /></el-form-item>
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
          <el-option label="单选" value="single_choice" /><el-option label="简答" value="short_answer" /><el-option label="图片作品" value="image_upload" />
        </el-select>
      </div>
      <el-table :data="questionOptions" @selection-change="(selection: Question[]) => selectedQuestionIds = selection.map((item) => item.id)">
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
  </div>
</template>
