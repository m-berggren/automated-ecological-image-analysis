"""Integration tests for POST /api/pollinator/training/.

The worker spawn is stubbed (the runner boundary): these assert the job is
created/validated and the busy-guard fires, not that training runs. Actual
training is an e2e concern.
"""

import pytest

from apps.analysis.models import JobStatus, ModelVersion, TrainingJob
from apps.datasets.models import Module
from apps.pollinator.training import PER_TRACK_DEFAULTS

pytestmark = pytest.mark.django_db

CREATE = '/api/pollinator/training/'
TRACK = next(iter(PER_TRACK_DEFAULTS))
KIND = PER_TRACK_DEFAULTS[TRACK]['kind']


@pytest.fixture(autouse=True)
def _no_spawn(monkeypatch):
    monkeypatch.setattr('apps.pollinator.views.spawn_training_job', lambda job: None)


def _source():
    return ModelVersion.objects.create(
        module=Module.POLLINATORS, kind=KIND, version_name='src', model_file_path='file://x'
    )


def _config(src):
    return {'config': {'track': TRACK, 'from_model_version_id': src.pk}}


def test_creates_pending_job(auth_client):
    src = _source()
    resp = auth_client.post(CREATE, _config(src), format='json')
    assert resp.status_code == 201
    assert (
        TrainingJob.objects.filter(
            module=Module.POLLINATORS, status=JobStatus.PENDING
        ).count()
        == 1
    )


def test_invalid_config_rejected(auth_client):
    resp = auth_client.post(CREATE, {'config': {'track': 'bogus'}}, format='json')
    assert resp.status_code == 400


def test_busy_returns_409(auth_client):
    src = _source()
    TrainingJob.objects.create(module=Module.POLLINATORS, status=JobStatus.RUNNING)
    resp = auth_client.post(CREATE, _config(src), format='json')
    assert resp.status_code == 409
