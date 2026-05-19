import { defineStore } from 'pinia'

export type ReviewLayout = 'crop-first' | 'image-first'

// Only YOLO and Group are reviewer-relevant for export gating. The
// binary classifier is a pipeline-internal insect/background filter
// applied at inference; any detection reaching the reviewer has already
// passed it, so re-gating on binary_confidence here adds no signal.
export interface ExportThresholds {
  yolo: number
  group: number
}

const STORAGE_KEY = 'pollinatorSettings'

interface PersistedShape {
  reviewLayout: ReviewLayout
  exportAutoSelect: boolean
  exportThresholds: ExportThresholds
}

const DEFAULTS: PersistedShape = {
  reviewLayout: 'crop-first',
  exportAutoSelect: false,
  exportThresholds: { yolo: 0.5, group: 0.5 },
}

function isReviewLayout(v: unknown): v is ReviewLayout {
  return v === 'crop-first' || v === 'image-first'
}

function clamp01(v: unknown): number | null {
  if (typeof v !== 'number' || Number.isNaN(v)) return null
  return Math.max(0, Math.min(1, v))
}

function load(): PersistedShape {
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) return { ...DEFAULTS, exportThresholds: { ...DEFAULTS.exportThresholds } }
  try {
    const parsed = JSON.parse(raw) as Partial<PersistedShape> | null
    if (!parsed || typeof parsed !== 'object') throw new Error('not an object')
    return {
      reviewLayout: isReviewLayout(parsed.reviewLayout)
        ? parsed.reviewLayout
        : DEFAULTS.reviewLayout,
      exportAutoSelect:
        typeof parsed.exportAutoSelect === 'boolean'
          ? parsed.exportAutoSelect
          : DEFAULTS.exportAutoSelect,
      exportThresholds: {
        yolo: clamp01(parsed.exportThresholds?.yolo) ?? DEFAULTS.exportThresholds.yolo,
        group: clamp01(parsed.exportThresholds?.group) ?? DEFAULTS.exportThresholds.group,
      },
    }
  } catch {
    return { ...DEFAULTS, exportThresholds: { ...DEFAULTS.exportThresholds } }
  }
}

export const usePollinatorSettingsStore = defineStore('pollinatorSettings', {
  state: () => load(),

  actions: {
    persist() {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          reviewLayout: this.reviewLayout,
          exportAutoSelect: this.exportAutoSelect,
          exportThresholds: this.exportThresholds,
        } satisfies PersistedShape),
      )
    },
    setReviewLayout(layout: ReviewLayout) {
      this.reviewLayout = layout
      this.persist()
    },
    setExportAutoSelect(on: boolean) {
      this.exportAutoSelect = on
      this.persist()
    },
    setExportThreshold(model: keyof ExportThresholds, value: number) {
      const clamped = clamp01(value)
      if (clamped === null) return
      this.exportThresholds[model] = clamped
      this.persist()
    },
    reset() {
      this.reviewLayout = DEFAULTS.reviewLayout
      this.exportAutoSelect = DEFAULTS.exportAutoSelect
      this.exportThresholds = { ...DEFAULTS.exportThresholds }
      this.persist()
    },
  },
})
