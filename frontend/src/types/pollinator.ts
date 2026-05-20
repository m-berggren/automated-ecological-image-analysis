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
  predicted_class: PollinatorClass | null
  source_image_filename: string
  source_image_url: string | null
  source_image_id: number | null
  crop_url: string | null
  bbox: BBox | null
  excluded_from_export: boolean
  // Per-image flag (same value on every detection sharing an image):
  // when true the image is excluded from YOLO detector training.
  exclude_from_training: boolean
}

// Per-run reviewer/export preferences. Any missing key falls back to the
// run's config confidence values via effectiveReviewSettings().
export interface ReviewSettings {
  auto_select?: boolean
  yolo_threshold?: number
  group_threshold?: number
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
      roi_bbox?: [number, number, number, number] | null
    }
  }
  review_settings?: ReviewSettings
}

export interface DetectionsPage {
  count: number
  next: string | null
  results: Detection[]
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
} {
  const rs = run?.review_settings ?? {}
  const cfg = run?.config
  return {
    autoSelect: rs.auto_select ?? false,
    yolo: rs.yolo_threshold ?? cfg?.yolo?.confidence ?? 0.5,
    group: rs.group_threshold ?? cfg?.group_classifier?.confidence ?? 0.5,
  }
}
