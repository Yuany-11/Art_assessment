<script setup lang="ts">
import { onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/api'
import { isEmail, EMAIL_MESSAGE } from '@/utils/email'

const router = useRouter()
const form = reactive({ nickname: '', email: '', code: '', password: '', confirmPassword: '' })
const submitting = ref(false)
const sending = ref(false)
const countdown = ref(0)
const errorMessage = ref('')
let timer: number | undefined

function validateEmailField(): string {
  const email = form.email.trim()
  if (!email) return '请输入邮箱'
  if (!isEmail(email)) return EMAIL_MESSAGE
  if (email.length > 64) return '邮箱长度不能超过 64 个字符'
  return ''
}

function validate(): string {
  const emailError = validateEmailField()
  if (emailError) return emailError
  const nickname = form.nickname.trim()
  if (!nickname) return '请输入昵称'
  if (nickname.length < 2) return '昵称至少 2 个字符'
  if (nickname.length > 30) return '昵称不能超过 30 个字符'
  if (!/^\d{6}$/.test(form.code.trim())) return '请输入 6 位数字验证码'
  if (form.password.length < 8 || form.password.length > 32) return '密码需为 8~32 位'
  if (!/[A-Za-z]/.test(form.password) || !/\d/.test(form.password)) return '密码需至少包含字母和数字'
  if (form.password !== form.confirmPassword) return '两次输入的密码不一致'
  return ''
}

function startCountdown() {
  countdown.value = 60
  timer = window.setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0 && timer) window.clearInterval(timer)
  }, 1000)
}

async function sendCode() {
  if (sending.value || countdown.value > 0) return
  const emailError = validateEmailField()
  if (emailError) {
    errorMessage.value = emailError
    return
  }
  sending.value = true
  errorMessage.value = ''
  try {
    await api.auth.sendRegisterCode(form.email.trim())
    ElMessage.success('验证码已发送，请查收邮箱')
    startCountdown()
  } catch (error) {
    errorMessage.value = (error as Error).message
  } finally {
    sending.value = false
  }
}

async function submit() {
  const message = validate()
  if (message) {
    errorMessage.value = message
    return
  }
  submitting.value = true
  errorMessage.value = ''
  try {
    await api.auth.register({
      nickname: form.nickname.trim(),
      email: form.email.trim(),
      code: form.code.trim(),
      password: form.password
    })
    localStorage.setItem('art-assessment-last-username', form.email.trim().toLowerCase())
    ElMessage.success('注册成功，请使用邮箱登录')
    await router.replace('/login')
  } catch (error) {
    errorMessage.value = (error as Error).message
  } finally {
    submitting.value = false
  }
}

onUnmounted(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<template>
  <div class="register-page">
    <section class="register-card">
      <div class="register-brand"><span>艺</span> 艺术素质测评系统</div>
      <h1>注册学生账号</h1>
      <p class="register-intro">填写昵称，通过邮箱验证码完成注册；注册后使用邮箱和密码登录。</p>

      <div class="register-fields">
        <label class="register-field">
          <span>昵称</span>
          <el-input v-model="form.nickname" maxlength="30" size="large" placeholder="请输入昵称" />
        </label>
        <label class="register-field">
          <span>邮箱</span>
          <div class="register-code-row">
            <el-input v-model="form.email" maxlength="64" size="large" placeholder="请输入邮箱地址" />
            <el-button size="large" :loading="sending" :disabled="countdown > 0" @click="sendCode">
              {{ countdown > 0 ? `重新获取(${countdown}s)` : '获取验证码' }}
            </el-button>
          </div>
        </label>
        <label class="register-field">
          <span>验证码</span>
          <el-input
            v-model="form.code"
            maxlength="6"
            inputmode="numeric"
            size="large"
            placeholder="请输入 6 位验证码"
            @input="form.code = form.code.replace(/\D/g, '').slice(0, 6)"
          />
        </label>
        <label class="register-field">
          <span>设置密码</span>
          <el-input
            v-model="form.password"
            type="password"
            show-password
            maxlength="32"
            size="large"
            placeholder="8~32 位，至少包含字母和数字"
          />
        </label>
        <label class="register-field">
          <span>再次输入密码</span>
          <el-input
            v-model="form.confirmPassword"
            type="password"
            show-password
            maxlength="32"
            size="large"
            placeholder="请再次输入密码"
          />
        </label>
      </div>

      <p v-if="errorMessage" class="login-error" role="alert">{{ errorMessage }}</p>
      <el-button type="primary" size="large" class="register-submit" :loading="submitting" @click="submit">注册</el-button>
      <p class="register-back">已有账号？<router-link to="/login">返回登录</router-link></p>
    </section>
  </div>
</template>

<style scoped>
.register-page {
  display: flex;
  min-height: 100vh;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  background:
    radial-gradient(circle at 12% 8%, rgba(143, 201, 237, 0.28), transparent 42%),
    radial-gradient(circle at 88% 92%, rgba(166, 156, 232, 0.24), transparent 45%),
    #f5f8fc;
}

.register-card {
  width: min(460px, 100%);
  padding: 34px 32px 26px;
  border: 1px solid var(--line);
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 24px 60px rgba(23, 43, 77, 0.12);
}

.register-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--ink);
  font-size: 15px;
  font-weight: 700;
}

.register-brand span {
  display: inline-flex;
  width: 32px;
  height: 32px;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: var(--primary);
  color: #fff;
  font-size: 18px;
}

.register-card h1 {
  margin: 18px 0 8px;
  color: var(--ink);
  font-size: 24px;
}

.register-intro {
  margin: 0 0 20px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.6;
}

.register-fields {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.register-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.register-field > span {
  color: var(--text);
  font-size: 13px;
  font-weight: 600;
}

.register-code-row {
  display: flex;
  gap: 10px;
}

.register-code-row .el-input {
  flex: 1;
}

.register-code-row .el-button {
  white-space: nowrap;
}

.register-submit {
  width: 100%;
  height: 46px;
  margin-top: 6px;
  border-radius: 12px;
}

.register-back {
  margin-top: 16px;
  color: var(--muted);
  font-size: 13px;
  text-align: center;
}

.register-back a {
  color: var(--primary-strong);
  font-weight: 600;
  text-decoration: none;
}
</style>
