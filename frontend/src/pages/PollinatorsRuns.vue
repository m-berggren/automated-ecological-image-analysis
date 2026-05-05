<template>
  <PageHeader title="Runs" subtitle="Inference runs over uploaded camera-trap folders" />

  <div class="flex-1 p-8 max-w-5xl mx-auto w-full space-y-4">
    <div class="flex items-center justify-between">
      <p class="text-sm text-muted-foreground">
        {{ runs.length }} {{ runs.length === 1 ? 'run' : 'runs' }}
      </p>
      <RouterLink
        to="/pollinators/upload"
        class="px-3 py-1.5 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90"
      >
        New run
      </RouterLink>
    </div>

    <div v-if="loading" class="text-sm text-muted-foreground">Loading…</div>
    <div v-else-if="error" class="text-sm text-red-600">{{ error }}</div>

    <div
      v-else-if="!runs.length"
      class="rounded-xl border border-dashed border-border bg-surface p-10 text-center text-sm text-muted-foreground"
    >
      No runs yet. Start one from the Upload page.
    </div>

    <ul v-else class="rounded-xl border border-border bg-surface divide-y divide-border">
      <li v-for="run in runs" :key="run.id" class="flex items-center gap-4 px-5 py-3 text-sm">
        <div class="flex-1 min-w-0">
          <div class="font-medium truncate">{{ run.name || `Run #${run.id}` }}</div>
          <div class="text-xs text-muted-foreground">
            {{ run.image_count }} images · {{ run.detection_count }} detections · created
            {{ formatDate(run.created_at) }}
          </div>
        </div>
        <span class="text-xs px-2 py-0.5 rounded-full" :class="statusClass(run.status)">
          {{ run.status }}
        </span>
        <RouterLink
          :to="`/pollinators/runs/${run.id}/detect`"
          class="text-xs px-2 py-1 rounded border border-border hover:bg-muted"
        >
          Open
        </RouterLink>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import { api } from '@/api'

interface Run {
  id: number
  name: string
  status: string
  image_count: number
  detection_count: number
  created_at: string
}

const runs = ref<Run[]>([])
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    const res = await api('/api/analysis/runs/?module=pollinators')
    if (!res.ok) {
      error.value = (await res.text()) || `HTTP ${res.status}`
      return
    }
    runs.value = await res.json()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
})

function formatDate(iso: string) {
  return new Date(iso).toLocaleString()
}

function statusClass(s: string) {
  switch (s) {
    case 'completed':
      return 'bg-green-100 text-green-700'
    case 'running':
      return 'bg-blue-100 text-blue-700'
    case 'failed':
      return 'bg-red-100 text-red-700'
    default:
      return 'bg-muted text-muted-foreground'
  }
}
</script>
