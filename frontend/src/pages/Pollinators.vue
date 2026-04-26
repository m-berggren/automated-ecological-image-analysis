<template>
  <PageHeader
    title="Pollinators"
    subtitle="Detection and classification from Arctic field images"
  />
  <div class="flex-1 p-8">
    <div
      class="rounded-xl border border-dashed border-border bg-surface p-12 text-center text-muted-foreground"
    >
      Pollinator workflow. Candidate extraction, possibly InsectNet classification, four-class
      review (bumblebee / fly / butterfly / other).
    </div>
  </div>
</template>

<script setup lang="ts">
import PageHeader from '@/components/PageHeader.vue'
</script>
