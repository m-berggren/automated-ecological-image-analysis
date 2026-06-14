"""Unit tests for the pure validation helpers in apps.pollinator.detector_upload.

Covers the zip-slip guard, dataset-root detection, and YOLO label remapping.
The zip-extraction entrypoints (validate_and_stage, merge_uploaded_into_dataset)
do filesystem work and belong in an integration test.
"""

from types import SimpleNamespace

import pytest

from apps.pollinator.detector_upload import (
    DetectorUploadError,
    _detect_root,
    _is_unsafe_member,
    _remap_label,
)


class TestIsUnsafeMember:
    @pytest.mark.parametrize(
        'name',
        [
            '/etc/passwd',  # absolute posix
            '\\\\server\\share',  # absolute windows / UNC
            'C:\\weights',  # drive letter
            'a/../../etc/passwd',  # parent traversal
            '../escape.txt',
        ],
    )
    def test_unsafe_paths(self, name):
        assert _is_unsafe_member(name) is True

    @pytest.mark.parametrize('name', ['data.yaml', 'images/train/a.jpg', 'labels/b.txt'])
    def test_safe_paths(self, name):
        assert _is_unsafe_member(name) is False


class TestDetectRoot:
    def _infos(self, *names):
        return [SimpleNamespace(filename=n) for n in names]

    def test_root_level_data_yaml(self):
        assert _detect_root(self._infos('data.yaml', 'images/a.jpg')) == ''

    def test_single_wrapper_folder(self):
        assert _detect_root(self._infos('ds/data.yaml', 'ds/images/a.jpg')) == 'ds'

    def test_missing_data_yaml_raises(self):
        with pytest.raises(DetectorUploadError):
            _detect_root(self._infos('images/a.jpg'))

    def test_multiple_data_yaml_raises(self):
        with pytest.raises(DetectorUploadError):
            _detect_root(self._infos('a/data.yaml', 'b/data.yaml'))


class TestRemapLabel:
    def test_valid_line_remapped_and_counted(self):
        out, errs, counts = _remap_label(
            '0 0.5 0.5 0.2 0.2',
            stem='img',
            remap={0: 1},
            n_their=2,
            target_classes=['a', 'b'],
        )
        assert out == ['1 0.500000 0.500000 0.200000 0.200000']
        assert errs == []
        assert counts == {'b': 1}

    def test_blank_lines_skipped(self):
        out, errs, _ = _remap_label(
            '\n   \n', stem='img', remap={0: 0}, n_their=1, target_classes=['a']
        )
        assert out == []
        assert errs == []

    def test_wrong_field_count_is_error(self):
        out, errs, _ = _remap_label(
            '0 0.5 0.5', stem='img', remap={0: 0}, n_their=1, target_classes=['a']
        )
        assert out == []
        assert len(errs) == 1

    def test_non_numeric_is_error(self):
        out, errs, _ = _remap_label(
            '0 x 0.5 0.2 0.2', stem='img', remap={0: 0}, n_their=1, target_classes=['a']
        )
        assert len(errs) == 1

    def test_class_out_of_range_is_error(self):
        out, errs, _ = _remap_label(
            '3 0.5 0.5 0.2 0.2', stem='img', remap={0: 0}, n_their=1, target_classes=['a']
        )
        assert len(errs) == 1

    def test_coords_outside_unit_range_is_error(self):
        out, errs, _ = _remap_label(
            '0 1.5 0.5 0.2 0.2', stem='img', remap={0: 0}, n_their=1, target_classes=['a']
        )
        assert len(errs) == 1
