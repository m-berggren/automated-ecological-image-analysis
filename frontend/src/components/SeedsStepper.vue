<template>
  <nav class="border-b border-border bg-surface/50 px-8 py-3 shrink-0">
    <ol class="flex items-center gap-2 max-w-3xl mx-auto">
      <template v-for="(step, idx) in steps" :key="step.key">
        <li>
          <component
            :is="hrefFor(step) ? RouterLink : 'div'"
            :to="hrefFor(step) ?? undefined"
            class="flex items-center gap-2"
            :class="{
              'cursor-pointer hover:opacity-80': hrefFor(step),
              'cursor-default': !hrefFor(step),
            }"
          >
            <span
              class="w-6 h-6 rounded-full flex items-center justify-center text-xs font-semibold border-2 transition-colors shrink-0"
              :class="circleClass(step, idx)"
            >
              <Check v-if="isCompleted(idx)" class="w-3.5 h-3.5" />
              <span v-else>{{ idx + 1 }}</span>
            </span>
            <span
              class="text-sm font-medium"
              :class="{
                'text-foreground': isCurrent(idx),
                'text-muted-foreground': !isCurrent(idx),
              }"
            >
              {{ step.label }}
            </span>
          </component>
        </li>
        <li v-if="idx < steps.length - 1" class="flex-1 h-px bg-border" />
      </template>
    </ol>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { Check } from 'lucide-vue-next'

type StepKey = 'upload' | 'detect' | 'review'| 'review-final' | 'export'

interface Step {
  key: StepKey
  label: string
}

const props = defineProps<{
  current: StepKey
  runId?: number | string
}>()

const steps: Step[] = [
  { key: 'upload', label: 'Upload' },
  { key: 'detect', label: 'Detect' },
  { key: 'review', label: 'Review' },
  { key: 'review-final', label: 'Final Review' },
  { key: 'export', label: 'Export' },
]

const currentIdx = computed(() => steps.findIndex((s) => s.key === props.current))

function isCurrent(idx: number) {
  return idx === currentIdx.value
}
function isCompleted(idx: number) {
  return idx < currentIdx.value
}
function circleClass(_step: Step, idx: number) {
  if (isCompleted(idx)) return 'bg-primary border-primary text-primary-foreground'
  if (isCurrent(idx)) return 'border-primary text-primary'
  return 'border-border text-muted-foreground'
}

function hrefFor(step: Step): string | null {
  if (step.key === 'upload') return '/seeds/upload'
  if (!props.runId) return null
  if (step.key === 'detect') return `/seeds/runs/${props.runId}/detect`
  if (step.key === 'review') return `/seeds/runs/${props.runId}/review`
  if (step.key === 'review-final') return `/seeds/runs/${props.runId}/review-final`
  if (step.key === 'export') return `/seeds/runs/${props.runId}/export`
  return null
}
</script>
