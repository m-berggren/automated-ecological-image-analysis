from ml_pipelines.seed_src.utils.active_seed_calculator import (
    count_active_and_aborted_seeds,
)

from apps.analysis.models import Detection, InferenceRun


def calculate_seed_status(reference_detection_id: int, image_id: int):
    reference = Detection.objects.get(id=reference_detection_id)
    detections = list(Detection.objects.filter(image_id=image_id))
    reference_poly = reference.polygon

    detected_seeds = [
        {'poly': d.polygon, 'id': d.id}
        for d in detections
    ]

    result = count_active_and_aborted_seeds(
        reference_seed=reference_poly,
        detected_seeds=detected_seeds,
        threshold=0.30,
    )

    status_map = {c['detection_id']: c['status'] for c in result['classifications']}
    for d in detections:
        status = status_map.get(d.id, 'unknown')
        d.seed_status = status
        d.predicted_class = status
        d.save(update_fields=['seed_status', 'predicted_class'])

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
            results[image_id_str] = {"error": str(e)}

    return results
