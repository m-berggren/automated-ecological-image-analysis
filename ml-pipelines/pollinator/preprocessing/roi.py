"""
preprocessing/roi.py
=====================
ROI primitives.

The pipeline does not decide how an ROI is chosen. It receives one rectangle
in cfg['roi_bbox'] (or nothing, meaning full image) and builds a zone from it.
Marker auto-detection lives here as a primitive that the application layer
(future preview endpoint, CLI helper, etc.) can call to suggest a default
rectangle, but the pipeline itself never calls find_marker.
"""

from typing import Optional

import cv2
import numpy as np


def find_marker(image: np.ndarray, cfg: dict) -> Optional[tuple]:
    """
    Locate a coloured marker clip in the image (HSV-thresholded, picks the
    cluster nearest the image center). Returns (cx, cy) or None.
    """
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


def build_marker_zone(image: np.ndarray, marker: tuple, radius: int) -> np.ndarray:
    """Circular zone of the given radius centered at the marker."""
    h, w = image.shape[:2]
    zone = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(zone, marker, radius, 255, -1)
    return zone


def build_zone_from_bbox(image_shape: tuple, bbox: tuple) -> np.ndarray:
    """Rectangular zone from an explicit (x, y, w, h) bbox."""
    h, w = image_shape[:2]
    zone = np.zeros((h, w), dtype=np.uint8)
    x, y, bw, bh = (int(v) for v in bbox)
    x  = max(0, min(x, w))
    y  = max(0, min(y, h))
    bw = max(0, min(bw, w - x))
    bh = max(0, min(bh, h - y))
    zone[y:y+bh, x:x+bw] = 255
    return zone


def full_zone(image: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    return np.full((h, w), 255, dtype=np.uint8)


def setup_zone(first_image: np.ndarray, cfg: dict) -> np.ndarray:
    """
    Build the detection zone for a camera folder.

    Priority:
        cfg['roi_bbox'] = [x, y, w, h]  -> rectangular zone from that bbox
        otherwise                       -> full image
    """
    bbox = cfg.get("roi_bbox")
    if bbox is not None:
        return build_zone_from_bbox(first_image.shape, bbox)
    return full_zone(first_image)


def is_in_roi(bbox: tuple, zone: np.ndarray) -> bool:
    """True if the bbox center or any corner falls inside the zone mask."""
    x, y, w, h = bbox
    cx, cy = x + w // 2, y + h // 2
    if zone[cy, cx] > 0:
        return True
    for px, py in [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]:
        px = max(0, min(px, zone.shape[1] - 1))
        py = max(0, min(py, zone.shape[0] - 1))
        if zone[py, px] > 0:
            return True
    return False
