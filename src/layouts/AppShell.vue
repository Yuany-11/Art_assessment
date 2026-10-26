<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import {
  Avatar,
  Collection,
  DataBoard,
  Document,
  DocumentChecked,
  DocumentCopy,
  Edit,
  EditPen,
  Expand,
  Fold,
  HomeFilled,
  Location,
  MapLocation,
  Medal,
  Menu,
  OfficeBuilding,
  Paperclip,
  Picture,
  Postcard,
  Reading,
  School,
  Search,
  Setting,
  SwitchButton,
  Tickets,
  TrendCharts,
  User,
  UserFilled
} from '@element-plus/icons-vue'
import { menusForRole } from '@/config/menu'
import { useAuthStore } from '@/stores/auth'
import { api } from '@/api'
import NotificationCenter from '@/components/NotificationCenter.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const groups = computed(() => menusForRole(auth.role))
const isStudent = computed(() => auth.role === 'student')
const isFullscreen = computed(() => Boolean(route.meta.fullscreen))
const collapsed = ref(false)
const iconMap = {
  Avatar,
  Collection,
  DataBoard,
  Document,
  DocumentChecked,
  DocumentCopy,
  Edit,
  EditPen,
  HomeFilled,
  Location,
  MapLocation,
  Medal,
  OfficeBuilding,
  Paperclip,
  Picture,
  Postcard,
  Reading,
  School,
  Search,
  Setting,
  Tickets,
  TrendCharts,
  User,
  UserFilled
}

function resolveIcon(name: string) {
  return iconMap[name as keyof typeof iconMap] ?? Menu
}

function active(path: string) {
  return route.path === path || route.path.startsWith(`${path}/`)
}

async function logout() {
  await ElMessageBox.confirm('确定退出当前账号吗？', '退出登录', { type: 'warning' })
  try {
    if (auth.refreshToken && !auth.refreshToken.startsWith('mock-')) {
      await api.auth.logout(auth.refreshToken)
    }
  } finally {
    auth.logout()
  }
  router.push('/login')
}
</script>

<template>
  <div
    class="app-shell"
    :class="{
      'app-shell--student': isStudent,
      'app-shell--attempt': isFullscreen,
      'app-shell--collapsed': collapsed
    }"
  >
    <aside v-if="!isFullscreen" class="sidebar">
      <div class="sidebar-atmosphere" aria-hidden="true">
        <span class="sidebar-image-wash"></span>
        <span class="sidebar-aurora sidebar-aurora--blue"></span>
        <span class="sidebar-aurora sidebar-aurora--violet"></span>
        <span class="sidebar-gold-thread"></span>
        <span class="sidebar-art-word">ART</span>
        <svg class="sidebar-stave" viewBox="0 0 220 640" preserveAspectRatio="none">
          <path d="M-24 550 C48 440 158 510 244 330" />
          <path d="M-28 574 C52 462 160 532 250 352" />
          <path d="M-34 598 C58 484 164 552 256 374" />
        </svg>
        <i v-for="particle in 6" :key="particle" class="sidebar-particle" :class="`sidebar-particle--${particle}`"></i>
      </div>
      <div class="brand">
        <div class="brand-mark">艺</div>
        <div>
          <strong>艺术素质测评</strong>
          <span>Assessment Console</span>
        </div>
      </div>
      <nav class="nav">
        <section v-for="group in groups" :key="group.title" class="nav-group">
          <p class="nav-title">{{ group.title }}</p>
          <router-link
            v-for="item in group.items"
            :key="item.path"
            :to="item.path"
            :title="item.title"
            class="nav-item"
            :class="{ active: active(item.path) }"
          >
            <el-icon><component :is="resolveIcon(item.icon)" /></el-icon>
            <span>{{ item.title }}</span>
          </router-link>
        </section>
      </nav>
      <div class="sidebar-footer">
        <span class="status-dot"></span>
        <div><b>演示环境</b><small>本地数据已连接</small></div>
      </div>
    </aside>

    <div class="shell-main">
      <header v-if="!isFullscreen" class="topbar">
        <div class="topbar-heading">
          <span class="breadcrumb">艺术素质测评 <i>/</i> {{ auth.user?.roleName }}</span>
          <h1>{{ route.meta.title || '工作台' }}</h1>
        </div>
        <div class="topbar-actions">
          <el-button
            class="sidebar-toggle"
            circle
            text
            :title="collapsed ? '展开导航' : '收起导航'"
            @click="collapsed = !collapsed"
          >
            <el-icon><component :is="collapsed ? Expand : Fold" /></el-icon>
          </el-button>
          <span class="environment-chip">演示环境</span>
          <NotificationCenter />
          <div class="user-chip">
            <div class="avatar">{{ auth.user?.realName?.slice(0, 1) }}</div>
            <div><b>{{ auth.user?.realName }}</b><small>{{ auth.user?.schoolName || auth.user?.cityName || '全域题库' }}</small></div>
          </div>
          <el-button class="logout-button" text :icon="SwitchButton" @click="logout">退出</el-button>
        </div>
      </header>
      <main class="page-content">
        <router-view />
      </main>
    </div>
  </div>
</template>
