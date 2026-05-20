<template>
  <div v-if="!images.length" class="flex-1 p-12 text-center text-sm text-muted-foreground">
    No detections match the current filters.
  </div>

  <div v-else class="flex-1 flex min-h-0">
    <ImageThumbnailRail
      :items="railItems"
      :active-key="activeFilename"
      deletable
      @update:active-key="selectByFilename"
      @delete="(fn) => emit('delete-image', fn)"
    />

    <!-- Collapse handle when the crops column is hidden. -->
    <button
      v-if="cropsCollapsed"
      class="order-last w-6 shrink-0 border-l border-border bg-surface flex items-center justify-center hover:bg-muted text-muted-foreground"
      title="Expand crops"
      @click="cropsCollapsed = false"
    >
      <ChevronsLeft class="w-4 h-4" />
    </button>

    <!-- Center: active source image fills the available area. The card is
         flex-column; the SVG cell takes flex-1 and the SVG letterboxes via
         preserveAspectRatio, so the image fits on any screen size without
         needing the outer container to scroll. -->
    <div class="flex-1 flex flex-col min-w-0 min-h-0">
      <div class="flex-1 min-h-0 p-1 flex">
        <div
          v-if="activeImage"
          class="flex-1 flex flex-col rounded-xl border border-border bg-surface overflow-hidden shadow-sm min-h-0"
        >
          <header class="shrink-0 px-4 py-2 border-b border-border flex items-center gap-3 text-sm">
            <h2 class="font-mono">{{ activeImage.filename }}</h2>
            <span class="text-xs text-muted-foreground">
              {{ activeImage.detections.length }} crop{{
                activeImage.detections.length === 1 ? '' : 's'
              }}
            </span>
            <span v-if="isZoomed" class="text-[11px] text-muted-foreground font-mono">
              {{ Math.round(zoom.scale * 100) }}%
            </span>
            <!-- Per-image training-exclude toggle. Set when the image has
                 more real insects than boxes, so YOLO shouldn't train on it. -->
            <div class="ml-auto inline-flex items-center gap-1 shrink-0">
              <label
                class="inline-flex items-center gap-1.5 text-xs cursor-pointer"
                :class="
                  activeImageExcludeTraining ? 'text-red-600 font-medium' : 'text-muted-foreground'
                "
              >
                <input
                  type="checkbox"
                  class="w-3.5 h-3.5 accent-red-600"
                  :checked="activeImageExcludeTraining"
                  @change="emit('toggle-training-exclude', activeImage.filename)"
                />
                <span>Exclude from YOLO training</span>
              </label>
              <InfoPopover>
                Mark this image as unfit for YOLO detector training. Use it when the photo has more
                real insects than annotated boxes (e.g. 5 flies, 1 box) — training on it would teach
                the detector that the un-boxed insects are background. The training-set builder
                skips flagged images. Does not affect review or export.
              </InfoPopover>
            </div>
          </header>
          <div
            class="flex-1 min-h-0 relative bg-background"
            :class="activeImage.naturalW ? (panning ? 'cursor-grabbing' : 'cursor-crosshair') : ''"
            @mousedown="onImageMouseDown"
            @wheel="onImageWheel"
            @contextmenu.prevent
          >
            <svg
              v-if="activeImage.naturalW && activeImage.sourceUrl"
              ref="svgEl"
              :viewBox="`0 0 ${activeImage.naturalW} ${activeImage.naturalH}`"
              preserveAspectRatio="xMidYMid meet"
              class="absolute inset-0 w-full h-full select-none"
            >
              <!-- All zoomable content lives inside the transform group so
                   pan/zoom and drag-select rectangles share one coord space. -->
              <g
                ref="transformGroupEl"
                :transform="`translate(${zoom.tx} ${zoom.ty}) scale(${zoom.scale})`"
              >
                <image
                  :href="activeImage.sourceUrl"
                  :width="activeImage.naturalW"
                  :height="activeImage.naturalH"
                />
                <rect
                  v-for="d in activeImage.detections"
                  :key="d.id"
                  v-show="d.bbox"
                  :x="d.bbox?.x1"
                  :y="d.bbox?.y1"
                  :width="d.bbox?.w"
                  :height="d.bbox?.h"
                  :fill="isHighlighted(d.id) ? '#ef4444' : 'transparent'"
                  :fill-opacity="isHighlighted(d.id) ? 0.18 : 0"
                  :stroke="isHighlighted(d.id) ? '#ef4444' : '#52525b'"
                  :stroke-width="d.id === selectedId ? 3 : 2"
                  vector-effect="non-scaling-stroke"
                  class="cursor-pointer"
                  @mousedown.stop="onBboxMouseDown(d.id, $event)"
                  @click="!$event.altKey && emit('update:selectedId', d.id)"
                  @contextmenu.prevent
                />
                <rect
                  v-if="dragRect"
                  :x="dragRect.x1"
                  :y="dragRect.y1"
                  :width="dragRect.x2 - dragRect.x1"
                  :height="dragRect.y2 - dragRect.y1"
                  fill="#3b82f6"
                  fill-opacity="0.15"
                  stroke="#3b82f6"
                  stroke-width="2"
                  stroke-dasharray="8 4"
                  vector-effect="non-scaling-stroke"
                  class="pointer-events-none"
                />
              </g>
            </svg>
            <div
              v-else-if="!activeImage.sourceUrl"
              class="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground"
            >
              source image unavailable
            </div>
            <div
              v-else
              class="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground"
            >
              loading image…
            </div>
            <!-- Reset-zoom button. Only visible when zoomed in; clicking
                 returns the view to 1×. -->
            <Tooltip text="Reset zoom · alt+scroll to zoom · right-drag (or alt+left-drag) to pan">
              <button
                v-if="isZoomed"
                class="absolute bottom-3 right-3 z-10 p-2 rounded-md bg-black/55 text-white hover:bg-black/75 cursor-pointer"
                @mousedown.stop
                @contextmenu.prevent
                @click.stop="resetZoom"
              >
                <ZoomOut class="w-4 h-4" />
              </button>
            </Tooltip>
          </div>
        </div>
      </div>

      <!-- Bottom panel. Compact: just the label radios + action footer.
           Predictions and per-crop details live in the right crops column. -->
      <div class="shrink-0 border-t border-border bg-surface flex flex-col">
        <slot name="below" :active-image="activeImage" />
      </div>
    </div>

    <!-- Right: crops column. Collapsible. Each row: clicking the thumbnail
         opens the crop popup; clicking the row body selects the crop. -->
    <aside
      v-if="!cropsCollapsed"
      class="w-52 shrink-0 border-l border-border bg-surface flex flex-col min-h-0"
    >
      <div class="shrink-0 flex items-center px-3 py-1.5 border-b border-border text-xs">
        <span class="font-semibold uppercase tracking-wider text-muted-foreground"> Crops </span>
        <span v-if="activeImage" class="ml-2 text-muted-foreground">
          {{ activeImage.detections.length }}
        </span>
        <button
          class="ml-auto p-1 rounded hover:bg-muted text-muted-foreground"
          title="Collapse crops"
          @click="cropsCollapsed = true"
        >
          <ChevronsRight class="w-4 h-4" />
        </button>
      </div>
      <div class="flex-1 overflow-y-auto">
        <ul v-if="activeImage" class="divide-y divide-border">
          <li v-for="d in activeImage.detections" :key="d.id">
            <div
              class="p-2 flex gap-2 transition-colors cursor-pointer"
              :class="isHighlighted(d.id) ? 'bg-primary/5' : 'hover:bg-muted/50'"
              @click="emit('update:selectedId', d.id)"
            >
              <!-- Sharp-cornered thumbnail. The whole row is the click
                   target (parent div); no separate popup. -->
              <div
                class="w-14 h-14 shrink-0 overflow-hidden bg-background border-2 shadow-sm"
                :class="isHighlighted(d.id) ? 'border-red-500' : 'border-border'"
              >
                <img
                  v-if="d.crop_url"
                  :src="d.crop_url"
                  :alt="`Detection ${d.id}`"
                  loading="lazy"
                  class="w-full h-full object-contain"
                />
                <div
                  v-else
                  class="w-full h-full flex items-center justify-center text-[10px] text-muted-foreground"
                >
                  n/a
                </div>
              </div>
              <!-- Two rows: model name | confidence | class abbreviation.
                   Fixed column widths so the values line up cleanly across
                   crops regardless of class name length. -->
              <div class="min-w-0 flex-1 text-xs space-y-0.5 font-mono">
                <div class="flex items-center gap-2">
                  <Tooltip text="YOLO detector branch: object detection score.">
                    <span class="text-muted-foreground w-16 text-[10px] cursor-help">YOLO</span>
                  </Tooltip>
                  <span class="w-10 tabular-nums">
                    {{ d.yolo_confidence != null ? d.yolo_confidence.toFixed(2) : '—' }}
                  </span>
                  <Tooltip :text="classFullName(d.yolo_class)">
                    <span class="font-medium cursor-help">{{ classAbbr(d.yolo_class) }}</span>
                  </Tooltip>
                </div>
                <div class="flex items-center gap-2">
                  <Tooltip
                    text="4-Group classifier: probability for the assigned class (fly / bumblebee / butterfly / other)."
                  >
                    <span class="text-muted-foreground w-16 text-[10px] cursor-help">4-Group</span>
                  </Tooltip>
                  <span class="w-10 tabular-nums">
                    {{ d.insectnet_confidence != null ? d.insectnet_confidence.toFixed(2) : '—' }}
                  </span>
                  <Tooltip :text="classFullName(d.insectnet_class)">
                    <span class="font-medium cursor-help">{{ classAbbr(d.insectnet_class) }}</span>
                  </Tooltip>
                </div>
              </div>
            </div>
          </li>
        </ul>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ChevronsLeft, ChevronsRight, ZoomOut } from 'lucide-vue-next'
import type { Detection, PollinatorClass } from '@/types/pollinator'
import Tooltip from '@/components/Tooltip.vue'
import InfoPopover from '@/components/InfoPopover.vue'
import ImageThumbnailRail, { type RailItem } from '@/components/pollinator/ImageThumbnailRail.vue'

const props = defineProps<{
  detections: Detection[]
  selectedId: number | null
  bulkIds?: Set<number>
}>()

const emit = defineEmits<{
  (e: 'update:selectedId', id: number): void
  // Fires on drag-select mouseup with the detection ids whose bbox center
  // falls inside the dragged rectangle. Empty array clears the bulk.
  (e: 'drag-select', ids: number[]): void
  // Fires when the user clicks a rail tile's delete button. Carries the
  // image filename; the parent rejects that image's unreviewed crops.
  (e: 'delete-image', filename: string): void
  // Fires when the active image's "exclude from YOLO training" toggle
  // flips. Carries the image filename; the parent persists + propagates.
  (e: 'toggle-training-exclude', filename: string): void
}>()

interface ImageGroup {
  filename: string
  sourceUrl: string | null
  detections: Detection[]
  naturalW: number
  naturalH: number
  aspectRatio: string | null
}

// Natural dimensions are loaded on-demand when an image becomes active.
const naturalSize = ref<Record<string, { w: number; h: number }>>({})

const images = computed<ImageGroup[]>(() => {
  const byFile = new Map<string, ImageGroup>()
  for (const d of props.detections) {
    if (!d.source_image_filename) continue
    const existing = byFile.get(d.source_image_filename)
    if (existing) {
      existing.detections.push(d)
    } else {
      const dims = naturalSize.value[d.source_image_filename]
      byFile.set(d.source_image_filename, {
        filename: d.source_image_filename,
        sourceUrl: d.source_image_url,
        detections: [d],
        naturalW: dims?.w ?? 0,
        naturalH: dims?.h ?? 0,
        aspectRatio: dims ? `${dims.w} / ${dims.h}` : null,
      })
    }
  }
  // Match the global filteredDetections sort: left-to-right (x1 asc),
  // then larger y first when x ties, then by id. Keeps the sidebar's
  // visual order in lockstep with arrow-key navigation.
  for (const img of byFile.values()) {
    img.detections.sort((a, b) => {
      const ax = a.bbox?.x1
      const bx = b.bbox?.x1
      if (ax == null && bx == null) return a.id - b.id
      if (ax == null) return 1
      if (bx == null) return -1
      if (ax !== bx) return ax - bx
      const ay = a.bbox?.y1 ?? 0
      const by = b.bbox?.y1 ?? 0
      if (ay !== by) return by - ay
      return a.id - b.id
    })
  }
  return [...byFile.values()].sort((a, b) => a.filename.localeCompare(b.filename))
})

// Manual override for image selection when the user clicks the rail
// without picking a specific crop.
const manualFilename = ref<string | null>(null)

const activeFilename = computed<string | null>(() => {
  if (manualFilename.value) {
    if (images.value.some((i) => i.filename === manualFilename.value)) {
      return manualFilename.value
    }
  }
  if (props.selectedId != null) {
    const sel = props.detections.find((d) => d.id === props.selectedId)
    if (sel?.source_image_filename) return sel.source_image_filename
  }
  return images.value[0]?.filename ?? null
})

const activeImage = computed<ImageGroup | null>(() => {
  if (!activeFilename.value) return null
  return images.value.find((i) => i.filename === activeFilename.value) ?? null
})

// All detections of an image carry the same per-image flag; read it off
// the first one.
const activeImageExcludeTraining = computed(
  () => activeImage.value?.detections[0]?.exclude_from_training ?? false,
)

function selectImage(img: ImageGroup) {
  manualFilename.value = img.filename
  const first = img.detections[0]
  if (first) emit('update:selectedId', first.id)
}

function selectByFilename(filename: string) {
  const img = images.value.find((i) => i.filename === filename)
  if (img) selectImage(img)
}

const railItems = computed<RailItem[]>(() =>
  images.value.map((img) => {
    const n = img.detections.length
    const cropsLabel = `${n} crop${n === 1 ? '' : 's'}`
    // Image is "done" when every detection has been reviewed (either
    // confirmed or corrected). Mirrors the Export-page green so the
    // visual reads as "ready to ship".
    const allReviewed =
      n > 0 &&
      img.detections.every(
        (d) => d.reviewer_status === 'confirmed' || d.reviewer_status === 'corrected',
      )
    return {
      key: img.filename,
      label: img.filename,
      src: img.sourceUrl,
      caption: cropsLabel,
      title: `${img.filename} · ${cropsLabel}`,
      accentClass: allReviewed ? 'border-green-800' : undefined,
    }
  }),
)

watch(
  () => props.selectedId,
  (newId, oldId) => {
    if (newId !== oldId) manualFilename.value = null
  },
)

// A bbox is highlighted (red-filled) when it's the single selection OR
// part of the bulk set. Empty bulk falls back to single selection.
function isHighlighted(id: number): boolean {
  if (props.bulkIds && props.bulkIds.size > 0) return props.bulkIds.has(id)
  return id === props.selectedId
}

// --- Crops column collapse state ----------------------------------------
const CROPS_COLLAPSED_KEY = 'pollinatorImageFirst:cropsCollapsed'
const cropsCollapsed = ref<boolean>(
  typeof localStorage !== 'undefined' && localStorage.getItem(CROPS_COLLAPSED_KEY) === '1',
)
watch(cropsCollapsed, (v) => {
  try {
    localStorage.setItem(CROPS_COLLAPSED_KEY, v ? '1' : '0')
  } catch {
    // localStorage may be unavailable; ignore.
  }
})

// Short class label used in the side column rows. The user wants the
// terse forms BB / BF (bumblebee / butterfly) for legibility in narrow
// rows; fly and other stay full words.
function classAbbr(cls: PollinatorClass | null): string {
  switch (cls) {
    case 'fly':
      return 'Fly'
    case 'bumblebee':
      return 'BB'
    case 'butterfly':
      return 'BF'
    case 'other':
      return 'Other'
    default:
      return '—'
  }
}

function classFullName(cls: PollinatorClass | null): string {
  switch (cls) {
    case 'fly':
      return 'Fly'
    case 'bumblebee':
      return 'Bumblebee'
    case 'butterfly':
      return 'Butterfly'
    case 'other':
      return 'Other'
    default:
      return 'No class assigned'
  }
}

// Lazy natural-dim preload for the active image.
watch(
  () => activeImage.value?.sourceUrl,
  (url) => {
    if (!url || !activeImage.value) return
    const filename = activeImage.value.filename
    if (naturalSize.value[filename]) return
    const img = new Image()
    img.onload = () => {
      naturalSize.value = {
        ...naturalSize.value,
        [filename]: { w: img.naturalWidth, h: img.naturalHeight },
      }
    }
    img.src = url
  },
  { immediate: true },
)

// Auto-scroll on activeFilename change is handled inside
// ImageThumbnailRail.

// --- Drag-select over the source image ------------------------------------

interface DragRect {
  x1: number
  y1: number
  x2: number
  y2: number
}
const dragRect = ref<DragRect | null>(null)
const svgEl = ref<SVGSVGElement | null>(null)
const transformGroupEl = ref<SVGGElement | null>(null)
let dragStartImg: { x: number; y: number } | null = null

// --- Inline zoom + pan --------------------------------------------------
//
// The transform group inside the SVG carries the zoom and pan as a single
// `translate scale` transform applied in viewBox-coords. Wheel + alt zooms
// around the cursor; right-click or alt+left-click drags pan. All drag-
// select rectangles share the same coord space (inside the same <g>) so
// hit tests stay correct at any zoom level.
const MIN_ZOOM = 1
const MAX_ZOOM = 8
const zoom = ref({ scale: 1, tx: 0, ty: 0 })
const isZoomed = computed(() => zoom.value.scale > 1.0001)
const panning = ref(false)

function resetZoom() {
  zoom.value = { scale: 1, tx: 0, ty: 0 }
}

// When the active image changes, snap the zoom back to 1× so the new
// image starts fully visible.
watch(activeFilename, () => {
  if (zoom.value.scale !== 1) resetZoom()
})

// Convert a browser MouseEvent into image-space coordinates via the
// transform group's CTM (which folds in the current zoom transform). This
// means drag-select rectangles stay aligned with bboxes at any zoom.
function eventToImagePoint(e: MouseEvent): { x: number; y: number } | null {
  const g = transformGroupEl.value
  const svg = svgEl.value
  if (!g || !svg) return null
  const pt = svg.createSVGPoint()
  pt.x = e.clientX
  pt.y = e.clientY
  const ctm = g.getScreenCTM()
  if (!ctm) return null
  const local = pt.matrixTransform(ctm.inverse())
  return { x: local.x, y: local.y }
}

// Cursor's position in untransformed viewBox coords. Used by zoom-around-
// cursor and pan delta math, where we work in the pre-transform space.
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

// Plain wheel flips through the source images in the rail; Alt+wheel zooms
// the current image. deltaY accumulates so trackpads (which fire many tiny
// events) advance one image per gesture rather than racing through dozens.
let wheelAccum = 0
const WHEEL_STEP = 60

function stepImage(dir: 1 | -1) {
  const list = images.value
  if (!list.length) return
  const idx = list.findIndex((i) => i.filename === activeFilename.value)
  const next = (idx < 0 ? 0 : idx) + dir
  if (next < 0 || next >= list.length) return
  selectImage(list[next])
}

function onImageWheel(e: WheelEvent) {
  if (!e.altKey) {
    // Step through rail images.
    if (!images.value.length) return
    e.preventDefault()
    wheelAccum += e.deltaY
    if (Math.abs(wheelAccum) < WHEEL_STEP) return
    stepImage(wheelAccum > 0 ? 1 : -1)
    wheelAccum = 0
    return
  }
  if (!activeImage.value?.naturalW) return
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
  // After transform: rendered = scale * orig + tx => orig = (rendered - tx) / scale
  const newTx = vb.x - ((vb.x - zoom.value.tx) * newScale) / oldScale
  const newTy = vb.y - ((vb.y - zoom.value.ty) * newScale) / oldScale
  zoom.value = { scale: newScale, tx: newTx, ty: newTy }
  // Snap to identity if scaled all the way out.
  if (newScale <= MIN_ZOOM + 0.0001) resetZoom()
}

// Pan state. Tracks the cursor's starting viewBox position and the
// translate at the moment the drag began.
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
  if (!activeImage.value?.naturalW) return
  // Right-click or alt+left-click starts a pan; plain left-click starts a
  // drag-select. Middle-click is ignored.
  const isPan = e.button === 2 || (e.button === 0 && e.altKey)
  if (isPan) {
    startPan(e)
    return
  }
  if (e.button !== 0) return
  const p = eventToImagePoint(e)
  if (!p) return
  e.preventDefault()
  dragStartImg = p
  dragRect.value = { x1: p.x, y1: p.y, x2: p.x, y2: p.y }
  window.addEventListener('mousemove', onImageMouseMove)
  window.addEventListener('mouseup', onImageMouseUp)
}
function onImageMouseMove(e: MouseEvent) {
  if (!dragStartImg) return
  const p = eventToImagePoint(e)
  if (!p) return
  dragRect.value = {
    x1: Math.min(dragStartImg.x, p.x),
    y1: Math.min(dragStartImg.y, p.y),
    x2: Math.max(dragStartImg.x, p.x),
    y2: Math.max(dragStartImg.y, p.y),
  }
}
function onImageMouseUp() {
  window.removeEventListener('mousemove', onImageMouseMove)
  window.removeEventListener('mouseup', onImageMouseUp)
  const r = dragRect.value
  dragStartImg = null
  dragRect.value = null
  if (!r || !activeImage.value) return
  // Treat a near-zero drag as a click on empty canvas — clear the bulk.
  const w = r.x2 - r.x1
  const h = r.y2 - r.y1
  if (w < 2 && h < 2) {
    emit('drag-select', [])
    return
  }
  const hits: number[] = []
  for (const d of activeImage.value.detections) {
    if (!d.bbox) continue
    const cx = d.bbox.x1 + d.bbox.w / 2
    const cy = d.bbox.y1 + d.bbox.h / 2
    if (cx >= r.x1 && cx <= r.x2 && cy >= r.y1 && cy <= r.y2) {
      hits.push(d.id)
    }
  }
  emit('drag-select', hits)
}

// Bbox mousedown: forward right-click / alt+left-click up to the image
// area so a pan can start from inside a bbox; otherwise stop propagation
// so click-to-select works without also kicking off a drag-select.
function onBboxMouseDown(_id: number, e: MouseEvent) {
  const isPan = e.button === 2 || (e.button === 0 && e.altKey)
  if (isPan) {
    startPan(e)
  }
}

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onImageMouseMove)
  window.removeEventListener('mouseup', onImageMouseUp)
  window.removeEventListener('mousemove', onPanMove)
  window.removeEventListener('mouseup', onPanEnd)
})
</script>
