<script setup lang="ts">
import { ref, watch } from 'vue'
import { FullScreen, ScaleToOriginal } from '@element-plus/icons-vue'

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    title?: string
    width?: string | number
    fullscreenable?: boolean
    appendToBody?: boolean
    destroyOnClose?: boolean
    closeOnClickModal?: boolean
  }>(),
  {
    title: '',
    width: '720px',
    fullscreenable: true,
    appendToBody: true,
    destroyOnClose: false,
    closeOnClickModal: false
  }
)

const emit = defineEmits<{ (event: 'update:modelValue', value: boolean): void }>()

const fullscreen = ref(false)

watch(
  () => props.modelValue,
  (open) => {
    if (!open) fullscreen.value = false
  }
)

function updateVisible(value: boolean) {
  emit('update:modelValue', value)
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :width="width"
    :fullscreen="fullscreen"
    :append-to-body="appendToBody"
    :destroy-on-close="destroyOnClose"
    :close-on-click-modal="closeOnClickModal"
    align-center
    class="detail-dialog"
    @update:model-value="updateVisible"
  >
    <template #header="{ titleId, titleClass }">
      <div class="detail-dialog-head">
        <span :id="titleId" :class="titleClass" class="detail-dialog-title">{{ title }}</span>
        <el-button
          v-if="fullscreenable"
          text
          circle
          class="detail-dialog-fullscreen"
          :title="fullscreen ? '退出全屏' : '全屏查看'"
          @click="fullscreen = !fullscreen"
        >
          <el-icon><ScaleToOriginal v-if="fullscreen" /><FullScreen v-else /></el-icon>
        </el-button>
      </div>
    </template>
    <slot />
    <template v-if="$slots.footer" #footer>
      <slot name="footer" />
    </template>
  </el-dialog>
</template>
