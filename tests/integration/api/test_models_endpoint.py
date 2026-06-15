"""Integration tests for the ModelVersion list + set-active endpoints."""

import pytest

from apps.analysis.models import ModelKind, ModelVersion
from apps.datasets.models import Module

pytestmark = pytest.mark.django_db

MODELS = '/api/analysis/models/'


def _mv(module=Module.POLLINATORS, kind=ModelKind.DETECTOR, name='v', active=False):
    return ModelVersion.objects.create(
        module=module,
        kind=kind,
        version_name=name,
        model_file_path='file://x',
        is_active=active,
    )


class TestListModels:
    def test_lists_all(self, auth_client):
        _mv(name='a')
        _mv(module=Module.SEEDS, name='b')
        resp = auth_client.get(MODELS)
        assert resp.status_code == 200
        assert len(resp.data) == 2

    def test_filter_by_module(self, auth_client):
        _mv(module=Module.POLLINATORS, name='p')
        _mv(module=Module.SEEDS, name='s')
        resp = auth_client.get(MODELS, {'module': 'seeds'})
        assert resp.status_code == 200
        assert [m['version_name'] for m in resp.data] == ['s']


class TestSetActive:
    def test_activates_and_demotes_sibling(self, auth_client):
        a = _mv(name='a', active=True)
        b = _mv(name='b', active=False)  # same module + kind
        resp = auth_client.post(f'{MODELS}{b.pk}/set-active/')
        assert resp.status_code == 200
        a.refresh_from_db()
        b.refresh_from_db()
        assert b.is_active is True
        assert a.is_active is False  # auto-demoted by save()

    def test_missing_returns_404(self, auth_client):
        assert auth_client.post(f'{MODELS}999999/set-active/').status_code == 404


class TestModelDetail:
    def test_get(self, auth_client):
        mv = _mv(name='a')
        assert auth_client.get(f'{MODELS}{mv.pk}/').status_code == 200

    def test_patch_rename(self, auth_client):
        mv = _mv(name='a')
        resp = auth_client.patch(
            f'{MODELS}{mv.pk}/', {'version_name': 'renamed'}, format='json'
        )
        assert resp.status_code == 200
        mv.refresh_from_db()
        assert mv.version_name == 'renamed'

    def test_delete(self, auth_client, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        mv = _mv(name='a')
        assert auth_client.delete(f'{MODELS}{mv.pk}/').status_code == 204
        assert not ModelVersion.objects.filter(pk=mv.pk).exists()
