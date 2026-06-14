"""Shared fixtures for the ml_pipelines unit tests.

Most modules import cleanly via their package path. The training leaf modules
(`splits`, `sampling`, `slicing`) and `seed_src` utilities are pure logic but
live under packages whose ``__init__`` pulls in the full torch/ultralytics
training stack. `load_leaf` loads such a module directly from its file so a
pathlib/numpy unit test never has to import a deep-learning framework.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ML_PIPELINES = REPO_ROOT / 'ml_pipelines'


@pytest.fixture(scope='session')
def load_leaf():
    """Return a loader for a single ml_pipelines module, bypassing package
    ``__init__`` side effects. Path is relative to ``ml_pipelines/``."""
    cache: dict[str, object] = {}

    def _load(relpath: str):
        if relpath in cache:
            return cache[relpath]
        path = ML_PIPELINES / relpath
        name = 'leaf_' + relpath.replace('/', '_').removesuffix('.py')
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        cache[relpath] = module
        return module

    return _load
