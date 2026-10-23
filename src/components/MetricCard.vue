<script setup lang="ts">
defineProps<{
  label: string
  value: string | number
  note?: string
  tone?: 'blue' | 'green' | 'amber' | 'violet'
}>()
</script>

<template>
  <article class="metric-card" :class="`metric-card--${tone || 'blue'}`">
    <span>{{ label }}</span>
    <strong>{{ value }}</strong>
    <small>{{ note }}</small>
  </article>
</template>
