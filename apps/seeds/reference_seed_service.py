from ml_pipelines.seed_src.utils.active_seed_calculator import (
    count_active_and_aborted_seeds,
)

from apps.analysis.models import Detection


def calculate_seed_status(reference_detection_id: int, image_id: int):


    reference = Detection.objects.get(id=reference_detection_id)

    detections = Detection.objects.filter(image_id=image_id)

    reference_poly = bbox_to_poly(reference.bbox)

    detected_polys = [
        bbox_to_poly(d.bbox)
        for d in detections
    ]

    result = count_active_and_aborted_seeds(
        reference_seed=reference_poly,
        detected_seeds=detected_polys,
        threshold=0.30,
    )

    # save back into DB
    detections.update(
        seed_status="unknown"
    )

    # assign labels based on result
    for d in detections:
        poly = bbox_to_poly(d.bbox)
        area = poly_area(poly)

        if area <= result_threshold(reference_poly):
            d.seed_status = "aborted"
        else:
            d.seed_status = "active"

        d.save()

    return result


def bbox_to_poly(bbox):
    x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]

    return [
        x1, y1,
        x2, y1,
        x2, y2,
        x1, y2
    ]