"""Unit tests for ml_pipelines.seed_src.training.slice_dataset.process_image.

Isolated-loaded (PIL + shapely). Uses the module's own SLICE_SIZE/STRIDE so the
tile grid matches production behaviour.
"""

import pytest
from PIL import Image


@pytest.fixture(scope='session')
def slice_dataset(load_leaf):
    return load_leaf('seed_src/training/slice_dataset.py')


def _dirs(tmp_path):
    img_dir = tmp_path / 'in_img'
    lbl_dir = tmp_path / 'in_lbl'
    out_img = tmp_path / 'out_img'
    out_lbl = tmp_path / 'out_lbl'
    for d in (img_dir, lbl_dir, out_img, out_lbl):
        d.mkdir()
    return img_dir, lbl_dir, out_img, out_lbl


def test_seed_centroid_kept_and_tiles_written(slice_dataset, tmp_path):
    img_dir, lbl_dir, out_img, out_lbl = _dirs(tmp_path)
    img_path = img_dir / 'frame.png'
    Image.new('RGB', (1000, 800)).save(img_path)
    # A small seed polygon centered at (500, 400) -> normalized coords.
    lbl_path = lbl_dir / 'frame.txt'
    lbl_path.write_text('cat 0.49 0.4875 0.51 0.4875 0.51 0.5125 0.49 0.5125\n')

    slice_dataset.process_image(str(img_path), str(lbl_path), str(out_img), str(out_lbl))

    # Grid: x in {0, 232}, y in {0, 32} -> 4 tiles, all contain the centroid.
    imgs = sorted(p.name for p in out_img.glob('*.png'))
    lbls = sorted(p.name for p in out_lbl.glob('*.txt'))
    assert len(imgs) == 4
    assert len(lbls) == 4

    # Every tile contains the centroid, so each label carries one 'cat' row
    # with 8 normalized coordinates in [0, 1].
    for lbl in out_lbl.glob('*.txt'):
        line = lbl.read_text().strip()
        parts = line.split()
        assert parts[0] == 'cat'
        coords = list(map(float, parts[1:]))
        assert len(coords) == 8
        assert all(0.0 <= c <= 1.0 for c in coords)


def test_image_without_label_writes_empty_label_files(slice_dataset, tmp_path):
    img_dir, lbl_dir, out_img, out_lbl = _dirs(tmp_path)
    img_path = img_dir / 'frame.png'
    Image.new('RGB', (1000, 800)).save(img_path)
    missing_label = lbl_dir / 'frame.txt'  # never created

    slice_dataset.process_image(
        str(img_path), str(missing_label), str(out_img), str(out_lbl)
    )

    assert len(list(out_img.glob('*.png'))) == 4
    lbls = list(out_lbl.glob('*.txt'))
    assert len(lbls) == 4
    assert all(lbl.read_text() == '' for lbl in lbls)
