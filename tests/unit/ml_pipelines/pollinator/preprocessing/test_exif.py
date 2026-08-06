"""Unit tests for ml_pipelines.pollinator.preprocessing.exif.

The EXIF reader (`_get_exif`) is monkeypatched so these tests exercise the
parsing and quality-gate logic without crafting real EXIF-bearing image files.
"""

from fractions import Fraction

import cv2
import numpy as np
import pytest

from ml_pipelines.pollinator.preprocessing import exif


@pytest.fixture
def fake_exif(monkeypatch):
    """Install a fake `_get_exif` returning a fixed tag dict."""

    def _install(tags: dict):
        monkeypatch.setattr(exif, '_get_exif', lambda path: tags)

    return _install


class TestGetExifDatetime:
    def test_parses_valid_datetime_into_tuple(self, fake_exif):
        fake_exif({exif._EXIF_DT_TAG: '2024:05:01 13:45:30'})
        assert exif.get_exif_datetime('img.jpg') == (2024, 5, 1, 13, 45, 30)

    def test_missing_tag_returns_none(self, fake_exif):
        fake_exif({})
        assert exif.get_exif_datetime('img.jpg') is None

    def test_unparseable_value_returns_none(self, fake_exif):
        fake_exif({exif._EXIF_DT_TAG: 'not-a-datetime'})
        assert exif.get_exif_datetime('img.jpg') is None


class TestGetExifMetadata:
    def test_shutter_speed_exported_as_label(self, fake_exif):
        fake_exif({exif._SHUTTER_TAG: Fraction(1, 250)})
        meta = exif.get_exif_metadata('img.jpg', {})
        assert meta['shutter_speed'] == '1/250'
        assert meta['skip'] is False

    def test_missing_shutter_gives_empty_label(self, fake_exif):
        fake_exif({})
        meta = exif.get_exif_metadata('img.jpg', {})
        assert meta['shutter_speed'] == ''

    def test_flash_frame_is_skipped(self, fake_exif):
        fake_exif({exif._FLASH_TAG: 1})
        meta = exif.get_exif_metadata('img.jpg', {'skip_flash': True})
        assert meta['skip'] is True
        assert meta['skip_reason'] == 'flash'

    def test_flash_not_skipped_when_gate_disabled(self, fake_exif):
        fake_exif({exif._FLASH_TAG: 1})
        meta = exif.get_exif_metadata('img.jpg', {'skip_flash': False})
        assert meta['skip'] is False
        assert meta['skip_reason'] == ''


class TestFoggyGate:
    """The skip_foggy branch reads the image from disk and thresholds on
    Laplacian variance, so these use real temp files."""

    def test_uniform_frame_is_skipped_as_fog(self, fake_exif, tmp_path):
        fake_exif({})
        path = tmp_path / 'flat.png'
        cv2.imwrite(str(path), np.full((80, 80, 3), 127, dtype=np.uint8))
        meta = exif.get_exif_metadata(
            str(path), {'skip_foggy': True, 'foggy_threshold': 50}
        )
        assert meta['skip'] is True
        assert meta['skip_reason'] == 'fog'
        assert meta['laplacian_var'] < 50

    def test_high_texture_frame_is_not_skipped(self, fake_exif, tmp_path):
        fake_exif({})
        rng = np.random.default_rng(0)
        noise = rng.integers(0, 256, size=(80, 80, 3), dtype=np.uint8)
        path = tmp_path / 'sharp.png'
        cv2.imwrite(str(path), noise)
        meta = exif.get_exif_metadata(
            str(path), {'skip_foggy': True, 'foggy_threshold': 50}
        )
        assert meta['skip'] is False
        assert meta['laplacian_var'] >= 50

    def test_unreadable_image_does_not_skip(self, fake_exif, tmp_path):
        fake_exif({})
        path = tmp_path / 'not_an_image.jpg'
        path.write_text('this is not an image')  # cv2.imread returns None
        meta = exif.get_exif_metadata(str(path), {'skip_foggy': True})
        assert meta['skip'] is False


class TestGetExifReader:
    """Direct coverage of the cached _get_exif disk reader."""

    def test_missing_file_returns_empty(self):
        assert exif._get_exif('/no/such/file.jpg') == {}

    def test_image_without_exif_returns_empty(self, tmp_path):
        path = tmp_path / 'plain.png'
        cv2.imwrite(str(path), np.zeros((4, 4, 3), dtype=np.uint8))
        assert exif._get_exif(str(path)) == {}
