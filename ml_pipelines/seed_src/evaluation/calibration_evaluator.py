"""
Confidence Calibration Evaluation for seed models that
calculates the Expected Calibration Error (ECE) and plots reliability
diagrams to check if model confidence scores are trustworthy.
"""

import os
import sys

import matplotlib.pyplot as plt
import numpy as np
from shapely.geometry import Polygon
from sklearn.calibration import calibration_curve

ML_PIPELINES_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
os.chdir(ML_PIPELINES_DIR)
sys.path.append(ML_PIPELINES_DIR)

from seed_src.inference.inference import run_sahi
from seed_src.utils.helpers import load_ground_truth, load_model


# -------------------------
# CALIBRATION HELPERS
# -------------------------
def calculate_iou(poly1_coords, poly2_coords):
    """Calculates IoU between two 8-point polygons using Shapely."""
    try:
        p1 = Polygon([(poly1_coords[i], poly1_coords[i + 1]) for i in range(0, 8, 2)])
        p2 = Polygon([(poly2_coords[i], poly2_coords[i + 1]) for i in range(0, 8, 2)])
        if not p1.is_valid:
            p1 = p1.buffer(0)
        if not p2.is_valid:
            p2 = p2.buffer(0)
        intersection = p1.intersection(p2).area
        union = p1.union(p2).area
        return intersection / union if union > 0 else 0
    except Exception:
        return 0


def expected_calibration_error(y_true, y_prob, n_bins=10):
    """Calculates the Expected Calibration Error (ECE)."""
    bins = np.linspace(0.0, 1.0 + 1e-8, n_bins + 1)
    binids = np.digitize(y_prob, bins) - 1

    bin_sums = np.bincount(binids, weights=y_prob, minlength=len(bins))
    bin_true = np.bincount(binids, weights=y_true, minlength=len(bins))
    bin_total = np.bincount(binids, minlength=len(bins))

    nonzero = bin_total != 0
    prob_true = bin_true[nonzero] / bin_total[nonzero]
    prob_pred = bin_sums[nonzero] / bin_total[nonzero]

    ece = np.sum(np.abs(prob_true - prob_pred) * (bin_total[nonzero] / len(y_true)))
    return ece


# -------------------------
# SETTINGS & SETUP
# -------------------------
BASE_PATH = '../data/seed'
SPECIES_LIST = [
    d.replace('_model', '')
    for d in os.listdir(BASE_PATH)
    if os.path.isdir(os.path.join(BASE_PATH, d)) and d.endswith('_model')
]
IOU_THRESHOLD = 0.3

print('Loading models...')
models = {
    s: load_model(os.path.abspath(os.path.join('runs', 'obb', s, 'weights', 'best.pt')))
    for s in SPECIES_LIST
}

# -------------------------
# EVALUATION LOOP
# -------------------------
os.makedirs('evaluations/calibration_plots', exist_ok=True)

for species in SPECIES_LIST:
    print(f'\nAnalyzing Calibration for {species.upper()}...')
    species_img_dir = os.path.join(BASE_PATH, f'{species}_model', 'val', 'images')
    if not os.path.exists(species_img_dir):
        continue

    current_model = models[species]
    all_confidences = []
    all_is_correct = []  # 1 for TP, 0 for FP

    for img_name in os.listdir(species_img_dir):
        img_path = os.path.join(species_img_dir, img_name)
        gt_boxes = load_ground_truth(img_path)

        result = run_sahi(img_path, current_model)

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
                preds.append({'poly': flat_poly[:8], 'conf': float(pred.score.value)})

        # Sort predictions by confidence, in descending order
        preds = sorted(preds, key=lambda x: x['conf'], reverse=True)
        matched_gt_indices = set()

        for p in preds:
            best_iou = 0
            best_gt_idx = -1

            for idx, gt in enumerate(gt_boxes):
                if idx in matched_gt_indices:
                    continue
                iou = calculate_iou(p['poly'], gt)
                if iou > best_iou:
                    best_iou = iou
                    best_gt_idx = idx

            all_confidences.append(p['conf'])
            if best_iou >= IOU_THRESHOLD:
                all_is_correct.append(1)  # TP
                matched_gt_indices.add(best_gt_idx)
            else:
                all_is_correct.append(0)  # FP

    # -------------------------
    # METRICS AND PLOT
    # -------------------------
    if len(all_confidences) == 0:
        continue

    y_true = np.array(all_is_correct)
    y_prob = np.array(all_confidences)

    ece = expected_calibration_error(y_true, y_prob)
    print(f'  Expected Calibration Error (ECE): {ece:.4f}')

    prob_true, prob_pred = calibration_curve(
        y_true, y_prob, n_bins=10, strategy='uniform'
    )

    plt.figure(figsize=(8, 8))
    plt.plot([0, 1], [0, 1], 'k:', label='Perfectly calibrated')
    plt.plot(prob_pred, prob_true, 's-', label=f'{species.upper()} (ECE={ece:.3f})')
    plt.ylabel('Fraction of True Positives')
    plt.xlabel('Mean Predicted Confidence')
    plt.title(f'Reliability Diagram: {species.upper()}')
    plt.legend(loc='lower right')
    plt.grid(True, alpha=0.3)

    plot_path = f'evaluations/calibration_plots/{species}_calibration.png'
    plt.savefig(plot_path)
    plt.close()

    print(f'  -> Saved Reliability Diagram to {plot_path}')

print('\nCalibration Analysis Complete.')
