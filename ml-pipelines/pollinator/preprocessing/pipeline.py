"""
preprocessing/pipeline.py
==========================
Background subtraction pipeline for Arctic pollinator detection.

Extracts candidate insect crops from time-lapse field images using:
- Frame-to-frame difference (previous frame as background reference)
- Caller-provided ROI bbox (or full image)
- Contour filtering and static detection suppression

Usage (standalone):
    python -m pollinator.preprocessing.pipeline \
        --image_dir path/to/camera_folder \
        --output_dir path/to/output

Usage (as module):
    from pollinator.preprocessing import run_preprocessing, DEFAULT_CONFIG
    run_preprocessing(image_dir="path/to/images", output_dir="path/to/output")
"""

import argparse
import csv
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .background import (
    StaticFilter,
    compute_global_background,
    crop_with_padding,
    detect_foreground,
    filter_contours,
)
from .config import CSV_FIELDS_DEBUG, CSV_FIELDS_MARIA, DEFAULT_CONFIG
from .exif   import get_exif_datetime, get_exif_metadata
from .roi    import is_in_roi, setup_zone

logger = logging.getLogger(__name__)


def _seconds_between(a: tuple, b: tuple) -> float:
    """Absolute seconds between two (y, m, d, hh, mm, ss) EXIF tuples."""
    return abs((datetime(*b) - datetime(*a)).total_seconds())


def robust_sort_key(p):
    """
    Sort by EXIF DateTimeOriginal first, then numeric suffix in filename,
    then filename string. EXIF reads are LRU-cached so the sort pass and
    the per-frame metadata pass share the work.
    """
    p   = Path(p)
    dt  = get_exif_datetime(str(p))
    if dt is not None:
        return (0, dt, p.name)
    m = re.search(r"(\d+)", p.stem)
    if m:
        return (1, int(m.group(1)), p.name)
    return (2, p.name)


def sorted_images(folder: Path) -> list:
    exts = {".jpg", ".jpeg", ".png", ".JPG", ".JPEG"}
    imgs = [p for p in folder.iterdir() if p.suffix in exts]
    return sorted(imgs, key=robust_sort_key)


def init_csv(path: Path, fields: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        csv.DictWriter(f, fieldnames=fields).writeheader()


def write_csv_row(path: Path, row: dict, fields: list):
    with open(path, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=fields).writerow(
            {k: row.get(k, "") for k in fields}
        )


def run_preprocessing(
    image_dir:    str,
    output_dir:   str,
    config:       Optional[dict] = None,
    debug:        bool = False,
    debug_csv:    bool = True,
    skip_first_n: int  = 0,
) -> dict:
    """
    Run background subtraction pipeline on a single camera folder.

    IMPORTANT: Camera angle must be consistent throughout the sequence.
    If the camera was repositioned mid-sequence, split the folder at that
    point before running. The pipeline cannot detect angle changes
    automatically.

    Args:
        image_dir:    Path to folder containing images for one camera plot.
        output_dir:   Path to output folder. Creates crops/ and results.csv.
        config:       Optional parameter overrides (merged with DEFAULT_CONFIG).
        debug:        If True, saves debug images to output_dir/debug/.
        debug_csv:    If True, uses full debug CSV fields. If False, researcher CSV.
        skip_first_n: Skip the first N images in the sorted folder. Useful for
                      resuming a partial run. 0 means process from the start.

    Returns:
        dict with keys: csv_path, crop_dir, n_crops, n_skipped
    """
    if skip_first_n < 0:
        raise ValueError(f"skip_first_n must be >= 0, got {skip_first_n}")
    cfg        = {**DEFAULT_CONFIG, **(config or {})}
    image_dir  = Path(image_dir)
    out_dir    = Path(output_dir)
    crop_dir   = out_dir / "crops"
    debug_dir  = out_dir / "debug"
    csv_path   = out_dir / "results.csv"
    csv_fields = CSV_FIELDS_DEBUG if debug_csv else CSV_FIELDS_MARIA

    crop_dir.mkdir(parents=True, exist_ok=True)
    if debug:
        debug_dir.mkdir(parents=True, exist_ok=True)

    paths = sorted_images(image_dir)
    if skip_first_n > 0:
        n_total = len(paths)
        paths   = paths[skip_first_n:]
        logger.info(f"Skipping first {skip_first_n} of {n_total} images; processing {len(paths)} remaining")
    if not paths:
        logger.warning(f"No images to process in {image_dir} (after skip_first_n={skip_first_n})")
        return {"csv_path": str(csv_path), "crop_dir": str(crop_dir),
                "n_crops": 0, "n_skipped": 0}

    cam_prefix = f"{image_dir.parent.name}_{image_dir.name}"
    init_csv(csv_path, csv_fields)

    global_bg = compute_global_background(paths, cfg)

    first = None
    for p in paths[:10]:
        first = cv2.imread(str(p))
        if first is not None:
            break
    if first is None:
        logger.warning(f"Could not read any image from {image_dir}")
        return {"csv_path": str(csv_path), "crop_dir": str(crop_dir),
                "n_crops": 0, "n_skipped": 0}
    zone = setup_zone(first, cfg)
    if cfg.get("roi_bbox") is not None:
        logger.info(f"Using caller-provided ROI bbox: {cfg['roi_bbox']}")
    else:
        logger.info("No roi_bbox in config; using full image as zone")

    static_filter = StaticFilter(cfg) if cfg.get("enable_static_filter") else None
    n_crops      = 0
    n_skipped    = 0
    prev_frame   = None
    prev_dt      = None
    max_gap_sec  = float(cfg.get("max_gap_seconds", 3600))

    for idx, path in enumerate(paths):
        img = cv2.imread(str(path))
        if img is None:
            logger.warning(f"Could not read {path}")
            continue

        cur_dt = get_exif_datetime(str(path))
        if prev_dt is not None and cur_dt is not None:
            gap = _seconds_between(prev_dt, cur_dt)
            if gap > max_gap_sec:
                logger.info(f"EXIF gap {gap:.0f}s exceeds {max_gap_sec:.0f}s; resetting background reference")
                prev_frame = None
        if cur_dt is not None:
            prev_dt = cur_dt

        sh = cfg.get("strip_height", 0)
        if sh and img.shape[0] > sh:
            img       = img[:img.shape[0] - sh]
            zone_crop = zone[:img.shape[0]]
        else:
            zone_crop = zone

        meta   = get_exif_metadata(str(path), cfg)
        rel_id = path.name

        if meta["skip"]:
            n_skipped += 1
            write_csv_row(csv_path, {
                "camera_path":         cam_prefix,
                "image_name":          rel_id,
                "datetime":            meta["datetime"],
                "weather":             meta["weather"],
                "skip":                True,
                "skip_reason":         meta["skip_reason"],
                "laplacian_var":       meta["laplacian_var"],
                "pollinator_detected": "skipped",
            }, csv_fields)
            prev_frame = img
            continue

        if prev_frame is not None:
            bg = prev_frame
        elif global_bg is not None:
            bg = global_bg
        else:
            prev_frame = img
            write_csv_row(csv_path, {
                "camera_path": cam_prefix, "image_name": rel_id,
                **meta, "pollinator_detected": "no",
            }, csv_fields)
            continue

        fg_mask    = detect_foreground(img, bg, zone_crop, cfg)
        detections = filter_contours(img, fg_mask, cfg)

        if not detections:
            write_csv_row(csv_path, {
                "camera_path": cam_prefix, "image_name": rel_id,
                **meta, "pollinator_detected": "no",
            }, csv_fields)
            prev_frame = img
            continue

        for i, det in enumerate(detections):
            bbox   = det["bbox"]
            is_roi = is_in_roi(bbox, zone_crop)
            scope  = "roi" if is_roi else "outside_roi"

            static_suspect = False
            if static_filter:
                static_suspect = static_filter.is_static(bbox)

            crop_fn = f"{cam_prefix}__{path.stem}_crop_{i}_{det['candidate_type']}_{scope}.jpg"
            crop    = crop_with_padding(img, det, cfg)
            cv2.imwrite(str(crop_dir / crop_fn), crop)
            n_crops += 1

            x, y, w, h = bbox
            write_csv_row(csv_path, {
                "camera_path":         cam_prefix,
                "image_name":          rel_id,
                "crop_filename":       crop_fn,
                "datetime":            meta["datetime"],
                "camera_name":         meta["camera_name"],
                "shutter_speed":       meta["shutter_speed"],
                "weather":             meta["weather"],
                "skip":                False,
                "laplacian_var":       meta["laplacian_var"],
                "pollinator_detected": "candidate",
                "detection_scope":     scope,
                "inside_roi":          str(is_roi),
                "bbox_x": x, "bbox_y": y, "bbox_w": w, "bbox_h": h,
                "candidate_type":      det["candidate_type"],
                "static_suspect":      static_suspect,
            }, csv_fields)

        prev_frame = img
        logger.info(f"[{idx+1}/{len(paths)}] {rel_id} | {len(detections)} candidate(s)")

    logger.info(f"Done. Crops: {n_crops} | Skipped: {n_skipped} | CSV: {csv_path}")
    return {
        "csv_path":  str(csv_path),
        "crop_dir":  str(crop_dir),
        "n_crops":   n_crops,
        "n_skipped": n_skipped,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Arctic pollinator preprocessing pipeline")
    parser.add_argument("--image_dir",       required=True)
    parser.add_argument("--output_dir",      required=True)
    parser.add_argument("--debug",           action="store_true")
    parser.add_argument("--researcher_csv",  action="store_true",
                        help="Use researcher CSV format instead of debug CSV")
    parser.add_argument("--no_large_motion", action="store_true",
                        help="Disable large motion tiling")
    parser.add_argument("--skip_first_n",    type=int, default=0,
                        help="Skip the first N images in the sorted folder (resume support)")
    args = parser.parse_args()

    cfg = {}
    if args.no_large_motion:
        cfg["enable_large_motion"] = False

    result = run_preprocessing(
        image_dir    = args.image_dir,
        output_dir   = args.output_dir,
        config       = cfg,
        debug        = args.debug,
        debug_csv    = not args.researcher_csv,
        skip_first_n = args.skip_first_n,
    )
    print(f"Crops saved:    {result['n_crops']}")
    print(f"Frames skipped: {result['n_skipped']}")
    print(f"CSV:            {result['csv_path']}")
