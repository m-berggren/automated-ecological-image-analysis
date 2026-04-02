<!-- Author: Claudia Sevilla -->

<template>
  <nav class="relative z-10 flex items-center justify-between px-6 md:px-12 py-5">
    <div class="flex items-center gap-2 mt-2">
      <Sprout class="w-7 h-7 text-primary" />
      <span class="font-display font-bold text-4xl text-foreground tracking-tight">
        ecosia
      </span>
    </div>
    <div class="flex items-center gap-2 text-m text-muted-foreground mt-2">
      <Sparkles class="w-4 h-4 text-accent" />
      <span class="font-body">ML-powered ecology</span>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { Sprout, Sparkles } from 'lucide-vue-next'
</script>