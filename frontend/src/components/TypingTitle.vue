<!-- Author: Claudia Sevilla -->
<!-- Typing animation ported from Lovable's React prototype -->

<template>
  <h1 className="font-display font-bold text-4xl md:text-5xl lg:text-6xl text-foreground leading-tight">
    {{ displayed }}<span class="text-accent">.</span>
    <span
      v-if="showCursor"
      class="inline-block w-[3px] h-[0.85em] bg-accent ml-1 align-middle"
      style="animation: typing-cursor 0.6s step-end infinite"
    />
  </h1>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

const FULL_TEXT = "Nature, decoded"
const displayed = ref("")
const showCursor = ref(true)

onMounted(() => {
  let i = 0
  const interval = setInterval(() => {
    i++
    displayed.value = FULL_TEXT.slice(0, i)
    if (i >= FULL_TEXT.length) {
      clearInterval(interval)
      setTimeout(() => showCursor.value = false, 2500)
    }
  }, 70)
})
</script>