<template>
  <aside class="w-32 shrink-0 border-r border-border bg-background overflow-y-auto p-2">
    <div v-if="!items.length" class="text-xs text-muted-foreground italic px-1 py-2">
      {{ emptyMessage }}
    </div>
    <div v-else class="flex flex-col gap-2">
      <button
        v-for="item in items"
        :key="item.key"
        :ref="(el) => setItemRef(el, item.key)"
        class="block w-full text-left relative focus:outline-none hover:opacity-90 border-2 rounded-md overflow-hidden transition-shadow"
        :class="
          item.key === activeKey
            ? 'border-transparent bg-border ring-[3px] ring-green-800 ring-offset-2 ring-offset-background shadow-md z-10'
            : (item.accentClass ?? 'border-border')
        "
        :title="item.title ?? item.label ?? item.key"
        @click="emit('update:activeKey', item.key)"
      >
        <div v-if="item.label" class="px-1 pt-0.5 text-[10px] font-mono font-bold truncate">
          {{ item.label }}
        </div>
        <div class="relative bg-background" :style="{ aspectRatio: item.aspectRatio ?? '4 / 3' }">
          <img
            v-if="item.src"
            :src="item.src"
            :alt="item.label ?? item.key"
            loading="lazy"
            class="absolute inset-0 w-full h-full object-cover"
          />
          <div
            v-else
            class="absolute inset-0 flex items-center justify-center text-[10px] text-muted-foreground"
          >
            n/a
          </div>
        </div>
        <div v-if="item.caption" class="px-1 pb-0.5 text-[10px] text-muted-foreground truncate">
          {{ item.caption }}
        </div>
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { nextTick, watch, type ComponentPublicInstance } from 'vue'

export interface RailItem {
  key: string
  label?: string
  src: string | null
  // CSS aspect-ratio value, default '4 / 3'. Override per-item when
  // you've preloaded natural dimensions to avoid tile reflow.
  aspectRatio?: string
  caption?: string
  title?: string
  // Tailwind class(es) for the tile's outer border, e.g.
  // 'border-red-500'. Omit to keep the transparent default so the tile
  // doesn't shift versus its neighbours.
  accentClass?: string
}

const props = defineProps<{
  items: RailItem[]
  activeKey: string | null
  emptyMessage?: string
}>()

const emit = defineEmits<{
  (e: 'update:activeKey', key: string): void
}>()

const itemEls: Record<string, HTMLElement | null> = {}

function setItemRef(el: Element | ComponentPublicInstance | null, key: string) {
  itemEls[key] = el as HTMLElement | null
}

// Keep the active tile in view when the parent changes selection
// (click on a bbox, keyboard arrow, filter switch, etc.).
watch(
  () => props.activeKey,
  async (k) => {
    if (!k) return
    await nextTick()
    itemEls[k]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  },
)
</script>
