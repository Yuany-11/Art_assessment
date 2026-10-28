<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, RefreshLeft, Search, UploadFilled } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import { api } from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { Account, AccountKind, OrgOption, SchoolClass } from '@/types'

const props = defineProps<{ kind: AccountKind }>()
const auth = useAuthStore()

const configs: Record<AccountKind, { title: string; description: string; role: string; orgLabel: string }> = {
  teachers: { title: '教师账号管理', description: '维护本校教师账号、任教班级和账号状态。', role: '教师', orgLabel: '所属学校' },
  students: { title: '学生账号管理', description: '维护学生账号、学籍信息和班级关系。', role: '学生', orgLabel: '所属学校' },
  schools: { title: '学校账号管理', description: '创建和维护权限范围内的学校及管理员账号。', role: '学校管理员', orgLabel: '学校名称' },
  districts: { title: '区县账号管理', description: '维护市州范围内的区县及区县管理员账号。', role: '区县管理员', orgLabel: '区县名称' },
  cities: { title: '市州账号管理', description: '维护全省市州及市州管理员账号。', role: '市州管理员', orgLabel: '市州名称' }
}

const config = computed(() => configs[props.kind])
const loading = ref(false)
const rows = ref<Account[]>([])
const total = ref(0)
const pageNum = ref(1)
const pageSize = ref(10)
const keyword = ref('')
const status = ref('')
const editorOpen = ref(false)
const editing = ref<Account | null>(null)
const fileInput = ref<HTMLInputElement>()
const classes = ref<SchoolClass[]>([])
const importClassId = ref<number>()
const credentialOpen = ref(false)
const credentials = ref<Array<{ studentNo: string; name: string; username: string; password: string }>>([])
const orgOptions = ref<OrgOption[]>([])
const needsDistrict = computed(() => props.kind === 'schools' && auth.role === 'province_admin')
const needsCity = computed(() => props.kind === 'districts' && auth.role === 'province_admin')
const needsSchool = computed(() => props.kind === 'students' && auth.role !== 'school_admin')
const canImport = computed(() => auth.role === 'school_admin')
const form = reactive({
  username: '',
  realName: '',
  phone: '',
  email: '',
  studentNo: '',
  subject: 'music',
  grade: 7,
  orgName: '',
  schoolType: 'middle',
  districtId: undefined as number | undefined,
  cityId: undefined as number | undefined,
  schoolId: undefined as number | undefined,
  classId: undefined as number | undefined,
  classIds: [] as number[],
  status: 'active'
})

function resetForm() {
  Object.assign(form, {
    username: '',
    realName: '',
    phone: '',
    email: '',
    studentNo: '',
    subject: 'music',
    grade: 7,
    orgName: '',
    schoolType: 'middle',
    districtId: undefined,
    cityId: undefined,
    schoolId: undefined,
    classId: undefined,
    classIds: [],
    status: 'active'
  })
}

async function load() {
  loading.value = true
  try {
    const result = await api.accounts.list(props.kind, {
      keyword: keyword.value,
      status: status.value,
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

function openCreate() {
  editing.value = null
  resetForm()
  editorOpen.value = true
}

function chooseImportFile() {
  fileInput.value?.click()
}

function openEdit(row: Account) {
  editing.value = row
  Object.assign(form, {
    username: row.username,
    realName: row.realName,
    phone: row.phone ?? '',
    email: row.email ?? '',
    studentNo: row.studentNo ?? '',
    subject: row.subject ?? 'music',
    grade: row.grade ?? 7,
    orgName: row.orgName ?? '',
    schoolType: 'middle',
    districtId: undefined,
    cityId: undefined,
    schoolId: undefined,
    classId: row.classId ?? undefined,
    classIds: row.classId ? [row.classId] : [],
    status: row.status
  })
  editorOpen.value = true
}

function createPayload() {
  const base = { username: form.username.trim(), realName: form.realName.trim() }
  if (props.kind === 'teachers') {
    return {
      ...base,
      phone: form.phone.trim(),
      email: form.email || null,
      subject: form.subject,
      classIds: form.classIds,
      status: form.status
    }
  }
  if (props.kind === 'students') {
    return {
      ...base,
      studentNo: form.studentNo.trim(),
      gender: 'unknown',
      grade: Number(form.grade),
      phone: form.phone || null,
      guardianPhone: form.phone || null,
      ...(needsSchool.value ? { schoolId: form.schoolId } : {}),
      ...(form.classId ? { classId: form.classId } : {})
    }
  }
  const org = {
    adminUsername: form.username.trim(),
    adminRealName: form.realName.trim(),
    adminPhone: form.phone.trim()
  }
  if (props.kind === 'schools') {
    return {
      ...org,
      schoolCode: form.username.trim(),
      schoolName: form.orgName.trim() || form.realName.trim(),
      schoolType: form.schoolType,
      ...(needsDistrict.value ? { districtId: form.districtId } : {}),
      ...(auth.role === 'city_admin' && auth.user?.cityId ? { cityId: auth.user.cityId } : {})
    }
  }
  if (props.kind === 'districts') {
    return {
      ...org,
      districtCode: form.username.trim(),
      districtName: form.orgName.trim() || form.realName.trim(),
      ...(needsCity.value ? { cityId: form.cityId } : {})
    }
  }
  return { ...org, cityCode: form.username.trim(), cityName: form.orgName.trim() || form.realName.trim() }
}

async function save() {
  if (!form.realName.trim() || (!editing.value && !form.username.trim())) {
    ElMessage.warning('请填写账号和姓名')
    return
  }
  if (!editing.value && props.kind !== 'students' && !form.phone.trim()) {
    ElMessage.warning('请填写手机号')
    return
  }
  if (!editing.value && props.kind === 'students' && !form.studentNo.trim()) {
    ElMessage.warning('请填写学籍号')
    return
  }
  if (!editing.value && ['schools', 'districts', 'cities'].includes(props.kind) && !form.orgName.trim()) {
    ElMessage.warning(`请填写${config.value.orgLabel}`)
    return
  }
  if (!editing.value && needsDistrict.value && !form.districtId) {
    ElMessage.warning('请选择所属区县')
    return
  }
  if (!editing.value && needsCity.value && !form.cityId) {
    ElMessage.warning('请选择所属市州')
    return
  }
  if (!editing.value && needsSchool.value && !form.schoolId) {
    ElMessage.warning('请选择所属学校')
    return
  }
  try {
    if (editing.value) {
      await api.accounts.update(editing.value.id, {
        realName: form.realName,
        phone: form.phone || null,
        email: form.email || null,
        status: form.status as Account['status']
      })
      ElMessage.success('账号信息已更新')
    } else {
      await api.accounts.create(props.kind, createPayload())
      ElMessage.success('账号已创建')
    }
    editorOpen.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function remove(row: Account) {
  try {
    await ElMessageBox.confirm(`确定删除“${row.realName}”的账号吗？`, '删除账号', { type: 'warning' })
    await api.accounts.remove(row.id)
    ElMessage.success('账号已删除')
    await load()
  } catch (error) {
    if (error instanceof Error) ElMessage.error(error.message)
  }
}

async function resetPassword(row: Account) {
  try {
    await ElMessageBox.confirm(`重置“${row.realName}”的密码？`, '重置密码', { type: 'warning' })
    const result = await api.accounts.resetPassword(row.id)
    await ElMessageBox.alert(`临时密码：${result.temporaryPassword}。用户下次登录后必须修改。`, '重置成功')
  } catch (error) {
    if (error instanceof Error) ElMessage.error(error.message)
  }
}

async function loadOrgOptions() {
  orgOptions.value = []
  const level: 'city' | 'district' | 'school' | null = needsDistrict.value
    ? 'district'
    : needsCity.value
      ? 'city'
      : needsSchool.value
        ? 'school'
        : null
  if (!level) return
  try {
    const result = await api.accounts.orgOptions({ level })
    orgOptions.value = result.list
    if (level === 'district' && !form.districtId) form.districtId = result.list[0]?.id
    if (level === 'city' && !form.cityId) form.cityId = result.list[0]?.id
    if (level === 'school' && !form.schoolId) {
      form.schoolId = result.list[0]?.id
      if (form.schoolId) await loadClasses(form.schoolId)
    }
  } catch {
    orgOptions.value = []
  }
}

async function loadClasses(schoolId?: number) {
  if (!['students', 'teachers'].includes(props.kind)) return
  if (props.kind === 'students' && needsSchool.value && !schoolId) {
    classes.value = []
    return
  }
  try {
    const result = await api.classes.list({
      pageSize: 100,
      ...(schoolId ? { schoolId } : {})
    })
    classes.value = result.list
    if (!importClassId.value || !classes.value.some((item) => item.id === importClassId.value)) {
      importClassId.value = classes.value[0]?.id
    }
    if (form.classId && !classes.value.some((item) => item.id === form.classId)) form.classId = undefined
  } catch {
    classes.value = []
  }
}

async function onSchoolChange() {
  form.classId = undefined
  await loadClasses(form.schoolId)
}

let importPolling = false

async function pollImport(taskId: string) {
  importPolling = true
  for (let index = 0; index < 60 && importPolling; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 2000))
    if (!importPolling) return
    try {
      const task = await api.accounts.importTask(taskId)
      if (task.status === 'completed') {
        ElMessage.success(`导入完成：成功 ${task.successCount} 条，失败 ${task.failCount} 条`)
        await load()
        return
      }
      if (task.status === 'failed') {
        ElMessage.error('导入任务失败，请检查文件后重试')
        return
      }
    } catch {
      return
    }
  }
  ElMessage.warning('导入仍在后台处理，可稍后刷新列表查看结果')
}

async function importAccounts(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  if (props.kind === 'students' && !importClassId.value) {
    ElMessage.warning('请先选择导入的目标班级')
    ;(event.target as HTMLInputElement).value = ''
    return
  }
  try {
    const result = await api.accounts.import(props.kind, file, importClassId.value)
    if (result.status === 'queued') {
      ElMessage.info('文件较大，已进入后台处理，请稍候')
      await pollImport(String(result.taskId))
    } else {
      credentials.value = (result.credentials as typeof credentials.value | undefined) ?? []
      ElMessage.success(`导入完成：成功 ${result.successCount} 条，失败 ${result.failCount} 条`)
      if (credentials.value.length) credentialOpen.value = true
      await load()
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
  ;(event.target as HTMLInputElement).value = ''
}

onUnmounted(() => {
  importPolling = false
})

function downloadCredentials() {
  if (!credentials.value.length) return
  const lines = [['学籍号', '姓名', '登录账号', '初始密码'], ...credentials.value.map((item) => [item.studentNo, item.name, item.username, item.password])]
  const url = URL.createObjectURL(new Blob([`﻿${lines.map((line) => line.join(',')).join('\n')}`], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = '学生账号清单.csv'
  link.click()
  URL.revokeObjectURL(url)
}

function search() {
  pageNum.value = 1
  load()
}

watch(() => props.kind, () => {
  pageNum.value = 1
  editorOpen.value = false
  load()
  loadOrgOptions()
  loadClasses()
})
onMounted(() => {
  load()
  loadOrgOptions()
  loadClasses()
})
</script>

<template>
  <div class="stack">
    <PageHeader :title="config.title" :description="config.description">
      <el-select v-if="kind === 'students' && canImport" v-model="importClassId" style="width: 200px" placeholder="导入目标班级">
        <el-option v-for="item in classes" :key="item.id" :label="item.name" :value="item.id" />
      </el-select>
      <el-button v-if="canImport && (kind === 'teachers' || kind === 'students')" :icon="UploadFilled" @click="chooseImportFile">批量导入</el-button>
      <input ref="fileInput" class="hidden-input" type="file" accept=".csv,.xlsx" @change="importAccounts" />
      <el-button type="primary" :icon="Plus" @click="openCreate">新建{{ config.role }}账号</el-button>
    </PageHeader>

    <section class="panel">
      <div class="filter-bar">
        <el-input v-model="keyword" :prefix-icon="Search" clearable placeholder="账号、姓名或学籍号" @keyup.enter="search" />
        <el-select v-model="status" clearable placeholder="账号状态">
          <el-option label="正常" value="active" />
          <el-option label="已禁用" value="disabled" />
        </el-select>
        <el-button type="primary" @click="search">查询</el-button>
        <el-button :icon="RefreshLeft" @click="keyword = ''; status = ''; search()">重置</el-button>
      </div>

      <el-table v-loading="loading" :data="rows" row-key="id" stripe>
        <el-table-column prop="username" label="登录账号" min-width="135" />
        <el-table-column prop="realName" label="姓名 / 名称" min-width="120" />
        <el-table-column v-if="kind === 'students'" prop="studentNo" label="学籍号" min-width="130" />
        <el-table-column v-if="kind === 'teachers'" prop="subject" label="学科" width="90">
          <template #default="{ row }">{{ row.subject === 'music' ? '音乐' : '美术' }}</template>
        </el-table-column>
        <el-table-column :label="config.orgLabel" min-width="135">
          <template #default="{ row }">{{ row.orgName || row.className || '—' }}</template>
        </el-table-column>
        <el-table-column prop="phone" label="手机号" min-width="125">
          <template #default="{ row }">{{ row.phone || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><StatusTag :value="row.status" /></template>
        </el-table-column>
        <el-table-column prop="createdAt" label="创建时间" width="150">
          <template #default="{ row }">{{ dayjs(row.createdAt).format('YYYY-MM-DD HH:mm') }}</template>
        </el-table-column>
        <el-table-column label="操作" width="205" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link @click="resetPassword(row)">重置密码</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="table-footer">
        <span>共 {{ total }} 个账号</span>
        <el-pagination v-model:current-page="pageNum" v-model:page-size="pageSize" :total="total" layout="prev, pager, next, sizes" @change="load" />
      </div>
    </section>

    <el-dialog v-model="editorOpen" :title="editing ? `编辑${config.role}账号` : `新建${config.role}账号`" width="640px">
      <el-form label-position="top" class="form-grid">
        <el-form-item label="登录账号" required>
          <el-input v-model="form.username" :disabled="Boolean(editing)" placeholder="例如 school301" />
        </el-form-item>
        <el-form-item label="姓名 / 名称" required>
          <el-input v-model="form.realName" placeholder="请输入真实名称" />
        </el-form-item>
        <el-form-item v-if="kind === 'students'" label="学籍号" required>
          <el-input v-model="form.studentNo" :disabled="Boolean(editing)" />
        </el-form-item>
        <el-form-item v-if="kind === 'teachers'" label="任教学科">
          <el-select v-model="form.subject">
            <el-option label="音乐" value="music" />
            <el-option label="美术" value="art" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="kind === 'students'" label="年级">
          <el-select v-model="form.grade">
            <el-option v-for="grade in 12" :key="grade" :label="`${grade} 年级`" :value="grade" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="['schools', 'districts', 'cities'].includes(kind)" :label="config.orgLabel">
          <el-input v-model="form.orgName" />
        </el-form-item>
        <el-form-item v-if="needsDistrict" label="所属区县" required>
          <el-select v-model="form.districtId" filterable placeholder="请选择区县" style="width: 100%">
            <el-option v-for="item in orgOptions" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="needsCity" label="所属市州" required>
          <el-select v-model="form.cityId" filterable placeholder="请选择市州" style="width: 100%">
            <el-option v-for="item in orgOptions" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="needsSchool" label="所属学校" required>
          <el-select v-model="form.schoolId" filterable placeholder="请选择学校" style="width: 100%" @change="onSchoolChange">
            <el-option v-for="item in orgOptions" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="kind === 'schools'" label="学校类型">
          <el-select v-model="form.schoolType">
            <el-option label="小学" value="primary" />
            <el-option label="初中" value="middle" />
            <el-option label="高中" value="high" />
            <el-option label="九年/十二年一贯制" value="combined" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="kind === 'students'" label="所在班级">
          <el-select
            v-model="form.classId"
            clearable
            filterable
            :disabled="needsSchool && !form.schoolId"
            placeholder="可暂不分配班级"
            style="width: 100%"
          >
            <el-option v-for="item in classes" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="kind === 'teachers'" label="任教班级">
          <el-select v-model="form.classIds" multiple filterable placeholder="可暂不分配班级" style="width: 100%">
            <el-option v-for="item in classes" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="form.phone" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" />
        </el-form-item>
        <el-form-item label="账号状态">
          <el-radio-group v-model="form.status">
            <el-radio value="active">正常</el-radio>
            <el-radio value="disabled">禁用</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editorOpen = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>

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
