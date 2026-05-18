<template>
  <PageHeader :title="headerTitle" :subtitle="headerSubtitle" />
  <PollinatorsStepper current="detect" :runId="run?.id" />

  <div class="flex-1 min-h-0 overflow-y-auto p-8 max-w-4xl mx-auto w-full space-y-6">
    <div v-if="loading" class="text-sm text-muted-foreground">Loading…</div>
    <div v-else-if="loadError" class="text-sm text-red-600">{{ loadError }}</div>

    <template v-else-if="run">
      <!-- Status card -->
      <section class="rounded-xl border bg-surface p-5" :class="statusBorderClass">
        <div class="flex items-center gap-3 mb-3">
          <span
            class="text-xs font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full"
            :class="statusBadgeClass"
          >
            {{ statusLabel }}
          </span>
          <span class="text-xs text-muted-foreground">
            {{ timingLine }}
          </span>
        </div>

        <div v-if="run.status === 'failed'" class="text-sm text-red-700 mb-3">
          {{ run.error_message || 'Run failed before completion.' }}
        </div>

        <div v-else-if="run.status === 'pending'" class="text-sm text-muted-foreground mb-3">
          Waiting for a worker to pick up this run.
        </div>

        <div v-else>
          <div class="text-sm font-medium">
            {{ run.processed_image_count.toLocaleString() }} of
            {{ run.image_count.toLocaleString() }} images processed
            <span class="text-muted-foreground font-normal">({{ percent }}%)</span>
          </div>
          <div class="mt-2 h-2 rounded-full bg-muted overflow-hidden">
            <div class="h-full bg-primary transition-all" :style="{ width: percent + '%' }" />
          </div>
          <div class="mt-2 text-xs text-muted-foreground">
            <template v-if="run.status === 'completed'"> Completed in {{ elapsedHuman }} </template>
            <template v-else>
              {{ elapsedHuman }} elapsed
              <span v-if="etaHuman"> · ~{{ etaHuman }} remaining</span>
            </template>
          </div>
        </div>

        <div class="mt-4 flex gap-2">
          <button
            v-if="canCancel"
            class="text-sm px-3 py-1.5 rounded-md border border-border hover:bg-muted disabled:opacity-50"
            :disabled="cancelling"
            @click="onCancel"
          >
            {{ cancelling ? 'Cancelling…' : 'Cancel run' }}
          </button>
          <RouterLink
            v-if="canOpenReview"
            :to="`/pollinators/runs/${run.id}/review`"
            class="ml-auto text-sm px-3 py-1.5 rounded-md font-medium bg-primary text-primary-foreground hover:bg-primary/90"
          >
            Open review →
          </RouterLink>
          <button
            v-if="run.status === 'failed'"
            class="ml-auto text-sm px-3 py-1.5 rounded-md border border-border hover:bg-muted disabled:opacity-50"
            :disabled="rerunning || run.upload == null || !run.module"
            :title="
              run.upload == null || !run.module
                ? 'Original upload missing from this run record'
                : ''
            "
            @click="onRerun"
          >
            {{ rerunning ? 'Restarting…' : 'Re-run with same config' }}
          </button>
        </div>
      </section>

      <!-- Counts -->
      <section
        v-if="run.detection_count > 0"
        class="rounded-xl border border-border bg-surface p-5"
      >
        <h2 class="text-sm font-semibold mb-3">
          Detections so far · {{ run.detection_count.toLocaleString() }}
        </h2>
        <div class="grid grid-cols-2 gap-6">
          <div>
            <div class="text-xs text-muted-foreground mb-2">By class</div>
            <ul class="space-y-1 text-sm">
              <li v-for="row in classRows" :key="row.label" class="flex items-center gap-2">
                <span
                  class="w-2 h-2 rounded-full shrink-0"
                  :style="{ backgroundColor: row.color }"
                />
                <span class="flex-1">{{ row.label }}</span>
                <span class="font-medium">{{ row.count.toLocaleString() }}</span>
                <span class="text-xs text-muted-foreground w-10 text-right"
                  >{{ row.percent }}%</span
                >
              </li>
            </ul>
          </div>
          <div>
            <div class="text-xs text-muted-foreground mb-2">By source</div>
            <ul class="space-y-1 text-sm">
              <li v-for="row in sourceRows" :key="row.label" class="flex items-center gap-2">
                <span class="flex-1">{{ row.label }}</span>
                <span class="font-medium">{{ row.count.toLocaleString() }}</span>
              </li>
            </ul>
          </div>
        </div>
      </section>

      <!-- Activity log -->
      <section class="rounded-xl border border-border bg-surface">
        <header class="px-5 py-3 border-b border-border flex items-center justify-between">
          <h2 class="text-sm font-semibold">Recent activity</h2>
          <span v-if="run.failed_image_count > 0" class="text-xs text-red-600">
            ⚠ {{ run.failed_image_count }} images failed
          </span>
        </header>
        <ul class="max-h-72 overflow-auto divide-y divide-border text-xs">
          <li
            v-for="(entry, idx) in run.activity_log.slice().reverse()"
            :key="idx"
            class="px-5 py-2 flex gap-3 font-mono"
            :class="logLevelClass(entry.level)"
          >
            <span class="text-muted-foreground shrink-0 w-12">{{ formatTime(entry.time) }}</span>
            <span class="flex-1">{{ entry.message }}</span>
          </li>
        </ul>
      </section>

      <!-- Configuration disclosure -->
      <section class="rounded-xl border border-border bg-surface">
        <button
          class="w-full px-5 py-3 text-left text-sm font-medium flex items-center justify-between hover:bg-muted/30"
          @click="showConfig = !showConfig"
        >
          <span>Configuration used</span>
          <span class="text-muted-foreground text-xs">
            {{ showConfig ? '▾' : '▸' }} frozen at run start
          </span>
        </button>
        <pre
          v-if="showConfig"
          class="border-t border-border px-5 py-3 text-xs overflow-x-auto bg-background"
          >{{ JSON.stringify(run.config, null, 2) }}</pre
        >
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import PollinatorsStepper from '@/components/PollinatorsStepper.vue'
import { api } from '@/api'
import { confirm } from '@/lib/confirm'

type RunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
type PreviewMode = 'queued' | 'running' | 'completed' | 'failed'

interface ActivityEntry {
  time: string
  message: string
  level: 'info' | 'warn' | 'error'
}

interface RunDetail {
  id: number
  name: string
  status: RunStatus
  created_at: string
  started_at: string | null
  completed_at: string | null
  image_count: number
  processed_image_count: number
  detection_count: number
  failed_image_count: number
  detections_by_class: Record<string, number>
  detections_by_source: Record<string, number>
  activity_log: ActivityEntry[]
  config: Record<string, unknown>
  error_message?: string
  // Present on real-API runs; optional so the preview-mode mock loader
  // (which doesn't include them) still satisfies the type.
  module?: string
  upload?: number
  model_version?: number | null
}

interface RunDetailMock {
  id: number
  name: string
  status: RunStatus
  created_at_offset_seconds: number
  started_at_offset_seconds: number | null
  completed_at_offset_seconds: number | null
  image_count: number
  processed_image_count: number
  detection_count: number
  failed_image_count: number
  detections_by_class: Record<string, number>
  detections_by_source: Record<string, number>
  activity_log: Array<{ offset_seconds: number; message: string; level: ActivityEntry['level'] }>
  config: Record<string, unknown>
  error_message?: string
}

const CLASS_COLORS: Record<string, string> = {
  fly: '#6b9bd2',
  bumblebee: '#e6a946',
  butterfly: '#c87bba',
  other: '#9aa3ab',
}

const SOURCE_LABELS: Record<string, string> = {
  yolo: 'YOLO',
  preprocessing: 'Classical preprocessing',
  both: 'Both',
}

const route = useRoute()
const router = useRouter()
const run = ref<RunDetail | null>(null)
const rerunning = ref(false)
const loading = ref(true)
const loadError = ref('')
const showConfig = ref(false)

let pollHandle: ReturnType<typeof setInterval> | null = null

const previewMode = computed<PreviewMode | null>(() => {
  const value = route.query.preview
  if (typeof value !== 'string') return null
  if (['queued', 'running', 'completed', 'failed'].includes(value)) {
    return value as PreviewMode
  }
  return null
})

onMounted(async () => {
  if (previewMode.value) {
    const preview = await loadPreview(previewMode.value)
    if (preview) {
      run.value = preview
      loading.value = false
      return
    }
  }
  void loadRun()
  pollHandle = setInterval(() => {
    if (run.value && (run.value.status === 'pending' || run.value.status === 'running')) {
      void loadRun()
    }
  }, 3000)
})

async function loadPreview(mode: PreviewMode): Promise<RunDetail | null> {
  if (!import.meta.env.DEV) return null
  const { default: mocks } = await import('@/mocks/pollinator-runs.json')
  const raw = (mocks as Record<string, RunDetailMock | undefined>)[mode]
  if (!raw) return null
  return resolveTimestamps(raw)
}

function resolveTimestamps(mock: RunDetailMock): RunDetail {
  const now = Date.now()
  const offsetIso = (offset: number | null): string | null =>
    offset == null ? null : new Date(now + offset * 1000).toISOString()
  return {
    id: mock.id,
    name: mock.name,
    status: mock.status,
    created_at: offsetIso(mock.created_at_offset_seconds) ?? new Date(now).toISOString(),
    started_at: offsetIso(mock.started_at_offset_seconds),
    completed_at: offsetIso(mock.completed_at_offset_seconds),
    image_count: mock.image_count,
    processed_image_count: mock.processed_image_count,
    detection_count: mock.detection_count,
    failed_image_count: mock.failed_image_count,
    detections_by_class: mock.detections_by_class,
    detections_by_source: mock.detections_by_source,
    config: mock.config,
    error_message: mock.error_message,
    activity_log: mock.activity_log.map((e) => ({
      time: offsetIso(e.offset_seconds) ?? new Date(now).toISOString(),
      message: e.message,
      level: e.level,
    })),
  }
}

onUnmounted(() => {
  if (pollHandle) clearInterval(pollHandle)
})

async function loadRun() {
  const id = route.params.id as string
  try {
    const res = await api(`/api/analysis/runs/${id}/`)
    if (!res.ok) {
      loadError.value = (await res.text()) || `HTTP ${res.status}`
      return
    }
    const data = await res.json()
    run.value = {
      processed_image_count: 0,
      failed_image_count: 0,
      detections_by_class: {},
      detections_by_source: {},
      activity_log: [],
      ...data,
    }
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

const headerTitle = computed(() => {
  if (!run.value) return 'Run'
  return run.value.name ? `${run.value.name}` : `Run #${run.value.id}`
})

const headerSubtitle = computed(() => {
  if (!run.value) return ''
  if (run.value.status === 'pending') return 'Queued · awaiting worker'
  if (run.value.started_at) {
    const started = new Date(run.value.started_at).toLocaleString()
    return `Started ${started}`
  }
  return ''
})

const statusLabel = computed(() => {
  switch (run.value?.status) {
    case 'pending':
      return 'Queued'
    case 'running':
      return 'Running'
    case 'completed':
      return 'Completed'
    case 'failed':
      return 'Failed'
    default:
      return ''
  }
})

const statusBadgeClass = computed(() => {
  switch (run.value?.status) {
    case 'pending':
      return 'bg-muted text-muted-foreground'
    case 'running':
      return 'bg-blue-100 text-blue-700'
    case 'completed':
      return 'bg-green-100 text-green-700'
    case 'failed':
      return 'bg-red-100 text-red-700'
    default:
      return 'bg-muted text-muted-foreground'
  }
})

const statusBorderClass = computed(() => {
  if (run.value?.status === 'failed') return 'border-red-300'
  if (run.value?.status === 'completed') return 'border-green-300'
  return 'border-border'
})

const percent = computed(() => {
  if (!run.value || run.value.image_count === 0) return 0
  return Math.min(100, Math.round((run.value.processed_image_count / run.value.image_count) * 100))
})

const elapsedSeconds = computed(() => {
  if (!run.value?.started_at) return 0
  const end = run.value.completed_at ? new Date(run.value.completed_at) : new Date()
  return Math.max(0, (end.getTime() - new Date(run.value.started_at).getTime()) / 1000)
})

const elapsedHuman = computed(() => humanDuration(elapsedSeconds.value))

const etaHuman = computed(() => {
  if (!run.value || run.value.status !== 'running') return ''
  if (run.value.processed_image_count === 0) return ''
  const remaining =
    (elapsedSeconds.value / run.value.processed_image_count) *
    (run.value.image_count - run.value.processed_image_count)
  return humanDuration(remaining)
})

const timingLine = computed(() => {
  if (!run.value) return ''
  const created = new Date(run.value.created_at).toLocaleString()
  return `Created ${created}`
})

const canCancel = computed(() => run.value?.status === 'pending' || run.value?.status === 'running')
const canOpenReview = computed(
  () =>
    !!run.value &&
    run.value.detection_count > 0 &&
    (run.value.status === 'running' || run.value.status === 'completed'),
)

const classRows = computed(() => {
  if (!run.value) return []
  const total = Object.values(run.value.detections_by_class).reduce((a, b) => a + b, 0) || 1
  return Object.entries(run.value.detections_by_class)
    .sort((a, b) => b[1] - a[1])
    .map(([label, count]) => ({
      label: label[0].toUpperCase() + label.slice(1),
      count,
      percent: Math.round((count / total) * 100),
      color: CLASS_COLORS[label] ?? '#9aa3ab',
    }))
})

const sourceRows = computed(() => {
  if (!run.value) return []
  return Object.entries(run.value.detections_by_source)
    .sort((a, b) => b[1] - a[1])
    .map(([key, count]) => ({
      label: SOURCE_LABELS[key] ?? key,
      count,
    }))
})

function humanDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`
  const hours = Math.floor(seconds / 3600)
  const mins = Math.round((seconds % 3600) / 60)
  return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function logLevelClass(level: ActivityEntry['level']): string {
  if (level === 'error') return 'text-red-700 bg-red-50/40'
  if (level === 'warn') return 'text-amber-700'
  return ''
}

const cancelling = ref(false)

async function onCancel() {
  if (!run.value || cancelling.value) return
  if (previewMode.value) {
    run.value.status = 'cancelled'
    run.value.error_message = 'Cancelled by user.'
    return
  }
  const ok = await confirm({
    title: 'Cancel run',
    message:
      'Cancel this run?\nThe worker stops at the next checkpoint and partial results are discarded.',
    confirmLabel: 'Cancel run',
    cancelLabel: 'Keep running',
    variant: 'danger',
  })
  if (!ok) return
  cancelling.value = true
  try {
    const res = await api(`/api/analysis/runs/${run.value.id}/cancel/`, {
      method: 'POST',
    })
    if (!res.ok) {
      let detail = `HTTP ${res.status}`
      try {
        const body = await res.json()
        detail = body.error || body.detail || detail
      } catch {}
      loadError.value = `Cancel failed: ${detail}`
      return
    }
    const data = await res.json()
    run.value = { ...run.value, ...data }
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    cancelling.value = false
  }
}

async function onRerun() {
  if (!run.value || rerunning.value) return
  if (previewMode.value) return
  const r = run.value
  if (r.upload == null || !r.module) {
    loadError.value = 'Cannot restart: original upload or module missing from this run.'
    return
  }
  rerunning.value = true
  try {
    const res = await api('/api/analysis/runs/', {
      method: 'POST',
      body: JSON.stringify({
        module: r.module,
        upload: r.upload,
        model_version: r.model_version ?? null,
        config: r.config,
        name: r.name ? `${r.name} (retry)` : '',
      }),
    })
    if (!res.ok) {
      let detail = `HTTP ${res.status}`
      try {
        const body = await res.json()
        detail = body.detail || body.error || JSON.stringify(body)
      } catch {}
      loadError.value = `Restart failed: ${detail}`
      return
    }
    const newRun = await res.json()
    await router.push(`/pollinators/runs/${newRun.id}`)
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    rerunning.value = false
  }
}
</script>
