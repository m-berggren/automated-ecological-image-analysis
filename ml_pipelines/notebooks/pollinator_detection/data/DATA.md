# data/

Input image data used by the ML pipelines. **Not tracked in git** — add `data/` to `.gitignore`.

```
data/
├── training/
│   ├── annotated_crops/        ← manually labeled crops, two-level layout: {dataset_name}/{class}/
│   │   ├── labeled_ls/         ← first labeled dataset
│   │   │   ├── bumblebee/
│   │   │   ├── fly/
│   │   │   ├── butterfly/
│   │   │   ├── other/
│   │   │   └── background/
│   │   ├── labeled_mb/         ← second labeled dataset (same class structure)
│   │   │   └── ...
│   │   └── labeled_set/        ← third dataset (mostly background + some fly/other)
│   │       └── ...
│   └── web_images/             ← iNaturalist downloads, one sub-folder per download batch
│       └── batch_YYYYMMDD_HHMMSS/   ← created by download_web_images.py
│           ├── bumblebee/
│           ├── fly/
│           ├── butterfly/
│           └── other/
└── evaluation/
    ├── images/  ← camera trap images for end-to-end evaluation
    │   └── {camera_name}/
    │       ├── frame_001.jpg
    │       └── ...
    └── annotations/   ← CVAT YOLO 1.1 ground truth
        ├── obj_Train_data/
        │   └── {frame_name}.txt    ← one line per bounding box: class cx cy w h
        ├── train.txt
        └── obj.data
```

---

## training/annotated_crops/

Manually labeled insect crops used to train and fine-tune the classifiers. Organised in a
two-level hierarchy: `annotated_crops/{dataset_name}/{class}/`. Each file is a JPG crop
extracted from a camera trap frame. The training notebooks combine all dataset sub-folders
automatically — to include a dataset, simply place it here with the expected class structure.

**Current datasets:**

| Dataset folder | Description |
|----------------|-------------|
| `labeled_ls/` | First labeled dataset |
| `labeled_mb/` | Second labeled dataset |
| `labeled_set/` | Third dataset — predominantly background crops (2 052), with some fly (76) and other (45); bumblebee and butterfly are absent or near-absent. Useful as hard negatives for the binary classifier. |

**Classes (same structure within each dataset):**

| Sub-folder | What it contains |
|------------|-----------------|
| `bumblebee/` | Bumble bee crops (*Bombus* spp.) |
| `fly/` | Fly crops (Diptera) |
| `butterfly/` | Butterfly and moth crops (Lepidoptera) |
| `other/` | Other insects (beetles, wasps, hoverflies, etc.) |
| `background/` | Crops with no insect — false positives from motion detection |

**Note:** the `unsure/` sub-folder (present in some datasets) is intentionally ignored by
all training notebooks — only the five class folders above are loaded.

These are the inputs for every classifier training notebook:
- `experiments/training/train_binary_group.ipynb` — two-stage binary + group classifier
- `experiments/training/train_5class.ipynb` — single 5-class classifier
- `experiments/training/retrain_cropbased.ipynb` — fine-tuning with new labeled data

### Adding new training data

The normal workflow for adding data from a new inference run:

```
experiments/inference/infer_cropbased.ipynb  (MODE = 'preprocess' or 'infer')
      ↓  Cell 8 — organise crops by predicted class
      ↓
[optional] experiments/training/prepare_retrain.ipynb
           filters to low-confidence crops only → outputs/training/retrain_review/
      ↓
tools/labeling/crop_labeler.py  or  tools/labeling/relabel.py
      ↓  confirmed crops moved to data/training/annotated_crops/{dataset_name}/{class}/
      ↓
experiments/training/retrain_cropbased.ipynb
```

You can also add web-downloaded images with `tools/data_prep/download_web_images.py` —
these land in a new timestamped folder `data/training/web_images/batch_YYYYMMDD_HHMMSS/{class}/`
and are used for both classifiers: directly for the group classifier, and as extra `insect`
data for the binary classifier when `USE_WEB_FOR_BINARY = True` (default). Control which
batches are included via `WEB_BATCHES` in the training notebooks (`[]` = all batches).

Do not mix unlabeled or `unsure/` crops into the class folders — both training notebooks
skip any sub-folder not in the expected class list.

---

## evaluation/images/

Raw camera trap image sequences, one sub-folder per camera location. These are the inputs
to `experiments/inference/infer_cropbased.ipynb` and `experiments/inference/infer_yolo.ipynb`.

Each camera sub-folder should contain JPG frames in chronological order. The crop-based
pipeline diffs consecutive frames to detect motion, so **frame order matters** — do not
shuffle or rename files in a way that breaks alphabetical sort order.

To add a new evaluation set, create a new sub-folder here named after the camera location
and place the frames in it. Set `RUN_NAME` in Cell 2 of the inference notebook before running.

---

## evaluation/annotations/

Ground-truth bounding box annotations exported from CVAT in **YOLO 1.1 format**. Used by
`experiments/evaluation/evaluate.ipynb` to score pipeline outputs.

**Format:** Each `.txt` annotation file has one line per bounding box:
```
class_id  cx  cy  w  h
```
All coordinates are normalised to [0, 1] relative to image dimensions. `class_id` maps to:
`0` = bumblebee, `1` = fly, `2` = butterfly, `3` = other (matches `data.yaml` in the export).

The annotation folder also contains a `train.txt` listing annotated frame paths and an
`obj.data` config file — these are standard CVAT exports and are used as-is by `evaluate.ipynb`.

To add annotations for new frames, export from CVAT as YOLO 1.1 and merge the `obj_Train_data/`
files into this folder. Do not change the `class_id` ordering without also updating `KEEP_CLASSES`
in `train_yolo.ipynb`.
