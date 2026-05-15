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
          <h2 class="font-bold text-lg tracking-tight">New Training Job</h2>
          <p class="text-xs text-muted-foreground mt-0.5">
            Select a seed species and start training. Training that runs on CPU may take a long
            time.
          </p>
        </header>

        <!-- Training mode -->
        <div class="px-5 py-4 border-b border-border">
          <div
            class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3"
          >
            Training mode
          </div>

          <div class="grid grid-cols-2 gap-3">
            <button
              @click="trainingMode = 'retrain'"
              :class="[
                'rounded-lg border p-4 text-left transition-colors',
                trainingMode === 'retrain'
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:border-primary/40',
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
                  : 'border-border hover:border-primary/40',
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
          <div
            class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3"
          >
            {{ trainingMode === 'scratch' ? '1. Choose seed type' : '1. Choose model to retrain' }}
          </div>

          <!-- SCRATCH: seed type picker -->
          <template v-if="trainingMode === 'scratch'">
            <div
              class="grid grid-cols-2 min-[860px]:grid-cols-4 gap-3 min-[860px]:gap-4 pt-1 max-h-[10rem] overflow-y-auto"
            >
              <div v-for="seed in seedTypes" :key="seed.id" class="relative shrink-0 pt-2 pr-2">
                <button
                  v-if="seed.isCustom"
                  @click.stop="removeSeed(seed.id)"
                  class="absolute -top-0 -right-0 w-5 h-5 flex items-center justify-center rounded-full bg-green-900 text-white text-xs z-10"
                >
                  ×
                </button>
                <button
                  @click="selectedSeed = seed.id"
                  :class="[
                    'group w-full flex items-center px-3 py-2 rounded-lg border-2 text-left transition-all overflow-hidden',
                    selectedSeed === seed.id
                      ? 'border-primary bg-primary/5'
                      : 'border-border bg-background hover:border-primary/40',
                  ]"
                >
                  <span class="text-sm font-semibold shrink-0">{{ seed.id }}</span>
                  <span
                    v-if="seed.species"
                    class="ml-2 overflow-hidden whitespace-nowrap text-[11px] text-muted-foreground italic max-w-0 group-hover:max-w-[100px] opacity-0 group-hover:opacity-100 transition-all duration-200"
                  >
                    · {{ seed.species }}
                  </span>
                </button>
              </div>
            </div>

            <button
              @click="showAddSeed = true"
              class="mt-3 w-full rounded-lg border-2 border-dashed border-border px-4 py-2 text-sm text-muted-foreground transition hover:border-primary hover:text-primary"
            >
              + Add new seed type
            </button>

            <div
              v-if="showAddSeed"
              class="mt-3 rounded-lg border border-border bg-background p-3 space-y-3"
            >
              <input
                v-model="newSeedId"
                placeholder="Code name (e.g. PEH)"
                class="w-full px-3 py-2 text-sm border border-border rounded-md"
              />
              <input
                v-model="newSeedSpecies"
                placeholder="Species name (optional)"
                class="w-full px-3 py-2 text-sm border border-border rounded-md"
              />
              <div class="flex gap-2">
                <button
                  @click="addSeed"
                  class="px-3 py-1.5 rounded-md text-sm bg-primary text-primary-foreground"
                >
                  Add
                </button>
                <button
                  @click="cancelAddSeed"
                  class="px-3 py-1.5 rounded-md text-sm border border-border"
                >
                  Cancel
                </button>
              </div>
            </div>
          </template>

          <!-- RETRAIN: model version picker -->
          <template v-else>
            <div v-if="!allVersions.length" class="text-sm text-muted-foreground">
              No trained models found. Train a new model first.
            </div>
            <div v-else class="space-y-2">
              <label
                v-for="version in allVersions"
                :key="version.id"
                class="flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors"
                :class="
                  selectedVersionId === version.id
                    ? 'border-primary bg-primary/5'
                    : 'border-border hover:border-primary/40'
                "
              >
                <input
                  type="radio"
                  :value="version.id"
                  v-model="selectedVersionId"
                  class="mt-0.5"
                />
                <div class="flex-1 min-w-0">
                  <div class="flex items-baseline gap-2 flex-wrap">
                    <span class="font-medium text-sm">{{ version.version_name }}</span>
                    <span
                      v-if="version.is_active"
                      class="text-xs px-2 py-0.5 rounded-full bg-green-300 text-green-900 font-medium"
                    >
                      active
                    </span>
                    <span class="text-xs text-muted-foreground italic">{{
                      version.track_label
                    }}</span>
                  </div>
                  <div class="text-xs text-muted-foreground mt-0.5">
                    MAE
                    <span class="font-mono text-foreground">{{
                      formatMetric(version.metrics?.mae)
                    }}</span>
                    · F1
                    <span class="font-mono text-foreground">{{
                      formatMetric(version.metrics?.f1)
                    }}</span>
                    · {{ version.samples.toLocaleString() }} samples
                  </div>
                </div>
              </label>
            </div>
          </template>
        </div>

        <!-- Step 2 -->
        <div
          v-if="trainingMode === 'scratch' ? selectedSeed : selectedVersionId"
          class="px-5 py-4 border-b border-border"
        >
          <div
            class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3"
          >
            2. Training data
          </div>

          <div class="rounded-lg border border-border bg-muted/20 p-4 space-y-2">
            <!-- Scratch -->

            <template v-if="trainingMode === 'scratch'">
              <div class="text-sm font-medium">New dataset for {{ selectedSeed }}</div>

              <div class="text-xs text-muted-foreground">
                Upload the full dataset for this new species
              </div>
            </template>

            <!-- Retrain -->

            <template v-else>
              <div class="text-sm font-medium">Extending model {{ selectedVersionId }}</div>

              <div class="text-xs text-muted-foreground">
                Upload additional samples (will be merged with existing dataset)
              </div>
            </template>

            <div class="text-xs text-muted-foreground">
              {{ uploadedFiles.length }} file(s) selected
            </div>
          </div>

          <!-- Drop zone -->

          <div
            class="mt-3 rounded-lg border-2 border-dashed border-border p-5 text-center cursor-pointer hover:bg-muted/20"
            :class="{ 'border-primary bg-primary/5': dragOver }"
            @dragover.prevent="dragOver = true"
            @dragleave.prevent="dragOver = false"
            @drop.prevent="onDrop"
            @click="triggerFilePicker"
          >
            <div class="text-sm font-medium">Drop images or click to upload</div>

            <div class="text-xs text-muted-foreground mt-1">.jpg, .png, .zip supported</div>

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
            :disabled="trainingMode === 'scratch' ? !selectedSeed : !selectedVersionId"
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
          <h2 class="font-bold text-lg tracking-tight">Active & Recent Jobs</h2>
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
                  'bg-blue-100 text-blue-800': job.status === 'running',
                  'bg-green-100 text-green-800': job.status === 'completed',
                  'bg-red-100 text-red-800': job.status === 'failed',
                }"
              >
                {{
                  job.status === 'running'
                    ? `Epoch ${job.currentEpoch} / ${job.totalEpochs}`
                    : job.status
                }}
              </span>
            </div>

            <!-- Progress bar (running only) -->
            <div
              v-if="job.status === 'running'"
              class="w-full h-1.5 rounded-full bg-muted overflow-hidden"
            >
              <div
                class="h-full bg-primary rounded-full transition-all duration-1000"
                :style="{ width: job.progress + '%' }"
              />
            </div>

            <!-- Stats row -->
            <div class="flex gap-4 text-xs text-muted-foreground flex-wrap">
              <span v-if="job.status === 'running'">
                Elapsed
                <span class="font-mono text-foreground">{{ formatDuration(job.elapsed) }}</span>
              </span>
              <span v-if="job.status === 'completed'">
                Duration
                <span class="font-mono text-foreground">{{ formatDuration(job.duration) }}</span>
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
import { api } from '@/api'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'

const route = useRoute()
const loading = ref(true)
const loadError = ref('')

const tracks = ref<any[]>([])
const trainingHistory = ref<any[]>([])
const trainingMode = ref<'scratch' | 'retrain'>('scratch')
const uploadedFiles = ref<{ name: string; size: number }[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)
const dragOver = ref(false)
const formMessage = ref('')
const now = ref(Date.now())
let ticker: ReturnType<typeof setInterval>

const seedTypes = ref([
  { id: 'PEH', species: 'Pisum sativum', isCustom: false },
  { id: 'PHYCA', species: 'Phacelia tanacetifolia', isCustom: false },
  { id: 'VAU', species: 'Vicia sativa', isCustom: false },
  { id: 'CAT', species: 'Carthamus tinctorius', isCustom: false },
])

const selectedSeed = ref<string | null>(null)
const showAddSeed = ref(false)
const newSeedId = ref('')
const newSeedSpecies = ref('')

const selectedVersionId = ref<number | null>(null)

// Flatten all versions from all tracks with their track label attached
const allVersions = computed(() =>
  tracks.value.flatMap((t) => (t.versions ?? []).map((v: any) => ({ ...v, track_label: t.label }))),
)

// Reset selection when switching mode
watch(trainingMode, () => {
  selectedSeed.value = null
  selectedVersionId.value = null
})

const canSubmit = computed(() => {
  if (trainingMode.value === 'scratch') return !!selectedSeed.value
  return !!selectedVersionId.value
})

function addSeed() {
  if (!newSeedId.value.trim()) return
  const id = newSeedId.value.trim().toUpperCase()
  if (seedTypes.value.some((s) => s.id === id)) return
  seedTypes.value.push({ id, species: newSeedSpecies.value.trim(), isCustom: true })
  cancelAddSeed()
}

function cancelAddSeed() {
  showAddSeed.value = false
  newSeedId.value = ''
  newSeedSpecies.value = ''
}

function removeSeed(id: string) {
  seedTypes.value = seedTypes.value.filter((s) => s.id !== id)
  if (selectedSeed.value === id) selectedSeed.value = null
}

const jobRows = computed(() => {
  const rows: any[] = []

  for (const t of tracks.value) {
    const j = t.active_job
    if (!j) continue
    const startedAt = j.started_at
      ? new Date(j.started_at)
      : new Date(now.value + (j.started_at_offset_seconds ?? 0) * 1000)
    const elapsedSec = Math.floor((now.value - startedAt.getTime()) / 1000)
    const progress = j.total_epochs > 0 ? Math.round((j.current_epoch / j.total_epochs) * 100) : 0
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

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`
}

function startTraining() {
  if (trainingMode.value === 'scratch') {
    if (!selectedSeed.value) return
    formMessage.value = `Training new model for ${selectedSeed.value}`
    return
  }
  if (!selectedVersionId.value) return
  formMessage.value = `Retraining model ${selectedVersionId.value}`
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
  ticker = setInterval(() => {
    now.value = Date.now()
  }, 1000)
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
