"""
preprocessing/background.py
============================
Background modeling, foreground detection, contour filtering with large-motion
tiling, and crop extraction. Also hosts StaticFilter, which suppresses bbox
locations that appear repeatedly across frames (e.g. wind-blown flowers).

Large-motion handling: when a contour exceeds max_contour_area but stays under
max_large_motion_area, the region is split into multi-scale square tiles. Each
tile is scored by foreground density and texture, then NMS removes near-
duplicates. Fallback crops at biased-low positions catch the bumblebee-pulling-
flower case where the insect sits near the bottom of the motion region.

Tile sizes (large_motion_tile_sizes, large_motion_fallback_sizes) should be
tuned if working with unusually large species; the defaults (320, 512, 640)
comfortably cover bumblebees and butterflies up to ~640px on a side.
"""

from typing import Optional

import cv2
import numpy as np


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

    hsv   = cv2.cvtColor(current, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(
        hsv,
        np.array([cfg.get("green_hue_min", 25), cfg.get("green_sat_min", 80), cfg.get("green_val_min", 40)]),
        np.array([cfg.get("green_hue_max", 95), 255, 255]),
    )
    mask = cv2.bitwise_and(mask, cv2.bitwise_not(green))

    kernel_open  = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (cfg["kernel_open_size"],  cfg["kernel_open_size"])
    )
    kernel_close = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (cfg["kernel_close_size"], cfg["kernel_close_size"])
    )
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel_open)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close)
    return mask


def _make_detection(bbox, candidate_type="normal",
                    source_area=None, source_bbox=None) -> dict:
    return {
        "bbox":           tuple(int(v) for v in bbox),
        "candidate_type": candidate_type,
        "source_area":    float(source_area) if source_area is not None else "",
        "source_bbox":    tuple(int(v) for v in source_bbox) if source_bbox is not None else tuple(int(v) for v in bbox),
    }


def _bbox_iou(a: tuple, b: tuple) -> float:
    """IoU for two (x, y, w, h) boxes."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    iw, ih   = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter    = iw * ih
    union    = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _tile_score(image: np.ndarray, mask: np.ndarray, bbox: tuple) -> float:
    """
    Score a candidate tile. Rewards moderate foreground content and visual
    texture; penalises tiles that are almost entirely foreground (which
    typically indicates a moving flower or background patch rather than an
    insect against background).
    """
    x, y, w, h = bbox
    tile_mask = mask[y:y+h, x:x+w]
    tile_img  = image[y:y+h, x:x+w]
    if tile_mask.size == 0 or tile_img.size == 0:
        return 0.0

    fg_frac = np.count_nonzero(tile_mask) / float(w * h)
    gray    = cv2.cvtColor(tile_img, cv2.COLOR_BGR2GRAY)
    texture = min(float(gray.std()) / 80.0, 1.0)

    fg_score = min(fg_frac / 0.12, 1.0)
    if fg_frac > 0.45:
        fg_score *= 0.75

    return 0.65 * fg_score + 0.35 * texture


def _select_tiles_with_nms(scored_tiles: list, max_tiles: int,
                           iou_threshold: float) -> list:
    """Greedy NMS over (score, bbox) pairs, returning the top non-overlapping ones."""
    selected = []
    for score, bbox in sorted(scored_tiles, key=lambda item: item[0], reverse=True):
        if all(_bbox_iou(bbox, kept_bbox) <= iou_threshold for _, kept_bbox in selected):
            selected.append((score, bbox))
        if len(selected) >= max_tiles:
            break
    return selected


def _tile_large_motion_region(image: np.ndarray, mask: np.ndarray,
                              bbox: tuple, cfg: dict) -> list:
    """
    Split a large motion region into a bounded set of multi-scale square tiles.
    Returns a list of (x, y, w, h) bboxes.
    """
    x, y, w, h = bbox
    H, W = mask.shape[:2]

    tile_sizes   = [int(t) for t in cfg.get("large_motion_tile_sizes", [320, 512])]
    stride_frac  = float(cfg.get("large_motion_tile_stride_frac", 0.65))
    max_per_size = int(cfg.get("large_motion_max_tiles_per_size", 6))
    max_total    = int(cfg.get("large_motion_max_tiles_total", 10))
    min_fg_frac  = float(cfg.get("large_motion_min_fg_frac", 0.008))
    nms_iou      = float(cfg.get("large_motion_tile_nms_iou", 0.35))

    all_scored = []
    seen       = set()

    for tile in tile_sizes:
        tile = min(tile, W, H)
        if tile <= 0:
            continue
        stride = max(1, int(tile * stride_frac))

        xs = list(range(x, max(x + w - tile + 1, x + 1), stride))
        ys = list(range(y, max(y + h - tile + 1, y + 1), stride))
        if not xs:
            xs = [x + w // 2 - tile // 2]
        if not ys:
            ys = [y + h // 2 - tile // 2]
        xs.append(x + w - tile)
        ys.append(y + h - tile)

        scored_for_size = []
        for yy in ys:
            for xx in xs:
                xx = max(0, min(int(xx), W - tile)) if W > tile else 0
                yy = max(0, min(int(yy), H - tile)) if H > tile else 0
                tw = min(tile, W - xx)
                th = min(tile, H - yy)
                key = (xx, yy, tw, th)
                if key in seen or tw <= 0 or th <= 0:
                    continue
                fg_frac = np.count_nonzero(mask[yy:yy+th, xx:xx+tw]) / float(tw * th)
                if fg_frac < min_fg_frac:
                    continue
                seen.add(key)
                scored_for_size.append((_tile_score(image, mask, key), key))

        all_scored.extend(_select_tiles_with_nms(scored_for_size, max_per_size, nms_iou))

    return [bb for _, bb in _select_tiles_with_nms(all_scored, max_total, nms_iou)]


def _fixed_square_bbox(cx: float, cy: float, size: int,
                       image_w: int, image_h: int) -> tuple:
    """Square bbox of `size` pixels centered at (cx, cy), clipped to image bounds."""
    size = int(size)
    half = size // 2
    x1   = int(round(cx - half))
    y1   = int(round(cy - half))
    x1   = max(0, min(x1, max(0, image_w - size)))
    y1   = max(0, min(y1, max(0, image_h - size)))
    x2   = min(image_w, x1 + size)
    y2   = min(image_h, y1 + size)
    return (x1, y1, x2 - x1, y2 - y1)


def _large_motion_fallback_crops(mask: np.ndarray, bbox: tuple, cfg: dict) -> list:
    """
    Extra crops biased toward the lower part of the motion region. Catches
    the case where a pollinator is pulling a flower or stem and sits at the
    bottom of the motion region while the regular tiles cluster around the
    centre (which is usually flower).
    """
    x, y, w, h = bbox
    H, W = mask.shape[:2]
    sizes         = [int(v) for v in cfg.get("large_motion_fallback_sizes", [640])]
    centers       = cfg.get("large_motion_fallback_centers", [(0.35, 0.78), (0.50, 0.78), (0.65, 0.78)])
    max_fallbacks = int(cfg.get("large_motion_max_fallbacks", 3))
    min_fg_frac   = float(cfg.get("large_motion_fallback_min_fg_frac", 0.003))

    crops = []
    seen  = set()
    for size in sizes:
        size = min(size, W, H)
        if size <= 0:
            continue
        for rx, ry in centers:
            cx = x + w * float(rx)
            cy = y + h * float(ry)
            bx = _fixed_square_bbox(cx, cy, size, W, H)
            if bx in seen:
                continue
            bx0, by0, bw, bh = bx
            if bw <= 0 or bh <= 0:
                continue
            fg_frac = np.count_nonzero(mask[by0:by0+bh, bx0:bx0+bw]) / float(bw * bh)
            if fg_frac < min_fg_frac:
                continue
            seen.add(bx)
            crops.append(bx)
            if len(crops) >= max_fallbacks:
                return crops
    return crops


def filter_contours(image: np.ndarray, mask: np.ndarray, cfg: dict) -> list:
    """
    Find candidate detections from the foreground mask.

    Normal-sized contours become one detection each. Contours larger than
    max_contour_area but smaller than max_large_motion_area are split into
    multi-scale tiles plus biased-low fallback crops, all tagged
    candidate_type='large_motion_tile' or 'large_motion_fallback'. Contours
    above max_large_motion_area are dropped entirely.
    """
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    detections  = []
    enable_lm   = cfg.get("enable_large_motion", True)
    max_lm_area = cfg.get("max_large_motion_area", 600000)
    max_area    = cfg["max_contour_area"]

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < cfg["min_contour_area"]:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        aspect = max(w, h) / max(min(w, h), 1)
        if aspect > cfg["max_aspect_ratio"]:
            continue
        if area > max_lm_area:
            continue

        if area > max_area:
            if not enable_lm:
                continue
            source_bbox = (x, y, w, h)
            tiles = _tile_large_motion_region(image, mask, source_bbox, cfg)
            for tile_bbox in tiles:
                detections.append(_make_detection(
                    tile_bbox,
                    candidate_type="large_motion_tile",
                    source_area=area,
                    source_bbox=source_bbox,
                ))
            for fb_bbox in _large_motion_fallback_crops(mask, source_bbox, cfg):
                detections.append(_make_detection(
                    fb_bbox,
                    candidate_type="large_motion_fallback",
                    source_area=area,
                    source_bbox=source_bbox,
                ))
        else:
            detections.append(_make_detection(
                (x, y, w, h),
                candidate_type="normal",
                source_area=area,
            ))
    return detections


def crop_with_padding(image: np.ndarray, det: dict, cfg: dict) -> np.ndarray:
    x, y, w, h = det["bbox"]
    pad        = int(max(w, h) * cfg.get("crop_pad_frac", 0.3))
    ih, iw     = image.shape[:2]
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(iw, x + w + pad)
    y2 = min(ih, y + h + pad)
    return image[y1:y2, x1:x2].copy()


class StaticFilter:
    """
    Tracks bbox centers across frames and flags locations that recur more
    than max_frames times within a distance tolerance. Used to suppress
    repeatedly-detected static objects like wind-blown flowers.
    """

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
