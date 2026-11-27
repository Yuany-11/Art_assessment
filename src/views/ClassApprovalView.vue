<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import { api } from '@/api'
import type { ClassRequest } from '@/types'

const loading = ref(false)
const rows = ref<ClassRequest[]>([])
const type = ref<'join' | 'change' | 'leave' | ''>('')

async function load() {
  loading.value = true
  try {
    rows.value = await api.classes.pendingRequests({ type: type.value || undefined })
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

function typeLabel(value: ClassRequest['type']) {
  return value === 'join' ? '加入班级' : value === 'leave' ? '退出班级' : '转班'
}

async function review(item: ClassRequest, action: 'approve' | 'reject') {
  let comment = action === 'approve' ? '信息核对无误' : '信息不符合要求'
  if (action === 'reject') {
    try {
      const result = await ElMessageBox.prompt('请填写驳回原因，申请人会收到通知。', '驳回申请', {
        inputValue: comment,
        inputValidator: (value) => Boolean(value?.trim()) || '请填写驳回原因'
      })
      comment = result.value
    } catch {
      return
    }
  }
  const classId = item.reviewClassId || item.classId
  try {
    const result = await api.classes.review(classId, item.id, action, comment)
    if (action === 'approve' && item.type === 'change' && result.status === 'pending') {
      ElMessage.success('本级审核已通过，等待另一方班主任确认后生效')
    } else {
      ElMessage.success(action === 'approve' ? '申请已通过' : '申请已驳回')
    }
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

onMounted(load)
</script>

<template>
  <div class="stack">
    <PageHeader title="入班审批" description="集中处理加入、退出和转班申请，无需逐个进入班级。">
      <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
    </PageHeader>
    <el-alert
      title="审批说明"
      description="转班申请需要原班级和目标班级双方班主任分别通过；任一方驳回后申请关闭。"
      type="info"
      :closable="false"
      show-icon
    />
    <section class="panel">
      <div class="filter-bar">
        <el-select v-model="type" clearable placeholder="全部申请类型" @change="load">
          <el-option label="加入班级" value="join" />
          <el-option label="退出班级" value="leave" />
          <el-option label="转班" value="change" />
        </el-select>
      </div>
      <el-table v-loading="loading" :data="rows" row-key="id" stripe empty-text="暂无待审核申请">
        <el-table-column prop="requesterName" label="申请人" width="110" />
        <el-table-column label="身份" width="80">
          <template #default="{ row }">{{ row.requesterRole === 'student' ? '学生' : '教师' }}</template>
        </el-table-column>
        <el-table-column label="申请类型" width="100">
          <template #default="{ row }">{{ typeLabel(row.type) }}</template>
        </el-table-column>
        <el-table-column label="申请班级" min-width="200">
          <template #default="{ row }">
            <span>{{ row.className }}</span>
            <span v-if="row.type === 'change' && row.targetClassName" class="muted"> → {{ row.targetClassName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="申请原因" min-width="200" show-overflow-tooltip />
        <el-table-column label="双签进度" width="190">
          <template #default="{ row }">
            <template v-if="row.type === 'change'">
              <el-tag :type="row.sourceApproved ? 'success' : 'info'" size="small" effect="plain">原班{{ row.sourceApproved ? '已通过' : '待审' }}</el-tag>
              <el-tag :type="row.targetApproved ? 'success' : 'info'" size="small" effect="plain" style="margin-left: 6px">目标班{{ row.targetApproved ? '已通过' : '待审' }}</el-tag>
            </template>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :value="row.status" /></template>
        </el-table-column>
        <el-table-column prop="createdAt" label="提交时间" width="170" />
        <el-table-column label="操作" width="130" fixed="right" align="center">
          <template #default="{ row }">
            <template v-if="row.status === 'pending'">
              <el-button link type="primary" @click="review(row, 'approve')">通过</el-button>
              <el-button link type="danger" @click="review(row, 'reject')">驳回</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
      <div class="table-footer"><span>共 {{ rows.length }} 条待审核申请</span></div>
    </section>
  </div>
</template>
