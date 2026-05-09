"""
inference/pipeline.py
======================
End-to-end pollinator detection pipeline.

Two parallel detectors operate on the same camera folder:
    YOLO         (full-image)  -> detections with yolo_class
    InsectNet    (preprocessing crops, binary filter, group classifier)
                 -> detections with insectnet_class

Per source image, detections are merged by spatial overlap (IoU). When both
detectors find the same physical insect, both labels are recorded; class
disagreements are surfaced for review by downstream consumers.

Output: results.json (run summary + per-detection records). No CSV at the
run level. CSV exports are a researcher-tooling concern, not the pipeline's.

Usage (CLI):
    python -m pollinator.inference.pipeline \
        --image_dir    path/to/camera_folder \
        --output_dir   path/to/output \
        --yolo_model   path/to/yolo_best.pt \
        --binary_model path/to/binary_best.pth \
        --group_model  path/to/group_best.pth

Usage (as module):
    from pollinator.inference import run_pipeline

    result = run_pipeline(
        image_dir    = "path/to/images",
        output_dir   = "path/to/output",
        yolo_model   = "path/to/yolo_best.pt",
        binary_model = "path/to/binary_best.pth",
        group_model  = "path/to/group_best.pth",
    )
"""

import argparse
import csv
import json
import logging
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from ..classification     import BinaryClassifier, GroupClassifier
from ..detection          import YoloDetector
from ..preprocessing      import run_preprocessing
from ..preprocessing.roi  import is_in_roi, setup_zone

from .merge import CLASSES, merge_per_image

logger = logging.getLogger(__name__)

IMG_SUFFIXES = (".jpg", ".jpeg", ".png", ".JPG", ".JPEG")


def list_images(folder: Path) -> list:
    return sorted([p for p in folder.iterdir() if p.suffix in IMG_SUFFIXES])


def run_yolo_step(
    image_paths:     list,
    yolo_model:      str,
    yolo_confidence: float,
    crop_dir:        Path,
    device:          Optional[str],
    zone:            Optional[np.ndarray] = None,
) -> list:
    """
    Run YOLO on every image and save bbox crops to crop_dir. When `zone` is
    provided, drop detections whose bbox falls outside the zone. The zone is
    computed once per run from cfg['roi_bbox'] (or full image when absent),
    so YOLO and the preprocessing branch share one ROI definition.

    Returns: list of dicts with keys
        image_name, bbox, bbox_w, bbox_h, yolo_class, yolo_confidence, crop_path
    """
    crop_dir.mkdir(parents=True, exist_ok=True)
    detector = YoloDetector(
        yolo_model, confidence=yolo_confidence, device=device,
    )

    out      = []
    n_total  = 0
    n_in_roi = 0
    for img_path in image_paths:
        try:
            dets = detector.predict(img_path)
        except Exception as e:
            logger.warning(f"YOLO failed on {img_path.name}: {e}")
            continue
        if not dets:
            continue
        img = cv2.imread(str(img_path))
        if img is None:
            logger.warning(f"Could not read {img_path} for crop save")
            continue
        for i, d in enumerate(dets):
            n_total += 1
            bbox_xywh = (d["x1"], d["y1"], d["w"], d["h"])
            if zone is not None and not is_in_roi(bbox_xywh, zone):
                continue
            n_in_roi += 1
            crop = img[d["y1"]:d["y2"], d["x1"]:d["x2"]]
            if crop.size == 0:
                continue
            crop_fn   = f"{img_path.stem}_yolo_{i}_{d['class']}.jpg"
            crop_path = crop_dir / crop_fn
            cv2.imwrite(str(crop_path), crop)
            out.append({
                "image_name":      img_path.name,
                "bbox":            (d["x1"], d["y1"], d["x2"], d["y2"]),
                "bbox_w":          d["w"],
                "bbox_h":          d["h"],
                "yolo_class":      d["class"],
                "yolo_confidence": float(d["confidence"]),
                "crop_path":       str(crop_path),
            })
    if zone is not None:
        logger.info(f"YOLO: {n_in_roi}/{n_total} detections inside ROI across {len(image_paths)} images")
    else:
        logger.info(f"YOLO: {n_total} detections across {len(image_paths)} images")
    return out


def run_insectnet_step(
    prep_csv_path:    Path,
    prep_crop_dir:    Path,
    binary_model:     str,
    group_model:      str,
    binary_threshold: float,
    device:           Optional[str],
) -> list:
    """
    Run binary + group classifiers on preprocessing crops.

    Drops crops the binary classifier flags as background. Returns one
    record per surviving insect crop.

    Returns: list of dicts with keys
        image_name, bbox, bbox_w, bbox_h, datetime, weather,
        binary_confidence, insectnet_class, insectnet_confidence,
        class_probs, crop_path
    """
    meta_by_crop = {}
    with open(prep_csv_path) as f:
        for row in csv.DictReader(f):
            fn = row.get("crop_filename", "")
            if fn and row.get("pollinator_detected") == "candidate":
                meta_by_crop[fn] = row

    crop_paths = sorted(prep_crop_dir.glob("*.jpg")) + sorted(prep_crop_dir.glob("*.png"))
    if not crop_paths:
        logger.info("InsectNet: no preprocessing crops to classify")
        return []

    binary_clf     = BinaryClassifier(binary_model, device=device)
    binary_results = binary_clf.predict_batch(crop_paths, threshold=binary_threshold)

    insect_crops = []
    for br in binary_results:
        if not br["is_insect"]:
            continue
        crop_fn = Path(br["path"]).name
        meta    = meta_by_crop.get(crop_fn)
        if meta is None:
            continue
        insect_crops.append((br, meta))

    n_total = len(binary_results)
    n_kept  = len(insect_crops)
    logger.info(f"Binary: {n_kept}/{n_total} crops kept as insect (threshold={binary_threshold})")

    if not insect_crops:
        return []

    group_clf     = GroupClassifier(group_model, device=device)
    insect_paths  = [br["path"] for br, _ in insect_crops]
    group_results = group_clf.predict_batch(insect_paths)
    group_by_path = {gr["path"]: gr for gr in group_results}

    out = []
    for br, meta in insect_crops:
        gr = group_by_path.get(br["path"])
        if gr is None or gr["label"] == "error":
            continue
        try:
            x = int(meta["bbox_x"])
            y = int(meta["bbox_y"])
            w = int(meta["bbox_w"])
            h = int(meta["bbox_h"])
        except (KeyError, ValueError):
            continue
        out.append({
            "image_name":           meta.get("image_name", ""),
            "bbox":                 (x, y, x + w, y + h),
            "bbox_w":               w,
            "bbox_h":               h,
            "datetime":             meta.get("datetime", ""),
            "weather":              meta.get("weather", ""),
            "binary_confidence":    float(br["confidence"]),
            "insectnet_class":      gr["label"],
            "insectnet_confidence": float(gr["confidence"]),
            "class_probs":          gr["all_probs"],
            "crop_path":            br["path"],
        })
    logger.info(f"Group: classified {len(out)} insect crops")
    return out


def run_pipeline(
    image_dir:         str,
    output_dir:        str,
    yolo_model:        str,
    binary_model:      str,
    group_model:       str,
    config:            Optional[dict] = None,
    yolo_confidence:   float = 0.25,
    binary_threshold:  float = 0.5,
    iou_threshold:     float = 0.3,
    skip_first_n:      int   = 0,
    device:            Optional[str] = None,
    debug:             bool  = False,
    progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
) -> dict:
    """
    Run full pollinator detection pipeline on a camera folder.

    IMPORTANT: The camera angle must be consistent throughout the image
    sequence. If the camera was repositioned mid-sequence, split the
    folder at that point before running.

    Args:
        image_dir:         Path to folder with images from one camera plot.
        output_dir:        Path to output folder.
        yolo_model:        Path to trained YOLO checkpoint (.pt).
        binary_model:      Path to trained binary classifier checkpoint (.pth).
        group_model:       Path to trained group classifier checkpoint (.pth).
        config:            Optional preprocessing config overrides.
        yolo_confidence:   YOLO minimum detection confidence.
        binary_threshold:  Minimum confidence to classify a preprocessing crop
                           as insect. Lower = higher recall, more false
                           positives for review.
        iou_threshold:     IoU above which a YOLO bbox and a preprocessing
                           bbox are treated as the same physical insect.
        skip_first_n:      Skip the first N images in the sorted folder
                           (resume support). Applied to both YOLO and the
                           preprocessing branch so they stay aligned.
        device:            "cuda", "cpu", or None (auto-detect).
        debug:             Save debug images from preprocessing.
        progress_callback: Optional callback invoked at major milestones.
                           Signature: (processed, total, message, level)
                           where level is one of 'info', 'warn', 'error'.
                           Exceptions raised by the callback are swallowed
                           so they cannot break the run.

    Returns:
        dict with keys:
            output_json:                Path to results.json
            n_images:                   Number of source images processed
            n_yolo_detections:          Raw YOLO detection count (pre-merge)
            n_preprocessing_candidates: Raw preprocessing crop count
            n_detections:               Final merged detection count
            detections_by_class:        Per-class counts (canonical class)
            detections_by_source:       Counts by source (yolo/preprocessing/both)
    """
    if skip_first_n < 0:
        raise ValueError(f"skip_first_n must be >= 0, got {skip_first_n}")

    def _emit(processed: int, total: int, message: str = "", level: str = "info") -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(processed, total, message, level)
        except Exception:
            logger.exception("progress_callback raised; ignoring")

    image_dir  = Path(image_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    image_paths = list_images(image_dir)
    if skip_first_n > 0:
        n_total     = len(image_paths)
        image_paths = image_paths[skip_first_n:]
        logger.info(f"Skipping first {skip_first_n} of {n_total} images; processing {len(image_paths)} remaining")
    if not image_paths:
        logger.warning(f"No images to process in {image_dir} (after skip_first_n={skip_first_n})")
        return {
            "output_json":                str(output_dir / "results.json"),
            "n_images":                   0,
            "n_yolo_detections":          0,
            "n_preprocessing_candidates": 0,
            "n_detections":               0,
            "detections_by_class":        {c: 0 for c in CLASSES},
            "detections_by_source":       {"yolo": 0, "preprocessing": 0, "both": 0},
        }

    n = len(image_paths)
    _emit(0, n, f"Starting run on {n} images")

    cfg = config or {}
    first_img = cv2.imread(str(image_paths[0]))
    zone = setup_zone(first_img, cfg) if first_img is not None else None
    if cfg.get("roi_bbox") is not None:
        logger.info(f"ROI: caller-provided bbox {cfg['roi_bbox']}")
    else:
        logger.info("ROI: full image (no roi_bbox in config)")

    logger.info(f"Step 1: YOLO on {len(image_paths)} images")
    yolo_dets = run_yolo_step(
        image_paths     = image_paths,
        yolo_model      = yolo_model,
        yolo_confidence = yolo_confidence,
        crop_dir        = output_dir / "yolo_crops",
        device          = device,
        zone            = zone,
    )
    _emit(int(n * 0.4), n, f"YOLO detected {len(yolo_dets)} candidates")

    logger.info(f"Step 2: Preprocessing {image_dir}")
    prep_result = run_preprocessing(
        image_dir    = str(image_dir),
        output_dir   = str(output_dir / "preprocessing"),
        config       = config,
        debug        = debug,
        skip_first_n = skip_first_n,
    )
    n_candidates = prep_result["n_crops"]
    logger.info(f"  Extracted {n_candidates} candidate crops")
    _emit(int(n * 0.7), n, f"Preprocessing extracted {n_candidates} candidate crops")

    if n_candidates > 0:
        logger.info(f"Step 3+4: InsectNet (binary threshold={binary_threshold})")
        insect_dets = run_insectnet_step(
            prep_csv_path    = Path(prep_result["csv_path"]),
            prep_crop_dir    = Path(prep_result["crop_dir"]),
            binary_model     = binary_model,
            group_model      = group_model,
            binary_threshold = binary_threshold,
            device           = device,
        )
        _emit(int(n * 0.9), n, f"Classifier kept {len(insect_dets)} insect crops")
    else:
        insect_dets = []

    logger.info(f"Step 5: Merge by IoU > {iou_threshold}")
    detections, by_class, by_source = merge_per_image(
        yolo_dets, insect_dets, iou_threshold,
    )
    _emit(n, n, f"Run complete: {len(detections)} detections")
    logger.info(
        f"  Final: {len(detections)} detections "
        f"({by_source['both']} both, {by_source['yolo']} yolo-only, "
        f"{by_source['preprocessing']} preprocessing-only)"
    )

    output = {
        "run": {
            "image_dir":                  str(image_dir),
            "output_dir":                 str(output_dir),
            "n_images":                   len(image_paths),
            "n_yolo_detections":          len(yolo_dets),
            "n_preprocessing_candidates": n_candidates,
            "n_detections":               len(detections),
            "detections_by_class":        by_class,
            "detections_by_source":       by_source,
            "config": {
                "yolo_confidence":  yolo_confidence,
                "binary_threshold": binary_threshold,
                "iou_threshold":    iou_threshold,
            },
        },
        "detections": detections,
    }
    json_path = output_dir / "results.json"
    json_path.write_text(json.dumps(output, indent=2))
    logger.info(f"Results saved to {json_path}")

    return {
        "output_json":                str(json_path),
        "n_images":                   len(image_paths),
        "n_yolo_detections":          len(yolo_dets),
        "n_preprocessing_candidates": n_candidates,
        "n_detections":               len(detections),
        "detections_by_class":        by_class,
        "detections_by_source":       by_source,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Run full pollinator detection pipeline")
    parser.add_argument("--image_dir",        required=True)
    parser.add_argument("--output_dir",       required=True)
    parser.add_argument("--yolo_model",       required=True)
    parser.add_argument("--binary_model",     required=True)
    parser.add_argument("--group_model",      required=True)
    parser.add_argument("--yolo_confidence",  type=float, default=0.25)
    parser.add_argument("--binary_threshold", type=float, default=0.5)
    parser.add_argument("--iou_threshold",    type=float, default=0.3)
    parser.add_argument("--skip_first_n",     type=int,   default=0,
                        help="Skip the first N images (resume support)")
    parser.add_argument("--debug",            action="store_true")
    args = parser.parse_args()

    result = run_pipeline(
        image_dir        = args.image_dir,
        output_dir       = args.output_dir,
        yolo_model       = args.yolo_model,
        binary_model     = args.binary_model,
        group_model      = args.group_model,
        yolo_confidence  = args.yolo_confidence,
        binary_threshold = args.binary_threshold,
        iou_threshold    = args.iou_threshold,
        skip_first_n     = args.skip_first_n,
        debug            = args.debug,
    )
    print(f"\nResults:")
    print(f"  Images processed: {result['n_images']}")
    print(f"  YOLO detections:  {result['n_yolo_detections']}")
    print(f"  Prep candidates:  {result['n_preprocessing_candidates']}")
    print(f"  Final detections: {result['n_detections']}")
    print(f"  By source:        {result['detections_by_source']}")
    print(f"  By class:         {result['detections_by_class']}")
    print(f"  JSON:             {result['output_json']}")
