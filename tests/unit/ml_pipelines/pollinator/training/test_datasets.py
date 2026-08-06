"""Unit tests for ml_pipelines.pollinator.training.datasets.

Isolated-loaded (the module imports torch.utils.data) so the pure letterbox
geometry and the tiny Dataset wrapper are exercised without the training stack.
"""

import pytest
from PIL import Image


@pytest.fixture(scope='session')
def datasets(load_leaf):
    return load_leaf('pollinator/training/datasets.py')


class TestLetterbox:
    def test_output_is_square_at_requested_size(self, datasets):
        img = Image.new('RGB', (10, 20), (255, 0, 0))
        out = datasets.letterbox(img, 8)
        assert out.size == (8, 8)
        assert out.mode == 'RGB'

    def test_already_square_input(self, datasets):
        img = Image.new('RGB', (4, 4), (0, 128, 0))
        out = datasets.letterbox(img, 16)
        assert out.size == (16, 16)


class TestCropDataset:
    def test_len_reflects_samples(self, datasets):
        ds = datasets.CropDataset([('a', 0), ('b', 1), ('c', 0)], transform=lambda x: x)
        assert len(ds) == 3

    def test_getitem_applies_transform_and_returns_label(self, datasets, tmp_path):
        path = tmp_path / 'crop.png'
        Image.new('RGB', (6, 9), (10, 20, 30)).save(path)
        ds = datasets.CropDataset([(str(path), 7)], transform=lambda im: im.size)
        sample, label = ds[0]
        assert sample == (6, 9)  # transform received the opened image
        assert label == 7

    def test_empty_samples_has_zero_length(self, datasets):
        ds = datasets.CropDataset([], transform=lambda x: x)
        assert len(ds) == 0

    def test_missing_file_raises(self, datasets, tmp_path):
        ds = datasets.CropDataset(
            [(str(tmp_path / 'gone.png'), 0)], transform=lambda x: x
        )
        with pytest.raises(FileNotFoundError):
            ds[0]
