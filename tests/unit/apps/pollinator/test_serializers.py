"""Unit tests for PollinatorTrainingCreateSerializer.validate_config.

Only the validation branches that fire before any DB lookup are covered: the
unknown-track guard and the required from_model_version_id. The source-model
existence/kind checks query the DB and belong in an integration test.
"""

import pytest
from rest_framework import serializers

from apps.analysis.models import ModelVersion
from apps.datasets.models import Module
from apps.pollinator.serializers import PollinatorTrainingCreateSerializer
from apps.pollinator.training import PER_TRACK_DEFAULTS

VALID_TRACK = next(iter(PER_TRACK_DEFAULTS))
EXPECTED_KIND = PER_TRACK_DEFAULTS[VALID_TRACK]['kind']


def test_unknown_track_rejected():
    ser = PollinatorTrainingCreateSerializer()
    with pytest.raises(serializers.ValidationError):
        ser.validate_config({'track': 'does-not-exist'})


def test_missing_source_model_id_rejected():
    ser = PollinatorTrainingCreateSerializer()
    with pytest.raises(serializers.ValidationError):
        ser.validate_config({'track': VALID_TRACK})


class TestValidateConfigAgainstSourceModel:
    pytestmark = pytest.mark.django_db

    def _source(self, *, module=Module.POLLINATORS, kind=EXPECTED_KIND):
        return ModelVersion.objects.create(
            module=module, kind=kind, version_name='src', model_file_path='file://x'
        )

    def test_valid_config_passes(self):
        source = self._source()
        cfg = {'track': VALID_TRACK, 'from_model_version_id': source.pk}
        ser = PollinatorTrainingCreateSerializer()
        assert ser.validate_config(cfg) == cfg

    def test_nonexistent_source_rejected(self):
        ser = PollinatorTrainingCreateSerializer()
        with pytest.raises(serializers.ValidationError):
            ser.validate_config({'track': VALID_TRACK, 'from_model_version_id': 999999})

    def test_wrong_module_rejected(self):
        source = self._source(module=Module.SEEDS)
        ser = PollinatorTrainingCreateSerializer()
        with pytest.raises(serializers.ValidationError):
            ser.validate_config(
                {'track': VALID_TRACK, 'from_model_version_id': source.pk}
            )

    def test_wrong_kind_rejected(self):
        from apps.analysis.models import ModelKind

        other = ModelKind.GROUP_CLASSIFIER if EXPECTED_KIND != ModelKind.GROUP_CLASSIFIER else ModelKind.DETECTOR
        source = self._source(kind=other)
        ser = PollinatorTrainingCreateSerializer()
        with pytest.raises(serializers.ValidationError):
            ser.validate_config(
                {'track': VALID_TRACK, 'from_model_version_id': source.pk}
            )

    def test_split_sum_must_be_100(self):
        source = self._source()
        ser = PollinatorTrainingCreateSerializer()
        with pytest.raises(serializers.ValidationError):
            ser.validate_config(
                {
                    'track': VALID_TRACK,
                    'from_model_version_id': source.pk,
                    'train_split': 70,
                    'val_split': 10,
                    'test_split': 10,
                }
            )
