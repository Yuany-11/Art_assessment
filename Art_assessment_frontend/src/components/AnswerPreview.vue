<script setup lang="ts">
import { computed } from 'vue'
import { answerFiles, formatAnswer, isAudioFile, isImageFile } from '@/utils/answers'

const props = defineProps<{ value: unknown }>()
const files = computed(() => answerFiles(props.value))
const images = computed(() => files.value.filter((file) => isImageFile(file) && file.url))
const audio = computed(() => files.value.find((file) => isAudioFile(file)) ?? null)
</script>

<template>
  <div class="answer-preview">
    <p>{{ formatAnswer(value) }}</p>
    <div v-if="images.length" class="answer-preview-grid">
      <el-image
        v-for="file in images"
        :key="file.fileId"
        :src="file.url"
        :preview-src-list="images.map((item) => item.url)"
        :initial-index="images.indexOf(file)"
        :alt="file.name"
        fit="contain"
        preview-teleported
        class="answer-preview-image"
      />
    </div>
    <audio v-else-if="audio" :src="audio.url" controls class="answer-preview-audio" />
  </div>
</template>
