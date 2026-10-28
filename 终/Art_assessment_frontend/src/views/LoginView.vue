<script setup lang="ts">
import { ref } from 'vue'
import type { Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Collection, EditPen, Location, Lock, MapLocation, OfficeBuilding, School, User } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { api } from '@/api'
import type { Role } from '@/types'
import { defaultPathForRole } from '@/utils/roleRoute'

type LoginRole = { value: Role; label: string; mockAccount: string; demoAccount: string; icon: Component }

const MOCK_PASSWORD = 'Abc@123456'
// 本地联调演示账号统一密码（与后端 seed_demo / seed_demo_accounts 保持一致）
const DEMO_PASSWORD = 'Demo@123456'

const roles: LoginRole[] = [
  { value: 'student', label: '学生端', mockAccount: 'student2026001', demoAccount: 'student', icon: User },
  { value: 'teacher', label: '教师端', mockAccount: 'teacher1001', demoAccount: 'teacher', icon: EditPen },
  { value: 'school_admin', label: '学校管理', mockAccount: 'school301', demoAccount: 'school_admin', icon: School },
  { value: 'district_admin', label: '区县管理', mockAccount: 'district22', demoAccount: 'district_admin', icon: OfficeBuilding },
  { value: 'city_admin', label: '市州管理', mockAccount: 'city03', demoAccount: 'city_admin', icon: MapLocation },
  { value: 'province_admin', label: '省级管理', mockAccount: 'province01', demoAccount: 'province_admin', icon: Location },
  { value: 'question_admin', label: '题库管理', mockAccount: 'qbank01', demoAccount: 'question_admin', icon: Collection }
]
const rememberedUsername = localStorage.getItem('art-assessment-last-username') ?? ''
const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const mockMode = import.meta.env.VITE_USE_MOCK === 'true'
const username = ref(rememberedUsername)
const password = ref('')
const loading = ref(false)
const rememberAccount = ref(Boolean(rememberedUsername))

function accountFor(item: LoginRole) {
  return mockMode ? item.mockAccount : item.demoAccount
}

function fillAccount(item: LoginRole) {
  username.value = accountFor(item)
  password.value = mockMode ? MOCK_PASSWORD : DEMO_PASSWORD
  ElMessage.success(`已填入${item.label}测试账号`)
}

function redirectAfterLogin(role: Role) {
  const requested = typeof route.query.redirect === 'string' ? route.query.redirect : ''
  if (requested && requested.startsWith('/') && !requested.startsWith('//')) {
    const target = router.resolve(requested)
    const allowedRoles = target.meta.roles as Role[] | undefined
    if (allowedRoles?.includes(role)) return target.fullPath
  }
  return defaultPathForRole(role)
}

function trackArtPointer(event: PointerEvent) {
  const panel = event.currentTarget as HTMLElement
  const page = panel.closest('.login-page') as HTMLElement | null
  const rect = panel.getBoundingClientRect()
  const x = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width))
  const y = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height))
  panel.style.setProperty('--art-pointer-x', `${Math.round(x * 100)}%`)
  panel.style.setProperty('--art-pointer-y', `${Math.round(y * 100)}%`)
  panel.style.setProperty('--art-tilt-x', `${((0.5 - y) * 3).toFixed(2)}deg`)
  panel.style.setProperty('--art-tilt-y', `${((x - 0.5) * 3).toFixed(2)}deg`)
  page?.style.setProperty('--art-pointer-page-x', `${Math.round(x * 52)}%`)
  page?.style.setProperty('--art-pointer-page-y', `${Math.round(y * 100)}%`)
}

function resetArtPointer(event: PointerEvent) {
  const panel = event.currentTarget as HTMLElement
  const page = panel.closest('.login-page') as HTMLElement | null
  panel.style.setProperty('--art-pointer-x', '58%')
  panel.style.setProperty('--art-pointer-y', '48%')
  panel.style.setProperty('--art-tilt-x', '0deg')
  panel.style.setProperty('--art-tilt-y', '0deg')
  page?.style.setProperty('--art-pointer-page-x', '31%')
  page?.style.setProperty('--art-pointer-page-y', '48%')
}

async function submit() {
  if (!username.value.trim()) return ElMessage.warning('请输入登录账号')
  if (!password.value) return ElMessage.warning('请输入登录密码')
  loading.value = true
  try {
    let role: Role
    if (mockMode) {
      const demo = roles.find((item) => item.mockAccount.toLowerCase() === username.value.trim().toLowerCase())
      if (!demo) throw new Error('演示账号不存在，请点击下方测试账号按钮填入')
      if (password.value !== MOCK_PASSWORD) throw new Error(`演示账号密码为 ${MOCK_PASSWORD}`)
      role = demo.value
      auth.login(role)
    } else {
      const session = await api.auth.login(username.value, password.value)
      role = session.user.role
      auth.setSession(role, session.user, session.token, session.refreshToken)
    }
    if (rememberAccount.value) localStorage.setItem('art-assessment-last-username', username.value.trim())
    else localStorage.removeItem('art-assessment-last-username')
    ElMessage.success(`登录成功，正在进入${roles.find((item) => item.value === role)?.label ?? ''}`)
    await router.replace(redirectAfterLogin(role))
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <section class="login-visual" @pointermove="trackArtPointer" @pointerleave="resetArtPointer">
      <div class="visual-atmosphere" aria-hidden="true">
        <span class="visual-aurora visual-aurora--blue"></span>
        <span class="visual-aurora visual-aurora--violet"></span>
        <span class="art-pointer-glow"></span>
        <span class="art-color-bloom art-color-bloom--blue"></span>
        <span class="art-color-bloom art-color-bloom--gold"></span>
        <svg class="flow-trails" viewBox="0 0 900 1000" preserveAspectRatio="xMidYMid slice">
          <defs>
            <linearGradient id="trail-gold" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0" stop-color="#e8c58d" stop-opacity="0" />
              <stop offset="0.42" stop-color="#f2d6a6" stop-opacity="0.72" />
              <stop offset="0.72" stop-color="#e8c58d" stop-opacity="0.38" />
              <stop offset="1" stop-color="#e8c58d" stop-opacity="0" />
            </linearGradient>
            <linearGradient id="trail-blue" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0" stop-color="#8fc9ed" stop-opacity="0" />
              <stop offset="0.46" stop-color="#c6e4f7" stop-opacity="0.58" />
              <stop offset="0.76" stop-color="#a69ce8" stop-opacity="0.3" />
              <stop offset="1" stop-color="#a69ce8" stop-opacity="0" />
            </linearGradient>
            <linearGradient id="trail-violet" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0" stop-color="#a69ce8" stop-opacity="0" />
              <stop offset="0.5" stop-color="#ddd5f6" stop-opacity="0.5" />
              <stop offset="1" stop-color="#8fc9ed" stop-opacity="0" />
            </linearGradient>
            <filter id="ribbon-soft-glow" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="13" />
            </filter>
          </defs>
          <path
            class="art-ribbon art-ribbon--halo"
            d="M-140 850 C120 760 70 570 330 500 S640 320 980 120"
            pathLength="1"
            stroke="url(#trail-gold)"
            filter="url(#ribbon-soft-glow)"
          />
          <path
            class="art-ribbon art-ribbon--core"
            d="M-140 850 C120 760 70 570 330 500 S640 320 980 120"
            pathLength="1"
            stroke="url(#trail-gold)"
          />
          <path
            class="art-ribbon art-ribbon--blue"
            d="M-160 620 C100 500 220 690 420 480 S700 210 1020 260"
            pathLength="1"
            stroke="url(#trail-blue)"
          />
          <circle class="ribbon-mote ribbon-mote--gold" r="5" fill="#ffe4b4" filter="url(#ribbon-soft-glow)">
            <animateMotion
              dur="7.5s"
              begin="-1.5s"
              repeatCount="indefinite"
              path="M-140 850 C120 760 70 570 330 500 S640 320 980 120"
            />
          </circle>
          <circle class="ribbon-mote ribbon-mote--soft" r="3.2" fill="#fff1d2">
            <animateMotion
              dur="10.5s"
              begin="-5s"
              repeatCount="indefinite"
              path="M-140 850 C120 760 70 570 330 500 S640 320 980 120"
            />
          </circle>
          <circle class="ribbon-mote ribbon-mote--blue" r="3.8" fill="#d6efff">
            <animateMotion
              dur="9s"
              begin="-3s"
              repeatCount="indefinite"
              path="M-160 620 C100 500 220 690 420 480 S700 210 1020 260"
            />
          </circle>
          <g class="flow-trail flow-trail--gold">
            <path class="flow-trail-glow" d="M-140 850 C120 760 70 570 330 500 S640 320 980 120" pathLength="1" stroke="url(#trail-gold)" />
            <path class="flow-trail-line" d="M-140 850 C120 760 70 570 330 500 S640 320 980 120" pathLength="1" stroke="url(#trail-gold)" />
          </g>
          <g class="flow-trail flow-trail--blue">
            <path class="flow-trail-glow" d="M-160 620 C100 500 220 690 420 480 S700 210 1020 260" pathLength="1" stroke="url(#trail-blue)" />
            <path class="flow-trail-line" d="M-160 620 C100 500 220 690 420 480 S700 210 1020 260" pathLength="1" stroke="url(#trail-blue)" />
          </g>
          <g class="flow-trail flow-trail--violet">
            <path class="flow-trail-line" d="M-100 970 C180 840 340 900 480 700 S630 390 960 410" pathLength="1" stroke="url(#trail-violet)" />
          </g>
        </svg>
        <span class="paper-crane paper-crane--one"><i></i></span>
        <span class="paper-crane paper-crane--two"><i></i></span>
        <span class="brush-stroke brush-stroke--one"></span>
        <span class="brush-stroke brush-stroke--two"></span>
        <span class="visual-note visual-note--one">♪</span>
        <span class="visual-note visual-note--two">♫</span>
        <span class="visual-note visual-note--three">♩</span>
        <i v-for="particle in 8" :key="particle" class="visual-particle" :class="`visual-particle--${particle}`"></i>
        <i v-for="spark in 14" :key="`spark-${spark}`" class="art-spark" :class="`art-spark--${spark}`"></i>
      </div>
      <div class="login-brand"><span>艺</span> 艺术素质测评系统</div>
      <div class="visual-copy">
        <span class="visual-badge">教育艺术素质测评平台</span>
        <h1>让每一次测评<br />都有清晰的成长路径</h1>
        <p>连接课堂、测评与成长数据，为学校和教育管理部门提供清晰、可信的艺术素质评价体验。</p>
      </div>
      <div class="visual-footnote"><span></span>统一登录入口 · 多级权限协同</div>
    </section>
    <section class="login-panel">
      <div class="login-form">
        <p class="eyebrow">{{ mockMode ? '演示账号登录' : '统一登录' }}</p>
        <h2>欢迎回来</h2>
        <p class="muted login-intro">直接输入账号和密码即可登录，系统会根据账号角色自动进入对应工作端。</p>

        <div class="login-fields">
          <label class="login-field">
            <span>登录账号</span>
            <el-input
              v-model="username"
              :prefix-icon="User"
              placeholder="请输入登录账号或学籍号"
              size="large"
              autocomplete="username"
              @keyup.enter="submit"
            />
          </label>
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
          <span>{{ mockMode ? '演示密码' : '测试密码' }}：{{ mockMode ? MOCK_PASSWORD : DEMO_PASSWORD }}</span>
        </div>
        <el-button type="primary" size="large" class="login-submit" :loading="loading" @click="submit">登录</el-button>
        <p class="login-help">登录即表示你同意遵守平台数据安全和隐私保护要求。</p>

        <div class="login-quick">
          <div class="login-quick-head">
            <b>测试账号</b>
            <span>点击按钮填入对应工作端的账号密码</span>
          </div>
          <div class="login-quick-grid">
            <button
              v-for="role in roles"
              :key="role.value"
              type="button"
              :aria-label="`填入${role.label}测试账号`"
              @click="fillAccount(role)"
            >
              <el-icon><component :is="role.icon" /></el-icon>
              <span>{{ role.label }}</span>
              <small>{{ accountFor(role) }}</small>
            </button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
