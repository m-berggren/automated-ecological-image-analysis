# seeds (backend app)

The seed module's backend. It drives the
[`ml-pipelines/seed_src`](../../ml-pipelines/seed_src/README.md) library for
inference and training, persists results onto the shared
[`analysis`](../analysis/README.md) models, and exposes the module-specific REST
endpoints.

Up one level: [apps/README.md](../README.md). Project view:
[architecture](../../README.md#architecture).

> Note: the backend is still changing; treat this README as a map, not a spec.

## What lives here

| File | Purpose |
|------|---------|
| `services.py` | Inference orchestration: load models, run the SAHI tiled inference loop, persist
OBB detections + areas, generate export imagesctions + crops. |
| `training.py` | Training orchestration: format datasets, spawn YOLO OBB training jobs with UI progress callbacks, register the new `ModelVersion`. |
| `reference_seed_service.py` | Business logic for establishing a baseline healthy reference seed to categorize remaining seeds as active vs. aborted based on area thresholds. |
| `views.py` | Detections list/detail, reference seed configuration, export bundle generation (CSV, annotated images), and training creation. |

## Inference

The single driver loop is `process_seeds_run` in `services.py` (nbypassing the ML library's hardcoded testing wrappers to inject dynamic UI config). Outline:

1. Updates the `InferenceRun` to `RUNNING` and extracts the frontend configuration (`slice_overlap_ratio`, `confidence_threshold`, `model_version_id`).
2. `load_model(model_path)` fetches the requested YOLO weights into memory.
3. For each image in the upload: check pause/cancel, run SAHI's `get_sliced_prediction` (768x768 tiles), persist results, checkpoint progress.

Because seeds require Oriented Bounding Boxes (OBB), `process_seeds_run` extracts the rotated polygon coordinates -- or falls back to Horizontal Bounding Boxes (HBB) -- and calculates the pixel area for every prediction. These are persisted as Detection rows. It simultaneously calls `generate_prediction_visuals` to save an annotated version of the image into Django's ImageAsset storage for the UI to display.

See the pipeline internals in
[ml-pipelines/seed_src](../../ml-pipelines/seed_src/README.md#inference).

## One training track in a multi-species split

Unlike the pollinator pipeline, the seeds module relies on a single model track: the YOLO OBB detector.
However, models are highly specialized and trained per species (current species include CAT, PEH, PHYCA, VAU).

| Track | Retrains | Trains on |
|-------|----------|-----------|
| `detector` | YOLO (OBB) | fully-reviewed **images** (+ polygon labels) |

`services.bootstrap_species_dataset` dynamically builds the expected directory structures and YAML configs whenever a new species is registered. When a `TrainingJob` is spawned, it collects the eligible pool of accepted images for that specific species, triggers the `train_species_model` callback, and registers the output as a new `ModelVersion`.

## Active vs. Aborted Seed Filtering

A core backend responsibility unique to this module is seed viability filtering. Because inactive/aborted/non-viable seeds can be present on the evaluated images, the backend allows users to designate one detection per image as a "Reference Seed" after the SAHI inference run has completed.

This step of the pipeline calculates the area of all polygons. Any seed whose area is <= 30% of the area of the selected Reference Seed is given a `seed_status` of 'aborted', while the rest are marked 'active'. The number of 'active' seeds and the status of each seed is displayed for the user to review and potentially modify.

During the export phase (`generate_export_bundle`), the backend permanently draws these final statuses onto the exported images (green = 'active', red = 'aborted') based on both the ML calculation and human reviewer overrides.

## Endpoints

Mounted at `/api/seeds/`:

```
runs/<id>/detections/          list detections for a run
detections/<id>/               detection detail
runs/<id>/export-bundle/       generate summary data and final green/red annotated images
runs/<id>/set-reference/       assign a specific detection as the area baseline
training/                      start a training job for a specific species
```

Generic run/model lifecycle (start, pause, set-active, etc.) is served by the
[`analysis`](../analysis/README.md#endpoints) app.
