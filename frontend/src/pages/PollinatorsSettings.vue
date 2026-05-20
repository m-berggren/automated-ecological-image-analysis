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

      <!-- Reset -->
      <section class="pt-4 border-t border-border">
        <button
          class="px-3 py-1.5 rounded-md text-sm font-medium border border-border hover:bg-muted"
          @click="settings.resetLayout()"
        >
          Reset layout to default
        </button>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import PageHeader from '@/components/PageHeader.vue'
import { usePollinatorSettingsStore, type ReviewLayout } from '@/stores/pollinatorSettings'

const settings = usePollinatorSettingsStore()

interface LayoutOption {
  value: ReviewLayout
  label: string
  description: string
}

const layoutOptions: LayoutOption[] = [
  {
    value: 'image-first',
    label: 'Image-first',
    description:
      'Scrollable rail of source images on the left. Selecting an image shows it large with all its crops. Best when context inside the image matters.',
  },
  {
    value: 'crop-first',
    label: 'Crop-first',
    description:
      'Grid of crops grouped by review status and class. Selecting a crop shows its source image with sibling bboxes faded out. Best for tight, high-throughput review.',
  },
]
</script>
