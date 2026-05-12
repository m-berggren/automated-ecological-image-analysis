"""
inference/merge.py
===================
IoU geometry helper and per-image merge logic for combining YOLO and
InsectNet detections into a single set of detection records.

When a YOLO bbox and a preprocessing bbox overlap above iou_threshold,
they are treated as the same physical insect: one record, source='both',
both labels recorded, YOLO's bbox kept. Class disagreements between the
two detectors are surfaced for downstream review (the frontend flags them).
"""

CLASSES = ['bumblebee', 'fly', 'butterfly', 'other']


def compute_iou(box_a: tuple, box_b: tuple) -> float:
    """IoU between two (x1, y1, x2, y2) bounding boxes."""
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def merge_per_image(
    yolo_dets: list,
    insect_dets: list,
    iou_threshold: float,
) -> tuple:
    """
    Merge YOLO and InsectNet detections per source image by IoU.

    Each detection in either list contributes one record. When a YOLO
    detection and an InsectNet detection overlap above the threshold,
    they merge into a single source='both' record using YOLO's bbox.

    Returns:
        (detections, by_class, by_source)
    """
    images = sorted(
        {d['image_name'] for d in yolo_dets} | {d['image_name'] for d in insect_dets}
    )

    detections = []
    detection_id = 0
    by_class = {c: 0 for c in CLASSES}
    by_source = {'yolo': 0, 'preprocessing': 0, 'both': 0}

    for img_name in images:
        y_dets = [d for d in yolo_dets if d['image_name'] == img_name]
        p_dets = [d for d in insect_dets if d['image_name'] == img_name]
        used_p = set()

        for y_det in y_dets:
            best_idx = None
            best_iou = iou_threshold
            for i, p_det in enumerate(p_dets):
                if i in used_p:
                    continue
                iou = compute_iou(y_det['bbox'], p_det['bbox'])
                if iou > best_iou:
                    best_iou = iou
                    best_idx = i

            detection_id += 1
            x1, y1, x2, y2 = y_det['bbox']

            if best_idx is not None:
                p_det = p_dets[best_idx]
                used_p.add(best_idx)
                detections.append(
                    {
                        'id': detection_id,
                        'image_name': img_name,
                        'datetime': p_det['datetime'],
                        'weather': p_det['weather'],
                        'source': 'both',
                        'bbox': {
                            'x1': x1,
                            'y1': y1,
                            'x2': x2,
                            'y2': y2,
                            'w': y_det['bbox_w'],
                            'h': y_det['bbox_h'],
                        },
                        'yolo_class': y_det['yolo_class'],
                        'yolo_confidence': round(y_det['yolo_confidence'], 4),
                        'insectnet_class': p_det['insectnet_class'],
                        'insectnet_confidence': round(p_det['insectnet_confidence'], 4),
                        'binary_confidence': round(p_det['binary_confidence'], 4),
                        'class_probs': {
                            k: round(v, 4) for k, v in p_det['class_probs'].items()
                        },
                        'merge_iou': round(best_iou, 4),
                        'yolo_crop': y_det['crop_path'],
                        'preprocessing_crop': p_det['crop_path'],
                    }
                )
                by_source['both'] += 1
                if y_det['yolo_class'] in by_class:
                    by_class[y_det['yolo_class']] += 1
            else:
                detections.append(
                    {
                        'id': detection_id,
                        'image_name': img_name,
                        'datetime': '',
                        'weather': '',
                        'source': 'yolo',
                        'bbox': {
                            'x1': x1,
                            'y1': y1,
                            'x2': x2,
                            'y2': y2,
                            'w': y_det['bbox_w'],
                            'h': y_det['bbox_h'],
                        },
                        'yolo_class': y_det['yolo_class'],
                        'yolo_confidence': round(y_det['yolo_confidence'], 4),
                        'insectnet_class': None,
                        'insectnet_confidence': None,
                        'binary_confidence': None,
                        'class_probs': None,
                        'merge_iou': None,
                        'yolo_crop': y_det['crop_path'],
                        'preprocessing_crop': None,
                    }
                )
                by_source['yolo'] += 1
                if y_det['yolo_class'] in by_class:
                    by_class[y_det['yolo_class']] += 1

        for i, p_det in enumerate(p_dets):
            if i in used_p:
                continue
            detection_id += 1
            x1, y1, x2, y2 = p_det['bbox']
            detections.append(
                {
                    'id': detection_id,
                    'image_name': img_name,
                    'datetime': p_det['datetime'],
                    'weather': p_det['weather'],
                    'source': 'preprocessing',
                    'bbox': {
                        'x1': x1,
                        'y1': y1,
                        'x2': x2,
                        'y2': y2,
                        'w': p_det['bbox_w'],
                        'h': p_det['bbox_h'],
                    },
                    'yolo_class': None,
                    'yolo_confidence': None,
                    'insectnet_class': p_det['insectnet_class'],
                    'insectnet_confidence': round(p_det['insectnet_confidence'], 4),
                    'binary_confidence': round(p_det['binary_confidence'], 4),
                    'class_probs': {
                        k: round(v, 4) for k, v in p_det['class_probs'].items()
                    },
                    'merge_iou': None,
                    'yolo_crop': None,
                    'preprocessing_crop': p_det['crop_path'],
                }
            )
            by_source['preprocessing'] += 1
            if p_det['insectnet_class'] in by_class:
                by_class[p_det['insectnet_class']] += 1

    return detections, by_class, by_source
