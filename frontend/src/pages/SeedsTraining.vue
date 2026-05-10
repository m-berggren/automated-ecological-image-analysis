<template>
  <PageHeader
    title="Training"
    subtitle="Retrain seed detection models per species"
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
            Select a seed species and start retraining. Training runs on CPU — expect long jobs.
          </p>
        </header>

        <!-- Step 1: Pick model -->
        <div class="px-5 py-4 border-b border-border">
          <div class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3">
            1. Pick a species model to retrain
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
                  <span class="text-xs text-muted-foreground italic">{{ track.species }}</span>
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
                <div v-if="activeVersion(track)" class="text-xs text-muted-foreground mt-1">
                  MAE
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

        <!-- Step 2: Add training data -->
        <div v-if="selectedTrack" class="px-5 py-4 border-b border-border">
          <div class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3">
            2. Add training data
          </div>
          <div class="rounded-lg border border-border bg-muted/20 p-4 space-y-2">
            <div class="text-sm font-medium">
              {{ totalPoolSamples.toLocaleString() }} samples available
            </div>
            <div class="text-xs text-muted-foreground">
              {{ selectedTrack.data_pool.total_samples.toLocaleString() }} from previous runs ·
              {{ uploadedFiles.length }} uploaded {{ uploadedFiles.length === 1 ? 'file' : 'files' }}
            </div>
          </div>

          <!-- Drop zone -->
          <div
            class="mt-3 rounded-lg border-2 border-dashed border-border p-5 text-center cursor-pointer transition-colors hover:bg-muted/20"
            :class="{ 'border-primary bg-primary/5': dragOver }"
            @dragover.prevent="dragOver = true"
            @dragleave.prevent="dragOver = false"
            @drop.prevent="onDrop"
            @click="triggerFilePicker"
          >
            <div class="text-sm font-medium">Drop images or a folder here, or click to browse</div>
            <div class="text-xs text-muted-foreground mt-1">
              Accepts .jpg, .png, or a .zip with annotated seed images.
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

          <!-- File list -->
          <ul v-if="uploadedFiles.length" class="mt-3 space-y-1 text-xs">
            <li
              v-for="(file, idx) in uploadedFiles"
              :key="file.name + idx"
              class="flex items-center gap-2 px-2 py-1 rounded border border-border bg-card"
            >
              <span class="font-mono flex-1 truncate">{{ file.name }}</span>
              <span class="text-muted-foreground shrink-0">{{ formatFileSize(file.size) }}</span>
              <button class="text-muted-foreground hover:text-red-600" @click="removeUpload(idx)">✕</button>
            </li>
          </ul>
        </div>

        <!-- Step 3: Settings -->
        <div v-if="selectedTrack" class="px-5 py-4 border-b border-border">
          <div class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3">
            3. Settings
          </div>
          <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <label class="text-xs text-muted-foreground space-y-1">
              <span>Train %</span>
              <input
                v-model.number="settings.train_split"
                type="number" min="50" max="95"
                class="w-full px-2 py-1 rounded border border-border bg-background text-sm font-mono text-foreground"
              />
            </label>
            <label class="text-xs text-muted-foreground space-y-1">
              <span>Val %</span>
              <input
                v-model.number="settings.val_split"
                type="number" min="0" max="40"
                class="w-full px-2 py-1 rounded border border-border bg-background text-sm font-mono text-foreground"
              />
            </label>
            <label class="text-xs text-muted-foreground space-y-1">
              <span>Test %</span>
              <input
                v-model.number="settings.test_split"
                type="number" min="0" max="40"
                class="w-full px-2 py-1 rounded border border-border bg-background text-sm font-mono text-foreground"
              />
            </label>
            <label class="text-xs text-muted-foreground space-y-1">
              <span>Epochs</span>
              <input
                v-model.number="settings.epochs"
                type="number" min="1" max="200"
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

      <!-- Active jobs -->
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
              <span class="text-xs text-muted-foreground italic">{{ entry.track.species }}</span>
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
              {{ entry.track.active_job!.loss.toFixed(3) }}
            </div>
            <div class="h-1.5 rounded-full bg-muted overflow-hidden max-w-md">
              <div
                class="h-full bg-blue-500 transition-all"
                :style="{ width: jobPercent(entry.track.active_job!) + '%' }"
              />
            </div>
            <div class="text-xs text-muted-foreground mt-1 font-mono">
              {{ humanDuration(jobElapsed(entry.track.active_job!)) }} elapsed ·
              ~{{ humanDuration(jobRemaining(entry.track.active_job!)) }} remaining
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
              <th class="text-left font-medium px-3 py-2">Species</th>
              <th class="text-left font-medium px-3 py-2">Started</th>
              <th class="text-left font-medium px-3 py-2">Duration</th>
              <th class="text-left font-medium px-3 py-2">Samples</th>
              <th class="text-left font-medium px-3 py-2">Status</th>
              <th class="text-left font-medium px-3 py-2">Results</th>
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
                        <span class="text-muted-foreground">MAE </span>
                        <span class="font-mono">{{ job.main_metric_value.toFixed(2) }}</span>
                        <span class="text-muted-foreground ml-2">P </span>
                        <span class="font-mono">{{ job.precision?.toFixed(2) ?? '—' }}</span>
                        <span class="text-muted-foreground ml-2">R </span>
                        <span class="font-mono">{{ job.recall?.toFixed(2) ?? '—' }}</span>
                        <span class="text-muted-foreground ml-2">F1 </span>
                        <span class="font-mono">{{ job.f1?.toFixed(2) ?? '—' }}</span>
                    </template>
                    <span v-else-if="job.error_message" class="text-red-700">{{ job.error_message }}</span>
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
                    <dt class="text-muted-foreground">Version</dt>
                    <dd class="font-medium">{{ job.version_name }}</dd>
                    <dt class="text-muted-foreground">Started</dt>
                    <dd>{{ new Date(job.started_at).toLocaleString() }}</dd>
                    <dt class="text-muted-foreground">Epochs</dt>
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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import { api } from '@/api'

interface Version {
  id: number
  version_name: string
  is_active: boolean
  metrics: Record<string, number>
  samples: number
  trained_at: string
}

interface ActiveJob {
  id: number
  version_name: string
  started_at: string
  estimated_total_seconds: number
  current_epoch: number
  total_epochs: number
  loss: number
}

interface DataPool {
  total_samples: number
  new_since_active: number
}

interface Track {
  id: string
  label: string
  species: string
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
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  main_metric_value: number | null //MAE
  precision: number | null
  recall: number | null
  f1: number | null
  initiated_by: string
  error_message?: string
}

// Mock types
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

const route = useRoute()
const loading = ref(true)
const loadError = ref('')
const tracks = ref<Track[]>([])
const history = ref<HistoryEntry[]>([])
const selectedTrackId = ref<string | null>(null)
const formMessage = ref('')
const expandedHistory = ref<Set<number>>(new Set())
const uploadedFiles = ref<Array<{ name: string; size: number }>>([])
const fileInputRef = ref<HTMLInputElement | null>(null)
const dragOver = ref(false)

const settings = reactive({
  train_split: 80,
  val_split: 10,
  test_split: 10,
  epochs: 90,
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

async function loadPreview(_mode: string) {
  if (!import.meta.env.DEV) return null
  const { default: mocks } = await import('@/mocks/seed-models.json')
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
    const res = await api('/api/analysis/models/?module=seeds')
    if (!res.ok) { loadError.value = `HTTP ${res.status}`; return }
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
  const seconds = (selectedTrack.value.data_pool.total_samples * settings.epochs) / 12
  return humanDuration(seconds)
})

function activeVersion(t: Track): Version | null {
  return t.versions.find((v) => v.is_active) ?? null
}
function activeMainMetric(t: Track): number | undefined {
  const v = activeVersion(t)
  if (!v) return undefined
  return v.metrics['mae'] ?? Object.values(v.metrics)[0]
}
function formatMetric(value: number | undefined): string {
  if (value === undefined) return '—'
  return value.toFixed(2)
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
    case 'completed':  return 'bg-green-200 text-green-800'
    case 'running':    return 'bg-blue-200 text-blue-800'
    case 'failed':     return 'bg-red-200 text-red-800'
    case 'cancelled':  return 'bg-muted text-muted-foreground'
    case 'pending':    return 'bg-amber-200 text-amber-800'
    default:           return 'bg-muted text-muted-foreground'
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
function startTraining() {
  if (!canSubmit.value || !selectedTrack.value) return
  formMessage.value = 'Training queued. (No worker wired up yet.)'
  if (previewMode.value) {
    const t = selectedTrack.value
    t.active_job = {
      id: Date.now(),
      version_name: `${t.id}-${(t.versions.length + 1).toString().padStart(2, '0')} (in progress)`,
      started_at: new Date().toISOString(),
      estimated_total_seconds: Math.round((t.data_pool.total_samples * settings.epochs) / 12),
      current_epoch: 0,
      total_epochs: settings.epochs,
      loss: 0,
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
        main_metric_value: null,
        initiated_by: 'you',
      },
      ...history.value,
    ]
  }
}
</script>
