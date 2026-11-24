<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue: number | null | undefined
    min?: number
    max?: number
    step?: number
    unit?: string
    disabled?: boolean
  }>(),
  {
    min: 0,
    max: 100,
    step: 0.5,
    unit: '',
    disabled: false
  }
)

const emit = defineEmits<{ 'update:modelValue': [value: number] }>()

const precision = computed(() => {
  const text = String(props.step)
  return text.includes('.') ? text.split('.')[1].length : 0
})

const current = computed(() => {
  const value = Number(props.modelValue ?? props.min)
  if (!Number.isFinite(value)) return props.min
  return Math.min(props.max, Math.max(props.min, value))
})

const display = computed(() => {
  const value = current.value
  if (Number.isInteger(value)) return String(value)
  return value.toFixed(precision.value)
})

const canDecrease = computed(() => current.value > props.min)
const canIncrease = computed(() => current.value < props.max)

// 中间的分数可以直接点开输入：键盘输入比连点加减更快，也方便录入 88.5 这类分数。
const draft = ref<string | null>(null)

function startEdit(event: FocusEvent) {
  if (props.disabled) return
  draft.value = display.value
  const input = event.target as HTMLInputElement
  requestAnimationFrame(() => input.select())
}

function onInput(event: Event) {
  draft.value = (event.target as HTMLInputElement).value
}

function commitEdit() {
  if (draft.value === null) return
  const raw = draft.value.trim()
  draft.value = null
  if (!raw) return
  const value = Number(raw)
  if (!Number.isFinite(value)) return
  emit('update:modelValue', clamp(value))
}

let holdTimer: ReturnType<typeof setTimeout> | null = null
let repeatTimer: ReturnType<typeof setInterval> | null = null
let repeated = false

function clamp(value: number) {
  const factor = 10 ** precision.value
  const rounded = Math.round(value * factor) / factor
  return Math.min(props.max, Math.max(props.min, rounded))
}

function change(delta: number) {
  if (props.disabled) return
  const next = clamp(current.value + delta)
  if (next !== current.value) emit('update:modelValue', next)
}

function stopHold() {
  if (holdTimer) {
    clearTimeout(holdTimer)
    holdTimer = null
  }
  if (repeatTimer) {
    clearInterval(repeatTimer)
    repeatTimer = null
  }
}

// 单击加减一档；按住按钮后连续加减，方便把分数逐步调到目标值。
function startHold(direction: 'up' | 'down') {
  if (props.disabled) return
  stopHold()
  repeated = false
  const delta = direction === 'up' ? props.step : -props.step
  holdTimer = setTimeout(() => {
    repeated = true
    change(delta)
    repeatTimer = setInterval(() => change(delta), 90)
  }, 420)
}

function handleClick(direction: 'up' | 'down') {
  if (repeated) {
    repeated = false
    return
  }
  change(direction === 'up' ? props.step : -props.step)
}

onBeforeUnmount(stopHold)
</script>

<template>
  <div class="score-stepper" :class="{ 'score-stepper--disabled': disabled }">
    <button
      type="button"
      class="score-stepper__button"
      :disabled="disabled || !canDecrease"
      aria-label="减分"
      @pointerdown="startHold('down')"
      @pointerup="stopHold"
      @pointerleave="stopHold"
      @pointercancel="stopHold"
      @click="handleClick('down')"
    >
      −
    </button>
    <input
      class="score-stepper__input"
      :value="draft ?? display"
      :disabled="disabled"
      inputmode="decimal"
      aria-label="得分"
      @focus="startEdit"
      @input="onInput"
      @blur="commitEdit"
      @keydown.enter.prevent="($event.target as HTMLInputElement).blur()"
      @keydown.esc.prevent="draft = null; ($event.target as HTMLInputElement).blur()"
    />
    <button
      type="button"
      class="score-stepper__button"
      :disabled="disabled || !canIncrease"
      aria-label="加分"
      @pointerdown="startHold('up')"
      @pointerup="stopHold"
      @pointerleave="stopHold"
      @pointercancel="stopHold"
      @click="handleClick('up')"
    >
      +
    </button>
    <span v-if="unit" class="score-stepper__unit">{{ unit }}</span>
  </div>
</template>
