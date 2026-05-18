<template>
  <div
    v-if="modelValue"
    class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
    role="dialog"
    aria-modal="true"
    @click="close"
    @keydown.esc="close"
  >
    <div
      @click.stop
      class="w-full max-w-md p-6 rounded-[var(--radius)] shadow-lg animate-fade-in bg-surface text-foreground border border-border"
    >
      <h2 class="text-lg font-semibold mb-1 font-display">CSV Export Options</h2>
      <p class="text-sm text-muted-foreground mb-4">
        Choose how you want your CSV to be structured.
      </p>

      <div class="space-y-3">
        <label
          class="flex items-center gap-3 cursor-pointer p-3 rounded-md border bg-muted hover:bg-primary/20 transition"
        >
          <input
            type="radio"
            value="per_detection"
            v-model="mode"
            class="accent-[var(--color-primary)]"
          />
          <span>Row per detection</span>
        </label>

        <label
          class="flex items-center gap-3 cursor-pointer p-3 rounded-md border bg-muted hover:bg-primary/20 transition"
        >
          <input
            type="radio"
            value="per_image"
            v-model="mode"
            class="accent-[var(--color-primary)]"
          />
          <span>Row per image</span>
        </label>
      </div>

      <div class="mt-6 flex justify-end gap-2">
        <button
          class="px-4 py-2 rounded-md border border-border text-muted-foreground hover:bg-muted transition"
          @click="close"
        >
          Cancel
        </button>
        <button
          class="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:opacity-90 transition disabled:opacity-50"
          :disabled="!mode"
          @click="onConfirm"
        >
          Download
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

export type CsvExportMode = 'per_image' | 'per_detection'

defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: [mode: CsvExportMode]
}>()

// Per-detection is the more detailed default; reviewers downgrade to
// per-image when they want one survey row per photo.
const mode = ref<CsvExportMode>('per_detection')

function close() {
  emit('update:modelValue', false)
}

function onConfirm() {
  // Emit 'confirm' BEFORE closing so any consumer state tied to the
  // open flag (e.g. a selected row id) is still readable while the
  // confirm handler runs. Closing first would race the v-model setter
  // against the confirm listener.
  emit('confirm', mode.value)
  emit('update:modelValue', false)
}
</script>
