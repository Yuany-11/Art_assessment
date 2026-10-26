<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/api'
import type { Attempt } from '@/types'

const route = useRoute()
const router = useRouter()
const attempt = ref<Attempt | null>(null)
const currentIndex = ref(0)
const answers = reactive<Record<number, string>>({})
const seconds = ref(0)
const saving = ref(false)
const submitting = ref(false)
let timer: number | undefined
let autosaveTimer: number | undefined
let deadlineTimestamp = 0
let autoSubmitStarted = false
let deadlineWarningShown = false

const currentQuestion = computed(() => attempt.value?.questions[currentIndex.value])
const timeText = computed(() => {
  const minutes = Math.floor(seconds.value / 60).toString().padStart(2, '0')
  const rest = (seconds.value % 60).toString().padStart(2, '0')
  return `${minutes}:${rest}`
})
const answeredCount = computed(() => Object.values(answers).filter(Boolean).length)

async function load() {
  try {
    attempt.value = await api.attempts.get(Number(route.params.attemptId))
    seconds.value = attempt.value.remainingSeconds
    deadlineTimestamp = new Date(attempt.value.deadline).getTime()
    attempt.value.savedAnswers.forEach((item) => {
      answers[item.questionId] = item.answer.value || item.answer.text || ''
    })
    timer = window.setInterval(() => {
      seconds.value = Math.max(0, Math.ceil((deadlineTimestamp - Date.now()) / 1000))
      if (seconds.value === 0 && attempt.value?.status === 'in_progress') void submit(true)
      if (!deadlineWarningShown && seconds.value > 0 && seconds.value <= 300) {
        deadlineWarningShown = true
        ElMessage.warning('距离自动交卷不足 5 分钟，请及时保存并提交')
      }
    }, 1000)
    autosaveTimer = window.setInterval(() => {
      if (attempt.value?.status === 'in_progress' && Object.values(answers).some(Boolean)) void save(true)
    }, 15_000)
    if (seconds.value <= 0) void submit(true)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function save(silent = false) {
  if (!attempt.value || saving.value) return
  saving.value = true
  try {
    const payload = Object.entries(answers).map(([questionId, value]) => ({
      questionId: Number(questionId),
      answer: attempt.value?.questions.find((question) => question.questionId === Number(questionId))?.type === 'short_answer' ? { text: value } : { value }
    }))
    await api.attempts.save(attempt.value.attemptId, payload)
    if (!silent) ElMessage.success('答案已保存')
  } catch (error) {
    if (!silent) ElMessage.error((error as Error).message)
  } finally {
    saving.value = false
  }
}

async function submit(auto = false) {
  if (!attempt.value || submitting.value || attempt.value.status !== 'in_progress') return
  if (auto && autoSubmitStarted) return
  if (!auto) {
    try {
      await ElMessageBox.confirm(`已作答 ${answeredCount.value}/${attempt.value.questions.length} 题，确认交卷吗？`, '提交答卷', { type: 'warning' })
    } catch {
      return
    }
  }
  if (auto) autoSubmitStarted = true
  submitting.value = true
  try {
    window.clearInterval(timer)
    window.clearInterval(autosaveTimer)
    await save(true)
    const result = await api.attempts.submit(attempt.value.attemptId, auto ? 'auto' : 'manual')
    attempt.value.status = 'submitted'
    ElMessage.success(auto ? '答题时间已到，系统已自动交卷' : '交卷成功')
    const scoreId = Number(result.scoreId)
    await router.replace({ path: '/student/results', query: Number.isFinite(scoreId) ? { scoreId } : {} })
  } catch (error) {
    autoSubmitStarted = false
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

function selectAnswer(value: string) {
  if (!currentQuestion.value) return
  answers[currentQuestion.value.questionId] = value
}

function playAudio() {
  const AudioContextClass = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!AudioContextClass) {
    ElMessage.warning('当前浏览器不支持音频播放')
    return
  }
  const context = new AudioContextClass()
  const oscillator = context.createOscillator()
  const gain = context.createGain()
  oscillator.type = 'sine'
  oscillator.frequency.setValueAtTime(440, context.currentTime)
  oscillator.frequency.linearRampToValueAtTime(660, context.currentTime + 0.8)
  gain.gain.setValueAtTime(0.12, context.currentTime)
  gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 1.2)
  oscillator.connect(gain).connect(context.destination)
  oscillator.start()
  oscillator.stop(context.currentTime + 1.2)
}

function selectFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file || !currentQuestion.value) return
  answers[currentQuestion.value.questionId] = file.name
  ElMessage.success(`已选择 ${file.name}`)
}

function saveWhenHidden() {
  if (document.visibilityState === 'hidden' && Object.values(answers).some(Boolean)) void save(true)
}

onMounted(() => {
  load()
  document.addEventListener('visibilitychange', saveWhenHidden)
})
onBeforeUnmount(() => {
  window.clearInterval(timer)
  window.clearInterval(autosaveTimer)
  document.removeEventListener('visibilitychange', saveWhenHidden)
})
</script>

<template>
  <div v-if="attempt" class="attempt-page">
    <header class="attempt-header">
      <div><p>{{ attempt.title }}</p><span>已答 {{ answeredCount }}/{{ attempt.questions.length }}</span></div>
      <strong :class="{ urgent: seconds < 300 }">{{ timeText }}</strong>
    </header>
    <main class="attempt-content" v-if="currentQuestion">
      <div class="question-progress"><span v-for="(q, index) in attempt.questions" :key="q.questionId" :class="{ active: index === currentIndex, done: answers[q.questionId] }" @click="currentIndex = index">{{ index + 1 }}</span></div>
      <article class="question-card">
        <small>第 {{ currentIndex + 1 }} 题 · {{ currentQuestion.score }} 分</small>
        <h1>{{ currentQuestion.stem }}</h1>
        <div v-if="currentQuestion.resources.some((item) => item.type === 'audio')" class="question-media">
          <button class="audio-player" @click="playAudio"><span>▶</span><div><b>播放听赏音频</b><small>演示音频 · 建议使用耳机</small></div></button>
        </div>
        <div v-if="currentQuestion.resources.some((item) => item.type === 'image')" class="question-media">
          <img
            v-for="item in currentQuestion.resources.filter((resource) => resource.type === 'image')"
            :key="item.name"
            :src="item.url || 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22640%22 height=%22360%22%3E%3Crect width=%22640%22 height=%22360%22 fill=%22%23eef4ff%22/%3E%3Ctext x=%22320%22 y=%22190%22 text-anchor=%22middle%22 font-size=%2224%22 fill=%22%232563eb%22%3E题目图片%3C/text%3E%3C/svg%3E'"
            :alt="item.name"
          />
        </div>
        <div v-if="currentQuestion.options.length" class="option-list">
          <button v-for="option in currentQuestion.options" :key="option.key" :class="{ selected: answers[currentQuestion.questionId] === option.key }" @click="selectAnswer(option.key)">
            <b>{{ option.key }}</b><span>{{ option.text }}</span>
          </button>
        </div>
        <el-input
          v-else-if="!currentQuestion.type.includes('upload')"
          v-model="answers[currentQuestion.questionId]"
          type="textarea"
          :rows="8"
          :maxlength="currentQuestion.answerConfig?.maxLength || 500"
          show-word-limit
          placeholder="请输入你的回答"
          resize="none"
        />
        <label v-else class="upload-zone answer-upload">
          <b>{{ answers[currentQuestion.questionId] || '点击上传作品文件' }}</b>
          <span>{{ currentQuestion.type === 'audio_upload' ? 'MP3、WAV 或 M4A' : 'JPG、PNG 或 WEBP' }}</span>
          <input type="file" :accept="currentQuestion.type === 'audio_upload' ? 'audio/*' : 'image/*'" @change="selectFile" />
        </label>
      </article>
      <div class="attempt-actions">
        <el-button :disabled="currentIndex === 0" @click="currentIndex -= 1">上一题</el-button>
        <el-button :loading="saving" @click="save(false)">保存答案</el-button>
        <el-button v-if="currentIndex < attempt.questions.length - 1" type="primary" @click="currentIndex += 1">下一题</el-button>
        <el-button v-else type="primary" :loading="submitting" @click="submit(false)">提交答卷</el-button>
      </div>
      <p class="autosave-note">答案每 15 秒自动保存；倒计时结束时系统会自动交卷，交卷后将展示答案与解析。</p>
    </main>
  </div>
</template>
