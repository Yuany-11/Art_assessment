<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, RefreshLeft, Search, UploadFilled } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import { api } from '@/api'
import type { Account, AccountKind } from '@/types'

const props = defineProps<{ kind: AccountKind }>()

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
const form = reactive({
  username: '',
  realName: '',
  phone: '',
  email: '',
  studentNo: '',
  subject: 'music',
  grade: 7,
  orgName: '',
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
    status: row.status
  })
  editorOpen.value = true
}

async function save() {
  if (!form.realName.trim() || (!editing.value && !form.username.trim())) {
    ElMessage.warning('请填写账号和姓名')
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
      await api.accounts.create(props.kind, { ...form })
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

async function importAccounts(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  const result = await api.accounts.import(props.kind, file)
  ElMessage.success(`导入完成：成功 ${result.successCount} 条，失败 ${result.failCount} 条`)
  ;(event.target as HTMLInputElement).value = ''
}

function search() {
  pageNum.value = 1
  load()
}

watch(() => props.kind, () => {
  pageNum.value = 1
  editorOpen.value = false
  load()
})
onMounted(load)
</script>

<template>
  <div class="stack">
    <PageHeader :title="config.title" :description="config.description">
      <el-button v-if="kind === 'teachers' || kind === 'students'" :icon="UploadFilled" @click="chooseImportFile">批量导入</el-button>
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
  </div>
</template>
