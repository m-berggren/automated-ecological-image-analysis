"""Unit tests for ml_pipelines.pollinator.preprocessing.background.

Focuses on the pure geometry/bookkeeping helpers and the StaticFilter state
machine. The cv2-heavy mask pipeline (detect_foreground, the tiling search) is
covered only by a single filter_contours smoke test; full motion behaviour
belongs in an integration test against real frames.
"""

import cv2
import numpy as np

from ml_pipelines.pollinator.preprocessing import background
from ml_pipelines.pollinator.preprocessing.config import DEFAULT_CONFIG


class TestBboxIou:
    def test_identical_boxes(self):
        assert background._bbox_iou((0, 0, 2, 2), (0, 0, 2, 2)) == 1.0

    def test_half_overlap(self):
        # inter=2, union=4+4-2=6 -> 1/3.
        assert background._bbox_iou((0, 0, 2, 2), (1, 0, 2, 2)) == 1 / 3

    def test_disjoint_boxes(self):
        assert background._bbox_iou((0, 0, 2, 2), (100, 100, 2, 2)) == 0.0


class TestFixedSquareBbox:
    def test_centered_square(self):
        assert background._fixed_square_bbox(50, 50, 20, 100, 100) == (40, 40, 20, 20)

    def test_clipped_to_right_bottom_edge(self):
        assert background._fixed_square_bbox(95, 95, 20, 100, 100) == (80, 80, 20, 20)

    def test_size_larger_than_image_fills_image(self):
        assert background._fixed_square_bbox(50, 50, 200, 100, 100) == (0, 0, 100, 100)


class TestMakeDetection:
    def test_defaults_coerce_to_int_and_mirror_bbox(self):
        det = background._make_detection((1.9, 2.1, 3.0, 4.0))
        assert det['bbox'] == (1, 2, 3, 4)
        assert det['candidate_type'] == 'normal'
        assert det['source_area'] == ''  # sentinel for "not provided"
        assert det['source_bbox'] == (1, 2, 3, 4)  # defaults to the bbox

    def test_explicit_source_fields(self):
        det = background._make_detection(
            (0, 0, 5, 5),
            candidate_type='large_motion_tile',
            source_area=1234.0,
            source_bbox=(1, 1, 50, 50),
        )
        assert det['source_area'] == 1234.0
        assert det['source_bbox'] == (1, 1, 50, 50)


class TestSelectTilesWithNms:
    def test_suppresses_overlap_keeps_distinct(self):
        scored = [
            (0.9, (0, 0, 10, 10)),
            (0.8, (1, 1, 10, 10)),  # heavy overlap with the top box
            (0.5, (100, 100, 10, 10)),  # far away, survives
        ]
        kept = background._select_tiles_with_nms(scored, max_tiles=5, iou_threshold=0.3)
        kept_boxes = [bb for _, bb in kept]
        assert kept_boxes == [(0, 0, 10, 10), (100, 100, 10, 10)]

    def test_respects_max_tiles(self):
        scored = [(0.9, (0, 0, 10, 10)), (0.5, (100, 100, 10, 10))]
        kept = background._select_tiles_with_nms(scored, max_tiles=1, iou_threshold=0.3)
        assert len(kept) == 1
        assert kept[0][1] == (0, 0, 10, 10)


class TestTileScore:
    def test_zero_size_tile_scores_zero(self):
        image = np.zeros((10, 10, 3), dtype=np.uint8)
        mask = np.zeros((10, 10), dtype=np.uint8)
        assert background._tile_score(image, mask, (0, 0, 0, 0)) == 0.0

    def test_moderate_foreground_no_penalty(self):
        # Uniform image -> texture term 0, so score is purely the fg term.
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        mask = np.zeros((100, 100), dtype=np.uint8)
        mask[:, :30] = 255  # 30% foreground, below the 0.45 penalty cutoff
        # fg_score = min(0.30/0.12, 1) = 1.0 -> 0.65 * 1.0 + 0.35 * 0.
        assert background._tile_score(image, mask, (0, 0, 100, 100)) == 0.65

    def test_high_foreground_is_penalised(self):
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        mask = np.full((100, 100), 255, dtype=np.uint8)  # 100% fg -> > 0.45
        # fg_score = 1.0 * 0.75 -> 0.65 * 0.75 + 0.35 * 0.
        assert background._tile_score(image, mask, (0, 0, 100, 100)) == 0.65 * 0.75


class TestCropWithPadding:
    def test_pads_and_returns_expected_shape(self):
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        det = {'bbox': (40, 40, 20, 20)}
        crop = background.crop_with_padding(image, det, {'crop_pad_frac': 0.3})
        # pad = int(20 * 0.3) = 6 -> 32x32 region.
        assert crop.shape == (32, 32, 3)

    def test_padding_clipped_at_image_border(self):
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        det = {'bbox': (90, 90, 20, 20)}
        crop = background.crop_with_padding(image, det, {'crop_pad_frac': 0.3})
        assert crop.shape == (16, 16, 3)


class TestStaticFilter:
    def test_recurring_location_flags_after_threshold(self):
        sf = background.StaticFilter({'static_dist': 80, 'static_max_frames': 2})
        assert sf.is_static((0, 0, 0, 0)) is False  # first sighting
        assert sf.is_static((10, 10, 0, 0)) is False  # 2nd, not over threshold
        assert sf.is_static((10, 10, 0, 0)) is True  # 3rd > max_frames

    def test_disabled_when_dist_zero(self):
        sf = background.StaticFilter({'static_dist': 0})
        assert sf.is_static((0, 0, 0, 0)) is False
        assert sf.is_static((0, 0, 0, 0)) is False

    def test_distant_locations_tracked_separately(self):
        sf = background.StaticFilter({'static_dist': 5, 'static_max_frames': 1})
        assert sf.is_static((0, 0, 0, 0)) is False
        # Far from the first center, so it starts its own count rather than
        # incrementing the existing one.
        assert sf.is_static((100, 100, 0, 0)) is False


class TestFilterContours:
    def test_single_normal_contour(self):
        cfg = dict(DEFAULT_CONFIG)
        image = np.zeros((200, 200, 3), dtype=np.uint8)
        mask = np.zeros((200, 200), dtype=np.uint8)
        mask[50:100, 50:100] = 255  # 50x50 blob, within [min, max] contour area

        dets = background.filter_contours(image, mask, cfg)
        assert len(dets) == 1
        assert dets[0]['candidate_type'] == 'normal'
        assert dets[0]['bbox'] == (50, 50, 50, 50)

    def test_contour_below_min_area_is_dropped(self):
        cfg = dict(DEFAULT_CONFIG)
        image = np.zeros((200, 200, 3), dtype=np.uint8)
        mask = np.zeros((200, 200), dtype=np.uint8)
        mask[50:65, 50:65] = 255  # ~15x15, area well under min_contour_area (400)
        assert background.filter_contours(image, mask, cfg) == []

    def test_extreme_aspect_ratio_is_dropped(self):
        cfg = dict(DEFAULT_CONFIG)
        image = np.zeros((200, 200, 3), dtype=np.uint8)
        mask = np.zeros((200, 200), dtype=np.uint8)
        mask[50:58, 20:140] = 255  # 120x8: area in range, aspect 15 > max_aspect_ratio
        assert background.filter_contours(image, mask, cfg) == []

    def test_contour_above_large_motion_cap_is_dropped(self):
        cfg = dict(DEFAULT_CONFIG)
        image = np.zeros((900, 900, 3), dtype=np.uint8)
        mask = np.zeros((900, 900), dtype=np.uint8)
        mask[0:800, 0:800] = 255  # 640000 px > max_large_motion_area (600000)
        assert background.filter_contours(image, mask, cfg) == []

    def test_large_contour_skipped_when_large_motion_disabled(self):
        cfg = dict(DEFAULT_CONFIG)
        cfg['enable_large_motion'] = False
        image = np.zeros((300, 300, 3), dtype=np.uint8)
        mask = np.zeros((300, 300), dtype=np.uint8)
        mask[20:270, 20:270] = 255  # 62500 px: above max_contour_area, below the cap
        assert background.filter_contours(image, mask, cfg) == []

    def test_large_contour_produces_tiled_candidates(self):
        cfg = dict(DEFAULT_CONFIG)  # enable_large_motion defaults True
        image = np.zeros((800, 800, 3), dtype=np.uint8)
        mask = np.zeros((800, 800), dtype=np.uint8)
        mask[100:350, 100:350] = 255  # 62500 px: large-motion tiling range

        dets = background.filter_contours(image, mask, cfg)
        assert len(dets) > 0
        types = {d['candidate_type'] for d in dets}
        assert types <= {'large_motion_tile', 'large_motion_fallback'}
        assert 'large_motion_tile' in types
        # All carry the originating contour bbox.
        assert all(d['source_bbox'] == (100, 100, 250, 250) for d in dets)


class TestComputeGlobalBackground:
    def test_returns_none_when_sampling_disabled(self):
        assert background.compute_global_background(['a.jpg'], {}) is None

    def test_returns_none_for_empty_paths(self):
        assert (
            background.compute_global_background([], {'background_sample_size': 2})
            is None
        )

    def test_median_of_identical_frames(self, tmp_path):
        paths = []
        for i in range(2):
            p = tmp_path / f'f{i}.png'
            cv2.imwrite(str(p), np.full((10, 10, 3), 100, dtype=np.uint8))
            paths.append(str(p))
        bg = background.compute_global_background(paths, {'background_sample_size': 2})
        assert bg.shape == (10, 10, 3)
        assert bg.dtype == np.uint8
        assert np.all(bg == 100)


class TestDetectForeground:
    def _zone(self, size):
        return np.full((size, size), 255, dtype=np.uint8)

    def test_no_change_yields_empty_mask(self):
        cfg = dict(DEFAULT_CONFIG)
        frame = np.full((60, 60, 3), 100, dtype=np.uint8)
        mask = background.detect_foreground(frame, frame, self._zone(60), cfg)
        assert mask.shape == (60, 60)
        assert np.count_nonzero(mask) == 0

    def test_bright_patch_is_detected(self):
        cfg = dict(DEFAULT_CONFIG)
        bg = np.full((60, 60, 3), 100, dtype=np.uint8)
        cur = bg.copy()
        cur[25:40, 25:40] = 200  # desaturated grey patch survives the green filter
        mask = background.detect_foreground(cur, bg, self._zone(60), cfg)
        assert np.count_nonzero(mask) > 0


class TestLargeMotionHelpers:
    def test_tile_region_returns_bounded_in_image_tiles(self):
        cfg = dict(DEFAULT_CONFIG)
        image = np.zeros((800, 800, 3), dtype=np.uint8)
        mask = np.zeros((800, 800), dtype=np.uint8)
        mask[100:700, 100:700] = 255
        tiles = background._tile_large_motion_region(
            image, mask, (100, 100, 600, 600), cfg
        )
        assert 0 < len(tiles) <= cfg['large_motion_max_tiles_total']
        for x, y, w, h in tiles:
            assert x >= 0 and y >= 0
            assert x + w <= 800 and y + h <= 800

    def test_fallback_crops_target_lower_region(self):
        cfg = dict(DEFAULT_CONFIG)
        mask = np.zeros((800, 800), dtype=np.uint8)
        mask[500:800, 200:600] = 255  # foreground biased toward the bottom
        crops = background._large_motion_fallback_crops(mask, (0, 0, 800, 800), cfg)
        assert 0 < len(crops) <= cfg['large_motion_max_fallbacks']
        for x, y, w, h in crops:
            assert x + w <= 800 and y + h <= 800
