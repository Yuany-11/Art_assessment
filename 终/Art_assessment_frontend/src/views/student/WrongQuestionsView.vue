<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Search, View } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import MetricCard from '@/components/MetricCard.vue'
import StatusTag from '@/components/StatusTag.vue'
import { api } from '@/api'
import type { WrongQuestionDetail, WrongQuestionItem, WrongQuestionStatistics } from '@/types'

const router = useRouter()
const rows = ref<WrongQuestionItem[]>([])
const loading = ref(false)
const pageNum = ref(1)
const pageSize = ref(10)
const total = ref(0)
const stats = ref<WrongQuestionStatistics>({ total: 0, unmastered: 0, reviewing: 0, mastered: 0, recent7Days: 0, bySubject: [], byType: [] })
const filters = reactive({ subject: '', questionType: '', masteryStatus: '', sourceType: '', keyword: '', dateFrom: '', dateTo: '' })
const detailOpen = ref(false)
const selected = ref<WrongQuestionDetail | null>(null)
const note = ref('')
const questionTypeLabels: Record<string, string> = {
  single_choice: '单选题',
  multiple_choice: '多选题',
  true_false: '判断题',
  fill_blank: '填空题',
  short_answer: '简答题',
  listening: '听赏题',
  image_upload: '图片作品',
  audio_upload: '音频作品'
}

async function load() {
  loading.value = true
  try {
    const [result, statistics] = await Promise.all([
      api.wrongQuestions.list({ ...filters, pageNum: pageNum.value, pageSize: pageSize.value }),
      api.wrongQuestions.statistics()
    ])
    rows.value = result.list
    total.value = result.total
    stats.value = statistics
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function openDetail(row: WrongQuestionItem) {
  try {
    selected.value = await api.wrongQuestions.detail(row.id)
    note.value = selected.value.note ?? ''
    detailOpen.value = true
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function saveDetail() {
  if (!selected.value) return
  try {
    selected.value = await api.wrongQuestions.update(selected.value.id, { masteryStatus: selected.value.masteryStatus, note: note.value || null })
    ElMessage.success('错题状态已保存')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function redo(row: WrongQuestionDetail | WrongQuestionItem) {
  try {
    const result = await api.wrongQuestions.redo(row.id)
    router.push(`/student/attempt/${result.attemptId}`)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function remove(row: WrongQuestionItem) {
  try {
    await ElMessageBox.confirm(`从错题本删除“${row.stem.slice(0, 24)}”？原答卷和成绩不会删除。`, '删除错题', { type: 'warning' })
    await api.wrongQuestions.remove(row.id)
    detailOpen.value = false
    ElMessage.success('错题已移除')
    await load()
  } catch (error) {
    if (error instanceof Error) ElMessage.error(error.message)
  }
}

function resetFilters() {
  Object.assign(filters, { subject: '', questionType: '', masteryStatus: '', sourceType: '', keyword: '', dateFrom: '', dateTo: '' })
  pageNum.value = 1
  load()
}

onMounted(load)
</script>

<template>
  <div class="student-page stack wrong-page">
    <div class="mobile-title"><p>WRONG QUESTIONS</p><h2>我的错题本</h2><span>自动收集练习与正式测评中的错题，支持重做和掌握状态管理。</span></div>
    <section class="metrics-grid wrong-metrics">
      <MetricCard label="错题总数" :value="stats.total" note="本人全部错题" />
      <MetricCard label="未掌握" :value="stats.unmastered" note="需要优先复习" tone="amber" />
      <MetricCard label="复习中" :value="stats.reviewing" note="正在巩固" tone="blue" />
      <MetricCard label="已掌握" :value="stats.mastered" note="已完成复习" tone="green" />
    </section>
    <section class="wrong-distribution">
      <div><b>学科分布</b><span v-for="item in stats.bySubject" :key="item.subject">{{ item.subject === 'music' ? '音乐' : '美术' }} {{ item.count }}</span></div>
      <div><b>题型分布</b><span v-for="item in stats.byType" :key="item.type">{{ questionTypeLabels[item.type] ?? item.type }} {{ item.count }}</span></div>
      <small>近 7 天新增 {{ stats.recent7Days }} 道错题</small>
    </section>

    <section class="panel">
      <div class="filter-bar">
        <el-input v-model="filters.keyword" :prefix-icon="Search" clearable placeholder="搜索题干" @keyup.enter="load" />
        <el-select v-model="filters.subject" clearable placeholder="学科"><el-option label="音乐" value="music" /><el-option label="美术" value="art" /></el-select>
        <el-select v-model="filters.questionType" clearable placeholder="题型"><el-option label="单选" value="single_choice" /><el-option label="简答" value="short_answer" /><el-option label="图片作品" value="image_upload" /></el-select>
        <el-select v-model="filters.masteryStatus" clearable placeholder="掌握状态"><el-option label="未掌握" value="unmastered" /><el-option label="复习中" value="reviewing" /><el-option label="已掌握" value="mastered" /></el-select>
        <el-select v-model="filters.sourceType" clearable placeholder="错题来源"><el-option label="练习" value="practice" /><el-option label="正式测评" value="formal" /><el-option label="补录" value="manual" /><el-option label="导入" value="import" /></el-select>
        <el-date-picker v-model="filters.dateFrom" type="date" value-format="YYYY-MM-DD" placeholder="开始日期" />
        <el-date-picker v-model="filters.dateTo" type="date" value-format="YYYY-MM-DD" placeholder="结束日期" />
        <el-button type="primary" @click="pageNum = 1; load()">查询</el-button>
        <el-button :icon="Refresh" @click="resetFilters">重置</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" row-key="id" stripe empty-text="暂无错题，继续保持">
        <el-table-column prop="stem" label="题目" min-width="230" show-overflow-tooltip />
        <el-table-column label="学科 / 题型" width="120"><template #default="{ row }">{{ row.subject === 'music' ? '音乐' : '美术' }} · {{ questionTypeLabels[row.type] ?? row.type }}</template></el-table-column>
        <el-table-column prop="wrongCount" label="错误" width="70" />
        <el-table-column label="掌握状态" width="100"><template #default="{ row }"><StatusTag :value="row.masteryStatus" /></template></el-table-column>
        <el-table-column prop="sourceAssessmentTitle" label="来源" min-width="160" show-overflow-tooltip />
        <el-table-column prop="lastWrongAt" label="最近错误" width="155"><template #default="{ row }">{{ row.lastWrongAt.replace('T', ' ').slice(0, 16) }}</template></el-table-column>
        <el-table-column label="操作" width="180">
          <template #default="{ row }">
            <el-button link type="primary" :icon="View" @click="openDetail(row)">详情</el-button>
            <el-button link @click="redo(row)">重做</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="table-footer"><span>共 {{ total }} 道错题</span><el-pagination v-model:current-page="pageNum" v-model:page-size="pageSize" :total="total" layout="prev, pager, next" @change="load" /></div>
    </section>

    <el-drawer v-model="detailOpen" title="错题详情" size="660px">
      <template v-if="selected">
        <div class="detail-title">
          <div><h2>{{ selected.stem }}</h2><p>{{ selected.sourceAssessmentTitle }} · 错 {{ selected.wrongCount }} 次</p></div>
          <StatusTag :value="selected.masteryStatus" />
        </div>
        <div v-if="selected.options.length" class="option-list static-options">
          <div v-for="option in selected.options" :key="option.key"><b>{{ option.key }}</b><span>{{ option.text }}</span></div>
        </div>
        <div class="answer-compare wrong-answer-compare">
          <div><small>你的答案</small><p>{{ JSON.stringify(selected.studentAnswer) }}</p></div>
          <div><small>正确答案</small><p>{{ JSON.stringify(selected.correctAnswer) }}</p></div>
        </div>
        <div class="answer-tip"><b>解析：</b>{{ selected.analysis || '暂无解析' }}</div>
        <div v-if="selected.resources.length" class="wrong-resources">
          <h3>题目资源</h3>
          <span v-for="resource in selected.resources" :key="resource.name">{{ resource.type === 'audio' ? '音频' : '图片' }} · {{ resource.name }}</span>
        </div>
        <div class="wrong-detail-form">
          <label><span>掌握状态</span><el-select v-model="selected.masteryStatus"><el-option label="未掌握" value="unmastered" /><el-option label="复习中" value="reviewing" /><el-option label="已掌握" value="mastered" /></el-select></label>
          <label><span>学习备注</span><el-input v-model="note" type="textarea" :rows="3" maxlength="500" show-word-limit placeholder="记录易错点或复习方法" /></label>
        </div>
        <div class="drawer-actions"><el-button type="primary" @click="saveDetail">保存状态</el-button><el-button @click="redo(selected)">重做本题</el-button><el-button type="danger" plain @click="remove(selected)">从错题本删除</el-button></div>
        <div class="wrong-records">
          <h3>答错记录</h3>
          <div v-for="record in selected.records" :key="record.attemptId"><b>答卷 {{ record.attemptId }}</b><span>{{ record.createdAt.replace('T', ' ').slice(0, 16) }}</span><p>{{ JSON.stringify(record.answer) }}</p></div>
        </div>
      </template>
    </el-drawer>
  </div>
</template>
