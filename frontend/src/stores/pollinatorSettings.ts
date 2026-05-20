import { defineStore } from 'pinia'

export type ReviewLayout = 'crop-first' | 'image-first'

const STORAGE_KEY = 'pollinatorSettings'

interface PersistedShape {
  reviewLayout: ReviewLayout
}

const DEFAULTS: PersistedShape = {
  reviewLayout: 'image-first',
}

function isReviewLayout(v: unknown): v is ReviewLayout {
  return v === 'crop-first' || v === 'image-first'
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
    }
  } catch {
    return { ...DEFAULTS }
  }
}

// User-level pollinator preference. Only the review layout lives here now;
// export thresholds and the auto-select toggle moved to per-run storage in
// the DB (run.review_settings), so they're remembered per run rather than
// globally per user.
export const usePollinatorSettingsStore = defineStore('pollinatorSettings', {
  state: () => load(),

  actions: {
    persist() {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ reviewLayout: this.reviewLayout }))
    },
    setReviewLayout(layout: ReviewLayout) {
      this.reviewLayout = layout
      this.persist()
    },
    resetLayout() {
      this.reviewLayout = 'image-first'
      this.persist()
    },
  },
})
