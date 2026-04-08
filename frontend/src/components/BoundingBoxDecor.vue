<!-- Author: Claudia Sevilla -->
<!-- Box animations ported from Lovable's React prototype -->

<template>
  <div
    :class="cn('absolute border-2 rounded-[2px] animate-bbox-pulse', colorMap[color], className)"
    :style="style"
  >
    <span v-if="label"
        :class="cn('absolute -top-6 left-0 px-2 py-0.5 text-xs font-display font-semibold rounded-t-sm text-background', bgMap[color])"
    >
      {{ label }} {{ confidence ? `${confidence}%` : '' }}
    </span>

    <!-- Corner markers -->
    <div :class="cn('absolute -top-0.5 -left-0.5 w-3 h-3 border-t-2 border-l-2', colorMap[color])" />
    <div :class="cn('absolute -top-0.5 -right-0.5 w-3 h-3 border-t-2 border-r-2', colorMap[color])" />
    <div :class="cn('absolute -bottom-0.5 -left-0.5 w-3 h-3 border-b-2 border-l-2', colorMap[color])" />
    <div :class="cn('absolute -bottom-0.5 -right-0.5 w-3 h-3 border-b-2 border-r-2', colorMap[color])" />
  </div>
</template>

<script setup lang="ts">
import { cn } from '@/lib/utils'

interface Props {
  color?: 'pink' | 'lime' | 'cyan' | 'orange' | 'purple' | 'yellow'
  className?: string
  label?: string
  confidence?: number
  style?: Record<string, string>
}

withDefaults(defineProps<Props>(), {
  color: 'pink',
})

const colorMap = {
  pink: 'border-bbox-pink text-bbox-pink',
  lime: 'border-bbox-lime text-bbox-lime',
  cyan: 'border-bbox-cyan text-bbox-cyan',
  orange: 'border-bbox-orange text-bbox-orange',
  purple: 'border-bbox-purple text-bbox-purple',
  yellow: 'border-bbox-yellow text-bbox-yellow',
}

const bgMap = {
  pink: 'bg-bbox-pink',
  lime: 'bg-bbox-lime',
  cyan: 'bg-bbox-cyan',
  orange: 'bg-bbox-orange',
  purple: 'bg-bbox-purple',
  yellow: 'bg-bbox-yellow',
}
</script>