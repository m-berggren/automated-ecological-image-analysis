#!/usr/bin/env python3
"""Build a single-frame qualitative panel for the combined pipeline on the
vetted field set.

Rather than collecting crops from many images, this takes one field frame and
shows every annotated fly in it, coloured by outcome at the deployed operating
point (YOLO 0.20, binary gate 0.20): green if the pipeline detected it, red if
it was missed. The establishing frame is shown on top with all flies boxed and
numbered, and each fly is zoomed below with its pixel size and outcome.

One frame cannot contain every failure mode, but tying the examples to a single
scene shows concretely what the pipeline catches and misses on a real image.

Set TARGET to a specific filename to override the automatic frame choice. The
auto choice prefers a busy frame with a balanced mix of hits and misses.

Writes yolo_failure_panel.png into paths.OUT_DIR. Needs only PIL + matplotlib.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from PIL import Image

from paths import IMAGES, LABELS, OUT_DIR as OUT, PRED_DIR

CVAT_CLASSES = ['bumblebee', 'fly', 'butterfly', 'other', 'unsure']
IMG_SUFFIXES = ('.jpg', '.jpeg', '.png')

YOLO_THR, BIN_THR, EVAL_IOU = 0.20, 0.20, 0.50
TARGET = None  # e.g. 'dryo_WSCT0001.JPG' to force a specific frame
MAX_COLS = 4

HIT, MISS = '#2c7a3f', '#cc3333'


def iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    return inter / (
        (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    )


def load_gt_fly(label_path, w, h):
    out = []
    if not label_path.exists():
        return out
    for line in label_path.read_text().splitlines():
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        idx = int(parts[0])
        if not 0 <= idx < len(CVAT_CLASSES) or CVAT_CLASSES[idx] != 'fly':
            continue
        cx, cy, bw, bh = (float(v) for v in parts[1:5])
        out.append(
            [(cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h]
        )
    return out


def combined_fly_boxes(dets):
    out = defaultdict(list)
    for d in dets:
        b = d['bbox']
        box = [b['x1'], b['y1'], b['x2'], b['y2']]
        keep_y = (
            d['source'] in ('yolo', 'both')
            and d.get('yolo_class') == 'fly'
            and float(d.get('yolo_confidence') or 0) >= YOLO_THR
        )
        bc = d.get('binary_confidence')
        keep_c = (
            d['source'] in ('preprocessing', 'both')
            and d.get('insectnet_class') == 'fly'
            and (float(bc) if bc is not None else 1.0) >= BIN_THR
        )
        if keep_y or keep_c:
            out[d['image_name']].append(box)
    return out


def flies_with_outcome(path, comb):
    """Return [(gt_box, detected_bool), ...] left-to-right for one image."""
    with Image.open(path) as im:
        w, h = im.size
    gts = load_gt_fly(LABELS / (path.stem + '.txt'), w, h)
    preds = list(comb.get(path.name, []))
    matched = set()
    res = []
    for gb in gts:
        hit = False
        for pi, pb in enumerate(preds):
            if pi in matched:
                continue
            if iou(gb, pb) >= EVAL_IOU:
                matched.add(pi)
                hit = True
                break
        res.append((gb, hit))
    res.sort(key=lambda t: t[0][0])
    return res, (w, h)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    all_dets = []
    for rj in sorted(PRED_DIR.glob('*_results.json')):
        all_dets.extend(json.loads(rj.read_text()).get('detections', []))
    comb = combined_fly_boxes(all_dets)
    name_to_path = {
        p.name: p for p in IMAGES.iterdir() if p.suffix.lower() in IMG_SUFFIXES
    }

    if TARGET:
        chosen = name_to_path[TARGET]
        flies, (W, H) = flies_with_outcome(chosen, comb)
    else:
        best, best_score = None, None
        for name, path in name_to_path.items():
            flies, dims = flies_with_outcome(path, comb)
            if len(flies) < 3:
                continue
            hits = sum(h for _, h in flies)
            miss = len(flies) - hits
            # Prefer a balanced mix, then a busy frame.
            score = (min(hits, miss), len(flies))
            if best_score is None or score > best_score:
                best, best_score, best_flies, best_dims = name, score, flies, dims
        chosen = name_to_path[best]
        flies, (W, H) = best_flies, best_dims

    n = len(flies)
    hits = sum(h for _, h in flies)
    print(f'chosen frame: {chosen.name}  {n} flies, {hits} detected, {n - hits} missed')

    ncol = min(MAX_COLS, n)
    nrow = math.ceil(n / ncol)
    fig = plt.figure(figsize=(7.4, 3.0 + 2.0 * nrow))
    gs = fig.add_gridspec(
        1 + nrow, ncol, height_ratios=[1.8] + [1] * nrow, hspace=0.30, wspace=0.06
    )

    ax0 = fig.add_subplot(gs[0, :])
    with Image.open(chosen) as im:
        ax0.imshow(im)
    for i, (gb, hit) in enumerate(flies, 1):
        c = HIT if hit else MISS
        bw, bh = gb[2] - gb[0], gb[3] - gb[1]
        pad = max(W, H) * 0.012
        ax0.add_patch(
            Rectangle(
                (gb[0] - pad, gb[1] - pad),
                bw + 2 * pad,
                bh + 2 * pad,
                fill=False,
                edgecolor=c,
                lw=1.6,
            )
        )
        ax0.text(
            gb[0] - pad,
            gb[1] - pad - max(W, H) * 0.012,
            str(i),
            color='white',
            fontsize=9,
            ha='left',
            va='bottom',
            bbox=dict(boxstyle='circle,pad=0.15', fc=c, ec='none'),
        )
    ax0.set_title(
        f'{chosen.name}: {n} annotated flies, '
        f'{hits} detected (green), {n - hits} missed (red)',
        fontsize=9.5,
    )
    ax0.axis('off')

    for i, (gb, hit) in enumerate(flies):
        ax = fig.add_subplot(gs[1 + i // ncol, i % ncol])
        c = HIT if hit else MISS
        bw, bh = gb[2] - gb[0], gb[3] - gb[1]
        with Image.open(chosen) as im:
            side = max(180, max(bw, bh) * 4)
            cx, cy = (gb[0] + gb[2]) / 2, (gb[1] + gb[3]) / 2
            x0 = max(0, min(W - side, cx - side / 2))
            y0 = max(0, min(H - side, cy - side / 2))
            crop = im.crop((int(x0), int(y0), int(x0 + side), int(y0 + side)))
            ax.imshow(crop)
        ax.add_patch(
            Rectangle((gb[0] - x0, gb[1] - y0), bw, bh, fill=False, edgecolor=c, lw=1.6)
        )
        tag = 'detected' if hit else 'missed'
        ax.set_title(f'{i + 1}. {tag}, {int(bw)} x {int(bh)} px', fontsize=8.5, color=c)
        ax.set_xticks([])
        ax.set_yticks([])

    # Hide any unused trailing cells.
    for j in range(n, nrow * ncol):
        fig.add_subplot(gs[1 + j // ncol, j % ncol]).axis('off')

    p = OUT / 'yolo_failure_panel.png'
    fig.savefig(p, dpi=200, bbox_inches='tight')
    print(f'wrote {p}')


if __name__ == '__main__':
    main()
