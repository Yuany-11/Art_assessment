<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import { api } from '@/api'
import type { Chapter, Course, Subject } from '@/types'

const loading = ref(false)
const courses = ref<Course[]>([])
const chapters = ref<Chapter[]>([])
const selectedCourse = ref<Course | null>(null)
const keyword = ref('')
const courseOpen = ref(false)
const chapterOpen = ref(false)
const editingCourse = ref<Course | null>(null)
const editingChapter = ref<Chapter | null>(null)
const courseForm = reactive({ name: '', subject: 'music' as Subject, grade: 7, description: '', status: 'active' as Course['status'], sortOrder: 0 })
const chapterForm = reactive({ name: '', description: '', sortOrder: 0 })

async function loadCourses() {
  loading.value = true
  try {
    const result = await api.courses.list({ keyword: keyword.value, pageSize: 100 })
    courses.value = result.list
    if (!selectedCourse.value && courses.value[0]) await selectCourse(courses.value[0])
  } finally {
    loading.value = false
  }
}

async function selectCourse(course: Course) {
  selectedCourse.value = course
  chapters.value = await api.courses.chapters(course.id)
}

function openCourse(course?: Course) {
  editingCourse.value = course ?? null
  Object.assign(courseForm, course ? { name: course.name, subject: course.subject, grade: course.grade, description: course.description ?? '', status: course.status, sortOrder: course.sortOrder } : { name: '', subject: 'music', grade: 7, description: '', status: 'active', sortOrder: 0 })
  courseOpen.value = true
}

async function saveCourse() {
  if (!courseForm.name.trim()) return ElMessage.warning('请填写课程名称')
  if (editingCourse.value) await api.courses.update(editingCourse.value.id, { ...courseForm })
  else await api.courses.create({ ...courseForm })
  courseOpen.value = false
  ElMessage.success('课程已保存')
  await loadCourses()
}

function openChapter(chapter?: Chapter) {
  if (!selectedCourse.value) return
  editingChapter.value = chapter ?? null
  Object.assign(chapterForm, chapter ? { name: chapter.name, description: chapter.description ?? '', sortOrder: chapter.sortOrder } : { name: '', description: '', sortOrder: 0 })
  chapterOpen.value = true
}

async function saveChapter() {
  if (!selectedCourse.value || !chapterForm.name.trim()) return ElMessage.warning('请填写章节名称')
  if (editingChapter.value) await api.courses.updateChapter(editingChapter.value.id, { ...chapterForm })
  else await api.courses.createChapter(selectedCourse.value.id, { ...chapterForm })
  chapterOpen.value = false
  ElMessage.success('章节已保存')
  await selectCourse(selectedCourse.value)
  await loadCourses()
}

async function removeCourse(course: Course) {
  try {
    await ElMessageBox.confirm(`确定删除“${course.name}”吗？`, '删除课程', { type: 'warning' })
    await api.courses.remove(course.id)
    selectedCourse.value = null
    chapters.value = []
    ElMessage.success('课程已删除')
    await loadCourses()
  } catch (error) {
    if (error instanceof Error) ElMessage.error(error.message)
  }
}

async function removeChapter(chapter: Chapter) {
  await api.courses.removeChapter(chapter.id)
  ElMessage.success('章节已删除')
  if (selectedCourse.value) await selectCourse(selectedCourse.value)
}

onMounted(loadCourses)
</script>

<template>
  <div class="stack">
    <PageHeader title="课程与章节" description="维护课程结构、章节顺序和题库归属。">
      <el-button type="primary" :icon="Plus" @click="openCourse()">新建课程</el-button>
    </PageHeader>
    <section class="filter-bar panel">
      <el-input v-model="keyword" :prefix-icon="Search" clearable placeholder="课程名称" @keyup.enter="loadCourses" />
      <el-button type="primary" @click="loadCourses">查询</el-button>
    </section>
    <section class="content-grid course-grid">
      <article class="panel course-list">
        <button v-for="course in courses" :key="course.id" :class="{ active: selectedCourse?.id === course.id }" @click="selectCourse(course)">
          <div><b>{{ course.name }}</b><span>{{ course.subject === 'music' ? '音乐' : '美术' }} · {{ course.grade }} 年级 · {{ course.chapterCount }} 个章节</span></div>
          <StatusTag :value="course.status" />
        </button>
      </article>
      <article class="panel">
        <div class="panel-head">
          <div><h3>{{ selectedCourse?.name || '选择课程' }}</h3><span>{{ selectedCourse?.description }}</span></div>
          <div class="inline-action">
            <el-button v-if="selectedCourse" @click="openCourse(selectedCourse)">编辑课程</el-button>
            <el-button v-if="selectedCourse" type="danger" plain @click="removeCourse(selectedCourse)">删除课程</el-button>
            <el-button v-if="selectedCourse" type="primary" @click="openChapter()">新增章节</el-button>
          </div>
        </div>
        <el-table v-loading="loading" :data="chapters">
          <el-table-column prop="sortOrder" label="排序" width="70" />
          <el-table-column prop="name" label="章节名称" min-width="180" />
          <el-table-column prop="description" label="说明" min-width="220" />
          <el-table-column prop="questionCount" label="题目数" width="100" />
          <el-table-column label="操作" width="150"><template #default="{ row }"><el-button link @click="openChapter(row)">编辑</el-button><el-button link type="danger" @click="removeChapter(row)">删除</el-button></template></el-table-column>
        </el-table>
      </article>
    </section>

    <el-dialog v-model="courseOpen" :title="editingCourse ? '编辑课程' : '新建课程'" width="580px">
      <el-form label-position="top" class="form-grid">
        <el-form-item label="课程名称" required class="span-2"><el-input v-model="courseForm.name" /></el-form-item>
        <el-form-item label="学科"><el-select v-model="courseForm.subject"><el-option label="音乐" value="music" /><el-option label="美术" value="art" /></el-select></el-form-item>
        <el-form-item label="适用年级"><el-select v-model="courseForm.grade"><el-option v-for="g in 12" :key="g" :label="`${g} 年级`" :value="g" /></el-select></el-form-item>
        <el-form-item label="状态"><el-select v-model="courseForm.status"><el-option label="启用" value="active" /><el-option label="停用" value="disabled" /></el-select></el-form-item>
        <el-form-item label="排序"><el-input-number v-model="courseForm.sortOrder" :min="0" /></el-form-item>
        <el-form-item label="课程简介" class="span-2"><el-input v-model="courseForm.description" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="courseOpen = false">取消</el-button><el-button type="primary" @click="saveCourse">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="chapterOpen" :title="editingChapter ? '编辑章节' : '新增章节'" width="540px">
      <el-form label-position="top">
        <el-form-item label="章节名称" required><el-input v-model="chapterForm.name" /></el-form-item>
        <el-form-item label="章节说明"><el-input v-model="chapterForm.description" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="排序"><el-input-number v-model="chapterForm.sortOrder" :min="0" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="chapterOpen = false">取消</el-button><el-button type="primary" @click="saveChapter">保存</el-button></template>
    </el-dialog>
  </div>
</template>
