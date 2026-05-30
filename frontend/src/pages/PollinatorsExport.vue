<template>
  <PageHeader :title="headerTitle" subtitle="Toggle detections off to drop them from the export" />
  <PollinatorsStepper current="export" :runId="run?.id" />

  <div v-if="loading" class="flex-1 p-8 text-sm text-muted-foreground">Loading…</div>
  <div v-else-if="loadError" class="flex-1 p-8 text-sm text-red-600">{{ loadError }}</div>

  <div v-else class="flex-1 flex flex-col min-h-0">
    <!-- Running totals -->
    <header
      ref="headerEl"
      class="@container relative px-8 py-2 border-b border-border bg-surface flex items-center gap-4 text-sm"
    >
      <svg
        class="absolute inset-0 w-full h-full overflow-visible pointer-events-none text-primary/70"
        aria-hidden="true"
      >
        <path
          v-for="p in branchPaths"
          :key="p.key"
          :d="p.d"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
      </svg>
      <div
        class="inline-flex rounded-md border border-border bg-background overflow-hidden text-xs shadow-sm"
        role="group"
        aria-label="Filter images"
      >
        <button
          v-for="opt in FILTER_OPTIONS"
          :key="opt.value"
          class="px-2.5 py-1 transition-colors"
          :class="
            filterMode === opt.value
              ? 'bg-primary text-primary-foreground'
              : 'hover:bg-muted text-muted-foreground'
          "
          :title="opt.title"
          @click="setFilterMode(opt.value)"
        >
          <span
            v-if="opt.dot"
            class="inline-block w-2 h-2 rounded-full mr-1.5 align-middle"
            :style="{ backgroundColor: opt.dot }"
          />
          {{ opt.label }}
          <span class="ml-1 font-mono opacity-70">{{ filterCounts[opt.value] }}</span>
        </button>
      </div>
      <!-- Compact counts. Tiers (container width):
             * class breakdown shows from @3xl up
             * Total / Excluded show from @5xl up
           Below @3xl only filter + buttons remain. 'Other' is excluded
           from the export entirely; it's a training-only label. -->
      <div class="hidden @3xl:flex items-center gap-3 whitespace-nowrap">
        <span v-for="row in classCounts" :key="row.key" class="inline-flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full" :style="{ backgroundColor: row.color }" />
          <span class="font-mono">{{ row.count }}</span>
          <span class="text-muted-foreground">{{ row.abbr }}</span>
        </span>
        <span class="hidden @5xl:inline-flex items-center gap-1.5">
          <span class="font-mono">{{ totalIncluded }}</span>
          <span class="text-muted-foreground">Total</span>
        </span>
        <span class="hidden @5xl:inline-flex items-center gap-1.5">
          <span class="font-mono">{{ totalExcluded }}</span>
          <span class="text-muted-foreground">Excluded</span>
        </span>
      </div>
      <span
        v-if="loadProgress.total && loadProgress.loaded < loadProgress.total"
        class="hidden @5xl:inline text-muted-foreground italic"
      >
        loading {{ loadProgress.loaded }}/{{ loadProgress.total }}…
      </span>
      <div class="ml-auto flex gap-2 shrink-0 relative">
        <button
          ref="csvBtn"
          class="px-3 py-1.5 shrink-0 rounded-md text-sm font-medium border border-border bg-background shadow-sm hover:bg-muted disabled:opacity-50"
          :disabled="downloading !== null || !run"
          @click="showCsvModal = true"
        >
          CSV
        </button>
        <button
          ref="cropsBtn"
          class="px-3 py-1.5 shrink-0 rounded-md text-sm font-medium border border-border bg-background shadow-sm hover:bg-muted disabled:opacity-50"
          :disabled="downloading !== null || !run"
          @click="downloadExport('crops')"
        >
          Crops
        </button>
        <button
          ref="annotBtn"
          class="px-3 py-1.5 shrink-0 rounded-md text-sm font-medium border border-border bg-background shadow-sm hover:bg-muted disabled:opacity-50"
          :disabled="downloading !== null || !run"
          @click="downloadExport('annotated')"
        >
          Annotations
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

    <div v-else class="flex-1 flex min-h-0">
      <!-- Thumbnail rail. Border color reflects state: red = has excluded
           crops (verify before exporting), blue = has auto-accepted crops
           (high-confidence agreement between YOLO and InsectNet). Red wins
           when both apply since excluded is the more actionable signal. -->
      <ImageThumbnailRail
        :items="railItems"
        :active-key="activeCard?.filename ?? null"
        empty-message="No images match this filter."
        @update:active-key="selectByFilename"
      />

      <!-- Active image card. One source image + its crops per page. -->
      <div class="flex-1 min-w-0 min-h-0 overflow-auto p-1">
        <section
          v-if="activeCard"
          :key="activeCard.filename"
          class="h-full flex flex-col rounded-xl border border-border bg-surface overflow-hidden"
        >
          <header
            class="shrink-0 px-4 py-2 border-b border-border flex items-baseline gap-3 text-sm"
          >
            <h2 class="font-mono">{{ activeCard.filename }}</h2>
            <span class="text-xs text-muted-foreground">
              {{ activeCard.includedCount }}/{{ activeCard.detections.length }} kept
            </span>
            <span v-if="isZoomed" class="text-[11px] text-muted-foreground font-mono ml-2">
              {{ Math.round(zoom.scale * 100) }}%
            </span>
            <span class="ml-auto text-xs text-muted-foreground font-mono">
              {{ selectedIndex + 1 }} / {{ filteredCards.length }} · ↑/↓ to step
            </span>
          </header>
          <div class="flex-1 min-h-0 flex gap-3 p-3">
            <!-- Source image. Alt+wheel zooms around the cursor; right-click
                 (or alt+left-click) drags pan. Bboxes still take a plain
                 left-click to toggle exclude. -->
            <div
              class="flex-1 min-w-0 min-h-0 relative bg-background rounded-md overflow-hidden"
              :class="
                activeCard.naturalW && activeCard.sourceUrl
                  ? panning
                    ? 'cursor-grabbing'
                    : ''
                  : ''
              "
              @mousedown="onImageMouseDown"
              @wheel="onImageWheel"
              @contextmenu.prevent
            >
              <svg
                v-if="activeCard.naturalW && activeCard.sourceUrl"
                ref="svgEl"
                :viewBox="`0 0 ${activeCard.naturalW} ${activeCard.naturalH}`"
                preserveAspectRatio="xMidYMid meet"
                class="absolute inset-0 w-full h-full select-none"
              >
                <g
                  ref="transformGroupEl"
                  :transform="`translate(${zoom.tx} ${zoom.ty}) scale(${zoom.scale})`"
                >
                  <image
                    :href="activeCard.sourceUrl"
                    :width="activeCard.naturalW"
                    :height="activeCard.naturalH"
                  />
                  <rect
                    v-for="d in activeCard.detections"
                    :key="d.id"
                    :x="d.bbox.x1"
                    :y="d.bbox.y1"
                    :width="d.bbox.w"
                    :height="d.bbox.h"
                    fill="none"
                    :stroke="bboxStroke(d)"
                    stroke-width="2"
                    vector-effect="non-scaling-stroke"
                    class="cursor-pointer"
                    @click.stop="toggleExclude(d)"
                    @contextmenu.prevent
                  />
                  <ROIOverlay
                    :bbox="roiBbox"
                    :image-w="activeCard.naturalW"
                    :image-h="activeCard.naturalH"
                    :color="settings.roiColor"
                  />
                </g>
              </svg>
              <div
                v-else
                class="absolute inset-0 flex items-center justify-center text-xs text-muted-foreground"
              >
                source unavailable
              </div>
              <button
                v-if="isZoomed"
                class="absolute bottom-3 right-3 z-10 p-2 rounded-md bg-black/55 text-white hover:bg-black/75 cursor-pointer"
                title="Reset zoom"
                @mousedown.stop
                @contextmenu.prevent
                @click.stop="resetZoom"
              >
                <ZoomOut class="w-4 h-4" />
              </button>
            </div>
            <!-- Crop strip: single vertical column. Scrolls when there
                 are more detections than fit in the panel height, so the
                 source image gets the bulk of the space. -->
            <aside class="w-24 shrink-0 overflow-y-auto flex flex-col gap-2 pr-1">
              <button
                v-for="d in activeCard.detections"
                :key="d.id"
                class="relative w-full aspect-square rounded-md overflow-hidden transition-colors focus:outline-none shrink-0"
                :class="cropBorderClass(d)"
                :title="cropTooltip(d)"
                @click="toggleExclude(d)"
              >
                <img
                  v-if="d.crop_url"
                  :src="d.crop_url"
                  :alt="`Detection ${d.id}`"
                  loading="lazy"
                  class="absolute inset-0 w-full h-full object-contain bg-background"
                />
              </button>
            </aside>
          </div>
        </section>
      </div>
    </div>
    <CsvExportDialog v-model="showCsvModal" @confirm="onCsvConfirm" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ZoomOut } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import PollinatorsStepper from '@/components/PollinatorsStepper.vue'
import ROIOverlay from '@/components/ROIOverlay.vue'
import CsvExportDialog, { type CsvExportMode } from '@/components/CsvExportDialog.vue'
import { api } from '@/api'
import {
  normalizeRoiBbox,
  type BBox,
  type Detection,
  type PollinatorClass,
} from '@/types/pollinator'
import { useRunDetections } from '@/composables/useRunDetections'
import ImageThumbnailRail, { type RailItem } from '@/components/pollinator/ImageThumbnailRail.vue'
import { usePollinatorSettingsStore } from '@/stores/pollinatorSettings'

// User-level ROI outline color, shared with the review pages via the same
// store, so the Export overlay matches whatever the reviewer picked.
const settings = usePollinatorSettingsStore()

const CLASS_COLORS: Record<PollinatorClass, string> = {
  fly: '#6b9bd2',
  bumblebee: '#e6a946',
  butterfly: '#c87bba',
  other: '#9aa3ab',
}
// 'other' is a training-only label; it never ships in the export, so
// it doesn't earn a slot in the totals row.
const DISPLAY_CLASSES: { key: PollinatorClass; abbr: string }[] = [
  { key: 'fly', abbr: 'Fly' },
  { key: 'bumblebee', abbr: 'BB' },
  { key: 'butterfly', abbr: 'BF' },
]

const showCsvModal = ref(false)

function onCsvConfirm(mode: CsvExportMode) {
  downloadExport('csv', mode)
}

const route = useRoute()
const runId = route.params.id as string
const naturalSize = ref<Record<string, { w: number; h: number }>>({})
type DownloadKind = 'csv' | 'crops' | 'annotated'
const downloading = ref<DownloadKind | null>(null)

const preloadSeen = new Set<string>()
const { run, detections, loading, loadError, loadProgress, load } = useRunDetections(runId, {
  // Apply engulfment auto-exclude on every Export visit BEFORE detections
  // are fetched, so the first page already reflects the new exclusions.
  // Backend skips rows the reviewer has toggled, so this only catches
  // newly-accepted duplicates from Review.
  onRunLoaded: async () => {
    await api(`/api/analysis/runs/${runId}/recompute-exclusions/`, { method: 'POST' })
  },
  onPage: (results) => {
    for (const d of results) preloadDims(d, preloadSeen)
  },
})

const headerTitle = computed(() =>
  run.value ? `Export · ${run.value.name || `Run #${run.value.id}`}` : 'Export',
)

function classLabel(cls: PollinatorClass | null): string {
  if (!cls) return '—'
  return cls[0].toUpperCase() + cls.slice(1)
}

function effective(d: Detection): PollinatorClass | null {
  return d.reviewer_label ?? d.predicted_class ?? d.yolo_class ?? d.insectnet_class ?? null
}

const roiBbox = computed<[number, number, number, number] | null>(() =>
  normalizeRoiBbox(run.value?.config?.preprocessing?.roi_bbox),
)

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
  const counts: Record<PollinatorClass, number> = { fly: 0, bumblebee: 0, butterfly: 0, other: 0 }
  for (const d of acceptedDetections.value) {
    if (d.excluded_from_export) continue
    const cls = effective(d)
    if (cls != null) counts[cls] += 1
  }
  return DISPLAY_CLASSES.map(({ key, abbr }) => ({
    key,
    abbr,
    color: CLASS_COLORS[key],
    count: counts[key],
  }))
})

const totalIncluded = computed(
  () => acceptedDetections.value.filter((d) => !d.excluded_from_export).length,
)
const totalExcluded = computed(
  () => acceptedDetections.value.filter((d) => d.excluded_from_export).length,
)

// "Auto-accepted" means the system confirmed this detection via the
// Review-page "Suggest exports" toggle (it cleared both thresholds), not a
// human. The backend stamps auto_accepted at toggle time and clears it on
// any manual review, so the blue (auto) vs green (manual) cue stays honest
// regardless of confidence.
function isAutoAccepted(d: Detection): boolean {
  return d.auto_accepted === true
}

function hasExcluded(card: ImageCard): boolean {
  return card.detections.some((d) => d.excluded_from_export)
}

function hasAutoAccepted(card: ImageCard): boolean {
  return card.detections.some(isAutoAccepted)
}

// Precedence: excluded > auto-accepted > fully manually validated.
// Anything reaching this page is already accepted, so the fall-through
// branch means "no exclusions, no auto-pass — the reviewer signed off
// on every detection by hand" and earns the same green as the bboxes.
function thumbBorderClass(card: ImageCard): string {
  if (hasExcluded(card)) return 'border-red-500'
  if (hasAutoAccepted(card)) return 'border-blue-500'
  return 'border-green-800'
}

// Color story for both crop borders and source-image bboxes:
//   red    = excluded from export (user dropped it)
//   blue   = auto-accepted (cleared thresholds in Settings)
//   green  = manually validated (confirmed/corrected, not auto)
// Excluded wins precedence; auto + excluded keeps the blue signal as an
// inset ring on the crop tile so both states stay visible.
function cropBorderClass(d: Detection): string {
  const auto = isAutoAccepted(d)
  if (d.excluded_from_export) {
    return auto
      ? 'border-2 border-red-500 ring-2 ring-inset ring-blue-500'
      : 'border-2 border-red-500'
  }
  if (auto) return 'border-2 border-blue-500'
  return 'border-2 border-green-800'
}

function bboxStroke(d: Detection): string {
  if (d.excluded_from_export) return '#ef4444'
  if (isAutoAccepted(d)) return '#3b82f6'
  return '#166534'
}

function fmtConf(v: number | null): string {
  return v == null ? '—' : v.toFixed(2)
}

function cropTooltip(d: Detection): string {
  return `${classLabel(effective(d))} · Y: ${fmtConf(d.yolo_confidence)} · I: ${fmtConf(d.insectnet_confidence)}`
}

type FilterMode = 'all' | 'excluded' | 'auto'
const FILTER_OPTIONS: { value: FilterMode; label: string; title: string; dot?: string }[] = [
  { value: 'all', label: 'All', title: 'Show every image' },
  {
    value: 'excluded',
    label: 'Excluded',
    title: 'Only images with at least one crop dropped from the export',
    dot: '#ef4444',
  },
  {
    value: 'auto',
    label: 'Auto-accepted',
    title:
      'Only images with detections that cleared both YOLO and group-classifier thresholds. Configure in Settings; disabled when auto-select is off.',
    dot: '#3b82f6',
  },
]

const filterMode = ref<FilterMode>('all')

const filteredCards = computed<ImageCard[]>(() => {
  if (filterMode.value === 'excluded') return imageCards.value.filter(hasExcluded)
  if (filterMode.value === 'auto') return imageCards.value.filter(hasAutoAccepted)
  return imageCards.value
})

const filterCounts = computed<Record<FilterMode, number>>(() => ({
  all: imageCards.value.length,
  excluded: imageCards.value.filter(hasExcluded).length,
  auto: imageCards.value.filter(hasAutoAccepted).length,
}))

const selectedIndex = ref(0)

const activeCard = computed<ImageCard | null>(
  () => filteredCards.value[selectedIndex.value] ?? null,
)

const railItems = computed<RailItem[]>(() =>
  filteredCards.value.map((card) => ({
    key: card.filename,
    label: card.filename,
    src: card.sourceUrl,
    aspectRatio: card.aspectRatio ?? undefined,
    caption: `${card.includedCount}/${card.detections.length} kept`,
    title: `${card.filename} · ${card.includedCount}/${card.detections.length} kept`,
    accentClass: thumbBorderClass(card),
  })),
)

function selectIndex(idx: number) {
  if (!filteredCards.value.length) return
  selectedIndex.value = Math.max(0, Math.min(filteredCards.value.length - 1, idx))
}

function selectByFilename(filename: string) {
  const idx = filteredCards.value.findIndex((c) => c.filename === filename)
  if (idx >= 0) selectedIndex.value = idx
}

function setFilterMode(mode: FilterMode) {
  if (filterMode.value === mode) return
  // Keep the currently-visible image selected if it survives the new
  // filter; otherwise fall back to the first match.
  const current = activeCard.value
  filterMode.value = mode
  const next = current ? filteredCards.value.findIndex((c) => c.filename === current.filename) : -1
  selectedIndex.value = next >= 0 ? next : 0
}

// Clamp if the visible list shrinks (re-fetch, or excluded-toggling
// removes the active card from the current filter).
watch(
  () => filteredCards.value.length,
  (n) => {
    if (selectedIndex.value >= n) selectedIndex.value = Math.max(0, n - 1)
  },
)

function onKeydown(e: KeyboardEvent) {
  if (!filteredCards.value.length) return
  const t = e.target as HTMLElement | null
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    selectIndex(selectedIndex.value + 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    selectIndex(selectedIndex.value - 1)
  }
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

// Fan-out lines that visually connect the stepper's Export step to
// each download button. Computed from live DOM rects so they survive
// flex-wrap, viewport resizes, and label width changes.
const headerEl = ref<HTMLElement | null>(null)
const csvBtn = ref<HTMLButtonElement | null>(null)
const cropsBtn = ref<HTMLButtonElement | null>(null)
const annotBtn = ref<HTMLButtonElement | null>(null)
const branchPaths = ref<{ key: string; d: string }[]>([])

function treePath(srcX: number, srcY: number, tx: number, ty: number, trunkY: number): string {
  // Straight line when the target sits directly under the source.
  if (Math.abs(tx - srcX) < 1) {
    return `M ${srcX.toFixed(1)} ${srcY.toFixed(1)} L ${tx.toFixed(1)} ${ty.toFixed(1)}`
  }
  // Clamp the corner radius so it can't outgrow any of the three
  // segments it has to round (incoming vertical, trunk horizontal,
  // outgoing vertical). Otherwise the quadratics overlap on tight rows.
  const desired = 10
  const r = Math.max(
    1,
    Math.min(desired, Math.abs(trunkY - srcY), Math.abs(ty - trunkY), Math.abs(tx - srcX) / 2),
  )
  const sign = tx > srcX ? 1 : -1
  const inX = (srcX + r * sign).toFixed(1)
  const outX = (tx - r * sign).toFixed(1)
  const sx = srcX.toFixed(1)
  const sy = srcY.toFixed(1)
  const txS = tx.toFixed(1)
  const tyS = ty.toFixed(1)
  const tY = trunkY.toFixed(1)
  const preY = (trunkY - r).toFixed(1)
  const postY = (trunkY + r).toFixed(1)
  return [
    `M ${sx} ${sy}`,
    `L ${sx} ${preY}`,
    `Q ${sx} ${tY} ${inX} ${tY}`,
    `L ${outX} ${tY}`,
    `Q ${txS} ${tY} ${txS} ${postY}`,
    `L ${txS} ${tyS}`,
  ].join(' ')
}

function recomputeBranchPaths() {
  const header = headerEl.value
  if (!header) {
    branchPaths.value = []
    return
  }
  // The data-step attribute is on the link/div that wraps both the
  // circle and the label, so the first span (the circle) is the actual
  // anchor for the line.
  const circleEl = document.querySelector<HTMLElement>('[data-step="export"] > span')
  if (!circleEl) {
    branchPaths.value = []
    return
  }
  const headerRect = header.getBoundingClientRect()
  const cr = circleEl.getBoundingClientRect()
  const srcX = cr.left + cr.width / 2 - headerRect.left
  // Bottom of the circle, in header-local coords. Negative because the
  // stepper sits above the header; the SVG has overflow-visible so the
  // path renders up into the stepper area.
  const srcY = cr.bottom - headerRect.top
  const targets: [HTMLButtonElement | null, string][] = [
    [csvBtn.value, 'csv'],
    [cropsBtn.value, 'crops'],
    [annotBtn.value, 'annot'],
  ]
  // Compute the trunk Y once so all three branches share a clean
  // horizontal line, like a real tree.
  const topMostTargetTop = Math.min(
    ...targets
      .map(([b]) => b)
      .filter((b): b is HTMLButtonElement => b != null)
      .map((b) => b.getBoundingClientRect().top - headerRect.top),
  )
  const trunkY = srcY + (topMostTargetTop - srcY) * 0.6
  const next: { key: string; d: string }[] = []
  for (const [btn, key] of targets) {
    if (!btn) continue
    const r = btn.getBoundingClientRect()
    const tx = r.left + r.width / 2 - headerRect.left
    const ty = r.top - headerRect.top
    next.push({ key, d: treePath(srcX, srcY, tx, ty, trunkY) })
  }
  branchPaths.value = next
}

let branchRO: ResizeObserver | null = null

// Retrigger when reactive state shifts button widths or wrapping, since
// the ResizeObserver above only fires when the header itself resizes.
watch(
  () => [downloading.value, filterMode.value, totalIncluded.value, totalExcluded.value],
  () => requestAnimationFrame(recomputeBranchPaths),
)

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('resize', recomputeBranchPaths)
  // ResizeObserver catches wrap/unwrap from the totals row growing, font
  // load shifts, and the buttons swapping labels to "Downloading…".
  if (headerEl.value) {
    branchRO = new ResizeObserver(recomputeBranchPaths)
    branchRO.observe(headerEl.value)
  }
  requestAnimationFrame(recomputeBranchPaths)
  load()
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('resize', recomputeBranchPaths)
  // Pan listeners are normally torn down by onPanEnd, but if a pan was
  // in flight when the user navigated away these would leak.
  window.removeEventListener('mousemove', onPanMove)
  window.removeEventListener('mouseup', onPanEnd)
  branchRO?.disconnect()
  branchRO = null
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

async function downloadExport(kind: DownloadKind, mode?: 'per_image' | 'per_detection') {
  if (!run.value || downloading.value !== null) return
  downloading.value = kind
  try {
    const path = {
      csv: `/api/pollinator/runs/${run.value.id}/export.csv?mode=${mode ?? 'per_detection'}`,
      crops: `/api/pollinator/runs/${run.value.id}/export-crops.zip`,
      annotated: `/api/pollinator/runs/${run.value.id}/export-annotated.zip`,
    }[kind]
    const res = await api(path)
    if (!res.ok) {
      loadError.value = `Export (${kind}): HTTP ${res.status}`
      return
    }
    const blob = await res.blob()
    // Name downloads after the run, not its id. CSV suffix tracks the mode:
    // per_image → _images, per_detection → _detections.
    const base = (run.value.name || `run-${run.value.id}`)
      .replace(/[^\w.-]+/g, '_')
      .replace(/^_+|_+$/g, '')
    const csvSuffix = mode === 'per_image' ? 'images' : 'detections'
    const filename = {
      csv: `${base}_${csvSuffix}.csv`,
      crops: `${base}_crops.zip`,
      annotated: `${base}_annotated.zip`,
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

// Inline pan + zoom. Mirrors PollinatorsReview / ReviewImageFirst:
// a single transform on the SVG <g> carries both translate and scale in
// viewBox units. Wheel + alt zooms around the cursor; right-click (or
// alt+left-click) drags pan. Plain left-click on a bbox still toggles
// the exclusion (the rect handler stops click propagation), so the two
// gestures don't collide.
const MIN_ZOOM = 1
const MAX_ZOOM = 8
const svgEl = ref<SVGSVGElement | null>(null)
const transformGroupEl = ref<SVGGElement | null>(null)
const zoom = ref({ scale: 1, tx: 0, ty: 0 })
const isZoomed = computed(() => zoom.value.scale > 1.0001)
const panning = ref(false)

function resetZoom() {
  zoom.value = { scale: 1, tx: 0, ty: 0 }
}

// Snap back to 1x when the user switches images so each one starts
// fully visible.
watch(
  () => activeCard.value?.filename,
  () => {
    if (zoom.value.scale !== 1) resetZoom()
  },
)

function eventToViewBox(e: MouseEvent): { x: number; y: number } | null {
  const svg = svgEl.value
  if (!svg) return null
  const pt = svg.createSVGPoint()
  pt.x = e.clientX
  pt.y = e.clientY
  const ctm = svg.getScreenCTM()
  if (!ctm) return null
  const local = pt.matrixTransform(ctm.inverse())
  return { x: local.x, y: local.y }
}

function onImageWheel(e: WheelEvent) {
  if (!e.altKey) return
  if (!activeCard.value?.naturalW) return
  e.preventDefault()
  const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15
  const oldScale = zoom.value.scale
  const newScale = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, oldScale * factor))
  if (newScale === oldScale) return
  const vb = eventToViewBox(e)
  if (!vb) {
    zoom.value = { ...zoom.value, scale: newScale }
    return
  }
  // Keep the image point under the cursor stationary on screen.
  const newTx = vb.x - ((vb.x - zoom.value.tx) * newScale) / oldScale
  const newTy = vb.y - ((vb.y - zoom.value.ty) * newScale) / oldScale
  zoom.value = { scale: newScale, tx: newTx, ty: newTy }
  if (newScale <= MIN_ZOOM + 0.0001) resetZoom()
}

let panStart: { vbX: number; vbY: number; tx: number; ty: number } | null = null

function startPan(e: MouseEvent) {
  const vb = eventToViewBox(e)
  if (!vb) return
  e.preventDefault()
  panning.value = true
  panStart = { vbX: vb.x, vbY: vb.y, tx: zoom.value.tx, ty: zoom.value.ty }
  window.addEventListener('mousemove', onPanMove)
  window.addEventListener('mouseup', onPanEnd)
}

function onPanMove(e: MouseEvent) {
  if (!panStart) return
  const vb = eventToViewBox(e)
  if (!vb) return
  zoom.value = {
    ...zoom.value,
    tx: panStart.tx + (vb.x - panStart.vbX),
    ty: panStart.ty + (vb.y - panStart.vbY),
  }
}

function onPanEnd() {
  panning.value = false
  panStart = null
  window.removeEventListener('mousemove', onPanMove)
  window.removeEventListener('mouseup', onPanEnd)
}

function onImageMouseDown(e: MouseEvent) {
  if (!activeCard.value?.naturalW) return
  const isPan = e.button === 2 || (e.button === 0 && e.altKey)
  if (isPan) startPan(e)
  // Plain left-click does nothing here; bboxes own their own click.
}
</script>
