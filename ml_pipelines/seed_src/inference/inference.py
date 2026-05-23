import os

from sahi.predict import get_sliced_prediction


def run_inference(image_path, model):
    return get_sliced_prediction(
        image_path,
        model,
        slice_height=768,
        slice_width=768,
        overlap_height_ratio=0.4,
        overlap_width_ratio=0.4,
        postprocess_type='NMS',
        postprocess_match_threshold=0.4,
    )

def generate_prediction_visuals(result, img_path, img_name, export_dir):
    """Encapsulates the result.export_visuals logic which previously existed in main.py."""
    os.makedirs(export_dir, exist_ok=True)
    result.export_visuals(
        export_dir=export_dir,
        file_name=img_name.split('.')[0],
        hide_labels=True,
        hide_conf=True,
    )
    # Return the full path to the generated image
    return os.path.join(export_dir, f"{img_name.split('.')[0]}.png")

def save_predictions_to_json(preds, img_name, export_dir):
    """Encapsulates the JSON export logic which previously existed in main.py."""
    os.makedirs(export_dir, exist_ok=True)
    file_path = os.path.join(export_dir, f'{img_name.split(".")[0]}_preds.json')
    with open(file_path, 'w') as f:
        import json
        json.dump(preds, f)
    return file_path