<template>
  <PageHeader title="Export" subtitle="Download CSV of accepted detections" />
  <SeedsStepper v-if="runId" current="export" :run-id="runId" />
  <div class="flex-1 p-8">
    <div
      class="rounded-xl border border-dashed border-border bg-surface p-12 text-center text-muted-foreground max-w-3xl mx-auto"
    >
      TODO: CSV export.
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import SeedsStepper from '@/components/SeedsStepper.vue'

const route = useRoute()
const runId = computed(() => (route.params.id ? String(route.params.id) : null))
</script>
