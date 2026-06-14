"""Unit tests for ml_pipelines.seed_src.utils.active_seed_calculator.

Isolated-loaded: the module is a pure (json/os) helper with a __main__ guard,
so file-path loading keeps it self-contained.
"""

import pytest

SQUARE_2 = [0, 0, 2, 0, 2, 2, 0, 2]  # area 4
UNIT_SQUARE = [0, 0, 1, 0, 1, 1, 0, 1]  # area 1


@pytest.fixture(scope='session')
def asc(load_leaf):
    return load_leaf('seed_src/utils/active_seed_calculator.py')


class TestCalculatePolygonArea:
    def test_obb_square_via_shoelace(self, asc):
        assert asc.calculate_polygon_area(SQUARE_2) == 4.0

    def test_four_value_hbb_is_width_times_height(self, asc):
        assert asc.calculate_polygon_area([0, 0, 3, 4]) == 12.0

    def test_degenerate_length_returns_zero(self, asc):
        assert asc.calculate_polygon_area([0, 0, 1, 0, 1, 1]) == 0.0


class TestCountActiveAndAbortedSeeds:
    def test_classifies_by_relative_size(self, asc):
        detected = [
            {'id': 'a', 'poly': SQUARE_2},  # full size -> active
            {'id': 'b', 'poly': UNIT_SQUARE},  # 1/4 of reference -> aborted
        ]
        result = asc.count_active_and_aborted_seeds(SQUARE_2, detected, threshold=0.30)

        assert result['summary'] == {
            'total_seeds': 2,
            'active_seeds': 1,
            'aborted_seeds': 1,
        }
        by_id = {c['detection_id']: c['status'] for c in result['classifications']}
        assert by_id == {'a': 'active', 'b': 'aborted'}

    def test_threshold_boundary_is_aborted(self, asc):
        # Seed area exactly at threshold_area (<=) counts as aborted.
        ref = SQUARE_2  # area 4, threshold 0.25 -> threshold_area 1.0
        detected = [{'id': 'x', 'poly': UNIT_SQUARE}]  # area exactly 1.0
        result = asc.count_active_and_aborted_seeds(ref, detected, threshold=0.25)
        assert result['summary']['aborted_seeds'] == 1

    def test_missing_reference_raises(self, asc):
        with pytest.raises(ValueError):
            asc.count_active_and_aborted_seeds([], [])
