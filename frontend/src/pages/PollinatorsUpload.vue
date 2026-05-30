<template>
  <PageHeader title="Upload" subtitle="Configure and upload a camera-trap folder" />
  <PollinatorsStepper current="upload" />

  <div class="flex-1 min-h-0 overflow-y-auto px-8 py-4 space-y-3 max-w-3xl mx-auto w-full">
    <!-- Run details -->
    <section class="rounded-xl border border-border bg-surface p-5 space-y-3">
      <h2 class="text-sm font-semibold">Run details</h2>
      <div class="space-y-2">
        <div class="flex items-center gap-1.5 text-xs text-muted-foreground">
          <label>Name <span class="text-red-600" aria-hidden="true">*</span></label>
          <InfoPopover>
            Free-text label used everywhere this run appears: the Runs list, the Detect stepper, CSV
            exports. Convention is site-plot-camera, e.g.
            <span class="font-mono">enbranten-aral_p1-101_WSCT</span>.
          </InfoPopover>
        </div>
        <input
          v-model="runName"
          type="text"
          required
          placeholder="e.g. enbranten-aral_p1-101_WSCT"
          class="w-full px-3 py-2 text-sm rounded-md border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
      </div>
    </section>

    <!-- Detection settings -->
    <section class="rounded-xl border border-border bg-surface p-5 space-y-4">
      <h2 class="text-sm font-semibold">Detection settings</h2>

      <!-- Two columns: YOLO detector on the left, 2-step Classification
           (Binary + Group, with one shared Confidence below) on the right.
           Same card styling as the surrounding sections — no special
           framing on the right column. -->
      <div class="grid grid-cols-1 md:grid-cols-[1fr_2fr] gap-6">
        <!-- YOLO column. -->
        <div class="space-y-3">
          <label class="space-y-1 block">
            <span class="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span class="font-semibold">YOLO</span>
              <InfoPopover>
                The detector. Finds insect bounding boxes anywhere in the frame using a CNN trained
                on labelled crops. Runs on every image regardless of motion.
              </InfoPopover>
            </span>
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
          <label class="space-y-1 block w-24">
            <span class="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span>Confidence</span>
              <InfoPopover>
                Minimum YOLO confidence to keep a detection. Lower = more candidates and more false
                positives surfaced for review.
              </InfoPopover>
            </span>
            <input
              v-model.number="config.yolo.confidence"
              type="number"
              min="0"
              max="1"
              step="0.05"
              class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm font-mono text-center"
            />
          </label>
        </div>

        <!-- 2-step Classification column: two model selects in a row,
             then a single shared Confidence input centered below. -->
        <div class="space-y-3 md:border-l md:border-border md:pl-6">
          <div class="grid grid-cols-2 gap-4">
            <label class="space-y-1 block">
              <span class="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span>Binary Classifier</span>
                <InfoPopover>
                  The insect/background gate (formerly "EfficientNet"). Every motion-detected crop
                  runs through this first; non-insect crops are dropped before the group classifier
                  sees them.
                </InfoPopover>
              </span>
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
            <label class="space-y-1 block">
              <span class="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span>Group Classifier</span>
                <InfoPopover>
                  Assigns insect crops to one of: bumblebee, fly, butterfly, other (formerly
                  "InsectNet"). Runs only on crops the Binary Classifier accepted.
                </InfoPopover>
              </span>
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
          <!-- Single Confidence centered under the two selectors. Writes
               to both stage thresholds. -->
          <label class="space-y-1 block w-24 mx-auto">
            <span class="flex items-center gap-1.5 text-xs text-muted-foreground justify-center">
              <span>Confidence</span>
              <InfoPopover>
                Applied to both stages: the Binary Classifier must exceed this for "insect", AND the
                Group Classifier's top-class probability must exceed it to keep the assigned class.
                Below this the detection is kept but the class is stripped so a reviewer assigns
                one.
              </InfoPopover>
            </span>
            <input
              :value="twoStepConfidence"
              type="number"
              min="0"
              max="1"
              step="0.05"
              class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm font-mono text-center"
              @input="onTwoStepConfidenceInput(($event.target as HTMLInputElement).value)"
            />
          </label>
        </div>
      </div>

      <!-- Misc row -->
      <div class="flex flex-wrap items-center gap-x-6 gap-y-3 pt-2 border-t border-border">
        <label class="flex items-center gap-2 text-sm">
          <input v-model="config.preprocessing.use_roi" type="checkbox" />
          <span>Use manual ROI</span>
          <InfoPopover>
            Restrict both YOLO and the motion branch to a user-drawn rectangle so detections outside
            the area of interest (e.g. ground beyond the plot) are ignored. The drawing UI lives
            upstream on main.
          </InfoPopover>
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
        “Start at image” is outside the picked range (max {{ pickedFiles.length }}).
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
            <span class="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span>Crop padding</span>
              <InfoPopover>
                Motion branch only (does not affect YOLO). Extra context around each motion bbox
                before it's sent to the binary/group classifiers, as a fraction of the box's larger
                side. 0.3 = 30% padding. A bit of context helps the classifiers distinguish insect
                from background.
              </InfoPopover>
            </span>
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
            <span class="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span>Min contour area (px²)</span>
              <InfoPopover>
                Motion branch only (does not affect YOLO). Smallest motion blob treated as a
                candidate before classification. Lower = catches small insects but also more noise
                (wind on grass, sensor flicker); higher = misses tiny visitors.
              </InfoPopover>
            </span>
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
            <span class="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span>Max contour area (px²)</span>
              <InfoPopover>
                Motion branch only (does not affect YOLO). Largest blob treated as a single motion
                candidate. Above this the blob is split into multiple tiles (see "Detect large
                motion").
              </InfoPopover>
            </span>
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
            <span class="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span>Background sample size</span>
              <InfoPopover>
                Motion branch only (does not affect YOLO). Number of frames evenly spaced across the
                upload used to build a per-pixel-median fallback background. Used when the previous
                frame isn't a valid motion reference (first image, large EXIF time gap, shape
                mismatch). 0 = skip; rely purely on prev-frame diffs.
              </InfoPopover>
            </span>
            <input
              v-model.number="config.preprocessing.background_sample_size"
              type="number"
              min="0"
              max="500"
              class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm font-mono"
            />
          </label>
          <label class="space-y-1">
            <span class="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span>Sunny shutter threshold</span>
              <InfoPopover>
                Shutter-speed denominator above which an EXIF frame is tagged "sunny" rather than
                "cloudy". Only affects the per-image weather label in exports; detection itself
                doesn't use it.
              </InfoPopover>
            </span>
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
            <span>Skip flash frames</span>
            <InfoPopover>
              Skip frames where the EXIF flash flag fired. The flash washes out colour and creates
              spurious motion edges. Skipped frames produce zero detections from both YOLO and the
              motion branch.
            </InfoPopover>
          </label>
          <label class="flex items-center gap-2 text-sm">
            <input v-model="config.preprocessing.skip_foggy" type="checkbox" />
            <span>Skip foggy frames</span>
            <InfoPopover>
              Skip frames whose Laplacian variance is below the foggy threshold (low edge contrast =
              likely fog or extreme blur). Skipped frames produce zero detections from both YOLO and
              the motion branch.
            </InfoPopover>
          </label>
          <label class="flex items-center gap-2 text-sm">
            <input v-model="config.preprocessing.enable_large_motion" type="checkbox" />
            <span>Detect large motion</span>
            <InfoPopover>
              Instead of dropping over-sized motion regions, split them into multi-scale tiles plus
              biased-low fallback crops. Catches the case where a bumblebee pulls on a flower and
              the whole flower moves with it.
            </InfoPopover>
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
        <div class="text-sm flex items-center gap-3">
          <template v-if="pickedFiles.length">
            <span>
              <span class="font-medium">{{ pickedFiles.length.toLocaleString() }}</span>
              <span class="text-muted-foreground"
                >&nbsp;{{ pickedFiles.length === 1 ? 'image' : 'images' }} selected ·
                {{ formatBytes(totalPickedBytes) }}</span
              >
            </span>
            <button
              v-if="!submitting"
              class="text-xs px-2 py-1 rounded-md border border-border text-muted-foreground hover:bg-muted hover:text-red-600"
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
            v-if="submitting"
            :disabled="cancelling"
            class="px-3 py-1.5 rounded-md text-sm font-medium border border-red-300 text-red-700 hover:bg-red-50 disabled:opacity-50 disabled:cursor-not-allowed"
            @click="cancelUpload"
          >
            {{ cancelling ? 'Cancelling…' : 'Cancel' }}
          </button>
          <button
            :disabled="!canStart"
            :title="startDisabledReason"
            class="px-3 py-1.5 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
            @click="startDetection"
          >
            Start detection
          </button>
        </div>
      </header>
      <div v-if="submitting" class="px-5 pb-3 space-y-1">
        <div class="flex items-center gap-2 text-[11px] font-mono text-muted-foreground">
          <span class="tabular-nums">
            {{ uploadedCount.toLocaleString() }} / {{ pickedFiles.length.toLocaleString() }}
          </span>
          <span>images</span>
          <span class="ml-auto tabular-nums">{{ uploadPercent }}%</span>
        </div>
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
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import PollinatorsStepper from '@/components/PollinatorsStepper.vue'
import UploadDropZone, { type UploadTab } from '@/components/UploadDropZone.vue'
import InfoPopover from '@/components/InfoPopover.vue'
import { api } from '@/api'
import ROIDrawer from '@/components/ROIDrawer.vue'
import { confirm, resolveConfirm } from '@/lib/confirm'
import { API_BASE_URL } from '@/lib/config'
import { tokenManager } from '@/lib/token'

interface ModelVersion {
  id: number
  module: string
  kind: string
  version_name: string
  is_active: boolean
}

const showRoiModal = ref(false)
const previewUrl = ref<string | null>(null)

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
// Active draft run + its abort controller. Set the moment the user
// clicks Start detection so any teardown (route guard, beforeunload,
// catch block) can stop in-flight uploads and clean up the server.
const draftRunId = ref<number | null>(null)
let uploadAborter: AbortController | null = null
// Marks navigations the user has explicitly approved via the route
// guard, so we don't double-prompt or double-abort on the way out.
let approvedLeave = false

const detectorModels = ref<ModelVersion[]>([])
const binaryModels = ref<ModelVersion[]>([])
const groupModels = ref<ModelVersion[]>([])

interface PipelineConfig {
  yolo: { model_version_id: number | null; confidence: number }
  binary_classifier: { model_version_id: number | null; confidence: number }
  group_classifier: { model_version_id: number | null; confidence: number }
  start_at_image: number
  preprocessing: {
    use_roi: boolean
    // Persisted as [x, y, width, height] in source-image pixels — the shape
    // both the backend burn-in and ROIOverlay expect. ROIDrawer emits an
    // {x,y,width,height} object, converted at assignment below.
    roi_bbox: null | [number, number, number, number]
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
  start_at_image: 1,
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

// Single "Confidence" knob inside the 2-step Classification frame:
// writes to BOTH the binary and group thresholds so the two-stage
// classifier reads with one number from the reviewer's perspective.
// Displays the binary value (they're kept in sync, so either works as
// the source of truth for the input).
const twoStepConfidence = computed(() => config.value.binary_classifier.confidence)

function onTwoStepConfidenceInput(raw: string) {
  const v = Number.parseFloat(raw)
  if (Number.isNaN(v)) return
  const clamped = Math.max(0, Math.min(1, v))
  config.value.binary_classifier.confidence = clamped
  config.value.group_classifier.confidence = clamped
}

// "Start at image" must point into the picked file list. Recomputes
// any time pickedFiles or the input value changes.
const startAtImageOutOfRange = computed(() => {
  if (!pickedFiles.value.length) return false
  const idx = (config.value.start_at_image || 1) - 1
  return idx < 0 || idx >= pickedFiles.value.length
})

const totalPickedBytes = computed(() => pickedFiles.value.reduce((sum, f) => sum + f.size, 0))

const uploadPercent = computed(() => {
  if (!pickedFiles.value.length) return 0
  return Math.round((uploadedCount.value / pickedFiles.value.length) * 100)
})

const canStart = computed(() => {
  if (submitting.value) return false
  if (!runName.value.trim()) return false
  if (!pickedFiles.value.length) return false
  if (!config.value.yolo.model_version_id) return false
  if (!config.value.binary_classifier.model_version_id) return false
  if (!config.value.group_classifier.model_version_id) return false
  if (startAtImageOutOfRange.value) return false
  return true
})

const startDisabledReason = computed(() => {
  if (submitting.value) return 'Upload in progress'
  if (!runName.value.trim()) return 'Name is required'
  if (!pickedFiles.value.length) return 'Pick at least one image first'
  if (
    !config.value.yolo.model_version_id ||
    !config.value.binary_classifier.model_version_id ||
    !config.value.group_classifier.model_version_id
  ) {
    return 'All three models must be selected'
  }
  if (startAtImageOutOfRange.value) return '"Start at image" is past the last picked file'
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

async function uploadOne(file: File, uploadId: number, signal: AbortSignal): Promise<void> {
  const form = new FormData()
  form.append('file', file)
  form.append('module', 'pollinators')
  form.append('purpose', 'inference')
  form.append('upload', String(uploadId))
  const res = await api('/api/datasets/images/', {
    method: 'POST',
    body: form,
    signal,
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

async function uploadAll(uploadId: number, signal: AbortSignal): Promise<void> {
  const queue = [...pickedFiles.value]
  const workers: Promise<void>[] = []
  for (let i = 0; i < Math.min(UPLOAD_CONCURRENCY, queue.length); i++) {
    workers.push(
      (async () => {
        while (queue.length) {
          if (signal.aborted) return
          const file = queue.shift()
          if (!file) return
          await uploadOne(file, uploadId, signal)
        }
      })(),
    )
  }
  await Promise.all(workers)
}

// ROI modal: opens the ROIDrawer with the first picked image as preview,
// resolves a Promise with the drawn bbox or null if the user cancelled.
// The pending resolver lives in module-local state so the @close /
// @confirm template handlers can fulfil it from outside the function.
let roiResolver: ((bbox: RoiBBox | null) => void) | null = null

function openRoiModal(file: File): Promise<RoiBBox | null> {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = URL.createObjectURL(file)
  showRoiModal.value = true
  return new Promise((resolve) => {
    roiResolver = resolve
  })
}

function tearDownRoiModal() {
  showRoiModal.value = false
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = null
  }
}

function onSaveRoi(bbox: RoiBBox) {
  const resolve = roiResolver
  roiResolver = null
  tearDownRoiModal()
  resolve?.(bbox)
}

function closeRoiModal() {
  const resolve = roiResolver
  roiResolver = null
  tearDownRoiModal()
  resolve?.(null)
}

// Tear down the draft on the server. Used by the route guard before an
// approved leave and by the catch block when an upload fails. Idempotent:
// safe to call twice (the abort endpoint returns 204 on a missing run).
async function abortDraft(): Promise<void> {
  uploadAborter?.abort()
  uploadAborter = null
  const id = draftRunId.value
  draftRunId.value = null
  if (id === null) return
  try {
    await api(`/api/analysis/runs/${id}/abort/`, { method: 'POST' })
  } catch (e) {
    console.warn('Failed to abort draft run', e)
  }
}

// In-page cancel: prompts, then tears down the draft (aborts the in-
// flight upload, calls the abort endpoint to drop uploaded files + DB
// trace). Re-enables the form so the user can adjust and retry.
const cancelling = ref(false)
async function cancelUpload(): Promise<void> {
  if (!submitting.value || cancelling.value) return
  const ok = await confirm({
    title: 'Cancel the upload?',
    message: 'The run and any images already uploaded will be discarded.',
    confirmLabel: 'Cancel upload',
    cancelLabel: 'Keep uploading',
    variant: 'danger',
  })
  if (!ok) return
  cancelling.value = true
  try {
    await abortDraft()
  } finally {
    cancelling.value = false
    // startDetection's finally clears submitting, but the upload loop is
    // already aborted via the signal — clear here too in case the loop
    // hadn't started yet (e.g. user cancelled during the ROI modal).
    submitting.value = false
  }
}

async function startDetection() {
  if (!canStart.value) return
  error.value = ''
  uploadedCount.value = 0
  submitting.value = true
  uploadAborter = new AbortController()
  const signal = uploadAborter.signal
  try {
    // If manual ROI is on, draw it before anything else — the bbox needs
    // to ride along inside the draft's config. Cancelling the modal
    // cancels the whole start without touching the server.
    if (config.value.preprocessing.use_roi) {
      const bbox = await openRoiModal(pickedFiles.value[0])
      if (!bbox) {
        error.value = 'ROI selection was cancelled.'
        return
      }
      config.value.preprocessing.roi_bbox = [bbox.x, bbox.y, bbox.width, bbox.height]
    } else {
      config.value.preprocessing.roi_bbox = null
    }

    const draftRes = await api('/api/analysis/runs/draft/', {
      method: 'POST',
      body: JSON.stringify({
        module: 'pollinators',
        name: runName.value.trim(),
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
    draftRunId.value = runId

    await uploadAll(uploadId, signal)
    if (signal.aborted) return

    const startRes = await api(`/api/analysis/runs/${runId}/start/`, {
      method: 'POST',
      body: JSON.stringify({
        start_at_image: config.value.start_at_image || 1,
      }),
    })
    if (!startRes.ok) {
      const body = await startRes.text()
      throw new Error(`Could not start run: ${body || startRes.status}`)
    }
    // Once the worker is spawned the draft graduates to a real run; the
    // route guard no longer needs to tear it down. If a "leave and
    // discard?" prompt is still sitting on screen from a navigation the
    // user tried mid-upload, dismiss it now — the question is moot
    // because we're voluntarily routing to the Detect page and no
    // damage can be done from here.
    draftRunId.value = null
    approvedLeave = true
    resolveConfirm(false)
    await router.push(`/pollinators/runs/${runId}/detect`)
  } catch (e) {
    if (signal.aborted) {
      // User-initiated abort already cleaned up via abortDraft(); don't
      // surface that as an error.
      return
    }
    // Real failure mid-flight: drop whatever we got partway through.
    await abortDraft()
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    submitting.value = false
    uploadAborter = null
  }
}

// In-app navigation (sidebar link, browser back): show our own confirm
// dialog. If the user picks "Leave", tear down the draft before letting
// the route change proceed.
onBeforeRouteLeave(async () => {
  if (!submitting.value || approvedLeave) return true
  const ok = await confirm({
    title: 'Stop the upload?',
    message:
      'Leaving now stops the upload. The run and any images already uploaded will be discarded.',
    confirmLabel: 'Leave and discard',
    cancelLabel: 'Keep uploading',
    variant: 'danger',
  })
  if (!ok) return false
  approvedLeave = true
  await abortDraft()
  return true
})

// Tab close / hard browser navigation. beforeunload triggers the native
// "Leave site?" prompt (custom text is not honoured by modern browsers);
// the actual teardown ping fires from pagehide once the user confirms,
// so we don't nuke the draft when they hit "Cancel" on the prompt.
function onBeforeUnload(e: BeforeUnloadEvent) {
  if (!submitting.value) return
  e.preventDefault()
  e.returnValue = ''
}

function onPageHide() {
  if (!submitting.value || draftRunId.value === null) return
  // fetch with keepalive survives the page unload and preserves headers
  // (which sendBeacon cannot — and we need the Authorization header for
  // our JWT). The response is ignored; this is fire-and-forget.
  const token = tokenManager.getAccessToken()
  void fetch(`${API_BASE_URL}/api/analysis/runs/${draftRunId.value}/abort/`, {
    method: 'POST',
    keepalive: true,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  }).catch(() => {})
}

onMounted(() => {
  window.addEventListener('beforeunload', onBeforeUnload)
  window.addEventListener('pagehide', onPageHide)
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
  window.removeEventListener('pagehide', onPageHide)
})
</script>
