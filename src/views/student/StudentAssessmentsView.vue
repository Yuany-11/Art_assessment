<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import StatusTag from '@/components/StatusTag.vue'
import { api } from '@/api'
import type { Assessment, SchoolClass } from '@/types'

const router = useRouter()
const assessments = ref<Assessment[]>([])
const loading = ref(false)
const filters = reactive({ subject: '', paperType: '', keyword: '' })
const classCode = ref('')
const classInfo = ref<SchoolClass | null>(null)

async function load() {
  loading.value = true
  try {
    const result = await api.assessments.list({ status: 'published', subject: filters.subject, paperType: filters.paperType, keyword: filters.keyword, pageSize: 50 })
    assessments.value = result.list
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function searchClass() {
  if (classCode.value.trim() !== 'C20260701') {
    ElMessage.warning('演示班级号：C20260701')
    return
  }
  const found = await api.classes.search(classCode.value.trim())
  if (!found) {
    ElMessage.warning('未找到该班级')
    return
  }
  classInfo.value = found
  await load()
}

async function start(row: Assessment) {
  try {
    const attempt = await api.attempts.start(row.id)
    router.push(`/student/attempt/${attempt.attemptId}`)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function startPractice(subject: 'music' | 'art') {
  try {
    const attempt = await api.attempts.startPractice(subject)
    router.push(`/student/attempt/${attempt.attemptId}`)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

onMounted(load)
</script>

<template>
  <div class="student-page stack">
    <div class="mobile-title"><p>ASSESSMENT</p><h2>我的测评</h2><span>请在规定时间内完成，答案会自动保存。</span></div>
    <div class="practice-actions">
      <el-button type="primary" plain @click="startPractice('music')">随机音乐练习</el-button>
      <el-button type="primary" plain @click="startPractice('art')">随机美术练习</el-button>
    </div>
    <div class="filter-bar">
      <el-radio-group v-model="filters.subject" @change="load"><el-radio-button value="">全部</el-radio-button><el-radio-button value="music">音乐</el-radio-button><el-radio-button value="art">美术</el-radio-button></el-radio-group>
      <el-select v-model="filters.paperType" clearable placeholder="测评类型" @change="load"><el-option label="正式测评" value="formal" /><el-option label="练习测评" value="practice" /></el-select>
      <el-input v-model="filters.keyword" clearable placeholder="按测评名称搜索" @keyup.enter="load" />
      <el-input v-model="classCode" clearable placeholder="按班级号搜索" @keyup.enter="searchClass" />
      <el-button @click="searchClass">班级查询</el-button>
    </div>
    <div v-if="classInfo" class="assessment-class-banner"><b>{{ classInfo.name }}</b><span>{{ classInfo.classCode }} · 班主任 {{ classInfo.headTeacherName }} · 当前可见该班测评</span></div>
    <section v-loading="loading" class="assessment-cards">
      <article v-for="item in assessments" :key="item.id" class="assessment-card">
        <div class="assessment-cover" :class="item.subject"><span>{{ item.subject === 'music' ? '♫' : '◐' }}</span><StatusTag :value="item.status" /></div>
        <div class="assessment-body">
          <small>{{ item.subject === 'music' ? '音乐' : '美术' }} · {{ item.targetGrades[0] || item.grade }} 年级</small>
          <h3>{{ item.title }}</h3>
          <p>{{ item.instructions || '按题目要求完成测评。' }}</p>
          <div class="assessment-meta"><span>{{ item.duration }} 分钟</span><span>{{ item.paperType === 'formal' ? '正式测评' : '练习' }}</span><span>最多 {{ item.attemptLimit }} 次</span></div>
          <el-button type="primary" class="full-button" @click="start(item)">进入测评</el-button>
        </div>
      </article>
    </section>
    <section v-if="!assessments.length && !loading" class="student-card empty-card">暂无符合条件且正在进行中的测评。</section>
  </div>
</template>
