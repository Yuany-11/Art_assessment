<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import echarts, { type EChartsType } from '@/utils/echarts'
import { ElMessage } from 'element-plus'
import { Download, Search } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import MetricCard from '@/components/MetricCard.vue'
import { api } from '@/api'
import { saveBlob } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { ensureTeacherSubject } from '@/utils/teacherAccess'
import { demoStatRows } from '@/utils/demoStatistics'
import type { StatRow, Subject } from '@/types'

const auth = useAuthStore()
const chartEl = ref<HTMLDivElement>()
const pieEl = ref<HTMLDivElement>()
let chart: EChartsType | null = null
let pieChart: EChartsType | null = null
const loading = ref(false)
const rows = ref<StatRow[]>([])
const summary = ref({ studentCount: 0, participantCount: 0, avgScore: 0, participationRate: 0 })
const filters = ref({ subject: '', keyword: '' })
const groupOptions = computed(() => {
  if (auth.role === 'teacher') return [{ value: 'class', label: '班级' }]
  if (auth.role === 'school_admin') return [{ value: 'class', label: '班级' }, { value: 'school', label: '学校' }]
  // 区县管理员只管理本区学校，不能跨区县比较。
  if (auth.role === 'district_admin') return [{ value: 'school', label: '学校' }]
  if (auth.role === 'city_admin') return [{ value: 'school', label: '学校' }, { value: 'district', label: '区县' }, { value: 'city', label: '市州' }]
  return [{ value: 'school', label: '学校' }, { value: 'district', label: '区县' }, { value: 'city', label: '市州' }]
})
const groupBy = ref(groupOptions.value.at(-1)?.value ?? 'school')
const groupLabel = computed(
  () => groupOptions.value.find((option) => option.value === groupBy.value)?.label ?? '统计对象'
)
const participation = computed(() => {
  const total = rows.value.reduce((sum, row) => sum + row.studentCount, 0)
  const participants = rows.value.reduce((sum, row) => sum + row.participantCount, 0)
  return {
    total,
    participants,
    pending: Math.max(total - participants, 0),
    rate: total ? (participants / total) * 100 : 0
  }
})

function onSubjectFilterChange(value: string | number | boolean) {
  const subject = value as Subject | ''
  if (subject && !ensureTeacherSubject(auth.user, subject)) filters.value.subject = ''
}

function summarize(list: StatRow[]) {
  const studentCount = list.reduce((sum, row) => sum + row.studentCount, 0)
  const participantCount = list.reduce((sum, row) => sum + row.participantCount, 0)
  const scoreTotal = list.reduce((sum, row) => sum + row.avgScore * row.studentCount, 0)
  return {
    studentCount,
    participantCount,
    avgScore: studentCount ? scoreTotal / studentCount : 0,
    participationRate: studentCount ? participantCount / studentCount : 0
  }
}

async function load() {
  loading.value = true
  try {
    const result = await api.statistics.list({ ...filters.value, groupBy: groupBy.value })
    // DEMO-FAKE-STATS：演示假数据，展示结束后删除 demoStatistics.ts 与这行引用。
    rows.value =
      demoStatRows(auth.role, groupBy.value, result.list, filters.value.keyword) ?? result.list
    summary.value = summarize(rows.value)
    await nextTick()
    renderChart()
    renderPie()
  } catch {
    rows.value = []
    await nextTick()
    renderPie()
  } finally {
    loading.value = false
  }
}

function renderChart() {
  if (!chartEl.value) return
  chart ??= echarts.init(chartEl.value)
  // 区县/市州较多时拆成上下两行，避免柱子挤在一起、标签互相遮挡。
  const midpoint = Math.ceil(rows.value.length / 2)
  const firstRows = rows.value.slice(0, midpoint)
  const secondRows = rows.value.slice(midpoint)
  const makeAxis = (list: StatRow[], gridIndex: number) => ({
    type: 'category' as const,
    gridIndex,
    data: list.map((row) => row.targetName),
    axisTick: { show: false },
    axisLine: { lineStyle: { color: '#e5e9f0' } },
    axisLabel: {
      color: '#667085',
      fontSize: 11,
      interval: 0,
      rotate: list.length > 6 ? 30 : 0,
      margin: 10
    }
  })
  const makeSeries = (list: StatRow[], index: number, color: string) => ({
    type: 'bar' as const,
    name: '平均分',
    xAxisIndex: index,
    yAxisIndex: index,
    data: list.map((row) => row.avgScore),
    barMaxWidth: 24,
    itemStyle: { color, borderRadius: [5, 5, 0, 0] },
    label: { show: true, position: 'top', color: '#667085', fontSize: 10 }
  })
  const hasSecond = secondRows.length > 0
  chart.setOption({
    textStyle: { fontFamily: 'Inter, PingFang SC, Microsoft YaHei, sans-serif' },
    tooltip: { trigger: 'axis', backgroundColor: '#fff', borderColor: '#e5e9f0', textStyle: { color: '#344054', fontSize: 13 }, extraCssText: 'box-shadow: 0 8px 24px rgba(16,24,40,.08); border-radius: 8px;' },
    grid: [
      { left: 46, right: 24, top: 18, height: 168, show: true },
      { left: 46, right: 24, top: 286, height: 168, show: hasSecond }
    ],
    xAxis: [makeAxis(firstRows, 0), makeAxis(secondRows, 1)],
    yAxis: [
      { type: 'value', gridIndex: 0, max: 100, splitLine: { lineStyle: { color: '#eef1f6' } }, axisLabel: { color: '#98a2b3', fontSize: 11 } },
      { type: 'value', gridIndex: 1, max: 100, show: hasSecond, splitLine: { lineStyle: { color: '#eef1f6' } }, axisLabel: { color: '#98a2b3', fontSize: 11 } }
    ],
    series: [
      makeSeries(firstRows, 0, '#5479d6'),
      makeSeries(secondRows, 1, '#7c9be8')
    ]
  }, true)
}

function renderPie() {
  if (!pieEl.value) return
  pieChart ??= echarts.init(pieEl.value)
  const { total, participants, pending, rate } = participation.value
  const hasData = total > 0 || participants > 0
  pieChart.setOption(
    {
      textStyle: { fontFamily: 'Inter, PingFang SC, Microsoft YaHei, sans-serif' },
      title: {
        text: `${rate.toFixed(1)}%`,
        subtext: hasData ? '总参与率' : '暂无参与数据',
        left: 'center',
        top: '34%',
        itemGap: 4,
        textStyle: { color: '#344054', fontSize: 28, fontWeight: 700 },
        subtextStyle: { color: '#98a2b3', fontSize: 12 }
      },
      tooltip: {
        trigger: 'item',
        formatter: (params: { name?: string }) => {
          const name = params.name ?? ''
          const count = name === '已参与' ? participants : pending
          const percent = total ? ((count / total) * 100).toFixed(1) : '0.0'
          return `${name}<br/>${count} 人（${percent}%）`
        },
        backgroundColor: '#fff',
        borderColor: '#e5e9f0',
        textStyle: { color: '#344054', fontSize: 13 },
        extraCssText: 'box-shadow: 0 8px 24px rgba(16,24,40,.08); border-radius: 8px;'
      },
      legend: {
        bottom: 0,
        left: 'center',
        icon: 'circle',
        itemWidth: 9,
        itemHeight: 9,
        itemGap: 22,
        textStyle: { color: '#667085', fontSize: 12 }
      },
      series: [
        {
          name: '参与情况',
          type: 'pie',
          radius: ['54%', '76%'],
          center: ['50%', '45%'],
          avoidLabelOverlap: true,
          itemStyle: { borderColor: '#fff', borderWidth: 3 },
          label: { show: false },
          labelLine: { show: false },
          emphasis: {
            scaleSize: 6,
            label: {
              show: true,
              fontSize: 14,
              fontWeight: 600,
              color: '#344054',
              formatter: '{b}\n{c} 人'
            }
          },
          data: hasData
            ? [
                { value: participants, name: '已参与', itemStyle: { color: '#12b76a' } },
                { value: pending, name: '未参与', itemStyle: { color: '#d0d5dd' } }
              ]
            : [
                { value: 0, name: '已参与', itemStyle: { color: '#12b76a' } },
                { value: 1, name: '未参与', itemStyle: { color: '#d0d5dd' } }
              ]
        }
      ]
    },
    true
  )
}

function csvCell(value: unknown): string {
  const text = String(value ?? '')
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function exportStats() {
  // 页面表格可能包含演示数据，导出必须与页面同源；此前导出走后端真实数据，
  // 会出现“页面有数据、导出为空”的不一致。
  const header = ['排名', '统计对象', '学生数', '参与人数', '参与率', '平均分', '合格率', '优秀率']
  const lines = rows.value.map((row) => [
    row.rank,
    row.targetName,
    row.studentCount,
    row.participantCount,
    `${(row.participationRate * 100).toFixed(1)}%`,
    row.avgScore,
    `${(row.passRate * 100).toFixed(1)}%`,
    `${(row.excellentRate * 100).toFixed(1)}%`
  ])
  const csv = [header, ...lines].map((line) => line.map(csvCell).join(',')).join('\r\n')
  saveBlob(
    new Blob([`﻿${csv}`], { type: 'text/csv;charset=utf-8' }),
    `assessment-statistics-${Date.now()}.csv`
  )
}

function resize() {
  chart?.resize()
  pieChart?.resize()
}
onMounted(() => {
  load()
  window.addEventListener('resize', resize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
  pieChart?.dispose()
})
</script>

<template>
  <div class="stack">
    <PageHeader title="数据统计" description="按当前数据范围查看学生参与、成绩水平和区域排名。">
      <el-button :icon="Download" @click="exportStats">导出统计表</el-button>
    </PageHeader>
    <section class="metrics-grid">
      <MetricCard label="学生总数" :value="summary.studentCount.toLocaleString()" note="当前统计范围" />
      <MetricCard label="实际参与" :value="summary.participantCount.toLocaleString()" note="已开始或已提交" tone="green" />
      <MetricCard label="参与率" :value="`${(summary.participationRate * 100).toFixed(1)}%`" note="参与人数 / 学生人数" tone="amber" />
      <MetricCard label="平均分" :value="summary.avgScore.toFixed(1)" note="正式测评成绩" tone="violet" />
    </section>
    <section class="filter-bar panel">
      <el-input v-model="filters.keyword" :prefix-icon="Search" clearable placeholder="学校、区县或市州名称" />
      <el-select v-model="filters.subject" clearable placeholder="学科" @change="onSubjectFilterChange"><el-option label="音乐" value="music" /><el-option label="美术" value="art" /></el-select>
      <el-radio-group v-model="groupBy" @change="load"><el-radio-button v-for="option in groupOptions" :key="option.value" :value="option.value">{{ option.label }}</el-radio-button></el-radio-group>
      <el-button type="primary" @click="load">查询</el-button>
    </section>
    <section class="content-grid stats-grid">
      <article class="panel">
        <div class="panel-head"><h3>平均分对比</h3><span>{{ rows.length }} 个统计对象</span></div>
        <div ref="chartEl" class="chart-box chart-box--tall"></div>
      </article>
      <article class="panel compact-panel">
        <div class="panel-head"><h3>排名概览</h3><span>按平均分</span></div>
        <div class="rank-list">
          <div v-for="row in rows" :key="row.targetId"><b>{{ row.rank }}</b><span>{{ row.targetName }}</span><strong>{{ row.avgScore }}</strong></div>
        </div>
      </article>
    </section>
    <section class="content-grid participation-grid">
      <article class="panel">
        <div class="panel-head"><h3>参与情况</h3><span>按{{ groupLabel }}统计 · 已参与 / 未参与</span></div>
        <div ref="pieEl" class="chart-box"></div>
      </article>
      <article class="panel compact-panel">
        <div class="panel-head"><h3>各{{ groupLabel }}参与情况</h3><span>{{ rows.length }} 个统计对象</span></div>
        <div class="participation-list">
          <div v-for="row in rows" :key="row.targetId" class="participation-item">
            <div class="participation-head">
              <b>{{ row.targetName }}</b>
              <span>{{ (row.participationRate * 100).toFixed(1) }}%</span>
            </div>
            <div class="participation-bar"><i :style="{ width: `${Math.min(row.participationRate * 100, 100)}%` }"></i></div>
            <small>已参与 {{ row.participantCount }} 人 · 未参与 {{ Math.max(row.studentCount - row.participantCount, 0) }} 人</small>
          </div>
          <el-empty v-if="!rows.length" description="暂无统计数据" :image-size="64" />
        </div>
      </article>
    </section>
    <section class="panel">
      <el-table v-loading="loading" :data="rows">
        <el-table-column prop="rank" label="排名" width="70" />
        <el-table-column prop="targetName" label="统计对象" min-width="170" />
        <el-table-column prop="studentCount" label="学生数" width="110" />
        <el-table-column prop="participantCount" label="参与人数" width="110" />
        <el-table-column label="参与率" width="110"><template #default="{ row }">{{ (row.participationRate * 100).toFixed(1) }}%</template></el-table-column>
        <el-table-column prop="avgScore" label="平均分" width="100" />
        <el-table-column label="合格率" width="110"><template #default="{ row }">{{ (row.passRate * 100).toFixed(1) }}%</template></el-table-column>
        <el-table-column label="优秀率" width="110"><template #default="{ row }">{{ (row.excellentRate * 100).toFixed(1) }}%</template></el-table-column>
      </el-table>
    </section>
  </div>
</template>
