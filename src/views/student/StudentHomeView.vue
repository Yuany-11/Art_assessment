<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { api } from '@/api'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const classCode = ref('')
const foundClass = ref<{ id: number; name: string; classCode: string; headTeacherName: string; studentCount: number } | null>(null)
const artworkInput = ref<HTMLInputElement>()
const requestOpen = ref(false)
const requestForm = reactive({ type: 'leave' as 'join' | 'change' | 'leave', reason: '', targetClassId: 5002 })

function searchClass() {
  if (classCode.value.trim() !== 'C20260701') {
    ElMessage.warning('演示班级号：C20260701')
    return
  }
  foundClass.value = { id: 5001, name: '七年级（1）班', classCode: 'C20260701', headTeacherName: '李老师', studentCount: 42 }
}

function openRequest(type: 'join' | 'change' | 'leave') {
  requestForm.type = type
  requestForm.reason = ''
  requestOpen.value = true
}

async function submitRequest() {
  if (!requestForm.reason.trim()) {
    ElMessage.warning('请填写申请原因')
    return
  }
  const classId = requestForm.type === 'join' ? foundClass.value?.id ?? 5001 : auth.user?.classId ?? 5001
  await api.classes.request(requestForm.type, classId, requestForm.reason, requestForm.type === 'change' ? requestForm.targetClassId : undefined)
  requestOpen.value = false
  ElMessage.success('申请已提交，等待班主任审核')
}

async function uploadArtwork(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  await api.artworks.upload(file, 'art')
  ElMessage.success(`作品 ${file.name} 已上传，后续可由教师进行艺术分析`)
  ;(event.target as HTMLInputElement).value = ''
}
</script>

<template>
  <div class="student-page stack">
    <section class="student-hero">
      <div class="student-avatar">{{ auth.user?.realName.slice(0, 1) }}</div>
      <div>
        <p>你好，{{ auth.user?.realName }}</p>
        <h2>今天也来发现艺术之美</h2>
        <span>{{ auth.user?.schoolName }} · {{ auth.user?.className || '尚未加入班级' }}</span>
      </div>
    </section>

    <section class="student-quick-grid">
      <router-link to="/student/assessments"><b>开始测评</b><span>音乐与美术正式测评</span></router-link>
      <router-link to="/student/results"><b>查看成绩</b><span>成绩、解析与成长趋势</span></router-link>
      <router-link to="/student/report"><b>学习报告</b><span>个性化学情分析与提升建议</span></router-link>
      <router-link to="/student/artworks"><b>课外作品</b><span>上传并管理日常艺术创作</span></router-link>
      <router-link to="/student/certificates"><b>我的证书</b><span>查看与下载测评证书</span></router-link>
    </section>

    <section class="student-card">
      <div class="student-section-head"><h3>我的班级</h3><span>{{ auth.user?.className }}</span></div>
      <div class="class-info">
        <div><span>班主任</span><b>李老师</b></div>
        <div><span>班级人数</span><b>42 人</b></div>
        <div><span>学科教师</span><b>音乐 · 美术</b></div>
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
      <el-form label-position="top">
        <el-form-item v-if="requestForm.type === 'change'" label="目标班级">
          <el-select v-model="requestForm.targetClassId"><el-option label="七年级（2）班" :value="5002" /><el-option label="七年级（1）班" :value="5001" /></el-select>
        </el-form-item>
        <el-form-item label="申请原因" required><el-input v-model="requestForm.reason" type="textarea" :rows="4" maxlength="200" show-word-limit placeholder="请填写申请原因" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="requestOpen = false">取消</el-button><el-button type="primary" @click="submitRequest">提交申请</el-button></template>
    </el-dialog>
  </div>
</template>
