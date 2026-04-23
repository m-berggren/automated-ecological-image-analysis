<template>
  <PageHeader title="Upload" subtitle="Add seed images to start a detection run" />
  <SeedsStepper current="upload" />

  <div class="flex-1 p-8 space-y-6 max-w-3xl mx-auto w-full">
    <section
      class="rounded-xl border-2 border-dashed border-border bg-surface p-10 text-center transition-colors"
      :class="{ 'border-primary bg-primary/5': dragOver }"
      @dragover.prevent="dragOver = true"
      @dragleave.prevent="dragOver = false"
      @drop.prevent="onDrop"
    >
      <UploadCloud class="w-10 h-10 mx-auto text-muted-foreground" />
      <p class="mt-3 text-sm font-medium">
        Drop seed images here, or
        <label class="text-primary cursor-pointer hover:underline">
          browse
          <input type="file" multiple accept="image/*" class="hidden" @change="onPick" />
        </label>
      </p>
      <p class="text-xs text-muted-foreground mt-1">
        JPG, PNG - uploads
        {{
          uploader.items.length ? `(${doneCount}/${uploader.items.length} done)` : 'in batches of 4'
        }}
      </p>
    </section>

    <section v-if="uploader.items.length" class="rounded-xl border border-border bg-surface">
      <header class="flex items-center justify-between px-5 py-3 border-b border-border">
        <div class="text-sm">
          <span class="font-medium">{{ doneCount }}</span>
          <span class="text-muted-foreground"> of </span>
          <span class="font-medium">{{ uploader.items.length }}</span>
          <span class="text-muted-foreground"> uploaded</span>
          <span v-if="failedCount" class="ml-3 text-red-600"> {{ failedCount }} failed </span>
        </div>
        <div class="flex items-center gap-2">
          <button
            v-if="doneCount"
            @click="uploader.clearDone"
            class="text-xs px-2 py-1 rounded hover:bg-muted text-muted-foreground"
          >
            Clear done
          </button>
          <button
            :disabled="!doneCount || running"
            @click="runInference"
            class="px-3 py-1.5 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <span v-if="!running">Run detection</span>
            <span v-else>Running…</span>
          </button>
        </div>
      </header>
      <ul class="max-h-80 overflow-auto divide-y divide-border">
        <li
          v-for="item in uploader.items"
          :key="item.id"
          class="flex items-center gap-3 px-5 py-2 text-sm"
        >
          <component
            :is="iconFor(item.status)"
            class="w-4 h-4 shrink-0"
            :class="colorFor(item.status)"
          />
          <span class="truncate flex-1">{{ item.file.name }}</span>
          <span class="text-xs text-muted-foreground shrink-0">
            {{ formatSize(item.file.size) }}
          </span>
          <span v-if="item.status === 'failed'" class="text-xs text-red-600 truncate max-w-[200px]">
            {{ item.error }}
          </span>
          <button
            v-if="item.status === 'failed'"
            @click="uploader.retry(item.id)"
            class="text-xs px-2 py-0.5 rounded border border-border hover:bg-muted"
          >
            Retry
          </button>
          <button
            v-if="item.status !== 'uploading'"
            @click="uploader.remove(item.id)"
            class="p-1 rounded hover:bg-muted text-muted-foreground"
            title="Remove"
          >
            <X class="w-3.5 h-3.5" />
          </button>
        </li>
      </ul>
    </section>

    <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import SeedsStepper from '@/components/SeedsStepper.vue'
import { createUploader } from '@/lib/uploader'
import { api } from '@/api'
import { UploadCloud, CheckCircle2, XCircle, Loader2, Clock, X } from 'lucide-vue-next'

const router = useRouter()
const uploader = createUploader({ module: 'seeds' })
const dragOver = ref(false)
const running = ref(false)
const error = ref('')

const doneCount = computed(() => uploader.items.filter((i) => i.status === 'done').length)
const failedCount = computed(() => uploader.items.filter((i) => i.status === 'failed').length)

function onPick(e: Event) {
  const target = e.target as HTMLInputElement
  if (target.files) uploader.enqueue(Array.from(target.files))
  target.value = ''
}

function onDrop(e: DragEvent) {
  dragOver.value = false
  if (e.dataTransfer?.files) uploader.enqueue(Array.from(e.dataTransfer.files))
}

function iconFor(s: string) {
  switch (s) {
    case 'done':
      return CheckCircle2
    case 'failed':
      return XCircle
    case 'uploading':
      return Loader2
    default:
      return Clock
  }
}

function colorFor(s: string) {
  switch (s) {
    case 'done':
      return 'text-green-600'
    case 'failed':
      return 'text-red-600'
    case 'uploading':
      return 'text-primary animate-spin'
    default:
      return 'text-muted-foreground'
  }
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

async function runInference() {
  error.value = ''
  const ids = uploader.items
    .filter((i) => i.status === 'done' && i.imageId !== undefined)
    .map((i) => i.imageId!)
  if (!ids.length) {
    error.value = 'No uploaded images to run on.'
    return
  }
  running.value = true
  try {
    const res = await api('/api/analysis/seeds/inference/', {
      method: 'POST',
      body: JSON.stringify({ image_ids: ids }),
    })
    if (!res.ok) {
      error.value = (await res.text()) || `HTTP ${res.status}`
      return
    }
    const data = await res.json()
    router.push(`/seeds/runs/${data.id}/detect`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    running.value = false
  }
}
</script>
