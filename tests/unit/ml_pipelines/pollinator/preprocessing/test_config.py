"""Sanity guards for the default motion-detection config.

These do not pin every value (the tuning is allowed to change); they assert the
structural invariants that downstream code relies on, so an accidental edit that
breaks one is caught loudly.
"""

from ml_pipelines.pollinator.preprocessing.config import DEFAULT_CONFIG


def test_roi_bbox_defaults_to_none():
    # None means full-image processing; the pipeline branches on this.
    assert DEFAULT_CONFIG['roi_bbox'] is None


def test_contour_area_bounds_are_ordered():
    assert DEFAULT_CONFIG['min_contour_area'] < DEFAULT_CONFIG['max_contour_area']


def test_green_hue_bounds_are_ordered():
    assert DEFAULT_CONFIG['green_hue_min'] < DEFAULT_CONFIG['green_hue_max']


def test_quality_gates_are_enabled_by_default():
    assert DEFAULT_CONFIG['skip_flash'] is True
    assert DEFAULT_CONFIG['skip_foggy'] is True


def test_required_keys_present():
    required = {
        'darker_threshold',
        'min_contour_area',
        'max_contour_area',
        'max_gap_seconds',
        'foggy_threshold',
        'sunny_shutter_threshold',
        'crop_pad_frac',
        'strip_height',
    }
    assert required <= DEFAULT_CONFIG.keys()
