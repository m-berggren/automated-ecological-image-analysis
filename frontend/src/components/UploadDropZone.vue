<template>
  <div>
    <!-- Tabs (only when more than one mode is configured). Switching the
         active tab swaps which hidden input the box click triggers. -->
    <div
      v-if="tabs.length > 1"
      class="inline-flex rounded border border-border overflow-hidden text-xs mb-2"
    >
      <button
        v-for="t in tabs"
        :key="t.key"
        type="button"
        :class="
          activeKey === t.key
            ? 'bg-primary text-primary-foreground'
            : 'bg-background hover:bg-muted'
        "
        class="px-3 py-1.5"
        @click="setActive(t.key)"
      >
        {{ t.label }}
      </button>
    </div>

    <div
      class="relative rounded-xl border-2 border-dashed text-center transition-colors select-none"
      :class="[boxClass, compact ? 'p-3' : 'p-6']"
      role="button"
      tabindex="0"
      @click="triggerActive"
      @keydown.enter.prevent="triggerActive"
      @keydown.space.prevent="triggerActive"
      @dragover.prevent="dragOver = true"
      @dragleave.prevent="dragOver = false"
      @drop.prevent="onDrop"
    >
      <slot name="body" :has-files="hasFiles" :active="active">
        <UploadCloud
          :class="compact ? 'w-6 h-6' : 'w-10 h-10'"
          class="mx-auto text-muted-foreground"
        />
        <p :class="compact ? 'mt-1 text-xs' : 'mt-3 text-sm'" class="font-medium">
          {{ activePlaceholder }}
        </p>
        <p
          v-if="activeHelper"
          :class="compact ? 'text-[11px] mt-0.5' : 'text-xs mt-1'"
          class="text-muted-foreground"
        >
          {{ activeHelper }}
        </p>
      </slot>

      <!-- One hidden input per tab so we can swap which file dialog opens
           without recreating the input (which would lose its
           webkitdirectory attribute on some browsers). -->
      <input
        v-for="t in tabs"
        :key="t.key"
        :ref="(el) => bindInput(t.key, el as HTMLInputElement | null)"
        type="file"
        :multiple="t.mode !== 'single-file'"
        :accept="t.accept || ''"
        class="hidden"
        @change="onPick($event, t)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { UploadCloud } from 'lucide-vue-next'

export type UploadMode = 'files' | 'folder' | 'single-file'

export interface UploadTab {
  key: string
  label: string
  mode: UploadMode
  accept?: string
  placeholder?: string
  helper?: string
}

const props = withDefaults(
  defineProps<{
    tabs: UploadTab[]
    activeTab?: string
    hasFiles?: boolean
    placeholder?: string
    helper?: string
    disabled?: boolean
    // Reduces padding, icon, and text sizes for use inside dialogs where
    // vertical space is tight. Callsites without this prop are unchanged.
    compact?: boolean
  }>(),
  {
    activeTab: undefined,
    hasFiles: false,
    placeholder: 'Drop files here or click to browse',
    helper: '',
    disabled: false,
    compact: false,
  },
)

const emit = defineEmits<{
  (e: 'update:activeTab', key: string): void
  (e: 'select', files: File[], tabKey: string): void
}>()

const internalActive = ref(props.activeTab ?? props.tabs[0]?.key ?? '')
watch(
  () => props.activeTab,
  (k) => {
    if (k && k !== internalActive.value) internalActive.value = k
  },
)

const activeKey = computed(() => internalActive.value)
const active = computed<UploadTab | undefined>(() =>
  props.tabs.find((t) => t.key === activeKey.value),
)
const activePlaceholder = computed(() => active.value?.placeholder ?? props.placeholder)
const activeHelper = computed(() => active.value?.helper ?? props.helper)

function setActive(key: string) {
  internalActive.value = key
  emit('update:activeTab', key)
}

const dragOver = ref(false)
const inputRefs = ref<Record<string, HTMLInputElement | null>>({})

function bindInput(key: string, el: HTMLInputElement | null) {
  inputRefs.value[key] = el
}

// webkitdirectory has to be set as a DOM attribute (Vue's prop-type checker
// rejects the non-standard prop). Re-apply whenever the input mounts.
function applyFolderAttrs() {
  for (const t of props.tabs) {
    const el = inputRefs.value[t.key]
    if (!el) continue
    if (t.mode === 'folder') {
      el.setAttribute('webkitdirectory', '')
      el.setAttribute('directory', '')
    } else {
      el.removeAttribute('webkitdirectory')
      el.removeAttribute('directory')
    }
  }
}

onMounted(() => {
  nextTick(applyFolderAttrs)
})
watch(
  () => props.tabs.map((t) => `${t.key}:${t.mode}`).join('|'),
  () => nextTick(applyFolderAttrs),
)

const boxClass = computed(() => {
  if (props.disabled) return 'border-border bg-muted/20 opacity-60 cursor-not-allowed'
  if (dragOver.value) return 'border-primary bg-primary/10 cursor-pointer'
  if (props.hasFiles) return 'border-primary bg-primary/5 cursor-pointer hover:bg-primary/10'
  return 'border-border cursor-pointer hover:border-primary/50 hover:bg-muted/30'
})

function triggerActive() {
  if (props.disabled) return
  const t = active.value
  if (!t) return
  inputRefs.value[t.key]?.click()
}

function onPick(e: Event, tab: UploadTab) {
  const target = e.target as HTMLInputElement
  if (!target.files || !target.files.length) return
  const files = Array.from(target.files)
  emit('select', files, tab.key)
  // Reset so picking the same path twice still fires change.
  target.value = ''
}

interface FsEntryReader {
  readEntries: (cb: (entries: FsEntry[]) => void) => void
}
interface FsEntry {
  isFile: boolean
  isDirectory: boolean
  file?: (cb: (f: File) => void) => void
  createReader?: () => FsEntryReader
}

function traverse(entry: FsEntry, out: File[], done: () => void) {
  if (entry.isFile && entry.file) {
    entry.file((f) => {
      out.push(f)
      done()
    })
    return
  }
  if (entry.isDirectory && entry.createReader) {
    const reader = entry.createReader()
    let pending = 1
    const finish = () => {
      pending -= 1
      if (pending === 0) done()
    }
    const readBatch = () => {
      reader.readEntries((entries: FsEntry[]) => {
        if (!entries.length) {
          finish()
          return
        }
        pending += entries.length
        for (const sub of entries) traverse(sub, out, finish)
        readBatch()
      })
    }
    readBatch()
    return
  }
  done()
}

function onDrop(e: DragEvent) {
  dragOver.value = false
  if (props.disabled) return
  const t = active.value
  if (!t) return
  const items = e.dataTransfer?.items
  // webkitGetAsEntry recurses into dropped folders; supported in Chromium
  // and Firefox. Fall back to the flat dataTransfer.files list when absent.
  if (items && items.length && typeof items[0].webkitGetAsEntry === 'function') {
    const out: File[] = []
    let pending = items.length
    const settle = () => {
      pending -= 1
      if (pending === 0 && out.length) emit('select', out, t.key)
    }
    for (const item of Array.from(items)) {
      const entry = item.webkitGetAsEntry?.() as FsEntry | null
      if (entry) traverse(entry, out, settle)
      else settle()
    }
    return
  }
  if (e.dataTransfer?.files?.length) {
    emit('select', Array.from(e.dataTransfer.files), t.key)
  }
}
</script>
