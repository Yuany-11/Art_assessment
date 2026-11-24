<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { EditPen, Picture, Postcard, Reading, Search, TrendCharts } from '@element-plus/icons-vue'
import { api } from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { SchoolClass } from '@/types'

const auth = useAuthStore()
const classCode = ref('')
const foundClass = ref<SchoolClass | null>(null)
const myClass = ref<SchoolClass | null>(null)
const artworkInput = ref<HTMLInputElement>()
const requestOpen = ref(false)
const avatarError = ref(false)
watch(() => auth.user?.avatarUrl, () => { avatarError.value = false })
const requestForm = reactive({ type: 'leave' as 'join' | 'change' | 'leave', reason: '', targetClassId: undefined as number | undefined })
const transferClasses = ref<SchoolClass[]>([])
const transferLoading = ref(false)

async function loadMyClass() {
  if (!auth.user?.classId) {
    myClass.value = null
    return
  }
  try {
    myClass.value = await api.classes.detail(auth.user.classId)
  } catch {
    myClass.value = null
  }
}

async function searchClass() {
  if (!classCode.value.trim()) {
    ElMessage.warning('请输入班级号')
    return
  }
  try {
    foundClass.value = await api.classes.search(classCode.value.trim())
    if (!foundClass.value) ElMessage.warning('未找到该班级')
  } catch (error) {
    foundClass.value = null
    ElMessage.error((error as Error).message)
  }
}

async function loadTransferClasses() {
  transferLoading.value = true
  transferClasses.value = []
  try {
    const result = await api.classes.list({
      grade: auth.user?.grade ?? undefined,
      status: 'active',
      pageSize: 100
    })
    transferClasses.value = result.list
      .filter((item) => item.id !== auth.user?.classId && item.status === 'active')
      .filter((item) => !auth.user?.grade || item.grade === auth.user.grade)
      .sort((a, b) => a.name.localeCompare(b.name, 'zh'))
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    transferLoading.value = false
  }
}

function openRequest(type: 'join' | 'change' | 'leave') {
  if (type !== 'join' && !auth.user?.classId) {
    ElMessage.warning('你当前还没有加入班级')
    return
  }
  requestForm.type = type
  requestForm.reason = ''
  requestForm.targetClassId = undefined
  requestOpen.value = true
  if (type === 'change') void loadTransferClasses()
}

async function resolveTargetClass() {
  if (requestForm.type !== 'change') return
  if (!requestForm.targetClassId) throw new Error('请选择目标班级')
  const target = transferClasses.value.find((item) => item.id === requestForm.targetClassId)
  if (!target) throw new Error('目标班级不在可选范围内，请刷新后重试')
  if (auth.user?.grade && target.grade !== auth.user.grade) {
    throw new Error('只能申请转入同年级的其他班级')
  }
}

async function submitRequest() {
  if (!requestForm.reason.trim()) {
    ElMessage.warning('请填写申请原因')
    return
  }
  try {
    await resolveTargetClass()
    const classId = requestForm.type === 'join' ? foundClass.value?.id : auth.user?.classId
    if (!classId) {
      ElMessage.warning('未找到可操作的班级')
      return
    }
    await api.classes.request(requestForm.type, classId, requestForm.reason, requestForm.type === 'change' ? requestForm.targetClassId : undefined)
    requestOpen.value = false
    ElMessage.success('申请已提交，等待班主任审核')
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function uploadArtwork(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    await api.artworks.upload(file, 'art')
    ElMessage.success(`作品 ${file.name} 已上传，后续可由教师进行艺术分析`)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
  ;(event.target as HTMLInputElement).value = ''
}

onMounted(loadMyClass)
</script>

<template>
  <div class="student-page stack">
    <section class="student-hero">
      <div class="student-hero-copy">
        <div class="student-avatar">
          <img v-if="auth.user?.avatarUrl && !avatarError" :src="auth.user.avatarUrl" :alt="auth.user.realName" @error="avatarError = true" />
          <template v-else>{{ auth.user?.realName?.slice(0, 1) || '艺' }}</template>
        </div>
        <div>
          <p><i></i> 你好，{{ auth.user?.realName }}</p>
          <h2>今天也来发现<br class="desktop-break" />艺术之美</h2>
          <span>{{ auth.user?.schoolName }} · {{ auth.user?.className || '尚未加入班级' }}</span>
          <div class="student-hero-tags"><em>音乐感知</em><em>视觉表达</em><em>成长记录</em></div>
        </div>
      </div>
      <router-link class="student-hero-inspiration" to="/student/assessments">
        <span class="inspiration-orbit inspiration-orbit--one"></span>
        <span class="inspiration-orbit inspiration-orbit--two"></span>
        <span class="inspiration-crane"></span>
        <small>DAILY ART MOMENT</small>
        <b>开启今日艺术灵感</b>
        <span>随机音乐或美术练习 <i>→</i></span>
      </router-link>
      <div class="student-hero-ribbon" aria-hidden="true">
        <span></span><span></span><span></span>
      </div>
    </section>

    <section class="student-quick-grid">
      <router-link to="/student/assessments"><el-icon class="quick-card-icon"><EditPen /></el-icon><small>01 / ASSESSMENT</small><b>开始测评</b><span>音乐与美术正式测评</span></router-link>
      <router-link to="/student/results"><el-icon class="quick-card-icon"><TrendCharts /></el-icon><small>02 / GROWTH</small><b>查看成绩</b><span>成绩、解析与成长趋势</span></router-link>
      <router-link to="/student/report"><el-icon class="quick-card-icon"><Reading /></el-icon><small>03 / REPORT</small><b>学习报告</b><span>个性化学情分析与提升建议</span></router-link>
      <router-link to="/student/artworks"><el-icon class="quick-card-icon"><Picture /></el-icon><small>04 / ARTWORK</small><b>课外作品</b><span>上传并管理日常艺术创作</span></router-link>
      <router-link to="/student/certificates"><el-icon class="quick-card-icon"><Postcard /></el-icon><small>05 / HONOR</small><b>我的证书</b><span>查看与下载测评证书</span></router-link>
    </section>

    <section class="student-card">
      <div class="student-section-head"><h3>我的班级</h3><span>{{ auth.user?.className }}</span></div>
      <div class="class-info">
        <div><span>班级号</span><b>{{ myClass?.classCode || '—' }}</b></div>
        <div><span>班主任</span><b>{{ myClass?.headTeacherName || '—' }}</b></div>
        <div><span>班级人数</span><b>{{ myClass?.studentCount ?? '—' }} 人</b></div>
      </div>
      <div class="profile-actions class-actions">
        <el-button plain @click="openRequest('change')">申请转班</el-button>
        <el-button plain @click="openRequest('leave')">申请退出</el-button>
      </div>
    </section>

    <section class="student-card">
      <div class="student-section-head"><h3>课外学习作品</h3><span>上传图片用于学习记录与教师评分</span></div>
      <label class="upload-zone">
        <b>上传课外自主学习图片</b>
        <span>支持 JPG、PNG、WEBP，单文件不超过 10 MB</span>
        <input ref="artworkInput" type="file" accept="image/*" @change="uploadArtwork" />
      </label>
    </section>

    <section class="student-card">
      <div class="student-section-head"><h3>加入其他班级</h3><span>使用班级号查询</span></div>
      <div class="student-search-row">
        <el-input v-model="classCode" :prefix-icon="Search" placeholder="请输入班级号" @keyup.enter="searchClass" />
        <el-button type="primary" @click="searchClass">查询</el-button>
      </div>
      <div v-if="foundClass" class="found-class">
        <div><b>{{ foundClass.name }}</b><span>{{ foundClass.classCode }} · 班主任 {{ foundClass.headTeacherName }} · {{ foundClass.studentCount }} 人</span></div>
        <el-button type="primary" plain @click="openRequest('join')">申请加入</el-button>
      </div>
    </section>

    <el-dialog v-model="requestOpen" :title="requestForm.type === 'join' ? '申请加入班级' : requestForm.type === 'change' ? '申请更换班级' : '申请退出班级'" width="480px">
      <el-alert
        v-if="requestForm.type === 'change'"
        title="转班需原班级和目标班级双方班主任分别通过后才会生效。"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      />
      <el-form label-position="top">
        <el-form-item v-if="requestForm.type === 'change'" label="目标班级" required>
          <el-select
            v-model="requestForm.targetClassId"
            :loading="transferLoading"
            filterable
            placeholder="请选择同年级班级"
            style="width: 100%"
          >
            <el-option
              v-for="item in transferClasses"
              :key="item.id"
              :label="`${item.name}（${item.grade} 年级）· ${item.headTeacherName || '暂无班主任'}`"
              :value="item.id"
            />
          </el-select>
          <div v-if="!transferLoading && !transferClasses.length" class="form-hint">本年级暂无可转入的班级</div>
        </el-form-item>
        <el-form-item label="申请原因" required><el-input v-model="requestForm.reason" type="textarea" :rows="4" maxlength="200" show-word-limit placeholder="请填写申请原因" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="requestOpen = false">取消</el-button><el-button type="primary" @click="submitRequest">提交申请</el-button></template>
    </el-dialog>
  </div>
</template>
