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

      <div v-else class="p-6 space-y-4">
        <section
          v-for="track in filteredTracks"
          :key="track.id"
          class="rounded-xl border border-border bg-card overflow-hidden shadow-md"
        >
          <header
            class="px-5 py-4 bg-primary/[0.22] border-b border-border flex items-baseline gap-3"
          >
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
                <tr v-if="expandedIds.has(v.id)" class="border-t border-border bg-muted/10">
                  <td></td>
                  <td colspan="4" class="px-3 py-4">
                    <div class="grid grid-cols-2 gap-x-8 gap-y-3 max-w-3xl">
                      <div>
                        <div
                          class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1"
                        >
                          Parameters
                        </div>
                        <dl class="text-xs grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
                          <template v-for="(value, key) in v.parameters" :key="String(key)">
                            <dt class="text-muted-foreground">{{ String(key) }}</dt>
                            <dd class="font-mono">{{ formatParam(value) }}</dd>
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
                        class="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground"
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

    <!-- Upload model modal -->
    <div
      v-if="uploadOpen"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      @click.self="uploadOpen = false"
    >
      <div class="bg-card border border-border rounded-xl shadow-xl w-full max-w-md">
        <header class="px-5 py-3 border-b border-border flex items-center justify-between">
          <h3 class="font-semibold">Upload existing model</h3>
          <button class="text-muted-foreground hover:text-foreground" @click="uploadOpen = false">
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
          <div>
            <span class="text-xs font-medium text-muted-foreground">
              Source
              <span class="text-red-600">*</span>
            </span>
            <UploadDropZone
              class="mt-1"
              v-model:active-tab="uploadMode"
              :tabs="modelUploadTabs"
              :has-files="uploadHasFiles"
              @select="onModelUploadSelect"
            />
            <p
              v-if="uploadMode === 'file' && uploadFile"
              class="mt-2 text-[11px] text-muted-foreground font-mono"
            >
              {{ uploadFile.name }} · {{ formatFileSize(uploadFile.size) }}
            </p>
            <div
              v-if="uploadMode === 'folder' && uploadFolderFiles.length"
              class="mt-2 rounded border border-border bg-muted/30 p-2 text-[11px] space-y-1"
            >
              <div>
                <span class="font-medium">Weights:</span>
                <span v-if="folderPreview.weightsLabel" class="ml-1 font-mono">
                  {{ folderPreview.weightsLabel }}
                </span>
                <span v-else class="ml-1 text-red-600">
                  not found (need weights/best.pt or weights/last.pt)
                </span>
              </div>
              <div>
                <span class="font-medium">
                  Artifacts ({{ folderPreview.recognised.length }}):
                </span>
                <span v-if="folderPreview.recognised.length" class="ml-1 font-mono">
                  {{ folderPreview.recognised.join(', ') }}
                </span>
                <span v-else class="ml-1 text-muted-foreground">none recognised</span>
              </div>
              <div v-if="folderPreview.skipped > 0" class="text-muted-foreground">
                {{ folderPreview.skipped }} other file(s) will be ignored.
              </div>
            </div>
          </div>
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
import UploadDropZone, { type UploadTab } from '@/components/UploadDropZone.vue'
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

// --- Upload modal state ---
const uploadOpen = ref(false)
const uploadKind = ref<string>('detector')
const uploadVersionName = ref('')
const uploadDescription = ref('')
const uploadFile = ref<File | null>(null)
const uploadSubmitting = ref(false)
const uploadError = ref('')
// 'file' = a single .pt/.pth weights file (legacy path).
// 'folder' = a YOLO Ultralytics run folder; the backend picks weights/best.pt
// (or last.pt) and ingests recognized siblings as ModelArtifact rows.
const uploadMode = ref<'file' | 'folder'>('file')
const uploadFolderFiles = ref<File[]>([])

const modelUploadTabs: UploadTab[] = [
  {
    key: 'file',
    label: 'Single weights file',
    mode: 'single-file',
    accept: '.pt,.pth,.bin',
    placeholder: 'Drop a .pt / .pth file or click to browse',
    helper: '.pt / .pth — metadata (img_size, arch, epoch) is auto-extracted if present.',
  },
  {
    key: 'folder',
    label: 'Training run folder',
    mode: 'folder',
    placeholder: 'Drop an Ultralytics run folder or click to browse',
    helper: 'Server takes weights/best.pt (or last.pt) and ingests recognised additional files.',
  },
]

const uploadHasFiles = computed(() =>
  uploadMode.value === 'file' ? !!uploadFile.value : uploadFolderFiles.value.length > 0,
)

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function onModelUploadSelect(files: File[], tabKey: string) {
  if (tabKey === 'file') {
    uploadFile.value = files[0] ?? null
  } else if (tabKey === 'folder') {
    uploadFolderFiles.value = files
  }
}

// Names the backend recognises and ingests into ModelArtifact. Used by the
// preview list so the user sees what will land in the DB before they submit.
// Kept aligned with _ARTIFACT_NAME_MAP in apps/analysis/views.py — when one
// changes, update the other.
const KNOWN_ARTIFACT_NAMES = new Set([
  'BoxF1_curve.png',
  'BoxP_curve.png',
  'BoxPR_curve.png',
  'BoxR_curve.png',
  'F1_curve.png',
  'P_curve.png',
  'PR_curve.png',
  'R_curve.png',
  'confusion_matrix.png',
  'confusion_matrix_normalized.png',
  'labels.jpg',
  'labels_correlogram.jpg',
  'results.csv',
  'results.png',
  'args.yaml',
])
const SAMPLE_PREFIXES = ['train_batch', 'val_batch']

function basename(path: string): string {
  return path.includes('/') ? path.slice(path.lastIndexOf('/') + 1) : path
}

function isRecognisedArtifact(name: string): boolean {
  if (KNOWN_ARTIFACT_NAMES.has(name)) return true
  return SAMPLE_PREFIXES.some((p) => name.startsWith(p))
}

interface FolderPreview {
  weightsLabel: string | null
  recognised: string[]
  skipped: number
}

const folderPreview = computed<FolderPreview>(() => {
  let weights: File | null = null
  let weightsRank = 99
  const recognised: string[] = []
  let skipped = 0
  for (const f of uploadFolderFiles.value) {
    const rel = (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name
    const tail = basename(rel)
    // weights/best.pt outranks weights/last.pt; the segment match is on the
    // immediate parent so a stray best.pt elsewhere in the tree is ignored.
    const segs = rel.split('/')
    const parent = segs.length >= 2 ? segs[segs.length - 2] : ''
    if (parent === 'weights' && tail === 'best.pt' && weightsRank > 0) {
      weights = f
      weightsRank = 0
    } else if (parent === 'weights' && tail === 'last.pt' && weightsRank > 1) {
      weights = f
      weightsRank = 1
    } else if (isRecognisedArtifact(tail)) {
      recognised.push(tail)
    } else {
      skipped++
    }
  }
  return {
    weightsLabel: weights
      ? (weights as File & { webkitRelativePath?: string }).webkitRelativePath || weights.name
      : null,
    recognised: recognised.sort((a, b) => a.localeCompare(b)),
    skipped,
  }
})

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
  uploadFolderFiles.value = []
  uploadMode.value = 'file'
  uploadError.value = ''
  uploadOpen.value = true
}

async function submitUpload() {
  uploadError.value = ''
  if (!uploadVersionName.value.trim()) {
    uploadError.value = 'Version name is required.'
    return
  }
  const form = new FormData()
  form.append('module', 'pollinators')
  form.append('kind', uploadKind.value)
  form.append('version_name', uploadVersionName.value.trim())
  form.append('description', uploadDescription.value.trim())

  if (uploadMode.value === 'file') {
    if (!uploadFile.value) {
      uploadError.value = 'Pick a .pt or .pth file.'
      return
    }
    form.append('weights_file', uploadFile.value)
  } else {
    if (!uploadFolderFiles.value.length) {
      uploadError.value = 'Pick a training run folder.'
      return
    }
    if (!folderPreview.value.weightsLabel) {
      uploadError.value = 'No weights/best.pt or weights/last.pt found in the selected folder.'
      return
    }
    // Browsers (Firefox at least) strip '/' from FormData filenames as a
    // path-traversal guard, so we can't smuggle the relative path through
    // the filename slot. Send paths as a parallel JSON array in the same
    // order as the file entries; the backend pairs by index.
    const paths: string[] = []
    for (const f of uploadFolderFiles.value) {
      const rel = (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name
      paths.push(rel)
      form.append('artifacts', f)
    }
    form.append('artifact_paths', JSON.stringify(paths))
  }

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

const totalVersions = computed(() => tracks.value.reduce((sum, t) => sum + t.versions.length, 0))

const activeCount = computed(() =>
  tracks.value.reduce((sum, t) => sum + t.versions.filter((v) => v.is_active).length, 0),
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
