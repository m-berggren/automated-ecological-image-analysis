import { onMounted, onUnmounted } from 'vue'
import type { Detection, PollinatorClass, ReviewerStatus } from '@/types/pollinator'
import { usePollinatorSettingsStore, type ReviewAction } from '@/stores/pollinatorSettings'

// Keyboard control for the review page. Structural keys (undo, clear-bulk,
// confirm, navigation) are fixed; the action keys (classify 1-4, reject,
// unsure, include-in-training, delete-image) are resolved against the user's
// remappable keymap in the pollinator settings store. The host passes its
// reactive state as getters and its actions as plain callbacks so this stays
// decoupled from the (large) review component.
export interface ReviewKeyboardDeps {
  getSelected: () => Detection | null
  getBulkSize: () => number
  isZoomOpen: () => boolean
  isImageFirst: () => boolean
  getColsPerRow: () => number
  undoLast: () => void
  clearBulk: () => void
  applyToBulk: (status: ReviewerStatus, label: PollinatorClass | null) => void
  confirmAs: (cls: PollinatorClass | null, advance?: boolean) => void
  reject: (advance?: boolean) => void
  markUnsure: (advance?: boolean) => void
  navigate: (delta: number, extend: boolean) => void
  navigateImage: (direction: 1 | -1) => void
  deleteImage: (filename: string) => void
  toggleInclude: (filename: string) => void
  suggestedClass: (d: Detection) => PollinatorClass | null
}

const CLASS_BY_ACTION: Partial<Record<ReviewAction, PollinatorClass>> = {
  classifyFly: 'fly',
  classifyBumblebee: 'bumblebee',
  classifyButterfly: 'butterfly',
  classifyOther: 'other',
}

export function useReviewKeyboard(deps: ReviewKeyboardDeps): void {
  const settings = usePollinatorSettingsStore()

  function resolveAction(key: string): ReviewAction | null {
    const k = key.toLowerCase()
    for (const action of Object.keys(settings.keybindings) as ReviewAction[]) {
      const bound = settings.keybindings[action]
      if (bound && bound.toLowerCase() === k) return action
    }
    return null
  }

  function onKeydown(e: KeyboardEvent) {
    // Inputs keep their own typing + native undo.
    if (
      e.target instanceof HTMLElement &&
      ['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)
    ) {
      return
    }
    // Ctrl/Cmd+Z reverts the last classify gesture. Handled before the
    // selection guard because a keyboard action auto-advances off the crop it
    // changed, so nothing may be selected when the user undoes.
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && (e.key === 'z' || e.key === 'Z')) {
      e.preventDefault()
      deps.undoLast()
      return
    }
    const sel = deps.getSelected()
    if (!sel) return
    if (deps.isZoomOpen()) return
    // Escape clears any bulk selection without losing the focused tile.
    if (e.key === 'Escape' && deps.getBulkSize() > 0) {
      deps.clearBulk()
      e.preventDefault()
      return
    }

    // Fixed structural keys: confirm + navigation. Image-first: up/down cycle
    // source images, left/right cycle crops within the image; crop-first keeps
    // its grid nav (a full row up/down). The physical Delete key stays a fixed
    // alias for delete-image regardless of the remappable binding.
    switch (e.key) {
      case 'Enter':
        deps.confirmAs(deps.suggestedClass(sel), true)
        e.preventDefault()
        return
      case 'ArrowDown':
      case 'j':
        if (deps.isImageFirst()) deps.navigateImage(1)
        else deps.navigate(deps.getColsPerRow(), e.shiftKey)
        e.preventDefault()
        return
      case 'ArrowUp':
      case 'k':
        if (deps.isImageFirst()) deps.navigateImage(-1)
        else deps.navigate(-deps.getColsPerRow(), e.shiftKey)
        e.preventDefault()
        return
      case 'ArrowRight':
      case 'l':
        deps.navigate(1, e.shiftKey)
        e.preventDefault()
        return
      case 'ArrowLeft':
      case 'h':
        deps.navigate(-1, e.shiftKey)
        e.preventDefault()
        return
      case 'Delete':
        if (deps.isImageFirst()) deps.deleteImage(sel.source_image_filename)
        e.preventDefault()
        return
    }

    // Remappable action keys.
    const action = resolveAction(e.key)
    if (!action) return
    const bulk = deps.getBulkSize() > 0
    const cls = CLASS_BY_ACTION[action]
    if (cls) {
      // Bulk-aware: with one or more tiles checkbox-selected the class key
      // applies to the whole bulk, otherwise just the focused tile.
      if (bulk) deps.applyToBulk('corrected', cls)
      else deps.confirmAs(cls, true)
      e.preventDefault()
      return
    }
    switch (action) {
      case 'reject':
        if (bulk) deps.applyToBulk('rejected', null)
        else deps.reject(true)
        break
      case 'unsure':
        if (bulk) deps.applyToBulk('unsure', null)
        else deps.markUnsure(true)
        break
      case 'includeTraining':
        deps.toggleInclude(sel.source_image_filename)
        break
      case 'deleteImage':
        // Image-first only, same as the rail's trash button.
        if (deps.isImageFirst()) deps.deleteImage(sel.source_image_filename)
        break
    }
    e.preventDefault()
  }

  onMounted(() => window.addEventListener('keydown', onKeydown))
  onUnmounted(() => window.removeEventListener('keydown', onKeydown))
}
