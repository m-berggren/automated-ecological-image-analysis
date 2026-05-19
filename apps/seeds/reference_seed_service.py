from ml_pipelines.seed_src.utils.active_seed_calculator import (
    count_active_and_aborted_seeds,
)

from apps.analysis.models import Detection


def calculate_seed_status(reference_detection_id: int, image_id: int):


    reference = Detection.objects.get(id=reference_detection_id)

    detections = list(Detection.objects.filter(image_id=image_id))

    reference_poly = reference.polygon

    detected_polys = [d.polygon for d in detections]

    result = count_active_and_aborted_seeds(
        reference_seed=reference_poly,
        detected_seeds=detected_polys,
        threshold=0.30,
    )

    ref_area = poly_area(reference_poly)
    active_threshold = ref_area * 0.30

    # save back into DB
    detections.update(
        seed_status="unknown"
    )

    # assign labels based on result
    for d in detections:
        area = poly_area(d.polygon)
        d.seed_status = "active" if area >= active_threshold else "aborted"
        d.save()

    return result

