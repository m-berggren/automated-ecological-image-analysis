"""Integration smoke tests for the pollinator export endpoints
(export.csv, export-crops.zip, export-annotated.zip).

These assert the endpoints stream a 200 of the right kind for a small real run
and 404 for a missing run; exhaustive content checks are out of scope.
"""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.analysis.models import Detection, DetectionStatus, InferenceRun
from apps.datasets.models import ImageAsset, Module, Upload

pytestmark = pytest.mark.django_db


def _upload():
    return Upload.objects.create(module=Module.POLLINATORS, name='u')


def _run(upload=None):
    return InferenceRun.objects.create(module=Module.POLLINATORS, upload=upload)


def _real_image(upload):
    buf = io.BytesIO()
    Image.new('RGB', (20, 20), (120, 120, 120)).save(buf, 'PNG')
    return ImageAsset.objects.create(
        module=Module.POLLINATORS,
        file=SimpleUploadedFile('a.png', buf.getvalue(), content_type='image/png'),
        purpose='inference',
        upload=upload,
    )


def _accepted_det(run, img):
    return Detection.objects.create(
        inference_run=run,
        image=img,
        bbox={'x1': 1, 'y1': 1, 'x2': 10, 'y2': 10, 'w': 9, 'h': 9},
        confidence=0.9,
        area=81.0,
        predicted_class='fly',
        status=DetectionStatus.ACCEPTED,
    )


@pytest.fixture
def small_run(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    up = _upload()
    img = _real_image(up)
    run = _run(up)
    _accepted_det(run, img)
    return run


class TestExportCsv:
    def test_streams_csv(self, auth_client, small_run):
        resp = auth_client.get(f'/api/pollinator/runs/{small_run.pk}/export.csv')
        assert resp.status_code == 200
        assert 'csv' in resp['Content-Type'].lower()

    def test_missing_returns_404(self, auth_client):
        assert auth_client.get('/api/pollinator/runs/999999/export.csv').status_code == 404


class TestExportCropsZip:
    def test_returns_zip(self, auth_client, small_run):
        resp = auth_client.get(f'/api/pollinator/runs/{small_run.pk}/export-crops.zip')
        assert resp.status_code == 200

    def test_missing_returns_404(self, auth_client):
        resp = auth_client.get('/api/pollinator/runs/999999/export-crops.zip')
        assert resp.status_code == 404


class TestExportAnnotatedZip:
    def test_returns_zip(self, auth_client, small_run):
        resp = auth_client.get(
            f'/api/pollinator/runs/{small_run.pk}/export-annotated.zip'
        )
        assert resp.status_code == 200

    def test_missing_returns_404(self, auth_client):
        resp = auth_client.get('/api/pollinator/runs/999999/export-annotated.zip')
        assert resp.status_code == 404
