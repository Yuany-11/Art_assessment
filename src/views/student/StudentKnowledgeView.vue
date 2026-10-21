<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Reading } from '@element-plus/icons-vue'
import { api } from '@/api'
import type { Chapter, Course, Subject } from '@/types'

const loading = ref(false)
const courses = ref<Course[]>([])
const chapters = ref<Record<number, Chapter[]>>({})
const expanded = ref<number[]>([])
const subject = ref<Subject>('music')

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

onMounted(load)
</script>

<template>
  <div class="student-page stack">
    <div class="mobile-title"><p>ART CLASSROOM</p><h2>趣味课堂</h2><span>浏览音乐与美术课程，发现课堂知识点。</span></div>
    <div class="filter-bar"><el-radio-group v-model="subject" @change="load"><el-radio-button value="music">音乐课堂</el-radio-button><el-radio-button value="art">美术课堂</el-radio-button></el-radio-group></div>
    <section v-loading="loading" class="knowledge-list">
      <article v-for="course in courses" :key="course.id" class="knowledge-card">
        <button class="knowledge-head" @click="toggle(course.id)">
          <div class="knowledge-icon"><el-icon><Reading /></el-icon></div>
          <div><span>{{ course.subject === 'music' ? '音乐' : '美术' }} · {{ course.grade }} 年级</span><h3>{{ course.name }}</h3><p>{{ course.description || '探索本课程的趣味知识。' }}</p></div>
          <strong>{{ expanded.includes(course.id) ? '−' : '+' }}</strong>
        </button>
        <div v-if="expanded.includes(course.id)" class="knowledge-chapters">
          <div v-for="(chapter, index) in chapters[course.id] || []" :key="chapter.id">
            <b>{{ String(index + 1).padStart(2, '0') }}</b>
            <div><h4>{{ chapter.name }}</h4><p>{{ chapter.description || '进入章节学习相关知识。' }}</p></div>
            <span>{{ chapter.questionCount }} 道练习</span>
          </div>
          <p v-if="!(chapters[course.id] || []).length" class="muted">课程章节内容正在准备中。</p>
        </div>
      </article>
    </section>
    <section v-if="!courses.length && !loading" class="student-card empty-card">当前学科暂无已发布课程。</section>
  </div>
</template>
