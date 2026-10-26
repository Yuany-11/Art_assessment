<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Plus, Search } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import { api } from '@/api'
import { saveBlob } from '@/api/client'
import type { Certificate, Subject } from '@/types'

const rows = ref<Certificate[]>([])
const loading = ref(false)
const keyword = ref('')
const subject = ref<Subject>('music')
const detailOpen = ref(false)
const editOpen = ref(false)
const selected = ref<Certificate | null>(null)
const editing = ref<Certificate | null>(null)
const editForm = reactive({ certificateNo: '', score: 0, level: '合格', issueDate: '', status: 'ready' as Certificate['status'] })
const levelLabels: Record<string, string> = { excellent: '优秀', good: '良好', pass: '合格', fail: '待提升' }
const visibleRows = computed(() => rows.value.filter((item) => item.subject === subject.value && (!keyword.value || `${item.studentName} ${item.certificateNo} ${item.assessmentTitle}`.includes(keyword.value))))

async function load() {
  loading.value = true
  try {
    rows.value = await api.certificates.list()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function generate() {
  try {
    const result = await ElMessageBox.confirm('为已完成判分的学生生成证书？', '批量生成证书', { type: 'info' })
    if (result) {
      const task = await api.certificates.generate(12001, subject.value)
      ElMessage.success(`证书任务 ${task.taskId} 已提交，稍后刷新查看状态`)
      await load()
    }
  } catch (error) {
    if (error instanceof Error) ElMessage.error(error.message)
  }
}

async function detail(row: Certificate) {
  try {
    selected.value = await api.certificates.detail(row.id)
    detailOpen.value = true
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function openEdit(row: Certificate) {
  editing.value = row
  Object.assign(editForm, {
    certificateNo: row.certificateNo,
    score: row.score,
    level: row.level,
    issueDate: row.issueDate,
    status: row.status
  })
  editOpen.value = true
}

async function saveEdit() {
  if (!editing.value) return
  if (!editForm.certificateNo.trim()) return ElMessage.warning('证书编号不能为空')
  if (editForm.score < 0 || editForm.score > 100) return ElMessage.warning('成绩应在 0 到 100 分之间')
  if (!editForm.issueDate) return ElMessage.warning('请选择发证日期')
  try {
    await api.certificates.update(editing.value.id, {
      certificateNo: editForm.certificateNo.trim(),
      score: editForm.score,
      level: editForm.level,
      issueDate: editForm.issueDate,
      status: editForm.status
    })
    editOpen.value = false
    await load()
    ElMessage.success('证书信息已更新')
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function download(row: Certificate) {
  try {
    const blob = await api.certificates.download(row.id)
    saveBlob(blob, `${row.certificateNo}.pdf`)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

onMounted(load)
</script>

<template>
  <div class="stack">
    <PageHeader title="学生证书管理" description="查看、生成、修改和下载权限范围内学生的测评证书。">
      <el-button type="primary" :icon="Plus" @click="generate">生成测评证书</el-button>
    </PageHeader>
    <section class="panel">
      <div class="filter-bar">
        <el-input v-model="keyword" :prefix-icon="Search" clearable placeholder="学生、证书编号或测评" />
        <el-radio-group v-model="subject"><el-radio-button value="music">音乐</el-radio-button><el-radio-button value="art">美术</el-radio-button></el-radio-group>
        <el-button type="primary" @click="load">刷新</el-button>
      </div>
      <el-table v-loading="loading" :data="visibleRows" row-key="id" stripe empty-text="暂无证书数据">
        <el-table-column prop="certificateNo" label="证书编号" min-width="190" />
        <el-table-column prop="studentName" label="学生" width="110" />
        <el-table-column prop="assessmentTitle" label="测评" min-width="220" />
        <el-table-column prop="score" label="成绩" width="80" />
        <el-table-column prop="level" label="等级" width="90" />
        <el-table-column prop="issueDate" label="发证日期" width="120" />
        <el-table-column label="状态" width="100"><template #default="{ row }"><StatusTag :value="row.status" /></template></el-table-column>
        <el-table-column label="操作" width="200"><template #default="{ row }"><el-button link type="primary" @click="detail(row)">查看</el-button><el-button link @click="openEdit(row)">修改</el-button><el-button link :icon="Download" :disabled="row.status !== 'ready'" @click="download(row)">下载</el-button></template></el-table-column>
      </el-table>
    </section>
    <el-drawer v-model="detailOpen" title="证书详情" size="480px">
      <div v-if="selected" class="certificate-detail">
        <div class="certificate-seal">艺</div>
        <span>艺术素质测评证书</span>
        <h2>{{ selected.studentName }}</h2>
        <p>{{ selected.assessmentTitle }}</p>
        <strong>{{ selected.score }} 分 · {{ levelLabels[selected.level] ?? selected.level }}</strong>
        <small>{{ selected.certificateNo }}</small>
        <el-button @click="openEdit(selected)">修改证书信息</el-button>
        <el-button type="primary" :disabled="selected.status !== 'ready'" @click="download(selected)">下载证书</el-button>
      </div>
    </el-drawer>
    <el-dialog v-model="editOpen" title="修改证书信息" width="520px">
      <el-form label-position="top">
        <el-form-item label="证书编号" required><el-input v-model="editForm.certificateNo" /></el-form-item>
        <el-form-item label="成绩" required><el-input-number v-model="editForm.score" :min="0" :max="100" :precision="0" /></el-form-item>
        <el-form-item label="等级">
          <el-select v-model="editForm.level"><el-option v-for="label in ['优秀', '良好', '合格', '待提升']" :key="label" :label="label" :value="label" /></el-select>
        </el-form-item>
        <el-form-item label="发证日期" required><el-date-picker v-model="editForm.issueDate" type="date" value-format="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="证书状态">
          <el-select v-model="editForm.status"><el-option label="可下载" value="ready" /><el-option label="生成中" value="generating" /><el-option label="生成失败" value="failed" /></el-select>
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="editOpen = false">取消</el-button><el-button type="primary" @click="saveEdit">保存修改</el-button></template>
    </el-dialog>
  </div>
</template>
