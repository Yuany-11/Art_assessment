<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import MetricCard from '@/components/MetricCard.vue'

const auth = useAuthStore()
const quickActions = computed(() => {
  if (auth.role === 'question_admin') return [
    { title: '试题管理', text: '查询、创建与审核试题', path: '/qbank/questions' },
    { title: '课程章节', text: '维护课程与章节结构', path: '/qbank/courses' },
    { title: '操作日志', text: '追踪题库操作记录', path: '/logs' }
  ]
  return [
    { title: '组卷管理', text: '创建、编辑和下载测评试卷', path: '/papers' },
    { title: '测评发布', text: '按组织与年级发布测评', path: '/assessments' },
    { title: '数据统计', text: '查看区域参与率和成绩分布', path: '/statistics' }
  ]
})
</script>

<template>
  <div class="stack">
    <section class="hero-card">
      <div>
        <span class="eyebrow">{{ auth.user?.roleName }}工作台</span>
        <h2>{{ auth.user?.realName }}，今天从这里开始</h2>
        <p>当前账号的数据范围和功能入口已经就绪。工作簿中的 268 项功能可按角色持续验收。</p>
      </div>
      <div class="hero-orbit"><span>268</span><small>功能验收</small></div>
    </section>

    <section class="metrics-grid">
      <MetricCard label="待发布试卷" value="12" note="草稿与就绪状态" tone="blue" />
      <MetricCard label="进行中测评" value="8" note="本周计划" tone="green" />
      <MetricCard label="待审核试题" value="19" note="题库审核队列" tone="amber" />
      <MetricCard label="本月参与率" value="93.8%" note="较上期提升 2.4%" tone="violet" />
    </section>

    <section class="content-grid">
      <article class="panel">
        <div class="panel-head"><h3>快捷入口</h3><span>常用功能</span></div>
        <div class="quick-list">
          <router-link v-for="item in quickActions" :key="item.path" :to="item.path">
            <div><b>{{ item.title }}</b><span>{{ item.text }}</span></div>
            <span>→</span>
          </router-link>
        </div>
      </article>
      <article class="panel">
        <div class="panel-head"><h3>今日待办</h3><span>3 项</span></div>
        <ul class="todo-list">
          <li><span class="todo-dot amber"></span><div><b>完善学校测评发布</b><small>核对发布年级与参与班级</small></div></li>
          <li><span class="todo-dot blue"></span><div><b>核验区域统计口径</b><small>确认参与率分母为学生人数</small></div></li>
          <li><span class="todo-dot green"></span><div><b>回归角色菜单</b><small>覆盖学校、区县、市州、省和题库</small></div></li>
        </ul>
      </article>
    </section>
  </div>
</template>
