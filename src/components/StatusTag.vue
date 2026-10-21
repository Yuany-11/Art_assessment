<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ value: string }>()
const labels: Record<string, string> = {
  active: '正常',
  disabled: '已禁用',
  draft: '草稿',
  ready: '已就绪',
  published: '已发布',
  archived: '已归档',
  withdrawn: '已撤回',
  finished: '已结束',
  pending: '待处理',
  in_progress: '答题中',
  submitted: '已提交',
  invalid: '已失效',
  grading: '评分中',
  approved: '已通过',
  rejected: '已驳回',
  offline: '已下架',
  generating: '生成中',
  graded: '已评分',
  failed: '失败',
  success: '成功'
}
const tone = computed(() => {
  if (['active', 'ready', 'published', 'approved', 'graded', 'success'].includes(props.value)) return 'success'
  if (['pending', 'generating', 'draft'].includes(props.value)) return 'warning'
  if (['failed', 'rejected', 'disabled', 'offline'].includes(props.value)) return 'danger'
  return 'info'
})
</script>

<template>
  <span class="status-tag" :class="`status-tag--${tone}`">{{ labels[value] ?? value }}</span>
</template>
