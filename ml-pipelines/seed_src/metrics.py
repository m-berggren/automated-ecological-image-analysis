from shapely.geometry import Polygon


def get_iou(box1, box2):
    """
    Calculates IoU for OBB [x1, y1, x2, y2, x3, y3, x4, y4].
    """
    if len(box1) != 8 or len(box2) != 8:
        return 0.0  # Fallback to 4-point HBB

    # Convert flat list to list of tuples [(x1, y1), (x2, y2)...]
    poly1 = Polygon([(box1[i], box1[i + 1]) for i in range(0, 8, 2)])
    poly2 = Polygon([(box2[i], box2[i + 1]) for i in range(0, 8, 2)])

    if not poly1.is_valid or not poly2.is_valid:
        poly1 = poly1.buffer(0)
        poly2 = poly2.buffer(0)

    intersection = poly1.intersection(poly2).area
    union = poly1.area + poly2.area - intersection

    return intersection / union if union > 0 else 0.0


def calculate_tp_fp_fn(preds, gts, iou_threshold=0.5):
    """Matches predictions to ground truth to find TP, FP, and FN"""
    tp = 0
    fp = 0
    matched_gt_indices = set()

    for p_box in preds:
        best_iou = 0
        best_gt_idx = -1

        for i, g_box in enumerate(gts):
            if i in matched_gt_indices:
                continue
            iou = get_iou(p_box["poly"], g_box)
            if iou > best_iou:
                best_iou = iou
                best_gt_idx = i

        if best_iou >= iou_threshold:
            tp += 1
            matched_gt_indices.add(best_gt_idx)
        else:
            fp += 1

    fn = len(gts) - len(matched_gt_indices)
    return tp, fp, fn
