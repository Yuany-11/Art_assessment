<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Lock, User } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { api } from '@/api'
import type { Role } from '@/types'

const roles: Array<{ value: Role; label: string; desc: string; account: string }> = [
  { value: 'student', label: '学生端', desc: '测评、练习与个人成果', account: 'student2026001' },
  { value: 'teacher', label: '教师端', desc: '班级、组卷、发布与成绩', account: 'teacher1001' },
  { value: 'school_admin', label: '学校管理', desc: '教师、学生与校级测评', account: 'school301' },
  { value: 'district_admin', label: '区县管理', desc: '学校账号与区域统计', account: 'district22' },
  { value: 'city_admin', label: '市州管理', desc: '区县、直属学校与统计', account: 'city03' },
  { value: 'province_admin', label: '省级管理', desc: '全省账号、测评与统计', account: 'province01' },
  { value: 'question_admin', label: '题库管理', desc: '试题、课程、资源与审核', account: 'qbank01' }
]
const rememberedUsername = localStorage.getItem('art-assessment-last-username') ?? ''
const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const selected = ref<Role>('school_admin')
const username = ref(rememberedUsername || 'school301')
const password = ref('Abc@123456')
const loading = ref(false)
const rememberAccount = ref(Boolean(rememberedUsername))
const mockMode = import.meta.env.VITE_USE_MOCK !== 'false'
const step = ref<1 | 2>(1)
const selectedRole = computed(() => roles.find((item) => item.value === selected.value) ?? roles[2])
const accountRoleHint = computed(() => {
  const matched = roles.find((item) => item.account.toLowerCase() === username.value.trim().toLowerCase())
  return matched && matched.value !== selected.value ? matched : null
})

function selectRole(role: Role) {
  selected.value = role
  if (mockMode) {
    username.value = roles.find((item) => item.value === role)?.account ?? ''
    password.value = 'Abc@123456'
  } else {
    username.value = rememberedUsername
    password.value = ''
  }
  step.value = 2
}

async function submit() {
  if (!username.value.trim()) return ElMessage.warning('请输入登录账号')
  if (!password.value) return ElMessage.warning('请输入登录密码')
  loading.value = true
  try {
    if (mockMode) {
      const demo = roles.find((item) => item.account.toLowerCase() === username.value.trim().toLowerCase())
      if (!demo) throw new Error('演示账号不存在，请点击右侧身份卡自动填入账号')
      if (demo.value !== selected.value) throw new Error('登录身份与账号不匹配')
      if (password.value !== 'Abc@123456') throw new Error('演示账号密码为 Abc@123456')
      auth.login(selected.value)
    } else {
      const session = await api.auth.login(username.value, password.value, selected.value)
      auth.setSession(session.user.role, session.user, session.token, session.refreshToken)
    }
    if (rememberAccount.value) localStorage.setItem('art-assessment-last-username', username.value.trim())
    else localStorage.removeItem('art-assessment-last-username')
    ElMessage.success('登录成功')
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : selected.value === 'student' ? '/student/home' : '/dashboard'
    await router.replace(redirect)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  if (!mockMode) return
  const matched = roles.find((item) => item.account.toLowerCase() === username.value.trim().toLowerCase())
  if (matched) selected.value = matched.value
})
</script>

<template>
  <div class="login-page">
    <section class="login-visual">
      <div class="login-brand"><span>艺</span> 艺术素质测评系统</div>
      <div class="visual-copy">
        <span class="visual-badge">教育艺术素质测评平台</span>
        <h1>让每一次测评<br />都有清晰的成长路径</h1>
        <p>连接课堂、测评与成长数据，为学校和教育管理部门提供清晰、可信的艺术素质评价体验。</p>
      </div>
      <div class="visual-footnote"><span></span>统一登录入口 · 多级权限协同</div>
    </section>
    <section class="login-panel">
      <div class="login-form" :class="{ 'login-form--login': step === 2 }">
        <div class="login-steps">
          <div :class="{ active: step === 1, complete: step === 2 }"><b>01</b><span>选择端</span></div>
          <i></i>
          <div :class="{ active: step === 2 }"><b>02</b><span>账号登录</span></div>
        </div>

        <template v-if="step === 1">
          <p class="eyebrow">选择工作端</p>
          <h2>选择你要进入的端</h2>
          <p class="muted">先选择学生端或对应管理端，再使用该端账号完成登录。</p>
          <div class="login-role-heading">
            <b>可用工作端</b>
            <span>共 {{ roles.length }} 个入口</span>
          </div>
          <div class="role-grid role-grid--entry">
            <button v-for="role in roles" :key="role.value" :class="{ active: selected === role.value }" @click="selectRole(role.value)">
              <b>{{ role.label }}</b>
              <span>{{ role.desc }}</span>
            </button>
          </div>
          <div class="login-entry-tip"><span>选择身份后，下一步输入对应账号和密码。</span></div>
        </template>

        <template v-else>
          <button class="login-back" @click="step = 1"><el-icon><ArrowLeft /></el-icon>返回选择端</button>
          <div class="login-role-context">
            <span>{{ selectedRole.label }}</span>
            <small>{{ selectedRole.desc }}</small>
          </div>
          <p class="eyebrow">{{ mockMode ? '演示账号登录' : '账号登录' }}</p>
          <h2>登录{{ selectedRole.label }}</h2>
          <p class="muted">{{ mockMode ? '当前端演示账号已自动填入，也可以手动修改。' : '请输入该端账号和密码。' }}</p>
          <div class="login-fields">
            <label class="login-field">
              <span>登录账号</span>
              <el-input
                v-model="username"
                :prefix-icon="User"
                placeholder="请输入登录账号或学籍号"
                size="large"
                autocomplete="username"
              />
            </label>
            <p v-if="accountRoleHint" class="account-role-warning">
              该账号属于{{ accountRoleHint.label }}，请返回并选择对应端。
            </p>
            <label class="login-field">
              <span>登录密码</span>
              <el-input
                v-model="password"
                :prefix-icon="Lock"
                type="password"
                show-password
                placeholder="请输入登录密码"
                size="large"
                autocomplete="current-password"
                @keyup.enter="submit"
              />
            </label>
          </div>
          <div class="login-options">
            <el-checkbox v-model="rememberAccount">记住账号</el-checkbox>
            <span v-if="mockMode">演示密码：Abc@123456</span>
            <span v-else>忘记密码请联系管理员</span>
          </div>
          <el-button type="primary" size="large" class="login-submit" :loading="loading" @click="submit">登录{{ selectedRole.label }}</el-button>
          <p class="login-help">登录即表示你同意遵守平台数据安全和隐私保护要求。</p>
        </template>
      </div>
    </section>
  </div>
</template>
