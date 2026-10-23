<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import { api } from '@/api'
import type { Assessment, Paper, ScopeType } from '@/types'

const loading = ref(false)
const rows = ref<Assessment[]>([])
const papers = ref<Paper[]>([])
const total = ref(0)
const pageNum = ref(1)
const pageSize = ref(10)
const filters = reactive({ subject: '', status: '', keyword: '' })
const dialogOpen = ref(false)
const form = reactive({
  paperId: 0,
  title: '',
  targetType: 'school' as ScopeType,
  targetNames: '示范中学',
  targetGrades: [7],
  startTime: '',
  endTime: '',
  attemptLimit: 1,
  showAnswerMode: 'after_end',
  instructions: '请在规定时间内完成，逾期系统自动交卷。'
})

async function load() {
  loading.value = true
  try {
    const [assessmentResult, paperResult] = await Promise.all([
      api.assessments.list({ ...filters, pageNum: pageNum.value, pageSize: pageSize.value }),
      api.papers.list({ status: 'ready', reviewStatus: 'approved', pageSize: 100 })
    ])
    rows.value = assessmentResult.list
    total.value = assessmentResult.total
    papers.value = paperResult.list
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  const paper = papers.value[0]
  Object.assign(form, {
    paperId: paper?.id ?? 0,
    title: paper ? `${paper.title}正式测评` : '',
    targetType: paper?.scopeType ?? 'school',
    targetNames: paper?.scopeName ?? '示范中学',
    targetGrades: [paper?.grade ?? 7],
    startTime: '',
    endTime: '',
    attemptLimit: 1,
    showAnswerMode: 'after_end',
    instructions: '请在规定时间内完成，逾期系统自动交卷。'
  })
  dialogOpen.value = true
}

async function publish() {
  if (!form.paperId || !form.title.trim()) {
    ElMessage.warning('请选择试卷并填写测评名称')
    return
  }
  const start = form.startTime || new Date().toISOString()
  const end = form.endTime || new Date(Date.now() + 86400000).toISOString()
  try {
    await api.assessments.create({
      ...form,
      targetIds: [301],
      startTime: start,
      endTime: end
    })
    dialogOpen.value = false
    ElMessage.success('测评已发布')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function withdraw(row: Assessment) {
  try {
    const result = await ElMessageBox.prompt('请填写撤回原因，操作会写入审计日志。', '撤回测评', {
      inputValidator: (value) => Boolean(value?.trim()) || '撤回原因不能为空',
      type: 'warning'
    })
    await api.assessments.withdraw(row.id, result.value)
    ElMessage.success('测评已撤回')
    await load()
  } catch (error) {
    if (error instanceof Error) ElMessage.error(error.message)
  }
}

onMounted(load)
</script>

<template>
  <div class="stack">
    <PageHeader title="测评发布" description="选择已就绪试卷，按年级、学校或行政区域发布测评。">
      <el-button type="primary" :icon="Plus" @click="openCreate">发布测评</el-button>
    </PageHeader>
    <section class="panel">
      <div class="filter-bar">
        <el-input v-model="filters.keyword" :prefix-icon="Search" clearable placeholder="测评名称" />
        <el-select v-model="filters.subject" clearable placeholder="学科"><el-option label="音乐" value="music" /><el-option label="美术" value="art" /></el-select>
        <el-select v-model="filters.status" clearable placeholder="状态"><el-option label="已发布" value="published" /><el-option label="已撤回" value="withdrawn" /><el-option label="已结束" value="finished" /></el-select>
        <el-button type="primary" @click="pageNum = 1; load()">查询</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" row-key="id" stripe>
        <el-table-column prop="title" label="测评名称" min-width="240" />
        <el-table-column prop="paperTitle" label="关联试卷" min-width="220" />
        <el-table-column prop="targetNames" label="目标范围" min-width="150"><template #default="{ row }">{{ row.targetNames.join('、') }}</template></el-table-column>
        <el-table-column label="时间" min-width="300"><template #default="{ row }">{{ row.startTime.replace('T', ' ').slice(0, 16) }} 至 {{ row.endTime.replace('T', ' ').slice(0, 16) }}</template></el-table-column>
        <el-table-column label="参与情况" width="120"><template #default="{ row }">{{ row.submittedCount }}/{{ row.participantCount }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><StatusTag :value="row.status" /></template></el-table-column>
        <el-table-column label="操作" width="140"><template #default="{ row }"><el-button link type="danger" :disabled="row.status !== 'published'" @click="withdraw(row)">撤回</el-button></template></el-table-column>
      </el-table>
      <div class="table-footer"><span>共 {{ total }} 场测评</span><el-pagination v-model:current-page="pageNum" v-model:page-size="pageSize" :total="total" layout="prev, pager, next" @change="load" /></div>
    </section>

    <el-dialog v-model="dialogOpen" title="发布测评" width="720px">
      <el-form label-position="top" class="form-grid">
        <el-form-item label="选择试卷" required class="span-2">
          <el-select v-model="form.paperId" @change="(id: number) => { const p = papers.find((item) => item.id === id); if (p) { form.title = `${p.title}正式测评`; form.targetType = p.scopeType; form.targetNames = p.scopeName; form.targetGrades = [p.grade] } }">
            <el-option v-for="paper in papers" :key="paper.id" :label="paper.title" :value="paper.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="测评名称" required class="span-2"><el-input v-model="form.title" /></el-form-item>
        <el-form-item label="发布层级"><el-input v-model="form.targetType" disabled /></el-form-item>
        <el-form-item label="目标名称"><el-input v-model="form.targetNames" /></el-form-item>
        <el-form-item label="开始时间"><el-date-picker v-model="form.startTime" type="datetime" value-format="YYYY-MM-DDTHH:mm:ssZ" /></el-form-item>
        <el-form-item label="结束时间"><el-date-picker v-model="form.endTime" type="datetime" value-format="YYYY-MM-DDTHH:mm:ssZ" /></el-form-item>
        <el-form-item label="允许作答次数"><el-input-number v-model="form.attemptLimit" :min="1" :max="10" /></el-form-item>
        <el-form-item label="答案展示"><el-select v-model="form.showAnswerMode"><el-option label="不展示" value="never" /><el-option label="交卷后" value="after_submit" /><el-option label="测评结束后" value="after_end" /></el-select></el-form-item>
        <el-form-item label="测评说明" class="span-2"><el-input v-model="form.instructions" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogOpen = false">取消</el-button><el-button type="primary" @click="publish">确认发布</el-button></template>
    </el-dialog>
  </div>
</template>
