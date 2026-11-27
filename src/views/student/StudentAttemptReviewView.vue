<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import { api } from '@/api'
import AnswerPreview from '@/components/AnswerPreview.vue'
import type { AttemptReview } from '@/types'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const review = ref<AttemptReview | null>(null)

const typeLabels: Record<string, string> = {
  single_choice: '单选题',
  multiple_choice: '多选题',
  true_false: '判断题',
  fill_blank: '填空题',
  listening: '听力题',
  audio_choice_judge: '音频选择判断题',
  image_choice_judge: '图像选择判断题',
  image_upload: '实践题（图片）',
  audio_upload: '实践题（音频）'
}

const answerTip = computed(() => {
  if (!review.value) return ''
  if (review.value.answerVisible) return '标准答案与解析已按老师设置的公布时间展示。'
  if (review.value.showAnswerMode === 'never') return '老师设置本次测评不公布标准答案，仅展示你的作答与得分。'
  if (review.value.showAnswerMode === 'after_end') {
    return `标准答案将在测评结束后公布（截止 ${formatDateTime(review.value.endTime)}）。`
  }
  return '标准答案暂未公布。'
})

function formatDateTime(value?: string | null) {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 16)
}

function scoreText(item: AttemptReview['questions'][number]) {
  if (item.score === null) return item.scoringMode === 'auto' ? '待评分' : '待教师评分'
  return `${item.score} / ${item.maxScore} 分`
}

async function load() {
  loading.value = true
  try {
    review.value = await api.attempts.review(Number(route.params.attemptId))
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="student-page stack" v-loading="loading">
    <div class="mobile-title"><p>PAPER REVIEW</p><h2>试卷阅览</h2><span>查看本次作答，标准答案按老师设置的公布时间展示。</span></div>
    <div class="filter-bar">
      <el-button :icon="ArrowLeft" @click="router.push('/student/results')">返回成绩</el-button>
      <el-button @click="router.push('/student/assessments')">返回我的测评</el-button>
    </div>

    <template v-if="review">
      <section class="student-card">
        <div class="student-section-head">
          <h3>{{ review.assessmentTitle }}</h3>
          <span>{{ review.subject === 'music' ? '音乐' : '美术' }} · {{ review.paperType === 'formal' ? '正式测评' : '练习测评' }}</span>
        </div>
        <div class="assessment-meta">
          <span>发布老师：{{ review.publisherName || '—' }}</span>
          <span>交卷时间：{{ formatDateTime(review.submittedAt) }}</span>
          <span>测评截止：{{ formatDateTime(review.endTime) }}</span>
          <span>客观题得分：{{ review.objectiveScore }}</span>
        </div>
        <div v-if="review.scoreReleased" class="review-total">
          <strong>{{ review.totalScore }}</strong><span>/ {{ review.maxScore }} 分</span>
        </div>
        <p v-else class="muted">本次答卷包含需要教师评分的实践作品，终评完成后公布总分。</p>
        <el-alert :title="answerTip" type="info" :closable="false" show-icon />
      </section>

      <section class="student-card">
        <div class="student-section-head"><h3>逐题阅览</h3><span>共 {{ review.questions.length }} 题</span></div>
        <div class="answer-detail-list">
          <article v-for="item in review.questions" :key="item.questionId">
            <div>
              <b>第 {{ item.order }} 题 · {{ typeLabels[item.type] || item.type }}</b>
              <span>{{ scoreText(item) }}</span>
            </div>
            <h3>{{ item.stem }}</h3>
            <ul v-if="item.options.length" class="review-options">
              <li v-for="option in item.options" :key="option.key">{{ option.key }}. {{ option.text }}</li>
            </ul>
            <div class="result-answer"><small>你的答案</small><AnswerPreview :value="item.studentAnswer" /></div>
            <div v-if="review.answerVisible && item.correctAnswer" class="result-answer">
              <small>参考答案</small><AnswerPreview :value="item.correctAnswer" />
            </div>
            <p v-if="review.answerVisible && item.analysis"><small>解析</small>{{ item.analysis }}</p>
            <p v-if="item.comment"><small>教师评语</small>{{ item.comment }}</p>
            <el-tag v-if="review.answerVisible && item.isCorrect === true" type="success" size="small">回答正确</el-tag>
            <el-tag v-else-if="review.answerVisible && item.isCorrect === false" type="danger" size="small">回答有误</el-tag>
          </article>
        </div>
      </section>
    </template>
  </div>
</template>
