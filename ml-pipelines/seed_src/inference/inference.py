from sahi.predict import get_sliced_prediction


def run_sahi(image_path, model):
    return get_sliced_prediction(
        image_path,
        model,
        slice_height=768,
        slice_width=768,
        overlap_height_ratio=0.35,
        overlap_width_ratio=0.35,
        postprocess_type='GREEDYNMM',
        postprocess_match_metric='IOS',
        postprocess_match_threshold=0.3,
    )
