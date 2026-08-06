"""Unit tests for pure helpers in apps.pollinator.training."""

from types import SimpleNamespace

import pytest

from apps.pollinator.training import (
    PER_TRACK_DEFAULTS,
    POLLINATOR_CLASSES,
    TILE_CONFIG_DEFAULTS,
    _effective_class,
    _resolve_tile_config,
    _stratified_image_split,
    _validate_config,
    canonical_class,
)

VALID_TRACK = next(iter(PER_TRACK_DEFAULTS))


@pytest.mark.parametrize('value', [None, ''])
def test_empty_input_returns_empty_string(value):
    assert canonical_class(value) == ''


def test_lowercases_input():
    assert canonical_class('Bumblebee') == 'bumblebee'


def test_alias_is_collapsed():
    assert canonical_class('butterfly_moth') == 'butterfly'
    assert canonical_class('Butterfly_Moth') == 'butterfly'  # case-insensitive


def test_unknown_label_passes_through_lowercased():
    assert canonical_class('WeirdLabel') == 'weirdlabel'


@pytest.mark.parametrize('cls', POLLINATOR_CLASSES)
def test_canonical_classes_are_stable(cls):
    assert canonical_class(cls) == cls


class TestEffectiveClass:
    def test_reviewer_label_wins(self):
        d = SimpleNamespace(reviewer_label='bumblebee', predicted_class='fly')
        assert _effective_class(d) == 'bumblebee'

    def test_falls_back_to_prediction(self):
        assert _effective_class(SimpleNamespace(reviewer_label='', predicted_class='fly')) == 'fly'
        assert _effective_class(SimpleNamespace(reviewer_label=None, predicted_class='other')) == 'other'


class TestStratifiedImageSplit:
    def test_partitions_without_loss_or_overlap(self):
        by_class = {'a': list(range(10)), 'b': [100, 101]}
        splits = {'train': 80, 'val': 10, 'test': 10}
        train, val, test = _stratified_image_split(by_class, splits, seed=42)

        all_ids = set(range(10)) | {100, 101}
        assert sorted(train + val + test) == sorted(all_ids)  # nothing lost/duplicated
        # Group 'a' (n=10) yields 1 val + 1 test; group 'b' (n<=2) stays all-train.
        assert len(val) == 1
        assert len(test) == 1
        assert len(train) == 10

    def test_deterministic_for_seed(self):
        by_class = {'a': list(range(20))}
        splits = {'train': 80, 'val': 10, 'test': 10}
        assert _stratified_image_split(by_class, splits, seed=7) == _stratified_image_split(
            by_class, splits, seed=7
        )


class TestValidateConfig:
    def _valid(self, **over):
        cfg = {
            'track': VALID_TRACK,
            'from_model_version_id': '5',
            'train_split': 80,
            'val_split': 20,
            'test_split': 0,
        }
        cfg.update(over)
        return cfg

    def test_valid_config(self):
        track, from_id, class_filter, splits, epochs = _validate_config(self._valid())
        assert track == VALID_TRACK
        assert from_id == 5  # coerced to int
        assert class_filter == list(POLLINATOR_CLASSES)
        assert sum(splits.values()) == 100
        assert epochs == PER_TRACK_DEFAULTS[VALID_TRACK]['epochs']

    def test_missing_track_or_source(self):
        with pytest.raises(ValueError):
            _validate_config({'from_model_version_id': 5})

    def test_unknown_track(self):
        with pytest.raises(ValueError):
            _validate_config(self._valid(track='nope'))

    def test_splits_must_sum_to_100(self):
        with pytest.raises(ValueError):
            _validate_config(self._valid(train_split=70, val_split=20, test_split=0))

    def test_train_and_val_must_be_positive(self):
        with pytest.raises(ValueError):
            _validate_config(self._valid(train_split=100, val_split=0, test_split=0))

    def test_epochs_must_be_positive(self):
        # 0 is falsy and falls back to the track default, so only a negative
        # value reaches the positivity guard.
        with pytest.raises(ValueError):
            _validate_config(self._valid(epochs=-1))


class TestResolveTileConfig:
    def test_layers_merge_defaults_source_then_override(self):
        source = SimpleNamespace(parameters={'tile_config': {'tile_size': 800}})
        config = {'tile_config': {'overlap': 0.5}}
        result = _resolve_tile_config(source, config)
        assert result['tile_size'] == 800  # inherited from source model
        assert result['overlap'] == 0.5  # job override
        assert result['use_tiles'] == TILE_CONFIG_DEFAULTS['use_tiles']  # default

    def test_job_override_beats_source(self):
        source = SimpleNamespace(parameters={'tile_config': {'tile_size': 800}})
        result = _resolve_tile_config(source, {'tile_config': {'tile_size': 999}})
        assert result['tile_size'] == 999
