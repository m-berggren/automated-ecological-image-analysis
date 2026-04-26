<template>
  <header
    class="border-b border-border px-8 h-16 flex items-center justify-between shrink-0 bg-surface"
  >
    <div>
      <h1 class="font-display font-semibold text-lg leading-none">
        {{ title }}
      </h1>
      <p v-if="subtitle" class="text-xs text-muted-foreground mt-1">
        {{ subtitle }}
      </p>
    </div>
    <div class="flex items-center gap-2">
      <slot name="actions" />
      <ThemeToggle />
    </div>
  </header>
</template>

<script setup lang="ts">
import ThemeToggle from '@/components/ThemeToggle.vue'

defineProps<{
  title: string
  subtitle?: string
}>()
</script>
