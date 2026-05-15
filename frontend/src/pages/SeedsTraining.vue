<template>
  <PageHeader title="Training" subtitle="Train seed detection models" />

  <div class="flex-1 overflow-auto">
    <div v-if="loading" class="p-8 text-sm text-muted-foreground">Loading…</div>
    <div v-else-if="loadError" class="p-8 text-sm text-red-600">{{ loadError }}</div>

    <div v-else class="p-6 space-y-4 max-w-4xl mx-auto w-full">

      <!-- Card -->
      <section class="rounded-xl border border-border bg-card overflow-hidden shadow-md">

        <!-- Header -->
        <header class="px-5 py-4 bg-primary/[0.22] border-b border-border">
          <h2 class="font-bold text-lg tracking-tight">New training job</h2>
          <p class="text-xs text-muted-foreground mt-0.5">
            Select a seed species and start training. Training that runs on CPU may take a long time.
          </p>
        </header>

        <!-- Training mode -->
        <div class="px-5 py-4 border-b border-border">
          <div class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3">
            Training mode
          </div>

          <div class="grid grid-cols-2 gap-3">
            <button
              @click="trainingMode = 'retrain'"
              :class="[
                'rounded-lg border p-4 text-left transition-colors',
                trainingMode === 'retrain'
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:border-primary/40'
              ]"
            >
              <div class="font-medium text-sm">Retrain model</div>
              <div class="text-xs text-muted-foreground mt-1">
                Improve an existing trained model
              </div>
            </button>

            <button
              @click="trainingMode = 'scratch'"
              :class="[
                'rounded-lg border p-4 text-left transition-colors',
                trainingMode === 'scratch'
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:border-primary/40'
              ]"
            >
              <div class="font-medium text-sm">Train new model</div>
              <div class="text-xs text-muted-foreground mt-1">
                Create a brand new model from scratch
              </div>
            </button>
          </div>
        </div>

        <!-- Step 1 -->
        <div class="px-5 py-4 border-b border-border">

          <div class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3">
            {{ trainingMode === 'scratch'
              ? '1. Choose seed type'
              : '1. Choose model to retrain'
            }}
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

                <!-- Always show base info -->
                <div class="flex items-baseline gap-2 flex-wrap">
                  <span class="font-medium text-sm">{{ track.label }}</span>
                  <span class="text-xs text-muted-foreground italic">{{ track.species }}</span>

                  <span
                    v-if="trainingMode === 'retrain' && activeVersion(track)"
                    class="text-xs px-2 py-0.5 rounded-full bg-green-300 text-green-900 font-medium"
                  >
                    {{ activeVersion(track)!.version_name }}
                  </span>
                </div>

                <div v-if="trainingMode === 'scratch'" class="text-xs text-muted-foreground mt-1">
                    New model will be saved as
                  <span class="font-mono text-foreground">{{ generateVersionName(track) }}</span>
                </div>

                <!-- Retrain mode details -->
                <div v-else-if="activeVersion(track)" class="text-xs text-muted-foreground mt-1">
                  MAE
                  <span class="font-mono ml-1 text-foreground">
                    {{ formatMetric(activeMainMetric(track)) }}
                  </span>

                  · {{ track.data_pool.total_samples.toLocaleString() }} samples
                </div>

              </div>
            </label>
          </div>
        </div>

        <!-- Step 2 -->
        <div v-if="selectedTrackId" class="px-5 py-4 border-b border-border">

          <div class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3">
            2. Training data
          </div>

          <div class="rounded-lg border border-border bg-muted/20 p-4 space-y-2">
            <div class="text-sm font-medium">
              {{ totalPoolSamples.toLocaleString() }} samples available
            </div>
            <div class="text-xs text-muted-foreground">
              {{ selectedTrack.data_pool.total_samples.toLocaleString() }} existing ·
              {{ uploadedFiles.length }} uploaded
            </div>
          </div>

          <div
            class="mt-3 rounded-lg border-2 border-dashed border-border p-5 text-center cursor-pointer hover:bg-muted/20"
            :class="{ 'border-primary bg-primary/5': dragOver }"
            @dragover.prevent="dragOver = true"
            @dragleave.prevent="dragOver = false"
            @drop.prevent="onDrop"
            @click="triggerFilePicker"
          >
            <div class="text-sm font-medium">
              Drop images or click to upload
            </div>
            <div class="text-xs text-muted-foreground mt-1">
              .jpg, .png, .zip supported
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

          <ul v-if="uploadedFiles.length" class="mt-3 space-y-1 text-xs">
            <li
              v-for="(file, idx) in uploadedFiles"
              :key="file.name + idx"
              class="flex items-center gap-2 px-2 py-1 rounded border border-border bg-card"
            >
              <span class="font-mono flex-1 truncate">{{ file.name }}</span>
              <span class="text-muted-foreground">{{ formatFileSize(file.size) }}</span>
              <button class="text-red-500" @click="removeUpload(idx)">✕</button>
            </li>
          </ul>

        </div>

        <!-- Submit -->
        <div class="px-5 py-4 flex justify-end items-center gap-3">
          <span v-if="formMessage" class="text-xs text-muted-foreground">
            {{ formMessage }}
          </span>

          <button
            :disabled="!canSubmit"
            class="px-4 py-2 rounded-md text-sm font-medium bg-primary text-primary-foreground disabled:opacity-50"
            @click="startTraining"
          >
            Start training
          </button>
        </div>

      </section>

      <!-- Active & Recent Jobs -->
      <section class="rounded-xl border border-border bg-card overflow-hidden shadow-md">

        <header class="px-5 py-4 bg-primary/[0.22] border-b border-border">
          <h2 class="font-bold text-lg tracking-tight">Active & recent jobs</h2>
          <p class="text-xs text-muted-foreground mt-0.5">
            Live training progress and recent results.
          </p>
        </header>

        <div v-if="!jobRows.length" class="px-5 py-6 text-sm text-muted-foreground">
          No active or recent jobs
        </div>

        <ul v-else class="divide-y divide-border">
          <li v-for="job in jobRows" :key="job.id" class="px-5 py-4 space-y-2">

            <!-- Top row -->
            <div class="flex items-center justify-between gap-2 flex-wrap">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-medium text-sm">{{ job.versionName }}</span>
                <span class="text-xs text-muted-foreground italic">{{ job.trackLabel }}</span>
              </div>

              <!-- Status badge -->
              <span
                class="text-xs px-2 py-0.5 rounded-full font-medium"
                :class="{
                  'bg-blue-100 text-blue-800':   job.status === 'running',
                  'bg-green-100 text-green-800': job.status === 'completed',
                  'bg-red-100 text-red-800':     job.status === 'failed',
                }"
              >
                {{ job.status === 'running' ? `Epoch ${job.currentEpoch} / ${job.totalEpochs}` : job.status }}
              </span>
            </div>

            <!-- Progress bar (running only) -->
            <div v-if="job.status === 'running'" class="w-full h-1.5 rounded-full bg-muted overflow-hidden">
              <div
                class="h-full bg-primary rounded-full transition-all duration-1000"
                :style="{ width: job.progress + '%' }"
              />
            </div>

            <!-- Stats row -->
            <div class="flex gap-4 text-xs text-muted-foreground flex-wrap">
              <span v-if="job.status === 'running'">
                Elapsed <span class="font-mono text-foreground">{{ formatDuration(job.elapsed) }}</span>
              </span>
              <span v-if="job.status === 'completed'">
                Duration <span class="font-mono text-foreground">{{ formatDuration(job.duration) }}</span>
              </span>
              <span v-if="job.status === 'failed'" class="text-red-500">
                {{ job.errorMessage }}
              </span>
              <span v-if="job.startedAt">
                Started <span class="font-mono text-foreground">{{ job.startedAt }}</span>
              </span>
            </div>
          </li>
        </ul>

      </section>

    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import { api } from '@/api'

const route = useRoute()
const loading = ref(true)
const loadError = ref('')

const tracks = ref<any[]>([])
const trainingHistory = ref<any[]>([])
const selectedTrackId = ref<string | null>(null)
const trainingMode = ref<'retrain' | 'scratch'>('retrain')
const uploadedFiles = ref<{ name: string; size: number }[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)
const dragOver = ref(false)
const formMessage = ref('')
const now = ref(Date.now())
let ticker: ReturnType<typeof setInterval>

const selectedTrack = computed(() =>
  tracks.value.find(t => t.id === selectedTrackId.value) ?? null
)

const totalPoolSamples = computed(() =>
  selectedTrack.value
    ? selectedTrack.value.data_pool.total_samples + uploadedFiles.value.length
    : 0
)

const canSubmit = computed(() =>
  !!selectedTrack.value && totalPoolSamples.value > 0
)

const jobRows = computed(() => {
  const rows: any[] = []

  for (const t of tracks.value) {
    const j = t.active_job
    if (!j) continue
    const startedAt = j.started_at
      ? new Date(j.started_at)
      : new Date(now.value + (j.started_at_offset_seconds ?? 0) * 1000)
    const elapsedSec = Math.floor((now.value - startedAt.getTime()) / 1000)
    const progress = j.total_epochs > 0
      ? Math.round((j.current_epoch / j.total_epochs) * 100)
      : 0
    rows.push({
      id: j.id,
      versionName: j.version_name,
      trackLabel: t.label,
      status: 'running',
      currentEpoch: j.current_epoch,
      totalEpochs: j.total_epochs,
      progress,
      elapsed: elapsedSec,
      duration: null,
      errorMessage: null,
    })
  }

  for (const h of trainingHistory.value) {
    rows.push({
      id: h.id,
      versionName: h.version_name,
      trackLabel: h.track_label,
      status: h.status,
      currentEpoch: h.epochs_total,
      totalEpochs: h.epochs_total,
      progress: h.status === 'completed' ? 100 : 0,
      elapsed: null,
      duration: h.duration_seconds,
      errorMessage: h.error_message,
    })
  }

  return rows
})

function formatDuration(seconds: number) {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

function activeVersion(t: any) {
  return t.versions?.find((v: any) => v.is_active) ?? null
}

function activeMainMetric(t: any) {
  return activeVersion(t)?.metrics?.mae
}

function formatMetric(v?: number) {
  return v != null ? v.toFixed(2) : '—'
}

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`
}

function generateVersionName(track: any) {
  const next = (track.versions.length + 1).toString().padStart(2, '0')
  return `${track.id}-${next}`
}

function startTraining() {
  if (!selectedTrack.value) return
  const t = selectedTrack.value
  t.active_job = {
    id: Date.now(),
    version_name: generateVersionName(t),
    started_at: new Date().toISOString(),
    current_epoch: 0,
    total_epochs: 90,
    loss: 0,
  }
  formMessage.value = trainingMode.value === 'scratch'
    ? 'New model training started.'
    : 'Model retraining started.'
}

function triggerFilePicker() {
  fileInputRef.value?.click()
}

function onFilePicked(e: Event) {
  const files = (e.target as HTMLInputElement).files
  if (!files) return
  for (const f of Array.from(files)) {
    uploadedFiles.value.push({ name: f.name, size: f.size })
  }
}

function onDrop(e: DragEvent) {
  dragOver.value = false
  if (!e.dataTransfer?.files) return
  for (const f of Array.from(e.dataTransfer.files)) {
    uploadedFiles.value.push({ name: f.name, size: f.size })
  }
}

function removeUpload(i: number) {
  uploadedFiles.value.splice(i, 1)
}

onMounted(async () => {
  ticker = setInterval(() => { now.value = Date.now() }, 1000)
  try {
    if (import.meta.env.DEV && route.query.preview === 'default') {
      const { default: mocks } = await import('@/mocks/seed-models.json')
      const raw = (mocks as any).default
      tracks.value = raw.tracks
      trainingHistory.value = raw.training_history ?? []
    } else {
      const res = await api('/api/analysis/models/?module=seeds')
      const data = await res.json()
      tracks.value = data.tracks ?? data
      trainingHistory.value = data.training_history ?? []
    }
  } catch (e) {
    loadError.value = String(e)
  } finally {
    loading.value = false
  }
})

onUnmounted(() => clearInterval(ticker))
</script>