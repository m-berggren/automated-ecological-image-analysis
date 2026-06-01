<template>
  <PageHeader title="Models" subtitle="Trained model versions per seed species" />

  <div class="flex-1 flex flex-col min-h-0">
    <!-- Filter chips -->
    <div class="px-8 py-3 border-b border-border bg-surface flex items-center gap-3 flex-wrap">
      <div class="flex gap-1 text-xs">
        <button
          v-for="opt in filterOptions"
          :key="opt.value"
          class="px-3 py-1.5 rounded-md font-medium transition-colors"
          :class="
            speciesFilter === opt.value
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:bg-muted'
          "
          @click="speciesFilter = opt.value"
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
            <span class="text-xs text-muted-foreground italic">{{ track.species }}</span>
            <span class="text-xs text-muted-foreground">
              · {{ track.versions.length }}
              {{ track.versions.length === 1 ? 'version' : 'versions' }}
            </span>
          </header>

          <div v-if="!track.versions.length" class="px-5 py-6 text-sm text-muted-foreground">
            No trained versions yet. Start a training job from the
            <RouterLink to="/seeds/training" class="text-primary hover:underline"
              >Training page</RouterLink
            >.
          </div>

          <table v-else class="w-full text-sm">
            <thead class="text-xs text-muted-foreground bg-muted/30">
              <tr>
                <th class="text-left font-medium px-5 py-2 w-10">Default</th>
                <th class="text-left font-medium px-3 py-2">Name</th>
                <th class="text-left font-medium px-3 py-2">MAE</th>
                <th class="text-left font-medium px-3 py-2">F1</th>
                <th class="text-left font-medium px-3 py-2">Recall</th>
                <th class="text-left font-medium px-3 py-2">Samples</th>
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
                    {{ formatMetric(v.metrics['mae']) }}
                  </td>
                  <td class="px-3 py-3 font-mono text-xs">
                    {{ formatMetric(v.metrics['f1']) }}
                  </td>
                  <td class="px-3 py-3 font-mono text-xs">
                    {{ formatMetric(v.metrics['recall']) }}
                  </td>
                  <td class="px-3 py-3 text-xs">{{ v.sample_count.toLocaleString() }}</td>
                  <td class="px-3 py-3 text-xs text-muted-foreground">
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
                <tr v-if="expandedIds.has(v.id)" class="border-t border-border bg-muted/10">
                  <td></td>
                  <td colspan="7" class="px-3 py-4">
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
                    <div class="text-xs text-muted-foreground mt-3 pt-3 border-t border-border">
                      Trained {{ formatRelative(v.trained_at) }}
                      <template v-if="v.training_duration_seconds">
                        · took {{ humanDuration(v.training_duration_seconds) }}
                      </template>
                      · {{ v.sample_count.toLocaleString() }} samples
                    </div>
                    <div v-if="v.artifacts.length > 0" class="mt-4 pt-3 border-t border-border">
                      <button
                        class="flex w-full items-center gap-1.5 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground"
                        @click="toggleArtifacts(v.id)"
                      >
                        <span>{{ artifactsExpanded.has(v.id) ? '▾' : '▸' }}</span>
                        <span>Training artifacts ({{ v.artifacts.length }})</span>
                      </button>
                      <div v-if="artifactsExpanded.has(v.id)" class="mt-3 space-y-4">
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
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </section>
      </div>
    </div>

    <ModelUploadDialog
      v-model:open="uploadOpen"
      module="seeds"
      :kind-options="UPLOAD_KIND_OPTIONS"
      :extra-fields="UPLOAD_EXTRA_FIELDS"
      @uploaded="onModelUploaded"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import ModelUploadDialog from '@/components/ModelUploadDialog.vue'
import { Trash2 } from 'lucide-vue-next'
import { api } from '@/api'
import { confirm, alert } from '@/lib/confirm'
import { useAuthStore } from '@/stores/auth'

interface Artifact {
  id: number
  kind: string
  caption: string
  url: string | null
}

interface Version {
  id: number
  version_name: string
  is_active: boolean
  metrics: Record<string, number>
  sample_count: number
  trained_at: string
  training_duration_seconds: number
  parameters: Record<string, unknown>
  artifacts: Artifact[]
}

interface Track {
  id: string
  label: string
  species: string
  versions: Version[]
}

interface VersionMock extends Omit<Version, 'trained_at' | 'artifacts'> {
  trained_at_offset_seconds: number
  artifacts?: Artifact[]
}
interface TrackMock extends Omit<Track, 'versions'> {
  versions: VersionMock[]
}

const route = useRoute()
const auth = useAuthStore()
const loading = ref(true)
const loadError = ref('')
const tracks = ref<Track[]>([])
const speciesFilter = ref<string>('all')
const expandedIds = ref<Set<number>>(new Set())
const artifactsExpanded = ref<Set<number>>(new Set())
const deletingId = ref<number | null>(null)

// Mirrors REQUIRE_STAFF_FOR_UPLOAD in PollinatorsModels.vue and the backend
// gate in ModelVersionListCreateView. Flip both to True to restore the
// staff-only check.
const REQUIRE_STAFF_FOR_UPLOAD = false
const canUploadModels = computed(() =>
  REQUIRE_STAFF_FOR_UPLOAD ? auth.user?.is_staff === true : !!auth.user,
)
const canDeleteModels = canUploadModels

// Display labels + ordering per ModelArtifactKind. Image kinds render as
// thumbnails; non-image kinds (results.csv) render as a download link.
// Same list as PollinatorsModels.vue — keep them in sync if you extend it.
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
  const byKind = new Map<string, Artifact[]>()
  for (const a of v.artifacts) {
    if (!byKind.has(a.kind)) byKind.set(a.kind, [])
    byKind.get(a.kind)!.push(a)
  }
  return ARTIFACT_GROUPS.filter((g) => byKind.has(g.kind)).map((g) => ({
    ...g,
    items: byKind.get(g.kind)!,
  }))
}

function toggleArtifacts(id: number) {
  const next = new Set(artifactsExpanded.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  artifactsExpanded.value = next
}

// Seeds only have one model kind today; the dialog hides the kind selector
// when there's a single option.
const UPLOAD_KIND_OPTIONS = [{ value: 'detector', label: 'YOLO detector' }]

// Existing species the user might pick from; the input is free-text so
// typing a brand-new species creates a new track on the next reload.
const knownSpecies = computed<string[]>(() => {
  const set = new Set<string>()
  for (const t of tracks.value) {
    const s = String(t.species ?? t.id ?? '').toLowerCase()
    if (s) set.add(s)
  }
  return Array.from(set).sort()
})

const UPLOAD_EXTRA_FIELDS = computed(() => [
  {
    name: 'species',
    label: 'Species',
    required: true,
    placeholder: 'e.g. phyca',
    options: knownSpecies.value,
    help: 'Pick an existing species or type a new one. Drives the grouping on this page.',
  },
])

const uploadOpen = ref(false)

function openUpload() {
  uploadOpen.value = true
}

async function onModelUploaded() {
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
  const { default: mocks } = await import('@/mocks/seed-models.json')
  const raw = (mocks as unknown as Record<string, { tracks: TrackMock[] } | undefined>).default
  if (!raw) return null
  const now = Date.now()
  return raw.tracks.map((t) => ({
    id: t.id,
    label: t.label,
    species: t.species,
    versions: t.versions.map((v) => ({
      ...v,
      trained_at: new Date(now + v.trained_at_offset_seconds * 1000).toISOString(),
    })),
  }))
}

async function loadFromApi() {
  try {
    const res = await api('/api/analysis/models/?module=seeds')
    if (!res.ok) {
      loadError.value = `HTTP ${res.status}`
      return
    }
    const versions: any[] = await res.json()
    console.log('versions from API:', versions.map(v => ({ id: v.id, name: v.version_name, active: v.is_active })))

    const speciesMap = new Map<string, Track>()

    for (const v of versions) {
      const species = (v.parameters?.species ?? '').toLowerCase()
      const id = species.toUpperCase()

      if (!speciesMap.has(id)) {
        speciesMap.set(id, {
          id,
          label: id,
          species: v.parameters?.species ?? id,
          versions: [],
        })
      }

      speciesMap.get(id)!.versions.push({
        id: v.id,
        version_name: v.version_name,
        is_active: v.is_active,
        metrics: v.metrics ?? {},
        sample_count: v.sample_count ?? 0,
        trained_at: v.trained_at ?? v.created_at,
        training_duration_seconds: v.training_duration_seconds ?? 0,
        parameters: v.parameters ?? {},
        artifacts: v.artifacts ?? [],
      })
    }

    tracks.value = Array.from(speciesMap.values())
  } catch (e) {
    console.error('loadFromApi error:', e)
    loadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

const filterOptions = computed(() => {
  const opts: Array<{ value: string; label: string; count: number }> = [
    { value: 'all', label: 'All', count: totalVersions.value },
  ]
  for (const t of tracks.value) {
    opts.push({ value: t.id, label: t.label, count: t.versions.length })
  }
  return opts
})

const filteredTracks = computed(() => {
  if (speciesFilter.value === 'all') return tracks.value
  return tracks.value.filter((t) => t.id === speciesFilter.value)
})

const totalVersions = computed(() => tracks.value.reduce((sum, t) => sum + t.versions.length, 0))
const activeCount = computed(() =>
  tracks.value.reduce((sum, t) => sum + t.versions.filter((v) => v.is_active).length, 0),
)

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
function humanDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`
  const hours = Math.floor(seconds / 3600)
  const mins = Math.round((seconds % 3600) / 60)
  return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`
}
function formatParam(value: unknown): string {
  if (typeof value === 'number') {
    if (value < 0.01 && value > 0) return value.toExponential(1)
    return String(value)
  }
  return String(value)
}

async function setDefault(track: Track, v: Version) {
  for (const x of track.versions) x.is_active = false
  v.is_active = true

  // Call backend to persist
  try {
    await api(`/api/analysis/models/${v.id}/set-active/`, {
      method: 'POST',
    })
  } catch (e) {
    console.error('Failed to set active model:', e)
  }
}

function toggleExpanded(id: number) {
  const next = new Set(expandedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedIds.value = next
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
</script>
