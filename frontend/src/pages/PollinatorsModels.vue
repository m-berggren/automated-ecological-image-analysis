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
          :class="
            kindFilter === opt.value
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:bg-muted'
          "
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
      <div
        v-else-if="!filteredTracks.length"
        class="p-12 text-center text-sm text-muted-foreground"
      >
        No models match this filter.
      </div>

      <div v-else class="p-6 space-y-6">
        <div v-for="group in pipelineGroups" :key="group.id" class="space-y-3">
          <div v-if="kindFilter === 'all'" class="flex items-center gap-3">
            <p class="text-xs font-medium text-muted-foreground whitespace-nowrap">{{ group.label }}</p>
            <div class="flex-1 border-t border-border" />
          </div>
          <section
            v-for="track in group.tracks"
            :key="track.id"
            class="rounded-xl border border-border bg-card overflow-hidden shadow-md"
          >
          <header
            class="px-5 py-4 bg-primary/[0.22] border-b border-border"
          >
            <div class="flex items-baseline gap-3">
              <h2 class="font-bold text-lg tracking-tight">{{ track.label }}</h2>
              <span v-if="track.id === 'detector'" class="text-xs text-muted-foreground font-mono">(Full-Image Detection)</span>
              <span v-else-if="track.id === 'binary_classifier'" class="text-xs text-muted-foreground font-mono">(Insect Detection)</span>
              <span v-else-if="track.id === 'group_classifier'" class="text-xs text-muted-foreground font-mono">(Insect Classification)</span>
              <InfoPopover v-if="TRACK_INFO[track.id]">{{ TRACK_INFO[track.id] }}</InfoPopover>
              <span class="text-xs text-muted-foreground">
                {{ track.versions.length }} {{ track.versions.length === 1 ? 'version' : 'versions' }}
              </span>
              <span class="text-xs text-muted-foreground ml-auto inline-flex items-center gap-1">
                metric: {{ track.metric_label }}
                <InfoPopover>{{
                  METRIC_INFO[track.metric_label] ?? 'Headline metric for this model.'
                }}</InfoPopover>
              </span>
            </div>
            <p v-if="track.description" class="text-xs text-muted-foreground mt-1">{{ track.description }}</p>
          </header>

          <!-- table-fixed so column widths come from the header, not cell
               content: the metric column no longer shifts when the artifacts
               panel expands, and every track's table lines up identically. -->
          <table class="w-full text-sm table-fixed">
            <thead class="text-xs text-muted-foreground bg-muted/30">
              <tr>
                <th class="text-left font-medium px-5 py-2 w-16">Default</th>
                <th class="text-left font-medium px-3 py-2">Name</th>
                <th class="text-right font-medium px-3 py-2 w-24">Recall</th>
                <th class="text-right font-medium px-3 py-2 w-24">{{ track.metric_label }}</th>
                <th class="text-right font-medium px-3 py-2 w-20">Samples</th>
                <th class="text-right font-medium px-3 py-2 w-24">Duration</th>
                <th class="text-left font-medium px-3 py-2 w-28">Trained</th>
                <th class="px-3 py-2 w-12"></th>
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
                    <template v-if="renamingId === v.id">
                      <input
                        v-model="renameValue"
                        class="border border-border rounded px-2 py-1 text-sm w-48"
                        :disabled="renameSaving"
                        @keyup.enter="saveRename(v)"
                        @keyup.esc="cancelRename"
                        @click.stop
                      />
                      <button
                        class="ml-2 text-xs text-primary hover:underline"
                        @click.stop="saveRename(v)"
                      >
                        Save
                      </button>
                      <button
                        class="ml-2 text-xs text-muted-foreground hover:underline"
                        @click.stop="cancelRename"
                      >
                        Cancel
                      </button>
                    </template>
                    <template v-else>
                      <span>{{ v.version_name }}</span>
                      <button
                        v-if="canDeleteModels"
                        class="ml-2 text-muted-foreground hover:text-primary align-middle"
                        :title="`Rename ${v.version_name}`"
                        @click.stop="startRename(v)"
                      >
                        <Pencil class="w-3.5 h-3.5 inline" />
                      </button>
                      <span
                        v-if="v.is_active"
                        class="ml-2 text-xs px-2 py-0.5 rounded-full bg-green-300 text-green-900 font-medium"
                      >
                        active
                      </span>
                    </template>
                  </td>
                  <td class="px-3 py-3 text-right font-mono text-xs text-muted-foreground">
                    {{ formatMetric(v.metrics['recall']) }}
                  </td>
                  <td class="px-3 py-3 text-right font-mono text-xs">
                    {{ formatMetric(mainMetric(v, track.metric_label)) }}
                  </td>
                  <td class="px-3 py-3 text-right font-mono text-xs text-muted-foreground">
                    {{ v.sample_count ? v.sample_count.toLocaleString() : '—' }}
                  </td>
                  <td class="px-3 py-3 text-right font-mono text-xs text-muted-foreground">
                    {{ formatDuration(v.training_duration_seconds) }}
                  </td>
                  <td class="px-3 py-3 text-xs text-muted-foreground truncate">
                    {{ formatRelative(v.trained_at) }}
                  </td>
                  <td class="px-3 py-3 text-right text-muted-foreground">
                    <div class="flex items-center justify-end gap-3" @click.stop>
                      <button
                        v-if="canDeleteModels"
                        :disabled="deletingId === v.id"
                        :title="
                          v.is_active
                            ? 'Cannot delete the active version. Pick another default first.'
                            : `Delete ${v.version_name}`
                        "
                        class="text-muted-foreground hover:text-red-600 disabled:opacity-40 disabled:cursor-not-allowed"
                        @click="confirmDelete(v)"
                      >
                        <Trash2 class="w-4 h-4" />
                      </button>
                      <span @click="toggleExpanded(v.id)" class="cursor-pointer">
                        {{ expandedIds.has(v.id) ? '▾' : '▸' }}
                      </span>
                    </div>
                  </td>
                </tr>
                <tr v-if="expandedIds.has(v.id)" class="border-t border-border bg-muted/40">
                  <td class="bg-muted/40"></td>
                  <td colspan="7" class="px-3 py-4">
                    <div class="grid grid-cols-2 gap-x-8 gap-y-3 max-w-3xl">
                      <div class="min-w-0">
                        <div
                          class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1"
                        >
                          Parameters
                        </div>
                        <dl class="text-xs grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
                          <template v-for="[key, value] in visibleParams(v.parameters)" :key="key">
                            <dt class="text-muted-foreground">{{ key }}</dt>
                            <dd class="font-mono min-w-0 break-words whitespace-pre-line">{{ formatParam(value) }}</dd>
                          </template>
                        </dl>
                      </div>
                      <div>
                        <div
                          class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1"
                        >
                          Metrics
                        </div>
                        <dl class="text-xs grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
                          <template v-for="(value, key) in v.metrics" :key="String(key)">
                            <dt class="text-muted-foreground">{{ String(key) }}</dt>
                            <dd class="font-mono">{{ formatMetric(value) }}</dd>
                          </template>
                        </dl>
                      </div>
                    </div>
                    <div v-if="v.artifacts.length > 0" class="mt-4 pt-3 border-t border-border">
                      <button
                        class="flex w-full items-center gap-1.5 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground"
                        @click="toggleArtifacts(v.id)"
                      >
                        <span>{{ expandedArtifactIds.has(v.id) ? '▾' : '▸' }}</span>
                        <span>Training artifacts ({{ v.artifacts.length }})</span>
                      </button>
                      <div v-if="expandedArtifactIds.has(v.id)" class="mt-3 space-y-4">
                        <div v-for="group in groupedArtifacts(v)" :key="group.kind">
                          <div class="text-xs font-medium text-foreground mb-1.5">
                            {{ group.label }}
                          </div>
                          <div v-if="group.isImage" class="flex flex-wrap gap-3">
                            <a
                              v-for="a in group.items"
                              :key="a.id"
                              :href="a.url ?? '#'"
                              target="_blank"
                              rel="noopener"
                              class="block border border-border rounded-md overflow-hidden hover:border-primary"
                              :title="a.caption || ''"
                            >
                              <img
                                v-if="a.url"
                                :src="a.url"
                                :alt="a.caption || group.label"
                                class="block w-60 h-auto bg-background"
                                loading="lazy"
                              />
                              <div
                                v-if="a.caption"
                                class="px-2 py-1 text-[10px] text-muted-foreground bg-muted/40"
                              >
                                {{ a.caption }}
                              </div>
                            </a>
                          </div>
                          <ul v-else class="text-xs space-y-1">
                            <li v-for="a in group.items" :key="a.id">
                              <a
                                v-if="a.url"
                                :href="a.url"
                                target="_blank"
                                rel="noopener"
                                class="text-primary hover:underline font-mono"
                                :download="true"
                              >
                                Download{{ a.caption ? ` (${a.caption})` : '' }}
                              </a>
                            </li>
                          </ul>
                        </div>
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
    </div>

    <ModelUploadDialog
      v-model:open="uploadOpen"
      module="pollinators"
      :kind-options="UPLOAD_KIND_OPTIONS"
      :structures="UPLOAD_STRUCTURE"
      @uploaded="onModelUploaded"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import ModelUploadDialog from '@/components/ModelUploadDialog.vue'
import InfoPopover from '@/components/InfoPopover.vue'
import { Trash2, Pencil } from 'lucide-vue-next'
import { api } from '@/api'
import { confirm, alert } from '@/lib/confirm'
import { useAuthStore } from '@/stores/auth'
import {
  tracksFromVersions,
  type BackendModelVersion,
  type Track,
  type TrackVersion as Version,
} from '@/lib/model-tracks'

// Display name for the backend track id badge (detector → yolo_detector for clarity).
const TRACK_ID_DISPLAY: Record<string, string> = { detector: 'yolo_detector' }

// Per-track help shown in the section-header info popover (keyed by track id).
const TRACK_INFO: Record<string, string> = {
  detector:
    'Full-Image Detection Pipeline (YOLO): scans each image directly to locate insects — no motion required. Can detect stationary insects.',
  binary_classifier:
    'Motion-Based Pipeline — Step 1 (Insect Detection): detects movement between frames and decides whether each moving object is an insect or background noise.',
  group_classifier:
    'Motion-Based Pipeline — Step 2 (Insect Classification): takes confirmed insects from Step 1 and classifies them as fly, bumblebee, butterfly, or other.',
}

// Why each headline metric (keyed by metric_label), shown next to "metric:".
const METRIC_INFO: Record<string, string> = {
  mAP50:
    'Mean average precision at IoU 0.5 — the standard detector quality score (precision/recall over boxes).',
  f1: 'F1, not accuracy: the classes are imbalanced (mostly background / one dominant taxon), so accuracy is inflated by the majority class. F1 balances precision and recall on the classes that matter.',
}

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
// Parallel set: when a version id is in here, the training-artifacts panel
// inside its (already-expanded) row is open. Kept separate from expandedIds
// so users can leave the parameters/metrics view open while flipping artifacts.
const expandedArtifactIds = ref<Set<number>>(new Set())

function toggleArtifacts(id: number) {
  const next = new Set(expandedArtifactIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedArtifactIds.value = next
}

// Display labels + ordering for each ModelArtifactKind. Image kinds render as
// thumbnails; non-image kinds (results.csv) render as a download link.
const ARTIFACT_GROUPS: Array<{ kind: string; label: string; isImage: boolean }> = [
  { kind: 'training_curve', label: 'Training curves (results.png)', isImage: true },
  { kind: 'confusion_matrix', label: 'Confusion matrix', isImage: true },
  { kind: 'f1_curve', label: 'F1 vs confidence', isImage: true },
  { kind: 'pr_curve', label: 'Precision-Recall', isImage: true },
  { kind: 'precision_curve', label: 'Precision vs confidence', isImage: true },
  { kind: 'recall_curve', label: 'Recall vs confidence', isImage: true },
  { kind: 'labels', label: 'Label distribution', isImage: true },
  { kind: 'sample_predictions', label: 'Sample predictions', isImage: true },
  { kind: 'results_csv', label: 'Per-epoch metrics CSV', isImage: false },
  { kind: 'other', label: 'Other', isImage: false },
]

function groupedArtifacts(v: Version) {
  const byKind = new Map<string, typeof v.artifacts>()
  for (const a of v.artifacts) {
    if (!byKind.has(a.kind)) byKind.set(a.kind, [])
    byKind.get(a.kind)!.push(a)
  }
  return ARTIFACT_GROUPS.filter((g) => byKind.has(g.kind)).map((g) => ({
    ...g,
    items: byKind.get(g.kind)!,
  }))
}

// Gates the "Upload model" button. Set REQUIRE_STAFF_FOR_UPLOAD=true to
// restore the staff-only check; left open while we work out the right
// permissioning for model uploads.
const REQUIRE_STAFF_FOR_UPLOAD = false
const canUploadModels = computed(() =>
  REQUIRE_STAFF_FOR_UPLOAD ? auth.user?.is_staff === true : !!auth.user,
)
const canDeleteModels = canUploadModels

const deletingId = ref<number | null>(null)

// Parameters surfaced from the trainer that don't add value to the
// per-version detail view: yolo_model/yolo_data are always the same
// reference paths, and `epoch` is the legacy in-checkpoint name we now
// expose as `yolo_epochs`.
const HIDDEN_PARAM_KEYS = new Set(['yolo_model', 'yolo_data'])

function visibleParams(params: Record<string, unknown>): Array<[string, unknown]> {
  const hasYoloEpochs = 'yolo_epochs' in params
  return Object.entries(params).filter(([key]) => {
    if (HIDDEN_PARAM_KEYS.has(key)) return false
    // Drop the raw `epoch` field when yolo_epochs already covers it; keep
    // it for non-YOLO models that don't surface yolo_epochs.
    if (key === 'epoch' && hasYoloEpochs) return false
    return true
  })
}

// --- Upload modal ---
// The dialog UI + folder/weights parsing + submit live in ModelUploadDialog;
// here we just hold open-state, the kind options, and per-kind folder layouts.
const uploadOpen = ref(false)

const UPLOAD_KIND_OPTIONS = [
  { value: 'detector', label: 'Full-Image Detection (YOLO)' },
  { value: 'binary_classifier', label: 'Insect Detection — Step 1  (file: *_binary_best.pth)' },
  { value: 'group_classifier', label: 'Insect Classification — Step 2  (file: group_*_best.pth)' },
]

// Expected upload layout per kind, shown in the dialog's info popover. The
// classifier trainers write only the checkpoint + a results.json (no plots),
// with arch-specific filenames; the detector kind falls back to the dialog's
// built-in Ultralytics layout.
const UPLOAD_STRUCTURE: Record<string, string> = {
  binary_classifier: [
    'run/',
    '├─ <arch>_binary_best.pth',
    '└─ <arch>_binary_results.json',
    '',
    '<arch> = efficientnet | insectnet.',
    'The trainer emits no plots.',
  ].join('\n'),
  group_classifier: [
    'run/',
    '├─ group_<arch>_best.pth',
    '└─ group_<arch>_results.json',
    '',
    '<arch> = efficientnet | insectnet.',
    'The trainer emits no plots.',
  ].join('\n'),
}

function openUpload() {
  uploadOpen.value = true
}

async function onModelUploaded() {
  // Reload to pick up the new version + any introspected parameters.
  loading.value = true
  await loadFromApi()
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
      sample_count: 0,
      training_duration_seconds: 0,
      trained_at: new Date(now + v.trained_at_offset_seconds * 1000).toISOString(),
      artifacts: [],
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
  const opts = [{ value: 'all', label: 'All', count: totalVersions.value }]
  for (const t of tracks.value) {
    opts.push({ value: t.id, label: t.label, count: t.versions.length })
  }
  return opts
})

const filteredTracks = computed(() => {
  if (kindFilter.value === 'all') return tracks.value
  return tracks.value.filter((t) => t.id === kindFilter.value)
})

const PIPELINE_GROUPS = [
  { id: 'full-image', label: 'Full-Image Detection Pipeline', ids: ['detector'] },
  { id: 'motion-based', label: 'Motion-Based Detection Pipeline', ids: ['binary_classifier', 'group_classifier'] },
]
const pipelineGroups = computed(() =>
  PIPELINE_GROUPS
    .map((g) => ({ ...g, tracks: filteredTracks.value.filter((t) => g.ids.includes(t.id)) }))
    .filter((g) => g.tracks.length > 0),
)

const totalVersions = computed(() => tracks.value.reduce((sum, t) => sum + t.versions.length, 0))

const activeCount = computed(() =>
  tracks.value.reduce((sum, t) => sum + t.versions.filter((v) => v.is_active).length, 0),
)

function mainMetric(v: Version, metricLabel: string): number | undefined {
  if (v.metrics[metricLabel] !== undefined) return v.metrics[metricLabel]
  return Object.values(v.metrics)[0]
}
function formatMetric(value: unknown): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—'
  return value.toFixed(2)
}
function formatRelative(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
  return `${Math.round(diff / 86400)}d ago`
}

function formatDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return '—'
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  if (m === 0) return `${s}s`
  if (m < 60) return s ? `${m}m ${s}s` : `${m}m`
  return `${Math.floor(m / 60)}h ${m % 60}m`
}

const renamingId = ref<number | null>(null)
const renameValue = ref('')
const renameSaving = ref(false)

function startRename(v: Version) {
  renamingId.value = v.id
  renameValue.value = v.version_name
}

function cancelRename() {
  renamingId.value = null
  renameValue.value = ''
}

async function saveRename(v: Version) {
  const name = renameValue.value.trim()
  if (!name || name === v.version_name) {
    cancelRename()
    return
  }
  if (previewMode.value) {
    v.version_name = name
    cancelRename()
    return
  }
  renameSaving.value = true
  try {
    const res = await api(`/api/analysis/models/${v.id}/`, {
      method: 'PATCH',
      body: JSON.stringify({ version_name: name }),
    })
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data.version_name?.[0] || data.detail || `HTTP ${res.status}`)
    }
    v.version_name = name
    cancelRename()
  } catch (e) {
    await alert({ title: 'Rename failed', message: e instanceof Error ? e.message : String(e) })
  } finally {
    renameSaving.value = false
  }
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

async function confirmDelete(v: Version) {
  if (v.is_active) {
    await alert({
      title: 'Cannot delete active model',
      message: `"${v.version_name}" is the active version. Pick another default first, then delete it.`,
    })
    return
  }
  if (deletingId.value !== null) return
  const ok = await confirm({
    title: 'Delete model',
    message: `Delete model "${v.version_name}"?\nThis removes the weights file and all artifacts. This cannot be undone.`,
    confirmLabel: 'Delete',
    variant: 'danger',
  })
  if (!ok) return
  deletingId.value = v.id
  try {
    const res = await api(`/api/analysis/models/${v.id}/`, { method: 'DELETE' })
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data.error || data.detail || `HTTP ${res.status}`)
    }
    await loadFromApi()
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    deletingId.value = null
  }
}

function toggleExpanded(id: number) {
  const next = new Set(expandedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedIds.value = next
}

// Compact one-line rendering for nested values (numbers, arrays, objects).
function inlineParam(value: unknown): string {
  if (typeof value === 'number') {
    if (value < 0.01 && value > 0) return value.toExponential(1)
    return String(value)
  }
  if (Array.isArray(value)) return `[${value.map(inlineParam).join(', ')}]`
  if (value !== null && typeof value === 'object') {
    return `{${Object.entries(value)
      .map(([k, v]) => `${k}: ${inlineParam(v)}`)
      .join(', ')}}`
  }
  return String(value)
}

function formatParam(value: unknown): string {
  if (typeof value === 'number') {
    if (value < 0.01 && value > 0) return value.toExponential(1)
    return String(value)
  }
  if (Array.isArray(value)) return value.map(inlineParam).join(', ')
  // Nested objects (e.g. tile_config): render one "key: value" per line so the
  // card stays readable instead of a long JSON blob. Nested objects are
  // compacted inline. The <dd> uses whitespace-pre-line to honor the breaks.
  if (value !== null && typeof value === 'object') {
    return Object.entries(value)
      .map(([k, v]) => `${k}: ${inlineParam(v)}`)
      .join('\n')
  }
  return String(value)
}
</script>
