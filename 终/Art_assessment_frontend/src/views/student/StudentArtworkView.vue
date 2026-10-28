<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, ZoomIn } from '@element-plus/icons-vue'
import { api } from '@/api'
import type { StudentArtwork, Subject } from '@/types'

const artworks = ref<StudentArtwork[]>([])
const loading = ref(false)
const subject = ref<Subject>('art')
const uploading = ref(false)
const fileInput = ref<HTMLInputElement>()
const previewOpen = ref(false)
const previewUrl = ref('')
const visibleArtworks = computed(() => artworks.value.filter((item) => item.subject === subject.value))

async function load() {
  loading.value = true
  try {
    artworks.value = await api.artworks.list()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function upload(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.warning('图片不能超过 10 MB')
    return
  }
  uploading.value = true
  try {
    await api.artworks.upload(file, subject.value)
    ElMessage.success('作品已上传')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    uploading.value = false
    ;(event.target as HTMLInputElement).value = ''
  }
}

function preview(item: StudentArtwork) {
  previewUrl.value = item.preview
  previewOpen.value = true
}

async function remove(item: StudentArtwork) {
  try {
    await ElMessageBox.confirm(`删除作品“${item.fileName}”？`, '删除作品', { type: 'warning' })
    await api.artworks.remove(item.id)
    ElMessage.success('作品已删除')
    await load()
  } catch (error) {
    if (error instanceof Error) ElMessage.error(error.message)
  }
}

onMounted(load)
</script>

<template>
  <div class="student-page stack">
    <div class="mobile-title"><p>MY ARTWORK</p><h2>课外学习作品</h2><span>上传日常创作，作为学习记录和教师评分材料。</span></div>
    <div class="filter-bar">
      <el-radio-group v-model="subject"><el-radio-button value="music">音乐作品</el-radio-button><el-radio-button value="art">美术作品</el-radio-button></el-radio-group>
      <el-button type="primary" :icon="Plus" :loading="uploading" @click="fileInput?.click()">上传作品</el-button>
      <input ref="fileInput" class="hidden-input" type="file" accept="image/*" @change="upload" />
    </div>
    <section v-loading="loading" class="artwork-grid">
      <article v-for="item in visibleArtworks" :key="item.id" class="artwork-card">
        <img :src="item.preview" :alt="item.fileName" />
        <div>
          <h3>{{ item.fileName }}</h3>
          <p>{{ item.uploadedAt.replace('T', ' ').slice(0, 16) }}</p>
          <span :class="item.status === 'reviewed' ? 'status-tag status-tag--success' : 'status-tag status-tag--warning'">{{ item.status === 'reviewed' ? '教师已查看' : '等待查看' }}</span>
        </div>
        <div class="artwork-actions"><el-button link :icon="ZoomIn" @click="preview(item)">预览</el-button><el-button link type="danger" @click="remove(item)">删除</el-button></div>
      </article>
    </section>
    <section v-if="!visibleArtworks.length && !loading" class="student-card empty-card">当前分类还没有上传作品，点击右上角上传第一张。</section>
    <el-dialog v-model="previewOpen" title="作品预览" width="min(760px, 92vw)">
      <img class="artwork-preview" :src="previewUrl" alt="学生作品预览" />
    </el-dialog>
  </div>
</template>
