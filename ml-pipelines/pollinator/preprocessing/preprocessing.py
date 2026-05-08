"""
preprocessing/pipeline.py
==========================
Background subtraction pipeline for Arctic pollinator detection.

Extracts candidate insect crops from time-lapse field images using:
- Frame-to-frame difference (rolling_window=1)
- ROI detection via coloured marker clip
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
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image as PILImage
from PIL.ExifTags import TAGS

logger = logging.getLogger(__name__)

# ── Default configuration ──────────────────────────────────────────────────
DEFAULT_CONFIG = {
    # Background computation
    # 0 = skip global background entirely, use frame-to-frame diff only
    "background_sample_size":        0,

    # Background subtraction threshold
    "darker_threshold":              30,

    # Contour filtering
    "min_contour_area":              400,
    "max_contour_area":              35000,

    # Large motion handling (bumblebee + flower displacement)
    # Set enable_large_motion=False to skip entirely if not needed
    "enable_large_motion":           True,
    "max_large_motion_area":         600000,
    "large_motion_tile_sizes":       [320, 512],
    "large_motion_tile_stride_frac": 0.65,
    "large_motion_max_tiles_per_size": 6,
    "large_motion_max_tiles_total":  10,
    "large_motion_tile_nms_iou":     0.35,
    "large_motion_min_fg_frac":      0.008,
    "large_motion_context_pad":      10,
    "large_motion_fallback_sizes":   [640],
    "large_motion_fallback_centers": [(0.35, 0.78), (0.50, 0.78), (0.65, 0.78)],
    "large_motion_max_fallbacks":    3,
    "large_motion_fallback_min_fg_frac": 0.003,

    "min_crop_px":                   10,
    "merge_dist":                    20,
    "max_aspect_ratio":              5,
    "kernel_open_size":              3,
    "kernel_close_size":             11,
    "min_texture":                   50,

    # Static detection suppression
    "enable_static_filter":          False,
    "static_dist":                   80,
    "static_max_frames":             15,

    # ROI / marker
    "use_roi":                       True,
    "marker_hue":                    (95, 135),
    "marker_sat_min":                80,
    "marker_val_min":                60,
    "marker_min_area":               50,
    "marker_zone_radius":            350,
    "roi_near_dist":                 50,

    # Quality filtering
    "skip_flash":                    True,
    "skip_foggy":                    True,
    "foggy_threshold":               50,

    # Crop extraction
    "crop_pad_frac":                 0.3,
    "crop_mode":                     "all",
    "strip_height":                  120,   # px to remove from bottom (Wingscapes info bar)

    # Green vegetation filter
    "green_hue_min":                 25,
    "green_hue_max":                 95,
    "green_sat_min":                 80,
    "green_val_min":                 40,

    # Classification
    "skip_classification":           False,
    "binary_threshold":              0.5,
}

# ── CSV fields ─────────────────────────────────────────────────────────────
CSV_FIELDS_DEBUG = [
    "camera_path", "image_name", "crop_filename",
    "datetime", "camera_name",
    "skip", "skip_reason", "laplacian_var", "shutter_speed", "weather",
    "pollinator_detected",
    "bbox_x", "bbox_y", "bbox_w", "bbox_h",
    "detection_scope", "near_marked_flower",
    "candidate_type", "static_suspect", "source_area",
    "binary_label", "binary_confidence",
    "pollinator_type", "group_confidence",
    "bumblebee_prob", "fly_prob", "butterfly_moth_prob", "other_prob",
]

CSV_FIELDS_MARIA = [
    "camera_path", "image_name", "crop_filename",
    "datetime", "weather",
    "pollinator_detected", "near_marked_flower",
    "pollinator_type", "binary_confidence", "group_confidence",
]

# ── EXIF helpers ───────────────────────────────────────────────────────────
_EXIF_DT_TAG  = next((k for k, v in TAGS.items() if v == "DateTimeOriginal"), None)
_FLASH_TAG    = 37385
_SHUTTER_TAG  = next((k for k, v in TAGS.items() if v == "ExposureTime"), None)
_CAMERA_TAG   = next((k for k, v in TAGS.items() if v == "Model"), None)


def _get_exif(path: str) -> dict:
    try:
        img  = PILImage.open(path)
        exif = img._getexif() if hasattr(img, "_getexif") else {}
        return exif or {}
    except Exception:
        return {}


def get_exif_metadata(path: str, cfg: dict) -> dict:
    exif    = _get_exif(path)
    dt      = exif.get(_EXIF_DT_TAG, "")
    flash   = exif.get(_FLASH_TAG, 0)
    shutter = exif.get(_SHUTTER_TAG)
    camera  = exif.get(_CAMERA_TAG, "")

    weather = "unknown"
    if shutter and hasattr(shutter, "denominator") and shutter.denominator:
        weather = "sunny" if shutter.denominator >= 200 else "cloudy"

    skip        = False
    skip_reason = ""
    lap_var     = 0.0

    if cfg.get("skip_flash") and flash and flash != 0:
        skip        = True
        skip_reason = "flash"

    if not skip and cfg.get("skip_foggy"):
        try:
            img_arr = cv2.imread(path)
            if img_arr is not None:
                gray    = cv2.cvtColor(img_arr, cv2.COLOR_BGR2GRAY)
                lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                if lap_var < cfg.get("foggy_threshold", 50):
                    skip        = True
                    skip_reason = "fog"
        except Exception:
            pass

    return {
        "datetime":      dt,
        "camera_name":   camera,
        "shutter_speed": str(shutter) if shutter else "",
        "weather":       weather,
        "skip":          skip,
        "skip_reason":   skip_reason,
        "laplacian_var": lap_var,
    }


# ── Image sorting ──────────────────────────────────────────────────────────
def filename_sort_key(p):
    p = Path(p)
    m = re.search(r"(\d+)", p.stem)
    if m:
        return (0, int(m.group(1)), p.name)
    return (1, p.name)


def sorted_images(folder: Path) -> list:
    exts = {".jpg", ".jpeg", ".png", ".JPG", ".JPEG"}
    imgs = [p for p in folder.iterdir() if p.suffix in exts]
    return sorted(imgs, key=filename_sort_key)


# ── ROI detection ──────────────────────────────────────────────────────────
def find_marker(image: np.ndarray, cfg: dict) -> Optional[tuple]:
    hsv  = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(
        hsv,
        np.array([cfg["marker_hue"][0], cfg["marker_sat_min"], cfg["marker_val_min"]]),
        np.array([cfg["marker_hue"][1], 255, 255]),
    )
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    clusters    = [c for c in contours if cv2.contourArea(c) > cfg["marker_min_area"]]
    if not clusters:
        return None
    h, w           = image.shape[:2]
    cx_img, cy_img = w // 2, h // 2

    def dist_to_center(c):
        M = cv2.moments(c)
        if M["m00"] == 0:
            return float("inf")
        return (int(M["m10"]/M["m00"]) - cx_img)**2 + (int(M["m01"]/M["m00"]) - cy_img)**2

    best = min(clusters, key=dist_to_center)
    M    = cv2.moments(best)
    return int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])


def build_zone(image: np.ndarray, marker: tuple, cfg: dict) -> np.ndarray:
    h, w = image.shape[:2]
    zone = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(zone, marker, cfg["marker_zone_radius"], 255, -1)
    return zone


def full_zone(image: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    return np.full((h, w), 255, dtype=np.uint8)


def is_in_roi(bbox: tuple, zone: np.ndarray, cfg: dict) -> bool:
    x, y, w, h = bbox
    cx, cy = x + w // 2, y + h // 2
    if zone[cy, cx] > 0:
        return True
    for px, py in [(x, y), (x+w, y), (x, y+h), (x+w, y+h)]:
        px = max(0, min(px, zone.shape[1] - 1))
        py = max(0, min(py, zone.shape[0] - 1))
        if zone[py, px] > 0:
            return True
    return False


# ── Background modeling ────────────────────────────────────────────────────
def compute_global_background(paths: list, cfg: dict) -> Optional[np.ndarray]:
    n = cfg.get("background_sample_size", 0)
    if not n or not paths:
        return None
    step   = max(1, len(paths) // n)
    frames = []
    for i in range(0, len(paths), step):
        img = cv2.imread(str(paths[i]))
        if img is not None:
            frames.append(img.astype(np.float32))
        if len(frames) >= n:
            break
    if not frames:
        return None
    return np.median(np.stack(frames, axis=0), axis=0).astype(np.uint8)


# ── Foreground detection ───────────────────────────────────────────────────
def detect_foreground(current: np.ndarray, background: np.ndarray,
                      zone: np.ndarray, cfg: dict) -> np.ndarray:
    roi_mask = zone > 0
    if roi_mask.any():
        mean_ref = float(cv2.cvtColor(background, cv2.COLOR_BGR2GRAY)[roi_mask].mean())
        mean_cur = float(cv2.cvtColor(current,    cv2.COLOR_BGR2GRAY)[roi_mask].mean())
        if mean_cur > 0:
            scale   = mean_ref / mean_cur
            current = np.clip(current.astype(np.float32) * scale, 0, 255).astype(np.uint8)

    diff     = cv2.absdiff(current, background)
    gray     = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    roi_gray = cv2.bitwise_and(gray, gray, mask=zone)
    blurred  = cv2.GaussianBlur(roi_gray, (5, 5), 0)
    _, mask  = cv2.threshold(blurred, cfg["darker_threshold"], 255, cv2.THRESH_BINARY)

    # Remove green vegetation
    hsv   = cv2.cvtColor(current, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(
        hsv,
        np.array([cfg.get("green_hue_min", 25), cfg.get("green_sat_min", 80), cfg.get("green_val_min", 40)]),
        np.array([cfg.get("green_hue_max", 95), 255, 255]),
    )
    mask = cv2.bitwise_and(mask, cv2.bitwise_not(green))

    kernel_open  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                    (cfg["kernel_open_size"],  cfg["kernel_open_size"]))
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                    (cfg["kernel_close_size"], cfg["kernel_close_size"]))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel_open)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close)
    return mask


# ── Contour filtering ──────────────────────────────────────────────────────
def filter_contours(mask: np.ndarray, cfg: dict) -> list:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    detections  = []
    enable_lm   = cfg.get("enable_large_motion", True)

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < cfg["min_contour_area"]:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        aspect = max(w, h) / max(min(w, h), 1)
        if aspect > cfg["max_aspect_ratio"]:
            continue
        if area > cfg.get("max_large_motion_area", 600000):
            continue
        if area > cfg["max_contour_area"]:
            if enable_lm:
                detections.append({"bbox": (x, y, w, h), "area": area,
                                   "candidate_type": "large_motion"})
        else:
            detections.append({"bbox": (x, y, w, h), "area": area,
                               "candidate_type": "normal"})
    return detections


# ── Crop extraction ────────────────────────────────────────────────────────
def crop_with_padding(image: np.ndarray, det: dict, cfg: dict) -> np.ndarray:
    x, y, w, h = det["bbox"]
    pad  = int(max(w, h) * cfg.get("crop_pad_frac", 0.3))
    ih, iw = image.shape[:2]
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(iw, x + w + pad)
    y2 = min(ih, y + h + pad)
    return image[y1:y2, x1:x2].copy()


# ── CSV helpers ────────────────────────────────────────────────────────────
def init_csv(path: Path, fields: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        csv.DictWriter(f, fieldnames=fields).writeheader()


def write_csv_row(path: Path, row: dict, fields: list):
    with open(path, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=fields).writerow(
            {k: row.get(k, "") for k in fields}
        )


# ── Static suppression ─────────────────────────────────────────────────────
class StaticFilter:
    def __init__(self, cfg: dict):
        self.dist    = cfg.get("static_dist", 80)
        self.max_f   = cfg.get("static_max_frames", 15)
        self.history = {}

    def is_static(self, bbox: tuple) -> bool:
        if not self.dist:
            return False
        x, y, w, h = bbox
        cx, cy = x + w // 2, y + h // 2
        for (hx, hy), count in list(self.history.items()):
            if abs(cx - hx) < self.dist and abs(cy - hy) < self.dist:
                self.history[(hx, hy)] = count + 1
                return count + 1 > self.max_f
        self.history[(cx, cy)] = 1
        return False


# ── Main pipeline function ─────────────────────────────────────────────────
def run_preprocessing(
    image_dir:  str,
    output_dir: str,
    config:     Optional[dict] = None,
    debug:      bool = False,
    debug_csv:  bool = True,
) -> dict:
    """
    Run background subtraction pipeline on a single camera folder.

    IMPORTANT: Camera angle must be consistent throughout the sequence.
    If the camera was repositioned mid-sequence, split the folder at that
    point before running — the pipeline cannot detect angle changes automatically.

    Args:
        image_dir:  Path to folder containing images for one camera plot.
        output_dir: Path to output folder. Creates crops/ and results.csv.
        config:     Optional parameter overrides (merged with DEFAULT_CONFIG).
        debug:      If True, saves debug images to output_dir/debug/.
        debug_csv:  If True, uses full debug CSV fields. If False, researcher CSV.

    Returns:
        dict with keys: csv_path, crop_dir, n_crops, n_skipped
    """
    cfg       = {**DEFAULT_CONFIG, **(config or {})}
    image_dir = Path(image_dir)
    out_dir   = Path(output_dir)
    crop_dir  = out_dir / "crops"
    debug_dir = out_dir / "debug"
    csv_path  = out_dir / "results.csv"
    csv_fields = CSV_FIELDS_DEBUG if debug_csv else CSV_FIELDS_MARIA

    crop_dir.mkdir(parents=True, exist_ok=True)
    if debug:
        debug_dir.mkdir(parents=True, exist_ok=True)

    paths = sorted_images(image_dir)
    if not paths:
        logger.warning(f"No images found in {image_dir}")
        return {"csv_path": str(csv_path), "crop_dir": str(crop_dir),
                "n_crops": 0, "n_skipped": 0}

    cam_prefix = f"{image_dir.parent.name}_{image_dir.name}"
    init_csv(csv_path, csv_fields)

    global_bg = compute_global_background(paths, cfg)

    # ROI from first valid frame
    zone = None
    for p in paths[:10]:
        img = cv2.imread(str(p))
        if img is None:
            continue
        if cfg.get("use_roi", True):
            marker = find_marker(img, cfg)
            if marker:
                zone = build_zone(img, marker, cfg)
                logger.info(f"Marker found at {marker}")
            else:
                logger.warning("No marker found — using full image as ROI")
                zone = full_zone(img)
        else:
            zone = full_zone(img)
        break

    if zone is None:
        first = cv2.imread(str(paths[0]))
        zone  = full_zone(first) if first is not None else np.ones((1080, 1920), dtype=np.uint8) * 255

    static_filter = StaticFilter(cfg) if cfg.get("enable_static_filter") else None
    n_crops   = 0
    n_skipped = 0
    prev_frame = None

    for idx, path in enumerate(paths):
        img = cv2.imread(str(path))
        if img is None:
            logger.warning(f"Could not read {path}")
            continue

        # Strip removal
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
                "camera_path":  cam_prefix,
                "image_name":   rel_id,
                "datetime":     meta["datetime"],
                "weather":      meta["weather"],
                "skip":         True,
                "skip_reason":  meta["skip_reason"],
                "laplacian_var": meta["laplacian_var"],
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
        detections = filter_contours(fg_mask, cfg)

        if not detections:
            write_csv_row(csv_path, {
                "camera_path": cam_prefix, "image_name": rel_id,
                **meta, "pollinator_detected": "no",
            }, csv_fields)
            prev_frame = img
            continue

        for i, det in enumerate(detections):
            bbox   = det["bbox"]
            is_roi = is_in_roi(bbox, zone_crop, cfg)
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
                "camera_path":       cam_prefix,
                "image_name":        rel_id,
                "crop_filename":     crop_fn,
                "datetime":          meta["datetime"],
                "camera_name":       meta["camera_name"],
                "shutter_speed":     meta["shutter_speed"],
                "weather":           meta["weather"],
                "skip":              False,
                "laplacian_var":     meta["laplacian_var"],
                "pollinator_detected": "candidate",
                "detection_scope":   scope,
                "near_marked_flower": str(is_roi),
                "bbox_x": x, "bbox_y": y, "bbox_w": w, "bbox_h": h,
                "candidate_type":    det["candidate_type"],
                "static_suspect":    static_suspect,
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


# ── CLI entry point ────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Arctic pollinator preprocessing pipeline")
    parser.add_argument("--image_dir",         required=True)
    parser.add_argument("--output_dir",        required=True)
    parser.add_argument("--debug",             action="store_true")
    parser.add_argument("--researcher_csv",    action="store_true",
                        help="Use researcher CSV format instead of debug CSV")
    parser.add_argument("--no_large_motion",   action="store_true",
                        help="Disable large motion tiling")
    parser.add_argument("--rolling",           type=int, default=1)
    args = parser.parse_args()

    cfg = {"rolling_window": args.rolling}
    if args.no_large_motion:
        cfg["enable_large_motion"] = False

    result = run_preprocessing(
        image_dir  = args.image_dir,
        output_dir = args.output_dir,
        config     = cfg,
        debug      = args.debug,
        debug_csv  = not args.researcher_csv,
    )
    print(f"Crops saved:    {result['n_crops']}")
    print(f"Frames skipped: {result['n_skipped']}")
    print(f"CSV:            {result['csv_path']}")