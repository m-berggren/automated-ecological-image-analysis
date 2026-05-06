import os
from collections import defaultdict

from seed_src.metrics import calculate_tp_fp_fn
from seed_src.train import train_model
from seed_src.utils import (
    get_latest_model_path,
    load_ground_truth,
    load_model,
    run_sahi,
    update_class_labels,
)

# -------------------------
# SETTINGS
# -------------------------
PREPARE_LABELS = False  # Set to True to run the label update on newly added label files
RETRAIN = True  # Set to True to train a new model, False to use existing weights

# -------------------------
# LABEL PREPARATION
# -------------------------
SPECIES_IDS = {'cat': 0, 'peh': 1, 'phyca': 2, 'vau': 3}
SPLITS = ['train', 'val']
BASE_PATH = '../data/seed'


def prepare_data_labels():
    for split in SPLITS:
        for species, folder_id in SPECIES_IDS.items():
            path = os.path.join(BASE_PATH, split, species, 'labels')
            update_class_labels(path, folder_id)


if PREPARE_LABELS:
    prepare_data_labels()
    print(f'Class labels prepared')


# -------------------------
# TRAIN
# -------------------------

if RETRAIN:
    print('Training started...')
    best_model_path = train_model()

else:
    best_model_path = get_latest_model_path()
    if best_model_path:
        print(f'Skipping Training. Loading latest model: {best_model_path}')
    else:
        print('No trained model found. Training a new model.')
        best_model_path = train_model()

# -------------------------
# LOAD MODEL
# -------------------------
model = load_model(best_model_path)


# -------------------------
# LOAD DATA
# -------------------------
VAL_DIR = '../data/seed/val'

image_paths = []

for species in os.listdir(VAL_DIR):
    species_dir = os.path.join(VAL_DIR, species, 'images')

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
for species, img_path in image_paths:
    gt_boxes = load_ground_truth(img_path)

    result = run_sahi(img_path, model)

    # Debug image output to see what the model catches, classification, confidence score
    result.export_visuals(export_dir='debug_outputs/')

    preds = []

    for pred in result.object_prediction_list:
        poly = None

        # Check for explicit polygon points
        if hasattr(pred, 'polygon') and pred.polygon is not None:
            poly = pred.polygon.points

        # Check for segmentation mask
        elif hasattr(pred, 'mask') and pred.mask is not None:
            poly = pred.mask.segmentation[0]

        # Check for rotated bbox (OBB specific)
        elif hasattr(pred, 'obb') and pred.obb is not None:
            poly = pred.obb  # Some handlers use this

        if poly is not None:
            # Standardize to a flat list of floats
            if isinstance(poly[0], (list, tuple)):
                flat_poly = [float(c) for point in poly for c in point]
            else:
                flat_poly = [float(c) for c in poly]

            # Ensure 8 coordinates for OBB IoU
            if len(flat_poly) == 8:
                preds.append(flat_poly)
            elif len(flat_poly) > 8:
                # Simplification: if it's a complex mask, take the first 8 points
                preds.append(flat_poly[:8])

    tp, fp, fn = calculate_tp_fp_fn(preds, gt_boxes, iou_threshold=0.4)

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
