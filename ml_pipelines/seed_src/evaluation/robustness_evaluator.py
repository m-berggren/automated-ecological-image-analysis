"""
Robustness evaluation for the seed models.
Applies mathematical perturbations (blur, darkness, compression) to the
validation images to test the input sensitivity of the trained models.
"""

import os
import sys
import tempfile
from collections import defaultdict

import cv2
import numpy as np

ML_PIPELINES_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
os.chdir(ML_PIPELINES_DIR)
sys.path.append(ML_PIPELINES_DIR)

from seed_src.inference.inference import run_sahi
from seed_src.utils.helpers import load_ground_truth, load_model
from seed_src.utils.metrics import (
    calculate_precision_recall_f1_score,
    calculate_tp_fp_fn,
)


# -------------------------
# PERTURBATION FUNCTIONS
# -------------------------
def apply_blur(img_path, out_path, severity=15):
    """Applies Gaussian Blur to simulate dirty lenses or out-of-focus shots."""
    img = cv2.imread(img_path)
    ksize = severity if severity % 2 != 0 else severity + 1  # ksize must be odd
    blurred = cv2.GaussianBlur(img, (ksize, ksize), 0)
    cv2.imwrite(out_path, blurred)


def apply_darkness(img_path, out_path, severity=0.4):
    """Reduces brightness to simulate poor lighting."""
    img = cv2.imread(img_path)
    # Multiply pixels by severity factor
    dark = np.clip(img * severity, 0, 255).astype(np.uint8)
    cv2.imwrite(out_path, dark)


def apply_jpeg_compression(img_path, out_path, quality=10):
    """Applies heavy JPEG compression to simulate poor image quality."""
    img = cv2.imread(img_path)
    # Quality range from 0 to 100 (lower is more compressed)
    cv2.imwrite(out_path, img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])


# Perturbations, explored various values to find weak points
PERTURBATIONS = {
    'clean_baseline': None,
    #   'gaussian_blur_15px': lambda i, o: apply_blur(i, o, severity=15),
    #   'darkness_60_percent': lambda i, o: apply_darkness(
    #       i, o, severity=0.4
    #   ),  # 60% darker
    'jpeg_compression_10': lambda i, o: apply_jpeg_compression(i, o, quality=1),
}

# -------------------------
# SETTINGS & SETUP
# -------------------------
BASE_PATH = '../data/seed'
SPECIES_LIST = [
    d.replace('_model', '')
    for d in os.listdir(BASE_PATH)
    if os.path.isdir(os.path.join(BASE_PATH, d)) and d.endswith('_model')
]

print('Loading models...')
models = {
    s: load_model(os.path.abspath(os.path.join('runs', 'obb', s, 'weights', 'best.pt')))
    for s in SPECIES_LIST
}

results = defaultdict(
    lambda: defaultdict(lambda: {'tp': 0, 'fp': 0, 'fn': 0, 'images': 0})
)

# -------------------------
# EVALUATION LOOP
# -------------------------
with tempfile.TemporaryDirectory() as temp_dir:
    for species in SPECIES_LIST:
        print(f'\nEvaluating robustness for species: {species.upper()}')
        species_img_dir = os.path.join(BASE_PATH, f'{species}_model', 'val', 'images')

        if not os.path.exists(species_img_dir):
            continue

        images = os.listdir(species_img_dir)
        current_model = models[species]

        for img_name in images:
            img_path = os.path.join(species_img_dir, img_name)
            gt_boxes = load_ground_truth(img_path)

            for condition_name, apply_func in PERTURBATIONS.items():
                if condition_name == 'clean_baseline':
                    test_img_path = img_path
                else:
                    test_img_path = os.path.join(
                        temp_dir, f'{condition_name}_{img_name}'
                    )
                    apply_func(img_path, test_img_path)

                result = run_sahi(test_img_path, current_model)

                preds = []
                for pred in result.object_prediction_list:
                    poly = None
                    if hasattr(pred, 'obb') and pred.obb is not None:
                        poly = (
                            pred.obb.points if hasattr(pred.obb, 'points') else pred.obb
                        )
                    elif hasattr(pred, 'polygon') and pred.polygon is not None:
                        poly = (
                            pred.polygon.exterior
                            if hasattr(pred.polygon, 'exterior')
                            else pred.polygon
                        )

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
                        flat_poly = (
                            [float(c) for point in poly for c in point]
                            if isinstance(poly[0], (list, tuple))
                            else [float(c) for c in poly]
                        )
                        preds.append({'poly': flat_poly[:8], 'class': 0})

                tp, fp, fn = calculate_tp_fp_fn(preds, gt_boxes, iou_threshold=0.3)

                results[species][condition_name]['tp'] += tp
                results[species][condition_name]['fp'] += fp
                results[species][condition_name]['fn'] += fn
                results[species][condition_name]['images'] += 1

# -------------------------
# RESULTS
# -------------------------
print('\n' + '=' * 50)
print(' ROBUSTNESS EVALUATION REPORT ')
print('=' * 50)

for species in SPECIES_LIST:
    print(f'\n--- {species.upper()} ---')

    # Calculate baseline first to be able to compute the degradation on changed conditions
    base_r = results[species]['clean_baseline']
    _, _, base_f1 = calculate_precision_recall_f1_score(
        base_r['tp'], base_r['fp'], base_r['fn']
    )

    for condition, r in results[species].items():
        if r['images'] == 0:
            continue

        p, rec, f1 = calculate_precision_recall_f1_score(r['tp'], r['fp'], r['fn'])

        if condition == 'clean_baseline':
            print(
                f'{condition.ljust(25)} | F1: {f1:.3f} | TP: {r["tp"]}, FP: {r["fp"]}, FN: {r["fn"]}'
            )
        else:
            drop = base_f1 - f1
            drop_str = f'(-{drop:.3f})' if drop > 0 else f'(+{abs(drop):.3f})'
            print(
                f'{condition.ljust(25)} | F1: {f1:.3f} {drop_str.ljust(8)} | TP: {r["tp"]}, FP: {r["fp"]}, FN: {r["fn"]}'
            )
