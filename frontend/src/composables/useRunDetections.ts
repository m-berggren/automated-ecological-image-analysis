import { ref, type Ref } from 'vue'
import { api } from '@/api'
import type { Detection, DetectionsPage, Run } from '@/types/pollinator'

export interface UseRunDetectionsOptions {
  // Called once per detections page as it arrives, before the page's results
  // are appended to detections.value. Lets callers do per-page work (e.g.
  // preloading source-image dimensions) without re-walking the full list.
  onPage?: (results: Detection[]) => void
  // Called after the run is fetched and before page streaming begins. The
  // composable awaits the returned promise, so callers can run dependent
  // setup (e.g. POSTing an exclusion-recompute) that must finish before
  // the first detections page is requested.
  onRunLoaded?: (run: Run) => Promise<void> | void
}

export interface UseRunDetectionsResult {
  run: Ref<Run | null>
  detections: Ref<Detection[]>
  loadProgress: Ref<{ loaded: number; total: number }>
  loading: Ref<boolean>
  loadError: Ref<string>
  load: () => Promise<void>
}

export function useRunDetections(
  runId: string | number,
  options: UseRunDetectionsOptions = {},
): UseRunDetectionsResult {
  const run = ref<Run | null>(null)
  const detections = ref<Detection[]>([])
  const loadProgress = ref({ loaded: 0, total: 0 })
  const loading = ref(true)
  const loadError = ref('')

  async function load() {
    try {
      const runRes = await api(`/api/analysis/runs/${runId}/`)
      if (!runRes.ok) {
        loadError.value = `Run: HTTP ${runRes.status}`
        loading.value = false
        return
      }
      run.value = await runRes.json()
      if (run.value && options.onRunLoaded) {
        await options.onRunLoaded(run.value)
      }

      // Stream pages: paint the first batch immediately so the UI becomes
      // interactive, then keep appending. detections.value is reactive, so
      // any computed downstream of it recomputes per page.
      let next: string | null = `/api/pollinator/runs/${runId}/detections/`
      let firstPage = true
      while (next) {
        // DRF sometimes returns the absolute URL; api() expects a relative path.
        const url: string = next.startsWith('http') ? next.replace(/^https?:\/\/[^/]+/, '') : next
        const res = await api(url)
        if (!res.ok) {
          loadError.value = `Detections: HTTP ${res.status}`
          return
        }
        const page = (await res.json()) as DetectionsPage
        options.onPage?.(page.results)
        detections.value = detections.value.concat(page.results)
        loadProgress.value = { loaded: detections.value.length, total: page.count }
        next = page.next
        if (firstPage) {
          loading.value = false
          firstPage = false
        }
      }
    } catch (e) {
      loadError.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  return { run, detections, loadProgress, loading, loadError, load }
}
