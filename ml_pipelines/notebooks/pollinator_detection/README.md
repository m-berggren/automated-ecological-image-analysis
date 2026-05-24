# Pollinator Classification ML Pipeline

This folder contains two complementary ML pipelines for detecting and classifying
pollinators in Arctic camera trap images. See [PIPELINE.md](PIPELINE.md) for the
full technical documentation.

---

## The two pipelines

**Crop-based pipeline** — classical motion detection extracts candidate crops from each
frame, then one or more CNN classifiers decide what (if anything) is in each crop.
Highly configurable at inference time; the preferred path for retraining.

**YOLO pipeline** — a full-image object detector trained end-to-end on CVAT annotations.
Better at finding insects that motion detection misses; comparisons with the crop pipeline
run through `experiments/evaluation/evaluate.ipynb`.

Neither pipeline is "primary" — they are designed to be run in parallel and compared.

---

## Pollinator classes

All classifiers recognise the same four groups:

| Class | Taxon |
|-------|-------|
| **bumblebee** | Bumble bees (*Bombus* spp.) |
| **fly** | Flies (Diptera) |
| **butterfly** | Butterflies and moths (Lepidoptera) |
| **other** | All other insect visitors (beetles, wasps, etc.) |

The crop-based classifiers also include a **background** class for regions with no insect.

---

## Repository layout

```
pollinator-classification/
│
├── experiments/                    ← standalone notebooks (run locally or in Colab)
│   ├── README.md                   ← per-notebook config reference
│   ├── inference/
│   │   ├── infer_cropbased.ipynb   ← preprocess images + (optionally) run classifiers
│   │   └── infer_yolo.ipynb        ← run YOLO detector
│   ├── training/
│   │   ├── train_binary_group.ipynb  ← train binary + group classifiers
│   │   ├── train_5class.ipynb        ← train single 5-class classifier
│   │   ├── train_yolo.ipynb          ← train YOLO detector (standalone, Colab/local)
│   │   ├── prepare_retrain.ipynb     ← select uncertain crops for human review
│   │   └── retrain_cropbased.ipynb   ← fine-tune classifiers with new labeled crops
│   └── evaluation/
│       └── evaluate.ipynb          ← compare pipelines against ground truth
│
├── colab/                          ← master pipeline notebooks (call pollinator package)
│   ├── README.md                   ← explains standalone vs package-linked distinction
│   └── colab_master_pipeline.ipynb ← orchestrates retrain via ml-pipelines backend
│
├── tools/                          ← labeling, triage, and data-prep scripts
│   ├── README.md                   ← usage guide for every script
│   ├── triage/                     ← frame selection before labeling
│   │   ├── frame_flag_mac.py       ← (macOS) browse camera folders and flag frames
│   │   ├── feh-triage.sh           ← (Linux) frame triage using feh
│   │   └── _feh-action.sh          ← feh key-binding helper
│   ├── labeling/                   ← crop annotation tools
│   │   ├── crop_labeler.py         ← label extracted crops interactively
│   │   └── relabel.py              ← correct existing labels
│   └── data_prep/                  ← dataset preparation utilities
│       ├── download_web_images.py  ← download iNaturalist reference images
│       └── flatten-jpg.sh          ← flatten nested JPG folder structures
│
├── models/                         ← model weights (current inference models)
│   ├── README.md                   ← model descriptions and update workflow
│   ├── binary_best.pth             ← binary classifier (insect vs background)
│   ├── 4group_insectnet.pth        ← 4-class group classifier (InsectNet)
│   ├── 5group_efficientnet.pth     ← 5-class classifier (EfficientNet)
│   ├── 5group_insectnet.pth        ← 5-class classifier (InsectNet)
│   └── yolo_best.pt                ← YOLO detector
│
├── InsectNet/                      ← third-party backbone (CC BY-NC 4.0, see NOTICE)
│   ├── README.md                   ← what it is, download link, when it's needed
│   ├── evaluate.py                 ← adapter code (one line changed from upstream)
│   └── model.pth                   ← pre-trained weights (gitignored — download from Zenodo)
│
├── data/                           ← input image data (not in git)
│   ├── README.md                   ← data layout, class structure, how to add training data
│   ├── training/                   ← data used for model training
│   │   └── annotated_crops/        ← manually labeled crops ({class}/ sub-folders)
│   └── evaluation/                 ← data used for pipeline evaluation
│       ├── images/  ← camera folders for inference (evaluation and general runs)
│       └── annotations/   ← CVAT YOLO 1.1 ground truth
│
├── outputs/                        ← generated outputs (not in git)
│   ├── README.md                   ← output folder structure, CSV column reference
│   ├── inference/                  ← results from running the pipelines
│   │   ├── crop_results/           ← crop-based inference runs
│   │   └── yolo_results/           ← YOLO inference runs
│   ├── training/                   ← artifacts from training runs
│   │   ├── model_runs/             ← timestamped YOLO training checkpoints
│   │   └── retrain_review/         ← crops flagged for human review
│   └── evaluation/                 ← evaluation reports and metrics
│
├── archive/                        ← old notebooks, kept for reference
├── PIPELINE.md                     ← full technical documentation
└── README.md                       ← this file
```

---

## Common tasks

**Run inference on camera images**
→ Put images in `data/evaluation/images/{camera_name}/` — works for any camera images, not just evaluation datasets
→ Open `experiments/inference/infer_cropbased.ipynb`, run all cells — `RUN_NAME` auto-generates a timestamp
→ To add a descriptive label, uncomment Option B in Cell 3 and edit the suffix

**Read temperatures from camera strip (optional)**
→ Set `strip_ocr_temperature: True` in Cell 3 of `infer_cropbased.ipynb`
→ Requires tesseract: `!apt-get install -y tesseract-ocr && !pip install pytesseract` (Colab)
→ Adds a `temperature_c` column to `results.csv`; adds ~0.3 s/frame overhead
→ See §6 of [PIPELINE.md](PIPELINE.md) for full details

**Evaluate accuracy against ground truth**
→ Open `experiments/evaluation/evaluate.ipynb`, point to a completed run, run all cells

**Label new crops for retraining**
→ `tools/labeling/crop_labeler.py` — primary labeling tool; shows source frame context, labels all crops
→ `experiments/training/prepare_retrain.ipynb` — future use once model is trustworthy; pre-filters to low-confidence crops only before labeling

**Retrain classifiers with new data**
→ Merge labeled crops into `data/training/annotated_crops/` → `experiments/training/retrain_cropbased.ipynb`

**Train from scratch**
→ `experiments/training/train_binary_group.ipynb` (two-stage) or `experiments/training/train_5class.ipynb` (single model)
→ `experiments/training/train_yolo.ipynb` for the YOLO detector

**Add more training images from the web**
→ `tools/data_prep/download_web_images.py` downloads from iNaturalist into `web_images/`

See [PIPELINE.md](PIPELINE.md) for the full data flow, annotation workflow, Colab setup,
and how initial training differs from incremental retraining.

---

## Quick path reference

| What | Where |
|------|-------|
| Labeled training crops | `data/training/annotated_crops/{class}/` |
| YOLO annotations (CVAT export) | `data/evaluation/annotations/` |
| Inference results | `outputs/inference/crop_results/{run_name}/` |
| Trained model weights (current) | `models/*.pth` / `models/*.pt` |
| Training run outputs (historical) | `outputs/training/model_runs/{name}_{timestamp}/` |
| Helper script docs | `tools/README.md` |
