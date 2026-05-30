# ml-pipelines

The machine-learning core of the project. Framework-agnostic PyTorch / YOLO
code with **no Django imports**. It is consumed in two places:

- the Django backend (`apps/`), at runtime, for production inference and
  retraining;
- the Colab notebooks (`notebooks/`), for from-scratch research training.

Both callers import the same functions, so research and production never drift
apart on the actual model logic.

## Two pipelines

| Package | Domain | How it is run |
|---------|--------|---------------|
| [`pollinator/`](pollinator/README.md) | Insect detection + classification | A **library**. Imported by the backend and the notebooks; no entry-point script. |
| [`seed_src/`](seed_src/README.md) | Seed detection (YOLO oriented bounding boxes) | A **library**. Imported by the backend. It can also be used for as a set of scripts via `main.py` with a settings block at the top. |

These are independent. They share nothing except living under this folder.

For deeper detail see the per-pipeline READMEs: [pollinator](pollinator/README.md),
[seed_src](seed_src/README.md). Project-wide context is in the
[root README](../README.md#architecture).

---

## pollinator/

Layered so each level has one job. Higher levels compose lower ones.

```
pollinator/
  detection/        YoloDetector (SAHI-tiled YOLO inference)
  classification/   BinaryClassifier (insect vs background),
                    GroupClassifier (bumblebee/fly/butterfly/other)
  preprocessing/    background subtraction, ROI/zone, EXIF gates, config
  training/         building blocks: train_yolo, train_binary, train_group,
                    slicing, splits, sampling, datasets, backbones
  workflows/        public entry points (the seam consumers import)
```

### The `workflows/` seam

Everything a consumer needs is exposed here. Two of the training workflows are
thin pass-throughs to `training/`; they exist so all entry points live in one
place.

```python
# Inference (stateful, per-image)
from pollinator.workflows.inference import PollinatorInferencePipeline

# Retraining
from pollinator.workflows.training_yolo import retrain_yolo
from pollinator.workflows.training_binary import retrain_binary   # -> training.train_binary
from pollinator.workflows.training_group import retrain_group     # -> training.train_group

# Stage classes (used directly by the notebooks)
from pollinator.detection.yolo_detector import YoloDetector
from pollinator.training import slice_dataset, restratify_by_plot
```

### Inference model

`PollinatorInferencePipeline` is stateful across frames. The driver loop lives
in the **caller** (the Django worker in `apps/pollinator/services.py`), not in
the library:

```python
pipeline = PollinatorInferencePipeline(
    yolo_model=..., binary_model=..., group_model=...,
    yolo_confidence=..., yolo_slice_size=..., yolo_overlap=...,
    binary_threshold=..., group_threshold=..., iou_threshold=...,
)
pipeline.prime(image_paths)          # sample the global background once
for path in image_paths:
    detections = pipeline.process_image(path)
```

Per image, `process_image` runs YOLO and a background-subtraction motion branch
(motion crops are gated by the binary classifier, then labelled by the group
classifier), then merges the two detectors by IoU. Flash/foggy frames are
skipped entirely when the corresponding config flags are set.

The constructor takes **no default thresholds**: callers own their operating
point. Production defaults live in `apps/pollinator/services.py`; the CLI
defaults live in `workflows/inference.py`'s argparse block. `YoloDetector`
keeps its own defaults because the notebooks instantiate it directly.

### Configuration

`preprocessing/config.py` holds `DEFAULT_CONFIG` (background sampling, ROI,
contour filtering, EXIF skip flags, tiling). The backend merges the upload
page's `preprocessing` settings over these defaults before constructing the
pipeline.

### CLI (offline / research)

```bash
python -m pollinator.workflows.inference \
    --image_dir path/to/images \
    --output_json out.json \
    --yolo_model best.pt --binary_model bin.pth --group_model grp.pth
```

---

## seed_src/

A standalone seed-detection pipeline using a YOLO26n **OBB** (oriented bounding
box) model with SAHI-tiled inference. Unlike `pollinator/`, it is not wired into
the backend; it is driven directly by `main.py`.

```
seed_src/
  inference/    run_sahi (sliced prediction), confidence_analyzer
  training/     train_species_model (fresh or fine-tune), slice_dataset
  utils/        label extraction, metrics, agreement/active-seed calculators,
                helpers (data routing, model loading, run naming)
main.py         orchestrator: SETTINGS block + run logic
```

### Running

Edit the `SETTINGS` block at the top of `main.py` (paths, `RETRAIN`,
`TRAINING_MODE` = `fresh` | `finetune`, per-species fine-tune weights, epochs,
learning rates), then:

```bash
cd ml-pipelines
python main.py
```

Models are trained per species (one OBB detector each) and evaluated with the
precision/recall/F1 helpers in `utils/metrics.py`.

---

## Notebooks

`notebooks/` holds the Colab research notebooks (e.g. the thesis YOLO training
notebook). They import this package via `AEA_PIPELINE_ROOT` on `sys.path` and
add Colab/Drive plumbing plus CVAT-export dataset prep on top of the shared
`pollinator.*` functions. See the notebooks themselves for usage; a dedicated
README is planned.
