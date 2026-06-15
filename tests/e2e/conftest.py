"""Fixtures for the e2e lane.

e2e tests run real model weights. They are deselected by default (the addopts
marker filter) and live outside `testpaths`, so they only run when invoked
explicitly:

    AEA_E2E_YOLO_WEIGHTS=/path/to/yolo.pt pytest -m e2e tests/e2e

Each weights fixture skips cleanly when its env var is unset or points at a
missing file, so the lane is a no-op until real checkpoints are provided (e.g.
fetched from a GitHub Release in a dedicated CI job).
"""

import os
from pathlib import Path

import pytest
from PIL import Image


def _weight_or_skip(env_var: str) -> Path:
    value = os.environ.get(env_var)
    if not value:
        pytest.skip(f'{env_var} not set; e2e weights required')
    path = Path(value)
    if not path.is_file():
        pytest.skip(f'{env_var}={value!r} is not a file')
    return path


@pytest.fixture
def yolo_weights() -> Path:
    """Path to a trained YOLO .pt checkpoint, or skip the test."""
    return _weight_or_skip('AEA_E2E_YOLO_WEIGHTS')


@pytest.fixture
def sample_image(tmp_path) -> Path:
    path = tmp_path / 'sample.jpg'
    Image.new('RGB', (640, 640), (130, 140, 120)).save(path, 'JPEG')
    return path
