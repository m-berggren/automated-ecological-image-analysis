"""Unit tests for apps.pollinator.exif pure helpers.

These cover the EXIF value parsing and exclusion heuristics. No database is
touched; `_determine_exclusion` reads Django settings via the pytest-django
``settings`` fixture. The disk-reading entrypoint (extract_image_metadata) is
left for an integration test against real camera files.
"""

import datetime
from fractions import Fraction

from apps.pollinator import exif


class TestShutterDenominator:
    def test_exposure_time_tuple_uses_denominator(self):
        assert exif._shutter_denominator({'ExposureTime': (1, 250)}) == 250

    def test_exposure_time_float_is_inverted(self):
        assert exif._shutter_denominator({'ExposureTime': 0.004}) == 250

    def test_apex_shutter_speed_value_fallback(self):
        # ShutterSpeedValue is APEX: denom = 2 ** value.
        assert exif._shutter_denominator({'ShutterSpeedValue': 8}) == 256

    def test_missing_returns_none(self):
        assert exif._shutter_denominator({}) is None

    def test_unparseable_exposure_returns_none(self):
        assert exif._shutter_denominator({'ExposureTime': ('a', 'b')}) is None


class TestShutterSpeedLabel:
    def test_formats_as_fraction(self):
        assert exif.shutter_speed_label({'ExposureTime': (1, 250)}) == '1/250'

    def test_unknown_is_empty_string(self):
        assert exif.shutter_speed_label({}) == ''


class TestCameraId:
    def test_extracts_second_to_last_field(self):
        maker = 'a0:b1:c2:LA21-17:WSCT0001.JPG'
        assert exif.camera_id({'MakerNote': maker}) == 'LA21-17'

    def test_strips_null_bytes(self):
        maker = 'a0:LA21-17:WSCT0001\x00.JPG'
        assert exif.camera_id({'MakerNote': maker}) == 'LA21-17'

    def test_absent_makernote_is_empty(self):
        assert exif.camera_id({}) == ''

    def test_single_field_is_empty(self):
        assert exif.camera_id({'MakerNote': 'solo'}) == ''


class TestParseExifDatetime:
    def test_valid_string(self):
        assert exif._parse_exif_datetime('2024:05:01 13:45:30') == datetime.datetime(
            2024, 5, 1, 13, 45, 30
        )

    def test_none_and_empty(self):
        assert exif._parse_exif_datetime(None) is None
        assert exif._parse_exif_datetime('') is None

    def test_malformed(self):
        assert exif._parse_exif_datetime('01/05/2024') is None

    def test_non_string(self):
        assert exif._parse_exif_datetime(12345) is None


class TestCoerce:
    def test_json_safe_passthrough(self):
        assert exif._coerce(42) == 42
        assert exif._coerce('x') == 'x'

    def test_bytes_decoded(self):
        assert exif._coerce(b'hello') == 'hello'

    def test_tuple_becomes_coerced_list(self):
        assert exif._coerce((1, b'a')) == [1, 'a']

    def test_rational_becomes_float(self):
        assert exif._coerce(Fraction(1, 4)) == 0.25

    def test_other_object_stringified(self):
        assert exif._coerce(object) == str(object)


class TestStripNulls:
    def test_string(self):
        assert exif._strip_nulls('a\x00b') == 'ab'

    def test_nested_dict_and_list(self):
        value = {'k': ['x\x00', {'n': 'y\x00z'}]}
        assert exif._strip_nulls(value) == {'k': ['x', {'n': 'yz'}]}

    def test_non_string_passthrough(self):
        assert exif._strip_nulls(7) == 7


class TestDetermineExclusion:
    def test_flash_excluded_when_enabled(self, settings):
        settings.AUTO_EXCLUDE_FLASH = True
        assert exif._determine_exclusion(True, 999.0) == (True, 'flash_fired')

    def test_foggy_below_threshold_excluded(self, settings):
        settings.AUTO_EXCLUDE_FLASH = True
        settings.AUTO_EXCLUDE_FOGGY = True
        settings.FOGGY_LAPLACIAN_THRESHOLD = 50
        assert exif._determine_exclusion(False, 10.0) == (True, 'out_of_focus')

    def test_sharp_frame_not_excluded(self, settings):
        settings.AUTO_EXCLUDE_FOGGY = True
        settings.FOGGY_LAPLACIAN_THRESHOLD = 50
        assert exif._determine_exclusion(False, 100.0) == (False, '')

    def test_none_inputs_not_excluded(self, settings):
        settings.AUTO_EXCLUDE_FLASH = True
        settings.AUTO_EXCLUDE_FOGGY = True
        assert exif._determine_exclusion(None, None) == (False, '')

    def test_flash_gate_disabled(self, settings):
        settings.AUTO_EXCLUDE_FLASH = False
        settings.AUTO_EXCLUDE_FOGGY = False
        assert exif._determine_exclusion(True, 10.0) == (False, '')
