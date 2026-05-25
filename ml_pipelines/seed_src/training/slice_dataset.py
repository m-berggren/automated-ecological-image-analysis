import os

from PIL import Image
from shapely.geometry import Polygon, box

# -------------------------
# SETTINGS
# -------------------------
BASE_PATH = '../data/seed'
SPECIES_LIST = ['cat', 'peh', 'phyca', 'vau']
SPLITS = ['train']

SLICE_SIZE = 768
OVERLAP = 0.2  # 20% overlap between slices
STRIDE = int(SLICE_SIZE * (1 - OVERLAP))


def process_image(img_path, label_path, output_img_dir, output_lbl_dir):
    img = Image.open(img_path)
    img_w, img_h = img.size
    base_name = os.path.splitext(os.path.basename(img_path))[0]

    # Load original labels and convert to absolute pixel coordinates
    original_boxes = []
    if os.path.exists(label_path):
        with open(label_path, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) < 9:
                    continue
                class_id = parts[0]
                coords = list(map(float, parts[1:]))

                # Convert normalized (0-1) to absolute pixels
                abs_coords = []
                for i in range(8):
                    abs_coords.append(
                        coords[i] * img_w if i % 2 == 0 else coords[i] * img_h
                    )
                original_boxes.append({'class': class_id, 'poly': abs_coords})

    # Generate Crop Windows
    x_points = list(range(0, img_w, STRIDE))
    y_points = list(range(0, img_h, STRIDE))

    # Ensure we don't go out of bounds on the far right/bottom edges
    if x_points[-1] + SLICE_SIZE > img_w:
        x_points[-1] = max(0, img_w - SLICE_SIZE)
    if y_points[-1] + SLICE_SIZE > img_h:
        y_points[-1] = max(0, img_h - SLICE_SIZE)

    # Remove duplicates if image is smaller than slice size
    x_points = sorted(list(set(x_points)))
    y_points = sorted(list(set(y_points)))

    for y in y_points:
        for x in x_points:
            crop_box = box(x, y, x + SLICE_SIZE, y + SLICE_SIZE)
            new_labels = []

            for b in original_boxes:
                poly_pts = [(b['poly'][i], b['poly'][i + 1]) for i in range(0, 8, 2)]
                seed_poly = Polygon(poly_pts)

                # If the seed's centroid is inside our crop window, we keep it
                if crop_box.contains(seed_poly.centroid):
                    # Shift coordinates relative to the new crop window
                    shifted_poly = []
                    for px, py in poly_pts:
                        # Clamp points to the crop boundaries so boxes don't bleed off-image
                        new_x = max(0, min(px - x, SLICE_SIZE))
                        new_y = max(0, min(py - y, SLICE_SIZE))

                        # Normalize to 0-1 for YOLO format
                        shifted_poly.extend([new_x / SLICE_SIZE, new_y / SLICE_SIZE])

                    new_labels.append(
                        f'{b["class"]} ' + ' '.join(map(str, shifted_poly))
                    )

            # Only save the image slice if it contains seeds OR if you want background images
            # (Saving some empty background images is good for reducing False Positives)
            crop_name = f'{base_name}_x{x}_y{y}'

            # Save cropped image
            cropped_img = img.crop((x, y, x + SLICE_SIZE, y + SLICE_SIZE))
            cropped_img.save(os.path.join(output_img_dir, f'{crop_name}.png'))

            # Save cropped label
            with open(os.path.join(output_lbl_dir, f'{crop_name}.txt'), 'w') as f:
                if new_labels:
                    f.write('\n'.join(new_labels) + '\n')


if __name__ == '__main__':
# -------------------------
# EXECUTION
# -------------------------
    for species in SPECIES_LIST:
        for split in SPLITS:
            input_img_dir = os.path.join(BASE_PATH, f'{species}_model', split, 'images')
            input_lbl_dir = os.path.join(BASE_PATH, f'{species}_model', split, 'labels')

            # Create new directories for the sliced data
            out_img_dir = os.path.join(
                BASE_PATH, f'{species}_model', f'{split}_sliced', 'images'
            )
            out_lbl_dir = os.path.join(
                BASE_PATH, f'{species}_model', f'{split}_sliced', 'labels'
            )

            os.makedirs(out_img_dir, exist_ok=True)
            os.makedirs(out_lbl_dir, exist_ok=True)

            if not os.path.exists(input_img_dir):
                continue

            print(f'Slicing {species} - {split}...')
            for img_name in os.listdir(input_img_dir):
                if img_name.endswith(('.png', '.jpg', '.jpeg')):
                    img_path = os.path.join(input_img_dir, img_name)
                    lbl_path = os.path.join(
                        input_lbl_dir, os.path.splitext(img_name)[0] + '.txt'
                    )
                    process_image(img_path, lbl_path, out_img_dir, out_lbl_dir)

    print('Sliced datasets created.')
