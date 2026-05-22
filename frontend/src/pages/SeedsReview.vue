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
                :stroke-width="selectedReferenceId === detection.id ? 12 : 2"
                style="pointer-events: all; cursor: pointer"
                :class="selectedReferenceId === detection.id ? 'ring-highlight' : ''"
                @click="selectReference(detection.id)"
              />
            </svg>

            <img
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
            :disabled="!allImagesHaveReference"
            @click="proceed"
          >
            {{ isCalculating ? 'Calculating...' : 'Continue' }}
          </button>
        </div>
      </div>
    </footer>
    <Transition name="toast">
      <div
        v-if="toast"
        class="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-5 py-3 rounded-xl shadow-lg text-sm font-medium text-white"
        :style="
          toast.type === 'success'
            ? 'background-color: hsl(128, 45%, 24%)'
            : 'background-color: hsl(0, 72%, 51%)'
        "
      >
        {{ toast.message }}
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
// Replace your script setup with this

import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import SeedsStepper from '@/components/SeedsStepper.vue'
import { api } from '@/api'

interface Detection {
  id: number
  confidence: number
  class: string
  polygon?: number[]
  bbox?: { x1: number; y1: number; x2: number; y2: number }
  poly?: number[]
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
  run: { id: number; name: string; status: string }
  images: ReviewImage[]
  reference_seeds: Record<string, number> // image_id -> detection_id
}

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const loadError = ref('')
const run = ref<ReviewBundle['run'] | null>(null)
const images = ref<ReviewImage[]>([])
const currentImageIndex = ref(0)
const isCalculating = ref(false)

// Per-image reference map: imageId (string) -> detectionId
const referenceMap = ref<Record<string, number>>({})

// Toast state
const toast = ref<{ message: string; type: 'success' | 'error' } | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | null = null

const currentImage = computed(() => images.value[currentImageIndex.value] ?? null)
const currentDetections = computed(() => currentImage.value?.detections ?? [])

const currentImageId = computed(() => currentImage.value?.id?.toString() ?? null)

// The selected detection id for the currently visible image
const selectedReferenceId = computed(() =>
  currentImageId.value ? (referenceMap.value[currentImageId.value] ?? null) : null,
)

const selectedReference = computed(
  () => currentDetections.value.find((d) => d.id === selectedReferenceId.value) ?? null,
)

const allImagesHaveReference = computed(() =>
  images.value.every((img) => referenceMap.value[img.id.toString()] != null),
)

const headerTitle = computed(() =>
  run.value ? `Seed Reference Review · ${run.value.name}` : 'Seed Reference Review',
)

function showToast(message: string, type: 'success' | 'error' = 'success') {
  if (toastTimer) clearTimeout(toastTimer)
  toast.value = { message, type }
  toastTimer = setTimeout(() => {
    toast.value = null
  }, 3000)
}

function polyPoints(detection: Detection): string {
  const poly = detection.polygon
  if (!poly || poly.length < 8) {
    const { x1, y1, x2, y2 } = detection.bbox
    return `${x1},${y1} ${x2},${y1} ${x2},${y2} ${x1},${y2}`
  }
  const points: string[] = []
  for (let i = 0; i < poly.length; i += 2) {
    points.push(`${poly[i]},${poly[i + 1]}`)
  }
  return points.join(' ')
}

async function selectReference(detectionId: number) {
  if (!currentImageId.value) return

  // Optimistically update UI immediately
  referenceMap.value = { ...referenceMap.value, [currentImageId.value]: detectionId }

  const id = route.params.id
  try {
    const response = await api(`/api/seeds/runs/${id}/reference-seed/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        reference_detection_id: detectionId,
        image_id: currentImage.value?.id,
      }),
    })

    if (!response.ok) throw new Error(`HTTP ${response.status}`)

    showToast('Reference seed saved for this image.')
  } catch (error) {
    // Revert on failure
    const reverted = { ...referenceMap.value }
    delete reverted[currentImageId.value]
    referenceMap.value = reverted
    showToast('Failed to save reference seed.', 'error')
    console.error(error)
  }
}

function clearReference() {
  if (!currentImageId.value) return
  const updated = { ...referenceMap.value }
  delete updated[currentImageId.value]
  referenceMap.value = updated
}

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
    // Restore any previously saved selections
    referenceMap.value = data.reference_seeds ?? {}
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error)
  } finally {
    loading.value = false
  }
}

async function proceed() {
  const id = route.params.id
  isCalculating.value = true

  try {
    const response = await api(`/api/seeds/runs/${id}/calculate/`, {
      method: 'POST',
    })

    if (!response.ok) throw new Error(`HTTP ${response.status}`)

    router.push({ name: 'seed-count-review', params: { id } })
  } catch (error) {
    showToast('Failed to calculate seed statuses.', 'error')
    console.error(error)
  } finally {
    isCalculating.value = false
  }
}

onMounted(loadFromApi)
</script>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition:
    opacity 0.3s,
    transform 0.3s;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(8px);
}
</style>
