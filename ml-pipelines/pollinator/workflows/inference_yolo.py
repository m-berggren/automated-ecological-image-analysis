"""YOLO-only inference workflow (no classical preprocessing, no classifiers).

Streamlined alternative to pollinator.workflows.inference. Skips the
classical preprocessing branch and the InsectNet binary/group classifiers.
Use this when YOLO alone is strong enough to be the sole detection signal.
Typical runtime is ~half of the full pipeline at the same image count.

Per image:
    1. YOLO detection (SAHI-tiled, native pixel scale preserved).
    2. Optional ROI filtering via cfg['roi_bbox'].
    3. Save bbox crops + a detection record to results.json.

Output JSON shape mirrors the full pipeline's so downstream consumers
(Django services, UI) can read it without code changes; classifier-only
fields (insectnet_class, binary_confidence, class_probs, merge_iou,
preprocessing_crop) are populated with None.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, Optional

import cv2

from ..detection import YoloDetector
from ..preprocessing.roi import is_in_roi, setup_zone

logger = logging.getLogger(__name__)

CLASSES = ['bumblebee', 'fly', 'butterfly', 'other']
IMG_SUFFIXES = ('.jpg', '.jpeg', '.png', '.JPG', '.JPEG')


def run_pipeline(
    image_dir: str,
    output_dir: str,
    yolo_model: str,
    config: Optional[dict] = None,
    yolo_confidence: float = 0.25,
    yolo_slice_size: int = 640,
    yolo_overlap: float = 0.2,
    skip_first_n: int = 0,
    device: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
    progress_every: int = 10,
) -> dict:
    """YOLO-only inference on a folder of images.

    Args:
        image_dir:         Folder of source images (one camera plot).
        output_dir:        Where to write results.json + yolo_crops/.
        yolo_model:        Path to trained YOLO checkpoint (.pt). Same path
                           convention as the full inference pipeline so the
                           Django ModelVersion resolver works unchanged.
        config:            Optional dict; only cfg['roi_bbox'] is read here.
        yolo_confidence:   Minimum detection confidence.
        yolo_slice_size:   SAHI tile size; should match training imgsz.
        yolo_overlap:      SAHI overlap ratio between tiles (0-1).
        skip_first_n:      Resume support; skip the first N sorted images.
        device:            'cuda', 'cpu', or None for auto-detect.
        progress_callback: (processed, total, message, level) hook. Fires
                           per `progress_every` images plus at the end.
        progress_every:    Emit progress every N images (default 10).

    Returns:
        dict with keys:
            output_json:         Path to results.json
            n_images:            Number of source images processed
            n_detections:        Final detection count (after ROI filter)
            detections_by_class: Per-class counts
            detections_by_source: {'yolo': N, 'preprocessing': 0, 'both': 0}
                                  Kept for shape parity with the full pipeline.
    """
    if skip_first_n < 0:
        raise ValueError(f'skip_first_n must be >= 0, got {skip_first_n}')

    def _emit(
        processed: int, total: int, message: str = '', level: str = 'info'
    ) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(processed, total, message, level)
        except Exception:
            logger.exception('progress_callback raised; ignoring')

    image_dir = Path(image_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    crop_dir = output_dir / 'yolo_crops'
    crop_dir.mkdir(parents=True, exist_ok=True)
    output_json = output_dir / 'results.json'

    image_paths = sorted([p for p in image_dir.iterdir() if p.suffix in IMG_SUFFIXES])
    if skip_first_n > 0:
        total_before_skip = len(image_paths)
        image_paths = image_paths[skip_first_n:]
        logger.info(
            f'Skipping first {skip_first_n} of {total_before_skip} images; '
            f'processing {len(image_paths)} remaining'
        )

    empty_summary = {
        'output_json': str(output_json),
        'n_images': 0,
        'n_detections': 0,
        'detections_by_class': {c: 0 for c in CLASSES},
        'detections_by_source': {'yolo': 0, 'preprocessing': 0, 'both': 0},
    }

    if not image_paths:
        logger.warning(f'No images to process in {image_dir}')
        output_json.write_text(
            json.dumps({'run': empty_summary, 'detections': []}, indent=2)
        )
        return empty_summary

    n = len(image_paths)
    _emit(0, n, f'Starting YOLO-only run on {n} images')

    cfg = config or {}
    use_roi = cfg.get('roi_bbox') is not None
    if use_roi:
        logger.info(f'ROI: caller-provided bbox {cfg["roi_bbox"]}')
    else:
        logger.info('ROI: full image (no roi_bbox in config)')

    detector = YoloDetector(
        yolo_model,
        confidence=yolo_confidence,
        device=device,
        slice_size=yolo_slice_size,
        overlap=yolo_overlap,
    )

    detections: list = []
    detection_id = 0
    by_class: dict = {c: 0 for c in CLASSES}
    n_total = 0
    n_in_roi = 0

    for i, img_path in enumerate(image_paths):
        try:
            dets = detector.predict(img_path)
        except Exception as e:
            logger.warning(f'YOLO failed on {img_path.name}: {e}')
            continue

        if not dets:
            if (i + 1) % progress_every == 0:
                _emit(i + 1, n, f'YOLO {i + 1}/{n}')
            continue

        img = cv2.imread(str(img_path))
        if img is None:
            logger.warning(f'Could not read {img_path} for crop save')
            continue

        # Per-image zone (image heights can vary across a folder when some
        # frames include an info-strip and others don't).
        img_zone = setup_zone(img, cfg) if use_roi else None

        for k, d in enumerate(dets):
            n_total += 1
            bbox_xywh = (d['x1'], d['y1'], d['w'], d['h'])
            if img_zone is not None and not is_in_roi(bbox_xywh, img_zone):
                continue
            n_in_roi += 1

            crop = img[d['y1'] : d['y2'], d['x1'] : d['x2']]
            if crop.size == 0:
                continue

            crop_fn = f'{img_path.stem}_yolo_{k}_{d["class"]}.jpg'
            crop_path = crop_dir / crop_fn
            cv2.imwrite(str(crop_path), crop)

            detection_id += 1
            detections.append(
                {
                    'id': detection_id,
                    'image_name': img_path.name,
                    'datetime': '',
                    'weather': '',
                    'source': 'yolo',
                    'bbox': {
                        'x1': d['x1'],
                        'y1': d['y1'],
                        'x2': d['x2'],
                        'y2': d['y2'],
                        'w': d['w'],
                        'h': d['h'],
                    },
                    'yolo_class': d['class'],
                    'yolo_confidence': round(float(d['confidence']), 4),
                    'insectnet_class': None,
                    'insectnet_confidence': None,
                    'binary_confidence': None,
                    'class_probs': None,
                    'merge_iou': None,
                    'yolo_crop': str(crop_path),
                    'preprocessing_crop': None,
                }
            )
            if d['class'] in by_class:
                by_class[d['class']] += 1

        if (i + 1) % progress_every == 0:
            _emit(i + 1, n, f'YOLO {i + 1}/{n} ({len(detections)} kept)')

    if use_roi:
        logger.info(
            f'YOLO: {n_in_roi}/{n_total} detections inside ROI across {n} images'
        )
    else:
        logger.info(f'YOLO: {n_total} detections across {n} images')

    summary = {
        'output_json': str(output_json),
        'n_images': n,
        'n_detections': len(detections),
        'detections_by_class': by_class,
        'detections_by_source': {
            'yolo': len(detections),
            'preprocessing': 0,
            'both': 0,
        },
    }
    output_json.write_text(
        json.dumps({'run': summary, 'detections': detections}, indent=2)
    )
    logger.info(f'Wrote {output_json}')

    _emit(n, n, f'Done: {len(detections)} detections')
    return summary
