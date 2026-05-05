def get_iou(box1, box2):
    """Calculates Intersection over Union (IoU) between two boxes [x1, y1, x2, y2]"""
    x_left = max(box1[0], box2[0])
    y_top = max(box1[1], box2[1])
    x_right = min(box1[2], box2[2])
    y_bottom = min(box1[3], box2[3])

    if x_right < x_left or y_bottom < y_top:
        return 0.0

    intersection_area = (x_right - x_left) * (y_bottom - y_top)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    return intersection_area / float(area1 + area2 - intersection_area)

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
            iou = get_iou(p_box, g_box)
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