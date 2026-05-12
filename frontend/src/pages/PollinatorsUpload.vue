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
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <label class="space-y-1">
          <span class="text-xs text-muted-foreground">YOLO</span>
          <select
            v-model="config.yolo.model_version_id"
            class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm"
            :disabled="!detectorModels.length"
          >
            <option :value="null" disabled>
              {{ detectorModels.length ? 'Select model' : 'No models yet' }}
            </option>
            <option v-for="m in detectorModels" :key="m.id" :value="m.id">
              {{ m.version_name }}{{ m.is_active ? ' (active)' : '' }}
            </option>
          </select>
        </label>
        <label class="space-y-1">
          <span class="text-xs text-muted-foreground">EfficientNet</span>
          <select
            v-model="config.binary_classifier.model_version_id"
            class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm"
            :disabled="!binaryModels.length"
          >
            <option :value="null" disabled>
              {{ binaryModels.length ? 'Select model' : 'No models yet' }}
            </option>
            <option v-for="m in binaryModels" :key="m.id" :value="m.id">
              {{ m.version_name }}{{ m.is_active ? ' (active)' : '' }}
            </option>
          </select>
        </label>
        <label class="space-y-1">
          <span class="text-xs text-muted-foreground">InsectNet</span>
          <select
            v-model="config.group_classifier.model_version_id"
            class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm"
            :disabled="!groupModels.length"
          >
            <option :value="null" disabled>
              {{ groupModels.length ? 'Select model' : 'No models yet' }}
            </option>
            <option v-for="m in groupModels" :key="m.id" :value="m.id">
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
          <span class="text-xs text-muted-foreground">Binary confidence</span>
          <input
            v-model.number="config.binary_classifier.confidence"
            type="number" min="0" max="1" step="0.05"
            class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm font-mono"
          />
        </label>
        <label class="space-y-1">
          <span class="text-xs text-muted-foreground">Group confidence</span>
          <input
            v-model.number="config.group_classifier.confidence"
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
        <!-- Button to open the ROI drawer -->
        <button
          v-if="config.preprocessing.use_roi"
          class="px-3 py-1.5 text-sm rounded bg-primary text-white hover:bg-primary/90"
          @click="openRoiModal"
        >
          Open ROI editor
        </button>
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
              v-model.number="config.preprocessing.crop_pad_frac"
              type="number" min="0" max="2" step="0.1"
              class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm font-mono"
            />
          </label>
          <label class="space-y-1">
            <span class="text-xs text-muted-foreground">Min contour area (px²)</span>
            <input
              v-model.number="config.preprocessing.min_contour_area"
              type="number" min="50" max="5000" step="50"
              class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm font-mono"
            />
          </label>
          <label class="space-y-1">
            <span class="text-xs text-muted-foreground">Max contour area (px²)</span>
            <input
              v-model.number="config.preprocessing.max_contour_area"
              type="number" min="1000" max="200000" step="1000"
              class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm font-mono"
            />
          </label>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <label class="space-y-1">
            <span class="text-xs text-muted-foreground">Background sample size</span>
            <input
              v-model.number="config.preprocessing.background_sample_size"
              type="number" min="0" max="500"
              class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm font-mono"
            />
          </label>
          <label class="space-y-1">
            <span class="text-xs text-muted-foreground">Sunny shutter threshold</span>
            <input
              v-model.number="config.preprocessing.sunny_shutter_threshold"
              type="number" min="50" max="500" step="10"
              class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm font-mono"
            />
          </label>
        </div>
        <div class="flex flex-wrap items-center gap-x-6 gap-y-2 pt-1 border-t border-border">
          <label class="flex items-center gap-2 text-sm">
            <input v-model="config.preprocessing.skip_flash" type="checkbox" />
            Skip flash frames
          </label>
          <label class="flex items-center gap-2 text-sm">
            <input v-model="config.preprocessing.skip_foggy" type="checkbox" />
            Skip foggy frames
          </label>
          <label class="flex items-center gap-2 text-sm">
            <input v-model="config.preprocessing.enable_large_motion" type="checkbox" />
            Detect large motion
          </label>
        </div>
        <p class="text-[11px] text-muted-foreground">
          Defaults match the production pipeline. Only change if a specific batch needs tuning.
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
    <!-- The ROI drawer modal -->
    <div>
      <ROIDrawer
        v-if="showRoiModal"
        :image-url="previewUrl"
        @close="closeRoiModal"
      />
    </div>

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
import ROIDrawer from '@/components/ROIDrawer.vue'

interface ModelVersion {
  id: number
  module: string
  kind: string
  version_name: string
  is_active: boolean
}

const localFiles = ref<File[]>([])
const showRoiModal = ref(false)
const previewUrl = ref<string | null>(null)

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
const binaryModels = ref<ModelVersion[]>([])
const groupModels = ref<ModelVersion[]>([])

interface PipelineConfig {
  yolo: { model_version_id: number | null; confidence: number }
  binary_classifier: { model_version_id: number | null; confidence: number }
  group_classifier: { model_version_id: number | null; confidence: number }
  preprocessing: {
    use_roi: boolean
    crop_pad_frac: number
    background_sample_size: number
    min_contour_area: number
    max_contour_area: number
    sunny_shutter_threshold: number
    skip_flash: boolean
    skip_foggy: boolean
    enable_large_motion: boolean
  }
  start_at_image: number
}

const config = ref<PipelineConfig>({
  yolo: { model_version_id: null, confidence: 0.4 },
  binary_classifier: { model_version_id: null, confidence: 0.5 },
  group_classifier: { model_version_id: null, confidence: 0.6 },
  preprocessing: {
    use_roi: false,
    crop_pad_frac: 0.3,
    background_sample_size: 100,
    min_contour_area: 400,
    max_contour_area: 35000,
    sunny_shutter_threshold: 150,
    skip_flash: true,
    skip_foggy: true,
    enable_large_motion: true,
  },
  start_at_image: 1,
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
      binaryModels.value = all.filter((m) => m.kind === 'binary_classifier')
      groupModels.value = all.filter((m) => m.kind === 'group_classifier')
      const pickDefault = (list: ModelVersion[]) =>
        list.find((m) => m.is_active) ?? list[0]
      const yoloDefault = pickDefault(detectorModels.value)
      const binaryDefault = pickDefault(binaryModels.value)
      const groupDefault = pickDefault(groupModels.value)
      if (yoloDefault) config.value.yolo.model_version_id = yoloDefault.id
      if (binaryDefault) config.value.binary_classifier.model_version_id = binaryDefault.id
      if (groupDefault) config.value.group_classifier.model_version_id = groupDefault.id
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

const IMAGE_EXT_RE = /\.(jpe?g|png|webp)$/i

async function handleFiles(files: File[]) {
  // Folder drops can include non-image files (subfolders' siblings,
  // hidden system files like .DS_Store, etc.). Drop them before enqueueing.
  const images = files.filter(
    (f) => f.type.startsWith('image/') || IMAGE_EXT_RE.test(f.name),
  )
  if (!images.length) return
  const id = await ensureUpload()
  if (!id || !uploader.value) return
  uploader.value.enqueue(images)
  localFiles.value = images
}

function onPick(e: Event, _isFolder: boolean) {
  const target = e.target as HTMLInputElement
  if (target.files) void handleFiles(Array.from(target.files))
  target.value = ''
}

async function onDrop(e: DragEvent) {
  dragOver.value = false
  if (!e.dataTransfer) return

  // dataTransfer.files alone can't recurse into dropped folders; use the
  // items API + webkitGetAsEntry to walk directories. Fall back to files
  // for any environment without items support.
  if (e.dataTransfer.items && e.dataTransfer.items.length) {
    const entries: FileSystemEntry[] = []
    for (const item of Array.from(e.dataTransfer.items)) {
      const entry = item.webkitGetAsEntry?.()
      if (entry) entries.push(entry)
    }
    const files: File[] = []
    await Promise.all(entries.map((entry) => collectFiles(entry, files)))
    if (files.length) void handleFiles(files)
    return
  }
  if (e.dataTransfer.files) void handleFiles(Array.from(e.dataTransfer.files))
}

// Recursively read every file under a dropped FileSystemEntry. Handles the
// readEntries() batch limit (typically 100 per call) by re-reading until
// the directory yields nothing.
async function collectFiles(entry: FileSystemEntry, out: File[]): Promise<void> {
  if (entry.isFile) {
    const file = await new Promise<File>((resolve, reject) => {
      (entry as FileSystemFileEntry).file(resolve, reject)
    })
    out.push(file)
    return
  }
  if (entry.isDirectory) {
    const reader = (entry as FileSystemDirectoryEntry).createReader()
    const children: FileSystemEntry[] = []
    let batch: FileSystemEntry[]
    do {
      batch = await new Promise<FileSystemEntry[]>((resolve, reject) => {
        reader.readEntries(resolve, reject)
      })
      children.push(...batch)
    } while (batch.length > 0)
    await Promise.all(children.map((child) => collectFiles(child, out)))
  }
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
  if (!config.value.binary_classifier.model_version_id) {
    error.value = 'Pick an EfficientNet model.'
    return
  }
  if (!config.value.group_classifier.model_version_id) {
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

// Choses the current selected manual roi image and makes the ROI drawing modal appear
function openRoiModal() {
  if (!localFiles.value.length) return

  const index = (config.value.start_at_image || 1) - 1

  if (index < 0 || index >= localFiles.value.length) return


  const file = localFiles.value[index]

  // clean up old URL
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
  }

  previewUrl.value = URL.createObjectURL(file)
  showRoiModal.value = true
}

// Makes the modal disappear and clears up the old image URL
function closeRoiModal() {
  showRoiModal.value = false

  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = null
  }
}
</script>
