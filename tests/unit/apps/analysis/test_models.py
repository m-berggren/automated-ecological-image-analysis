"""Database-backed tests for ModelVersion.save().

The save() override enforces "at most one active model per (module, kind)",
scoped by parameters.species for seeds. These hit the sqlite test DB.
"""

import pytest

from apps.analysis.models import ModelKind, ModelVersion
from apps.datasets.models import Module

pytestmark = pytest.mark.django_db


def _make(active, *, kind=ModelKind.DETECTOR, module=Module.POLLINATORS,
          species=None, name='v'):
    return ModelVersion.objects.create(
        module=module,
        kind=kind,
        version_name=name,
        model_file_path='file://x',
        is_active=active,
        parameters={'species': species} if species else {},
    )


def test_activating_deactivates_same_module_and_kind():
    v1 = _make(True, name='v1')
    v2 = _make(True, name='v2')
    v1.refresh_from_db()
    assert v1.is_active is False
    assert ModelVersion.objects.get(pk=v2.pk).is_active is True


def test_other_kind_is_left_active():
    detector = _make(True, kind=ModelKind.DETECTOR, name='det')
    _make(True, kind=ModelKind.BINARY_CLASSIFIER, name='bin')
    detector.refresh_from_db()
    assert detector.is_active is True


def test_seeds_activation_is_scoped_to_species():
    cat = _make(True, module=Module.SEEDS, species='cat', name='cat')
    # A different species does not deactivate the cat model.
    _make(True, module=Module.SEEDS, species='peh', name='peh')
    cat.refresh_from_db()
    assert cat.is_active is True
    # Same species does.
    _make(True, module=Module.SEEDS, species='cat', name='cat2')
    cat.refresh_from_db()
    assert cat.is_active is False
