#!/usr/bin/env python3
"""Analyse YOLO vetted-set predictions against ground truth.

Uses the predictions already stored in vetted_predictions.json plus the
hand-drawn ground-truth labels to, without re-running the model:

  - match predictions to ground truth (greedy, IoU >= 0.5, per class),
  - draw an overlay per image colouring true positives, false positives,
    and (most importantly) false negatives,
  - dump cropped false negatives, the insects the model missed, into their
    own folder so the failure modes can be studied,
  - write a per-image summary CSV and print a confidence-threshold sweep.

The team's priority is minimising false negatives (a missed pollinator visit
cannot be recovered), so the false-negative crops are the main output. The
default confidence threshold is 0.05: a miss at 0.05 is a genuine miss, not a
confidence-threshold casualty.

No GPU, ultralytics, or SAHI required. Only Pillow.

Usage:
    python3 analyze_vetted.py
    python3 analyze_vetted.py --conf 0.20 --iou 0.5
    python3 analyze_vetted.py --classes fly      # restrict to one class
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from PIL import Image, ImageDraw

from paths import IMAGES, LABELS, OUT_DIR as _OUT_ROOT, VETTED_JSON

# CVAT export order (index in the .txt label files) and the subset the YOLO
# detector was trained on. GT lines use CVAT indices; predictions use names.
CVAT_CLASSES = ['bumblebee', 'fly', 'butterfly', 'other', 'unsure']
KEEP_CLASSES = ['fly', 'butterfly', 'other']

# Defaults resolved by paths.py (overridable per flag below).
PRED_JSON = VETTED_JSON
IMAGES_DIR = IMAGES
LABELS_DIR = LABELS
OUT_DIR = _OUT_ROOT / 'vetted_analysis'

# Overlay colours (RGB).
COLOR_TP = (0, 200, 0)      # correctly detected GT
COLOR_FP = (255, 140, 0)    # false alarm
COLOR_FN = (220, 0, 0)      # missed GT (the important one)


def iou(a: list, b: list) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    aa = (a[2] - a[0]) * (a[3] - a[1])
    bb = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (aa + bb - inter)


def load_gt(label_path: Path, img_w: int, img_h: int, keep: list) -> list:
    """Read a YOLO label file. Returns [(class_name, [x1,y1,x2,y2]), ...]
    keeping only classes in `keep`. Empty or missing file -> []."""
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
        if name not in keep:
            continue
        cx, cy, w, h = (float(v) for v in parts[1:5])
        x1 = (cx - w / 2) * img_w
        y1 = (cy - h / 2) * img_h
        x2 = (cx + w / 2) * img_w
        y2 = (cy + h / 2) * img_h
        out.append((name, [x1, y1, x2, y2]))
    return out


def match(preds: list, gts: list, iou_thr: float):
    """Greedy match predictions to GT, highest confidence first, per class.

    Returns (tp_pred_idxs, fp_pred_idxs, fn_gt_idxs, matched_pairs).
    """
    order = sorted(range(len(preds)), key=lambda i: -preds[i]['confidence'])
    matched_gt: set = set()
    tp, fp = [], []
    pairs = []
    for pi in order:
        p = preds[pi]
        pb = [p['x1'], p['y1'], p['x2'], p['y2']]
        best, best_gi = 0.0, None
        for gi, (gc, gb) in enumerate(gts):
            if gi in matched_gt or gc != p['class']:
                continue
            v = iou(pb, gb)
            if v > best:
                best, best_gi = v, gi
        if best_gi is not None and best >= iou_thr:
            tp.append(pi)
            matched_gt.add(best_gi)
            pairs.append((pi, best_gi))
        else:
            fp.append(pi)
    fn = [gi for gi in range(len(gts)) if gi not in matched_gt]
    return tp, fp, fn, pairs


def draw_overlay(img: Image.Image, preds: list, gts: list, tp, fp, fn) -> Image.Image:
    im = img.convert('RGB').copy()
    d = ImageDraw.Draw(im)
    # False positives first (thin), so they sit under the more important boxes.
    for pi in fp:
        p = preds[pi]
        d.rectangle([p['x1'], p['y1'], p['x2'], p['y2']], outline=COLOR_FP, width=2)
    # True positives.
    for pi in tp:
        p = preds[pi]
        d.rectangle([p['x1'], p['y1'], p['x2'], p['y2']], outline=COLOR_TP, width=3)
    # Missed GT, drawn last and thick so they stand out.
    for gi in fn:
        gc, gb = gts[gi]
        d.rectangle(gb, outline=COLOR_FN, width=4)
        d.text((gb[0], max(0, gb[1] - 12)), f'MISS:{gc}', fill=COLOR_FN)
    return im


def crop_fn(img: Image.Image, box: list, pad_frac: float = 0.6) -> Image.Image:
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    pad = int(max(w, h) * pad_frac)
    ix1 = max(0, int(x1) - pad)
    iy1 = max(0, int(y1) - pad)
    ix2 = min(img.width, int(x2) + pad)
    iy2 = min(img.height, int(y2) + pad)
    return img.convert('RGB').crop((ix1, iy1, ix2, iy2))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--pred', default=PRED_JSON)
    ap.add_argument('--images', default=IMAGES_DIR)
    ap.add_argument('--labels', default=LABELS_DIR)
    ap.add_argument('--out', default=OUT_DIR)
    ap.add_argument('--conf', type=float, default=0.05,
                    help='Confidence threshold for the overlays and FN crops.')
    ap.add_argument('--iou', type=float, default=0.5)
    ap.add_argument('--classes', nargs='+', default=KEEP_CLASSES,
                    help='Subset of classes to evaluate (default all kept).')
    ap.add_argument('--no-overlays', action='store_true',
                    help='Skip full-image overlays (faster; FN crops still written).')
    args = ap.parse_args()

    keep = list(args.classes)
    images_dir = Path(args.images)
    labels_dir = Path(args.labels)
    out_dir = Path(args.out)
    overlays_dir = out_dir / 'overlays'
    fn_dir = out_dir / 'false_negatives'
    fn_dir.mkdir(parents=True, exist_ok=True)
    if not args.no_overlays:
        overlays_dir.mkdir(parents=True, exist_ok=True)

    all_preds = json.loads(Path(args.pred).read_text())['predictions']

    # Per-image accounting at the chosen confidence threshold.
    rows = []
    totals = {c: {'tp': 0, 'fp': 0, 'fn': 0} for c in keep}
    fn_count = 0

    img_files = sorted(p for p in images_dir.iterdir()
                       if p.suffix.lower() in ('.jpg', '.jpeg', '.png'))
    for img_path in img_files:
        with Image.open(img_path) as im:
            iw, ih = im.size
            gts = load_gt(labels_dir / (img_path.stem + '.txt'), iw, ih, keep)
            preds = [p for p in all_preds.get(img_path.name, [])
                     if p['confidence'] >= args.conf and p['class'] in keep]
            tp, fp, fn, _ = match(preds, gts, args.iou)

            for c in keep:
                totals[c]['tp'] += sum(1 for i in tp if preds[i]['class'] == c)
                totals[c]['fp'] += sum(1 for i in fp if preds[i]['class'] == c)
                totals[c]['fn'] += sum(1 for gi in fn if gts[gi][0] == c)

            rows.append({
                'image': img_path.name,
                'n_gt': len(gts), 'n_pred': len(preds),
                'tp': len(tp), 'fp': len(fp), 'fn': len(fn),
            })

            # Dump each missed insect as its own crop for inspection.
            for gi in fn:
                gc, gb = gts[gi]
                crop = crop_fn(im, gb)
                crop.save(fn_dir / f'{img_path.stem}__{gc}__fn{gi}.jpg', 'JPEG', quality=90)
                fn_count += 1

            if not args.no_overlays and (tp or fp or fn):
                draw_overlay(im, preds, gts, tp, fp, fn).save(
                    overlays_dir / img_path.name)

    # Write per-image CSV.
    csv_path = out_dir / f'per_image_conf{args.conf}.csv'
    with open(csv_path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['image', 'n_gt', 'n_pred', 'tp', 'fp', 'fn'])
        w.writeheader()
        w.writerows(rows)

    # Aggregate at this threshold.
    print(f'\n=== Vetted analysis @ conf={args.conf}, IoU={args.iou} ===')
    print(f'images={len(img_files)}  classes={keep}')
    for c in keep:
        s = totals[c]
        p = s['tp'] / max(1, s['tp'] + s['fp'])
        r = s['tp'] / max(1, s['tp'] + s['fn'])
        f1 = 2 * p * r / max(1e-9, p + r)
        print(f'  {c:10s}  TP={s["tp"]:4d} FP={s["fp"]:5d} FN={s["fn"]:4d}  '
              f'P={p:.3f} R={r:.3f} F1={f1:.3f}')
    print(f'\nFalse-negative crops written: {fn_count} -> {fn_dir}/')
    if not args.no_overlays:
        print(f'Overlays written -> {overlays_dir}/')
    print(f'Per-image CSV -> {csv_path}')

    # Quick recall-vs-threshold sweep (recall is the metric the team cares about).
    print('\n=== Recall sweep (fly) ===')
    for t in (0.05, 0.10, 0.15, 0.20, 0.25, 0.30):
        tp = fp = fn = 0
        for img_path in img_files:
            with Image.open(img_path) as im:
                iw, ih = im.size
            gts = [g for g in load_gt(labels_dir / (img_path.stem + '.txt'), iw, ih, keep)
                   if g[0] == 'fly']
            preds = [p for p in all_preds.get(img_path.name, [])
                     if p['confidence'] >= t and p['class'] == 'fly']
            t_, f_, n_, _ = match(preds, gts, args.iou)
            tp += len(t_)
            fp += len(f_)
            fn += len(n_)
        r = tp / max(1, tp + fn)
        p = tp / max(1, tp + fp)
        print(f'  conf={t:.2f}  R={r:.3f}  P={p:.3f}  (TP={tp} FP={fp} FN={fn})')


if __name__ == '__main__':
    main()