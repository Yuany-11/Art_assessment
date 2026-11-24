<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute } from 'vue-router'
import { MagicStick, Search } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import AnswerPreview from '@/components/AnswerPreview.vue'
import ScoreStepper from '@/components/ScoreStepper.vue'
import DetailDialog from '@/components/DetailDialog.vue'
import AudioTagCard from '@/components/AudioTagCard.vue'
import { api } from '@/api'
import type { AudioTags, GradingQuestion, GradingTask } from '@/types'

const loading = ref(false)
const rows = ref<GradingTask[]>([])
const total = ref(0)
const pageNum = ref(1)
const pageSize = ref(10)
const route = useRoute()
const keyword = ref('')
const status = ref(String(route.query.status || ''))
const detailOpen = ref(false)
const selected = ref<GradingTask | null>(null)
const scores = reactive<Record<number, number>>({})
const comments = reactive<Record<number, string>>({})
const finalize = ref(false)
const reason = ref('')
const submitting = ref(false)
const aiLoading = ref(false)

const hasScorableQuestion = computed(() =>
  Boolean(
    selected.value?.questions.some((question) =>
      ['audio_upload', 'image_upload'].includes(question.type)
    )
  )
)

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

function resetQuery() {
  keyword.value = ''
  status.value = ''
  pageNum.value = 1
  load()
}

async function detail(row: GradingTask) {
  try {
    selected.value = await api.grading.detail(row.attemptId)
    selected.value.questions.forEach((question) => {
      scores[question.questionId] = question.currentScore ?? 0
      comments[question.questionId] = question.comment ?? ''
    })
    // 默认终评：教师打完分点「保存并发布成绩」即可出分；需要留草稿时自行取消勾选。
    finalize.value = true
    reason.value = ''
    detailOpen.value = true
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function formatDateTime(value?: string | null) {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 16)
}

function answerFileId(answer: unknown): number | null {
  if (!answer || typeof answer !== 'object') return null
  const fileId = (answer as { fileId?: unknown }).fileId
  return typeof fileId === 'number' ? fileId : null
}

function showAudioTags(question: GradingQuestion) {
  // 仅音乐类测评或音频题展示音频分析，美术作品不显示音频标签。
  return (
    selected.value?.subject === 'music' ||
    question.type === 'audio_upload' ||
    question.type === 'listening'
  )
}

async function onAudioAnalyzed(question: GradingQuestion, tags: AudioTags) {
  question.audioTags = tags
  // 重新分析后同步刷新建议分，避免标签是新规则、建议分还是旧结果。
  await generateSuggestions()
}

function applySuggestion(question: GradingQuestion) {
  const suggestion = question.aiSuggestion
  if (!suggestion || suggestion.suggestedScore === null) return
  scores[question.questionId] = suggestion.suggestedScore
  ElMessage.success(`已采用 AI 建议分 ${suggestion.suggestedScore} 分，可继续调整`)
}

async function generateSuggestions() {
  if (!selected.value || aiLoading.value) return
  aiLoading.value = true
  try {
    const result = await api.grading.aiSuggestions(selected.value.attemptId)
    const byQuestion = new Map(result.items.map((item) => [item.questionId, item]))
    selected.value.questions.forEach((question) => {
      const item = byQuestion.get(question.questionId)
      if (item) {
        question.aiSuggestion = item
        if (item.audioTags) question.audioTags = item.audioTags
      }
    })
    const done = result.items.filter((item) => item.status === 'completed').length
    const failed = result.items.filter((item) => item.status !== 'completed').length
    if (done) ElMessage.success(`AI 建议分已生成 ${done} 道题${failed ? `，${failed} 道题待补充分析` : ''}`)
    else ElMessage.warning('暂未生成建议分，请确认音频已上传且分析服务可用')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    aiLoading.value = false
  }
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
    ElMessage.success(
      finalize.value
        ? `成绩已发布，总分 ${result.totalScore}，学生可在“我的成绩”查看`
        : '评分已保存为草稿，完成终评后学生才能看到成绩'
    )
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
    <PageHeader title="学生评分" description="只处理实践作品题与课外作品，完成逐题评分与终评。" />
    <section class="panel">
      <div class="filter-bar">
        <el-input v-model="keyword" :prefix-icon="Search" clearable placeholder="学生姓名、学号或测评" />
        <el-select v-model="status" clearable placeholder="评分状态"><el-option label="待评分" value="pending" /><el-option label="评分中" value="grading" /><el-option label="已完成（可修改）" value="graded" /><el-option label="评分失败" value="failed" /></el-select>
        <el-button type="primary" @click="pageNum = 1; load()">查询</el-button>
        <el-button @click="resetQuery">返回全部</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" row-key="attemptId" stripe empty-text="当前没有待评分答卷">
        <el-table-column prop="studentName" label="学生" width="100" />
        <el-table-column prop="studentNo" label="学籍号" min-width="140" />
        <el-table-column prop="className" label="班级" min-width="130" />
        <el-table-column prop="assessmentTitle" label="测评" min-width="220" />
        <el-table-column label="交卷时间" min-width="160"><template #default="{ row }">{{ formatDateTime(row.submittedAt) }}</template></el-table-column>
        <el-table-column label="待评分" width="90"><template #default="{ row }">{{ row.pendingCount }} 题</template></el-table-column>
        <el-table-column label="状态" width="90"><template #default="{ row }"><StatusTag :value="row.gradingStatus" /></template></el-table-column>
        <el-table-column label="操作" width="100"><template #default="{ row }"><el-button link type="primary" @click="detail(row)">开始评分</el-button></template></el-table-column>
      </el-table>
      <div class="table-footer"><span>共 {{ total }} 份待处理答卷</span><el-pagination v-model:current-page="pageNum" v-model:page-size="pageSize" :total="total" layout="prev, pager, next" @change="load" /></div>
    </section>

    <DetailDialog v-model="detailOpen" title="人工评分" width="760px">
      <template v-if="selected">
        <div class="detail-title"><div><h2>{{ selected.studentName }} · {{ selected.assessmentTitle }}</h2><p>{{ selected.className }} · 客观题 {{ selected.objectiveScore }} 分</p></div><StatusTag :value="selected.gradingStatus" /></div>
        <div v-if="hasScorableQuestion" class="ai-actions">
          <el-button
            :icon="MagicStick"
            :loading="aiLoading"
            :disabled="selected.aiScoringEnabled === false"
            @click="generateSuggestions"
          >生成 AI 建议分</el-button>
          <span class="muted">
            {{ selected.aiScoringEnabled === false
              ? '未启用 AI 评分，请人工评分。'
              : '音乐作品题与美术作品题可用；建议分按本题满分折算，只作参考，不会自动计入成绩。' }}
          </span>
        </div>
        <div class="grading-question-list">
          <article v-for="question in selected.questions" :key="question.questionId" class="grading-card">
            <div class="grading-card-head"><span>第 {{ question.order }} 题 · {{ question.maxScore }} 分</span><b>需要教师人工评分</b></div>
            <h3>{{ question.stem }}</h3>
            <div class="answer-compare">
              <div><small>学生答案</small><AnswerPreview :value="question.studentAnswer" /></div>
              <div><small>参考答案</small><AnswerPreview :value="question.correctAnswer" /></div>
            </div>
            <AudioTagCard
              v-if="showAudioTags(question)"
              :tags="question.audioTags"
              :file-id="answerFileId(question.studentAnswer)"
              :max-score="question.maxScore"
              show-reference
              title="学生音频参考分析"
              @analyzed="(tags) => onAudioAnalyzed(question, tags)"
            />
            <div
              v-if="question.aiSuggestion"
              class="ai-suggestion"
              :class="{ 'is-review': question.aiSuggestion.needsReview }"
            >
              <div class="ai-suggestion-head">
                <b>AI 建议分</b>
                <template v-if="question.aiSuggestion.status === 'completed'">
                  <span class="ai-suggestion-score">
                    {{ question.aiSuggestion.suggestedScore }} / {{ question.maxScore }} 分
                    <small>原始参考分 {{ question.aiSuggestion.rawScore }}/100{{ question.aiSuggestion.grade ? ` · ${question.aiSuggestion.grade}` : '' }}</small>
                  </span>
                  <el-tag v-if="question.aiSuggestion.needsReview" size="small" type="warning" effect="plain">建议人工复核</el-tag>
                  <el-tag v-if="question.aiSuggestion.degraded" size="small" type="info" effect="plain">{{ question.aiSuggestion.method === 'rule_based' ? '规则式参考' : '降级结果' }}</el-tag>
                  <el-button link type="primary" size="small" @click="applySuggestion(question)">采用建议分</el-button>
                </template>
                <span v-else class="ai-suggestion-score is-muted">{{ question.aiSuggestion.message }}</span>
              </div>
              <div v-if="question.aiSuggestion.dimensions?.length" class="ai-dims">
                <div v-for="dim in question.aiSuggestion.dimensions" :key="dim.key" class="ai-dim">
                  <span>{{ dim.label }}</span>
                  <el-progress :percentage="Math.round(dim.score)" :stroke-width="7" :show-text="false" />
                  <b>{{ dim.score }}</b>
                </div>
              </div>
              <p v-if="question.aiSuggestion.analysis" class="ai-analysis">{{ question.aiSuggestion.analysis }}</p>
              <p v-if="question.aiSuggestion.disclaimer" class="ai-suggestion-disclaimer">{{ question.aiSuggestion.disclaimer }}</p>
            </div>
            <p class="rubric"><b>评分要点：</b>{{ question.rubric }}</p>
            <div class="grading-inputs">
              <div class="grading-score">
                <span>本题得分</span>
                <ScoreStepper v-model="scores[question.questionId]" :min="0" :max="question.maxScore" :step="0.5" unit="分" />
              </div>
              <label><span>教师评语</span><el-input v-model="comments[question.questionId]" type="textarea" :rows="2" placeholder="请输入评分说明" /></label>
            </div>
          </article>
        </div>
        <div class="grading-footer">
          <el-checkbox v-model="finalize">{{ selected.gradingStatus === 'graded' ? '更新已终评成绩（可修改后重新生成）' : '完成终评并生成最终成绩' }}</el-checkbox>
          <el-input v-if="finalize" v-model="reason" placeholder="终评说明（建议填写）" />
          <el-button type="primary" :loading="submitting" @click="submit">{{ finalize ? '保存并发布成绩' : '保存草稿' }}</el-button>
        </div>
      </template>
    </DetailDialog>
  </div>
</template>

<style scoped>
.ai-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin: 8px 0 4px;
}
.ai-actions .muted {
  font-size: 12px;
  color: #667085;
}
.ai-suggestion {
  margin-top: 10px;
  border: 1px solid #dbe4f3;
  border-radius: 10px;
  padding: 8px 12px;
  background: #f4f7fd;
}
.ai-suggestion.is-review {
  border-color: #f3d9a4;
  background: #fffaf0;
}
.ai-suggestion-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 13px;
  color: #344054;
}
.ai-suggestion-head b {
  font-weight: 600;
}
.ai-suggestion-score {
  color: #1d4ed8;
  font-weight: 600;
}
.ai-suggestion-score small {
  margin-left: 6px;
  color: #98a2b3;
  font-weight: 400;
}
.ai-suggestion-score.is-muted {
  color: #667085;
  font-weight: 400;
}
.ai-suggestion-disclaimer {
  margin: 6px 0 0;
  font-size: 11px;
  color: #98a2b3;
  line-height: 1.5;
}
.ai-dims {
  display: grid;
  gap: 6px;
  margin-top: 8px;
}
.ai-dim {
  display: grid;
  grid-template-columns: 72px 1fr 40px;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #475467;
}
.ai-dim b {
  text-align: right;
  color: #1d4ed8;
}
.ai-analysis {
  margin: 8px 0 0;
  font-size: 12px;
  color: #475467;
  line-height: 1.6;
}
</style>
