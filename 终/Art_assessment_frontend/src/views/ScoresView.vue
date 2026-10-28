<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Plus, Search, UploadFilled } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import { api } from '@/api'
import { saveBlob } from '@/api/client'
import type { Account, Assessment, Score } from '@/types'

const loading = ref(false)
const rows = ref<Score[]>([])
const total = ref(0)
const pageNum = ref(1)
const pageSize = ref(10)
const filters = reactive({ subject: '', keyword: '' })
const manualOpen = ref(false)
const importResult = ref<Record<string, unknown> | null>(null)
const importInput = ref<HTMLInputElement>()
const assessments = ref<Assessment[]>([])
const students = ref<Account[]>([])
const importAssessmentId = ref<number>()
const form = reactive({ studentId: undefined as number | undefined, assessmentId: undefined as number | undefined, totalScore: 60, reason: '' })

const currentAssessment = computed(() => assessments.value.find((item) => item.id === form.assessmentId))
const currentMaxScore = computed(() => currentAssessment.value?.totalScore ?? 100)
const importAssessment = computed(() => assessments.value.find((item) => item.id === importAssessmentId.value))
const levelLabels: Record<string, string> = { excellent: '优秀', good: '良好', pass: '合格', fail: '待提升' }
const importStatusText = computed(() => {
  const status = String(importResult.value?.status || '')
  return ({ queued: '排队中', processing: '处理中', completed: '已完成', failed: '处理失败' } as Record<string, string>)[status] || status
})

async function loadOptions() {
  try {
    const [assessmentResult, studentResult] = await Promise.all([
      api.assessments.list({ pageSize: 100 }),
      api.accounts.list('students', { pageSize: 100 })
    ])
    // 补录和导入只针对正式测评，随机练习卷不进入成绩管理。
    assessments.value = assessmentResult.list.filter((item) => item.paperType === 'formal')
    students.value = studentResult.list
  } catch {
    // 账号范围受限时仍可查看成绩列表，静默忽略选项加载失败
  }
}

async function load() {
  loading.value = true
  try {
    const result = await api.scores.list({ ...filters, pageNum: pageNum.value, pageSize: pageSize.value })
    rows.value = result.list
    total.value = result.total
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

function openManual() {
  const first = assessments.value[0]
  Object.assign(form, {
    studentId: undefined,
    assessmentId: first?.id,
    totalScore: Math.min(60, first?.totalScore ?? 100),
    reason: ''
  })
  manualOpen.value = true
}

function onAssessmentChange() {
  form.totalScore = Math.min(form.totalScore, currentMaxScore.value)
}

async function saveManual() {
  if (!form.studentId || !form.assessmentId || !form.reason.trim()) {
    ElMessage.warning('请选择学生、测评并填写补录原因')
    return
  }
  const assessment = currentAssessment.value
  if (!assessment) {
    ElMessage.warning('请选择有效的测评')
    return
  }
  const totalScore = Number(form.totalScore)
  if (totalScore > currentMaxScore.value) {
    ElMessage.warning(`总分不能超过试卷满分 ${currentMaxScore.value}`)
    return
  }
  try {
    await api.scores.manual({
      studentId: form.studentId,
      assessmentId: form.assessmentId,
      subject: assessment.subject,
      scoreItems: [{ name: '总评', score: totalScore, maxScore: 100 }],
      totalScore,
      reason: form.reason,
      overwrite: true
    })
    manualOpen.value = false
    ElMessage.success('成绩补录成功')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

let importPolling = false

async function pollImport(taskId: string) {
  importPolling = true
  for (let index = 0; index < 60 && importPolling; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 2000))
    if (!importPolling) return
    try {
      const task = await api.scores.importTask(taskId)
      importResult.value = task
      if (task.status === 'completed') {
        ElMessage.success(`导入完成：成功 ${task.successCount} 条，失败 ${task.failCount} 条`)
        await load()
        return
      }
      if (task.status === 'failed') {
        ElMessage.error('导入失败，请查看失败明细')
        return
      }
    } catch {
      return
    }
  }
}

async function importFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  if (!importAssessmentId.value) {
    ElMessage.warning('请先选择导入的测评')
    ;(event.target as HTMLInputElement).value = ''
    return
  }
  const assessment = importAssessment.value
  if (!assessment) return
  try {
    const result = await api.scores.import(file, assessment.id, assessment.subject)
    importResult.value = result
    if (result.status === 'queued') {
      ElMessage.info('文件较大，已进入后台处理，请稍候')
      await pollImport(String(result.taskId))
    } else {
      ElMessage.success('导入处理完成')
      await load()
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
  ;(event.target as HTMLInputElement).value = ''
}

onUnmounted(() => {
  importPolling = false
})

function chooseImportFile() {
  importInput.value?.click()
}

function exportScores() {
  const header = ['学号', '姓名', '班级', '客观分', '主观分', 'AI分', '总分', '等级']
  const lines = rows.value.map((row) => [row.studentNo, row.studentName, row.className, row.objectiveScore, row.subjectiveScore, row.aiScore, row.totalScore, row.level])
  const csv = `\ufeff${[header, ...lines].map((row) => row.join(',')).join('\n')}`
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `score-export-${Date.now()}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

function downloadTemplate() {
  const content = '\ufeff学籍号,姓名,客观题得分,主观题得分,AI得分,总分,备注\nS20260001,王小明,35,48,5,88,示例数据\n'
  saveBlob(new Blob([content], { type: 'text/csv;charset=utf-8' }), '线下成绩导入模板.csv')
}

async function regrade(row: Score) {
  try {
    const result = await ElMessageBox.prompt('重新判分会按当前答案与评分标准重算客观题，并写入审计日志。', '重新判分', {
      inputPlaceholder: '请填写重新判分原因',
      inputValidator: (value) => Boolean(value?.trim()) || '原因不能为空',
      type: 'warning'
    })
    await api.scores.regrade(row.id, result.value.trim())
    ElMessage.success('重新判分完成')
    await load()
  } catch (error) {
    if (error instanceof Error) ElMessage.error(error.message)
  }
}

async function showDetail(row: Score) {
  try {
    const detail = await api.scores.detail(row.id)
    await ElMessageBox.alert(
      `客观题 ${detail.objectiveScore} 分，主观题 ${detail.subjectiveScore} 分，AI 辅助 ${detail.aiScore} 分，最终 ${detail.totalScore} 分。`,
      `${detail.studentName}的成绩`,
      { confirmButtonText: '关闭' }
    )
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

onMounted(() => {
  load()
  loadOptions()
})
</script>

<template>
  <div class="stack">
    <PageHeader title="成绩管理" description="按权限范围查询、补录、导入和导出学生测评成绩。">
      <el-select v-model="importAssessmentId" style="width: 220px" placeholder="选择导入测评" filterable>
        <el-option v-for="item in assessments" :key="item.id" :label="item.title" :value="item.id" />
      </el-select>
      <el-button :icon="UploadFilled" @click="chooseImportFile">导入线下成绩</el-button>
      <el-button @click="downloadTemplate">下载导入模板</el-button>
      <input ref="importInput" class="hidden-input" type="file" accept=".csv,.xlsx" @change="importFile" />
      <el-button :icon="Download" @click="exportScores">导出成绩</el-button>
      <el-button type="primary" :icon="Plus" @click="openManual">成绩补录</el-button>
    </PageHeader>
    <section class="panel">
      <div class="filter-bar">
        <el-input v-model="filters.keyword" :prefix-icon="Search" clearable placeholder="学生姓名或学号" />
        <el-select v-model="filters.subject" clearable placeholder="学科"><el-option label="音乐" value="music" /><el-option label="美术" value="art" /></el-select>
        <el-button type="primary" @click="pageNum = 1; load()">查询</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" row-key="id" stripe>
        <el-table-column prop="studentNo" label="学籍号" min-width="140" />
        <el-table-column prop="studentName" label="学生" min-width="110" />
        <el-table-column prop="className" label="班级" min-width="140" />
        <el-table-column prop="assessmentTitle" label="测评" min-width="220" />
        <el-table-column label="成绩构成" min-width="220">
          <template #default="{ row }">客观 {{ row.objectiveScore }} · 主观 {{ row.subjectiveScore }} · AI {{ row.aiScore }}</template>
        </el-table-column>
        <el-table-column prop="totalScore" label="总分" width="90" />
        <el-table-column prop="level" label="等级" width="90"><template #default="{ row }">{{ levelLabels[row.level as string] }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><StatusTag :value="row.status" /></template></el-table-column>
        <el-table-column label="操作" width="160"><template #default="{ row }">
          <el-button link type="primary" @click="showDetail(row)">详情</el-button>
          <el-button link type="warning" :disabled="!row.attemptId" title="仅在线作答成绩可重新判分" @click="regrade(row)">重新判分</el-button>
        </template></el-table-column>
      </el-table>
      <div class="table-footer"><span>共 {{ total }} 条成绩</span><el-pagination v-model:current-page="pageNum" v-model:page-size="pageSize" :total="total" layout="prev, pager, next" @change="load" /></div>
    </section>

    <el-dialog v-model="manualOpen" title="成绩补录" width="620px">
      <el-form label-position="top" class="form-grid">
        <el-form-item label="测评" required>
          <el-select v-model="form.assessmentId" filterable placeholder="选择测评" @change="onAssessmentChange">
            <el-option v-for="item in assessments" :key="item.id" :label="`${item.title}（${item.subject === 'music' ? '音乐' : '美术'}，满分 ${item.totalScore ?? 100}）`" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="学生" required>
          <el-select v-model="form.studentId" filterable placeholder="选择学生">
            <el-option v-for="item in students" :key="item.id" :label="`${item.realName}（${item.studentNo || item.username}）`" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="学科"><el-input :model-value="currentAssessment ? (currentAssessment.subject === 'music' ? '音乐' : '美术') : ''" disabled /></el-form-item>
        <el-form-item :label="`补录总分（满分 ${currentMaxScore}）`"><el-input-number v-model="form.totalScore" :min="0" :max="currentMaxScore" /></el-form-item>
        <el-form-item label="补录原因" required class="span-2"><el-input v-model="form.reason" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="manualOpen = false">取消</el-button><el-button type="primary" @click="saveManual">确认补录</el-button></template>
    </el-dialog>

    <el-dialog :model-value="Boolean(importResult)" title="导入结果" width="620px" @close="importResult = null">
      <template v-if="importResult">
        <div class="result-strip"><span>状态 {{ importStatusText }}</span><span>总行数 {{ importResult.total }}</span><b>成功 {{ importResult.successCount }}</b><b class="danger">失败 {{ importResult.failCount }}</b></div>
        <el-alert v-if="importResult.status === 'queued' || importResult.status === 'processing'" title="后台处理中，结果会自动刷新，请勿关闭页面。" type="info" :closable="false" show-icon />
        <el-table :data="(importResult.errors as Array<Record<string, unknown>>) || []">
          <el-table-column prop="row" label="行号" width="80" /><el-table-column prop="studentNo" label="学籍号" /><el-table-column prop="message" label="失败原因" />
        </el-table>
      </template>
    </el-dialog>
  </div>
</template>
