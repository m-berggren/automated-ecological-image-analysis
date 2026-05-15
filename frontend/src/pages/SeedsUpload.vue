<template>
  <PageHeader title="Upload" subtitle="Add seed images to start a detection run" />
  <SeedsStepper current="upload" />

  <div class="flex-1 p-8 space-y-6 max-w-3xl mx-auto w-full">
    <!-- Run details -->
    <section class="rounded-xl border border-border bg-surface p-5 space-y-4">
      <div>
        <h2 class="text-sm font-semibold">Run details</h2>
        <p class="text-xs text-muted-foreground mt-1">
          Configure the seed analysis pipeline before uploading images.
        </p>
      </div>

      <div class="space-y-2">
        <label class="block text-xs text-muted-foreground">Run name</label>

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
          placeholder="e.g. Dry soil, PEH test v2, camera slightly tilted"
          class="w-full px-3 py-2 text-sm rounded-md border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
      </div>
    </section>

    <!-- Seed type -->
    <section class="rounded-xl border border-border bg-surface p-5 space-y-4">
      <h2 class="text-sm font-semibold">Seed type</h2>
      <p class="text-xs text-muted-foreground">Each batch must contain a single species.</p>

      <!-- Seed list -->
      <div class="grid grid-cols-4 gap-3 pt-1 max-h-[10rem] overflow-y-auto">
        <div v-for="seed in seedTypes" :key="seed.id" class="relative shrink-0 pt-2 pr-2">
          <!-- Delete button -->
          <button
            v-if="seed.isCustom"
            @click.stop="removeSeed(seed.id)"
            class="absolute -top-0 -right-0 w-5 h-5 flex items-center justify-center rounded-full bg-green-900 text-white text-xs z-10"
          >
            ×
          </button>

          <!-- Seed button -->
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

            <span
              v-if="seed.species"
              class="ml-2 overflow-hidden whitespace-nowrap text-[11px] text-muted-foreground italic max-w-0 group-hover:max-w-[100px] opacity-0 group-hover:opacity-100 transition-all duration-200"
            >
              · {{ seed.species }}
            </span>
          </button>
        </div>
      </div>

      <!-- Add seed -->
      <button
        @click="showAddSeed = true"
        class="w-full rounded-lg border-2 border-dashed border-border px-4 py-2 text-sm text-muted-foreground transition hover:border-primary hover:text-primary"
      >
        + Add new seed type
      </button>

      <!-- Add form -->
      <div v-if="showAddSeed" class="rounded-lg border border-border bg-background p-3 space-y-3">
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
    </section>

    <!-- Detection settings -->
    <section class="rounded-xl border border-border bg-surface p-5 space-y-5">
      <div>
        <h2 class="text-sm font-semibold">Detection settings</h2>

        <p class="text-xs text-muted-foreground mt-1">
          Configure model selection and inference behavior.
        </p>
      </div>

      <!-- Model selector — single, filtered by selected seed -->
      <div class="space-y-2">
        <label class="block text-xs text-muted-foreground">
          Model version
          <span v-if="selectedSeed" class="ml-1 text-foreground font-medium"
            >for {{ selectedSeed }}</span
          >
        </label>
        <select
          :value="selectedSeed ? config.models[selectedSeed]?.model_version_id : null"
          @change="
            (e) => {
              if (selectedSeed) {
                config.models[selectedSeed].model_version_id = Number(
                  (e.target as HTMLSelectElement).value,
                )
              }
            }
          "
          :disabled="!selectedSeed"
          class="w-full px-3 py-2 rounded-md border border-border bg-background text-sm disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <option :value="''" disabled>
            {{ selectedSeed ? 'Select model version' : 'Select a seed type first' }}
          </option>

          <option v-for="model in filteredModelVersions" :key="model.id" :value="model.id">
            {{ model.version_name }}{{ model.is_active ? ' (active)' : '' }}
          </option>
        </select>
        <p v-if="selectedSeed && !filteredModelVersions.length" class="text-xs text-amber-600">
          No trained models found for {{ selectedSeed }}. Train one first on the
          <RouterLink to="/seeds/training" class="underline hover:text-foreground"
            >Training page</RouterLink
          >.
        </p>
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

          <input type="file" multiple accept="image/*" class="hidden" @change="onPick($event)" />
        </label>

        /

        <label class="text-primary cursor-pointer hover:underline">
          browse folder

          <input ref="folderInput" type="file" multiple class="hidden" @change="onPick($event)" />
        </label>
      </p>

      <p class="text-xs text-muted-foreground mt-1">JPG, PNG - uploads in batches of 4</p>
    </section>

    <!-- Upload progress -->
    <section
      v-if="uploader && uploader.items.length"
      class="rounded-xl border border-border bg-surface"
    >
      <header class="flex items-center justify-between px-5 py-3 border-b border-border">
        <div class="text-sm">
          <span class="font-medium">{{ doneCount }}</span>

          <span class="text-muted-foreground"> of </span>

          <span class="font-medium">
            {{ uploader.items.length }}
          </span>

          <span class="text-muted-foreground"> uploaded </span>

          <span v-if="failedCount" class="ml-3 text-red-600"> {{ failedCount }} failed </span>
        </div>

        <button
          :disabled="!doneCount || starting"
          class="px-3 py-1.5 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
          @click="startDetection"
        >
          <span v-if="!starting"> Start detection </span>

          <span v-else> Starting… </span>
        </button>
      </header>

      <ul v-if="recentFailures.length" class="max-h-60 overflow-auto divide-y divide-border">
        <li
          v-for="item in recentFailures"
          :key="item.id"
          class="flex items-center gap-3 px-5 py-2 text-sm"
        >
          <XCircle class="w-4 h-4 shrink-0 text-red-600" />

          <span class="truncate flex-1">
            {{ item.file.name }}
          </span>

          <span class="text-xs text-red-600 truncate max-w-[260px]">
            {{ item.error }}
          </span>

          <button
            class="text-xs px-2 py-0.5 rounded border border-border hover:bg-muted"
            @click="onRetry(item.id)"
          >
            Retry
          </button>
        </li>
      </ul>

      <p v-else class="px-5 py-3 text-xs text-muted-foreground">No failures detected.</p>
    </section>

    <p v-if="error" class="text-sm text-red-600">
      {{ error }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { RouterLink } from 'vue-router'

import { UploadCloud, XCircle } from 'lucide-vue-next'

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

interface SeedType {
  id: string
  species: string
  isCustom: boolean
}

interface SeedModelConfig {
  model_version_id: number | null
}

interface PipelineConfig {
  confidence_threshold: number
  slice_overlap_ratio: number

  models: Record<string, SeedModelConfig>
}

type Uploader = ReturnType<typeof createUploader>

const router = useRouter()

const creatingUpload = ref(false)
const starting = ref(false)
const dragOver = ref(false)

const error = ref('')
const uploadId = ref<number | null>(null)
const uploader = ref<Uploader | null>(null)
const folderInput = ref<HTMLInputElement | null>(null)

const runName = ref('')
const runNotes = ref('')

const selectedSeed = ref<string | null>(null)

const showAddSeed = ref(false)
const newSeedId = ref('')
const newSeedSpecies = ref('')

const modelVersions = ref<ModelVersion[]>([])

const seedTypes = ref<SeedType[]>([
  {
    id: 'PEH',
    species: 'Species name',
    isCustom: false,
  },
  {
    id: 'PHYCA',
    species: 'Species name',
    isCustom: false,
  },
  {
    id: 'VAU',
    species: 'Species name',
    isCustom: false,
  },
  {
    id: 'CAT',
    species: 'Species name',
    isCustom: false,
  },
])

const config = ref<PipelineConfig>({
  confidence_threshold: 0.25,
  slice_overlap_ratio: 0.25,

  models: {
    PEH: { model_version_id: null },
    PHYCA: { model_version_id: null },
    VAU: { model_version_id: null },
    CAT: { model_version_id: null },
  },
})

const filteredModelVersions = computed(() => {
  if (!selectedSeed.value) return []

  return modelVersions.value.filter((m) => m.module === 'seeds' && m.kind === selectedSeed.value)
})

watch(selectedSeed, (seed) => {
  if (!seed) return

  config.value.models[seed] ??= {
    model_version_id: null,
  }
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
    const res = await api('/api/analysis/models/?module=seeds')
    if (res.ok) modelVersions.value = await res.json()
  } catch {}
})

function onRetry(id: string) {
  uploader.value?.retry(id)
}

function cancelAddSeed() {
  showAddSeed.value = false
  newSeedId.value = ''
  newSeedSpecies.value = ''
}

function addSeed() {
  error.value = ''

  if (!newSeedId.value.trim()) {
    return
  }

  const id = newSeedId.value.trim().toUpperCase()

  if (seedTypes.value.some((seed) => seed.id === id)) {
    error.value = `Seed type ${id} already exists.`

    return
  }

  seedTypes.value.push({
    id,

    species: newSeedSpecies.value.trim(),

    isCustom: true,
  })

  config.value.models[id] = {
    model_version_id: null,
  }

  cancelAddSeed()
}

function removeSeed(id: string) {
  seedTypes.value = seedTypes.value.filter((seed) => seed.id !== id)

  delete config.value.models[id]

  if (selectedSeed.value === id) {
    selectedSeed.value = null
  }
}

async function ensureUpload(): Promise<number | null> {
  if (uploadId.value) {
    return uploadId.value
  }

  if (creatingUpload.value) {
    return null
  }

  creatingUpload.value = true

  try {
    const response = await api('/api/datasets/uploads/', {
      method: 'POST',
      body: JSON.stringify({
        module: 'seeds',
        name: runName.value,
      }),
    })

    if (!response.ok) {
      error.value = (await response.text()) || `HTTP ${response.status}`
      return null
    }

    const data = await response.json()

    uploadId.value = data.id

    uploader.value = createUploader({
      module: 'seeds',
      uploadId: data.id,
    })

    return data.id
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

async function startDetection() {
  error.value = ''

  if (!uploadId.value) {
    error.value = 'No upload in progress.'
    return
  }

  if (!selectedSeed.value) {
    error.value = 'Select a seed type.'
    return
  }

  const modelId = selectedSeed.value
    ? config.value.models[selectedSeed.value]?.model_version_id
    : null

  if (!modelId) {
    error.value = `Select a model version for ${selectedSeed.value}.`

    return
  }

  starting.value = true

  try {
    const response = await api('/api/analysis/runs/', {
      method: 'POST',
      body: JSON.stringify({
        module: 'seeds',
        upload: uploadId.value,
        name: runName.value,
        notes: runNotes.value,

        config: {
          ...config.value,
          selected_seed: selectedSeed.value,
        },
      }),
    })

    if (!response.ok) {
      error.value = (await response.text()) || `HTTP ${response.status}`
      return
    }

    const run = await response.json()

    router.push(`/seeds/runs/${run.id}/detect`)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    starting.value = false
  }
}
</script>
