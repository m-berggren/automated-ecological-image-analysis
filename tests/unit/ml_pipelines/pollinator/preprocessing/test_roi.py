"""Unit tests for ml_pipelines.pollinator.preprocessing.roi."""

import cv2
import numpy as np
import pytest

from ml_pipelines.pollinator.preprocessing import roi


class TestBboxXywh:
    def test_dict_form_coerced_to_int_tuple(self):
        bbox = {'x': 1.9, 'y': 2.1, 'width': 30.7, 'height': 40.2}
        assert roi._bbox_xywh(bbox) == (1, 2, 30, 40)

    def test_sequence_form_coerced_to_int_tuple(self):
        assert roi._bbox_xywh([1.9, 2.1, 30.7, 40.2]) == (1, 2, 30, 40)

    def test_dict_and_sequence_round_trip_to_same_value(self):
        seq = (5, 6, 7, 8)
        as_dict = {'x': 5, 'y': 6, 'width': 7, 'height': 8}
        assert roi._bbox_xywh(seq) == roi._bbox_xywh(as_dict)


class TestBuildZoneFromBbox:
    def test_marks_only_the_bbox_region(self):
        zone = roi.build_zone_from_bbox((100, 100), (10, 20, 30, 40))
        assert zone.shape == (100, 100)
        assert zone.dtype == np.uint8
        assert zone[20, 10] == 255
        assert zone[59, 39] == 255  # last row/col inside the box
        assert zone[60, 40] == 0  # just outside
        assert zone[0, 0] == 0

    def test_bbox_is_clamped_to_image_bounds(self):
        # Origin and size exceed the image; nothing should index out of range.
        zone = roi.build_zone_from_bbox((50, 50), (40, 40, 999, 999))
        assert zone.shape == (50, 50)
        assert zone[49, 49] == 255
        assert zone[39, 39] == 0

    def test_negative_origin_does_not_wrap(self):
        zone = roi.build_zone_from_bbox((50, 50), (-10, -10, 20, 20))
        # x/y clamp to 0, so the painted region starts at the origin.
        assert zone[0, 0] == 255


class TestFullZone:
    def test_all_pixels_set(self):
        img = np.zeros((8, 12, 3), dtype=np.uint8)
        zone = roi.full_zone(img)
        assert zone.shape == (8, 12)
        assert zone.dtype == np.uint8
        assert np.all(zone == 255)


class TestSetupZone:
    def test_uses_bbox_when_present(self):
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        zone = roi.setup_zone(img, {'roi_bbox': (0, 0, 10, 10)})
        assert zone[5, 5] == 255
        assert zone[50, 50] == 0

    def test_falls_back_to_full_image_without_bbox(self):
        img = np.zeros((20, 20, 3), dtype=np.uint8)
        zone = roi.setup_zone(img, {})
        assert np.all(zone == 255)

    def test_none_bbox_is_full_image(self):
        img = np.zeros((20, 20, 3), dtype=np.uint8)
        zone = roi.setup_zone(img, {'roi_bbox': None})
        assert np.all(zone == 255)


class TestIsInRoi:
    @pytest.fixture
    def zone(self):
        z = np.zeros((100, 100), dtype=np.uint8)
        z[40:60, 40:60] = 255
        return z

    def test_box_centered_inside_zone(self, zone):
        assert roi.is_in_roi((45, 45, 8, 8), zone) is True

    def test_box_fully_outside_zone(self, zone):
        assert roi.is_in_roi((0, 0, 5, 5), zone) is False

    def test_box_with_corner_inside_zone(self, zone):
        # Center sits outside the mask but a corner lands inside it.
        assert roi.is_in_roi((35, 35, 10, 10), zone) is True

    def test_corner_index_is_clamped_to_image(self, zone):
        # A box whose corners exceed the image must not raise.
        assert roi.is_in_roi((95, 95, 20, 20), zone) is False


class TestMarkerHelpers:
    def test_find_marker_returns_none_for_blank_image(self):
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        cfg = {
            'marker_hue': (40, 80),
            'marker_sat_min': 100,
            'marker_val_min': 100,
            'marker_min_area': 10,
        }
        assert roi.find_marker(img, cfg) is None

    def test_find_marker_returns_centroid_of_blob(self):
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        # Pure green (BGR) maps to hue 60 in OpenCV's 0-179 HSV range.
        cv2.rectangle(img, (40, 40), (60, 60), (0, 255, 0), -1)
        cfg = {
            'marker_hue': (40, 80),
            'marker_sat_min': 100,
            'marker_val_min': 100,
            'marker_min_area': 10,
        }
        cx, cy = roi.find_marker(img, cfg)
        assert abs(cx - 50) <= 1
        assert abs(cy - 50) <= 1

    def test_build_marker_zone_sets_center_pixel(self):
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        zone = roi.build_marker_zone(img, (50, 50), radius=10)
        assert zone.shape == (100, 100)
        assert zone[50, 50] == 255
        assert zone[0, 0] == 0
