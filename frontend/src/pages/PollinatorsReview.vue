<template>
  <PageHeader :title="headerTitle" subtitle="Confirm, correct, or reject detections" />
  <PollinatorsStepper current="review" :runId="run?.id" />

  <div v-if="loading" class="flex-1 p-8 text-sm text-muted-foreground">Loading…</div>
  <div v-else-if="loadError" class="flex-1 p-8 text-sm text-red-600">{{ loadError }}</div>

  <div v-else class="flex-1 flex flex-col-reverse lg:flex-row min-h-0">
    <!-- Left: filters + grouped grid -->
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
          <label class="ml-auto flex items-center gap-1 text-muted-foreground">
            <input v-model="disagreementsOnly" type="checkbox" />
            Disagreements only
          </label>
        </div>
        <div class="text-xs text-muted-foreground flex items-center justify-between">
          <span>
            {{ filteredDetections.length }} of {{ detections.length }} detections ·
            sorted by ascending InsectNet confidence
          </span>
          <button
            class="text-primary hover:underline"
            :disabled="!filteredDetections.length"
            @click="selectAllVisible"
          >
            Select all
          </button>
        </div>
      </div>

      <!-- Bulk action bar (only when 1+ selected) -->
      <div
        v-if="bulkIds.size > 0"
        class="px-4 py-2 border-b border-border bg-primary/5 flex flex-wrap items-center gap-2 text-xs"
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
        <select
          v-model="bulkCorrectClass"
          class="px-2 py-1 rounded border border-border bg-background"
          @change="onBulkCorrectChange"
        >
          <option value="">Correct to…</option>
          <option v-for="cls in CLASSES" :key="cls" :value="cls">
            {{ classLabel(cls) }}
          </option>
        </select>
        <button
          class="ml-auto text-muted-foreground hover:text-foreground"
          @click="clearBulk"
        >
          Clear
        </button>
      </div>

      <div class="flex-1 overflow-auto">
        <div v-for="group in groupedDetections" :key="group.label" class="border-b border-border">
          <header class="px-4 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground bg-surface/50 sticky top-0">
            {{ group.label }} <span class="font-normal">({{ group.detections.length }})</span>
          </header>
          <div class="grid grid-cols-5 gap-1 p-2">
            <div
              v-for="d in group.detections"
              :key="d.id"
              class="rounded-md overflow-hidden border-2 transition-all"
              :class="[
                selectedId === d.id ? 'border-primary ring-2 ring-primary' : 'border-transparent hover:border-border',
                reviewedFade(d) ? 'opacity-50' : '',
              ]"
            >
              <div
                :data-detection-id="d.id"
                role="button"
                tabindex="0"
                class="relative aspect-square cursor-pointer focus:outline-none"
                :style="{ backgroundColor: classBgFor(d.yolo_class) }"
                @click="selectedId = d.id"
                @keydown.enter.prevent="selectedId = d.id"
              >
                <div class="absolute inset-0 flex items-center justify-center text-2xl font-bold opacity-30">
                  {{ classGlyph(d.yolo_class) }}
                </div>
                <span
                  class="absolute top-1 left-1 w-2 h-2 rounded-full"
                  :class="statusDotClass(d.reviewer_status)"
                />
                <span
                  v-if="hasDisagreement(d)"
                  class="absolute top-1 right-1 text-amber-600 text-xs leading-none"
                  title="YOLO and InsectNet disagree"
                >⚠</span>
                <span class="absolute bottom-2 left-1 text-[9px] text-muted-foreground/70 font-mono">
                  {{ d.source === 'preprocessing' ? 'P' : d.source === 'both' ? 'YP' : 'Y' }}
                </span>
                <div
                  class="absolute bottom-0 left-0 right-0 h-1.5"
                  :style="{ backgroundColor: classColor(d.yolo_class) }"
                />
              </div>
              <div
                role="checkbox"
                :aria-checked="bulkIds.has(d.id)"
                tabindex="0"
                class="h-5 flex items-center justify-center text-xs cursor-pointer transition-colors"
                :class="bulkIds.has(d.id)
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-surface text-muted-foreground hover:bg-muted'"
                @click="toggleBulk(d.id)"
                @keydown.space.prevent="toggleBulk(d.id)"
              >
                <span v-if="bulkIds.has(d.id)">✓</span>
              </div>
            </div>
          </div>
        </div>
        <div v-if="!groupedDetections.length" class="p-8 text-center text-sm text-muted-foreground">
          No detections match the current filter.
        </div>
      </div>
    </section>

    <!-- Right: preview pane (mirrors left's structural feel: thin top bar, scroll body, action bar at bottom) -->
    <section class="flex-1 flex flex-col min-w-0">
      <div v-if="!selected" class="m-auto text-sm text-muted-foreground">
        Select a detection on the left to review it.
      </div>
      <template v-else>
        <!-- Top bar (height matches left filter bar) -->
        <header class="px-5 py-3 border-b border-border bg-surface text-sm flex items-center gap-3">
          <span class="font-medium">Detection #{{ selected.id }}</span>
          <span class="text-muted-foreground font-mono text-xs truncate">
            {{ selected.source_image_filename }}
          </span>
          <span
            class="ml-auto text-xs px-2 py-0.5 rounded-full shrink-0"
            :class="statusBadgeClass(selected.reviewer_status)"
          >{{ statusLabel(selected.reviewer_status) }}</span>
        </header>

        <div class="flex-1 overflow-auto">
          <!-- Crop preview, edge-to-edge -->
          <div
            class="aspect-video flex items-center justify-center text-7xl font-bold relative"
            :style="{ backgroundColor: classBgFor(selected.yolo_class) }"
          >
            <div
              class="absolute top-0 left-0 right-0 h-1.5"
              :style="{ backgroundColor: classColor(selected.yolo_class) }"
            />
            <span class="opacity-30">{{ classGlyph(selected.yolo_class) }}</span>
          </div>

          <!-- Predictions + Label: stacked below xl, side-by-side at xl+ (Label left, Predictions right) -->
          <div class="grid grid-cols-1 xl:grid-cols-2 border-b border-border">
            <!-- Predictions (compact, two-line). Order swap at xl+ via order-2. -->
            <div class="px-5 py-4 border-b border-border xl:border-b-0 xl:order-2">
              <div class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                Predictions
              </div>
              <div class="space-y-1.5 text-sm">
                <div class="flex items-center gap-2">
                  <span class="text-muted-foreground w-20">YOLO</span>
                  <span
                    class="w-2 h-2 rounded-full shrink-0"
                    :style="{ backgroundColor: classColor(selected.yolo_class) }"
                  />
                  <span class="font-medium flex-1">{{ classLabel(selected.yolo_class) }}</span>
                  <span class="font-mono text-xs text-muted-foreground">
                    {{ selected.yolo_confidence.toFixed(2) }}
                  </span>
                </div>
                <div class="flex items-center gap-2">
                  <span class="text-muted-foreground w-20">InsectNet</span>
                  <span
                    class="w-2 h-2 rounded-full shrink-0"
                    :style="{ backgroundColor: classColor(selected.insectnet_class) }"
                  />
                  <span class="font-medium flex-1">{{ classLabel(selected.insectnet_class) }}</span>
                  <span class="font-mono text-xs text-muted-foreground">
                    {{ selected.insectnet_confidence.toFixed(2) }}
                  </span>
                </div>
                <div v-if="hasDisagreement(selected)" class="text-xs text-amber-700 pt-1">
                  ⚠ Models disagree
                </div>
              </div>
            </div>

            <!-- Label (one row per class with checkbox at end). Visually first at xl+ via order-1. -->
            <div class="px-5 py-4 xl:order-1 xl:border-r border-border">
              <div class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                Label
              </div>
              <div>
                <label
                  v-for="cls in CLASSES"
                  :key="cls"
                  class="flex items-center gap-3 py-2 px-2 -mx-2 rounded cursor-pointer"
                >
                  <span
                    class="w-2 h-2 rounded-full shrink-0"
                    :style="{ backgroundColor: classColor(cls) }"
                  />
                  <span class="flex-1 text-sm">{{ classLabel(cls) }}</span>
                  <input
                    type="checkbox"
                    :checked="cls === effectiveLabel(selected)"
                    @change="correctTo(cls)"
                    class="w-4 h-4"
                  />
                </label>
              </div>
            </div>
          </div>
        </div>

        <!-- Bottom action bar -->
        <footer class="border-t border-border bg-surface px-5 py-3 flex items-center justify-between">
          <span class="text-[11px] text-muted-foreground font-mono hidden md:block">
            1-4 confirm · x reject · ⏎ suggested · ↑↓ navigate
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
              @click="confirmAs(suggestedClass(selected))"
            >
              Confirm as {{ classLabel(suggestedClass(selected)) }}
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
import PollinatorsStepper from '@/components/PollinatorsStepper.vue'
import { api } from '@/api'

type ClassName = 'fly' | 'bumblebee' | 'butterfly' | 'other'
type ReviewerStatus = 'unreviewed' | 'confirmed' | 'corrected' | 'rejected'
type Source = 'yolo' | 'preprocessing' | 'both'

interface Detection {
  id: number
  yolo_class: ClassName
  yolo_confidence: number
  insectnet_class: ClassName
  insectnet_confidence: number
  source: Source
  reviewer_status: ReviewerStatus
  reviewer_label: ClassName | null
  source_image_filename: string
}

interface ReviewBundle {
  run: { id: number; name: string; status: string; detection_count: number }
  detections: Detection[]
}

const CLASSES: ClassName[] = ['fly', 'bumblebee', 'butterfly', 'other']
const CLASS_COLORS: Record<ClassName, string> = {
  fly: '#6b9bd2',
  bumblebee: '#e6a946',
  butterfly: '#c87bba',
  other: '#9aa3ab',
}
const CLASS_GLYPHS: Record<ClassName, string> = {
  fly: '🪰',
  bumblebee: '🐝',
  butterfly: '🦋',
  other: '?',
}

const route = useRoute()
const loading = ref(true)
const loadError = ref('')
const run = ref<ReviewBundle['run'] | null>(null)
const detections = ref<Detection[]>([])
const selectedId = ref<number | null>(null)
const statusFilter = ref<'unreviewed' | 'all' | 'reviewed'>('unreviewed')
const disagreementsOnly = ref(false)
const bulkIds = ref<Set<number>>(new Set())
const bulkCorrectClass = ref<'' | ClassName>('')

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
  const { default: mocks } = await import('@/mocks/pollinator-detections.json')
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
    if (!runRes.ok) {
      loadError.value = `Run: HTTP ${runRes.status}`
      return
    }
    if (!detRes.ok) {
      loadError.value = `Detections: HTTP ${detRes.status}`
      return
    }
    run.value = await runRes.json()
    detections.value = await detRes.json()
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

const headerTitle = computed(() =>
  run.value ? `Review · ${run.value.name || `Run #${run.value.id}`}` : 'Review',
)

const filteredDetections = computed(() => {
  let list = detections.value
  if (statusFilter.value === 'unreviewed') {
    list = list.filter((d) => d.reviewer_status === 'unreviewed')
  } else if (statusFilter.value === 'reviewed') {
    list = list.filter((d) => d.reviewer_status !== 'unreviewed')
  }
  if (disagreementsOnly.value) {
    list = list.filter((d) => hasDisagreement(d))
  }
  return [...list].sort((a, b) => a.insectnet_confidence - b.insectnet_confidence)
})

const groupedDetections = computed(() => {
  const groups = new Map<ClassName, Detection[]>()
  for (const d of filteredDetections.value) {
    const cls = d.yolo_class
    if (!groups.has(cls)) groups.set(cls, [])
    groups.get(cls)!.push(d)
  }
  return CLASSES.filter((cls) => groups.has(cls)).map((cls) => ({
    label: classLabel(cls),
    detections: groups.get(cls)!,
  }))
})

const selected = computed(() =>
  detections.value.find((d) => d.id === selectedId.value) ?? null,
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
  const el = document.querySelector(`[data-detection-id="${id}"]`)
  el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
})

function classColor(cls: string): string {
  return CLASS_COLORS[cls as ClassName] ?? '#9aa3ab'
}
function classBgFor(cls: string): string {
  const hex = classColor(cls)
  return hex + '14'
}
function classGlyph(cls: string): string {
  return CLASS_GLYPHS[cls as ClassName] ?? '?'
}
function classLabel(cls: string | null): string {
  if (!cls) return '—'
  return cls[0].toUpperCase() + cls.slice(1)
}
function hasDisagreement(d: Detection): boolean {
  return d.yolo_class !== d.insectnet_class
}
function reviewedFade(d: Detection): boolean {
  return d.reviewer_status !== 'unreviewed'
}
function statusDotClass(s: ReviewerStatus): string {
  switch (s) {
    case 'confirmed': return 'bg-green-500'
    case 'corrected': return 'bg-blue-500'
    case 'rejected': return 'bg-red-500'
    default: return 'bg-muted-foreground/40'
  }
}
function statusBadgeClass(s: ReviewerStatus): string {
  switch (s) {
    case 'confirmed': return 'bg-green-100 text-green-700'
    case 'corrected': return 'bg-blue-100 text-blue-700'
    case 'rejected': return 'bg-red-100 text-red-700'
    default: return 'bg-muted text-muted-foreground'
  }
}
function statusLabel(s: ReviewerStatus): string {
  return s[0].toUpperCase() + s.slice(1)
}
function suggestedClass(d: Detection): ClassName {
  return d.insectnet_confidence >= d.yolo_confidence ? d.insectnet_class : d.yolo_class
}

function effectiveLabel(d: Detection): ClassName | null {
  if (d.reviewer_label) return d.reviewer_label
  if (d.yolo_class === d.insectnet_class) return d.yolo_class
  return null
}

function applyAction(status: ReviewerStatus, label: ClassName | null) {
  if (!selected.value) return
  selected.value.reviewer_status = status
  selected.value.reviewer_label = label
  advanceToNext()
}

function toggleBulk(id: number) {
  const next = new Set(bulkIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  bulkIds.value = next
}

function clearBulk() {
  bulkIds.value = new Set()
  bulkCorrectClass.value = ''
}

function selectAllVisible() {
  bulkIds.value = new Set(filteredDetections.value.map((d) => d.id))
}

function applyToBulk(status: ReviewerStatus, label: ClassName | null) {
  for (const d of detections.value) {
    if (bulkIds.value.has(d.id)) {
      d.reviewer_status = status
      d.reviewer_label = label
    }
  }
  clearBulk()
}

function bulkConfirm() {
  for (const d of detections.value) {
    if (bulkIds.value.has(d.id)) {
      d.reviewer_status = 'confirmed'
      d.reviewer_label = d.yolo_class
    }
  }
  clearBulk()
}

function bulkReject() {
  applyToBulk('rejected', null)
}

function onBulkCorrectChange() {
  if (bulkCorrectClass.value === '') return
  applyToBulk('corrected', bulkCorrectClass.value)
}

function confirmAs(cls: ClassName) {
  applyAction('confirmed', cls)
}
function correctTo(cls: ClassName) {
  applyAction('corrected', cls)
}
function reject() {
  applyAction('rejected', null)
}

function advanceToNext() {
  const list = filteredDetections.value
  const idx = list.findIndex((d) => d.id === selectedId.value)
  if (idx >= 0 && idx + 1 < list.length) {
    selectedId.value = list[idx + 1].id
  }
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
  if (e.target instanceof HTMLElement && ['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) {
    return
  }
  switch (e.key) {
    case '1': confirmAs('fly'); e.preventDefault(); break
    case '2': confirmAs('bumblebee'); e.preventDefault(); break
    case '3': confirmAs('butterfly'); e.preventDefault(); break
    case '4': confirmAs('other'); e.preventDefault(); break
    case 'x':
    case 'X': reject(); e.preventDefault(); break
    case 'Enter': confirmAs(suggestedClass(selected.value)); e.preventDefault(); break
    case 'ArrowDown':
    case 'j': navigate(1); e.preventDefault(); break
    case 'ArrowUp':
    case 'k': navigate(-1); e.preventDefault(); break
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>
