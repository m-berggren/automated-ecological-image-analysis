"""Unit tests for the guard branches of crops.write_detection_crop.

The function returns False (never raises) on bad input so one corrupt detection
can't abort a run. These guards run before any image/storage work, so they are
exercised with lightweight stand-ins. The successful render path (real image +
storage) belongs in an integration test.
"""

from types import SimpleNamespace

from apps.analysis.crops import write_detection_crop

GOOD_BBOX = {'x1': 0, 'y1': 0, 'x2': 10, 'y2': 10}


def _det(image, bbox):
    return SimpleNamespace(image=image, bbox=bbox)


def test_no_image_returns_false():
    assert write_detection_crop(_det(None, GOOD_BBOX)) is False


def test_image_without_file_returns_false():
    assert write_detection_crop(_det(SimpleNamespace(file=None), GOOD_BBOX)) is False


def test_missing_bbox_keys_returns_false():
    det = _det(SimpleNamespace(file='x.jpg'), {})
    assert write_detection_crop(det) is False


def test_non_numeric_bbox_returns_false():
    det = _det(SimpleNamespace(file='x.jpg'), {'x1': 'a', 'y1': 0, 'x2': 5, 'y2': 5})
    assert write_detection_crop(det) is False


def test_degenerate_x_extent_returns_false():
    det = _det(SimpleNamespace(file='x.jpg'), {'x1': 10, 'y1': 0, 'x2': 5, 'y2': 5})
    assert write_detection_crop(det) is False


def test_degenerate_y_extent_returns_false():
    det = _det(SimpleNamespace(file='x.jpg'), {'x1': 0, 'y1': 10, 'x2': 5, 'y2': 5})
    assert write_detection_crop(det) is False
