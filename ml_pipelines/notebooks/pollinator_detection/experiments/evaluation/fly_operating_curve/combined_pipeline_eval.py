#!/usr/bin/env python3
"""Combined-pipeline evaluation on the vetted field set.

Runs the REAL pollinator inference pipeline
(``pollinator.workflows.inference``) per camera plot, then matches the merged
YOLO + crop-classifier detections against ground truth to compare three
configurations on the same images:

  - YOLO branch only          (detections with a YOLO box)
  - crop-based branch only     (detections from background subtraction + InsectNet)
  - combined                   (the union, exactly what the deployed tool produces)

The point is to show whether combining the two branches recovers insects that
either branch alone misses, since recall (not precision) is the binding metric:
a missed pollinator cannot be recovered downstream, while a false positive is
discarded at the review step.

This script does NOT reimplement inference. It invokes the pipeline's own CLI
(``python -m pollinator.workflows.inference``) as a subprocess and consumes the
genuine results.json it writes. Inference is run once per plot because the crop
branch builds a median background from each run's frames, so mixing plots in one
run would corrupt that background.

Run from inside the pipeline's environment. Image, label, output and
pipeline-root paths default via paths.py, so only the model checkpoints are
required:

    uv run python combined_pipeline_eval.py \
        --yolo-model  /path/to/best.pt \
        --binary-model /path/to/efficientnet_binary_best.pth \
        --group-model  /path/to/group_insectnet_best.pth \
        --plots dia dryo

Re-running evaluation only (skip the slow inference) once the per-plot
results.json files exist:

    uv run python combined_pipeline_eval.py ... --skip-inference
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from PIL import Image

from paths import IMAGES, LABELS, PRED_DIR

# This folder lives at ml_pipelines/notebooks/pollinator_detection/experiments/
# evaluation/fly_operating_curve, so ml_pipelines is five parents up.
PIPELINE_ROOT = Path(__file__).resolve().parents[4]

CVAT_CLASSES = ['bumblebee', 'fly', 'butterfly', 'other', 'unsure']
KEEP_CLASSES = ['fly', 'butterfly', 'other']
IMG_SUFFIXES = ('.jpg', '.jpeg', '.png')


# ── ground truth ────────────────────────────────────────────────────────────
def load_gt(label_path: Path, img_w: int, img_h: int, keep: list) -> list:
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
        out.append(
            (
                name,
                [
                    (cx - w / 2) * img_w,
                    (cy - h / 2) * img_h,
                    (cx + w / 2) * img_w,
                    (cy + h / 2) * img_h,
                ],
            )
        )
    return out


def iou(a: list, b: list) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    aa = (a[2] - a[0]) * (a[3] - a[1])
    bb = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (aa + bb - inter)


# ── plot grouping + inference ────────────────────────────────────────────────
def plot_of(stem: str) -> str:
    """Plot key from a filename stem. 'dia_WSCT0001' -> 'dia'."""
    return stem.split('_', 1)[0]


def group_by_plot(images_dir: Path, only: list) -> dict:
    groups: dict = defaultdict(list)
    for p in sorted(images_dir.iterdir()):
        if p.suffix.lower() not in IMG_SUFFIXES:
            continue
        key = plot_of(p.stem)
        if only and key not in only:
            continue
        groups[key].append(p)
    return groups


def run_pipeline_for_plot(plot: str, paths: list, args, out_json: Path) -> None:
    """Symlink one plot's images into a temp dir and invoke the pipeline CLI on it."""
    with tempfile.TemporaryDirectory(prefix=f'pollin_{plot}_') as tmp:
        tmp_dir = Path(tmp)
        for p in paths:
            (tmp_dir / p.name).symlink_to(p.resolve())
        cmd = [
            sys.executable,
            '-m',
            'pollinator.workflows.inference',
            '--image_dir',
            str(tmp_dir),
            '--output_json',
            str(out_json),
            '--yolo_model',
            str(Path(args.yolo_model).resolve()),
            '--binary_model',
            str(Path(args.binary_model).resolve()),
            '--group_model',
            str(Path(args.group_model).resolve()),
            '--yolo_confidence',
            str(args.infer_yolo_conf),
            '--yolo_slice_size',
            str(args.slice_size),
            '--yolo_overlap',
            str(args.overlap),
            '--binary_threshold',
            str(args.infer_binary_thr),
            '--iou_threshold',
            str(args.merge_iou),
        ]
        env = dict(os.environ, PYTHONPATH=str(Path(args.pipeline_root).resolve()))
        print(f'[infer] plot={plot} ({len(paths)} images) -> {out_json}')
        subprocess.run(cmd, env=env, check=True)


# ── branch extraction ────────────────────────────────────────────────────────
def detection_to_box(d: dict) -> list:
    b = d['bbox']
    return [b['x1'], b['y1'], b['x2'], b['y2']]


def yolo_branch(d: dict):
    """Return (class, conf, box) if this record has a YOLO detection, else None."""
    if d['source'] in ('yolo', 'both') and d.get('yolo_class') is not None:
        return d['yolo_class'], float(d['yolo_confidence']), detection_to_box(d)
    return None


def crop_branch(d: dict):
    """Return (class, conf, box) if this record has a crop detection, else None.
    Confidence is the binary insect/background gate score."""
    if (
        d['source'] in ('preprocessing', 'both')
        and d.get('insectnet_class') is not None
    ):
        conf = d.get('binary_confidence')
        conf = float(conf) if conf is not None else 1.0
        return d['insectnet_class'], conf, detection_to_box(d)
    return None


def combined_branch(d: dict, yolo_thr: float, bin_thr: float):
    """A combined detection survives if either branch passes its threshold.
    Class follows YOLO when present (the merge gives YOLO the bbox), else InsectNet."""
    y = yolo_branch(d)
    c = crop_branch(d)
    keep_y = y is not None and y[1] >= yolo_thr
    keep_c = c is not None and c[1] >= bin_thr
    if not (keep_y or keep_c):
        return None
    if keep_y:
        return y[0], y[1], y[2]
    return c[0], c[1], c[2]


# ── matching ─────────────────────────────────────────────────────────────────
def evaluate(
    dets_per_image: dict, gt_per_image: dict, iou_thr: float, classes: list
) -> dict:
    """dets_per_image: {image_name: [(class, conf, box), ...]}. Greedy IoU match per class."""
    stats = {c: {'tp': 0, 'fp': 0, 'fn': 0} for c in classes}
    for img_name, gts in gt_per_image.items():
        preds = sorted(dets_per_image.get(img_name, []), key=lambda t: -t[1])
        matched = set()
        for cls, _conf, box in preds:
            if cls not in stats:
                continue
            best, best_i = iou_thr, None
            for i, (gc, gb) in enumerate(gts):
                if i in matched or gc != cls:
                    continue
                v = iou(box, gb)
                if v > best:
                    best, best_i = v, i
            if best_i is not None:
                stats[cls]['tp'] += 1
                matched.add(best_i)
            else:
                stats[cls]['fp'] += 1
        for i, (gc, _gb) in enumerate(gts):
            if i not in matched and gc in stats:
                stats[gc]['fn'] += 1
    out = {}
    for c, s in stats.items():
        tp, fp, fn = s['tp'], s['fp'], s['fn']
        p = tp / max(1, tp + fp)
        r = tp / max(1, tp + fn)
        out[c] = {**s, 'precision': p, 'recall': r, 'f1': 2 * p * r / max(1e-9, p + r)}
    return out


def print_block(title: str, res: dict, classes: list) -> None:
    print(f'\n{title}')
    for c in classes:
        s = res[c]
        if s['tp'] + s['fp'] + s['fn'] == 0:
            continue
        print(
            f'  {c:10s} TP={s["tp"]:4d} FP={s["fp"]:5d} FN={s["fn"]:4d}  '
            f'R={s["recall"]:.3f} P={s["precision"]:.3f} F1={s["f1"]:.3f}'
        )


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        '--pipeline-root',
        default=PIPELINE_ROOT,
        help='Path to ml_pipelines (so pollinator.* is importable).',
    )
    ap.add_argument('--images', default=IMAGES)
    ap.add_argument('--labels', default=LABELS)
    ap.add_argument('--yolo-model', required=True)
    ap.add_argument('--binary-model', required=True)
    ap.add_argument('--group-model', required=True)
    ap.add_argument('--out', default=PRED_DIR)
    ap.add_argument(
        '--plots',
        nargs='*',
        default=[],
        help='Restrict to these plot prefixes (default: all found).',
    )
    # Inference-time thresholds: keep low to capture every candidate, then sweep in post.
    ap.add_argument('--infer-yolo-conf', type=float, default=0.05)
    ap.add_argument('--infer-binary-thr', type=float, default=0.05)
    ap.add_argument('--slice-size', type=int, default=640)
    ap.add_argument('--overlap', type=float, default=0.2)
    ap.add_argument('--merge-iou', type=float, default=0.3)
    # Evaluation-time operating point and matching.
    ap.add_argument('--op-yolo-conf', type=float, default=0.20)
    ap.add_argument('--op-binary-thr', type=float, default=0.50)
    ap.add_argument('--eval-iou', type=float, default=0.5)
    ap.add_argument(
        '--skip-inference',
        action='store_true',
        help='Reuse existing per-plot results.json under --out.',
    )
    args = ap.parse_args()

    images_dir = Path(args.images)
    labels_dir = Path(args.labels)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    groups = group_by_plot(images_dir, args.plots)
    if not groups:
        sys.exit('No images found for the requested plots.')
    print(f'Plots: {", ".join(f"{k}({len(v)})" for k, v in groups.items())}')

    # 1. Run the real pipeline per plot (or reuse).
    results_files = {}
    for plot, paths in groups.items():
        rj = out_dir / f'{plot}_results.json'
        results_files[plot] = rj
        if args.skip_inference and rj.exists():
            print(f'[infer] plot={plot}: reusing {rj}')
            continue
        run_pipeline_for_plot(plot, paths, args, rj)

    # 2. Collect detections per image from all plots.
    all_dets = []
    for rj in results_files.values():
        all_dets.extend(json.loads(rj.read_text()).get('detections', []))

    # 3. Ground truth (one pass over images for dimensions).
    gt_per_image = {}
    for plot, paths in groups.items():
        for p in paths:
            with Image.open(p) as im:
                w, h = im.size
            gt_per_image[p.name] = load_gt(
                labels_dir / (p.stem + '.txt'), w, h, KEEP_CLASSES
            )

    # 4. Build per-branch detections at the operating point.
    yolo_dets, crop_dets, comb_dets = (
        defaultdict(list),
        defaultdict(list),
        defaultdict(list),
    )
    for d in all_dets:
        name = d['image_name']
        y = yolo_branch(d)
        if y is not None and y[1] >= args.op_yolo_conf:
            yolo_dets[name].append(y)
        c = crop_branch(d)
        if c is not None and c[1] >= args.op_binary_thr:
            crop_dets[name].append(c)
        cb = combined_branch(d, args.op_yolo_conf, args.op_binary_thr)
        if cb is not None:
            comb_dets[name].append(cb)

    n_gt = sum(len(v) for v in gt_per_image.values())
    gt_by_class = defaultdict(int)
    for v in gt_per_image.values():
        for cls, _ in v:
            gt_by_class[cls] += 1
    print(f'\nGround truth: {n_gt} boxes  {dict(gt_by_class)}')
    print(
        f'Operating point: yolo_conf>={args.op_yolo_conf}, '
        f'binary>={args.op_binary_thr}, match IoU>={args.eval_iou}'
    )

    print_block(
        'YOLO branch only:',
        evaluate(yolo_dets, gt_per_image, args.eval_iou, KEEP_CLASSES),
        KEEP_CLASSES,
    )
    print_block(
        'Crop branch only:',
        evaluate(crop_dets, gt_per_image, args.eval_iou, KEEP_CLASSES),
        KEEP_CLASSES,
    )
    print_block(
        'Combined (deployed):',
        evaluate(comb_dets, gt_per_image, args.eval_iou, KEEP_CLASSES),
        KEEP_CLASSES,
    )

    # 5. Combined recall sweep over the YOLO threshold (binary held at the operating value).
    print('\nCombined recall sweep (binary held at operating value):')
    for t in (0.05, 0.10, 0.15, 0.20, 0.25, 0.30):
        sweep = defaultdict(list)
        for d in all_dets:
            cb = combined_branch(d, t, args.op_binary_thr)
            if cb is not None:
                sweep[d['image_name']].append(cb)
        res = evaluate(sweep, gt_per_image, args.eval_iou, KEEP_CLASSES)
        fly = res['fly']
        print(
            f'  yolo_conf={t:.2f}  fly R={fly["recall"]:.3f} P={fly["precision"]:.3f} '
            f'(TP={fly["tp"]} FP={fly["fp"]} FN={fly["fn"]})'
        )

    summary_path = out_dir / 'combined_eval_summary.json'
    summary_path.write_text(
        json.dumps(
            {
                'gt_by_class': dict(gt_by_class),
                'operating_point': {
                    'yolo_conf': args.op_yolo_conf,
                    'binary_thr': args.op_binary_thr,
                    'eval_iou': args.eval_iou,
                },
                'yolo_only': evaluate(
                    yolo_dets, gt_per_image, args.eval_iou, KEEP_CLASSES
                ),
                'crop_only': evaluate(
                    crop_dets, gt_per_image, args.eval_iou, KEEP_CLASSES
                ),
                'combined': evaluate(
                    comb_dets, gt_per_image, args.eval_iou, KEEP_CLASSES
                ),
            },
            indent=2,
        )
    )
    print(f'\nWrote {summary_path}')


if __name__ == '__main__':
    main()
