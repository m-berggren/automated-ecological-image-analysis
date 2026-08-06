"""Integration tests for the InferenceRun lifecycle endpoints
(create / list / detail / delete / cancel).
"""

import pytest

from apps.analysis.models import InferenceRun, JobStatus
from apps.datasets.models import Module, Upload

pytestmark = pytest.mark.django_db

RUNS = '/api/analysis/runs/'


def _upload(module=Module.POLLINATORS):
    return Upload.objects.create(module=module, name='u')


def _run(status=JobStatus.PENDING, module=Module.POLLINATORS, upload=None):
    return InferenceRun.objects.create(module=module, status=status, upload=upload)


class TestRunCreate:
    def test_create_run_pending(self, auth_client):
        up = _upload(Module.POLLINATORS)
        resp = auth_client.post(
            RUNS, {'module': 'pollinators', 'upload': up.pk}, format='json'
        )
        assert resp.status_code == 201
        assert InferenceRun.objects.get(upload=up).status == JobStatus.PENDING

    def test_module_mismatch_rejected(self, auth_client):
        up = _upload(Module.SEEDS)
        resp = auth_client.post(
            RUNS, {'module': 'pollinators', 'upload': up.pk}, format='json'
        )
        assert resp.status_code == 400


class TestRunList:
    def test_list_and_module_filter(self, auth_client):
        _run(module=Module.POLLINATORS)
        _run(module=Module.SEEDS)
        assert len(auth_client.get(RUNS).data) == 2
        assert len(auth_client.get(RUNS, {'module': 'seeds'}).data) == 1


class TestRunDetail:
    def test_get(self, auth_client):
        run = _run()
        assert auth_client.get(f'{RUNS}{run.pk}/').status_code == 200

    def test_delete_completed_run(self, auth_client, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        run = _run(status=JobStatus.COMPLETED)
        assert auth_client.delete(f'{RUNS}{run.pk}/').status_code == 204
        assert not InferenceRun.objects.filter(pk=run.pk).exists()

    def test_delete_in_flight_run_refused(self, auth_client):
        run = _run(status=JobStatus.PENDING)
        assert auth_client.delete(f'{RUNS}{run.pk}/').status_code == 400
        assert InferenceRun.objects.filter(pk=run.pk).exists()


class TestRunCancel:
    def test_cancel_sets_cancelled(self, auth_client):
        run = _run(status=JobStatus.PENDING)
        resp = auth_client.post(f'{RUNS}{run.pk}/cancel/')
        assert resp.status_code == 200
        run.refresh_from_db()
        assert run.status == JobStatus.CANCELLED

    def test_cancel_missing_returns_404(self, auth_client):
        assert auth_client.post(f'{RUNS}999999/cancel/').status_code == 404
