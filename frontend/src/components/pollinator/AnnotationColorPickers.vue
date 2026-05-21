<template>
  <div class="flex items-center gap-1">
    <span
      class="text-[10px] xl:text-[11px] font-semibold uppercase tracking-wider text-muted-foreground"
    >
      Box colors
    </span>
    <InfoPopover>
      Outline color for annotation boxes on the image. "Box" is the default outline; "Selected" is
      the focused/highlighted box. Saved for your account across runs.
    </InfoPopover>
    <label class="ml-auto flex items-center gap-1 text-xs cursor-pointer">
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
