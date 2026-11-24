<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { api } from '@/api'
import type { AudioTags } from '@/types'

const props = withDefaults(defineProps<{
  tags?: AudioTags | null
  fileId?: number | null
  showReference?: boolean
  canAnalyze?: boolean
  title?: string
  maxScore?: number | null
}>(), {
  tags: null,
  fileId: null,
  showReference: false,
  canAnalyze: true,
  title: '音频参考分析',
  maxScore: null
})

const emit = defineEmits<{ analyzed: [tags: AudioTags] }>()
const loading = ref(false)
const current = computed(() => props.tags)
const completed = computed(() => current.value?.status === 'completed')
const canRun = computed(() => Boolean(props.fileId) && props.canAnalyze)
// 置信度低于阈值时不硬给确定标签，提示教师人工判断。
const lowConfidence = computed(() => {
  const item = current.value
  if (!item || item.status !== 'completed') return false
  const values = [item.genreConfidence, item.emotionConfidence, item.modeConfidence]
    .filter((value): value is number => typeof value === 'number')
  return values.length > 0 && Math.min(...values) < 0.4
})
// 模型参考分是 0–100 口径，展示时按本题满分折算，避免教师看到的分数和题目分值不一致。
const convertedReference = computed(() => {
  const raw = current.value?.referenceScore
  if (raw === null || raw === undefined || !props.maxScore) return null
  return Math.round((raw / 100) * props.maxScore * 100) / 100
})

async function run() {
  if (!props.fileId || loading.value) return
  loading.value = true
  try {
    const result = await api.files.analyzeAudio(props.fileId, completed.value)
    emit('analyzed', result)
    ElMessage.success('音频标签已更新')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="audio-tag-card">
    <div class="audio-tag-head">
      <b>{{ title }}</b>
      <span class="audio-tag-status" :class="`is-${current?.status || 'pending'}`">
        {{ current?.status === 'completed' ? '已分析' : current?.status === 'failed' ? '分析失败' : '待分析' }}
      </span>
      <el-button
        v-if="canRun"
        link
        type="primary"
        size="small"
        :icon="Refresh"
        :loading="loading"
        @click="run"
      >{{ completed ? '重新分析' : '生成标签' }}</el-button>
    </div>

    <div v-if="completed" class="audio-tag-body">
      <span class="tag-chip">曲风 {{ current?.genreLabel || current?.genre || '—' }}<small v-if="current?.genreConfidence">{{ Math.round(current.genreConfidence * 100) }}%</small></span>
      <span class="tag-chip">情绪 {{ current?.emotionLabel || current?.emotion || '—' }}<small v-if="current?.emotionConfidence">{{ Math.round(current.emotionConfidence * 100) }}%</small></span>
      <span class="tag-chip">调式 {{ current?.modeLabel || current?.mode || '—' }}</span>
      <span class="tag-chip">BPM {{ current?.bpm ? Math.round(current.bpm) : '—' }}<small>估计值</small></span>
      <span v-if="current?.key" class="tag-chip">调性 {{ current.key }}</span>
      <span v-if="lowConfidence" class="tag-chip tag-chip--uncertain">不确定，建议人工判断</span>
      <span v-if="current?.segments && current.segments > 1" class="tag-chip">分段 <small>{{ current.segments }} 段聚合</small></span>
      <span v-if="showReference && current?.referenceScore !== null && current?.referenceScore !== undefined" class="tag-chip tag-chip--score">
        <template v-if="convertedReference !== null">
          参考分 {{ convertedReference }} / {{ maxScore }}<small>原始 {{ current.referenceScore }}/100{{ current.referenceGrade ? ` · ${current.referenceGrade}` : '' }}</small>
        </template>
        <template v-else>
          规则参考分 {{ current.referenceScore }}<small>{{ current.referenceGrade }}</small>
        </template>
      </span>
    </div>
    <p v-else-if="current?.status === 'failed'" class="audio-tag-tip is-error">
      {{ current.errorMessage || '分析服务暂时不可用，请稍后重试。' }}
    </p>
    <p v-else class="audio-tag-tip">尚未生成标签。标签用于检索与教学参考，不影响本题得分。</p>
    <p v-if="current?.disclaimer" class="audio-tag-disclaimer">{{ current.disclaimer }}</p>
  </div>
</template>

<style scoped>
.audio-tag-card {
  border: 1px solid #e5e9f0;
  border-radius: 10px;
  padding: 10px 12px;
  background: #f8fafc;
}
.audio-tag-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #344054;
}
.audio-tag-head b { flex: 1; font-weight: 600; }
.audio-tag-status {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 999px;
  background: #eef1f6;
  color: #667085;
}
.audio-tag-status.is-completed { background: #e8f6ee; color: #1f7a46; }
.audio-tag-status.is-failed { background: #fdecec; color: #b42318; }
.audio-tag-body {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.tag-chip {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  font-size: 12px;
  color: #344054;
  background: #fff;
  border: 1px solid #e5e9f0;
  border-radius: 6px;
  padding: 3px 8px;
}
.tag-chip small { color: #98a2b3; font-size: 11px; }
.tag-chip--score { border-color: #f3d9a4; background: #fffaef; color: #8a5a00; }
.tag-chip--uncertain { border-color: #f3d9a4; background: #fff8e6; color: #8a5a00; }
.audio-tag-tip { margin: 8px 0 0; font-size: 12px; color: #667085; }
.audio-tag-tip.is-error { color: #b42318; }
.audio-tag-disclaimer { margin: 6px 0 0; font-size: 11px; color: #98a2b3; line-height: 1.5; }
</style>
