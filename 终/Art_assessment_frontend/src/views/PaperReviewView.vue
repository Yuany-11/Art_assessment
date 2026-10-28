<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import MetricCard from '@/components/MetricCard.vue'
import { api } from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { Paper, PaperReviewLog } from '@/types'

const auth = useAuthStore()
const loading = ref(false)
const rows = ref<Paper[]>([])
const historyOpen = ref(false)
const history = ref<PaperReviewLog[]>([])
const current = ref<Paper | null>(null)
const reviewOpen = ref(false)
const reviewLoading = ref(false)
const action = ref<'approve' | 'reject'>('approve')
const comment = ref('')
const filters = reactive({ keyword: '', subject: '' })
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

const visibleRows = computed(() => rows.value.filter((row) =>
  row.reviewStatus === 'pending' &&
  (!filters.subject || row.subject === filters.subject) &&
  (!filters.keyword || row.title.includes(filters.keyword))
))
const assignedCount = computed(() => visibleRows.value.filter((row) => row.reviewerId === auth.user?.id).length)

async function load() {
  loading.value = true
  try {
    const result = await api.papers.list({ reviewStatus: 'pending', pageNum: 1, pageSize: 100 })
    rows.value = result.list
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function openReview(row: Paper) {
  reviewLoading.value = true
  try {
    current.value = await api.papers.detail(row.id)
    action.value = 'approve'
    comment.value = ''
    reviewOpen.value = true
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    reviewLoading.value = false
  }
}

async function submitReview() {
  if (!current.value) return
  if (action.value === 'reject' && !comment.value.trim()) {
    ElMessage.warning('驳回时必须填写原因')
    return
  }
  try {
    await api.papers.review(current.value.id, action.value, comment.value, current.value.version)
    reviewOpen.value = false
    ElMessage.success(action.value === 'approve' ? '试卷审核通过' : '试卷已驳回')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function openHistory(row: Paper) {
  try {
    current.value = row
    history.value = await api.papers.reviewHistory(row.id)
    historyOpen.value = true
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

onMounted(load)
</script>

<template>
  <div class="stack">
    <PageHeader title="试卷审核" description="题库管理端统一审核各端提交的试卷；审核结果会自动通知创建人。">
      <el-button @click="load">刷新待办</el-button>
    </PageHeader>
    <section class="metrics-grid review-metrics">
      <MetricCard label="待审核试卷" :value="visibleRows.length" note="全部来自各端提交" tone="amber" />
      <MetricCard label="已分配给我" :value="assignedCount" note="题库管理端统一处理" />
      <MetricCard label="当前审核身份" :value="auth.user?.roleName || '—'" note="试卷审核集中到题库管理端" tone="blue" />
    </section>
    <section class="panel">
      <div class="filter-bar">
        <el-input v-model="filters.keyword" :prefix-icon="Search" clearable placeholder="搜索试卷名称" />
        <el-select v-model="filters.subject" clearable placeholder="学科"><el-option label="音乐" value="music" /><el-option label="美术" value="art" /></el-select>
        <el-button type="primary" @click="load">查询</el-button>
      </div>
      <el-table v-loading="loading" :data="visibleRows" row-key="id" stripe empty-text="当前没有待审核试卷">
        <el-table-column prop="title" label="试卷名称" min-width="230" show-overflow-tooltip />
        <el-table-column prop="subject" label="学科" width="80"><template #default="{ row }">{{ row.subject === 'music' ? '音乐' : '美术' }}</template></el-table-column>
        <el-table-column prop="creatorName" label="提交人" width="110" />
        <el-table-column prop="scopeName" label="归属范围" min-width="140" />
        <el-table-column label="题目 / 总分" width="130"><template #default="{ row }">{{ row.questionCount }} 题 / {{ row.totalScore }} 分</template></el-table-column>
        <el-table-column label="版本" width="80"><template #default="{ row }">v{{ row.version }}</template></el-table-column>
        <el-table-column label="审核状态" width="110"><template #default="{ row }"><StatusTag :value="row.reviewStatus" /></template></el-table-column>
        <el-table-column label="操作" width="220"><template #default="{ row }"><el-button link type="primary" :loading="reviewLoading" @click="openReview(row)">查看原卷并审核</el-button><el-button link @click="openHistory(row)">审核记录</el-button></template></el-table-column>
      </el-table>
    </section>
    <el-dialog v-model="reviewOpen" title="查看原卷并审核" width="980px" top="4vh">
      <template v-if="current">
        <div class="review-workspace">
          <section class="review-original">
            <div class="review-original-head">
              <div>
                <span>{{ current.subject === 'music' ? '音乐' : '美术' }} · {{ current.paperType === 'formal' ? '正式卷' : '练习卷' }} · {{ current.grade }} 年级</span>
                <h3>{{ current.title }}</h3>
                <p>创建人：{{ current.creatorName }} · 归属：{{ current.scopeName }}</p>
              </div>
              <StatusTag :value="current.reviewStatus" />
            </div>
            <div class="review-original-meta">
              <div><small>题目数量</small><b>{{ current.questionCount }} 题</b></div>
              <div><small>试卷总分</small><b>{{ current.totalScore }} 分</b></div>
              <div><small>建议时长</small><b>{{ current.duration }} 分钟</b></div>
              <div><small>试卷版本</small><b>v{{ current.version }}</b></div>
            </div>
            <div v-if="current.instructions" class="review-instructions"><b>考试说明</b><p>{{ current.instructions }}</p></div>
            <div class="review-question-list">
              <article v-for="(question, index) in current.questions" :key="`${question.questionId}-${index}`">
                <div class="review-question-head"><b>第 {{ index + 1 }} 题</b><span>{{ questionTypeLabels[question.type] ?? question.type }} · {{ question.score }} 分</span></div>
                <p>{{ question.stem }}</p>
                <div v-if="question.options?.length" class="review-options">
                  <div v-for="option in question.options" :key="option.key"><b>{{ option.key }}</b><span>{{ option.text }}</span></div>
                </div>
                <div v-if="question.resources?.length" class="review-resource-row">
                  <span v-for="resource in question.resources" :key="resource.name">{{ resource.type === 'audio' ? '音频' : '图片' }} · {{ resource.name }}</span>
                </div>
                <div v-if="question.analysis" class="review-analysis"><b>试题解析</b><span>{{ question.analysis }}</span></div>
              </article>
              <p v-if="!current.questions?.length" class="muted">该试卷暂无题目内容。</p>
            </div>
          </section>
          <aside class="review-decision">
            <div class="review-paper-summary"><div><b>{{ current.title }}</b><span>v{{ current.version }}</span></div><p>提交人：{{ current.creatorName }} · 归属：{{ current.scopeName }}</p></div>
            <el-form label-position="top">
              <el-form-item label="审核结果"><el-radio-group v-model="action"><el-radio value="approve">审核通过</el-radio><el-radio value="reject">审核驳回</el-radio></el-radio-group></el-form-item>
              <el-form-item :label="action === 'reject' ? '驳回原因（必填）' : '审核意见'"><el-input v-model="comment" type="textarea" :rows="5" maxlength="500" show-word-limit /></el-form-item>
            </el-form>
          </aside>
        </div>
      </template>
      <template #footer><el-button @click="reviewOpen = false">取消</el-button><el-button :type="action === 'approve' ? 'primary' : 'danger'" @click="submitReview">确认审核</el-button></template>
    </el-dialog>
    <el-drawer v-model="historyOpen" title="审核记录" size="520px">
      <div class="panel-head"><div><h3>{{ current?.title }}</h3><span>当前版本 v{{ current?.version }}</span></div></div>
      <el-timeline v-if="history.length">
        <el-timeline-item v-for="item in history" :key="item.id" :timestamp="item.createdAt.replace('T', ' ').slice(0, 16)" :type="item.action === 'reject' ? 'danger' : item.action === 'approve' ? 'success' : 'primary'">
          <div class="review-history-item"><b>{{ item.action === 'submit' ? '提交审核' : item.action === 'approve' ? '审核通过' : '审核驳回' }}</b><span>版本 v{{ item.version }} · {{ item.reviewerName || current?.creatorName }}</span><p>{{ item.comment || '无补充说明' }}</p></div>
        </el-timeline-item>
      </el-timeline>
      <div v-else class="empty-card student-card">暂无审核记录</div>
    </el-drawer>
  </div>
</template>
