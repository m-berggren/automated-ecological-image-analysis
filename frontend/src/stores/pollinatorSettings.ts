import { defineStore } from 'pinia'

export type ReviewLayout = 'crop-first' | 'image-first'

// Single-key review shortcuts the user can remap (Settings page). Navigation
// (arrows + h/j/k/l), confirm (Enter), undo (Ctrl/Cmd+Z) and clear-bulk
// (Escape) stay fixed and are not remappable.
export type ReviewAction =
  | 'classifyFly'
  | 'classifyBumblebee'
  | 'classifyButterfly'
  | 'classifyOther'
  | 'reject'
  | 'unsure'
  | 'includeTraining'
  | 'deleteImage'

export const REVIEW_ACTIONS: ReviewAction[] = [
  'classifyFly',
  'classifyBumblebee',
  'classifyButterfly',
  'classifyOther',
  'reject',
  'unsure',
  'includeTraining',
  'deleteImage',
]

export const REVIEW_ACTION_LABELS: Record<ReviewAction, string> = {
  classifyFly: 'Classify: fly',
  classifyBumblebee: 'Classify: bumblebee',
  classifyButterfly: 'Classify: butterfly',
  classifyOther: 'Classify: other',
  reject: 'Reject (background)',
  unsure: 'Mark unsure',
  includeTraining: 'Include image in YOLO training',
  deleteImage: "Reject image's unreviewed crops",
}

export type Keybindings = Record<ReviewAction, string>

const DEFAULT_KEYBINDINGS: Keybindings = {
  classifyFly: '1',
  classifyBumblebee: '2',
  classifyButterfly: '3',
  classifyOther: '4',
  reject: 'x',
  unsure: 'u',
  includeTraining: 'y',
  deleteImage: 'd',
}

// Keys owned by fixed navigation/structural shortcuts; cannot be reassigned to
// a configurable action. Compared lowercased; ' ' is the space bar.
export const RESERVED_KEYS = new Set([
  'enter',
  'escape',
  'z',
  ' ',
  'arrowup',
  'arrowdown',
  'arrowleft',
  'arrowright',
  'h',
  'j',
  'k',
  'l',
])

export type KeybindResult = 'ok' | 'reserved' | 'invalid'

const STORAGE_KEY = 'pollinatorSettings'

// Defaults match the hardcoded bbox strokes the review page used before these
// became configurable: zinc-600 for a normal box, red-500 for the highlighted/
// selected box.
const DEFAULT_ANNOTATION_COLOR = '#52525b'
const DEFAULT_ANNOTATION_HIGHLIGHT_COLOR = '#ef4444'
// blue-500, the ROIOverlay's previous hardcoded default.
const DEFAULT_ROI_COLOR = '#3b82f6'

interface PersistedShape {
  reviewLayout: ReviewLayout
  annotationColor: string
  annotationHighlightColor: string
  roiColor: string
  keybindings: Keybindings
}

const DEFAULTS: PersistedShape = {
  reviewLayout: 'image-first',
  annotationColor: DEFAULT_ANNOTATION_COLOR,
  annotationHighlightColor: DEFAULT_ANNOTATION_HIGHLIGHT_COLOR,
  roiColor: DEFAULT_ROI_COLOR,
  keybindings: { ...DEFAULT_KEYBINDINGS },
}

function isReviewLayout(v: unknown): v is ReviewLayout {
  return v === 'crop-first' || v === 'image-first'
}

function isHexColor(v: unknown): v is string {
  return typeof v === 'string' && /^#[0-9a-fA-F]{6}$/.test(v)
}

// Merge stored bindings over the defaults, keeping only valid single-char,
// non-reserved, conflict-free assignments. Anything dropped falls back to the
// default for that action, so a corrupt entry can never strand the reviewer.
function normalizeKeybindings(raw: unknown): Keybindings {
  const out: Keybindings = { ...DEFAULT_KEYBINDINGS }
  if (raw && typeof raw === 'object') {
    const taken = new Set<string>()
    for (const action of REVIEW_ACTIONS) {
      const v = (raw as Record<string, unknown>)[action]
      if (typeof v === 'string' && v.length === 1) {
        const k = v.toLowerCase()
        if (!RESERVED_KEYS.has(k) && !taken.has(k)) {
          out[action] = v
          taken.add(k)
        }
      }
    }
  }
  return out
}

function load(): PersistedShape {
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) return { ...DEFAULTS, keybindings: { ...DEFAULT_KEYBINDINGS } }
  try {
    const parsed = JSON.parse(raw) as Partial<PersistedShape> | null
    if (!parsed || typeof parsed !== 'object') throw new Error('not an object')
    return {
      reviewLayout: isReviewLayout(parsed.reviewLayout)
        ? parsed.reviewLayout
        : DEFAULTS.reviewLayout,
      annotationColor: isHexColor(parsed.annotationColor)
        ? parsed.annotationColor
        : DEFAULTS.annotationColor,
      annotationHighlightColor: isHexColor(parsed.annotationHighlightColor)
        ? parsed.annotationHighlightColor
        : DEFAULTS.annotationHighlightColor,
      roiColor: isHexColor(parsed.roiColor) ? parsed.roiColor : DEFAULTS.roiColor,
      keybindings: normalizeKeybindings(parsed.keybindings),
    }
  } catch {
    return { ...DEFAULTS, keybindings: { ...DEFAULT_KEYBINDINGS } }
  }
}

// User-level pollinator preference (localStorage, global across runs). The
// review layout, annotation colors, and review keybindings live here; export
// thresholds and the auto-select toggle moved to per-run storage in the DB
// (run.review_settings), so they're remembered per run rather than per user.
export const usePollinatorSettingsStore = defineStore('pollinatorSettings', {
  state: () => load(),

  actions: {
    persist() {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          reviewLayout: this.reviewLayout,
          annotationColor: this.annotationColor,
          annotationHighlightColor: this.annotationHighlightColor,
          roiColor: this.roiColor,
          keybindings: this.keybindings,
        }),
      )
    },
    setReviewLayout(layout: ReviewLayout) {
      this.reviewLayout = layout
      this.persist()
    },
    setAnnotationColor(color: string) {
      if (!isHexColor(color)) return
      this.annotationColor = color
      this.persist()
    },
    setAnnotationHighlightColor(color: string) {
      if (!isHexColor(color)) return
      this.annotationHighlightColor = color
      this.persist()
    },
    setRoiColor(color: string) {
      if (!isHexColor(color)) return
      this.roiColor = color
      this.persist()
    },
    // Assign `key` to `action`. Must be a single, non-reserved character; the
    // key is stolen from any other action that held it so bindings stay unique
    // (that other action is left unbound until the user sets it again).
    setKeybinding(action: ReviewAction, key: string): KeybindResult {
      if (!key || key.length !== 1) return 'invalid'
      const k = key.toLowerCase()
      if (RESERVED_KEYS.has(k)) return 'reserved'
      const next: Keybindings = { ...this.keybindings }
      for (const a of REVIEW_ACTIONS) {
        if (a !== action && next[a].toLowerCase() === k) next[a] = ''
      }
      next[action] = key
      this.keybindings = next
      this.persist()
      return 'ok'
    },
    resetKeybindings() {
      this.keybindings = { ...DEFAULT_KEYBINDINGS }
      this.persist()
    },
    resetLayout() {
      this.reviewLayout = 'image-first'
      this.persist()
    },
  },
})
