<template>
  <PageHeader title="Models" subtitle="Trained model versions for the seeds module" />
  <div class="flex-1 p-8">
    <div
      v-if="!auth.user?.is_staff"
      class="rounded-xl border border-border bg-surface p-8 max-w-md mx-auto text-center"
    >
      <p class="text-sm text-muted-foreground">This page is restricted to administrators.</p>
    </div>
    <div
      v-else
      class="rounded-xl border border-dashed border-border bg-surface p-12 text-center text-muted-foreground max-w-3xl mx-auto"
    >
      TODO: Model version list, set-active toggle, and "Retrain on flagged" trigger.
    </div>
  </div>
</template>

<script setup lang="ts">
import PageHeader from '@/components/PageHeader.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
</script>
