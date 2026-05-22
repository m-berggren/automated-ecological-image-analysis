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
                ML Counted:
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
      <div class="mx-auto max-w-5xl">
        <div class="relative overflow-hidden rounded-2xl border border-border bg-black/5 shadow-sm">
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
          />
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
  poly: number[] // Oriented Bounding Box: [x1, y1, x2, y2, x3, y3, x4, y4]
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
}

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const loadError = ref('')
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
  // If we have a real Run ID, we are NOT in preview mode, even in DEV
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
    console.log('Detections for this image:', currentList) // DEBUG

    manualActiveCount.value = currentList.filter((d) => isActiveSeed(d)).length

    // Fetch initial model metrics from permanent lookup map
    const baseline = initialMetricsLookupMap.value[newImage.filename]
    if (baseline) {
      initialAutomatedActiveCount.value = baseline.automatedActiveCount
      initialOverallConfidenceScore.value = baseline.overallConfidenceScore
      initialSeedRangeMin.value = baseline.seedRangeMin
      initialSeedRangeMax.value = baseline.seedRangeMax
    }
  },
  { immediate: true },
)

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
  // Handle both bbox and poly mode
  const p = detection.bbox || detection.poly
  if (!p || p.length < 8) return ''
  return `${p[0]},${p[1]} ${p[2]},${p[3]} ${p[4]},${p[5]} ${p[6]},${p[7]}`
}

onMounted(async () => {
  await initializeReviewBundle()
})

// Initialize the run session data structure
async function initializeReviewBundle() {
  const id = route.params.id as string

  if ((!id || id === 'undefined') && !isPreviewMode.value) {
    loadError.value = 'Route error: Run ID could not be extracted from the URL parameters.'
    loading.value = false
    return
  }

  loading.value = true

  try {
    if (isPreviewMode.value) {
      console.log('Preview mode: Initialized via seed-detections.json mock.')

      const rawModule = await import('@/mocks/seed-detections.json')
      const mocks = rawModule.default?.default || rawModule.default

      run.value = {
        id: (mocks.run?.id ?? Number(id)) || 1,
        name: mocks.run?.name ?? 'Mock Run',
        status: 'completed',
        detection_count: mocks.run?.detection_count ?? 12,
      }

      imagesList.value = mocks.run?.images_list || mocks.images_list || []

      const rawDetections = mocks.detections || []
      const distributedMap: Record<string, Detection[]> = {}

      imagesList.value.forEach((img) => {
        const imageDetections = rawDetections.map((det: any, index: number) => {
          const startX = 10 + ((index * 14) % 75)
          const startY = 20 + Math.floor(index / 5) * 20
          const sizeW = 7
          const sizeH = 10

          return {
            ...det,
            id: det.id + img.id * 1000,
            predicted_class: det.predicted_class || det.viability_status || 'aborted',
            poly: det.poly || [
              startX,
              startY,
              startX + sizeW,
              startY + 2,
              startX + sizeW - 1,
              startY + sizeH,
              startX - 1,
              startY + sizeH - 1,
            ],
          }
        })

        distributedMap[img.filename] = imageDetections

        // Calculate and cache the original model calculations the image before any user modifications happen
        const initialActive = imageDetections.filter((d) => isActiveSeed(d))
        const sumConfidence = imageDetections.reduce((acc, curr) => acc + curr.confidence, 0)

        initialMetricsLookupMap.value[img.filename] = {
          automatedActiveCount: initialActive.length,
          overallConfidenceScore:
            imageDetections.length > 0 ? sumConfidence / imageDetections.length : 0,
          seedRangeMin: imageDetections.filter((d) => d.confidence >= 0.75 && isActiveSeed(d))
            .length,
          seedRangeMax: initialActive.length,
        }
      })

      imageDetectionsMap.value = distributedMap
      currentImageIndex.value = 0

      manualActiveCount.value = currentDetections.value.filter((d) => isActiveSeed(d)).length
      loading.value = false
      return
    }

    // Connected API mode
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
      const filteredDetections = (img.detections || []).map((d: any) => ({
        ...d,
        poly: d.polygon || d.poly || [],
      }))

      prodMap[img.filename] = filteredDetections

      // Calculate the metrics using the extracted detections
      const initialActive = filteredDetections.filter((d: any) => isActiveSeed(d))
      const sumConfidence = filteredDetections.reduce(
        (acc: number, curr: any) => acc + curr.confidence,
        0,
      )
      initialMetricsLookupMap.value[img.filename] = {
        automatedActiveCount: initialActive.length,
        overallConfidenceScore:
          filteredDetections.length > 0 ? sumConfidence / filteredDetections.length : 0,
        seedRangeMin: filteredDetections.filter((d: any) => d.confidence >= 0.75 && isActiveSeed(d))
          .length,
        seedRangeMax: initialActive.length,
      }
    })

    imageDetectionsMap.value = prodMap

    currentImageIndex.value = 0
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

  if (isPreviewMode.value) {
    await new Promise((resolve) => setTimeout(resolve, 300))
    alert(
      `[MOCK] Metrics synchronized.\nSaved manual override adjustments for ${currentImage.value.filename}.`,
    )
    savingCount.value = false
    return
  }

  try {
    const confirmedDetections = currentDetections.value
    const activeIds = confirmedDetections.filter((d) => isActiveSeed(d)).map((d) => d.id)
    const abortedIds = confirmedDetections.filter((d) => !isActiveSeed(d)).map((d) => d.id)

    // Apply modifications using bulk views update endpoints schema
    await Promise.all([
      api(`/api/analysis/detections/bulk/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: activeIds, reviewer_status: 'confirmed' }),
      }),
      api(`/api/analysis/detections/bulk/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: abortedIds, reviewer_status: 'rejected' }),
      }),
    ])
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
