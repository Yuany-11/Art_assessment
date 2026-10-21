<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import { api } from '@/api'
import type { Question } from '@/types'

const loading = ref(false)
const rows = ref<Question[]>([])
const total = ref(0)
const pageNum = ref(1)
const pageSize = ref(10)
const filters = reactive({ subject: '', difficulty: '', type: '', grade: '', keyword: '' })
const detailOpen = ref(false)
const selected = ref<Question | null>(null)

async function load() {
  loading.value = true
  try {
    const result = await api.questions.list({ ...filters, status: 'approved', pageNum: pageNum.value, pageSize: pageSize.value })
    rows.value = result.list
    total.value = result.total
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function detail(row: Question) {
  try {
    selected.value = await api.questions.detail(row.id)
    detailOpen.value = true
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

onMounted(load)
</script>

<template>
  <div class="stack">
    <PageHeader title="题库查询" description="按学科、难度、题型和年级筛选已通过审核的公共试题。" />
    <section class="panel">
      <div class="filter-bar">
        <el-input v-model="filters.keyword" :prefix-icon="Search" clearable placeholder="搜索题干" />
        <el-select v-model="filters.subject" clearable placeholder="学科"><el-option label="音乐" value="music" /><el-option label="美术" value="art" /></el-select>
        <el-select v-model="filters.difficulty" clearable placeholder="难度"><el-option v-for="d in 5" :key="d" :label="`难度 ${d}`" :value="String(d)" /></el-select>
        <el-select v-model="filters.type" clearable placeholder="题型"><el-option label="单选" value="single_choice" /><el-option label="简答" value="short_answer" /><el-option label="图片作品" value="image_upload" /></el-select>
        <el-select v-model="filters.grade" clearable placeholder="年级"><el-option v-for="g in 12" :key="g" :label="`${g} 年级`" :value="String(g)" /></el-select>
        <el-button type="primary" @click="pageNum = 1; load()">查询</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" row-key="id" stripe empty-text="没有符合条件的试题">
        <el-table-column prop="stem" label="题干" min-width="320" show-overflow-tooltip />
        <el-table-column prop="subject" label="学科" width="80"><template #default="{ row }">{{ row.subject === 'music' ? '音乐' : '美术' }}</template></el-table-column>
        <el-table-column prop="grade" label="年级" width="70" />
        <el-table-column prop="type" label="题型" width="120" />
        <el-table-column prop="difficulty" label="难度" width="70" />
        <el-table-column prop="score" label="分值" width="70" />
        <el-table-column label="状态" width="90"><template #default="{ row }"><StatusTag :value="row.status" /></template></el-table-column>
        <el-table-column label="操作" width="90"><template #default="{ row }"><el-button link type="primary" @click="detail(row)">查看</el-button></template></el-table-column>
      </el-table>
      <div class="table-footer"><span>共 {{ total }} 道试题</span><el-pagination v-model:current-page="pageNum" v-model:page-size="pageSize" :total="total" layout="prev, pager, next" @change="load" /></div>
    </section>

    <el-drawer v-model="detailOpen" title="试题详情" size="600px">
      <template v-if="selected">
        <div class="detail-title"><div><h2>{{ selected.stem }}</h2><p>{{ selected.courseName }} · {{ selected.chapterName }}</p></div><StatusTag :value="selected.status" /></div>
        <div v-if="selected.options?.length" class="option-list static-options"><div v-for="option in selected.options" :key="option.key"><b>{{ option.key }}</b><span>{{ option.text }}</span></div></div>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="题型">{{ selected.type }}</el-descriptions-item>
          <el-descriptions-item label="难度">{{ selected.difficulty }}</el-descriptions-item>
          <el-descriptions-item label="分值">{{ selected.score }}</el-descriptions-item>
          <el-descriptions-item label="资源数量">{{ selected.resourceCount }}</el-descriptions-item>
        </el-descriptions>
        <div class="answer-tip"><b>标准答案：</b>{{ JSON.stringify(selected.answer) }}<br /><b>解析：</b>{{ selected.analysis || '暂无解析' }}</div>
      </template>
    </el-drawer>
  </div>
</template>
