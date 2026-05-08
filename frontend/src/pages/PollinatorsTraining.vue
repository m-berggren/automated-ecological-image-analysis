<template>
  <PageHeader
    title="Training"
    subtitle="Retrain the pollinator pipeline on accumulated review data"
  />

  <div class="flex-1 overflow-auto">
    <div v-if="loading" class="p-8 text-sm text-muted-foreground">Loading…</div>
    <div v-else-if="loadError" class="p-8 text-sm text-red-600">{{ loadError }}</div>

    <div v-else class="p-6 space-y-4 max-w-4xl mx-auto w-full">
      <!-- New training job card -->
      <section class="rounded-xl border border-border bg-card overflow-hidden shadow-md">
        <header class="px-5 py-4 bg-primary/[0.22] border-b border-border">
          <h2 class="font-bold text-lg tracking-tight">New training job</h2>
          <p class="text-xs text-muted-foreground mt-0.5">
            Pick a model, choose data, and start. Training runs on CPU — expect long jobs.
          </p>
        </header>

        <!-- Step 1: Pick model -->
        <div class="px-5 py-4 border-b border-border">
          <div
            class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3"
          >
            1. Pick a model to retrain
          </div>
          <div class="space-y-2">
            <label
              v-for="track in tracks"
              :key="track.id"
              class="flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors"
              :class="
                selectedTrackId === track.id
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:border-primary/40'
              "
            >
              <input type="radio" :value="track.id" v-model="selectedTrackId" class="mt-0.5" />
              <div class="flex-1 min-w-0">
                <div class="flex items-baseline gap-2 flex-wrap">
                  <span class="font-medium text-sm">{{ track.label }}</span>
                  <span
                    v-if="activeVersion(track)"
                    class="text-xs px-2 py-0.5 rounded-full bg-green-300 text-green-900 font-medium"
                  >
                    {{ activeVersion(track)!.version_name }}
                  </span>
                  <span
                    v-if="track.active_job"
                    class="text-xs px-2 py-0.5 rounded-full bg-blue-200 text-blue-800 font-medium"
                  >
                    training in progress
                  </span>
                </div>
                <p class="text-xs text-muted-foreground mt-0.5">{{ track.description }}</p>
                <div v-if="activeVersion(track)" class="text-xs text-muted-foreground mt-1">
                  {{ track.metric_label }}
                  <span class="font-mono ml-1 text-foreground">
                    {{ formatMetric(activeMainMetric(track)) }}
                  </span>
                  · {{ track.data_pool.total_samples.toLocaleString() }} samples available
                  <span v-if="track.data_pool.new_since_active > 0" class="text-primary">
                    (+{{ track.data_pool.new_since_active }} new since active)
                  </span>
                </div>
              </div>
            </label>
          </div>
        </div>

        <!-- Step 2: Choose data -->
        <div v-if="selectedTrack" class="px-5 py-4 border-b border-border">
          <div
            class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3"
          >
            2. Choose training data
          </div>
          <!-- Pool summary card -->
          <div class="rounded-lg border border-border bg-muted/20 p-4 space-y-3">
            <div class="flex items-baseline justify-between">
              <div>
                <div class="text-sm font-medium">
                  {{ totalPoolSamples.toLocaleString() }} samples in pool
                </div>
                <div class="text-xs text-muted-foreground">
                  {{ selectedTrack.data_pool.total_samples.toLocaleString() }} from review ·
                  {{ uploadedFiles.length }} uploaded
                  {{ uploadedFiles.length === 1 ? 'file' : 'files' }}
                </div>
              </div>
              <button class="text-xs text-primary hover:underline" @click="openReviewDrawer">
                Browse pool →
              </button>
            </div>
            <div class="flex flex-wrap gap-3 text-xs text-muted-foreground">
              <span
                v-for="row in classRows(selectedTrack)"
                :key="row.label"
                class="inline-flex items-center gap-1"
              >
                <span class="w-1.5 h-1.5 rounded-full" :style="{ backgroundColor: row.color }" />
                {{ row.count.toLocaleString() }} {{ row.label.toLowerCase() }}
              </span>
            </div>
            <div class="h-1.5 rounded-full overflow-hidden flex">
              <div
                v-for="row in classRows(selectedTrack)"
                :key="row.label"
                :style="{ width: row.percent + '%', backgroundColor: row.color }"
                class="h-full"
              />
            </div>
          </div>

          <!-- Add data drop zone -->
          <div
            class="mt-3 rounded-lg border-2 border-dashed border-border p-5 text-center cursor-pointer transition-colors hover:bg-muted/20"
            :class="{ 'border-primary bg-primary/5': dragOver }"
            @dragover.prevent="dragOver = true"
            @dragleave.prevent="dragOver = false"
            @drop.prevent="onDrop"
            @click="triggerFilePicker"
          >
            <div class="text-sm font-medium">Drop crops or a folder here, or click to browse</div>
            <div class="text-xs text-muted-foreground mt-1">
              Adds to the training pool. Accepts .jpg, .png, or a .zip with per-class folders.
            </div>
            <input
              ref="fileInputRef"
              type="file"
              multiple
              accept=".jpg,.jpeg,.png,.zip"
              class="hidden"
              @change="onFilePicked"
            />
          </div>

          <!-- Files list -->
          <ul v-if="uploadedFiles.length" class="mt-3 space-y-1 text-xs">
            <li
              v-for="(file, idx) in uploadedFiles"
              :key="file.name + idx"
              class="flex items-center gap-2 px-2 py-1 rounded border border-border bg-card"
            >
              <span class="font-mono flex-1 truncate">{{ file.name }}</span>
              <span class="text-muted-foreground shrink-0">
                {{ formatFileSize(file.size) }}
              </span>
              <button class="text-muted-foreground hover:text-red-600" @click="removeUpload(idx)">
                ✕
              </button>
            </li>
          </ul>

          <!-- Rejected as background option (binary classifier only) -->
          <label
            v-if="selectedTrack.id === 'insectnet_binary'"
            class="mt-3 flex items-center gap-2 text-sm"
          >
            <input v-model="rejectedAsBackground" type="checkbox" />
            Include rejected detections as background examples
          </label>
        </div>

        <!-- Step 3: Settings -->
        <div v-if="selectedTrack" class="px-5 py-4 border-b border-border">
          <div
            class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3"
          >
            3. Settings
          </div>
          <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <label class="text-xs text-muted-foreground space-y-1">
              <span>Train %</span>
              <input
                v-model.number="settings.train_split"
                type="number"
                min="50"
                max="95"
                class="w-full px-2 py-1 rounded border border-border bg-background text-sm font-mono text-foreground"
              />
            </label>
            <label class="text-xs text-muted-foreground space-y-1">
              <span>Val %</span>
              <input
                v-model.number="settings.val_split"
                type="number"
                min="0"
                max="40"
                class="w-full px-2 py-1 rounded border border-border bg-background text-sm font-mono text-foreground"
              />
            </label>
            <label class="text-xs text-muted-foreground space-y-1">
              <span>Test %</span>
              <input
                v-model.number="settings.test_split"
                type="number"
                min="0"
                max="40"
                class="w-full px-2 py-1 rounded border border-border bg-background text-sm font-mono text-foreground"
              />
            </label>
            <label class="text-xs text-muted-foreground space-y-1">
              <span>Epochs</span>
              <input
                v-model.number="settings.epochs"
                type="number"
                min="1"
                max="200"
                class="w-full px-2 py-1 rounded border border-border bg-background text-sm font-mono text-foreground"
              />
            </label>
          </div>
          <div class="mt-2 text-xs text-muted-foreground flex items-center gap-3">
            <label class="inline-flex items-center gap-2">
              <input v-model="settings.stratified" type="checkbox" />
              Stratified split
            </label>
            <span v-if="splitTotal !== 100" class="text-amber-700">
              ⚠ Splits sum to {{ splitTotal }}% (must equal 100)
            </span>
            <span v-else class="ml-auto">
              Estimated time on CPU: <span class="font-mono">~{{ estimatedTime }}</span>
            </span>
          </div>
        </div>

        <!-- Submit -->
        <div class="px-5 py-4 flex items-center gap-3 justify-end">
          <span v-if="formMessage" class="text-xs text-muted-foreground">{{ formMessage }}</span>
          <button
            :disabled="!canSubmit"
            class="px-4 py-2 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
            @click="startTraining"
          >
            Start training
          </button>
        </div>
      </section>

      <!-- Active job (if any) -->
      <section
        v-if="activeJobs.length"
        class="rounded-xl border border-border bg-card overflow-hidden shadow-md"
      >
        <header class="px-5 py-4 bg-blue-100 border-b border-border">
          <h2 class="font-bold text-base tracking-tight">
            Currently training · {{ activeJobs.length }}
          </h2>
        </header>
        <ul class="divide-y divide-border">
          <li v-for="entry in activeJobs" :key="entry.track.id" class="px-5 py-4">
            <div class="flex items-baseline gap-3 mb-2">
              <span class="font-medium text-sm">{{ entry.track.label }}</span>
              <span class="text-xs text-muted-foreground">
                {{ entry.track.active_job!.version_name }}
              </span>
              <button
                class="ml-auto text-xs px-2 py-1 rounded border border-border hover:bg-muted"
                @click="cancelJob(entry.track)"
              >
                Cancel
              </button>
            </div>
            <div class="text-xs text-muted-foreground mb-2">
              epoch {{ entry.track.active_job!.current_epoch }} /
              {{ entry.track.active_job!.total_epochs }} · loss
              {{ entry.track.active_job!.loss.toFixed(3) }} · val acc
              {{ (entry.track.active_job!.val_accuracy * 100).toFixed(1) }}%
            </div>
            <div class="h-1.5 rounded-full bg-muted overflow-hidden max-w-md">
              <div
                class="h-full bg-blue-500 transition-all"
                :style="{ width: jobPercent(entry.track.active_job!) + '%' }"
              />
            </div>
            <div class="text-xs text-muted-foreground mt-1 font-mono">
              {{ humanDuration(jobElapsed(entry.track.active_job!)) }} elapsed · ~{{
                humanDuration(jobRemaining(entry.track.active_job!))
              }}
              remaining
            </div>
          </li>
        </ul>
      </section>

      <!-- Training history -->
      <section class="rounded-xl border border-border bg-card overflow-hidden shadow-md">
        <header class="px-5 py-4 bg-primary/[0.22] border-b border-border">
          <h2 class="font-bold text-lg tracking-tight">Training history</h2>
        </header>
        <table class="w-full text-sm">
          <thead class="text-xs text-muted-foreground bg-muted/30">
            <tr>
              <th class="text-left font-medium px-5 py-2">Job</th>
              <th class="text-left font-medium px-3 py-2">Model</th>
              <th class="text-left font-medium px-3 py-2">Started</th>
              <th class="text-left font-medium px-3 py-2">Duration</th>
              <th class="text-left font-medium px-3 py-2">Samples</th>
              <th class="text-left font-medium px-3 py-2">Status</th>
              <th class="text-left font-medium px-3 py-2">Result</th>
              <th class="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="job in history" :key="job.id">
              <tr
                class="border-t border-border hover:bg-muted/20 cursor-pointer"
                @click="toggleHistory(job.id)"
              >
                <td class="px-5 py-2 font-mono text-xs">#{{ job.id }}</td>
                <td class="px-3 py-2 text-xs">{{ job.track_label }}</td>
                <td class="px-3 py-2 text-xs text-muted-foreground">
                  {{ formatRelative(job.started_at) }}
                </td>
                <td class="px-3 py-2 text-xs font-mono">
                  {{ job.duration_seconds ? humanDuration(job.duration_seconds) : '—' }}
                </td>
                <td class="px-3 py-2 text-xs">{{ job.samples_used.toLocaleString() }}</td>
                <td class="px-3 py-2">
                  <span class="text-xs px-2 py-0.5 rounded-full" :class="statusClass(job.status)">
                    {{ job.status }}
                  </span>
                </td>
                <td class="px-3 py-2 text-xs">
                  <template v-if="job.main_metric_value != null">
                    <span class="text-muted-foreground">{{ job.main_metric_label }}</span>
                    <span class="ml-1 font-mono">{{ job.main_metric_value.toFixed(2) }}</span>
                  </template>
                  <span v-else-if="job.error_message" class="text-red-700 text-xs">
                    {{ job.error_message }}
                  </span>
                  <span v-else class="text-muted-foreground">—</span>
                </td>
                <td class="px-3 py-2 text-right text-muted-foreground">
                  {{ expandedHistory.has(job.id) ? '▾' : '▸' }}
                </td>
              </tr>
              <tr v-if="expandedHistory.has(job.id)" class="border-t border-border bg-muted/10">
                <td></td>
                <td colspan="7" class="px-3 py-4">
                  <dl class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs max-w-md">
                    <dt class="text-muted-foreground">Resulting version</dt>
                    <dd class="font-medium">{{ job.version_name }}</dd>
                    <dt class="text-muted-foreground">Started</dt>
                    <dd>{{ new Date(job.started_at).toLocaleString() }}</dd>
                    <dt class="text-muted-foreground">Epochs requested</dt>
                    <dd class="font-mono">{{ job.epochs_total }}</dd>
                    <dt class="text-muted-foreground">Samples used</dt>
                    <dd class="font-mono">{{ job.samples_used.toLocaleString() }}</dd>
                    <dt class="text-muted-foreground">Initiated by</dt>
                    <dd>{{ job.initiated_by }}</dd>
                    <template v-if="job.error_message">
                      <dt class="text-muted-foreground">Error</dt>
                      <dd class="text-red-700">{{ job.error_message }}</dd>
                    </template>
                  </dl>
                  <div v-if="chartsForJob(job)" class="mt-4 pt-3 border-t border-border">
                    <div
                      class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-2"
                    >
                      Charts
                    </div>
                    <TrainingCharts :charts="chartsForJob(job)" />
                  </div>
                </td>
              </tr>
            </template>
            <tr v-if="!history.length">
              <td colspan="8" class="px-5 py-6 text-center text-sm text-muted-foreground">
                No training jobs yet.
              </td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>

    <!-- Review drawer -->
    <Transition name="drawer">
      <div
        v-if="reviewDrawerOpen"
        class="fixed inset-0 z-50 flex"
        @click.self="reviewDrawerOpen = false"
      >
        <div class="flex-1 bg-black/40" />
        <aside class="w-[640px] max-w-full bg-card border-l border-border shadow-2xl flex flex-col">
          <header
            class="px-5 py-3 border-b border-border bg-primary/[0.22] flex items-center gap-3"
          >
            <h2 class="font-bold text-base tracking-tight">Review training pool</h2>
            <span v-if="selectedTrack" class="text-xs text-muted-foreground">
              {{ selectedTrack.label }} ·
              {{ selectedTrack.data_pool.total_samples.toLocaleString() }} samples
            </span>
            <button
              class="ml-auto text-muted-foreground hover:text-foreground"
              @click="reviewDrawerOpen = false"
            >
              ✕
            </button>
          </header>
          <div class="px-5 py-3 border-b border-border flex items-center gap-2 text-xs">
            <span class="text-muted-foreground">Filter:</span>
            <button
              v-for="cls in drawerClasses"
              :key="cls.value"
              class="px-2 py-1 rounded font-medium transition-colors"
              :class="
                drawerFilter === cls.value
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-muted'
              "
              @click="drawerFilter = cls.value"
            >
              {{ cls.label }}
            </button>
          </div>
          <div class="flex-1 overflow-auto p-4">
            <div class="grid grid-cols-5 gap-2">
              <div
                v-for="(thumb, i) in drawerThumbnails"
                :key="i"
                class="aspect-square rounded border border-border flex items-center justify-center text-2xl relative overflow-hidden"
                :style="{ backgroundColor: thumb.bg }"
                :title="thumb.label"
              >
                <span class="opacity-40">{{ thumb.glyph }}</span>
                <div
                  class="absolute bottom-0 left-0 right-0 h-1.5"
                  :style="{ backgroundColor: thumb.color }"
                />
              </div>
            </div>
            <p class="text-xs text-muted-foreground mt-4 text-center">
              Showing placeholder thumbnails. Real crops appear here once the training-data manifest
              is wired up.
            </p>
          </div>
        </aside>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import TrainingCharts from '@/components/TrainingCharts.vue'
import { api } from '@/api'

interface ChartData {
  training_curve?: Array<{ epoch: number; loss: number; val_metric: number }>
  confusion_matrix?: { labels: string[]; values: number[][] }
  per_class?: Array<{ label: string; value: number }>
}

interface Version {
  id: number
  version_name: string
  is_active: boolean
  metrics: Record<string, number>
  samples: number
  trained_at: string
  training_duration_seconds: number
  parameters: Record<string, unknown>
  charts?: ChartData | null
}

interface ActiveJob {
  id: number
  version_name: string
  mode: string
  started_at: string
  estimated_total_seconds: number
  current_epoch: number
  total_epochs: number
  loss: number
  val_accuracy: number
}

interface DataPool {
  total_samples: number
  new_since_active: number
  by_class: Record<string, number>
}

interface Track {
  id: string
  label: string
  description: string
  kind: string
  metric_label: string
  active_version_id: number | null
  versions: Version[]
  data_pool: DataPool
  active_job: ActiveJob | null
}

interface HistoryEntry {
  id: number
  track_id: string
  track_label: string
  version_name: string
  samples_used: number
  epochs_total: number
  started_at: string
  duration_seconds: number | null
  status: 'running' | 'completed' | 'failed' | 'cancelled' | 'pending'
  main_metric_label: string
  main_metric_value: number | null
  initiated_by: string
  error_message?: string
}

const CLASS_COLORS: Record<string, string> = {
  fly: '#6b9bd2',
  bumblebee: '#e6a946',
  butterfly: '#c87bba',
  other: '#9aa3ab',
  insect: '#6b9bd2',
  background: '#9aa3ab',
}

const route = useRoute()
const loading = ref(true)
const loadError = ref('')
const tracks = ref<Track[]>([])
const history = ref<HistoryEntry[]>([])
const selectedTrackId = ref<string | null>(null)
const rejectedAsBackground = ref(true)
const formMessage = ref('')
const expandedHistory = ref<Set<number>>(new Set())
const uploadedFiles = ref<Array<{ name: string; size: number }>>([])
const fileInputRef = ref<HTMLInputElement | null>(null)
const reviewDrawerOpen = ref(false)
const drawerFilter = ref<string>('all')
const dragOver = ref(false)

const settings = reactive({
  train_split: 80,
  val_split: 10,
  test_split: 10,
  epochs: 20,
  stratified: true,
})

const previewMode = computed<string | null>(() => {
  const value = route.query.preview
  return typeof value === 'string' ? value : null
})

onMounted(async () => {
  if (previewMode.value) {
    const data = await loadPreview(previewMode.value)
    if (data) {
      tracks.value = data.tracks
      history.value = data.history
      if (tracks.value.length) selectedTrackId.value = tracks.value[0].id
      loading.value = false
      return
    }
  }
  await loadFromApi()
})

interface VersionMock extends Omit<Version, 'trained_at'> {
  trained_at_offset_seconds: number
}
interface ActiveJobMock extends Omit<ActiveJob, 'started_at'> {
  started_at_offset_seconds: number
}
interface TrackMock extends Omit<Track, 'versions' | 'active_job'> {
  versions: VersionMock[]
  active_job: ActiveJobMock | null
}
interface HistoryMock extends Omit<HistoryEntry, 'started_at'> {
  started_at_offset_seconds: number
}

async function loadPreview(_mode: string) {
  if (!import.meta.env.DEV) return null
  const { default: mocks } = await import('@/mocks/pollinator-models.json')
  const raw = (
    mocks as unknown as Record<
      string,
      { tracks: TrackMock[]; training_history: HistoryMock[] } | undefined
    >
  ).default
  if (!raw) return null
  const now = Date.now()
  const isoFromOffset = (offset: number): string => new Date(now + offset * 1000).toISOString()
  return {
    tracks: raw.tracks.map((t) => ({
      ...t,
      versions: t.versions.map((v) => ({
        ...v,
        trained_at: isoFromOffset(v.trained_at_offset_seconds),
      })),
      active_job: t.active_job
        ? { ...t.active_job, started_at: isoFromOffset(t.active_job.started_at_offset_seconds) }
        : null,
    })),
    history: raw.training_history.map((h) => ({
      ...h,
      started_at: isoFromOffset(h.started_at_offset_seconds),
    })),
  }
}

async function loadFromApi() {
  try {
    const res = await api('/api/analysis/models/?module=pollinators')
    if (!res.ok) {
      loadError.value = `HTTP ${res.status}`
      return
    }
    tracks.value = []
    history.value = []
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

const selectedTrack = computed(
  () => tracks.value.find((t) => t.id === selectedTrackId.value) ?? null,
)

const splitTotal = computed(() => settings.train_split + settings.val_split + settings.test_split)

const activeJobs = computed(() =>
  tracks.value.filter((t) => t.active_job !== null).map((track) => ({ track })),
)

const canSubmit = computed(() => {
  if (!selectedTrack.value) return false
  if (selectedTrack.value.active_job) return false
  if (splitTotal.value !== 100) return false
  if (totalPoolSamples.value === 0) return false
  return true
})

const totalPoolSamples = computed(() => {
  if (!selectedTrack.value) return 0
  return selectedTrack.value.data_pool.total_samples + uploadedFiles.value.length
})

const estimatedTime = computed(() => {
  if (!selectedTrack.value) return ''
  const samples = selectedTrack.value.data_pool.total_samples
  const seconds = (samples * settings.epochs) / 12
  return humanDuration(seconds)
})

function activeVersion(t: Track): Version | null {
  return t.versions.find((v) => v.is_active) ?? null
}
function activeMainMetric(t: Track): number | undefined {
  const v = activeVersion(t)
  if (!v) return undefined
  return v.metrics[t.metric_label] ?? Object.values(v.metrics)[0]
}
function formatMetric(value: number | undefined): string {
  if (value === undefined) return '—'
  return value.toFixed(2)
}
function classRows(t: Track) {
  const total = Object.values(t.data_pool.by_class).reduce((a, b) => a + b, 0) || 1
  return Object.entries(t.data_pool.by_class)
    .sort((a, b) => b[1] - a[1])
    .map(([cls, count]) => ({
      label: cls[0].toUpperCase() + cls.slice(1),
      count,
      percent: Math.round((count / total) * 100),
      color: CLASS_COLORS[cls] ?? '#9aa3ab',
    }))
}
function jobElapsed(j: ActiveJob): number {
  return Math.max(0, (Date.now() - new Date(j.started_at).getTime()) / 1000)
}
function jobRemaining(j: ActiveJob): number {
  return Math.max(0, j.estimated_total_seconds - jobElapsed(j))
}
function jobPercent(j: ActiveJob): number {
  if (!j.estimated_total_seconds) return 0
  return Math.min(100, Math.round((jobElapsed(j) / j.estimated_total_seconds) * 100))
}
function humanDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`
  const hours = Math.floor(seconds / 3600)
  const mins = Math.round((seconds % 3600) / 60)
  return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`
}
function formatRelative(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
  return `${Math.round(diff / 86400)}d ago`
}

function statusClass(s: string): string {
  switch (s) {
    case 'completed':
      return 'bg-green-200 text-green-800'
    case 'running':
      return 'bg-blue-200 text-blue-800'
    case 'failed':
      return 'bg-red-200 text-red-800'
    case 'cancelled':
      return 'bg-muted text-muted-foreground'
    case 'pending':
      return 'bg-amber-200 text-amber-800'
    default:
      return 'bg-muted text-muted-foreground'
  }
}

function cancelJob(track: Track) {
  track.active_job = null
}

function toggleHistory(id: number) {
  const next = new Set(expandedHistory.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedHistory.value = next
}

function chartsForJob(job: HistoryEntry): ChartData | null {
  for (const t of tracks.value) {
    const v = t.versions.find((x) => x.version_name === job.version_name)
    if (v?.charts) return v.charts
  }
  return null
}

const CLASS_GLYPHS: Record<string, string> = {
  fly: '🪰',
  bumblebee: '🐝',
  butterfly: '🦋',
  other: '?',
  insect: '🪰',
  background: '·',
}

function triggerFilePicker() {
  fileInputRef.value?.click()
}

function onFilePicked(e: Event) {
  const target = e.target as HTMLInputElement
  if (!target.files) return
  for (const f of Array.from(target.files)) {
    uploadedFiles.value.push({ name: f.name, size: f.size })
  }
  target.value = ''
}

function onDrop(e: DragEvent) {
  dragOver.value = false
  if (!e.dataTransfer?.files) return
  for (const f of Array.from(e.dataTransfer.files)) {
    uploadedFiles.value.push({ name: f.name, size: f.size })
  }
}

function removeUpload(idx: number) {
  uploadedFiles.value.splice(idx, 1)
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function openReviewDrawer() {
  if (!selectedTrack.value) return
  drawerFilter.value = 'all'
  reviewDrawerOpen.value = true
}

const drawerClasses = computed(() => {
  if (!selectedTrack.value) return [{ value: 'all', label: 'All' }]
  const classes = Object.keys(selectedTrack.value.data_pool.by_class)
  return [
    { value: 'all', label: 'All' },
    ...classes.map((c) => ({
      value: c,
      label: c[0].toUpperCase() + c.slice(1),
    })),
  ]
})

const drawerThumbnails = computed(() => {
  if (!selectedTrack.value) return []
  const balance = selectedTrack.value.data_pool.by_class
  const filter = drawerFilter.value
  const result: Array<{ label: string; glyph: string; color: string; bg: string }> = []
  for (const [cls, count] of Object.entries(balance)) {
    if (filter !== 'all' && filter !== cls) continue
    const visible = Math.min(count, 30)
    for (let i = 0; i < visible; i++) {
      result.push({
        label: cls,
        glyph: CLASS_GLYPHS[cls] ?? '?',
        color: CLASS_COLORS[cls] ?? '#9aa3ab',
        bg: (CLASS_COLORS[cls] ?? '#9aa3ab') + '14',
      })
    }
  }
  return result
})

function startTraining() {
  if (!canSubmit.value || !selectedTrack.value) return
  formMessage.value = 'Training queued. (No worker wired up yet.)'
  if (previewMode.value) {
    const t = selectedTrack.value
    t.active_job = {
      id: Date.now(),
      version_name: `${t.id}-${(t.versions.length + 1).toString().padStart(2, '0')} (in progress)`,
      mode: 'unfreeze_last',
      started_at: new Date().toISOString(),
      estimated_total_seconds: Math.round((t.data_pool.total_samples * settings.epochs) / 12),
      current_epoch: 0,
      total_epochs: settings.epochs,
      loss: 0,
      val_accuracy: 0,
    }
    history.value = [
      {
        id: Date.now(),
        track_id: t.id,
        track_label: t.label,
        version_name: t.active_job.version_name,
        samples_used: t.data_pool.total_samples,
        epochs_total: settings.epochs,
        started_at: new Date().toISOString(),
        duration_seconds: null,
        status: 'running',
        main_metric_label: t.metric_label,
        main_metric_value: null,
        initiated_by: 'you',
      },
      ...history.value,
    ]
  }
}
</script>

<style scoped>
.drawer-enter-active aside,
.drawer-leave-active aside {
  transition: transform 220ms ease;
}
.drawer-enter-from aside,
.drawer-leave-to aside {
  transform: translateX(100%);
}
.drawer-enter-active > div:first-child,
.drawer-leave-active > div:first-child {
  transition: opacity 220ms ease;
}
.drawer-enter-from > div:first-child,
.drawer-leave-to > div:first-child {
  opacity: 0;
}
</style>
