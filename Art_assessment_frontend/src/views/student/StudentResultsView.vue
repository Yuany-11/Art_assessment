<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import echarts, { type EChartsType } from '@/utils/echarts'
import { ElMessage } from 'element-plus'
import { useRoute } from 'vue-router'
import DetailDialog from '@/components/DetailDialog.vue'
import { api } from '@/api'
import AnswerPreview from '@/components/AnswerPreview.vue'
import type { Score } from '@/types'

const route = useRoute()
const scores = ref<Score[]>([])
const formalChartEl = ref<HTMLDivElement>()
const practiceChartEl = ref<HTMLDivElement>()
const detailOpen = ref(false)
const selected = ref<Score | null>(null)
const subject = ref<'music' | 'art'>('music')
const paperType = ref<'all' | 'formal' | 'practice'>('all')
const charts: Record<'formal' | 'practice', EChartsType | null> = { formal: null, practice: null }
let openedFromQuery = false
const visibleScores = computed(() => scores.value.filter((item) => item.subject === subject.value))
const filteredScores = computed(() =>
  visibleScores.value.filter(
    (item) => paperType.value === 'all' || (item.paperType ?? 'formal') === paperType.value
  )
)
const formalScores = computed(() => filteredScores.value.filter((item) => (item.paperType ?? 'formal') === 'formal'))
const practiceScores = computed(() => filteredScores.value.filter((item) => item.paperType === 'practice'))
const groupedScores = computed(() =>
  [
    { type: 'formal', title: '正式测评', hint: '计入等级与证书', items: formalScores.value },
    { type: 'practice', title: '平时练习', hint: '仅作练习反馈，不计入证书', items: practiceScores.value }
  ].filter((group) => group.items.length)
)
const formalFullScore = computed(() =>
  formalScores.value.reduce((max, score) => Math.max(max, Number(score.maxScore ?? 0)), 0)
)
const practiceFullScore = computed(() =>
  practiceScores.value.reduce((max, score) => Math.max(max, Number(score.maxScore ?? 0)), 0)
)

function scoreRate(score: Score) {
  const max = Number(score.maxScore ?? 0)
  if (!max) return 0
  return Math.round((Number(score.totalScore) / max) * 1000) / 10
}

function seriesOf(list: Score[]) {
  return [...list]
    .sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime())
    .map((score) => ({
      value: [new Date(score.createdAt).getTime(), Number(score.totalScore)],
      title: score.assessmentTitle,
      totalScore: score.totalScore,
      maxScore: score.maxScore ?? 0
    }))
}

type TooltipItem = {
  data?: { title?: string; totalScore?: number; maxScore?: number; value?: [number, number] }
}

function renderTypeChart(
  key: 'formal' | 'practice',
  el: HTMLDivElement | undefined,
  list: Score[],
  fullScore: number,
  seriesName: string,
  color: string,
  areaColor: string
) {
  if (!el || !list.length) return
  let instance = charts[key]
  if (!instance || instance.getDom() !== el) {
    instance?.dispose()
    instance = echarts.init(el)
    charts[key] = instance
  }
  instance.setOption({
    textStyle: { fontFamily: 'Inter, PingFang SC, Microsoft YaHei, sans-serif' },
    grid: { left: 40, right: 18, top: 22, bottom: 30 },
    tooltip: {
      trigger: 'item',
      backgroundColor: '#fff',
      borderColor: '#e5e9f0',
      textStyle: { color: '#344054' },
      formatter: (params: unknown) => {
        const data = (params as TooltipItem).data
        const timestamp = data?.value?.[0]
        const date = timestamp ? new Date(timestamp) : null
        const head = date
          ? `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
          : ''
        return [
          head,
          data?.title ?? '',
          `${seriesName}得分 ${data?.totalScore ?? 0} / ${data?.maxScore ?? 0} 分`
        ].filter(Boolean).join('<br/>')
      }
    },
    xAxis: {
      type: 'time',
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#e5e9f0' } },
      axisLabel: {
        color: '#667085',
        fontSize: 12,
        formatter: (value: number) => {
          const date = new Date(value)
          return `${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
        }
      }
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: Math.max(1, fullScore),
      splitLine: { lineStyle: { color: '#eef1f6' } },
      axisLabel: { color: '#98a2b3', fontSize: 11 }
    },
    series: [{
      name: seriesName,
      type: 'line',
      data: seriesOf(list),
      smooth: true,
      symbolSize: 7,
      lineStyle: { width: 3, color },
      itemStyle: { color },
      areaStyle: { color: areaColor }
    }]
  }, true)
}

/** 正式测评与平时练习满分不同，各画一张图、各自用自己的满分作为纵轴上限。 */
function renderCharts() {
  renderTypeChart(
    'formal', formalChartEl.value, formalScores.value, formalFullScore.value,
    '正式测评', '#5479d6', 'rgba(84,121,214,.10)'
  )
  renderTypeChart(
    'practice', practiceChartEl.value, practiceScores.value, practiceFullScore.value,
    '平时练习', '#9b8cdb', 'rgba(155,140,219,.10)'
  )
}

async function onTypeChange() {
  await nextTick()
  renderCharts()
}

async function load() {
  try {
    const result = await api.scores.mine({ pageSize: 50, subject: subject.value })
    scores.value = result.list
    const requestedScoreId = Number(route.query.scoreId)
    const requestedScore = scores.value.find((item) => item.id === requestedScoreId)
    if (!openedFromQuery && requestedScore) {
      openedFromQuery = true
      subject.value = requestedScore.subject
      await showDetail(requestedScore)
    }
    await nextTick()
    renderCharts()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

onMounted(load)

onBeforeUnmount(() => {
  charts.formal?.dispose()
  charts.practice?.dispose()
  charts.formal = null
  charts.practice = null
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
    <div class="filter-bar">
      <el-radio-group v-model="subject" @change="load">
        <el-radio-button value="music">音乐</el-radio-button>
        <el-radio-button value="art">美术</el-radio-button>
      </el-radio-group>
      <el-radio-group v-model="paperType" @change="onTypeChange">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="formal">正式测评</el-radio-button>
        <el-radio-button value="practice">平时练习</el-radio-button>
      </el-radio-group>
    </div>
    <section v-if="formalScores.length" class="student-card">
      <div class="student-section-head">
        <h3>正式测评趋势</h3>
        <span>满分 {{ formalFullScore }} 分 · 共 {{ formalScores.length }} 次</span>
      </div>
      <div ref="formalChartEl" class="student-chart"></div>
    </section>
    <section v-if="practiceScores.length" class="student-card">
      <div class="student-section-head">
        <h3>平时练习趋势</h3>
        <span>满分 {{ practiceFullScore }} 分 · 共 {{ practiceScores.length }} 次</span>
      </div>
      <div ref="practiceChartEl" class="student-chart"></div>
    </section>
    <section v-for="group in groupedScores" :key="group.type" class="result-group">
      <div class="student-section-head">
        <h3>{{ group.title }}</h3>
        <span>{{ group.hint }} · {{ group.items.length }} 次</span>
      </div>
      <div class="result-cards">
        <article v-for="score in group.items" :key="score.id" class="result-card" @click="showDetail(score)">
          <div>
            <span>{{ score.subject === 'music' ? '音乐' : '美术' }} · {{ group.title }} · {{ score.createdAt.slice(0, 10) }}</span>
            <h3>{{ score.assessmentTitle }}</h3>
          </div>
          <strong>{{ score.totalScore }}<small>/ {{ score.maxScore ?? 100 }}</small></strong>
          <div class="score-bars">
            <span>客观 {{ score.objectiveScore }}</span><span>主观 {{ score.subjectiveScore }}</span>
            <span>得分率 {{ scoreRate(score) }}%</span>
            <span v-if="correctRate(score) !== null">逐题正确率 {{ correctRate(score) }}%</span>
          </div>
        </article>
      </div>
    </section>
    <section v-if="!filteredScores.length" class="student-card empty-card">当前学科暂无可查看的测评成绩。</section>
    <DetailDialog v-model="detailOpen" title="成绩与解析" width="480px">
      <template v-if="selected">
        <div class="detail-title"><div><h2>{{ selected.assessmentTitle }}</h2><p>成绩构成与答案解析</p></div><strong class="result-total">{{ selected.totalScore }}</strong></div>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="总分">{{ selected.totalScore }} / {{ selected.maxScore ?? 100 }} 分</el-descriptions-item>
          <el-descriptions-item label="客观题">{{ selected.objectiveScore }} 分</el-descriptions-item>
          <el-descriptions-item label="主观题">{{ selected.subjectiveScore }} 分</el-descriptions-item>
          <el-descriptions-item label="成绩等级">{{ { excellent: '优秀', good: '良好', pass: '合格', fail: '待提升' }[selected.level] }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="selected.answerVisible && selected.answerDetails?.length" class="answer-detail-list">
          <article v-for="item in selected.answerDetails" :key="item.questionId">
            <div><b>第 {{ item.order }} 题</b><span>{{ item.score }} / {{ item.maxScore }} 分</span></div>
            <h3>{{ item.stem }}</h3>
            <div class="result-answer"><small>你的答案</small><AnswerPreview :value="item.studentAnswer" /></div>
            <div class="result-answer"><small>参考答案</small><AnswerPreview :value="item.correctAnswer" /></div>
            <p><small>教师评语</small>{{ item.comment }}</p>
          </article>
        </div>
        <div v-else class="answer-tip">标准答案与解析按测评的“答案展示”设置控制；未到展示时间时仅显示成绩构成。</div>
      </template>
    </DetailDialog>
  </div>
</template>
