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
  crop_url: string | null
  bbox: BBox | null
  excluded_from_export: boolean
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
}

export interface DetectionsPage {
  count: number
  next: string | null
  results: Detection[]
}
