<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, ZoomIn } from '@element-plus/icons-vue'
import { api } from '@/api'
import { isAudioFile, isImageFile } from '@/utils/media'
import type { StudentArtwork, Subject } from '@/types'

const artworks = ref<StudentArtwork[]>([])
const loading = ref(false)
const subject = ref<Subject>('art')
const uploading = ref(false)
const fileInput = ref<HTMLInputElement>()
const previewOpen = ref(false)
const previewItem = ref<StudentArtwork | null>(null)
const accept = computed(() => (subject.value === 'music' ? 'audio/*' : 'image/*'))
const visibleArtworks = computed(() => artworks.value.filter((item) => item.subject === subject.value))

function isAudio(item: StudentArtwork) {
  return isAudioFile(item.fileName, item.mimeType)
}

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
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const music = subject.value === 'music'
  const matched = music ? isAudioFile(file.name, file.type) : isImageFile(file.name, file.type)
  if (!matched) {
    ElMessage.warning(music ? '请选择 MP3、WAV、M4A、WEBM 或 OGG 音频文件' : '请选择 JPG、PNG 或 WEBP 图片文件')
    input.value = ''
    return
  }
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.warning(`${music ? '音频' : '图片'}不能超过 10 MB`)
    input.value = ''
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
    input.value = ''
  }
}

function preview(item: StudentArtwork) {
  previewItem.value = item
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
      <input ref="fileInput" class="hidden-input" type="file" :accept="accept" @change="upload" />
    </div>
    <section v-loading="loading" class="artwork-grid">
      <article v-for="item in visibleArtworks" :key="item.id" class="artwork-card">
        <figure v-if="isAudio(item)" class="artwork-audio-box">
          <audio :src="item.preview" controls preload="none" class="artwork-audio"></audio>
        </figure>
        <img v-else :src="item.preview" :alt="item.fileName" />
        <div>
          <h3>{{ item.fileName }}</h3>
          <p>{{ item.uploadedAt.replace('T', ' ').slice(0, 16) }}</p>
          <span :class="item.status === 'reviewed' ? 'status-tag status-tag--success' : 'status-tag status-tag--warning'">{{ item.status === 'reviewed' ? '教师已查看' : '等待查看' }}</span>
        </div>
        <div class="artwork-actions"><el-button link :icon="ZoomIn" @click="preview(item)">预览</el-button><el-button link type="danger" @click="remove(item)">删除</el-button></div>
      </article>
    </section>
    <section v-if="!visibleArtworks.length && !loading" class="student-card empty-card">当前分类还没有上传作品，点击右上角上传第一个。</section>
    <el-dialog v-model="previewOpen" title="作品预览" width="min(760px, 92vw)">
      <figure v-if="previewItem && isAudio(previewItem)" class="artwork-preview-audio-box">
        <audio :src="previewItem.preview" controls class="artwork-preview-audio"></audio>
      </figure>
      <img v-else-if="previewItem" class="artwork-preview" :src="previewItem.preview" :alt="previewItem.fileName" />
    </el-dialog>
  </div>
</template>
