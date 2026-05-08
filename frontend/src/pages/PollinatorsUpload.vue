<template>
  <PageHeader title="Upload" subtitle="Configure and upload a camera-trap folder" />
  <PollinatorsStepper current="upload" />

  <div class="flex-1 p-8 space-y-6 max-w-3xl mx-auto w-full">
    <!-- Run details -->
    <section class="rounded-xl border border-border bg-surface p-5 space-y-3">
      <h2 class="text-sm font-semibold">Run details</h2>
      <div class="space-y-2">
        <label class="block text-xs text-muted-foreground">Name</label>
        <input
          v-model="runName"
          type="text"
          placeholder="e.g. Camera A — July 2026"
          class="w-full px-3 py-2 text-sm rounded-md border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
      </div>
    </section>

    <!-- Detection settings -->
    <section class="rounded-xl border border-border bg-surface p-5 space-y-4">
      <h2 class="text-sm font-semibold">Detection settings</h2>

      <!-- Models row -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <label class="space-y-1">
          <span class="text-xs text-muted-foreground">YOLO model</span>
          <select
            v-model="config.yolo.model_version_id"
            class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm"
            :disabled="!detectorModels.length"
          >
            <option :value="null" disabled>
              {{ detectorModels.length ? 'Select model' : 'No detector models yet' }}
            </option>
            <option v-for="m in detectorModels" :key="m.id" :value="m.id">
              {{ m.version_name }}{{ m.is_active ? ' (active)' : '' }}
            </option>
          </select>
        </label>
        <label class="space-y-1">
          <span class="text-xs text-muted-foreground">InsectNet model</span>
          <select
            v-model="config.classifier.model_version_id"
            class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm"
            :disabled="!classifierModels.length"
          >
            <option :value="null" disabled>
              {{ classifierModels.length ? 'Select model' : 'No classifier models yet' }}
            </option>
            <option v-for="m in classifierModels" :key="m.id" :value="m.id">
              {{ m.version_name }}{{ m.is_active ? ' (active)' : '' }}
            </option>
          </select>
        </label>
      </div>

      <!-- Confidence row -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <label class="space-y-1">
          <span class="text-xs text-muted-foreground">YOLO confidence</span>
          <input
            v-model.number="config.yolo.confidence"
            type="number" min="0" max="1" step="0.05"
            class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm font-mono"
          />
        </label>
        <label class="space-y-1">
          <span class="text-xs text-muted-foreground">InsectNet binary</span>
          <input
            v-model.number="config.classifier.binary_confidence"
            type="number" min="0" max="1" step="0.05"
            class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm font-mono"
          />
        </label>
        <label class="space-y-1">
          <span class="text-xs text-muted-foreground">InsectNet species</span>
          <input
            v-model.number="config.classifier.group_confidence"
            type="number" min="0" max="1" step="0.05"
            class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm font-mono"
          />
        </label>
      </div>

      <!-- Misc row -->
      <div class="flex flex-wrap items-center gap-x-6 gap-y-3 pt-2 border-t border-border">
        <label class="flex items-center gap-2 text-sm">
          <input v-model="config.preprocessing.use_roi" type="checkbox" />
          Use manual ROI
        </label>
        <label class="flex items-center gap-2 text-sm">
          <span class="text-xs text-muted-foreground">Start at image</span>
          <input
            v-model.number="config.start_at_image"
            type="number" min="1"
            class="w-20 px-2 py-1 rounded border border-border bg-background text-sm font-mono"
          />
        </label>
      </div>

      <!-- Advanced -->
      <button
        class="text-xs text-muted-foreground hover:text-foreground"
        @click="showAdvanced = !showAdvanced"
      >
        {{ showAdvanced ? '▾ Hide advanced' : '▸ Advanced' }}
      </button>
      <div
        v-if="showAdvanced"
        class="border-t border-border pt-3 space-y-3"
      >
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <label class="space-y-1">
            <span class="text-xs text-muted-foreground">Crop padding</span>
            <input
              v-model.number="config.advanced.crop_padding"
              type="number" min="0" max="2" step="0.1"
              class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm font-mono"
            />
          </label>
          <label class="space-y-1">
            <span class="text-xs text-muted-foreground">Background sample size</span>
            <input
              v-model.number="config.advanced.background_sample_size"
              type="number" min="10" max="500"
              class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm font-mono"
            />
          </label>
          <label class="space-y-1">
            <span class="text-xs text-muted-foreground">Rolling window (frames)</span>
            <input
              v-model.number="config.advanced.rolling_window"
              type="number" min="1" max="100"
              class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm font-mono"
            />
          </label>
        </div>
        <p class="text-[11px] text-muted-foreground">
          Pre-annotating filter knobs. Defaults match the production pipeline; only change if a
          specific batch needs tuning.
        </p>
      </div>
    </section>

    <!-- Drop zone -->
    <section
      class="rounded-xl border-2 border-dashed border-border bg-surface p-10 text-center transition-colors"
      :class="{ 'border-primary bg-primary/5': dragOver, 'opacity-60': creatingUpload }"
      @dragover.prevent="dragOver = true"
      @dragleave.prevent="dragOver = false"
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
            accept="image/*"
            class="hidden"
            @change="onPick($event, false)"
          />
        </label>
        /
        <label class="text-primary cursor-pointer hover:underline">
          browse folder
          <input
            ref="folderInput"
            type="file"
            multiple
            class="hidden"
            @change="onPick($event, true)"
          />
        </label>
      </p>
      <p class="text-xs text-muted-foreground mt-1">
        JPG, PNG — up to ~12,000 images per run
      </p>
    </section>

    <!-- Upload progress + start -->
    <section
      v-if="uploader && uploader.items.length"
      class="rounded-xl border border-border bg-surface"
    >
      <header class="flex items-center justify-between px-5 py-3 border-b border-border">
        <div class="text-sm">
          <span class="font-medium">{{ doneCount }}</span>
          <span class="text-muted-foreground"> of </span>
          <span class="font-medium">{{ uploader.items.length }}</span>
          <span class="text-muted-foreground"> uploaded</span>
          <span v-if="failedCount" class="ml-3 text-red-600">{{ failedCount }} failed</span>
        </div>
        <div class="flex items-center gap-2">
          <button
            :disabled="!doneCount || starting"
            class="px-3 py-1.5 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
            @click="startDetection"
          >
            <span v-if="!starting">Start detection</span>
            <span v-else>Starting…</span>
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
          <span class="truncate flex-1">{{ item.file.name }}</span>
          <span class="text-xs text-red-600 truncate max-w-[260px]">{{ item.error }}</span>
          <button
            class="text-xs px-2 py-0.5 rounded border border-border hover:bg-muted"
            @click="onRetry(item.id)"
          >
            Retry
          </button>
        </li>
      </ul>
      <p v-else class="px-5 py-3 text-xs text-muted-foreground">
        No failures. (Per-file list hidden at this scale — failures will appear here as they happen.)
      </p>
    </section>

    <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import PollinatorsStepper from '@/components/PollinatorsStepper.vue'
import { createUploader, type UploadItem } from '@/lib/uploader'
import { api } from '@/api'
import { UploadCloud, XCircle } from 'lucide-vue-next'

interface ModelVersion {
  id: number
  module: string
  kind: string
  version_name: string
  is_active: boolean
}

const router = useRouter()
const dragOver = ref(false)
const creatingUpload = ref(false)
const starting = ref(false)
const error = ref('')
const showAdvanced = ref(false)

const runName = ref('')
const uploadId = ref<number | null>(null)

type Uploader = ReturnType<typeof createUploader>
const uploader = ref<Uploader | null>(null)

const detectorModels = ref<ModelVersion[]>([])
const classifierModels = ref<ModelVersion[]>([])

interface PipelineConfig {
  yolo: { model_version_id: number | null; confidence: number }
  classifier: {
    model_version_id: number | null
    binary_confidence: number
    group_confidence: number
  }
  preprocessing: { use_roi: boolean }
  start_at_image: number
  advanced: {
    crop_padding: number
    background_sample_size: number
    rolling_window: number
  }
}

const config = ref<PipelineConfig>({
  yolo: { model_version_id: null, confidence: 0.4 },
  classifier: {
    model_version_id: null,
    binary_confidence: 0.5,
    group_confidence: 0.6,
  },
  preprocessing: { use_roi: false },
  start_at_image: 1,
  advanced: {
    crop_padding: 0.3,
    background_sample_size: 100,
    rolling_window: 30,
  },
})

const doneCount = computed(
  () => uploader.value?.items.filter((i: UploadItem) => i.status === 'done').length ?? 0,
)
const failedCount = computed(
  () => uploader.value?.items.filter((i: UploadItem) => i.status === 'failed').length ?? 0,
)
const recentFailures = computed<UploadItem[]>(
  () => uploader.value?.items.filter((i: UploadItem) => i.status === 'failed').slice(-20) ?? [],
)

function onRetry(id: string) {
  uploader.value?.retry(id)
}

onMounted(async () => {
  try {
    const res = await api('/api/analysis/models/?module=pollinators')
    if (res.ok) {
      const all: ModelVersion[] = await res.json()
      detectorModels.value = all.filter((m) => m.kind === 'detector')
      classifierModels.value = all.filter((m) => m.kind === 'classifier')
      const yoloDefault = detectorModels.value.find((m) => m.is_active) ?? detectorModels.value[0]
      const insectDefault =
        classifierModels.value.find((m) => m.is_active) ?? classifierModels.value[0]
      if (yoloDefault) config.value.yolo.model_version_id = yoloDefault.id
      if (insectDefault) config.value.classifier.model_version_id = insectDefault.id
    }
  } catch (e) {
    console.warn('Failed to load model versions', e)
  }
})

async function ensureUpload(): Promise<number | null> {
  if (uploadId.value) return uploadId.value
  if (creatingUpload.value) return null
  creatingUpload.value = true
  try {
    const res = await api('/api/datasets/uploads/', {
      method: 'POST',
      body: JSON.stringify({ module: 'pollinators', name: runName.value }),
    })
    if (!res.ok) {
      error.value = (await res.text()) || `HTTP ${res.status}`
      return null
    }
    const data = await res.json()
    uploadId.value = data.id
    uploader.value = createUploader({ module: 'pollinators', uploadId: data.id })
    return data.id
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    return null
  } finally {
    creatingUpload.value = false
  }
}

async function handleFiles(files: File[]) {
  if (!files.length) return
  const id = await ensureUpload()
  if (!id || !uploader.value) return
  uploader.value.enqueue(files)
}

function onPick(e: Event, _isFolder: boolean) {
  const target = e.target as HTMLInputElement
  if (target.files) void handleFiles(Array.from(target.files))
  target.value = ''
}

function onDrop(e: DragEvent) {
  dragOver.value = false
  if (e.dataTransfer?.files) void handleFiles(Array.from(e.dataTransfer.files))
}

const folderInput = ref<HTMLInputElement | null>(null)
onMounted(() => {
  if (folderInput.value) folderInput.value.setAttribute('webkitdirectory', '')
})

async function startDetection() {
  error.value = ''
  if (!uploadId.value) {
    error.value = 'No upload in progress.'
    return
  }
  if (!config.value.yolo.model_version_id) {
    error.value = 'Pick a YOLO model.'
    return
  }
  if (!config.value.classifier.model_version_id) {
    error.value = 'Pick an InsectNet model.'
    return
  }
  starting.value = true
  try {
    const res = await api('/api/analysis/runs/', {
      method: 'POST',
      body: JSON.stringify({
        module: 'pollinators',
        upload: uploadId.value,
        name: runName.value,
        config: config.value,
      }),
    })
    if (!res.ok) {
      error.value = (await res.text()) || `HTTP ${res.status}`
      return
    }
    const run = await res.json()
    router.push(`/pollinators/runs/${run.id}/detect`)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    starting.value = false
  }
}
</script>
