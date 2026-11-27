<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Camera, Loading, Microphone } from '@element-plus/icons-vue'
import { api } from '@/api'
import type { Attempt, AttemptAnswer, AttemptQuestion } from '@/types'
import { answerFile, answerFiles, isAudioFile, isImageFile } from '@/utils/answers'

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
/** 客户端时钟与服务器时钟的差值，避免本机时间不准导致自动交卷提前或延后。 */
let clockOffset = 0
let autoSubmitStarted = false
let deadlineWarningShown = false
let pendingSave: Promise<boolean> | null = null

const RECORDING_LIMIT_SECONDS = 300
const MAX_UPLOAD_BYTES = 20 * 1024 * 1024
const recording = ref(false)
const recordingQuestionId = ref<number | null>(null)
const recordingSeconds = ref(0)
const processingRecordingId = ref<number | null>(null)
const captureInput = ref<HTMLInputElement>()
const cameraOpen = ref(false)
const cameraLoading = ref(false)
const cameraVideo = ref<HTMLVideoElement>()
const cameraStream = ref<MediaStream | null>(null)
const cameraQuestion = ref<AttemptQuestion | null>(null)
const cameraReplace = ref(false)
let mediaRecorder: MediaRecorder | null = null
let mediaStream: MediaStream | null = null
let recordedChunks: BlobPart[] = []
let recordingTimer: number | undefined
let discardRecording = false

const currentQuestion = computed(() => attempt.value?.questions[currentIndex.value])
const currentAnswerFile = computed(() => answerFile(currentQuestion.value ? answers[currentQuestion.value.questionId] : null))
const currentAnswerFiles = computed(() =>
  answerFiles(currentQuestion.value ? answers[currentQuestion.value.questionId] : null)
)
const MAX_ARTWORK_PHOTOS = 3
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
  if (question.type === 'image_upload' || question.type === 'audio_upload') {
    return answerFiles(answer).length > 0
  }
  return answer.value !== undefined && answer.value !== null && String(answer.value).trim() !== ''
}

/** 从右侧答题卡切换题目，回到页面上方从题面开始阅读。 */
function goToQuestion(index: number) {
  if (!attempt.value || index === currentIndex.value) return
  currentIndex.value = index
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

async function load() {
  try {
    attempt.value = await api.attempts.get(Number(route.params.attemptId))
    // 后端在截止时间后会自动交卷；此时直接进入试卷阅览页，避免停留在无法作答的页面。
    if (attempt.value.status !== 'in_progress') {
      await router.replace(`/student/attempt/${attempt.value.attemptId}/review`)
      return
    }
    seconds.value = attempt.value.remainingSeconds
    deadlineTimestamp = new Date(attempt.value.deadline).getTime()
    const serverNow = new Date(attempt.value.serverTime).getTime()
    clockOffset = Number.isFinite(serverNow) ? serverNow - Date.now() : 0
    attempt.value.savedAnswers.forEach((item) => {
      const saved = { ...item.answer }
      if (Array.isArray(saved.values)) saved.values = [...saved.values]
      answers[item.questionId] = saved
    })
    timer = window.setInterval(() => {
      seconds.value = Math.max(0, Math.ceil((deadlineTimestamp - (Date.now() + clockOffset)) / 1000))
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
    const files = answerFiles(answer)
    if (!files.length) return null
    const primary = files[0]
    return {
      ...primary,
      captureMode: primary.captureMode || answer.captureMode,
      ...(question.type === 'image_upload' && files.length > 1 ? { files } : {})
    }
  }
  if (question.type === 'multiple_choice' || question.type === 'fill_blank') {
    const values = (answer.values ?? []).map((value) => String(value ?? ''))
    return values.some((value) => value.trim()) ? { values } : null
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
    const missingArtworks = attempt.value.questions
      .filter((question) => question.type === 'image_upload' && !hasAnswer(question))
      .map((question) => question.order)
    const missingHint = missingArtworks.length
      ? `；第 ${missingArtworks.join('、')} 题美术作品尚未上传`
      : ''
    try {
      await ElMessageBox.confirm(
        `已作答 ${answeredCount.value}/${attempt.value.questions.length} 题${missingHint}，确认交卷吗？`,
        '提交答卷',
        {
          type: 'warning',
          confirmButtonText: '确认交卷',
          cancelButtonText: '再检查一下',
          customClass: 'compact-confirm'
        }
      )
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
    // 交卷后统一进入试卷阅览页；标准答案按老师设置的公布时间展示。
    await router.replace(`/student/attempt/${attempt.value.attemptId}/review`)
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
      cancelButtonText: '继续答题',
      customClass: 'compact-confirm'
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

async function handlePickedFile(
  file: File,
  question: AttemptQuestion,
  captureMode: 'camera' | 'album' | 'file' = 'file',
  replace = false
) {
  const isAudio = question.type === 'audio_upload'
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  const allowed = isAudio ? ['mp3', 'wav', 'm4a', 'webm', 'ogg'] : ['jpg', 'jpeg', 'png', 'webp']
  if (!allowed.includes(ext)) {
    ElMessage.warning(isAudio ? '请上传 MP3、WAV、M4A、WEBM 或 OGG 音频' : '请上传 JPG、PNG 或 WEBP 图片')
    return
  }
  const limit = isAudio ? MAX_UPLOAD_BYTES : 10 * 1024 * 1024
  if (file.size > limit) {
    ElMessage.warning(isAudio ? '音频大小不能超过 20 MB' : '图片大小不能超过 10 MB')
    return
  }
  if (!isAudio && !replace) {
    const existing = answerFiles(answers[question.questionId])
    if (existing.length >= MAX_ARTWORK_PHOTOS) {
      ElMessage.warning(`每道作品题最多上传 ${MAX_ARTWORK_PHOTOS} 张照片`)
      return
    }
  }
  await uploadAnswerFile(file, question.questionId, '作品已上传并保存', captureMode, replace)
}

function stopCamera() {
  cameraStream.value?.getTracks().forEach((track) => track.stop())
  cameraStream.value = null
  if (cameraVideo.value) cameraVideo.value.srcObject = null
}

function fallbackToCaptureInput() {
  captureInput.value?.click()
}

async function openCamera(question: AttemptQuestion, replace = false) {
  cameraQuestion.value = question
  cameraReplace.value = replace
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    ElMessage.warning('当前环境无法调用摄像头（需要 HTTPS 或 localhost），已切换为相册/文件上传')
    fallbackToCaptureInput()
    return
  }
  cameraLoading.value = true
  cameraOpen.value = true
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' } },
      audio: false
    })
    cameraStream.value = stream
    await nextTick()
    if (cameraVideo.value) cameraVideo.value.srcObject = stream
  } catch {
    cameraOpen.value = false
    stopCamera()
    ElMessage.warning('摄像头不可用或权限被拒绝，已切换为相册/文件上传')
    fallbackToCaptureInput()
  } finally {
    cameraLoading.value = false
  }
}

async function capturePhoto() {
  const video = cameraVideo.value
  const question = cameraQuestion.value
  if (!video || !question || !video.videoWidth) {
    ElMessage.warning('摄像头画面尚未准备好，请稍后重试')
    return
  }
  const canvas = document.createElement('canvas')
  canvas.width = video.videoWidth
  canvas.height = video.videoHeight
  canvas.getContext('2d')?.drawImage(video, 0, 0)
  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, 'image/jpeg', 0.9)
  )
  stopCamera()
  cameraOpen.value = false
  if (!blob) {
    ElMessage.warning('拍照失败，请改用相册上传')
    return
  }
  const file = new File([blob], `photo-${Date.now()}.jpg`, { type: 'image/jpeg' })
  await handlePickedFile(file, question, 'camera', cameraReplace.value)
}

async function uploadCaptureFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  const question = currentQuestion.value
  if (!file || !question || !attempt.value) return
  await handlePickedFile(file, question, 'camera', cameraReplace.value)
}

async function uploadFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  const question = currentQuestion.value
  if (!file || !question || !attempt.value) return
  await handlePickedFile(file, question)
}

const uploadDragActive = ref(false)

function onUploadDragOver(event: DragEvent) {
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
  uploadDragActive.value = true
}

function onUploadDragLeave(event: DragEvent) {
  const zone = event.currentTarget as HTMLElement
  if (event.relatedTarget instanceof Node && zone.contains(event.relatedTarget)) return
  uploadDragActive.value = false
}

async function onUploadDrop(event: DragEvent) {
  uploadDragActive.value = false
  const file = event.dataTransfer?.files?.[0]
  const question = currentQuestion.value
  if (!file || !question || !attempt.value) return
  await handlePickedFile(file, question)
}

async function uploadAnswerFile(
  file: File,
  questionId: number,
  successText: string,
  captureMode: 'camera' | 'album' | 'file' = 'file',
  replace = false
) {
  if (!attempt.value) return
  if (file.size > MAX_UPLOAD_BYTES) {
    ElMessage.warning('文件大小不能超过 20 MB')
    return
  }
  uploadingId.value = questionId
  try {
    const uploaded = await api.attempts.uploadAnswer(attempt.value.attemptId, file, attempt.value.subject)
    const item = { ...uploaded, captureMode }
    const question = attempt.value.questions.find((row) => row.questionId === questionId)
    const isAudio = question?.type === 'audio_upload'
    const existing = answerFiles(answers[questionId])
    const nextFiles = (isAudio || replace ? [item] : [...existing, item]).slice(
      0,
      MAX_ARTWORK_PHOTOS
    )
    const primary = nextFiles[0]
    answers[questionId] = {
      ...primary,
      ...(nextFiles.length > 1 ? { files: nextFiles } : {})
    }
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

async function removePhoto(index: number) {
  const question = currentQuestion.value
  if (!question) return
  const files = answerFiles(answers[question.questionId])
  const next = files.filter((_, itemIndex) => itemIndex !== index)
  if (!next.length) {
    answers[question.questionId] = {}
  } else {
    answers[question.questionId] = {
      ...next[0],
      ...(next.length > 1 ? { files: next } : {})
    }
  }
  const saved = await save(true)
  if (saved) ElMessage.success('已删除这张照片')
  else ElMessage.warning('照片已删除，但保存失败，请稍后重试')
}

function playAudio(url?: string) {
  if (!url) {
    ElMessage.warning('题目音频缺失，请联系老师重新上传')
    return
  }
  const audio = new Audio(url)
  audio.play().catch(() => ElMessage.warning('音频暂时无法播放，请检查文件是否存在'))
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
  stopCamera()
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
            <template v-if="currentQuestion.type === 'image_upload'">
              <div class="answer-photo-grid">
                <figure v-for="(photo, index) in currentAnswerFiles" :key="photo.fileId" class="answer-photo">
                  <img :src="photo.url" :alt="photo.name" />
                  <figcaption>
                    <span>{{ photo.captureMode === 'camera' ? '拍照' : '相册' }}</span>
                    <el-button link type="danger" size="small" @click="removePhoto(index)">删除</el-button>
                  </figcaption>
                </figure>
              </div>
              <div class="upload-file-meta">
                <b>已上传 {{ currentAnswerFiles.length }} / {{ MAX_ARTWORK_PHOTOS }} 张</b>
                <span>支持 JPG、PNG、WEBP，单张最大 10 MB</span>
              </div>
            </template>
            <template v-else>
              <img v-if="isImageFile(currentAnswerFile)" :src="currentAnswerFile.url" :alt="currentAnswerFile.name" class="upload-preview-image" />
              <audio v-else-if="isAudioFile(currentAnswerFile)" :src="currentAnswerFile.url" controls class="upload-preview-audio" />
              <div class="upload-file-meta">
                <b>{{ currentAnswerFile.name }}</b>
                <span>{{ (currentAnswerFile.size / 1024 / 1024).toFixed(2) }} MB</span>
              </div>
            </template>
            <div class="upload-file-actions">
              <label v-if="currentQuestion.type !== 'image_upload' || currentAnswerFiles.length < MAX_ARTWORK_PHOTOS" class="el-button el-button--default">
                <span>{{ currentQuestion.type === 'image_upload' ? '继续添加照片' : '重新上传' }}</span>
                <input type="file" :accept="currentQuestion.type === 'audio_upload' ? 'audio/*' : 'image/*'" @change="uploadFile" />
              </label>
              <el-button v-if="currentQuestion.type === 'audio_upload'" @click="startRecording">重新录音</el-button>
              <el-button v-if="currentQuestion.type === 'image_upload'" @click="openCamera(currentQuestion, true)">重拍</el-button>
              <el-button @click="removeUpload">移除全部</el-button>
            </div>
          </template>
          <div v-else class="answer-upload-options" :class="{ 'answer-upload-options--pair': currentQuestion.type === 'audio_upload' }">
            <label
              class="upload-zone answer-upload"
              :class="{ uploading: uploadingId === currentQuestion.questionId, 'is-dragover': uploadDragActive }"
              @dragover.prevent="onUploadDragOver"
              @dragenter.prevent="onUploadDragOver"
              @dragleave.prevent="onUploadDragLeave"
              @drop.prevent="onUploadDrop"
            >
              <b>{{ uploadingId === currentQuestion.questionId ? '正在上传并保存…' : uploadDragActive ? '松开即可上传作品' : '拖拽文件到这里，或点击上传' }}</b>
              <span>{{ currentQuestion.type === 'audio_upload' ? '支持 MP3、WAV、M4A、WEBM，最大 20 MB' : '支持 JPG、PNG、WEBP，最大 10 MB' }}</span>
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
            <button
              v-if="currentQuestion.type === 'image_upload'"
              type="button"
              class="answer-record"
              :disabled="uploadingId === currentQuestion.questionId"
              @click="openCamera(currentQuestion)"
            >
              <el-icon><Camera /></el-icon>
              <b>拍照上传作品</b>
              <span>摄像头 / 后置相机；无摄像头时可从相册选择</span>
            </button>
            <input
              ref="captureInput"
              class="hidden-input"
              type="file"
              accept="image/*"
              capture="environment"
              @change="uploadCaptureFile"
            />
          </div>
        </div>

      </article>
      <div class="attempt-actions">
        <el-button :disabled="currentIndex === 0" @click="currentIndex -= 1">上一题</el-button>
        <el-button :loading="saving" @click="save(false)">保存答案</el-button>
        <el-button :loading="saving" @click="saveAndExit">保存并退出</el-button>
        <el-button v-if="currentIndex < attempt.questions.length - 1" type="primary" @click="currentIndex += 1">下一题</el-button>
        <el-button v-else type="primary" :loading="submitting" @click="submit(false)">提交答卷</el-button>
      </div>
      <p class="autosave-note">答案每 15 秒自动保存；“保存并退出”后考试仍在计时，可从“我的测评”继续作答；倒计时结束时系统会自动交卷。</p>
      <aside class="question-nav" aria-label="答题卡">
        <div class="question-nav-head">
          <b>答题卡</b>
          <span>已答 {{ answeredCount }}/{{ attempt.questions.length }}</span>
        </div>
        <div class="question-nav-grid">
          <button
            v-for="(question, index) in attempt.questions"
            :key="question.questionId"
            type="button"
            :class="{ active: index === currentIndex, done: hasAnswer(question) }"
            :title="`第 ${index + 1} 题${hasAnswer(question) ? '（已答）' : '（未答）'}`"
            @click="goToQuestion(index)"
          >
            {{ index + 1 }}
          </button>
        </div>
        <div class="question-nav-legend">
          <span><i class="done" />已答</span>
          <span><i />未答</span>
          <span><i class="active" />当前题</span>
        </div>
      </aside>
    </main>
    <el-dialog v-model="cameraOpen" title="拍照上传作品" width="560px" @closed="stopCamera">
      <div class="camera-preview">
        <video ref="cameraVideo" autoplay playsinline muted></video>
      </div>
      <p class="camera-hint">
        请将纸质作品放平、光线均匀后拍摄；确认后会直接上传并保存答案。摄像头需要 HTTPS 或 localhost 环境，无摄像头时可从相册选择。
      </p>
      <template #footer>
        <el-button @click="cameraOpen = false">取消</el-button>
        <el-button type="primary" :loading="cameraLoading" @click="capturePhoto">拍摄</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.camera-preview {
  background: #0f172a;
  border-radius: 10px;
  overflow: hidden;
  aspect-ratio: 4 / 3;
  display: flex;
  align-items: center;
  justify-content: center;
}
.camera-preview video {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.camera-hint {
  margin: 10px 0 0;
  font-size: 12px;
  color: #667085;
  line-height: 1.6;
}
.hidden-input {
  display: none;
}
.answer-photo-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 8px;
}
.answer-photo {
  margin: 0;
  width: 150px;
  border: 1px solid #e5e9f0;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}
.answer-photo img {
  width: 100%;
  height: 110px;
  object-fit: cover;
  display: block;
}
.answer-photo figcaption {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  font-size: 11px;
  color: #667085;
}
</style>
