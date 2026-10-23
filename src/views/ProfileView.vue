<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import PageHeader from '@/components/PageHeader.vue'
import { api } from '@/api'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const saving = ref(false)
const passwordOpen = ref(false)
const passwordForm = reactive({ oldPassword: '', newPassword: '', confirmPassword: '' })
const form = reactive({
  realName: auth.user?.realName ?? '',
  gender: 'unknown',
  phone: '13800000001',
  email: '',
  avatarUrl: auth.user?.avatarUrl ?? ''
})

async function save() {
  if (!form.realName.trim()) return ElMessage.warning('姓名不能为空')
  saving.value = true
  try {
    await api.profile.update({ ...form })
    auth.updateProfile({ realName: form.realName, avatarUrl: form.avatarUrl || null })
    ElMessage.success('个人信息已更新')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    saving.value = false
  }
}

async function changePassword() {
  if (!passwordForm.oldPassword || passwordForm.newPassword.length < 8) return ElMessage.warning('请填写旧密码，新密码至少 8 位')
  if (passwordForm.newPassword !== passwordForm.confirmPassword) return ElMessage.warning('两次输入的新密码不一致')
  try {
    const result = await api.profile.changePassword(passwordForm.oldPassword, passwordForm.newPassword)
    passwordOpen.value = false
    if (result.reloginRequired) {
      auth.logout()
      location.href = '/login'
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}
</script>

<template>
  <div class="stack profile-page">
    <PageHeader title="个人信息" description="管理本人资料和登录密码；角色、学校及学籍信息不可自行修改。" />
    <section class="profile-card">
      <aside class="profile-summary">
        <div class="profile-avatar">{{ auth.user?.realName.slice(0, 1) }}</div>
        <h2>{{ auth.user?.realName }}</h2>
        <span>{{ auth.user?.roleName }}</span>
        <p>{{ auth.user?.schoolName || auth.user?.cityName || '题库全域' }}</p>
        <div class="profile-meta">
          <div><small>登录账号</small><b>{{ auth.user?.username }}</b></div>
          <div v-if="auth.role === 'student'"><small>学籍号</small><b>S20260001</b></div>
          <div v-if="auth.role === 'student'"><small>班级</small><b>{{ auth.user?.className }}</b></div>
          <div v-if="auth.role === 'teacher'"><small>任教学科</small><b>音乐</b></div>
        </div>
      </aside>
      <main class="profile-form">
        <h3>基本资料</h3>
        <el-form label-position="top" class="form-grid">
          <el-form-item label="姓名"><el-input v-model="form.realName" /></el-form-item>
          <el-form-item label="性别"><el-select v-model="form.gender"><el-option label="男" value="male" /><el-option label="女" value="female" /><el-option label="未填写" value="unknown" /></el-select></el-form-item>
          <el-form-item label="手机号"><el-input v-model="form.phone" /></el-form-item>
          <el-form-item label="邮箱"><el-input v-model="form.email" placeholder="未填写" /></el-form-item>
          <el-form-item label="头像地址" class="span-2"><el-input v-model="form.avatarUrl" placeholder="上传后返回的文件访问地址" /></el-form-item>
        </el-form>
        <div class="profile-actions">
          <el-button @click="passwordOpen = true">修改密码</el-button>
          <el-button type="primary" :loading="saving" @click="save">保存资料</el-button>
        </div>
      </main>
    </section>

    <el-dialog v-model="passwordOpen" title="修改密码" width="460px">
      <el-form label-position="top">
        <el-form-item label="旧密码"><el-input v-model="passwordForm.oldPassword" type="password" show-password /></el-form-item>
        <el-form-item label="新密码"><el-input v-model="passwordForm.newPassword" type="password" show-password placeholder="8~32 位，至少包含字母和数字" /></el-form-item>
        <el-form-item label="确认新密码"><el-input v-model="passwordForm.confirmPassword" type="password" show-password /></el-form-item>
      </el-form>
      <template #footer><el-button @click="passwordOpen = false">取消</el-button><el-button type="primary" @click="changePassword">确认修改</el-button></template>
    </el-dialog>
  </div>
</template>
