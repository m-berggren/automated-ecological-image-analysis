"""Default configuration for the motion-detection branch of the pipeline.

Only keys that are actually read by ``background.py``, ``roi.py``,
``exif.py``, or ``workflows/inference.py`` live here. Anything else has
been removed during the dead-code sweep.
"""

DEFAULT_CONFIG = {
    # Background computation.
    # 0 = skip global background entirely, use frame-to-frame diff only.
    'background_sample_size': 0,
    # Background subtraction threshold.
    'darker_threshold': 15,
    # Contour filtering.
    'min_contour_area': 400,
    'max_contour_area': 35000,
    'max_aspect_ratio': 5,
    'kernel_open_size': 3,
    'kernel_close_size': 11,
    # Large motion handling (bumblebee + flower displacement).
    'enable_large_motion': True,
    'max_large_motion_area': 600000,
    'large_motion_tile_sizes': [320, 512],
    'large_motion_tile_stride_frac': 0.65,
    'large_motion_max_tiles_per_size': 6,
    'large_motion_max_tiles_total': 10,
    'large_motion_tile_nms_iou': 0.35,
    'large_motion_min_fg_frac': 0.008,
    'large_motion_fallback_sizes': [640],
    'large_motion_fallback_centers': [(0.35, 0.78), (0.50, 0.78), (0.65, 0.78)],
    'large_motion_max_fallbacks': 3,
    'large_motion_fallback_min_fg_frac': 0.003,
    # Static detection suppression.
    'enable_static_filter': False,
    'static_dist': 80,
    'static_max_frames': 15,
    # ROI: caller provides an explicit rectangle (e.g. from the UI) or
    # omits the field for full-image processing.
    'roi_bbox': None,  # (x, y, w, h) or None
    # Background-reference gap reset. When EXIF time between successive
    # frames exceeds this many seconds, the previous frame is no longer a
    # valid background reference (lighting/camera changed); the next frame
    # restarts from the global background or skips detection.
    'max_gap_seconds': 3600,
    # Quality filtering. A flagged frame is skipped entirely: no YOLO, no
    # motion-branch crops, zero detections recorded.
    'skip_flash': True,
    'skip_foggy': True,
    'foggy_threshold': 50,
    # Crop extraction.
    'crop_pad_frac': 0.3,
    'strip_height': 120,  # px to remove from bottom (Wingscapes info bar)
    # Green vegetation filter (subtracted from the foreground mask before
    # contour extraction).
    'green_hue_min': 25,
    'green_hue_max': 95,
    'green_sat_min': 80,
    'green_val_min': 40,
    # EXIF weather classification (sunny vs cloudy from shutter speed).
    'sunny_shutter_threshold': 200,
}
