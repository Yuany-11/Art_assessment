<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import StatusTag from '@/components/StatusTag.vue'
import { api } from '@/api'
import type { Assessment, SchoolClass } from '@/types'

const router = useRouter()
const assessments = ref<Assessment[]>([])
const loading = ref(false)
const filters = reactive({ subject: '', keyword: '' })
const classCode = ref('')
const classInfo = ref<SchoolClass | null>(null)
const formalAssessments = computed(() => assessments.value.filter((item) => item.paperType === 'formal'))
const practiceAssessments = computed(() => assessments.value.filter((item) => item.paperType === 'practice'))

async function load() {
  loading.value = true
  try {
    const result = await api.assessments.list({
      subject: filters.subject,
      keyword: filters.keyword,
      classCode: classCode.value.trim(),
      pageSize: 100
    })
    assessments.value = result.list
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function searchClass() {
  if (!classCode.value.trim()) {
    ElMessage.warning('请输入班级号')
    return
  }
  try {
    const found = await api.classes.search(classCode.value.trim())
    if (!found) {
      classInfo.value = null
      ElMessage.warning('未找到该班级，请核对班级号')
      return
    }
    classInfo.value = found
    await load()
    ElMessage.success(`已按班级号筛选：${found.name}`)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function resetQuery() {
  filters.subject = ''
  filters.keyword = ''
  classCode.value = ''
  classInfo.value = null
  pageNumReset()
}

function pageNumReset() {
  load()
}

function canEnter(item: Assessment) {
  return !item.isEnded && item.isStarted !== false
}

function entryLabel(item: Assessment) {
  if (item.isEnded) return '已结束'
  if (item.isStarted === false) return '未开始'
  return item.myAttempt?.status === 'in_progress' ? '继续作答' : item.paperType === 'practice' ? '进入练习' : '进入测评'
}

async function start(row: Assessment) {
  if (!canEnter(row)) {
    ElMessage.warning(row.isEnded ? '该测评已结束' : '该测评尚未开始')
    return
  }
  try {
    const attempt = await api.attempts.start(row.id)
    router.push(`/student/attempt/${attempt.attemptId}`)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function resumeText(item: Assessment) {
  if (item.myAttempt?.status !== 'in_progress') return ''
  const seconds = item.myAttempt.remainingSeconds ?? 0
  return seconds > 0 ? `第 ${item.myAttempt.attemptNo} 次作答 · 剩余 ${Math.ceil(seconds / 60)} 分钟` : '即将自动交卷'
}

function formatDateTime(value?: string | null) {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 16)
}

function openReview(attemptId: number) {
  router.push(`/student/attempt/${attemptId}/review`)
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
      <el-input v-model="filters.keyword" clearable placeholder="按测评名称搜索" @keyup.enter="load" />
      <el-input v-model="classCode" clearable placeholder="按班级号搜索" @keyup.enter="searchClass" />
      <el-button type="primary" @click="load">搜索</el-button>
      <el-button @click="searchClass">班级查询</el-button>
      <el-button @click="resetQuery">返回全部</el-button>
    </div>
    <div v-if="classInfo" class="assessment-class-banner"><b>{{ classInfo.name }}</b><span>{{ classInfo.classCode }} · 班主任 {{ classInfo.headTeacherName }}（{{ classInfo.headTeacherAccount || '账号待完善' }}，{{ classInfo.headTeacherPhone || '电话待完善' }}） · 当前已按该班筛选</span></div>

    <section class="student-card">
      <div class="student-section-head"><h3>正式测评</h3><span>{{ formalAssessments.length }} 场老师发布的正式测评</span></div>
      <div v-loading="loading" class="assessment-cards assessment-cards--embedded">
        <article v-for="item in formalAssessments" :key="item.id" class="assessment-card">
          <div class="assessment-cover" :class="item.subject"><span>{{ item.subject === 'music' ? '♫' : '◐' }}</span><StatusTag :value="item.status" /></div>
          <div class="assessment-body">
            <small>{{ item.subject === 'music' ? '音乐' : '美术' }} · {{ item.targetGrades[0] || item.grade }} 年级</small>
            <h3>{{ item.title }}</h3>
            <p>{{ item.instructions || '按题目要求完成测评。' }}</p>
            <div class="assessment-meta">
              <span>发布老师：{{ item.publisherName || '—' }}</span><span>截止：{{ formatDateTime(item.endTime) }}</span>
              <span>{{ item.duration }} 分钟</span><span>正式测评</span><span>最多 {{ item.attemptLimit }} 次</span>
              <span v-if="resumeText(item)" class="resume-note">{{ resumeText(item) }}</span>
            </div>
            <el-button type="primary" class="full-button" :disabled="!canEnter(item)" @click="start(item)">{{ entryLabel(item) }}</el-button>
            <el-button v-if="item.myAttempt && item.myAttempt.status !== 'in_progress'" plain class="full-button" @click="openReview(item.myAttempt.attemptId)">查看已交试卷</el-button>
          </div>
        </article>
      </div>
      <p v-if="!formalAssessments.length && !loading" class="muted">暂无符合条件的正式测评。</p>
    </section>

    <section class="student-card">
      <div class="student-section-head"><h3>练习测评</h3><span>{{ practiceAssessments.length }} 场老师发布的练习测评</span></div>
      <div v-loading="loading" class="assessment-cards assessment-cards--embedded">
        <article v-for="item in practiceAssessments" :key="item.id" class="assessment-card">
          <div class="assessment-cover" :class="item.subject"><span>{{ item.subject === 'music' ? '♫' : '◐' }}</span><StatusTag :value="item.status" /></div>
          <div class="assessment-body">
            <small>{{ item.subject === 'music' ? '音乐' : '美术' }} · {{ item.targetGrades[0] || item.grade }} 年级</small>
            <h3>{{ item.title }}</h3>
            <p>{{ item.instructions || '练习测评用于巩固本章知识。' }}</p>
            <div class="assessment-meta">
              <span>发布老师：{{ item.publisherName || '—' }}</span><span>截止：{{ formatDateTime(item.endTime) }}</span>
              <span>{{ item.duration }} 分钟</span><span>练习测评</span><span>最多 {{ item.attemptLimit }} 次</span>
              <span v-if="resumeText(item)" class="resume-note">{{ resumeText(item) }}</span>
            </div>
            <el-button type="primary" plain class="full-button" :disabled="!canEnter(item)" @click="start(item)">{{ entryLabel(item) }}</el-button>
            <el-button v-if="item.myAttempt && item.myAttempt.status !== 'in_progress'" plain class="full-button" @click="openReview(item.myAttempt.attemptId)">查看已交试卷</el-button>
          </div>
        </article>
      </div>
      <p v-if="!practiceAssessments.length && !loading" class="muted">暂无老师发布的练习测评；也可使用上方“随机音乐/美术练习”自主练习。</p>
    </section>
  </div>
</template>
