<template>
  <PageHeader :title="headerTitle" :subtitle="headerSubtitle" />
  <SeedsStepper current="detect" :runId="run?.id" />

  <div class="flex-1 p-8 max-w-4xl mx-auto w-full space-y-6">
    <div v-if="loading" class="text-sm text-muted-foreground">Loading…</div>
    <div v-else-if="loadError" class="text-sm text-red-600">{{ loadError }}</div>

    <template v-else-if="run">
      <section class="rounded-xl border bg-surface p-5" :class="statusBorderClass">
        <div class="flex items-center gap-3 mb-3">
          <span
            class="text-xs font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full"
            :class="statusBadgeClass"
          >
            {{ statusLabel }}
          </span>
          <span class="text-xs text-muted-foreground">{{ timingLine }}</span>
        </div>

        <div v-if="run.status === 'failed'" class="text-sm text-red-700 mb-3">
          {{ run.error_message || 'Run failed before completion.' }}
        </div>

        <div v-else-if="run.status === 'cancelled'" class="text-sm text-amber-700 mb-3">
          {{ run.error_message || 'Run was cancelled by the user.' }}
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
            <template v-if="run.status === 'completed'">Completed in {{ elapsedHuman }}</template>
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
            @click="onCancel"
            :disabled="cancelling"
          >
            {{ cancelling ? 'Cancelling...' : 'Cancel run' }}
          </button>

          <button
            v-if="
              run.status === 'pending' || run.status === 'running' || run.status === 'completed'
            "
            @click="router.push(`/seeds/runs/${run.id}/review`)"
            :disabled="run.status !== 'completed'"
            class="ml-auto text-sm px-3 py-1.5 rounded-md font-medium transition-colors"
            :class="
              run.status === 'completed'
                ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                : 'bg-muted text-muted-foreground opacity-50 cursor-not-allowed'
            "
          >
            {{ run.status === 'completed' ? 'Open review →' : 'Review pending...' }}
          </button>

          <template v-if="run.status === 'failed' || run.status === 'cancelled'">
            <button
              class="text-sm px-3 py-1.5 rounded-md border border-border hover:bg-muted disabled:opacity-50"
              @click="reRun"
              :disabled="creatingRun"
            >
              {{ creatingRun ? 'Starting...' : 'Re-run with same config' }}
            </button>

            <RouterLink
              to="/seeds/upload"
              class="ml-auto text-sm px-3 py-1.5 rounded-md font-medium bg-primary text-primary-foreground hover:bg-primary/90"
            >
              Upload new batch
            </RouterLink>
          </template>
        </div>
      </section>

      <section
        v-if="run.detection_count > 0"
        class="rounded-xl border border-border bg-surface p-5"
      >
        <h2 class="text-sm font-semibold mb-4">
          Seeds detected · {{ run.detection_count.toLocaleString() }}
        </h2>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div class="space-y-0.5">
            <div class="text-xs text-muted-foreground">Total seeds</div>
            <div class="text-2xl font-bold text-primary">
              {{ run.detection_count.toLocaleString() }}
            </div>
          </div>
          <div class="space-y-0.5">
            <div class="text-xs text-muted-foreground">Avg per image</div>
            <div class="text-2xl font-bold text-foreground">
              {{ avgPerImage }}
            </div>
          </div>
          <div v-if="run.viability" class="space-y-0.5">
            <div class="text-xs text-muted-foreground">Active seeds</div>
            <div class="text-2xl font-bold text-green-600">
              {{ run.viability.active.toLocaleString() }}
            </div>
          </div>
          <div v-if="run.viability" class="space-y-0.5">
            <div class="text-xs text-muted-foreground">Aborted seeds</div>
            <div class="text-2xl font-bold text-red-500">
              {{ run.viability.aborted.toLocaleString() }}
            </div>
          </div>
        </div>

        <div v-if="run.viability" class="mt-4">
          <div class="flex justify-between text-xs text-muted-foreground mb-1">
            <span>Batch health</span>
            <span class="font-mono">{{ viabilityPercent }}%</span>
          </div>
          <div class="h-2 rounded-full bg-muted overflow-hidden">
            <div
              class="h-full bg-green-500 transition-all"
              :style="{ width: viabilityPercent + '%' }"
            />
          </div>
        </div>

        <div class="mt-4 flex gap-2 flex-wrap">
          <span
            v-if="run.config?.selected_seed"
            class="text-xs px-2 py-0.5 rounded-full bg-eco-mint text-eco-forest font-medium"
          >
            {{ run.config.selected_seed }}
          </span>
          <span
            v-if="run.config?.condition"
            class="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground"
          >
            {{ run.config.condition }}
          </span>
          <span
            v-if="run.config?.enable_viability"
            class="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700"
          >
            viability enabled
          </span>
        </div>
      </section>

      <section class="rounded-xl border border-border bg-surface">
        <header class="px-5 py-3 border-b border-border flex items-center justify-between">
          <h2 class="text-sm font-semibold">Images Processed</h2>
          <span v-if="run.failed_image_count > 0" class="text-xs text-red-600">
            ⚠ {{ run.processed_image_count }} images processed, {{ run.failed_image_count }} images
            failed
          </span>
          <span v-else> {{ run.processed_image_count }} images processed </span>
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
import SeedsStepper from '@/components/SeedsStepper.vue'
import { api } from '@/api'

type RunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
type PreviewMode = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'

interface ActivityEntry {
  time: string
  message: string
  level: 'info' | 'warn' | 'error'
}

interface Viability {
  active: number
  aborted: number
  threshold: number
}

interface RunDetail {
  id: number
  name: string
  status: RunStatus
  upload: number
  model_version: number | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  image_count: number
  processed_image_count: number
  detection_count: number
  failed_image_count: number
  viability?: Viability
  activity_log: ActivityEntry[]
  config: Record<string, unknown>
  error_message?: string
}

const route = useRoute()
const router = useRouter()
const run = ref<RunDetail | null>(null)
const loading = ref(true)
const loadError = ref('')
const showConfig = ref(false)
const cancelling = ref(false)
const creatingRun = ref(false)

const now = ref(Date.now())
let timerHandle: ReturnType<typeof setInterval> | null = null
let pollHandle: ReturnType<typeof setInterval> | null = null

const previewMode = computed<PreviewMode | null>(() => {
  const value = route.query.preview
  if (typeof value !== 'string') return null
  if (['queued', 'running', 'completed', 'failed', 'cancelled'].includes(value))
    return value as PreviewMode
  return null
})

onMounted(async () => {
  if (previewMode.value) {
    loading.value = false
    return
  }

  void loadRun()

  timerHandle = setInterval(() => {
    now.value = Date.now()
  }, 1000)

  pollHandle = setInterval(() => {
    if (run.value && (run.value.status === 'pending' || run.value.status === 'running')) {
      void loadRun()
    }
  }, 3000)
})

onUnmounted(() => {
  if (pollHandle) clearInterval(pollHandle)
  if (timerHandle) clearInterval(timerHandle)
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
      activity_log: [],
      ...data,
    }
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

const headerTitle = computed(() => (run.value ? run.value.name || `Run #${run.value.id}` : 'Run'))
const headerSubtitle = computed(() => {
  if (!run.value) return ''
  if (run.value.status === 'pending') return 'Queued · awaiting worker'
  if (run.value.started_at) return `Started ${new Date(run.value.started_at).toLocaleString()}`
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
    case 'cancelled':
      return 'Cancelled'
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
    case 'cancelled':
      return 'bg-amber-100 text-amber-800'
    default:
      return 'bg-muted text-muted-foreground'
  }
})
const statusBorderClass = computed(() => {
  if (run.value?.status === 'failed') return 'border-red-300'
  if (run.value?.status === 'cancelled') return 'border-amber-300'
  if (run.value?.status === 'completed') return 'border-green-300'
  return 'border-border'
})
const percent = computed(() => {
  if (!run.value || run.value.image_count === 0) return 0
  return Math.min(100, Math.round((run.value.processed_image_count / run.value.image_count) * 100))
})
const elapsedSeconds = computed(() => {
  const startTime = run.value?.started_at || run.value?.created_at
  if (!startTime) return 0

  const start = new Date(startTime).getTime()
  const end = run.value?.completed_at ? new Date(run.value.completed_at).getTime() : now.value

  return Math.max(0, (end - start) / 1000)
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
  return `Created ${new Date(run.value.created_at).toLocaleString()}`
})
const canCancel = computed(() => run.value?.status === 'pending' || run.value?.status === 'running')

const avgPerImage = computed(() => {
  if (!run.value || run.value.processed_image_count === 0) return '—'
  return Math.round(run.value.detection_count / run.value.processed_image_count)
})
const viabilityPercent = computed(() => {
  if (!run.value?.viability) return 0
  const total = run.value.viability.active + run.value.viability.aborted
  if (!total) return 0
  return Math.round((run.value.viability.active / total) * 100)
})

function humanDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`
  const hours = Math.floor(seconds / 3600)
  const mins = Math.round((seconds % 3600) / 60)
  return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`
}
function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}
function logLevelClass(level: ActivityEntry['level']): string {
  if (level === 'error') return 'text-red-700 bg-red-50/40'
  if (level === 'warn') return 'text-amber-700'
  return ''
}

async function onCancel() {
  if (!run.value) return
  cancelling.value = true
  try {
    const res = await api(`/api/analysis/runs/${run.value.id}/cancel/`, { method: 'POST' })
    if (!res.ok) {
      loadError.value = (await res.text()) || `HTTP ${res.status}`
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

async function reRun() {
  if (!run.value) return
  creatingRun.value = true
  try {
    const response = await api('/api/analysis/runs/', {
      method: 'POST',
      body: JSON.stringify({
        module: 'seeds',
        upload: run.value.upload,
        name: `${run.value.name} (Retry)`,
        config: run.value.config,
        model_version: run.value.model_version,
      }),
    })

    if (!response.ok) throw new Error(await response.text())

    const newRun = await response.json()
    router.push(`/seeds/runs/${newRun.id}/detect`)
    setTimeout(() => {
      loadRun()
    }, 100)
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    creatingRun.value = false
  }
}
</script>
