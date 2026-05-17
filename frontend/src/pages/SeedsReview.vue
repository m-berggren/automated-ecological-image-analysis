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
  <div v-else-if="currentImage" class="flex-1 flex flex-col min-h-0 bg-background">
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
            {{ detections.length }} detected seeds
          </div>

          <div v-if="selectedReference" class="px-3 py-1 rounded-full bg-green-100 text-green-700">
            Reference seed selected
          </div>
        </div>
      </div>
    </section>

    <!-- Image review area -->
    <section class="flex-1 overflow-auto p-6">
      <div class="mx-auto max-w-7xl">
        <div class="relative overflow-hidden rounded-2xl border border-border bg-black/5 shadow-sm">
          <!-- Image -->
          <img
            :src="currentImage.image_url"
            :alt="currentImage.filename"
            class="w-full h-auto select-none"
            draggable="false"
          />

          <!-- Bounding boxes -->
          <button
            v-for="detection in detections"
            :key="detection.id"
            type="button"
            class="absolute rounded-sm border-2 transition-all duration-150"
            :class="
              selectedReferenceId === detection.id
                ? 'border-green-500 ring-4 ring-green-500/30 z-10'
                : 'border-primary hover:border-green-400 hover:bg-green-500/10'
            "
            :style="boxStyle(detection)"
            @click="selectReference(detection.id)"
          >
            <span class="sr-only"> Select seed {{ detection.id }} </span>
          </button>
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
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import PageHeader from '@/components/PageHeader.vue'
import SeedsStepper from '@/components/SeedsStepper.vue'

import { api } from '@/api'

//Types
interface Detection {
  id: number

  confidence: number

  /*
    Note to self: check that boundingboxes are normalized correctly in backend
  */

  bbox_x: number
  bbox_y: number
  bbox_width: number
  bbox_height: number
}

interface ReviewImage {
  id: number

  filename: string
  image_url: string
}

interface ReviewBundle {
  run: {
    id: number
    name: string
    status: string
  }

  image: ReviewImage

  detections: Detection[]
}

//Routing
const route = useRoute()
const router = useRouter()

//State
const loading = ref(true)
const loadError = ref('')

const run = ref<ReviewBundle['run'] | null>(null)

const currentImage = ref<ReviewImage | null>(null)

const detections = ref<Detection[]>([])

const selectedReferenceId = ref<number | null>(null)

//Computation
const previewMode = computed(() => {
  const value = route.query.preview

  return typeof value === 'string' ? value : null
})

const headerTitle = computed(() =>
  run.value ? `Seed Reference Review · ${run.value.name}` : 'Seed Reference Review',
)

const selectedReference = computed(() =>
  detections.value.find((detection) => detection.id === selectedReferenceId.value),
)

//Actual lifecycle of the page
onMounted(async () => {
  if (previewMode.value) {
    const bundle = await loadPreview()

    if (bundle) {
      run.value = bundle.run
      currentImage.value = bundle.image
      detections.value = bundle.detections

      loading.value = false

      return
    }
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
    const response = await api(`/api/analysis/runs/${id}/reference-review/`)

    if (!response.ok) {
      loadError.value = `HTTP ${response.status}`

      return
    }

    const data: ReviewBundle = await response.json()

    run.value = data.run
    currentImage.value = data.image
    detections.value = data.detections
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

//Styling of the selected boundingbox
function boxStyle(detection: Detection) {
  return {
    left: `${detection.bbox_x}%`,
    top: `${detection.bbox_y}%`,
    width: `${detection.bbox_width}%`,
    height: `${detection.bbox_height}%`,
  }
}

//Function to proceed to calculations with reference seed (Needs implementation in backend)
async function proceedToCalculation() {
  if (!selectedReferenceId.value) {
    return
  }

  const id = route.params.id

  try {
    const response = await api(`/api/analysis/runs/${id}/reference-seed/`, {
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

    //Redirect to next review page after selecting a reference seed.
    router.push({
      name: 'seed-count-review',

      params: {
        id,
      },
    })
  } catch (error) {
    console.error(error)

    alert('Failed to calculate active seeds.')
  }
}
</script>
