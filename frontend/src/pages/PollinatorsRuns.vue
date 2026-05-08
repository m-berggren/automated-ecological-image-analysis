<template>
  <PageHeader title="Runs" subtitle="Inference runs over uploaded camera-trap folders" />

  <div class="flex-1 flex flex-col min-h-0">
    <!-- Filter / counts bar -->
    <div class="px-8 py-3 border-b border-border bg-surface flex items-center gap-3 flex-wrap">
      <div class="flex gap-1 text-xs">
        <button
          v-for="opt in FILTER_OPTIONS"
          :key="opt.value"
          class="px-3 py-1.5 rounded-md font-medium transition-colors"
          :class="
            statusFilter === opt.value
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:bg-muted'
          "
          @click="statusFilter = opt.value"
        >
          {{ opt.label }}
          <span v-if="opt.count !== undefined" class="opacity-70">· {{ opt.count }}</span>
        </button>
      </div>
      <span class="text-xs text-muted-foreground ml-auto">
        {{ filteredRuns.length }} {{ filteredRuns.length === 1 ? 'run' : 'runs' }} across
        {{ groupedByUpload.length }}
        {{ groupedByUpload.length === 1 ? 'upload' : 'uploads' }}
      </span>
      <RouterLink
        to="/pollinators/upload"
        class="px-3 py-1.5 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90"
      >
        New run
      </RouterLink>
    </div>

    <!-- Body -->
    <div class="flex-1 overflow-auto">
      <div v-if="loading" class="p-8 text-sm text-muted-foreground">Loading…</div>
      <div v-else-if="loadError" class="p-8 text-sm text-red-600">{{ loadError }}</div>
      <div v-else-if="!filteredRuns.length" class="p-12 text-center text-sm text-muted-foreground">
        No runs match this filter. Start one from the
        <RouterLink to="/pollinators/upload" class="text-primary hover:underline">
          Upload page</RouterLink
        >.
      </div>

      <div v-else class="p-6 space-y-4">
        <section
          v-for="group in groupedByUpload"
          :key="group.upload?.id ?? 'orphan'"
          class="rounded-xl border border-border bg-card overflow-hidden shadow-md"
        >
          <header
            class="px-5 py-4 bg-primary/[0.22] border-b border-border flex items-baseline gap-3"
          >
            <h2 class="font-bold text-lg tracking-tight">
              {{
                group.upload?.name ||
                (group.upload ? `Upload #${group.upload.id}` : 'Unattached runs')
              }}
            </h2>
            <span v-if="group.upload" class="text-xs text-muted-foreground">
              {{ group.upload.image_count.toLocaleString() }} images
            </span>
            <span class="text-xs text-muted-foreground ml-auto">
              {{ group.runs.length }} {{ group.runs.length === 1 ? 'run' : 'runs' }}
            </span>
          </header>

          <ul class="divide-y divide-border">
            <li
              v-for="run in group.runs"
              :key="run.id"
              class="px-5 py-3 hover:bg-muted/30 transition-colors"
            >
              <div class="flex items-center gap-4">
                <div class="flex-1 min-w-0">
                  <div class="flex items-baseline gap-2">
                    <span class="font-medium text-sm truncate">
                      {{ run.name || `Run #${run.id}` }}
                    </span>
                    <span class="text-xs text-muted-foreground shrink-0">
                      created {{ formatDate(run.created_at) }}
                    </span>
                  </div>
                  <div class="text-xs text-muted-foreground mt-0.5">
                    <template
                      v-if="run.status === 'completed' && run.completed_at && run.started_at"
                    >
                      took {{ humanDuration(durationSeconds(run)) }} ·
                    </template>
                    <template v-else-if="run.status === 'failed'">
                      failed
                      <span v-if="run.error_message"> — {{ run.error_message }}</span> ·
                    </template>
                    <span v-if="run.detection_count > 0">
                      {{ run.detection_count.toLocaleString() }} detections
                    </span>
                    <span v-else-if="run.status === 'completed'">no detections</span>
                  </div>

                  <!-- Class breakdown for runs with detections -->
                  <div
                    v-if="hasClassBreakdown(run)"
                    class="text-xs text-muted-foreground mt-1 flex items-center gap-3 flex-wrap"
                  >
                    <span
                      v-for="row in classRows(run)"
                      :key="row.label"
                      class="inline-flex items-center gap-1"
                    >
                      <span
                        class="w-1.5 h-1.5 rounded-full"
                        :style="{ backgroundColor: row.color }"
                      />
                      {{ row.count.toLocaleString() }} {{ row.label.toLowerCase() }}
                    </span>
                  </div>

                  <!-- Inline progress for running -->
                  <div v-if="run.status === 'running'" class="mt-2 max-w-md">
                    <div class="h-1.5 rounded-full bg-muted overflow-hidden">
                      <div
                        class="h-full bg-blue-500 transition-all"
                        :style="{ width: progressPercent(run) + '%' }"
                      />
                    </div>
                    <div class="text-xs text-muted-foreground mt-1 font-mono">
                      {{ run.processed_image_count?.toLocaleString() ?? 0 }} /
                      {{ run.image_count.toLocaleString() }}
                      ({{ progressPercent(run) }}%)
                    </div>
                  </div>
                </div>

                <span
                  class="text-xs px-2 py-0.5 rounded-full shrink-0"
                  :class="statusClass(run.status)"
                >
                  {{ run.status }}
                </span>
                <RouterLink
                  :to="
                    run.status === 'completed'
                      ? `/pollinators/runs/${run.id}/review`
                      : `/pollinators/runs/${run.id}/detect`
                  "
                  class="text-xs px-2 py-1 rounded border border-border hover:bg-muted shrink-0"
                >
                  {{ run.status === 'completed' ? 'Review' : 'Open' }}
                </RouterLink>
              </div>
            </li>
          </ul>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import { api } from '@/api'

interface Upload {
  id: number
  name: string
  image_count: number
  created_at: string
}

interface Run {
  id: number
  name: string
  upload: number | null
  status: 'pending' | 'running' | 'completed' | 'failed'
  image_count: number
  processed_image_count?: number
  detection_count: number
  failed_image_count?: number
  detections_by_class?: Record<string, number>
  created_at: string
  started_at: string | null
  completed_at: string | null
  error_message?: string
}

interface UploadMock {
  id: number
  name: string
  image_count: number
  created_at_offset_seconds: number
}
interface RunMock extends Omit<Run, 'created_at' | 'started_at' | 'completed_at'> {
  created_at_offset_seconds: number
  started_at_offset_seconds: number | null
  completed_at_offset_seconds: number | null
}
interface ListBundle {
  uploads: Upload[]
  runs: Run[]
}

const CLASS_COLORS: Record<string, string> = {
  fly: '#6b9bd2',
  bumblebee: '#e6a946',
  butterfly: '#c87bba',
  other: '#9aa3ab',
}

const FILTER_OPTIONS_BASE: Array<{ value: StatusFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'active', label: 'Active' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
]

type StatusFilter = 'all' | 'active' | 'completed' | 'failed'

const route = useRoute()
const loading = ref(true)
const loadError = ref('')
const uploads = ref<Upload[]>([])
const runs = ref<Run[]>([])
const statusFilter = ref<StatusFilter>('all')

const previewMode = computed<string | null>(() => {
  const value = route.query.preview
  return typeof value === 'string' ? value : null
})

onMounted(async () => {
  if (previewMode.value) {
    const bundle = await loadPreview(previewMode.value)
    if (bundle) {
      uploads.value = bundle.uploads
      runs.value = bundle.runs
      loading.value = false
      return
    }
  }
  await loadFromApi()
})

async function loadPreview(_mode: string): Promise<ListBundle | null> {
  if (!import.meta.env.DEV) return null
  const { default: mocks } = await import('@/mocks/pollinator-runs-list.json')
  const raw = (mocks as Record<string, { uploads: UploadMock[]; runs: RunMock[] } | undefined>)
    .default
  if (!raw) return null
  return resolveBundle(raw)
}

function resolveBundle(raw: { uploads: UploadMock[]; runs: RunMock[] }): ListBundle {
  const now = Date.now()
  const offsetIso = (offset: number | null): string | null =>
    offset == null ? null : new Date(now + offset * 1000).toISOString()
  return {
    uploads: raw.uploads.map((u) => ({
      id: u.id,
      name: u.name,
      image_count: u.image_count,
      created_at: offsetIso(u.created_at_offset_seconds) ?? new Date(now).toISOString(),
    })),
    runs: raw.runs.map((r) => ({
      ...r,
      created_at: offsetIso(r.created_at_offset_seconds) ?? new Date(now).toISOString(),
      started_at: offsetIso(r.started_at_offset_seconds),
      completed_at: offsetIso(r.completed_at_offset_seconds),
    })),
  }
}

async function loadFromApi() {
  try {
    const [runsRes, uploadsRes] = await Promise.all([
      api('/api/analysis/runs/?module=pollinators'),
      api('/api/datasets/uploads/?module=pollinators'),
    ])
    if (!runsRes.ok) {
      loadError.value = `Runs: HTTP ${runsRes.status}`
      return
    }
    if (!uploadsRes.ok) {
      loadError.value = `Uploads: HTTP ${uploadsRes.status}`
      return
    }
    runs.value = await runsRes.json()
    uploads.value = await uploadsRes.json()
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

const filteredRuns = computed(() => {
  switch (statusFilter.value) {
    case 'active':
      return runs.value.filter((r) => r.status === 'pending' || r.status === 'running')
    case 'completed':
      return runs.value.filter((r) => r.status === 'completed')
    case 'failed':
      return runs.value.filter((r) => r.status === 'failed')
    default:
      return runs.value
  }
})

const FILTER_OPTIONS = computed(() =>
  FILTER_OPTIONS_BASE.map((opt) => ({
    ...opt,
    count: countFor(opt.value),
  })),
)

function countFor(status: StatusFilter): number {
  switch (status) {
    case 'all':
      return runs.value.length
    case 'active':
      return runs.value.filter((r) => r.status === 'pending' || r.status === 'running').length
    case 'completed':
      return runs.value.filter((r) => r.status === 'completed').length
    case 'failed':
      return runs.value.filter((r) => r.status === 'failed').length
  }
}

const uploadsById = computed(() => {
  const map = new Map<number, Upload>()
  for (const u of uploads.value) map.set(u.id, u)
  return map
})

const groupedByUpload = computed(() => {
  const groups = new Map<number | null, Run[]>()
  for (const r of filteredRuns.value) {
    const key = r.upload ?? null
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(r)
  }
  const out = Array.from(groups.entries()).map(([uploadId, groupRuns]) => ({
    upload: uploadId == null ? null : (uploadsById.value.get(uploadId) ?? null),
    runs: [...groupRuns].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    ),
  }))
  out.sort((a, b) => {
    const aTime = a.runs[0] ? new Date(a.runs[0].created_at).getTime() : 0
    const bTime = b.runs[0] ? new Date(b.runs[0].created_at).getTime() : 0
    return bTime - aTime
  })
  return out
})

function progressPercent(run: Run): number {
  if (!run.image_count) return 0
  const processed = run.processed_image_count ?? 0
  return Math.min(100, Math.round((processed / run.image_count) * 100))
}

function durationSeconds(run: Run): number {
  if (!run.started_at || !run.completed_at) return 0
  return Math.max(
    0,
    (new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()) / 1000,
  )
}

function humanDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`
  const hours = Math.floor(seconds / 3600)
  const mins = Math.round((seconds % 3600) / 60)
  return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  const now = Date.now()
  const diffSec = (now - d.getTime()) / 1000
  if (diffSec < 60) return 'just now'
  if (diffSec < 3600) return `${Math.round(diffSec / 60)}m ago`
  if (diffSec < 86400) return `${Math.round(diffSec / 3600)}h ago`
  if (diffSec < 86400 * 7) return `${Math.round(diffSec / 86400)}d ago`
  return d.toLocaleDateString()
}

function hasClassBreakdown(run: Run): boolean {
  return !!run.detections_by_class && Object.keys(run.detections_by_class).length > 0
}

function classRows(run: Run) {
  if (!run.detections_by_class) return []
  return Object.entries(run.detections_by_class)
    .sort((a, b) => b[1] - a[1])
    .map(([cls, count]) => ({
      label: cls[0].toUpperCase() + cls.slice(1),
      count,
      color: CLASS_COLORS[cls] ?? '#9aa3ab',
    }))
}

function statusClass(s: string): string {
  switch (s) {
    case 'completed':
      return 'bg-green-200 text-green-800'
    case 'running':
      return 'bg-blue-200 text-blue-800'
    case 'failed':
      return 'bg-red-200 text-red-800'
    case 'pending':
      return 'bg-amber-200 text-amber-800'
    default:
      return 'bg-muted text-muted-foreground'
  }
}
</script>
