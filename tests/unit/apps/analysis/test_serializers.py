"""Unit tests for serializer validation in apps.analysis.serializers.

Only the pure validation branches are tested here (no DB): the upload/module
cross-check and the empty version_name guard. Uniqueness checks that query the
DB belong in an integration test.
"""

from types import SimpleNamespace

import pytest
from rest_framework import serializers

from apps.analysis.models import ModelVersion
from apps.analysis.serializers import (
    InferenceRunCreateSerializer,
    ModelVersionUpdateSerializer,
)
from apps.datasets.models import Module


class TestInferenceRunCreateValidate:
    def test_module_mismatch_rejected(self):
        ser = InferenceRunCreateSerializer()
        attrs = {'upload': SimpleNamespace(module='pollinators'), 'module': 'seeds'}
        with pytest.raises(serializers.ValidationError):
            ser.validate(attrs)

    def test_matching_module_passes_through(self):
        ser = InferenceRunCreateSerializer()
        attrs = {'upload': SimpleNamespace(module='seeds'), 'module': 'seeds'}
        assert ser.validate(attrs) is attrs


class TestVersionNameValidate:
    def test_blank_name_rejected(self):
        ser = ModelVersionUpdateSerializer()
        with pytest.raises(serializers.ValidationError):
            ser.validate_version_name('   ')


class TestVersionNameUniqueness:
    pytestmark = pytest.mark.django_db

    def _make(self, name):
        return ModelVersion.objects.create(
            module=Module.POLLINATORS, version_name=name, model_file_path='file://x'
        )

    def test_duplicate_name_rejected(self):
        self._make('v1')
        ser = ModelVersionUpdateSerializer()
        with pytest.raises(serializers.ValidationError):
            ser.validate_version_name('v1')

    def test_same_instance_keeping_its_name_is_allowed(self):
        mv = self._make('v1')
        ser = ModelVersionUpdateSerializer(instance=mv)
        assert ser.validate_version_name('v1') == 'v1'  # excludes self
