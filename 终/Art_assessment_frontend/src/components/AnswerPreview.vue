<script setup lang="ts">
import { computed } from 'vue'
import { answerFile, formatAnswer, isAudioFile, isImageFile } from '@/utils/answers'

const props = defineProps<{ value: unknown }>()
const file = computed(() => answerFile(props.value))
</script>

<template>
  <div class="answer-preview">
    <p>{{ formatAnswer(value) }}</p>
    <img v-if="file && isImageFile(file)" :src="file.url" :alt="file.name" class="answer-preview-image" />
    <audio v-else-if="file && isAudioFile(file)" :src="file.url" controls class="answer-preview-audio" />
  </div>
</template>
