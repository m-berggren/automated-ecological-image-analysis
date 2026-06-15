"""Integration tests for the seeds species-validation (OCR fallback) branch of
the image-upload endpoint. The easyocr-backed LabelExtractor is stubbed so the
branch is exercised without the real OCR model.
"""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.analysis.models import InferenceRun
from apps.datasets.models import Module, Upload

pytestmark = pytest.mark.django_db

IMAGES = '/api/datasets/images/'


class _FakeExtractor:
    text = ''

    def __init__(self, gpu=False):
        pass

    def extract_from_image(self, path):
        return type(self).text


def _png(name='photo.jpg'):
    buf = io.BytesIO()
    Image.new('RGB', (10, 10)).save(buf, 'JPEG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/jpeg')


@pytest.fixture
def seeds_upload():
    up = Upload.objects.create(module=Module.SEEDS, name='u')
    InferenceRun.objects.create(
        module=Module.SEEDS, upload=up, config={'selected_seed': 'cat'}
    )
    return up


def _post(client, upload):
    return client.post(
        IMAGES,
        {
            'file': _png(),
            'module': 'seeds',
            'purpose': 'inference',
            'upload': upload.pk,
        },
        format='multipart',
    )


def test_ocr_finds_species_accepts(
    auth_client, settings, tmp_path, monkeypatch, seeds_upload
):
    settings.MEDIA_ROOT = str(tmp_path)
    _FakeExtractor.text = 'CAT LABEL'  # filename lacks 'cat' -> OCR finds it
    monkeypatch.setattr('seed_src.utils.label_extractor.LabelExtractor', _FakeExtractor)
    assert _post(auth_client, seeds_upload).status_code == 201


def test_ocr_misses_species_rejects(
    auth_client, settings, tmp_path, monkeypatch, seeds_upload
):
    settings.MEDIA_ROOT = str(tmp_path)
    _FakeExtractor.text = 'nothing useful'
    monkeypatch.setattr('seed_src.utils.label_extractor.LabelExtractor', _FakeExtractor)
    assert _post(auth_client, seeds_upload).status_code == 400
