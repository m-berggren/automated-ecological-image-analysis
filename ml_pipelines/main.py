"""Main file used for local testing/research purposes of the seed module ML pipeline."""

import json
import os
import sys

import django
from PIL import Image

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

django.setup()

from collections import defaultdict

from django.core.files import File
from seed_src.inference.inference import run_sahi
from seed_src.training.train import train_species_model
from seed_src.utils.helpers import (
    get_next_run_name,
    load_ground_truth,
    load_model,
    update_class_labels,
    verify_and_route_data,
)
from seed_src.utils.label_extractor import LabelExtractor
from seed_src.utils.metrics import (
    calculate_precision_recall_f1_score,
    calculate_tp_fp_fn,
)

from apps.analysis.models import Detection, InferenceRun
from apps.datasets.models import ImageAsset

# -------------------------
# SETTINGS
# -------------------------
BASE_PATH = '../data/seed'

PREPARE_LABELS = True  # Set to True to run the label update on newly added label files
RETRAIN = False  # Set to True to train a new model from scratch, False to use existing weights
TRAINING_MODE = 'finetune'  # Set to 'fresh' to train from scratch, set to 'finetune' for incremental training
FINETUNE_WEIGHTS = {  # Per-species checkpoint to fine-tune from, only used if TRAIN_MODE == 'finetune'
    'cat': os.path.abspath(os.path.join('runs', 'obb', 'cat', 'weights', 'best.pt')),
    'peh': os.path.abspath(os.path.join('runs', 'obb', 'peh', 'weights', 'best.pt')),
    'phyca': os.path.abspath(
        os.path.join('runs', 'obb', 'phyca', 'weights', 'best.pt')
    ),
    'vau': os.path.abspath(os.path.join('runs', 'obb', 'vau', 'weights', 'best.pt')),
}
FINETUNE_LR0 = 0.001
FINETUNE_LRF = 0.01
FINETUNE_EPOCHS = 45  # User should be able to specify this

SPECIES_LIST = [
    d.replace('_model', '')
    for d in os.listdir(BASE_PATH)
    if os.path.isdir(os.path.join(BASE_PATH, d)) and d.endswith('_model')
]
# Dynamic updates based on what is found in the base directory (looking files ending in '_model')

CONFIG_MAP = {
    s: os.path.join(BASE_PATH, f'{s}_model', f'{s}.yaml') for s in SPECIES_LIST
}  # Map species to their specific yaml files

# -------------------------
# LABEL.TXT PREPARATION
# -------------------------
SPECIES_IDS = {s: 0 for s in SPECIES_LIST}
SPLITS = ['train', 'val']
BASE_PATH = '../data/seed'


def prepare_data_labels():
    for species, folder_id in SPECIES_IDS.items():
        for split in SPLITS:
            path = os.path.join(BASE_PATH, f'{species}_model', split, 'labels')
            if os.path.exists(path):
                update_class_labels(path, 0)
                print(f'  - Updated labels for {species} ({split}) to ID 0')
            else:
                print(f'  - Path not found {path}')


if PREPARE_LABELS:
    prepare_data_labels()
    print(f'Class labels prepared')

# -------------------------
# TRAIN
# -------------------------

best_model_paths = {}

for species in SPECIES_LIST:
    expected_path = os.path.join('runs', 'obb', 'species', 'weights', 'best.pt')

    if RETRAIN:
        run_name = get_next_run_name(species)
        print(f'Training started on {species}...')
        if TRAINING_MODE == 'finetune':
            ckpt = FINETUNE_WEIGHTS.get(species)
            if ckpt and os.path.isfile(ckpt):
                pass  # If species-specific weights exist, proceed with the incremental training as intended
            else:
                raise FileNotFoundError(f'Fine-tune checkpoint missing: {ckpt}')
            out_pt = train_species_model(
                species,
                CONFIG_MAP[species],
                epochs=FINETUNE_EPOCHS,
                finetune_from=ckpt,
                run_name=run_name,
                lr0=FINETUNE_LR0,
                lrf=FINETUNE_LRF,
            )
            best_model_paths[species] = os.path.abspath(out_pt)
        else:
            new_pt = train_species_model(
                species, CONFIG_MAP[species], run_name=run_name
            )
            best_model_paths[species] = os.path.abspath(new_pt)
    else:  # If not retraining, finds the latest model path per species
        target_dir = os.path.join('runs', 'obb')
        existing = (
            [d for d in os.listdir(target_dir) if d.startswith(species)]
            if os.path.exists(target_dir)
            else []
        )
        if existing:
            # Sort by: base name first, then base2, base3, and so on
            latest_run = sorted(existing, key=lambda x: (len(x), x))[-1]
            expected_path = os.path.join(
                'runs', 'obb', latest_run, 'weights', 'best.pt'
            )
        else:
            expected_path = os.path.join('runs', 'obb', species, 'weights', 'best.pt')

        best_model_paths[species] = expected_path

        if not os.path.exists(best_model_paths[species]):
            print(
                f'No model found at {expected_path}. Train a new model for {species}.'
            )
            del best_model_paths[species]
        else:
            print(f'Using model: {best_model_paths[species]}')


# -------------------------
# LOAD MODEL
# -------------------------
models = {s: load_model(path) for s, path in best_model_paths.items()}


# -------------------------
# LOAD DATA
# -------------------------
VAL_BASE = '../data/seed'

# Extract seed species (from image name or handwritten label)
ocr_tool = LabelExtractor(gpu=False)
verify_and_route_data(VAL_BASE, SPECIES_LIST, ocr_tool)

image_paths = []


for species in SPECIES_LIST:
    species_dir = os.path.join(VAL_BASE, f'{species}_model', 'val', 'images')

    for img in os.listdir(species_dir):
        image_paths.append((species, os.path.join(species_dir, img)))

# -------------------------
# RESULTS STORAGE
# -------------------------
results = defaultdict(
    lambda: {'total_error': 0, 'total_gt': 0, 'images': 0, 'tp': 0, 'fp': 0, 'fn': 0}
)


run = InferenceRun.objects.create(
    module='seeds',
    name='Seed inference test',
    status='completed',
)

# -------------------------
# LOOP
# -------------------------

for species in SPECIES_LIST:
    species_img_dir = os.path.join(VAL_BASE, f'{species}_model', 'val', 'images')
    if not os.path.exists(species_img_dir):
        continue

    if species not in models:
        print(f'  - Skipping inference for {species} (no model loaded).')
        continue

    # Select the model specialized for this species
    current_model = models[species]

    for img_name in os.listdir(species_img_dir):
        img_path = os.path.join(species_img_dir, img_name)

        with Image.open(img_path) as im:
            img_width, img_height = im.size

        gt_boxes = load_ground_truth(img_path)

        # Run inference using the specific species model
        result = run_sahi(img_path, current_model)

        # Prediction image output to see what the model catches
        output_filename = f'predicted_{img_name}'

        predicted_path = os.path.join(
            'seed_src/prediction_images/', f'{img_name.split(".")[0]}.png'
        )

        result.export_visuals(
            export_dir='seed_src/prediction_images/',
            file_name=img_name.split('.')[0],
            hide_labels=True,
            hide_conf=True,
        )

        # Save predicted images into django media storage so that they can be displayed in frontend.
        with open(predicted_path, 'rb') as f:
            image_asset = ImageAsset.objects.create(
                module='seeds',
                purpose='inference_output',
                width=img_width,
                height=img_height,
            )

            image_asset.file.save(
                os.path.basename(predicted_path),
                File(f),
                save=True,
            )

        run.images.add(image_asset)

        preds = []

        for pred in result.object_prediction_list:
            poly = None

            if hasattr(pred, 'obb') and pred.obb is not None:
                poly = pred.obb.points if hasattr(pred.obb, 'points') else pred.obb
            elif hasattr(pred, 'polygon') and pred.polygon is not None:
                poly = (
                    pred.polygon.exterior
                    if hasattr(pred.polygon, 'exterior')
                    else pred.polygon
                )
            elif hasattr(pred, 'mask') and pred.mask is not None:
                poly = pred.mask.segmentation[0]

            # Fallback only if rotation data is missing
            if poly is None and pred.bbox is not None:
                bbox = pred.bbox
                poly = [
                    bbox.minx,
                    bbox.miny,
                    bbox.maxx,
                    bbox.miny,
                    bbox.maxx,
                    bbox.maxy,
                    bbox.minx,
                    bbox.maxy,
                ]

            if poly is not None:
                if isinstance(poly[0], (list, tuple)):
                    flat_poly = [float(c) for point in poly for c in point]
                else:
                    flat_poly = [float(c) for c in poly]

                preds.append(
                    {'poly': flat_poly[:8], 'class': 0, 'conf': float(pred.score.value)}
                )

                xs = flat_poly[0::2]
                ys = flat_poly[1::2]

                x1 = min(xs)
                x2 = max(xs)
                y1 = min(ys)
                y2 = max(ys)

                # In the detection save block, store flat polygon alongside bbox
                Detection.objects.create(
                    inference_run=run,
                    image=image_asset,
                    confidence=float(pred.score.value),
                    predicted_class=species,
                    area=(x2 - x1) * (y2 - y1),
                    bbox={
                        'x1': x1,
                        'y1': y1,
                        'x2': x2,
                        'y2': y2,
                    },
                    polygon=flat_poly[:8],
                )

        tp, fp, fn = calculate_tp_fp_fn(preds, gt_boxes, iou_threshold=0.3)

        # Save the preds to a json file for testing the seed size calculations
        export_dir = 'seed_src/predictions/'
        os.makedirs(export_dir, exist_ok=True)
        file_path = os.path.join(export_dir, f'{img_name.split(".")[0]}_preds.json')

        with open(file_path, 'w') as f:
            json.dump(preds, f)

        # Detailed per-image logging
        num_preds = len(preds)
        num_gts = len(gt_boxes)
        print(f'  - Found {num_preds} predictions and {num_gts} ground truths.')
        print(f'  - Matches: TP={tp}, FP={fp}, FN={fn}')

        detected = len(preds)
        expected = len(gt_boxes)
        diff = detected - expected

        results[species]['total_error'] += abs(diff)
        results[species]['total_gt'] += expected
        results[species]['images'] += 1
        results[species]['tp'] += tp
        results[species]['fp'] += fp
        results[species]['fn'] += fn

# -------------------------
# RESULTS
# -------------------------


print('\n==== PER SPECIES RESULTS ====\n')

for species, r in results.items():
    mae = r['total_error'] / r['images'] if r['images'] > 0 else 0
    precision, recall, f1 = calculate_precision_recall_f1_score(
        r['tp'], r['fp'], r['fn']
    )

    print(f'{species}:')
    print(f'  Images: {r["images"]}')
    print(f'  MAE: {mae:.2f}')
    print(f'  TP: {r["tp"]} | FP: {r["fp"]} | FN: {r["fn"]}')
    print(f'  Precision: {precision:.2f}')
    print(f'  Recall: {recall:.2f}')
    print(f'  F1-score: {f1:.2f}')
    print('-' * 30)

# Overall results
overall_tp = sum(r['tp'] for r in results.values())
overall_fp = sum(r['fp'] for r in results.values())
overall_fn = sum(r['fn'] for r in results.values())

op, or_, of1 = calculate_precision_recall_f1_score(overall_tp, overall_fp, overall_fn)
print('\n==== Overall results ====\n')
print(f'  TP: {overall_tp} | FP: {overall_fp} | FN: {overall_fn}')
print(f'  Precision: {op:.2f}')
print(f'  Recall: {or_:.2f}')
print(f'  F1: {of1:.2f}')
