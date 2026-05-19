<template>
  <PageHeader
    title="Pollinator settings"
    subtitle="Per-user preferences for the review and export pages"
  />

  <div class="flex-1 overflow-auto">
    <div class="max-w-3xl mx-auto p-8 space-y-10">
      <!-- Review layout -->
      <section class="space-y-3">
        <header>
          <h2 class="text-base font-semibold">Review layout</h2>
          <p class="text-sm text-muted-foreground">
            Pick how the review page is organized. Both layouts show the same data; the difference
            is whether you step crop-by-crop or image-by-image.
          </p>
        </header>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <button
            v-for="opt in layoutOptions"
            :key="opt.value"
            class="text-left rounded-lg border-2 transition-shadow p-4 focus:outline-none"
            :class="
              settings.reviewLayout === opt.value
                ? 'border-transparent bg-border ring-[3px] ring-primary ring-offset-2 ring-offset-background shadow-md'
                : 'border-border hover:border-muted-foreground/50 hover:bg-muted/30'
            "
            @click="settings.setReviewLayout(opt.value)"
          >
            <div class="flex items-baseline gap-2 mb-2">
              <span class="font-semibold text-sm">{{ opt.label }}</span>
              <span
                v-if="settings.reviewLayout === opt.value"
                class="text-[10px] uppercase tracking-wide bg-primary text-primary-foreground px-1.5 py-0.5 rounded font-semibold"
              >
                Active
              </span>
            </div>
            <p class="text-xs text-muted-foreground">{{ opt.description }}</p>
          </button>
        </div>
      </section>

      <!-- Export auto-select -->
      <section class="space-y-3">
        <header>
          <h2 class="text-base font-semibold">Auto-select for export</h2>
          <p class="text-sm text-muted-foreground">
            When on, confirmed detections that pass the per-model thresholds get a blue ring on the
            export page to mark them as auto-picked. Their export inclusion still matches whatever
            the reviewer has explicitly toggled; this is a visual cue, not a commit.
          </p>
        </header>

        <label class="inline-flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="checkbox"
            :checked="settings.exportAutoSelect"
            @change="settings.setExportAutoSelect(($event.target as HTMLInputElement).checked)"
          />
          <span>Enable auto-select indicator on export</span>
        </label>

        <div
          class="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2"
          :class="settings.exportAutoSelect ? '' : 'opacity-50 pointer-events-none'"
        >
          <label v-for="row in thresholdRows" :key="row.key" class="space-y-1">
            <span class="text-xs text-muted-foreground">{{ row.label }}</span>
            <input
              type="number"
              min="0"
              max="1"
              step="0.05"
              :value="settings.exportThresholds[row.key]"
              class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm font-mono"
              @change="onThresholdChange(row.key, $event)"
            />
            <span class="block text-[11px] text-muted-foreground">{{ row.help }}</span>
          </label>
        </div>
      </section>

      <!-- Reset -->
      <section class="pt-4 border-t border-border">
        <button
          class="px-3 py-1.5 rounded-md text-sm font-medium border border-border hover:bg-muted"
          @click="settings.reset()"
        >
          Reset to defaults
        </button>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import PageHeader from '@/components/PageHeader.vue'
import {
  usePollinatorSettingsStore,
  type ExportThresholds,
  type ReviewLayout,
} from '@/stores/pollinatorSettings'

const settings = usePollinatorSettingsStore()

interface LayoutOption {
  value: ReviewLayout
  label: string
  description: string
}

const layoutOptions: LayoutOption[] = [
  {
    value: 'crop-first',
    label: 'Crop-first',
    description:
      'Grid of crops grouped by review status and class. Selecting a crop shows its source image with sibling bboxes faded out. Best for tight, high-throughput review.',
  },
  {
    value: 'image-first',
    label: 'Image-first',
    description:
      'Scrollable rail of source images on the left. Selecting an image shows it large with all its crops. Best when context inside the image matters.',
  },
]

interface ThresholdRow {
  key: keyof ExportThresholds
  label: string
  help: string
}

const thresholdRows: ThresholdRow[] = [
  { key: 'yolo', label: 'YOLO confidence', help: 'Detector score from the YOLO branch' },
  {
    key: 'group',
    label: 'Group confidence',
    help: "InsectNet group classifier's probability for the assigned class",
  },
]

function onThresholdChange(key: keyof ExportThresholds, event: Event) {
  const target = event.target as HTMLInputElement
  const v = Number.parseFloat(target.value)
  if (Number.isNaN(v)) return
  settings.setExportThreshold(key, v)
}
</script>
