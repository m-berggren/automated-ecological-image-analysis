<template>
  <PageHeader title="Upload" subtitle="Configure and upload a camera-trap folder" />
  <PollinatorsStepper current="upload" />

  <div class="flex-1 min-h-0 overflow-y-auto px-8 py-4 space-y-3 max-w-3xl mx-auto w-full">
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
            type="number"
            min="0"
            max="1"
            step="0.05"
            class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm font-mono"
          />
        </label>
        <label class="space-y-1">
          <span class="text-xs text-muted-foreground">Binary confidence</span>
          <input
            v-model.number="config.binary_classifier.confidence"
            type="number"
            min="0"
            max="1"
            step="0.05"
            class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm font-mono"
          />
        </label>
        <label class="space-y-1">
          <span class="text-xs text-muted-foreground">Group confidence</span>
          <input
            v-model.number="config.group_classifier.confidence"
            type="number"
            min="0"
            max="1"
            step="0.05"
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
            type="number"
            min="1"
            class="w-20 px-2 py-1 rounded border border-border bg-background text-sm font-mono"
          />
        </label>
      </div>
      <div v-if="startAtImageOutOfRange" class="text-xs text-red-600">
        “Start at image” is outside the uploaded range (max {{ localFiles.length }}).
      </div>

      <!-- Advanced -->
      <button
        class="text-xs text-muted-foreground hover:text-foreground"
        @click="showAdvanced = !showAdvanced"
      >
        {{ showAdvanced ? '▾ Hide advanced' : '▸ Advanced' }}
      </button>
      <div v-if="showAdvanced" class="border-t border-border pt-3 space-y-3">
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <label class="space-y-1">
            <span class="text-xs text-muted-foreground">Crop padding</span>
            <input
              v-model.number="config.preprocessing.crop_pad_frac"
              type="number"
              min="0"
              max="2"
              step="0.1"
              class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm font-mono"
            />
          </label>
          <label class="space-y-1">
            <span class="text-xs text-muted-foreground">Min contour area (px²)</span>
            <input
              v-model.number="config.preprocessing.min_contour_area"
              type="number"
              min="50"
              max="5000"
              step="50"
              class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm font-mono"
            />
          </label>
          <label class="space-y-1">
            <span class="text-xs text-muted-foreground">Max contour area (px²)</span>
            <input
              v-model.number="config.preprocessing.max_contour_area"
              type="number"
              min="1000"
              max="200000"
              step="1000"
              class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm font-mono"
            />
          </label>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <label class="space-y-1">
            <span class="text-xs text-muted-foreground">Background sample size</span>
            <input
              v-model.number="config.preprocessing.background_sample_size"
              type="number"
              min="0"
              max="500"
              class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm font-mono"
            />
          </label>
          <label class="space-y-1">
            <span class="text-xs text-muted-foreground">Sunny shutter threshold</span>
            <input
              v-model.number="config.preprocessing.sunny_shutter_threshold"
              type="number"
              min="50"
              max="500"
              step="10"
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
    <UploadDropZone
      v-model:active-tab="uploadActiveTab"
      :tabs="uploadTabs"
      :has-files="pickedFiles.length > 0"
      @select="onUploadSelect"
    />

    <!-- Selection summary + start. Images stay in the browser until the
         user clicks "Start detection"; we then create the run, transmit
         the files, and route to the Detect page. -->
    <section class="rounded-xl border border-border bg-surface">
      <header class="flex items-center justify-between px-5 py-3">
        <div class="text-sm">
          <template v-if="pickedFiles.length">
            <span class="font-medium">{{ pickedFiles.length.toLocaleString() }}</span>
            <span class="text-muted-foreground">
              {{ pickedFiles.length === 1 ? 'image' : 'images' }} selected ·
              {{ formatBytes(totalPickedBytes) }}
            </span>
            <button
              v-if="!submitting"
              class="ml-3 text-xs text-muted-foreground hover:text-red-600"
              @click="clearPicked"
            >
              Clear
            </button>
          </template>
          <template v-else>
            <span class="text-muted-foreground"> Drop or browse images above to count them. </span>
          </template>
        </div>
        <div class="flex items-center gap-2">
          <button
            :disabled="!canStart"
            :title="startDisabledReason"
            class="px-3 py-1.5 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
            @click="startDetection"
          >
            {{
              submitting ? `Uploading ${uploadedCount}/${pickedFiles.length}…` : 'Start detection'
            }}
          </button>
        </div>
      </header>
      <div v-if="submitting" class="px-5 pb-3">
        <div class="h-1.5 rounded-full bg-muted overflow-hidden">
          <div class="h-full bg-primary transition-all" :style="{ width: uploadPercent + '%' }" />
        </div>
      </div>
    </section>

    <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
    <!-- The ROI drawer modal -->
    <div>
      <ROIDrawer
        v-if="showRoiModal"
        :image-url="previewUrl"
        @close="closeRoiModal"
        @confirm="onSaveRoi"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import PollinatorsStepper from '@/components/PollinatorsStepper.vue'
import UploadDropZone, { type UploadTab } from '@/components/UploadDropZone.vue'
import { api } from '@/api'
import { XCircle } from 'lucide-vue-next'
import ROIDrawer from '@/components/ROIDrawer.vue'

interface ModelVersion {
  id: number
  module: string
  kind: string
  version_name: string
  is_active: boolean
}

const startAtImageOutOfRange = computed(() => {
  if (!localFiles.value.length) return false
  const idx = (config.value.start_at_image || 1) - 1
  return idx < 0 || idx >= localFiles.value.length
})

const localFiles = ref<File[]>([])
const showRoiModal = ref(false)
const previewUrl = ref<string | null>(null)

const creatingUpload = ref(false)

const router = useRouter()
const uploadActiveTab = ref('files')
const uploadTabs: UploadTab[] = [
  {
    key: 'files',
    label: 'Files',
    mode: 'files',
    accept: 'image/*',
    placeholder: 'Drop images here or click to browse',
    helper: 'JPG, PNG -> Up to 12,000 images per run',
  },
  {
    key: 'folder',
    label: 'Folder',
    mode: 'folder',
    placeholder: 'Drop a folder here or click to browse',
    helper: 'Subfolders are walked; non-image files are ignored.',
  },
]
const error = ref('')
const showAdvanced = ref(false)

const runName = ref('')

const pickedFiles = ref<File[]>([])
const submitting = ref(false)
const uploadedCount = ref(0)

const detectorModels = ref<ModelVersion[]>([])
const binaryModels = ref<ModelVersion[]>([])
const groupModels = ref<ModelVersion[]>([])

interface PipelineConfig {
  yolo: { model_version_id: number | null; confidence: number }
  binary_classifier: { model_version_id: number | null; confidence: number }
  group_classifier: { model_version_id: number | null; confidence: number }
  preprocessing: {
    use_roi: boolean
    roi_bbox: null | RoiBBox
    crop_pad_frac: number
    background_sample_size: number
    min_contour_area: number
    max_contour_area: number
    sunny_shutter_threshold: number
    skip_flash: boolean
    skip_foggy: boolean
    enable_large_motion: boolean
  }
}

interface RoiBBox {
  x: number
  y: number
  width: number
  height: number
}

const config = ref<PipelineConfig>({
  yolo: { model_version_id: null, confidence: 0.2 },
  binary_classifier: { model_version_id: null, confidence: 0.2 },
  group_classifier: { model_version_id: null, confidence: 0.2 },
  preprocessing: {
    use_roi: false,
    roi_bbox: null,
    crop_pad_frac: 0.3,
    background_sample_size: 100,
    min_contour_area: 400,
    max_contour_area: 35000,
    sunny_shutter_threshold: 150,
    skip_flash: true,
    skip_foggy: true,
    enable_large_motion: true,
  },
})

const totalPickedBytes = computed(() => pickedFiles.value.reduce((sum, f) => sum + f.size, 0))

const uploadPercent = computed(() => {
  if (!pickedFiles.value.length) return 0
  return Math.round((uploadedCount.value / pickedFiles.value.length) * 100)
})

const canStart = computed(() => {
  if (submitting.value) return false
  if (!pickedFiles.value.length) return false
  if (!config.value.yolo.model_version_id) return false
  if (!config.value.binary_classifier.model_version_id) return false
  if (!config.value.group_classifier.model_version_id) return false
  return true
})

const startDisabledReason = computed(() => {
  if (submitting.value) return 'Upload in progress'
  if (!pickedFiles.value.length) return 'Pick at least one image first'
  if (
    !config.value.yolo.model_version_id ||
    !config.value.binary_classifier.model_version_id ||
    !config.value.group_classifier.model_version_id
  ) {
    return 'All three models must be selected'
  }
  return ''
})

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

function clearPicked() {
  pickedFiles.value = []
  uploadedCount.value = 0
  error.value = ''
}

onMounted(async () => {
  try {
    const res = await api('/api/analysis/models/?module=pollinators')
    if (res.ok) {
      const all: ModelVersion[] = await res.json()
      detectorModels.value = all.filter((m) => m.kind === 'detector')
      binaryModels.value = all.filter((m) => m.kind === 'binary_classifier')
      groupModels.value = all.filter((m) => m.kind === 'group_classifier')
      const pickDefault = (list: ModelVersion[]) => list.find((m) => m.is_active) ?? list[0]
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

const IMAGE_EXT_RE = /\.(jpe?g|png|webp)$/i

function onUploadSelect(files: File[]) {
  // Folder drops include hidden / non-image siblings; drop them before
  // counting so the summary reflects what would actually be uploaded.
  const images = files.filter((f) => f.type.startsWith('image/') || IMAGE_EXT_RE.test(f.name))
  if (!images.length) return
  pickedFiles.value = pickedFiles.value.concat(images)
}

// Cap concurrent uploads so 12k-image batches don't open 12k sockets and
// trip browser / server connection limits. 6 in flight is a good balance
// for HTTP/1.1 servers and stays comfortably below typical Chrome caps.
const UPLOAD_CONCURRENCY = 6

async function uploadOne(file: File, uploadId: number): Promise<void> {
  const form = new FormData()
  form.append('file', file)
  form.append('module', 'pollinators')
  form.append('purpose', 'inference')
  form.append('upload', String(uploadId))
  const res = await api('/api/datasets/images/', {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      detail = body.detail || body.error || JSON.stringify(body)
    } catch {}
    throw new Error(`Upload failed for ${file.name}: ${detail}`)
  }
  uploadedCount.value += 1
}

async function uploadAll(uploadId: number): Promise<void> {
  const queue = [...pickedFiles.value]
  const workers: Promise<void>[] = []
  for (let i = 0; i < Math.min(UPLOAD_CONCURRENCY, queue.length); i++) {
    workers.push(
      (async () => {
        while (queue.length) {
          const file = queue.shift()
          if (!file) return
          await uploadOne(file, uploadId)
        }
      })(),
    )
  }
  await Promise.all(workers)
}

async function startDetection() {
  if (!canStart.value) return
  error.value = ''
  uploadedCount.value = 0
  submitting.value = true
  try {
    const draftRes = await api('/api/analysis/runs/draft/', {
      method: 'POST',
      body: JSON.stringify({
        module: 'pollinators',
        name: runName.value,
        config: config.value,
      }),
    })
    if (!draftRes.ok) {
      const body = await draftRes.text()
      throw new Error(`Could not create run draft: ${body || draftRes.status}`)
    }
    const draft = await draftRes.json()
    const runId: number = draft.run_id
    const uploadId: number = draft.upload_id

    await uploadAll(uploadId)

    const startRes = await api(`/api/analysis/runs/${runId}/start/`, {
      method: 'POST',
      body: JSON.stringify({}),
    })
    if (!startRes.ok) {
      const body = await startRes.text()
      throw new Error(`Could not start run: ${body || startRes.status}`)
    }
    await router.push(`/pollinators/runs/${runId}/detect`)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    submitting.value = false
  }
}
</script>
