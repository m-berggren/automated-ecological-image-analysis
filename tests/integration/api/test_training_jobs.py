"""Integration tests for the training-job list / detail / cancel endpoints."""

import pytest

from apps.analysis.models import JobStatus, TrainingJob
from apps.datasets.models import Module

pytestmark = pytest.mark.django_db

TRAINING = '/api/analysis/training/'


def _job(status=JobStatus.PENDING, module=Module.POLLINATORS):
    return TrainingJob.objects.create(module=module, status=status)


class TestList:
    def test_list_and_module_filter(self, auth_client):
        _job(module=Module.POLLINATORS)
        _job(module=Module.SEEDS)
        assert len(auth_client.get(TRAINING).data) == 2
        assert len(auth_client.get(TRAINING, {'module': 'seeds'}).data) == 1


class TestDetail:
    def test_get(self, auth_client):
        job = _job()
        assert auth_client.get(f'{TRAINING}{job.pk}/').status_code == 200


class TestCancel:
    def test_cancel_pending(self, auth_client):
        job = _job(status=JobStatus.PENDING)
        resp = auth_client.post(f'{TRAINING}{job.pk}/cancel/')
        assert resp.status_code == 200
        job.refresh_from_db()
        assert job.status == JobStatus.CANCELLED

    def test_cancel_completed_is_conflict(self, auth_client):
        job = _job(status=JobStatus.COMPLETED)
        assert auth_client.post(f'{TRAINING}{job.pk}/cancel/').status_code == 409

    def test_cancel_missing_returns_404(self, auth_client):
        assert auth_client.post(f'{TRAINING}999999/cancel/').status_code == 404
