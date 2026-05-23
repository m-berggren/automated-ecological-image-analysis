from apps.analysis.models import Detection, InferenceRun
from apps.datasets.models import ImageAsset
from ml_pipelines.seed_src.inference.confidence_analyzer import analyze_seed_confidence
from ml_pipelines.seed_src.utils.active_seed_calculator import (
    count_active_and_aborted_seeds,
)


def calculate_seed_status(reference_detection_id: int, image_id: int):
    reference = Detection.objects.get(id=reference_detection_id)
    detections = list(Detection.objects.filter(image_id=image_id))
    reference_poly = reference.polygon

    detected_seeds = [
        {'poly': d.polygon, 'id': d.id, 'confidence': d.confidence} for d in detections
    ]

    result = count_active_and_aborted_seeds(
        reference_seed=reference_poly,
        detected_seeds=detected_seeds,
        threshold=0.30,
    )

    status_map = {c['detection_id']: c['status'] for c in result['classifications']}
    active_seeds_for_analysis = []

    for d in detections:
        status = status_map.get(d.id, 'unknown')
        d.seed_status = status
        d.predicted_class = status
        d.save(update_fields=['seed_status', 'predicted_class'])

        # Determine the confidence range of the 'active' seed count
        if status == 'active':
            active_seeds_for_analysis.append({'conf': d.confidence})

    conf_analysis = analyze_seed_confidence(
        active_seeds_for_analysis, risk_threshold=0.20
    )

    # Save calculated metrics to the ImageAsset metadata for the frontend to read
    image = ImageAsset.objects.get(id=image_id)
    if not isinstance(image.metadata, dict):
        image.metadata = {}

    image.metadata['seed_range_min'] = conf_analysis['estimated_range'][0]
    image.metadata['seed_range_max'] = conf_analysis['estimated_range'][1]
    image.metadata['overall_confidence'] = conf_analysis['overall_confidence']
    image.metadata['calculated_active'] = result['summary']['active_seeds']

    image.save(update_fields=['metadata'])

    return result


def bulk_calculate_run_seed_status(run_id: int):
    """Loops through all reference seeds in a run and calculates status for their images."""
    run = InferenceRun.objects.get(id=run_id)
    refs = run.reference_seeds or {}
    results = {}

    for image_id_str, ref_detection_id in refs.items():
        image_id = int(image_id_str)
        try:
            res = calculate_seed_status(ref_detection_id, image_id)
            results[image_id_str] = res
        except Exception as e:
            results[image_id_str] = {'error': str(e)}

    return results
