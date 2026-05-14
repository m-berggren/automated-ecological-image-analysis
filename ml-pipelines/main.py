import json
import os
from collections import defaultdict

from seed_src.metrics import calculate_precision_recall_f1_score, calculate_tp_fp_fn
from seed_src.train import train_species_model
from seed_src.utils import (
    load_ground_truth,
    load_model,
    run_sahi,
    update_class_labels,
)

# -------------------------
# SETTINGS
# -------------------------
PREPARE_LABELS = True  # Set to True to run the label update on newly added label files
RETRAIN = False  # Set to True to train a new model from scratch, False to use existing weights
TRAINING_MODE = 'finetune'  # This we can set to either 'fresh' (train from scratch) or 'finetune' (incremental training)
FINETUNE_WEIGHTS = {  # Per-species checkpoint to fine-tune from (best.pt or last.pt). Only used if TRAIN_MODE == 'finetune'
    'cat': os.path.abspath(
        os.path.join('runs', 'obb', 'cat', 'weights', 'best.pt')
    ),  # Might need to update these paths later
    'peh': os.path.abspath(os.path.join('runs', 'obb', 'peh', 'weights', 'best.pt')),
    'phyca': os.path.abspath(
        os.path.join('runs', 'obb', 'phyca', 'weights', 'best.pt')
    ),
    'vau': os.path.abspath(os.path.join('runs', 'obb', 'vau', 'weights', 'best.pt')),
}
FINETUNE_RUN_SUFFIX = (
    ''  # Suffix for the new run directory. A bit clunky now so will update later
)
# Optional: lower LR for fine-tuning (set to None to use Ultralytics defaults)
FINETUNE_LR0 = 0.001  # example learning rate, potentially the user should be able to specify/tune this tune (or set to None to use Ultralytics defaults)
FINETUNE_LRF = 0.01  # example learning rate, same note as LR0
FINETUNE_EPOCHS = 45  # example, user should definitely be able to specify this (probably will be set to less than a full fresh run)

SPECIES_LIST = [
    'cat',
    'peh',
    'phyca',
    'vau',
]  # Removed the rest of the species temporarily so I can test incremental training on PEH where we had new images
# The above is potentially a clunky solution

CONFIG_MAP = {
    s: f'../data/seed/{s}_model/{s}.yaml' for s in SPECIES_LIST
}  # Map species to their specific yaml files

# -------------------------
# LABEL PREPARATION
# -------------------------
SPECIES_IDS = {'cat': 0, 'peh': 0, 'phyca': 0, 'vau': 0}
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
    expected_path = os.path.join(
        'runs', 'obb', f'{species}{FINETUNE_RUN_SUFFIX}', 'weights', 'best.pt'
    )  # Might need to update this path later

    if RETRAIN:
        print(f'Training started on {species}...')
        if TRAINING_MODE == 'finetune':
            ckpt = FINETUNE_WEIGHTS[species]
            if not os.path.isfile(ckpt):
                raise FileNotFoundError(f'Fine-tune checkpoint missing: {ckpt}')
            out_pt = train_species_model(
                species,
                CONFIG_MAP[species],
                epochs=FINETUNE_EPOCHS,
                finetune_from=ckpt,
                run_name=f'{species}{FINETUNE_RUN_SUFFIX}',
                lr0=FINETUNE_LR0,
                lrf=FINETUNE_LRF,
            )
            best_model_paths[species] = os.path.abspath(out_pt)
        else:
            new_pt = train_species_model(species, CONFIG_MAP[species])
            best_model_paths[species] = os.path.abspath(new_pt)
    else:
        best_model_paths[species] = expected_path

        if not os.path.exists(best_model_paths[species]):
            print(f'No model found at {expected_path} → training new one')
            new_pt = train_species_model(species, CONFIG_MAP[species])
            best_model_paths[species] = os.path.abspath(new_pt)
    print(f'Using model: {best_model_paths[species]}')


# -------------------------
# LOAD MODEL
# -------------------------
# model = load_model(best_model_path)
models = {s: load_model(path) for s, path in best_model_paths.items()}


# -------------------------
# LOAD DATA
# -------------------------
VAL_BASE = '../data/seed'

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

# -------------------------
# LOOP
# -------------------------

for species in SPECIES_LIST:
    species_img_dir = os.path.join(VAL_BASE, f'{species}_model', 'val', 'images')
    if not os.path.exists(species_img_dir):
        continue

    # Select the model specialized for this species
    current_model = models[species]

    for img_name in os.listdir(species_img_dir):
        img_path = os.path.join(species_img_dir, img_name)
        gt_boxes = load_ground_truth(img_path)

        # Run inference using the specific species model
        result = run_sahi(img_path, current_model)

        # Debug image output to see what the model catches, classification, confidence score
        output_filename = f'debug_{img_name}'
        result.export_visuals(
            export_dir='debug_outputs/',
            file_name=img_name,
            hide_labels=True,  # Removes class names
            hide_conf=True,  # Removes confidence scores
        )

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
                # Standardize poly to a flat list of floats [x1, y1, x2, y2, x3, y3, x4, y4]
                if isinstance(poly[0], (list, tuple)):
                    flat_poly = [float(c) for point in poly for c in point]
                else:
                    flat_poly = [float(c) for c in poly]

                preds.append(
                    {
                        'poly': flat_poly[:8],
                        'class': 0,
                    }
                )

        tp, fp, fn = calculate_tp_fp_fn(preds, gt_boxes, iou_threshold=0.3)

        # Save the preds to a json file for testing the seed size calculations
        export_dir = 'predictions/'
        os.makedirs(export_dir, exist_ok=True)
        file_path = os.path.join(export_dir, f'{img_name}_preds.json')

        with open(file_path, 'w') as f:
            json.dump(preds, f)
        print(f'Saved seed predictions to {img_name}_preds.json')

        # Detailed per-image logging (for debug to make our lives easier, pls don't remove for now)
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
