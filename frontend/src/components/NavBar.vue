<!-- Author: Claudia Sevilla -->

<template>
  <nav class="relative z-10 flex items-center justify-between px-6 md:px-12 py-5">
    <RouterLink to="/" class="flex items-center gap-2 mt-2">
      <Sprout class="w-5 h-5 md:w-7 md:h-7 text-primary" />
      <span class="font-display font-bold text-2xl md:text-4xl text-foreground tracking-tight">
        ecosia
      </span>
    </RouterLink>
    <div class="flex items-center gap-2 mt-2">
      <RouterLink
        to="/signin"
        class="px-4 py-1.5 rounded-lg text-sm font-semibold bg-secondary text-secondary-foreground hover:bg-secondary/70 transition-colors"
      >
        Log In
      </RouterLink>
      <RouterLink
        to="/signup"
        class="px-4 py-1.5 rounded-lg text-sm font-semibold bg-primary text-primary-foreground hover:bg-primary/80 transition-colors"
      >
        Sign Up
      </RouterLink>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { Sprout } from 'lucide-vue-next'
</script>
