import glob
import os

from PIL import Image
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction


def load_model(model_path):
    return AutoDetectionModel.from_pretrained(
        model_type='ultralytics',
        model_path=model_path,
        confidence_threshold=0.25,
        device='cpu',
    )


def run_sahi(image_path, model):
    return get_sliced_prediction(
        image_path,
        model,
        slice_height=768,
        slice_width=768,
        overlap_height_ratio=0.25,
        overlap_width_ratio=0.25,
        postprocess_type='NMS',
        postprocess_match_metric='IOU',
        postprocess_match_threshold=0.15,
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


def get_latest_model_path(base_path='runs/obb'):
    """
    Finds the latest 'train' folder and returns the path to its best.pt weights.
    """
    folders = glob.glob(os.path.join(base_path, 'train*'))
    if not folders:
        return None

    latest_folder = max(folders, key=os.path.getctime)
    best_weights = os.path.join(latest_folder, 'weights', 'best.pt')

    return best_weights if os.path.exists(best_weights) else None
