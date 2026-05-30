<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
    @click.self="close"
  >
    <!-- max-h-[90vh] + flex column keeps the footer glued to the bottom; the
         body scrolls internally instead of pushing the buttons off-screen. -->
    <div
      class="bg-card border border-border rounded-xl shadow-xl w-full max-w-md max-h-[90vh] flex flex-col"
    >
      <header class="px-5 py-2 border-b border-border flex items-center justify-between shrink-0">
        <h3 class="font-semibold">Upload existing model</h3>
        <button class="text-muted-foreground hover:text-foreground" @click="close">✕</button>
      </header>
      <div class="px-5 py-3 space-y-2 text-sm overflow-y-auto">
        <!-- Kind selector only when there's a real choice (seeds = detector
             only, so it's hidden there). -->
        <label v-if="kindOptions.length > 1" class="block">
          <span class="text-xs font-medium text-muted-foreground">Kind</span>
          <select
            v-model="kind"
            class="mt-1 w-full px-2 py-1.5 rounded border border-border bg-background"
          >
            <option v-for="opt in kindOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
        </label>
        <label
          v-for="f in extraFields"
          :key="f.name"
          class="block"
        >
          <span class="text-xs font-medium text-muted-foreground">
            {{ f.label }}
            <span v-if="f.required" class="text-red-600">*</span>
          </span>
          <input
            v-model="extraValues[f.name]"
            type="text"
            :placeholder="f.placeholder"
            :list="f.options && f.options.length ? `extra-${f.name}-options` : undefined"
            class="mt-1 w-full px-2 py-1.5 rounded border border-border bg-background"
          />
          <datalist v-if="f.options && f.options.length" :id="`extra-${f.name}-options`">
            <option v-for="opt in f.options" :key="opt" :value="opt" />
          </datalist>
          <span v-if="f.help" class="text-[11px] text-muted-foreground">{{ f.help }}</span>
        </label>
        <label class="block">
          <span class="text-xs font-medium text-muted-foreground">
            Version name
            <span class="text-red-600">*</span>
          </span>
          <input
            v-model="versionName"
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
            v-model="description"
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
            compact
            v-model:active-tab="mode"
            :tabs="UPLOAD_TABS"
            :has-files="hasFiles"
            @select="onSelect"
          >
            <template #tabs-after>
              <InfoPopover v-if="mode === 'folder'">
                <div class="font-medium mb-1">Expected folder layout</div>
                <pre class="whitespace-pre text-[11px] leading-snug overflow-x-auto">{{
                  structure
                }}</pre>
                <div class="mt-1.5 text-muted-foreground">
                  Recognised files are ingested; anything else is ignored.
                </div>
              </InfoPopover>
            </template>
          </UploadDropZone>
          <p
            v-if="mode === 'file' && file"
            class="mt-2 text-[11px] text-muted-foreground font-mono"
          >
            {{ file.name }} · {{ formatFileSize(file.size) }}
          </p>
          <div v-if="mode === 'folder' && folderFiles.length" class="mt-2 text-[11px] space-y-1">
            <div>
              <span class="text-muted-foreground">Weights: </span>
              <span v-if="folderPreview.weightsLabel" class="font-mono">
                {{ folderPreview.weightsLabel }}
              </span>
              <span v-else class="text-red-600">
                not found (need best.pt/.pth or last.pt/.pth, ideally under weights/)
              </span>
            </div>
            <div v-if="folderPreview.recognised.length">
              <span class="text-muted-foreground">
                Artifacts ({{ folderPreview.recognised.length }}):
              </span>
              <div class="mt-0.5 max-h-32 overflow-y-auto font-mono leading-snug pl-2">
                <div v-for="name in folderPreview.recognised" :key="name">{{ name }}</div>
              </div>
            </div>
            <div v-else class="text-muted-foreground">Artifacts: none recognised.</div>
            <div v-if="folderPreview.skipped > 0" class="text-muted-foreground">
              {{ folderPreview.skipped }} other file(s) will be ignored.
            </div>
          </div>
        </div>
        <p v-if="error" class="text-xs text-red-600">{{ error }}</p>
      </div>
      <footer class="px-5 py-3 border-t border-border flex items-center justify-end gap-2 shrink-0">
        <button
          class="px-3 py-1.5 rounded-md text-sm font-medium text-muted-foreground hover:bg-muted"
          :disabled="submitting"
          @click="close"
        >
          Cancel
        </button>
        <button
          class="px-3 py-1.5 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="submitting"
          @click="submit"
        >
          <span v-if="submitting">Uploading…</span>
          <span v-else>Upload</span>
        </button>
      </footer>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import InfoPopover from '@/components/InfoPopover.vue'
import UploadDropZone, { type UploadTab } from '@/components/UploadDropZone.vue'
import { api } from '@/api'

export interface ModelKindOption {
  value: string
  label: string
}

// Caller-defined extra inputs (e.g. seeds passes a species datalist).
// Rendered as text inputs with an optional <datalist> for autocomplete +
// free-text. Submitted to the backend as a parameters_extra JSON blob that
// gets merged into ModelVersion.parameters.
export interface ModelUploadExtraField {
  name: string
  label: string
  required?: boolean
  placeholder?: string
  // When non-empty, renders a datalist of suggested values; users can pick
  // one or type their own.
  options?: string[]
  defaultValue?: string
  help?: string
}

const props = withDefaults(
  defineProps<{
    open: boolean
    // Pipeline module the version belongs to (e.g. 'pollinators', 'seeds').
    module: string
    // Selectable kinds. One option → the Kind selector is hidden.
    kindOptions: ModelKindOption[]
    // Per-kind expected folder layout, shown in the info popover. A built-in
    // YOLO detector layout covers any kind not present here.
    structures?: Record<string, string>
    // Extra fields stored in ModelVersion.parameters. Seeds uses this for
    // a `species` datalist so a hand-uploaded model is grouped correctly.
    extraFields?: ModelUploadExtraField[]
  }>(),
  { structures: () => ({}), extraFields: () => [] },
)

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'uploaded'): void
}>()

const kind = ref<string>(props.kindOptions[0]?.value ?? 'detector')
const versionName = ref('')
const description = ref('')
const extraValues = ref<Record<string, string>>({})
const file = ref<File | null>(null)
const folderFiles = ref<File[]>([])
const mode = ref<'file' | 'folder'>('file')
const submitting = ref(false)
const error = ref('')

function resetExtras() {
  const next: Record<string, string> = {}
  for (const f of props.extraFields) next[f.name] = f.defaultValue ?? ''
  extraValues.value = next
}

// Reset the form each time the dialog opens.
watch(
  () => props.open,
  (isOpen) => {
    if (!isOpen) return
    kind.value = props.kindOptions[0]?.value ?? 'detector'
    versionName.value = ''
    description.value = ''
    file.value = null
    folderFiles.value = []
    mode.value = 'file'
    error.value = ''
    resetExtras()
  },
)

function close() {
  emit('update:open', false)
}

const UPLOAD_TABS: UploadTab[] = [
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
    placeholder: 'Drop a training run folder or click to browse',
    helper: 'See the ⓘ next to "Source" for the exact folder layout.',
  },
]

// Default YOLO/Ultralytics run layout. Callers can override or add per-kind
// layouts (e.g. classifier checkpoints) via the `structures` prop.
const DEFAULT_DETECTOR_STRUCTURE = [
  'run/        (Ultralytics output)',
  '├─ weights/',
  '│  └─ best.pt',
  '├─ results.csv',
  '├─ results.png',
  '├─ confusion_matrix.png',
  '├─ PR_curve.png / F1_curve.png / …',
  '├─ args.yaml',
  '└─ val_batch*.jpg',
].join('\n')

const structure = computed(() => props.structures[kind.value] ?? DEFAULT_DETECTOR_STRUCTURE)

const hasFiles = computed(() =>
  mode.value === 'file' ? !!file.value : folderFiles.value.length > 0,
)

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function onSelect(files: File[], tabKey: string) {
  if (tabKey === 'file') {
    file.value = files[0] ?? null
  } else if (tabKey === 'folder') {
    folderFiles.value = files
  }
}

// Names the backend recognises and ingests into ModelArtifact. Kept aligned
// with _ARTIFACT_NAME_MAP in apps/analysis/views.py — when one changes,
// update the other.
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

// Rank candidate weight files: best > last, weights/ subfolder preferred but
// not required. Suffix match so classifier checkpoints
// (efficientnet_binary_best.pth, group_insectnet_best.pth) and Ultralytics'
// weights/best.pt all count. 99 = not a weight.
function weightRank(parent: string, tail: string): number {
  const lower = tail.toLowerCase()
  const isBest = lower.endsWith('best.pt') || lower.endsWith('best.pth')
  const isLast = lower.endsWith('last.pt') || lower.endsWith('last.pth')
  if (!isBest && !isLast) return 99
  return (parent === 'weights' ? 0 : 2) + (isBest ? 0 : 1)
}

const folderPreview = computed<FolderPreview>(() => {
  let weights: File | null = null
  let weightsRank = 99
  const recognised: string[] = []
  let skipped = 0
  for (const f of folderFiles.value) {
    const rel = (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name
    const tail = basename(rel)
    const segs = rel.split('/')
    const parent = segs.length >= 2 ? segs[segs.length - 2] : ''
    const rank = weightRank(parent, tail)
    if (rank < 99) {
      if (rank < weightsRank) {
        weights = f
        weightsRank = rank
      }
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

async function submit() {
  error.value = ''
  if (!versionName.value.trim()) {
    error.value = 'Version name is required.'
    return
  }
  // Required-extra-field validation before opening a network request.
  for (const f of props.extraFields) {
    if (f.required && !(extraValues.value[f.name] ?? '').trim()) {
      error.value = `${f.label} is required.`
      return
    }
  }
  const form = new FormData()
  form.append('module', props.module)
  form.append('kind', kind.value)
  form.append('version_name', versionName.value.trim())
  form.append('description', description.value.trim())
  // Send extra fields as one JSON blob so the backend can merge them into
  // ModelVersion.parameters without per-field special-casing.
  if (props.extraFields.length) {
    const extra: Record<string, string> = {}
    for (const f of props.extraFields) {
      const v = (extraValues.value[f.name] ?? '').trim()
      if (v) extra[f.name] = v
    }
    if (Object.keys(extra).length) {
      form.append('parameters_extra', JSON.stringify(extra))
    }
  }

  if (mode.value === 'file') {
    if (!file.value) {
      error.value = 'Pick a .pt or .pth file.'
      return
    }
    form.append('weights_file', file.value)
  } else {
    if (!folderFiles.value.length) {
      error.value = 'Pick a training run folder.'
      return
    }
    if (!folderPreview.value.weightsLabel) {
      error.value =
        'No weights file found. Expected best.pt/.pth or last.pt/.pth (ideally under weights/).'
      return
    }
    // Browsers strip '/' from FormData filenames as a path-traversal guard,
    // so paths ride along as a parallel JSON array; the backend pairs by index.
    const paths: string[] = []
    for (const f of folderFiles.value) {
      const rel = (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name
      paths.push(rel)
      form.append('artifacts', f)
    }
    form.append('artifact_paths', JSON.stringify(paths))
  }

  submitting.value = true
  try {
    const res = await api('/api/analysis/models/', { method: 'POST', body: form })
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data.detail || `HTTP ${res.status}`)
    }
    emit('uploaded')
    close()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    submitting.value = false
  }
}
</script>
