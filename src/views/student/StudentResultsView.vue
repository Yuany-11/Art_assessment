<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import echarts, { type EChartsType } from '@/utils/echarts'
import { ElMessage } from 'element-plus'
import { useRoute } from 'vue-router'
import { api } from '@/api'
import type { Score } from '@/types'

const route = useRoute()
const scores = ref<Score[]>([])
const chartEl = ref<HTMLDivElement>()
const detailOpen = ref(false)
const selected = ref<Score | null>(null)
const subject = ref<'music' | 'art'>('music')
let chart: EChartsType | null = null
let openedFromQuery = false
const visibleScores = computed(() => scores.value.filter((item) => item.subject === subject.value))

async function load() {
  try {
    const result = await api.scores.list({ pageSize: 50 })
    scores.value = result.list
    const requestedScoreId = Number(route.query.scoreId)
    const requestedScore = scores.value.find((item) => item.id === requestedScoreId)
    if (!openedFromQuery && requestedScore) {
      openedFromQuery = true
      subject.value = requestedScore.subject
      await showDetail(requestedScore)
    }
    await nextTick()
    if (chartEl.value) {
      chart ??= echarts.init(chartEl.value)
      chart.setOption({
        textStyle: { fontFamily: 'Inter, PingFang SC, Microsoft YaHei, sans-serif' },
        grid: { left: 28, right: 18, top: 26, bottom: 30 },
        tooltip: { trigger: 'axis', backgroundColor: '#fff', borderColor: '#e5e9f0', textStyle: { color: '#344054' } },
        xAxis: { type: 'category', data: visibleScores.value.map((item) => item.createdAt.slice(5, 10)), axisTick: { show: false }, axisLine: { lineStyle: { color: '#e5e9f0' } }, axisLabel: { color: '#667085', fontSize: 12 } },
        yAxis: { type: 'value', min: 0, max: 100, splitLine: { lineStyle: { color: '#eef1f6' } }, axisLabel: { color: '#98a2b3', fontSize: 11 } },
        series: [{ type: 'line', data: visibleScores.value.map((item) => item.totalScore), smooth: true, symbolSize: 7, lineStyle: { width: 3, color: '#5479d6' }, itemStyle: { color: '#5479d6' }, areaStyle: { color: 'rgba(84,121,214,.10)' } }]
      })
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

onMounted(load)

onBeforeUnmount(() => {
  chart?.dispose()
  chart = null
})

async function showDetail(score: Score) {
  try {
    selected.value = await api.scores.detail(score.id)
    detailOpen.value = true
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function correctRate(score: Score) {
  const details = score.answerDetails ?? []
  const max = details.reduce((sum, item) => sum + item.maxScore, 0)
  if (!max) return null
  return Math.round((details.reduce((sum, item) => sum + item.score, 0) / max) * 100)
}
</script>

<template>
  <div class="student-page stack">
    <div class="mobile-title"><p>MY RESULTS</p><h2>我的成绩</h2><span>查看测评结果、等级与成长趋势。</span></div>
    <div class="filter-bar"><el-radio-group v-model="subject" @change="load"><el-radio-button value="music">音乐</el-radio-button><el-radio-button value="art">美术</el-radio-button></el-radio-group></div>
    <section class="student-card">
      <div class="student-section-head"><h3>成绩趋势</h3><span>正式测评</span></div>
      <div ref="chartEl" class="student-chart"></div>
    </section>
    <section class="result-cards">
      <article v-for="score in visibleScores" :key="score.id" class="result-card" @click="showDetail(score)">
        <div><span>{{ score.subject === 'music' ? '音乐' : '美术' }} · {{ score.createdAt.slice(0, 10) }}</span><h3>{{ score.assessmentTitle }}</h3></div>
        <strong>{{ score.totalScore }}</strong>
        <div class="score-bars">
          <span>客观 {{ score.objectiveScore }}</span><span>主观 {{ score.subjectiveScore }}</span><span>AI {{ score.aiScore }}</span>
          <span v-if="correctRate(score) !== null">逐题正确率 {{ correctRate(score) }}%</span>
        </div>
      </article>
    </section>
    <section v-if="!visibleScores.length" class="student-card empty-card">当前学科暂无可查看的正式测评成绩。</section>
    <el-drawer v-model="detailOpen" title="成绩与解析" size="480px">
      <template v-if="selected">
        <div class="detail-title"><div><h2>{{ selected.assessmentTitle }}</h2><p>成绩构成与答案解析</p></div><strong class="result-total">{{ selected.totalScore }}</strong></div>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="客观题">{{ selected.objectiveScore }} 分</el-descriptions-item>
          <el-descriptions-item label="主观题">{{ selected.subjectiveScore }} 分</el-descriptions-item>
          <el-descriptions-item label="AI 辅助">{{ selected.aiScore }} 分</el-descriptions-item>
          <el-descriptions-item label="成绩等级">{{ { excellent: '优秀', good: '良好', pass: '合格', fail: '待提升' }[selected.level] }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="selected.answerVisible && selected.answerDetails?.length" class="answer-detail-list">
          <article v-for="item in selected.answerDetails" :key="item.questionId">
            <div><b>第 {{ item.order }} 题</b><span>{{ item.score }} / {{ item.maxScore }} 分</span></div>
            <h3>{{ item.stem }}</h3>
            <p><small>你的答案</small>{{ item.studentAnswer }}</p>
            <p><small>参考答案</small>{{ item.correctAnswer }}</p>
            <p><small>教师评语</small>{{ item.comment }}</p>
            <p v-if="item.aiAnalysis"><small>AI 分析</small>{{ item.aiAnalysis }}</p>
          </article>
        </div>
        <div v-else class="answer-tip">标准答案与解析按测评的“答案展示”设置控制；未到展示时间时仅显示成绩构成。</div>
      </template>
    </el-drawer>
  </div>
</template>
