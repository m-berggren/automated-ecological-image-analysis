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
          <div class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3">
            Training mode
          </div>

          <div class="grid grid-cols-2 gap-3">
            <button
                @click="trainingMode = 'incremental'"
                :class="[
                  'rounded-lg border p-4 text-left transition-colors',
                  trainingMode === 'incremental'
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
            {{ trainingMode === 'scratch' ? '1. Choose seed type' : '1. Choose seed type and model' }}
          </div>

          <!-- Seed type picker — shown for both modes. In incremental
               mode it gates which models can be picked to retrain. -->
          <div
            class="grid grid-cols-2 min-[860px]:grid-cols-4 gap-3 min-[860px]:gap-4 pt-1 max-h-[10rem] overflow-y-auto"
          >
            <div v-for="seed in visibleSeedTypes" :key="seed.id" class="relative shrink-0 pt-2 pr-2">
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

          <!-- Add-new-seed UI is scratch-only. In incremental you're
               picking among already-trained models, so adding a brand-
               new species would have no models to extend. -->
          <template v-if="trainingMode === 'scratch'">
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

          <!-- Incremental: model list, gated by the species picker above. -->
          <template v-if="trainingMode === 'incremental'">
            <div v-if="!selectedSeed" class="mt-3 text-sm text-muted-foreground">
              Pick a seed type above to see available models to extend.
            </div>
            <div v-else-if="!activeVersions.length" class="mt-3 text-sm text-muted-foreground">
              No trained {{ selectedSeed }} models found. Train one from scratch first.
            </div>
            <div v-else class="mt-3 space-y-2">
              <label
                v-for="version in activeVersions"
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
                    · {{ version.sample_count.toLocaleString() }} samples
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
              <div class="text-sm font-medium">Extending model {{ allVersions.find(v => v.id === selectedVersionId)?.version_name || selectedVersionId }}</div>

              <div class="text-xs text-muted-foreground">
                Upload additional samples (will be merged with existing dataset)
              </div>
            </template>

            <div class="text-xs text-muted-foreground">
              {{ uploadedFiles.length }} file(s) selected
            </div>
          </div>

          <!-- Drop zone -->
          <UploadDropZone
            class="mt-3"
            v-model:active-tab="trainingUploadTab"
            :tabs="trainingUploadTabs"
            :has-files="uploadedFiles.length > 0"
            @select="onTrainingUploadSelect"
          >
            <template #body>
              <UploadCloud class="w-8 h-8 mx-auto text-muted-foreground" />
              <div class="text-sm font-medium mt-2">
                <template v-if="uploadedFiles.length">
                  {{ uploadedFiles.length }}
                  file{{ uploadedFiles.length === 1 ? '' : 's' }}
                  added to selection
                </template>

                <template v-else>
                  Drop images and label files here, or click to browse
                </template>
              </div>

              <div class="text-xs text-muted-foreground mt-1">
                Supports .jpg, .png, .txt, .zip, or a folder containing YOLO datasets
              </div>

              <div class="text-xs text-muted-foreground mt-1">
                Each image should have a matching
                <span class="font-mono">.txt</span>
                annotation file
              </div>
            </template>
          </UploadDropZone>

        <!-- File list -->
          <div v-if="uploadedFiles.length" class="mt-3">
            <div class="flex items-center justify-between px-3 py-2 rounded-lg border border-border bg-card text-xs">
              <div class="flex items-center gap-3">
                <span class="font-medium text-foreground">
                  {{ imageFiles.length }} images
                </span>
                <span
                  :class="unpairedImages.length === 0 && imageFiles.length > 0 ? 'text-green-600' : 'text-amber-600'"
                >
                  {{ labelFiles.length }} labels
                  <span v-if="imageFiles.length === 0 && labelFiles.length > 0">
                    ⚠ Labels found but no images - each label needs a matching image
                  </span>
                  <span v-else-if="unpairedImages.length > 0">
                    ⚠ {{ unpairedImages.length }} image(s) without a matching .txt label
                  </span>
                  <span v-else>✓</span>
                </span>
                <span class="text-muted-foreground">· {{ formatFileSize(totalUploadSize) }} total</span>
              </div>
            <button
              class="text-muted-foreground hover:text-red-500 transition-colors"
              @click="clearFiles"
            >
              Clear all
            </button>
          </div>

          <ul class="mt-2 space-y-1 text-xs">
            <li
              v-for="(file, idx) in uploadedFiles.slice(0, 3)"
              :key="file.name + idx"
              class="flex items-center gap-2 px-2 py-1 rounded border border-border bg-card"
            >
              <span
                class="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium"
                :class="file.name.endsWith('.txt') ? 'bg-blue-100 text-blue-700' : 'bg-green-100 text-green-700'"
              >
                {{ file.name.endsWith('.txt') ? 'label' : 'image' }}
              </span>
              <span class="font-mono flex-1 truncate">{{ file.name }}</span>
              <span class="text-muted-foreground shrink-0">{{ formatFileSize(file.size) }}</span>
              <button class="text-red-500 shrink-0" @click="removeUpload(idx)">✕</button>
            </li>
            <li v-if="uploadedFiles.length > 3" class="px-2 py-1 text-muted-foreground italic">
              + {{ uploadedFiles.length - 3 }} more files
            </li>
          </ul>
        </div>
        </div>

        <!-- Step 3: Settings -->
          <div
            v-if="trainingMode === 'scratch' ? selectedSeed : selectedVersionId"
            class="px-5 py-4 border-b border-border"
          >
            <div class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3">
              3. Settings
            </div>

            <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <label class="text-xs text-muted-foreground space-y-1">
                <span>Epochs</span>
                <input
                  v-model.number="settings.epochs"
                  type="number"
                  min="1"
                  max="300"
                  class="w-full px-2 py-1 rounded border border-border bg-background text-sm font-mono text-foreground"
                />
              </label>

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
            </div>

            <div class="mt-2 text-xs text-muted-foreground">
              <span
                v-if="settings.train_split + settings.val_split + settings.test_split !== 100"
                class="text-amber-600"
              >
                ⚠ Splits should sum to 100%
              </span>

              <span v-else class="text-green-600">
                ✓ Split looks good
              </span>
            </div>
          </div>

        <!-- Submit -->
        <div class="px-5 py-4 flex justify-end items-center gap-3">
          <span v-if="formMessage" class="text-xs text-muted-foreground">
            {{ formMessage }}
          </span>

          <button
            :disabled="(trainingMode === 'scratch' ? !selectedSeed : !selectedVersionId) || hasActiveJob || (uploadedFiles.length > 0 && !canStartTraining)"
            class="px-4 py-2 rounded-md text-sm font-medium bg-primary text-primary-foreground disabled:opacity-50"
            @click="startTraining"
          >
            {{ hasActiveJob ? 'A job is already running' : (uploadedFiles.length > 0 && !canStartTraining ? 'Fix file mismatch to start' : 'Start training') }}
          </button>
        </div>
      </section>

      <!-- Active & Recent Jobs -->
      <section class="rounded-xl border border-border bg-card overflow-hidden shadow-md">
        <header class="px-5 py-4 bg-primary/[0.22] border-b border-border flex items-center justify-between">
          <div>
            <h2 class="font-bold text-lg tracking-tight">Active & Recent Jobs</h2>
            <p class="text-xs text-muted-foreground mt-0.5">
              Live training progress and recent results.
            </p>
          </div>
          <span class="text-xs text-muted-foreground">
            {{ jobRows.length }} {{ jobRows.length === 1 ? 'job' : 'jobs' }}
          </span>
        </header>

        <div v-if="!jobRows.length" class="px-5 py-6 text-sm text-muted-foreground">
          No active or recent jobs
        </div>

        <ul v-else class="divide-y divide-border">
          <li v-for="job in paginatedJobRows" :key="job.id" class="px-5 py-4 space-y-2">
            <!-- Top row -->
            <div class="flex items-center justify-between gap-2 flex-wrap">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-medium text-sm">{{ job.versionName }}</span>
                <span class="text-xs text-muted-foreground italic">{{ job.trackLabel }}</span>
                <span
                  class="text-xs px-2 py-0.5 rounded-full font-medium"
                  :class="job.trainingMode === 'incremental'
                    ? 'bg-purple-100 text-purple-800'
                    : 'bg-blue-100 text-blue-800'"
                >
                  {{ job.trainingMode === 'incremental' ? 'incremental' : 'scratch' }}
                </span>
              </div>

            <div class="flex items-center gap-2">
                <!-- Cancel button for running/pending jobs -->
                <button
                  v-if="job.status === 'running' || job.status === 'pending'"
                  @click="cancelTrainingJob(job)"
                  class="text-xs px-2 py-1 rounded border border-red-300 text-red-600 hover:bg-red-50 transition-colors"
                  :disabled="cancellingJobId === job.id"
                >
                  {{ cancellingJobId === job.id ? 'Cancelling...' : 'Cancel' }}
                </button>

              <span
                class="text-xs px-2 py-0.5 rounded-full font-medium"
                :class="{
                  'bg-blue-100 text-blue-800':   job.status === 'running' && !job.isEvaluating,
                  'bg-purple-100 text-purple-800': job.isEvaluating,
                  'bg-amber-100 text-amber-800': job.status === 'pending',
                  'bg-green-100 text-green-800': job.status === 'completed',
                  'bg-red-100 text-red-800':     job.status === 'failed',
                }"
              >
                <span v-if="job.isEvaluating">Evaluating…</span>
                <span v-else-if="job.status === 'running'">
                  Epoch {{ job.currentEpoch }} / {{ job.totalEpochs }}
                </span>
                <span v-else>{{ job.status }}</span>
              </span>
            </div>
          </div>

            <!-- Progress bar -->
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

        <!-- Pagination -->
        <div
          v-if="totalPages > 1"
          class="px-5 py-3 border-t border-border flex items-center justify-between text-xs text-muted-foreground"
        >
          <span>Page {{ currentPage }} of {{ totalPages }}</span>
          <div class="flex items-center gap-1">
            <button
              @click="currentPage = 1"
              :disabled="currentPage === 1"
              class="px-2 py-1 rounded border border-border hover:bg-muted disabled:opacity-40"
            >
              «
            </button>
            <button
              @click="currentPage--"
              :disabled="currentPage === 1"
              class="px-2 py-1 rounded border border-border hover:bg-muted disabled:opacity-40"
            >
              ‹
            </button>

            <!-- Dynamic page buttons with ellipsis -->
            <template v-for="page in displayedPages" :key="page">
              <button
                v-if="page !== '...'"
                @click="currentPage = page"
                class="px-2 py-1 rounded border transition-colors"
                :class="
                  page === currentPage
                    ? 'border-primary bg-primary/5 text-foreground'
                    : 'border-border hover:bg-muted'
                "
              >
                {{ page }}
              </button>
              <span v-else class="px-1 text-muted-foreground">...</span>
            </template>

            <button
              @click="currentPage++"
              :disabled="currentPage === totalPages"
              class="px-2 py-1 rounded border border-border hover:bg-muted disabled:opacity-40"
            >
              ›
            </button>
            <button
              @click="currentPage = totalPages"
              :disabled="currentPage === totalPages"
              class="px-2 py-1 rounded border border-border hover:bg-muted disabled:opacity-40"
            >
              »
            </button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { api } from '@/api'
import { confirm } from '@/lib/confirm'
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import UploadDropZone, { type UploadTab } from '@/components/UploadDropZone.vue'
import { UploadCloud } from 'lucide-vue-next'

const route = useRoute()
const loading = ref(true)
const loadError = ref('')

const tracks = ref<any[]>([])
const trainingHistory = ref<any[]>([])
const trainingMode = ref<'scratch' | 'incremental'>('scratch')
const uploadedFiles = ref<{ name: string; size: number }[]>([])
const formMessage = ref('')
const now = ref(Date.now())
const cancellingJobId = ref<number | null>(null)
let ticker: ReturnType<typeof setInterval>

const currentPage = ref(1)
const pageSize = 4
const totalPages = computed(() => Math.ceil(jobRows.value.length / pageSize))

const displayedPages = computed(() => {
  const delta = 2 // Number of pages to show on each side of current page
  const range = []
  const rangeWithDots = []
  let l
  for (let i = 1; i <= totalPages.value; i++) {
    if (i === 1 || i === totalPages.value || (i >= currentPage.value - delta && i <= currentPage.value + delta)) {
      range.push(i)
    }
  }
  for (const i of range) {
    if (l) {
      if (i - l === 2) {
        rangeWithDots.push(l + 1)
      } else if (i - l !== 1) {
        rangeWithDots.push('...')
      }
    }
    rangeWithDots.push(i)
    l = i
  }
  return rangeWithDots
})

const trainingUploadTab = ref('files')
const trainingUploadTabs: UploadTab[] = [
  {
    key: 'files',
    label: 'Files',
    mode: 'files',
    accept: '.jpg,.jpeg,.png,.zip,.txt',
  },
  {
    key: 'folder',
    label: 'Folder',
    mode: 'folder',
  },
]

// Stem-level pairing: for each image, does a matching <stem>.txt exist?
// Matching counts alone isn't enough — the user might have N images and
// N labels with completely different names. The backend filters out
// unpaired uploads in _prepare_job_dataset and raises a clear error if
// nothing's left, but we'd rather catch it here before the upload.
function stripExt(name: string): string {
  const i = name.lastIndexOf('.')
  return i > 0 ? name.slice(0, i) : name
}

const unpairedImages = computed(() => {
  const labelStems = new Set(labelFiles.value.map((f) => stripExt(f.name)))
  return imageFiles.value.filter((f) => !labelStems.has(stripExt(f.name)))
})

const canStartTraining = computed(() => {
  // Both modes require at least one image+label pair when files are
  // staged. Incremental training fine-tunes on the new batch, so an
  // unpaired-name upload there fails just like scratch.
  if (uploadedFiles.value.length === 0) return true
  return imageFiles.value.length > 0 &&
         labelFiles.value.length > 0 &&
         unpairedImages.value.length === 0
})

// Source-model options for incremental training: scoped to whichever
// species the user has selected on this page. Shows every version, not
// just the active one, so the user can fine-tune from an older release
// on purpose; the card marks the active version with a badge.
const activeVersions = computed(() => {
  if (!selectedSeed.value) return []
  const target = selectedSeed.value.toLowerCase()
  return allVersions.value
    .filter((v: any) => {
      const species = String(v.parameters?.species ?? '').toLowerCase()
      return species === target
    })
    .sort((a: any, b: any) => {
      if (a.is_active !== b.is_active) return a.is_active ? -1 : 1
      return new Date(b.trained_at ?? 0).getTime() - new Date(a.trained_at ?? 0).getTime()
    })
})

function onTrainingUploadSelect(files: File[]) {
  for (const f of files) addFile(f)
}

function addFile(f: File) {
  const name = f.name.toLowerCase()

  // Accept images, labels, and zip datasets
  if (!/\.(jpe?g|png|zip|txt)$/.test(name)) return

  // Avoid duplicate files
  const alreadyExists = actualFiles.value.some(
    (existing) =>
      existing.name === f.name &&
      existing.size === f.size
  )

  if (alreadyExists) return

  actualFiles.value.push(f)
  uploadedFiles.value.push({
    name: f.name,
    size: f.size,
  })
}

const paginatedJobRows = computed(() =>
  jobRows.value.slice((currentPage.value - 1) * pageSize, currentPage.value * pageSize)
)

const imageFiles = computed(() =>
  actualFiles.value.filter((f) => !f.name.endsWith('.txt'))
)
const labelFiles = computed(() =>
  actualFiles.value.filter((f) => f.name.endsWith('.txt'))
)

const hasActiveJob = computed(() =>
  tracks.value.some(
    (t) => t.active_job && (t.active_job.status === 'running' || t.active_job.status === 'pending')
  )
)

async function cancelTrainingJob(job: { id: number; versionName?: string; trackLabel?: string }) {
  // Use the project's confirm modal (variant: danger), matching the
  // pattern in PollinatorsTraining.vue. The browser-native confirm()
  // looked out of place against the rest of the dialogs.
  const label = job.versionName?.trim() || `${(job.trackLabel || 'seed').trim()} training`
  const ok = await confirm({
    title: 'Cancel running job',
    message:
      `Cancel "${label}"? The training worker will stop at the next ` +
      `epoch boundary and no new model version will be created.`,
    confirmLabel: 'Cancel job',
    cancelLabel: 'Keep training',
    variant: 'danger',
  })
  if (!ok) return

  cancellingJobId.value = job.id
  try {
    const res = await api(`/api/analysis/training/${job.id}/cancel/`, {
      method: 'POST',
    })

    if (res.ok) {
      formMessage.value = 'Training job cancelled'
      for (const t of tracks.value) {
        if (t.active_job?.id === job.id) {
          t.active_job = null
        }
      }
      if (pollHandle) {
        clearInterval(pollHandle)
        pollHandle = null
      }
      await loadFromApi()
    } else {
      const error = await res.text()
      formMessage.value = `Failed to cancel: ${error}`
    }
  } catch (e) {
    formMessage.value = e instanceof Error ? e.message : String(e)
  } finally {
    cancellingJobId.value = null
  }
}

const settings = reactive({
  epochs: 90,
  train_split: 80,
  val_split: 10,
  test_split:10,
})

const seedTypes = ref([
  { id: 'PEH', species: 'Pedicularis hirsuta', isCustom: false },
  { id: 'PHYCA', species: 'Phyllodoce caerulea', isCustom: false },
  { id: 'VAU', species: 'Vaccinium uliginosum', isCustom: false },
  { id: 'CAT', species: 'Cassiope tetragona', isCustom: false },
])

const selectedSeed = ref<string | null>(null)
const showAddSeed = ref(false)
const newSeedId = ref('')
const newSeedSpecies = ref('')

const selectedVersionId = ref<number | null>(null)

const totalUploadSize = computed(() =>
  uploadedFiles.value.reduce((sum, f) => sum + f.size, 0)
)

function formatMetric(v?: number) {
  return v != null ? v.toFixed(2) : '—'
}

function clearFiles() {
  uploadedFiles.value = []
  actualFiles.value = []
}

// Flatten all versions from all tracks with their track label attached
const allVersions = computed(() =>
  tracks.value.flatMap((t) =>
    (t.versions ?? []).map((v: any) => ({
      ...v,
      track_label: t.label,
      sample_count: v.sample_count ?? 0
    }))
  )
)

// In incremental mode, only show seed types that actually have a trained
// model — picking a type with no model would dead-end at "no trained X
// models found." Scratch mode shows everything since the user is
// creating a brand-new dataset (possibly for a fresh species).
const visibleSeedTypes = computed(() => {
  if (trainingMode.value !== 'incremental') return seedTypes.value
  const speciesWithModels = new Set(
    allVersions.value
      .map((v: any) => String(v.parameters?.species ?? '').toLowerCase())
      .filter(Boolean),
  )
  return seedTypes.value.filter((s) => speciesWithModels.has(s.id.toLowerCase()))
})

// Reset selection when switching mode
watch(trainingMode, () => {
  selectedSeed.value = null
  selectedVersionId.value = null

  // Set different default epochs based on training mode
  if (trainingMode.value === 'incremental') {
    settings.epochs = 45
  } else {
    settings.epochs = 90
  }
})

// Auto-pick the active version when the species changes (incremental
// mode only). Keeps a one-click flow for the common case while still
// letting the user pick a non-active version on purpose.
watch([selectedSeed, activeVersions], () => {
  if (trainingMode.value !== 'incremental') return
  const visible = activeVersions.value
  const current = selectedVersionId.value
  if (current && visible.some((v: any) => v.id === current)) return
  const active = visible.find((v: any) => v.is_active)
  selectedVersionId.value = active ? active.id : visible[0]?.id ?? null
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
    // No projected name for an in-progress job. The backend mints the
    // name only at completion, so we render an action-style label
    // ("Training PHYCA from PHYCA-01") instead of a fake version number.
    const mode = j.config?.training_mode ?? 'scratch'
    const activeLabel =
      mode === 'incremental' && j.source_model_name
        ? `Training ${t.label} from ${j.source_model_name}`
        : `Training ${t.label} from scratch`
    rows.push({
      id: j.id,
      versionName: activeLabel,
      trackLabel: '',
      isPlaceholderName: true,
      isEvaluating: j.status === 'running' && (
        ((j.current_epoch ?? 0) >= (j.total_epochs ?? 90) && (j.total_epochs ?? 0) > 0)
        || (j.current_epoch === 0 && j.total_epochs === 0 && j.hasStartedTraining)
      ),
      trainingMode: j.config?.training_mode ?? 'scratch',
      status: j.status ?? 'pending',
      currentEpoch: j.current_epoch ?? 0,
      totalEpochs: j.total_epochs ?? 90,
      progress,
      elapsed: (j.current_epoch > 0 || j.status === 'running') ? elapsedSec : null,
      duration: j.completed_at && j.started_at
        ? Math.round(
            (new Date(j.completed_at).getTime() - new Date(j.started_at).getTime()) / 1000
          )
        : null,
      errorMessage: j.errorMessage ?? j.error_message ?? null,
      startedAt: (j.status === 'running' || j.status === 'pending') && j.started_at
        ? new Date(j.started_at).toLocaleTimeString()
        : null,
      _sortKey: new Date(j.started_at ?? 0).getTime(),
    })
  }
  // Sort newest jobs first
  rows.sort((a, b) => b._sortKey - a._sortKey)

  for (const h of trainingHistory.value) {
    // Failed jobs and any legacy completed jobs that never linked a
    // resulting_model fall back to "Job #N" rather than rendering blank.
    rows.push({
      id: h.id,
      versionName: h.version_name ?? `Job #${h.id}`,
      trackLabel: h.version_name ? h.track_label : '',
      isPlaceholderName: !h.version_name,
      trainingMode: h.training_mode ?? 'scratch',
      status: h.status,
      currentEpoch: h.epochs_total,
      totalEpochs: h.epochs_total,
      progress: h.status === 'completed' ? 100 : 0,
      elapsed: null,
      duration: h.duration_seconds,
      errorMessage: h.error_message,
      startedAt: null,
      _sortKey: 0,
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

let pollHandle: ReturnType<typeof setInterval> | null = null

function startPolling(jobId: number) {
  if (pollHandle) clearInterval(pollHandle)
  pollHandle = setInterval(async () => {
    try {
      const res = await api(`/api/analysis/training/${jobId}/`)
      if (!res.ok) return
      const job = await res.json()

      console.log('Poll response:', job.id, job.status, job.current_epoch, job.total_epochs)

      for (const t of tracks.value) {
        if (t.active_job?.id === jobId) {
          console.log('Found track, updating:', t.id, t.active_job.current_epoch, '→', job.current_epoch)
          t.active_job = {
            ...t.active_job,
            current_epoch: job.current_epoch ?? 0,
            total_epochs: job.total_epochs ?? 90,
            status: job.status,
            hasStartedTraining: t.active_job.hasStartedTraining || (job.current_epoch ?? 0) > 0,
            errorMessage: job.error_message ?? null,
            completed_at: job.completed_at ?? null,
          }
        }
      }

      if (job.status === 'completed' || job.status === 'failed') {
        clearInterval(pollHandle!)
        pollHandle = null
        formMessage.value =
          job.status === 'completed'
            ? 'Training complete!'
            : `Training failed: ${job.error_message}`
        // Only reload after job finishes to get the new ModelVersion
        setTimeout(async () => {
          await loadFromApi()
        }, 2000)
      }
    } catch {}
  }, 3000)
}

const actualFiles = ref<File[]>([])

function removeUpload(i: number) {
  uploadedFiles.value.splice(i, 1)
  actualFiles.value.splice(i, 1)
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
      await loadFromApi()
    }
  } catch (e) {
    loadError.value = String(e)
  } finally {
    loading.value = false
  }
})

async function loadFromApi() {
  // Don't reload if we're actively polling
  if (pollHandle) return

  const versionsRes = await api('/api/analysis/models/?module=seeds')
  if (!versionsRes.ok) {
    loadError.value = `Models: HTTP ${versionsRes.status}`
    return
  }
  const versions: any[] = await versionsRes.json()

  const speciesMap = new Map<string, any>()
  for (const seed of seedTypes.value) {
    speciesMap.set(seed.id.toLowerCase(), {
      id: seed.id,
      label: seed.id,
      species: seed.species,
      versions: [],
      active_job: null,
      data_pool: { total_samples: 0, new_since_active: 0 },
    })
  }

  for (const v of versions) {
    const species = (v.parameters?.species ?? v.version_name.split('-')[0]).toLowerCase()

    // Create track for manually added seed types
    if (!speciesMap.has(species)) {
      speciesMap.set(species, {
        id: species.toUpperCase(),
        label: species.toUpperCase(),
        species: species,
        versions: [],
        active_job: null,
        data_pool: { total_samples: 0, new_since_active: 0 },
      })
    }

    const track = speciesMap.get(species)
    if (track) {
      track.versions.push({ ...v, sample_count: v.sample_count ?? 0 })
    }
  }

  tracks.value = Array.from(speciesMap.values())

  const jobsRes = await api('/api/analysis/training/?module=seeds')
  if (jobsRes.ok) {
    const jobs: any[] = await jobsRes.json()

    // Active jobs: no projected name. The backend mints the name only at
    // completion (lineage-aware: <SPECIES>-NN for scratch, <source>.K for
    // incremental), so we render a placeholder until the row exists.
    for (const job of jobs.filter((j) => j.status === 'running' || j.status === 'pending')) {
      const species = (job.config?.species ?? '').toLowerCase()
      const track = tracks.value.find((t) => t.id.toLowerCase() === species)
      if (track) {
        track.active_job = {
          id: job.id,
          // Placeholder name for the in-progress row. trainingMode +
          // source_model_name drive the prettier label in the template.
          version_name: '',
          source_model_name: job.source_model_name ?? null,
          started_at: job.started_at,
          current_epoch: job.current_epoch,
          total_epochs: job.total_epochs,
          status: job.status,
          loss: job.metrics?.loss ?? 0,
          errorMessage: job.error_message ?? null,
          completed_at: job.completed_at ?? null,
          config: job.config,
        }
        if (!pollHandle) startPolling(job.id)
      }
    }

    // History (completed + failed), newest first. Use the backend's
    // resulting_model_name so the training page and the Models page agree
    // on the name for the same model.
    trainingHistory.value = jobs
      .filter((j) => j.status === 'completed' || j.status === 'failed')
      .sort((a, b) => b.id - a.id)
      .map((j) => {
        const species = (j.config?.species ?? '').toLowerCase()
        return {
          id: j.id,
          version_name: j.resulting_model_name ?? null,
          source_model_name: j.source_model_name ?? null,
          track_label: species.toUpperCase() || '?',
          status: j.status,
          training_mode: j.config?.training_mode ?? 'scratch',
          epochs_total: j.total_epochs,
          duration_seconds:
            j.completed_at && j.started_at
              ? Math.round((new Date(j.completed_at).getTime() - new Date(j.started_at).getTime()) / 1000)
              : null,
          error_message: j.error_message || null,
        }
      })
  }
}

async function startTraining() {
  formMessage.value = ''

  if (trainingMode.value === 'scratch' && !uploadedFiles.value.length) {
    formMessage.value = 'Please upload training images first.'
    return
  }

  // Backend now wants ratios in [0, 1), not percentages, and runs the
  // split inside the job. The upload endpoint returns a staging_id we
  // hand to /start/ so it knows which uploaded files belong to this job.
  const valRatio = settings.val_split / 100
  const testRatio = settings.test_split / 100

  const speciesLower =
    trainingMode.value === 'scratch'
      ? selectedSeed.value!.toLowerCase()
      : allVersions.value
          .find((v) => v.id === selectedVersionId.value)
          ?.track_label.toLowerCase()

  const basePayload: Record<string, unknown> = {
    species: speciesLower,
    training_mode: trainingMode.value,
    epochs: settings.epochs,
    val_ratio: valRatio,
    test_ratio: testRatio,
  }
  if (trainingMode.value === 'incremental') {
    basePayload.source_model_id = selectedVersionId.value
  }

  try {
    if (!actualFiles.value.length) {
      formMessage.value = 'Upload training images before starting a job.'
      return
    }

    formMessage.value =
      trainingMode.value === 'scratch'
        ? 'Uploading training data...'
        : 'Uploading additional training data...'
    const formData = new FormData()
    formData.append('species', speciesLower!)
    for (const file of actualFiles.value) formData.append('files', file)

    const uploadRes = await api('/api/seeds/training/upload-data/', {
      method: 'POST',
      body: formData,
    })
    if (!uploadRes.ok) {
      formMessage.value = (await uploadRes.text()) || 'Upload failed'
      return
    }
    const uploadData = await uploadRes.json()
    const stagingId = uploadData?.staging_id
    if (!stagingId) {
      formMessage.value = 'Upload succeeded but staging_id was missing.'
      return
    }

    formMessage.value = 'Starting training job...'
    const res = await api('/api/seeds/training/start/', {
      method: 'POST',
      body: JSON.stringify({ ...basePayload, staging_id: stagingId }),
    })
    if (!res.ok) {
      formMessage.value = (await res.text()) || `HTTP ${res.status}`
      return
    }
    const job = await res.json()

    // Reload to get the correct version number from the full jobs list
    await loadFromApi()
    formMessage.value = `Job #${job.id} started — training ${(speciesLower ?? '').toUpperCase()}`
    currentPage.value = 1
  } catch (e) {
    formMessage.value = e instanceof Error ? e.message : String(e)
  }
}
</script>
