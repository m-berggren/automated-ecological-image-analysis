<template>
  <Teleport to="body">
    <div
      v-if="state.open"
      class="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      @click.self="onCancel"
      @keydown.esc="onCancel"
    >
      <div class="bg-card border border-border rounded-xl shadow-xl w-full max-w-sm">
        <header v-if="state.title" class="px-5 py-3 border-b border-border">
          <h3 class="font-semibold text-sm">{{ state.title }}</h3>
        </header>
        <div class="px-5 py-4 text-sm whitespace-pre-line">
          {{ state.message }}
        </div>
        <footer class="px-5 py-3 border-t border-border flex items-center justify-end gap-2">
          <button
            v-if="!state.alertOnly"
            ref="cancelBtn"
            class="px-3 py-1.5 rounded-md text-sm font-medium text-muted-foreground hover:bg-muted"
            @click="onCancel"
          >
            {{ state.cancelLabel }}
          </button>
          <button
            ref="confirmBtn"
            class="px-3 py-1.5 rounded-md text-sm font-medium text-primary-foreground"
            :class="
              state.variant === 'danger'
                ? 'bg-red-600 hover:bg-red-700'
                : 'bg-primary hover:bg-primary/90'
            "
            @click="onConfirm"
          >
            {{ state.confirmLabel }}
          </button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { confirmState, resolveConfirm } from '@/lib/confirm'

const state = confirmState()
const cancelBtn = ref<HTMLButtonElement | null>(null)
const confirmBtn = ref<HTMLButtonElement | null>(null)

function onConfirm() {
  resolveConfirm(true)
}
function onCancel() {
  // In alert mode there is no Cancel button; treat dismiss (Esc / backdrop)
  // the same as pressing OK so the caller's promise always resolves.
  resolveConfirm(state.alertOnly)
}

// Focus Cancel by default so an accidental Enter doesn't fire a destructive
// action. In alert mode there's no Cancel, so focus the (only) OK button.
watch(
  () => state.open,
  async (open) => {
    if (open) {
      await nextTick()
      if (state.alertOnly) confirmBtn.value?.focus()
      else cancelBtn.value?.focus()
    }
  },
)
</script>
