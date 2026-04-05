<!-- Author: Claudia Sevilla -->
<!-- Animation ported from Lovable's React prototype -->

<template>
  <div class="pointer-events-none inset-0 overflow-hidden z-0 hidden lg:block">
    <!-- Bottom-left -->
    <div
      class="absolute bottom-24 left-16 transition-transform duration-300 ease-out"
      :style="{ transform: `scale(${leftScale})`, transformOrigin: 'bottom left' }"
    >
      <BoundingBoxDecor color="purple" label="Pollinator" class="w-16 h-14 relative opacity-50" />
    </div>
    <!-- Right middle -->
    <div
      class="absolute top-[42%] right-16 transition-transform duration-300 ease-out"
      :style="{ transform: `scale(${rightScale})`, transformOrigin: 'center right' }"
    >
      <BoundingBoxDecor color="yellow" label="Flower" class="w-14 h-12 relative opacity-50" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import BoundingBoxDecor from '@/components/BoundingBoxDecor.vue'

const mouse = ref({ x: 0, y: 0 })

const handleMouseMove = (e: MouseEvent) => {
  mouse.value = { x: e.clientX, y: e.clientY }
}

onMounted(() => window.addEventListener('mousemove', handleMouseMove))
onUnmounted(() => window.removeEventListener('mousemove', handleMouseMove))

const getScale = (boxX: number, boxY: number) => {
  const dx = mouse.value.x - boxX
  const dy = mouse.value.y - boxY
  const dist = Math.sqrt(dx * dx + dy * dy)
  const maxDist = 400
  const minScale = 1
  const maxScale = 2.2
  if (dist > maxDist) return minScale
  return minScale + (maxScale - minScale) * (1 - dist / maxDist)
}

const leftScale = computed(() => getScale(80, window.innerHeight - 120))
const rightScale = computed(() => getScale(window.innerWidth - 80, window.innerHeight * 0.45))
</script>