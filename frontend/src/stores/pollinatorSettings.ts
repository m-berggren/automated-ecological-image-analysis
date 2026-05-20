import { defineStore } from 'pinia'

export type ReviewLayout = 'crop-first' | 'image-first'

const STORAGE_KEY = 'pollinatorSettings'

// Defaults match the hardcoded bbox strokes the review page used before these
// became configurable: zinc-600 for a normal box, red-500 for the highlighted/
// selected box.
const DEFAULT_ANNOTATION_COLOR = '#52525b'
const DEFAULT_ANNOTATION_HIGHLIGHT_COLOR = '#ef4444'

interface PersistedShape {
  reviewLayout: ReviewLayout
  annotationColor: string
  annotationHighlightColor: string
}

const DEFAULTS: PersistedShape = {
  reviewLayout: 'image-first',
  annotationColor: DEFAULT_ANNOTATION_COLOR,
  annotationHighlightColor: DEFAULT_ANNOTATION_HIGHLIGHT_COLOR,
}

function isReviewLayout(v: unknown): v is ReviewLayout {
  return v === 'crop-first' || v === 'image-first'
}

function isHexColor(v: unknown): v is string {
  return typeof v === 'string' && /^#[0-9a-fA-F]{6}$/.test(v)
}

function load(): PersistedShape {
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) return { ...DEFAULTS }
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
    }
  } catch {
    return { ...DEFAULTS }
  }
}

// User-level pollinator preference (localStorage, global across runs). The
// review layout and annotation colors live here; export thresholds and the
// auto-select toggle moved to per-run storage in the DB (run.review_settings),
// so they're remembered per run rather than globally per user.
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
    resetLayout() {
      this.reviewLayout = 'image-first'
      this.persist()
    },
  },
})
