"""Integration tests for the datasets endpoints (upload batches + image upload)."""

import io

import pytest
from PIL import Image

from apps.datasets.models import ImageAsset, Module, Upload

pytestmark = pytest.mark.django_db

UPLOADS = '/api/datasets/uploads/'
IMAGES = '/api/datasets/images/'


def _png_upload(name='x.png'):
    from django.core.files.uploadedfile import SimpleUploadedFile

    buf = io.BytesIO()
    Image.new('RGB', (10, 10), (120, 120, 120)).save(buf, 'PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


class TestUploadCreate:
    def test_create_returns_201_and_links_user(self, auth_client, user):
        resp = auth_client.post(
            UPLOADS, {'name': 'batch1', 'module': 'pollinators'}, format='json'
        )
        assert resp.status_code == 201
        assert resp.data['name'] == 'batch1'
        assert resp.data['image_count'] == 0
        assert Upload.objects.get(pk=resp.data['id']).uploaded_by == user


class TestUploadList:
    def test_list_and_module_filter(self, auth_client):
        Upload.objects.create(module=Module.POLLINATORS, name='p')
        Upload.objects.create(module=Module.SEEDS, name='s')
        assert len(auth_client.get(UPLOADS).data) == 2
        filtered = auth_client.get(UPLOADS, {'module': 'seeds'})
        assert [u['name'] for u in filtered.data] == ['s']


class TestUploadDetail:
    def test_get(self, auth_client):
        up = Upload.objects.create(module=Module.POLLINATORS, name='x')
        resp = auth_client.get(f'{UPLOADS}{up.pk}/')
        assert resp.status_code == 200
        assert resp.data['name'] == 'x'

    def test_patch_rename(self, auth_client):
        up = Upload.objects.create(module=Module.POLLINATORS, name='old')
        resp = auth_client.patch(f'{UPLOADS}{up.pk}/', {'name': 'new'}, format='json')
        assert resp.status_code == 200
        up.refresh_from_db()
        assert up.name == 'new'


class TestImageUpload:
    def test_upload_image_creates_asset(self, auth_client, user, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        # module=seeds without an upload skips OCR/EXIF, exercising the plain
        # create path with a real (validated) image file.
        resp = auth_client.post(
            IMAGES,
            {'file': _png_upload(), 'module': 'seeds', 'purpose': 'inference'},
            format='multipart',
        )
        assert resp.status_code == 201
        assert ImageAsset.objects.filter(pk=resp.data['id']).exists()
