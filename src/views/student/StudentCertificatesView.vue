<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/api'
import { saveBlob } from '@/api/client'
import type { Certificate, Subject } from '@/types'

const certificates = ref<Certificate[]>([])
const loading = ref(false)
const subject = ref<Subject>('music')
const visibleCertificates = computed(() => certificates.value.filter((item) => item.subject === subject.value))
const levelLabels: Record<string, string> = { excellent: '优秀', good: '良好', pass: '合格', fail: '待提升' }

async function load() {
  loading.value = true
  try {
    certificates.value = await api.certificates.list()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function download(cert: Certificate) {
  try {
    const blob = await api.certificates.download(cert.id)
    saveBlob(blob, `${cert.certificateNo}.pdf`)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

onMounted(load)
</script>

<template>
  <div class="student-page stack">
    <div class="mobile-title"><p>MY CERTIFICATES</p><h2>我的证书</h2><span>完成正式测评并判分后可查看证书。</span></div>
    <div class="filter-bar"><el-radio-group v-model="subject"><el-radio-button value="music">音乐证书</el-radio-button><el-radio-button value="art">美术证书</el-radio-button></el-radio-group></div>
    <section v-loading="loading" class="certificate-list">
      <article v-for="cert in visibleCertificates" :key="cert.id" class="certificate-card">
        <div class="certificate-seal">艺</div>
        <span>艺术素质测评证书</span>
        <h3>{{ cert.studentName }}</h3>
        <p>{{ cert.assessmentTitle }}</p>
        <div><b>{{ cert.score }} 分</b><span>{{ levelLabels[cert.level] ?? cert.level }}</span></div>
        <small>证书编号 {{ cert.certificateNo }}</small>
        <el-button type="primary" plain class="full-button" :disabled="cert.status !== 'ready'" @click="download(cert)">下载证书</el-button>
      </article>
    </section>
    <section v-if="!visibleCertificates.length && !loading" class="student-card empty-card">当前学科暂无已生成证书，完成正式测评并判分后可查看。</section>
  </div>
</template>
