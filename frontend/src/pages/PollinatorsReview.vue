<template>
  <PageHeader :title="headerTitle" subtitle="Confirm, correct, or reject detections" />
  <PollinatorsStepper current="review" :runId="run?.id" />

  <div v-if="loading" class="flex-1 p-8 text-sm text-muted-foreground">Loading…</div>
  <div v-else-if="loadError" class="flex-1 p-8 text-sm text-red-600">{{ loadError }}</div>

  <div v-else class="flex-1 flex flex-col min-h-0">
    <div
      v-if="failedSaves.size > 0"
      class="border-l-4 border-red-500 bg-red-50 px-4 py-2 text-sm text-red-800 flex items-center gap-3 shrink-0"
    >
      <span class="flex-1">
        ⚠ {{ failedSaves.size }} review{{ failedSaves.size === 1 ? '' : 's' }} failed to save
      </span>
      <button
        class="px-2 py-1 rounded bg-red-600 text-white hover:bg-red-700 text-xs font-medium"
        @click="retryFailedSaves"
        :disabled="retrying"
      >
        {{ retrying ? 'Retrying…' : 'Retry all' }}
      </button>
      <button
        class="px-2 py-1 rounded border border-red-300 text-red-700 hover:bg-red-100 text-xs"
        @click="dismissFailedSaves"
        :disabled="retrying"
      >
        Dismiss
      </button>
    </div>
    <div class="flex-1 flex flex-col-reverse lg:flex-row min-h-0">
      <!-- Left: filters + grouped grid -->
      <section
        class="w-full lg:w-[480px] shrink-0 border-t lg:border-t-0 lg:border-r border-border flex flex-col bg-surface max-h-[55vh] lg:max-h-none"
      >
        <div class="px-4 py-3 border-b border-border space-y-2">
          <div class="flex items-center gap-2 text-xs">
            <label class="text-muted-foreground">Show</label>
            <select
              v-model="statusFilter"
              class="px-2 py-1 rounded border border-border bg-background"
            >
              <option value="pending">Pending</option>
              <option value="reviewed">Reviewed</option>
              <option value="unsure">Unsure</option>
              <option value="all">All</option>
            </select>
            <label class="text-muted-foreground">Class</label>
            <select
              v-model="classFilter"
              class="px-2 py-1 rounded border border-border bg-background"
            >
              <option value="all">All</option>
              <option v-for="cls in CLASSES" :key="cls" :value="cls">
                {{ classLabel(cls) }}
              </option>
              <option value="background">Background</option>
            </select>
          </div>
          <!-- Single minimum-confidence slider. Filters on the strongest
             model score per detection (max of yolo / insectnet). One control
             instead of two means the slider always does something regardless
             of which branch produced the detection. Step 0.05 keeps it
             snappy. -->
          <div class="grid grid-cols-[auto_1fr_auto] items-center gap-x-2 gap-y-1 text-xs">
            <label for="min-conf" class="text-muted-foreground">Min conf ≥</label>
            <input
              id="min-conf"
              type="range"
              min="0"
              max="1"
              step="0.05"
              v-model.number="minConf"
              class="w-full accent-primary"
            />
            <span class="font-mono w-10 text-right">{{ minConf.toFixed(2) }}</span>
          </div>
          <div v-if="belowThresholdIds.length" class="flex items-center justify-end text-xs">
            <button
              class="px-2 py-1 rounded border border-red-300 text-red-700 hover:bg-red-50 disabled:opacity-50"
              :disabled="rejectingBelow"
              @click="rejectBelowThreshold"
            >
              {{
                rejectingBelow ? 'Rejecting…' : `Reject ${belowThresholdIds.length} below threshold`
              }}
            </button>
          </div>
          <div class="text-xs text-muted-foreground flex items-center justify-between gap-3">
            <span class="flex-1 min-w-0 truncate">
              {{ filteredDetections.length }} of {{ detections.length }} detections<span
                v-if="loadProgress.total && loadProgress.loaded < loadProgress.total"
                class="italic"
              >
                · loading {{ loadProgress.loaded }}/{{ loadProgress.total }}…</span
              >
            </span>
            <button
              class="text-primary hover:underline"
              :disabled="!filteredDetections.length"
              @click="selectAllVisible"
            >
              Select all
            </button>
          </div>
        </div>

        <!-- Bulk action bar (only when 1+ selected) -->
        <div
          v-if="bulkIds.size > 0"
          class="px-4 py-2 border-b border-border bg-primary/5 flex flex-wrap items-center gap-2 text-xs"
        >
          <span class="font-medium">{{ bulkIds.size }} selected</span>
          <button
            class="px-2 py-1 rounded bg-primary text-primary-foreground hover:bg-primary/90"
            @click="bulkConfirm"
          >
            Confirm
          </button>
          <button class="px-2 py-1 rounded border border-border hover:bg-muted" @click="bulkReject">
            Reject
          </button>
          <select
            v-model="bulkCorrectClass"
            class="px-2 py-1 rounded border border-border bg-background"
            @change="onBulkCorrectChange"
          >
            <option value="">Correct to…</option>
            <option v-for="cls in CLASSES" :key="cls" :value="cls">
              {{ classLabel(cls) }}
            </option>
          </select>
          <button class="ml-auto text-muted-foreground hover:text-foreground" @click="clearBulk">
            Clear
          </button>
        </div>
        <div
          v-if="bulkConfirmSkipped > 0"
          class="px-4 py-2 border-b border-border bg-amber-50 text-amber-800 flex items-center gap-2 text-xs"
        >
          <span>
            Skipped {{ bulkConfirmSkipped }} row{{ bulkConfirmSkipped === 1 ? '' : 's' }}
            with no predicted class. Correct them explicitly so they're included in group/detector
            training.
          </span>
          <button
            class="ml-auto text-amber-700 hover:text-amber-900"
            @click="bulkConfirmSkipped = 0"
          >
            Dismiss
          </button>
        </div>

        <div class="flex-1 overflow-auto">
          <div v-for="group in groupedDetections" :key="group.label" class="border-b border-border">
            <header
              class="px-4 py-2 text-xs font-semibold uppercase tracking-wide bg-surface sticky top-0 z-20 border-b border-border"
              :class="
                group.kind === 'needs_review'
                  ? 'text-amber-700'
                  : group.kind === 'unclassified'
                    ? 'text-indigo-700'
                    : group.kind === 'background'
                      ? 'text-muted-foreground/70'
                      : 'text-muted-foreground'
              "
            >
              <span v-if="group.kind === 'needs_review'" class="mr-1">⚠</span>
              <span v-else-if="group.kind === 'unclassified'" class="mr-1">?</span>
              <span v-else-if="group.kind === 'background'" class="mr-1">✗</span>
              {{ group.label }}
              <span class="font-normal">({{ group.detections.length }})</span>
            </header>
            <div class="grid grid-cols-5 gap-1 p-2">
              <div
                v-for="d in group.detections"
                :key="d.id"
                class="rounded-md overflow-hidden border-2 transition-all"
                :class="[
                  selectedId === d.id
                    ? 'border-primary ring-2 ring-primary'
                    : 'border-transparent hover:border-border',
                  reviewedFade(d) ? 'opacity-50' : '',
                ]"
              >
                <div
                  :data-detection-id="d.id"
                  role="button"
                  tabindex="0"
                  class="relative aspect-square cursor-pointer focus:outline-none select-none"
                  :class="imageParityById.get(d.id) ? 'bg-muted/60' : 'bg-background'"
                  @click="onTileClick(d, $event)"
                  @keydown.enter.prevent="onTileClick(d, $event)"
                >
                  <img
                    v-if="d.crop_url"
                    :src="d.crop_url"
                    :alt="`Detection ${d.id}`"
                    loading="lazy"
                    class="absolute inset-0 w-full h-full object-contain"
                  />
                  <div
                    v-else
                    class="absolute inset-0 flex items-center justify-center text-2xl font-bold opacity-30"
                  >
                    {{ classGlyph(primaryClass(d)) }}
                  </div>
                </div>
                <div
                  role="checkbox"
                  :aria-checked="bulkIds.has(d.id)"
                  tabindex="0"
                  class="h-5 flex items-center justify-center text-xs cursor-pointer transition-colors"
                  :class="
                    bulkIds.has(d.id)
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-surface text-muted-foreground hover:bg-muted'
                  "
                  @click="toggleBulk(d.id)"
                  @keydown.space.prevent="toggleBulk(d.id)"
                >
                  <span v-if="bulkIds.has(d.id)">✓</span>
                </div>
              </div>
            </div>
          </div>
          <div
            v-if="!groupedDetections.length"
            class="p-8 text-center text-sm text-muted-foreground"
          >
            No detections match the current filter.
          </div>
        </div>
      </section>

      <!-- Right: preview pane (mirrors left's structural feel: thin top bar, scroll body, action bar at bottom) -->
      <section class="flex-1 flex flex-col min-w-0">
        <div v-if="!selected" class="m-auto text-sm text-muted-foreground">
          Select a detection on the left to review it.
        </div>
        <template v-else>
          <!-- Top bar (height matches left filter bar) -->
          <header
            class="px-5 py-3 border-b border-border bg-surface text-sm flex items-center gap-3"
          >
            <span class="font-medium">Detection #{{ selected.id }}</span>
            <span class="text-muted-foreground font-mono text-xs truncate">
              {{ selected.source_image_filename }}
            </span>
            <span
              class="ml-auto text-xs px-2 py-0.5 rounded-full shrink-0"
              :class="statusBadgeClass(selected.reviewer_status)"
              >{{ statusLabel(selected.reviewer_status) }}</span
            >
          </header>

          <div class="flex-1 flex flex-col min-h-0">
            <!-- Source image with bbox overlay. Click to open the zoom modal.
               flex-1 + min-h-0 makes it fill whatever vertical space is left
               after the predictions/label/footer, instead of locking to a
               16:9 box that forced the right pane to scroll. -->
            <div
              class="flex-1 min-h-0 relative overflow-hidden"
              :class="selected.source_image_url && sourceImage.w ? 'cursor-zoom-in' : ''"
              :style="{ backgroundColor: classBgFor(primaryClass(selected)) }"
              role="button"
              tabindex="0"
              @click="openZoom"
              @keydown.enter.prevent="openZoom"
            >
              <div
                class="absolute top-0 left-0 right-0 h-1.5 z-10"
                :style="{ backgroundColor: classColor(primaryClass(selected)) }"
              />
              <svg
                v-if="selected.source_image_url && sourceImage.w"
                :viewBox="`0 0 ${sourceImage.w} ${sourceImage.h}`"
                preserveAspectRatio="xMidYMid meet"
                class="absolute inset-0 w-full h-full"
              >
                <image
                  :href="selected.source_image_url"
                  :width="sourceImage.w"
                  :height="sourceImage.h"
                />
                <rect
                  v-if="bboxOutline"
                  :x="bboxOutline.x"
                  :y="bboxOutline.y"
                  :width="bboxOutline.width"
                  :height="bboxOutline.height"
                  fill="#ef4444"
                  fill-opacity="0.18"
                  stroke="#ef4444"
                  :stroke-width="bboxStrokeWidth"
                />
                <ROIOverlay :bbox="roiBbox" :image-w="sourceImage.w" :image-h="sourceImage.h" />
              </svg>
              <span
                v-else
                class="absolute inset-0 flex items-center justify-center text-7xl font-bold opacity-30"
                >{{ classGlyph(primaryClass(selected)) }}</span
              >
            </div>

            <!-- Predictions + Label: stacked below xl, side-by-side at xl+ (Label left, Predictions right) -->
            <div class="grid grid-cols-1 xl:grid-cols-2 border-b border-border">
              <!-- Predictions (compact, two-line). Order swap at xl+ via order-2. -->
              <div class="px-5 py-4 border-b border-border xl:border-b-0 xl:order-2">
                <div
                  class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-2"
                >
                  Predictions
                </div>
                <div class="space-y-1.5 text-sm">
                  <div
                    class="flex items-center gap-2"
                    :class="selected.yolo_class == null ? 'opacity-60' : ''"
                  >
                    <span class="text-muted-foreground w-20">YOLO</span>
                    <span
                      class="w-2 h-2 rounded-full shrink-0"
                      :style="{ backgroundColor: classColor(selected.yolo_class) }"
                    />
                    <span class="font-medium flex-1">{{
                      selected.yolo_class ? classLabel(selected.yolo_class) : '—'
                    }}</span>
                    <span class="font-mono text-xs text-muted-foreground">
                      {{
                        selected.yolo_confidence != null ? selected.yolo_confidence.toFixed(2) : '—'
                      }}
                    </span>
                  </div>
                  <div
                    class="flex items-center gap-2"
                    :class="selected.insectnet_class == null ? 'opacity-60' : ''"
                  >
                    <span class="text-muted-foreground w-20">InsectNet</span>
                    <span
                      class="w-2 h-2 rounded-full shrink-0"
                      :style="{ backgroundColor: classColor(selected.insectnet_class) }"
                    />
                    <span class="font-medium flex-1">{{
                      selected.insectnet_class ? classLabel(selected.insectnet_class) : '—'
                    }}</span>
                    <span class="font-mono text-xs text-muted-foreground">
                      {{
                        selected.insectnet_confidence != null
                          ? selected.insectnet_confidence.toFixed(2)
                          : '—'
                      }}
                    </span>
                  </div>
                  <div v-if="hasDisagreement(selected)" class="text-xs text-amber-700 pt-1">
                    ⚠ Models disagree
                  </div>
                  <div v-else-if="isLowConfidence(selected)" class="text-xs text-amber-700 pt-1">
                    ⚠ Low confidence
                  </div>
                </div>
              </div>

              <!-- Label (one row per class with checkbox at end). Visually first at xl+ via order-1. -->
              <div class="px-5 py-4 xl:order-1 xl:border-r border-border">
                <div
                  class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-2"
                >
                  Label
                </div>
                <!-- Radios (not checkboxes) so the browser enforces single-
                   select at the DOM level. With checkboxes a click race
                   between Vue's :checked re-binding and the DOM's own state
                   could leave two ticks visible. The name attribute groups
                   them so picking one auto-unsets the others. -->
                <div>
                  <label
                    v-for="cls in CLASSES"
                    :key="cls"
                    class="flex items-center gap-3 py-2 px-2 -mx-2 rounded cursor-pointer"
                  >
                    <span
                      class="w-2 h-2 rounded-full shrink-0"
                      :style="{ backgroundColor: classColor(cls) }"
                    />
                    <span class="flex-1 text-sm">{{ classLabel(cls) }}</span>
                    <input
                      type="radio"
                      name="label-class"
                      :checked="cls === effectiveLabel(selected)"
                      @change="confirmAs(cls)"
                      class="w-4 h-4"
                    />
                  </label>
                  <!-- 5th option: rejecting means "this is background" — the
                     binary classifier trains rejected detections as the
                     'background' class. Treating it as a label keeps the
                     Label panel as a single source of truth for what the
                     reviewer decided. -->
                  <label class="flex items-center gap-3 py-2 px-2 -mx-2 rounded cursor-pointer">
                    <span class="w-2 h-2 rounded-full shrink-0 bg-muted-foreground/40" />
                    <span class="flex-1 text-sm">
                      Background
                      <span class="text-[10px] text-muted-foreground ml-1">(reject)</span>
                    </span>
                    <input
                      type="radio"
                      name="label-class"
                      :checked="selected.reviewer_status === 'rejected'"
                      @change="reject()"
                      class="w-4 h-4"
                    />
                  </label>
                </div>
              </div>
            </div>
          </div>

          <!-- "All reviewed" CTA. Sits above the footer so the action bar
             buttons are still visible for further edits, while making the
             next-step path obvious. -->
          <div
            v-if="allReviewed && run"
            class="border-t border-border bg-green-50 px-5 py-3 flex items-center gap-3 text-sm"
          >
            <span class="text-green-800 flex-1">
              ✓ All detections reviewed. Ready for export.
            </span>
            <RouterLink
              :to="`/pollinators/runs/${run.id}/export`"
              class="px-3 py-1.5 rounded-md bg-green-600 text-white hover:bg-green-700 font-medium"
            >
              Continue to Export →
            </RouterLink>
          </div>
          <!-- Bottom action bar -->
          <footer
            class="border-t border-border bg-surface px-5 py-3 flex items-center justify-between"
          >
            <span class="text-[11px] text-muted-foreground font-mono hidden md:block">
              1-4 confirm · x reject · u unsure · ⏎ suggested · ←→↑↓ navigate · ⇧ + arrows / click:
              range select · esc: clear
            </span>
            <div class="flex gap-2 ml-auto">
              <button
                class="px-3 py-1.5 rounded-md text-sm font-medium border border-border hover:bg-muted"
                @click="reject()"
              >
                Reject
              </button>
              <button
                class="px-3 py-1.5 rounded-md text-sm font-medium border border-amber-300 text-amber-700 hover:bg-amber-50"
                @click="markUnsure()"
              >
                Unsure
              </button>
              <button
                class="px-3 py-1.5 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-primary"
                :disabled="!effectiveLabel(selected)"
                :title="effectiveLabel(selected) ? '' : 'Pick a label or wait for models to agree'"
                @click="confirmAs(effectiveLabel(selected))"
              >
                Confirm
              </button>
            </div>
          </footer>
        </template>
      </section>
    </div>
  </div>

  <!-- Fullscreen zoom for the selected detection's source image. Wheel-zooms
       around the cursor; click-and-drag pans. ESC or backdrop closes. -->
  <dialog
    ref="zoomDialog"
    class="m-0 p-0 w-screen h-screen max-w-none max-h-none bg-black/95 backdrop:bg-black/95"
    @close="onZoomClose"
    @click.self="closeZoom"
  >
    <div
      v-if="selected && selected.source_image_url && sourceImage.w"
      class="w-screen h-screen relative select-none overflow-hidden"
      @wheel.prevent="onZoomWheel"
      @mousedown="onPanStart"
      @mousemove="onPanMove"
      @mouseup="onPanEnd"
      @mouseleave="onPanEnd"
      :style="{ cursor: panning ? 'grabbing' : 'grab' }"
    >
      <svg
        :viewBox="`0 0 ${sourceImage.w} ${sourceImage.h}`"
        preserveAspectRatio="xMidYMid meet"
        class="w-full h-full"
      >
        <g :transform="`translate(${zoom.tx} ${zoom.ty}) scale(${zoom.scale})`">
          <image :href="selected.source_image_url" :width="sourceImage.w" :height="sourceImage.h" />
          <rect
            v-if="bboxOutline"
            :x="bboxOutline.x"
            :y="bboxOutline.y"
            :width="bboxOutline.width"
            :height="bboxOutline.height"
            fill="none"
            stroke="#ef4444"
            :stroke-width="bboxStrokeWidth"
            vector-effect="non-scaling-stroke"
          />
          <ROIOverlay
            :bbox="roiBbox"
            :image-w="sourceImage.w"
            :image-h="sourceImage.h"
            non-scaling-stroke
          />
        </g>
      </svg>
      <button
        class="absolute top-4 right-4 px-3 py-1.5 rounded-md bg-white/10 text-white text-sm hover:bg-white/20"
        @click.stop="closeZoom"
      >
        Close (Esc)
      </button>
      <div class="absolute bottom-4 left-1/2 -translate-x-1/2 text-white/60 text-xs font-mono">
        scroll to zoom · drag to pan · {{ Math.round(zoom.scale * 100) }}%
      </div>
    </div>
  </dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import PollinatorsStepper from '@/components/PollinatorsStepper.vue'
import ROIOverlay from '@/components/ROIOverlay.vue'
import { api } from '@/api'

type ClassName = 'fly' | 'bumblebee' | 'butterfly' | 'other'
type ReviewerStatus = 'unreviewed' | 'confirmed' | 'corrected' | 'rejected' | 'unsure'
// Frontend workflow labels (not the backend reviewer_status).
//   pending  — unreviewed; the active working queue.
//   reviewed — anything the reviewer has settled (confirmed / corrected /
//              rejected). Lets the reviewer see what's already handled.
//   unsure   — explicitly parked for revisit; kept separate so it doesn't
//              disappear into the reviewed pile.
//   all      — everything.
type StatusFilter = 'pending' | 'reviewed' | 'unsure' | 'all'
type Source = 'yolo' | 'preprocessing' | 'both'

const LOW_CONFIDENCE_THRESHOLD = 0.6

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
  // YOLO-only detections have null insectnet_*, preprocessing-only have null
  // yolo_*. Only source='both' detections populate both branches.
  yolo_class: ClassName | null
  yolo_confidence: number | null
  insectnet_class: ClassName | null
  insectnet_confidence: number | null
  source: Source
  reviewer_status: ReviewerStatus
  reviewer_label: ClassName | null
  predicted_class: ClassName | null
  source_image_filename: string
  bbox: BBox | null
  source_image_url: string | null
  crop_url: string | null
}

interface ReviewBundle {
  run: {
    id: number
    name: string
    status: string
    detection_count: number
    config?: {
      preprocessing?: {
        roi_bbox?: [number, number, number, number] | null
      }
    }
  }
  detections: Detection[]
}

const CLASSES: ClassName[] = ['fly', 'bumblebee', 'butterfly', 'other']
const CLASS_COLORS: Record<ClassName, string> = {
  fly: '#6b9bd2',
  bumblebee: '#e6a946',
  butterfly: '#c87bba',
  other: '#9aa3ab',
}
const CLASS_GLYPHS: Record<ClassName, string> = {
  fly: '🪰',
  bumblebee: '🐝',
  butterfly: '🦋',
  other: '?',
}

const route = useRoute()
const loading = ref(true)
const loadError = ref('')
const run = ref<ReviewBundle['run'] | null>(null)
const detections = ref<Detection[]>([])
const selectedId = ref<number | null>(null)
const statusFilter = ref<StatusFilter>('pending')
type ClassFilter = ClassName | 'background' | 'all'
const classFilter = ref<ClassFilter>('all')
// Single confidence slider. Filters on the strongest model score per
// detection so it always does something regardless of which branch fired.
// Starts at 0 ("no filter") so the reviewer has to opt in.
const minConf = ref(0)

function passesSliders(d: Detection): boolean {
  return maxConfidence(d) >= minConf.value
}
const bulkIds = ref<Set<number>>(new Set())
const bulkCorrectClass = ref<'' | ClassName>('')
// Surfaces how many rows the most recent bulk-confirm skipped because they
// had no derivable class. Reset when the reviewer next interacts with the
// bulk bar (selection change or explicit clear).
const bulkConfirmSkipped = ref(0)

interface FailedEntry {
  status: ReviewerStatus
  label: ClassName | null
  prevStatus: ReviewerStatus
  prevLabel: ClassName | null
}
const failedSaves = ref<Map<number, FailedEntry>>(new Map())
const retrying = ref(false)
const rejectingBelow = ref(false)

onMounted(loadFromApi)

interface DetectionsPage {
  count: number
  next: string | null
  results: Detection[]
}

const loadProgress = ref({ loaded: 0, total: 0 })

async function loadFromApi() {
  const id = route.params.id as string
  try {
    const runRes = await api(`/api/analysis/runs/${id}/`)
    if (!runRes.ok) {
      loadError.value = `Run: HTTP ${runRes.status}`
      loading.value = false
      return
    }
    run.value = await runRes.json()
    // Stream pages: paint the first batch immediately so the reviewer
    // can start clicking, then keep appending until the run is fully
    // loaded. detections.value is reactive; groupedDetections recomputes
    // each time we extend it.
    let next: string | null = `/api/pollinator/runs/${id}/detections/`
    let firstPage = true
    while (next) {
      const url: string = next.startsWith('http') ? next.replace(/^https?:\/\/[^/]+/, '') : next
      const res = await api(url)
      if (!res.ok) {
        loadError.value = `Detections: HTTP ${res.status}`
        return
      }
      const page = (await res.json()) as DetectionsPage
      detections.value = detections.value.concat(page.results)
      loadProgress.value = { loaded: detections.value.length, total: page.count }
      next = page.next
      if (firstPage) {
        loading.value = false
        firstPage = false
      }
    }
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

const headerTitle = computed(() =>
  run.value ? `Review · ${run.value.name || `Run #${run.value.id}`}` : 'Review',
)

// Reviewer is done when no detection is still in the unreviewed pile.
// Computed over the full detections list, not filteredDetections, so a
// status/class filter doesn't make the banner falsely appear.
const allReviewed = computed(
  () =>
    detections.value.length > 0 &&
    detections.value.every((d) => d.reviewer_status !== 'unreviewed'),
)

const filteredDetections = computed(() => {
  let list = detections.value
  if (statusFilter.value === 'pending') {
    list = list.filter((d) => d.reviewer_status === 'unreviewed')
  } else if (statusFilter.value === 'reviewed') {
    list = list.filter(
      (d) =>
        d.reviewer_status === 'confirmed' ||
        d.reviewer_status === 'corrected' ||
        d.reviewer_status === 'rejected',
    )
  } else if (statusFilter.value === 'unsure') {
    list = list.filter((d) => d.reviewer_status === 'unsure')
  }
  // Class filter.
  //   Background    → only rejected rows (rejected = background label).
  //   Fly/Bee/etc.  → reviewer's call wins. Confirmed/corrected match strictly
  //                   on reviewer_label. Rejected rows are excluded entirely
  //                   even if the original model thought they were that
  //                   class — the reviewer overruled that prediction.
  //                   Unreviewed/unsure still match any signal so the
  //                   reviewer can hunt by detector output when nothing has
  //                   been settled yet.
  if (classFilter.value !== 'all') {
    const cls = classFilter.value
    list = list.filter((d) => {
      if (cls === 'background') return d.reviewer_status === 'rejected'
      if (d.reviewer_status === 'rejected') return false
      if (d.reviewer_status === 'confirmed' || d.reviewer_status === 'corrected') {
        return (d.reviewer_label ?? d.predicted_class) === cls
      }
      return (
        d.yolo_class === cls ||
        d.insectnet_class === cls ||
        d.reviewer_label === cls ||
        d.predicted_class === cls
      )
    })
  }
  list = list.filter(passesSliders)
  // Stable sort by id. The previous double-sort (confidence at this layer,
  // then by source-image filename inside each group) caused tiles to
  // visibly swap places whenever streamed pages arrived or a review action
  // shifted the underlying ordering. Insertion order from the backend is
  // deterministic and never moves once loaded.
  return [...list].sort((a, b) => a.id - b.id)
})

const groupedDetections = computed(() => {
  const review: Detection[] = []
  const unclassified: Detection[] = []
  const background: Detection[] = []
  const classGroups = new Map<ClassName, Detection[]>()
  // Placement priority:
  // 1. Rejected detections are labelled "background" — they go to the
  //    Background bucket regardless of detector state. Keeping them under
  //    a Fly / Needs-review header would suggest they belonged to that
  //    class, which they don't.
  // 2. Confirmed/corrected detections have a settled class — drop them
  //    into that class group, even when the detectors split.
  // 3. Unreviewed/unsure detections fall back to detector logic: needs-
  //    review when the detectors aren't unanimous, the agreed class when
  //    they are, unclassified when neither named a class.
  // When the user filtered to a specific class, drop the needs-review /
  // unclassified split: everything that matched is a candidate for *this*
  // class. Background still gets pulled aside so duplicate-spotting in
  // Class=Fly doesn't count rejected things.
  // Class=Background is handled via the existing rejected → background
  // bucket above, so we don't need a collapse rule for it.
  const collapseToClass: ClassName | null =
    classFilter.value !== 'all' && classFilter.value !== 'background'
      ? classFilter.value
      : null
  for (const d of filteredDetections.value) {
    if (d.reviewer_status === 'rejected') {
      background.push(d)
      continue
    }
    if (collapseToClass != null) {
      if (!classGroups.has(collapseToClass)) classGroups.set(collapseToClass, [])
      classGroups.get(collapseToClass)!.push(d)
      continue
    }
    const settled = settledClass(d)
    if (settled != null) {
      if (!classGroups.has(settled)) classGroups.set(settled, [])
      classGroups.get(settled)!.push(d)
      continue
    }
    if (needsReview(d)) {
      review.push(d)
      continue
    }
    const cls = primaryClass(d)
    if (cls == null) {
      unclassified.push(d)
      continue
    }
    if (!classGroups.has(cls)) classGroups.set(cls, [])
    classGroups.get(cls)!.push(d)
  }
  // No per-group re-sort. filteredDetections is already sorted by id, and
  // the bucketing above preserves that order within each bucket.
  const out: {
    label: string
    kind: 'needs_review' | 'unclassified' | 'class' | 'background'
    detections: Detection[]
  }[] = []
  if (unclassified.length) {
    out.push({ label: 'Unclassified', kind: 'unclassified', detections: unclassified })
  }
  if (review.length) {
    out.push({ label: 'Needs review', kind: 'needs_review', detections: review })
  }
  for (const cls of CLASSES) {
    const list = classGroups.get(cls)
    if (list) out.push({ label: classLabel(cls), kind: 'class', detections: list })
  }
  // Background pinned to the bottom: rejected stuff is the "done pile",
  // not the working queue.
  if (background.length) {
    out.push({ label: 'Background', kind: 'background', detections: background })
  }
  return out
})

// Flattened in the same order the grid renders, so keyboard navigation
// matches what the reviewer sees rather than the raw confidence sort.
const flatVisible = computed(() => groupedDetections.value.flatMap((g) => g.detections))

// Stripe by source image: same image → same tile background, image
// changes → flip. Restarts per group so each group's first cluster is
// always the same shade. Lets reviewers eyeball "two tiles from img0091
// in a row → possible duplicate".
const imageParityById = computed(() => {
  const map = new Map<number, 0 | 1>()
  for (const group of groupedDetections.value) {
    let parity: 0 | 1 = 0
    let lastImage: string | null = null
    for (const d of group.detections) {
      if (lastImage !== null && d.source_image_filename !== lastImage) {
        parity = parity === 0 ? 1 : 0
      }
      lastImage = d.source_image_filename
      map.set(d.id, parity)
    }
  }
  return map
})

const selected = computed(() => detections.value.find((d) => d.id === selectedId.value) ?? null)

// Only pick an initial selection when nothing is selected. We deliberately
// do not snap to list[0] when the current selection falls out of the
// filtered view (e.g. slider moved, bulk action, status change) — the
// reviewer keeps seeing the tile they were on instead of teleporting to a
// random low-id detection. The grid just won't show a highlight; clicking
// another tile takes over from there.
watch(
  filteredDetections,
  (list) => {
    if (!selectedId.value && list.length) {
      selectedId.value = list[0].id
    }
  },
  { immediate: true },
)

watch(selectedId, async (id) => {
  if (id == null) return
  await nextTick()
  const el = document.querySelector(`[data-detection-id="${id}"]`)
  el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
})

// Preloaded natural dimensions of the currently-selected source image.
// Needed so the SVG viewBox can match the bbox coords, which are in raw
// source-image pixels. Reset on URL change so a stale size never lingers.
const sourceImage = ref<{ w: number; h: number; url: string | null }>({
  w: 0,
  h: 0,
  url: null,
})

watch(
  () => selected.value?.source_image_url ?? null,
  (url) => {
    sourceImage.value = { w: 0, h: 0, url }
    if (!url) return
    const img = new Image()
    img.onload = () => {
      if (sourceImage.value.url === url) {
        sourceImage.value = {
          w: img.naturalWidth,
          h: img.naturalHeight,
          url,
        }
      }
    }
    img.src = url
  },
  { immediate: true },
)

// SVG strokes scale with the viewBox, so size the bbox outline relative to
// the source image rather than the screen. ~0.15% of the longest side
// renders as a hairline on a high-res photo without covering small insects.
const bboxStrokeWidth = computed(() => {
  const longest = Math.max(sourceImage.value.w, sourceImage.value.h)
  return Math.max(1, longest * 0.0015)
})

// The model's bbox sits tight against the insect, so drawing the outline
// right on it covers the edges. Expand the rectangle outward by ~8% of
// the longer bbox side so the line frames the insect with a small gap.
const bboxOutline = computed(() => {
  const b = selected.value?.bbox
  if (!b) return null
  const margin = Math.max(b.w, b.h) * 0.08
  return {
    x: b.x1 - margin,
    y: b.y1 - margin,
    width: b.w + 2 * margin,
    height: b.h + 2 * margin,
  }
})

const roiBbox = computed<[number, number, number, number] | null>(() => {
  const r = run.value?.config?.preprocessing?.roi_bbox
  return r && r.length === 4 ? r : null
})

// Fullscreen zoom modal. State lives in viewBox units; the SVG <g> is
// translated then scaled, so the wheel-around-cursor math has to convert
// the cursor's client coords into viewBox coords before applying.
const zoomDialog = ref<HTMLDialogElement | null>(null)
const zoom = ref({ scale: 1, tx: 0, ty: 0 })
const panning = ref(false)
const panStart = ref({ x: 0, y: 0, tx: 0, ty: 0 })

function openZoom() {
  if (!selected.value?.source_image_url || !sourceImage.value.w) return
  zoom.value = { scale: 1, tx: 0, ty: 0 }
  zoomDialog.value?.showModal()
}

function closeZoom() {
  zoomDialog.value?.close()
}

function onZoomClose() {
  panning.value = false
}

// Zoom toward the cursor: keep the source-image point under the cursor
// fixed while the scale changes. Done by adjusting the translate so the
// post-scale cursor location matches the pre-scale one.
function onZoomWheel(e: WheelEvent) {
  const target = e.currentTarget as HTMLElement
  const rect = target.getBoundingClientRect()
  // Cursor in viewBox coords: the SVG fills the container and uses
  // preserveAspectRatio=meet, so map via the longest fitted side.
  const sx = sourceImage.value.w
  const sy = sourceImage.value.h
  const fit = Math.min(rect.width / sx, rect.height / sy)
  const offX = (rect.width - sx * fit) / 2
  const offY = (rect.height - sy * fit) / 2
  const vx = (e.clientX - rect.left - offX) / fit
  const vy = (e.clientY - rect.top - offY) / fit

  const factor = e.deltaY < 0 ? 1.2 : 1 / 1.2
  const next = Math.max(1, Math.min(20, zoom.value.scale * factor))
  if (next === zoom.value.scale) return
  const k = next / zoom.value.scale
  zoom.value = {
    scale: next,
    tx: vx - k * (vx - zoom.value.tx),
    ty: vy - k * (vy - zoom.value.ty),
  }
}

function onPanStart(e: MouseEvent) {
  if (e.button !== 0) return
  panning.value = true
  panStart.value = {
    x: e.clientX,
    y: e.clientY,
    tx: zoom.value.tx,
    ty: zoom.value.ty,
  }
}

function onPanMove(e: MouseEvent) {
  if (!panning.value) return
  const target = e.currentTarget as HTMLElement
  const rect = target.getBoundingClientRect()
  const sx = sourceImage.value.w
  const sy = sourceImage.value.h
  const fit = Math.min(rect.width / sx, rect.height / sy)
  zoom.value = {
    ...zoom.value,
    tx: panStart.value.tx + (e.clientX - panStart.value.x) / fit,
    ty: panStart.value.ty + (e.clientY - panStart.value.y) / fit,
  }
}

function onPanEnd() {
  panning.value = false
}

function classColor(cls: string | null): string {
  if (!cls) return '#9aa3ab'
  return CLASS_COLORS[cls as ClassName] ?? '#9aa3ab'
}
function classBgFor(cls: string | null): string {
  const hex = classColor(cls)
  return hex + '14'
}
function classGlyph(cls: string | null): string {
  if (!cls) return '?'
  return CLASS_GLYPHS[cls as ClassName] ?? '?'
}
function classLabel(cls: string | null): string {
  if (!cls) return '—'
  return cls[0].toUpperCase() + cls.slice(1)
}
// Class shown on the grid card and used for grouping/coloring. Falls back
// to whichever branch produced the detection when only one is populated.
function primaryClass(d: Detection): ClassName | null {
  return d.yolo_class ?? d.insectnet_class ?? null
}
// Highest of the populated confidences. 0 when both are missing (shouldn't
// happen with valid data, defensive default).
function maxConfidence(d: Detection): number {
  return Math.max(d.yolo_confidence ?? 0, d.insectnet_confidence ?? 0)
}
// A detection needs reviewer eyes when the two detectors aren't unanimous:
// either they fired on different classes, or only one fired at all. The
// class group is reserved for detections both detectors agreed on.
function needsReview(d: Detection): boolean {
  if (hasDisagreement(d)) return true
  const yoloFired = !!d.yolo_class
  const insectnetFired = !!d.insectnet_class
  return yoloFired !== insectnetFired
}

function hasDisagreement(d: Detection): boolean {
  // Disagreement only meaningful when both branches contributed a class.
  return d.yolo_class != null && d.insectnet_class != null && d.yolo_class !== d.insectnet_class
}
function isLowConfidence(d: Detection): boolean {
  return maxConfidence(d) < LOW_CONFIDENCE_THRESHOLD
}
function reviewedFade(d: Detection): boolean {
  return (
    d.reviewer_status === 'confirmed' ||
    d.reviewer_status === 'corrected' ||
    d.reviewer_status === 'rejected'
  )
}
function statusBadgeClass(s: ReviewerStatus): string {
  switch (s) {
    case 'confirmed':
      return 'bg-green-100 text-green-700'
    case 'corrected':
      return 'bg-blue-100 text-blue-700'
    case 'rejected':
      return 'bg-red-100 text-red-700'
    case 'unsure':
      return 'bg-amber-100 text-amber-700'
    default:
      return 'bg-muted text-muted-foreground'
  }
}
function statusLabel(s: ReviewerStatus): string {
  return s[0].toUpperCase() + s.slice(1)
}
function suggestedClass(d: Detection): ClassName | null {
  if (d.yolo_class == null) return d.insectnet_class
  if (d.insectnet_class == null) return d.yolo_class
  return (d.insectnet_confidence ?? 0) >= (d.yolo_confidence ?? 0)
    ? d.insectnet_class
    : d.yolo_class
}

// The class to use for grouping a *reviewed* detection. Returns the
// reviewer's settled call (confirmed or corrected) so the row visibly
// moves into that class group. Returns null for rejected/unsure/
// unreviewed — those use the detector-state fallback in
// groupedDetections.
function settledClass(d: Detection): ClassName | null {
  if (d.reviewer_status === 'confirmed' || d.reviewer_status === 'corrected') {
    return effectiveLabel(d)
  }
  return null
}

function effectiveLabel(d: Detection): ClassName | null {
  // Rejected = background, which isn't one of the four class labels. Clear
  // any class hint so the Label panel doesn't end up with both Fly and
  // Background ticked when a previously-consensus-Fly is rejected.
  if (d.reviewer_status === 'rejected') return null
  if (d.reviewer_label) return d.reviewer_label
  // Consensus: both detectors fired with the same class.
  if (d.yolo_class != null && d.yolo_class === d.insectnet_class) return d.yolo_class
  // Single-detector hit: suggest the only class on offer. The detection
  // still lives in "Needs review" (no consensus), but Confirm can now act
  // on it directly instead of forcing the reviewer to tick the checkbox.
  if (d.yolo_class != null && d.insectnet_class == null) return d.yolo_class
  if (d.insectnet_class != null && d.yolo_class == null) return d.insectnet_class
  return null
}

async function patchDetection(
  id: number,
  status: ReviewerStatus,
  label: ClassName | null,
): Promise<boolean> {
  try {
    const res = await api(`/api/pollinator/detections/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify({
        reviewer_status: status,
        reviewer_label: label ?? '',
      }),
    })
    return res.ok
  } catch {
    return false
  }
}

async function postBulkReview(
  ids: number[],
  status: ReviewerStatus,
  label: ClassName | null,
): Promise<boolean> {
  try {
    const res = await api('/api/analysis/detections/bulk/', {
      method: 'POST',
      body: JSON.stringify({
        ids,
        reviewer_status: status,
        reviewer_label: label ?? '',
      }),
    })
    return res.ok
  } catch {
    return false
  }
}

function clearFailedSave(id: number) {
  if (!failedSaves.value.has(id)) return
  failedSaves.value.delete(id)
  failedSaves.value = new Map(failedSaves.value)
}

async function applyAction(status: ReviewerStatus, label: ClassName | null, advanceAfter = false) {
  if (!selected.value) return
  const d = selected.value
  // If a previous save for this detection already failed, keep its original
  // prev so Dismiss reverts all the way back, not to the last optimistic state.
  const existing = failedSaves.value.get(d.id)
  const prevStatus = existing ? existing.prevStatus : d.reviewer_status
  const prevLabel = existing ? existing.prevLabel : d.reviewer_label
  // Auto-advance is for keyboard review (1/2/3/4/x/u to fly through tiles).
  // Mouse clicks on the Label panel or footer buttons stay on the current
  // tile — the reviewer is clearly focused on this tile, and jumping
  // makes it look like the action saved to a different one. Captured BEFORE
  // mutating so the next-tile lookup runs against the current view.
  if (advanceAfter) {
    const nextId = nextVisibleId(d.id)
    if (nextId != null) selectedId.value = nextId
  }

  d.reviewer_status = status
  d.reviewer_label = label

  const ok = await patchDetection(d.id, status, label)
  if (!ok) {
    failedSaves.value.set(d.id, { status, label, prevStatus, prevLabel })
    failedSaves.value = new Map(failedSaves.value)
  } else {
    clearFailedSave(d.id)
  }
}

function toggleBulk(id: number) {
  bulkConfirmSkipped.value = 0
  const next = new Set(bulkIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  bulkIds.value = next
}

function clearBulk() {
  bulkIds.value = new Set()
  bulkCorrectClass.value = ''
  bulkConfirmSkipped.value = 0
}

function selectAllVisible() {
  bulkConfirmSkipped.value = 0
  bulkIds.value = new Set(filteredDetections.value.map((d) => d.id))
}

// Unreviewed detections that the confidence sliders are currently hiding.
// Restricted to 'unreviewed' so we never silently overwrite a reviewer's
// confirmed/corrected/unsure call when the slider moves. Shares the
// passesSliders predicate with filteredDetections so the two views can't
// drift.
const belowThresholdIds = computed<number[]>(() =>
  detections.value
    .filter((d) => d.reviewer_status === 'unreviewed' && !passesSliders(d))
    .map((d) => d.id),
)

async function rejectBelowThreshold() {
  if (rejectingBelow.value) return
  const ids = belowThresholdIds.value
  if (!ids.length) return
  rejectingBelow.value = true
  const snapshot = new Map<number, ReviewerStatus>()
  for (const d of detections.value) {
    if (belowThresholdIds.value.includes(d.id)) {
      snapshot.set(d.id, d.reviewer_status)
      d.reviewer_status = 'rejected'
      d.reviewer_label = null
    }
  }
  try {
    const ok = await postBulkReview(ids, 'rejected', null)
    if (!ok) {
      for (const id of ids) {
        const prev = snapshot.get(id)!
        failedSaves.value.set(id, {
          status: 'rejected',
          label: null,
          prevStatus: prev,
          prevLabel: null,
        })
      }
      failedSaves.value = new Map(failedSaves.value)
    }
  } finally {
    rejectingBelow.value = false
  }
}

async function submitBulk(ids: number[], status: ReviewerStatus, label: ClassName | null) {
  if (!ids.length) return
  const idSet = new Set(ids)
  const snapshot = new Map<number, { status: ReviewerStatus; label: ClassName | null }>()
  for (const d of detections.value) {
    if (idSet.has(d.id)) {
      const existing = failedSaves.value.get(d.id)
      snapshot.set(d.id, {
        status: existing ? existing.prevStatus : d.reviewer_status,
        label: existing ? existing.prevLabel : d.reviewer_label,
      })
      d.reviewer_status = status
      d.reviewer_label = label
    }
  }

  const ok = await postBulkReview(ids, status, label)
  if (!ok) {
    for (const id of ids) {
      const prev = snapshot.get(id)!
      failedSaves.value.set(id, {
        status,
        label,
        prevStatus: prev.status,
        prevLabel: prev.label,
      })
    }
    failedSaves.value = new Map(failedSaves.value)
  } else {
    let changed = false
    for (const id of ids) {
      if (failedSaves.value.delete(id)) changed = true
    }
    if (changed) failedSaves.value = new Map(failedSaves.value)
  }
}

async function applyToBulk(status: ReviewerStatus, label: ClassName | null) {
  const ids = [...bulkIds.value]
  clearBulk()
  await submitBulk(ids, status, label)
}

async function retryFailedSaves() {
  if (retrying.value || failedSaves.value.size === 0) return
  retrying.value = true
  try {
    // Group by intended (status, label) so we can retry as bulk requests.
    const groups = new Map<
      string,
      { status: ReviewerStatus; label: ClassName | null; ids: number[] }
    >()
    for (const [id, entry] of failedSaves.value) {
      const key = `${entry.status}::${entry.label ?? ''}`
      if (!groups.has(key)) {
        groups.set(key, { status: entry.status, label: entry.label, ids: [] })
      }
      groups.get(key)!.ids.push(id)
    }
    let changed = false
    for (const { status, label, ids } of groups.values()) {
      const ok = await postBulkReview(ids, status, label)
      if (ok) {
        for (const id of ids) failedSaves.value.delete(id)
        changed = true
      }
    }
    if (changed) failedSaves.value = new Map(failedSaves.value)
  } finally {
    retrying.value = false
  }
}

function dismissFailedSaves() {
  for (const [id, entry] of failedSaves.value) {
    const d = detections.value.find((x) => x.id === id)
    if (d) {
      d.reviewer_status = entry.prevStatus
      d.reviewer_label = entry.prevLabel
    }
  }
  failedSaves.value = new Map()
}

// Bulk-confirming the raw selection used to send ('confirmed', null) for every
// row, which clears reviewer_label server-side. Rows where the group classifier
// fell below threshold at inference land with predicted_class='' too, and the
// training-pool gate (reviewer_label or predicted_class in canonical classes)
// then drops them silently. Partition by effective label and send each bucket
// as 'corrected' so reviewer_label is always populated. Rows with no derivable
// class are skipped and surfaced to the reviewer.
async function bulkConfirm() {
  const buckets = new Map<ClassName, number[]>()
  let skipped = 0
  for (const d of detections.value) {
    if (!bulkIds.value.has(d.id)) continue
    const lbl = effectiveLabel(d)
    if (lbl == null) {
      skipped++
      continue
    }
    if (!buckets.has(lbl)) buckets.set(lbl, [])
    buckets.get(lbl)!.push(d.id)
  }
  bulkConfirmSkipped.value = skipped
  clearBulk()
  for (const [label, ids] of buckets) {
    await submitBulk(ids, 'corrected', label)
  }
}

function bulkReject() {
  applyToBulk('rejected', null)
}

function onBulkCorrectChange() {
  if (bulkCorrectClass.value === '') return
  applyToBulk('corrected', bulkCorrectClass.value)
}

// Confirmed only when both models agreed and the user picked that class.
// When models disagree there's no single prediction to confirm, so any pick
// is a correction (and the label is preserved server-side).
function confirmAs(cls: ClassName | null, advanceAfter = false) {
  if (!selected.value || cls == null) return
  const d = selected.value
  const consensus = d.yolo_class != null && d.yolo_class === d.insectnet_class ? d.yolo_class : null
  if (consensus === cls) applyAction('confirmed', null, advanceAfter)
  else applyAction('corrected', cls, advanceAfter)
}
function reject(advanceAfter = false) {
  applyAction('rejected', null, advanceAfter)
}
function markUnsure(advanceAfter = false) {
  applyAction('unsure', null, advanceAfter)
}

function nextVisibleId(currentId: number): number | null {
  const list = flatVisible.value
  const idx = list.findIndex((d) => d.id === currentId)
  if (idx < 0) return null
  // Forward if possible; otherwise fall back to the previous tile so a
  // reject on the last visible item doesn't snap selection to list[0].
  if (idx + 1 < list.length) return list[idx + 1].id
  if (idx > 0) return list[idx - 1].id
  return null
}

// Grid is 5 columns. Down/Up jump a row, Left/Right step one tile.
const GRID_COLS = 5

// Anchor for range selection. Set by every plain click and by every
// non-extending keyboard navigation. Shift+arrow / shift+click define the
// range anchor->current; backtracking shrinks rather than accumulating.
const anchorId = ref<number | null>(null)
// Bulk ids that pre-date the current shift gesture. The active shift range
// gets layered on top so backtracking through it doesn't erase manual picks.
const stableBulkIds = ref<Set<number>>(new Set())

function setShiftRange(fromIdx: number, toIdx: number) {
  const list = flatVisible.value
  const [lo, hi] = fromIdx <= toIdx ? [fromIdx, toIdx] : [toIdx, fromIdx]
  const next = new Set(stableBulkIds.value)
  for (let i = lo; i <= hi; i++) next.add(list[i].id)
  bulkIds.value = next
}

function navigate(delta: number, extend: boolean) {
  const list = flatVisible.value
  const idx = list.findIndex((d) => d.id === selectedId.value)
  if (idx < 0) return
  const newIdx = Math.max(0, Math.min(list.length - 1, idx + delta))
  if (newIdx === idx) return
  selectedId.value = list[newIdx].id
  if (extend) {
    // First key in a shift gesture: snapshot the current bulk so the range
    // we're about to paint on top can be backtracked without erasing it.
    if (anchorId.value == null) {
      anchorId.value = list[idx].id
      stableBulkIds.value = new Set(bulkIds.value)
    }
    const anchorIdx = list.findIndex((d) => d.id === anchorId.value)
    setShiftRange(anchorIdx >= 0 ? anchorIdx : idx, newIdx)
  } else {
    anchorId.value = list[newIdx].id
    stableBulkIds.value = new Set(bulkIds.value)
  }
}

function onTileClick(d: Detection, e: MouseEvent | KeyboardEvent) {
  if (e.shiftKey && anchorId.value != null) {
    const list = flatVisible.value
    const ai = list.findIndex((x) => x.id === anchorId.value)
    const ci = list.findIndex((x) => x.id === d.id)
    if (ai >= 0 && ci >= 0) setShiftRange(ai, ci)
    selectedId.value = d.id
    return
  }
  selectedId.value = d.id
  anchorId.value = d.id
  stableBulkIds.value = new Set(bulkIds.value)
}

function onKeydown(e: KeyboardEvent) {
  if (!selected.value) return
  if (zoomDialog.value?.open) return
  if (
    e.target instanceof HTMLElement &&
    ['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)
  ) {
    return
  }
  // Escape clears any bulk selection without losing the currently-focused tile.
  if (e.key === 'Escape' && bulkIds.value.size > 0) {
    clearBulk()
    e.preventDefault()
    return
  }
  // Bulk-aware shortcuts: when one or more tiles are checkbox-selected,
  // class keys (1-4), reject (x) and unsure (u) apply to the whole bulk
  // instead of just the focused tile. Lets the reviewer do "select 30
  // crops, press x" without reaching for the bulk action bar.
  const bulkMode = bulkIds.value.size > 0
  // Keyboard actions auto-advance to the next tile so the reviewer can
  // fly through a queue without touching the mouse. Mouse-driven actions
  // (Label panel clicks, footer buttons) stay put — see applyAction.
  const classKeyAction = (cls: ClassName) =>
    bulkMode ? applyToBulk('corrected', cls) : confirmAs(cls, true)
  switch (e.key) {
    case '1':
      classKeyAction('fly')
      e.preventDefault()
      break
    case '2':
      classKeyAction('bumblebee')
      e.preventDefault()
      break
    case '3':
      classKeyAction('butterfly')
      e.preventDefault()
      break
    case '4':
      classKeyAction('other')
      e.preventDefault()
      break
    case 'x':
    case 'X':
      if (bulkMode) applyToBulk('rejected', null)
      else reject(true)
      e.preventDefault()
      break
    case 'u':
    case 'U':
      if (bulkMode) applyToBulk('unsure', null)
      else markUnsure(true)
      e.preventDefault()
      break
    case 'Enter':
      confirmAs(suggestedClass(selected.value), true)
      e.preventDefault()
      break
    case 'ArrowDown':
    case 'j':
      navigate(GRID_COLS, e.shiftKey)
      e.preventDefault()
      break
    case 'ArrowUp':
    case 'k':
      navigate(-GRID_COLS, e.shiftKey)
      e.preventDefault()
      break
    case 'ArrowRight':
    case 'l':
      navigate(1, e.shiftKey)
      e.preventDefault()
      break
    case 'ArrowLeft':
    case 'h':
      navigate(-1, e.shiftKey)
      e.preventDefault()
      break
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>
