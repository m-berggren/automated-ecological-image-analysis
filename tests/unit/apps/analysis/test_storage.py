"""Unit tests for apps.analysis.storage path/materialisation helpers.

MEDIA_ROOT is redirected to tmp via the pytest-django ``settings`` fixture.
The cloud-download branches of resolve_model_path (s3/gs) need boto3/network
and are out of scope here; only local/file passthrough and the unknown-scheme
guard are tested.
"""

from pathlib import Path

import pytest

from apps.analysis import storage


class TestModelDirAndWeightsPath:
    def test_model_dir(self, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        assert storage.model_dir('pollinators', 5) == tmp_path / 'models' / 'pollinators' / '5'

    def test_weights_path_adds_missing_dot(self, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        assert storage.weights_path('seeds', 3, 'pt').name == 'weights.pt'

    def test_weights_path_keeps_existing_dot(self, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        assert storage.weights_path('seeds', 3, '.pth').name == 'weights.pth'


class TestMoveWeightsIntoPlace:
    def test_moves_source_to_canonical_location(self, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        src = tmp_path / 'incoming.pt'
        src.write_bytes(b'weights')

        dst = storage.move_weights_into_place(src, 'pollinators', 9, 'pt')

        assert dst == storage.weights_path('pollinators', 9, 'pt')
        assert dst.read_bytes() == b'weights'
        assert not src.exists()


class TestLinkOrCopy:
    def test_materialises_destination(self, tmp_path):
        src = tmp_path / 'a.bin'
        src.write_bytes(b'data')
        dst = tmp_path / 'sub' / 'b.bin'
        dst.parent.mkdir()
        storage.link_or_copy(src, dst)
        assert dst.read_bytes() == b'data'

    def test_is_idempotent_and_skips_existing(self, tmp_path):
        src = tmp_path / 'a.bin'
        src.write_bytes(b'new')
        dst = tmp_path / 'b.bin'
        dst.write_bytes(b'original')  # already present
        storage.link_or_copy(src, dst)
        assert dst.read_bytes() == b'original'  # untouched


class TestResolveModelPath:
    def test_plain_local_path(self):
        assert storage.resolve_model_path('/models/x.pt') == Path('/models/x.pt')

    def test_file_uri(self):
        assert storage.resolve_model_path('file:///models/x.pt') == Path('/models/x.pt')

    def test_unknown_scheme_raises(self, monkeypatch, tmp_path):
        monkeypatch.setattr(storage, '_MODEL_CACHE', tmp_path / 'cache')
        with pytest.raises(ValueError):
            storage.resolve_model_path('ftp://host/key.pt')
