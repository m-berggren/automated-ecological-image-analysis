# outputs/

All generated outputs from running the ML pipelines. **Not tracked in git** — add `outputs/` to `.gitignore`.

```
outputs/
├── inference/
│   ├── crop_results/
│   │   └── {run_name}/
│   │       ├── results.csv
│   │       ├── {camera_name}/
│   │       │   ├── crops/
│   │       │   │   ├── bumblebee/
│   │       │   │   ├── fly/
│   │       │   │   ├── butterfly/
│   │       │   │   ├── other/
│   │       │   │   └── background/
│   │       │   └── results.csv          ← one row per crop for this camera
│   │       └── ...
│   └── yolo_results/
│       └── {run_name}_{timestamp}/
│           ├── yolo_results.csv
│           ├── yolo_crops/             ← cropped detection patches
│           └── annotated/              ← frames with bounding boxes drawn
│               └── {camera_name}/
├── training/
│   ├── model_runs/
│   │   └── {name}_{timestamp}/
│   │       ├── weights/
│   │       │   ├── best.pt             ← best checkpoint (lowest val loss)
│   │       │   └── last.pt             ← final epoch checkpoint
│   │       ├── results.csv             ← per-epoch metrics
│   │       ├── confusion_matrix.png
│   │       └── args.yaml               ← full training config snapshot
│   └── retrain_review/
│       ├── bumblebee/
│       ├── fly/
│       ├── butterfly/
│       ├── other/
│       └── background/
└── evaluation/
    ├── {run_name}_{timestamp}/          ← from evaluate.ipynb
    │   ├── summary.csv
    │   ├── confusion_matrix.png
    │   ├── pr_curve.png
    │   └── report.html
    ├── yolo_sensitivity_{timestamp}/    ← from yolo_sensitivity_analysis.ipynb
    │   ├── yolo_robustness.png
    │   ├── yolo_ece.png
    │   ├── yolo_occlusion.png
    │   └── yolo_eigencam.png
    └── crop_sensitivity_{timestamp}/    ← from crop_classifier_sensitivity_analysis.ipynb
        ├── gradcam_all_classes.png
        ├── robustness_all_classes.png
        └── ece_all_classes.png
```

---

## inference/crop_results/

Written by `experiments/inference/infer_cropbased.ipynb`.

One folder per run. The `{run_name}` comes from the `RUN_NAME` variable in Cell 3 of the notebook. **The notebook aborts at startup if a folder with that name already exists** (checks both local and Drive) — choose a new name before re-running.

### results.csv

One row per detected crop across all cameras in the run. Multiple classifiers can run on
the same crops in a single pass — each pipeline adds its own prefixed columns.

**Base columns (always present):**

| Column | Description |
|--------|-------------|
| `camera_folder` | Camera folder name |
| `image_name` | Source image filename |
| `datetime` | EXIF datetime string from the image |
| `camera_name` | Camera model from EXIF |
| `shutter_speed` | Shutter speed from EXIF |
| `weather` | Weather tag (if available) |
| `skip` | `True` if the frame was skipped before motion detection |
| `skip_reason` | `flash` or `foggy` (only set when `skip=True`) |
| `laplacian_var` | Laplacian variance of the frame (sharpness proxy) |
| `pollinator_detected` | `yes` / `no` — whether any active pipeline classified the crop as insect |
| `crop_filename` | Filename of the saved crop image |
| `bbox_x, bbox_y, bbox_w, bbox_h` | Bounding box: top-left x/y plus width and height (pixels) |
| `candidate_type` | How the candidate was detected (`motion`, `large_motion`, `large_motion_context`, etc.) |
| `static_suspect` | `True` if the region was flagged as likely static background |
| `detection_scope` | Whether detection fell inside ROI (`roi`) or outside (`full_frame`) |
| `near_marked_flower` | `True` if the bounding box overlaps a marked flower region |

**Per-pipeline columns** (one set per pipeline listed in `PIPELINES`; prefix = pipeline name):

| Column | Description |
|--------|-------------|
| `{pipe}__binary_label` | `insect` or `background` (Stage 1 output) |
| `{pipe}__binary_conf` | Binary classifier confidence [0, 1] |
| `{pipe}__pollinator_type` | `bumblebee` / `fly` / `butterfly` / `other` / `background` (final class prediction) |
| `{pipe}__group_conf` | Group classifier confidence [0, 1] |
| `{pipe}__bumblebee_prob` | Per-class probability for bumblebee [0, 1] |
| `{pipe}__fly_prob` | Per-class probability for fly [0, 1] |
| `{pipe}__butterfly_prob` | Per-class probability for butterfly [0, 1] |
| `{pipe}__other_prob` | Per-class probability for other insect [0, 1] |
| `{pipe}__background_prob` | Per-class probability for background [0, 1] |

Default pipeline names: `two_stage`, `five_class_eff`, `five_class_ins` (whichever are
enabled in Cell 3 of `infer_cropbased.ipynb`).

### crops/

Crop images organised into class sub-folders by `infer_cropbased.ipynb` Cell 8. Each crop
filename encodes the source frame and bounding box so it can be traced back to the original.
These are the direct input to `tools/labeling/relabel.py` for building training data.

---

## inference/yolo_results/

Written by `experiments/inference/infer_yolo.ipynb`.

### yolo_results.csv

One row per bounding box detection:

| Column | Description |
|--------|-------------|
| `camera_folder` | Camera folder name |
| `image_name` | Source image filename |
| `crop_filename` | Saved crop filename (empty if `save_crops = False`) |
| `bbox_x, bbox_y, bbox_w, bbox_h` | Bounding box: top-left x/y plus width and height (pixels) |
| `class_name` | Predicted class name (`fly`, `butterfly`, or `other`) |
| `confidence` | YOLO confidence score [0, 1] |
| `method` | Detection method: `sahi` (tiled) or `direct` |

### yolo_crops/

Cropped detection patches saved by the inference loop. Each filename encodes camera, image stem,
detection index, and class so it can be traced back to the source frame.

### annotated/

Copies of source frames with bounding boxes and class labels drawn on. Useful for a quick visual sanity check.

---

## training/model_runs/

Written by `train_yolo.ipynb`, `train_binary_group.ipynb`, `train_5class.ipynb`, and
`retrain_cropbased.ipynb`. One timestamped folder per training run.

For YOLO runs the folder mirrors the standard Ultralytics output structure:
- `weights/best.pt` — checkpoint with the lowest validation loss; this is what gets
  copied to `models/yolo_best.pt` on completion
- `weights/last.pt` — final epoch checkpoint, useful for resuming training
- `results.csv` — epoch-by-epoch: `train/box_loss`, `val/box_loss`, `metrics/mAP50`, etc.
- `args.yaml` — full snapshot of every training hyperparameter used in that run

For classifier runs, the structure is similar but uses `.pth` weights files and a
`config.json` (training hyperparameters) instead of Ultralytics CSV format.

**Deploying a new model:** copy the best checkpoint to `models/` manually after verifying
accuracy with `evaluate.ipynb`:
```bash
cp outputs/training/model_runs/{run}/weights/best.pt models/yolo_best.pt
```
The training notebooks do this automatically on completion, but re-copying manually lets
you choose between multiple runs.

---

## training/retrain_review/

Written by `experiments/training/prepare_retrain.ipynb`.

Low-confidence crops selected from a completed inference run, ready for human labeling.
Organised into class sub-folders by the notebook's predicted class — the predicted label
is a starting point; the labeler corrects mistakes.

Hand this folder to `tools/labeling/crop_labeler.py` or `tools/labeling/relabel.py`,
then move confirmed crops into `data/training/annotated_crops/` before running
`retrain_cropbased.ipynb`.

---

## evaluation/

Written by `experiments/evaluation/evaluate.ipynb`.

One timestamped folder per evaluation run.

| File | Contents |
|------|----------|
| `summary.csv` | Per-class and overall precision, recall, F1, AP@0.5 |
| `confusion_matrix.png` | Normalised confusion matrix heatmap |
| `pr_curve.png` | Precision–recall curves, one line per class |
| `report.html` | Full report: all metrics, sample TP/FP/FN images, run config |

Compare `summary.csv` across evaluation runs to track whether retraining improved accuracy
before promoting new weights to `models/`. The `report.html` is the easiest way to visually
inspect what the model is getting wrong.

---

## evaluation/yolo_sensitivity_{timestamp}/

Written by `experiments/evaluation/yolo_sensitivity_analysis.ipynb`.

| File | Contents |
|------|----------|
| `yolo_robustness.png` | Recall vs. image degradation (blur, brightness, contrast) |
| `yolo_ece.png` | Expected calibration error curve |
| `yolo_occlusion.png` | Occlusion sensitivity heatmap (bottom strip excluded) |
| `yolo_eigencam.png` | EigenCAM activation saliency overlays |

---

## evaluation/crop_sensitivity_{timestamp}/

Written by `experiments/evaluation/crop_classifier_sensitivity_analysis.ipynb`.

| File | Contents |
|------|----------|
| `gradcam_all_classes.png` | GradCAM saliency maps per class |
| `robustness_all_classes.png` | Classifier accuracy vs. image degradation |
| `ece_all_classes.png` | Calibration curves per class |
