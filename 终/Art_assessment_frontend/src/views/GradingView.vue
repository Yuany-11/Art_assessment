<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import AnswerPreview from '@/components/AnswerPreview.vue'
import { api } from '@/api'
import type { GradingQuestion, GradingTask } from '@/types'

const loading = ref(false)
const rows = ref<GradingTask[]>([])
const total = ref(0)
const pageNum = ref(1)
const pageSize = ref(10)
const keyword = ref('')
const status = ref('')
const detailOpen = ref(false)
const selected = ref<GradingTask | null>(null)
const scores = reactive<Record<number, number>>({})
const comments = reactive<Record<number, string>>({})
const finalize = ref(false)
const reason = ref('')
const submitting = ref(false)

async function load() {
  loading.value = true
  try {
    const result = await api.grading.list({ keyword: keyword.value, gradingStatus: status.value, pageNum: pageNum.value, pageSize: pageSize.value })
    rows.value = result.list
    total.value = result.total
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function detail(row: GradingTask) {
  try {
    selected.value = await api.grading.detail(row.attemptId)
    selected.value.questions.forEach((question) => {
      scores[question.questionId] = question.currentScore ?? question.aiScore ?? 0
      comments[question.questionId] = question.comment ?? ''
    })
    finalize.value = false
    reason.value = ''
    detailOpen.value = true
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function confidence(question: GradingQuestion) {
  if (question.aiAnalysis && question.aiScore !== null) return 'AI 辅助评分，请在提交前人工确认'
  return '需要教师人工评分'
}

async function submit() {
  if (!selected.value) return
  if (finalize.value && selected.value.questions.some((question) => scores[question.questionId] === undefined || scores[question.questionId] === null)) {
    ElMessage.warning('完成终评前必须为所有题目打分')
    return
  }
  submitting.value = true
  try {
    const items = selected.value.questions.map((question) => ({
      questionId: question.questionId,
      score: Number(scores[question.questionId] ?? 0),
      comment: comments[question.questionId] || null
    }))
    const result = await api.grading.submit(selected.value.attemptId, items, finalize.value, reason.value, selected.value.version)
    ElMessage.success(`评分已保存，当前总分 ${result.totalScore}`)
    detailOpen.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="stack">
    <PageHeader title="学生评分" description="处理主观题、作品题和 AI 待确认结果，完成逐题评分与终评。" />
    <section class="panel">
      <div class="filter-bar">
        <el-input v-model="keyword" :prefix-icon="Search" clearable placeholder="学生姓名、学号或测评" />
        <el-select v-model="status" clearable placeholder="评分状态"><el-option label="待评分" value="pending" /><el-option label="评分中" value="grading" /><el-option label="评分失败" value="failed" /></el-select>
        <el-button type="primary" @click="pageNum = 1; load()">查询</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" row-key="attemptId" stripe empty-text="当前没有待评分答卷">
        <el-table-column prop="studentName" label="学生" width="100" />
        <el-table-column prop="studentNo" label="学籍号" min-width="140" />
        <el-table-column prop="className" label="班级" min-width="130" />
        <el-table-column prop="assessmentTitle" label="测评" min-width="220" />
        <el-table-column prop="submittedAt" label="交卷时间" min-width="180" />
        <el-table-column label="待评分" width="90"><template #default="{ row }">{{ row.pendingCount }} 题</template></el-table-column>
        <el-table-column label="状态" width="90"><template #default="{ row }"><StatusTag :value="row.gradingStatus" /></template></el-table-column>
        <el-table-column label="操作" width="100"><template #default="{ row }"><el-button link type="primary" @click="detail(row)">开始评分</el-button></template></el-table-column>
      </el-table>
      <div class="table-footer"><span>共 {{ total }} 份待处理答卷</span><el-pagination v-model:current-page="pageNum" v-model:page-size="pageSize" :total="total" layout="prev, pager, next" @change="load" /></div>
    </section>

    <el-drawer v-model="detailOpen" title="人工评分" size="760px">
      <template v-if="selected">
        <div class="detail-title"><div><h2>{{ selected.studentName }} · {{ selected.assessmentTitle }}</h2><p>{{ selected.className }} · 客观题 {{ selected.objectiveScore }} 分</p></div><StatusTag :value="selected.gradingStatus" /></div>
        <div class="grading-question-list">
          <article v-for="question in selected.questions" :key="question.questionId" class="grading-card">
            <div class="grading-card-head"><span>第 {{ question.order }} 题 · {{ question.maxScore }} 分</span><b>{{ confidence(question) }}</b></div>
            <h3>{{ question.stem }}</h3>
            <div class="answer-compare">
              <div><small>学生答案</small><AnswerPreview :value="question.studentAnswer" /></div>
              <div><small>参考答案</small><AnswerPreview :value="question.correctAnswer" /></div>
            </div>
            <p class="rubric"><b>评分要点：</b>{{ question.rubric }}</p>
            <p v-if="question.aiAnalysis" class="answer-tip"><b>AI 分析：</b>{{ question.aiAnalysis }}</p>
            <div class="grading-inputs">
              <label><span>本题得分</span><el-input-number v-model="scores[question.questionId]" :min="0" :max="question.maxScore" :step="0.5" /></label>
              <label><span>教师评语</span><el-input v-model="comments[question.questionId]" type="textarea" :rows="2" placeholder="请输入评分说明" /></label>
            </div>
          </article>
        </div>
        <div class="grading-footer">
          <el-checkbox v-model="finalize">完成终评并生成最终成绩</el-checkbox>
          <el-input v-if="finalize" v-model="reason" placeholder="终评说明（建议填写）" />
          <el-button type="primary" :loading="submitting" @click="submit">保存评分</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>
