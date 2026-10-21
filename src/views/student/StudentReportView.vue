<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import echarts, { type EChartsType } from '@/lib/echarts'
import { ElMessage } from 'element-plus'
import { Download, Printer } from '@element-plus/icons-vue'
import { api } from '@/api'
import { saveBlob } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { LearningReport, Subject } from '@/types'

const auth = useAuthStore()
const report = ref<LearningReport | null>(null)
const loading = ref(false)
const subject = ref<Subject>('music')
const chartEl = ref<HTMLDivElement>()
let chart: EChartsType | null = null

async function load() {
  loading.value = true
  try {
    report.value = await api.reports.get(auth.user?.id ?? 1001, subject.value)
    if (!report.value) {
      ElMessage.info('当前学科暂无已生成报告')
      chart?.clear()
      return
    }
    await nextTick()
    if (chartEl.value) {
      chart ??= echarts.init(chartEl.value)
      chart.setOption({
        textStyle: { fontFamily: 'Inter, PingFang SC, Microsoft YaHei, sans-serif' },
        grid: { left: 35, right: 20, top: 25, bottom: 35 },
        tooltip: { trigger: 'axis', backgroundColor: '#fff', borderColor: '#e5e9f0', textStyle: { color: '#344054' } },
        xAxis: { type: 'category', data: report.value.scoreTrend.map((point) => point.date), axisTick: { show: false }, axisLine: { lineStyle: { color: '#e5e9f0' } }, axisLabel: { color: '#667085', fontSize: 12 } },
        yAxis: { type: 'value', min: 0, max: 100, splitLine: { lineStyle: { color: '#eef1f6' } }, axisLabel: { color: '#98a2b3', fontSize: 11 } },
        series: [{ type: 'line', data: report.value.scoreTrend.map((point) => point.score), smooth: true, symbolSize: 8, lineStyle: { color: '#3569d4', width: 3 }, itemStyle: { color: '#3569d4' }, areaStyle: { color: 'rgba(53,105,212,.10)' } }]
      })
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

function download() {
  if (!report.value) return
  saveBlob(new Blob([report.value.rawText], { type: 'text/plain;charset=utf-8' }), `学情报告-${report.value.reportId}.txt`)
}

function printReport() {
  window.print()
}

onMounted(load)
</script>

<template>
  <div class="student-page stack report-page">
    <div class="mobile-title"><p>LEARNING REPORT</p><h2>我的学习报告</h2><span>结合历次成绩与答题表现生成个性化建议。</span></div>
    <div class="filter-bar">
      <el-radio-group v-model="subject" @change="load"><el-radio-button value="music">音乐</el-radio-button><el-radio-button value="art">美术</el-radio-button></el-radio-group>
      <el-button :icon="Printer" @click="printReport">打印报告</el-button>
      <el-button :icon="Download" :disabled="!report" @click="download">导出正文</el-button>
    </div>
    <div v-loading="loading" class="report-body">
      <template v-if="report">
        <section class="report-head">
          <div><span>个性化学习报告</span><h2>{{ auth.user?.realName }} · {{ subject === 'music' ? '音乐' : '美术' }}</h2><p>{{ report.summary }}</p></div>
          <div class="report-score"><strong>{{ report.scoreTrend.at(-1)?.score }}</strong><span>最新测评</span></div>
        </section>
        <section class="student-card"><div class="student-section-head"><h3>成绩趋势</h3><span>{{ report.generatedAt.slice(0, 10) }} 生成</span></div><div ref="chartEl" class="student-chart"></div></section>
        <section class="report-grid">
          <article class="report-card success"><h3>优势表现</h3><ul><li v-for="item in report.strengths" :key="item">{{ item }}</li></ul></article>
          <article class="report-card warning"><h3>需要加强</h3><ul><li v-for="item in report.weaknesses" :key="item">{{ item }}</li></ul></article>
        </section>
        <section class="report-narrative"><h3>学习建议</h3><ol><li v-for="item in report.suggestions" :key="item">{{ item }}</li></ol><p>{{ report.rawText }}</p><small>模型版本：{{ report.modelVersion }} · AI 结果仅作为学习辅助</small></section>
      </template>
      <div v-else class="student-card empty-card">当前学科暂无报告，完成正式测评并生成分析后可查看。</div>
    </div>
  </div>
</template>
