<template>
  <PageHeader :title="headerTitle" subtitle="Select a healthy active seed as the reference seed" />

  <SeedsStepper current="review" :runId="run?.id" />

  <!-- Loading -->
  <div v-if="loading" class="flex-1 flex items-center justify-center text-sm text-muted-foreground">
    Loading...
  </div>

  <!-- Error -->
  <div v-else-if="loadError" class="flex-1 flex items-center justify-center text-sm text-red-600">
    {{ loadError }}
  </div>

  <!-- Main layout -->
  <div v-else-if="images.length" class="flex-1 flex flex-col min-h-0 bg-background">
    <!-- Instructions -->
    <section class="border-b border-border bg-surface px-6 py-5">
      <div class="max-w-5xl">
        <h2 class="text-lg font-semibold">Select a reference active seed</h2>

        <p class="mt-2 text-sm text-muted-foreground leading-relaxed">
          Click on one healthy active seed in the image. This seed will be used as the reference
          example for determining which detected seeds are active versus aborted.
        </p>

        <div class="mt-4 flex flex-wrap items-center gap-3 text-sm">
          <div class="px-3 py-1 rounded-full bg-muted text-muted-foreground">
            {{ currentDetections.length }} detected seeds
          </div>

          <div v-if="selectedReference" class="px-3 py-1 rounded-full bg-green-100 text-green-700">
            Reference seed selected
          </div>
        </div>
      </div>
    </section>

    <!-- IMAGE AREA -->
    <section class="flex-1 overflow-auto p-6">
      <div class="mx-auto max-w-7xl">
        <!-- IMAGE WRAPPER -->
        <div
          class="relative w-full overflow-hidden rounded-2xl border border-border bg-black/5 shadow-sm"
        >
          <div class="flex items-center justify-between mb-3">
            <button
              class="px-3 py-1 border rounded"
              :disabled="currentImageIndex === 0"
              @click="currentImageIndex--"
            >
              Prev
            </button>

            <div class="text-sm text-muted-foreground">
              Image {{ currentImageIndex + 1 }} / {{ images.length }}
            </div>

            <button
              class="px-3 py-1 border rounded"
              :disabled="currentImageIndex === images.length - 1"
              @click="currentImageIndex++"
            >
              Next
            </button>
          </div>
          <div class="relative w-full">
            <svg
              ref="svgRef"
              class="absolute inset-0 w-full h-full"
              :viewBox="`0 0 ${currentImage.width} ${currentImage.height}`"
              preserveAspectRatio="none"
              style="pointer-events: none"
            >
              <polygon
                v-for="detection in currentDetections"
                :key="detection.id"
                :points="polyPoints(detection)"
                fill="transparent"
                :stroke="selectedReferenceId === detection.id ? '#22c55e' : '#60a5fa'"
                stroke-width="3"
                style="pointer-events: all; cursor: pointer"
                :class="selectedReferenceId === detection.id ? 'ring-highlight' : ''"
                @click="selectReference(detection.id)"
              />
            </svg>

            <img
              ref="imageRef"
              :src="currentImage.image_url"
              :alt="currentImage.filename"
              class="w-full h-auto block select-none"
              draggable="false"
            />
          </div>
        </div>
      </div>
    </section>

    <!-- Footer -->
    <footer class="border-t border-border bg-surface px-6 py-4">
      <div class="flex items-center justify-between gap-4">
        <!-- Left -->
        <div class="text-sm text-muted-foreground">
          <template v-if="selectedReference">
            Selected reference seed:
            <span class="font-medium text-foreground"> #{{ selectedReference.id }} </span>
          </template>

          <template v-else> Select one healthy seed to continue. </template>
        </div>

        <!-- Right -->
        <div class="flex items-center gap-3">
          <button
            v-if="selectedReference"
            type="button"
            class="px-4 py-2 rounded-md border border-border hover:bg-muted transition-colors"
            @click="clearReference"
          >
            Reselect
          </button>

          <button
            type="button"
            class="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="!selectedReference"
            @click="proceedToCalculation"
          >
            Continue
          </button>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import SeedsStepper from '@/components/SeedsStepper.vue'

import { api } from '@/api'

//Types
interface Detection {
  id: number
  confidence: number
  class: string

  bbox: {
    x1: number
    y1: number
    x2: number
    y2: number
    w: number
    h: number
  }
}

interface ReviewImage {
  id: number
  filename: string
  image_url: string

  width: number
  height: number

  detections: Detection[]
}

interface ReviewBundle {
  run: {
    id: number
    name: string
    status: string
  }

  images: ReviewImage[]

  detections: Detection[]
}

//Routing
const route = useRoute()
const router = useRouter()

//State
const loading = ref(true)
const loadError = ref('')

const run = ref<ReviewBundle['run'] | null>(null)

const images = ref<ReviewImage[]>([])
const currentImageIndex = ref(0)

const currentImage = computed(() => images.value[currentImageIndex.value] ?? null)
const currentDetections = computed(() => currentImage.value?.detections ?? [])

const selectedReferenceId = ref<number | null>(null)

const imageRef = ref<HTMLImageElement | null>(null)
const imageSize = ref({ width: 0, height: 0 })

//Computation
const previewMode = computed(() => {
  const value = route.query.preview

  return typeof value === 'string' ? value : null
})

const headerTitle = computed(() =>
  run.value ? `Seed Reference Review · ${run.value.name}` : 'Seed Reference Review',
)

const selectedReference = computed(() =>
  currentDetections.value.find((detection) => detection.id === selectedReferenceId.value),
)

// Converts flat coordinate points to SVG points string
// This is to prevent needing scaling for matching correct position of boundingboxes in frontend page.
function polyPoints(detection: Detection): string {
  const poly = detection.polygon
  if (!poly || poly.length < 8) {
    // Fallback to bbox corners if polygon missing
    const { x1, y1, x2, y2 } = detection.bbox
    return `${x1},${y1} ${x2},${y1} ${x2},${y2} ${x1},${y2}`
  }
  // Pair up flat coords into "x,y" strings
  const points: string[] = []
  for (let i = 0; i < poly.length; i += 2) {
    points.push(`${poly[i]},${poly[i + 1]}`)
  }
  return points.join(' ')
}

//Actual lifecycle of the page
onMounted(async () => {
  if (previewMode.value) {
    const bundle = await loadPreview()
  }

  await loadFromApi()
})

//Preview section using mock data for easier visualization of UI before its all connected. (remove later prob)
async function loadPreview(): Promise<ReviewBundle | null> {
  if (!import.meta.env.DEV) {
    return null
  }

  const { default: mock } = await import('@/mocks/seed-reference-review.json')

  return JSON.parse(JSON.stringify(mock))
}

//API loading
async function loadFromApi() {
  const id = route.params.id

  try {
    const response = await api(`/api/seeds/runs/${id}/reference-review/`)

    if (!response.ok) {
      loadError.value = `HTTP ${response.status}`

      return
    }

    const data: ReviewBundle = await response.json()

    run.value = data.run
    images.value = data.images
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error)
  } finally {
    loading.value = false
  }
}

//Seed reference selection section
function selectReference(id: number) {
  selectedReferenceId.value = id
}

function clearReference() {
  selectedReferenceId.value = null
}

async function updateImageSize() {
  await nextTick()

  const img = imageRef.value
  if (!img) return

  imageSize.value = {
    width: img.clientWidth,
    height: img.clientHeight,
  }
}

watch(currentImageIndex, updateImageSize)
watch(images, updateImageSize)

//Styling of the selected boundingbox
function boxStyle(detection: Detection) {
  const img = imageRef.value
  if (!img || !currentImage.value) return {}

  const renderedWidth = img.clientWidth
  const renderedHeight = img.clientHeight

  const originalWidth = currentImage.value.width
  const originalHeight = currentImage.value.height

  const scaleX = renderedWidth / originalWidth
  const scaleY = renderedHeight / originalHeight

  return {
    left: `${detection.bbox.x1 * scaleX}px`,
    top: `${detection.bbox.y1 * scaleY}px`,
    width: `${(detection.bbox.x2 - detection.bbox.x1) * scaleX}px`,
    height: `${(detection.bbox.y2 - detection.bbox.y1) * scaleY}px`,
  }
}

//Function to proceed to calculations with reference seed
async function proceedToCalculation() {
  if (!selectedReferenceId.value) {
    return
  }

  const id = route.params.id

  try {
    const response = await api(`/api/seeds/runs/${id}/reference-seed/`, {
      method: 'POST',

      headers: {
        'Content-Type': 'application/json',
      },

      body: JSON.stringify({
        reference_detection_id: selectedReferenceId.value,

        image_id: currentImage.value?.id,
      }),
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
  } catch (error) {
    console.error(error)
    alert('Failed to calculate active seeds.')
    return // stop here if the API call failed
  }

  //Redirect to next review page after selecting a reference seed.
  router.push({
    name: 'seed-count-review',

    params: {
      id,
    },
  })
}
</script>
