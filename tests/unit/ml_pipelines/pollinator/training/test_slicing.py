"""Unit tests for ml_pipelines.pollinator.training.slicing.

Covers the pure tiling helpers plus one end-to-end slice over a real (small)
PIL image so the full read/clip/write path is exercised.
"""

import pytest
from PIL import Image


@pytest.fixture(scope='session')
def slicing(load_leaf):
    return load_leaf('pollinator/training/slicing.py')


class TestTileOrigins:
    def test_extent_not_larger_than_tile_is_single_origin(self, slicing):
        assert slicing._tile_origins(500, 640, 0.2) == [0]
        assert slicing._tile_origins(640, 640, 0.2) == [0]

    def test_last_origin_is_right_aligned_to_edge(self, slicing):
        # stride = int(640 * 0.8) = 512.
        assert slicing._tile_origins(1000, 640, 0.2) == [0, 360]
        assert slicing._tile_origins(1280, 640, 0.2) == [0, 512, 640]


class TestParseYoloLine:
    def test_valid_line_to_pixel_corners(self, slicing):
        assert slicing._parse_yolo_line('0 0.5 0.5 0.5 0.5', 100, 100) == (
            0,
            25.0,
            25.0,
            75.0,
            75.0,
        )

    def test_blank_line_returns_none(self, slicing):
        assert slicing._parse_yolo_line('   ', 100, 100) is None

    def test_malformed_line_returns_none(self, slicing):
        assert slicing._parse_yolo_line('0 foo bar', 100, 100) is None


class TestClipToTile:
    def test_box_partially_clipped_to_tile_local_coords(self, slicing):
        box = (0, 25, 25, 75, 75)
        clipped = slicing._clip_to_tile(box, (0, 0, 50, 50), min_area=0.1)
        assert clipped == (0, 25, 25, 50, 50)

    def test_box_below_min_area_dropped(self, slicing):
        box = (0, 25, 25, 75, 75)  # only 1/4 survives the (0,0,50,50) tile
        assert slicing._clip_to_tile(box, (0, 0, 50, 50), min_area=0.5) is None

    def test_box_outside_tile_returns_none(self, slicing):
        box = (0, 25, 25, 75, 75)
        assert slicing._clip_to_tile(box, (200, 200, 300, 300), min_area=0.1) is None


class TestToYoloLine:
    def test_round_trip_centered_box(self, slicing):
        line = slicing._to_yolo_line(0, 0, 0, 32, 32, w=64, h=64)
        assert line == '0 0.250000 0.250000 0.500000 0.500000'


class TestResolveTargetEmpties:
    def test_bool_true_keeps_all(self, slicing):
        assert slicing._resolve_target_empties(True, 5, 10) == 10

    def test_bool_false_keeps_none(self, slicing):
        assert slicing._resolve_target_empties(False, 5, 10) == 0

    def test_int_is_ratio_capped_by_available(self, slicing):
        assert slicing._resolve_target_empties(2, 3, 100) == 6
        assert slicing._resolve_target_empties(50, 3, 100) == 100

    def test_negative_int_raises(self, slicing):
        with pytest.raises(ValueError):
            slicing._resolve_target_empties(-1, 3, 100)

    def test_float_is_fraction_of_available(self, slicing):
        assert slicing._resolve_target_empties(0.5, 3, 10) == 5

    def test_float_out_of_range_raises(self, slicing):
        with pytest.raises(ValueError):
            slicing._resolve_target_empties(1.5, 3, 10)

    def test_wrong_type_raises(self, slicing):
        with pytest.raises(TypeError):
            slicing._resolve_target_empties('all', 3, 10)


class TestSliceDataset:
    def test_slices_single_image_into_tiles(self, slicing, tmp_path):
        src = tmp_path / 'src'
        out = tmp_path / 'out'
        img_dir = src / 'images' / 'train'
        lbl_dir = src / 'labels' / 'train'
        img_dir.mkdir(parents=True)
        lbl_dir.mkdir(parents=True)

        Image.new('RGB', (800, 800), (120, 120, 120)).save(img_dir / 'a.jpg')
        # Centered 200px box -> overlaps all four tiles.
        (lbl_dir / 'a.txt').write_text('0 0.5 0.5 0.25 0.25\n')

        stats = slicing.slice_dataset(
            str(src), str(out), tile_size=640, overlap=0.2, splits=('train',)
        )

        # origins along each axis: [0, 160] -> 4 tiles, all labeled.
        assert stats['train']['source_images'] == 1
        assert stats['train']['tiles'] == 4
        assert stats['train']['labeled_tiles'] == 4
        assert stats['train']['empties_total'] == 0

        out_imgs = list((out / 'images' / 'train').glob('*.jpg'))
        out_lbls = list((out / 'labels' / 'train').glob('*.txt'))
        assert len(out_imgs) == 4
        assert len(out_lbls) == 4
