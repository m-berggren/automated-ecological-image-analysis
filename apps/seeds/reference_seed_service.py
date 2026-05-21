from ml_pipelines.seed_src.utils.active_seed_calculator import (
    count_active_and_aborted_seeds,
)

from apps.analysis.models import Detection


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
        d.seed_status = status_map.get(d.id, 'unknown')
        d.save()

    return result


