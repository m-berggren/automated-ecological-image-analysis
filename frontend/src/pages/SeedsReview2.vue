<template>
  <PageHeader
    :title="headerTitle"
    subtitle="Review oriented classifications and analyze confidence distributions"
  />

  <SeedsStepper current="review-final" :runId="run?.id" />

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
                <span class="font-bold text-foreground">{{ initialAutomatedActiveCount }}</span>
              </div>
            </div>

            <div class="flex items-center gap-1">
              <input
                id="manual-count"
                type="number"
                min="0"
                v-model.number="manualActiveCount"
                class="w-14 px-1 py-1 rounded border border-border bg-background text-xs text-center font-bold focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <button
                type="button"
                class="px-2 py-1 bg-primary text-primary-foreground rounded text-[10px] font-medium hover:bg-primary/90 transition-colors shadow-sm"
                @click="saveCurrentPageCount"
                :disabled="savingCount"
              >
                {{ savingCount ? '...' : 'Save' }}
              </button>
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
import { computed, onMounted, ref, watch } from 'vue'
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
const savingCount = ref(false)

const run = ref<ClassificationBundle['run'] | null>(null)
const imagesList = ref<ReviewImage[]>([])
const currentImageIndex = ref(0)

const imageDetectionsMap = ref<Record<string, Detection[]>>({})
const initialMetricsLookupMap = ref<Record<string, BaselineMetrics>>({})
const manualActiveCount = ref<number>(0)
const initialAutomatedActiveCount = ref<number>(0)
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

    // Fetch current number of detections to set the manual input counter value correctly
    const currentList = imageDetectionsMap.value[newImage.filename] || []

    manualActiveCount.value = currentList.filter((d) => isActiveSeed(d)).length

    // Fetch initial model metrics from permanent lookup map
    const baseline = initialMetricsLookupMap.value[newImage.filename]
    if (baseline) {
      initialAutomatedActiveCount.value = baseline.automatedActiveCount
      initialOverallConfidenceScore.value = baseline.overallConfidenceScore
      initialSeedRangeMin.value = baseline.seedRangeMin
      initialSeedRangeMax.value = baseline.seedRangeMax
    }
    if (baseline.savedManualCount !== null) {
      manualActiveCount.value = baseline.savedManualCount
    } else {
      manualActiveCount.value = currentList.filter((d) => isActiveSeed(d)).length
    }
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
      manualActiveCount.value = Math.max(0, manualActiveCount.value - 1)
    } else {
      target.predicted_class = 'active'
      target.reviewer_status = 'confirmed'
      manualActiveCount.value++
    }

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
        manualActiveCount.value = prodMap[firstImg.filename].filter((d: any) =>
          isActiveSeed(d),
        ).length
      }
    }
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error)
  } finally {
    loading.value = false
  }
}

// Saves edits on current image
async function saveCurrentPageCount() {
  if (!currentImage.value || !run.value) return
  savingCount.value = true

  try {
    const confirmedDetections = currentDetections.value
    const activeIds = confirmedDetections.filter((d) => isActiveSeed(d)).map((d) => d.id)
    const abortedIds = confirmedDetections.filter((d) => !isActiveSeed(d)).map((d) => d.id)

    const apiPromises = []

    if (activeIds.length > 0) {
      apiPromises.push(
        api(`/api/analysis/detections/bulk/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ids: activeIds, reviewer_status: 'confirmed' }),
        }),
      )
    }

    if (abortedIds.length > 0) {
      apiPromises.push(
        api(`/api/analysis/detections/bulk/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ids: abortedIds, reviewer_status: 'rejected' }),
        }),
      )
    }

    apiPromises.push(
      api(`/api/seeds/images/${currentImage.value.id}/manual-count/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ manual_count: manualActiveCount.value }),
      }),
    )

    if (initialMetricsLookupMap.value[currentImage.value.filename]) {
      initialMetricsLookupMap.value[currentImage.value.filename].savedManualCount =
        manualActiveCount.value
    }

    // Await all queued requests
    if (apiPromises.length > 0) {
      const responses = await Promise.all(apiPromises)

      for (const res of responses) {
        if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to update database`)
      }
    }

    alert('Active counts updated.')
  } catch (error) {
    console.error(error)
    alert('Failed to execute bulk counts persistence transactions.')
  } finally {
    savingCount.value = false
  }
}

function navigateImage(direction: number) {
  const nextIndex = currentImageIndex.value + direction
  if (nextIndex >= 0 && nextIndex < totalImagesCount.value) {
    currentImageIndex.value = nextIndex
  }
}

function goBack() {
  router.push({ path: `/seeds/runs/${route.params.id}/review` })
}

function navigateToExport() {
  router.push({ path: `/seeds/runs/${route.params.id}/export` })
}
</script>
