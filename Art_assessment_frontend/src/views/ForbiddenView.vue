<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { defaultPathForRole } from '@/utils/roleRoute'

const auth = useAuthStore()
const homePath = computed(() => defaultPathForRole(auth.role))
const homeLabel = computed(() => (auth.role === 'student' ? '返回我的学习' : '返回工作台'))
</script>

<template>
  <div class="empty-page">
    <strong>403</strong>
    <h1>当前角色无权访问此页面</h1>
    <router-link :to="homePath">{{ homeLabel }}</router-link>
  </div>
</template>
