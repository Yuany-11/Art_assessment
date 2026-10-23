<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Upload } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import { api } from '@/api'
import type { Question, Subject } from '@/types'

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
const form = reactive({ subject: 'music' as Subject, grade: 7, courseId: 6001, chapterId: '', type: 'single_choice', difficulty: 2, stem: '', score: 5, publishNow: true })

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

function openCreate() {
  editing.value = null
  Object.assign(form, { subject: 'music', grade: 7, courseId: 6001, chapterId: '', type: 'single_choice', difficulty: 2, stem: '', score: 5, publishNow: true })
  dialogOpen.value = true
}

function openEdit(row: Question) {
  editing.value = row
  Object.assign(form, { subject: row.subject, grade: row.grade, courseId: row.courseId, chapterId: row.chapterId || '', type: row.type, difficulty: row.difficulty, stem: row.stem, score: row.score, publishNow: row.status === 'approved' })
  dialogOpen.value = true
}

async function save() {
  if (!form.stem.trim()) {
    ElMessage.warning('请填写题干')
    return
  }
  try {
    if (editing.value) {
      await api.questions.update(editing.value.id, { ...form, chapterId: form.chapterId ? Number(form.chapterId) : null })
      ElMessage.success('试题已更新')
    } else {
      await api.questions.create({ ...form })
      ElMessage.success(form.publishNow ? '试题已创建并发布' : '试题已提交审核')
    }
    dialogOpen.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

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
  await api.questions.update(current.value.id, { resourceCount: 0 })
  ElMessage.success('试题资源已删除')
  resourceOpen.value = false
  await load()
}

onMounted(load)
</script>

<template>
  <div class="stack">
    <PageHeader title="试题管理" description="维护公共题库与教师提交试题，完成审核和音视频资源关联。">
      <el-button type="primary" :icon="Plus" @click="openCreate">创建试题</el-button>
    </PageHeader>
    <section class="panel">
      <div class="filter-bar">
        <el-input v-model="filters.keyword" :prefix-icon="Search" clearable placeholder="题干关键词" />
        <el-select v-model="filters.subject" clearable placeholder="学科"><el-option label="音乐" value="music" /><el-option label="美术" value="art" /></el-select>
        <el-select v-model="filters.status" clearable placeholder="状态"><el-option label="待审核" value="pending" /><el-option label="已通过" value="approved" /><el-option label="已驳回" value="rejected" /></el-select>
        <el-select v-model="filters.type" clearable placeholder="题型"><el-option label="单选" value="single_choice" /><el-option label="简答" value="short_answer" /><el-option label="图片作品" value="image_upload" /></el-select>
        <el-select v-model="filters.difficulty" clearable placeholder="难度"><el-option v-for="d in 5" :key="d" :label="`难度 ${d}`" :value="String(d)" /></el-select>
        <el-button type="primary" @click="pageNum = 1; load()">查询</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" row-key="id" stripe>
        <el-table-column prop="id" label="编号" width="90" />
        <el-table-column prop="stem" label="题干" min-width="280" show-overflow-tooltip />
        <el-table-column prop="subject" label="学科" width="80"><template #default="{ row }">{{ row.subject === 'music' ? '音乐' : '美术' }}</template></el-table-column>
        <el-table-column prop="grade" label="年级" width="70" />
        <el-table-column prop="type" label="题型" width="120" />
        <el-table-column prop="difficulty" label="难度" width="70" />
        <el-table-column prop="score" label="分值" width="70" />
        <el-table-column prop="resourceCount" label="资源" width="70" />
        <el-table-column label="状态" width="100"><template #default="{ row }"><StatusTag :value="row.status" /></template></el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="row.status === 'pending'" link @click="openReview(row, 'approve')">通过</el-button>
            <el-button v-if="row.status === 'pending'" link type="warning" @click="openReview(row, 'reject')">驳回</el-button>
            <el-button link @click="openResources(row)">资源</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="table-footer"><span>共 {{ total }} 道试题</span><el-pagination v-model:current-page="pageNum" v-model:page-size="pageSize" :total="total" layout="prev, pager, next" @change="load" /></div>
    </section>

    <el-dialog v-model="dialogOpen" :title="editing ? '修改试题' : '创建试题'" width="720px">
      <el-form label-position="top" class="form-grid">
        <el-form-item label="学科"><el-select v-model="form.subject"><el-option label="音乐" value="music" /><el-option label="美术" value="art" /></el-select></el-form-item>
        <el-form-item label="年级"><el-select v-model="form.grade"><el-option v-for="g in 12" :key="g" :label="`${g} 年级`" :value="g" /></el-select></el-form-item>
        <el-form-item label="课程 ID"><el-input-number v-model="form.courseId" :min="1" /></el-form-item>
        <el-form-item label="章节 ID"><el-input v-model="form.chapterId" placeholder="可不填" /></el-form-item>
        <el-form-item label="题型"><el-select v-model="form.type"><el-option label="单选题" value="single_choice" /><el-option label="简答题" value="short_answer" /><el-option label="图片作品" value="image_upload" /><el-option label="音频作品" value="audio_upload" /></el-select></el-form-item>
        <el-form-item label="难度"><el-select v-model="form.difficulty"><el-option v-for="d in 5" :key="d" :label="`难度 ${d}`" :value="d" /></el-select></el-form-item>
        <el-form-item label="默认分值"><el-input-number v-model="form.score" :min="0.5" :max="100" :step="0.5" /></el-form-item>
        <el-form-item label="创建后立即发布"><el-switch v-model="form.publishNow" /></el-form-item>
        <el-form-item label="题干" required class="span-2"><el-input v-model="form.stem" type="textarea" :rows="5" /></el-form-item>
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
