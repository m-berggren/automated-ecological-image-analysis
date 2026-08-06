"""Unit tests for the pure / filesystem helpers in ml_pipelines.seed_src.utils.helpers.

Isolated-loaded (the module imports sahi at top). load_model and the
OCR/routing paths that need real models are not unit-tested here.
"""

import pytest
from PIL import Image


@pytest.fixture(scope='session')
def helpers(load_leaf):
    return load_leaf('seed_src/utils/helpers.py')


class TestGetNextRunName:
    def test_returns_base_when_no_runs_dir(self, helpers, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        assert helpers.get_next_run_name('phyca') == 'phyca'

    def test_increments_past_existing_base(self, helpers, monkeypatch, tmp_path):
        (tmp_path / 'runs' / 'obb' / 'phyca').mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        assert helpers.get_next_run_name('phyca') == 'phyca2'

    def test_increments_past_highest_suffix(self, helpers, monkeypatch, tmp_path):
        obb = tmp_path / 'runs' / 'obb'
        (obb / 'phyca').mkdir(parents=True)
        (obb / 'phyca2').mkdir()
        monkeypatch.chdir(tmp_path)
        assert helpers.get_next_run_name('phyca') == 'phyca3'

    def test_unrelated_runs_do_not_count(self, helpers, monkeypatch, tmp_path):
        (tmp_path / 'runs' / 'obb' / 'other').mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        assert helpers.get_next_run_name('phyca') == 'phyca'


class TestLoadGroundTruth:
    def test_scales_normalized_coords_to_pixels(self, helpers, tmp_path):
        (tmp_path / 'images').mkdir()
        (tmp_path / 'labels').mkdir()
        img_path = tmp_path / 'images' / 'x.jpg'
        Image.new('RGB', (100, 200)).save(img_path)
        (tmp_path / 'labels' / 'x.txt').write_text(
            '0 0.1 0.2 0.3 0.2 0.3 0.4 0.1 0.4\n'
        )

        boxes = helpers.load_ground_truth(str(img_path))
        assert boxes == [[10.0, 40.0, 30.0, 40.0, 30.0, 80.0, 10.0, 80.0]]

    def test_missing_label_file_returns_empty(self, helpers, tmp_path):
        (tmp_path / 'images').mkdir()
        img_path = tmp_path / 'images' / 'x.jpg'
        Image.new('RGB', (10, 10)).save(img_path)
        assert helpers.load_ground_truth(str(img_path)) == []

    def test_short_lines_are_skipped(self, helpers, tmp_path):
        (tmp_path / 'images').mkdir()
        (tmp_path / 'labels').mkdir()
        img_path = tmp_path / 'images' / 'x.jpg'
        Image.new('RGB', (10, 10)).save(img_path)
        (tmp_path / 'labels' / 'x.txt').write_text('0 0.1 0.2\n')  # <9 parts
        assert helpers.load_ground_truth(str(img_path)) == []


class TestUpdateClassLabels:
    def test_rewrites_class_id_and_skips_classes_file(self, helpers, tmp_path):
        (tmp_path / 'a.txt').write_text('5 0.1 0.2\n7 0.3 0.4\n')
        (tmp_path / 'classes.txt').write_text('seed\n')

        helpers.update_class_labels(str(tmp_path), 3)

        assert (tmp_path / 'a.txt').read_text() == '3 0.1 0.2\n3 0.3 0.4\n'
        assert (tmp_path / 'classes.txt').read_text() == 'seed\n'  # untouched


class TestIdentifySpecies:
    def test_matches_from_filename(self, helpers):
        result = helpers.identify_species(
            'VAU_sample.jpg', '/p.jpg', ['vau', 'cat'], ocr_tool=None
        )
        assert result == 'vau'  # OCR not consulted

    def test_falls_back_to_ocr(self, helpers):
        class FakeOcr:
            def extract_from_image(self, path):
                return 'DETECTED CAT LABEL'

        result = helpers.identify_species(
            'mystery.jpg', '/p.jpg', ['vau', 'cat'], ocr_tool=FakeOcr()
        )
        assert result == 'cat'

    def test_unknown_when_nothing_matches(self, helpers):
        class FakeOcr:
            def extract_from_image(self, path):
                return 'NOTHING USEFUL'

        result = helpers.identify_species(
            'mystery.jpg', '/p.jpg', ['vau', 'cat'], ocr_tool=FakeOcr()
        )
        assert result == 'UNKNOWN'
