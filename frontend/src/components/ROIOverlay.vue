<template>
  <template v-if="bbox">
    <rect
      :x="bbox[0]"
      :y="bbox[1]"
      :width="bbox[2]"
      :height="bbox[3]"
      fill="none"
      :stroke="color"
      :stroke-width="strokeWidth"
      :stroke-dasharray="`${strokeWidth * 4} ${strokeWidth * 2.5}`"
      :vector-effect="nonScalingStroke ? 'non-scaling-stroke' : undefined"
    />
    <text
      :x="bbox[0]"
      :y="labelY"
      :font-size="fontSize"
      :fill="color"
      font-weight="700"
      paint-order="stroke"
      stroke="white"
      :stroke-width="fontSize * 0.2"
      >{{ label }}</text
    >
  </template>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    bbox: [number, number, number, number] | null
    imageW: number
    imageH: number
    label?: string
    color?: string
    nonScalingStroke?: boolean
  }>(),
  {
    label: 'ROI section',
    color: '#3b82f6',
    nonScalingStroke: false,
  },
)

const longest = computed(() => Math.max(props.imageW, props.imageH))
const strokeWidth = computed(() => Math.max(1.5, longest.value * 0.0022))
const fontSize = computed(() => Math.max(12, longest.value * 0.018))
const labelY = computed(() =>
  props.bbox ? Math.max(fontSize.value, props.bbox[1] - fontSize.value * 0.35) : 0,
)
</script>
