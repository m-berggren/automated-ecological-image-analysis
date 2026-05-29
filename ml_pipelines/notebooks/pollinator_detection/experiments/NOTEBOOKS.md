# experiments/

Standalone notebooks for inference, training, and evaluation. Each notebook is
self-contained — no external package install required. All can be run locally or in
Google Colab (mount Drive in Cell 1).

```
experiments/
├── inference/                      ← run the pipelines on new images
│   ├── infer_cropbased.ipynb       ← motion detection + CNN classifier pipeline
│   └── infer_yolo.ipynb            ← YOLO full-image detector pipeline
├── training/                       ← train and fine-tune models
│   ├── train_binary_group.ipynb    ← train binary + group classifiers from scratch
│   ├── train_5class.ipynb          ← train a single 5-class classifier from scratch
│   ├── train_yolo.ipynb            ← fine-tune YOLO detector (standalone)
│   ├── prepare_retrain.ipynb       ← select uncertain crops for human review
│   └── retrain_cropbased.ipynb     ← fine-tune classifiers with newly labeled crops
└── evaluation/                     ← measure pipeline accuracy
    ├── evaluate.ipynb                        ← compare outputs against ground truth
    ├── yolo_sensitivity_analysis.ipynb       ← YOLO occlusion sensitivity + EigenCAM
    └── crop_classifier_sensitivity_analysis.ipynb  ← crop classifier GradCAM visualisations
```

## Quick reference

| Notebook | Reads from | Writes to |
|----------|-----------|-----------|
| `inference/infer_cropbased.ipynb` | `data/evaluation/images/` | `outputs/inference/crop_results/` |
| `inference/infer_yolo.ipynb` | `data/evaluation/images/` | `outputs/inference/yolo_results/` |
| `evaluation/evaluate.ipynb` | `outputs/inference/*/` + `data/evaluation/annotations/` | `outputs/evaluation/` |
| `evaluation/yolo_sensitivity_analysis.ipynb` | `data/evaluation/images/` + `data/evaluation/annotations/` + `models/yolo_best.pt` | `outputs/evaluation/yolo_sensitivity_{timestamp}/` |
| `evaluation/crop_classifier_sensitivity_analysis.ipynb` | `data/training/annotated_crops/` + `models/` | `outputs/evaluation/crop_sensitivity_{timestamp}/` |
| `training/train_binary_group.ipynb` | `data/training/annotated_crops/` | `outputs/training/model_runs/`, `models/` |
| `training/train_5class.ipynb` | `data/training/annotated_crops/` | `outputs/training/model_runs/`, `models/` |
| `training/train_yolo.ipynb` | CVAT YOLO 1.1 zip (path set in Cell 2) | `outputs/training/model_runs/`, `models/` |
| `training/prepare_retrain.ipynb` | `outputs/inference/crop_results/` | `outputs/training/retrain_review/` |
| `training/retrain_cropbased.ipynb` | `data/training/annotated_crops/` | `outputs/training/model_runs/`, `models/` |

## Colab setup

In each notebook, Cell 1 detects the environment automatically:

```python
IN_COLAB = 'google.colab' in sys.modules
if IN_COLAB:
    from google.colab import drive
    drive.mount('/content/drive')
    # Extracts pollinator-colab.zip from Drive to local SSD for fast I/O
    zipfile.ZipFile('/content/drive/MyDrive/pollinator-colab.zip').extractall('/content/')
    BASE_DIR = Path('/content/pollinator-colab')
else:
    BASE_DIR = Path('...')   # absolute path to this repo on disk
```

**On Colab:** upload `pollinator-colab.zip` to the root of your Google Drive before running.
The zip must have `pollinator-colab/` as its top-level folder. See the Cell 0 markdown in each
notebook for the required zip contents. All other paths are derived from `BASE_DIR` automatically.

## Difference from colab/

The notebooks here are fully self-contained. `colab/colab_master_pipeline.ipynb` calls
the `pollinator` package instead and is used for backend-linked retraining.
The 5-class classifier (`training/train_5class.ipynb`) exists only here — it is not in
the backend package.

---

## inference/

### infer_cropbased.ipynb

The primary inference notebook. Runs the full crop-based pipeline on a set of camera images.

**Notebook cells (labeled Cell 0–8 inside the notebook):**

- **Cell 0** — Colab setup: mount Drive, set `BASE_DIR` (skip locally)
- **Cell 1** — Environment: imports, path definitions
- **Cell 2** — Pipeline code (no edits needed)
- **Cell 3 ← edit before every run** — `RUN_NAME`, `PREPROCESS_CONFIG`, `PIPELINES`
- **Cell 4** — Verify model files exist
- **Cell 5** — Load models, discover camera folders
- **Cell 6** — Run inference (main processing cell)
- **Cell 7** — Quick summary
- **Cell 8** — Organise crops by predicted class *(optional)*

**Key config (Cell 3):**

| Variable | Type | Description |
|----------|------|-------------|
| `RUN_NAME` | `str` | Unique name for this run; notebook raises `FileExistsError` if already exists |
| `PREPROCESS_CONFIG` | `dict` | Motion detection parameters — override individual keys from `DEFAULT_PREPROCESS_CONFIG`; includes `strip_height` |
| `PIPELINES` | `dict` | One entry per classifier pipeline to run; each has `enabled`, `type` (`'two_stage'` or `'five_class'`), model paths, and optionally `conf_threshold`. All enabled pipelines run in parallel and each adds its own columns to `results.csv` |

Key optional fields inside each `PIPELINES` entry (five_class only):

| Key | Default | Effect |
|-----|---------|--------|
| `conf_threshold` | `0` (off) | Predictions below this confidence are reclassified as background. `0.40` removes ~96% of false positives while keeping ~55% of true positives (measured on run_01 against CVAT ground truth). Set to `0` to disable. |

Key toggles inside `PREPROCESS_CONFIG`:

| Key | Default | Effect |
|-----|---------|--------|
| `enable_large_motion` | `True` | Detect large fast-moving objects in addition to frame diffs |
| `darker_threshold` | `15` | Sensitivity of motion detection |
| `min_contour_area` | `200` | Minimum pixel area for a detected contour to become a crop |

**Important:** The notebook raises `FileExistsError` at startup if `RUN_NAME` already exists in
`outputs/inference/crop_results/` **or** in the Drive backup folder. This check covers both
local and Drive paths so a fresh Colab session can't silently overwrite a previous run.
Choose a new name each time.

**Colab auto-save (last cell):** Results are copied from local Colab runtime (`/content/data/`)
to Drive at the end. This is intentional — writing directly to Drive during inference risks
data loss if the session times out.

---

### infer_yolo.ipynb

Runs the YOLO full-image object detector. Detects insects directly without a separate
motion detection step — better at finding insects that motion detection misses.

**Key config (Cell 3):**

| Variable | Type | Description |
|----------|------|-------------|
| `RUN_NAME` | `str` | Unique name for this run |
| `YOLO_WEIGHTS` | `Path` | Path to YOLO weights file (default `models/yolo_best.pt`) |
| `YOLO_CLASSES` | `list` | Class names in the order the model was trained on |
| `YOLO_CONFIG` | `dict` | Detection parameters — see table below |

Key entries inside `YOLO_CONFIG`:

| Key | Default | Effect |
|-----|---------|--------|
| `conf_threshold` | `0.2` | Minimum confidence to keep a detection |
| `nms_iou` | `0.45` | NMS IoU threshold |
| `use_sahi` | `True` | Slice-and-tile detection via SAHI (recommended for full-res images) |
| `sahi_slice` | `640` | Tile size for SAHI inference |
| `sahi_overlap` | `0.2` | Overlap fraction between SAHI tiles |
| `sahi_conf` | `0.05` | Per-tile confidence threshold before NMS |
| `save_crops` | `True` | Save cropped detection patches |
| `strip_height` | `120` | Pixels to crop from frame bottom (camera OSD bar) |

Output goes to `outputs/inference/yolo_results/{RUN_NAME}/`:
- `yolo_results.csv` — one row per detection: camera folder, image name, bbox, class, confidence
- `yolo_crops/` — cropped detection patches (if `save_crops = True`)

Use `evaluation/evaluate.ipynb` to compare this against the crop-based pipeline.

---

## training/

### train_binary_group.ipynb

Trains the two-stage crop classifier from scratch.

- **Binary classifier:** EfficientNet-B2 or InsectNet backbone, 2 classes (insect / background).
  Backbone chosen via `BINARY_BACKBONE`; optimises for insect recall so real insects are not missed.
  Web images (`data/web_images/`) are added as extra insect data when `USE_WEB_FOR_BINARY = True`.
- **Group classifier:** InsectNet backbone, 4 classes (bumblebee / fly / butterfly / other).
  Reads from the four insect class folders only (no background). Uses web images for Stage 1.

Both classifiers write timestamped run folders to `outputs/training/model_runs/` and copy best
weights to `models/binary_best.pth` and `models/4group_insectnet.pth` on completion.
When `BINARY_BACKBONE = 'both'`, backbone-specific copies (`binary_efficientnet_best.pth`,
`binary_insectnet_best.pth`) are also saved for comparison.

**Key config (Cell 2):**

| Variable | Default | Description |
|----------|---------|-------------|
| `BINARY_BACKBONE` | `'both'` | Which backbone to use for binary: `'efficientnet'` \| `'insectnet'` \| `'both'` |
| `EPOCHS_BINARY` | `20` | Epochs for binary classifier |
| `EPOCHS_S1` | `20` | Epochs for group classifier Stage 1 (web + field combined) |
| `EPOCHS_S2` | `0` | Epochs for group classifier Stage 2 fine-tune on field only (0 = skip) |
| `LR_S1` | `1e-3` | Learning rate for Stage 1 |
| `LR_S2` | `1e-4` | Learning rate for Stage 2 |
| `BG_RATIO` | `3` | Background : insect sampling ratio. Background sampling is balanced across camera plots — each plot contributes an equal quota. Camera-overflow folders (`_101_WSCT`, `_102_WSCT`, …) are the same physical camera hitting the 9 999-image folder limit and are automatically merged into one plot key. |
| `USE_WEB_FOR_BINARY` | `True` | Add iNaturalist web images as extra insect data for binary |
| `WEB_DIR` | `data/web_images/` | Folder produced by `download_web_images.py` |

---

### train_5class.ipynb

Trains a single 5-class classifier (bumblebee / fly / butterfly / other / background) instead
of the two-stage approach. Useful for comparing single-model vs two-stage accuracy.

**Standalone only** — this classifier is not used by the backend package or
`colab/colab_master_pipeline.ipynb`. Best weights go to `models/5group_efficientnet.pth`
or `models/5group_insectnet.pth` depending on the chosen backbone.

**Key config (Cell 2):**

| Variable | Default | Description |
|----------|---------|-------------|
| `TRAIN_MODEL` | `'both'` | Which backbone: `'efficientnet'` \| `'insectnet'` \| `'both'` |
| `EPOCHS_S1` | `20` | Stage 1 epochs (web + field combined) |
| `EPOCHS_S2` | `0` | Stage 2 fine-tune on field only (0 = skip) |
| `LR_S1` / `LR_S2` | `1e-3` / `1e-4` | Learning rates for each stage |
| `BG_RATIO` | `3` | Background : insect sampling ratio. Background sampling is balanced across camera plots — each plot contributes an equal quota. Camera-overflow folders (`_101_WSCT`, `_102_WSCT`, …) are the same physical camera hitting the 9 999-image folder limit and are automatically merged into one plot key. |
| `WEB_DIR` | `None` | Set to `BASE_DIR / 'data' / 'web_images'` to use web images |

---

### train_yolo.ipynb

Fine-tunes a YOLO detector from a pretrained checkpoint. Runs two training stages to
avoid destroying pretrained features.

**Training procedure:**

| Stage | Frozen layers | LR | Patience | Purpose |
|-------|-------------|-----|---------|---------|
| Stage 1 | First 10 backbone layers | `1e-3` | 15 epochs | Warm up the new head |
| Stage 2 | None (full unfreeze) | `5e-4` | 20 epochs | Fine-tune everything |

**Optimizer:** AdamW, set explicitly (`optimizer='AdamW'`). Do not change to `'auto'` —
Ultralytics `'auto'` silently overrides the learning rate.

**Tiling:** Training images are sliced into 640 × 640 px tiles with 20 % overlap before
training (`USE_TILES = True`). This is important for small-insect detection — without tiling,
small insects at full-frame resolution are too small for the detector to learn from.

**Key config (Cell 2):**

| Variable | Default | Description |
|----------|---------|-------------|
| `YOLO_ZIP` | `BASE_DIR / 'yolo.zip'` | Path to CVAT YOLO 1.1 export zip — place the file at the project root or set any path |
| `MODEL_SIZE` | `'yolo26n.pt'` | Pretrained checkpoint to start from (Ultralytics 2026 nano) |
| `KEEP_CLASSES` | all | List of class names to train on; others are dropped |
| `TILE_SIZE` | `640` | Tile size in pixels |
| `TILE_OVERLAP` | `0.2` | Overlap fraction between adjacent tiles |
| `SMOKE_TEST` | `False` | If True, train for 2 epochs only (quick sanity check) |
| `MERGE_TEST_INTO_TRAIN` | `False` | Merge test split into training data before final run |

Best weights are copied to `models/yolo_best.pt` on completion.

---

### prepare_retrain.ipynb

> **Crop-based pipeline only.** Does not apply to the YOLO pipeline.

Reads `results.csv` from a completed inference run and copies crops into a review folder
sorted by predicted class, ready for human labeling and correction.

> ⚠️ **The model is not yet reliable.** Do not trust its confidence scores or class predictions at this stage.
> Set `FORCE_ALL = True` to copy every detected crop regardless of confidence.
> Only crops that are manually moved into `annotated_crops/` will enter retraining —
> nothing is labeled or accepted automatically.
> Once the model has been retrained on a fully human-labeled dataset and its confidence
> scores are well-calibrated, you can switch to confidence-based filtering for faster
> incremental improvement rounds.

**Key config (Cell 2):**

| Variable | Default | Description |
|----------|---------|-------------|
| `INFER_RESULTS` | `CROP_RESULTS_ROOT` | Path to an inference run folder (or the whole `crop_results/` root to scan all runs) |
| `CONF_THRESHOLD_LOW` | `0.70` | Crops with confidence **below** this are flagged as uncertain and queued for review |
| `CONF_THRESHOLD_HIGH` | `0.95` | Crops with confidence **above** this are skipped — assumed correct, not reviewed |
| `INCLUDE_BACKGROUND` | `True` | Include background crops (useful as hard negatives) |
| `INCLUDE_CLASSES` | all 5 | List of class names to include in the review set |
| `FORCE_ALL` | `False` | Ignore confidence thresholds and queue every crop (equivalent to full manual labeling) |
| `MAX_PER_CLASS` | `200` | Cap crops per class to keep the review session manageable (`None` = no limit) |

Output goes to `outputs/training/retrain_review/{class}/`.
Hand this to `tools/labeling/crop_labeler.py` for labeling,
then move confirmed crops to `data/training/annotated_crops/`.

**Note on high-confidence crops:** crops above `CONF_THRESHOLD_HIGH` are excluded from
the review set — they enter retraining with their predicted label unchanged.
To lower the bar for what gets reviewed, reduce `CONF_THRESHOLD_HIGH`;
to review everything regardless of confidence, set `FORCE_ALL = True`.

---

### retrain_cropbased.ipynb

> **Crop-based pipeline only.** Does not apply to the YOLO pipeline.

Fine-tunes the existing binary, 5-class, and 4-class InsectNet classifiers with newly labeled crops, rather
than training from scratch. Faster and requires fewer new samples than a full retrain.

**What it does:** loads the current `models/binary_best.pth`, `models/5group_efficientnet.pth`, and `models/4group_insectnet.pth`,
optionally freezes the backbone, and continues training on the updated `annotated_crops/` dataset.

**Key config (Cell 2):**

| Variable | Default | Description |
|----------|---------|-------------|
| `RETRAIN_BINARY` | `True` | Whether to fine-tune the binary classifier |
| `RETRAIN_5CLASS` | `True` | Whether to fine-tune the 5-class EfficientNet classifier |
| `RETRAIN_4CLASS` | `True` | Whether to fine-tune the 4-class InsectNet group classifier |
| `EPOCHS_BINARY` | `12` | Fine-tune epochs for binary |
| `EPOCHS_5CLASS` | `12` | Fine-tune epochs for 5-class EfficientNet |
| `EPOCHS_4CLASS` | `12` | Fine-tune epochs for 4-class InsectNet |
| `LR_FINETUNE` | `1e-4` | Lower LR than scratch training to avoid overwriting learned features |
| `FREEZE_BACKBONE` | `False` | `True` = update head only (safer for small datasets); `False` = full network |
| `USE_WEB_FOR_BINARY` | `True` | Add web images as extra insect data for binary |
| `BG_RATIO` | `3` | Background : insect sampling ratio. Background sampling is balanced across camera plots — each plot contributes an equal quota. Camera-overflow folders (`_101_WSCT`, `_102_WSCT`, …) are the same physical camera hitting the 9 999-image folder limit and are automatically merged into one plot key. |

Best weights overwrite `models/binary_best.pth`, `models/5group_efficientnet.pth`, and `models/4group_insectnet.pth` on completion (for whichever models were enabled).
The old weights are backed up to `{model}_prev.pth` before overwriting.

---

## evaluation/

### evaluate.ipynb

Scores one or both pipeline outputs against the CVAT ground truth in
`data/evaluation/annotations/`.

**Key config (Cell 2):**

| Variable | Type | Description |
|----------|------|-------------|
| `CROP_RUNS` | `dict` | `{label: path}` mapping of crop-based runs to evaluate; omit or leave empty to skip |
| `YOLO_RUNS` | `dict` | `{label: path}` mapping of YOLO runs to evaluate; omit or leave empty to skip |
| `GT_CLASSES` | `list` | Class names for crop-based ground truth matching (order must match CVAT export) |
| `CLASSES_NO_BB` | `list` | Class names for YOLO ground truth matching (excludes bumblebee — YOLO not trained on it) |
| `STRIP_HEIGHT` | `120` | Pixels to exclude from frame bottom when matching detections to annotations |
| `CONF_THRESHOLDS` | `dict` | Per-pipeline confidence threshold applied at eval time only — predictions below this are treated as background. `0` = off. The CSV is never modified; re-run evaluate.ipynb with a different value to test a new threshold instantly. |

**Choosing a threshold for five_class pipelines** — these pipelines output high false-positive counts at zero threshold because any argmax ≠ background counts as a detection, even at low confidence. Based on run_01 vs CVAT ground truth (`five_class_ins`):

| `CONF_THRESHOLDS` value | FP removed | TP kept | Precision |
|------------------------|------------|---------|-----------|
| `0` (off) | 0% | 100% | 0.062 |
| `0.30` | 71% | 78% | 0.151 |
| `0.40` | 96% | 55% | 0.454 |
| `0.45` | 98% | 52% | 0.595 |
| `0.50` | 98% | 47% | 0.669 |

Cell 10 (`threshold_analysis.png`) plots the full precision-recall curve so you can pick any target recall and read off the threshold.

Example:
```python
CROP_RUNS = {
    'run_lm_on':  CROP_RESULTS_ROOT / 'run_20260522_143000',
    'run_lm_off': CROP_RESULTS_ROOT / 'run_20260522_151200',
}
YOLO_RUNS = {
    'yolo': YOLO_RESULTS_ROOT / 'run_20260522_160000',
}
```
Run names are auto-generated timestamps (e.g. `run_20260522_143000`). Use the key (left side) as a short label in the output plots.

**Outputs** go to `outputs/evaluation/{run_name}_{timestamp}/`:

| File | Contents |
|------|----------|
| `summary.csv` | Per-class and overall precision, recall, F1, AP |
| `confusion_matrix.png` | Confusion matrix heatmap |
| `pr_curve.png` | Precision–recall curves per class |
| `report.html` | Full report with sample images and all metrics |

Run after every inference run before promoting new model weights to `models/` to confirm
accuracy improved. Compare `summary.csv` across runs to track model progress over time.
