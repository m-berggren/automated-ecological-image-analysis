#!/usr/bin/env python3
"""Sweep the YOLO confidence threshold on the stored combined-pipeline
predictions and emit the recall-vs-false-positive operating curve for flies.

Reuses the exact branch and greedy-IoU matching logic from
combined_pipeline_eval.py, but runs entirely on the per-plot results.json
vendored under predictions/ (no inference, no model). The binary gate is held
fixed; only the YOLO confidence threshold moves, since the sweep we found
earlier showed the YOLO threshold is the real lever and the binary gate barely
shifts recall.

Writes the operating-curve JSON (paths.OPERATING_CURVE_JSON) for the figure
script to read.
"""

from __future__ import annotations

import json
from collections import defaultdict

from PIL import Image

from paths import IMAGES, LABELS, OPERATING_CURVE_JSON, PRED_DIR, require

CVAT_CLASSES = ['bumblebee', 'fly', 'butterfly', 'other', 'unsure']
KEEP_CLASSES = ['fly', 'butterfly', 'other']
IMG_SUFFIXES = ('.jpg', '.jpeg', '.png')

BINARY_THR = 0.20
EVAL_IOU = 0.50
THRESHOLDS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]
# The crop branch responds to the binary gate, not the YOLO threshold, so it is
# swept over its own knob, across the same 0.05 to 0.50 range as the YOLO curves.
BINARY_THRESHOLDS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]


def iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    aa = (a[2] - a[0]) * (a[3] - a[1])
    bb = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (aa + bb - inter)


def load_gt(label_path, w, h):
    out = []
    if not label_path.exists():
        return out
    for line in label_path.read_text().splitlines():
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        idx = int(parts[0])
        if not 0 <= idx < len(CVAT_CLASSES):
            continue
        name = CVAT_CLASSES[idx]
        if name not in KEEP_CLASSES:
            continue
        cx, cy, bw, bh = (float(v) for v in parts[1:5])
        out.append(
            (
                name,
                [
                    (cx - bw / 2) * w,
                    (cy - bh / 2) * h,
                    (cx + bw / 2) * w,
                    (cy + bh / 2) * h,
                ],
            )
        )
    return out


def box(d):
    b = d['bbox']
    return [b['x1'], b['y1'], b['x2'], b['y2']]


def yolo_branch(d):
    if d['source'] in ('yolo', 'both') and d.get('yolo_class') is not None:
        return d['yolo_class'], float(d['yolo_confidence']), box(d)
    return None


def crop_branch(d):
    if (
        d['source'] in ('preprocessing', 'both')
        and d.get('insectnet_class') is not None
    ):
        conf = d.get('binary_confidence')
        return d['insectnet_class'], float(conf) if conf is not None else 1.0, box(d)
    return None


def combined(d, yt, bt):
    y, c = yolo_branch(d), crop_branch(d)
    keep_y = y is not None and y[1] >= yt
    keep_c = c is not None and c[1] >= bt
    if not (keep_y or keep_c):
        return None
    return y if keep_y else c


def fly_stats(dets_per_image, gt_per_image):
    tp = fp = fn = 0
    for img, gts in gt_per_image.items():
        preds = sorted(dets_per_image.get(img, []), key=lambda t: -t[1])
        matched = set()
        for cls, _conf, b in preds:
            if cls != 'fly':
                continue
            best, best_i = EVAL_IOU, None
            for i, (gc, gb) in enumerate(gts):
                if i in matched or gc != 'fly':
                    continue
                v = iou(b, gb)
                if v > best:
                    best, best_i = v, i
            if best_i is not None:
                tp += 1
                matched.add(best_i)
            else:
                fp += 1
        for i, (gc, _gb) in enumerate(gts):
            if i not in matched and gc == 'fly':
                fn += 1
    r = tp / max(1, tp + fn)
    p = tp / max(1, tp + fp)
    return {'tp': tp, 'fp': fp, 'fn': fn, 'recall': r, 'precision': p}


def main():
    require(PRED_DIR, 'prediction directory')
    require(IMAGES, 'vetted images')

    all_dets = []
    for rj in sorted(PRED_DIR.glob('*_results.json')):
        all_dets.extend(json.loads(rj.read_text()).get('detections', []))

    gt_per_image = {}
    for p in sorted(IMAGES.iterdir()):
        if p.suffix.lower() not in IMG_SUFFIXES:
            continue
        with Image.open(p) as im:
            w, h = im.size
        gt_per_image[p.name] = load_gt(LABELS / (p.stem + '.txt'), w, h)

    n_fly = sum(1 for v in gt_per_image.values() for c, _ in v if c == 'fly')

    rows = []
    for t in THRESHOLDS:
        comb = defaultdict(list)
        yolo = defaultdict(list)
        for d in all_dets:
            cb = combined(d, t, BINARY_THR)
            if cb is not None:
                comb[d['image_name']].append(cb)
            y = yolo_branch(d)
            if y is not None and y[1] >= t:
                yolo[d['image_name']].append(y)
        rows.append(
            {
                'yolo_conf': t,
                'combined': fly_stats(comb, gt_per_image),
                'yolo_only': fly_stats(yolo, gt_per_image),
            }
        )

    crop_rows = []
    for bt in BINARY_THRESHOLDS:
        crop = defaultdict(list)
        for d in all_dets:
            c = crop_branch(d)
            if c is not None and c[1] >= bt:
                crop[d['image_name']].append(c)
        crop_rows.append({'binary_thr': bt, 'crop_only': fly_stats(crop, gt_per_image)})

    out = {
        'n_fly': n_fly,
        'binary_thr': BINARY_THR,
        'eval_iou': EVAL_IOU,
        'rows': rows,
        'crop_rows': crop_rows,
    }
    OPERATING_CURVE_JSON.write_text(json.dumps(out, indent=2))
    print(f'flies (GT) = {n_fly}')
    print(f'{"thr":>5} | {"comb R":>7} {"comb FP":>8} | {"yolo R":>7} {"yolo FP":>8}')
    for r in rows:
        c, y = r['combined'], r['yolo_only']
        print(
            f'{r["yolo_conf"]:5.2f} | {c["recall"]:7.3f} {c["fp"]:8d} | '
            f'{y["recall"]:7.3f} {y["fp"]:8d}'
        )
    print('crop-only (sweep binary gate):')
    for r in crop_rows:
        s = r['crop_only']
        print(f'{r["binary_thr"]:5.2f} | {s["recall"]:7.3f} {s["fp"]:8d}')


if __name__ == '__main__':
    main()
