"""Integration tests for the dataset/zip staging endpoints:
pollinator detector-dataset upload, seeds upload-data, seeds training/start.

Covers validation/error paths plus a minimal valid-zip happy path for the
detector-dataset and seeds upload. The worker spawn in training/start is not
reached (validation rejects before it).
"""

import io
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.analysis.models import ModelKind, ModelVersion
from apps.datasets.models import Module

pytestmark = pytest.mark.django_db

DETECTOR_DATASET = '/api/pollinator/training/detector-dataset/'
SEED_UPLOAD = '/api/seeds/training/upload-data/'
SEED_START = '/api/seeds/training/start/'


def _jpeg(size=(20, 20)):
    buf = io.BytesIO()
    Image.new('RGB', size, (120, 120, 120)).save(buf, 'JPEG')
    return buf.getvalue()


def _detector_source():
    return ModelVersion.objects.create(
        module=Module.POLLINATORS,
        kind=ModelKind.DETECTOR,
        version_name='src',
        model_file_path='file://x',
    )


def _yolo_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('data.yaml', 'names: [bumblebee, fly, butterfly, other]\n')
        z.writestr('images/img1.jpg', _jpeg())
        z.writestr('labels/img1.txt', '0 0.5 0.5 0.2 0.2\n')
    return SimpleUploadedFile('ds.zip', buf.getvalue(), content_type='application/zip')


class TestDetectorDatasetUpload:
    def test_no_file_rejected(self, auth_client):
        src = _detector_source()
        resp = auth_client.post(
            DETECTOR_DATASET, {'from_model_version_id': src.pk}, format='multipart'
        )
        assert resp.status_code == 400

    def test_bad_source_rejected(self, auth_client):
        resp = auth_client.post(
            DETECTOR_DATASET,
            {'file': _yolo_zip(), 'from_model_version_id': 999999},
            format='multipart',
        )
        assert resp.status_code == 400

    def test_valid_zip_stages(self, auth_client, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        src = _detector_source()
        resp = auth_client.post(
            DETECTOR_DATASET,
            {'file': _yolo_zip(), 'from_model_version_id': src.pk},
            format='multipart',
        )
        assert resp.status_code == 200


class TestSeedUploadData:
    def test_missing_species_rejected(self, auth_client):
        resp = auth_client.post(SEED_UPLOAD, {}, format='multipart')
        assert resp.status_code == 400

    def test_no_files_rejected(self, auth_client):
        resp = auth_client.post(SEED_UPLOAD, {'species': 'cat'}, format='multipart')
        assert resp.status_code == 400

    def test_stages_and_returns_id(self, auth_client, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        img = SimpleUploadedFile('a.jpg', _jpeg(), content_type='image/jpeg')
        label = SimpleUploadedFile(
            'a.txt', b'0 0.5 0.5 0.2 0.2\n', content_type='text/plain'
        )
        resp = auth_client.post(
            SEED_UPLOAD, {'species': 'cat', 'files': [img, label]}, format='multipart'
        )
        assert resp.status_code in (200, 201)
        assert 'staging_id' in resp.data


class TestSeedTrainingStart:
    def test_missing_species_rejected(self, auth_client):
        assert auth_client.post(SEED_START, {}, format='json').status_code == 400

    def test_invalid_mode_rejected(self, auth_client):
        resp = auth_client.post(
            SEED_START, {'species': 'cat', 'training_mode': 'bogus'}, format='json'
        )
        assert resp.status_code == 400
