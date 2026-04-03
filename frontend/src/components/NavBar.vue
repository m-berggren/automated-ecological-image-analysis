<!-- Author: Claudia Sevilla -->

<template>
  <nav class="relative z-10 flex items-center justify-between px-6 md:px-12 py-5">
    <div class="flex items-center gap-2 mt-2">
      <Sprout class="w-5 h-5 md:w-7 md:h-7 text-primary" />
      <span class="font-display font-bold text-2xl md:text-4xl text-foreground tracking-tight">
        ecosia
      </span>
    </div>
    <div class="flex items-center gap-2 text-sm text-muted-foreground mt-2">
      <Sparkles class="w-3 h-3 md:w-4 md:h-4 text-accent" />
      <span class="font-body hidden sm:inline">ML-powered ecology</span>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { Sprout, Sparkles } from 'lucide-vue-next'
</script>