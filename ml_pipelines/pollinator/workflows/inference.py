"""Per-image pollinator inference.

The pipeline is exposed as a class with one stateful step per source image,
so the Django worker can checkpoint to the database after every image and
react to pause/cancel signals between iterations.

Per image:
    1. YOLO (SAHI-tiled) over the full frame.
    2. Background-subtraction motion candidates against the previous frame.
    3. Binary insect/background gate on each motion candidate.
    4. Group classifier on the survivors.
    5. IoU merge of the YOLO and InsectNet detections for that frame.

The driver loop and per-image checkpointing live in
``apps/pollinator/services.py``. This module produces neither intermediate
JSON nor CSV; results flow back through ``process_image`` return values.
The ``__main__`` CLI at the bottom of the file is a standalone alternative
for offline / researcher use and writes a single results.json on completion.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, Union

import cv2
import numpy as np
from PIL import Image

from ..classification import BinaryClassifier, GroupClassifier
from ..detection import YoloDetector
from ..preprocessing.background import (
    StaticFilter,
    compute_global_background,
    detect_foreground,
    filter_contours,
)
from ..preprocessing.config import DEFAULT_CONFIG
from ..preprocessing.exif import get_exif_datetime, get_exif_metadata
from ..preprocessing.roi import is_in_roi, setup_zone

logger = logging.getLogger(__name__)

CLASSES = ['bumblebee', 'fly', 'butterfly', 'other']
IMG_SUFFIXES = ('.jpg', '.jpeg', '.png', '.JPG', '.JPEG')


def list_images(folder: Union[str, Path]) -> list[Path]:
    """Sorted image paths from a folder.

    Order is EXIF datetime first, then a numeric suffix in the filename,
    then filename string. Stable across reruns so resume offsets stay
    meaningful.
    """
    folder = Path(folder)
    paths = [p for p in folder.iterdir() if p.suffix in IMG_SUFFIXES]
    return sorted(paths, key=_robust_sort_key)


def _robust_sort_key(p: Path) -> tuple:
    dt = get_exif_datetime(str(p))
    if dt is not None:
        return (0, dt, p.name)
    m = re.search(r'(\d+)', p.stem)
    if m:
        return (1, int(m.group(1)), p.name)
    return (2, p.name)


def _seconds_between(a: tuple, b: tuple) -> float:
    return abs((datetime(*b) - datetime(*a)).total_seconds())


def _compute_iou(box_a: tuple, box_b: tuple) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    iw = max(0, min(ax2, bx2) - max(ax1, bx1))
    ih = max(0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _merge_image_detections(
    image_name: str,
    yolo_dets: list[dict],
    insect_dets: list[dict],
    iou_threshold: float,
) -> list[dict]:
    """Merge one image's YOLO + InsectNet detections by IoU.

    YOLO bbox wins on overlap (the detector was trained on this geometry).
    Class labels from both branches are preserved on source='both' rows so
    the review UI can flag disagreement.
    """
    merged: list[dict] = []
    used = set()
    for y in yolo_dets:
        best_idx, best_iou = None, iou_threshold
        for i, p in enumerate(insect_dets):
            if i in used:
                continue
            iou = _compute_iou(y['bbox'], p['bbox'])
            if iou > best_iou:
                best_idx, best_iou = i, iou
        x1, y1, x2, y2 = y['bbox']
        record = {
            'image_name': image_name,
            'bbox': {
                'x1': x1,
                'y1': y1,
                'x2': x2,
                'y2': y2,
                'w': y['bbox_w'],
                'h': y['bbox_h'],
            },
            'yolo_class': y['yolo_class'],
            'yolo_confidence': round(y['yolo_confidence'], 4),
        }
        if best_idx is None:
            record.update(
                {
                    'source': 'yolo',
                    'insectnet_class': None,
                    'insectnet_confidence': None,
                    'binary_confidence': None,
                    'class_probs': None,
                    'merge_iou': None,
                }
            )
        else:
            p = insect_dets[best_idx]
            used.add(best_idx)
            record.update(
                {
                    'source': 'both',
                    'insectnet_class': p['insectnet_class'],
                    'insectnet_confidence': round(p['insectnet_confidence'], 4),
                    'binary_confidence': round(p['binary_confidence'], 4),
                    'class_probs': {
                        k: round(v, 4) for k, v in (p['class_probs'] or {}).items()
                    },
                    'merge_iou': round(best_iou, 4),
                }
            )
        merged.append(record)

    for i, p in enumerate(insect_dets):
        if i in used:
            continue
        x1, y1, x2, y2 = p['bbox']
        merged.append(
            {
                'image_name': image_name,
                'bbox': {
                    'x1': x1,
                    'y1': y1,
                    'x2': x2,
                    'y2': y2,
                    'w': p['bbox_w'],
                    'h': p['bbox_h'],
                },
                'source': 'preprocessing',
                'yolo_class': None,
                'yolo_confidence': None,
                'insectnet_class': p['insectnet_class'],
                'insectnet_confidence': round(p['insectnet_confidence'], 4),
                'binary_confidence': round(p['binary_confidence'], 4),
                'class_probs': {
                    k: round(v, 4) for k, v in (p['class_probs'] or {}).items()
                },
                'merge_iou': None,
            }
        )
    return merged


class PollinatorInferencePipeline:  # pragma: no cover
    """Stateful pollinator pipeline driven one image at a time.

    Construction loads the three models and caches the merged config. Call
    :meth:`prime` once with the full image list (used to sample the global
    background) before iterating. Then call :meth:`process_image` for each
    source image; it returns the merged detection records for that frame.

    The pipeline keeps the previous frame as the background reference for
    the next image. EXIF time gaps beyond ``cfg['max_gap_seconds']`` clear
    the reference so a new sub-sequence starts fresh.
    """

    def __init__(
        self,
        *,
        yolo_model: str,
        binary_model: str,
        group_model: str,
        yolo_confidence: float,
        yolo_slice_size: int,
        yolo_overlap: float,
        binary_threshold: float,
        group_threshold: float,
        iou_threshold: float,
        config: Optional[dict] = None,
        device: Optional[str] = None,
    ) -> None:
        self.cfg = {**DEFAULT_CONFIG, **(config or {})}
        self.binary_threshold = binary_threshold
        self.group_threshold = group_threshold
        self.iou_threshold = iou_threshold
        self.max_gap_sec = float(self.cfg.get('max_gap_seconds', 3600))

        self.yolo = YoloDetector(
            yolo_model,
            confidence=yolo_confidence,
            device=device,
            slice_size=yolo_slice_size,
            overlap=yolo_overlap,
        )
        self.binary = BinaryClassifier(binary_model, device=device)
        self.group = GroupClassifier(group_model, device=device)

        self.global_bg: Optional[np.ndarray] = None
        self.prev_frame: Optional[np.ndarray] = None
        self.prev_dt: Optional[tuple] = None
        self.static_filter = (
            StaticFilter(self.cfg) if self.cfg.get('enable_static_filter') else None
        )

    def prime(self, image_paths: Iterable[Path]) -> None:
        """Sample the global background once before the per-image loop."""
        self.global_bg = compute_global_background(list(image_paths), self.cfg)

    def process_image(self, img_path: Path) -> list[dict]:
        """Return merged detection records for one source image.

        An unreadable image, an EXIF skip (flash/fog), or a missing
        background reference returns an empty list and still updates
        internal state so the next image has a usable reference.
        """
        img = cv2.imread(str(img_path))
        if img is None:
            logger.warning(f'Could not read {img_path}')
            return []

        cur_dt = get_exif_datetime(str(img_path))
        if (
            self.prev_dt is not None
            and cur_dt is not None
            and _seconds_between(self.prev_dt, cur_dt) > self.max_gap_sec
        ):
            self.prev_frame = None
        if cur_dt is not None:
            self.prev_dt = cur_dt

        # Zone is built on the original frame so YOLO's bboxes (un-stripped
        # coords from the on-disk image) align with the mask. The motion
        # branch operates on the stripped image, so it gets a
        # correspondingly-stripped slice of the same zone.
        zone_full = setup_zone(img, self.cfg)

        sh = self.cfg.get('strip_height', 0)
        if sh and img.shape[0] > sh:
            img = img[: img.shape[0] - sh]
            zone_motion = zone_full[: zone_full.shape[0] - sh]
        else:
            zone_motion = zone_full

        meta = get_exif_metadata(str(img_path), self.cfg)

        # skip_flash / skip_foggy skip the frame entirely: no YOLO and no
        # motion branch. prev_frame is still refreshed so the next image's
        # motion reference is the most recent real frame.
        if meta['skip']:
            self.prev_frame = img
            return []

        yolo_dets = self._yolo_for_image(img_path, zone_full)
        insect_dets = self._motion_for_image(img, zone_motion)
        self.prev_frame = img

        return _merge_image_detections(
            img_path.name, yolo_dets, insect_dets, self.iou_threshold
        )

    # --- internals ---

    def _yolo_for_image(self, img_path: Path, zone: np.ndarray) -> list[dict]:
        try:
            raw = self.yolo.predict(img_path)
        except Exception as e:
            logger.warning(f'YOLO failed on {img_path.name}: {e}')
            return []
        out = []
        for d in raw:
            bbox_xywh = (d['x1'], d['y1'], d['w'], d['h'])
            if zone is not None and not is_in_roi(bbox_xywh, zone):
                continue
            out.append(
                {
                    'bbox': (d['x1'], d['y1'], d['x2'], d['y2']),
                    'bbox_w': d['w'],
                    'bbox_h': d['h'],
                    'yolo_class': d['class'],
                    'yolo_confidence': float(d['confidence']),
                }
            )
        return out

    def _motion_for_image(self, img: np.ndarray, zone: np.ndarray) -> list[dict]:
        # Background reference must have the same shape as the current
        # image. Mixed shapes (some frames include an info-strip, others
        # don't) would crash downstream mask indexing.
        if self.prev_frame is not None and self.prev_frame.shape == img.shape:
            bg = self.prev_frame
        elif self.global_bg is not None and self.global_bg.shape == img.shape:
            bg = self.global_bg
        else:
            return []

        fg_mask = detect_foreground(img, bg, zone, self.cfg)
        contours = filter_contours(img, fg_mask, self.cfg)
        if not contours:
            return []

        candidates: list[tuple[tuple, Image.Image]] = []
        pad_frac = float(self.cfg.get('crop_pad_frac', 0.3))
        ih, iw = img.shape[:2]
        for det in contours:
            x, y, w, h = det['bbox']
            if self.static_filter and self.static_filter.is_static((x, y, w, h)):
                continue
            pad = int(max(w, h) * pad_frac)
            x1, y1 = max(0, x - pad), max(0, y - pad)
            x2, y2 = min(iw, x + w + pad), min(ih, y + h + pad)
            if x2 <= x1 or y2 <= y1:
                continue
            bgr = img[y1:y2, x1:x2]
            if bgr.size == 0:
                continue
            pil = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
            candidates.append(((x, y, w, h), pil))

        out: list[dict] = []
        for (x, y, w, h), pil in candidates:
            try:
                label, b_conf = self.binary.predict(
                    pil, threshold=self.binary_threshold
                )
            except Exception as e:
                logger.warning(f'Binary classifier failed: {e}')
                continue
            if label != 'insect':
                continue
            try:
                g_label, g_conf, g_probs = self.group.predict(pil)
            except Exception as e:
                logger.warning(f'Group classifier failed: {e}')
                continue
            if g_label == 'error':
                continue
            if g_conf < self.group_threshold:
                # Binary said insect but the group classifier wasn't
                # confident enough: keep the detection, strip the class so
                # a reviewer assigns one. Probabilities are preserved.
                g_label = ''
            out.append(
                {
                    'bbox': (x, y, x + w, y + h),
                    'bbox_w': w,
                    'bbox_h': h,
                    'binary_confidence': float(b_conf),
                    'insectnet_class': g_label,
                    'insectnet_confidence': float(g_conf),
                    'class_probs': g_probs,
                }
            )
        return out


def _cli() -> None:  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    parser = argparse.ArgumentParser(
        description='Run the full pollinator inference pipeline on a folder.'
    )
    parser.add_argument('--image_dir', required=True)
    parser.add_argument('--output_json', required=True)
    parser.add_argument('--yolo_model', required=True)
    parser.add_argument('--binary_model', required=True)
    parser.add_argument('--group_model', required=True)
    parser.add_argument('--yolo_confidence', type=float, default=0.25)
    parser.add_argument('--yolo_slice_size', type=int, default=640)
    parser.add_argument('--yolo_overlap', type=float, default=0.2)
    parser.add_argument('--binary_threshold', type=float, default=0.5)
    parser.add_argument('--group_threshold', type=float, default=0.0)
    parser.add_argument('--iou_threshold', type=float, default=0.3)
    parser.add_argument(
        '--skip_first_n',
        type=int,
        default=0,
        help='Skip the first N images in sorted order (resume support).',
    )
    args = parser.parse_args()

    image_paths = list_images(args.image_dir)
    if args.skip_first_n:
        image_paths = image_paths[args.skip_first_n :]
    if not image_paths:
        logger.warning('No images to process')
        Path(args.output_json).write_text(json.dumps({'detections': []}, indent=2))
        return

    pipeline = PollinatorInferencePipeline(
        yolo_model=args.yolo_model,
        binary_model=args.binary_model,
        group_model=args.group_model,
        yolo_confidence=args.yolo_confidence,
        yolo_slice_size=args.yolo_slice_size,
        yolo_overlap=args.yolo_overlap,
        binary_threshold=args.binary_threshold,
        group_threshold=args.group_threshold,
        iou_threshold=args.iou_threshold,
    )
    pipeline.prime(image_paths)

    all_detections: list[dict] = []
    by_class = {c: 0 for c in CLASSES}
    by_source = {'yolo': 0, 'preprocessing': 0, 'both': 0}
    for i, p in enumerate(image_paths, start=1):
        dets = pipeline.process_image(p)
        all_detections.extend(dets)
        for d in dets:
            by_source[d['source']] = by_source.get(d['source'], 0) + 1
            cls = d.get('yolo_class') or d.get('insectnet_class') or ''
            if cls in by_class:
                by_class[cls] += 1
        logger.info(f'[{i}/{len(image_paths)}] {p.name}: {len(dets)} detections')

    output = {
        'run': {
            'image_dir': args.image_dir,
            'n_images': len(image_paths),
            'n_detections': len(all_detections),
            'detections_by_class': by_class,
            'detections_by_source': by_source,
        },
        'detections': all_detections,
    }
    Path(args.output_json).write_text(json.dumps(output, indent=2))
    logger.info(f'Wrote {len(all_detections)} detections to {args.output_json}')


if __name__ == '__main__':
    _cli()
