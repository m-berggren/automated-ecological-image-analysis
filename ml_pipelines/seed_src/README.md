# seed_src

Seed-detection pipeline using per-species YOLO **OBB** (oriented bounding box)
detectors with SAHI-tiled inference. The pipeline is wired into the Django backend
(apps/seeds/) at runtime for UI-driven inference and training, and driven by
[`main.py`](../main.py) for offline research purposes.

See also: [ml_pipelines overview](../README.md) and the
[project architecture](../../README.md#architecture).

## Per-species models

One OBB detector is trained per seed species. Species are discovered
dynamically from the data directory: any folder named `<species>_model` under
`data/seed` (current set: `cat`, `peh`, `phyca`, `vau`). Each species has its
own data YAML and its own weights under `runs/obb/<species>/`.

Expected layout:

```
data/seed/
  <species>_model/
    <species>.yaml         data config for this species
    train/{images,labels}/
    train_sliced/{images, labels}/
    val/{images,labels}/
```

Labels are single-class per species (class ID normalized to 0 during prep).

## Structure

```
seed_src/
  inference/
    inference.py            run_sahi (SAHI sliced prediction, 768px tiles)
    confidence_analyzer.py  analyze_seed_confidence: count confidence, calculate seed count range, high-risk flagging
  training/
    train.py                train_species_model (fresh or fine-tune, YOLO26n-OBB, supports UI callbacks)
    slice_dataset.py        tile images + OBB labels into 768px slices (shapely)
  utils/
    metrics.py              OBB IoU (shapely), TP/FP/FN, precision/recall/F1-score
    label_extractor.py      LabelExtractor: EasyOCR reader for handwritten
                            species label cards
    helpers.py              data routing, model loading, run naming, label prep
    active_seed_calculator.py  polygon area (shoelace) to categorize active vs. aborted seeds based on a reference size
    agreement_calculator.py    inter-annotator agreement over ground truth based on F1-score
main.py                     research orchestrator (settings + run)
```

## Backend Integration
To support the Django backend (apps/seeds/), the core functionalities are encapsulated:

- **Inference**: run_inference() wraps the SAHI-tiled prediction logic (768px tiles with 40% overlap) without assuming local directory structures. It returns raw results for the UI or downstream utilities.

- **Confidence and Quality**: confidence_analyzer.py calculates risk thresholds based on aggregated seed confidence scores. Active_seed_calculator.py filters out aborted seeds by comparing their area to the area of a user-provided reference seed polygon. Aborted seeds are <=30% the size of active seeds.

- **Training**: train_species_model accepts a progress_callback to stream epoch updates (progress and loss metrics) back to the Django UI.

## What `main.py` does
For offline research, [`main.py`](../main.py) orchestrates the entire training and inference workflow:
1. **Prepare labels** (`PREPARE_LABELS`): Normalizes every label file's class ID to 0 per species and split
   to 0 per species/split.
2. **Train or locate models** (`RETRAIN`, `TRAINING_MODE`):
   - `fresh`: Trains from a pretrained existing `yolo26n-obb.pt` model.
   - `finetune`: Continues from a per-species checkpoint in `FINETUNE_WEIGHTS`.
   - When not retraining, finds the latest existing `runs/obb/<species>/weights/best.pt`.
3. **Load** each species' model, dynamically locating all species models from the data directory.
4. **Route data** with OCR: [`label_extractor.py`](utils/label_extractor.py) reads the species from each image's label card and `verify_and_route_data` in [`helpers.py`](utils/helpers.py) sorts images into the right
   `<species>_model` folder.
5. **Inference loop**: For each species' val images, runs SAHI predictions in [`inference.py`](inference/inference.py), exports prediction visuals and per-image prediction JSON files, and scores against ground truth with OBB-IoU TP/FP/FN at threshold 0.3.
6. **Report**: Per-species and overall Mean Absolute Error (MAE), precision, recall, F1-score.

## Training

```python
from seed_src.training.train import train_species_model

train_species_model(
    species_name,
    data_yaml_path,
    epochs=90,                       # Default; 45 used for fine-tune in main.py
    finetune_from=None,              # Path to a checkpoint to continue from
    run_name=None,
    lr0=None,
    lrf=None,
    progress_callback=my_callback    # Used by Django to stream progress to UI
)
```

YOLO26n-OBB, `imgsz=768`, mosaic augmentation disabled, early-stop patience 20.
Returns the path to `best.pt`.

## Running

Paths in [`main.py`](../main.py) and [`slice_dataset.py`](training/slice_dataset.py) are **relative to the `ml_pipelines/` directory** (`../data/seed`, `runs/obb/...`). Run from there:

```bash
cd ml_pipelines
# edit the SETTINGS block at the top of main.py first
python main.py
```

Outputs:

- `runs/obb/<species>/weights/best.pt` (trained models)
- `seed_src/prediction_images/` (visualized predictions)
- `seed_src/predictions/<image>_preds.json` (per-image polygons for seed-size
  analysis)

## Caveats

- While core inference and training functionalities are decoupled for backend use, some utility scripts (like slice_dataset.py and main.py) contain hardcoded relative paths and settings blocks and assume they are being run from the ml_pipelines working directory.

[`label_extractor.py`](utils/label_extractor.py) relies on the `easyocr` library, which requires `PyTorch` and can be heavy to initialize.
