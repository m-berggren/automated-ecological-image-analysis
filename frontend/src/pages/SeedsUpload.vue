<template>
  <PageHeader title="Upload" subtitle="Add seed images to start a detection run" />
  <SeedsStepper current="upload" />

  <div class="flex-1 overflow-y-auto p-8 space-y-6 max-w-3xl mx-auto w-full">
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
          placeholder="e.g. Dry soil, PEH test v2, camera slightly tilted"
          class="w-full px-3 py-2 text-sm rounded-md border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
      </div>
    </section>

    <!-- Detection settings -->
    <section class="rounded-xl border border-border bg-surface p-5 space-y-5">
      <div>
        <h2 class="text-sm font-semibold">Detection settings</h2>
      </div>

      <!-- Model selector -->
<div class="space-y-2">
  <div
    class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3"
  >
    Choose model version
  </div>

  <!-- Empty state -->
  <div
    v-if="!activeModelVersions.length"
    class="rounded-lg border border-border bg-muted/20 p-4 text-sm"
  >
    <span class="text-muted-foreground">
      No active models yet.
    </span>

    <RouterLink
      to="/seeds/training"
      class="ml-1 text-primary hover:underline font-medium"
    >
      Go to the training page
    </RouterLink>

    <span class="text-muted-foreground">
      to create one.
    </span>
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
import { computed, onMounted, ref } from 'vue'
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

const error = ref('')
const uploadId = ref<number | null>(null)
const uploader = ref<Uploader | null>(null)
const folderInput = ref<HTMLInputElement | null>(null)

const runName = ref('')
const runNotes = ref('')

const modelVersions = ref<ModelVersion[]>([])

const config = ref<PipelineConfig>({
  confidence_threshold: 0.25,
  slice_overlap_ratio: 0.25,
  model_version_id: null,
})

const activeModelVersions = computed(() => {
  return modelVersions.value.filter(
    (m) => m.module === 'seeds' && m.is_active,
  )
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
    }
  } catch {}
})

function onRetry(id: string) {
  uploader.value?.retry(id)
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

  if (!config.value.model_version_id) {
  error.value = 'Select a model version.'
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

        config: config.value,
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
