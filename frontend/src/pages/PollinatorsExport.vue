<template>
  <PageHeader :title="headerTitle" subtitle="Toggle detections off to drop them from the export" />
  <PollinatorsStepper current="export" :runId="run?.id" />

  <div v-if="loading" class="flex-1 p-8 text-sm text-muted-foreground">Loading…</div>
  <div v-else-if="loadError" class="flex-1 p-8 text-sm text-red-600">{{ loadError }}</div>

  <div v-else class="flex-1 flex flex-col min-h-0">
    <!-- Running totals -->
    <header
      class="px-8 py-3 border-b border-border bg-surface flex items-center gap-4 flex-wrap text-sm"
    >
      <span class="text-muted-foreground">Will export:</span>
      <span v-for="row in classCounts" :key="row.label" class="inline-flex items-center gap-1.5">
        <span class="w-2 h-2 rounded-full" :style="{ backgroundColor: row.color }" />
        <span class="font-mono">{{ row.count }}</span>
        <span class="text-muted-foreground">{{ row.label.toLowerCase() }}</span>
      </span>
      <span class="text-muted-foreground">·</span>
      <span class="font-mono">{{ totalIncluded }}</span>
      <span class="text-muted-foreground">total ({{ totalExcluded }} excluded)</span>
      <span
        v-if="loadProgress.total && loadProgress.loaded < loadProgress.total"
        class="text-muted-foreground italic"
      >
        loading {{ loadProgress.loaded }}/{{ loadProgress.total }}…
      </span>
      <div class="ml-auto flex items-center gap-2">
        <button
          class="px-3 py-1.5 rounded-md text-sm font-medium border border-border hover:bg-muted disabled:opacity-50"
          :disabled="downloading !== null || !run"
          @click="downloadExport('csv')"
        >
          {{ downloading === 'csv' ? 'Downloading…' : 'CSV' }}
        </button>
        <button
          class="px-3 py-1.5 rounded-md text-sm font-medium border border-border hover:bg-muted disabled:opacity-50"
          :disabled="downloading !== null || !run"
          @click="downloadExport('crops')"
        >
          {{ downloading === 'crops' ? 'Downloading…' : 'Crops (zip)' }}
        </button>
        <button
          class="px-3 py-1.5 rounded-md text-sm font-medium border border-border hover:bg-muted disabled:opacity-50"
          :disabled="downloading !== null || !run"
          @click="downloadExport('annotated')"
        >
          {{ downloading === 'annotated' ? 'Downloading…' : 'Annotated images (zip)' }}
        </button>
      </div>
    </header>

    <div v-if="!imageCards.length" class="flex-1 p-12 text-center text-sm text-muted-foreground">
      No accepted detections in this run yet. Confirm or correct some in
      <RouterLink :to="`/pollinators/runs/${runId}/review`" class="text-primary hover:underline"
        >Review</RouterLink
      >
      first.
    </div>

    <div v-else class="flex-1 overflow-auto p-6 space-y-6">
      <section
        v-for="card in imageCards"
        :key="card.filename"
        class="rounded-xl border border-border bg-surface overflow-hidden"
      >
        <header class="px-5 py-3 border-b border-border flex items-baseline gap-3">
          <h2 class="font-mono text-sm">{{ card.filename }}</h2>
          <span class="text-xs text-muted-foreground">
            {{ card.includedCount }}/{{ card.detections.length }} kept
          </span>
        </header>
        <div class="grid grid-cols-1 xl:grid-cols-[2fr_1fr] gap-4 p-4">
          <!-- Source image with all bboxes overlaid -->
          <div
            class="relative bg-background rounded-md overflow-hidden"
            :style="{ aspectRatio: card.aspectRatio || 'auto' }"
          >
            <svg
              v-if="card.naturalW && card.sourceUrl"
              :viewBox="`0 0 ${card.naturalW} ${card.naturalH}`"
              preserveAspectRatio="xMidYMid meet"
              class="absolute inset-0 w-full h-full"
            >
              <image :href="card.sourceUrl" :width="card.naturalW" :height="card.naturalH" />
              <rect
                v-for="d in card.detections"
                :key="d.id"
                :x="d.bbox.x1"
                :y="d.bbox.y1"
                :width="d.bbox.w"
                :height="d.bbox.h"
                :fill="d.excluded_from_export ? '#ef4444' : 'transparent'"
                :fill-opacity="d.excluded_from_export ? 0.35 : 0"
                :stroke="d.excluded_from_export ? '#ef4444' : strokeFor(d)"
                :stroke-width="Math.max(2, Math.max(card.naturalW, card.naturalH) * 0.002)"
                class="cursor-pointer"
                @click="toggleExclude(d)"
              />
            </svg>
            <div
              v-else
              class="absolute inset-0 flex items-center justify-center text-xs text-muted-foreground"
            >
              source unavailable
            </div>
          </div>
          <!-- Crop strip -->
          <div class="grid grid-cols-4 gap-2 content-start">
            <button
              v-for="d in card.detections"
              :key="d.id"
              class="relative aspect-square rounded-md overflow-hidden border-2 transition-colors focus:outline-none"
              :class="
                d.excluded_from_export ? 'border-red-500' : 'border-transparent hover:border-border'
              "
              :title="`${classLabel(effective(d))} · ${(d.confidence ?? 0).toFixed(2)}`"
              @click="toggleExclude(d)"
            >
              <img
                v-if="d.crop_url"
                :src="d.crop_url"
                :alt="`Detection ${d.id}`"
                loading="lazy"
                class="absolute inset-0 w-full h-full object-contain bg-background"
              />
              <div
                v-if="d.excluded_from_export"
                class="absolute inset-0 bg-red-500/40 flex items-center justify-center text-white text-2xl font-bold"
              >
                ✗
              </div>
              <div
                class="absolute bottom-0 left-0 right-0 h-1.5"
                :style="{ backgroundColor: strokeFor(d) }"
              />
            </button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import PollinatorsStepper from '@/components/PollinatorsStepper.vue'
import { api } from '@/api'

type ClassName = 'fly' | 'bumblebee' | 'butterfly' | 'other'

interface BBox {
  x1: number
  y1: number
  x2: number
  y2: number
  w: number
  h: number
}

interface Detection {
  id: number
  yolo_class: ClassName | null
  insectnet_class: ClassName | null
  reviewer_label: ClassName | null
  predicted_class: ClassName | null
  reviewer_status: 'unreviewed' | 'confirmed' | 'corrected' | 'rejected' | 'unsure'
  excluded_from_export: boolean
  confidence: number | null
  bbox: BBox | null
  source_image_filename: string
  source_image_url: string | null
  crop_url: string | null
}

interface RunRow {
  id: number
  name: string
  status: string
}

const CLASSES: ClassName[] = ['fly', 'bumblebee', 'butterfly', 'other']
const CLASS_COLORS: Record<ClassName, string> = {
  fly: '#6b9bd2',
  bumblebee: '#e6a946',
  butterfly: '#c87bba',
  other: '#9aa3ab',
}

const route = useRoute()
const runId = route.params.id as string
const loading = ref(true)
const loadError = ref('')
const run = ref<RunRow | null>(null)
const detections = ref<Detection[]>([])
const naturalSize = ref<Record<string, { w: number; h: number }>>({})
type DownloadKind = 'csv' | 'crops' | 'annotated'
const downloading = ref<DownloadKind | null>(null)
const loadProgress = ref({ loaded: 0, total: 0 })

const headerTitle = computed(() =>
  run.value ? `Export · ${run.value.name || `Run #${run.value.id}`}` : 'Export',
)

function classLabel(cls: ClassName | null): string {
  if (!cls) return '—'
  return cls[0].toUpperCase() + cls.slice(1)
}

function effective(d: Detection): ClassName | null {
  return d.reviewer_label ?? d.predicted_class ?? d.yolo_class ?? d.insectnet_class ?? null
}

function strokeFor(d: Detection): string {
  return CLASS_COLORS[effective(d) ?? 'other']
}

// Only accepted detections matter for export. Rejected/unsure/unreviewed
// don't count in the CSV anyway, so don't clutter the Export view with
// them. Group by source filename; sort by captured order via filename.
const acceptedDetections = computed(() =>
  detections.value.filter(
    (d) =>
      (d.reviewer_status === 'confirmed' || d.reviewer_status === 'corrected') &&
      d.bbox != null &&
      d.source_image_filename,
  ),
)

interface ImageCard {
  filename: string
  sourceUrl: string | null
  detections: (Detection & { bbox: BBox })[]
  naturalW: number
  naturalH: number
  aspectRatio: string | null
  includedCount: number
}

const imageCards = computed<ImageCard[]>(() => {
  const byImage = new Map<string, ImageCard>()
  for (const d of acceptedDetections.value) {
    if (!d.bbox) continue
    const existing = byImage.get(d.source_image_filename)
    if (existing) {
      existing.detections.push(d as Detection & { bbox: BBox })
    } else {
      const dims = naturalSize.value[d.source_image_filename]
      byImage.set(d.source_image_filename, {
        filename: d.source_image_filename,
        sourceUrl: d.source_image_url,
        detections: [d as Detection & { bbox: BBox }],
        naturalW: dims?.w ?? 0,
        naturalH: dims?.h ?? 0,
        aspectRatio: dims ? `${dims.w} / ${dims.h}` : null,
      } as ImageCard)
    }
  }
  for (const card of byImage.values()) {
    card.detections.sort((a, b) => a.id - b.id)
    card.includedCount = card.detections.filter((d) => !d.excluded_from_export).length
  }
  return [...byImage.values()].sort((a, b) => a.filename.localeCompare(b.filename))
})

const classCounts = computed(() => {
  const counts: Record<ClassName, number> = { fly: 0, bumblebee: 0, butterfly: 0, other: 0 }
  for (const d of acceptedDetections.value) {
    if (d.excluded_from_export) continue
    const cls = effective(d)
    if (cls != null) counts[cls] += 1
  }
  return CLASSES.map((cls) => ({
    label: classLabel(cls),
    color: CLASS_COLORS[cls],
    count: counts[cls],
  }))
})

const totalIncluded = computed(
  () => acceptedDetections.value.filter((d) => !d.excluded_from_export).length,
)
const totalExcluded = computed(
  () => acceptedDetections.value.filter((d) => d.excluded_from_export).length,
)

interface PageResponse {
  count: number
  next: string | null
  results: Detection[]
}

function preloadDims(d: Detection, seen: Set<string>) {
  if (!d.source_image_url || seen.has(d.source_image_filename)) return
  seen.add(d.source_image_filename)
  const fname = d.source_image_filename
  const url = d.source_image_url
  const img = new Image()
  img.onload = () => {
    naturalSize.value = {
      ...naturalSize.value,
      [fname]: { w: img.naturalWidth, h: img.naturalHeight },
    }
  }
  img.src = url
}

async function fetchAllPages() {
  // First page resolves loading=false so the user gets immediate feedback.
  // Subsequent pages stream in via reactive push to detections.value, and
  // image cards re-render incrementally.
  const seen = new Set<string>()
  let next: string | null = `/api/pollinator/runs/${runId}/detections/`
  let firstPage = true
  while (next) {
    // Strip absolute prefix when DRF returns the full URL — api() expects
    // a relative path.
    const url: string = next.startsWith('http') ? next.replace(/^https?:\/\/[^/]+/, '') : next
    const res = await api(url)
    if (!res.ok) {
      loadError.value = `Detections: HTTP ${res.status}`
      return
    }
    const page = (await res.json()) as PageResponse
    for (const d of page.results) preloadDims(d, seen)
    detections.value = detections.value.concat(page.results)
    loadProgress.value = { loaded: detections.value.length, total: page.count }
    next = page.next
    if (firstPage) {
      loading.value = false
      firstPage = false
    }
  }
}

onMounted(async () => {
  try {
    const runRes = await api(`/api/analysis/runs/${runId}/`)
    if (!runRes.ok) {
      loadError.value = `Run: HTTP ${runRes.status}`
      loading.value = false
      return
    }
    run.value = await runRes.json()
    await fetchAllPages()
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
    loading.value = false
  }
})

async function toggleExclude(d: Detection) {
  const next = !d.excluded_from_export
  d.excluded_from_export = next
  const res = await api(`/api/analysis/detections/${d.id}/exclude/`, {
    method: 'POST',
    body: JSON.stringify({ excluded: next }),
  })
  if (!res.ok) {
    // Roll back optimistic flip on failure.
    d.excluded_from_export = !next
    loadError.value = `Toggle failed: HTTP ${res.status}`
  }
}

async function downloadExport(kind: DownloadKind) {
  if (!run.value || downloading.value !== null) return
  downloading.value = kind
  try {
    const path = {
      csv: `/api/pollinator/runs/${run.value.id}/export.csv`,
      crops: `/api/pollinator/runs/${run.value.id}/export-crops.zip`,
      annotated: `/api/pollinator/runs/${run.value.id}/export-annotated.zip`,
    }[kind]
    const res = await api(path)
    if (!res.ok) {
      loadError.value = `Export (${kind}): HTTP ${res.status}`
      return
    }
    const blob = await res.blob()
    const filename = {
      csv: `run-${run.value.id}-images.csv`,
      crops: `run-${run.value.id}-crops.zip`,
      annotated: `run-${run.value.id}-annotated.zip`,
    }[kind]
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    downloading.value = null
  }
}
</script>
