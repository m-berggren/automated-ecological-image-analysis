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
    └── evaluate.ipynb              ← compare outputs against ground truth
```

## Quick reference

| Notebook | Reads from | Writes to |
|----------|-----------|-----------|
| `inference/infer_cropbased.ipynb` | `data/evaluation/e2e_evaluation_images/` | `outputs/inference/crop_results/` |
| `inference/infer_yolo.ipynb` | `data/evaluation/e2e_evaluation_images/` | `outputs/inference/yolo_results/` |
| `evaluation/evaluate.ipynb` | `outputs/inference/*/` + `data/evaluation/e2e_yolo_annotations/` | `outputs/evaluation/` |
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
    BASE_DIR = Path('/content/drive/MyDrive/pollinator-classification')
else:
    BASE_DIR = Path('...')   # absolute path to this repo on disk
```

**Only edit Cell 1** if your Google Drive folder has a different name than
`pollinator-classification`. All other paths are derived from `BASE_DIR` automatically.

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
| `PREPROCESS_CONFIG` | `dict` | Motion detection parameters — override individual keys from `DEFAULT_PREPROCESS_CONFIG`; includes `strip_ocr_temperature` (default `False`) and `strip_height` |
| `PIPELINES` | `dict` | One entry per classifier pipeline to run; each has `enabled`, `type` (`'two_stage'` or `'five_class'`), model paths, and optionally `conf_threshold`. All enabled pipelines run in parallel and each adds its own columns to `results.csv` |

Key optional fields inside each `PIPELINES` entry (five_class only):

| Key | Default | Effect |
|-----|---------|--------|
| `conf_threshold` | `0` (off) | Predictions below this confidence are reclassified as background. `0.40` removes ~96% of false positives while keeping ~55% of true positives (measured on run_01 against CVAT ground truth). Set to `0` to disable. |

Key toggles inside `PREPROCESS_CONFIG`:

| Key | Default | Effect |
|-----|---------|--------|
| `strip_ocr_temperature` | `False` | Extract temperature from camera OSD strip (requires tesseract) |
| `enable_large_motion` | `True` | Detect large fast-moving objects in addition to frame diffs |
| `darker_threshold` | `15` | Sensitivity of motion detection |
| `min_contour_area` | `200` | Minimum pixel area for a detected contour to become a crop |

**Important:** The notebook raises `FileExistsError` at startup if `RUN_NAME` already exists in
`outputs/inference/crop_results/`. Choose a new name or delete the old folder first.

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
| `conf_threshold` | `0.25` | Minimum confidence to keep a detection |
| `nms_iou` | `0.45` | NMS IoU threshold |
| `use_sahi` | `True` | Slice-and-tile detection via SAHI (recommended for full-res images) |
| `sahi_slice` | `640` | Tile size for SAHI inference |
| `sahi_overlap` | `0.2` | Overlap fraction between SAHI tiles |
| `sahi_conf` | `0.20` | Per-tile confidence threshold before NMS |
| `save_crops` | `True` | Save cropped detection patches |
| `strip_height` | `120` | Pixels to crop from frame bottom (camera OSD bar) |

Output goes to `outputs/inference/yolo_results/{RUN_NAME}/`:
- `detections.csv` — per-frame: frame path, bbox (x1 y1 x2 y2), class, confidence
- `crops/{class}/` — cropped detection patches (if `save_crops = True`)

Use `evaluation/evaluate.ipynb` to compare this against the crop-based pipeline.

---

## training/

### train_binary_group.ipynb

Trains the two-stage crop classifier from scratch.

- **Stage 1 — binary classifier:** InsectNet or EfficientNet backbone, 2 classes (insect / background).
  Reads from all class folders in `data/training/annotated_crops/`; background class vs everything else.
- **Stage 2 — group classifier:** InsectNet backbone, 4 classes (bumblebee / fly / butterfly / other).
  Reads from the four insect class folders only (no background).

Both stages write timestamped run folders to `outputs/training/model_runs/` and copy best
weights to `models/binary_best.pth` and `models/4group_insectnet.pth` on completion.

**Key config (Cell 2):** `EPOCHS`, `BATCH_SIZE`, `LR`, `BACKBONE` (`'insectnet'` or `'efficientnet'`),
`AUGMENT` (enable data augmentation), `VAL_SPLIT`.

---

### train_5class.ipynb

Trains a single 5-class classifier (bumblebee / fly / butterfly / other / background) instead
of the two-stage approach. Useful for comparing single-model vs two-stage accuracy.

**Standalone only** — this classifier is not used by the backend package or
`colab/colab_master_pipeline.ipynb`. Best weights go to `models/5group_efficientnet.pth`
or `models/5group_insectnet.pth` depending on the chosen backbone.

**Key config (Cell 2):** same structure as `train_binary_group.ipynb`.

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

Reads `results.csv` from a completed inference run and extracts low-confidence crops
for human review — instead of labeling the entire crop set.

**Key config (Cell 2):**

| Variable | Default | Description |
|----------|---------|-------------|
| `INFER_RESULTS` | `CROP_RESULTS_ROOT` | Path to an inference run folder (or the whole `crop_results/` root to scan all runs) |
| `CONF_THRESHOLD_LOW` | `0.70` | Crops with confidence **below** this are flagged as uncertain and queued for review |
| `CONF_THRESHOLD_HIGH` | `0.95` | Crops with confidence **above** this are skipped as already confident |
| `INCLUDE_BACKGROUND` | `True` | Include background crops (useful as hard negatives) |
| `INCLUDE_CLASSES` | all 5 | List of class names to include in the review set |
| `FORCE_ALL` | `False` | Ignore confidence thresholds and queue every crop |
| `MAX_PER_CLASS` | `200` | Cap crops per class to keep the review session manageable (`None` = no limit) |

Output goes to `outputs/training/retrain_review/{class}/`.
Hand this to `tools/labeling/crop_labeler.py` or `tools/labeling/relabel.py` for labeling,
then move confirmed crops to `data/training/annotated_crops/`.

**When to skip this notebook:** If the inference run produced fewer than ~300 crops total,
go straight to `relabel.py` — the filtering step adds overhead not worth it at small scale.

---

### retrain_cropbased.ipynb

Fine-tunes the existing binary and group classifiers with newly labeled crops, rather
than training from scratch. Faster and requires fewer new samples than a full retrain.

**What it does:** loads the current `models/binary_best.pth` and `models/4group_insectnet.pth`,
freezes early layers, and continues training on the updated `annotated_crops/` dataset.

**Key config (Cell 2):** `EPOCHS`, `LR` (typically `1e-4`, lower than scratch training),
`FREEZE_LAYERS`, `BATCH_SIZE`.

Best weights overwrite `models/binary_best.pth` and `models/4group_insectnet.pth` on completion.
The old weights are backed up to `outputs/training/model_runs/` before overwriting.

---

## evaluation/

### evaluate.ipynb

Scores one or both pipeline outputs against the CVAT ground truth in
`data/evaluation/e2e_yolo_annotations/`.

**Key config (Cell 2):**

| Variable | Type | Description |
|----------|------|-------------|
| `CROP_RUNS` | `dict` | `{label: path}` mapping of crop-based runs to evaluate; omit or leave empty to skip |
| `YOLO_RUNS` | `dict` | `{label: path}` mapping of YOLO runs to evaluate; omit or leave empty to skip |
| `GT_CLASSES` | `list` | Class names for crop-based ground truth matching (order must match CVAT export) |
| `YOLO_GT_CLASSES` | `list` | Class names for YOLO ground truth matching |
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
    'run_01': CROP_RESULTS_ROOT / 'run_01_lm_on',
    'run_02': CROP_RESULTS_ROOT / 'run_02_lm_off',
}
YOLO_RUNS = {
    'yolo_run_01': YOLO_RESULTS_ROOT / 'yolo_run_01',
}
```

**Outputs** go to `outputs/evaluation/{run_name}_{timestamp}/`:

| File | Contents |
|------|----------|
| `summary.csv` | Per-class and overall precision, recall, F1, AP |
| `confusion_matrix.png` | Confusion matrix heatmap |
| `pr_curve.png` | Precision–recall curves per class |
| `report.html` | Full report with sample images and all metrics |

Run after every inference run before promoting new model weights to `models/` to confirm
accuracy improved. Compare `summary.csv` across runs to track model progress over time.
