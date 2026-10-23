<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import { api } from '@/api'
import type { OperationLog } from '@/types'

const rows = ref<OperationLog[]>([])
const total = ref(0)
const pageNum = ref(1)
const pageSize = ref(10)
const keyword = ref('')
const loading = ref(false)
const current = ref<OperationLog | null>(null)
const detailOpen = ref(false)

async function load() {
  loading.value = true
  try {
    const result = await api.logs.list({ keyword: keyword.value, pageNum: pageNum.value, pageSize: pageSize.value })
    rows.value = result.list
    total.value = result.total
  } finally {
    loading.value = false
  }
}

async function detail(row: OperationLog) {
  try {
    current.value = await api.logs.detail(row.id)
    detailOpen.value = true
  } catch {
    current.value = row
    detailOpen.value = true
  }
}

onMounted(load)
</script>

<template>
  <div class="stack">
    <PageHeader title="操作日志" description="查询账号、题库、测评和资源相关审计记录。">
      <el-input v-model="keyword" :prefix-icon="Search" clearable placeholder="操作人、动作或说明" @keyup.enter="load" />
      <el-button type="primary" @click="pageNum = 1; load()">查询</el-button>
    </PageHeader>
    <section class="panel">
      <el-table v-loading="loading" :data="rows" row-key="id" stripe>
        <el-table-column prop="createdAt" label="操作时间" min-width="180" />
        <el-table-column prop="operatorName" label="操作人" width="120" />
        <el-table-column prop="action" label="操作类型" min-width="160" />
        <el-table-column prop="resourceType" label="资源类型" width="110" />
        <el-table-column prop="description" label="说明" min-width="260" />
        <el-table-column label="结果" width="90"><template #default="{ row }"><StatusTag :value="row.result" /></template></el-table-column>
        <el-table-column label="操作" width="90"><template #default="{ row }"><el-button link type="primary" @click="detail(row)">详情</el-button></template></el-table-column>
      </el-table>
      <div class="table-footer"><span>共 {{ total }} 条日志</span><el-pagination v-model:current-page="pageNum" v-model:page-size="pageSize" :total="total" layout="prev, pager, next" @change="load" /></div>
    </section>
    <el-drawer v-model="detailOpen" title="日志详情" size="460px">
      <el-descriptions v-if="current" :column="1" border>
        <el-descriptions-item label="日志编号">{{ current.id }}</el-descriptions-item>
        <el-descriptions-item label="操作人">{{ current.operatorName }}</el-descriptions-item>
        <el-descriptions-item label="操作时间">{{ current.createdAt }}</el-descriptions-item>
        <el-descriptions-item label="操作类型">{{ current.action }}</el-descriptions-item>
        <el-descriptions-item label="资源">{{ current.resourceType }} / {{ current.resourceId }}</el-descriptions-item>
        <el-descriptions-item label="IP 地址">{{ current.ip }}</el-descriptions-item>
        <el-descriptions-item label="说明">{{ current.description }}</el-descriptions-item>
      </el-descriptions>
    </el-drawer>
  </div>
</template>
