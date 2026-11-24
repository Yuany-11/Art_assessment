<script setup lang="ts">
defineProps<{
  label: string
  value: string | number
  note?: string
  tone?: 'blue' | 'green' | 'amber' | 'violet'
  to?: string
  clickable?: boolean
  active?: boolean
}>()

defineEmits<{ click: [] }>()
</script>

<template>
  <router-link v-if="to" class="metric-card metric-card--link" :class="`metric-card--${tone || 'blue'}`" :to="to">
    <span>{{ label }}</span>
    <strong>{{ value }}</strong>
    <small>{{ note }}</small>
    <slot />
  </router-link>
  <component
    :is="clickable ? 'button' : 'article'"
    v-else
    class="metric-card"
    :class="[
      `metric-card--${tone || 'blue'}`,
      { 'metric-card--clickable': clickable, 'metric-card--active': active }
    ]"
    :type="clickable ? 'button' : undefined"
    @click="clickable && $emit('click')"
  >
    <span>{{ label }}</span>
    <strong>{{ value }}</strong>
    <small>{{ note }}</small>
    <slot />
  </component>
</template>
