<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { api } from '@/api'
import MetricCard from '@/components/MetricCard.vue'

const auth = useAuthStore()

interface DashboardSummary {
  month: string
  pendingPublishPapers: number | null
  runningAssessments: number | null
  pendingQuestions: number | null
  pendingReviewPapers: number | null
  participationRate: number | null
}

const summary = ref<DashboardSummary | null>(null)

async function loadSummary() {
  try {
    summary.value = await api.dashboard.summary()
  } catch {
    summary.value = null
  }
}

function metric(value: number | null | undefined, suffix = '') {
  return value === null || value === undefined ? '—' : `${value}${suffix}`
}

onMounted(loadSummary)

interface TodoItem {
  id: string
  text: string
  createdAt: string
}

const todoInput = ref('')
const todos = ref<TodoItem[]>([])
const todoStorageKey = computed(
  () => `art-assessment-todos:${auth.user?.id ?? auth.role ?? 'guest'}`
)

function loadTodos() {
  try {
    const raw = localStorage.getItem(todoStorageKey.value)
    todos.value = raw ? (JSON.parse(raw) as TodoItem[]) : []
  } catch {
    todos.value = []
  }
}

function saveTodos() {
  localStorage.setItem(todoStorageKey.value, JSON.stringify(todos.value))
}

function addTodo() {
  const text = todoInput.value.trim()
  if (!text) return
  todos.value.unshift({
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    text,
    createdAt: new Date().toISOString()
  })
  todoInput.value = ''
  saveTodos()
}

function removeTodo(id: string) {
  todos.value = todos.value.filter((item) => item.id !== id)
  saveTodos()
}

watch(todoStorageKey, loadTodos, { immediate: true })
const quickActions = computed(() => {
  if (auth.role === 'question_admin') return [
    { title: '试题管理', text: '查询、创建与审核试题', path: '/qbank/questions' },
    { title: '课程章节', text: '维护课程与章节结构', path: '/qbank/courses' },
    { title: '操作日志', text: '追踪题库操作记录', path: '/logs' }
  ]
  return [
    { title: '组卷管理', text: '创建、编辑和下载测评试卷', path: '/papers' },
    { title: '测评发布', text: '按组织与年级发布测评', path: '/assessments' },
    { title: '数据统计', text: '查看区域参与率和成绩分布', path: '/statistics' }
  ]
})
</script>

<template>
  <div class="stack">
    <section class="hero-card">
      <div>
        <span class="eyebrow">{{ auth.user?.roleName }}工作台</span>
        <h2>{{ auth.user?.realName }}，今天从这里开始</h2>
        <p>当前账号的数据范围和功能入口已经就绪。</p>
      </div>
    </section>

    <section class="metrics-grid">
      <MetricCard
        label="待发布试卷"
        :value="metric(summary?.pendingPublishPapers)"
        note="草稿与已就绪 · 点击进入"
        tone="blue"
        to="/papers"
      />
      <MetricCard
        v-if="auth.role !== 'question_admin'"
        label="进行中测评"
        :value="metric(summary?.runningAssessments)"
        note="未结束的已发布测评 · 点击进入"
        tone="green"
        to="/assessments"
      />
      <template v-if="auth.role === 'question_admin'">
        <MetricCard
          label="待审核试题"
          :value="metric(summary?.pendingQuestions)"
          note="题库审核队列 · 点击进入"
          tone="amber"
          to="/qbank/questions?status=pending"
        />
        <MetricCard
          label="待审核试卷"
          :value="metric(summary?.pendingReviewPapers)"
          note="试卷审核 · 点击进入"
          tone="violet"
          to="/paper-review"
        />
      </template>
      <MetricCard
        v-else
        label="组卷管理"
        value="查看"
        note="创建、编辑和下载试卷 · 点击进入"
        tone="violet"
        to="/papers"
      />
      <MetricCard
        v-if="auth.role !== 'question_admin'"
        label="本月参与率"
        :value="metric(summary?.participationRate, '%')"
        :note="`${summary?.month || '本月'} 在册学生参与 · 查看统计`"
        tone="violet"
        to="/statistics"
      />
    </section>

    <section class="content-grid">
      <article class="panel">
        <div class="panel-head"><h3>快捷入口</h3><span>常用功能</span></div>
        <div class="quick-list">
          <router-link v-for="item in quickActions" :key="item.path" :to="item.path">
            <div><b>{{ item.title }}</b><span>{{ item.text }}</span></div>
            <span>→</span>
          </router-link>
        </div>
      </article>
      <article class="panel">
        <div class="panel-head"><h3>今日待办</h3><span>{{ todos.length }} 项</span></div>
        <div class="todo-add">
          <el-input
            v-model="todoInput"
            placeholder="输入待办内容，回车即可添加"
            maxlength="100"
            @keyup.enter="addTodo"
          />
          <el-button type="primary" :disabled="!todoInput.trim()" @click="addTodo">添加</el-button>
        </div>
        <ul v-if="todos.length" class="todo-list">
          <li v-for="item in todos" :key="item.id">
            <span class="todo-dot blue"></span>
            <div><b>{{ item.text }}</b><small>{{ item.createdAt.slice(0, 10) }}</small></div>
            <el-button link type="danger" size="small" @click="removeTodo(item.id)">删除</el-button>
          </li>
        </ul>
        <el-empty v-else description="暂无待办，添加一条吧" :image-size="54" />
      </article>
    </section>
  </div>
</template>
