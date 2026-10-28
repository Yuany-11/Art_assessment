<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import { api } from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { Account, ClassRequest, SchoolClass } from '@/types'

const auth = useAuthStore()
const loading = ref(false)
const rows = ref<SchoolClass[]>([])
const total = ref(0)
const pageNum = ref(1)
const pageSize = ref(10)
const keyword = ref('')
const classCodeQuery = ref('')
const dialogOpen = ref(false)
const editing = ref<SchoolClass | null>(null)
const detailOpen = ref(false)
const selectedClassInfo = ref<SchoolClass | null>(null)
const requestOpen = ref(false)
const studentOpen = ref(false)
const studentDetailOpen = ref(false)
const selectedClass = ref<SchoolClass | null>(null)
const selectedStudent = ref<Account | null>(null)
const requests = ref<ClassRequest[]>([])
const students = ref<Account[]>([])
const studentKeyword = ref('')
const importInput = ref<HTMLInputElement>()
const teachers = ref<Account[]>([])
const form = reactive({ name: '', classCode: '', grade: 7, headTeacherId: undefined as number | undefined, description: '' })

function canManageClass(row: SchoolClass) {
  if (auth.role === 'school_admin') return true
  return auth.role === 'teacher' && row.headTeacherId === auth.user?.id
}

async function load() {
  loading.value = true
  try {
    const result = await api.classes.list({ keyword: keyword.value, pageNum: pageNum.value, pageSize: pageSize.value })
    rows.value = result.list
    total.value = result.total
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function searchByCode() {
  const code = classCodeQuery.value.trim()
  if (!code) return ElMessage.warning('请输入班级号')
  loading.value = true
  try {
    const found = await api.classes.search(code)
    if (!found) {
      rows.value = []
      total.value = 0
      ElMessage.warning('未找到该班级，请核对班级号')
      return
    }
    rows.value = [found]
    total.value = 1
    pageNum.value = 1
    openClassInfo(found)
    ElMessage.success(`已找到 ${found.name}`)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  Object.assign(form, { name: '', classCode: '', grade: 7, headTeacherId: undefined, description: '' })
  dialogOpen.value = true
}

function openEdit(row: SchoolClass) {
  editing.value = row
  Object.assign(form, {
    name: row.name,
    classCode: row.classCode,
    grade: row.grade,
    headTeacherId: row.headTeacherId ?? undefined,
    description: ''
  })
  dialogOpen.value = true
}

function openClassInfo(row: SchoolClass) {
  selectedClassInfo.value = row
  detailOpen.value = true
}

async function save() {
  if (!form.name.trim()) return ElMessage.warning('请填写班级名称')
  try {
    if (editing.value) {
      await api.classes.update(editing.value.id, {
        name: form.name.trim(),
        grade: Number(form.grade),
        headTeacherId: form.headTeacherId ?? null
      })
    } else {
      await api.classes.create({
        name: form.name.trim(),
        classCode: form.classCode.trim() || undefined,
        grade: Number(form.grade),
        headTeacherId: form.headTeacherId ?? null
      } as Partial<SchoolClass>)
    }
    dialogOpen.value = false
    ElMessage.success('班级信息已保存')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function loadTeachers() {
  if (auth.role !== 'school_admin') {
    teachers.value = []
    return
  }
  try {
    const result = await api.accounts.list('teachers', { pageSize: 100 })
    teachers.value = result.list
  } catch {
    teachers.value = []
  }
}

async function archive(row: SchoolClass) {
  try {
    await ElMessageBox.confirm(`确定归档“${row.name}”吗？历史成绩会保留。`, '归档班级', { type: 'warning' })
    await api.classes.update(row.id, { status: 'archived' })
    ElMessage.success('班级已归档')
    await load()
  } catch (error) {
    if (error instanceof Error) ElMessage.error(error.message)
  }
}

async function openRequests(row: SchoolClass) {
  selectedClass.value = row
  requestOpen.value = true
  requests.value = await api.classes.requests(row.id)
}

async function openStudents(row: SchoolClass) {
  selectedClass.value = row
  studentOpen.value = true
  await loadStudents()
}

function openStudentInfo(student: Account) {
  selectedStudent.value = student
  studentDetailOpen.value = true
}

async function loadStudents() {
  if (!selectedClass.value) return
  const result = await api.classes.students(selectedClass.value.id, { keyword: studentKeyword.value, pageSize: 100 })
  students.value = result.list
}

async function removeStudent(student: Account) {
  if (!selectedClass.value) return
  try {
    await ElMessageBox.confirm(`将“${student.realName}”移出当前班级？学生账号和历史成绩会保留。`, '移出学生', { type: 'warning' })
    await api.classes.removeStudent(selectedClass.value.id, student.id)
    await loadStudents()
    await load()
    ElMessage.success('学生已移出班级')
  } catch (error) {
    if (error instanceof Error) ElMessage.error(error.message)
  }
}

async function importStudents(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file || !selectedClass.value) return
  try {
    const result = await api.classes.importStudents(selectedClass.value.id, file)
    ElMessage.success(`导入完成：成功 ${result.successCount} 条，失败 ${result.failCount} 条`)
    await Promise.all([loadStudents(), load()])
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    ;(event.target as HTMLInputElement).value = ''
  }
}

async function applyAsTeacher(row: SchoolClass) {
  try {
    const result = await ElMessageBox.prompt('请填写申请说明，班主任或学校管理员审核后生效。', '申请成为科任教师', {
      inputValue: '申请加入本班承担音乐或美术教学',
      inputValidator: (value) => Boolean(value?.trim()) || '申请说明不能为空'
    })
    await api.classes.request('join', row.id, result.value, undefined, (auth.user?.subject as 'music' | 'art' | undefined) ?? 'music')
    ElMessage.success('科任教师申请已提交')
  } catch (error) {
    if (error instanceof Error) ElMessage.error(error.message)
  }
}

async function review(item: ClassRequest, action: 'approve' | 'reject') {
  if (!selectedClass.value) return
  try {
    await api.classes.review(selectedClass.value.id, item.id, action, action === 'approve' ? '信息核对无误' : '信息不符合要求')
    requests.value = await api.classes.requests(selectedClass.value.id)
    await load()
    ElMessage.success(action === 'approve' ? '申请已通过，学生班级信息已同步' : '申请已驳回')
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

onMounted(() => {
  load()
  loadTeachers()
})
</script>

<template>
  <div class="stack">
    <PageHeader title="班级管理" description="教师管理本人班级，学校管理员维护本校班级并审核学生申请。">
      <el-button type="primary" :icon="Plus" @click="openCreate">创建班级</el-button>
    </PageHeader>
    <el-alert
      title="操作提示"
      description="输入完整班级号可精确查询并打开班级信息；班主任信息、学生名册和入班申请均可在当前页面查看和审核。"
      type="info"
      :closable="false"
      show-icon
    />
    <section class="panel">
      <div class="filter-bar">
        <el-input v-model="keyword" :prefix-icon="Search" clearable placeholder="班级名称或班级号" @keyup.enter="load" />
        <el-button type="primary" @click="pageNum = 1; load()">查询</el-button>
        <el-input v-model="classCodeQuery" clearable placeholder="输入完整班级号" @keyup.enter="searchByCode" />
        <el-button @click="searchByCode">按班级号查询</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" row-key="id" stripe>
        <el-table-column prop="classCode" label="班级号" min-width="140" />
        <el-table-column prop="name" label="班级名称" min-width="160" />
        <el-table-column prop="grade" label="年级" width="80" />
        <el-table-column prop="schoolName" label="学校" min-width="150" />
        <el-table-column prop="headTeacherName" label="班主任" width="100" />
        <el-table-column prop="studentCount" label="学生人数" width="100" />
        <el-table-column label="状态" width="90"><template #default="{ row }"><StatusTag :value="row.status" /></template></el-table-column>
        <el-table-column label="操作" width="330" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openClassInfo(row)">班级信息</el-button>
            <el-button v-if="canManageClass(row)" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="auth.role === 'teacher'" link @click="applyAsTeacher(row)">申请科任</el-button>
            <el-button link @click="openStudents(row)">学生名单</el-button>
            <el-button link @click="openRequests(row)">学生审核</el-button>
            <el-button v-if="canManageClass(row)" link type="danger" :disabled="row.status === 'archived'" @click="archive(row)">归档</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="table-footer"><span>共 {{ total }} 个班级</span><el-pagination v-model:current-page="pageNum" v-model:page-size="pageSize" :total="total" layout="prev, pager, next" @change="load" /></div>
    </section>

    <el-dialog v-model="dialogOpen" :title="editing ? '编辑班级' : '创建班级'" width="560px">
      <el-form label-position="top" class="form-grid">
        <el-form-item label="班级名称" required class="span-2"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="班级号"><el-input v-model="form.classCode" :disabled="Boolean(editing)" placeholder="不填则自动生成" /></el-form-item>
        <el-form-item label="年级"><el-select v-model="form.grade"><el-option v-for="g in 12" :key="g" :label="`${g} 年级`" :value="g" /></el-select></el-form-item>
        <el-form-item v-if="auth.role === 'school_admin'" label="班主任" class="span-2">
          <el-select v-model="form.headTeacherId" clearable placeholder="暂不指定" filterable>
            <el-option v-for="teacher in teachers" :key="teacher.id" :label="`${teacher.realName}（${teacher.username}）`" :value="teacher.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-else label="班主任" class="span-2">
          <el-text type="info">班主任由学校管理员指定；如需调整请联系本校管理员。</el-text>
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogOpen = false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template>
    </el-dialog>

    <el-drawer v-model="detailOpen" title="班级信息" size="560px">
      <el-descriptions v-if="selectedClassInfo" :column="1" border>
        <el-descriptions-item label="班级号">{{ selectedClassInfo.classCode }}</el-descriptions-item>
        <el-descriptions-item label="班级名称">{{ selectedClassInfo.name }}</el-descriptions-item>
        <el-descriptions-item label="所属学校">{{ selectedClassInfo.schoolName }}</el-descriptions-item>
        <el-descriptions-item label="年级">{{ selectedClassInfo.grade }} 年级</el-descriptions-item>
        <el-descriptions-item label="班主任">{{ selectedClassInfo.headTeacherName }}</el-descriptions-item>
        <el-descriptions-item label="班主任账号">{{ selectedClassInfo.headTeacherAccount || '—' }}</el-descriptions-item>
        <el-descriptions-item label="任教学科">{{ selectedClassInfo.headTeacherSubject === 'music' ? '音乐' : selectedClassInfo.headTeacherSubject === 'art' ? '美术' : '—' }}</el-descriptions-item>
        <el-descriptions-item label="联系电话">{{ selectedClassInfo.headTeacherPhone || '—' }}</el-descriptions-item>
        <el-descriptions-item label="学生人数">{{ selectedClassInfo.studentCount }}</el-descriptions-item>
        <el-descriptions-item label="状态"><StatusTag :value="selectedClassInfo.status" /></el-descriptions-item>
      </el-descriptions>
    </el-drawer>

    <el-drawer v-model="requestOpen" :title="`${selectedClass?.name || ''} · 学生审核`" size="600px">
      <el-alert title="审核通过后，学生所属班级和班级人数会同步更新。" type="info" :closable="false" show-icon />
      <el-table :data="requests">
        <el-table-column prop="requesterName" label="申请人" width="100" />
        <el-table-column label="身份" width="80"><template #default="{ row }">{{ row.requesterRole === 'student' ? '学生' : '教师' }}</template></el-table-column>
        <el-table-column prop="type" label="类型" width="80"><template #default="{ row }">{{ row.type === 'join' ? '加入' : row.type === 'leave' ? '退出' : '转班' }}</template></el-table-column>
        <el-table-column prop="reason" label="原因" min-width="140" />
        <el-table-column label="状态" width="90"><template #default="{ row }"><StatusTag :value="row.status" /></template></el-table-column>
        <el-table-column label="操作" width="120"><template #default="{ row }"><template v-if="row.status === 'pending'"><el-button link @click="review(row, 'approve')">通过</el-button><el-button link type="danger" @click="review(row, 'reject')">驳回</el-button></template></template></el-table-column>
      </el-table>
    </el-drawer>

    <el-drawer v-model="studentOpen" :title="`${selectedClass?.name || ''} · 学生管理`" size="680px">
      <div class="filter-bar">
        <el-input v-model="studentKeyword" :prefix-icon="Search" clearable placeholder="姓名、账号或学籍号" @keyup.enter="loadStudents" />
        <el-button type="primary" @click="loadStudents">查询</el-button>
        <el-button @click="importInput?.click()">批量导入学生</el-button>
        <input ref="importInput" class="hidden-input" type="file" accept=".csv,.xlsx" @change="importStudents" />
      </div>
      <el-table :data="students" class="roster-table">
        <el-table-column prop="studentNo" label="学籍号" min-width="140" />
        <el-table-column prop="realName" label="姓名" width="100" />
        <el-table-column prop="username" label="账号" min-width="150" />
        <el-table-column prop="phone" label="手机号" min-width="130" />
        <el-table-column label="操作" width="150">
          <template #default="{ row }"><el-button link type="primary" @click="openStudentInfo(row)">查看信息</el-button><el-button link type="danger" @click="removeStudent(row)">移出班级</el-button></template>
        </el-table-column>
      </el-table>
    </el-drawer>

    <el-drawer v-model="studentDetailOpen" title="学生信息" size="500px">
      <el-descriptions v-if="selectedStudent" :column="1" border>
        <el-descriptions-item label="姓名">{{ selectedStudent.realName }}</el-descriptions-item>
        <el-descriptions-item label="学籍号">{{ selectedStudent.studentNo || '—' }}</el-descriptions-item>
        <el-descriptions-item label="登录账号">{{ selectedStudent.username }}</el-descriptions-item>
        <el-descriptions-item label="所属班级">{{ selectedStudent.className || '未分班' }}</el-descriptions-item>
        <el-descriptions-item label="年级">{{ selectedStudent.grade || '—' }}</el-descriptions-item>
        <el-descriptions-item label="手机号">{{ selectedStudent.phone || '—' }}</el-descriptions-item>
        <el-descriptions-item label="邮箱">{{ selectedStudent.email || '—' }}</el-descriptions-item>
        <el-descriptions-item label="账号状态"><StatusTag :value="selectedStudent.status" /></el-descriptions-item>
      </el-descriptions>
    </el-drawer>
  </div>
</template>
