# analysis

The module-agnostic core of the backend. It owns the domain models that every
analysis module reuses (`ModelVersion`, `TrainingJob`, `InferenceRun`,
`Detection`) and the generic machinery for running and training models.
Per-module apps such as [`pollinator`](../pollinator/README.md) build on top of
these.

Up one level: [apps/README.md](../README.md). Project view:
[architecture](../../README.md#architecture).

> Note: the backend is still changing; treat this README as a map, not a spec.

## Models

```
ModelKind            detector | binary | group | ...   (per-track discriminator)
ModelVersion         a trained model: name, kind, module, metrics, active flag,
                     model_file_path (URI), source lineage
ModelArtifactKind    weights | config | ...
ModelArtifact        extra files attached to a ModelVersion
JobStatus            pending | running | paused | completed | cancelled | failed
TrainingJob          one retraining run: config, status, metrics, initiated_by,
                     training_detections (M2M of consumed samples)
InferenceRun         one detection run over an Upload: status, progress counters,
                     per-class / per-source tallies, module
Detection            one predicted box: bbox {x1,y1,x2,y2,w,h}, confidence,
                     predicted_class, reviewer_label, status, crop, area
DetectionStatus      pending | reviewed | ...
```

`Detection.bbox` is written by the ML pipeline as `{x1, y1, x2, y2, w, h}` in
source-image pixels. `Detection.crop` is the per-detection JPEG used by the
review UI and as a training sample. `reviewer_label` holds a reviewer's
correction; the effective class is `reviewer_label or predicted_class`.

Module-specific extras live on 1:1 side tables in the per-module app (e.g.
`pollinator.PollinatorDetection` holds the dual-detector `yolo_*` / `insectnet_*`
fields), keeping `Detection` itself neutral.

## Endpoints

Mounted at `/api/analysis/` (`urls.py`):

```
models/                          list / create ModelVersion
models/<id>/                     retrieve / update
models/<id>/set-active/          activate this version for its track

runs/                            list / create InferenceRun
runs/draft/                      create a draft run
runs/active/                     the currently active run
runs/<id>/                       retrieve
runs/<id>/start|pause|resume|cancel|abort/    lifecycle
runs/<id>/recompute-exclusions/  re-run engulfment exclusion

detections/bulk/                 bulk review/update
detections/<id>/exclude/         toggle exclusion

training/                        list TrainingJob
training/<id>/                   retrieve
training/<id>/cancel/            cancel a running job
```

## Run / train lifecycle

Inference and training execute in daemon threads (see
[apps/README.md](../README.md#background-work)). The pattern:

1. A start endpoint flips the row to `running` and spawns a worker thread.
2. The worker checkpoints progress (processed counts, per-class tallies) to the
   row after each image / step.
3. Pause / resume / cancel are read cooperatively between steps; the worker
   raises a cancellation exception and unwinds cleanly.

Because progress is persisted per step, a paused run resumes from where it
stopped and a crash loses at most one unit of work.

## Supporting modules

| File | Purpose |
|------|---------|
| `crops.py` | `write_detection_crop`: render and save the tight bbox crop for a `Detection` (reads `{x1,y1,x2,y2}`). |
| `storage.py` | `resolve_model_path` (local / `file://` / `s3://` / `gs://` with caching) and `link_or_copy` (hardlink-or-copy, cross-filesystem safe). |
| `cancellation.py` | `RunCancelled` / `RunPaused` primitives shared by inference and training workers. |
| `engulfment.py` | Suppress duplicate detections when one detector's bbox strictly contains another's. |
| `serializers.py` | DRF serializers for the models above. |
