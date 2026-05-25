# pollinator

Insect detection and classification pipeline. A **library**: no entry-point
script, no Django. Consumed by the Django backend (`apps/pollinator/`) at
runtime and by the [Colab notebooks](../notebooks/) for research training.

See also: [ml-pipelines overview](../README.md) and the
[project architecture](../../README.md#architecture).

## Three model tracks

The pipeline runs three models that play distinct roles:

| Track | Model | Role |
|-------|-------|------|
| `detector` | YOLO (SAHI-tiled) | Find insect bounding boxes anywhere in the full frame. |
| `binary` | EfficientNet | Gate motion crops: insect vs background. |
| `group` | InsectNet | Classify accepted crops: bumblebee / fly / butterfly / other. |

YOLO sees every frame. The binary and group models only see crops produced by
the background-subtraction motion branch.

## Layered structure

Each level has one job; higher levels compose lower ones.

```
pollinator/
  detection/        YoloDetector            SAHI-tiled YOLO inference
  classification/   BinaryClassifier        insect vs background
                    GroupClassifier         species group
  preprocessing/    background.py           motion subtraction, contour filtering,
                                            large-motion tiling, StaticFilter
                    roi.py                  ROI/zone setup, in-zone test
                    exif.py                 capture time + flash/fog skip gates
                    config.py               DEFAULT_CONFIG
  training/         train_yolo, train_binary, train_group   model fitting
                    slicing                 slice_dataset (tile images + labels)
                    splits                  restratify_by_plot, plot_holdout
                    sampling, datasets, backbones
  workflows/        the public seam consumers import
```

## The `workflows/` seam

All entry points live here. `training_binary` and `training_group` are thin
pass-throughs to `training/`; they exist so every entry point is in one place.

```python
from pollinator.workflows.inference import PollinatorInferencePipeline
from pollinator.workflows.training_yolo import retrain_yolo
from pollinator.workflows.training_binary import retrain_binary   # -> training.train_binary
from pollinator.workflows.training_group import retrain_group     # -> training.train_group

# Stage classes / building blocks the notebooks import directly:
from pollinator.detection.yolo_detector import YoloDetector
from pollinator.training import slice_dataset, restratify_by_plot
```

## Inference

`PollinatorInferencePipeline` is **stateful across frames** (it carries the
previous frame, the previous capture time, the sampled global background, and an
optional static-object filter). The driver loop lives in the caller, not here:

```python
pipeline = PollinatorInferencePipeline(
    yolo_model=..., binary_model=..., group_model=...,
    yolo_confidence=..., yolo_slice_size=..., yolo_overlap=...,
    binary_threshold=..., group_threshold=..., iou_threshold=...,
)
pipeline.prime(image_paths)          # sample the global background once
for path in image_paths:             # the loop is the caller's
    detections = pipeline.process_image(path)
```

The constructor takes **no default thresholds**: the caller owns the operating
point. Production defaults live in `apps/pollinator/services.py`; CLI defaults
live in `workflows/inference.py`'s argparse block. `YoloDetector` keeps its own
defaults because the notebooks instantiate it directly.

What `process_image` does per frame:

1. Read the image; reset the motion reference if the EXIF time gap to the
   previous frame exceeds `max_gap_seconds`.
2. Build the ROI zone; strip the camera info-bar (`strip_height`).
3. If a flash/fog EXIF skip flag fires, return no detections for the frame
   (skips both YOLO and motion).
4. Run YOLO over the full frame.
5. Motion branch: background-subtract against the previous frame (or the global
   background), filter contours, gate each crop with the binary classifier,
   label survivors with the group classifier.
6. Merge YOLO and motion detections by IoU into one record list.

### Background reference

`prime()` samples a global median background once. Per frame, the previous frame
is preferred as the reference; the global background is the fallback. Both must
match the current frame's shape, so frames of a different resolution simply skip
the motion branch (YOLO still runs).

## Training

```python
retrain_yolo(...)     # YOLO detector (own logic in workflows/training_yolo.py)
retrain_binary(...)   # EfficientNet gate  (-> training/train_binary.py)
retrain_group(...)    # InsectNet group    (-> training/train_group.py)
```

Lower-level helpers in `training/`:

- `slice_dataset` tiles full images and their labels into model-sized slices.
- `restratify_by_plot` / `plot_holdout` build plot-stratified splits so no camera
  plot leaks between train and val.

The backend's `TrainingJob` flow (in `apps/pollinator/`) collects reviewed
detections, calls the matching `retrain_*` function, and registers the result as
a new `ModelVersion`. The notebooks call the same functions for from-scratch
training on a CVAT export.

## Configuration

`preprocessing/config.py` holds `DEFAULT_CONFIG` (background sampling, ROI,
contour filtering, EXIF skip flags, tiling). The backend merges the upload
page's `preprocessing` settings over these defaults before constructing the
pipeline. `skip_flash` / `skip_foggy` skip a flagged frame entirely (no YOLO,
no motion).

## CLI (offline / research)

```bash
python -m pollinator.workflows.inference \
    --image_dir path/to/images \
    --output_json out.json \
    --yolo_model best.pt --binary_model bin.pth --group_model grp.pth
```
