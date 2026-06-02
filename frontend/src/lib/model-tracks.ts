// Maps the flat ModelVersion[] returned by /api/analysis/models/ into the
// grouped Track shape the Models and Training pages render. Track ids match
// ModelKind values so filter UIs can pass them straight through.

export interface ModelArtifact {
  id: number
  kind: string
  caption: string
  url: string | null
  created_at: string
}

export interface BackendModelVersion {
  id: number
  module: string
  kind: string
  version_name: string
  is_active: boolean
  description?: string
  // Raw, shape varies per track: detector stores {val:{mAP50,...}, test:{...}}
  // with a nested per_class object; classifiers store a flat numeric map.
  // Normalised to a flat numeric map by flattenMetrics before rendering.
  metrics: Record<string, unknown>
  parameters: Record<string, unknown>
  sample_count?: number
  training_duration_seconds?: number
  trained_at?: string | null
  source_model_version?: number | null
  created_at: string
  artifacts?: ModelArtifact[]
}

export interface TrackVersion {
  id: number
  version_name: string
  is_active: boolean
  metrics: Record<string, number>
  parameters: Record<string, unknown>
  sample_count: number
  training_duration_seconds: number
  trained_at: string
  artifacts: ModelArtifact[]
}

export interface Track {
  id: string
  label: string
  description: string
  kind: string
  metric_label: string
  active_version_id: number | null
  versions: TrackVersion[]
}

interface TrackDef {
  id: string
  label: string
  description: string
  metric_label: string
}

const POLLINATOR_TRACK_DEFS: TrackDef[] = [
  {
    id: 'detector',
    label: 'YOLO',
    description: 'Scans every image directly to find and label insects — no motion required.',
    // mAP50 is the headline detector metric stored at model level (recall
    // only exists per-class in the nested metrics, not as a top-level key).
    metric_label: 'mAP50',
  },
  {
    id: 'binary_classifier',
    label: 'Binary Classifier',
    description: 'Step 1 — checks each moving object and decides: is this an insect or just background noise?',
    // F1, not accuracy: the insect/background split is imbalanced (mostly
    // background), so accuracy is inflated by the majority class. F1 balances
    // precision and recall on the insect class we actually care about.
    metric_label: 'f1',
  },
  {
    id: 'group_classifier',
    label: 'Group Classifier',
    description: 'Step 2 — takes confirmed insects from Step 1 and classifies them as fly, bumblebee, butterfly, or other.',
    // Macro-F1 (surfaced as 'f1'): multi-class with a dominant class, so
    // accuracy is dominated by the majority. Macro-F1 weights each class
    // equally — the honest headline for imbalanced taxa.
    metric_label: 'f1',
  },
]

// Flatten a raw metrics blob into a flat numeric map the table can render.
// A nested split dict (detector's val/test) is unwrapped: val keys keep their
// bare name (the primary, e.g. mAP50), other splits are prefixed (test_mAP50).
// Non-numeric leaves (e.g. the per_class object) are dropped.
function flattenMetrics(raw: Record<string, unknown>): Record<string, number> {
  const out: Record<string, number> = {}
  for (const [key, value] of Object.entries(raw ?? {})) {
    if (typeof value === 'number') {
      out[key] = value
    } else if (value && typeof value === 'object') {
      for (const [inner, innerVal] of Object.entries(value as Record<string, unknown>)) {
        if (typeof innerVal === 'number') {
          out[key === 'val' ? inner : `${key}_${inner}`] = innerVal
        }
      }
    }
  }
  return out
}

export function tracksFromVersions(versions: BackendModelVersion[]): Track[] {
  return POLLINATOR_TRACK_DEFS.map((def) => {
    const matching = versions.filter((v) => v.kind === def.id)
    const trackVersions: TrackVersion[] = matching.map((v) => ({
      id: v.id,
      version_name: v.version_name,
      is_active: v.is_active,
      metrics: flattenMetrics(v.metrics),
      parameters: v.parameters,
      sample_count: v.sample_count ?? 0,
      training_duration_seconds: v.training_duration_seconds ?? 0,
      trained_at: v.trained_at ?? v.created_at,
      artifacts: v.artifacts ?? [],
    }))
    const active = trackVersions.find((v) => v.is_active)
    return {
      id: def.id,
      label: def.label,
      description: def.description,
      kind: def.id,
      metric_label: def.metric_label,
      active_version_id: active?.id ?? null,
      versions: trackVersions,
    }
  })
}
