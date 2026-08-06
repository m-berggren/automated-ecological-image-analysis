"""Unit tests for the pure split/validation helpers in apps.seeds.training."""

from pathlib import Path

import pytest

from apps.seeds.training import _split_files, _validate_config


def _files(n):
    return [Path(f'{i:03d}.jpg') for i in range(n)]


class TestSplitFiles:
    def test_empty(self):
        assert _split_files([], 0.1, 0.0, seed=1) == ([], [], [])

    def test_single_is_train_only(self):
        train, val, test = _split_files(_files(1), 0.1, 0.0, seed=1)
        assert len(train) == 1
        assert val == [] and test == []

    def test_small_dataset_gets_one_val_no_test(self):
        train, val, test = _split_files(_files(5), 0.1, 0.1, seed=1)
        assert len(train) == 4
        assert len(val) == 1
        assert test == []

    def test_ratios_applied_for_large_dataset(self):
        train, val, test = _split_files(_files(10), 0.2, 0.2, seed=1)
        assert (len(train), len(val), len(test)) == (6, 2, 2)

    def test_partition_preserves_all_files(self):
        files = _files(12)
        train, val, test = _split_files(files, 0.2, 0.1, seed=3)
        assert sorted(train + val + test) == sorted(files)

    def test_deterministic_for_seed(self):
        files = _files(15)
        assert _split_files(files, 0.2, 0.1, seed=9) == _split_files(files, 0.2, 0.1, seed=9)


class TestValidateConfig:
    def test_valid_scratch_defaults(self):
        result = _validate_config({'species': 'cat'})
        assert result == ('cat', 'scratch', 30, None, 0.1, 0.0)

    def test_missing_species(self):
        with pytest.raises(ValueError):
            _validate_config({'training_mode': 'scratch'})

    def test_invalid_training_mode(self):
        with pytest.raises(ValueError):
            _validate_config({'species': 'cat', 'training_mode': 'bogus'})

    def test_non_positive_epochs(self):
        with pytest.raises(ValueError):
            _validate_config({'species': 'cat', 'epochs': 0})

    def test_incremental_requires_source(self):
        with pytest.raises(ValueError):
            _validate_config({'species': 'cat', 'training_mode': 'incremental'})

    def test_ratio_out_of_range(self):
        with pytest.raises(ValueError):
            _validate_config({'species': 'cat', 'val_ratio': 1.5})

    def test_ratios_must_leave_room_for_train(self):
        with pytest.raises(ValueError):
            _validate_config({'species': 'cat', 'val_ratio': 0.6, 'test_ratio': 0.5})
