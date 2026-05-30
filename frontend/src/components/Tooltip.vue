<template>
  <span
    ref="root"
    class="inline-flex"
    @mouseenter="onEnter"
    @mouseleave="onLeave"
    @focusin="onEnter"
    @focusout="onLeave"
  >
    <slot />
    <Teleport to="body">
      <Transition name="tt-pop">
        <div
          v-if="open && hasContent"
          ref="panel"
          role="tooltip"
          class="fixed z-50 max-w-xs rounded-md border border-border bg-card px-2.5 py-1.5 text-xs leading-snug text-foreground shadow-md whitespace-normal pointer-events-none"
          :style="{ top: `${pos.top}px`, left: `${pos.left}px` }"
        >
          <slot name="content">{{ text }}</slot>
        </div>
      </Transition>
    </Teleport>
  </span>
</template>

<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, useSlots } from 'vue'

const props = withDefaults(
  defineProps<{
    text?: string
    // Delay before showing on hover, in ms. 0 for instant.
    delay?: number
  }>(),
  { delay: 250 },
)

const slots = useSlots()
const hasContent = computed(() => !!props.text || !!slots.content)

const open = ref(false)
const root = ref<HTMLElement | null>(null)
const panel = ref<HTMLElement | null>(null)
const pos = ref({ top: 0, left: 0 })

const MARGIN = 8
let showTimer: number | null = null

function reposition() {
  const t = root.value
  const p = panel.value
  if (!t || !p) return
  const tr = t.getBoundingClientRect()
  const pw = p.offsetWidth
  const ph = p.offsetHeight
  const vw = window.innerWidth
  const vh = window.innerHeight

  // Prefer below the trigger; flip above if there's no room. Horizontally
  // anchor centered on the trigger, clamped to the viewport.
  let left = tr.left + tr.width / 2 - pw / 2
  left = Math.max(MARGIN, Math.min(left, vw - pw - MARGIN))

  let top = tr.bottom + 4
  if (top + ph > vh - MARGIN && tr.top - 4 - ph > MARGIN) {
    top = tr.top - 4 - ph
  }
  pos.value = { top, left }
}

function clearShowTimer() {
  if (showTimer != null) {
    window.clearTimeout(showTimer)
    showTimer = null
  }
}

async function onEnter() {
  if (!hasContent.value) return
  clearShowTimer()
  showTimer = window.setTimeout(async () => {
    open.value = true
    await nextTick()
    reposition()
  }, props.delay)
}

function onLeave() {
  clearShowTimer()
  open.value = false
}

function onScrollOrResize() {
  if (open.value) reposition()
}

window.addEventListener('scroll', onScrollOrResize, true)
window.addEventListener('resize', onScrollOrResize)

onUnmounted(() => {
  clearShowTimer()
  window.removeEventListener('scroll', onScrollOrResize, true)
  window.removeEventListener('resize', onScrollOrResize)
})
</script>

<style scoped>
.tt-pop-enter-active,
.tt-pop-leave-active {
  transition:
    opacity 100ms ease,
    transform 100ms ease;
}
.tt-pop-enter-from,
.tt-pop-leave-to {
  opacity: 0;
  transform: translateY(-2px);
}
</style>
