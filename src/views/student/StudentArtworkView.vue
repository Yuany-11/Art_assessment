<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Headset, Plus, UploadFilled, View } from '@element-plus/icons-vue'
import AudioTagCard from '@/components/AudioTagCard.vue'
import { api } from '@/api'
import type { AudioTags, StudentArtwork, Subject } from '@/types'

const artworks = ref<StudentArtwork[]>([])
const loading = ref(false)
const subject = ref<Subject>('art')
const uploading = ref(false)
const dragActive = ref(false)
const fileInput = ref<HTMLInputElement>()
const previewOpen = ref(false)
const previewUrl = ref('')
const previewIsAudio = ref(false)
const visibleArtworks = computed(() => artworks.value.filter((item) => item.subject === subject.value))
const accept = computed(() => (subject.value === 'music' ? 'audio/*,.mp3,.wav,.m4a,.ogg' : 'image/*'))
const kindLabel = computed(() => (subject.value === 'music' ? '音频' : '图片'))
const kindTip = computed(() => (subject.value === 'music' ? 'MP3 / WAV / M4A / OGG' : 'JPG / PNG / WEBP'))
const MAX_SIZE = 20 * 1024 * 1024

function isAudio(item: StudentArtwork) {
  return (item.mimeType ?? '').startsWith('audio/') || /\.(mp3|wav|m4a|ogg|webm)$/i.test(item.fileName)
}

function onAnalyzed(item: StudentArtwork, tags: AudioTags) {
  item.audioTags = tags
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

function validate(file: File): boolean {
  if (subject.value === 'music') {
    const ok = file.type.startsWith('audio/') || /\.(mp3|wav|m4a|ogg|webm)$/i.test(file.name)
    if (!ok) {
      ElMessage.warning('音乐作品请上传 MP3 / WAV / M4A / OGG 音频文件')
      return false
    }
  } else if (!file.type.startsWith('image/') && !/\.(jpg|jpeg|png|webp)$/i.test(file.name)) {
    ElMessage.warning('美术作品请上传 JPG / PNG / WEBP 图片文件')
    return false
  }
  if (file.size > MAX_SIZE) {
    ElMessage.warning('单个文件不能超过 20 MB')
    return false
  }
  return true
}

async function handleFile(file: File | undefined | null) {
  if (!file || uploading.value) return
  if (!validate(file)) return
  uploading.value = true
  try {
    await api.artworks.upload(file, subject.value)
    ElMessage.success(`${kindLabel.value}作品已上传`)
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    uploading.value = false
  }
}

async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  await handleFile(input.files?.[0])
  input.value = ''
}

function onDragOver(event: DragEvent) {
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
  dragActive.value = true
}

function onDragLeave(event: DragEvent) {
  const zone = event.currentTarget as HTMLElement
  if (event.relatedTarget instanceof Node && zone.contains(event.relatedTarget)) return
  dragActive.value = false
}

async function onDrop(event: DragEvent) {
  dragActive.value = false
  await handleFile(event.dataTransfer?.files?.[0])
}

function preview(item: StudentArtwork) {
  previewUrl.value = item.preview
  previewIsAudio.value = isAudio(item)
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
    <div class="mobile-title"><p>MY ARTWORK</p><h2>课外学习作品</h2><span>上传日常创作（图片或音频），作为学习记录和教师评分材料。</span></div>
    <div class="filter-bar">
      <el-radio-group v-model="subject"><el-radio-button value="music">音乐作品</el-radio-button><el-radio-button value="art">美术作品</el-radio-button></el-radio-group>
      <el-button type="primary" :icon="Plus" :loading="uploading" @click="fileInput?.click()">上传{{ kindLabel }}作品</el-button>
      <input ref="fileInput" class="hidden-input" type="file" :accept="accept" @change="upload" />
    </div>
    <section
      class="artwork-dropzone"
      :class="{ 'is-active': dragActive, 'is-uploading': uploading }"
      @click="fileInput?.click()"
      @dragover.prevent="onDragOver"
      @dragenter.prevent="onDragOver"
      @dragleave.prevent="onDragLeave"
      @drop.prevent="onDrop"
    >
      <el-icon class="dropzone-icon"><UploadFilled /></el-icon>
      <div>
        <b>{{ dragActive ? `松开即可上传${kindLabel}作品` : `拖拽${kindLabel}作品到这里上传` }}</b>
        <span>或点击选择文件 · 支持 {{ kindTip }} · 单个文件不超过 20 MB</span>
      </div>
    </section>
    <section v-loading="loading" class="artwork-grid">
      <article v-for="item in visibleArtworks" :key="item.id" class="artwork-card">
        <div v-if="isAudio(item)" class="artwork-audio">
          <el-icon><Headset /></el-icon>
          <audio :src="item.preview" preload="metadata" controls></audio>
        </div>
        <img v-else :src="item.preview" :alt="item.fileName" />
        <div>
          <h3>{{ item.fileName }}</h3>
          <p>{{ item.uploadedAt.replace('T', ' ').slice(0, 16) }}</p>
          <span :class="item.status === 'reviewed' ? 'status-tag status-tag--success' : 'status-tag status-tag--warning'">{{ item.status === 'reviewed' ? `教师评分 ${item.score ?? 0} 分` : '等待查看' }}</span>
          <p v-if="item.comment" class="artwork-comment">教师评语：{{ item.comment }}</p>
        </div>
        <AudioTagCard
          v-if="isAudio(item)"
          :tags="item.audioTags"
          :file-id="item.id"
          title="作品音频标签"
          @analyzed="(tags) => onAnalyzed(item, tags)"
        />
        <div class="artwork-actions"><el-button link :icon="isAudio(item) ? Headset : View" @click="preview(item)">{{ isAudio(item) ? '播放' : '预览' }}</el-button><el-button link type="danger" @click="remove(item)">删除</el-button></div>
      </article>
    </section>
    <section v-if="!visibleArtworks.length && !loading" class="student-card empty-card">当前分类还没有上传作品，拖拽{{ kindLabel }}文件到上方区域即可上传。</section>
    <el-dialog v-model="previewOpen" :title="previewIsAudio ? '音频作品播放' : '作品预览'" width="min(760px, 92vw)">
      <audio v-if="previewIsAudio" class="artwork-audio-player" :src="previewUrl" controls autoplay></audio>
      <img v-else class="artwork-preview" :src="previewUrl" alt="学生作品预览" />
    </el-dialog>
  </div>
</template>
