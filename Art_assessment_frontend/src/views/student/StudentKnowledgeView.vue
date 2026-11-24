<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Reading } from '@element-plus/icons-vue'
import DetailDialog from '@/components/DetailDialog.vue'
import { api } from '@/api'
import type { Chapter, ChapterQuestion, ChapterQuestionBundle, Course, Subject } from '@/types'

const router = useRouter()
const loading = ref(false)
const courses = ref<Course[]>([])
const chapters = ref<Record<number, Chapter[]>>({})
const expanded = ref<number[]>([])
const subject = ref<Subject>('music')
const activeChapter = ref<Chapter | null>(null)
const drawerOpen = ref(false)
const starting = ref(false)
const questionsLoading = ref(false)
const chapterBundle = ref<ChapterQuestionBundle | null>(null)
const activeType = ref('all')

const typeLabels: Record<string, string> = {
  single_choice: '单选题',
  multiple_choice: '多选题',
  true_false: '判断题',
  fill_blank: '填空题',
  listening: '听赏题',
  audio_choice_judge: '音频选择判断题',
  image_choice_judge: '图像选择判断题',
  image_upload: '图片作品',
  audio_upload: '音频作品'
}
const typeOrder = [
  'single_choice',
  'multiple_choice',
  'true_false',
  'fill_blank',
  'listening',
  'image_upload',
  'audio_upload'
]

const questions = computed<ChapterQuestion[]>(() => chapterBundle.value?.questions ?? [])

const questionGroups = computed(() =>
  typeOrder
    .map((type) => ({
      type,
      label: typeLabels[type],
      items: questions.value.filter((question) => question.type === type)
    }))
    .filter((group) => group.items.length)
)

const displayQuestions = computed(() =>
  questions.value
    .map((question, index) => ({ question, no: index + 1 }))
    .filter((item) => activeType.value === 'all' || item.question.type === activeType.value)
)

const knowledgeSections = computed(() => {
  const content = (chapterBundle.value?.chapter.content || activeChapter.value?.content || '').trim()
  if (!content) return []
  const sections: Array<{ title: string; lines: string[] }> = []
  let current = { title: '知识讲解', lines: [] as string[] }
  for (const raw of content.split('\n')) {
    const line = raw.trim()
    if (!line) continue
    const heading = line.match(/^【(.+)】$/)
    if (heading) {
      if (current.lines.length || sections.length) sections.push(current)
      current = { title: heading[1], lines: [] }
      continue
    }
    current.lines.push(line.replace(/^[·•]\s*/, ''))
  }
  sections.push(current)
  return sections.filter((section) => section.lines.length)
})

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

async function openChapter(chapter: Chapter) {
  activeChapter.value = chapter
  activeType.value = 'all'
  chapterBundle.value = null
  drawerOpen.value = true
  questionsLoading.value = true
  try {
    chapterBundle.value = await api.courses.chapterQuestions(chapter.id)
    activeChapter.value = chapterBundle.value.chapter
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    questionsLoading.value = false
  }
}

function typeLabel(type: string) {
  return typeLabels[type] || '题目'
}

function isTrueValue(value: unknown) {
  if (typeof value === 'boolean') return value
  return ['true', '1', '正确', '对', 'a', 't'].includes(String(value ?? '').trim().toLowerCase())
}

function formatAnswer(question: ChapterQuestion): string {
  const answer = (question.answer || {}) as Record<string, unknown>
  if (question.type === 'true_false') return isTrueValue(answer.value) ? '正确' : '错误'
  if (Array.isArray(answer.values)) {
    const values = answer.values.map((item) => String(item)).filter(Boolean)
    return values.length ? values.join('、') : '由老师评分'
  }
  if (answer.value !== undefined && answer.value !== null && String(answer.value).trim()) {
    return String(answer.value)
  }
  for (const key of ['text', 'reference', 'rubric', 'answer']) {
    const value = answer[key]
    if (typeof value === 'string' && value.trim()) return value
  }
  return '由老师评分'
}

function correctKeys(question: ChapterQuestion): string[] {
  const answer = (question.answer || {}) as Record<string, unknown>
  if (question.type === 'true_false') return []
  if (Array.isArray(answer.values)) return answer.values.map((item) => String(item).toUpperCase())
  if (answer.value !== undefined && answer.value !== null) return [String(answer.value).toUpperCase()]
  return []
}

function isCorrectOption(question: ChapterQuestion, key: string) {
  return correctKeys(question).includes(key.toUpperCase())
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
    <div class="mobile-title"><p>ART CLASSROOM</p><h2>趣味课堂</h2><span>浏览音乐与美术课程，读知识讲解，逐题查看本章全部题目。</span></div>
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
            <div><h4>{{ chapter.name }}</h4><p>{{ chapter.description || '点击查看知识讲解与本章全部题目。' }}</p></div>
            <span>{{ chapter.questionCount }} 道题 · 知识讲解 ›</span>
          </div>
          <p v-if="!(chapters[course.id] || []).length" class="muted">课程章节内容正在准备中。</p>
        </div>
      </article>
    </section>
    <section v-if="!courses.length && !loading" class="student-card empty-card">当前学科暂无已发布课程。</section>

    <DetailDialog v-model="drawerOpen" :title="activeChapter?.name" width="min(760px, 94vw)">
      <div v-if="activeChapter" class="chapter-detail">
        <p class="chapter-detail-meta">{{ activeChapter.courseName }} · {{ chapterBundle?.total ?? activeChapter.questionCount }} 道题</p>
        <p v-if="activeChapter.description" class="chapter-detail-summary">{{ activeChapter.description }}</p>

        <section class="knowledge-notes">
          <div class="chapter-section-title"><span>知识讲解</span><b>{{ knowledgeSections.length }} 个板块</b></div>
          <div v-if="knowledgeSections.length" class="knowledge-blocks">
            <article v-for="section in knowledgeSections" :key="section.title" class="knowledge-block">
              <h4>{{ section.title }}</h4>
              <p v-for="(line, index) in section.lines" :key="index">{{ line }}</p>
            </article>
          </div>
          <p v-else class="muted">本章知识讲解正在整理中。</p>
        </section>

        <section class="chapter-questions">
          <div class="chapter-section-title"><span>本章题目</span><b>共 {{ questions.length }} 道</b></div>
          <div class="question-type-tabs">
            <button :class="{ active: activeType === 'all' }" @click="activeType = 'all'">全部 {{ questions.length }}</button>
            <button v-for="group in questionGroups" :key="group.type" :class="{ active: activeType === group.type }" @click="activeType = group.type">{{ group.label }} {{ group.items.length }}</button>
          </div>
          <div v-loading="questionsLoading" class="learn-question-list">
            <article v-for="item in displayQuestions" :key="item.question.id" class="learn-question">
              <header class="learn-question-head">
                <b>{{ item.no }}</b>
                <span class="learn-question-type">{{ typeLabel(item.question.type) }}</span>
              </header>
              <p class="learn-question-stem">{{ item.question.stem }}</p>
              <ul v-if="item.question.options.length" class="learn-question-options">
                <li v-for="option in item.question.options" :key="option.key" :class="{ correct: isCorrectOption(item.question, option.key) }">
                  <b>{{ option.key }}</b><span>{{ option.text }}</span>
                  <img v-if="option.mediaUrl" :src="option.mediaUrl" alt="" />
                </li>
              </ul>
              <div v-if="item.question.resources.length" class="learn-question-resources">
                <template v-for="resource in item.question.resources" :key="resource.resourceId">
                  <audio v-if="resource.type === 'audio' && resource.url" :src="resource.url" controls />
                  <a v-else-if="resource.url" :href="resource.url" target="_blank" rel="noreferrer">{{ resource.name }}</a>
                  <span v-else>{{ resource.name }}</span>
                </template>
              </div>
              <div class="learn-question-answer"><b>参考答案</b><span>{{ formatAnswer(item.question) }}</span></div>
              <div v-if="item.question.analysis" class="learn-question-analysis"><b>解析</b><span>{{ item.question.analysis }}</span></div>
            </article>
            <p v-if="!questionsLoading && !displayQuestions.length" class="muted">本章暂无已发布的题目。</p>
          </div>
        </section>

        <div class="chapter-actions">
          <el-button type="primary" :loading="starting" @click="startChapterPractice">开始本章练习（10 题）</el-button>
          <p class="chapter-detail-tip">练习由本章题库随机抽取：6 道单选、3 道多选、1 道判断题，共 100 分，提交后立即出分，不计入正式测评。</p>
        </div>
      </div>
    </DetailDialog>
  </div>
</template>
