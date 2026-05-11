<template>
  <PageHeader title="Export" subtitle="Download results from this seed detection run" />
  <SeedsStepper v-if="runId" current="export" :run-id="runId" />

  <div class="flex-1 p-8 max-w-3xl mx-auto w-full space-y-4">
    <div v-if="loading" class="text-sm text-muted-foreground">Loading…</div>
    <div v-else-if="loadError" class="text-sm text-red-600">{{ loadError }}</div>

    <template v-else-if="run">

      <!-- Run summary -->
      <section class="rounded-xl border border-border bg-surface p-5 space-y-1">
        <h2 class="text-sm font-semibold">{{ run.name || `Run #${run.id}` }}</h2>
        <p class="text-xs text-muted-foreground">
          {{ run.detection_count.toLocaleString() }} seeds detected ·
          {{ run.image_count.toLocaleString() }} images ·
          completed {{ formatRelative(run.completed_at) }}
        </p>
      </section>

      <!-- Export options -->
      <section class="rounded-xl border border-border bg-surface p-5 space-y-4">
        <h2 class="text-sm font-semibold">Export options</h2>

        <!-- Format -->
        <div class="space-y-2">
          <label class="text-xs text-muted-foreground">Format</label>
          <div class="flex gap-3">
            <button
              v-for="fmt in formats"
              :key="fmt.id"
              @click="selectedFormat = fmt.id"
              :class="[
                'flex flex-col items-start px-4 py-3 rounded-lg border-2 text-left transition-all flex-1',
                selectedFormat === fmt.id
                  ? 'border-primary bg-primary/5'
                  : 'border-border bg-background hover:border-primary/40'
              ]"
            >
              <span class="text-sm font-semibold">{{ fmt.label }}</span>
              <span class="text-xs text-muted-foreground">{{ fmt.desc }}</span>
            </button>
          </div>
        </div>

        <!-- Filter -->
        <div class="space-y-2">
          <label class="text-xs text-muted-foreground">Include detections</label>
          <div class="flex gap-3">
            <button
              v-for="opt in filterOptions"
              :key="opt.id"
              @click="selectedFilter = opt.id"
              :class="[
                'flex flex-col items-start px-4 py-3 rounded-lg border-2 text-left transition-all flex-1',
                selectedFilter === opt.id
                  ? 'border-primary bg-primary/5'
                  : 'border-border bg-background hover:border-primary/40'
              ]"
            >
              <span class="text-sm font-semibold">{{ opt.label }}</span>
              <span class="text-xs text-muted-foreground">{{ opt.desc }}</span>
            </button>
          </div>
        </div>

        <!-- Columns (CSV only) -->
        <div v-if="selectedFormat === 'csv'" class="space-y-2">
          <label class="text-xs text-muted-foreground">Columns to include</label>
          <div class="flex flex-wrap gap-2">
            <label
              v-for="col in csvColumns"
              :key="col.id"
              class="flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg border border-border bg-background cursor-pointer hover:border-primary/40"
            >
              <input type="checkbox" v-model="col.enabled" />
              {{ col.label }}
            </label>
          </div>
        </div>
      </section>

      <!-- Preview -->
      <section class="rounded-xl border border-border bg-surface p-5 space-y-3">
        <div class="flex items-center justify-between">
          <h2 class="text-sm font-semibold">Preview</h2>
          <span class="text-xs text-muted-foreground">first 5 rows</span>
        </div>
        <div class="overflow-x-auto rounded-lg border border-border">
          <table class="text-xs w-full">
            <thead class="bg-muted/30">
              <tr>
                <th
                  v-for="col in enabledColumns"
                  :key="col.id"
                  class="text-left font-medium px-3 py-2 text-muted-foreground"
                >
                  {{ col.label }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in previewRows" :key="i" class="border-t border-border">
                <td
                  v-for="col in enabledColumns"
                  :key="col.id"
                  class="px-3 py-2 font-mono"
                >
                  {{ row[col.id] ?? '—' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Download -->
      <div class="flex items-center justify-between">
        <p class="text-xs text-muted-foreground">
          ~{{ estimatedRows.toLocaleString() }} rows in export
        </p>
        <button
          @click="onDownload"
          :disabled="downloading"
          class="px-4 py-2 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <span v-if="!downloading">Download {{ selectedFormat.toUpperCase() }}</span>
          <span v-else>Preparing…</span>
        </button>
      </div>

      <p v-if="downloadError" class="text-sm text-red-600">{{ downloadError }}</p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import SeedsStepper from '@/components/SeedsStepper.vue'
import { api } from '@/api'

interface Run {
  id: number
  name: string
  detection_count: number
  image_count: number
  completed_at: string | null
}

type Format = 'csv' | 'json'
type FilterOption = 'confirmed' | 'all' | 'unrejected'

const route = useRoute()
const runId = computed(() => route.params.id ? String(route.params.id) : null)
const loading = ref(true)
const loadError = ref('')
const downloading = ref(false)
const downloadError = ref('')
const run = ref<Run | null>(null)
const selectedFormat = ref<Format>('csv')
const selectedFilter = ref<FilterOption>('confirmed')

const formats = [
  { id: 'csv' as Format, label: 'CSV', desc: 'Spreadsheet-compatible, one row per seed' },
  { id: 'json' as Format, label: 'JSON', desc: 'Structured, one object per seed' },
]

const filterOptions = [
  { id: 'confirmed' as FilterOption, label: 'Confirmed only', desc: 'Seeds marked as confirmed in review' },
  { id: 'all' as FilterOption, label: 'All detections', desc: 'Including rejected' },
]

const csvColumns = reactive([
  { id: 'image_id',         label: 'Image ID',        enabled: true },
  { id: 'image_filename',   label: 'Image filename',  enabled: true },
  { id: 'seed_count',       label: 'Seed count',      enabled: true },
  { id: 'confidence',       label: 'Confidence',      enabled: true },
  { id: 'reviewer_status',  label: 'Review status',   enabled: true },
])

const enabledColumns = computed(() => csvColumns.filter((c) => c.enabled))

const previewRows = ref<Record<string, string | number | null>[]>([
  { image_id: 'PEH_001', image_filename: 'PEH_001.jpg', seed_count: 8,  confidence: '0.94', reviewer_status: 'confirmed' },
  { image_id: 'PEH_002', image_filename: 'PEH_002.jpg', seed_count: 6,  confidence: '0.91', reviewer_status: 'confirmed' },
  { image_id: 'PEH_003', image_filename: 'PEH_003.jpg', seed_count: 11, confidence: '0.88', reviewer_status: 'confirmed' },
  { image_id: 'PEH_004', image_filename: 'PEH_004.jpg', seed_count: 3,  confidence: '0.71', reviewer_status: 'confirmed' },
  { image_id: 'PEH_005', image_filename: 'PEH_005.jpg', seed_count: 0,  confidence: '0.58', reviewer_status: 'rejected' },
])

const estimatedRows = computed(() => {
  if (!run.value) return 0
  switch (selectedFilter.value) {
    case 'confirmed':  return Math.round(run.value.detection_count * 0.7)
    case 'unrejected': return Math.round(run.value.detection_count * 0.9)
    case 'all':        return run.value.detection_count
  }
})

const previewMode = computed<string | null>(() => {
  const value = route.query.preview
  return typeof value === 'string' ? value : null
})

onMounted(async () => {
  if (previewMode.value) {
    run.value = {
      id: 1,
      name: 'PEH batch May 2026',
      detection_count: 312,
      image_count: 40,
      completed_at: new Date(Date.now() - 3600_000).toISOString(),
    }
    loading.value = false
    return
  }
  if (!runId.value) { loading.value = false; return }
  try {
    const res = await api(`/api/analysis/runs/${runId.value}/`)
    if (!res.ok) { loadError.value = `HTTP ${res.status}`; return }
    run.value = await res.json()
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
})

async function onDownload() {
  if (!runId.value) return
  downloadError.value = ''
  downloading.value = true
  try {
    const params = new URLSearchParams({
      format: selectedFormat.value,
      filter: selectedFilter.value,
      columns: enabledColumns.value.map((c) => c.id).join(','),
    })
    const res = await api(`/api/analysis/runs/${runId.value}/export/?${params}`)
    if (!res.ok) { downloadError.value = `Export failed: HTTP ${res.status}`; return }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `run-${runId.value}-seeds.${selectedFormat.value}`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    downloadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    downloading.value = false
  }
}

function formatRelative(iso: string | null): string {
  if (!iso) return '—'
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
  return `${Math.round(diff / 86400)}d ago`
}
</script>