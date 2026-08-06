"""Unit tests for ml_pipelines.pollinator.training.splits.

Loaded in isolation (see conftest.load_leaf) so the plot-stratification logic
is tested without importing the torch/ultralytics training stack that the
package ``__init__`` would otherwise pull in.
"""

import json

import pytest


@pytest.fixture(scope='session')
def splits(load_leaf):
    return load_leaf('pollinator/training/splits.py')


def _make_dataset(root, plot_to_count):
    """Build a minimal YOLO-format dataset with everything in images/train."""
    img_dir = root / 'images' / 'train'
    lbl_dir = root / 'labels' / 'train'
    img_dir.mkdir(parents=True)
    lbl_dir.mkdir(parents=True)
    for plot, count in plot_to_count.items():
        for i in range(count):
            stem = f'{plot}__img{i}'
            (img_dir / f'{stem}.jpg').write_bytes(b'')
            (lbl_dir / f'{stem}.txt').write_text('')


class TestDefaultPlotFromStem:
    def test_extracts_leading_plot_segment(self, splits):
        assert splits._default_plot_from_stem('PlotA__103_WSCT__x') == 'PlotA'

    def test_stem_without_marker_is_unknown(self, splits):
        assert splits._default_plot_from_stem('noseparator') == 'unknown'


class TestRestratifyValidation:
    def test_val_frac_out_of_range_raises(self, splits, tmp_path):
        with pytest.raises(ValueError):
            splits.restratify_by_plot(str(tmp_path), val_frac=1.0)

    def test_negative_test_frac_raises(self, splits, tmp_path):
        with pytest.raises(ValueError):
            splits.restratify_by_plot(str(tmp_path), test_frac=-0.1)

    def test_fractions_summing_to_one_raises(self, splits, tmp_path):
        with pytest.raises(ValueError):
            splits.restratify_by_plot(str(tmp_path), val_frac=0.6, test_frac=0.5)


class TestRestratifyByPlot:
    def test_partitions_each_plot_proportionally(self, splits, tmp_path):
        _make_dataset(tmp_path, {'plotA': 20, 'plotB': 5})
        counts = splits.restratify_by_plot(
            str(tmp_path), val_frac=0.20, test_frac=0.10, seed=42
        )

        # plotB is tiny (<10) so it stays entirely in train.
        assert counts['plotB'] == {'total': 5, 'train': 5, 'val': 0, 'test': 0}
        # plotA: test=max(1,int(20*0.1))=2, val=max(1,int(20*0.2))=4, train=14.
        assert counts['plotA'] == {'total': 20, 'train': 14, 'val': 4, 'test': 2}

    def test_files_are_moved_and_artifacts_written(self, splits, tmp_path):
        _make_dataset(tmp_path, {'plotA': 20, 'plotB': 5})
        splits.restratify_by_plot(str(tmp_path), seed=42)

        n_test_imgs = len(list((tmp_path / 'images' / 'test').glob('*.jpg')))
        n_test_lbls = len(list((tmp_path / 'labels' / 'test').glob('*.txt')))
        assert n_test_imgs == 2
        assert n_test_lbls == 2  # labels move alongside their images
        assert (tmp_path / 'stratified_split_counts.json').exists()
        assert (tmp_path / '.stratified_for').exists()

    def test_rerun_is_idempotent(self, splits, tmp_path):
        _make_dataset(tmp_path, {'plotA': 20, 'plotB': 5})
        first = splits.restratify_by_plot(str(tmp_path), seed=42)
        second = splits.restratify_by_plot(str(tmp_path), seed=42)
        assert first == second

    def test_empty_dataset_returns_empty_dict(self, splits, tmp_path):
        (tmp_path / 'images' / 'train').mkdir(parents=True)
        assert splits.restratify_by_plot(str(tmp_path)) == {}


class TestPlotHoldout:
    def test_empty_test_plots_raises(self, splits, tmp_path):
        with pytest.raises(ValueError):
            splits.plot_holdout(str(tmp_path), test_plots=[])

    def test_held_out_plot_goes_entirely_to_test(self, splits, tmp_path):
        _make_dataset(tmp_path, {'plotA': 20, 'plotB': 20})
        counts = splits.plot_holdout(
            str(tmp_path), test_plots=['plotA'], val_frac=0.15, seed=42
        )
        assert counts['plotA']['test'] == 20
        assert counts['plotA']['train'] == 0
        assert counts['plotA']['val'] == 0
        # plotB is split into train/val only, never test.
        assert counts['plotB']['test'] == 0
        assert counts['plotB']['train'] + counts['plotB']['val'] == 20
        loaded = json.loads((tmp_path / 'holdout_split_counts.json').read_text())
        assert loaded == counts
