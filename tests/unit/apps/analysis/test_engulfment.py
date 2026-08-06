"""Unit tests for the overlap geometry in apps.analysis.engulfment.

Covers the pure helpers that decide when two detections are the same insect.
The DB-bound apply_engulfment_exclusions (queries + transaction) is left for an
integration test.
"""

from apps.analysis import engulfment


def _box(x1, y1, x2, y2):
    return {'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2}


class TestArea:
    def test_area(self):
        assert engulfment._area(_box(0, 0, 2, 3)) == 6


class TestCenterIn:
    def test_center_inside(self):
        outer = _box(0, 0, 10, 10)
        inner = _box(4, 4, 6, 6)  # center (5, 5)
        assert engulfment._center_in(outer, inner) is True

    def test_center_outside(self):
        outer = _box(0, 0, 10, 10)
        other = _box(20, 20, 24, 24)  # center (22, 22)
        assert engulfment._center_in(outer, other) is False


class TestIou:
    def test_identical(self):
        b = _box(0, 0, 2, 2)
        assert engulfment._iou(b, dict(b)) == 1.0

    def test_disjoint(self):
        assert engulfment._iou(_box(0, 0, 2, 2), _box(5, 5, 7, 7)) == 0.0

    def test_half_overlap(self):
        # inter = 2, union = 4 + 4 - 2 = 6 -> 1/3.
        assert engulfment._iou(_box(0, 0, 2, 2), _box(1, 0, 3, 2)) == 1 / 3


class TestSameInsect:
    def test_contained_box_is_same_insect(self):
        larger = _box(0, 0, 10, 10)
        smaller = _box(4, 4, 6, 6)
        assert engulfment._same_insect(larger, smaller, iou_threshold=0.5) is True

    def test_disjoint_low_iou_is_not_same(self):
        a = _box(0, 0, 2, 2)
        b = _box(50, 50, 52, 52)
        assert engulfment._same_insect(a, b, iou_threshold=0.5) is False

    def test_overlap_meeting_iou_threshold_is_same(self):
        # Offset only in x so neither center lands in the other box; the
        # decision then rests purely on IoU. inter=40, union=160 -> 0.25.
        a = _box(0, 0, 10, 10)
        b = _box(6, 0, 16, 10)
        assert engulfment._center_in(a, b) is False
        assert engulfment._center_in(b, a) is False
        assert engulfment._same_insect(a, b, iou_threshold=0.2) is True
        assert engulfment._same_insect(a, b, iou_threshold=0.3) is False
