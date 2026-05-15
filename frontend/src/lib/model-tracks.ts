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
  metrics: Record<string, number>
  parameters: Record<string, unknown>
  created_at: string
  artifacts?: ModelArtifact[]
}

export interface TrackVersion {
  id: number
  version_name: string
  is_active: boolean
  metrics: Record<string, number>
  parameters: Record<string, unknown>
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
    description: 'Pollinator detector',
    metric_label: 'mAP50',
  },
  {
    id: 'binary_classifier',
    label: 'EfficientNet',
    description: 'Insect vs background',
    metric_label: 'accuracy',
  },
  {
    id: 'group_classifier',
    label: 'InsectNet',
    description: 'Bumblebee, fly, butterfly, other',
    metric_label: 'accuracy',
  },
]

export function tracksFromVersions(versions: BackendModelVersion[]): Track[] {
  return POLLINATOR_TRACK_DEFS.map((def) => {
    const matching = versions.filter((v) => v.kind === def.id)
    const trackVersions: TrackVersion[] = matching.map((v) => ({
      id: v.id,
      version_name: v.version_name,
      is_active: v.is_active,
      metrics: v.metrics,
      parameters: v.parameters,
      trained_at: v.created_at,
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
