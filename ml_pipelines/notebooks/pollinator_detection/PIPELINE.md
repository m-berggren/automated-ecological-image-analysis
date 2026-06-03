# Pipeline Technical Documentation

This document covers how the pollinator ML pipeline works, where data comes from,
how training data is collected, and how the two detection approaches relate to each other.
For quick-start instructions, see [README.md](README.md).

---

## Contents

1. [Two complementary pipelines](#1-two-complementary-pipelines)
2. [Pollinator classes](#2-pollinator-classes)
3. [Annotations and ground truth](#3-annotations-and-ground-truth)
4. [How training crops are acquired](#4-how-training-crops-are-acquired)
5. [Initial training vs incremental retraining](#5-initial-training-vs-incremental-retraining)
6. [Crop-based pipeline in depth](#6-crop-based-pipeline-in-depth)
7. [YOLO pipeline in depth](#7-yolo-pipeline-in-depth)
8. [Training notebooks: Colab and local](#8-training-notebooks-colab-and-local)
9. [Model outputs and versioning](#9-model-outputs-and-versioning)
10. [Active learning loop](#10-active-learning-loop)
11. [Relationship to the Django production system](#11-relationship-to-the-django-production-system)
12. [Deploying models to the production system](#12-deploying-models-to-the-production-system)

---

## 1. Two complementary pipelines

The project uses two fundamentally different approaches and they are designed to be
run in parallel, not as alternatives.

### Crop-based pipeline
Runs in `infer_cropbased.ipynb`.

1. **Preprocessing (motion detection):** for each pair of consecutive frames, a background
   subtraction algorithm finds regions that changed — these are candidate insect bounding boxes.
2. **Crop extraction:** each candidate region is cut out (with padding) and saved as a crop image.
3. **Classification (optional):** one or more CNN models classify each crop as background,
   bumblebee, fly, butterfly, or other.

The preprocessing step is independent of the classification step. You can run
`infer_cropbased.ipynb` in `MODE = 'preprocess'` to extract crops without any model loaded
(useful for data collection), or in `MODE = 'infer'` to do both in one pass.

> **Note on the notebook name:** `infer_cropbased.ipynb` does *both* preprocessing and
> inference — the name only reflects the most common use case. If you want to collect
> training data without running a classifier, set `MODE = 'preprocess'` in Cell 3.

### YOLO pipeline
Runs in `infer_yolo.ipynb`.

A YOLO26n (Ultralytics) model trained end-to-end on CVAT-annotated full images. It detects
and classifies pollinators in a single forward pass with no separate preprocessing step.
The YOLO model tends to find insects that motion detection misses (e.g. stationary insects
or insects on very busy backgrounds). It also provides an independent second opinion for
evaluating annotation quality.

### Using them together
Both pipelines write results in a comparable format. `evaluate.ipynb` ingests the outputs
of both and computes precision/recall/F1 against the same CVAT ground truth, so you can
directly compare detection rates and classification accuracy side by side.

---

## 2. Pollinator classes

Four pollinator groups are used across all models:

| Class | What it covers | iNaturalist taxon | ID |
|-------|---------------|------------------|----|
| **bumblebee** | Bumble bees (*Bombus* spp.) | *Bombus* (genus) | **52775** |
| **fly** | All flies (Diptera) | Diptera (order) | **47822** |
| **butterfly** | Butterflies and moths (Lepidoptera) | Lepidoptera (order) | **47157** |
| **other** | Beetles, wasps, bugs, and any other insect visitor | Coleoptera / Hymenoptera / Hemiptera | **47208 / 47201 / 47744** |

Verify or look up any ID at `https://www.inaturalist.org/taxa/<id>`.
Place IDs: Sweden = **7599**, Norway = **7016**.

The crop-based classifiers also predict **background** for crops with no insect.
The YOLO model does not need a background class since it only fires on detections.

> **Class name note:** older model checkpoints may store `butterfly_moth` as the class
> name. This is equivalent to `butterfly`. The ALIAS maps in training notebooks handle
> both names.

---

## 3. Annotations and ground truth

### YOLO detector annotations
All bounding box annotations are made in **CVAT** and exported in **YOLO 1.1 format**.

CVAT export structure:
```
yolo.zip
  images/
    train/  val/  test/
  labels/
    train/  val/  test/      ← one .txt per image
  data.yaml
```

Label file format (one line per detection):
```
class_id  cx  cy  width  height
```
All coordinates are normalised to [0, 1] relative to image dimensions.
`class_id` is the integer index of the class in `data.yaml` (order = CVAT export order).

The exported `yolo.zip` is placed in the project root (or any path you set in Cell 2 of `train_yolo.ipynb`). The notebook extracts and patches it — remapping class indices to whichever subset you choose to train on (`KEEP_CLASSES`).

### Ground truth for evaluation
`evaluate.ipynb` uses the same CVAT annotations as ground truth.
The raw `.txt` files live in `data/evaluation/annotations/{dataset_name}/obj_train_data/`.
These match the images in `data/evaluation/images/`.

---

## 4. How training crops are acquired

Training crops for the crop-based classifiers can come from three sources. The first
two produce crops from the same field images; the third adds web images for generalisation.

### Method A — preprocessing pipeline (primary source for initial training)

This is how the first labeled dataset was built and remains the standard way to collect
new training data from field images.

```
Camera folder (raw JPG images)
      ↓  [optional] tools/triage/frame_flag_mac.py or feh-triage.sh
         → flag interesting frames to prioritise
      ↓  infer_cropbased.ipynb  (MODE = 'preprocess', no classifiers loaded)
         → background subtraction extracts candidate regions
         → crops/ folder: one JPEG per candidate bounding box
         → results.csv: one row per crop with bbox coords, no predictions
      ↓  tools/labeling/crop_labeler.py
         → human labels each crop: background / bumblebee / fly / butterfly / other / unsure
         → crops moved into annotated_crops/{dataset_name}/{class}/
```

The preprocessing step runs without any trained models — you only need raw images.
This means you can build the initial labeled dataset entirely from field images before
any classifier exists.

### Method B — inference-based crop selection (incremental retraining)

Once a classifier exists and its confidence scores are reliable, new labelled data can
be gathered more efficiently by using the classifier's own uncertainty to prioritise
which crops to label.

> **Prerequisite: trustworthy model.** `prepare_retrain.ipynb` skips crops the model is
> confident about and only queues uncertain ones for review. If confidence scores are
> not reliable (early-stage or poorly-performing models), this filtering is not useful —
> use Method A (label everything from scratch with `crop_labeler.py`) until the model
> is accurate enough to trust.

**Full path (model is trustworthy, large runs):**
```
Camera folder (raw JPG images)
      ↓  infer_cropbased.ipynb  (MODE = 'infer', classifiers loaded)
         → full inference: preprocessing + classification
         → crop_results/{run_name}/{camera}/crops/*.jpg  +  results.csv
      ↓  prepare_retrain.ipynb
         → selects only low-confidence crops (below CONF_THRESHOLD_LOW)
         → high-confidence crops enter retrain unchanged, no human review
         → copies uncertain crops to outputs/training/retrain_review/{class}/
      ↓  tools/labeling/crop_labeler.py
           --results retrain_review/  --output annotated_crops/
         → human confirms or corrects each uncertain crop
         → crops moved to annotated_crops/{dataset_name}/{class}/
```

**When model is not yet trustworthy — label everything (Method A):**
```
      ↓  infer_cropbased.ipynb
      ↓  tools/labeling/crop_labeler.py
           --results crop_results/run_XX/  --output annotated_crops/
         → label all crops; ignore predicted confidence
```

### Method C — web images (group classifier augmentation only)

`tools/data_prep/download_web_images.py` downloads research-grade photos from iNaturalist
(Sweden and Norway) for fly, butterfly, and other insect classes.

For the **group / 5-class classifier**: used as Stage 1 training data to improve
generalisation, especially for rare classes like butterfly.

For the **binary classifier**: all web image classes count as `insect` — set
`USE_WEB_FOR_BINARY = True` in `train_binary_group.ipynb` or `retrain_cropbased.ipynb`
(enabled by default).

```
download_web_images.py
  → data/training/web_images/batch_YYYYMMDD_HHMMSS/{class}/
  → set WEB_BATCHES in train_binary_group.ipynb or train_5class.ipynb to select batches ([] = all)
```

---

## 5. Initial training vs incremental retraining

### Initial training (Methods A + C)

The first labeled dataset was built by:
1. Running the preprocessing pipeline on raw field images (no classifier needed)
2. Using `crop_labeler.py` to label the resulting crops
3. Supplementing with iNaturalist web images (group classifier only)

Training notebooks: `train_binary_group.ipynb`, `train_5class.ipynb`, `train_yolo.ipynb`.

Labeled crops are stored in two subfolders of `annotated_crops/`:
- `labeled_ls/` — labeled via LabelStudio annotation tool
- `labeled_mb/` — labeled via manual batch (`crop_labeler.py`)

The `colab_master_pipeline.ipynb` reads both as `data_dirs = ['labeled_ls/', 'labeled_mb/']`.
The standalone training notebooks point directly to `annotated_crops/` and read all subfolders.

### Incremental retraining (Method B)

After the pipeline is running, `retrain_cropbased.ipynb` fine-tunes the binary, 5-class, and 4-class InsectNet classifiers using new labeled crops from inference runs. Key differences from
initial training:

- Uses a **lower learning rate** (`LR_FINETUNE = 1e-4` vs `1e-3`) to avoid overwriting
  existing learned features
- Optionally **freezes the backbone** (`FREEZE_BACKBONE = True`) for small datasets
- **Backs up** existing weights before overwriting so you can roll back if metrics drop
- The same `annotated_crops/` folder is the data source — new crops are simply merged in

After retraining, re-run inference with a new `RUN_NAME` and compare metrics in
`evaluate.ipynb` to verify the model improved.

---

## 6. Crop-based pipeline in depth

### Detection (preprocessing)

The preprocessing stage uses rolling-window background subtraction:

1. Each frame is compared against the previous frame (or a short rolling average)
2. Pixel differences above `darker_threshold` are flagged as foreground
3. Vegetation is masked out using HSV colour ranges
4. Morphological operations (open/close) clean up the mask
5. Contours above `min_contour_area` become candidate bounding boxes
6. Nearby boxes are merged; very large regions are handled as "large motion" tiles

#### Frame skip logic

Before motion detection runs, two checks can skip a frame entirely (skipped frames still get a row in `results.csv` with `skip=True` and a `skip_reason`):

| Check | Config key | Default | Trigger |
|---|---|---|---|
| Flash (night shot) | `skip_flash` | `True` | EXIF Flash tag ≠ 0 |
| Foggy / blurry | `skip_foggy` | `True` | Laplacian variance < `foggy_threshold` |

The Laplacian is computed on the image **after** the strip is removed and at whatever `detection_scale` is set, so lowering `detection_scale` also lowers the measured sharpness. Use `detection_scale=1.0` (the default) to keep the Laplacian on full-resolution pixels. The per-frame variance is always written to `results.csv` as `laplacian_var` for post-hoc inspection.

#### Bottom-strip removal

Wingscapes cameras overlay a text bar at the bottom of each image (date, time, temperature). The pipeline removes this strip before processing:

- `strip_height` (default `120` px) — how many pixels to remove from the bottom.

#### Key detection parameters (set in Cell 3 of `infer_cropbased.ipynb`)

- `darker_threshold` — sensitivity; lower = more detections, more false positives
- `enable_large_motion` — enables tile-based detection for big motion events
- `min_contour_area` — minimum pixel area for a detection
- `detection_scale` — downscale factor for CV operations (1.0 = full resolution, recommended)
- `foggy_threshold` — Laplacian variance below this → frame skipped as blurry (default `20`)
- `strip_height` — pixels to remove from the bottom strip (default `120`)

Each run is identified by a `RUN_NAME` and its full config is saved to
`crop_results/{RUN_NAME}/run_config.json` for reproducibility. If a run with the
same `RUN_NAME` already exists, the notebook will raise a `FileExistsError` — change
`RUN_NAME` before re-running to avoid overwriting previous results.

### Classification pipelines

Multiple classifiers can be run on the same crops in a single pass. Each pipeline
adds columns to `results.csv` prefixed with its name:

| Pipeline name | Architecture | How it works |
|---|---|---|
| `two_stage` | EfficientNet-B2 (binary) + InsectNet (4-class) | binary gate first, then group classification for detections |
| `five_class_eff` | EfficientNet-B2 (5-class) | single model, background is one of the 5 classes |
| `five_class_ins` | InsectNet/RegNet (5-class) | same but InsectNet backbone |

Predictions from all pipelines are compared in `evaluate.ipynb`.

### Output structure

```
outputs/inference/crop_results/{RUN_NAME}/
  {camera_folder}/
    results.csv          ← one row per candidate crop (all pipeline predictions)
    crops/               ← extracted crop images
    debug/               ← annotated frames showing detected bboxes
  run_config.json        ← exact preprocessing + pipeline parameters
```

---

## 7. YOLO pipeline in depth

### Model

The YOLO detector uses **Ultralytics YOLO26n** (`yolo26n.pt`). This is the default in
`colab_master_pipeline.ipynb` and in `train_yolo.ipynb`. The standalone `train_yolo.ipynb`
defaults to `yolo26n.pt` — verify `MODEL_SIZE` in Cell 2 matches the checkpoint you want.

Two-stage training: Stage 1 freezes the backbone (fast convergence, learns the detection
head); Stage 2 fine-tunes the entire network (best final performance).

### Tile-based training (colab advanced version)

`colab_master_pipeline.ipynb` supports tile-based training: source images are sliced into
overlapping `TILE_SIZE × TILE_SIZE` crops before training so YOLO sees pollinators at
native resolution rather than downsized. This is especially useful for small insects
(30–80 px in 4K source images). The tiled dataset is cached and rebuilt only if the
tile config changes.

### Dataset format

Input: a CVAT YOLO 1.1 export zip with `images/`, `labels/`, and `data.yaml`. Set
`YOLO_ZIP` in Cell 2 of `train_yolo.ipynb` to point to it. The notebook extracts and
patches it each run, remapping class indices to whatever subset you chose with `KEEP_CLASSES`.

You can train on any subset of the four classes by listing them in `KEEP_CLASSES`.
For example `['fly', 'butterfly']` trains a two-class detector and discards all other
annotations. Incrementally add classes as annotation coverage grows.

---

## 8. Training notebooks: Colab and local

There are two kinds of training notebooks: **standalone** (self-contained, no dependencies
beyond pip packages) and **backend-linked** (`colab_master_pipeline.ipynb`, which calls the
`pollinator` package used by the Django backend).

### Standalone notebooks (`train_*.ipynb`)

| Notebook | Trains | Notes |
|---|---|---|
| `train_yolo.ipynb` | YOLO detector | yolo26n, 2-stage, tile-based |
| `train_binary_group.ipynb` | Binary + group (4-class) classifiers | Binary backbone: EfficientNet-B2 or InsectNet (set `BINARY_BACKBONE`); group: InsectNet |
| `train_5class.ipynb` | 5-class classifier | **standalone only** — not in the backend |

All three are fully self-contained: no `pollinator` package needed, run identically on
Colab or locally.

**On Colab:** Runtime → Change runtime type → T4 GPU. Set `BASE_DIR` in Cell 1 to your
Google Drive path. `train_yolo.ipynb` installs `ultralytics` automatically in Cell 3.

**Locally:** Set `BASE_DIR` in Cell 1. Install:
`pip install torch torchvision ultralytics scikit-learn opencv-python pillow`

> **Note on `train_5class.ipynb`:** The 5-class classifier is a research variant that
> collapses background into one of the five output classes. It is not supported by the
> Django backend or the `pollinator` package — use it for offline experiments only.

### `colab_master_pipeline.ipynb`

This is the **backend-linked** master notebook. It calls the `pollinator.workflows`
package from the `ml-pipelines/` folder and trains the **same three models the Django
backend uses**: YOLO, binary classifier, and group classifier. The 5-class classifier is
**not included** because it is not part of the production pipeline.

It requires `ml-pipelines/` on the Python path (`PIPELINE_ROOT` in Cell 0). It covers
YOLO training (with tile slicing), binary training, group training, and inference in a
single notebook. It also supports merging the test split into training data to maximise
Colab GPU use.

Use the **standalone** notebooks for self-contained experiments that don't need the
backend. Use `colab_master_pipeline.ipynb` when training models destined for the Django
production system — it guarantees checkpoint format and hyperparameters match what the
backend expects.

---

## 9. Model outputs and versioning

### Current inference models

The `models/` flat directory holds the models currently used by `infer_cropbased.ipynb`
and `infer_yolo.ipynb`. These are the "active" weights and can be updated by retraining.

| File | Trained by | Used by |
|------|-----------|---------|
| `binary_best.pth` | `train_binary_group.ipynb` | `two_stage` pipeline |
| `4group_insectnet.pth` | `train_binary_group.ipynb` | `two_stage` pipeline (group stage) |
| `5group_efficientnet.pth` | `train_5class.ipynb` | `five_class_eff` pipeline |
| `5group_insectnet.pth` | `train_5class.ipynb` | `five_class_ins` pipeline |
| `yolo_best.pt` | `train_yolo.ipynb` | `infer_yolo.ipynb` |

These filenames are stable conventions — inference notebooks look for these exact names.
If you train a better model, copy it here under the same name (the old weights are
preserved in `outputs/training/model_runs/`).

### Training run outputs (`outputs/training/model_runs/`)

Every training run saves its outputs to a timestamped subdirectory so you have a complete
history of all experiments:

```
outputs/training/model_runs/{name}_{YYYYMMDD_HHMMSS}/
  {model}_best.pth             ← best checkpoint for this run
  {model}_curves.png           ← loss + F1 curves per model
  config.json                  ← training hyperparameters
```

For `train_binary_group.ipynb` the run folder contains two sub-directories (`binary/` and `group/`) with model-specific checkpoints and curves inside each. For `train_5class.ipynb` and `retrain_cropbased.ipynb` the checkpoints and curves are written directly into the run folder.

After a run completes, the notebook also copies the best model to the flat `models/`
directory to make it the new active inference model.

---

## 10. Active learning loop

The full iterative improvement cycle looks like this:

```
1. Collect new camera images
        ↓
2. [optional] tools/triage/frame_flag_mac.py  — flag interesting frames
        ↓
3. infer_cropbased.ipynb  (MODE='infer')
   → preprocessing + current classifiers
   → writes crop_results/{run_name}/{camera}/crops/  +  results.csv
        ↓
4. evaluate.ipynb
   → compare against CVAT ground truth
   → if accuracy is acceptable, no retraining needed → done
        ↓
6a. [model not yet trustworthy — label everything]
    tools/labeling/crop_labeler.py
      --results crop_results/run_XX/  --output annotated_crops/
    → label every crop with source-frame context
    → predicted class shown as default; move files as you confirm/correct
    → progress JSON per camera; quit and resume any time

6b. [model is trustworthy — active-learning loop]
    prepare_retrain.ipynb
      → pre-filters to low-confidence crops (CONF_THRESHOLD_LOW)
      → high-confidence crops skipped; enter retrain with predicted label unchanged
      → output: retrain_review/{class}/
    tools/labeling/crop_labeler.py
      --results retrain_review/  --output annotated_crops/
    → review only the uncertain fraction
        ↓
7. retrain_cropbased.ipynb
   → fine-tunes binary, 5-class, and 4-class InsectNet classifiers
   → new weights → models/ + outputs/training/model_runs/{name}_{timestamp}/
        ↓
8. back to step 3 with new RUN_NAME to verify improvement
```

### YOLO improvement loop

YOLO can be retrained in two ways:

**Via the Django web app** (preferred when the app is running):
The app allows reviewing inference results directly in the browser.
Images with confirmed or corrected bounding-box annotations can trigger a
retraining job from within the app — no manual export step needed.

**Via notebook** (when the app is not available or for larger annotation batches):
1. Annotate new images in CVAT, export as YOLO 1.1 format
2. Set `YOLO_ZIP` in Cell 2 of `train_yolo.ipynb` to point to the exported zip
3. Run `experiments/training/train_yolo.ipynb` — outputs go to `outputs/training/model_runs/yolo_{timestamp}/`
4. Best weights are automatically copied to `models/yolo_best.pt` for inference

Both paths produce the same `models/yolo_best.pt` that `infer_yolo.ipynb` reads.

---

## 11. Relationship to the Django production system

This folder's notebooks are **standalone research tools**. They share model weights with
the Django app but the inference and training pipelines are architecturally different.
Understanding the boundary is important to avoid confusion when handing off models or
comparing results.

### What is independent (no Django dependency)

All of the following work entirely without the Django app or the `pollinator` library:

| Notebook | What it does |
|---|---|
| `experiments/inference/infer_cropbased.ipynb` | Motion detection + crop classification, outputs CSV |
| `experiments/inference/infer_yolo.ipynb` | YOLO detection only, outputs CSV |
| `experiments/evaluation/evaluate.ipynb` | Compares both pipelines against CVAT ground truth |
| `experiments/training/train_binary_group.ipynb` | Trains binary + group classifiers (standalone PyTorch) |
| `experiments/training/train_5class.ipynb` | Trains 5-class classifier (standalone PyTorch) |
| `experiments/training/train_yolo.ipynb` | Trains YOLO detector (standalone Ultralytics) |
| `experiments/training/prepare_retrain.ipynb` | Selects low-confidence crops for relabeling |
| `experiments/training/retrain_cropbased.ipynb` | Fine-tunes binary + group classifiers |
| `tools/` scripts  | All labeling, triage, and data-prep tools |

These notebooks are self-contained: they run on Colab or locally with no knowledge of
Django, no API calls, and no shared database.

### What is connected (`colab_master_pipeline.ipynb`)

`colab_master_pipeline.ipynb` is the **only notebook that imports the `pollinator`
library** (the `ml-pipelines/` backend package). It calls:
- `pollinator.workflows.retrain_yolo` — same function Django's `TrainingJob` uses
- `pollinator.workflows.retrain_binary` — same
- `pollinator.workflows.retrain_group` — same

The **5-class classifier** (`train_5class.ipynb`) is **not included** in this notebook
because the `pollinator` package and Django backend only support the two-stage pipeline
(binary gate → 4-class group classifier). The 5-class variant is a standalone research
notebook only.

Use `colab_master_pipeline.ipynb` when training models destined for Django — it
guarantees checkpoint format and hyperparameters match what the backend expects.
The standalone `train_*.ipynb` notebooks produce compatible weights too, but the master
notebook is the authoritative path for backend-bound models.

### How the production inference pipeline differs

The Django app (`pollinator.workflows.inference.PollinatorInferencePipeline`) **does not
run YOLO and motion detection as separate pipelines**. It runs them together on every
frame and then merges the results by IoU into a single detection list. This is
fundamentally different from how these notebooks work.

Research notebooks:
```
infer_cropbased.ipynb  →  crop_results/  ┐
                                          ├──  evaluate.ipynb  →  compare side-by-side
infer_yolo.ipynb       →  yolo_results/  ┘
```

Production (`PollinatorInferencePipeline`):
```
Each frame:
  YOLO (SAHI-tiled, slice_size=640)  ─────┐
                                           ├──  IoU merge  →  unified detection list
  Motion detection → binary → group  ─────┘
```

In production, a detection can be `source='yolo'` (YOLO only), `source='preprocessing'`
(motion only), or `source='both'` (both agreed, IoU > threshold). Detections with
`source='both'` carry labels and confidence scores from both branches, which the review
UI uses to flag disagreements.

**Practical implications:**
- Accuracy numbers from `evaluate.ipynb` (separate pipelines, ground truth comparison)
  are not directly comparable to accuracy in production (merged pipeline, human review).
- `evaluate.ipynb` is the right tool for measuring model quality during development.
  Production accuracy is measured by the Django review workflow.
- YOLO's SAHI tiling settings in production (`slice_size=640, overlap=0.2`) must match
  what was used during training if you trained with tiling enabled — see
  [§ 12 Deploying models](#12-deploying-models-to-the-production-system).

### Summary table

| | Standalone notebooks | `colab_master_pipeline.ipynb` | Django production |
|---|---|---|---|
| Runs standalone | ✓ | needs `pollinator` library | Django app |
| Trains YOLO | ✓ `train_yolo.ipynb` | ✓ (via `retrain_yolo`) | ✓ `TrainingJob` |
| Trains binary + group | ✓ `train_binary_group.ipynb` | ✓ (via `retrain_binary/group`) | ✓ `TrainingJob` |
| Trains 5-class | ✓ `train_5class.ipynb` | ✗ not included | ✗ not supported |
| Inference approach | YOLO or motion, separate | — | YOLO + motion merged |
| Training entry point | own inline PyTorch/Ultralytics | `pollinator.workflows.*` | `pollinator.workflows.*` |
| Output format | CSV + crops / checkpoints | checkpoints | database + `ModelVersion` |
| Models used | `models/*.pth/.pt` | any path | registered `ModelVersion` |

---

## 12. Deploying models to the production system

The research notebooks (this folder) and the Django production system share the same
underlying `pollinator` Python library. A model trained here can be registered in the
Django app with a single upload step — no format conversion needed.

### Overview

```
Research notebooks (this folder)
  train_binary_group.ipynb  /  train_5class.ipynb  /  train_yolo.ipynb
          ↓  train on Colab or locally
  outputs/training/model_runs/{name}_{timestamp}/
          ↓  best weights copied automatically
  models/binary_best.pth  /  4group_insectnet.pth  /  yolo_best.pt
          ↓  upload via the web frontend
  Django ModelVersion (registered, selectable for inference)
          ↓  Django TrainingJob (active-learning round)
  retrain_binary() / retrain_group() / retrain_yolo()  ← same functions as here
          ↓
  new ModelVersion (incremental, resume_from= previous upload)
```

### Checkpoint format compatibility

The `.pth` files saved by the training notebooks are loaded directly by the
`pollinator.classification` module that the Django app uses. No manual conversion is
needed. The fields that matter:

| Field | Binary classifier | Group classifier |
|---|---|---|
| `state_dict` | ✓ required | ✓ required |
| `img_size` | read (default 256 if absent) | read (default 224 if absent) |
| `classes` | not used (always background/insect) | ✓ required — list of class names |
| `model_name` / arch | auto-detected from `state_dict` keys | auto-detected from `state_dict` keys |

The YOLO model (`yolo_best.pt`) is a standard Ultralytics checkpoint and is loaded
directly by Ultralytics YOLO in the Django backend — no special handling needed.

> **Architecture auto-detection:** `BinaryClassifier` and `GroupClassifier` identify the
> backbone by inspecting the `state_dict` key names — no explicit `model_name` field is
> read. EfficientNet-B2 keys start with `features.`; InsectNet (RegNet-Y-32GF) keys
> contain `trunk_output` or `stem.`. Both architectures produced by the training
> notebooks are recognised correctly.

### Uploading a trained model

After a training run completes, the best weights are in `outputs/training/model_runs/{name}_{timestamp}/`
and also copied to `models/` (flat).

Upload the file through the **web frontend** — navigate to the model management page
and use the upload form. The Django backend registers it as a new `ModelVersion`, which
can then be selected for inference and used as the starting point for future retraining jobs.

### Incremental retraining from a notebook-trained base

When Django's `TrainingJob` runs a retraining round, it calls the same
`retrain_binary()`, `retrain_group()`, and `retrain_yolo()` functions from
`pollinator.workflows`. The `resume_from` parameter points to the currently deployed
`ModelVersion` weights, so the production retraining always starts from the last
uploaded checkpoint — including one you trained here.

This means the standard handoff looks like:
1. Train a strong base model in the notebooks (full dataset, more epochs, Colab GPU)
2. Upload via the web frontend → registered as `ModelVersion` in Django
3. Django retraining jobs take it from there, fine-tuning incrementally as new
   annotations arrive from the field

### Notes

- **YOLO tile size must match.** If you trained YOLO with tiling enabled
  (`use_tiles=True`, `tile_size=640`), the Django inference config must use the same
  tile size. Mismatches will not cause an error but will degrade detection accuracy.
  Document the tile config alongside the uploaded weights.

- **Class order for the group classifier.** The `classes` list stored in the `.pth`
  checkpoint is what `GroupClassifier` uses to map output indices to names. The
  standard order is `['bumblebee', 'fly', 'butterfly', 'other']`. If you train with
  a non-standard subset (e.g. `['fly', 'butterfly']`), the `classes` field will reflect
  that — make sure the Django inference config matches.

- **Rolling back.** All previous `ModelVersion` entries are kept in Django. If a new
  upload degrades accuracy in production, you can switch back to an earlier version
  from the admin interface without re-uploading.

