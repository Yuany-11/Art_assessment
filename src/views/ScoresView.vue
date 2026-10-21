<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Plus, Search, UploadFilled } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import { api } from '@/api'
import { saveBlob } from '@/api/client'
import type { Score } from '@/types'

const loading = ref(false)
const rows = ref<Score[]>([])
const total = ref(0)
const pageNum = ref(1)
const pageSize = ref(10)
const filters = reactive({ subject: '', keyword: '' })
const manualOpen = ref(false)
const importResult = ref<Record<string, unknown> | null>(null)
const importInput = ref<HTMLInputElement>()
const form = reactive({ studentName: '', studentNo: '', className: '', assessmentId: 12001, subject: 'music', totalScore: 60, reason: '' })
const levelLabels: Record<string, string> = { excellent: '优秀', good: '良好', pass: '合格', fail: '待提升' }

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
  Object.assign(form, { studentName: '', studentNo: '', className: '', assessmentId: 12001, subject: 'music', totalScore: 60, reason: '' })
  manualOpen.value = true
}

async function saveManual() {
  if (!form.studentNo || !form.reason.trim()) {
    ElMessage.warning('请填写学籍号和补录原因')
    return
  }
  try {
    await api.scores.manual({ ...form })
    manualOpen.value = false
    ElMessage.success('成绩补录成功')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function importFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    importResult.value = await api.scores.import(file)
    ElMessage.success('导入处理完成')
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
  ;(event.target as HTMLInputElement).value = ''
}

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

onMounted(load)
</script>

<template>
  <div class="stack">
    <PageHeader title="成绩管理" description="按权限范围查询、补录、导入和导出学生测评成绩。">
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
        <el-table-column label="操作" width="100"><template #default="{ row }"><el-button link type="primary" @click="showDetail(row)">详情</el-button></template></el-table-column>
      </el-table>
      <div class="table-footer"><span>共 {{ total }} 条成绩</span><el-pagination v-model:current-page="pageNum" v-model:page-size="pageSize" :total="total" layout="prev, pager, next" @change="load" /></div>
    </section>

    <el-dialog v-model="manualOpen" title="成绩补录" width="620px">
      <el-form label-position="top" class="form-grid">
        <el-form-item label="学籍号" required><el-input v-model="form.studentNo" /></el-form-item>
        <el-form-item label="学生姓名"><el-input v-model="form.studentName" /></el-form-item>
        <el-form-item label="班级"><el-input v-model="form.className" /></el-form-item>
        <el-form-item label="学科"><el-select v-model="form.subject"><el-option label="音乐" value="music" /><el-option label="美术" value="art" /></el-select></el-form-item>
        <el-form-item label="补录总分"><el-input-number v-model="form.totalScore" :min="0" :max="100" /></el-form-item>
        <el-form-item label="补录原因" required class="span-2"><el-input v-model="form.reason" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="manualOpen = false">取消</el-button><el-button type="primary" @click="saveManual">确认补录</el-button></template>
    </el-dialog>

    <el-dialog :model-value="Boolean(importResult)" title="导入结果" width="620px" @close="importResult = null">
      <template v-if="importResult">
        <div class="result-strip"><span>总行数 {{ importResult.total }}</span><b>成功 {{ importResult.successCount }}</b><b class="danger">失败 {{ importResult.failCount }}</b></div>
        <el-table :data="(importResult.errors as Array<Record<string, unknown>>) || []">
          <el-table-column prop="row" label="行号" width="80" /><el-table-column prop="studentNo" label="学籍号" /><el-table-column prop="message" label="失败原因" />
        </el-table>
      </template>
    </el-dialog>
  </div>
</template>
