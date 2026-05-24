# seed_src

Seed-detection pipeline using per-species YOLO **OBB** (oriented bounding box)
detectors with SAHI-tiled inference. Unlike [pollinator](../pollinator/), this
is **not wired into the Django backend**: it is a research script driven by
[`main.py`](../main.py) with a settings block at the top.

See also: [ml-pipelines overview](../README.md) and the
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
    val/{images,labels}/
```

Labels are single-class per species (class id normalised to 0 during prep).

## Structure

```
seed_src/
  inference/
    inference.py            run_sahi (SAHI sliced prediction, 768px tiles)
    confidence_analyzer.py  analyze_seed_confidence: count confidence range
                            + high-risk flagging
  training/
    train.py                train_species_model (fresh or fine-tune, YOLO26n-OBB)
    slice_dataset.py        tile images + OBB labels into 768px slices (shapely)
  utils/
    metrics.py              OBB IoU (shapely), TP/FP/FN, precision/recall/F1
    label_extractor.py      LabelExtractor: EasyOCR reader for handwritten
                            species label cards
    helpers.py              data routing, model loading, run naming, label prep
    active_seed_calculator.py  polygon area (shoelace) for seed-size estimates
    agreement_calculator.py    inter-source agreement over ground truth
main.py                     orchestrator (settings + run)
```

## What `main.py` does

1. **Prepare labels** (`PREPARE_LABELS`): normalise every label file's class id
   to 0 per species/split.
2. **Train or locate models** (`RETRAIN`, `TRAINING_MODE`):
   - `fresh`: train from `yolo26n-obb.pt`.
   - `finetune`: continue from a per-species checkpoint in `FINETUNE_WEIGHTS`.
   - When not retraining, find the latest existing `runs/obb/<species>/weights/best.pt`.
3. **Load** each species' model.
4. **Route data** with OCR: `LabelExtractor` reads the species from each image's
   label card and `verify_and_route_data` sorts images into the right
   `<species>_model` folder.
5. **Inference loop**: for each species' val images, run `run_sahi`, export
   prediction visuals and per-image prediction JSON, and score against ground
   truth with OBB-IoU TP/FP/FN at threshold 0.3.
6. **Report**: per-species and overall MAE (count error), precision, recall, F1.

## Training

```python
from seed_src.training.train import train_species_model

train_species_model(
    species_name, data_yaml_path,
    epochs=90,                       # default; 45 used for fine-tune in main.py
    finetune_from=None,              # path to a checkpoint to continue from
    run_name=None, lr0=None, lrf=None,
)
```

YOLO26n-OBB, `imgsz=768`, mosaic augmentation disabled, early-stop patience 20.
Returns the path to `best.pt`.

## Running

Paths in `main.py` and `slice_dataset.py` are **relative to the
`ml-pipelines/` directory** (`../data/seed`, `runs/obb/...`). Run from there:

```bash
cd ml-pipelines
# edit the SETTINGS block at the top of main.py first
python main.py
```

Outputs:

- `runs/obb/<species>/weights/best.pt` (trained models)
- `seed_src/prediction_images/` (visualised predictions)
- `seed_src/predictions/<image>_preds.json` (per-image polygons for seed-size
  analysis)

## Caveats

- This is research-grade script code: hardcoded relative paths, settings blocks
  in multiple files, and a hard cwd assumption. It is not a clean importable
  library like `pollinator/`.
- `label_extractor.py` was converted from a notebook and depends on `easyocr`.
