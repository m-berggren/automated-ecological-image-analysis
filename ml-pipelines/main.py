import os
from collections import defaultdict

from seed_src.metrics import calculate_tp_fp_fn
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
RETRAIN = False  # Set to True to train a new model, False to use existing weights
SPECIES_LIST = ['cat', 'peh', 'phyca', 'vau']
# Map species to their specific yaml files
CONFIG_MAP = {s: f'../data/seed/{s}_model/{s}.yaml' for s in SPECIES_LIST}

# -------------------------
# LABEL PREPARATION
# -------------------------
SPECIES_IDS = {'cat': 0, 'peh': 1, 'phyca': 2, 'vau': 3}
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
    expected_path = os.path.join('runs', 'obb', species, 'weights', 'best.pt')

    if RETRAIN:
        print(f'Training started on {species}...')
        best_model_paths[species] = train_species_model(species, CONFIG_MAP[species])

    else:
        best_model_paths[species] = expected_path

        if not best_model_paths[species]:
            print('No model found → training new one')
            best_model_paths[species] = train_species_model(
                species, CONFIG_MAP[species]
            )

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

    print(f'{species}:')
    print(f'  Images: {r["images"]}')
    print(f'  MAE: {mae:.2f}')
    print(f'  TP: {r["tp"]} | FP: {r["fp"]} | FN: {r["fn"]}')
    print('-' * 30)
