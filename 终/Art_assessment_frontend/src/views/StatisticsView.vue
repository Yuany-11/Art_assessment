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
import type { StatRow } from '@/types'

const auth = useAuthStore()
const chartEl = ref<HTMLDivElement>()
let chart: EChartsType | null = null
const loading = ref(false)
const rows = ref<StatRow[]>([])
const summary = ref({ studentCount: 0, participantCount: 0, avgScore: 0, participationRate: 0 })
const filters = ref({ subject: '', keyword: '' })
const groupOptions = computed(() => {
  if (auth.role === 'teacher') return [{ value: 'class', label: '班级' }]
  if (auth.role === 'school_admin') return [{ value: 'class', label: '班级' }, { value: 'school', label: '学校' }]
  if (auth.role === 'district_admin') return [{ value: 'school', label: '学校' }, { value: 'district', label: '区县' }]
  if (auth.role === 'city_admin') return [{ value: 'school', label: '学校' }, { value: 'district', label: '区县' }, { value: 'city', label: '市州' }]
  return [{ value: 'school', label: '学校' }, { value: 'district', label: '区县' }, { value: 'city', label: '市州' }]
})
const groupBy = ref(groupOptions.value.at(-1)?.value ?? 'school')

async function load() {
  loading.value = true
  try {
    const result = await api.statistics.list({ ...filters.value, groupBy: groupBy.value })
    rows.value = result.list
    summary.value = result.summary
    await nextTick()
    renderChart()
  } catch {
    rows.value = []
  } finally {
    loading.value = false
  }
}

function renderChart() {
  if (!chartEl.value) return
  chart ??= echarts.init(chartEl.value)
  chart.setOption({
    textStyle: { fontFamily: 'Inter, PingFang SC, Microsoft YaHei, sans-serif' },
    grid: { left: 42, right: 20, top: 30, bottom: 42 },
    tooltip: { trigger: 'axis', backgroundColor: '#fff', borderColor: '#e5e9f0', textStyle: { color: '#344054', fontSize: 13 }, extraCssText: 'box-shadow: 0 8px 24px rgba(16,24,40,.08); border-radius: 8px;' },
    xAxis: { type: 'category', data: rows.value.map((row) => row.targetName), axisTick: { show: false }, axisLine: { lineStyle: { color: '#e5e9f0' } }, axisLabel: { color: '#667085', fontSize: 12 } },
    yAxis: { type: 'value', max: 100, splitLine: { lineStyle: { color: '#eef1f6' } }, axisLabel: { color: '#98a2b3', fontSize: 11 } },
    series: [{ type: 'bar', data: rows.value.map((row) => row.avgScore), barWidth: 32, itemStyle: { color: '#5479d6', borderRadius: [5, 5, 0, 0] }, name: '平均分' }]
  })
}

async function exportStats() {
  try {
    const blob = await api.statistics.export({ groupBy: groupBy.value, ...filters.value })
    saveBlob(blob, `assessment-statistics-${Date.now()}.xlsx`)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function resize() {
  chart?.resize()
}
onMounted(() => {
  load()
  window.addEventListener('resize', resize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
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
      <el-select v-model="filters.subject" clearable placeholder="学科"><el-option label="音乐" value="music" /><el-option label="美术" value="art" /></el-select>
      <el-radio-group v-model="groupBy" @change="load"><el-radio-button v-for="option in groupOptions" :key="option.value" :value="option.value">{{ option.label }}</el-radio-button></el-radio-group>
      <el-button type="primary" @click="load">查询</el-button>
    </section>
    <section class="content-grid stats-grid">
      <article class="panel">
        <div class="panel-head"><h3>平均分对比</h3><span>{{ rows.length }} 个统计对象</span></div>
        <div ref="chartEl" class="chart-box"></div>
      </article>
      <article class="panel compact-panel">
        <div class="panel-head"><h3>排名概览</h3><span>按平均分</span></div>
        <div class="rank-list">
          <div v-for="row in rows" :key="row.targetId"><b>{{ row.rank }}</b><span>{{ row.targetName }}</span><strong>{{ row.avgScore }}</strong></div>
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
