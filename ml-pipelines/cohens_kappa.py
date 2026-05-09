import os

from PIL import Image
from seed_src.metrics import calculate_tp_fp_fn
from sklearn.metrics import cohen_kappa_score

BASE_PATH = '../data/seed'
SPECIES_LIST = ['cat', 'peh', 'phyca', 'vau']


def load_specific_ground_truth(img_path, label_path):
    gt_boxes = []
    if not os.path.exists(label_path):
        return gt_boxes

    with Image.open(img_path) as img:
        width, height = img.size

    # Open the specific label file (named, for example,
    # "IMG_0044_A.jpg" and "IMG_0044_B.jpg" - one for annotator A and one for annotator B)
    with open(label_path, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 9:
                continue

            norm_coords = list(map(float, parts[1:]))
            pixel_coords = []
            for i in range(len(norm_coords)):
                if i % 2 == 0:
                    pixel_coords.append(norm_coords[i] * width)
                else:
                    pixel_coords.append(norm_coords[i] * height)

            gt_boxes.append(pixel_coords)

    return gt_boxes


# Calculate Bohen's Kappa
all_y_true = []
all_y_pred = []

# Our folder structure should follow the same format just like in train/ and val/:
# {species}_model/cohens_kappa/images and {species}_model/cohens_kappa/labels
for species in SPECIES_LIST:
    kappa_img_dir = os.path.join(
        BASE_PATH, f'{species}_model', 'cohens_kappa', 'images'
    )

    kappa_lbl_dir = os.path.join(
        BASE_PATH, f'{species}_model', 'cohens_kappa', 'labels'
    )

    if not os.path.exists(kappa_img_dir):
        print(f'Skipping {species}: Folder not found.')
        continue

    images = [f for f in os.listdir(kappa_img_dir) if f.endswith(('.png', '.jpg'))]

    for img_name in images:
        img_path = os.path.join(kappa_img_dir, img_name)

        base_name = os.path.splitext(img_name)[0]

        # Specific label paths to compare
        label_a_path = os.path.join(kappa_lbl_dir, f'{base_name}_A.txt')
        label_b_path = os.path.join(kappa_lbl_dir, f'{base_name}_B.txt')

        boxes_a = load_specific_ground_truth(img_path, label_a_path)
        boxes_b = load_specific_ground_truth(img_path, label_b_path)

        preds_b = [{'poly': b, 'class': 0} for b in boxes_b]

        # Calculate tp, fp, fn used later in Cohen's Kappa calculation
        tp, fp, fn = calculate_tp_fp_fn(preds_b, boxes_a, iou_threshold=0.3)

        y_true = [1] * (tp + fn) + [0] * fp
        y_pred = [1] * tp + [0] * fn + [1] * fp

        all_y_true.extend(y_true)
        all_y_pred.extend(y_pred)

        print(f'  Processed {species} - {img_name}: Matches={tp}, Misses={fn + fp}')

# Calculate overall Cohen's Kappa score
if all_y_true:
    kappa = cohen_kappa_score(all_y_true, all_y_pred)
    print(f"\nFINAL COHEN'S KAPPA: {kappa:.4f}")
else:
    print('No data found to calculate Kappa.')
