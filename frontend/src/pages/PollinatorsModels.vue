<template>
  <PageHeader title="Models" subtitle="Trained model versions for the pollinator pipeline" />

  <div class="flex-1 flex flex-col min-h-0">
    <!-- Filter chips + stats -->
    <div class="px-8 py-3 border-b border-border bg-surface flex items-center gap-3 flex-wrap">
      <div class="flex gap-1 text-xs">
        <button
          v-for="opt in filterOptions"
          :key="opt.value"
          class="px-3 py-1.5 rounded-md font-medium transition-colors"
          :class="kindFilter === opt.value
            ? 'bg-primary text-primary-foreground'
            : 'text-muted-foreground hover:bg-muted'"
          @click="kindFilter = opt.value"
        >
          {{ opt.label }}
          <span v-if="opt.count !== undefined" class="opacity-70">· {{ opt.count }}</span>
        </button>
      </div>
      <span class="text-xs text-muted-foreground ml-auto">
        {{ totalVersions }} {{ totalVersions === 1 ? 'version' : 'versions' }} ·
        {{ activeCount }} active
      </span>
      <button
        v-if="canUploadModels"
        class="px-3 py-1.5 rounded-md text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90"
        @click="openUpload"
      >
        Upload model
      </button>
    </div>

    <!-- Body -->
    <div class="flex-1 overflow-auto">
      <div v-if="loading" class="p-8 text-sm text-muted-foreground">Loading…</div>
      <div v-else-if="loadError" class="p-8 text-sm text-red-600">{{ loadError }}</div>
      <div v-else-if="!filteredTracks.length" class="p-12 text-center text-sm text-muted-foreground">
        No models match this filter.
      </div>

      <div v-else class="p-6 space-y-4">
        <section
          v-for="track in filteredTracks"
          :key="track.id"
          class="rounded-xl border border-border bg-card overflow-hidden shadow-md"
        >
          <header class="px-5 py-4 bg-primary/[0.22] border-b border-border flex items-baseline gap-3">
            <h2 class="font-bold text-lg tracking-tight">{{ track.label }}</h2>
            <span class="text-xs text-muted-foreground">
              {{ track.versions.length }} {{ track.versions.length === 1 ? 'version' : 'versions' }}
            </span>
            <span class="text-xs text-muted-foreground ml-auto">
              metric: {{ track.metric_label }}
            </span>
          </header>

          <table class="w-full text-sm">
            <thead class="text-xs text-muted-foreground bg-muted/30">
              <tr>
                <th class="text-left font-medium px-5 py-2 w-10">Default</th>
                <th class="text-left font-medium px-3 py-2">Name</th>
                <th class="text-left font-medium px-3 py-2">{{ track.metric_label }}</th>
                <th class="text-left font-medium px-3 py-2">Trained</th>
                <th class="px-3 py-2 w-10"></th>
              </tr>
            </thead>
            <tbody>
              <template v-for="v in track.versions" :key="v.id">
                <tr
                  class="border-t border-border hover:bg-muted/20 cursor-pointer"
                  :class="v.is_active ? 'bg-primary/[0.05]' : ''"
                  @click="toggleExpanded(v.id)"
                >
                  <td class="px-5 py-3" @click.stop>
                    <input
                      type="radio"
                      :name="`default-${track.id}`"
                      :value="v.id"
                      :checked="v.is_active"
                      @change="setDefault(track, v)"
                    />
                  </td>
                  <td class="px-3 py-3 font-medium">
                    {{ v.version_name }}
                    <span
                      v-if="v.is_active"
                      class="ml-2 text-xs px-2 py-0.5 rounded-full bg-green-300 text-green-900 font-medium"
                    >
                      active
                    </span>
                  </td>
                  <td class="px-3 py-3 font-mono text-xs">
                    {{ formatMetric(mainMetric(v, track.metric_label)) }}
                  </td>
                  <td class="px-3 py-3 text-xs text-muted-foreground">
                    {{ formatRelative(v.trained_at) }}
                  </td>
                  <td class="px-3 py-3 text-right text-muted-foreground">
                    {{ expandedIds.has(v.id) ? '▾' : '▸' }}
                  </td>
                </tr>
                <tr
                  v-if="expandedIds.has(v.id)"
                  class="border-t border-border bg-muted/10"
                >
                  <td></td>
                  <td colspan="4" class="px-3 py-4">
                    <div class="grid grid-cols-2 gap-x-8 gap-y-3 max-w-3xl">
                      <div>
                        <div class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
                          Parameters
                        </div>
                        <dl class="text-xs grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
                          <template
                            v-for="(value, key) in v.parameters"
                            :key="String(key)"
                          >
                            <dt class="text-muted-foreground">{{ String(key) }}</dt>
                            <dd class="font-mono">{{ formatParam(value) }}</dd>
                          </template>
                        </dl>
                      </div>
                      <div>
                        <div class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
                          Metrics
                        </div>
                        <dl class="text-xs grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
                          <template
                            v-for="(value, key) in v.metrics"
                            :key="String(key)"
                          >
                            <dt class="text-muted-foreground">{{ String(key) }}</dt>
                            <dd class="font-mono">{{ formatMetric(value) }}</dd>
                          </template>
                        </dl>
                      </div>
                    </div>
                    <div class="text-xs text-muted-foreground mt-3 pt-3 border-t border-border">
                      Trained {{ formatRelative(v.trained_at) }}
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </section>
      </div>
    </div>

    <!-- Upload model modal -->
    <div
      v-if="uploadOpen"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      @click.self="uploadOpen = false"
    >
      <div class="bg-card border border-border rounded-xl shadow-xl w-full max-w-md">
        <header class="px-5 py-3 border-b border-border flex items-center justify-between">
          <h3 class="font-semibold">Upload existing model</h3>
          <button
            class="text-muted-foreground hover:text-foreground"
            @click="uploadOpen = false"
          >
            ✕
          </button>
        </header>
        <div class="p-5 space-y-3 text-sm">
          <label class="block">
            <span class="text-xs font-medium text-muted-foreground">Kind</span>
            <select
              v-model="uploadKind"
              class="mt-1 w-full px-2 py-1.5 rounded border border-border bg-background"
            >
              <option v-for="opt in UPLOAD_KIND_OPTIONS" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </label>
          <label class="block">
            <span class="text-xs font-medium text-muted-foreground">
              Version name
              <span class="text-red-600">*</span>
            </span>
            <input
              v-model="uploadVersionName"
              type="text"
              placeholder="e.g. yolo-v1"
              class="mt-1 w-full px-2 py-1.5 rounded border border-border bg-background font-mono"
            />
            <span class="text-[11px] text-muted-foreground">
              Used as the filename and must be unique.
            </span>
          </label>
          <label class="block">
            <span class="text-xs font-medium text-muted-foreground">Description</span>
            <textarea
              v-model="uploadDescription"
              rows="2"
              placeholder="Optional notes on dataset, training, etc."
              class="mt-1 w-full px-2 py-1.5 rounded border border-border bg-background"
            />
          </label>
          <label class="block">
            <span class="text-xs font-medium text-muted-foreground">
              Weights file
              <span class="text-red-600">*</span>
            </span>
            <input
              type="file"
              accept=".pt,.pth,.bin"
              class="mt-1 w-full text-xs"
              @change="pickUploadFile"
            />
            <span class="text-[11px] text-muted-foreground">
              .pt / .pth — metadata (img_size, arch, epoch) is auto-extracted if present.
            </span>
          </label>
          <p v-if="uploadError" class="text-xs text-red-600">{{ uploadError }}</p>
        </div>
        <footer class="px-5 py-3 border-t border-border flex items-center justify-end gap-2">
          <button
            class="px-3 py-1.5 rounded-md text-sm font-medium text-muted-foreground hover:bg-muted"
            :disabled="uploadSubmitting"
            @click="uploadOpen = false"
          >
            Cancel
          </button>
          <button
            class="px-3 py-1.5 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="uploadSubmitting"
            @click="submitUpload"
          >
            <span v-if="uploadSubmitting">Uploading…</span>
            <span v-else>Upload</span>
          </button>
        </footer>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import { api } from '@/api'
import { useAuthStore } from '@/stores/auth'
import {
  tracksFromVersions,
  type BackendModelVersion,
  type Track,
  type TrackVersion as Version,
} from '@/lib/model-tracks'

interface VersionMock {
  id: number
  version_name: string
  is_active: boolean
  metrics: Record<string, number>
  parameters: Record<string, unknown>
  trained_at_offset_seconds: number
}
interface TrackMock {
  id: string
  label: string
  description: string
  kind: string
  metric_label: string
  active_version_id: number | null
  versions: VersionMock[]
}

const route = useRoute()
const auth = useAuthStore()
const loading = ref(true)
const loadError = ref('')
const tracks = ref<Track[]>([])
const kindFilter = ref<string>('all')
const expandedIds = ref<Set<number>>(new Set())

// Toggle that gates the "Upload model" button. Currently checks staff
// status from the auth store; flip to `true` to make the button visible
// to everyone (e.g. for local testing without staff users).
const canUploadModels = computed(() => auth.user?.is_staff === true)

// --- Upload modal state ---
const uploadOpen = ref(false)
const uploadKind = ref<string>('detector')
const uploadVersionName = ref('')
const uploadDescription = ref('')
const uploadFile = ref<File | null>(null)
const uploadSubmitting = ref(false)
const uploadError = ref('')

const UPLOAD_KIND_OPTIONS = [
  { value: 'detector', label: 'YOLO detector' },
  { value: 'binary_classifier', label: 'EfficientNet binary classifier' },
  { value: 'group_classifier', label: 'InsectNet group classifier' },
]

function openUpload() {
  uploadKind.value = 'detector'
  uploadVersionName.value = ''
  uploadDescription.value = ''
  uploadFile.value = null
  uploadError.value = ''
  uploadOpen.value = true
}

function pickUploadFile(e: Event) {
  const target = e.target as HTMLInputElement
  uploadFile.value = target.files?.[0] ?? null
}

async function submitUpload() {
  uploadError.value = ''
  if (!uploadFile.value) {
    uploadError.value = 'Pick a .pt or .pth file.'
    return
  }
  if (!uploadVersionName.value.trim()) {
    uploadError.value = 'Version name is required.'
    return
  }
  const form = new FormData()
  form.append('module', 'pollinators')
  form.append('kind', uploadKind.value)
  form.append('version_name', uploadVersionName.value.trim())
  form.append('description', uploadDescription.value.trim())
  form.append('weights_file', uploadFile.value)

  uploadSubmitting.value = true
  try {
    const res = await api('/api/analysis/models/', { method: 'POST', body: form })
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data.detail || `HTTP ${res.status}`)
    }
    uploadOpen.value = false
    // Reload to pick up the new version + any introspected parameters.
    loading.value = true
    await loadFromApi()
  } catch (e) {
    uploadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    uploadSubmitting.value = false
  }
}

const previewMode = computed<string | null>(() => {
  const value = route.query.preview
  return typeof value === 'string' ? value : null
})

onMounted(async () => {
  if (previewMode.value) {
    const data = await loadPreview(previewMode.value)
    if (data) {
      tracks.value = data
      loading.value = false
      return
    }
  }
  await loadFromApi()
})

async function loadPreview(_mode: string): Promise<Track[] | null> {
  if (!import.meta.env.DEV) return null
  const { default: mocks } = await import('@/mocks/pollinator-models.json')
  const raw = (mocks as unknown as Record<string, { tracks: TrackMock[] } | undefined>).default
  if (!raw) return null
  const now = Date.now()
  return raw.tracks.map((t) => ({
    id: t.id,
    label: t.label,
    description: t.description,
    kind: t.kind,
    metric_label: t.metric_label,
    active_version_id: t.active_version_id,
    versions: t.versions.map((v) => ({
      id: v.id,
      version_name: v.version_name,
      is_active: v.is_active,
      metrics: v.metrics,
      parameters: v.parameters,
      trained_at: new Date(now + v.trained_at_offset_seconds * 1000).toISOString(),
    })),
  }))
}

async function loadFromApi() {
  try {
    const res = await api('/api/analysis/models/?module=pollinators')
    if (!res.ok) {
      loadError.value = `HTTP ${res.status}`
      return
    }
    const versions: BackendModelVersion[] = await res.json()
    tracks.value = tracksFromVersions(versions)
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

const filterOptions = computed(() => {
  const opts = [
    { value: 'all', label: 'All', count: totalVersions.value },
  ]
  for (const t of tracks.value) {
    opts.push({ value: t.id, label: t.label, count: t.versions.length })
  }
  return opts
})

const filteredTracks = computed(() => {
  if (kindFilter.value === 'all') return tracks.value
  return tracks.value.filter((t) => t.id === kindFilter.value)
})

const totalVersions = computed(() =>
  tracks.value.reduce((sum, t) => sum + t.versions.length, 0),
)

const activeCount = computed(() =>
  tracks.value.reduce(
    (sum, t) => sum + t.versions.filter((v) => v.is_active).length,
    0,
  ),
)

function mainMetric(v: Version, metricLabel: string): number | undefined {
  if (v.metrics[metricLabel] !== undefined) return v.metrics[metricLabel]
  return Object.values(v.metrics)[0]
}
function formatMetric(value: number | undefined): string {
  if (value === undefined) return '—'
  return value.toFixed(2)
}
function formatRelative(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
  return `${Math.round(diff / 86400)}d ago`
}

async function setDefault(track: Track, v: Version) {
  // Optimistic flip; server demotes the previous active row in the same
  // (module, kind) on save, so we mirror that locally before the request.
  const prevActiveId = track.active_version_id
  for (const x of track.versions) x.is_active = false
  v.is_active = true
  track.active_version_id = v.id

  if (previewMode.value) return
  try {
    const res = await api(`/api/analysis/models/${v.id}/set-active/`, {
      method: 'POST',
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
  } catch (e) {
    // Revert optimistic update on failure.
    v.is_active = false
    track.active_version_id = prevActiveId
    if (prevActiveId != null) {
      const prev = track.versions.find((x) => x.id === prevActiveId)
      if (prev) prev.is_active = true
    }
    loadError.value = e instanceof Error ? e.message : String(e)
  }
}

function toggleExpanded(id: number) {
  const next = new Set(expandedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedIds.value = next
}

function formatParam(value: unknown): string {
  if (typeof value === 'number') {
    if (value < 0.01 && value > 0) return value.toExponential(1)
    return String(value)
  }
  return String(value)
}

</script>
