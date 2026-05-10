<template>
  <PageHeader :title="headerTitle" subtitle="Confirm or reject seed detections" />
  <SeedsStepper current="review" :runId="run?.id" />

  <div v-if="loading" class="flex-1 p-8 text-sm text-muted-foreground">Loading…</div>
  <div v-else-if="loadError" class="flex-1 p-8 text-sm text-red-600">{{ loadError }}</div>

  <div v-else class="flex-1 flex flex-col-reverse lg:flex-row min-h-0">

    <!-- Left: grid of detections -->
    <section
      class="w-full lg:w-[480px] shrink-0 border-t lg:border-t-0 lg:border-r border-border flex flex-col bg-surface max-h-[55vh] lg:max-h-none"
    >
      <div class="px-4 py-3 border-b border-border space-y-2">
        <div class="flex items-center gap-2 text-xs">
          <label class="text-muted-foreground">Show</label>
          <select
            v-model="statusFilter"
            class="px-2 py-1 rounded border border-border bg-background"
          >
            <option value="unreviewed">Unreviewed</option>
            <option value="all">All</option>
            <option value="reviewed">Reviewed</option>
          </select>
        </div>
        <div class="text-xs text-muted-foreground flex items-center justify-between">
          <span>{{ filteredDetections.length }} of {{ detections.length }} detections</span>
          <button
            class="text-primary hover:underline"
            :disabled="!filteredDetections.length"
            @click="selectAllVisible"
          >
            Select all
          </button>
        </div>
      </div>

      <!-- Bulk action bar -->
      <div
        v-if="bulkIds.size > 0"
        class="px-4 py-2 border-b border-border bg-primary/5 flex items-center gap-2 text-xs"
      >
        <span class="font-medium">{{ bulkIds.size }} selected</span>
        <button
          class="px-2 py-1 rounded bg-primary text-primary-foreground hover:bg-primary/90"
          @click="bulkConfirm"
        >
          Confirm
        </button>
        <button
          class="px-2 py-1 rounded border border-border hover:bg-muted"
          @click="bulkReject"
        >
          Reject
        </button>
        <button class="ml-auto text-muted-foreground hover:text-foreground" @click="clearBulk">
          Clear
        </button>
      </div>

      <div class="flex-1 overflow-auto">
        <div class="grid grid-cols-5 gap-1 p-2">
          <div
            v-for="d in filteredDetections"
            :key="d.id"
            class="rounded-md overflow-hidden border-2 transition-all"
            :class="[
              selectedId === d.id
                ? 'border-primary ring-2 ring-primary'
                : 'border-transparent hover:border-border',
              d.reviewer_status !== 'unreviewed' ? 'opacity-50' : '',
            ]"
          >
            <div
              :data-detection-id="d.id"
              role="button"
              tabindex="0"
              class="relative aspect-square cursor-pointer focus:outline-none bg-eco-mint/30 flex items-center justify-center"
              @click="selectedId = d.id"
              @keydown.enter.prevent="selectedId = d.id"
            >
              <span class="text-2xl opacity-40">🌱</span>
              <span
                class="absolute top-1 left-1 w-2 h-2 rounded-full"
                :class="statusDotClass(d.reviewer_status)"
              />
              <span class="absolute bottom-1 right-1 text-[9px] font-mono text-muted-foreground/70">
                {{ d.confidence.toFixed(2) }}
              </span>
            </div>
            <div
              role="checkbox"
              :aria-checked="bulkIds.has(d.id)"
              tabindex="0"
              class="h-5 flex items-center justify-center text-xs cursor-pointer transition-colors"
              :class="
                bulkIds.has(d.id)
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-surface text-muted-foreground hover:bg-muted'
              "
              @click="toggleBulk(d.id)"
              @keydown.space.prevent="toggleBulk(d.id)"
            >
              <span v-if="bulkIds.has(d.id)">✓</span>
            </div>
          </div>
        </div>
        <div v-if="!filteredDetections.length" class="p-8 text-center text-sm text-muted-foreground">
          No detections match the current filter.
        </div>
      </div>
    </section>

    <!-- Right: detail pane -->
    <section class="flex-1 flex flex-col min-w-0">
      <div v-if="!selected" class="m-auto text-sm text-muted-foreground">
        Select a detection on the left to review it.
      </div>
      <template v-else>
        <header class="px-5 py-3 border-b border-border bg-surface text-sm flex items-center gap-3">
          <span class="font-medium">Detection #{{ selected.id }}</span>
          <span class="text-muted-foreground font-mono text-xs truncate">
            {{ selected.source_image_filename }}
          </span>
          <span
            class="ml-auto text-xs px-2 py-0.5 rounded-full shrink-0"
            :class="statusBadgeClass(selected.reviewer_status)"
          >
            {{ statusLabel(selected.reviewer_status) }}
          </span>
        </header>

        <div class="flex-1 overflow-auto">
          <!-- Crop preview -->
          <div class="aspect-video flex items-center justify-center text-7xl bg-eco-mint/20 relative">
            <span class="opacity-30">🌱</span>
          </div>

          <!-- Stats -->
          <div class="px-5 py-4 border-b border-border space-y-3">
            <div class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Detection details
            </div>
            <dl class="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
              <div>
                <dt class="text-xs text-muted-foreground">Confidence</dt>
                <dd class="font-mono font-medium">{{ selected.confidence.toFixed(3) }}</dd>
              </div>
              <div>
                <dt class="text-xs text-muted-foreground">Area (px²)</dt>
                <dd class="font-mono font-medium">{{ selected.area.toLocaleString() }}</dd>
              </div>
              <div v-if="selected.length_mm">
                <dt class="text-xs text-muted-foreground">Length</dt>
                <dd class="font-mono font-medium">{{ selected.length_mm.toFixed(1) }} mm</dd>
              </div>
              <div v-if="selected.width_mm">
                <dt class="text-xs text-muted-foreground">Width</dt>
                <dd class="font-mono font-medium">{{ selected.width_mm.toFixed(1) }} mm</dd>
              </div>
              <div v-if="selected.viability_status">
                <dt class="text-xs text-muted-foreground">Viability</dt>
                <dd
                  class="font-medium"
                  :class="selected.viability_status === 'Active' ? 'text-green-600' : 'text-red-500'"
                >
                  {{ selected.viability_status }}
                </dd>
              </div>
            </dl>
          </div>
        </div>

        <!-- Action bar -->
        <footer class="border-t border-border bg-surface px-5 py-3 flex items-center justify-between">
          <span class="text-[11px] text-muted-foreground font-mono hidden md:block">
            ↵ confirm · x reject · ↑↓ navigate
          </span>
          <div class="flex gap-2 ml-auto">
            <button
              class="px-3 py-1.5 rounded-md text-sm font-medium border border-border hover:bg-muted"
              @click="reject"
            >
              Reject
            </button>
            <button
              class="px-3 py-1.5 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90"
              @click="confirm"
            >
              Confirm seed
            </button>
          </div>
        </footer>
      </template>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import SeedsStepper from '@/components/SeedsStepper.vue'
import { api } from '@/api'

type ReviewerStatus = 'unreviewed' | 'confirmed' | 'rejected'

interface Detection {
  id: number
  confidence: number
  area: number
  length_mm?: number
  width_mm?: number
  viability_status?: 'Active' | 'Aborted'
  reviewer_status: ReviewerStatus
  source_image_filename: string
}

interface ReviewBundle {
  run: { id: number; name: string; status: string; detection_count: number }
  detections: Detection[]
}

const route = useRoute()
const loading = ref(true)
const loadError = ref('')
const run = ref<ReviewBundle['run'] | null>(null)
const detections = ref<Detection[]>([])
const selectedId = ref<number | null>(null)
const statusFilter = ref<'unreviewed' | 'all' | 'reviewed'>('unreviewed')
const bulkIds = ref<Set<number>>(new Set())

const previewMode = computed<string | null>(() => {
  const value = route.query.preview
  return typeof value === 'string' ? value : null
})

onMounted(async () => {
  if (previewMode.value) {
    const bundle = await loadPreview(previewMode.value)
    if (bundle) {
      run.value = bundle.run
      detections.value = bundle.detections
      loading.value = false
      return
    }
  }
  await loadFromApi()
})

async function loadPreview(_mode: string): Promise<ReviewBundle | null> {
  if (!import.meta.env.DEV) return null
  const { default: mocks } = await import('@/mocks/seed-detections.json')
  const bundle = (mocks as Record<string, ReviewBundle | undefined>).default
  if (!bundle) return null
  return JSON.parse(JSON.stringify(bundle))
}

async function loadFromApi() {
  const id = route.params.id as string
  try {
    const [runRes, detRes] = await Promise.all([
      api(`/api/analysis/runs/${id}/`),
      api(`/api/analysis/runs/${id}/detections/`),
    ])
    if (!runRes.ok) { loadError.value = `Run: HTTP ${runRes.status}`; return }
    if (!detRes.ok) { loadError.value = `Detections: HTTP ${detRes.status}`; return }
    run.value = await runRes.json()
    detections.value = await detRes.json()
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

const headerTitle = computed(() =>
  run.value ? `Review · ${run.value.name || `Run #${run.value.id}`}` : 'Review'
)

const filteredDetections = computed(() => {
  let list = detections.value
  if (statusFilter.value === 'unreviewed')
    list = list.filter((d) => d.reviewer_status === 'unreviewed')
  else if (statusFilter.value === 'reviewed')
    list = list.filter((d) => d.reviewer_status !== 'unreviewed')
  return [...list].sort((a, b) => a.confidence - b.confidence)
})

const selected = computed(() =>
  detections.value.find((d) => d.id === selectedId.value) ?? null
)

watch(filteredDetections, (list) => {
  if (selectedId.value && !list.find((d) => d.id === selectedId.value)) {
    selectedId.value = list[0]?.id ?? null
  } else if (!selectedId.value && list.length) {
    selectedId.value = list[0].id
  }
}, { immediate: true })

watch(selectedId, async (id) => {
  if (id == null) return
  await nextTick()
  document.querySelector(`[data-detection-id="${id}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
})

function statusDotClass(s: ReviewerStatus): string {
  switch (s) {
    case 'confirmed': return 'bg-green-500'
    case 'rejected':  return 'bg-red-500'
    default:          return 'bg-muted-foreground/40'
  }
}
function statusBadgeClass(s: ReviewerStatus): string {
  switch (s) {
    case 'confirmed': return 'bg-green-100 text-green-700'
    case 'rejected':  return 'bg-red-100 text-red-700'
    default:          return 'bg-muted text-muted-foreground'
  }
}
function statusLabel(s: ReviewerStatus): string {
  return s[0].toUpperCase() + s.slice(1)
}

function applyAction(status: ReviewerStatus) {
  if (!selected.value) return
  selected.value.reviewer_status = status
  advanceToNext()
}

function confirm() { applyAction('confirmed') }
function reject()  { applyAction('rejected') }

function toggleBulk(id: number) {
  const next = new Set(bulkIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  bulkIds.value = next
}
function clearBulk() { bulkIds.value = new Set() }
function selectAllVisible() {
  bulkIds.value = new Set(filteredDetections.value.map((d) => d.id))
}
function bulkConfirm() {
  for (const d of detections.value) {
    if (bulkIds.value.has(d.id)) d.reviewer_status = 'confirmed'
  }
  clearBulk()
}
function bulkReject() {
  for (const d of detections.value) {
    if (bulkIds.value.has(d.id)) d.reviewer_status = 'rejected'
  }
  clearBulk()
}

function advanceToNext() {
  const list = filteredDetections.value
  const idx = list.findIndex((d) => d.id === selectedId.value)
  if (idx >= 0 && idx + 1 < list.length) selectedId.value = list[idx + 1].id
}

function navigate(delta: number) {
  const list = filteredDetections.value
  const idx = list.findIndex((d) => d.id === selectedId.value)
  if (idx < 0) return
  const next = list[Math.max(0, Math.min(list.length - 1, idx + delta))]
  if (next) selectedId.value = next.id
}

function onKeydown(e: KeyboardEvent) {
  if (!selected.value) return
  if (e.target instanceof HTMLElement && ['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return
  switch (e.key) {
    case 'Enter':     confirm(); e.preventDefault(); break
    case 'x': case 'X': reject(); e.preventDefault(); break
    case 'ArrowDown': case 'j': navigate(1); e.preventDefault(); break
    case 'ArrowUp':   case 'k': navigate(-1); e.preventDefault(); break
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>