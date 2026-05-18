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
      <!-- Left: filters + grouped grid. Width controlled by --left-width
           at lg+ so the divider drag can update it via a single CSS var.
           @container lets children query *this section's* width (not the
           viewport) so the crops grid and filter row reflow as the
           reviewer drags the divider. Mobile keeps the full-width stacked
           layout. -->
      <section
        :style="{ '--left-width': leftWidth + 'px' }"
        class="@container w-full lg:w-[var(--left-width)] shrink-0 border-t lg:border-t-0 lg:border-r border-border flex flex-col bg-surface max-h-[55vh] lg:max-h-none"
      >
        <div class="px-4 py-3 border-b border-border space-y-2">
          <!-- Filter row: stacks vertically below 340px and runs side by
               side from 340px upward. Side-by-side needs ~290px just for
               the two label+select pairs plus the gap; below that the
               Class group runs off the edge. Show goes on top when
               stacked so the most-used control stays reachable first. -->
          <div class="flex flex-col @[340px]:flex-row @[340px]:items-center gap-2 text-xs">
            <div class="flex items-center gap-2">
              <label class="text-muted-foreground">Show</label>
              <select
                v-model="statusFilter"
                class="flex-1 px-2 py-1 rounded border border-border bg-background"
              >
                <option value="pending">Pending</option>
                <option value="reviewed">Reviewed</option>
                <option value="unsure">Unsure</option>
                <option value="all">All</option>
              </select>
            </div>
            <div class="flex items-center gap-2">
              <label class="text-muted-foreground">Class</label>
              <select
                v-model="classFilter"
                class="flex-1 px-2 py-1 rounded border border-border bg-background"
              >
                <option value="all">All</option>
                <option v-for="cls in CLASSES" :key="cls" :value="cls">
                  {{ classLabel(cls) }}
                </option>
                <option value="background">Background</option>
              </select>
            </div>
          </div>
          <!-- Per-branch min-confidence sliders. Letting the reviewer tune
             YOLO and the crop classifier independently mirrors how those
             stages are configured at upload time. Detections with no
             score in a branch (e.g. preprocessing-only crops lack a YOLO
             score) pass that branch's filter unaffected, so the slider
             only hides things its branch actually scored. -->
          <div class="grid grid-cols-[auto_1fr_auto] items-center gap-x-2 gap-y-1 text-xs">
            <label for="yolo-min" class="text-muted-foreground">YOLO ≥</label>
            <input
              id="yolo-min"
              type="range"
              min="0"
              max="1"
              step="0.05"
              v-model.number="yoloMinConf"
              class="w-full accent-primary"
            />
            <span class="font-mono w-10 text-right">{{ yoloMinConf.toFixed(2) }}</span>
            <label for="insectnet-min" class="text-muted-foreground">InsectNet ≥</label>
            <input
              id="insectnet-min"
              type="range"
              min="0"
              max="1"
              step="0.05"
              v-model.number="insectnetMinConf"
              class="w-full accent-primary"
            />
            <span class="font-mono w-10 text-right">{{ insectnetMinConf.toFixed(2) }}</span>
          </div>
          <!-- Search + below-threshold toggle. Same row when the section
               is wide enough; stacks when not (search on top, button
               underneath). Search runs after 3 characters so single-key
               typing doesn't trigger noisy re-filters. -->
          <div class="flex flex-col gap-2 text-xs @[340px]:flex-row @[340px]:items-center">
            <input
              type="text"
              v-model.trim="searchQuery"
              placeholder="Search image (3+ chars)"
              class="flex-1 min-w-0 px-2 py-1 rounded border border-border bg-background"
            />
            <button
              v-if="!viewBelowOnly && belowThresholdIds.length"
              class="shrink-0 px-2 py-1 rounded border border-border text-foreground hover:bg-muted"
              @click="viewBelowOnly = true"
            >
              View {{ belowThresholdIds.length }} below threshold
            </button>
            <button
              v-else-if="viewBelowOnly"
              class="shrink-0 px-2 py-1 rounded border border-primary text-primary hover:bg-primary/10"
              @click="viewBelowOnly = false"
            >
              ← Back to normal view
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
            <!-- Column count scales with the section's own width via
                 container queries. Crops stay roughly square at every
                 breakpoint so the grid feels consistent as the divider
                 moves. -->
            <div
              class="grid grid-cols-3 @[260px]:grid-cols-4 @[340px]:grid-cols-5 @[440px]:grid-cols-6 @[560px]:grid-cols-7 gap-1 p-2"
            >
              <div
                v-for="d in group.detections"
                :key="d.id"
                class="rounded-md overflow-hidden border-2 transition-all"
                :class="[
                  isHighlighted(d.id)
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

      <!-- Drag-resizable divider, lg+ only. 1px visible line in a 4px hit
           area so the cursor doesn't have to be pixel-perfect. -->
      <div
        class="hidden lg:flex w-1 shrink-0 cursor-col-resize group items-stretch"
        role="separator"
        aria-orientation="vertical"
        @mousedown="onResizerMouseDown"
      >
        <div class="w-px h-full bg-border group-hover:bg-primary mx-auto" />
      </div>

      <!-- Right: preview pane (mirrors left's structural feel: thin top
           bar, scroll body, action bar at bottom). @container so the
           Label/Predictions row can adapt to *this pane's* width as the
           divider moves. -->
      <section class="@container flex-1 flex flex-col min-w-0">
        <div v-if="!selected" class="m-auto text-sm text-muted-foreground">
          Select a detection on the left to review it.
        </div>
        <template v-else>
          <!-- Top bar. Filename is the primary identifier here — the
               internal Detection #id was a debug crutch that ate
               horizontal space without telling the reviewer anything they
               needed. -->
          <header class="px-5 py-1.5 border-b border-border bg-surface flex items-center gap-3">
            <span class="font-medium font-mono text-sm truncate">
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
          <div class="flex-1 flex flex-col min-h-0">
            <!-- Source image with bbox overlay. Click to open the zoom modal.
               flex-1 + min-h-0 makes it fill whatever vertical space is left
               after the predictions/label/footer, instead of locking to a
               16:9 box that forced the right pane to scroll. -->
            <div
              class="flex-1 min-h-0 relative overflow-hidden"
              :style="{ backgroundColor: classBgFor(primaryClass(selected)) }"
              :class="selected.source_image_url && sourceImage.w ? 'cursor-crosshair' : ''"
              @mousedown="onPreviewMouseDown"
            >
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
                <!-- Red = single-selected (no bulk) OR in the current
                   drag-selected bulk. Gray = unreviewed sibling, available
                   to click or drag over. Bulk takes priority over single
                   selection so a stale auto-selected tile doesn't keep
                   its red bbox after a drag-select picks elsewhere. -->
                <rect
                  v-for="ov in siblingOverlays"
                  :key="ov.id"
                  :x="ov.outline.x"
                  :y="ov.outline.y"
                  :width="ov.outline.width"
                  :height="ov.outline.height"
                  :fill="isHighlighted(ov.id) ? '#ef4444' : 'transparent'"
                  :fill-opacity="isHighlighted(ov.id) ? 0.18 : 0"
                  :stroke="isHighlighted(ov.id) ? '#ef4444' : '#52525b'"
                  :stroke-width="bboxStrokeWidth"
                  class="cursor-pointer"
                  @mousedown.stop
                  @click="onSiblingBboxClick(ov, $event)"
                />
                <!-- Drag-select rectangle. pointer-events-none so it can't
                   intercept mousemove from the window listener. -->
                <rect
                  v-if="dragRect"
                  :x="dragRect.x1"
                  :y="dragRect.y1"
                  :width="dragRect.x2 - dragRect.x1"
                  :height="dragRect.y2 - dragRect.y1"
                  fill="#3b82f6"
                  fill-opacity="0.15"
                  stroke="#3b82f6"
                  :stroke-width="bboxStrokeWidth"
                  stroke-dasharray="8 4"
                  class="pointer-events-none"
                />
                <ROIOverlay :bbox="roiBbox" :image-w="sourceImage.w" :image-h="sourceImage.h" />
              </svg>
              <span
                v-else
                class="absolute inset-0 flex items-center justify-center text-7xl font-bold opacity-30"
                >{{ classGlyph(primaryClass(selected)) }}</span
              >
              <!-- Explicit zoom button. The whole tile is still click-to-
                 zoom but the bbox overlays now eat most of the surface, so
                 an unambiguous button avoids the "I tried to zoom but
                 selected a sibling instead" miss. -->
              <button
                v-if="selected.source_image_url && sourceImage.w"
                @mousedown.stop
                @click.stop="openZoom"
                title="Zoom in"
                class="absolute bottom-3 right-3 z-10 p-2 rounded-md bg-black/55 text-white hover:bg-black/75 cursor-pointer"
              >
                <ZoomIn class="w-4 h-4" />
              </button>
            </div>

            <!-- Label + Predictions row. Column count tracks the pane's
                 own width via container queries:
                   < 500px  stack vertically (1 col)
                   500-700  side by side (2 cols, fills the row)
                   700-1000 2 panels + 1 empty col on the right
                   1000+    2 panels + 2 empty cols on the right
                 Empty cols come from grid auto-flow (no explicit divs).
                 Label is first in DOM so the stacked view shows it on
                 top — text-size and padding still scale with the
                 viewport via xl: since legibility is about pixel size
                 on the user's screen, not container width. -->
            <div
              class="grid grid-cols-1 @[500px]:grid-cols-2 @[700px]:grid-cols-3 @[1000px]:grid-cols-4 border-b border-border"
            >
              <!-- Label first (one row per class with radio at end). -->
              <div class="px-5 py-2 border-b border-border @[500px]:border-b-0 @[500px]:border-r">
                <div
                  class="text-[10px] xl:text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-0.5"
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
                    class="flex items-center gap-2 py-0 xl:py-0.5 px-2 -mx-2 rounded cursor-pointer"
                  >
                    <span
                      class="w-2 h-2 rounded-full shrink-0"
                      :style="{ backgroundColor: classColor(cls) }"
                    />
                    <span class="flex-1 text-xs xl:text-sm">{{ classLabel(cls) }}</span>
                    <input
                      type="radio"
                      name="label-class"
                      :checked="cls === effectiveLabel(selected)"
                      @change="confirmAs(cls)"
                      class="w-3.5 h-3.5 xl:w-4 xl:h-4"
                    />
                  </label>
                  <!-- 5th option: rejecting means "this is background" — the
                     binary classifier trains rejected detections as the
                     'background' class. Treating it as a label keeps the
                     Label panel as a single source of truth for what the
                     reviewer decided. -->
                  <label
                    class="flex items-center gap-2 py-0 xl:py-0.5 px-2 -mx-2 rounded cursor-pointer"
                  >
                    <span class="w-2 h-2 rounded-full shrink-0 bg-muted-foreground/40" />
                    <span class="flex-1 text-xs xl:text-sm">
                      Background
                      <span class="text-[10px] xl:text-[11px] text-muted-foreground ml-1"
                        >(reject)</span
                      >
                    </span>
                    <input
                      type="radio"
                      name="label-class"
                      :checked="selected.reviewer_status === 'rejected'"
                      @change="reject()"
                      class="w-3.5 h-3.5 xl:w-4 xl:h-4"
                    />
                  </label>
                </div>
              </div>

              <!-- Predictions (compact, two-line). -->
              <div class="px-5 py-2">
                <div
                  class="text-[10px] xl:text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-0.5"
                >
                  Predictions
                </div>
                <div class="space-y-0.5 text-xs xl:text-sm">
                  <div
                    class="flex items-center gap-2"
                    :class="selected.yolo_class == null ? 'opacity-60' : ''"
                  >
                    <span class="text-muted-foreground w-16 xl:w-20">YOLO</span>
                    <span
                      class="w-2 h-2 rounded-full shrink-0"
                      :style="{ backgroundColor: classColor(selected.yolo_class) }"
                    />
                    <span class="font-medium flex-1">{{
                      selected.yolo_class ? classLabel(selected.yolo_class) : '—'
                    }}</span>
                    <span class="font-mono text-muted-foreground">
                      {{
                        selected.yolo_confidence != null ? selected.yolo_confidence.toFixed(2) : '—'
                      }}
                    </span>
                  </div>
                  <div
                    class="flex items-center gap-2"
                    :class="selected.insectnet_class == null ? 'opacity-60' : ''"
                  >
                    <span class="text-muted-foreground w-16 xl:w-20">InsectNet</span>
                    <span
                      class="w-2 h-2 rounded-full shrink-0"
                      :style="{ backgroundColor: classColor(selected.insectnet_class) }"
                    />
                    <span class="font-medium flex-1">{{
                      selected.insectnet_class ? classLabel(selected.insectnet_class) : '—'
                    }}</span>
                    <span class="font-mono text-muted-foreground">
                      {{
                        selected.insectnet_confidence != null
                          ? selected.insectnet_confidence.toFixed(2)
                          : '—'
                      }}
                    </span>
                  </div>
                  <div v-if="hasDisagreement(selected)" class="text-amber-700">
                    ⚠ Models disagree
                  </div>
                  <div v-else-if="isLowConfidence(selected)" class="text-amber-700">
                    ⚠ Low confidence
                  </div>
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
          <image :href="selected.source_image_url" :width="sourceImage.w" :height="sourceImage.h" />
          <rect
            v-for="ov in siblingOverlays"
            :key="ov.id"
            :x="ov.outline.x"
            :y="ov.outline.y"
            :width="ov.outline.width"
            :height="ov.outline.height"
            fill="none"
            :stroke="isHighlighted(ov.id) ? '#ef4444' : '#a1a1aa'"
            :stroke-width="bboxStrokeWidth"
            vector-effect="non-scaling-stroke"
            class="cursor-pointer"
            @click="onSiblingBboxClick(ov, $event)"
            @mousedown="isHighlighted(ov.id) || $event.stopPropagation()"
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
import { ZoomIn } from 'lucide-vue-next'
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
      yolo?: { confidence?: number }
      binary_classifier?: { confidence?: number }
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
// Per-branch confidence sliders. Seeded from the run's own config in
// loadFromApi so the review view starts in the same regime the run was
// actually created with — whatever the reviewer set on the upload page
// is what they see here, not a hard-coded default. The literals here
// are just a placeholder before the run loads. Detections with no score
// in a branch pass that branch's filter so preprocessing-only crops
// aren't dropped by the YOLO slider, etc.
const yoloMinConf = ref(0)
const insectnetMinConf = ref(0)

function passesSliders(d: Detection): boolean {
  const yoloOk = d.yolo_confidence == null || d.yolo_confidence >= yoloMinConf.value
  const insectnetOk =
    d.insectnet_confidence == null || d.insectnet_confidence >= insectnetMinConf.value
  return yoloOk && insectnetOk
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
// When true, the grid inverts the slider filter and shows ONLY the
// unreviewed rows the sliders would otherwise hide, so the reviewer can
// step through them one by one and confirm/reject individually instead
// of bulk-rejecting blindly.
const viewBelowOnly = ref(false)
// Free-text substring filter on source image filename. Held in the
// review page (not query-string) since reviewers tend to clear it as
// they jump between tiles. Substring match (case-insensitive) so
// typing "011" finds "WSCT0011.JPG". Min length keeps the filter from
// firing on single-key noise; below the floor it does nothing.
const searchQuery = ref('')
const SEARCH_MIN_LEN = 3

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
    // Seed the confidence sliders from the run's own config so the
    // review view starts at the same thresholds the upload page picked.
    // Falls back to 0 ("no filter") if the run was created without an
    // explicit threshold for that branch.
    yoloMinConf.value = run.value?.config?.yolo?.confidence ?? 0
    insectnetMinConf.value = run.value?.config?.binary_classifier?.confidence ?? 0
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
  // Image-name search. Only kicks in past the min length so a single key
  // doesn't whip the grid through every partial match. Case-insensitive
  // substring so "011" matches "WSCT0011.JPG" anywhere in the filename.
  if (searchQuery.value.length >= SEARCH_MIN_LEN) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter((d) => d.source_image_filename.toLowerCase().includes(q))
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
  // Slider filter, or its inverse for the "View below threshold" mode:
  // unreviewed-only rows that the sliders are currently hiding.
  if (viewBelowOnly.value) {
    list = list.filter((d) => d.reviewer_status === 'unreviewed' && !passesSliders(d))
  } else {
    list = list.filter(passesSliders)
  }
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
    classFilter.value !== 'all' && classFilter.value !== 'background' ? classFilter.value : null
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
// the source image rather than the screen. ~0.3% of the longest side reads
// clearly when the preview is shrunk down to fit the pane, while still
// staying out of the way of small insects. Zoom uses non-scaling-stroke
// (template-side) so it stays a hairline regardless of this value.
const bboxStrokeWidth = computed(() => {
  const longest = Math.max(sourceImage.value.w, sourceImage.value.h)
  return Math.max(2, longest * 0.003)
})

// The model's bbox sits tight against the insect, so drawing the outline
// right on it covers the edges. Expand the rectangle outward by ~8% of
// the longer bbox side so the line frames the insect with a small gap.
function outlineFor(d: Detection | null): {
  x: number
  y: number
  width: number
  height: number
} | null {
  const b = d?.bbox
  if (!b) return null
  const margin = Math.max(b.w, b.h) * 0.08
  return {
    x: b.x1 - margin,
    y: b.y1 - margin,
    width: b.w + 2 * margin,
    height: b.h + 2 * margin,
  }
}

// Every detection that shares the selected detection's source image,
// painted on the preview as bbox overlays. The selected one renders red;
// siblings render dark-gray and are clickable to switch selection. Selected
// goes last so it stacks on top of any overlapping siblings. Useful for
// spotting clusters (multiple insects in the same photo) without having
// to flip through tiles.
interface SiblingOverlay {
  id: number
  outline: { x: number; y: number; width: number; height: number }
  isSelected: boolean
}
// Click on a sibling bbox in the preview SVG → switch selection. Stops
// propagation so it doesn't trigger drag-select on the outer container.
function onSiblingBboxClick(ov: SiblingOverlay, e: MouseEvent) {
  e.stopPropagation()
  selectedId.value = ov.id
}

// Single source of truth for "this detection looks selected". When a drag
// bulk is active it takes priority: only bulk members read as selected,
// so a stale single-selection (the auto-selected preview tile) doesn't
// keep its red bbox / green grid ring after the reviewer drags a new
// region that doesn't include it. When no bulk is active, fall back to
// the normal single-selection (selectedId).
function isHighlighted(id: number): boolean {
  if (bulkIds.value.size > 0) return bulkIds.value.has(id)
  return selectedId.value === id
}

const siblingOverlays = computed<SiblingOverlay[]>(() => {
  const sel = selected.value
  if (!sel) return []
  const filename = sel.source_image_filename
  const peers = filename
    ? detections.value.filter((d) => d.source_image_filename === filename)
    : [sel]
  const out: SiblingOverlay[] = []
  for (const d of peers) {
    // Overlays are a working aid — they highlight detections the reviewer
    // still needs to act on. Once a detection has been confirmed,
    // corrected, rejected, or marked unsure, drop its bbox so the image
    // doesn't stay cluttered with boxes that have already been handled.
    // Exception: the currently selected detection always gets its
    // overlay, even when reviewed, so a reviewer browsing the Reviewed
    // pile can still see where on the image the selected crop sits.
    if (d.id !== sel.id && d.reviewer_status !== 'unreviewed') continue
    const outline = outlineFor(d)
    if (!outline) continue
    out.push({ id: d.id, outline, isSelected: d.id === sel.id })
  }
  out.sort((a, b) => (a.isSelected ? 1 : 0) - (b.isSelected ? 1 : 0))
  return out
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

// Width of the left (crops) section in pixels at lg+. Persisted so each
// reviewer's choice survives reloads. The bounds keep the layout sane —
// below the min the filter row stops fitting in one line, above the max
// the preview pane gets squashed.
const LEFT_WIDTH_KEY = 'review:left-width'
const LEFT_WIDTH_DEFAULT = 300
const LEFT_WIDTH_MIN = 220
const LEFT_WIDTH_MAX = 700
const leftWidth = ref<number>(
  (() => {
    if (typeof localStorage === 'undefined') return LEFT_WIDTH_DEFAULT
    const stored = Number(localStorage.getItem(LEFT_WIDTH_KEY))
    if (!Number.isFinite(stored) || stored < LEFT_WIDTH_MIN || stored > LEFT_WIDTH_MAX) {
      return LEFT_WIDTH_DEFAULT
    }
    return stored
  })(),
)
watch(leftWidth, (w) => {
  try {
    localStorage.setItem(LEFT_WIDTH_KEY, String(w))
  } catch {
    // localStorage may be unavailable (private mode); ignore.
  }
})

let resizeStartX = 0
let resizeStartWidth = 0

function onResizerMouseDown(e: MouseEvent) {
  if (e.button !== 0) return
  e.preventDefault()
  resizeStartX = e.clientX
  resizeStartWidth = leftWidth.value
  window.addEventListener('mousemove', onResizerMove)
  window.addEventListener('mouseup', onResizerUp)
  // Lock cursor and kill text-selection while dragging so the mouse looks
  // right wherever it travels and a sloppy drag doesn't highlight prose.
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

function onResizerMove(e: MouseEvent) {
  const delta = e.clientX - resizeStartX
  const next = resizeStartWidth + delta
  leftWidth.value = Math.max(LEFT_WIDTH_MIN, Math.min(LEFT_WIDTH_MAX, next))
}

function onResizerUp() {
  window.removeEventListener('mousemove', onResizerMove)
  window.removeEventListener('mouseup', onResizerUp)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

// Drag-to-select on the static preview image: drag a rectangle to add all
// unreviewed sibling detections whose bboxes intersect it to bulkIds. The
// existing bulk action bar then takes over for the actual review action.
// Coordinates live in source-image pixels (same space as detection bboxes)
// so the intersection test is a straight number comparison.
const dragRect = ref<{ x1: number; y1: number; x2: number; y2: number } | null>(null)
let dragStartImg: { x: number; y: number } | null = null
let dragContainerRect: DOMRect | null = null

function clientToImageXY(e: MouseEvent, contRect: DOMRect) {
  const sx = sourceImage.value.w
  const sy = sourceImage.value.h
  if (!sx || !sy) return { x: 0, y: 0 }
  const fit = Math.min(contRect.width / sx, contRect.height / sy)
  const offX = (contRect.width - sx * fit) / 2
  const offY = (contRect.height - sy * fit) / 2
  return {
    x: Math.max(0, Math.min(sx, (e.clientX - contRect.left - offX) / fit)),
    y: Math.max(0, Math.min(sy, (e.clientY - contRect.top - offY) / fit)),
  }
}

// Detections in the current source image that the drag rect intersects.
// Filename guard avoids accidentally selecting same-bbox detections from
// other photos (we're looking at one image at a time on the preview).
function dragHits(r: { x1: number; y1: number; x2: number; y2: number }): number[] {
  const filename = selected.value?.source_image_filename
  if (!filename) return []
  const out: number[] = []
  for (const d of detections.value) {
    if (d.source_image_filename !== filename) continue
    if (d.reviewer_status !== 'unreviewed') continue
    const b = d.bbox
    if (!b) continue
    if (b.x1 < r.x2 && b.x2 > r.x1 && b.y1 < r.y2 && b.y2 > r.y1) out.push(d.id)
  }
  return out
}

function onPreviewMouseDown(e: MouseEvent) {
  if (e.button !== 0) return
  if (!selected.value || !sourceImage.value.w) return
  const cont = e.currentTarget as HTMLElement
  dragContainerRect = cont.getBoundingClientRect()
  dragStartImg = clientToImageXY(e, dragContainerRect)
  dragRect.value = {
    x1: dragStartImg.x,
    y1: dragStartImg.y,
    x2: dragStartImg.x,
    y2: dragStartImg.y,
  }
  // A new drag = a fresh selection. Clearing here is what gives the
  // "previous selection gone, new batch starts" feel the reviewer expects.
  bulkIds.value = new Set()
  bulkConfirmSkipped.value = 0
  window.addEventListener('mousemove', onPreviewDragMove)
  window.addEventListener('mouseup', onPreviewDragEnd)
}

function onPreviewDragMove(e: MouseEvent) {
  if (!dragStartImg || !dragContainerRect) return
  const p = clientToImageXY(e, dragContainerRect)
  const r = {
    x1: Math.min(dragStartImg.x, p.x),
    y1: Math.min(dragStartImg.y, p.y),
    x2: Math.max(dragStartImg.x, p.x),
    y2: Math.max(dragStartImg.y, p.y),
  }
  dragRect.value = r
  // Live update so bboxes turn red the instant the rect covers them, and
  // turn back gray if the user pulls the rect off them. The set is rebuilt
  // each frame so backtracking shrinks the selection.
  bulkIds.value = new Set(dragHits(r))
}

function onPreviewDragEnd() {
  window.removeEventListener('mousemove', onPreviewDragMove)
  window.removeEventListener('mouseup', onPreviewDragEnd)
  dragStartImg = null
  dragContainerRect = null
  dragRect.value = null
  // bulkIds is already correct from the last mousemove. Nothing to do.
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

// When the reviewer is in view-below mode and processes the last entry,
// the special view is empty and meaningless — drop back to the normal
// filter so they're not staring at a blank grid.
watch([belowThresholdIds, viewBelowOnly], ([ids, on]) => {
  if (on && ids.length === 0) viewBelowOnly.value = false
})

async function submitBulk(ids: number[], status: ReviewerStatus, label: ClassName | null) {
async function submitBulk(ids: number[], status: ReviewerStatus, label: ClassName | null) {
  if (!ids.length) return
  const idSet = new Set(ids)
  const snapshot = new Map<number, { status: ReviewerStatus; label: ClassName | null }>()
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

// Crops grid column count follows the container-query thresholds in the
// template, so Down/Up keyboard nav matches the actual visual rows. Below
// the lg breakpoint (stacked mobile layout) the section is full-width;
// default to 5 there.
const GRID_COLS = computed(() => {
  const w = leftWidth.value
  if (w >= 560) return 7
  if (w >= 440) return 6
  if (w >= 340) return 5
  if (w >= 260) return 4
  return 3
})

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
      navigate(GRID_COLS.value, e.shiftKey)
      e.preventDefault()
      break
    case 'ArrowUp':
    case 'k':
      navigate(-GRID_COLS.value, e.shiftKey)
      e.preventDefault()
      break
    case 'ArrowRight':
    case 'l':
      navigate(1, e.shiftKey)
      e.preventDefault()
      break
    case 'l':
      navigate(1, e.shiftKey)
      e.preventDefault()
      break
    case 'ArrowLeft':
    case 'h':
      navigate(-1, e.shiftKey)
      e.preventDefault()
      break
    case 'h':
      navigate(-1, e.shiftKey)
      e.preventDefault()
      break
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  // If the user navigates away mid-drag, the move/up listeners would leak.
  window.removeEventListener('mousemove', onPreviewDragMove)
  window.removeEventListener('mouseup', onPreviewDragEnd)
  window.removeEventListener('mousemove', onResizerMove)
  window.removeEventListener('mouseup', onResizerUp)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
})
</script>
