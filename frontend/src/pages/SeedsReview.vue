<template>
  <PageHeader :title="headerTitle" subtitle="Review seed status classifications and calculations" />

  <SeedsStepper current="review" :runId="run?.id" />

  <div v-if="loading" class="flex-1 flex items-center justify-center text-sm text-muted-foreground">
    Loading classification results...
  </div>

  <div v-else-if="loadError" class="flex-1 flex items-center justify-center text-sm text-red-600">
    {{ loadError }}
  </div>

  <div v-else-if="currentImage" class="flex-1 flex flex-col min-h-0 bg-background">
    <section class="border-b border-border bg-surface px-6 py-4">
      <div
        class="max-w-7xl mx-auto flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6"
      >
        <div>
          <h2 class="text-base font-semibold flex items-center gap-2">
            Image Review
            <span class="text-sm font-normal text-muted-foreground">
              ({{ currentImageIndex + 1 }} of {{ totalImagesCount }})
            </span>
          </h2>
          <p class="text-xs text-muted-foreground mt-0.5 font-mono">
            {{ currentImage.filename }}
          </p>
        </div>

        <div
          class="grid grid-cols-2 md:grid-cols-3 gap-4 bg-muted/20 p-3 rounded-xl border border-border flex-1 max-w-2xl"
        >
          <div class="px-2 border-r border-border/60">
            <span
              class="text-[10px] text-muted-foreground block font-bold uppercase tracking-wider"
            >
              Mean Confidence
            </span>
            <div class="text-base font-mono font-bold text-foreground mt-0.5">
              {{ (initialOverallConfidenceScore * 100).toFixed(1) }}%
            </div>
          </div>

          <div class="px-2 border-r border-border/60">
            <span
              class="text-[10px] text-muted-foreground block font-bold uppercase tracking-wider"
            >
              Approximate Range
            </span>
            <div class="text-base font-mono font-bold text-foreground mt-0.5">
              {{ initialSeedRangeMin }} – {{ initialSeedRangeMax }}
              <span class="text-[10px] text-muted-foreground font-normal">seeds</span>
            </div>
          </div>

          <div
            class="px-2 col-span-2 md:col-span-1 flex items-center justify-between gap-2 bg-background/50 p-1.5 rounded-lg border border-border/40"
          >
            <div>
              <span
                class="text-[10px] text-muted-foreground block font-medium uppercase tracking-tight"
              >
                Active Seeds
              </span>
              <div class="text-xs text-muted-foreground font-mono">
                <!-- Model's automated count, immutable. The adjustment
                     input below tweaks the actual count saved/exported. -->
                <span class="font-bold text-foreground">{{ initialAutomatedActiveCount }}</span>
                <template v-if="manualActiveDelta !== 0">
                  <span class="mx-1">-></span>
                  <span class="font-bold text-foreground">{{ actualActiveCount }}</span>
                </template>
              </div>
            </div>

            <div class="flex items-center gap-1">
              <input
                id="manual-count"
                type="number"
                v-model.number="manualActiveDelta"
                title="Adjustment to the model's count. Negative removes, positive adds."
                placeholder="0"
                class="w-14 px-1 py-1 rounded border border-border bg-background text-xs text-center font-bold focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <span
                v-if="saveStatus"
                class="text-[10px] text-muted-foreground italic"
              >
                {{ saveStatus }}
              </span>
            </div>
          </div>
        </div>

        <div class="flex items-center gap-2 shrink-0">
          <button
            type="button"
            class="p-2 rounded-md border border-border bg-surface hover:bg-muted transition-colors disabled:opacity-40 disabled:cursor-not-allowed text-xs font-medium"
            :disabled="currentImageIndex === 0"
            @click="navigateImage(-1)"
          >
            ← Prev
          </button>
          <button
            type="button"
            class="p-2 rounded-md border border-border bg-surface hover:bg-muted transition-colors disabled:opacity-40 disabled:cursor-not-allowed text-xs font-medium"
            :disabled="currentImageIndex === totalImagesCount - 1"
            @click="navigateImage(1)"
          >
            Next →
          </button>
        </div>
      </div>
    </section>

    <div
      class="bg-muted/20 px-6 py-2 border-b border-border flex items-center gap-4 text-xs font-medium"
    >
      <span class="text-muted-foreground">Legend:</span>
      <span class="flex items-center gap-1.5">
        <span class="w-3 h-3 rounded-full bg-green-500 block border border-green-600"></span> Active
        Seed
      </span>
      <span class="flex items-center gap-1.5">
        <span class="w-3 h-3 rounded-full bg-red-500 block border border-red-600"></span> Aborted /
        Inactive Seed
      </span>
      <span class="text-muted-foreground font-normal italic ml-auto hidden sm:inline">
        Click on a bounding box to toggle its status manually.
      </span>
    </div>

    <section class="flex-1 overflow-auto p-6">
      <div
        class="relative w-full overflow-hidden rounded-2xl border border-border bg-black/5 shadow-sm"
      >
        <div
          class="absolute top-4 right-4 z-10 flex items-center bg-surface border border-border rounded-lg shadow-md overflow-hidden text-sm"
        >
          <button @click="zoomOut" class="px-3 py-2 hover:bg-muted font-bold text-lg leading-none">
            −
          </button>
          <button
            @click="resetZoom"
            class="px-3 py-2 hover:bg-muted border-x border-border font-medium"
          >
            {{ Math.round(zoom * 100) }}%
          </button>
          <button @click="zoomIn" class="px-3 py-2 hover:bg-muted font-bold text-lg leading-none">
            +
          </button>
        </div>
        <div class="relative w-full h-[65vh] overflow-auto">
          <div
            class="relative w-full transition-transform duration-200"
            :style="{ transform: `scale(${zoom})`, transformOrigin: 'top left' }"
          >
            <img
              :src="currentImage.image_url"
              :alt="currentImage.filename"
              class="w-full h-auto select-none block"
              draggable="false"
            />

            <svg
              :viewBox="`0 0 ${currentImage.width} ${currentImage.height}`"
              preserveAspectRatio="none"
              class="absolute inset-0 w-full h-full pointer-events-none select-none"
            >
              <polygon
                v-for="detection in currentDetections"
                :key="detection.id"
                :points="getPolygonPoints(detection)"
                stroke-width="12"
                class="pointer-events-auto cursor-pointer transition-all duration-150 fill-transparent hover:fill-current/10"
                :class="
                  isActiveSeed(detection)
                    ? 'stroke-green-500 text-green-500 hover:stroke-green-400'
                    : 'stroke-red-500 text-red-500 hover:stroke-red-400'
                "
                @click="toggleSeedStatus(detection.id)"
                :title="`Confidence: ${(detection.confidence * 100).toFixed(1)}%`"
              />
            </svg>
          </div>
        </div>
      </div>
    </section>

    <footer class="border-t border-border bg-surface px-6 py-4 mt-auto">
      <div class="max-w-7xl mx-auto flex items-center justify-between gap-4">
        <div class="text-sm text-muted-foreground">
          Review metrics can be exported as unified datasets in the final step.
        </div>

        <div class="flex items-center gap-3">
          <button
            type="button"
            class="px-4 py-2 rounded-md border border-border hover:bg-muted text-sm font-medium transition-colors"
            @click="goBack"
          >
            Back
          </button>

          <button
            type="button"
            class="px-5 py-2 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 text-sm font-medium transition-colors shadow-sm"
            @click="navigateToExport"
          >
            Export
          </button>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import SeedsStepper from '@/components/SeedsStepper.vue'
import { api } from '@/api'

interface Detection {
  id: number
  confidence: number
  predicted_class: string
  area: number
  reviewer_status: 'unreviewed' | 'confirmed' | 'rejected'
  source_image_filename: string
  polygon?: number[]
  bbox?: any
  poly?: number[]
}

interface ReviewImage {
  id: number
  filename: string
  image_url: string
}

interface ClassificationBundle {
  run: { id: number; name: string; status: string; detection_count: number }
  images_list: ReviewImage[]
  detections: Detection[]
}

interface BaselineMetrics {
  automatedActiveCount: number
  overallConfidenceScore: number
  seedRangeMin: number
  seedRangeMax: number
  savedManualCount: number | null
}

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const loadError = ref('')
const zoom = ref(1)
// Auto-save state. saveStatus is a short user-visible string ("Saving…",
// "Saved", "Error: …") that the header chip surfaces; null hides it.
const saveStatus = ref<string | null>(null)
let pendingSaveTimer: ReturnType<typeof setTimeout> | null = null
let inFlightSave: Promise<void> | null = null
// True while the image-change watch is mutating manualActiveDelta back to
// the baseline-derived value. The delta-watch checks this so loading a
// new image doesn't trigger a spurious save.
let loadingBaseline = false
const SAVE_DEBOUNCE_MS = 600
const SAVED_PILL_MS = 1500

const run = ref<ClassificationBundle['run'] | null>(null)
const imagesList = ref<ReviewImage[]>([])
const currentImageIndex = ref(0)

const imageDetectionsMap = ref<Record<string, Detection[]>>({})
const initialMetricsLookupMap = ref<Record<string, BaselineMetrics>>({})
// Delta from the model's automated count, not an absolute. 0 means "model
// got it right". Negative means the user is removing seeds, positive means
// they're adding. The actual count saved/exported is initial + delta.
const manualActiveDelta = ref<number>(0)
const initialAutomatedActiveCount = ref<number>(0)
const actualActiveCount = computed(
  () => initialAutomatedActiveCount.value + manualActiveDelta.value,
)
const initialOverallConfidenceScore = ref<number>(0)
const initialSeedRangeMin = ref<number>(0)
const initialSeedRangeMax = ref<number>(0)

const isPreviewMode = computed(() => {
  const hasRunId = route.params.id && route.params.id !== 'undefined'
  if (hasRunId) return false

  return route.query.preview === 'default' || import.meta.env.DEV
})

const currentImage = computed<ReviewImage | null>(() => {
  return imagesList.value[currentImageIndex.value] || null
})

const totalImagesCount = computed(() => imagesList.value.length)

const headerTitle = computed(() =>
  run.value
    ? `Seed Classification Review · ${run.value.name || `Run #${run.value.id}`}`
    : 'Seed Classification Review',
)

const currentDetections = computed<Detection[]>(() => {
  if (!currentImage.value) return []
  return imageDetectionsMap.value[currentImage.value.filename] || []
})

// Retrieves the initial seed count metrics from the permanent map and keeps manual input synced
watch(
  currentImage,
  (newImage) => {
    if (!newImage) return

    const currentList = imageDetectionsMap.value[newImage.filename] || []

    // Fetch initial model metrics from permanent lookup map
    const baseline = initialMetricsLookupMap.value[newImage.filename]
    if (baseline) {
      initialAutomatedActiveCount.value = baseline.automatedActiveCount
      initialOverallConfidenceScore.value = baseline.overallConfidenceScore
      initialSeedRangeMin.value = baseline.seedRangeMin
      initialSeedRangeMax.value = baseline.seedRangeMax
    }
    // Delta is the difference between what we'll actually save and the
    // model's automated count. If the user already saved a manual count
    // for this image, restore the delta that yields it. Otherwise default
    // to 0 (no adjustment from the model). loadingBaseline shields the
    // delta-watch from treating this assignment as a user edit.
    loadingBaseline = true
    if (baseline?.savedManualCount !== null && baseline?.savedManualCount !== undefined) {
      manualActiveDelta.value = baseline.savedManualCount - initialAutomatedActiveCount.value
    } else {
      manualActiveDelta.value = 0
    }
    loadingBaseline = false
    // Suppress unused warning while keeping the variable in scope for
    // future per-detection-driven UI cues.
    void currentList
  },
  { immediate: true },
)

function zoomIn() {
  zoom.value = Math.min(zoom.value + 0.25, 4)
}
function zoomOut() {
  zoom.value = Math.max(zoom.value - 0.25, 0.5)
}
function resetZoom() {
  zoom.value = 1
}

function isActiveSeed(detection: Detection): boolean {
  const statusString = detection.predicted_class || (detection as any).viability_status || ''
  return statusString.toLowerCase() === 'active'
}

// Updates bounding box state and input values
function toggleSeedStatus(detectionId: number) {
  if (!currentImage.value) return
  const filename = currentImage.value.filename
  const detectionsList = imageDetectionsMap.value[filename] || []
  const target = detectionsList.find((d) => d.id === detectionId)

  if (target) {
    const currentClass = (target.predicted_class || '').toLowerCase()

    if (currentClass === 'active') {
      target.predicted_class = 'aborted'
      target.reviewer_status = 'confirmed'
      // Lose one active seed → delta goes down by one. Allow negative
      // values: the user can keep removing past the model's count.
      manualActiveDelta.value -= 1
    } else {
      target.predicted_class = 'active'
      target.reviewer_status = 'confirmed'
      manualActiveDelta.value += 1
    }
    scheduleSave()

    console.log(`Box #${detectionId} successfully toggled to: ${target.predicted_class}`)
  }
}

function getPolygonPoints(detection: Detection): string {
  const p =
    detection.polygon || (detection.bbox && detection.bbox.poly) || detection.bbox || detection.poly
  if (!p || p.length < 8) return ''
  return `${p[0]},${p[1]} ${p[2]},${p[3]} ${p[4]},${p[5]} ${p[6]},${p[7]}`
}

onMounted(async () => {
  await initializeReviewBundle()
})

// Initialize the run session data structure
async function initializeReviewBundle() {
  const id = route.params.id as string

  loading.value = true

  try {
    const response = await api(`/api/seeds/runs/${id}/reference-review/`)

    if (!response.ok) {
      loadError.value = `HTTP Server Configuration Load Error`
      return
    }

    const data = await response.json()
    run.value = data.run
    imagesList.value = data.images

    const prodMap: Record<string, Detection[]> = {}

    imagesList.value.forEach((img: any) => {
      const detections = img.detections || []
      const filteredDetections = detections.map((d: any) => ({
        ...d,
        predicted_class: d.class || d.predicted_class || 'aborted',
        poly: d.polygon || d.poly || [],
      }))

      prodMap[img.filename] = filteredDetections

      const initialActive = filteredDetections.filter((d: any) => isActiveSeed(d))

      initialMetricsLookupMap.value[img.filename] = {
        automatedActiveCount: initialActive.length,
        overallConfidenceScore: img.overall_confidence || 0,
        seedRangeMin: img.seed_range_min || 0,
        seedRangeMax: img.seed_range_max || 0,
        savedManualCount: img.manual_active_count !== undefined ? img.manual_active_count : null,
      }
    })

    imageDetectionsMap.value = prodMap
    currentImageIndex.value = 0

    if (imagesList.value.length > 0) {
      const firstImg = imagesList.value[0]
      const baseline = initialMetricsLookupMap.value[firstImg.filename]
      if (baseline) {
        initialAutomatedActiveCount.value = baseline.automatedActiveCount
        initialOverallConfidenceScore.value = baseline.overallConfidenceScore
        initialSeedRangeMin.value = baseline.seedRangeMin
        initialSeedRangeMax.value = baseline.seedRangeMax
        // First-image bootstrap before the watch fires. No saved manual
        // count yet, so start with zero delta.
        manualActiveDelta.value = 0
      }
    }
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error)
  } finally {
    loading.value = false
  }
}

// Save the current image's edits (per-detection statuses + manual count).
// Awaits the previous in-flight save so two debounced saves can't race a
// stale payload over a fresh one.
async function persistCurrentImage(filename: string, imageId: number) {
  if (inFlightSave) {
    try { await inFlightSave } catch { /* swallow: handled by its caller */ }
  }
  const work = (async () => {
    const list = imageDetectionsMap.value[filename] || []
    const activeIds = list.filter((d) => isActiveSeed(d)).map((d) => d.id)
    const abortedIds = list.filter((d) => !isActiveSeed(d)).map((d) => d.id)
    // Backend stores manual_count as an absolute; the delta is UI-only.
    const baseline = initialMetricsLookupMap.value[filename]
    const initial = baseline?.automatedActiveCount ?? 0
    const savedCount = initial + manualActiveDelta.value

    const requests: Promise<Response>[] = []
    if (activeIds.length > 0) {
      requests.push(
        api(`/api/analysis/detections/bulk/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ids: activeIds, reviewer_status: 'confirmed' }),
        }),
      )
    }
    if (abortedIds.length > 0) {
      requests.push(
        api(`/api/analysis/detections/bulk/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ids: abortedIds, reviewer_status: 'rejected' }),
        }),
      )
    }
    requests.push(
      api(`/api/seeds/images/${imageId}/manual-count/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ manual_count: savedCount }),
      }),
    )

    const responses = await Promise.all(requests)
    for (const res of responses) {
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
    }
    if (baseline) baseline.savedManualCount = savedCount
  })()
  inFlightSave = work
  try {
    await work
  } finally {
    if (inFlightSave === work) inFlightSave = null
  }
}

// Track which image a pending save belongs to so a navigate that fires
// while the timer is queued doesn't accidentally save the new image's
// state under the old image's key.
let pendingSaveTarget: { filename: string; imageId: number } | null = null

function scheduleSave() {
  if (!currentImage.value || !run.value) return
  pendingSaveTarget = {
    filename: currentImage.value.filename,
    imageId: currentImage.value.id,
  }
  if (pendingSaveTimer) clearTimeout(pendingSaveTimer)
  saveStatus.value = 'Saving…'
  pendingSaveTimer = setTimeout(() => {
    pendingSaveTimer = null
    void runSave()
  }, SAVE_DEBOUNCE_MS)
}

async function runSave() {
  const target = pendingSaveTarget
  if (!target) return
  pendingSaveTarget = null
  try {
    await persistCurrentImage(target.filename, target.imageId)
    saveStatus.value = 'Saved'
    setTimeout(() => {
      if (saveStatus.value === 'Saved') saveStatus.value = null
    }, SAVED_PILL_MS)
  } catch (error) {
    console.error('Auto-save failed:', error)
    saveStatus.value = 'Save failed'
  }
}

// Run any pending debounced save immediately. Used before navigating
// away from an image and on component teardown.
async function flushSave() {
  if (pendingSaveTimer) {
    clearTimeout(pendingSaveTimer)
    pendingSaveTimer = null
    await runSave()
  } else if (inFlightSave) {
    try { await inFlightSave } catch { /* surfaced via saveStatus */ }
  }
}

async function navigateImage(direction: number) {
  const nextIndex = currentImageIndex.value + direction
  if (nextIndex < 0 || nextIndex >= totalImagesCount.value) return
  // Flush before swapping currentImage so the still-pending edits are
  // saved against the old image, not the new one.
  await flushSave()
  currentImageIndex.value = nextIndex
}

// Auto-save when the delta input changes. Toggling a detection already
// calls scheduleSave from toggleSeedStatus, so this watcher covers the
// direct-input path. loadingBaseline suppresses saves caused by the
// image-change watcher resetting the delta back to its baseline.
watch(manualActiveDelta, () => {
  if (loadingBaseline) return
  if (!currentImage.value) return
  scheduleSave()
})

onBeforeUnmount(() => {
  void flushSave()
})

function goBack() {
  router.push({ path: `/seeds/runs/${route.params.id}/set-reference` })
}

function navigateToExport() {
  router.push({ path: `/seeds/runs/${route.params.id}/export` })
}
</script>
