<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import PageHeader from '@/components/PageHeader.vue'
import { api } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { PASSWORD_REQUIREMENT, isStrongPassword } from '@/constants/validation'
import type { UserProfile } from '@/types'

const auth = useAuthStore()
const saving = ref(false)
const avatarUploading = ref(false)
const avatarInput = ref<HTMLInputElement>()
const PHONE_PATTERN = /^1[3-9]\d{9}$/
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const passwordOpen = ref(false)
const avatarPreviewOpen = ref(false)
const avatarError = ref(false)
const passwordFormRef = ref<FormInstance>()
const passwordForm = reactive({ oldPassword: '', newPassword: '', confirmPassword: '' })
const passwordRules: FormRules = {
  oldPassword: [{ required: true, message: '请输入旧密码', trigger: 'blur' }],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value && !isStrongPassword(String(value))) callback(new Error(PASSWORD_REQUIREMENT))
        else callback()
      },
      trigger: ['blur', 'change']
    }
  ],
  confirmPassword: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== passwordForm.newPassword) callback(new Error('两次输入的新密码不一致'))
        else callback()
      },
      trigger: ['blur', 'change']
    }
  ]
}
const subjectLabel = computed(() => (auth.user?.subject === 'music' ? '音乐' : auth.user?.subject === 'art' ? '美术' : '—'))
const form = reactive({
  realName: auth.user?.realName ?? '',
  gender: auth.user?.gender ?? 'unknown',
  phone: auth.user?.phone ?? '',
  email: auth.user?.email ?? '',
  avatarUrl: auth.user?.avatarUrl ?? ''
})
watch(() => form.avatarUrl, () => { avatarError.value = false })

async function save() {
  if (!form.realName.trim()) return ElMessage.warning('姓名不能为空')
  if (form.phone.trim() && !PHONE_PATTERN.test(form.phone.trim())) {
    return ElMessage.warning('手机号需为 11 位数字，且以 1 开头')
  }
  if (form.email.trim() && !EMAIL_PATTERN.test(form.email.trim())) {
    return ElMessage.warning('邮箱格式不正确，请检查后重新填写')
  }
  saving.value = true
  try {
    const values = {
      realName: form.realName.trim(),
      gender: form.gender,
      phone: form.phone.trim() || null,
      email: form.email.trim() || null,
      avatarUrl: form.avatarUrl.trim() || null
    }
    const updated = (await api.profile.update(values)) as Partial<UserProfile>
    auth.updateProfile({
      realName: (updated.realName as string) ?? values.realName,
      gender: (updated.gender as 'male' | 'female' | 'unknown') ?? values.gender,
      phone: (updated.phone as string | null) ?? values.phone,
      email: (updated.email as string | null) ?? values.email,
      avatarUrl: (updated.avatarUrl as string | null) ?? values.avatarUrl
    })
    ElMessage.success('个人信息已更新')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    saving.value = false
  }
}

async function persistAvatar(url: string | null) {
  const updated = (await api.profile.update({ avatarUrl: url })) as Partial<UserProfile>
  const next = (updated.avatarUrl as string | null | undefined) ?? url
  form.avatarUrl = next ?? ''
  auth.updateProfile({ avatarUrl: next })
}

async function uploadAvatar(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!file.type.startsWith('image/')) return ElMessage.warning('头像请选择 JPG、PNG 或 WEBP 图片')
  if (file.size > 10 * 1024 * 1024) return ElMessage.warning('头像图片不能超过 10 MB')
  avatarUploading.value = true
  try {
    const uploaded = await api.files.upload(file, 'avatar')
    await persistAvatar(uploaded.url)
    ElMessage.success('头像已更新')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    avatarUploading.value = false
  }
}

function openAvatarPreview() {
  if (form.avatarUrl) avatarPreviewOpen.value = true
}

async function removeAvatar() {
  if (!form.avatarUrl) return
  avatarUploading.value = true
  try {
    await persistAvatar(null)
    ElMessage.success('头像已移除')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    avatarUploading.value = false
  }
}

async function changePassword() {
  const valid = await passwordFormRef.value?.validate().catch(() => false)
  if (!valid) return
  try {
    const result = await api.profile.changePassword(passwordForm.oldPassword, passwordForm.newPassword)
    passwordOpen.value = false
    Object.assign(passwordForm, { oldPassword: '', newPassword: '', confirmPassword: '' })
    ElMessage.success('密码已修改')
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
        <div
          class="profile-avatar"
          :class="{ 'avatar--zoomable': form.avatarUrl }"
          :title="form.avatarUrl ? '双击查看头像' : undefined"
          @dblclick="openAvatarPreview"
        >
          <img v-if="form.avatarUrl && !avatarError" :src="form.avatarUrl" alt="当前头像" @error="avatarError = true" />
          <template v-else>{{ auth.user?.realName.slice(0, 1) }}</template>
        </div>
        <div class="avatar-actions">
          <el-button size="small" :loading="avatarUploading" @click="avatarInput?.click()">更换头像</el-button>
          <el-button v-if="form.avatarUrl" size="small" text type="danger" @click="removeAvatar">移除</el-button>
          <input ref="avatarInput" class="hidden-input" type="file" accept="image/*" @change="uploadAvatar" />
        </div>
        <h2>{{ auth.user?.realName }}</h2>
        <span>{{ auth.user?.roleName }}</span>
        <p>{{ auth.user?.schoolName || auth.user?.cityName || '题库全域' }}</p>
        <div class="profile-meta">
          <div><small>登录账号</small><b>{{ auth.user?.username }}</b></div>
          <div v-if="auth.role === 'student'"><small>学籍号</small><b>{{ auth.user?.studentNo || '—' }}</b></div>
          <div v-if="auth.role === 'student'"><small>班级</small><b>{{ auth.user?.className || '未分班' }}</b></div>
          <div v-if="auth.role === 'teacher'"><small>教师工号</small><b>{{ auth.user?.teacherNo || '—' }}</b></div>
          <div v-if="auth.role === 'teacher'"><small>任教学科</small><b>{{ subjectLabel }}</b></div>
        </div>
      </aside>
      <main class="profile-form">
        <h3>基本资料</h3>
        <el-form label-position="top" class="form-grid">
          <el-form-item label="姓名"><el-input v-model="form.realName" /></el-form-item>
          <el-form-item label="性别"><el-select v-model="form.gender"><el-option label="男" value="male" /><el-option label="女" value="female" /><el-option label="未填写" value="unknown" /></el-select></el-form-item>
          <el-form-item label="手机号"><el-input v-model="form.phone" maxlength="11" inputmode="numeric" placeholder="11 位手机号" /></el-form-item>
          <el-form-item label="邮箱"><el-input v-model="form.email" placeholder="未填写" /></el-form-item>
          <el-form-item label="头像" class="span-2">
            <div class="avatar-field">
              <div
                class="avatar-field-preview"
                :class="{ 'avatar--zoomable': form.avatarUrl }"
                :title="form.avatarUrl ? '双击查看头像' : undefined"
                @dblclick="openAvatarPreview"
              >
                <img v-if="form.avatarUrl && !avatarError" :src="form.avatarUrl" alt="头像预览" @error="avatarError = true" />
                <span v-else>{{ auth.user?.realName.slice(0, 1) }}</span>
              </div>
              <div class="avatar-field-copy">
                <b>{{ form.avatarUrl ? '已设置头像' : '还没有上传头像' }}</b>
                <span>支持 JPG、PNG、WEBP，建议 1:1 图片，不超过 10 MB</span>
              </div>
            </div>
          </el-form-item>
        </el-form>
        <div class="profile-actions">
          <el-button @click="passwordOpen = true">修改密码</el-button>
          <el-button type="primary" :loading="saving" @click="save">保存资料</el-button>
        </div>
      </main>
    </section>

    <el-dialog v-model="passwordOpen" title="修改密码" width="460px">
      <el-form ref="passwordFormRef" :model="passwordForm" :rules="passwordRules" label-position="top">
        <el-form-item label="旧密码" prop="oldPassword"><el-input v-model="passwordForm.oldPassword" type="password" show-password /></el-form-item>
        <el-form-item label="新密码" prop="newPassword">
          <el-input v-model="passwordForm.newPassword" type="password" show-password maxlength="32" placeholder="请输入新密码" />
          <div class="form-hint">{{ PASSWORD_REQUIREMENT }}</div>
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirmPassword">
          <el-input v-model="passwordForm.confirmPassword" type="password" show-password maxlength="32" />
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="passwordOpen = false">取消</el-button><el-button type="primary" @click="changePassword">确认修改</el-button></template>
    </el-dialog>
    <el-image-viewer
      v-if="avatarPreviewOpen"
      :url-list="[form.avatarUrl]"
      hide-on-click-modal
      teleported
      @close="avatarPreviewOpen = false"
    />
  </div>
</template>
