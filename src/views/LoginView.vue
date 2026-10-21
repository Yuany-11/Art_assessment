<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { api } from '@/api'
import type { Role } from '@/types'

const roles: Array<{ value: Role; label: string; desc: string }> = [
  { value: 'student', label: '学生端', desc: '测评、练习与个人成果' },
  { value: 'teacher', label: '教师端', desc: '班级、组卷、发布与成绩' },
  { value: 'school_admin', label: '学校管理', desc: '教师、学生与校级测评' },
  { value: 'district_admin', label: '区县管理', desc: '学校账号与区域统计' },
  { value: 'city_admin', label: '市州管理', desc: '区县、直属学校与统计' },
  { value: 'province_admin', label: '省级管理', desc: '全省账号、测评与统计' },
  { value: 'question_admin', label: '题库管理', desc: '试题、课程、资源与审核' }
]
const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const selected = ref<Role>('school_admin')
const username = ref('school301')
const password = ref('Abc@123456')
const loading = ref(false)
const mockMode = import.meta.env.VITE_USE_MOCK !== 'false'

async function submit() {
  loading.value = true
  try {
    if (mockMode) {
      auth.login(selected.value)
    } else {
      if (!username.value.trim() || !password.value) throw new Error('请输入登录账号和密码')
      const session = await api.auth.login(username.value, password.value, selected.value)
      auth.setSession(session.user.role, session.user, session.token, session.refreshToken)
    }
    ElMessage.success(mockMode ? '已进入演示工作台' : '登录成功')
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : selected.value === 'student' ? '/student/home' : '/dashboard'
    await router.replace(redirect)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}
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
      <div class="login-form">
        <p class="eyebrow">演示登录</p>
        <h2>选择你的工作角色</h2>
        <p class="muted">{{ mockMode ? '当前为本地 Mock 模式，不需要后端即可操作。' : '使用后端账号登录，角色必须与账号一致。' }}</p>
        <div v-if="!mockMode" class="login-fields">
          <el-input v-model="username" placeholder="登录账号或学籍号" size="large" />
          <el-input v-model="password" type="password" show-password placeholder="登录密码" size="large" @keyup.enter="submit" />
        </div>
        <div class="role-grid">
          <button v-for="role in roles" :key="role.value" :class="{ active: selected === role.value }" @click="selected = role.value">
            <b>{{ role.label }}</b>
            <span>{{ role.desc }}</span>
          </button>
        </div>
        <el-button type="primary" size="large" class="login-submit" :loading="loading" @click="submit">进入工作台</el-button>
        <p class="login-help">如账号无法登录，请联系所属学校或教育管理部门。</p>
      </div>
    </section>
  </div>
</template>
