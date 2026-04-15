<template>
  <button
    @click="theme.cycle()"
    class="p-2 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
    :title="`Theme: ${label}. Click to cycle.`"
    :aria-label="`Current theme: ${label}`"
  >
    <component :is="icon" class="w-4 h-4" />
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Sun, Moon, Leaf } from 'lucide-vue-next'
import { useThemeStore } from '@/stores/theme'

const theme = useThemeStore()

const icon = computed(() => {
  switch (theme.current) {
    case 'dark': return Moon
    case 'green': return Leaf
    default: return Sun
  }
})

const label = computed(() => {
  switch (theme.current) {
    case 'dark': return 'Dark'
    case 'green': return 'Green'
    default: return 'Light'
  }
})
</script>
