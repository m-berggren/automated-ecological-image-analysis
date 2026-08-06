"""Integration test for POST /api/analysis/models/ (weights upload).

Exercises the checkpoint-introspection + file-write path with a tiny real
torch checkpoint, so the upload view and _introspect_checkpoint helper are
covered without a production-size model.
"""

import torch
from django.core.files.uploadedfile import SimpleUploadedFile

import pytest

from apps.analysis.models import ModelVersion

pytestmark = pytest.mark.django_db

MODELS = '/api/analysis/models/'


def _checkpoint(tmp_path):
    path = tmp_path / 'w.pt'
    torch.save({'img_size': 640, 'arch': 'yolov8', 'epoch': -1}, path)
    return SimpleUploadedFile(
        'w.pt', path.read_bytes(), content_type='application/octet-stream'
    )


def test_upload_creates_model_version(auth_client, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    resp = auth_client.post(
        MODELS,
        {
            'module': 'pollinators',
            'kind': 'detector',
            'version_name': 'uploaded-v1',
            'weights_file': _checkpoint(tmp_path),
        },
        format='multipart',
    )
    assert resp.status_code in (200, 201)
    mv = ModelVersion.objects.get(version_name='uploaded-v1')
    # img_size was introspected from the checkpoint; epoch=-1 sentinel dropped.
    assert mv.parameters.get('img_size') == 640
    assert 'epoch' not in mv.parameters
