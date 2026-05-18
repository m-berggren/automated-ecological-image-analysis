<template>
  <span ref="root" class="relative inline-block leading-none">
    <button
      type="button"
      aria-label="More info"
      class="inline-flex items-center text-muted-foreground hover:text-foreground focus:text-foreground focus:outline-none"
      @click.stop="open = !open"
    >
      <Info class="w-3.5 h-3.5" />
    </button>
    <Transition name="info-pop">
      <div
        v-if="open"
        class="absolute left-0 top-5 z-20 w-64 rounded-md border border-border bg-card p-2.5 text-xs leading-relaxed text-foreground shadow-md whitespace-normal"
      >
        <slot />
      </div>
    </Transition>
  </span>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { Info } from 'lucide-vue-next'

const open = ref(false)
const root = ref<HTMLElement | null>(null)

function onDocClick(e: MouseEvent) {
  if (!open.value) return
  if (root.value && !root.value.contains(e.target as Node)) {
    open.value = false
  }
}

onMounted(() => document.addEventListener('mousedown', onDocClick))
onUnmounted(() => document.removeEventListener('mousedown', onDocClick))
</script>

<style scoped>
.info-pop-enter-active,
.info-pop-leave-active {
  transition:
    opacity 120ms ease,
    transform 120ms ease;
}
.info-pop-enter-from,
.info-pop-leave-to {
  opacity: 0;
  transform: translateY(-2px);
}
</style>
