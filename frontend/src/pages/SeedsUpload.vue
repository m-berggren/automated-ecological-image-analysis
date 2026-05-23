<template>
  <PageHeader title="Upload" subtitle="Add seed images to start a detection run" />
  <SeedsStepper current="upload" />

  <div class="flex-1 overflow-y-auto h-full p-8 space-y-6 max-w-3xl mx-auto w-full">
    <!-- Run details -->
    <section class="rounded-xl border border-border bg-surface p-5 space-y-4">
      <div>
        <h2 class="text-sm font-semibold">Run details</h2>
        <p class="text-xs text-muted-foreground mt-1">
          Configure the seed analysis pipeline before uploading images.
        </p>
      </div>

      <div class="space-y-2">
        <label class="block text-xs text-muted-foreground">Run Name</label>

        <input
          v-model="runName"
          type="text"
          placeholder="e.g. Seeds B — July 2026"
          class="w-full px-3 py-2 text-sm rounded-md border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
      </div>

      <div class="space-y-2">
        <label class="block text-xs text-muted-foreground">Run Notes</label>

        <textarea
          v-model="runNotes"
          rows="3"
          placeholder="e.g. PEH test v2, lots of debris, crowded seeds"
          class="w-full px-3 py-2 text-sm rounded-md border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
      </div>
    </section>

    <!-- Seed type -->
    <section class="rounded-xl border border-border bg-surface p-5 space-y-4">
      <h2 class="text-sm font-semibold">Seed type</h2>
      <p class="text-xs text-muted-foreground">Each batch must contain a single species.</p>

      <!-- Seed list -->
      <div
        v-if="seedTypes.length === 0"
        class="text-sm text-amber-700 p-4 bg-amber-50/50 border border-amber-200 rounded-lg"
      >
        No trained models found in the database. You must train or register a model on the
        <RouterLink to="/seeds/training" class="font-bold underline hover:text-amber-900"
          >Training page</RouterLink
        >
        before you can upload images.
      </div>

      <div v-else class="grid grid-cols-4 gap-3 pt-1 max-h-[10rem] overflow-y-auto">
        <div v-for="seed in seedTypes" :key="seed.id" class="relative shrink-0 pt-2 pr-2">
          <button
            @click="selectedSeed = seed.id"
            :class="[
              'group w-36 flex items-center px-3 py-2 rounded-lg border-2 text-left transition-all overflow-hidden',
              selectedSeed === seed.id
                ? 'border-primary bg-primary/5'
                : 'border-border bg-background hover:border-primary/40',
            ]"
          >
            <span class="text-sm font-semibold shrink-0">
              {{ seed.id }}
            </span>
          </button>
        </div>
      </div>
    </section>

    <!-- Detection settings -->
    <section class="rounded-xl border border-border bg-surface p-5 space-y-5">
      <div>
        <h2 class="text-sm font-semibold">Detection settings</h2>
      </div>

      <!-- Model selector -->
      <div class="space-y-2">
        <div class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3">
          Choose model version
        </div>

        <!-- Empty state -->
        <div
          v-if="!activeModelVersions.length"
          class="rounded-lg border border-border bg-muted/20 p-4 text-sm"
        >
          <span class="text-muted-foreground"> No active models yet. </span>

          <RouterLink to="/seeds/training" class="ml-1 text-primary hover:underline font-medium">
            Go to the training page
          </RouterLink>

          <span class="text-muted-foreground"> to create one. </span>
        </div>

        <!-- Cards -->
        <div v-else class="space-y-2">
          <label
            v-for="model in activeModelVersions"
            :key="model.id"
            class="flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors"
            :class="
              config.model_version_id === model.id
                ? 'border-primary bg-primary/5'
                : 'border-border hover:border-primary/40'
            "
          >
            <input
              type="radio"
              name="model-version"
              class="mt-0.5"
              :checked="config.model_version_id === model.id"
              @change="config.model_version_id = model.id"
            />

            <div class="flex-1 min-w-0">
              <!-- Top row -->
              <div class="flex items-baseline gap-2 flex-wrap">
                <span class="font-medium text-sm">
                  {{ model.version_name }}
                </span>

                <span class="text-xs text-muted-foreground italic">
                  {{ model.kind }}
                </span>

                <span
                  class="text-xs px-2 py-0.5 rounded-full bg-green-300 text-green-900 font-medium"
                >
                  Active
                </span>
              </div>

              <!-- Subtitle -->
              <div class="text-xs text-muted-foreground mt-1">
                Seed detection model ready for inference
              </div>
            </div>
          </label>
        </div>
      </div>

      <!-- Advanced settings -->
      <div class="flex flex-wrap items-center gap-x-6 gap-y-3 pt-2 border-t border-border">
        <!-- Confidence -->
        <label class="flex items-center gap-2 text-sm">
          <span class="text-xs text-muted-foreground"> Confidence threshold </span>

          <input
            v-model.number="config.confidence_threshold"
            type="number"
            min="0"
            max="1"
            step="0.05"
            class="w-20 px-2 py-1 rounded border border-border bg-background text-sm font-mono"
          />
        </label>

        <!-- Slice overlap -->
        <label class="flex items-center gap-2 text-sm">
          <span class="text-xs text-muted-foreground"> Slice overlap </span>

          <input
            v-model.number="config.slice_overlap_ratio"
            type="number"
            min="0"
            max="1"
            step="0.05"
            class="w-20 px-2 py-1 rounded border border-border bg-background text-sm font-mono"
          />
        </label>
      </div>
    </section>

    <!-- Upload -->
    <div class="relative">
      <div
        v-if="!selectedSeed || !config.model_version_id"
        class="absolute inset-0 z-10 bg-surface/60 backdrop-blur-[1px] flex items-center justify-center rounded-xl border border-border"
      >
        <p
          class="text-sm font-medium bg-background px-4 py-2 rounded-md shadow-sm border border-border"
        >
          Select a seed species and model version first
        </p>
      </div>
      <section
        class="rounded-xl border-2 border-dashed border-border bg-surface p-10 text-center transition-colors"
        :class="{
          'border-primary bg-primary/5': dragOver,
          'opacity-60': creatingUpload,
        }"
        @dragover.prevent="dragOver = true"
        @dragleave.prevent="onDragLeave"
        @drop.prevent="onDrop"
      >
        <UploadCloud class="w-10 h-10 mx-auto text-muted-foreground" />

        <p class="mt-3 text-sm font-medium">
          Drop a folder or images here, or

          <label class="text-primary cursor-pointer hover:underline">
            browse files

            <input
              type="file"
              multiple
              accept="image/png, image/jpeg, image/jpg"
              class="hidden"
              @change="onPick($event)"
            />
          </label>

          /

          <label class="text-primary cursor-pointer hover:underline">
            browse folder

            <input ref="folderInput" type="file" multiple class="hidden" @change="onPick($event)" />
          </label>
        </p>

        <p class="text-xs text-muted-foreground mt-1">JPG, PNG - uploads in batches of 4</p>
      </section>
    </div>

    <!-- Upload progress -->
    <section
      v-if="uploader && uploader.items.length"
      class="rounded-xl border border-border bg-surface"
    >
      <header
        class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 px-5 py-3 border-b border-border"
      >
        <div class="text-sm">
          <span class="font-medium">{{ doneCount }}</span>
          <span class="text-muted-foreground"> of </span>
          <span class="font-medium">
            {{ uploader.items.length }}
          </span>
          <span class="text-muted-foreground"> uploaded </span>

          <span v-if="uploadingCount > 0" class="ml-3 text-primary animate-pulse font-medium">
            Uploading & verifying species...
          </span>

          <span v-if="failedCount" class="ml-3 text-red-600"> {{ failedCount }} failed </span>
        </div>

        <div class="flex items-center gap-3 shrink-0">
          <button
            :disabled="starting || cancellingUpload"
            class="px-3 py-1.5 rounded-md text-sm font-medium border border-border bg-background hover:bg-muted text-foreground transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            @click="cancelUpload"
          >
            {{ cancellingUpload ? 'Cancelling...' : 'Cancel upload' }}
          </button>

          <button
            :disabled="!doneCount || starting || uploadingCount > 0 || failedCount > 0"
            class="px-3 py-1.5 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
            @click="startDetection"
          >
            <span v-if="!starting"> Start detection </span>
            <span v-else> Starting… </span>
          </button>
        </div>
      </header>

      <ul v-if="recentFailures.length" class="max-h-60 overflow-auto divide-y divide-border">
        <li
          v-for="item in recentFailures"
          :key="item.id"
          class="flex items-center gap-3 px-5 py-2 text-sm"
        >
          <XCircle class="w-4 h-4 shrink-0 text-red-600" />

          <span class="truncate flex-1" :title="item.file.name">
            {{ item.file.name }}
          </span>

          <span
            class="text-xs text-red-600 truncate max-w-[320px]"
            :title="formatError(item.error)"
          >
            {{ formatError(item.error) }}
          </span>

          <div class="flex items-center gap-2">
            <button
              v-if="formatError(item.error).includes('Validation failed')"
              class="text-xs px-2 py-0.5 rounded border border-primary text-primary hover:bg-green-50 transition-colors"
              title="Bypass seed species verification checks"
              @click="promptForceUpload(item.id)"
            >
              Upload Anyway
            </button>
            <button
              class="text-xs px-2 py-0.5 rounded border border-red-200 text-red-600 hover:bg-red-50 transition-colors"
              title="Remove image from uploads"
              @click="onRemove(item.id)"
            >
              Remove
            </button>
          </div>
        </li>
      </ul>

      <p v-else class="px-5 py-3 text-xs text-muted-foreground">No failures detected.</p>
    </section>

    <p v-if="error" class="text-sm text-red-600">
      {{ error }}
    </p>
  </div>
  <div
    v-if="forcingId"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
  >
    <div
      class="bg-surface border border-border rounded-xl shadow-xl max-w-md w-full p-6 space-y-4 text-left animate-in fade-in zoom-in-95 duration-200"
    >
      <h3 class="text-lg font-semibold text-foreground flex items-center gap-2">
        <AlertTriangle class="w-5 h-5 text-amber-500" />
        Force Upload Image
      </h3>

      <div class="space-y-3 text-sm text-muted-foreground leading-relaxed">
        <p>
          You are about to bypass the automated OCR label verification. Only proceed if you are sure
          that this image contains
          <strong class="text-foreground">{{ selectedSeed }}</strong> seeds.
        </p>
        <p>
          Running the detection pipeline on incorrectly labeled images will likely produce incorrect
          predictions. Are you absolutely sure you want to continue?
        </p>
      </div>

      <div class="flex justify-end gap-3 pt-4 border-t border-border mt-2">
        <button
          @click="cancelForceUpload"
          class="px-4 py-2 text-sm font-medium border border-border rounded-md hover:bg-muted transition-colors"
        >
          Cancel
        </button>
        <button
          @click="confirmForceUpload"
          class="px-4 py-2 text-sm font-medium bg-amber-600 text-white rounded-md hover:bg-amber-700 transition-colors shadow-sm"
        >
          Yes, force upload
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { RouterLink } from 'vue-router'

import { UploadCloud, XCircle, AlertTriangle } from 'lucide-vue-next'

import PageHeader from '@/components/PageHeader.vue'
import SeedsStepper from '@/components/SeedsStepper.vue'

import { api } from '@/api'
import { createUploader, type UploadItem } from '@/lib/uploader'

interface ModelVersion {
  id: number
  module: string
  kind: string
  version_name: string
  is_active: boolean
}

interface PipelineConfig {
  confidence_threshold: number
  slice_overlap_ratio: number
  model_version_id: number | null
}

type Uploader = ReturnType<typeof createUploader>

const router = useRouter()

const creatingUpload = ref(false)
const starting = ref(false)
const dragOver = ref(false)
const cancellingUpload = ref(false)

const error = ref('')
const uploadId = ref<number | null>(null)
const uploader = ref<Uploader | null>(null)
const folderInput = ref<HTMLInputElement | null>(null)

const runName = ref('')
const runNotes = ref('')

const selectedSeed = ref<string | null>(null)

const modelVersions = ref<ModelVersion[]>([])

const seedTypes = ref<SeedType[]>([])

const config = ref<PipelineConfig>({
  confidence_threshold: 0.3,
  slice_overlap_ratio: 0.35,
  models: {},
})

// Filter models to match the selected seed species
const activeModelVersions = computed(() => {
  if (!selectedSeed.value) return []
  return modelVersions.value.filter(
    (m) => m.module === 'seeds' && m.is_active && m.kind === selectedSeed.value,
  )
})

const uploadingCount = computed(() => {
  return uploader.value?.items.filter((item: UploadItem) => item.status === 'uploading').length ?? 0
})

const doneCount = computed(() => {
  return uploader.value?.items.filter((item: UploadItem) => item.status === 'done').length ?? 0
})

const failedCount = computed(() => {
  return uploader.value?.items.filter((item: UploadItem) => item.status === 'failed').length ?? 0
})

const recentFailures = computed<UploadItem[]>(() => {
  return (
    uploader.value?.items.filter((item: UploadItem) => item.status === 'failed').slice(-20) ?? []
  )
})

onMounted(async () => {
  if (folderInput.value) {
    folderInput.value.setAttribute('webkitdirectory', '')
  }
  try {
    if (import.meta.env.DEV && window.location.search.includes('preview=default')) {
      const { default: mocks } = await import('@/mocks/seed-models.json')
      const raw = (mocks as any).default
      modelVersions.value = raw.tracks.flatMap((track: any) =>
        track.versions.map((version: any) => ({
          id: version.id,
          module: 'seeds',
          kind: track.id,
          version_name: version.version_name,
          is_active: version.is_active,
        })),
      )
      return
    }

    const res = await api('/api/analysis/models/?module=seeds')
    if (res.ok) {
      modelVersions.value = await res.json()

      // Extract unique species from available models
      const uniqueKinds = Array.from(
        new Set(modelVersions.value.map((m) => m.kind).filter(Boolean)),
      )

      // Build the UI buttons
      seedTypes.value = uniqueKinds.map((kind) => ({
        id: kind,
        species: '',
        isCustom: false,
      }))

      // Build the configuration tracking object
      const dynamicModels: Record<string, SeedModelConfig> = {}
      uniqueKinds.forEach((kind) => {
        dynamicModels[kind] = { model_version_id: null }
      })
      config.value.models = dynamicModels
    }
  } catch {}
})

function onRemove(id: string) {
  if (!uploader.value) return
  const idx = uploader.value.items.findIndex((item) => item.id === id)
  if (idx > -1) {
    uploader.value.items.splice(idx, 1)
  }
}

const forcingId = ref<string | null>(null)

function promptForceUpload(id: string) {
  forcingId.value = id
}

function cancelForceUpload() {
  forcingId.value = null
}

function confirmForceUpload() {
  if (!uploader.value || !selectedSeed.value || !forcingId.value) return

  const idx = uploader.value.items.findIndex((item) => item.id === forcingId.value)
  if (idx > -1) {
    const item = uploader.value.items[idx]
    uploader.value.items.splice(idx, 1)

    const forcedFilename = `${selectedSeed.value}_forced_${item.file.name}`
    const newFile = new File([item.file], forcedFilename, {
      type: item.file.type,
    })

    uploader.value.enqueue([newFile])
  }

  forcingId.value = null
}

function formatError(err?: string) {
  if (!err) return 'Upload failed'
  try {
    const parsed = JSON.parse(err)
    if (Array.isArray(parsed)) return parsed[0]
    if (parsed.detail) return parsed.detail
    if (parsed.non_field_errors) return parsed.non_field_errors[0]
  } catch {
    // Not JSON, continue to fallback
  }
  // Remove brackets and quotes from raw DRF array strings
  return err.replace(/^\["|"]$/g, '').replace(/\\"/g, '"')
}

const runId = ref<number | null>(null)

async function ensureUpload(): Promise<number | null> {
  if (uploadId.value) return uploadId.value
  if (creatingUpload.value) return null

  creatingUpload.value = true
  try {
    const response = await api('/api/analysis/runs/draft/', {
      method: 'POST',
      body: JSON.stringify({
        module: 'seeds',
        name: runName.value,
        config: {
          ...config.value,
          selected_seed: selectedSeed.value,
        },
      }),
    })

    if (!response.ok) {
      error.value = (await response.text()) || `HTTP ${response.status}`
      return null
    }

    const data = await response.json()
    uploadId.value = data.upload_id
    runId.value = data.run_id // Save the paired run ID

    uploader.value = createUploader({
      module: 'seeds',
      uploadId: data.upload_id,
    })
    return data.upload_id
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    return null
  } finally {
    creatingUpload.value = false
  }
}

async function handleFiles(files: File[]) {
  if (!files.length) {
    return
  }

  const id = await ensureUpload()

  if (!id || !uploader.value) {
    return
  }

  uploader.value.enqueue(files)
}

function onPick(event: Event) {
  const target = event.target as HTMLInputElement

  if (target.files) {
    void handleFiles(Array.from(target.files))
  }

  target.value = ''
}

function onDrop(event: DragEvent) {
  dragOver.value = false

  if (event.dataTransfer?.files) {
    void handleFiles(Array.from(event.dataTransfer.files))
  }
}

function onDragLeave(event: DragEvent) {
  if (!(event.currentTarget as HTMLElement).contains(event.relatedTarget as Node)) {
    dragOver.value = false
  }
}

async function cancelUpload() {
  if (!runId.value) return

  cancellingUpload.value = true
  try {
    // Kill the run and discard the images
    await api(`/api/analysis/runs/${runId.value}/cancel/`, { method: 'POST' })
  } catch (e) {
    console.error('Failed to cancel run on server:', e)
  } finally {
    if (uploader.value) {
      uploader.value.items = [] // Clear items to stop processing
    }
    uploader.value = null
    uploadId.value = null
    runId.value = null
    error.value = ''
    cancellingUpload.value = false
  }
}

async function startDetection() {
  error.value = ''

  if (!uploadId.value) {
    error.value = 'No upload in progress.'
    return
  }

  if (!config.value.model_version_id) {
    error.value = 'Select a model version.'
    return
  }

  starting.value = true

  try {
    const response = await api(`/api/analysis/runs/${runId.value}/start/`, {
      method: 'POST',
      body: JSON.stringify({
        config: { ...config.value, selected_seed: selectedSeed.value },
      }),
    })
    if (!response.ok) throw new Error(await response.text())

    router.push(`/seeds/runs/${runId.value}/detect`)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    starting.value = false
  }
}
</script>
