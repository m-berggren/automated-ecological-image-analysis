"""
Occlusion Sensitivity Analysis for the seed_src pipeline.
Slides a masking patch across an image to find spatial vulnerabilities.
"""

import os
import sys
import tempfile

import cv2
import matplotlib.pyplot as plt
import numpy as np

ML_PIPELINES_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
os.chdir(ML_PIPELINES_DIR)
sys.path.append(ML_PIPELINES_DIR)

from seed_src.inference.inference import run_sahi
from seed_src.utils.helpers import load_model

PATCH_SIZE = 150
STRIDE = 150
SPECIES = 'cat'  # Model to test, updated by species


def main():
    print(f'Loading {SPECIES.upper()} model...')
    model = load_model(os.path.abspath(f'runs/obb/{SPECIES}/weights/best.pt'))

    # Pick a specific validation image to test
    img_dir = f'../data/seed/{SPECIES}_model/val/images/'
    img_name = os.listdir(img_dir)[0]
    img_path = os.path.join(img_dir, img_name)

    original_img = cv2.imread(img_path)
    h, w, _ = original_img.shape

    # Baseline inference run
    print('Calculating baseline predictions...')
    base_result = run_sahi(img_path, model)
    base_count = len(base_result.object_prediction_list)
    base_conf_sum = sum([p.score.value for p in base_result.object_prediction_list])
    print(f'Baseline -> Seeds: {base_count}, Total Confidence: {base_conf_sum:.2f}')

    # Occlusion Grid
    rows = h // STRIDE
    cols = w // STRIDE
    sensitivity_map = np.zeros((rows, cols))

    print(f'Running occlusion grid ({rows}x{cols} patches)...')

    with tempfile.TemporaryDirectory() as tmp:
        for r in range(rows):
            for c in range(cols):
                y, x = r * STRIDE, c * STRIDE

                occluded = original_img.copy()
                # Black out the current patch
                occluded[y : y + PATCH_SIZE, x : x + PATCH_SIZE] = 0

                tmp_path = os.path.join(tmp, f'occ_{r}_{c}.jpg')
                cv2.imwrite(tmp_path, occluded)

                # Run inference on occluded image
                result = run_sahi(tmp_path, model)
                occ_conf_sum = sum(
                    [p.score.value for p in result.object_prediction_list]
                )

                # Calculate sensitivity, meaning how much confidence was
                # lost globally by blacking out the current patch
                drop = base_conf_sum - occ_conf_sum
                sensitivity_map[r, c] = max(0, drop)

                sys.stdout.write(
                    f'\rProcessed patch ({r + 1},{c + 1})/({rows}x{cols}). Confidence Drop: {drop:.2f}\n'
                )
                sys.stdout.flush()

    # Heatmap
    plt.figure(figsize=(10, 8))
    plt.imshow(cv2.cvtColor(original_img, cv2.COLOR_BGR2RGB), alpha=0.5)
    plt.imshow(cv2.resize(sensitivity_map, (w, h)), cmap='inferno', alpha=0.7)
    plt.colorbar(label='Confidence Drop')
    plt.title(f'Occlusion Sensitivity Map: {SPECIES.upper()}')

    os.makedirs('evaluations/occlusion_plots', exist_ok=True)
    out_path = f'evaluations/occlusion_plots/{img_name}_heatmap.png'
    plt.savefig(out_path)
    print(f'\nSaved heatmap overlay to {out_path}')


if __name__ == '__main__':
    main()
