# pollinator (backend app)

The pollinator module's backend. It drives the
[`ml-pipelines/pollinator`](../../ml-pipelines/pollinator/README.md) library for
inference and training, persists results onto the shared
[`analysis`](../analysis/README.md) models, and exposes the module-specific REST
endpoints.

Up one level: [apps/README.md](../README.md). Project view:
[architecture](../../README.md#architecture).

> Note: the backend is still changing; treat this README as a map, not a spec.

## What lives here

| File | Purpose |
|------|---------|
| `services.py` | Inference orchestration: build the pipeline, run the per-image loop, persist detections + crops. |
| `training.py` | Training orchestration: collect the eligible sample pool per track, spawn jobs, build datasets, register the new `ModelVersion`. |
| `models.py` | `PollinatorDetection`: 1:1 side table on `Detection` holding dual-detector fields (`yolo_*`, `insectnet_*`) and `DetectionSource`. |
| `views.py` | Detections list/detail, exports (CSV, crops zip, annotated zip), training create, training pool. |
| `exif.py` | Pollinator EXIF helpers (capture time, exclusion determination). |
| `serializers.py` | DRF serializers for the endpoints above. |

## Inference

The single driver loop is `run_inference_pipeline` in `services.py` (not in the
ML library). Outline:

1. `_build_pipeline(run)` resolves the active model files and merges the run's
   config, then constructs `PollinatorInferencePipeline` (passing explicit
   thresholds; the library has no default operating point).
2. `pipeline.prime(image_paths)` samples the global background once.
3. For each image in capture-time order: check pause/cancel, call
   `pipeline.process_image`, persist results, checkpoint progress.

`process_image` runs YOLO and a background-subtraction motion branch (gated by
the binary classifier, labelled by the group classifier) and merges them by IoU.
Each merged box is stored as a `Detection` (+ `PollinatorDetection` side row
recording which detector(s) fired) with a per-detection crop. The run row is
saved after every image, enabling pause / resume / cancel.

See the pipeline internals in
[ml-pipelines/pollinator](../../ml-pipelines/pollinator/README.md#inference).

## Three training tracks

Retraining mirrors the three models, each retrained independently:

| Track | Retrains | Trains on |
|-------|----------|-----------|
| `detector` | YOLO | fully-reviewed **images** (+ bbox labels) |
| `binary` | EfficientNet | reviewed detection **crops**, insect vs background |
| `group` | InsectNet | reviewed detection **crops**, by class |

`run_training_job` collects the eligible pool, exports a dataset (crops or YOLO
labels), calls the matching `retrain_*` workflow, and registers the output as a
new `ModelVersion` for that track.

## The training-pool consumption model

A detection is eligible to train a track when it has been reviewed and has not
already been consumed by a past **completed** job for that track:

- `TrainingJob.training_detections` (M2M) records exactly which detections a job
  consumed. `_consumed_detection_ids(track)` is the union over completed jobs.
- `_collect_detector_pool` / `_collect_binary_pool` / `_collect_group_pool`
  return the currently-eligible detections, minus consumed ones, with the
  effective class = `reviewer_label or predicted_class`.
- The `training/pool/` endpoint reports `available`, `consumed`,
  `new_since_active` (reviewed after the active model trained), `by_class`
  counts, and a capped list of `samples` (crop URLs for binary/group, per-image
  rows for detector) for the review drawer.

Availability is **per track**: the same detection can train the detector and the
group classifier independently, tracked separately via each job's M2M.

## Endpoints

Mounted at `/api/pollinator/`:

```
runs/<id>/detections/          list detections for a run
detections/<id>/               detection detail
runs/<id>/export.csv           per-image survey CSV
runs/<id>/export-crops.zip     detection crops
runs/<id>/export-annotated.zip source images with boxes drawn
training/                      start a training job (per track)
training/pool/?track=<track>   eligible-sample pool for a track
```

Generic run/model lifecycle (start, pause, set-active, etc.) is served by the
[`analysis`](../analysis/README.md#endpoints) app.
