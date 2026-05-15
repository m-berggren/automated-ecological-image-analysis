import glob
import os

from PIL import Image
from sahi import AutoDetectionModel


def load_model(model_path):
    return AutoDetectionModel.from_pretrained(
        model_type='ultralytics',
        model_path=model_path,
        confidence_threshold=0.3,
        device=0,
    )


def load_ground_truth(img_path):
    """
    Translates image path to label path and loads OBB label coordinates.
    """
    label_path = img_path.replace('images', 'labels')
    label_path = os.path.splitext(label_path)[0] + '.txt'

    gt_boxes = []

    # Get image dimensions for scaling
    with Image.open(img_path) as img:
        width, height = img.size

    if not os.path.exists(label_path):
        return gt_boxes

    with open(label_path, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 9:
                continue

            # The coordinates are normalized (0-1)
            norm_coords = list(map(float, parts[1:]))

            # Scale to pixels
            pixel_coords = []
            for i in range(len(norm_coords)):
                if i % 2 == 0:  # X coordinate
                    pixel_coords.append(norm_coords[i] * width)
                else:  # Y coordinate
                    pixel_coords.append(norm_coords[i] * height)

            gt_boxes.append(pixel_coords)

    return gt_boxes


def update_class_labels(directory, new_id):
    """
    Updates the class ID in each label.txt file to match what is expected in data.yaml.
    """

    if not os.path.exists(directory):
        print(f'Directory not found: {directory}')
        return

    count = 0
    for filename in os.listdir(directory):
        if filename.endswith('.txt') and filename != 'classes.txt':
            file_path = os.path.join(directory, filename)

            with open(file_path, 'r') as f:
                lines = f.readlines()

            with open(file_path, 'w') as f:
                for line in lines:
                    parts = line.split()
                    if len(parts) > 0:
                        if parts[0] != str(new_id):
                            parts[0] = str(new_id)
                        f.write(' '.join(parts) + '\n')
            count += 1


def get_next_run_name(base_run_name):
    """
    Checks the runs/obb directory and returns a name with an incremented suffix
    if the base name already exists (e.g., 'phyca' -> 'phyca2' -> 'phyca3').
    """
    import re

    target_dir = os.path.join('runs', 'obb')
    if not os.path.exists(target_dir):
        return base_run_name

    existing_runs = [
        d for d in os.listdir(target_dir) if os.path.isdir(os.path.join(target_dir, d))
    ]

    # Filter for folders that start with the base run species name
    pattern = re.compile(rf'^{re.escape(base_run_name)}(\d*)$')

    max_num = 0
    found = False

    for run in existing_runs:
        match = pattern.match(run)
        if match:
            found = True
            suffix = match.group(1)
            if suffix == '':
                max_num = max(max_num, 1)
            else:
                max_num = max(max_num, int(suffix))

    if not found:
        return base_run_name

    return f'{base_run_name}{max_num + 1}'
