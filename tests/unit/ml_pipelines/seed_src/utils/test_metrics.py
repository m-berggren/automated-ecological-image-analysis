"""Unit tests for ml_pipelines.seed_src.utils.metrics.

Loaded in isolation: seed_src.utils ships without an ``__init__`` and these
functions only need shapely, so file-path loading keeps the test self-contained.
"""

import pytest

# Axis-aligned 2x2 squares as flat 8-coord OBB polygons (x1,y1,...,x4,y4).
SQUARE_A = [0, 0, 2, 0, 2, 2, 0, 2]
SQUARE_A_DUP = [0, 0, 2, 0, 2, 2, 0, 2]
SQUARE_SHIFTED = [1, 0, 3, 0, 3, 2, 1, 2]  # 50% overlap with A
SQUARE_FAR = [10, 10, 12, 10, 12, 12, 10, 12]


@pytest.fixture(scope='session')
def metrics(load_leaf):
    return load_leaf('seed_src/utils/metrics.py')


class TestGetIou:
    def test_identical_boxes_iou_one(self, metrics):
        assert metrics.get_iou(SQUARE_A, SQUARE_A_DUP) == pytest.approx(1.0)

    def test_disjoint_boxes_iou_zero(self, metrics):
        assert metrics.get_iou(SQUARE_A, SQUARE_FAR) == pytest.approx(0.0)

    def test_half_overlap(self, metrics):
        # intersection 2, union 4+4-2=6 -> 1/3.
        assert metrics.get_iou(SQUARE_A, SQUARE_SHIFTED) == pytest.approx(1 / 3)

    def test_wrong_length_returns_zero(self, metrics):
        assert metrics.get_iou([0, 0, 1, 1], SQUARE_A) == 0.0


class TestCalculateTpFpFn:
    def test_counts_match_extra_and_missed(self, metrics):
        preds = [{'poly': SQUARE_A}, {'poly': SQUARE_FAR}]
        gts = [SQUARE_A, [20, 20, 22, 20, 22, 22, 20, 22]]
        tp, fp, fn = metrics.calculate_tp_fp_fn(preds, gts, iou_threshold=0.5)
        assert (tp, fp, fn) == (1, 1, 1)

    def test_each_gt_matched_once(self, metrics):
        # Two predictions over the same gt: one TP, the second is a FP.
        preds = [{'poly': SQUARE_A}, {'poly': SQUARE_A_DUP}]
        gts = [SQUARE_A]
        tp, fp, fn = metrics.calculate_tp_fp_fn(preds, gts, iou_threshold=0.5)
        assert (tp, fp, fn) == (1, 1, 0)


class TestPrecisionRecallF1:
    def test_balanced_counts(self, metrics):
        p, r, f1 = metrics.calculate_precision_recall_f1_score(1, 1, 1)
        assert (p, r, f1) == (0.5, 0.5, 0.5)

    def test_perfect_scores(self, metrics):
        p, r, f1 = metrics.calculate_precision_recall_f1_score(4, 0, 0)
        assert (p, r, f1) == (1.0, 1.0, 1.0)

    def test_zero_counts_do_not_divide_by_zero(self, metrics):
        assert metrics.calculate_precision_recall_f1_score(0, 0, 0) == (0.0, 0.0, 0.0)
