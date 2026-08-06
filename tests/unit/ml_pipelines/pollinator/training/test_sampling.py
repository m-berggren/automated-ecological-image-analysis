"""Unit tests for ml_pipelines.pollinator.training.sampling."""

from pathlib import Path

import pytest


@pytest.fixture(scope='session')
def sampling(load_leaf):
    return load_leaf('pollinator/training/sampling.py')


class TestParsePlotKey:
    def test_four_segment_format(self, sampling):
        p = Path('hdd_1_2025_cg_Vamy_p1_101_WSCT__WSCT5926.jpg')
        assert sampling.parse_plot_key(p) == 'hdd1_cg_Vamy_p1'

    def test_dated_format(self, sampling):
        p = Path('hdd_2_2025_desert_Asa_p2_20250729_102_WSCT__x.jpg')
        assert sampling.parse_plot_key(p) == 'hdd2_desert_Asa_p2'

    def test_unrecognized_filename_is_unknown(self, sampling):
        assert sampling.parse_plot_key(Path('random_name.jpg')) == 'unknown'


class TestSampleBackgroundBalanced:
    def _make_bg(self, root, group_to_count):
        for prefix, count in group_to_count.items():
            for i in range(count):
                (root / f'{prefix}_{i}.jpg').write_bytes(b'')

    def test_balances_quota_across_groups(self, sampling, tmp_path):
        self._make_bg(
            tmp_path,
            {
                'hdd_1_2025_cg_Vamy_p1_101_WSCT__a': 4,
                'hdd_2_2025_desert_Asa_p2_20250729_102_WSCT__b': 4,
            },
        )
        sampled = sampling.sample_background_balanced(tmp_path, n_total=4, seed=1)
        assert len(sampled) == 4
        # Two groups, quota 2 each: exactly 2 from each group.
        keys = [sampling.parse_plot_key(p) for p in sampled]
        assert keys.count('hdd1_cg_Vamy_p1') == 2
        assert keys.count('hdd2_desert_Asa_p2') == 2

    def test_deterministic_for_fixed_seed(self, sampling, tmp_path):
        self._make_bg(tmp_path, {'hdd_1_2025_cg_Vamy_p1_101_WSCT__a': 10})
        first = sampling.sample_background_balanced(tmp_path, n_total=5, seed=7)
        second = sampling.sample_background_balanced(tmp_path, n_total=5, seed=7)
        assert first == second

    def test_empty_directory_returns_empty(self, sampling, tmp_path):
        assert sampling.sample_background_balanced(tmp_path, n_total=10, seed=1) == []

    def test_zero_total_returns_empty(self, sampling, tmp_path):
        self._make_bg(tmp_path, {'hdd_1_2025_cg_Vamy_p1_101_WSCT__a': 3})
        assert sampling.sample_background_balanced(tmp_path, n_total=0, seed=1) == []
