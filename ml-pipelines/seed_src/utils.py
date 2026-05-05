import os
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction

def load_model(model_path):
    return AutoDetectionModel.from_pretrained(
        model_type="ultralytics",
        model_path=model_path,
        confidence_threshold=0.5,
        device="cpu"
    )

def run_sahi(image_path, model):
    return get_sliced_prediction(
        image_path,
        model,
        slice_height=768,
        slice_width=768,
        overlap_height_ratio=0.4,
        overlap_width_ratio=0.4,
        postprocess_type="NMS",
        postprocess_match_metric="IOU",
        postprocess_match_threshold=0.15
    )