<template>
  <PageHeader title="Seeds" subtitle="Detection, counting, and review of microscope seed images" />
  <div class="flex-1 p-8">
    <div
      class="rounded-xl border border-dashed border-border bg-surface p-12 text-center text-muted-foreground"
    >
      Seed counting workflow lives here. Upload, inference, review queue with volume-gradient
      filter.
    </div>
  </div>
</template>

<script setup lang="ts">
import PageHeader from '@/components/PageHeader.vue'
</script>
