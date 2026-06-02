export type PollinatorClass = 'fly' | 'bumblebee' | 'butterfly' | 'other'

export type ReviewerStatus = 'unreviewed' | 'confirmed' | 'corrected' | 'rejected' | 'unsure'

// Which pipeline branch produced a detection. 'both' means the YOLO and
// preprocessing branches agreed on the same region.
export type DetectionSource = 'yolo' | 'preprocessing' | 'both'

export interface BBox {
  x1: number
  y1: number
  x2: number
  y2: number
  w: number
  h: number
}

export interface Detection {
  id: number
  yolo_class: PollinatorClass | null
  yolo_confidence: number | null
  insectnet_class: PollinatorClass | null
  insectnet_confidence: number | null
  // Legacy single-confidence field still surfaced by the detections endpoint.
  // Prefer yolo_confidence / insectnet_confidence when present.
  confidence: number | null
  source: DetectionSource
  reviewer_status: ReviewerStatus
  reviewer_label: PollinatorClass | null
  // True when "Suggest exports" auto-confirmed this detection (cleared both
  // thresholds), as opposed to a manual reviewer confirmation. Drives the
  // blue (auto) vs green (manual) cue on the Export page.
  auto_accepted: boolean
  predicted_class: PollinatorClass | null
  source_image_filename: string
  source_image_url: string | null
  source_image_id: number | null
  crop_url: string | null
  bbox: BBox | null
  excluded_from_export: boolean
  // Per-image flag (same value on every detection sharing an image):
  // when true the image is included in YOLO detector training.
  include_in_training: boolean
}

// Per-run reviewer/export preferences. Any missing key falls back to the
// run's config confidence values via effectiveReviewSettings().
export interface ReviewSettings {
  auto_select?: boolean
  yolo_threshold?: number
  group_threshold?: number
  // Export-page duplicate suppression: two accepted boxes on one image are the
  // same insect when one center is inside the other or their IoU >= this.
  dedup_iou_threshold?: number
}

export interface Run {
  id: number
  name: string
  status: string
  detection_count?: number
  config?: {
    yolo?: { confidence?: number }
    binary_classifier?: { confidence?: number }
    group_classifier?: { confidence?: number }
    preprocessing?: {
      // New runs store [x, y, width, height]; runs created before that store
      // the legacy {x, y, width, height} object. Read via normalizeRoiBbox().
      roi_bbox?: [number, number, number, number] | RoiBoxObject | null
    }
  }
  review_settings?: ReviewSettings
}

export interface DetectionsPage {
  count: number
  next: string | null
  results: Detection[]
}

// Legacy ROI shape: runs created before the switch to a [x,y,w,h] tuple
// stored the drawer's raw object. Kept only so normalizeRoiBbox can read
// older runs; new runs persist the tuple.
export interface RoiBoxObject {
  x: number
  y: number
  width: number
  height: number
}

// Coerce either ROI shape to the [x, y, width, height] tuple the overlay
// and CSV/annotated export expect, or null if absent/malformed. Tolerating
// both shapes lets pre-existing runs keep rendering their ROI.
export function normalizeRoiBbox(
  r: [number, number, number, number] | RoiBoxObject | null | undefined,
): [number, number, number, number] | null {
  if (Array.isArray(r) && r.length === 4 && r.every((n) => typeof n === 'number')) {
    return r as [number, number, number, number]
  }
  if (r && typeof r === 'object' && !Array.isArray(r)) {
    const { x, y, width, height } = r
    if ([x, y, width, height].every((n) => typeof n === 'number')) {
      return [x, y, width, height]
    }
  }
  return null
}

// Resolves a run's effective review thresholds + auto-select toggle.
// Thresholds default to the confidence values the run was processed with
// (YOLO ← config.yolo.confidence, Group ← config.group_classifier
// .confidence) so review starts in the run's own regime; a per-run
// override in review_settings wins when present. Final fallback is 0.5.
export function effectiveReviewSettings(run: Run | null | undefined): {
  autoSelect: boolean
  yolo: number
  group: number
  dedupIou: number
} {
  const rs = run?.review_settings ?? {}
  const cfg = run?.config
  return {
    autoSelect: rs.auto_select ?? false,
    yolo: rs.yolo_threshold ?? cfg?.yolo?.confidence ?? 0.5,
    group: rs.group_threshold ?? cfg?.group_classifier?.confidence ?? 0.5,
    dedupIou: rs.dedup_iou_threshold ?? 0.5,
  }
}
