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
            Pick how the review page is organized. Both layouts show the same data, the difference
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

        <button
          class="px-3 py-1.5 rounded-md text-sm font-medium border border-border hover:bg-muted"
          @click="settings.resetLayout()"
        >
          Reset layout to default
        </button>
      </section>

      <!-- Review shortcuts -->
      <section class="space-y-3">
        <header>
          <h2 class="text-base font-semibold">Review shortcuts</h2>
          <p class="text-sm text-muted-foreground">
            Single-key shortcuts for the review page. Click a key, then press the key you want.
          </p>
        </header>

        <ul class="divide-y divide-border rounded-lg border border-border">
          <li
            v-for="action in reviewActions"
            :key="action"
            class="flex items-center justify-between gap-3 px-4 py-2.5"
          >
            <span class="text-sm">{{ actionLabels[action] }}</span>
            <button
              class="min-w-[6rem] px-2 py-1 rounded-md border text-sm font-mono text-center"
              :class="
                listeningAction === action
                  ? 'border-primary text-primary animate-pulse'
                  : 'border-border hover:bg-muted'
              "
              @click="startRebind(action)"
            >
              {{ listeningAction === action ? 'Press a key…' : keyDisplay(action) }}
            </button>
          </li>
        </ul>
        <p v-if="bindNote" class="text-xs text-red-600">{{ bindNote }}</p>

        <button
          class="px-3 py-1.5 rounded-md text-sm font-medium border border-border hover:bg-muted"
          @click="settings.resetKeybindings()"
        >
          Reset shortcuts to defaults
        </button>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import PageHeader from '@/components/PageHeader.vue'
import {
  usePollinatorSettingsStore,
  REVIEW_ACTIONS,
  REVIEW_ACTION_LABELS,
  type ReviewLayout,
  type ReviewAction,
} from '@/stores/pollinatorSettings'

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

// --- Review shortcuts ------------------------------------------------------
const reviewActions = REVIEW_ACTIONS
const actionLabels = REVIEW_ACTION_LABELS

// When an action is "listening", the next keydown becomes its shortcut.
// Escape cancels; reserved/invalid keys surface a transient note.
const listeningAction = ref<ReviewAction | null>(null)
const bindNote = ref('')

function startRebind(action: ReviewAction) {
  bindNote.value = ''
  listeningAction.value = action
}

function keyDisplay(action: ReviewAction): string {
  const k = settings.keybindings[action]
  return k ? k.toUpperCase() : '—'
}

function onRebindKeydown(e: KeyboardEvent) {
  const action = listeningAction.value
  if (!action) return
  e.preventDefault()
  e.stopPropagation()
  if (e.key === 'Escape') {
    listeningAction.value = null
    return
  }
  // Single printable character only; ignore modifier-only presses.
  if (e.key.length !== 1) {
    bindNote.value = 'Pick a single character key.'
    return
  }
  const result = settings.setKeybinding(action, e.key)
  if (result === 'reserved') {
    bindNote.value = `"${e.key}" is reserved for navigation / undo / confirm.`
    return
  }
  if (result === 'invalid') {
    bindNote.value = 'Invalid key.'
    return
  }
  listeningAction.value = null
}

// Capture phase so a rebind keypress is intercepted before anything else.
onMounted(() => window.addEventListener('keydown', onRebindKeydown, true))
onUnmounted(() => window.removeEventListener('keydown', onRebindKeydown, true))
</script>
