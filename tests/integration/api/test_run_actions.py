"""Integration tests for the run sub-action endpoints:
draft / start / pause / resume / abort / active / review-settings.

Worker spawns happen via transaction.on_commit, which does not fire inside the
test's rolled-back transaction, so start/resume never launch a real pipeline.
"""

import pytest

from apps.analysis.models import InferenceRun, JobStatus
from apps.datasets.models import ImageAsset, Module, Upload, UploadStatus

pytestmark = pytest.mark.django_db

RUNS = '/api/analysis/runs/'


def _upload(module=Module.POLLINATORS, status=UploadStatus.DRAFT):
    return Upload.objects.create(module=module, name='u', status=status)


def _image(upload, module=Module.POLLINATORS):
    return ImageAsset.objects.create(
        module=module, file='x.jpg', purpose='inference', upload=upload
    )


def _run(status=JobStatus.PENDING, module=Module.POLLINATORS, upload=None):
    return InferenceRun.objects.create(module=module, status=status, upload=upload)


class TestDraft:
    def test_creates_run_and_upload(self, auth_client):
        resp = auth_client.post(
            f'{RUNS}draft/', {'module': 'pollinators', 'config': {}}, format='json'
        )
        assert resp.status_code in (200, 201)
        assert 'run_id' in resp.data and 'upload_id' in resp.data
        assert InferenceRun.objects.filter(pk=resp.data['run_id']).exists()

    def test_invalid_module_rejected(self, auth_client):
        resp = auth_client.post(
            f'{RUNS}draft/', {'module': 'nope', 'config': {}}, format='json'
        )
        assert resp.status_code == 400


class TestStart:
    def test_start_draft_with_images(self, auth_client):
        up = _upload()
        _image(up)
        run = _run(status=JobStatus.PENDING, upload=up)
        resp = auth_client.post(f'{RUNS}{run.pk}/start/')
        assert resp.status_code == 200
        up.refresh_from_db()
        assert up.status == UploadStatus.READY  # draft -> ready, synchronously

    def test_non_pending_rejected(self, auth_client):
        run = _run(status=JobStatus.COMPLETED, upload=_upload())
        assert auth_client.post(f'{RUNS}{run.pk}/start/').status_code == 409

    def test_no_images_rejected(self, auth_client):
        run = _run(status=JobStatus.PENDING, upload=_upload())
        assert auth_client.post(f'{RUNS}{run.pk}/start/').status_code == 409

    def test_missing_returns_404(self, auth_client):
        assert auth_client.post(f'{RUNS}999999/start/').status_code == 404


class TestPause:
    def test_pause_running(self, auth_client):
        run = _run(status=JobStatus.RUNNING)
        resp = auth_client.post(f'{RUNS}{run.pk}/pause/')
        assert resp.status_code == 200
        run.refresh_from_db()
        assert run.status == JobStatus.PAUSED

    def test_pause_non_running_rejected(self, auth_client):
        run = _run(status=JobStatus.PENDING)
        assert auth_client.post(f'{RUNS}{run.pk}/pause/').status_code == 409

    def test_missing_returns_404(self, auth_client):
        assert auth_client.post(f'{RUNS}999999/pause/').status_code == 404


class TestResume:
    def test_resume_paused(self, auth_client):
        run = _run(status=JobStatus.PAUSED)
        resp = auth_client.post(f'{RUNS}{run.pk}/resume/')
        assert resp.status_code == 200
        run.refresh_from_db()
        assert run.status == JobStatus.PENDING  # re-queued for the worker

    def test_resume_non_paused_rejected(self, auth_client):
        run = _run(status=JobStatus.RUNNING)
        assert auth_client.post(f'{RUNS}{run.pk}/resume/').status_code == 409

    def test_missing_returns_404(self, auth_client):
        assert auth_client.post(f'{RUNS}999999/resume/').status_code == 404


class TestAbort:
    def test_abort_pending_deletes(self, auth_client, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        run = _run(status=JobStatus.PENDING, upload=_upload())
        resp = auth_client.post(f'{RUNS}{run.pk}/abort/')
        assert resp.status_code in (200, 204)
        assert not InferenceRun.objects.filter(pk=run.pk).exists()

    def test_abort_in_flight_rejected(self, auth_client):
        run = _run(status=JobStatus.COMPLETED, upload=_upload())
        assert auth_client.post(f'{RUNS}{run.pk}/abort/').status_code == 409

    def test_abort_missing_is_idempotent_success(self, auth_client):
        assert auth_client.post(f'{RUNS}999999/abort/').status_code == 204


class TestActive:
    def test_none_when_idle(self, auth_client):
        resp = auth_client.get(f'{RUNS}active/', {'module': 'pollinators'})
        assert resp.status_code == 200
        assert resp.data['active'] is None

    def test_returns_running_run(self, auth_client):
        _run(status=JobStatus.RUNNING, module=Module.POLLINATORS)
        resp = auth_client.get(f'{RUNS}active/', {'module': 'pollinators'})
        assert resp.data['active'] is not None

    def test_missing_module_rejected(self, auth_client):
        assert auth_client.get(f'{RUNS}active/').status_code == 400


class TestReviewSettings:
    def test_merge_partial_settings(self, auth_client):
        run = _run()
        resp = auth_client.post(
            f'{RUNS}{run.pk}/review-settings/', {'auto_select': True}, format='json'
        )
        assert resp.status_code == 200
        run.refresh_from_db()
        assert run.review_settings.get('auto_select') is True

    def test_missing_returns_404(self, auth_client):
        resp = auth_client.post(
            f'{RUNS}999999/review-settings/', {'auto_select': True}, format='json'
        )
        assert resp.status_code == 404
