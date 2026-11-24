<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowDown, Headset, Plus, Search, UploadFilled } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import DetailDialog from '@/components/DetailDialog.vue'
import ScoreStepper from '@/components/ScoreStepper.vue'
import AudioTagCard from '@/components/AudioTagCard.vue'
import { api } from '@/api'
import { copyText as copyToClipboard } from '@/utils/clipboard'
import { saveBlob } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import {
  DEFAULT_INITIAL_PASSWORD,
  PASSWORD_REQUIREMENT,
  STUDENT_NO_PATTERN,
  STUDENT_NO_REQUIREMENT,
  USERNAME_PATTERN,
  USERNAME_REQUIREMENT,
  isStrongPassword
} from '@/constants/validation'
import type { Account, AudioTags, SchoolClass, Score, StudentArtwork } from '@/types'

const auth = useAuthStore()

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
const manageableClasses = computed(() => classes.value.filter((item) => item.headTeacherId === auth.user?.id))
const canManageStudents = computed(() => manageableClasses.value.length > 0)
const scoreLevelLabels: Record<string, string> = { excellent: '优秀', good: '良好', pass: '合格', fail: '待提升' }
const addOpen = ref(false)
const addForm = reactive({ realName: '', username: '', studentNo: '', gender: 'unknown', classId: undefined as number | undefined, phone: '', initialPassword: '', initialPasswordConfirm: '' })
const credentialTitle = ref('导入成功 · 学生初始账号')
const resetOpen = ref(false)
const resetLoading = ref(false)
const resetRow = ref<Account | null>(null)
const resetPasswordValue = ref('')
const resetPasswordConfirm = ref('')
const reviewOpen = ref(false)
const reviewArtwork = ref<StudentArtwork | null>(null)
const reviewForm = reactive({ score: 90, comment: '' })

async function copyText(value: string) {
  const ok = await copyToClipboard(value)
  if (ok) ElMessage.success('已复制')
  else ElMessage.warning('复制失败，请手动选择文本复制')
}

function openReview(item: StudentArtwork) {
  reviewArtwork.value = item
  reviewForm.score = item.score ?? 0
  reviewForm.comment = item.comment ?? ''
  reviewOpen.value = true
}

async function saveReview() {
  if (!reviewArtwork.value) return
  if (reviewForm.score === null || reviewForm.score === undefined || reviewForm.score < 0 || reviewForm.score > 100) {
    ElMessage.warning('评分需在 0 到 100 分之间')
    return
  }
  try {
    const result = await api.artworks.review(reviewArtwork.value.id, Number(reviewForm.score), reviewForm.comment.trim())
    Object.assign(reviewArtwork.value, result, { status: 'reviewed', score: Number(reviewForm.score), comment: reviewForm.comment.trim() })
    reviewOpen.value = false
    ElMessage.success('作品评分已保存，学生端可查看')
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function canManageStudent(row: Account) {
  return manageableClasses.value.some((item) => item.id === row.classId)
}

function openAdd() {
  if (!canManageStudents.value) {
    ElMessage.warning('科任老师只能查看学生信息，添加学生需由班主任操作')
    return
  }
  Object.assign(addForm, { realName: '', username: '', studentNo: '', gender: 'unknown', classId: manageableClasses.value[0]?.id, phone: '', initialPassword: '', initialPasswordConfirm: '' })
  addOpen.value = true
}

async function addStudent() {
  if (!addForm.realName.trim() || !addForm.username.trim() || !addForm.studentNo.trim()) {
    ElMessage.warning('请填写姓名、登录账号和学籍号')
    return
  }
  if (!USERNAME_PATTERN.test(addForm.username.trim())) {
    ElMessage.warning(USERNAME_REQUIREMENT)
    return
  }
  if (!STUDENT_NO_PATTERN.test(addForm.studentNo.trim())) {
    ElMessage.warning(STUDENT_NO_REQUIREMENT)
    return
  }
  if (addForm.initialPassword && !isStrongPassword(addForm.initialPassword)) {
    ElMessage.warning(PASSWORD_REQUIREMENT)
    return
  }
  if (addForm.initialPassword !== addForm.initialPasswordConfirm) {
    ElMessage.warning('两次输入的初始密码不一致')
    return
  }
  if (!addForm.classId) {
    ElMessage.warning('请选择班级')
    return
  }
  if (!manageableClasses.value.some((item) => item.id === addForm.classId)) {
    ElMessage.warning('只能向本人担任班主任的班级添加学生')
    return
  }
  const classroom = manageableClasses.value.find((item) => item.id === addForm.classId)
  try {
    const created = (await api.accounts.create('students', {
      realName: addForm.realName.trim(),
      username: addForm.username.trim(),
      studentNo: addForm.studentNo.trim(),
      gender: addForm.gender,
      grade: classroom?.grade ?? 7,
      classId: addForm.classId,
      phone: addForm.phone.trim() || null,
      initialPassword: addForm.initialPassword || undefined
    })) as Account
    addOpen.value = false
    credentials.value = [{
      studentNo: created.studentNo || addForm.studentNo.trim(),
      name: created.realName || addForm.realName.trim(),
      username: created.username || addForm.username.trim(),
      password: created.initialPassword || addForm.initialPassword || DEFAULT_INITIAL_PASSWORD
    }]
    credentialTitle.value = '学生已添加 · 初始账号'
    credentialOpen.value = true
    ElMessage.success('学生已添加')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function resetQuery() {
  keyword.value = ''
  classFilter.value = ''
  pageNum.value = 1
  load()
}

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

function resetPassword(row: Account) {
  if (!canManageStudent(row)) {
    ElMessage.warning('科任老师只能查看学生信息，重置密码需由班主任操作')
    return
  }
  resetRow.value = row
  resetPasswordValue.value = ''
  resetPasswordConfirm.value = ''
  resetOpen.value = true
}

async function confirmResetPassword() {
  if (!resetRow.value) return
  if (resetPasswordValue.value && !isStrongPassword(resetPasswordValue.value)) {
    ElMessage.warning(PASSWORD_REQUIREMENT)
    return
  }
  if (resetPasswordValue.value !== resetPasswordConfirm.value) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  resetLoading.value = true
  try {
    const result = await api.accounts.resetPassword(resetRow.value.id, resetPasswordValue.value || undefined)
    credentials.value = [{
      studentNo: resetRow.value.studentNo || '',
      name: resetRow.value.realName,
      username: resetRow.value.username,
      password: result.temporaryPassword
    }]
    credentialTitle.value = '密码已重置 · 新密码'
    resetOpen.value = false
    credentialOpen.value = true
    await load()
    ElMessage.success('密码已重置')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    resetLoading.value = false
  }
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
  const lines = [['学号', '姓名', '测评', '客观分', '主观分', '总分', '状态'], ...studentScores.value.map((item) => [item.studentNo, item.studentName, item.assessmentTitle, item.objectiveScore, item.subjectiveScore, item.totalScore, item.status])]
  saveBlob(new Blob([`\ufeff${lines.map((line) => line.join(',')).join('\n')}`], { type: 'text/csv;charset=utf-8' }), `${selected.value.studentNo}-全部成绩.csv`)
}

type StudentAction = 'scores' | 'materials' | 'reset' | 'temp'

async function viewTemporaryPassword(row: Account) {
  try {
    const result = await api.accounts.temporaryPassword(row.id)
    credentials.value = [{
      studentNo: row.studentNo || '',
      name: row.realName,
      username: row.username,
      password: result.temporaryPassword
    }]
    credentialTitle.value = '最近一次临时密码'
    credentialOpen.value = true
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function handleStudentAction(command: StudentAction, row: Account) {
  if (command === 'scores') return openScores(row)
  if (command === 'materials') return openMaterials(row)
  if (command === 'reset') return resetPassword(row)
  if (command === 'temp') return viewTemporaryPassword(row)
}

function isAudioArtwork(item: StudentArtwork) {
  return (item.mimeType ?? '').startsWith('audio/') || /\.(mp3|wav|m4a|ogg|webm)$/i.test(item.fileName)
}

function onArtworkAnalyzed(item: StudentArtwork, tags: AudioTags) {
  item.audioTags = tags
}

async function importStudents(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  if (!importClassId.value) {
    ElMessage.warning('请先选择导入的目标班级')
    ;(event.target as HTMLInputElement).value = ''
    return
  }
  if (!manageableClasses.value.some((item) => item.id === importClassId.value)) {
    ElMessage.warning('只能向本人担任班主任的班级导入学生')
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
      importClassId.value = manageableClasses.value[0]?.id
    })
  ])
})
</script>

<template>
  <div class="stack">
    <PageHeader title="学生管理" :description="canManageStudents ? '班主任可维护本班学生账号；科任老师可查看任教班级学生信息。' : '科任老师可查看任教班级学生信息；账号维护由班主任操作。'">
      <el-select v-if="canManageStudents" v-model="importClassId" class="header-class-select" placeholder="导入目标班级">
        <el-option v-for="item in manageableClasses" :key="item.id" :label="item.name" :value="item.id" />
      </el-select>
      <el-button v-if="canManageStudents" type="primary" :icon="Plus" @click="openAdd">手动添加学生</el-button>
      <el-button v-if="canManageStudents" :icon="UploadFilled" @click="importInput?.click()">外校学生导入</el-button>
      <input v-if="canManageStudents" ref="importInput" class="hidden-input" type="file" accept=".csv,.xlsx" @change="importStudents" />
    </PageHeader>
    <section class="panel">
      <div class="filter-bar">
        <el-input v-model="keyword" :prefix-icon="Search" clearable placeholder="姓名、登录账号或学籍号" @keyup.enter="load" />
        <el-select v-model="classFilter" clearable placeholder="全部班级" @change="pageNum = 1; load()">
          <el-option v-for="item in classes" :key="item.id" :label="`${item.name}（${item.classCode}）`" :value="item.id" />
        </el-select>
        <el-button type="primary" @click="pageNum = 1; load()">查询</el-button>
        <el-button @click="resetQuery">返回全部</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" row-key="id" stripe empty-text="暂无学生数据">
        <el-table-column prop="studentNo" label="学籍号" min-width="140" />
        <el-table-column prop="realName" label="姓名" width="110" />
        <el-table-column prop="username" label="登录账号" min-width="150" />
        <el-table-column prop="className" label="班级" min-width="140" />
        <el-table-column prop="phone" label="手机号" min-width="130" />
        <el-table-column label="状态" width="90"><template #default="{ row }"><StatusTag :value="row.status" /></template></el-table-column>
        <el-table-column label="操作" width="170" fixed="right" align="center">
          <template #default="{ row }">
            <div class="table-row-actions">
              <el-button link type="primary" @click="detail(row)">查看学籍</el-button>
              <el-dropdown trigger="click" @command="(command: string) => handleStudentAction(command as StudentAction, row)">
                <el-button link class="row-more-button">更多<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="scores">测评成绩</el-dropdown-item>
                    <el-dropdown-item command="materials">学习材料</el-dropdown-item>
                    <el-dropdown-item v-if="canManageStudent(row)" command="reset" divided>重置密码</el-dropdown-item>
                    <el-dropdown-item v-if="canManageStudent(row) && row.hasTemporaryPassword" command="temp">查看临时密码</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div class="table-footer"><span>共 {{ total }} 名学生</span><el-pagination v-model:current-page="pageNum" v-model:page-size="pageSize" :total="total" layout="prev, pager, next" @change="load" /></div>
    </section>

    <DetailDialog v-model="detailOpen" title="学生学籍信息" width="520px">
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
    </DetailDialog>

    <DetailDialog v-model="scoresOpen" :title="`${selected?.realName || ''} · 全部测评成绩`" width="760px">
      <div class="drawer-actions top-actions"><el-button type="primary" plain @click="exportStudentScores">导出全部成绩</el-button></div>
      <el-table :data="studentScores" empty-text="暂无该学生成绩">
        <el-table-column prop="assessmentTitle" label="测评" min-width="220" />
        <el-table-column prop="subject" label="学科" width="80"><template #default="{ row }">{{ row.subject === 'music' ? '音乐' : '美术' }}</template></el-table-column>
        <el-table-column prop="totalScore" label="总分" width="80" />
        <el-table-column prop="level" label="等级" width="90"><template #default="{ row }">{{ scoreLevelLabels[row.level as string] }}</template></el-table-column>
        <el-table-column prop="status" label="状态" width="100"><template #default="{ row }"><StatusTag :value="row.status" /></template></el-table-column>
        <el-table-column prop="createdAt" label="时间" min-width="170" />
      </el-table>
    </DetailDialog>

    <DetailDialog v-model="materialsOpen" :title="`${selected?.realName || ''} · 课外学习材料`" width="680px">
      <div class="artwork-grid">
        <article v-for="item in studentArtworks" :key="item.id" class="artwork-card">
          <div v-if="isAudioArtwork(item)" class="artwork-audio">
            <el-icon><Headset /></el-icon>
            <audio :src="item.preview" preload="metadata" controls></audio>
          </div>
          <img v-else :src="item.preview" :alt="item.fileName" />
          <div>
            <h3>{{ item.fileName }}</h3>
            <p>{{ item.uploadedAt.replace('T', ' ').slice(0, 16) }}</p>
            <span :class="item.status === 'reviewed' ? 'status-tag status-tag--success' : 'status-tag status-tag--warning'">{{ item.status === 'reviewed' ? `已评分 ${item.score ?? 0} 分` : '待评分' }}</span>
            <p v-if="item.comment" class="artwork-comment">评语：{{ item.comment }}</p>
          </div>
          <AudioTagCard
            v-if="isAudioArtwork(item)"
            :tags="item.audioTags"
            :file-id="item.id"
            show-reference
            title="作品音频参考分析"
            @analyzed="(tags) => onArtworkAnalyzed(item, tags)"
          />
          <div class="artwork-actions"><el-button link type="primary" @click="openReview(item)">{{ item.status === 'reviewed' ? '修改评分' : '评分' }}</el-button></div>
        </article>
      </div>
      <div v-if="!studentArtworks.length" class="empty-card student-card">该学生暂未上传课外学习材料。</div>
      <el-dialog v-model="reviewOpen" title="课外作品评分" width="520px" append-to-body>
        <p class="muted">{{ reviewArtwork?.fileName }} · {{ reviewArtwork?.subject === 'music' ? '音乐' : '美术' }}</p>
        <el-form label-position="top">
          <el-form-item label="作品得分（0–100）">
            <ScoreStepper v-model="reviewForm.score" :min="0" :max="100" :step="1" unit="分" />
            <div class="muted score-hint">点击 − / + 逐步加减分数，不能直接输入。</div>
          </el-form-item>
          <el-form-item label="教师评语"><el-input v-model="reviewForm.comment" type="textarea" :rows="4" maxlength="1000" show-word-limit placeholder="可从主题、构图/音准节奏、表现力等方面评价" /></el-form-item>
        </el-form>
        <template #footer><el-button @click="reviewOpen = false">取消</el-button><el-button type="primary" @click="saveReview">保存评分</el-button></template>
      </el-dialog>
    </DetailDialog>

    <el-dialog v-model="addOpen" title="手动添加学生" width="560px">
      <el-form label-position="top" class="form-grid">
        <el-form-item label="姓名" required><el-input v-model="addForm.realName" /></el-form-item>
        <el-form-item label="登录账号" required><el-input v-model="addForm.username" maxlength="32" placeholder="4~32 位字母、数字或下划线" /><div class="form-hint">{{ USERNAME_REQUIREMENT }}</div></el-form-item>
        <el-form-item label="学籍号" required><el-input :model-value="addForm.studentNo" :maxlength="20" placeholder="6~20 位字母或数字" @input="addForm.studentNo = String($event).replace(/[^A-Za-z0-9]/g, '').slice(0, 20)" /><div class="form-hint">{{ STUDENT_NO_REQUIREMENT }}</div></el-form-item>
        <el-form-item label="班级" required><el-select v-model="addForm.classId"><el-option v-for="item in manageableClasses" :key="item.id" :label="`${item.name}（${item.classCode}）`" :value="item.id" /></el-select></el-form-item>
        <el-form-item label="性别"><el-select v-model="addForm.gender"><el-option label="男" value="male" /><el-option label="女" value="female" /><el-option label="未填写" value="unknown" /></el-select></el-form-item>
        <el-form-item label="手机号"><el-input v-model="addForm.phone" /></el-form-item>
        <el-form-item label="初始密码"><el-input v-model="addForm.initialPassword" type="password" show-password maxlength="32" :placeholder="`不填则使用默认密码 ${DEFAULT_INITIAL_PASSWORD}`" /><div class="form-hint">{{ PASSWORD_REQUIREMENT }}</div></el-form-item>
        <el-form-item label="确认初始密码"><el-input v-model="addForm.initialPasswordConfirm" type="password" show-password maxlength="32" placeholder="请再次输入初始密码" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="addOpen = false">取消</el-button><el-button type="primary" @click="addStudent">确认添加</el-button></template>
    </el-dialog>

    <el-dialog v-model="resetOpen" title="重置学生密码" width="480px">
      <p class="muted">{{ resetRow?.realName }} · {{ resetRow?.username }}</p>
      <el-form label-position="top">
        <el-form-item label="新密码">
          <el-input v-model="resetPasswordValue" type="password" show-password maxlength="32" :placeholder="`留空则随机生成临时密码`" />
          <div class="form-hint">如填写，需满足：{{ PASSWORD_REQUIREMENT }}</div>
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input v-model="resetPasswordConfirm" type="password" show-password maxlength="32" placeholder="请再次输入新密码" />
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="resetOpen = false">取消</el-button><el-button type="primary" :loading="resetLoading" @click="confirmResetPassword">确认重置</el-button></template>
    </el-dialog>

    <el-dialog v-model="credentialOpen" :title="credentialTitle" width="640px">
      <el-alert title="请及时复制或下载保存；重置产生的临时密码在 10 分钟内可从「更多」再次查看，过期后需重新重置。" type="warning" :closable="false" show-icon />
      <el-table :data="credentials" size="small" class="credential-table">
        <el-table-column prop="studentNo" label="学籍号" min-width="120" />
        <el-table-column prop="name" label="姓名" width="100" />
        <el-table-column prop="username" label="登录账号" min-width="130" />
        <el-table-column prop="password" label="密码" min-width="130" />
        <el-table-column label="操作" width="80"><template #default="{ row }"><el-button link type="primary" @click="copyText(`账号：${row.username}，密码：${row.password}`)">复制</el-button></template></el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="credentialOpen = false">关闭</el-button>
        <el-button type="primary" @click="downloadCredentials">下载账号清单</el-button>
      </template>
    </el-dialog>
  </div>
</template>
