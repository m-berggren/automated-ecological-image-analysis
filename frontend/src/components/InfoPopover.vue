<template>
  <span ref="root" class="inline-block leading-none">
    <button
      ref="trigger"
      type="button"
      aria-label="More info"
      class="inline-flex items-center text-muted-foreground hover:text-foreground focus:text-foreground focus:outline-none"
      @click.stop="toggle"
    >
      <Info class="w-3.5 h-3.5" />
    </button>
    <Teleport to="body">
      <Transition name="info-pop">
        <div
          v-if="open"
          ref="panel"
          class="fixed z-50 w-64 rounded-md border border-border bg-card p-2.5 text-xs leading-relaxed text-foreground shadow-md whitespace-normal"
          :style="{ top: `${pos.top}px`, left: `${pos.left}px` }"
        >
          <slot />
        </div>
      </Transition>
    </Teleport>
  </span>
</template>

<script setup lang="ts">
import { nextTick, onUnmounted, ref } from 'vue'
import { Info } from 'lucide-vue-next'

const open = ref(false)
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const panel = ref<HTMLElement | null>(null)
const pos = ref({ top: 0, left: 0 })

// Render in the body via Teleport with position:fixed so the popover
// escapes every overflow-y-auto / overflow-hidden ancestor. We then
// compute viewport-relative coords from the trigger button's rect on
// open (and on scroll/resize while open), flipping the anchor side or
// stacking above the trigger when there isn't room.
const MARGIN = 8

function reposition() {
  const t = trigger.value
  const p = panel.value
  if (!t || !p) return
  const tr = t.getBoundingClientRect()
  const pw = p.offsetWidth
  const ph = p.offsetHeight
  const vw = window.innerWidth
  const vh = window.innerHeight

  // Horizontal: prefer aligning the popover's left edge with the trigger's
  // left edge. If that overflows the viewport on the right, right-align it
  // to the trigger instead. Clamp to the viewport as a final guard.
  let left = tr.left
  if (left + pw > vw - MARGIN) left = tr.right - pw
  left = Math.max(MARGIN, Math.min(left, vw - pw - MARGIN))

  // Vertical: below the trigger by default, above if there's no room.
  let top = tr.bottom + 4
  if (top + ph > vh - MARGIN && tr.top - 4 - ph > MARGIN) {
    top = tr.top - 4 - ph
  }

  pos.value = { top, left }
}

async function toggle() {
  if (open.value) {
    open.value = false
    return
  }
  open.value = true
  await nextTick()
  reposition()
}

function onDocClick(e: MouseEvent) {
  if (!open.value) return
  if (root.value?.contains(e.target as Node)) return
  if (panel.value?.contains(e.target as Node)) return
  open.value = false
}

function onScrollOrResize() {
  if (open.value) reposition()
}

document.addEventListener('mousedown', onDocClick)
window.addEventListener('scroll', onScrollOrResize, true)
window.addEventListener('resize', onScrollOrResize)

onUnmounted(() => {
  document.removeEventListener('mousedown', onDocClick)
  window.removeEventListener('scroll', onScrollOrResize, true)
  window.removeEventListener('resize', onScrollOrResize)
})
</script>

<style scoped>
.info-pop-enter-active,
.info-pop-leave-active {
  transition:
    opacity 120ms ease,
    transform 120ms ease;
}
.info-pop-enter-from,
.info-pop-leave-to {
  opacity: 0;
  transform: translateY(-2px);
}
</style>
