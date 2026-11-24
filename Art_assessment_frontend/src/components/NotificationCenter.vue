<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Bell, Check } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { api } from '@/api'
import type { NotificationItem } from '@/types'

const router = useRouter()
const open = ref(false)
const loading = ref(false)
const unreadOnly = ref(false)
const items = ref<NotificationItem[]>([])
const unreadCount = ref(0)
let timer: number | undefined

const typeLabels: Record<string, string> = {
  paper_review_submitted: '试卷待审核',
  paper_review_approved: '试卷审核通过',
  paper_review_rejected: '试卷审核驳回',
  question_review_approved: '试题审核通过',
  question_review_rejected: '试题审核驳回',
  system: '系统通知'
}

async function load(silent = false) {
  if (!silent) loading.value = true
  try {
    const result = await api.notifications.list({ unreadOnly: unreadOnly.value, pageNum: 1, pageSize: 50 })
    items.value = result.list
    unreadCount.value = result.unreadCount
  } catch (error) {
    if (!silent) ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function openCenter() {
  open.value = true
  await load()
}

async function read(item: NotificationItem) {
  try {
    if (!item.read) {
      await api.notifications.read(item.id)
      item.read = true
      unreadCount.value = Math.max(0, unreadCount.value - 1)
    }
    if (item.link?.startsWith('/')) {
      open.value = false
      await router.push(item.link)
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function readAll() {
  try {
    const result = await api.notifications.readAll()
    items.value.forEach((item) => { item.read = true })
    unreadCount.value = 0
    ElMessage.success(`已将 ${result.updatedCount} 条通知标记为已读`)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

onMounted(() => {
  load(true)
  timer = window.setInterval(() => load(true), 60_000)
})

onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <button class="notification-trigger" title="通知中心" @click="openCenter">
    <el-badge :value="unreadCount" :hidden="unreadCount === 0" :max="99">
      <el-icon><Bell /></el-icon>
    </el-badge>
  </button>
  <el-drawer v-model="open" title="通知中心" size="480px" append-to-body>
    <div class="notification-toolbar">
      <el-radio-group v-model="unreadOnly" size="small" @change="load()">
        <el-radio-button :value="false">全部</el-radio-button>
        <el-radio-button :value="true">未读</el-radio-button>
      </el-radio-group>
      <el-button text :icon="Check" :disabled="unreadCount === 0" @click="readAll">全部已读</el-button>
    </div>
    <div v-loading="loading" class="notification-list">
      <button v-for="item in items" :key="item.id" class="notification-item" :class="{ unread: !item.read }" @click="read(item)">
        <span class="notification-dot"></span>
        <div>
          <div class="notification-item-head"><b>{{ item.title }}</b><small>{{ item.createdAt.replace('T', ' ').slice(5, 16) }}</small></div>
          <p>{{ item.content }}</p>
          <span class="notification-type">{{ typeLabels[item.type] ?? item.type }}</span>
        </div>
      </button>
      <div v-if="!items.length && !loading" class="notification-empty">暂无通知</div>
    </div>
  </el-drawer>
</template>
