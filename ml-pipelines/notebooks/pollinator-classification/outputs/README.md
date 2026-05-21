# outputs/

All generated outputs from running the ML pipelines. **Not tracked in git** — add `outputs/` to `.gitignore`.

```
outputs/
├── inference/
│   ├── crop_results/
│   │   └── {run_name}_{timestamp}/
│   │       ├── results.csv
│   │       ├── {camera_name}/
│   │       │   ├── crops/
│   │       │   │   ├── bumblebee/
│   │       │   │   ├── fly/
│   │       │   │   ├── butterfly/
│   │       │   │   ├── other/
│   │       │   │   └── background/
│   │       │   └── frames/              ← original frames (symlinks or copies)
│   │       └── ...
│   └── yolo_results/
│       └── {run_name}_{timestamp}/
│           ├── detections.csv
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
│       └── {run_name}_{timestamp}/
│           ├── bumblebee/
│           ├── fly/
│           ├── butterfly/
│           ├── other/
│           └── background/
└── evaluation/
    └── {run_name}_{timestamp}/
        ├── summary.csv
        ├── confusion_matrix.png
        ├── pr_curve.png
        └── report.html
```

---

## inference/crop_results/

Written by `experiments/inference/infer_cropbased.ipynb`.

One timestamped folder per run. The `{run_name}` comes from the `RUN_NAME` variable in Cell 2 of the notebook. **The notebook aborts at startup if a folder with that name already exists** — choose a new name or delete the old folder first.

### results.csv

One row per detected crop across all cameras in the run:

| Column | Description |
|--------|-------------|
| `frame_path` | Absolute path to the source frame |
| `camera` | Camera folder name |
| `x1, y1, x2, y2` | Bounding box in pixels (top-left, bottom-right) |
| `binary_class` | `insect` or `background` (Stage 1 output) |
| `binary_conf` | Binary classifier confidence [0, 1] |
| `group_class` | `bumblebee` / `fly` / `butterfly` / `other` (Stage 2 output; empty if binary = background) |
| `group_conf` | Group classifier confidence [0, 1] |
| `temperature_c` | Temperature extracted from frame strip (only if OCR enabled) |

### crops/

Crop images organised into class sub-folders by `infer_cropbased.ipynb` Cell 8. Each crop
filename encodes the source frame and bounding box so it can be traced back to the original.
These are the direct input to `tools/labeling/relabel.py` for building training data.

---

## inference/yolo_results/

Written by `experiments/inference/infer_yolo.ipynb`.

### detections.csv

One row per bounding box detection:

| Column | Description |
|--------|-------------|
| `frame_path` | Absolute path to the source frame |
| `camera` | Camera folder name |
| `x1, y1, x2, y2` | Bounding box in pixels |
| `class` | Predicted class name |
| `confidence` | YOLO confidence score [0, 1] |

### annotated/

Copies of source frames with bounding boxes and class labels drawn on. Only written if
`SAVE_ANNOTATED = True` in Cell 2 (default). Useful for a quick visual sanity check.

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
`metrics.json` instead of Ultralytics CSV format.

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
