"""
Default configuration for the background-subtraction preprocessing pipeline,
plus CSV field definitions for the internal results CSV.
"""

DEFAULT_CONFIG = {
    # Background computation
    # 0 = skip global background entirely, use frame-to-frame diff only
    'background_sample_size': 0,
    # Background subtraction threshold
    'darker_threshold': 30,
    # Contour filtering
    'min_contour_area': 400,
    'max_contour_area': 35000,
    # Large motion handling (bumblebee + flower displacement)
    # Set enable_large_motion=False to skip entirely if not needed
    'enable_large_motion': True,
    'max_large_motion_area': 600000,
    'large_motion_tile_sizes': [320, 512],
    'large_motion_tile_stride_frac': 0.65,
    'large_motion_max_tiles_per_size': 6,
    'large_motion_max_tiles_total': 10,
    'large_motion_tile_nms_iou': 0.35,
    'large_motion_min_fg_frac': 0.008,
    'large_motion_context_pad': 10,
    'large_motion_fallback_sizes': [640],
    'large_motion_fallback_centers': [(0.35, 0.78), (0.50, 0.78), (0.65, 0.78)],
    'large_motion_max_fallbacks': 3,
    'large_motion_fallback_min_fg_frac': 0.003,
    'min_crop_px': 10,
    'merge_dist': 20,
    'max_aspect_ratio': 5,
    'kernel_open_size': 3,
    'kernel_close_size': 11,
    'min_texture': 50,
    # Static detection suppression
    'enable_static_filter': False,
    'static_dist': 80,
    'static_max_frames': 15,
    # ROI: caller provides an explicit rectangle (e.g. from the UI) or omits
    # the field for full-image processing. Marker auto-detection lives in
    # preprocessing.roi.find_marker as a primitive callers can use to
    # populate roi_bbox; the pipeline itself never auto-detects.
    'roi_bbox': None,  # (x, y, w, h) or None
    # Background-reference gap reset. When EXIF time between successive frames
    # exceeds this many seconds, the previous frame is no longer a valid
    # background reference (lighting/camera changed) so we clear it and let
    # the next frame restart from the global background or skip detection.
    'max_gap_seconds': 3600,  # 1 hour
    # Quality filtering
    'skip_flash': True,
    'skip_foggy': True,
    'foggy_threshold': 50,
    # Crop extraction
    'crop_pad_frac': 0.3,
    'crop_mode': 'all',
    'strip_height': 120,  # px to remove from bottom (Wingscapes info bar)
    # Green vegetation filter
    'green_hue_min': 25,
    'green_hue_max': 95,
    'green_sat_min': 80,
    'green_val_min': 40,
    # Classification
    'skip_classification': False,
    'binary_threshold': 0.5,
}

CSV_FIELDS_DEBUG = [
    'camera_path',
    'image_name',
    'crop_filename',
    'datetime',
    'camera_name',
    'skip',
    'skip_reason',
    'laplacian_var',
    'shutter_speed',
    'weather',
    'pollinator_detected',
    'bbox_x',
    'bbox_y',
    'bbox_w',
    'bbox_h',
    'detection_scope',
    'inside_roi',
    'candidate_type',
    'static_suspect',
    'source_area',
    'binary_label',
    'binary_confidence',
    'pollinator_type',
    'group_confidence',
    'bumblebee_prob',
    'fly_prob',
    'butterfly_prob',
    'other_prob',
]

CSV_FIELDS_MARIA = [
    'camera_path',
    'image_name',
    'crop_filename',
    'datetime',
    'weather',
    'pollinator_detected',
    'inside_roi',
    'pollinator_type',
    'binary_confidence',
    'group_confidence',
]
