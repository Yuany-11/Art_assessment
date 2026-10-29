<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, UploadFilled } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import { api } from '@/api'
import { saveBlob } from '@/api/client'
import { isAudioFile } from '@/utils/media'
import type { Account, SchoolClass, Score, StudentArtwork } from '@/types'

const loading = ref(false)
const rows = ref<Account[]>([])
const total = ref(0)
const pageNum = ref(1)
const pageSize = ref(10)
const keyword = ref('')
const classFilter = ref<number | ''>('')
const detailOpen = ref(false)
const materialsOpen = ref(false)
const scoresOpen = ref(false)
const selected = ref<Account | null>(null)
const studentScores = ref<Score[]>([])
const studentArtworks = ref<StudentArtwork[]>([])
const importInput = ref<HTMLInputElement>()
const importClassId = ref<number>()
const credentialOpen = ref(false)
const credentials = ref<Array<{ studentNo: string; name: string; username: string; password: string }>>([])
const classes = ref<SchoolClass[]>([])
const scoreLevelLabels: Record<string, string> = { excellent: '优秀', good: '良好', pass: '合格', fail: '待提升' }

async function load() {
  loading.value = true
  try {
    const result = await api.accounts.list('students', {
      keyword: keyword.value,
      classId: classFilter.value || undefined,
      pageNum: pageNum.value,
      pageSize: pageSize.value
    })
    rows.value = result.list
    total.value = result.total
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function detail(row: Account) {
  try {
    selected.value = await api.accounts.detail(row.id)
    detailOpen.value = true
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function resetPassword(row: Account) {
  try {
    await ElMessageBox.confirm(`重置“${row.realName}”的密码？`, '重置学生密码', { type: 'warning' })
    const result = await api.accounts.resetPassword(row.id)
    await ElMessageBox.alert(`临时密码：${result.temporaryPassword}`, '重置成功')
  } catch (error) {
    if (error instanceof Error) ElMessage.error(error.message)
  }
}

function downloadIdentity(row: Account) {
  const content = `学生身份材料\n姓名：${row.realName}\n学籍号：${row.studentNo}\n学校：${row.orgName}\n班级：${row.className}`
  saveBlob(new Blob([content], { type: 'text/plain;charset=utf-8' }), `${row.studentNo || row.username}-身份材料.txt`)
}

async function openMaterials(row: Account) {
  selected.value = row
  materialsOpen.value = true
  const artworks = await api.artworks.list()
  studentArtworks.value = artworks.filter((item) => item.studentId === row.id)
}

async function openScores(row: Account) {
  selected.value = row
  scoresOpen.value = true
  const result = await api.scores.list({ keyword: row.studentNo || row.username, pageSize: 100 })
  studentScores.value = result.list
}

function exportStudentScores() {
  if (!selected.value) return
  const lines = [['学号', '姓名', '测评', '客观分', '主观分', 'AI分', '总分', '状态'], ...studentScores.value.map((item) => [item.studentNo, item.studentName, item.assessmentTitle, item.objectiveScore, item.subjectiveScore, item.aiScore, item.totalScore, item.status])]
  saveBlob(new Blob([`\ufeff${lines.map((line) => line.join(',')).join('\n')}`], { type: 'text/csv;charset=utf-8' }), `${selected.value.studentNo}-全部成绩.csv`)
}

async function importStudents(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  if (!importClassId.value) {
    ElMessage.warning('请先选择导入的目标班级')
    ;(event.target as HTMLInputElement).value = ''
    return
  }
  try {
    const result = await api.classes.importStudents(importClassId.value, file)
    ElMessage.success(`导入完成：成功 ${result.successCount} 条，失败 ${result.failCount} 条`)
    credentials.value = (result.credentials as typeof credentials.value | undefined) ?? []
    if (credentials.value.length) credentialOpen.value = true
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    ;(event.target as HTMLInputElement).value = ''
  }
}

function downloadCredentials() {
  if (!credentials.value.length) return
  const lines = [['学籍号', '姓名', '登录账号', '初始密码'], ...credentials.value.map((item) => [item.studentNo, item.name, item.username, item.password])]
  saveBlob(new Blob([`﻿${lines.map((line) => line.join(',')).join('\n')}`], { type: 'text/csv;charset=utf-8' }), '学生账号清单.csv')
}

onMounted(async () => {
  await Promise.all([
    load(),
    api.classes.list({ pageSize: 100 }).then((result) => {
      classes.value = result.list
      importClassId.value = classes.value[0]?.id
    })
  ])
})
</script>

<template>
  <div class="stack">
    <PageHeader title="学生管理" description="查询任教班级学生，查看学籍材料并重置学生密码。">
      <el-select v-model="importClassId" class="header-class-select" placeholder="导入目标班级">
        <el-option v-for="item in classes" :key="item.id" :label="item.name" :value="item.id" />
      </el-select>
      <el-button :icon="UploadFilled" @click="importInput?.click()">外校学生导入</el-button>
      <input ref="importInput" class="hidden-input" type="file" accept=".csv,.xlsx" @change="importStudents" />
    </PageHeader>
    <section class="panel">
      <div class="filter-bar">
        <el-input v-model="keyword" :prefix-icon="Search" clearable placeholder="姓名、登录账号或学籍号" @keyup.enter="load" />
        <el-select v-model="classFilter" clearable placeholder="全部班级" @change="pageNum = 1; load()">
          <el-option v-for="item in classes" :key="item.id" :label="`${item.name}（${item.classCode}）`" :value="item.id" />
        </el-select>
        <el-button type="primary" @click="pageNum = 1; load()">查询</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" row-key="id" stripe empty-text="暂无学生数据">
        <el-table-column prop="studentNo" label="学籍号" min-width="140" />
        <el-table-column prop="realName" label="姓名" width="110" />
        <el-table-column prop="username" label="登录账号" min-width="150" />
        <el-table-column prop="className" label="班级" min-width="140" />
        <el-table-column prop="phone" label="手机号" min-width="130" />
        <el-table-column label="状态" width="90"><template #default="{ row }"><StatusTag :value="row.status" /></template></el-table-column>
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="detail(row)">查看学籍</el-button>
            <el-button link @click="openScores(row)">测评成绩</el-button>
            <el-button link @click="openMaterials(row)">学习材料</el-button>
            <el-button link @click="downloadIdentity(row)">身份材料</el-button>
            <el-button link @click="resetPassword(row)">重置密码</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="table-footer"><span>共 {{ total }} 名学生</span><el-pagination v-model:current-page="pageNum" v-model:page-size="pageSize" :total="total" layout="prev, pager, next" @change="load" /></div>
    </section>

    <el-drawer v-model="detailOpen" title="学生学籍信息" size="520px">
      <el-descriptions v-if="selected" :column="1" border>
        <el-descriptions-item label="姓名">{{ selected.realName }}</el-descriptions-item>
        <el-descriptions-item label="登录账号">{{ selected.username }}</el-descriptions-item>
        <el-descriptions-item label="学籍号">{{ selected.studentNo }}</el-descriptions-item>
        <el-descriptions-item label="学校">{{ selected.orgName }}</el-descriptions-item>
        <el-descriptions-item label="班级">{{ selected.className || '未分班' }}</el-descriptions-item>
        <el-descriptions-item label="年级">{{ selected.grade || '—' }}</el-descriptions-item>
        <el-descriptions-item label="手机号">{{ selected.phone || '—' }}</el-descriptions-item>
        <el-descriptions-item label="电子邮箱">{{ selected.email || '—' }}</el-descriptions-item>
        <el-descriptions-item label="账号创建时间">{{ selected.createdAt.replace('T', ' ').slice(0, 16) }}</el-descriptions-item>
        <el-descriptions-item label="账号状态"><StatusTag :value="selected.status" /></el-descriptions-item>
      </el-descriptions>
      <el-button v-if="selected" class="full-button" type="primary" plain @click="downloadIdentity(selected)">下载身份材料</el-button>
    </el-drawer>

    <el-drawer v-model="scoresOpen" :title="`${selected?.realName || ''} · 全部测评成绩`" size="760px">
      <div class="drawer-actions top-actions"><el-button type="primary" plain @click="exportStudentScores">导出全部成绩</el-button></div>
      <el-table :data="studentScores" empty-text="暂无该学生成绩">
        <el-table-column prop="assessmentTitle" label="测评" min-width="220" />
        <el-table-column prop="subject" label="学科" width="80"><template #default="{ row }">{{ row.subject === 'music' ? '音乐' : '美术' }}</template></el-table-column>
        <el-table-column prop="totalScore" label="总分" width="80" />
        <el-table-column prop="level" label="等级" width="90"><template #default="{ row }">{{ scoreLevelLabels[row.level as string] }}</template></el-table-column>
        <el-table-column prop="status" label="状态" width="100"><template #default="{ row }"><StatusTag :value="row.status" /></template></el-table-column>
        <el-table-column prop="createdAt" label="时间" min-width="170" />
      </el-table>
    </el-drawer>

    <el-drawer v-model="materialsOpen" :title="`${selected?.realName || ''} · 课外学习材料`" size="680px">
      <div class="artwork-grid">
        <article v-for="item in studentArtworks" :key="item.id" class="artwork-card">
          <figure v-if="isAudioFile(item.fileName, item.mimeType)" class="artwork-audio-box">
            <audio :src="item.preview" controls preload="none" class="artwork-audio"></audio>
          </figure>
          <img v-else :src="item.preview" :alt="item.fileName" />
          <div><h3>{{ item.fileName }}</h3><p>{{ item.uploadedAt.replace('T', ' ').slice(0, 16) }}</p><span class="status-tag status-tag--warning">{{ item.status === 'reviewed' ? '已查看' : '待查看' }}</span></div>
        </article>
      </div>
      <div v-if="!studentArtworks.length" class="empty-card student-card">该学生暂未上传课外学习材料。</div>
    </el-drawer>

    <el-dialog v-model="credentialOpen" title="导入成功 · 学生初始账号" width="640px">
      <el-alert title="以下临时密码仅本次展示，请及时下载或分发给学生；关闭后需重置密码才能再次获取。" type="warning" :closable="false" show-icon />
      <el-table :data="credentials" size="small" class="credential-table">
        <el-table-column prop="studentNo" label="学籍号" min-width="120" />
        <el-table-column prop="name" label="姓名" width="100" />
        <el-table-column prop="username" label="登录账号" min-width="130" />
        <el-table-column prop="password" label="初始密码" min-width="130" />
      </el-table>
      <template #footer>
        <el-button @click="credentialOpen = false">关闭</el-button>
        <el-button type="primary" @click="downloadCredentials">下载账号清单</el-button>
      </template>
    </el-dialog>
  </div>
</template>
