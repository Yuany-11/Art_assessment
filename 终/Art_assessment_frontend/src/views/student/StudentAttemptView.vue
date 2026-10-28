<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading, Microphone } from '@element-plus/icons-vue'
import { api } from '@/api'
import type { Attempt, AttemptAnswer, AttemptQuestion } from '@/types'
import { answerFile, isAudioFile, isImageFile } from '@/utils/answers'

const route = useRoute()
const router = useRouter()
const attempt = ref<Attempt | null>(null)
const currentIndex = ref(0)
const answers = reactive<Record<number, AttemptAnswer>>({})
const seconds = ref(0)
const saving = ref(false)
const submitting = ref(false)
const uploadingId = ref<number | null>(null)
let timer: number | undefined
let autosaveTimer: number | undefined
let deadlineTimestamp = 0
let autoSubmitStarted = false
let deadlineWarningShown = false
let pendingSave: Promise<boolean> | null = null

const RECORDING_LIMIT_SECONDS = 300
const MAX_UPLOAD_BYTES = 20 * 1024 * 1024
const recording = ref(false)
const recordingQuestionId = ref<number | null>(null)
const recordingSeconds = ref(0)
const processingRecordingId = ref<number | null>(null)
let mediaRecorder: MediaRecorder | null = null
let mediaStream: MediaStream | null = null
let recordedChunks: BlobPart[] = []
let recordingTimer: number | undefined
let discardRecording = false

const currentQuestion = computed(() => attempt.value?.questions[currentIndex.value])
const currentAnswerFile = computed(() => answerFile(currentQuestion.value ? answers[currentQuestion.value.questionId] : null))
const timeText = computed(() => {
  const minutes = Math.floor(seconds.value / 60).toString().padStart(2, '0')
  const rest = (seconds.value % 60).toString().padStart(2, '0')
  return `${minutes}:${rest}`
})
const recordingTimeText = computed(() => {
  const minutes = Math.floor(recordingSeconds.value / 60).toString().padStart(2, '0')
  const rest = (recordingSeconds.value % 60).toString().padStart(2, '0')
  return `${minutes}:${rest}`
})
const answeredCount = computed(() => (attempt.value?.questions ?? []).filter((question) => hasAnswer(question)).length)

function hasAnswer(question: AttemptQuestion) {
  const answer = answers[question.questionId]
  if (!answer) return false
  if (question.type === 'multiple_choice' || question.type === 'fill_blank') {
    return (answer.values ?? []).some((value) => String(value ?? '').trim() !== '')
  }
  if (question.type === 'short_answer') return Boolean(answer.text?.trim())
  if (question.type === 'image_upload' || question.type === 'audio_upload') {
    return Boolean(answer.fileId && answer.url)
  }
  return answer.value !== undefined && answer.value !== null && String(answer.value).trim() !== ''
}

async function load() {
  try {
    attempt.value = await api.attempts.get(Number(route.params.attemptId))
    seconds.value = attempt.value.remainingSeconds
    deadlineTimestamp = new Date(attempt.value.deadline).getTime()
    attempt.value.savedAnswers.forEach((item) => {
      const saved = { ...item.answer }
      if (Array.isArray(saved.values)) saved.values = [...saved.values]
      answers[item.questionId] = saved
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
      if (attempt.value?.status === 'in_progress' && Object.keys(answers).length) void save(true)
    }, 15_000)
    if (seconds.value <= 0) void submit(true)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function buildAnswer(question: AttemptQuestion): AttemptAnswer | null {
  const answer = answers[question.questionId]
  if (!answer) return null
  if (question.type === 'image_upload' || question.type === 'audio_upload') {
    const file = answerFile(answer)
    return file ? { ...file } : null
  }
  if (question.type === 'multiple_choice' || question.type === 'fill_blank') {
    const values = (answer.values ?? []).map((value) => String(value ?? ''))
    return values.some((value) => value.trim()) ? { values } : null
  }
  if (question.type === 'short_answer') {
    return answer.text?.trim() ? { text: answer.text } : null
  }
  if (question.type === 'true_false') {
    if (typeof answer.value === 'boolean') return { value: answer.value }
    if (answer.value === 'true' || answer.value === 'false') return { value: answer.value === 'true' }
    return null
  }
  return answer.value !== undefined && answer.value !== null && String(answer.value).trim() !== ''
    ? { value: answer.value }
    : null
}

async function save(silent = false): Promise<boolean> {
  if (!attempt.value) return false
  if (pendingSave) return pendingSave
  saving.value = true
  const task = (async () => {
    try {
      const payload = attempt.value!.questions
        .filter((question) => answers[question.questionId] !== undefined)
        .map((question) => ({
          questionId: question.questionId,
          answer: buildAnswer(question) ?? {}
        }))
      if (payload.length) await api.attempts.save(attempt.value!.attemptId, payload)
      if (!silent) ElMessage.success('答案已保存')
      return true
    } catch (error) {
      if (!silent) ElMessage.error((error as Error).message)
      return false
    }
  })()
  pendingSave = task.finally(() => {
    saving.value = false
    pendingSave = null
  })
  return pendingSave
}

async function submit(auto = false) {
  if (!attempt.value || submitting.value || attempt.value.status !== 'in_progress') return
  if (auto && autoSubmitStarted) return
  if (recording.value) stopRecording(true)
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
    const saved = await save(true)
    if (!saved && !auto) {
      ElMessage.error('答案保存失败，请检查网络后重试')
      return
    }
    const result = await api.attempts.submit(attempt.value.attemptId, auto ? 'auto' : 'manual')
    attempt.value.status = 'submitted'
    const scoreId = Number(result.scoreId)
    const released = Number.isFinite(scoreId)
    ElMessage.success(
      auto
        ? `答题时间已到，系统已自动交卷${released ? '' : '，等待教师评分'}`
        : (result.message as string | undefined) ?? '交卷成功'
    )
    // 含简答题的测评要等教师终评后才公布成绩，未出分时返回测评列表。
    await router.replace(
      released
        ? { path: '/student/results', query: { scoreId } }
        : { path: '/student/assessments' }
    )
  } catch (error) {
    autoSubmitStarted = false
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function saveAndExit() {
  if (!attempt.value) return
  try {
    await ElMessageBox.confirm('答案会立即保存，考试仍在计时，可从“我的测评”继续作答。', '保存并退出', {
      type: 'info',
      confirmButtonText: '保存并退出',
      cancelButtonText: '继续答题'
    })
  } catch {
    return
  }
  if (recording.value) stopRecording(true)
  const saved = await save(true)
  if (!saved) {
    ElMessage.error('答案保存失败，请检查网络后重试')
    return
  }
  window.clearInterval(timer)
  window.clearInterval(autosaveTimer)
  ElMessage.success('已保存，可从“我的测评”继续作答')
  await router.push('/student/assessments')
}

function ensureAnswer(questionId: number) {
  if (!answers[questionId]) answers[questionId] = {}
  return answers[questionId]
}

function selectAnswer(questionId: number, value: string) {
  ensureAnswer(questionId).value = value
}

function toggleOption(questionId: number, key: string) {
  const answer = ensureAnswer(questionId)
  const values = new Set(answer.values ?? [])
  if (values.has(key)) values.delete(key)
  else values.add(key)
  answer.values = [...values].sort()
}

function isOptionSelected(questionId: number, key: string) {
  const answer = answers[questionId]
  if (!answer) return false
  if (Array.isArray(answer.values)) return answer.values.includes(key)
  return answer.value === key
}

function setTrueFalse(questionId: number, value: boolean) {
  ensureAnswer(questionId).value = value
}

function setText(questionId: number, value: string) {
  ensureAnswer(questionId).text = value
}

function blankCount(question: AttemptQuestion) {
  return Math.max(1, question.answerConfig?.blankCount ?? 1)
}

function setBlank(questionId: number, index: number, value: string) {
  const answer = ensureAnswer(questionId)
  const values = [...(answer.values ?? [])]
  while (values.length <= index) values.push('')
  values[index] = value
  answer.values = values
}

async function uploadFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  const question = currentQuestion.value
  if (!file || !question || !attempt.value) return

  const isAudio = question.type === 'audio_upload'
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  const allowed = isAudio ? ['mp3', 'wav', 'm4a', 'webm', 'ogg'] : ['jpg', 'jpeg', 'png', 'webp']
  if (!allowed.includes(ext)) {
    ElMessage.warning(isAudio ? '请上传 MP3、WAV、M4A、WEBM 或 OGG 音频' : '请上传 JPG、PNG 或 WEBP 图片')
    return
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    ElMessage.warning('文件大小不能超过 20 MB')
    return
  }

  await uploadAnswerFile(file, question.questionId, '作品已上传并保存')
}

async function uploadAnswerFile(file: File, questionId: number, successText: string) {
  if (!attempt.value) return
  if (file.size > MAX_UPLOAD_BYTES) {
    ElMessage.warning('文件大小不能超过 20 MB')
    return
  }
  uploadingId.value = questionId
  try {
    const uploaded = await api.attempts.uploadAnswer(attempt.value.attemptId, file, attempt.value.subject)
    answers[questionId] = { ...uploaded }
    const saved = await save(true)
    if (saved) ElMessage.success(successText)
    else ElMessage.warning('上传成功，但答案保存失败，请点击“保存答案”重试')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    uploadingId.value = null
  }
}

function recordingExtension(type: string) {
  if (type.includes('mp4')) return 'm4a'
  if (type.includes('ogg')) return 'ogg'
  return 'webm'
}

function audioContextConstructor() {
  return window.AudioContext
    || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
}

function encodeWav(buffer: AudioBuffer) {
  const samples = buffer.length
  const dataSize = samples * 2
  const wav = new DataView(new ArrayBuffer(44 + dataSize))
  const writeText = (offset: number, text: string) => {
    for (let index = 0; index < text.length; index += 1) {
      wav.setUint8(offset + index, text.charCodeAt(index))
    }
  }
  writeText(0, 'RIFF')
  wav.setUint32(4, 36 + dataSize, true)
  writeText(8, 'WAVE')
  writeText(12, 'fmt ')
  wav.setUint32(16, 16, true)
  wav.setUint16(20, 1, true)
  wav.setUint16(22, 1, true)
  wav.setUint32(24, buffer.sampleRate, true)
  wav.setUint32(28, buffer.sampleRate * 2, true)
  wav.setUint16(32, 2, true)
  wav.setUint16(34, 16, true)
  writeText(36, 'data')
  wav.setUint32(40, dataSize, true)
  const left = buffer.getChannelData(0)
  const right = buffer.numberOfChannels > 1 ? buffer.getChannelData(1) : null
  let offset = 44
  for (let index = 0; index < samples; index += 1) {
    const value = right ? (left[index] + right[index]) / 2 : left[index]
    const clamped = Math.max(-1, Math.min(1, value))
    wav.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true)
    offset += 2
  }
  return new Blob([wav], { type: 'audio/wav' })
}

/** 浏览器的 MediaRecorder 多输出 webm（缺少时长信息），转成 24 kHz 单声道 WAV 后更好播放。 */
async function recordingToWav(blob: Blob): Promise<Blob | null> {
  const AudioContextClass = audioContextConstructor()
  if (!AudioContextClass) return null
  let context: AudioContext | null = null
  try {
    context = new AudioContextClass()
    const decoded = await context.decodeAudioData(await blob.arrayBuffer())
    if (!decoded.length) return null
    const sampleRate = Math.min(24_000, decoded.sampleRate)
    const offline = new OfflineAudioContext(1, Math.ceil(decoded.duration * sampleRate), sampleRate)
    const source = offline.createBufferSource()
    source.buffer = decoded
    source.connect(offline.destination)
    source.start()
    return encodeWav(await offline.startRendering())
  } catch {
    return null
  } finally {
    void context?.close()
  }
}

async function handleRecordingBlob(blob: Blob, mimeType: string, questionId: number) {
  processingRecordingId.value = questionId
  try {
    const wav = await recordingToWav(blob)
    const stamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14)
    const file = wav
      ? new File([wav], `recording-${stamp}.wav`, { type: 'audio/wav' })
      : new File([blob], `recording-${stamp}.${recordingExtension(mimeType)}`, { type: mimeType })
    await uploadAnswerFile(file, questionId, '录音已上传并保存')
  } finally {
    if (processingRecordingId.value === questionId) processingRecordingId.value = null
  }
}

function preferredRecordingType() {
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']
  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) ?? ''
}

function cleanupRecording() {
  window.clearInterval(recordingTimer)
  recordingTimer = undefined
  mediaStream?.getTracks().forEach((track) => track.stop())
  mediaStream = null
  mediaRecorder = null
  recording.value = false
  recordingQuestionId.value = null
  recordingSeconds.value = 0
}

async function startRecording() {
  const question = currentQuestion.value
  if (!question || !attempt.value || recording.value) return
  if (!window.MediaRecorder || !navigator.mediaDevices?.getUserMedia) {
    ElMessage.warning('当前浏览器不支持录音，请改用上传音频文件')
    return
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    mediaStream = stream
    const mimeType = preferredRecordingType()
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
    mediaRecorder = recorder
    recordedChunks = []
    discardRecording = false
    recordingQuestionId.value = question.questionId
    recordingSeconds.value = 0
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) recordedChunks.push(event.data)
    }
    recorder.onstop = () => {
      const chunks = recordedChunks
      const questionId = recordingQuestionId.value
      const type = recorder.mimeType || mimeType || 'audio/webm'
      recordedChunks = []
      cleanupRecording()
      if (discardRecording || !chunks.length || !questionId) return
      void handleRecordingBlob(new Blob(chunks, { type }), type, questionId)
    }
    recorder.start()
    recording.value = true
    recordingTimer = window.setInterval(() => {
      recordingSeconds.value += 1
      if (recordingSeconds.value >= RECORDING_LIMIT_SECONDS) {
        ElMessage.info('已达到 5 分钟录音上限，正在自动保存')
        stopRecording(false)
      }
    }, 1000)
    ElMessage.success('录音开始，请对着麦克风演唱')
  } catch {
    mediaStream?.getTracks().forEach((track) => track.stop())
    mediaStream = null
    mediaRecorder = null
    ElMessage.error('无法使用麦克风，请检查浏览器麦克风权限')
  }
}

function stopRecording(discard = false) {
  discardRecording = discard
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop()
  } else {
    cleanupRecording()
  }
  if (discard) ElMessage.info('已取消录音')
}

async function removeUpload() {
  if (!currentQuestion.value) return
  answers[currentQuestion.value.questionId] = {}
  const saved = await save(true)
  if (saved) ElMessage.success('已移除上传文件')
  else ElMessage.warning('文件已移除，但保存失败，请稍后重试')
}

function playAudio(url?: string) {
  if (url) {
    const audio = new Audio(url)
    audio.play().catch(() => ElMessage.warning('音频暂时无法播放，请检查文件是否存在'))
    return
  }
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

function questionAudio(question: AttemptQuestion) {
  return question.resources.find((item) => item.type === 'audio')?.url
}

function saveWhenHidden() {
  if (document.visibilityState === 'hidden' && Object.keys(answers).length) void save(true)
}

watch(currentIndex, () => {
  if (recording.value) stopRecording(true)
})

onMounted(() => {
  load()
  document.addEventListener('visibilitychange', saveWhenHidden)
})
onBeforeUnmount(() => {
  window.clearInterval(timer)
  window.clearInterval(autosaveTimer)
  if (recording.value) stopRecording(true)
  else cleanupRecording()
  document.removeEventListener('visibilitychange', saveWhenHidden)
})
</script>

<template>
  <div v-if="attempt" class="attempt-page">
    <header class="attempt-header">
      <div><p>{{ attempt.title }}</p><span>已答 {{ answeredCount }}/{{ attempt.questions.length }} · 答案自动保存</span></div>
      <strong :class="{ urgent: seconds < 300 }">{{ timeText }}</strong>
    </header>
    <main v-if="currentQuestion" class="attempt-content">
      <div class="question-progress">
        <span
          v-for="(question, index) in attempt.questions"
          :key="question.questionId"
          :class="{ active: index === currentIndex, done: hasAnswer(question) }"
          @click="currentIndex = index"
        >
          {{ index + 1 }}
        </span>
      </div>
      <article class="question-card">
        <small>第 {{ currentIndex + 1 }} 题 · {{ currentQuestion.score }} 分</small>
        <h1>{{ currentQuestion.stem }}</h1>
        <div v-if="currentQuestion.resources.some((item) => item.type === 'audio')" class="question-media">
          <button class="audio-player" @click="playAudio(questionAudio(currentQuestion))">
            <span>▶</span><div><b>播放听赏音频</b><small>建议使用耳机</small></div>
          </button>
        </div>
        <div v-if="currentQuestion.resources.some((item) => item.type === 'image')" class="question-media">
          <img
            v-for="item in currentQuestion.resources.filter((resource) => resource.type === 'image')"
            :key="item.name"
            :src="item.url || 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22640%22 height=%22360%22%3E%3Crect width=%22640%22 height=%22360%22 fill=%22%23eef4ff%22/%3E%3Ctext x=%22320%22 y=%22190%22 text-anchor=%22middle%22 font-size=%2224%22 fill=%22%232563eb%22%3E题目图片%3C/text%3E%3C/svg%3E'"
            :alt="item.name"
          />
        </div>

        <div v-if="currentQuestion.type === 'true_false'" class="option-list true-false-list">
          <button :class="{ selected: answers[currentQuestion.questionId]?.value === true }" @click="setTrueFalse(currentQuestion.questionId, true)">
            <b>✓</b><span>正确</span>
          </button>
          <button :class="{ selected: answers[currentQuestion.questionId]?.value === false }" @click="setTrueFalse(currentQuestion.questionId, false)">
            <b>✕</b><span>错误</span>
          </button>
        </div>

        <div v-else-if="currentQuestion.options.length" class="option-list">
          <button
            v-for="option in currentQuestion.options"
            :key="option.key"
            :class="{ selected: isOptionSelected(currentQuestion.questionId, option.key) }"
            @click="currentQuestion.type === 'multiple_choice'
              ? toggleOption(currentQuestion.questionId, option.key)
              : selectAnswer(currentQuestion.questionId, option.key)"
          >
            <b>{{ option.key }}</b><span>{{ option.text }}</span>
          </button>
          <p v-if="currentQuestion.type === 'multiple_choice'" class="question-hint">多选题，请选择所有正确选项。</p>
        </div>

        <div v-else-if="currentQuestion.type === 'fill_blank'" class="fill-blank-list">
          <label v-for="index in blankCount(currentQuestion)" :key="index">
            <span>第 {{ index }} 空</span>
            <el-input
              :model-value="answers[currentQuestion.questionId]?.values?.[index - 1] ?? ''"
              placeholder="请输入答案"
              @update:model-value="setBlank(currentQuestion.questionId, index - 1, $event)"
            />
          </label>
        </div>

        <el-input
          v-else-if="currentQuestion.type === 'short_answer'"
          :model-value="answers[currentQuestion.questionId]?.text ?? ''"
          type="textarea"
          :rows="8"
          :maxlength="currentQuestion.answerConfig?.maxLength || 500"
          show-word-limit
          placeholder="请输入你的回答"
          resize="none"
          @update:model-value="setText(currentQuestion.questionId, $event)"
        />

        <div v-else-if="currentQuestion.type === 'image_upload' || currentQuestion.type === 'audio_upload'" class="answer-upload-box">
          <div v-if="processingRecordingId === currentQuestion.questionId" class="recording-panel recording-panel--processing">
            <el-icon class="is-loading processing-icon"><Loading /></el-icon>
            <div class="recording-copy">
              <b>正在处理录音</b>
              <span>正在生成音频文件并上传，请稍候…</span>
            </div>
          </div>
          <div v-else-if="recording && recordingQuestionId === currentQuestion.questionId" class="recording-panel">
            <span class="recording-dot" aria-hidden="true"></span>
            <div class="recording-copy">
              <b>正在录音</b>
              <span>已录制 {{ recordingTimeText }} / 05:00，停止后会自动上传</span>
            </div>
            <div class="recording-actions">
              <el-button size="small" @click="stopRecording(true)">取消</el-button>
              <el-button type="primary" size="small" @click="stopRecording(false)">停止并上传</el-button>
            </div>
          </div>
          <template v-else-if="currentAnswerFile">
            <img v-if="isImageFile(currentAnswerFile)" :src="currentAnswerFile.url" :alt="currentAnswerFile.name" class="upload-preview-image" />
            <audio v-else-if="isAudioFile(currentAnswerFile)" :src="currentAnswerFile.url" controls class="upload-preview-audio" />
            <div class="upload-file-meta">
              <b>{{ currentAnswerFile.name }}</b>
              <span>{{ (currentAnswerFile.size / 1024 / 1024).toFixed(2) }} MB</span>
            </div>
            <div class="upload-file-actions">
              <label class="el-button el-button--default">
                <span>重新上传</span>
                <input type="file" :accept="currentQuestion.type === 'audio_upload' ? 'audio/*' : 'image/*'" @change="uploadFile" />
              </label>
              <el-button v-if="currentQuestion.type === 'audio_upload'" @click="startRecording">重新录音</el-button>
              <el-button @click="removeUpload">移除文件</el-button>
            </div>
          </template>
          <div v-else class="answer-upload-options" :class="{ 'answer-upload-options--pair': currentQuestion.type === 'audio_upload' }">
            <label class="upload-zone answer-upload" :class="{ uploading: uploadingId === currentQuestion.questionId }">
              <b>{{ uploadingId === currentQuestion.questionId ? '正在上传并保存…' : '点击上传作品文件' }}</b>
              <span>{{ currentQuestion.type === 'audio_upload' ? '支持 MP3、WAV、M4A、WEBM，最大 20 MB' : '支持 JPG、PNG、WEBP，最大 20 MB' }}</span>
              <input
                type="file"
                :accept="currentQuestion.type === 'audio_upload' ? 'audio/*' : 'image/*'"
                :disabled="uploadingId === currentQuestion.questionId"
                @change="uploadFile"
              />
            </label>
            <button
              v-if="currentQuestion.type === 'audio_upload'"
              type="button"
              class="answer-record"
              :disabled="uploadingId === currentQuestion.questionId"
              @click="startRecording"
            >
              <el-icon><Microphone /></el-icon>
              <b>直接录音</b>
              <span>使用麦克风演唱，最长 5 分钟</span>
            </button>
          </div>
        </div>

        <el-input
          v-else
          :model-value="answers[currentQuestion.questionId]?.text ?? ''"
          type="textarea"
          :rows="8"
          :maxlength="currentQuestion.answerConfig?.maxLength || 500"
          show-word-limit
          placeholder="请输入你的回答"
          resize="none"
          @update:model-value="setText(currentQuestion.questionId, $event)"
        />
      </article>
      <div class="attempt-actions">
        <el-button :disabled="currentIndex === 0" @click="currentIndex -= 1">上一题</el-button>
        <el-button :loading="saving" @click="save(false)">保存答案</el-button>
        <el-button :loading="saving" @click="saveAndExit">保存并退出</el-button>
        <el-button v-if="currentIndex < attempt.questions.length - 1" type="primary" @click="currentIndex += 1">下一题</el-button>
        <el-button v-else type="primary" :loading="submitting" @click="submit(false)">提交答卷</el-button>
      </div>
      <p class="autosave-note">答案每 15 秒自动保存；“保存并退出”后考试仍在计时，可从“我的测评”继续作答；倒计时结束时系统会自动交卷。</p>
    </main>
  </div>
</template>
