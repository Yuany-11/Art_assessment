<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Reading } from '@element-plus/icons-vue'
import { api } from '@/api'
import type { Chapter, Course, Subject } from '@/types'

const router = useRouter()
const loading = ref(false)
const courses = ref<Course[]>([])
const chapters = ref<Record<number, Chapter[]>>({})
const expanded = ref<number[]>([])
const subject = ref<Subject>('music')
const activeChapter = ref<Chapter | null>(null)
const drawerOpen = ref(false)
const starting = ref(false)

async function load() {
  loading.value = true
  try {
    const result = await api.courses.list({ subject: subject.value, pageSize: 100 })
    courses.value = result.list
    const entries = await Promise.all(result.list.map(async (course) => [course.id, await api.courses.chapters(course.id)] as const))
    chapters.value = Object.fromEntries(entries)
    expanded.value = result.list[0] ? [result.list[0].id] : []
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

function toggle(id: number) {
  expanded.value = expanded.value.includes(id) ? expanded.value.filter((item) => item !== id) : [...expanded.value, id]
}

function openChapter(chapter: Chapter) {
  activeChapter.value = chapter
  drawerOpen.value = true
}

async function startChapterPractice() {
  if (!activeChapter.value) return
  starting.value = true
  try {
    const attempt = await api.attempts.startPractice(subject.value, activeChapter.value.id)
    drawerOpen.value = false
    router.push(`/student/attempt/${attempt.attemptId}`)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    starting.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="student-page stack">
    <div class="mobile-title"><p>ART CLASSROOM</p><h2>趣味课堂</h2><span>浏览音乐与美术课程，读知识讲解，做本章练习。</span></div>
    <div class="filter-bar"><el-radio-group v-model="subject" @change="load"><el-radio-button value="music">音乐课堂</el-radio-button><el-radio-button value="art">美术课堂</el-radio-button></el-radio-group></div>
    <section v-loading="loading" class="knowledge-list">
      <article v-for="course in courses" :key="course.id" class="knowledge-card">
        <button class="knowledge-head" @click="toggle(course.id)">
          <div class="knowledge-icon"><el-icon><Reading /></el-icon></div>
          <div><span>{{ course.subject === 'music' ? '音乐' : '美术' }} · 适用 {{ course.grade }} 年级</span><h3>{{ course.name }}</h3><p>{{ course.description || '探索本课程的趣味知识。' }}</p></div>
          <strong>{{ expanded.includes(course.id) ? '−' : '+' }}</strong>
        </button>
        <div v-if="expanded.includes(course.id)" class="knowledge-chapters">
          <div v-for="(chapter, index) in chapters[course.id] || []" :key="chapter.id" class="knowledge-chapter" @click="openChapter(chapter)">
            <b>{{ String(index + 1).padStart(2, '0') }}</b>
            <div><h4>{{ chapter.name }}</h4><p>{{ chapter.description || '点击查看知识讲解并做本章练习。' }}</p></div>
            <span>{{ chapter.questionCount }} 道练习 ›</span>
          </div>
          <p v-if="!(chapters[course.id] || []).length" class="muted">课程章节内容正在准备中。</p>
        </div>
      </article>
    </section>
    <section v-if="!courses.length && !loading" class="student-card empty-card">当前学科暂无已发布课程。</section>

    <el-drawer v-model="drawerOpen" :title="activeChapter?.name" size="min(560px, 92vw)">
      <div v-if="activeChapter" class="chapter-detail">
        <p class="chapter-detail-meta">{{ activeChapter.courseName }} · {{ activeChapter.questionCount }} 道练习</p>
        <p v-if="activeChapter.description" class="chapter-detail-summary">{{ activeChapter.description }}</p>
        <div v-if="activeChapter.content" class="chapter-detail-body">{{ activeChapter.content }}</div>
        <p v-else class="muted">本章知识讲解正在整理中，可以先做本章练习。</p>
        <el-button type="primary" :loading="starting" @click="startChapterPractice">开始本章练习（10 题）</el-button>
        <p class="chapter-detail-tip">练习由本章题库随机抽取：6 道单选、3 道多选、1 道实践题，提交后立即出分，不计入正式测评。</p>
      </div>
    </el-drawer>
  </div>
</template>
