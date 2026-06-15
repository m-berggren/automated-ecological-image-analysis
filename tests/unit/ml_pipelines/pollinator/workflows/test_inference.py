"""Unit tests for the pure helpers in ml_pipelines.pollinator.workflows.inference.

inference imports the classifier and detector packages (torch + ultralytics +
sahi, ~4.5s). The helpers under test touch none of that, so the heavy sibling
packages are stubbed in sys.modules before import to keep these tests fast and
isolated.
"""

import importlib
import sys
import types

import pytest

_INFERENCE = 'ml_pipelines.pollinator.workflows.inference'
_HEAVY_STUBS = {
    'ml_pipelines.pollinator.classification': {
        'BinaryClassifier': object,
        'GroupClassifier': object,
    },
    'ml_pipelines.pollinator.detection': {'YoloDetector': object},
}


@pytest.fixture(scope='module')
def inference():
    saved = {}
    for name, attrs in _HEAVY_STUBS.items():
        saved[name] = sys.modules.get(name)
        stub = types.ModuleType(name)
        for attr, value in attrs.items():
            setattr(stub, attr, value)
        sys.modules[name] = stub
    saved[_INFERENCE] = sys.modules.get(_INFERENCE)
    sys.modules.pop(_INFERENCE, None)
    try:
        yield importlib.import_module(_INFERENCE)
    finally:
        for name, prev in saved.items():
            if prev is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prev


class TestComputeIou:
    def test_identical(self, inference):
        assert inference._compute_iou((0, 0, 2, 2), (0, 0, 2, 2)) == 1.0

    def test_half_overlap(self, inference):
        assert inference._compute_iou((0, 0, 2, 2), (1, 0, 3, 2)) == 1 / 3

    def test_disjoint(self, inference):
        assert inference._compute_iou((0, 0, 2, 2), (5, 5, 7, 7)) == 0.0


class TestSecondsBetween:
    def test_symmetric_difference(self, inference):
        a = (2024, 5, 1, 12, 0, 0)
        b = (2024, 5, 1, 12, 0, 30)
        assert inference._seconds_between(a, b) == 30.0
        assert inference._seconds_between(b, a) == 30.0


class TestRobustSortKey:
    def test_exif_datetime_takes_priority(self, inference, monkeypatch):
        monkeypatch.setattr(
            inference, 'get_exif_datetime', lambda p: (2024, 1, 1, 0, 0, 0)
        )
        from pathlib import Path

        key = inference._robust_sort_key(Path('whatever.jpg'))
        assert key[0] == 0  # group 0: exif present

    def test_numeric_suffix_when_no_exif(self, inference, monkeypatch):
        monkeypatch.setattr(inference, 'get_exif_datetime', lambda p: None)
        from pathlib import Path

        assert inference._robust_sort_key(Path('img_0042.jpg')) == (
            1,
            42,
            'img_0042.jpg',
        )

    def test_filename_fallback_without_digits(self, inference, monkeypatch):
        monkeypatch.setattr(inference, 'get_exif_datetime', lambda p: None)
        from pathlib import Path

        assert inference._robust_sort_key(Path('nonum.jpg')) == (2, 'nonum.jpg')


class TestListImages:
    def test_sorts_numerically_and_filters_non_images(
        self, inference, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(inference, 'get_exif_datetime', lambda p: None)
        for name in ('img10.jpg', 'img2.jpg', 'img1.jpg', 'notes.txt'):
            (tmp_path / name).write_bytes(b'')

        result = [p.name for p in inference.list_images(tmp_path)]
        assert result == ['img1.jpg', 'img2.jpg', 'img10.jpg']


class TestMergeImageDetections:
    def _yolo(self):
        return {
            'bbox': (0, 0, 10, 10),
            'bbox_w': 10,
            'bbox_h': 10,
            'yolo_class': 'fly',
            'yolo_confidence': 0.987654,
        }

    def _insect(self, bbox, probs=None):
        return {
            'bbox': bbox,
            'bbox_w': bbox[2] - bbox[0],
            'bbox_h': bbox[3] - bbox[1],
            'insectnet_class': 'bee',
            'insectnet_confidence': 0.5,
            'binary_confidence': 0.6,
            'class_probs': probs,
        }

    def test_overlapping_pair_merges_to_both(self, inference):
        yolo = [self._yolo()]
        insect = [self._insect((0, 0, 9, 9), probs={'bee': 0.5})]
        merged = inference._merge_image_detections('a.jpg', yolo, insect, 0.3)

        assert len(merged) == 1
        rec = merged[0]
        assert rec['source'] == 'both'
        assert rec['bbox'] == {'x1': 0, 'y1': 0, 'x2': 10, 'y2': 10, 'w': 10, 'h': 10}
        assert rec['yolo_confidence'] == 0.9877  # rounded to 4 dp
        assert rec['insectnet_class'] == 'bee'

    def test_unmatched_yolo_and_insect_kept_separately(self, inference):
        yolo = [self._yolo()]
        insect = [self._insect((100, 100, 110, 110))]
        merged = inference._merge_image_detections('a.jpg', yolo, insect, 0.3)

        sources = sorted(rec['source'] for rec in merged)
        assert sources == ['preprocessing', 'yolo']
        yolo_rec = next(r for r in merged if r['source'] == 'yolo')
        assert yolo_rec['insectnet_class'] is None
