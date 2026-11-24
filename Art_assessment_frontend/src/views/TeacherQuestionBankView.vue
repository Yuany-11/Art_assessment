<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import DetailDialog from '@/components/DetailDialog.vue'
import { api } from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { Question } from '@/types'
import { formatAnswer } from '@/utils/answers'
import {
  allowedQuestionTypes,
  allowedSubjects,
  labelsForTypes,
  QUESTION_TYPE_LABELS
} from '@/utils/questionTypes'

const auth = useAuthStore()
const subjects = allowedSubjects(auth.user)
const typeOptions = labelsForTypes(allowedQuestionTypes(auth.user))

const gradeLabels: Record<number, string> = {
  1: '一年级', 2: '二年级', 3: '三年级', 4: '四年级', 5: '五年级',
  6: '六年级', 7: '七年级', 8: '八年级', 9: '九年级'
}
const questionTypeLabels = QUESTION_TYPE_LABELS

const loading = ref(false)
const rows = ref<Question[]>([])
const total = ref(0)
const pageNum = ref(1)
const pageSize = ref(10)
const filters = reactive({ subject: '', grade: '', type: '', keyword: '' })
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

function changePageSize() {
  pageNum.value = 1
  load()
}

function resetFilters() {
  Object.assign(filters, { subject: '', grade: '', type: '', keyword: '' })
  pageNum.value = 1
  load()
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
    <PageHeader title="题库查询" description="按学科、年级和题型筛选已通过审核的公共试题；题目与所在年级的课程章节对应。" />
    <section class="panel">
      <div class="filter-bar">
        <el-input v-model="filters.keyword" :prefix-icon="Search" clearable placeholder="搜索题干" />
        <el-select v-model="filters.subject" clearable placeholder="学科"><el-option v-for="subject in subjects" :key="subject" :label="subject === 'music' ? '音乐' : '美术'" :value="subject" /></el-select>
        <el-select v-model="filters.grade" clearable placeholder="年级"><el-option v-for="grade in 9" :key="grade" :label="gradeLabels[grade]" :value="String(grade)" /></el-select>
        <el-select v-model="filters.type" clearable placeholder="题型"><el-option v-for="(label, value) in typeOptions" :key="value" :label="label" :value="value" /></el-select>
        <el-button type="primary" @click="pageNum = 1; load()">查询</el-button>
        <el-button @click="resetFilters">返回全部</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" row-key="id" stripe empty-text="没有符合条件的试题">
        <el-table-column prop="stem" label="题干" min-width="320" show-overflow-tooltip />
        <el-table-column prop="subject" label="学科" width="80"><template #default="{ row }">{{ row.subject === 'music' ? '音乐' : '美术' }}</template></el-table-column>
        <el-table-column label="题型" width="110"><template #default="{ row }">{{ questionTypeLabels[row.type] || row.type }}</template></el-table-column>
        <el-table-column prop="chapterName" label="所属章节" min-width="160" show-overflow-tooltip />
        <el-table-column label="年级" width="90"><template #default="{ row }">{{ gradeLabels[row.grade] || `${row.grade} 年级` }}</template></el-table-column>
        <el-table-column label="状态" width="90"><template #default="{ row }"><StatusTag :value="row.status" /></template></el-table-column>
        <el-table-column label="操作" width="100" fixed="right" align="center"><template #default="{ row }"><el-button link type="primary" @click="detail(row)">查看</el-button></template></el-table-column>
      </el-table>
      <div class="table-footer">
        <span>共 {{ total }} 道试题</span>
        <el-pagination
          v-model:current-page="pageNum"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="sizes, prev, pager, next, jumper"
          @size-change="changePageSize"
          @current-change="load"
        />
      </div>
    </section>

    <DetailDialog v-model="detailOpen" title="试题详情" width="600px">
      <template v-if="selected">
        <div class="detail-title"><div><h2>{{ selected.stem }}</h2><p>{{ selected.courseName }} · {{ selected.chapterName }}</p></div><StatusTag :value="selected.status" /></div>
        <div v-if="selected.options?.length" class="option-list static-options"><div v-for="option in selected.options" :key="option.key"><b>{{ option.key }}</b><span>{{ option.text }}</span></div></div>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="题型">{{ selected.type }}</el-descriptions-item>
          <el-descriptions-item label="年级">{{ gradeLabels[selected.grade] || `${selected.grade} 年级` }}</el-descriptions-item>
          <el-descriptions-item label="资源数量">{{ selected.resourceCount }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="selected.resources?.length" class="question-media">
          <template v-for="resource in selected.resources" :key="resource.resourceId">
            <img v-if="resource.type === 'image' && resource.url" :src="resource.url" :alt="resource.name" />
            <audio v-else-if="resource.type === 'audio' && resource.url" :src="resource.url" controls />
          </template>
        </div>
        <div class="answer-tip"><b>标准答案：</b>{{ formatAnswer(selected.answer) }}<br /><b>解析：</b>{{ selected.analysis || '暂无解析' }}</div>
      </template>
    </DetailDialog>
  </div>
</template>
