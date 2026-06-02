<template>
  <PageHeader :title="headerTitle" subtitle="Confirm, correct, or reject detections" />
  <PollinatorsStepper current="review" :runId="run?.id" />
  <div
    v-if="detections.length > 0"
    class="px-8 py-1.5 border-b border-border bg-surface flex items-center gap-3 text-xs text-muted-foreground"
  >
    <span
      v-if="imageFirstPageInfo"
      class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-muted"
    >
      <span class="font-medium text-foreground">Image</span>
      <span class="font-mono tabular-nums text-foreground"
        >{{ imageFirstPageInfo.current.toLocaleString() }} /
        {{ imageFirstPageInfo.total.toLocaleString() }}</span
      >
    </span>
    <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-muted">
      <span class="font-mono tabular-nums text-foreground">{{
        filteredDetections.length.toLocaleString()
      }}</span>
      <span>visible</span>
      <span class="text-muted-foreground/50">/</span>
      <span class="font-mono tabular-nums text-foreground">{{
        detections.length.toLocaleString()
      }}</span>
      <span>total crops</span>
    </span>
    <InfoPopover>
      Visible = crops shown right now; total = every crop in the run. Crops are hidden when they
      fall below the confidence thresholds or don't match the active filters, and already-reviewed
      crops are hidden by default.
    </InfoPopover>
    <span v-if="loadProgress.total && loadProgress.loaded < loadProgress.total" class="italic">
      loading {{ loadProgress.loaded.toLocaleString() }}/{{ loadProgress.total.toLocaleString() }}…
    </span>
  </div>

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
    <ReviewImageFirst
      v-if="settings.reviewLayout === 'image-first'"
      :detections="filteredDetections"
      :selected-id="selectedId"
      :bulk-ids="bulkIds"
      :roi-bbox="roiBbox"
      @update:selected-id="selectedId = $event"
      @drag-select="onImageFirstDragSelect"
      @delete-image="onDeleteImage"
      @toggle-training-include="onToggleTrainingInclude"
    >
      <template #below>
        <!-- Four side-by-side containers under the image. Fixed height so
             the row never reflows when a crop with unusual aspect lands
             in the preview. Left to right: crop preview, predictions,
             thresholds, labels. -->
        <div
          class="grid grid-cols-1 md:grid-cols-[1fr_1fr_1fr_1.2fr] divide-y md:divide-y-0 md:divide-x divide-border h-48"
        >
          <!-- Focused crop preview. Hidden in bulk mode since there's no
               single crop to preview; only shown for a lone selection. -->
          <div class="p-2 min-h-0 flex items-center justify-center">
            <img
              v-if="!bulkMode && selected && selected.crop_url"
              :src="selected.crop_url"
              :alt="`Detection ${selected.id}`"
              class="w-full h-full object-contain bg-background border border-border shadow-sm"
            />
            <span v-else class="text-xs text-muted-foreground">
              {{ bulkMode ? `${bulkIds.size} crops selected` : 'No crop selected' }}
            </span>
          </div>

          <!-- Model predictions for the focused crop. Mirrors the sidebar
               row format so the same info is reachable without scrolling.
               Empty-state message is centered to match the crop-preview
               container's layout when nothing is selected or in bulk mode. -->
          <div class="px-4 py-2 min-h-0 overflow-auto flex flex-col">
            <div
              class="flex items-center gap-1 text-[10px] xl:text-[11px] font-semibold uppercase tracking-wider text-muted-foreground"
            >
              <span>Predictions</span>
              <InfoPopover>
                The model calls for this crop: the Full-Image (YOLO) detector and the Motion-Based (4-group) classifier (fly / bumblebee / butterfly / other), each with its confidence. These are model outputs, not your decision — confirm or correct them with the Label controls.
              </InfoPopover>
            </div>
            <div
              class="flex-1 min-h-0 mt-1"
              :class="!bulkMode && selected ? '' : 'flex items-center justify-center text-center'"
            >
              <div v-if="!bulkMode && selected" class="space-y-0.5 text-xs font-mono">
                <div class="flex items-center gap-2">
                  <span class="text-muted-foreground w-24 text-[10px] flex flex-col leading-tight">YOLO<span class="opacity-60">(Full-Image)</span></span>
                  <span class="w-10 tabular-nums">
                    {{
                      selected.yolo_confidence != null ? selected.yolo_confidence.toFixed(2) : '—'
                    }}
                  </span>
                  <span class="font-medium">{{
                    selected.yolo_class
                      ? classLabel(selected.yolo_class).slice(0, 1).toUpperCase() +
                        classLabel(selected.yolo_class).slice(1)
                      : '—'
                  }}</span>
                </div>
                <div class="flex items-center gap-2">
                  <span class="text-muted-foreground w-24 text-[10px] flex flex-col leading-tight">4-Group<span class="opacity-60">(Motion-Based)</span></span>
                  <span class="w-10 tabular-nums">
                    {{
                      selected.insectnet_confidence != null
                        ? selected.insectnet_confidence.toFixed(2)
                        : '—'
                    }}
                  </span>
                  <span class="font-medium">{{
                    selected.insectnet_class ? classLabel(selected.insectnet_class) : '—'
                  }}</span>
                </div>
              </div>
              <span v-else class="text-xs text-muted-foreground">
                {{ bulkMode ? `${bulkIds.size} crops selected` : 'No crop selected' }}
              </span>
            </div>

            <!-- Annotation bbox colors. User-level (localStorage), shared across
                 runs; the review boxes read these from the same store. -->
            <div class="border-t border-border pt-2 mt-2">
              <AnnotationColorPickers />
            </div>
          </div>

          <!-- Thresholds -->
          <div class="px-4 py-2 space-y-1 min-h-0 overflow-auto">
            <div
              class="flex items-center gap-1 text-[10px] xl:text-[11px] font-semibold uppercase tracking-wider text-muted-foreground"
            >
              <span>Thresholds</span>
              <InfoPopover>
                Hide crops below either confidence from the review grid. The same values drive the
                "Suggest exports" blue ring on the Export page. Crops with no score in a branch pass
                that branch's filter (e.g. a preprocessing-only crop has no YOLO score). Stored per
                run.
              </InfoPopover>
            </div>
            <div class="grid grid-cols-[auto_1fr_auto] items-center gap-x-1 gap-y-1 text-xs">
              <label for="img-yolo-min" class="text-muted-foreground" title="Full-Image Detection (YOLO) confidence threshold"><span class="min-[1200px]:hidden">FI ≥</span><span class="hidden min-[1200px]:inline">Full-Image ≥</span></label>
              <input
                id="img-yolo-min"
                type="range"
                min="0.05"
                max="1"
                step="0.05"
                v-model.number="yoloMinConf"
                class="w-full accent-primary"
              />
              <span class="font-mono w-9 text-right">{{ yoloMinConf.toFixed(2) }}</span>
              <label for="img-group-min" class="text-muted-foreground" title="Classifier Classification confidence threshold"><span class="min-[1200px]:hidden">Cls ≥</span><span class="hidden min-[1200px]:inline">Classification ≥</span></label>
              <input
                id="img-group-min"
                type="range"
                min="0.05"
                max="1"
                step="0.05"
                v-model.number="groupMinConf"
                class="w-full accent-primary"
              />
              <span class="font-mono w-9 text-right">{{ groupMinConf.toFixed(2) }}</span>
            </div>

            <!-- Run-scoped controls live with the thresholds they relate to.
                 flex-wrap keeps the toggle + its info icon together as one
                 unit and drops the reset link to its own line when the column
                 is too narrow for both. pt-4 spaces it down from the sliders. -->
            <div class="flex flex-wrap items-center gap-x-3 gap-y-2 pt-4 text-xs">
              <div class="flex items-center gap-1.5">
                <button
                  role="switch"
                  :aria-checked="exportAutoSelect"
                  :disabled="!run"
                  class="inline-flex items-center gap-1.5 cursor-pointer focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
                  @click="toggleAutoSelect"
                >
                  <span
                    class="relative inline-block w-8 h-4 rounded-full transition-colors shrink-0"
                    :class="exportAutoSelect ? 'bg-primary' : 'bg-muted-foreground/30'"
                  >
                    <span
                      class="absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white shadow transition-transform"
                      :class="exportAutoSelect ? 'translate-x-4' : ''"
                    />
                  </span>
                  <span class="font-medium">Suggest exports</span>
                </button>
                <InfoPopover>
                  When on, every unreviewed detection that clears both confidence thresholds is
                  auto-confirmed and sent to the Export page, shown with a blue ring to mark it as
                  machine-picked (manual confirmations stay green). Turning it off reverts those
                  auto-confirmations; your manual decisions are untouched.
                </InfoPopover>
              </div>
              <Tooltip
                class="ml-auto"
                text="Set both thresholds back to the confidence values this run was configured with on the upload page."
              >
                <button
                  class="text-muted-foreground hover:text-foreground underline-offset-2 hover:underline disabled:opacity-50 disabled:cursor-not-allowed disabled:no-underline"
                  :disabled="!run"
                  @click="resetThresholdsToRunConfig"
                >
                  Use run's thresholds
                </button>
              </Tooltip>
            </div>
          </div>

          <!-- Labels (right) -->
          <div class="px-4 py-2 flex flex-col gap-1 min-h-0 overflow-auto">
            <div
              class="flex items-center gap-1 text-[10px] xl:text-[11px] font-semibold uppercase tracking-wider text-muted-foreground"
            >
              <span>Label</span>
              <InfoPopover>
                Your decision for the selected crop (or the whole bulk selection). Pick a class to
                confirm/correct it, or Background to reject. Keyboard: 1 Fly, 2 Bumblebee,
                3 Butterfly, 4 Other; x to reject, u for unsure, ⏎ for the suggested class. In the
                image-first layout, d rejects every still-unreviewed crop in the current image as
                background (deletes nothing, undo with Ctrl+Z).
              </InfoPopover>
              <span
                v-if="bulkMode"
                class="ml-1 normal-case tracking-normal text-muted-foreground/80"
              >
                · {{ bulkIds.size }} selected
              </span>
            </div>
            <div class="flex flex-col">
              <label
                v-for="cls in CLASSES"
                :key="cls"
                class="flex items-center gap-2 py-0 px-2 -mx-2 rounded text-sm cursor-pointer hover:bg-muted/50"
                :class="!selected && !bulkMode ? 'opacity-50 pointer-events-none' : ''"
              >
                <span
                  class="w-2 h-2 rounded-full shrink-0"
                  :style="{ backgroundColor: classColor(cls) }"
                />
                <span class="flex-1">{{ classLabel(cls) }}</span>
                <input
                  type="radio"
                  name="label-class-img"
                  :checked="panelLabelOf(selected) === cls"
                  @change="pendingLabel = cls"
                  class="w-4 h-4"
                />
              </label>
              <label
                class="flex items-center gap-2 py-0 px-2 -mx-2 rounded text-sm cursor-pointer hover:bg-muted/50"
                :class="!selected && !bulkMode ? 'opacity-50 pointer-events-none' : ''"
              >
                <span class="w-2 h-2 rounded-full shrink-0 bg-muted-foreground/40" />
                <span class="flex-1">
                  Background
                  <span class="text-[11px] text-muted-foreground ml-1">(reject)</span>
                </span>
                <input
                  type="radio"
                  name="label-class-img"
                  :checked="panelLabelOf(selected) === 'background'"
                  @change="pendingLabel = 'background'"
                  class="w-4 h-4"
                />
              </label>
            </div>
            <div class="flex gap-2 pt-1">
              <Tooltip
                text="Mark the selection as unsure — parks it for later revisit (shortcut: u)."
              >
                <button
                  class="flex-1 px-2 py-1 rounded-md text-sm font-medium border border-amber-300 text-amber-700 hover:bg-amber-50"
                  @click="commitUnsure"
                >
                  Unsure
                </button>
              </Tooltip>
              <Tooltip
                text="Apply the chosen label to the selection (shortcuts: 1-4 for classes, x for reject, ⏎ for the suggested class)."
              >
                <button
                  class="flex-1 px-2 py-1 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
                  :disabled="!canConfirm"
                  @click="commitPending"
                >
                  Confirm
                </button>
              </Tooltip>
            </div>
          </div>
        </div>
      </template>
    </ReviewImageFirst>
    <div v-else class="flex-1 flex flex-col-reverse lg:flex-row min-h-0">
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
          <div class="grid grid-cols-[auto_1fr_auto] items-center gap-x-1 gap-y-1 text-xs">
            <label for="yolo-min" class="text-muted-foreground" title="Full-Image Detection (YOLO) confidence threshold"><span class="min-[1200px]:hidden">FI ≥</span><span class="hidden min-[1200px]:inline">Full-Image ≥</span></label>
            <input
              id="yolo-min"
              type="range"
              min="0.05"
              max="1"
              step="0.05"
              v-model.number="yoloMinConf"
              class="w-full accent-primary"
            />
            <span class="font-mono w-9 text-right">{{ yoloMinConf.toFixed(2) }}</span>
            <label for="group-min" class="text-muted-foreground" title="Classifier Classification confidence threshold"><span class="min-[1200px]:hidden">Cls ≥</span><span class="hidden min-[1200px]:inline">Classification ≥</span></label>
            <input
              id="group-min"
              type="range"
              min="0.05"
              max="1"
              step="0.05"
              v-model.number="groupMinConf"
              class="w-full accent-primary"
            />
            <span class="font-mono w-9 text-right">{{ groupMinConf.toFixed(2) }}</span>
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
            <span class="flex items-center gap-1 flex-1 min-w-0">
              <span class="truncate">
                {{ filteredDetections.length }} of {{ detections.length }} detections<span
                  v-if="loadProgress.total && loadProgress.loaded < loadProgress.total"
                  class="italic"
                >
                  · loading {{ loadProgress.loaded }}/{{ loadProgress.total }}…</span
                >
              </span>
              <InfoPopover>
                First number = detections left under the current filters (Show, Class, search, and
                the YOLO / Group sliders); second = total in the run. The default "Pending" filter
                hides crops you've already reviewed.
              </InfoPopover>
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

        <!-- Virtualized grid. groupedDetections is flattened into header rows
             and fixed-width tile rows (gridRows); DynamicScroller mounts only
             the rows near the viewport, so a 15k-crop run paints ~2 screens of
             DOM instead of every tile. Column count (colsPerRow) is measured
             from the scroll container so the rows match the visual width at
             every divider position, and keyboard nav reads the same value.
             Group headers no longer stick — virtual rows are absolutely
             positioned, so sticky has nothing to stick to. -->
        <DynamicScroller
          v-if="gridRows.length"
          ref="gridScroller"
          :items="gridRows"
          :min-item-size="40"
          key-field="key"
          class="flex-1 min-h-0"
        >
          <template #default="{ item, index, active }">
            <DynamicScrollerItem
              :item="item"
              :active="active"
              :data-index="index"
              :size-dependencies="item.type === 'tiles' ? [colsPerRow, item.detections.length] : []"
            >
              <header
                v-if="item.type === 'header'"
                class="px-4 py-2 text-xs font-semibold uppercase tracking-wide bg-surface border-b border-border"
                :class="
                  item.kind === 'needs_review'
                    ? 'text-amber-700'
                    : item.kind === 'unclassified'
                      ? 'text-indigo-700'
                      : item.kind === 'background'
                        ? 'text-muted-foreground/70'
                        : 'text-muted-foreground'
                "
              >
                <span v-if="item.kind === 'needs_review'" class="mr-1">⚠</span>
                <span v-else-if="item.kind === 'unclassified'" class="mr-1">?</span>
                <span v-else-if="item.kind === 'background'" class="mr-1">✗</span>
                {{ item.label }}
                <span class="font-normal">({{ item.count }})</span>
              </header>
              <div
                v-else
                class="grid gap-1 px-2 py-0.5"
                :style="{ gridTemplateColumns: `repeat(${colsPerRow}, minmax(0, 1fr))` }"
              >
                <div
                  v-for="d in item.detections"
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
            </DynamicScrollerItem>
          </template>
        </DynamicScroller>
        <div v-else class="flex-1 p-8 text-center text-sm text-muted-foreground">
          No detections match the current filter.
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
                  :fill="isHighlighted(ov.id) ? settings.annotationHighlightColor : 'transparent'"
                  :fill-opacity="isHighlighted(ov.id) ? 0.18 : 0"
                  :stroke="
                    isHighlighted(ov.id)
                      ? settings.annotationHighlightColor
                      : settings.annotationColor
                  "
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
                <ROIOverlay
                  :bbox="roiBbox"
                  :image-w="sourceImage.w"
                  :image-h="sourceImage.h"
                  :color="settings.roiColor"
                />
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
                  class="inline-flex items-center gap-1 text-[10px] xl:text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-0.5"
                >
                  Label
                  <InfoPopover>
                    Your decision for the selected crop (or the whole bulk selection). Pick a class
                    to confirm/correct it, or Background to reject. Keyboard: 1 Fly, 2 Bumblebee,
                    3 Butterfly, 4 Other; x to reject, u for unsure, ⏎ for the suggested class. In
                    the image-first layout, d rejects every still-unreviewed crop in the current
                    image as background (deletes nothing, undo with Ctrl+Z).
                  </InfoPopover>
                  <span
                    v-if="bulkMode"
                    class="ml-1 normal-case tracking-normal text-muted-foreground/80"
                  >
                    · applies to {{ bulkIds.size }} selected
                  </span>
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
                      :checked="panelLabel(selected) === cls"
                      @change="pendingLabel = cls"
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
                      :checked="panelLabel(selected) === 'background'"
                      @change="pendingLabel = 'background'"
                      class="w-3.5 h-3.5 xl:w-4 xl:h-4"
                    />
                  </label>
                </div>
              </div>

              <!-- Predictions (compact, two-line). Hidden in bulk mode —
                   per-detection model output doesn't make sense when the
                   user is acting on a mixed selection. -->
              <div v-if="!bulkMode" class="px-5 py-2 flex flex-col">
                <div
                  class="inline-flex items-center gap-1 text-[10px] xl:text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-0.5"
                >
                  Predictions
                  <InfoPopover>
                    The model calls for this crop: the Full-Image (YOLO) detector and the Motion-Based (4-group) classifier (fly / bumblebee / butterfly / other), each with its confidence. These are model outputs, not your decision — confirm or correct them with the Label controls.
                  </InfoPopover>
                </div>
                <div class="space-y-0.5 text-xs xl:text-sm">
                  <div
                    class="flex items-center gap-2"
                    :class="selected.yolo_class == null ? 'opacity-60' : ''"
                  >
                    <span class="text-muted-foreground w-24 xl:w-28 flex flex-col leading-tight text-xs">YOLO<span class="opacity-60">(Full-Image)</span></span>
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
                    <span class="text-muted-foreground w-24 xl:w-28 flex flex-col leading-tight text-xs">4-Group<span class="opacity-60">(Motion-Based)</span></span>
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
                <!-- Annotation bbox colors (shared store; same control as the
                     image-first layout). Pushed to the bottom of the panel. -->
                <div class="border-t border-border pt-3 mt-auto">
                  <AnnotationColorPickers />
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
                class="px-3 py-1.5 rounded-md text-sm font-medium border border-amber-300 text-amber-700 hover:bg-amber-50"
                @click="commitUnsure"
              >
                Unsure
              </button>
              <button
                class="px-3 py-1.5 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-primary"
                :disabled="!canConfirm"
                :title="canConfirm ? '' : 'Pick a label or wait for models to agree'"
                @click="commitPending"
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
            :color="settings.roiColor"
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
import { ZoomIn } from 'lucide-vue-next'
import { DynamicScroller, DynamicScrollerItem } from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'
import PageHeader from '@/components/PageHeader.vue'
import Tooltip from '@/components/Tooltip.vue'
import InfoPopover from '@/components/InfoPopover.vue'
import PollinatorsStepper from '@/components/PollinatorsStepper.vue'
import ROIOverlay from '@/components/ROIOverlay.vue'
import { api } from '@/api'
import {
  effectiveReviewSettings,
  normalizeRoiBbox,
  type Detection,
  type PollinatorClass,
  type ReviewerStatus,
  type ReviewSettings,
} from '@/types/pollinator'
import { useRunDetections } from '@/composables/useRunDetections'
import { useReviewKeyboard } from '@/composables/useReviewKeyboard'
import { useImageZoom } from '@/composables/useImageZoom'
import { usePollinatorSettingsStore } from '@/stores/pollinatorSettings'
import ReviewImageFirst from '@/components/pollinator/ReviewImageFirst.vue'
import AnnotationColorPickers from '@/components/pollinator/AnnotationColorPickers.vue'

const settings = usePollinatorSettingsStore()

// Frontend workflow labels (not the backend reviewer_status).
//   pending  — unreviewed; the active working queue.
//   reviewed — anything the reviewer has settled (confirmed / corrected /
//              rejected). Lets the reviewer see what's already handled.
//   unsure   — explicitly parked for revisit; kept separate so it doesn't
//              disappear into the reviewed pile.
//   all      — everything.
type StatusFilter = 'pending' | 'reviewed' | 'unsure' | 'all'

const LOW_CONFIDENCE_THRESHOLD = 0.6

const CLASSES: PollinatorClass[] = ['fly', 'bumblebee', 'butterfly', 'other']
const CLASS_COLORS: Record<PollinatorClass, string> = {
  fly: '#6b9bd2',
  bumblebee: '#e6a946',
  butterfly: '#c87bba',
  other: '#9aa3ab',
}
const CLASS_GLYPHS: Record<PollinatorClass, string> = {
  fly: '🪰',
  bumblebee: '🐝',
  butterfly: '🦋',
  other: '?',
}

const route = useRoute()
const { run, detections, loading, loadError, loadProgress, load } = useRunDetections(
  route.params.id as string,
)
const selectedId = ref<number | null>(null)
const statusFilter = ref<StatusFilter>('pending')
type ClassFilter = PollinatorClass | 'background' | 'all'
const classFilter = ref<ClassFilter>('all')
// Per-run reviewer settings (thresholds + auto-select). Stored in the DB
// on the run, defaulting to the run's own config confidences via
// effectiveReviewSettings — so a run's sliders start where it was
// processed, and any change is remembered per-run. The thresholds drive
// BOTH the visible filter here AND the export auto-select indicator.
//
// Writes are optimistic + debounced: dragging a slider updates the UI and
// filtering immediately, but only one PATCH lands ~400ms after the drag
// settles instead of one per step.
let reviewSettingsTimer: ReturnType<typeof setTimeout> | null = null
let pendingReviewSettings: ReviewSettings = {}
let pendingReviewSettingsRunId: number | null = null

// True while an auto-select round-trip + reload is in flight, so the toggle
// can't be double-fired and the UI can show a busy state.
const applyingAutoSelect = ref(false)

// Drive the "Suggest exports" toggle: the backend persists auto_select,
// reverts prior auto-accepts, and (when enabled) confirms every unreviewed
// detection above both thresholds. Reload afterwards so the grid reflects
// the new reviewer_status / auto_accepted stamps. detections.value is reset
// first because the composable's load() appends pages onto the current list.
async function runAutoSelect(enabled: boolean) {
  const r = run.value
  if (!r || applyingAutoSelect.value) return
  applyingAutoSelect.value = true
  try {
    const res = await api(`/api/pollinator/runs/${r.id}/auto-select/`, {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    })
    if (!res.ok) throw new Error(`Auto-select: HTTP ${res.status}`)
    r.review_settings = { ...(r.review_settings ?? {}), auto_select: enabled }
    detections.value = []
    await load()
  } catch (e) {
    console.error(e)
  } finally {
    applyingAutoSelect.value = false
  }
}

// Send whatever's queued right now and clear the timer. Called both by the
// debounce and on unmount, so a save can't be lost by navigating away
// inside the debounce window. recompute=false on unmount so we don't kick
// off a reload into a dead component.
async function flushReviewSettings(recompute = true) {
  if (reviewSettingsTimer != null) {
    clearTimeout(reviewSettingsTimer)
    reviewSettingsTimer = null
  }
  if (pendingReviewSettingsRunId == null || Object.keys(pendingReviewSettings).length === 0) return
  const id = pendingReviewSettingsRunId
  const body = pendingReviewSettings
  pendingReviewSettings = {}
  pendingReviewSettingsRunId = null
  const hadThreshold = 'yolo_threshold' in body || 'group_threshold' in body
  const res = await api(`/api/analysis/runs/${id}/review-settings/`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
  // A threshold change while auto-select is on must re-derive the
  // auto-accepted set against the new bounds.
  if (recompute && res.ok && hadThreshold && effectiveReviewSettings(run.value).autoSelect) {
    await runAutoSelect(true)
  }
}

function patchReviewSettings(partial: ReviewSettings) {
  const r = run.value
  if (!r) return
  r.review_settings = { ...(r.review_settings ?? {}), ...partial }
  pendingReviewSettings = { ...pendingReviewSettings, ...partial }
  pendingReviewSettingsRunId = r.id
  if (reviewSettingsTimer != null) clearTimeout(reviewSettingsTimer)
  reviewSettingsTimer = setTimeout(flushReviewSettings, 400)
}

const yoloMinConf = computed<number>({
  get: () => effectiveReviewSettings(run.value).yolo,
  set: (v) => patchReviewSettings({ yolo_threshold: v }),
})
// The wire field is `insectnet_confidence`, but the value it carries is
// the group classifier's top-class probability.
const groupMinConf = computed<number>({
  get: () => effectiveReviewSettings(run.value).group,
  set: (v) => patchReviewSettings({ group_threshold: v }),
})
const exportAutoSelect = computed(() => effectiveReviewSettings(run.value).autoSelect)
function toggleAutoSelect() {
  // Flush any pending threshold edits first so the backend recompute reads
  // the thresholds the reviewer just set, then apply/revert auto-accept.
  void flushReviewSettings(false).then(() =>
    runAutoSelect(!effectiveReviewSettings(run.value).autoSelect),
  )
}

function passesSliders(d: Detection): boolean {
  const yoloOk = d.yolo_confidence == null || d.yolo_confidence >= yoloMinConf.value
  const groupOk = d.insectnet_confidence == null || d.insectnet_confidence >= groupMinConf.value
  return yoloOk && groupOk
}

// Reset both sliders to the confidence values THIS run was created with on
// the upload page (YOLO ← yolo.confidence, Group ← group_classifier
// .confidence), persisting them as the run's review thresholds.
function resetThresholdsToRunConfig() {
  const cfg = run.value?.config
  patchReviewSettings({
    yolo_threshold: cfg?.yolo?.confidence ?? 0.5,
    group_threshold: cfg?.group_classifier?.confidence ?? 0.5,
  })
}
const bulkIds = ref<Set<number>>(new Set())
const bulkCorrectClass = ref<'' | PollinatorClass>('')
// Surfaces how many rows the most recent bulk-confirm skipped because they
// had no derivable class. Reset when the reviewer next interacts with the
// bulk bar (selection change or explicit clear).
const bulkConfirmSkipped = ref(0)

interface FailedEntry {
  status: ReviewerStatus
  label: PollinatorClass | null
  prevStatus: ReviewerStatus
  prevLabel: PollinatorClass | null
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

onMounted(load)

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
  // Sort by (source image filename, bbox.x1, bbox.y1, id). Within a single
  // image this gives the natural left-to-right reading order, which
  // matches the image-first arrow-key navigation users expect; between
  // images it falls back to alphabetical filename so the rail and the
  // detection sequence stay aligned. Detections with no bbox sink to the
  // end of their image's group (by id), keeping the comparator total and
  // deterministic.
  return [...list].sort((a, b) => {
    const fn = a.source_image_filename.localeCompare(b.source_image_filename)
    if (fn !== 0) return fn
    const ax = a.bbox?.x1
    const bx = b.bbox?.x1
    if (ax == null && bx == null) return a.id - b.id
    if (ax == null) return 1
    if (bx == null) return -1
    if (ax !== bx) return ax - bx
    // Larger y first when x ties: at the same horizontal slot, the
    // lower-on-image crop comes earlier in the sequence.
    const ay = a.bbox?.y1 ?? 0
    const by = b.bbox?.y1 ?? 0
    if (ay !== by) return by - ay
    return a.id - b.id
  })
})

const groupedDetections = computed(() => {
  const review: Detection[] = []
  const unclassified: Detection[] = []
  const background: Detection[] = []
  const classGroups = new Map<PollinatorClass, Detection[]>()
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
  const collapseToClass: PollinatorClass | null =
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

// --- Virtualized grid rows -------------------------------------------------
// The crops grid renders through DynamicScroller, which windows a flat list
// of rows. Each group becomes one header row plus ceil(n / colsPerRow) tile
// rows. Only the rows near the viewport are mounted, so DOM size stays
// constant regardless of how many crops the run produced.
type HeaderRow = {
  key: string
  type: 'header'
  label: string
  kind: 'needs_review' | 'unclassified' | 'class' | 'background'
  count: number
}
type TileRow = { key: string; type: 'tiles'; detections: Detection[] }
type GridRow = HeaderRow | TileRow

// Map the container-query breakpoints in the grid template to a column count.
// Single source of truth shared by the layout (gridRows) and keyboard nav
// (navigate steps by a full row), so the two can't drift.
function colsForWidth(w: number): number {
  if (w >= 560) return 7
  if (w >= 440) return 6
  if (w >= 340) return 5
  if (w >= 260) return 4
  return 3
}

// Live width of the scroll container, measured (not derived from leftWidth)
// so the column count is correct on mobile too, where the section is
// full-width rather than pinned to the divider. Seeded with the default left
// width (4 cols); the ResizeObserver overwrites it as soon as the scroller
// mounts, so this only governs the very first frame.
const containerWidth = ref(300)
const colsPerRow = computed(() => colsForWidth(containerWidth.value))
const gridScroller = ref<{ $el: HTMLElement; scrollToItem: (i: number) => void } | null>(null)

const gridRows = computed<GridRow[]>(() => {
  const cols = colsPerRow.value
  const rows: GridRow[] = []
  for (const group of groupedDetections.value) {
    rows.push({
      key: `h:${group.label}`,
      type: 'header',
      label: group.label,
      kind: group.kind,
      count: group.detections.length,
    })
    for (let i = 0; i < group.detections.length; i += cols) {
      const slice = group.detections.slice(i, i + cols)
      rows.push({ key: `t:${group.label}:${slice[0].id}`, type: 'tiles', detections: slice })
    }
  }
  return rows
})

// Observe the scroll container so colsPerRow tracks the divider drag and
// viewport changes. The scroller only exists once detections have loaded, so
// (re)attach whenever the element appears.
let gridResizeObserver: ResizeObserver | null = null
watch(gridScroller, (s) => {
  gridResizeObserver?.disconnect()
  gridResizeObserver = null
  const el = s?.$el
  if (!el) return
  gridResizeObserver = new ResizeObserver((entries) => {
    containerWidth.value = entries[0].contentRect.width
  })
  gridResizeObserver.observe(el)
  containerWidth.value = el.clientWidth
})

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

// Image-first page indicator: count unique source-image filenames in the
// filtered view, find where the active selection sits in that order.
// Returns null in crop-first or when nothing is selected — the strip
// below the stepper only renders the indicator when this resolves.
const imageFirstPageInfo = computed<{ current: number; total: number } | null>(() => {
  if (settings.reviewLayout !== 'image-first') return null
  const filenames: string[] = []
  const seen = new Set<string>()
  for (const d of filteredDetections.value) {
    if (d.source_image_filename && !seen.has(d.source_image_filename)) {
      seen.add(d.source_image_filename)
      filenames.push(d.source_image_filename)
    }
  }
  if (filenames.length === 0) return null
  const activeFilename = selected.value?.source_image_filename ?? filenames[0]
  const idx = filenames.indexOf(activeFilename)
  if (idx < 0) return { current: 1, total: filenames.length }
  return { current: idx + 1, total: filenames.length }
})

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

// Mouse picks on the Label panel set this rather than firing a server PATCH
// immediately. The Confirm button reads it. 'background' = the panel's
// reject row. null = no pending change. Resets on selection change (or
// when bulkIds shifts) so a staged-but-uncommitted pick can't leak into
// the next target.
type PendingLabel = PollinatorClass | 'background' | null
const pendingLabel = ref<PendingLabel>(null)

// True when the bulk drag-selected more than one detection — the Label
// panel then targets the whole bulk instead of just the primary `selected`.
const bulkMode = computed(() => bulkIds.value.size > 1)

// Drag-select handler for the image-first view. The child computes which
// detection ids fell inside the dragged rectangle (center-in-rect) and
// sends them up here so the parent's bulkIds stays the single source of
// truth across both layouts.
function onImageFirstDragSelect(ids: number[]) {
  if (ids.length === 0) {
    bulkIds.value = new Set()
    return
  }
  bulkIds.value = new Set(ids)
  // Promote the first hit to the active selection so the right pane is
  // populated and the keyboard shortcuts have something to act on.
  if (selectedId.value == null || !bulkIds.value.has(selectedId.value)) {
    selectedId.value = ids[0]
  }
}

// Rail "delete": reject every still-unreviewed crop in the image as
// background. Already-decided crops (confirmed/corrected/rejected/unsure)
// are left untouched, and the source file/image is NOT deleted. Undoable
// as one Ctrl+Z (pushUndo captures the prior state of every crop touched).
function onDeleteImage(filename: string) {
  const ids = detections.value
    .filter((d) => d.source_image_filename === filename && d.reviewer_status === 'unreviewed')
    .map((d) => d.id)
  if (!ids.length) return
  // If the active selection is one we're about to reject, move it to the
  // first crop that isn't being deleted (computed before the mutation,
  // while the list still contains everything).
  if (selectedId.value != null && ids.includes(selectedId.value)) {
    const deleted = new Set(ids)
    const nextOutside = filteredDetections.value.find((d) => !deleted.has(d.id))
    selectedId.value = nextOutside ? nextOutside.id : null
  }
  pushUndo(ids)
  void submitBulk(ids, 'rejected', null)
}

// Toggle the per-image "include in YOLO training" flag. Optimistically
// flips it on every detection of that image (they all carry the same
// per-image value), then persists against the image id.
function onToggleTrainingInclude(filename: string) {
  const imgDets = detections.value.filter((d) => d.source_image_filename === filename)
  const imageId = imgDets[0]?.source_image_id
  if (imageId == null) return
  const next = !imgDets[0].include_in_training
  for (const d of imgDets) d.include_in_training = next
  void api(`/api/analysis/images/${imageId}/include-training/`, {
    method: 'POST',
    body: JSON.stringify({ included: next }),
  })
}

watch(selectedId, async (id) => {
  pendingLabel.value = null
  if (id == null) return
  await nextTick()
  // The tile may be windowed out of the DOM. If so, scroll its row into the
  // scroller's buffer first so the element mounts, then fall back to the
  // browser's "nearest" scroll which keeps an already-visible tile from
  // jumping during left/right navigation.
  let el = document.querySelector(`[data-detection-id="${id}"]`)
  if (!el) {
    const rowIdx = gridRows.value.findIndex(
      (r) => r.type === 'tiles' && r.detections.some((d) => d.id === id),
    )
    if (rowIdx >= 0) {
      gridScroller.value?.scrollToItem(rowIdx)
      await nextTick()
      el = document.querySelector(`[data-detection-id="${id}"]`)
    }
  }
  el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
})

// Clearing the bulk set or shrinking it back to a single row should also
// drop any pending pick that was staged for the bulk.
watch(bulkMode, (isBulk, wasBulk) => {
  if (isBulk !== wasBulk) pendingLabel.value = null
})

// What the Label panel should show as ticked. In bulk mode there's no
// "single source of truth" across the selected detections, so nothing is
// pre-ticked — the user has to actively pick one. Otherwise pending pick
// wins; falling back to the row's settled state.
function panelLabel(d: Detection): PendingLabel {
  if (bulkMode.value) return pendingLabel.value
  if (pendingLabel.value !== null) return pendingLabel.value
  if (d.reviewer_status === 'rejected') return 'background'
  return effectiveLabel(d)
}

// Null-tolerant variant for templates that render under (selected || bulk)
// guards: when no row is selected but a bulk is active, the pending
// pick is what the panel should mirror.
function panelLabelOf(d: Detection | null): PendingLabel {
  return d ? panelLabel(d) : pendingLabel.value
}

// Confirm enabled when there's something to send.
//   Bulk: a staged pick (we apply it to every selected detection).
//   Single: a pending pick that differs from the row's state, or an
//           unreviewed row that already has an effective label.
const canConfirm = computed(() => {
  if (bulkMode.value) return pendingLabel.value !== null
  const d = selected.value
  if (!d) return false
  if (pendingLabel.value !== null) {
    if (pendingLabel.value === 'background') return d.reviewer_status !== 'rejected'
    return d.reviewer_label !== pendingLabel.value || d.reviewer_status === 'unreviewed'
  }
  return d.reviewer_status === 'unreviewed' && effectiveLabel(d) != null
})

function commitPending() {
  if (bulkMode.value) {
    if (pendingLabel.value === 'background') {
      applyToBulk('rejected', null)
    } else if (pendingLabel.value !== null) {
      applyToBulk('corrected', pendingLabel.value)
    }
    pendingLabel.value = null
    return
  }
  const d = selected.value
  if (!d) return
  // Auto-advance after the commit so the just-reviewed detection drops
  // out of selection. Without this the selectedId stays on the row, and
  // siblingOverlays' "always render the selected bbox" exception keeps the
  // red box on the source image until the reviewer navigates away.
  // Matches the keyboard flow (1-4 / x already pass advanceAfter=true).
  if (pendingLabel.value === 'background') {
    reject(true)
  } else if (pendingLabel.value !== null) {
    confirmAs(pendingLabel.value, true)
  } else {
    const eff = effectiveLabel(d)
    if (eff) confirmAs(eff, true)
  }
  pendingLabel.value = null
}

// Footer Unsure also has to branch — single uses markUnsure() with
// auto-advance (same rationale as Confirm), bulk goes through applyToBulk
// so every selected detection lands on 'unsure' in one request.
function commitUnsure() {
  if (bulkMode.value) {
    applyToBulk('unsure', null)
    pendingLabel.value = null
    return
  }
  markUnsure(true)
}

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

const roiBbox = computed<[number, number, number, number] | null>(() =>
  normalizeRoiBbox(run.value?.config?.preprocessing?.roi_bbox),
)

// Fullscreen zoom/pan over the selected detection's source image.
const {
  zoomDialog,
  zoom,
  panning,
  openZoom,
  closeZoom,
  onZoomClose,
  onZoomWheel,
  onPanStart,
  onPanMove,
  onPanEnd,
} = useImageZoom(sourceImage)

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
  return CLASS_COLORS[cls as PollinatorClass] ?? '#9aa3ab'
}
function classBgFor(cls: string | null): string {
  const hex = classColor(cls)
  return hex + '14'
}
function classGlyph(cls: string | null): string {
  if (!cls) return '?'
  return CLASS_GLYPHS[cls as PollinatorClass] ?? '?'
}
function classLabel(cls: string | null): string {
  if (!cls) return '—'
  return cls[0].toUpperCase() + cls.slice(1)
}
// Class shown on the grid card and used for grouping/coloring. Falls back
// to whichever branch produced the detection when only one is populated.
function primaryClass(d: Detection): PollinatorClass | null {
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
function suggestedClass(d: Detection): PollinatorClass | null {
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
function settledClass(d: Detection): PollinatorClass | null {
  if (d.reviewer_status === 'confirmed' || d.reviewer_status === 'corrected') {
    return effectiveLabel(d)
  }
  return null
}

function effectiveLabel(d: Detection): PollinatorClass | null {
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
  label: PollinatorClass | null,
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
  label: PollinatorClass | null,
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

// --- Undo -----------------------------------------------------------------
// Each classify gesture (a single key/click, or one bulk apply) snapshots
// the prior state of every detection it touches as ONE entry, so a single
// Ctrl+Z reverts the whole gesture — including a bulk that hit dozens of
// crops. Capacity-capped so the stack can't grow unbounded on long runs.
interface UndoItem {
  id: number
  status: ReviewerStatus
  label: PollinatorClass | null
}
const undoStack = ref<{ items: UndoItem[] }[]>([])
const UNDO_LIMIT = 50

function pushUndo(ids: number[]) {
  const idSet = new Set(ids)
  const items: UndoItem[] = []
  for (const d of detections.value) {
    if (idSet.has(d.id)) {
      items.push({ id: d.id, status: d.reviewer_status, label: d.reviewer_label })
    }
  }
  if (!items.length) return
  undoStack.value.push({ items })
  if (undoStack.value.length > UNDO_LIMIT) undoStack.value.shift()
}

async function undoLast() {
  const entry = undoStack.value.pop()
  if (!entry) return
  const byId = new Map(entry.items.map((i) => [i.id, i]))
  // Restore optimistically in the UI.
  for (const d of detections.value) {
    const it = byId.get(d.id)
    if (!it) continue
    d.reviewer_status = it.status
    d.reviewer_label = it.label
    clearFailedSave(d.id)
  }
  // Re-select the single reverted crop so the change is visible; leave
  // selection alone for a bulk revert.
  if (entry.items.length === 1) selectedId.value = entry.items[0].id
  // Persist, grouping identical (status, label) into one bulk request.
  const groups = new Map<
    string,
    { status: ReviewerStatus; label: PollinatorClass | null; ids: number[] }
  >()
  for (const it of entry.items) {
    const key = `${it.status}|${it.label ?? ''}`
    if (!groups.has(key)) groups.set(key, { status: it.status, label: it.label, ids: [] })
    groups.get(key)!.ids.push(it.id)
  }
  for (const g of groups.values()) {
    if (g.ids.length === 1) await patchDetection(g.ids[0], g.status, g.label)
    else await postBulkReview(g.ids, g.status, g.label)
  }
}

async function applyAction(
  status: ReviewerStatus,
  label: PollinatorClass | null,
  advanceAfter = false,
) {
  if (!selected.value) return
  const d = selected.value
  pushUndo([d.id])
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

async function submitBulk(ids: number[], status: ReviewerStatus, label: PollinatorClass | null) {
  if (!ids.length) return
  const idSet = new Set(ids)
  const snapshot = new Map<number, { status: ReviewerStatus; label: PollinatorClass | null }>()
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

async function applyToBulk(status: ReviewerStatus, label: PollinatorClass | null) {
  const ids = [...bulkIds.value]
  pushUndo(ids)
  // If the bulk includes the primary selection, advance selectedId off
  // it before the commit. siblingOverlays keeps the selected row's bbox
  // visible even after it's reviewed (intentional, for browsing the
  // Reviewed pile), which would otherwise leave a stale red box on the
  // source image after a bulk action. Captured BEFORE clearBulk so we
  // can still read the membership.
  const sel = selected.value
  const advanceTo = sel && bulkIds.value.has(sel.id) ? nextVisibleId(sel.id) : null
  clearBulk()
  if (advanceTo != null) selectedId.value = advanceTo
  await submitBulk(ids, status, label)
}

async function retryFailedSaves() {
  if (retrying.value || failedSaves.value.size === 0) return
  retrying.value = true
  try {
    // Group by intended (status, label) so we can retry as bulk requests.
    const groups = new Map<
      string,
      { status: ReviewerStatus; label: PollinatorClass | null; ids: number[] }
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
  const buckets = new Map<PollinatorClass, number[]>()
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
  // One undo entry for the whole confirm gesture, across every bucket.
  pushUndo([...buckets.values()].flat())
  // Same advance logic as applyToBulk — see comment there.
  const sel = selected.value
  const advanceTo = sel && bulkIds.value.has(sel.id) ? nextVisibleId(sel.id) : null
  clearBulk()
  if (advanceTo != null) selectedId.value = advanceTo
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
function confirmAs(cls: PollinatorClass | null, advanceAfter = false) {
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
  // Image-first navigates purely by spatial order (filteredDetections,
  // sorted filename → x1 asc → y1 desc → id). It never touches
  // flatVisible, whose status/class bucketing interleaves images and
  // would skip whole images on the cross-image step.
  if (settings.reviewLayout === 'image-first') {
    const fl = filteredDetections.value
    const fIdx = fl.findIndex((d) => d.id === currentId)
    if (fIdx < 0) return null
    const fn = fl[fIdx].source_image_filename
    // 1. Finish the current image: forward (left-to-right) first…
    for (let i = fIdx + 1; i < fl.length; i++) {
      if (fl[i].source_image_filename === fn) return fl[i].id
    }
    // …then wrap backward to mop up any earlier crops skipped in this
    // image (e.g. the reviewer clicked the right-most one first).
    for (let i = fIdx - 1; i >= 0; i--) {
      if (fl[i].source_image_filename === fn) return fl[i].id
    }
    // 2. Image cleared: jump to the first (left-most) crop of the next
    //    image. Since crops are contiguous per filename and x-ascending,
    //    the first differing filename ahead is that image's left-most.
    for (let i = fIdx + 1; i < fl.length; i++) {
      if (fl[i].source_image_filename !== fn) return fl[i].id
    }
    // 3. Nothing ahead (finished the last image): fall back to the
    //    nearest crop in the previous image so selection doesn't dead-end.
    for (let i = fIdx - 1; i >= 0; i--) {
      if (fl[i].source_image_filename !== fn) return fl[i].id
    }
    return null
  }

  // Crop-first: unchanged — grouped flatVisible order, forward then back.
  const list = flatVisible.value
  const idx = list.findIndex((d) => d.id === currentId)
  if (idx < 0) return null
  if (idx + 1 < list.length) return list[idx + 1].id
  if (idx > 0) return list[idx - 1].id
  return null
}

// Anchor for range selection. Set by every plain click and by every
// non-extending keyboard navigation. Shift+arrow / shift+click define the
// range anchor->current; backtracking shrinks rather than accumulating.
const anchorId = ref<number | null>(null)
// Bulk ids that pre-date the current shift gesture. The active shift range
// gets layered on top so backtracking through it doesn't erase manual picks.
const stableBulkIds = ref<Set<number>>(new Set())

function setShiftRange(fromIdx: number, toIdx: number) {
  const list = navList.value
  const [lo, hi] = fromIdx <= toIdx ? [fromIdx, toIdx] : [toIdx, fromIdx]
  const next = new Set(stableBulkIds.value)
  for (let i = lo; i <= hi; i++) next.add(list[i].id)
  bulkIds.value = next
}

// Image-first up/down: jump to the first detection of the next or
// previous unique source image in filteredDetections order. Bulk
// extension via shift is intentionally ignored — extending a bulk
// across whole images isn't the gesture users want from arrow keys
// here. Left/right keys keep their per-crop step.
function navigateImage(direction: 1 | -1) {
  const sel = selected.value
  if (!sel) return
  const list = filteredDetections.value
  const currentIdx = list.findIndex((d) => d.id === sel.id)
  if (currentIdx < 0) return
  const currentFilename = sel.source_image_filename

  if (direction === 1) {
    for (let i = currentIdx + 1; i < list.length; i++) {
      if (list[i].source_image_filename !== currentFilename) {
        selectedId.value = list[i].id
        anchorId.value = list[i].id
        stableBulkIds.value = new Set(bulkIds.value)
        return
      }
    }
    return
  }

  // Prev image: walk back until the filename changes, then keep
  // walking until it changes again — that's the first detection of
  // the previous image.
  let prevImageLast = -1
  for (let i = currentIdx - 1; i >= 0; i--) {
    if (list[i].source_image_filename !== currentFilename) {
      prevImageLast = i
      break
    }
  }
  if (prevImageLast < 0) return
  const prevFilename = list[prevImageLast].source_image_filename
  let prevImageFirst = prevImageLast
  for (let i = prevImageLast - 1; i >= 0; i--) {
    if (list[i].source_image_filename !== prevFilename) break
    prevImageFirst = i
  }
  selectedId.value = list[prevImageFirst].id
  anchorId.value = list[prevImageFirst].id
  stableBulkIds.value = new Set(bulkIds.value)
}

// The list left/right arrow nav and shift-range selection walk. Image-first
// uses spatial order (filteredDetections) so arrows match the crops sidebar
// and the bbox order on the image; crop-first uses the grouped grid order
// (flatVisible) so arrows match the rendered tile grid. Both navigate() and
// setShiftRange() MUST read the same list since navigate computes indices
// it hands to setShiftRange.
const navList = computed(() =>
  settings.reviewLayout === 'image-first' ? filteredDetections.value : flatVisible.value,
)

function navigate(delta: number, extend: boolean) {
  const list = navList.value
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

useReviewKeyboard({
  getSelected: () => selected.value,
  getBulkSize: () => bulkIds.value.size,
  isZoomOpen: () => zoomDialog.value?.open ?? false,
  isImageFirst: () => settings.reviewLayout === 'image-first',
  getColsPerRow: () => colsPerRow.value,
  undoLast,
  clearBulk,
  applyToBulk,
  confirmAs,
  reject,
  markUnsure,
  navigate,
  navigateImage,
  deleteImage: onDeleteImage,
  toggleInclude: onToggleTrainingInclude,
  suggestedClass,
})

onUnmounted(() => {
  gridResizeObserver?.disconnect()
  // If the user navigates away mid-drag, the move/up listeners would leak.
  window.removeEventListener('mousemove', onPreviewDragMove)
  window.removeEventListener('mouseup', onPreviewDragEnd)
  window.removeEventListener('mousemove', onResizerMove)
  window.removeEventListener('mouseup', onResizerUp)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  // Persist any threshold/toggle change still sitting in the debounce
  // window so navigating away can't drop it. recompute=false: don't reload
  // into a component that's being torn down.
  void flushReviewSettings(false)
})
</script>
