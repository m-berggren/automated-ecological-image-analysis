<template>
  <!-- Below 1400px viewport the panel column is too narrow for the label plus
       three swatches in a row, so everything stacks vertically (label on top,
       each swatch on its own line). At 1400px+ it lays out in a single row with
       the swatches right-aligned. -->
  <div class="flex flex-col gap-1.5 min-[1400px]:flex-row min-[1400px]:items-center">
    <div class="flex items-center gap-1">
      <span
        class="text-[10px] xl:text-[11px] font-semibold uppercase tracking-wider text-muted-foreground"
      >
        Box colors
      </span>
      <InfoPopover>
        Outline color for annotation boxes on the image. "Box" is the default outline; "Selected"
        is the focused/highlighted box; "ROI" is the region-of-interest outline (also used on the
        Export page). Saved for your account across runs.
      </InfoPopover>
    </div>
    <div
      class="flex flex-col gap-1.5 min-[1400px]:flex-row min-[1400px]:items-center min-[1400px]:gap-3 min-[1400px]:ml-auto"
    >
        <label class="flex items-center gap-1 text-xs cursor-pointer">
          <input
            type="color"
            :value="settings.annotationColor"
            class="w-5 h-5 rounded border border-border bg-transparent cursor-pointer p-0"
            @input="settings.setAnnotationColor(($event.target as HTMLInputElement).value)"
            @change="($event.target as HTMLInputElement).blur()"
          />
          <span class="text-muted-foreground">Box</span>
        </label>
        <label class="flex items-center gap-1 text-xs cursor-pointer">
          <input
            type="color"
            :value="settings.annotationHighlightColor"
            class="w-5 h-5 rounded border border-border bg-transparent cursor-pointer p-0"
            @input="settings.setAnnotationHighlightColor(($event.target as HTMLInputElement).value)"
            @change="($event.target as HTMLInputElement).blur()"
          />
          <span class="text-muted-foreground">Selected</span>
        </label>
        <label class="flex items-center gap-1 text-xs cursor-pointer">
          <input
            type="color"
            :value="settings.roiColor"
            class="w-5 h-5 rounded border border-border bg-transparent cursor-pointer p-0"
            @input="settings.setRoiColor(($event.target as HTMLInputElement).value)"
            @change="($event.target as HTMLInputElement).blur()"
          />
          <span class="text-muted-foreground">ROI</span>
        </label>
    </div>
  </div>
</template>

<script setup lang="ts">
import InfoPopover from '@/components/InfoPopover.vue'
import { usePollinatorSettingsStore } from '@/stores/pollinatorSettings'

// User-level bbox colors (persisted in localStorage, shared across runs). Both
// review layouts read these from the same store, so changing them here updates
// every box overlay live.
const settings = usePollinatorSettingsStore()
</script>
